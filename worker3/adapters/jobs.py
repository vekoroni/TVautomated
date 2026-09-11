"""SQLite durable job state, conservative dispatch recovery, no provider imports."""
from contextlib import contextmanager
import json
import sqlite3
import uuid
import math

from ..domain import ContractError, canonical, digest, nonempty, sha, utc


def valid_time(now):
    if type(now) not in (int,float) or not math.isfinite(now) or now < 0:
        raise ContractError("finite nonnegative clock required")


class JobStore:
    def __init__(self, path, *, budget_microusd):
        if type(budget_microusd) is not int or budget_microusd <= 0:
            raise ContractError("positive explicit monetary budget required")
        self.db = sqlite3.connect(str(path), isolation_level=None, timeout=10)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA synchronous=FULL")
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS settings (id INTEGER PRIMARY KEY CHECK(id=1), budget INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, run_id TEXT NOT NULL, ticker TEXT NOT NULL, payload TEXT NOT NULL,
          status TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, max_attempts INTEGER NOT NULL,
          ceiling INTEGER NOT NULL, available REAL NOT NULL, lease_until REAL, token TEXT,
          response TEXT, reason TEXT);
        CREATE TABLE IF NOT EXISTS charges (
          token TEXT PRIMARY KEY, job_id TEXT NOT NULL, reserved INTEGER NOT NULL,
          cost INTEGER, receipt TEXT);
        CREATE TABLE IF NOT EXISTS events (
          seq INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL, at REAL NOT NULL,
          state TEXT NOT NULL, reason TEXT);
        CREATE TABLE IF NOT EXISTS intakes (
          id TEXT PRIMARY KEY, run_id TEXT NOT NULL, invocation_id TEXT NOT NULL,
          ticker TEXT NOT NULL, status TEXT NOT NULL, evidence_hash TEXT,
          job_id TEXT, reason_code TEXT, reason TEXT, payload_hash TEXT NOT NULL,
          at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS activations (
          id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE,
          release_id TEXT NOT NULL, release_hash TEXT NOT NULL,
          operator_approval_id TEXT NOT NULL, at REAL NOT NULL);
        CREATE TABLE IF NOT EXISTS assessment_index (
          assessment_id TEXT PRIMARY KEY, job_id TEXT NOT NULL UNIQUE,
          run_id TEXT NOT NULL, ticker TEXT NOT NULL, context_hash TEXT NOT NULL,
          evidence_cutoff TEXT NOT NULL, generated_at TEXT NOT NULL);
        ''')
        try:
            with self.transaction():
                row = self.db.execute("SELECT budget FROM settings WHERE id=1").fetchone()
                if row is None:
                    self.db.execute("INSERT INTO settings VALUES(1,?)", (budget_microusd,))
                elif row[0] != budget_microusd:
                    raise ContractError("stored budget differs; cannot silently reset it")
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    @contextmanager
    def transaction(self):
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def event(self, job_id, now, state, reason=None):
        self.db.execute("INSERT INTO events(job_id,at,state,reason) VALUES(?,?,?,?)", (job_id,now,state,reason))

    def enqueue(self, *, run_id, ticker, job_key, context_hash, request_fingerprint,
                payload, now, max_attempts=3, call_ceiling_microusd=100000):
        valid_time(now)
        for value in (run_id,ticker): nonempty(value,"job identity")
        for value in (job_key,context_hash,request_fingerprint): sha(value)
        if any(type(v) is not int or v <= 0 for v in (max_attempts,call_ceiling_microusd)):
            raise ContractError("positive retry/call-cost limits required")
        raw = canonical(payload)
        # Hash all material configuration, including model request, evidence and policy.
        job_id = digest({"run":run_id,"ticker":ticker,"job":job_key,"context":context_hash,
                         "request":request_fingerprint,"payload":raw,
                         "attempts":max_attempts,"ceiling":call_ceiling_microusd})
        with self.transaction():
            self.db.execute("INSERT OR IGNORE INTO jobs(id,run_id,ticker,payload,status,max_attempts,ceiling,available) VALUES(?,?,?,?,?,?,?,?)",
                            (job_id,run_id,ticker,raw,"QUEUED",max_attempts,call_ceiling_microusd,now))
            if self.db.execute("SELECT changes()").fetchone()[0]: self.event(job_id,now,"QUEUED")
        return job_id

    def stage_prepared(self, *, run_id, ticker, job_key, context_hash,
                       request_fingerprint, payload, now, max_attempts=3,
                       call_ceiling_microusd=100000):
        """Persist an idempotent job that no dispatcher can claim yet."""
        valid_time(now)
        for value in (run_id, ticker):
            nonempty(value, "job identity")
        for value in (job_key, context_hash, request_fingerprint):
            sha(value)
        if any(type(value) is not int or value <= 0
               for value in (max_attempts, call_ceiling_microusd)):
            raise ContractError("positive retry/call-cost limits required")
        raw = canonical(payload)
        if len(raw.encode("utf-8")) > 2_000_000:
            raise ContractError("prepared job exceeds durable payload limit")
        job_id = digest({"run": run_id, "ticker": ticker, "job": job_key,
                         "context": context_hash, "request": request_fingerprint,
                         "payload": raw, "attempts": max_attempts,
                         "ceiling": call_ceiling_microusd,
                         "initial_status": "PREPARED"})
        with self.transaction():
            self.db.execute(
                """INSERT OR IGNORE INTO jobs
                   (id,run_id,ticker,payload,status,max_attempts,ceiling,available)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (job_id, run_id, ticker, raw, "PREPARED", max_attempts,
                 call_ceiling_microusd, now),
            )
            if self.db.execute("SELECT changes()").fetchone()[0]:
                self.event(job_id, now, "PREPARED", "PROVIDER_DISPATCH_DISABLED")
        return job_id

    def record_intake(self, *, run_id, invocation_id, ticker, status,
                      payload_hash, now, evidence_hash=None, job_id=None,
                      reason_code=None, reason=None):
        valid_time(now)
        for value in (run_id, invocation_id, ticker):
            nonempty(value, "intake identity")
        if status not in ("JOB_PREPARED", "DATA_EXCEPTION"):
            raise ContractError("unsupported intake status")
        sha(payload_hash)
        if evidence_hash is not None:
            sha(evidence_hash)
        if status == "JOB_PREPARED":
            nonempty(job_id, "prepared job id")
            if reason_code is not None or reason is not None:
                raise ContractError("prepared intake cannot carry an exception")
        else:
            nonempty(reason_code, "data exception reason code")
            nonempty(reason, "data exception reason")
            if len(reason) > 2000:
                raise ContractError("data exception reason exceeds limit")
            if evidence_hash is not None or job_id is not None:
                raise ContractError("data exception cannot carry a prepared job")
        intake_id = digest({"run": run_id, "invocation": invocation_id,
                            "ticker": ticker, "status": status,
                            "evidence": evidence_hash, "job": job_id,
                            "reason_code": reason_code, "reason": reason,
                            "payload_hash": payload_hash})
        with self.transaction():
            existing = self.db.execute(
                "SELECT * FROM intakes WHERE id=?", (intake_id,)
            ).fetchone()
            values = (intake_id, run_id, invocation_id, ticker, status,
                      evidence_hash, job_id, reason_code, reason, payload_hash, now)
            if existing is None:
                self.db.execute("INSERT INTO intakes VALUES(?,?,?,?,?,?,?,?,?,?,?)", values)
            else:
                comparable = tuple(existing[key] for key in (
                    "id", "run_id", "invocation_id", "ticker", "status",
                    "evidence_hash", "job_id", "reason_code", "reason", "payload_hash"
                ))
                if comparable != values[:-1]:
                    raise ContractError("immutable intake conflict")
        return intake_id

    def intake_progress(self, run_id):
        return [dict(row) for row in self.db.execute(
            """SELECT id,ticker,status,evidence_hash,job_id,reason_code,reason,payload_hash,at
               FROM intakes WHERE run_id=? ORDER BY ticker,id""", (run_id,)
        )]

    def job_record(self, job_id):
        row = self.db.execute(
            "SELECT id,run_id,ticker,payload,status,attempts,max_attempts,ceiling,reason FROM jobs WHERE id=?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def record_assessment(self, *, assessment_id, job_id, run_id, ticker,
                          context_hash, evidence_cutoff, generated_at):
        """Index one validated projection without duplicating its immutable payload."""
        for value in (assessment_id, context_hash):
            sha(value)
        for value in (job_id, run_id, ticker):
            nonempty(value, "assessment identity")
        evidence_cutoff = utc(evidence_cutoff)
        generated_at = utc(generated_at)
        with self.transaction():
            job = self.db.execute(
                "SELECT run_id,ticker,payload,status,response FROM jobs WHERE id=?",
                (job_id,),
            ).fetchone()
            if job is None or job["status"] != "REVIEW_REQUIRED" or job["response"] is None:
                raise ContractError("assessment requires a durable validated response")
            if (job["run_id"], job["ticker"]) != (run_id, ticker):
                raise ContractError("assessment index differs from durable job identity")
            payload = json.loads(job["payload"])
            response = json.loads(job["response"])
            if (
                payload.get("context_hash") != context_hash
                or response.get("context_hash") != context_hash
                or utc(response.get("generated_at")) != generated_at
            ):
                raise ContractError("assessment index differs from validated response")
            values = (
                assessment_id, job_id, run_id, ticker, context_hash,
                evidence_cutoff, generated_at,
            )
            existing = self.db.execute(
                "SELECT * FROM assessment_index WHERE assessment_id=? OR job_id=?",
                (assessment_id, job_id),
            ).fetchone()
            if existing is not None:
                comparable = tuple(existing[key] for key in (
                    "assessment_id", "job_id", "run_id", "ticker", "context_hash",
                    "evidence_cutoff", "generated_at",
                ))
                if comparable != values:
                    raise ContractError("immutable assessment index conflict")
            else:
                self.db.execute(
                    "INSERT INTO assessment_index VALUES(?,?,?,?,?,?,?)", values
                )
        return assessment_id

    def assessment_record(self, assessment_id):
        sha(assessment_id)
        row = self.db.execute(
            "SELECT * FROM assessment_index WHERE assessment_id=?",
            (assessment_id,),
        ).fetchone()
        return dict(row) if row else None

    def completed_job_records(self):
        """Return only jobs with durable responses, for hash-verified index backfill."""
        rows = self.db.execute(
            """SELECT id,run_id,ticker,payload,status,attempts,max_attempts,
                      ceiling,reason
               FROM jobs
               WHERE status='REVIEW_REQUIRED' AND response IS NOT NULL
               ORDER BY id"""
        ).fetchall()
        result = []
        for row in rows:
            value = dict(row)
            value["payload"] = json.loads(value["payload"])
            result.append(value)
        return result

    def activate_prepared(self, job_id, *, release_id, release_hash,
                          operator_approval_id, now):
        """Explicit audited PREPARED -> QUEUED transition; never dispatches."""
        return self.activate_prepared_batch(
            (job_id,), release_id=release_id, release_hash=release_hash,
            operator_approval_id=operator_approval_id,
            max_total_ceiling=2**63 - 1, now=now,
        )[0]

    def activate_prepared_batch(self, job_ids, *, release_id, release_hash,
                                operator_approval_id, max_total_ceiling, now):
        """Atomically activate a release-bound batch within its cumulative ceiling."""
        valid_time(now)
        for value in (release_id, operator_approval_id):
            nonempty(value, "activation identity")
        sha(release_hash)
        if (type(job_ids) is not tuple or not job_ids
                or len(set(job_ids)) != len(job_ids)):
            raise ContractError("activation requires unique immutable job ids")
        if type(max_total_ceiling) is not int or max_total_ceiling <= 0:
            raise ContractError("positive release activation ceiling required")
        for job_id in job_ids:
            nonempty(job_id, "activation job id")
        activation_ids = tuple(digest({
            "job": job_id, "release": release_id,
            "release_hash": release_hash,
            "operator_approval": operator_approval_id,
        }) for job_id in job_ids)
        with self.transaction():
            already_reserved = self.db.execute(
                """SELECT COALESCE(SUM(j.ceiling),0)
                   FROM activations a JOIN jobs j ON j.id=a.job_id
                   WHERE a.release_id=? AND a.release_hash=?""",
                (release_id, release_hash),
            ).fetchone()[0]
            pending = []
            added_ceiling = 0
            for job_id, activation_id in zip(job_ids, activation_ids):
                row = self.db.execute(
                    "SELECT status,ceiling FROM jobs WHERE id=?", (job_id,)
                ).fetchone()
                if row is None:
                    raise ContractError("prepared job not found")
                prior = self.db.execute(
                    "SELECT * FROM activations WHERE job_id=?", (job_id,)
                ).fetchone()
                if prior is not None:
                    if prior["id"] != activation_id:
                        raise ContractError("job already activated by a different release")
                    continue
                if row["status"] != "PREPARED":
                    raise ContractError("only PREPARED jobs can be activated")
                added_ceiling += row["ceiling"]
                pending.append((job_id, activation_id))
            if already_reserved + added_ceiling > max_total_ceiling:
                raise ContractError("cumulative activation exceeds release cost ceiling")
            for job_id, activation_id in pending:
                self.db.execute(
                    "INSERT INTO activations VALUES(?,?,?,?,?,?)",
                    (activation_id, job_id, release_id, release_hash,
                     operator_approval_id, now),
                )
                self.db.execute(
                    "UPDATE jobs SET status='QUEUED',available=?,reason=NULL WHERE id=?",
                    (now, job_id),
                )
                self.event(job_id, now, "QUEUED", "CONTROLLED_PROVIDER_ACTIVATION")
        return activation_ids

    def activation_record(self, job_id):
        row = self.db.execute(
            "SELECT * FROM activations WHERE job_id=?", (job_id,)
        ).fetchone()
        return dict(row) if row else None

    def claim(self, *, now, lease_seconds=60, job_id=None):
        valid_time(now)
        if type(lease_seconds) not in (int,float) or not 0 < lease_seconds <= 3600:
            raise ContractError("bounded lease required")
        with self.transaction():
            row = self.db.execute("SELECT * FROM jobs WHERE status IN ('QUEUED','RETRY_WAIT') AND available<=? AND attempts<max_attempts AND (? IS NULL OR id=?) ORDER BY available,id LIMIT 1",(now,job_id,job_id)).fetchone()
            if row is None: return None
            token = uuid.uuid4().hex
            self.db.execute("UPDATE jobs SET status='LEASED',token=?,lease_until=?,attempts=attempts+1 WHERE id=?",(token,now+lease_seconds,row['id']))
            self.event(row['id'],now,"LEASED")
            return {"id":row['id'],"token":token,"payload":json.loads(row['payload'])}

    def owned(self, job_id, token, status, now):
        valid_time(now)
        row = self.db.execute("SELECT * FROM jobs WHERE id=?",(job_id,)).fetchone()
        if row is None or row['token'] != token or row['status'] != status or row['lease_until'] <= now:
            raise ContractError("lease expired, fenced or wrong job state")
        return row

    def dispatch(self, job_id, token, *, now):
        with self.transaction():
            row=self.owned(job_id,token,"LEASED",now)
            spent=self.db.execute("SELECT COALESCE(SUM(COALESCE(cost,reserved)),0) FROM charges").fetchone()[0]
            budget=self.db.execute("SELECT budget FROM settings WHERE id=1").fetchone()[0]
            if spent+row['ceiling'] > budget:
                raise ContractError("budget unavailable; unknown calls retain reservations")
            self.db.execute("INSERT INTO charges(token,job_id,reserved) VALUES(?,?,?)",(token,job_id,row['ceiling']))
            self.db.execute("UPDATE jobs SET status='DISPATCHED' WHERE id=?",(job_id,))
            self.event(job_id,now,"DISPATCHED")

    def finish(self, job_id, token, *, now, response, receipt, cost_microusd=None):
        if cost_microusd is not None and (type(cost_microusd) is not int or cost_microusd < 0):
            raise ContractError("cost must be explicit nonnegative microusd or unknown")
        raw, usage=canonical(response),canonical(receipt)
        with self.transaction():
            self.owned(job_id,token,"DISPATCHED",now)
            self.db.execute("UPDATE charges SET cost=?,receipt=? WHERE token=?",(cost_microusd,usage,token))
            self.db.execute("UPDATE jobs SET status='REVIEW_REQUIRED',response=?,lease_until=NULL WHERE id=?",(raw,job_id))
            self.event(job_id,now,"REVIEW_REQUIRED")

    def fail_before_send(self, job_id, token, *, now, reason_code, delay_seconds=30):
        nonempty(reason_code,"reason code")
        if type(delay_seconds) not in (int,float) or not 0 <= delay_seconds <= 3600:
            raise ContractError("bounded retry delay required")
        with self.transaction():
            row=self.owned(job_id,token,"LEASED",now)
            state="FAILED" if row['attempts']>=row['max_attempts'] else "RETRY_WAIT"
            self.db.execute("UPDATE jobs SET status=?,available=?,lease_until=NULL,token=NULL,reason=? WHERE id=?",(state,now+delay_seconds,reason_code,job_id))
            self.event(job_id,now,state,reason_code)

    def recover(self, *, now):
        valid_time(now)
        with self.transaction():
            rows=self.db.execute("SELECT * FROM jobs WHERE status IN ('LEASED','DISPATCHED') AND lease_until<=?",(now,)).fetchall()
            for row in rows:
                state="UNCERTAIN" if row['status']=="DISPATCHED" else "FAILED" if row['attempts']>=row['max_attempts'] else "RETRY_WAIT"
                self.db.execute("UPDATE jobs SET status=?,available=?,token=NULL,lease_until=NULL WHERE id=?",(state,now,row['id']))
                self.event(row['id'],now,state,"LEASE_EXPIRED")
            return len(rows)

    def progress(self, run_id):
        return [dict(r) for r in self.db.execute("SELECT id,ticker,status,attempts,max_attempts,reason FROM jobs WHERE run_id=? ORDER BY ticker,id",(run_id,))]

    def completed_result(self, job_id):
        row=self.db.execute("SELECT response FROM jobs WHERE id=? AND status='REVIEW_REQUIRED'",(job_id,)).fetchone()
        return json.loads(row[0]) if row else None

    def accounting(self):
        row=self.db.execute("SELECT COALESCE(SUM(cost),0),COALESCE(SUM(CASE WHEN cost IS NULL THEN reserved ELSE 0 END),0),SUM(CASE WHEN cost IS NULL THEN 1 ELSE 0 END) FROM charges").fetchone()
        return {"reported_cost_microusd":row[0],"unknown_cost_reservation_microusd":row[1],"unknown_calls":row[2] or 0}

    def mark_uncertain(self, job_id, token, *, now, receipt=None):
        usage = canonical(receipt) if receipt is not None else None
        with self.transaction():
            self.owned(job_id,token,"DISPATCHED",now)
            if usage is not None:
                self.db.execute("UPDATE charges SET receipt=? WHERE token=?", (usage, token))
            self.db.execute("UPDATE jobs SET status='UNCERTAIN',lease_until=NULL,token=NULL WHERE id=?",(job_id,))
            self.event(job_id,now,"UNCERTAIN","PROVIDER_OUTCOME_UNCERTAIN")


def execute_one(store, executor, *, clock, lease_seconds=120):
    """Executor is responsible for v2/semantic validation; never grant authority.

    Callback returns response, sanitized receipt, explicit cost or None. Persist
    dispatch before calling it. Any error after dispatch needs reconciliation.
    """
    claim=store.claim(now=clock(),lease_seconds=lease_seconds)
    if claim is None: return None
    store.dispatch(claim['id'],claim['token'],now=clock())
    try:
        response,receipt,cost=executor(claim['payload'])
        store.finish(claim['id'],claim['token'],now=clock(),response=response,receipt=receipt,cost_microusd=cost)
        return "REVIEW_REQUIRED"
    except Exception:
        try:
            store.mark_uncertain(claim['id'],claim['token'],now=clock())
        except ContractError:
            store.recover(now=clock())
        return "UNCERTAIN"

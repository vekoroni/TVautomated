"""p10_A_run_inventory.py -- Track A / A1 + REQ-WP0-01 field presence.
Read-only. For every run directory with a run_meta.json, derive evidence cutoff, XNYS session
state at cutoff, recorded/inferred run condition, dirty flag, provider completeness (recorded or
computed), quote timestamp distribution (options_intelligence), and row counts.
Writes: audit/td/AVS-TD-001/run_inventory.csv and probes/p10_A_run_inventory_out.json
"""
import csv, json, os, re, sys, statistics, sqlite3
from datetime import datetime, timedelta, timezone, date
import pandas as pd

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
CP_DB = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "db_copies", "control_plane.sqlite")
RP_DB = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "db_copies", "run_plans.sqlite")
RUNS = os.path.join(ROOT, "data", "output", "runs")
OUT_CSV = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "run_inventory.csv")
OUT_JSON = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_run_inventory_out.json")

ET_OFFSET = timedelta(hours=-4)  # EDT, valid for all stored runs (Jul-Sep 2026)
XNYS_HOLIDAYS = {date(2026, 7, 3), date(2026, 9, 7)}  # Independence Day observed, Labor Day

REQ01_FIELDS = ["run_condition", "baseline_eligible", "code_identity", "config_identity", "session_date",
                "evidence_cutoff_utc", "operator_mode", "provider_completeness_evidence", "macro_packet_id"]
COND_VOCAB = re.compile(r"NORMAL_COMPLETED_SESSION|FORCED_INTRASESSION|PREOPEN_THESIS_CHECK|POSTOPEN_CONTRACT_REFRESH|REPLAY|\bTEST\b")


def parse_ts(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return None
    s = s.replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def session_state(ts_utc):
    et = ts_utc + ET_OFFSET
    if et.weekday() >= 5:
        return "WEEKEND"
    if et.date() in XNYS_HOLIDAYS:
        return "HOLIDAY"
    t = et.time()
    if t < datetime.strptime("09:30", "%H:%M").time():
        return "PRE_OPEN"
    if t < datetime.strptime("16:00", "%H:%M").time():
        return "INTRA_SESSION"
    return "POST_CLOSE"


def last_completed_session(ts_utc):
    """Most recent XNYS session whose 16:00 ET close is <= ts."""
    et = ts_utc + ET_OFFSET
    d = et.date()
    if et.time() < datetime.strptime("16:00", "%H:%M").time():
        d = d - timedelta(days=1)
    while d.weekday() >= 5 or d in XNYS_HOLIDAYS:
        d -= timedelta(days=1)
    return d


def find_nested(obj, key):
    """Return first value for key anywhere in nested dict/list, else None."""
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = find_nested(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find_nested(v, key)
            if r is not None:
                return r
    return None


def count_csv_rows(path):
    try:
        return int(len(pd.read_csv(path, usecols=[0], low_memory=False)))
    except Exception as e:  # noqa
        return f"ERR:{type(e).__name__}"


def quote_ts_distribution(oi_path, anchor):
    """From options_intelligence csv: n quotes, min/median/max provider ts, same-session fraction,
    per-ticker max-ts fraction >= 20:00 UTC on anchor, and column used."""
    res = {"col": None, "n": 0, "min": None, "median": None, "max": None, "same_session_frac": None,
           "ticker_max_ge_close_frac": None, "n_tickers": None, "no_ts": None}
    if not os.path.exists(oi_path):
        return res
    with open(oi_path, encoding="utf-8", errors="replace") as fh:
        hdr = next(csv.reader(fh))
    cands = [c for c in ["quote_as_of", "contract_quote_timestamp_utc", "quote_timestamp_utc", "l2_quote_timestamp_utc"] if c in hdr]
    if not cands:
        res["col"] = "NO_QUOTE_TS_COLUMN"
        return res
    col = cands[0]
    tcol = "ticker" if "ticker" in hdr else ("symbol" if "symbol" in hdr else None)
    use = [col] + ([tcol] if tcol else [])
    df = pd.read_csv(oi_path, usecols=use, low_memory=False)
    ts = df[col].map(parse_ts)
    valid = ts.dropna()
    res["col"] = col
    res["n"] = int(len(df))
    res["no_ts"] = int(len(df) - len(valid))
    if len(valid) == 0:
        return res
    vs = sorted(valid)
    res["min"] = vs[0].isoformat()
    res["max"] = vs[-1].isoformat()
    res["median"] = vs[len(vs) // 2].isoformat()
    res["same_session_frac"] = round(sum(1 for v in vs if v.date() == anchor) / len(vs), 4)
    if tcol:
        close_utc = datetime.combine(anchor, datetime.strptime("20:00", "%H:%M").time(), tzinfo=timezone.utc)
        g = pd.DataFrame({"t": df[tcol], "ts": ts}).dropna().groupby("t")["ts"].max()
        res["n_tickers"] = int(len(g))
        res["ticker_max_ge_close_frac"] = round(float((g >= close_utc).mean()), 4) if len(g) else None
    return res


def db_context():
    """run_registry (control_plane copy), run_plans payload session_state/operational_context (run_plans copy),
    api_request_ledger min/max started_at and count of requests started after the evidence cutoff."""
    reg, plans, ledger = {}, {}, {}
    try:
        c = sqlite3.connect(f"file:{CP_DB}?mode=ro", uri=True)
        for run_id, run_type, sd, st in c.execute("select run_id, run_type, session_date, started_at from run_registry"):
            reg[run_id] = {"run_type": run_type, "session_date": sd, "started_at": st}
        for run_id, n, mn, mx, phys in c.execute("select run_id, count(*), min(started_at), max(started_at), coalesce(sum(physical_request_count),0) from api_request_ledger group by run_id"):
            ledger[run_id] = {"n": n, "min_started_at": mn, "max_started_at": mx, "physical": phys}
        c.close()
    except Exception as e:
        reg["__error__"] = str(e)
    try:
        p = sqlite3.connect(f"file:{RP_DB}?mode=ro", uri=True)
        for run_id, cutoff, payload in p.execute("select pipeline_run_id, evidence_cutoff_utc, payload_json from run_plans order by persisted_at_utc"):
            j = json.loads(payload)
            plans.setdefault(run_id, []).append({"evidence_cutoff_utc": cutoff, "session_state": j.get("session_state"), "operational_context": j.get("operational_context"),
                                                 "requested_action": j.get("requested_action"), "resolved_action": j.get("resolved_action"),
                                                 "vocab": sorted(set(COND_VOCAB.findall(payload)))})
        p.close()
    except Exception as e:
        plans["__error__"] = str(e)
    return reg, plans, ledger


def main():
    rows = []
    detail = {}
    reg, plans, ledger = db_context()
    for run_id in sorted(os.listdir(RUNS)):
        rd = os.path.join(RUNS, run_id)
        rm_path = os.path.join(rd, "run_meta.json")
        if not os.path.isdir(rd) or not os.path.exists(rm_path):
            continue
        rm = json.load(open(rm_path, encoding="utf-8"))
        plan = rm.get("dynamic_plan") or {}
        cutoff_rec = plan.get("evidence_cutoff_utc")
        cutoff_src = "dynamic_plan.evidence_cutoff_utc"
        cutoff = parse_ts(cutoff_rec)
        if cutoff is None:
            # fall back: run_id is a UTC stamp (verified: 20260911_115904 == 2026-09-11T11:59:04Z)
            m = re.match(r"(\d{8})_(\d{6})$", run_id)
            if m:
                cutoff = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
                cutoff_src = "run_id_stamp(ABSENT in run_meta)"
        pinned = parse_ts(rm.get("pinned_at_utc"))
        state = session_state(cutoff) if cutoff else "UNKNOWN"
        lcs_rec = plan.get("last_completed_session")
        lcs_comp = last_completed_session(cutoff) if cutoff else None
        anchor = date.fromisoformat(lcs_rec) if lcs_rec else lcs_comp
        gd = rm.get("git_describe")
        dirty = ("ABSENT" if gd is None else ("True" if str(gd).endswith("-dirty") else "False"))
        # recorded condition: search whole run_meta and final_run_manifest for the vocabulary
        rec_cond = rm.get("run_condition")
        manifest = {}
        mp = os.path.join(rd, "final_run_manifest.json")
        if os.path.exists(mp):
            try:
                manifest = json.load(open(mp, encoding="utf-8"))
            except Exception:
                manifest = {}
        vocab_hits = sorted(set(COND_VOCAB.findall(json.dumps(rm) + json.dumps(manifest))))
        # DB-side vocabulary: run_registry.run_type, run_plans.session_state (no REQ-WP0-01 vocabulary exists in either)
        db_bits = []
        if run_id in reg:
            db_bits.append(f"run_registry.run_type={reg[run_id]['run_type']}")
        if run_id in plans:
            db_bits.append("run_plans.session_state=" + "|".join(str(x["session_state"]) for x in plans[run_id]))
            pv = sorted({v for x in plans[run_id] for v in x["vocab"]})
            if pv:
                db_bits.append(f"run_plans vocab={pv}")
        # ledger: provider requests started after the recorded evidence cutoff contradict the cutoff
        led = ledger.get(run_id)
        after_cutoff = None
        if led and cutoff:
            mx = parse_ts(led["max_started_at"]); mn = parse_ts(led["min_started_at"])
            after_cutoff = f"ledger n={led['n']} physical={led['physical']} started {mn.isoformat() if mn else '?'}..{mx.isoformat() if mx else '?'}; max_after_cutoff={'YES' if mx and mx > cutoff else 'NO'}"
        if rec_cond is None:
            rec_cond = "ABSENT" + (f"(vocab hits elsewhere: {vocab_hits})" if vocab_hits else "") + (f" [{'; '.join(db_bits)}]" if db_bits else "")
        # inferred
        if dirty == "True":
            inferred = "TEST" + (" (also FORCED_INTRASESSION by cutoff)" if state == "INTRA_SESSION" else "")
        elif dirty == "ABSENT":
            inferred = "INDETERMINATE (no code identity)" + (" [cutoff INTRA_SESSION]" if state == "INTRA_SESSION" else "")
        elif state == "INTRA_SESSION":
            inferred = "FORCED_INTRASESSION"
        else:
            inferred = "INDETERMINATE (no provider_completeness_evidence)"
        # field presence REQ-WP0-01
        presence = {f: ("PRESENT" if f in rm else ("NESTED:" + str(find_nested(rm, f))[:40] if find_nested(rm, f) is not None else "ABSENT")) for f in REQ01_FIELDS}
        # counts
        disc = os.path.join(rd, "discovery", f"discovery_candidates_ultimate_{run_id}.csv")
        oi = os.path.join(rd, "options", f"options_intelligence_{run_id}.csv")
        lab3 = os.path.join(rd, "intelligence_lab", "lab_signal_book_v3.csv")
        fob = os.path.join(rd, "intelligence_lab", f"final_opportunity_book_{run_id}.csv")
        rows_disc = count_csv_rows(disc) if os.path.exists(disc) else "ABSENT"
        oi_unique = "ABSENT"
        if os.path.exists(oi):
            try:
                with open(oi, encoding="utf-8", errors="replace") as fh:
                    hdr = next(csv.reader(fh))
                tcol = "ticker" if "ticker" in hdr else None
                oi_unique = int(pd.read_csv(oi, usecols=[tcol], low_memory=False)[tcol].nunique()) if tcol else "NO_TICKER_COL"
            except Exception as e:
                oi_unique = f"ERR:{type(e).__name__}"
        rows_fob = count_csv_rows(fob) if os.path.exists(fob) else "ABSENT"
        rows_lab = (f"lab_signal_book_v3={count_csv_rows(lab3)}" if os.path.exists(lab3) else f"final_book={rows_fob}")
        qd = quote_ts_distribution(oi, anchor) if anchor else {}
        pce = rm.get("provider_completeness_evidence")
        pc = ("RECORDED:" + json.dumps(pce)[:80]) if pce is not None else "ABSENT"
        if qd.get("ticker_max_ge_close_frac") is not None:
            pc += f"; computed(options_intelligence ticker max ts>=20:00Z on {anchor})={qd['ticker_max_ge_close_frac']} of {qd['n_tickers']} tickers"
        qsum = (f"n={qd.get('n')} col={qd.get('col')} no_ts={qd.get('no_ts')} min={qd.get('min')} median={qd.get('median')} max={qd.get('max')} same_session_frac={qd.get('same_session_frac')}"
                if qd else "ABSENT")
        code_id = f"baseline_commit_hash={rm.get('baseline_commit_hash','ABSENT')}; git_describe={gd if gd else 'ABSENT'}"
        row = {
            "run_id": run_id,
            "dispatcher_anchor": (lcs_rec if lcs_rec else f"ABSENT(computed:{lcs_comp})"),
            "evidence_cutoff_utc": (cutoff.isoformat() if cutoff else "ABSENT") + f" [{cutoff_src}]" + (f" ({after_cutoff})" if after_cutoff else ""),
            "session_state_at_cutoff": state,
            "provider_completeness": pc,
            "quote_timestamp_distribution": qsum,
            "rows_discovery": rows_disc,
            "rows_governed_book": oi_unique,
            "rows_lab": rows_lab,
            "run_condition_recorded": rec_cond,
            "run_condition_inferred": inferred,
            "code_identity": code_id,
            "dirty": dirty,
        }
        rows.append(row)
        detail[run_id] = {"row": row, "req01_presence": presence, "pipeline_mode": rm.get("pipeline_mode"),
                          "run_kind": rm.get("run_kind"), "run_meta_schema_version": rm.get("run_meta_schema_version"),
                          "pinned_at_utc": rm.get("pinned_at_utc"), "pinned_session_state": session_state(pinned) if pinned else None,
                          "operator_accepted_at_utc": rm.get("operator_accepted_at_utc"),
                          "quote_dist": qd, "vocab_hits": vocab_hits, "top_level_keys": sorted(rm.keys()),
                          "run_registry": reg.get(run_id), "run_plans": plans.get(run_id), "ledger": led, "ledger_after_cutoff": after_cutoff}
        print(run_id, state, "dirty=" + dirty, "rec=" + str(rec_cond)[:30], "inf=" + inferred, "quotes:", qsum[:120])
    with open(OUT_CSV, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    json.dump(detail, open(OUT_JSON, "w", encoding="utf-8"), indent=1, default=str)
    print("runs with run_meta:", len(rows))
    print("wrote", OUT_CSV, OUT_JSON)


if __name__ == "__main__":
    main()

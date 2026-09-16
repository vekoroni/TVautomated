"""p10_A_provider_completeness.py -- Track A / A2 + A3 ledger counts (REQ-WP0-02, ALG-15).
Read-only on db_copies/control_plane.sqlite. Computes per run: max provider quote ts per ticker
(option_contract_observations.quote_as_of), fraction of tickers with max ts >= 20:00 UTC on the
session date, quote_as_of==observed_at-to-the-second count, dataset_registry and api_request_ledger
vocabulary/counts. Also reads the Stage 1 replay artefact (offline evidence only).
Output: probes/p10_A_provider_completeness_out.json (and stdout)
"""
import json, os, sqlite3
from datetime import datetime, timezone, date, timedelta

ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
DB = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "db_copies", "control_plane.sqlite")
OUT = os.path.join(ROOT, "audit", "td", "AVS-TD-001", "probes", "p10_A_provider_completeness_out.json")
REPLAY = os.path.join(ROOT, "audit", "avs_fix_002", "stage1", "PROVIDER_FINALITY_TWO_SESSION_REPLAY.json")
RUNS = {"20260911_115904": "2026-09-10", "20260910_150045": "2026-09-09"}


def pts(s):
    if s is None:
        return None
    s = str(s).strip().replace("Z", "+00:00")
    try:
        d = datetime.fromisoformat(s)
    except ValueError:
        return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(timezone.utc)


def main():
    c = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    out = {}
    print("observations per run_id:")
    per_run = c.execute("select run_id, count(*), count(distinct ticker), min(quote_as_of), max(quote_as_of), min(observed_at), max(observed_at) from option_contract_observations group by run_id order by run_id").fetchall()
    for r in per_run:
        print("  ", r)
    out["observations_per_run"] = per_run
    for run, sess in RUNS.items():
        sd = date.fromisoformat(sess)
        close_utc = datetime.combine(sd, datetime.strptime("20:00", "%H:%M").time(), tzinfo=timezone.utc)
        rows = c.execute("select ticker, option_side, quote_as_of, observed_at, source_dataset_id, source_provider from option_contract_observations where run_id=?", (run,)).fetchall()
        res = {"session_date": sess, "n_obs": len(rows)}
        if rows:
            tmax = {}
            eq_sec = 0
            no_ts = 0
            same_sess = 0
            by_side = {}
            dists = []
            for t, side, q, o, dsid, prov in rows:
                qt, ot = pts(q), pts(o)
                side = side or "OTHER"
                by_side.setdefault(side, {"n": 0, "same_session": 0, "no_ts": 0, "eq_to_second": 0})
                by_side[side]["n"] += 1
                if qt is None:
                    no_ts += 1; by_side[side]["no_ts"] += 1
                    continue
                dists.append(qt)
                if qt.date() == sd:
                    same_sess += 1; by_side[side]["same_session"] += 1
                if ot is not None and qt.replace(microsecond=0) == ot.replace(microsecond=0):
                    eq_sec += 1; by_side[side]["eq_to_second"] += 1
                if t not in tmax or qt > tmax[t]:
                    tmax[t] = qt
            dists.sort()
            n = len(dists)
            res.update({
                "n_tickers": len(tmax),
                "frac_tickers_max_ts_ge_1600ET_on_session": round(sum(1 for v in tmax.values() if v >= close_utc) / len(tmax), 4) if tmax else None,
                "frac_tickers_max_ts_on_session_date": round(sum(1 for v in tmax.values() if v.date() == sd) / len(tmax), 4) if tmax else None,
                # ALG-15 style: max ts must be ON the session date AND at/after the 16:00 ET close of that date
                "n_tickers_max_ts_on_session_date_and_ge_close": sum(1 for v in tmax.values() if v.date() == sd and v >= close_utc),
                "frac_tickers_max_ts_on_session_date_and_ge_close": round(sum(1 for v in tmax.values() if v.date() == sd and v >= close_utc) / len(tmax), 4) if tmax else None,
                "quotes_no_provider_ts": no_ts,
                "quotes_same_session_frac": round(same_sess / n, 4) if n else None,
                "quote_as_of_eq_observed_at_to_second": eq_sec,
                "quote_ts_min": dists[0].isoformat() if n else None,
                "quote_ts_median": dists[n // 2].isoformat() if n else None,
                "quote_ts_p95": dists[int(0.95 * (n - 1))].isoformat() if n else None,
                "quote_ts_max": dists[-1].isoformat() if n else None,
                "by_side": by_side,
                "ticker_max_ts_date_hist": {},
            })
            hist = {}
            for v in tmax.values():
                k = v.strftime("%Y-%m-%d %H") + "h UTC"
                hist[k] = hist.get(k, 0) + 1
            res["ticker_max_ts_date_hist"] = dict(sorted(hist.items()))
            res["distinct_source_dataset_ids"] = len({r[4] for r in rows})
            res["source_providers"] = sorted({str(r[5]) for r in rows})
        # dataset_registry
        dr = c.execute("select dataset_type, session_date, completeness_status, count(*), min(observed_at), max(observed_at), min(as_of), max(as_of) from dataset_registry where source_run_id=? group by 1,2,3 order by 1,2,3", (run,)).fetchall()
        res["dataset_registry_by_type_session_status"] = dr
        # api_request_ledger
        al = c.execute("select stage, dataset_type, evidence_state, resolution, count(*), sum(physical_request_count), min(started_at), max(started_at) from api_request_ledger where run_id=? group by 1,2,3,4 order by 1,2,3,4", (run,)).fetchall()
        res["api_request_ledger_by_stage_type_state_res"] = al
        res["api_request_ledger_option_quote_physical_total"] = c.execute("select coalesce(sum(physical_request_count),0), count(*) from api_request_ledger where run_id=? and (upper(dataset_type) like '%OPTION%' or upper(stage) like '%OPTION%' or upper(stage) like '%MORNING%' or upper(stage) like '%REFRESH%')", (run,)).fetchone()
        out[run] = res
        print("==", run, json.dumps({k: v for k, v in res.items() if not isinstance(v, list)}, indent=1, default=str))
        print("   dataset_registry:", dr)
        print("   ledger:", al)
    out["dataset_registry_vocab"] = {
        "dataset_type": c.execute("select dataset_type, count(*) from dataset_registry group by 1").fetchall(),
        "completeness_status": c.execute("select completeness_status, count(*) from dataset_registry group by 1").fetchall(),
    }
    out["ledger_vocab"] = {
        "stage": c.execute("select stage, count(*) from api_request_ledger group by 1").fetchall(),
        "dataset_type": c.execute("select dataset_type, count(*) from api_request_ledger group by 1").fetchall(),
        "evidence_state": c.execute("select evidence_state, count(*) from api_request_ledger group by 1").fetchall(),
        "resolution": c.execute("select resolution, count(*) from api_request_ledger group by 1").fetchall(),
    }
    print("vocab:", json.dumps(out["dataset_registry_vocab"]), json.dumps(out["ledger_vocab"]))
    # Stage 1 replay artefact (offline)
    if os.path.exists(REPLAY):
        rp = json.load(open(REPLAY, encoding="utf-8"))
        def summarise(o, depth=0):
            if isinstance(o, dict):
                return {k: (summarise(v, depth + 1) if depth < 3 else str(v)[:80]) for k, v in o.items()}
            if isinstance(o, list):
                return [summarise(v, depth + 1) for v in o[:6]] + ([f"...+{len(o)-6}"] if len(o) > 6 else [])
            return o
        out["stage1_replay"] = summarise(rp)
        print("REPLAY:", json.dumps(out["stage1_replay"], indent=1, default=str)[:6000])
    else:
        out["stage1_replay"] = "ABSENT"
        print("REPLAY ABSENT")
    json.dump(out, open(OUT, "w", encoding="utf-8"), indent=1, default=str)
    print("wrote", OUT)


if __name__ == "__main__":
    main()

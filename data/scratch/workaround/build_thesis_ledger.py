#!/usr/bin/env python3
"""Hand Discovery/Vanguard's thesis to the standalone workflow (v1, 12 Oct 2026).

Builds the decision ledger (same columns as decision_ledger_2026-10-12.csv, v3) straight from the stages that own
the thesis, so nothing after Vanguard (Options Intelligence, EIL, horizon router, Lab) can change it:

    <run>/forecast/behavioural_candidate_packet_v1/candidates.csv   governing thesis per ticker (Spine_Role GOVERNING):
                                                                     side, readiness, trigger, invalidation, structural level,
                                                                     time to level (q50/q80 bars), setup, timeframe;
                                                                     conflicting count and intraday alignment from the other rows
    <run>/discovery/discovery_candidates_cds3_<run>.csv              evidence close, daily ATR, sector ETF
    <run>/forecast/ticker_forecast_descriptive_v1/packet.json        Vanguard structure stage (recorded, not graded)
    macro_board/output/etf_macro_board.html                          money map (optional)
    macro_board/output/external/earnings/*.json                      earnings dates where the board has them (optional)
    vanguard actuarial database + barrier cache (parquet)            half-target-first odds (optional, needs pyarrow)

All of these exist about 5h45m into the evening run (10 Oct run: thesis packet written 00:56 UTC, run finished 08:22 UTC).
Read-only on every input. Writes data/scratch/workaround/decision_ledger_<decision_session>.csv and a JSON receipt.

Run from the repo root:
    venv\\Scripts\\python.exe data\\scratch\\workaround\\build_thesis_ledger.py                     (newest run with a thesis packet)
    venv\\Scripts\\python.exe data\\scratch\\workaround\\build_thesis_ledger.py --run 20261012_191500 --no-barrier
    venv\\Scripts\\python.exe data\\scratch\\workaround\\build_thesis_ledger.py --wait
        (parallel running: start it within 30 minutes of starting the evening pipeline; it waits for that run's folder, then until
         Vanguard's thesis packet is written, then builds. --wait-hours 12 by default)
    venv\\Scripts\\python.exe data\\scratch\\workaround\\build_thesis_ledger.py --run 20261010_191314 --check data\\scratch\\workaround\\decision_ledger_2026-10-12.csv
        (--check compares with an earlier ledger and prints the match rates; it does not write)

Differences from the 12 Oct ledger (built from the Lab book), on purpose:
  level        the packet's structural level. The Lab moderated it on about a third of theses (820 of 2,320 on 10 Oct,
               rule not documented). Here the level is capped at 1 x ATR x sqrt(q80 sessions) from the evidence close
               (the Lab's moderated levels sat at a median 0.88 of that); the structural level is kept in level_structural
               and level_capped says when the cap bit. Confidence in the cap value: Medium.
  checks       structure_evidence_state is produced after Options Intelligence, so it is not available here. focus uses
               the two checks that are (intraday aligned, no conflicting thesis): at least one of two. On 10 Oct this keeps
               all 361 focus names of the Lab version and adds about 107.
  phase status wyckoff_validation_phase_status is also post-options; the 17 INVALIDATED theses of 10 Oct are not excluded.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

VERSION = "build_thesis_ledger_v1.2"
RUNS = Path("data") / "output" / "runs"
WORK = Path("data") / "scratch" / "workaround"
BOARD = Path("macro_board") / "output" / "etf_macro_board.html"
EARN = Path("macro_board") / "output" / "external" / "earnings"
VANGUARD = Path(r"C:\Users\ACKVerissimo\vanguard\data")
TF_SESSIONS = {"1d": 1, "1w": 5, "1mo": 21}
INTRADAY = {"5m", "15m", "30m", "60m"}
LEVEL_CAP_K = 1.0
US_HOLIDAYS = {"2026-01-01", "2026-01-19", "2026-02-16", "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
               "2026-09-07", "2026-11-26", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15", "2027-03-26",
               "2027-05-31", "2027-06-18", "2027-07-05", "2027-09-06", "2027-11-25", "2027-12-24"}
STATE_RANK = {"READY_FRESH_IN_RANGE": 1, "WAIT_TRIGGER_0.5ATR": 2, "READY_FRESH_EXTENDED": 3, "WAIT_TRIGGER_1ATR": 4,
              "READY_OLD_EVENT": 5, "WAIT_TRIGGER_FAR": 6}
COLUMNS = ["ledger_id", "decision_session", "source_run", "evidence_as_of", "thesis_id", "ticker", "side", "sector_etf", "money",
           "readiness", "state", "focus", "focus_v3", "size_note", "timeframe", "setup", "thesis_phase", "vanguard_structure",
           "vanguard_matches_side", "structure_evidence", "intraday_alignment", "conflicting_count", "coherence", "checks3",
           "ref_price", "trigger", "entry_ref", "atr", "half_target", "level", "invalidation", "practical_stop", "reward_pct",
           "risk_to_invalidation_pct", "rr_practical", "p_half_target_first", "p_invalidation_first", "p_timeout",
           "barrier_n_eff", "conditions_rank_for_side", "actuarial_state", "actuarial_state_date", "q50_sessions",
           "q80_sessions", "realisation", "earnings_date", "earnings_sessions", "contract_note", "best_ntm_spread",
           "tightest_ntm_contract_seen", "decision", "decision_reason", "contract_symbol", "entry_time_et", "entry_premium",
           "contracts", "exit_time_et", "exit_premium", "exit_reason",
           # added by this builder
           "level_structural", "level_capped", "readiness_event_date", "thesis_source"]


def bday_offset(d: str, n: int) -> str:
    return str(np.busday_offset(np.datetime64(d), n, roll="forward" if n >= 0 else "backward",
                                holidays=sorted(US_HOLIDAYS)))


def sessions_between(a: str, b: str) -> float:
    try:
        return float(np.busday_count(np.datetime64(a), np.datetime64(b), holidays=sorted(US_HOLIDAYS)))
    except Exception:
        return np.nan


def newest_run() -> Path:
    hits = sorted(glob.glob(str(RUNS / "*" / "forecast" / "behavioural_candidate_packet_v1" / "receipt.json")))
    if not hits:
        raise SystemExit(f"No run under {RUNS} has forecast/behavioural_candidate_packet_v1/receipt.json yet")
    return Path(hits[-1]).parents[2]


def wait_for_thesis(run: Path | None, hours: float) -> Path:
    """Wait until a run's thesis packet and Discovery file exist (written about 5h45m into the evening run)."""
    deadline = time.time() + hours * 3600
    if run is None:
        # only a run folder created in the last 30 minutes (or later) counts, so an older finished run is never picked up
        # by mistake (folder creation time on Windows, so the run id's clock does not matter)
        floor = time.time() - 1800
        print(f"waiting for an evening run folder created after {datetime.fromtimestamp(floor).strftime('%H:%M')} ...")
        while True:
            runs = sorted((p for p in RUNS.iterdir() if p.is_dir() and re.fullmatch(r"\d{8}_\d{6}", p.name)
                           and p.stat().st_ctime >= floor), key=lambda p: p.stat().st_ctime)
            if runs:
                run = runs[-1]
                print(f"found run {run.name}; waiting for Vanguard's thesis packet ...")
                break
            if time.time() > deadline:
                raise SystemExit(f"gave up after {hours}h: no new run folder under {RUNS}")
            time.sleep(60)
    receipt = run / "forecast" / "behavioural_candidate_packet_v1" / "receipt.json"
    while True:
        disc = list((run / "discovery").glob("discovery_candidates_cds3_*.csv")) if (run / "discovery").exists() else []
        if receipt.exists() and disc and (run / "vanguard" / "vanguard_rejects.csv").exists():
            time.sleep(30)  # let the writer finish flushing
            print(f"thesis packet ready for {run.name} at {datetime.now().strftime('%H:%M:%S')}")
            return run
        if time.time() > deadline:
            raise SystemExit(f"gave up after {hours}h: no thesis packet in {run}")
        time.sleep(60)


def money_map(board_path: Path) -> dict:
    if not board_path.exists():
        return {}
    h = board_path.read_text(encoding="utf-8")
    i = h.find("const BOARD=")
    if i < 0:
        return {}
    b = json.JSONDecoder().raw_decode(h[i + len("const BOARD="):])[0]
    out = {}
    for r in b.get("rotation", {}).get("rows", []):
        q, r5 = r.get("quadrant"), r.get("rel_5d") or 0
        out[r["ticker"]] = "IN" if q in ("LEADING", "IMPROVING") and r5 > 0 else "OUT" if q in ("WEAKENING", "LAGGING") and r5 < 0 else "MIXED"
    out["_as_of"] = b.get("as_of_session")
    out["_built"] = b.get("built_at_utc")
    return out


def earnings_map(evidence: str) -> dict:
    files = sorted(glob.glob(str(EARN / "*.json")))
    if not files:
        return {}
    try:
        d = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
        return {t: v.get("date") for t, v in d.items() if isinstance(v, dict) and v.get("date") and v["date"] >= evidence}
    except Exception:
        return {}


def barrier_odds(t: pd.DataFrame, act_path: Path, cache_path: Path) -> pd.DataFrame:
    """Half-target-first odds from the Vanguard barrier cache for each ticker's latest actuarial state (in-sample)."""
    import pyarrow.parquet as pq
    keycols = ["vol_regime", "trend_direction", "structure_quality", "adx_bucket", "wyckoff_phase_bucket", "trend_maturity", "atr_pct_bucket"]
    act = pq.read_table(act_path, columns=["ticker", "date", "state_v2"] + keycols).to_pandas()
    last = act.sort_values("date").groupby("ticker").tail(1)
    last["state_key"] = last[keycols].astype(str).agg("|".join, axis=1)
    e = pq.read_table(cache_path).to_pandas()
    tg, sg = np.array(sorted(e.target_distance_fraction.unique())), np.array(sorted(e.stop_distance_fraction.unique()))
    groups = {k: g for k, g in e.groupby(["state_key", "direction"])}
    x = t.merge(last[["ticker", "date", "state_v2", "state_key"]], on="ticker", how="left")
    rows = []
    for r in x.itertuples():
        g = groups.get((r.state_key, r.side))
        half = abs(r.half_target - r.entry_ref) / r.entry_ref if r.entry_ref else np.nan
        stop = abs(r.entry_ref - r.invalidation) / r.entry_ref if r.entry_ref else np.nan
        res = (np.nan,) * 4
        if g is not None and half > 0 and stop > 0 and pd.notna(r.q50_sessions):
            h = 5 if r.q50_sessions <= 6 else (10 if r.q50_sessions <= 14 else 20)
            y = g[(g.horizon_sessions == h) & (g.target_distance_fraction == tg[np.abs(tg - half).argmin()])
                  & (g.stop_distance_fraction == sg[np.abs(sg - stop).argmin()])]
            if len(y):
                y = y.iloc[0]
                res = (y.p_target_first, y.p_stop_first, y.p_timeout, y.n_effective)
        rows.append(res)
    out = pd.DataFrame(rows, columns=["p_half_target_first", "p_invalidation_first", "p_timeout", "barrier_n_eff"], index=x.index)
    out["actuarial_state"], out["actuarial_state_date"] = x["state_v2"], x["date"].astype(str)
    return out


def build(run: Path, decision_session: str | None, use_barrier: bool) -> tuple[pd.DataFrame, dict]:
    rid = run.name
    cand_path = run / "forecast" / "behavioural_candidate_packet_v1" / "candidates.csv"
    disc_path = next(iter(sorted((run / "discovery").glob("discovery_candidates_cds3_*.csv"))), None)
    fc_path = run / "forecast" / "ticker_forecast_descriptive_v1" / "packet.json"
    if not cand_path.exists() or disc_path is None:
        raise SystemExit(f"{rid}: thesis packet or Discovery cds3 file missing - Vanguard has not finished")
    c = pd.read_csv(cand_path, low_memory=False)
    need = ["Ticker", "Spine_Role", "Thesis_Side", "Readiness", "Trigger_Level", "Invalidation_Level", "Outcome_Level",
            "Duration_Level_Q50_Bars", "Duration_Level_Q80_Bars", "Timeframe", "Signal_Type", "Thesis_ID", "Adoption_State",
            "Readiness_Event_Date", "As_Of"]
    miss = [k for k in need if k not in c.columns]
    if miss:
        raise SystemExit(f"Thesis packet format changed, missing columns: {miss}. Stop and check before trading on it.")
    disc = pd.read_csv(disc_path, low_memory=False, usecols=lambda k: k in ("ticker", "stock_price", "geometry_atr_daily", "ATR_14", "sector_etf"))
    disc = disc.drop_duplicates("ticker")
    evidence = str(c["As_Of"].dropna().max())[:10]
    ds = decision_session or bday_offset(evidence, 1)

    gov = c[c.Spine_Role.eq("GOVERNING") & c.Readiness.isin(["READY_FOR_HUMAN_REVIEW", "WAIT_TRIGGER"]) & c.Thesis_Side.isin(["BULL", "BEAR"])].copy()
    gov = gov.drop_duplicates("Ticker")
    # Vanguard rejects (no or stale price history, e.g. delisted names) keep a governing row in the packet; the full
    # pipeline drops them at the canonical manifest. Drop them here too (10 Oct: 125 names).
    rej_path = run / "vanguard" / "vanguard_rejects.csv"
    rejected = set()
    if rej_path.exists():
        rj = pd.read_csv(rej_path)
        if "ticker" in rj:
            rejected = set(rj["ticker"].astype(str).str.upper())
    else:
        raise SystemExit(f"{rid}: vanguard/vanguard_rejects.csv missing - Vanguard has not finished")
    n_rejected = int(gov.Ticker.isin(rejected).sum())
    gov = gov[~gov.Ticker.isin(rejected)]
    conflicting = c[c.Spine_Role.eq("CONFLICTING") & ~c.Timeframe.isin(INTRADAY)].groupby("Ticker").size()
    intra = c[c.Timeframe.isin(INTRADAY) & c.Adoption_State.eq("ADOPTED") & c.Thesis_Side.isin(["BULL", "BEAR"])]
    intra_sides = intra.groupby("Ticker").Thesis_Side.agg(set)

    t = gov.rename(columns={"Ticker": "ticker"}).merge(disc, on="ticker", how="left")
    t["side"] = t.Thesis_Side.map({"BULL": "CALL", "BEAR": "PUT"})
    s = np.where(t.side == "CALL", 1, -1)
    f = t.Timeframe.map(TF_SESSIONS)
    t["q50_sessions"] = t.Duration_Level_Q50_Bars * f
    t["q80_sessions"] = t.Duration_Level_Q80_Bars * f
    t["ref_price"] = pd.to_numeric(t.stock_price, errors="coerce")
    t["atr"] = pd.to_numeric(t.geometry_atr_daily, errors="coerce").fillna(pd.to_numeric(t.get("ATR_14"), errors="coerce"))
    t["trigger"], t["invalidation"] = t.Trigger_Level, t.Invalidation_Level
    t["level_structural"] = t.Outcome_Level
    cap = LEVEL_CAP_K * t.atr * np.sqrt(t.q80_sessions)
    struct_move = (t.level_structural - t.ref_price) * s
    t["level_capped"] = struct_move > cap
    t["level"] = np.where(t.level_capped, t.ref_price + s * cap, t.level_structural)
    t["readiness"] = t.Readiness
    t["readiness_event_date"] = t.Readiness_Event_Date.astype(str).str[:10]
    fresh_from = bday_offset(evidence, -4)
    fresh = t.readiness_event_date >= fresh_from
    ready = t.readiness.str.startswith("READY")
    past = (t.ref_price - t.trigger) * s / t.atr
    trig_atr = past.abs()
    t["state"] = np.select([ready & fresh & (past <= 1), ready & fresh, ready,
                            ~ready & (trig_atr <= 0.5), ~ready & (trig_atr <= 1.0)],
                           ["READY_FRESH_IN_RANGE", "READY_FRESH_EXTENDED", "READY_OLD_EVENT", "WAIT_TRIGGER_0.5ATR", "WAIT_TRIGGER_1ATR"],
                           "WAIT_TRIGGER_FAR")
    t["entry_ref"] = np.where(ready, t.ref_price, t.trigger)
    t["half_target"] = t.entry_ref + (t.level - t.entry_ref) / 2
    ps = t.trigger - s * t.atr
    t["practical_stop"] = np.where(s > 0, np.maximum(ps, t.invalidation), np.minimum(ps, t.invalidation))
    t["reward_pct"] = (t.level - t.entry_ref) * s / t.entry_ref * 100
    t["risk_to_invalidation_pct"] = (t.entry_ref - t.invalidation) * s / t.entry_ref * 100
    t["rr_practical"] = t.reward_pct / ((t.entry_ref - t.practical_stop) * s / t.entry_ref * 100)
    t["stale"] = np.select([(t.ref_price - t.level) * s >= 0, (t.invalidation - t.ref_price) * s >= 0], ["PAST_LEVEL", "PAST_INVALIDATION"], "")
    t["conflicting_count"] = t.ticker.map(conflicting).fillna(0).astype(int)
    side_b = t.Thesis_Side
    t["intraday_alignment"] = [("NONE" if not isinstance(x, set) else "ALIGNED" if sb in x else "OPPOSED")
                               for x, sb in zip(t.ticker.map(intra_sides), side_b)]
    t["checks3"] = t.intraday_alignment.eq("ALIGNED").astype(int) + t.conflicting_count.eq(0).astype(int)  # two checks here (see header)
    t["realisation"] = pd.cut(t.q50_sessions, [0, 3, 10, 20, 60, 10_000],
                              labels=["1-3 sessions", "4-10 sessions", "11-20 sessions", "21-60 sessions", ">60 sessions"]).astype(str)
    t["focus_v3"] = t.state.map(STATE_RANK).le(4) & t.checks3.ge(1) & t.rr_practical.ge(1) & t.stale.eq("")
    t["focus"] = t.focus_v3

    if fc_path.exists():
        fc = pd.DataFrame(json.loads(fc_path.read_text(encoding="utf-8")).get("rows", []))
        if len(fc):
            t["vanguard_structure"] = t.ticker.map(fc.set_index("ticker").get("forecast_structure_stage"))
    if "vanguard_structure" not in t:
        t["vanguard_structure"] = np.nan
    stage = t.vanguard_structure.fillna("").astype(str)
    t["vanguard_matches_side"] = np.where(s > 0, stage.str.startswith("ACCUMULATION"), stage.str.startswith("DISTRIBUTION"))

    mm = money_map(BOARD)
    flow = t.sector_etf.map(lambda e: mm.get(e, "UNMAPPED") if isinstance(e, str) else "UNMAPPED")
    flow = np.where(t.ticker.isin([k for k in mm if not k.startswith("_")]), t.ticker.map(mm), flow)
    t["money"] = [f_ if f_ in ("UNMAPPED", "MIXED") else ("WITH" if (f_ == "IN") == (sd == "CALL") else "AGAINST") for f_, sd in zip(flow, t.side)]

    em = earnings_map(evidence)
    t["earnings_date"] = t.ticker.map(em)
    t["earnings_sessions"] = [sessions_between(ds, e) if isinstance(e, str) else np.nan for e in t.earnings_date]

    t["size_note"] = np.where(t.side == "PUT", "HALF_SIZE_PUT", "FULL")
    for k in ["p_half_target_first", "p_invalidation_first", "p_timeout", "barrier_n_eff", "actuarial_state", "actuarial_state_date"]:
        t[k] = np.nan
    barrier_status = "SKIPPED"
    if use_barrier:
        try:
            b = barrier_odds(t, VANGUARD / "actuarial_database_v7.parquet", VANGUARD / "ev3_barrier_outcome_cache.parquet")
            for k in b.columns:
                t[k] = b[k].values
            more_inv = t.p_invalidation_first > t.p_half_target_first
            t.loc[more_inv, "size_note"] = t.loc[more_inv, "size_note"] + ";INVALIDATION_MORE_LIKELY_THAN_HALF_TARGET"
            barrier_status = f"OK ({int(t.p_half_target_first.notna().sum())} of {len(t)} with odds)"
        except Exception as e:  # optional input: record and carry on
            barrier_status = f"FAILED {type(e).__name__}: {e}"

    t["ledger_id"] = [f"{ds}_{a}_{b}" for a, b in zip(t.ticker, t.side)]
    t["decision_session"], t["source_run"], t["evidence_as_of"] = ds, rid, evidence
    t["thesis_id"] = t.Thesis_ID
    t["timeframe"], t["setup"] = t.Timeframe, t.Signal_Type
    t["thesis_phase"] = t.get("Wyckoff_Phase")
    t["structure_evidence"] = "NOT_AVAILABLE_PRE_OPTIONS"
    t["coherence"] = np.select([t.checks3 == 2, t.checks3 == 1], ["A", "B"], "C")
    t["conditions_rank_for_side"] = np.nan
    t["contract_note"] = np.where(t.ref_price < 5, "UNDER_$5_MANUAL", "SEE_OPTIONS_TOOL")
    t["best_ntm_spread"] = np.nan
    t["tightest_ntm_contract_seen"] = np.nan
    t["thesis_source"] = "behavioural_candidate_packet_v1:GOVERNING"
    for k in ["decision", "decision_reason", "contract_symbol", "entry_time_et", "entry_premium", "contracts", "exit_time_et", "exit_premium", "exit_reason"]:
        t[k] = ""
    t["state_rank"] = t.state.map(STATE_RANK)
    t["real_rank"] = t.realisation.map({"1-3 sessions": 0, "4-10 sessions": 1, "11-20 sessions": 2, "21-60 sessions": 3, ">60 sessions": 4}).fillna(9)
    t = t.sort_values(["focus_v3", "state_rank", "real_rank", "p_half_target_first"], ascending=[False, True, True, False])
    for k in ["ref_price", "trigger", "entry_ref", "atr", "half_target", "level", "invalidation", "practical_stop", "level_structural"]:
        t[k] = pd.to_numeric(t[k], errors="coerce").round(4)
    for k in ["reward_pct", "risk_to_invalidation_pct", "rr_practical"]:
        t[k] = t[k].round(2)
    L = t[COLUMNS].reset_index(drop=True)
    receipt = {"version": VERSION, "built_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "run": rid,
               "evidence_as_of": evidence, "decision_session": ds, "theses": int(len(L)), "focus": int(L.focus_v3.sum()),
               "state_counts": L.state.value_counts().to_dict(), "level_capped": int(L.level_capped.sum()),
               "money_board": {"as_of": mm.get("_as_of"), "built": mm.get("_built")} if mm else "BOARD_NOT_FOUND",
               "earnings_dates_found": int(L.earnings_date.notna().sum()), "barrier": barrier_status,
               "vanguard_rejects_excluded": n_rejected,
               "inputs": {"thesis_packet": str(cand_path), "discovery": str(disc_path), "forecast": str(fc_path) if fc_path.exists() else None}}
    return L, receipt


def check(L: pd.DataFrame, old_path: Path) -> None:
    O = pd.read_csv(old_path)
    m = O.merge(L, on=["ticker", "side"], how="outer", suffixes=("_old", "_new"), indicator=True)
    both = m[m._merge == "both"]
    print(f"old {len(O)} / new {len(L)} theses; same ticker+side {len(both)}; only old {int((m._merge == 'left_only').sum())}; only new {int((m._merge == 'right_only').sum())}")
    for k in ["trigger", "invalidation", "ref_price", "atr", "q50_sessions", "q80_sessions", "level"]:
        a, b = pd.to_numeric(both[k + "_old"], errors="coerce"), pd.to_numeric(both[k + "_new"], errors="coerce")
        ok = np.isclose(a, b, rtol=1e-3, atol=1e-3) | (a.isna() & b.isna())
        print(f"  {k:18s} match {ok.mean():.3f}")
    both = both.assign(intraday_alignment_old=both.intraday_alignment_old.replace("NOT_MEASURED", "NONE"),
                       conflicting_count_old=pd.to_numeric(both.conflicting_count_old, errors="coerce").fillna(0).astype(int).astype(str),
                       conflicting_count_new=both.conflicting_count_new.astype(str))
    for k in ["readiness", "state", "intraday_alignment", "conflicting_count", "sector_etf", "money"]:
        print(f"  {k:18s} match {(both[k + '_old'].astype(str) == both[k + '_new'].astype(str)).mean():.3f}")
    fo, fn = both.focus_v3_old.astype(str).str.upper().eq("TRUE"), both.focus_v3_new.astype(bool)
    print(f"  focus: old {int(fo.sum())}, new {int(fn.sum())}, kept {int((fo & fn).sum())}, dropped {int((fo & ~fn).sum())}, added {int((~fo & fn).sum())}")
    if (fo & ~fn).any():
        d = both[fo & ~fn]
        print("  dropped by state:", d.state_new.value_counts().to_dict())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", help="run id (default: newest run whose thesis packet exists)")
    ap.add_argument("--decision-session", help="YYYY-MM-DD (default: next session after the evidence date)")
    ap.add_argument("--no-barrier", action="store_true", help="skip the Vanguard barrier odds (no pyarrow needed)")
    ap.add_argument("--check", help="an earlier ledger to compare with; nothing is written")
    ap.add_argument("--wait", action="store_true", help="wait for the (newest or given) run's thesis packet, then build")
    ap.add_argument("--wait-hours", type=float, default=12)
    a = ap.parse_args()
    started = time.time()
    if a.wait:
        run = wait_for_thesis(RUNS / a.run if a.run else None, a.wait_hours)
    else:
        run = RUNS / a.run if a.run else newest_run()
    L, receipt = build(run, a.decision_session, not a.no_barrier)
    receipt["thesis_ready_local"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    receipt["waited_minutes"] = round((time.time() - started) / 60, 1)
    if a.check:
        check(L, Path(a.check))
        print(json.dumps({k: v for k, v in receipt.items() if k != "inputs"}, indent=1, default=str))
        return
    WORK.mkdir(parents=True, exist_ok=True)
    out = WORK / f"decision_ledger_{receipt['decision_session']}.csv"
    if out.exists():
        out = WORK / f"decision_ledger_{receipt['decision_session']}_{run.name}.csv"
        print(f"note: a ledger for {receipt['decision_session']} already exists; writing {out.name} instead (rename it to use it)")
    L.to_csv(out, index=False)
    (WORK / f"thesis_handover_{run.name}.json").write_text(json.dumps(receipt, indent=1, default=str))
    print(f"{VERSION}: run {run.name}, evidence {receipt['evidence_as_of']} -> {out}")
    print(f"  {receipt['theses']} active theses, {receipt['focus']} focus; levels capped {receipt['level_capped']}; barrier {receipt['barrier']}")
    print(f"  money board {receipt['money_board']}; earnings dates found {receipt['earnings_dates_found']}")
    print("next: options tool (newest ledger is picked up), then build_mining_handoff.py")


if __name__ == "__main__":
    main()

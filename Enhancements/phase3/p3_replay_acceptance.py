"""Phase 3 acceptance on real data (offline replay, read-only; same sample as Phases 1-2).

Checks: every daily/weekly/monthly thesis carries an events status; event mix; ticker last-event fields; and the
consistency of the single acceptance owner - the engine's ACTIVATED state vs the detector's BREAK_ACCEPTED event
on the candidate's own trigger.
"""
import json, sys
from pathlib import Path
import numpy as np, pandas as pd
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "Enhancements" / "direction_evidence"))
import avshunter_discovery_ULTIMATE as disc  # noqa: E402
from WyckoffEngine_3101_v2 import WyckoffEngine_3101_v2 as W  # noqa: E402
from dir002_replay import read_bars  # noqa: E402

life = pd.read_parquet(ROOT / "tests/fixtures/phase0/lifecycle.parquet")
rng = np.random.default_rng(8)
sample = [t for c in ("INTRADAY_ONLY_UNTESTED", "NO_LIVE_SETUP", "DISCOVERY_SURVIVOR")
          for t in rng.choice(sorted(life.loc[life.reason_code == c, "ticker"]), 40, replace=False)]
cfg, wy = disc.UltimateConfig(), W()
cands, tick = [], []
for t in sample:
    b = read_bars(t); b = b[b.date <= "2026-10-05"].reset_index(drop=True)
    s, _ = disc._scan_with_lifecycle(t, b, cfg, wy)
    if s is None:
        continue
    tick.append({"ticker": t, "side": s.get("thesis__side"), "last_event": s.get("thesis__last_event"),
                 "events_status": s.get("thesis__events_status")})
    for c in s.get("_beh001_candidates") or []:
        ev = [e["event"] for e in json.loads(c.get("Events_JSON") or "[]")]
        side = c.get("Proposed_Side")
        tag = "UP" if side == "BULL" else "DOWN"
        cands.append({"tf": c.get("Timeframe"), "state": c.get("Signal_State"), "side": side,
                      "status": (c.get("Events_Status") or "")[:12], "last": c.get("Last_Event"),
                      "accepted_event": f"BREAK_ACCEPTED_{tag}" in ev if side else None,
                      "n": len(ev), "adopted": c.get("Adoption_State")})
c, k = pd.DataFrame(cands), pd.DataFrame(tick)
d = c[c.tf.isin(["1d", "1w", "1mo"])]
dd = d[d.side.isin(["BULL", "BEAR"]) & d.state.isin(["DETECTED", "ACTIVATED"])]
agree = pd.crosstab(dd.state, dd.accepted_event)
out = {"candidates": len(c), "tested_tf": len(d), "events_status": d.status.value_counts().to_dict(),
       "last_event_mix_tested": d["last"].fillna("<none>").value_counts().to_dict(),
       "engine_state_vs_detector_acceptance": {str(i): {str(j): int(agree.loc[i, j]) for j in agree.columns} for i in agree.index},
       "ticker_last_event": k.last_event.fillna("<none>").value_counts().to_dict(),
       "directed_tickers_with_event_status": int(k[k.side.isin(["BULL","BEAR"])].events_status.notna().sum()),
       "directed_tickers": int(k.side.isin(["BULL","BEAR"]).sum())}
(Path(__file__).parent / "p3_replay_acceptance.json").write_text(json.dumps(out, indent=2, default=str))
print(json.dumps(out, indent=2, default=str))

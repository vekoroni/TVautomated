"""M-REVIEW-01 replay (ACK 10 Oct 2026: "bring the design forward with replay").

Re-runs the real Morning gate (morning_gate.run_gate) on every row of the 9 Oct Morning (run 20261008_220129), from the
Evening candidate rows plus the Morning's captured live fields, twice with today's code:
  BASELINE  - the current upstream authority rule (EOD capital permission, set by the legacy execution layer from
              Vanguard's signal_type / PSE classification);
  CANDIDATE - thesis authority: provenance, options route and invalidation checks kept; the legacy capital-permission
              label becomes context; a row needs an adopted thesis instead.
Everything else (direction integrity, strategy, contract, pays, trigger eligibility) is unchanged. Network access is
blocked for the replay (no provider calls). Read-only; JSON receipt beside.
"""
import ast
import collections
import json
import socket
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))


def _no_network(*a, **k):
    raise RuntimeError("network blocked in replay")


socket.socket.connect = _no_network          # no provider calls from the replay
import morning_gate  # noqa: E402

RUN = "20261008_220129"
mv = ROOT / "data/output/runs" / RUN / "morning_validation"
eod = pd.read_csv(mv / f"morning_candidates_{RUN}.csv", low_memory=False, dtype=str)
eod = eod.loc[:, ~eod.columns.duplicated()]
mor = pd.read_csv(mv / f"morning_validated_trades_{RUN}.csv", low_memory=False, dtype=str)
mor = mor.loc[:, ~mor.columns.duplicated()].set_index("ticker")
summary = json.loads((mv / f"morning_gate_summary_{RUN}.json").read_text(encoding="utf-8"))
morning_gate._today_session = lambda: date(2026, 10, 9)
# Time-dependent inputs are the ones the Morning recorded at its own decision time (about 14:10 London, before the
# advisory structure stage), not the replay's clock: each row's recorded effective quote age.
CURRENT = {"ticker": None}
_RECORDED_AGE = {}
morning_gate.effective_quote_age_seconds = lambda observed, **kw: _RECORDED_AGE.get(CURRENT["ticker"])
LIVE_PREFIX = ("live_", "quote_", "execution_viability_", "selected_", "current_", "atm_", "skew_", "greek_", "contract_",
               "morning_repair", "morning_contract_repair", "ms_", "ib_", "spread_", "liquidity_", "primary_", "minimum_",
               "msi_")   # the live stage's fields, not gate outputs; checked by the baseline reproducing the recorded run

original_rule = morning_gate._check_upstream_authority


def thesis_authority(row):
    """CANDIDATE: thesis authority; legacy capital permission becomes context."""
    if morning_gate._u(row.get("authority_source_stage")) != "FINAL_EXECUTION":
        return False, f"UNSAFE_AUTHORITY_SOURCE:{morning_gate._u(row.get('authority_source_stage')) or 'MISSING'}"
    route = morning_gate._u(row.get("final_route"))
    if route in {"OPTIONS_BLOCKED", "OPTIONS_EQUITY_ONLY_BETTER"}:
        return False, f"UPSTREAM_OPTIONS_ROUTE_BLOCKED:{route}"
    if morning_gate._u(row.get("capital_authorization_state")) == "NOT_AUTHORIZED_INVALIDATION_MISSING":
        return False, "UPSTREAM_INVALIDATION_MISSING"
    readiness = morning_gate._u(row.get("thesis__readiness"))
    if readiness in {"", "NAN", "NOT_ADOPTED", "NOT_MEASURED"}:
        return False, f"NO_ADOPTED_THESIS:{readiness or 'MISSING'}"
    return True, f"THESIS_AUTHORITY:{readiness}"


def clean(d):
    return {k: (None if (v is None or (isinstance(v, float) and v != v)) else v) for k, v in d.items()}


def run(rule):
    morning_gate._check_upstream_authority = rule
    out = {}
    for _, r in eod.iterrows():
        t = r["ticker"]
        row = clean(r.to_dict())
        live = clean({k: v for k, v in mor.loc[t].items() if str(k).startswith(LIVE_PREFIX)}) if t in mor.index else {}
        # structured live fields were written to CSV as text; restore them (selected_long_leg carries the contract dte)
        for key in ("selected_long_leg",):
            if isinstance(live.get(key), str) and live[key].startswith("{"):
                live[key] = ast.literal_eval(live[key])
        CURRENT["ticker"] = t
        try:
            _RECORDED_AGE[t] = float(mor.loc[t].get("quote_age_seconds")) if t in mor.index else None
        except (TypeError, ValueError):
            _RECORDED_AGE[t] = None
        try:
            g = morning_gate.run_gate(row, live, summary.get("current_regime") or "UNKNOWN",
                                      morning_gate.DEFAULT_SPREAD_THRESHOLD)
            out[t] = (g.get("verdict"), g.get("morning_unlock_condition") or "", g.get("anticipated_pays_state"))
        except Exception as e:                                # noqa: BLE001 - counted, never hidden
            out[t] = ("ERROR", f"{type(e).__name__}: {e}"[:160], None)
    return out


base, cand = run(original_rule), run(thesis_authority)
recorded = mor["verdict"].to_dict()
agree = sum(1 for t, v in base.items() if v[0] == recorded.get(t))
moves = collections.Counter(f"{base[t][0]} -> {cand[t][0]}" for t in base)
blocked_upstream = [t for t in base if "UPSTREAM_NOT_AUTHORIZED" in base[t][1] or "UPSTREAM_CAPITAL_PERMISSION" in base[t][1]]
after = collections.Counter(cand[t][0] for t in blocked_upstream)
why = collections.Counter(cand[t][1].split(";")[0].split(":")[0][:60] for t in blocked_upstream if cand[t][0] != "GO")
new_go = sorted(t for t in base if base[t][0] != "GO" and cand[t][0] == "GO")
lost_go = sorted(t for t in base if base[t][0] == "GO" and cand[t][0] != "GO")
eodrows = eod.set_index("ticker")
detail = [{"ticker": t, "lane": eodrows.loc[t].get("trade_lane"), "readiness": eodrows.loc[t].get("thesis__readiness"),
           "legacy_reason": eodrows.loc[t].get("signal_authority_reason"), "pays": cand[t][2]} for t in new_go]
res = {"run": RUN, "rows": len(base), "baseline_matches_recorded_verdict": agree,
       "baseline_vs_recorded_differences": collections.Counter(f"{recorded.get(t)} -> {v[0]}" for t, v in base.items()
                                                               if v[0] != recorded.get(t)),
       "baseline_vs_recorded_tickers": {t: {"recorded": recorded.get(t), "baseline": v[0], "why": v[1][:200]}
                                        for t, v in base.items() if v[0] != recorded.get(t)},
       "baseline_counts": collections.Counter(v[0] for v in base.values()),
       "candidate_counts": collections.Counter(v[0] for v in cand.values()),
       "transitions": dict(moves.most_common()), "upstream_blocked_rows": len(blocked_upstream),
       "upstream_blocked_after_candidate": dict(after), "why_still_not_go": dict(why.most_common(12)),
       "new_go": detail, "lost_go": lost_go}
Path(__file__).with_suffix(".json").write_text(json.dumps(res, indent=2, default=str), encoding="utf-8")
print(json.dumps({k: v for k, v in res.items() if k != "new_go"}, indent=1, default=str))
print("new GO:", len(new_go), collections.Counter(d["lane"] for d in detail), collections.Counter(d["pays"] for d in detail))

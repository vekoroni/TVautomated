"""p11_B_b3_spread: REQ-WP1-03 / NFR-04. Read-only.
(1) Every CSV in both runs (packages/ excluded): presence of spread_fraction_mid / spread_pct_of_mid, and for every
    column whose name contains 'spread' the value range: n, min, max, n<=1, n in (1,2], n>2 (unit characterisation).
(2) Adapter fixture: 0.12 and 12.0 through domain.quote_units.resolve_spread, contracts.opportunity_tier._tier_spread_fraction,
    contracts.quote_change_evidence snapshot builder, and domain.long_option_execution.quote_spread_fraction (bid/ask).
Outputs: p11_B_b3_spread.csv (per column stats), p11_B_b3_spread.txt (fixture outputs)."""
import os, sys, inspect
import pandas as pd, numpy as np
ROOT = r"C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; sys.path.insert(0, ROOT)
RUNS = ["20260911_115904", "20260910_150045"]
lines, rows = [], []


def say(s):
    print(s); lines.append(s)


for run in RUNS:
    base = os.path.join(ROOT, "data/output/runs", run)
    n_csv = 0; has_fm = 0; has_pom = 0
    for dp, dn, fn in os.walk(base):
        dn[:] = [d for d in dn if d != "packages"]
        for f in fn:
            if not f.lower().endswith(".csv"):
                continue
            p = os.path.join(dp, f); rel = os.path.relpath(p, base)
            try:
                df = pd.read_csv(p, low_memory=False)
            except Exception as e:
                rows.append({"run": run, "csv": rel, "column": "READ_ERROR", "note": str(e)[:80]}); continue
            n_csv += 1
            has_fm += int("spread_fraction_mid" in df.columns); has_pom += int("spread_pct_of_mid" in df.columns)
            if "spread_fraction_mid" in df.columns:
                s = pd.to_numeric(df["spread_fraction_mid"], errors="coerce")
                rows.append({"run": run, "csv": rel, "column": "spread_fraction_mid", "rows": len(df), "n": int(s.notna().sum()), "min": s.min(), "max": s.max(), "n_in_0_2": int(((s >= 0) & (s <= 2)).sum()), "n_outside_0_2": int(((s < 0) | (s > 2)).sum())})
                if "spread_pct_of_mid" in df.columns:
                    t = pd.to_numeric(df["spread_pct_of_mid"], errors="coerce"); both = s.notna() & t.notna()
                    rows.append({"run": run, "csv": rel, "column": "spread_pct_of_mid==100*fraction", "rows": len(df), "n": int(both.sum()), "n_mismatch": int(((t[both] - 100 * s[both]).abs() > 1e-6).sum())})
            for c in df.columns:
                if "spread" not in c.lower():
                    continue
                s = pd.to_numeric(df[c], errors="coerce")
                if s.notna().sum() == 0:
                    rows.append({"run": run, "csv": rel, "column": c, "rows": len(df), "n": 0, "dtype": str(df[c].dtype), "sample": str(df[c].dropna().astype(str).head(3).tolist())[:80]}); continue
                rows.append({"run": run, "csv": rel, "column": c, "rows": len(df), "n": int(s.notna().sum()), "min": float(s.min()), "max": float(s.max()), "median": float(s.median()),
                             "n_le_1": int((s <= 1).sum()), "n_1_to_2": int(((s > 1) & (s <= 2)).sum()), "n_gt_2": int((s > 2).sum()), "n_neg": int((s < 0).sum()),
                             "n_0_to_0.25": int(((s >= 0) & (s <= 0.25)).sum()), "n_gt_0.25_le_1": int(((s > 0.25) & (s <= 1)).sum())})
    say(f"=== run {run}: csv files={n_csv}; with spread_fraction_mid={has_fm}; with spread_pct_of_mid={has_pom}")
out = pd.DataFrame(rows); out.to_csv(os.path.join(ROOT, "audit/td/AVS-TD-001/probes/p11_B_b3_spread.csv"), index=False)
num = out[out.get("n", 0) > 0].copy() if "n" in out else out
say("--- per-column-name summary across CSVs (primary run) ---")
prim = num[num["run"] == RUNS[0]]
for c, grp in prim.groupby("column"):
    say(f"  {c}: csvs={len(grp)} n_total={int(grp['n'].sum())} min={grp['min'].min():.4g} max={grp['max'].max():.4g} n_le_1={int(grp['n_le_1'].sum()) if 'n_le_1' in grp else '-'} n_(1,2]={int(grp['n_1_to_2'].sum()) if 'n_1_to_2' in grp else '-'} n_gt_2={int(grp['n_gt_2'].sum()) if 'n_gt_2' in grp else '-'}")
say("--- per-column-name summary (comparison run) ---")
comp = num[num["run"] == RUNS[1]]
for c, grp in comp.groupby("column"):
    say(f"  {c}: csvs={len(grp)} n_total={int(grp['n'].sum())} min={grp['min'].min():.4g} max={grp['max'].max():.4g} n_le_1={int(grp['n_le_1'].sum()) if 'n_le_1' in grp else '-'} n_(1,2]={int(grp['n_1_to_2'].sum()) if 'n_1_to_2' in grp else '-'} n_gt_2={int(grp['n_gt_2'].sum()) if 'n_gt_2' in grp else '-'}")

say("=== ADAPTER FIXTURE 0.12 / 12.0")
from domain.quote_units import resolve_spread
from contracts.opportunity_tier import _tier_spread_fraction, _hard_veto, SPREAD_TIER_2_MAX
from domain.long_option_execution import quote_spread_fraction
import contracts.quote_change_evidence as qce
for v in (0.12, 12.0):
    say(f"  resolve_spread({{'spread_pct': {v}}}) -> {resolve_spread({'spread_pct': v}).to_dict()}")
    say(f"  resolve_spread({{'contract_spread_pct': {v}}}) -> {resolve_spread({'contract_spread_pct': v}).to_dict()}")
    say(f"  resolve_spread({{'spread_pct': {v}, 'spread_unit': 'PERCENT'}}) -> {resolve_spread({'spread_pct': v, 'spread_unit': 'PERCENT'}).to_dict()}")
    say(f"  resolve_spread({{'spread_pct': {v}, 'spread_unit': 'FRACTION_OF_MID'}}) -> {resolve_spread({'spread_pct': v, 'spread_unit': 'FRACTION_OF_MID'}).to_dict()}")
    say(f"  resolve_spread({{'spread_fraction_mid': {v}}}) -> {resolve_spread({'spread_fraction_mid': v}).to_dict()}")
    say(f"  resolve_spread({{'spread_pct_of_mid': {v}}}) -> {resolve_spread({'spread_pct_of_mid': v}).to_dict()}")
    say(f"  opportunity_tier._tier_spread_fraction({{'spread_pct': {v}}}) -> {_tier_spread_fraction({'spread_pct': v})}  (SPREAD_TIER_2_MAX={SPREAD_TIER_2_MAX}; would veto: {_tier_spread_fraction({'spread_pct': v}) > SPREAD_TIER_2_MAX})")
    say(f"  opportunity_tier._tier_spread_fraction({{'spread_fraction_mid': {v}}}) -> {_tier_spread_fraction({'spread_fraction_mid': v})}")
    say(f"  opportunity_tier._tier_spread_fraction({{'spread_pct_of_mid': {v}}}) -> {_tier_spread_fraction({'spread_pct_of_mid': v})}")
say(f"  quote_spread_fraction(bid=1.00, ask=1.12) -> {quote_spread_fraction(1.00, 1.12)}   (selected_contract_economics.py:289 computes from bid/ask; not a legacy adapter)")
say(f"  quote_spread_fraction(bid=100, ask=112) -> {quote_spread_fraction(100, 112)}")
# quote_change_evidence snapshot builder: find the function whose body returns QuoteSnapshot
builder = None
for name, fn in inspect.getmembers(qce, inspect.isfunction):
    try:
        src = inspect.getsource(fn)
    except OSError:
        continue
    if "return QuoteSnapshot(" in src and fn.__module__ == qce.__name__:
        builder = (name, fn); break
if builder:
    name, fn = builder; sig = inspect.signature(fn)
    say(f"  quote_change_evidence builder = {name}{sig}")
    for v in (0.12, 12.0):
        for key in ("current_contract_spread_pct", "morning_contract_spread_pct", "contract_spread_pct", "live_contract_spread_fraction"):
            row = {key: v, "contract_symbol": "X", "current_contract_bid": 1.0, "current_contract_ask": 1.1, "morning_contract_bid": 1.0, "morning_contract_ask": 1.1, "contract_bid": 1.0, "contract_ask": 1.1}
            for args in ((row,), (row, True), (row, False)):
                try:
                    snap = fn(*args); say(f"    {name}(row[{key}={v}], {args[1:] if len(args)>1 else ''}) -> spread_pct={snap.spread_pct} bid={snap.bid} ask={snap.ask} (no unit label on QuoteSnapshot; field name 'spread_pct')"); break
                except TypeError as e:
                    continue
                except Exception as e:
                    say(f"    {name} raised {type(e).__name__}: {e}"); break
    row = {"contract_symbol": "X", "current_contract_bid": 1.0, "current_contract_ask": 1.12}
    for args in ((row,), (row, True)):
        try:
            snap = fn(*args); say(f"    {name}(bid=1.0, ask=1.12, no spread field) -> spread_pct={snap.spread_pct} (fallback quote_spread_fraction => FRACTION stored under name spread_pct)"); break
        except TypeError:
            continue
else:
    say("  quote_change_evidence: snapshot builder not found by introspection")
open(os.path.join(ROOT, "audit/td/AVS-TD-001/probes/p11_B_b3_spread.txt"), "w", encoding="utf-8").write("\n".join(lines))

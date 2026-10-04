# AVS options analytics framework — build plan (30 Sep 2026, draft for ACK approval)

ACK, 29 Sep 2026: "then we need to implement the avs options analytics framework". Basis: the framework review
`Enhancements/assessment/AVS_OPTION_ANALYTICS_FRAMEWORK_REVIEW_20260929.md`. Governing rules: CLAUDE.md (enhance in
place, test-first, one owner per fact, configuration not literals, no authority without G1–G4) and the TEV-001 design
(one valuation owner, C8). Everything here is **display and measurement only**: no gate, rank or permission reads it.

## Principles

- One owner per fact: contract analytics live in `contracts/selected_contract_economics.py`, which already owns the
  hydrated contract identity (strike, expiry, DTE fixed 28 Sep). One Black–Scholes: `domain/deterministic_option_valuation.py`.
- Prices a trader would actually pay: breakeven and maximum loss at the **ask**; exit values at the **bid**.
- Units in names: `_per_share`, `_per_contract_usd`, `_pct`, `_per_vol_point`, `_per_calendar_day`.
- Every slice: failing business-rule test → minimal change in the existing owner → focused tests → regression →
  Lab check → receipt. Commit only when ACK asks.

## Slice 1 — verified defects (each fixed on its own, test-first)

| # | Defect (verified 29 Sep) | Owner | Fix |
|---|---|---|---|
| 1a | `vega_risk_pct` 100× too small (per-share 10-point loss ÷ per-contract premium) | `scripts/avshunter_options_intelligence.py` ~6783 | loss per contract = vega × 10 × 100 |
| 1b | "Too late" check always uses the call wall as a put's stop, ignoring the recorded stop (operator precedence) | same file ~8977 | parenthesise the side choice; recorded stop first |
| 1c | Lab prints "+" before a put's breakeven % | `intelligence-lab/static/index.html` | signed display by side |
| 1d | Legacy EV v2 wrong for puts and IV adjustment sign inverted | `ev_engine_v2.py` (four copies) | **ACK decision:** retire from display (recommended — it is labelled "not real EV") or repair |
| 1e | Provider Greeks replaced by Heston/BSM Greeks without provenance | Options Intelligence | publish `contract_greeks_source` |

Reported but still to verify before fixing: Kelly sizing forces ≥ 1 contract above the risk budget; journal
`rr_realised = pnl% / breakeven%`; `emp_path_*`/`contract_value_*` reach the book without the quote-ownership gate;
Lab "Expected Move 6–10d / 11–20d" shows increments; monitor exits priced at mid/last or (open+close)/2.

## Slice 2 — standard contract analytics block

One function `contract_analytics(identity, quote, spot, contracts=1)` in `selected_contract_economics.py`, called
wherever the contract identity is set (Evening selection and Morning hydration), published in the Lab book, shown in
the signal modal as "Contract analytics":

- intrinsic value per share at the current spot; extrinsic = mid − intrinsic (and ask − intrinsic);
- expiry breakeven at the ask (call K + ask, put K − ask) and the move to it in %;
- maximum loss per contract = ask × multiplier × contracts;
- delta exposure (share equivalent) and dollar delta;
- theta in $ per contract per calendar day; vega in $ per contract per IV point; spread % of mid;
- market-implied move to expiry and over the planned hold: S × IV × √(days / 365), with the IV source named.

## Slice 3 — required move-to-return

Inverse solve on the one pricer: the underlying price needed for the option's **bid** to reach +50 % and +100 % of
the entry ask after 1, 3, 5, 10 sessions and the planned hold, with IV unchanged and IV −10 % (relative). Shown as a
small table; labelled "price required, not a probability" until the ticker forecast (TEV-001 C4/C5) supplies the
probability of that move.

## Slice 4 — implied move versus forecast move

Display the market-implied move over the hold beside the pipeline's volatility-budget move and their ratio, labelled
as a volatility-premium diagnostic. **Display only:** the 30 Sep real-price test found no option edge from volatility compression (calm stocks' options already carry 1.2–1.25 × realised volatility; real excess ≈ 0), so this is context for the trader, not a signal (`AVS_VOLATILITY_LEAD_REAL_PRICE_TEST_PREREGISTRATION_20260929.md`).

## Slice 5 — realised slippage and P&L attribution (post-trade learning)

For journal trades: slippage = fill − reference quote (mid and ask at decision time); attribution of the realised
option change into delta, gamma, vega, theta and execution cost from entry/exit quotes and Greeks, with a residual.
Prerequisite: executable exit marks (bid) in the monitor instead of mid/last/(open+close)/2.

## Not in this build (tracked under TEV-001)

EV from the option return distribution (C8 on the ticker forecast's path set, one owner, EV engines consolidated);
premium target/stop rules (the 29 Sep replay shows tight premium stops lower EV; adopt only on replay evidence);
any use of these fields in a gate, rank or permission.

## Decisions for ACK

1. Approve slices 1–5 and their order.
2. Legacy EV v2: retire from display, or repair.
3. Slice 4 is display-only (settled by the 30 Sep real-price test).

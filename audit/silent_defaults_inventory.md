# AVS-FIX-002 silent numeric default inventory

Scope: monetisability, rate, dividend, volatility, spread, target and probability paths.

| Site | Prior behaviour | Stage 2–5 disposition |
|---|---|---|
| `canonical_data/dynamic_options_production.py` rate | per-row lookup, absent stopped all valuation | one `MarketRateObservation` per run; absent is `RATE_UNAVAILABLE`; explicit legacy row rate remains a labelled compatibility input |
| `canonical_data/dynamic_options_production.py` dividend | absent became 0 | raw absence remains `dividend_yield_available=false`; zero is disclosed BS assumption and cannot become observed evidence |
| `layer3_forward_variance.py` failed forecast | legacy zero display fields | `volatility_budget_v2` publishes null and `NOT_EVALUATED_DATA_MISSING`; legacy fields remain marked deprecated |
| `trigger_layer.py` expected move | differenced percentage | prefers cumulative fraction; legacy percentage conversion is explicit |
| `contracts/opportunity_tier.py` spread | ambiguous `spread_pct` compared as fraction | canonical fraction projector; frozen v1 field adapted explicitly as `FRACTION_OF_MID` |
| `canonical_data/dynamic_options_valuation.py` quote time | missing provider time became observation time | fallback removed; named `MISSING_PROVIDER_QUOTE_TIMESTAMP` exception |
| `domain/contract_economics_v2.py` target/IV/quote | missing inputs could resemble zero economics | null produces `NOT_EVALUATED_DATA_MISSING`; invalid quote produces `DATA_DEFECT` |
| `domain/capacity_suggestion.py` multiplier/budget | implicit multiplier or size | missing config produces `CONFIG_UNAVAILABLE`; no assumption of 100 or desk budget |
| DOI probability outputs | deterministic score could be read as probability | `ranking_score_kind=DETERMINISTIC_UTILITY`; calibration fields remain unavailable/null |

Known legacy computations outside the v2 authority path remain compatibility output and are not evidence for `lab_signal_book_v4`.

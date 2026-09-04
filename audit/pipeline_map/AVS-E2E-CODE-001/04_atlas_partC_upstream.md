# Part C — Upstream: macro, packages, Discovery, Vanguard

_Consolidated from lane C working files (`_scratch_discovery.md`, `_scratch_vanguard.md`). Lane C was terminated by a session limit before it wrote its own consolidated fragment; these are its completed sections, unmodified._

### avshunter_discovery_ULTIMATE.py

**Classification:** ORCHESTRATED — subprocess stage, 2,686 lines.

**Real execution position:** stage 10 of 51, evening. Invoked by `intelligent_orchestrator.py::evening_workflow` at L4115 (`run_discovery`), script path from `OrchestratorConfig` L424. [OBSERVED `03_execution_order.md` §2]

**Task in the process:** Loads the augmented universe, fetches or reads daily bars per ticker, runs the Wyckoff engine and the Crabel/Precor state machine, computes a composite score, applies a regime × phase prior adjustment and a staleness decay, assigns a tier (0/1/2/3, tier 4 discarded), derives a preliminary direction hint, computes structural stop/target and a ranking score (`lift_proxy_score`), stamps a preliminary `horizon_bucket` and a scaffold `dte`, and writes one row per surviving ticker to `discovery/discovery_candidates_ultimate_<TS>.csv` plus four sibling artefacts. It is the first stage that produces a per-ticker candidate record and the first that writes a direction field.

**Entry points:** `main()` L2336 (argparse CLI, `--universe`, `--force-update`, `--lookback-days`, `--progress-every`); `scan_ticker_ultimate()` L1303 is the per-ticker unit.

**Imports (production):** `WyckoffEngine_3101_v2.WyckoffEngine_3101_v2` (L42) · `polygon_data_fetcher.PolygonDataFetcher` (L43) · `wyckoff_crabel_precor_logic_v2.process_precore_signal` (L44) · `wyckoff_phase_validator.{prefixed_validation_fields, validate_wyckoff_phase}` (L45) · `contracts.direction_governance.preliminary_discovery_direction` (L46) · `scripts.macro_quant_packet.{build_macro_quant_packet, macro_quant_columns_for_row, missing_macro_quant_packet}` (L48–52, with a bare-name `except` re-import at L54–58) · `swing_fusion.fuse_wyckoff_crabel`, `asymmetry_gate_swing.compute_asymmetry_swing`, `enums_structural.{Direction, Intent}` (L64–66, guarded by `try/except ImportError`) · `regime_threshold_injector.apply_regime_to_config` (L2359, inline).
· **Imported by:** none in production; invoked as a subprocess. [OBSERVED — no `import avshunter_discovery_ULTIMATE` in the repo]
· **Broken/retired imports:** `enums_structural.{Direction, Intent}` are imported at L66 and never referenced anywhere in the file [OBSERVED]. `_SWING_FUSION_AVAILABLE = False` (L69) silently degrades direction and asymmetry geometry to "WyckoffEngine only" with a warning only (L71–74).

**Inputs**
- Files/tables read: universe CSV (`--universe`, default `data/universe/polygon_liquid_universe.csv`); per-ticker bar cache under `data/` via `load_bars` L930; `dropbox/macro/macro_intelligence_latest.json` (L2360, L2369); `dropbox/macro/sec_activist_signals.json` (L2278); sector map via `_load_sector_map` L1224 and the universe sector lookup L1248; scanner context (`vms_context`) injected onto `cfg`.
- Upstream fields consumed (with fallback chains):
  - `wyckoff_data.get('truth_confidence', 50.0) or 50.0` (L1461) — **missing → 50.0**, a mid-scale numeric standing in for "not measured".
  - `wyckoff_data.get('dominant_event','TR') or 'TR'` (L1462) — **missing → 'TR'** (trading range), i.e. absent evidence is encoded as a real categorical event value; `_normalise_event` L742–743 additionally maps `'NONE'` and `''` to `'TR'`.
  - `wyckoff_data.get('execution_bias','OBSERVE_ONLY')` (L1467); `setup_quality` → `'Observe'` (L1470); `wyckoff_mode` → `'UNKNOWN'` (L1483).
  - `precor_data.get('transition_conf', 0.0) or precor_data.get('transition_confidence', 0.0) or 0.0` (L1481–1482) — three-step `or` chain; a genuine 0.0 confidence is indistinguishable from a missing key.
  - `crabel_result.get('compression', 0.85) or 0.85` (L1444) — **missing → 0.85**, which is exactly `cfg.compression_max`, so "no compression measured" scores as "worst measurable compression" and `comp_strength` becomes 0.0 (L1445).
  - `_macro_sector_tilt.get(_ticker_etf, 'NEUTRAL')` (L1863) and `_etf_signal_score.get(..., 0.0)` (L1864) — unknown sector ETF and unknown signal string both collapse to lift 0.0.
  - `_vms_ticker_data.get('scanner_signal_type') or .get('scanner_decision') or _vms_decision or ''` (L1421–1426).
  - `getattr(cfg, 'active_regime', 'UNKNOWN')` (L598, L1396, L2108, L2109).
- External calls: Polygon via `PolygonDataFetcher` inside `load_bars` L930; results cached on disk, `--force-update` bypasses the cache. `df.attrs['data_source']` records `POLYGON_FRESH | CACHE_OK | STALE_CACHE` (L2162).
- Config/policy read: `UltimateConfig` L94–134 (price 5–500, min avg vol 500 000, `min_adv_dollars` 2 500 000, `min_atr_dollars` 0.40, `min_atr_pct` 1.0, tier floors 50/35/25, `risk_off_composite_floor` 72.0, `min_bars` 30); regime-dependent overrides applied by `regime_threshold_injector.apply_regime_to_config` at L2361.

**Logic and algorithms**
- Hard liquidity/viability rejection ladder, `scan_ticker_ultimate` L1313–1343: `len(df) < min_bars` → None; price outside 5–500 → None; `vol20 < 500 000` → None; `adv_dollars < 2 500 000` → None; `atr_14 < 0.40` → None; `atr_pct < 1.0` → None. [OBSERVED]
- Wyckoff phase state machine (external, `WyckoffEngine_3101_v2.analyze` L1346) and Crabel/Precor state machine (`process_precore_signal` L1352, wrapped in `try/except` that logs at DEBUG and leaves `precor_data = None`, L1353–1354).
- Phase selection rule L1398–1403 and again L1909–1914: Precor's phase replaces Wyckoff's when `precor_conf > wyckoff_conf`. The two blocks use different confidence variables (`phase_evidence_strength` at L1401 vs `phase_strength` at L1907) but resolve identically.
- `_reconcile_intent` L291–335 — a four-rule intent reconciliation (detailed below).
- `assign_tier` L587–613 — regime-adaptive tier floors.
- `apply_state_prior_adjustment` L847–918 — regime × phase prior lookup plus late-trend penalty plus staleness decay.
- `assign_discovery_horizon` L2241–2267 — preliminary three-bucket horizon.
- Decision branches (CALL / PUT / other-blank):
  - `_candidate_direction` L1580 = `preliminary_discovery_direction(fusion.direction, wyckoff.trade_direction)`; the callee returns the first of the two that normalises into `{CALL, PUT}`, else `UNRESOLVED` (`contracts/direction_governance.py:98-104`). It never defaults to CALL. [OBSERVED]
  - `vwap_acceptance_score` L1689–1709 — **CALL:** four sub-branches 1.0 / 0.2 / 0.3 / 0.6; **PUT:** mirror-image four sub-branches 1.0 / 0.2 / 0.3 / 0.6; **other/blank (UNRESOLVED, STRANGLE, NONE, ""):** single `else` at L1707 → **0.5**.
  - `repricing_direction` L1712–1720 — **CALL/PUT aligned** → the direction itself; **CALL/PUT counter-aligned** → `COUNTER_CALL` / `COUNTER_PUT`; **other/blank** → literal `'UNRESOLVED'` (STRANGLE and NONE are both flattened to `UNRESOLVED` here, losing the distinction).
  - `_ema_aligned` L1733–1736 — **CALL** requires `dominant_trend == 'BULLISH'`; **PUT** requires `'BEARISH'`; **other/blank** can never be True, so the term contributes `0.3 × 10 = 3.0` instead of `10.0` to `abnormal_repricing_score` (L1744).
  - Structural target validity L1809–1813 branches on `wyckoff_data['trade_direction']` ∈ `{LONG, SHORT, NONE}` — a **third vocabulary** for direction, distinct from both `{CALL,PUT,UNRESOLVED}` and the fusion `{LONG,SHORT,NONE}` used at L1376. `NONE` gets a ±30 % proximity test instead of a sign test.
  - Structural stop L1802–1805 (`ATR_FALLBACK`) is computed as `current_price - _atr_stop_dist` with **no direction branch at all**.

**Computations and formulas (exact)**
- `composite_score = (wyckoff_score * 0.6) + (crabel_score * 0.4) if crabel_score > 0 else wyckoff_score` (`calculate_composite_score` L623–631). Units: points on the same 0–100 scale as the two inputs. No clamp. **The documented `0.60*wyckoff + 0.40*crabel` is therefore PARTIAL**: it holds only on the `crabel_score > 0` branch.
- `win_probability = min(75.0, max(35.0, 40.0 + composite * 0.25))` (`calculate_win_probability` L634–643), where `composite` is the L623 composite, not the prior-adjusted one. Units: percent. Bounds 35–75. The lower bound is unreachable for any non-negative composite because `40 + 0.25·c ≥ 40`; the upper bound requires `composite ≥ 140`, above the observable 0–100 range. Effective range is therefore 40.0–65.0. No calibration term, no lookup, no fit. **It is a bounded linear heuristic of the composite, not a calibrated probability.**
- `adjusted = composite_score + adj`, then `adj = max(-20.0, min(+15.0, adj))` applied *before* the addition (L887–889); `adj = _STATE_PRIOR_ADJUSTMENTS.get((bucket, regime), 0.0)` (L879) plus `_LATE_TREND_PENALTY = -8.0` when `trend_maturity ∈ {LATE, EXHAUSTED}` and `regime != 'RISK_OFF'` (L883–884).
- Signal decay L906–916: `_decay = min(days_old * 0.03, 0.20)`; `adjusted = adjusted * (1.0 - _decay)`. Multiplicative, cap 20 %, wrapped in `try/except: pass` (L915–916).
- `comp_strength = max(0.0, min(1.0, (0.85 - compression) / 0.85))` (L1445), 0–1.
- `_pa_raw = truth_conf/100*30 + event_ev/100*25 + phase_ev/100*20 + _event_bonus + _recency*15 + _trans_score*10` (L1560–1567); comment at L1568 states max = 115; `_pa_normalised = min(1.0, _pa_raw/100.0)` (L1570) — the 0–115 raw scale is normalised by 100 and clamped, so every candidate scoring above 100 raw is flattened to 1.0.
- `phase_align = round(min(1.0, _pa_normalised + _regime_boost), 3)` where `_regime_boost = {'RISK_OFF': 0.05, 'RISK_ON': 0.02}.get(regime_norm, 0.0)` (L1573–1574).
- `regime_align = {'RISK_ON': 0.6, 'RISK_OFF': 0.75, 'TRANSITIONAL': 0.45}.get(regime_norm, 0.5)` (L1588–1589), 0–1.
- `lift_proxy_score` is computed **twice**. First at L1619–1627 with weights 28/19/19/19/9/6 and `_sector_lift_placeholder = 0.0` (L1617). Then recomputed at L1891–1903 with weights 20/20/10/12/10/6/10/6/4/2 and the real `_sector_lift`. Only the second value reaches the dict (L1964). The first computation is dead. [OBSERVED]
- `abnormal_repricing_score = _gap_score_raw*20 + _vol_score_raw*20 + _range_score_raw*15 + vwap_acceptance_score*15 + _dv_score_raw*10 + vol_expansion_potential*10 + (1.0 if _ema_aligned else 0.3)*10` (L1737–1746), 0–100, rounded to 1 dp.
- `gap_pct = (open_today - prev_close)/prev_close*100` (L1661); `range_pct = (high-low)/px*100` (L1666); `range_expansion_vs_20d = (high-low)/avg_range_20d` (L1671); `dollar_volume_zscore = (dv_today - dv_mean)/dv_std` with `dv_std` defaulting to 1.0 when fewer than 5 prior bars (L1673–1679).
- `rr_underlying = round(abs(structural_target - current_price) / max(current_price - structural_stop, 0.01), 2)` when a target exists, else `asymmetry_result['R_to_T1'] or round(atr_14*3.0 / max(current_price - structural_stop, 0.01), 2)` (L2054–2060). `rr` L2067–2073 is a byte-identical duplicate of the same expression. Capped post-hoc at `_MAX_RR = 50.0` with `rr_flag ∈ {RR_OK, RR_ANOMALY_ZERO_RISK, RR_ANOMALY_CAPPED_FROM_<x>}` (L2206–2216).
- `dte = _DTE_SCAFFOLD.get((min(tier,3), phase[:1].upper() or 'C'), 45)` (L2188–2191, table L2229–2234). Units: calendar days. Never 0.
- `_bar_days_old_safe` L818–831 returns `999` on any parse failure or unknown `data_as_of`; `_is_stale = data_source == 'STALE_CACHE' or bar_days_old > 5` (L1921).

**Models**
- **Composite scorer** — rule/linear blend. Inputs `wyckoff_score`, `crabel_score`. Parameters 0.6 / 0.4, with an unconditional pass-through branch when `crabel_score == 0`. Output `composite_score` 0–100. No calibration source claimed. No version tag. (L623–631)
- **Win-probability heuristic** — linear map. Input composite. Parameters intercept 40.0, slope 0.25, clamp [35, 75]. Output `win_probability` in percent. Docstring says only "Estimate win probability" (L635); no calibration source, no version tag. (L634–643)
- **State-prior table `_STATE_PRIOR_ADJUSTMENTS`** — 9-cell lookup keyed `(phase_bucket, regime)`, values +2/+10/+1/−5/+12/+3/−15/−12/−12 (L666–676). Calibration source *claimed* in the comment at L648: "Empirically derived from 3.7M cleaned actuarial observations. Source: validate_enrichment.py output". No version tag. **The table is unreachable** — see CON-201.
- **Late-trend penalty** — scalar rule, `-8.0`, gated on regime (L680, L883–884).
- **Signal decay** — exponential-free linear decay, 3 %/day, cap 20 % (L911).
- **Tier assigner** — threshold rule set with regime-conditional floors 50 / 68 / 72 (L587–613).
- **DTE scaffold** — 20-cell `(tier, phase)` lookup, default 45 (L2229–2238). Comment L2227–2228 claims it "mirrors DTE_MATRIX in avshunter_options_intelligence.py"; not verified here (that file is outside this lane) — recorded as GAP-207.
- **`lift_proxy_score` v3** — weighted linear sum of 10 normalised components, weights documented at L1876–1887 and matching the code at L1891–1903. Comment L1437 claims "Weights derived from empirical Hit10 differentials in actuarial DB"; no source artefact, query or fit is referenced anywhere in the file. Recorded as GAP-201.
- **`abnormal_repricing_score`** — weighted linear sum of 7 components, weights 20/20/15/15/10/10/10 (L1737–1746). No calibration claimed.

**Outputs**
Written by `main()` L2559–2569 and following:
- `discovery/discovery_candidates_ultimate_<TS>.csv` — the full signal dict (L1941–2201), ≈180 columns.
- `discovery/discovery_lifecycle_<TS>.csv` — one governed outcome row per input ticker: `ticker, outcome, lifecycle_state, reason_code, next_stage, horizon_bucket, tier` (L2487–2550, written L2569). A hard reconciliation check raises `RuntimeError` if the row count differs from the input ticker count (L2574–2578).
- `discovery/early_positions_ultimate_<TS>.csv`, `final_watchlist_ultimate_<TS>.csv`, `discovery_summary_ultimate_<TS>.json` (paths L2561–2565).
- Atomic promotion: **no**. `pd.DataFrame(...).to_csv(path)` writes directly to the final path (L2569 and the equivalent writes below it); there is no temp-file-then-rename. The orchestrator subsequently rewrites the candidates CSV in place at stage 12 (L4126) and three times via `patch_horizon_fields_into_csv`.
- Schema/version field: **none**. No `schema_version`, `contract_version` or `calc_version` column is written. [OBSERVED — grep over the signal dict]
- Fields carrying authority claims:
  - `direction_authority = 'DISCOVERY_PRELIMINARY_ONLY'` (L2038) — **HOLDS** as a label; the value is a hard-coded constant and Discovery genuinely does not resolve direction (L1580 delegates to the governance module, which returns `UNRESOLVED` on ambiguity).
  - `'direction'` written as an exact alias of `discovery_direction_preliminary` (L2036–2037) with the comment "It has no post-structure authority" — **PARTIAL**: within this file the claim holds, but the generic column name `direction` is the one most downstream CSV readers key on, and the alias carries no marker distinguishing it from a resolved direction. Recorded as CON-205.
  - `macro_regime` commented as "the canonical field name read by Vanguard and Edge Detector" with `active_regime` as an alias (L2106–2107) — **HOLDS** in this file; both are written from the same `getattr(cfg,'active_regime','UNKNOWN')`.
  - `rr_underlying` commented "Computed here once; all downstream modules read this field" (L2053) — **FALSE** within this file: the identical expression is computed a second time into `rr` at L2067–2073, and both are mutated again at L2213–2214.

**Handoff**
- Receives from: `scripts/build_packages_from_discovery.py` does not precede it — Discovery is upstream of the *second* package build; it receives the augmented universe from orchestrator stages 1–2 and the macro artefacts from stages 6–8.
- Hands to: `scripts/apply_external_intel_review_lane.py` (stage 11), `scripts/apply_macro_enrichment_to_discovery.py` (stage 12, rewrites the same CSV), then packages and Vanguard.
- Join keys: `ticker` (upper-cased at L2488, L2510, L2528 in the lifecycle rows; **not** upper-cased in the signal dict — L1942 writes `ticker` as received). Recorded as GAP-205.

**Missing-data handling**
| Condition | Emitted value/state | file:line | §10-compliant? |
|---|---|---|---|
| No bars for ticker | lifecycle `DROPPED_TERMINAL_DATA` / `NO_PRICE_DATA` | L2490–2491 | N — vocabulary is local, not §10; the closest §10 term is `UNAVAILABLE_PROVIDER` |
| Rejected by liquidity/viability filters | `scan_ticker_ultimate` returns `None`; lifecycle row `DROPPED_STAGE` / `NO_SIGNAL_AT_ANY_HORIZON` | L1324–1343, L2542–2549 | N — the reason code says "no signal", which is not what happened |
| Tier 4 | returns `None`, same `NO_SIGNAL_AT_ANY_HORIZON` code | L1641–1642 | N — same conflation |
| `truth_confidence` missing | `50.0` | L1461 | N — numeric default indistinguishable from a measured 50 |
| `dominant_event` missing | `'TR'` | L1462, L742–743 | N — categorical default `TR` is also a legitimate measured value |
| `compression` missing | `0.85` (= `compression_max`) | L1444 | N |
| `move_age_bars` missing | `_recency = 0.5`; bucket `'UNKNOWN'` | L1520, L792 | N (`UNKNOWN` is not a §10 term) |
| `data_as_of` unparseable | `bar_data_days_old = 999`, `is_stale = True` | L818–831, L1921 | N — 999 is a sentinel numeric, not a state |
| macro JSON missing/unreadable | `cfg.macro_sector_signals = {}`, `cfg.macro_quant_packet = missing_macro_quant_packet(path)` | L2384–2385, L2392–2394 | Partially — the packet helper emits an explicit missing-state object; the sector dict silently becomes empty, which is then indistinguishable from "all sectors NEUTRAL" (L1863) |
| `apply_regime_to_config` raises | `active_regime = "TRANSITIONAL"`, label `"DEFAULT (injection error)"` | L2390–2391 | N — an error is bridged into a real regime value that then modulates tier floors and scores |
| No structural target | `structural_target = None`, `_target_source = 'PENDING_OI'` | L1820–1821 | N — `PENDING_OI` is a local term |
| Options fields not yet priced | `expiry/strike/contract_type/bid/ask/premium/iv/ivp = None` | L2192–2199 | N — bare `None`, no `PENDING_*` state |
| Activist file missing or malformed | `{}` returned, `except Exception` logs at INFO | L2279–2294 | N, but the field is explicitly advisory (L2276) |

**Contradictions found here:** CON-200, CON-201, CON-202, CON-203, CON-204, CON-205, CON-206, CON-207, CON-208
**Gaps found here:** GAP-200, GAP-201, GAP-202, GAP-203, GAP-204, GAP-205, GAP-206, GAP-207

**Comment/docstring claims audited:**
- L60–62 "swing_fusion is the single authority for direction + intent" → **PARTIAL**. `_candidate_direction` (L1580) takes fusion first but falls back to `wyckoff_data['trade_direction']`, and when the import fails (L68–74) fusion never runs at all and the Wyckoff value is the only source.
- L300–305 `_reconcile_intent` Rule 3 "dominant trend is strongly BULLISH (EMA stack + **60+ days** above EMA50)" → **FALSE**. The coded condition is `days_above >= 40` (L332), and the docstring omits the fourth conjunct `pct_from_low >= 25` entirely.
- L307 "The raw intent is always preserved in precor_intent_raw for auditability" → **HOLDS** (L2083).
- L588–596 `assign_tier` docstring "RISK_OFF: >= 72 for Tier 1 … RISK_ON: >= 50 standard" → **HOLDS** (L599–606), with the qualification that failing the floor yields Tier 2, not rejection.
- L615–620 "In RISK_OFF: ACCUMULATION/MARKUP stocks receive +10/+12 prior boosts. Stocks with raw scores ~39-41 land at ~51-53 adjusted" → **FALSE**, consequent on CON-201: no `_STATE_PRIOR_ADJUSTMENTS` key can ever match, so no boost is ever applied.
- L648–664 "Empirically derived from 3.7M cleaned actuarial observations … Score adjustments are bounded: max +15, min -20 … Applied to composite_score BEFORE tier assignment" → **PARTIAL**. The bounds claim HOLDS (L887) and the ordering claim HOLDS (L1406 precedes L1637). The derivation claim is unverifiable from this repo and, given CON-201, has no effect.
- L683–705 `_wyckoff_phase_to_bucket` "This is the granular bucket used for setup quality scoring. The broad bucket … is preserved separately for actuarial DB state hash backward compatibility" → **FALSE as applied**. `apply_state_prior_adjustment` calls the *granular* mapper at L867 and looks the result up in a *broad*-keyed table.
- L834–837 `_wyckoff_phase_to_broad_bucket` "Used for wyckoff_phase_bucket field only (do not use for scoring)" → **HOLDS** (called only at L1438, written at L1994).
- L863–865 "injects known historical asymmetry into Discovery WITHOUT querying the actuarial DB at runtime" → **HOLDS** for the no-query half; the injection half is void per CON-201.
- L1456–1458 "Direction plays no role in any scoring component below. A strong DISTRIBUTION setup scores identically to a strong ACCUMULATION setup of the same evidence quality." → **FALSE**. `vwap_acceptance_score` (L1689–1709) and `_ema_aligned` (L1733–1736) are both direction-conditional and both feed `abnormal_repricing_score` (L1741, L1744); `vwap_acceptance_score` additionally carries weight 4.0 in `lift_proxy_score` (L1900). An `UNRESOLVED` candidate is scored 0.5 and 0.3 on those two terms against a directed candidate's possible 1.0 and 1.0.
- L1572 "Regime modulates conviction (not direction)" → **HOLDS** for `_regime_boost`.
- L1586 `regime_align` "Not direction-biased" → **HOLDS**.
- L1614–1617 "A placeholder is used so lift_proxy_score can be computed in one place" → **FALSE**; it is computed in two places (L1619, L1891) with different weight vectors.
- L2053 "Computed here once; all downstream modules read this field" → **FALSE** (see Outputs).
- L2106–2107 "'macro_regime' is the canonical field name read by Vanguard and Edge Detector" → **HOLDS** within this file.
- L2179–2187 "Discovery does not price options … OI will overwrite with the actual selected contract DTE after chain fetch" → **PARTIAL**; the write here is OBSERVED, the overwrite claim concerns a file in another lane.
- L2227–2228 "_DTE_SCAFFOLD mirrors DTE_MATRIX in avshunter_options_intelligence.py" → **NOT VERIFIED here** (GAP-207).
- L2242–2250 `assign_discovery_horizon` "1_5d: Tier 0/1 with immediate trigger confirmed … None: NO_SIGNAL_AT_ANY_HORIZON — only legitimate discard" → **FALSE**; see CON-203 and CON-204.
- L2276 activist signals "ADVISORY ONLY — never gates any discovery verdict" → **HOLDS**; `_enrich_with_activist_signals` (L2297) only adds columns.

**Confidence in this section:** HIGH — every claim is a direct read of the cited lines; the two claims with numeric consequences (CON-201, CON-203) are stated as INFERRED with the settling query attached.

---

## Discovery priority deep-dive — resolved

### D1. Every macro read in Discovery and precisely what it modulates

| # | Macro read | file:line | What it modulates | Can change DIRECTION? | Can BLOCK a ticker? |
|---|---|---|---|---|---|
| 1 | `apply_regime_to_config(cfg, macro_intelligence_latest.json)` → `cfg.active_regime`, tier floors, compression thresholds, volume minimums | L2359–2361 | `cfg` fields consumed by every filter below | No | **Yes, indirectly** — the injector mutates `min_avg_vol20`/compression thresholds, and L1328/L1338–1343 return `None` on those thresholds |
| 2 | `active_regime` → `assign_tier` regime floors | L598–606 | Tier 1 → Tier 2 demotion at composite < 72 (RISK_OFF) or < 68 (TRANSITIONAL) | No | **No** — demotion is to Tier 2, which survives |
| 3 | `active_regime` → `apply_state_prior_adjustment` state-prior table | L847–879 | `composite_adjusted` | No | **No** — the lookup never matches (CON-201), so contribution is 0.0 |
| 4 | `active_regime` → late-trend penalty gate | L883–884 | `composite_adjusted` −8.0 when maturity is LATE/EXHAUSTED **and** regime ≠ RISK_OFF | No | **Yes** — an 8-point subtraction can carry `composite_adjusted` below `tier3_min = 25.0`, giving tier 4 at L612 and `return None` at L1641 |
| 5 | `regime_norm` → `_regime_boost` in `phase_align` | L1573–1574 | `phase_align` +0.05 (RISK_OFF) / +0.02 (RISK_ON) / +0.0 | No | No (boost only) |
| 6 | `regime_norm` → `regime_align` score | L1588–1589 | `lift_proxy_score` weight 10.0 | No | No (ranking only) |
| 7 | `cfg.macro_sector_signals[sector_etf]` → `_sector_lift` | L1861–1870 | `lift_proxy_score` weight 6.0 on `(lift+1)/2` | No | No |
| 8 | `macro_abstain` from the universe file | L1871, L2155 | Written as a display/annotation column only | No | No |
| 9 | `macro_quant_columns_for_row(cfg.macro_quant_packet, …)` | L2156–2159 | Annotation columns spliced into the row | No | No |
| 10 | `macro_regime` / `active_regime` annotation columns | L2108–2109 | Display + downstream state keys | No | No |

**Documented policy "macro must neither change direction nor block a ticker": DIRECTION — HOLDS. BLOCK — FALSE.**
Direction is produced solely at L1580 from fusion and Wyckoff outputs; no macro value is an input to `preliminary_discovery_direction`, and no later line reassigns `_candidate_direction`. [OBSERVED]
Blocking fails on two independent paths: (a) the regime injector rewrites the hard liquidity/compression thresholds that produce `return None` at L1328 and L1338–1343 [OBSERVED L2361 + L1324–1343]; (b) the regime-gated `_LATE_TREND_PENALTY` at L883–884 subtracts 8.0 from the score that `assign_tier` thresholds at 25.0, and tier 4 is discarded at L1641 [OBSERVED]. Both are INFERRED as to *frequency*, HIGH confidence as to *possibility*.
`NEEDS_MEASUREMENT:` count rows in `discovery_lifecycle_<TS>.csv` with `reason_code='NO_SIGNAL_AT_ANY_HORIZON'` whose `tier` is blank, then re-run `apply_state_prior_adjustment` offline with `_LATE_TREND_PENALTY = 0.0` over the same `composite_score`/`trend_maturity` pairs and count how many cross `composite_adjusted >= 25.0`.

### D2. Every use of `_candidate_direction` in scoring

Defined once at L1580. Used at exactly five sites:
1. **`vwap_acceptance_score`** L1689–1709 — CALL branch L1689–1697 (1.0 / 0.2 / 0.3 / 0.6), PUT branch L1698–1706 (1.0 / 0.2 / 0.3 / 0.6, mirror image), `else` L1707–1709 → **0.5** for UNRESOLVED / STRANGLE / NONE / blank. Feeds `abnormal_repricing_score` at weight 15.0 (L1741), `lift_proxy_score` at weight 4.0 (L1900), and the `VWAP_ACCEPTANCE` / `VWAP_REJECTION` reason codes (L1763–1764).
2. **`repricing_direction`** L1712–1720 — emits `CALL`, `PUT`, `COUNTER_CALL`, `COUNTER_PUT` or `UNRESOLVED`; STRANGLE and NONE are both collapsed into `UNRESOLVED`. Written to the CSV at L1974.
3. **`_ema_aligned`** L1733–1736 — True only for `CALL ∧ BULLISH` or `PUT ∧ BEARISH`; every other combination, including all non-directed values, yields False and contributes `0.3 × 10.0 = 3.0` instead of `10.0` (L1744).
4. **`discovery_direction_preliminary`** L2036 — verbatim write.
5. **`direction`** L2037 — verbatim alias write.

Net effect: an `UNRESOLVED` candidate is deterministically penalised against an otherwise identical directed candidate by `(1.0 − 0.5) × 15.0 + (1.0 − 0.3) × 10.0 = 14.5` points of `abnormal_repricing_score` and `(1.0 − 0.5) × 4.0 = 2.0` points of `lift_proxy_score`. `abnormal_repricing_score` sets `repricing_state` (L1749–1756) and `_candidate_lane` (L1926–1931), and `lift_proxy_score` is the default sort column for the watchlist (L2594). [OBSERVED]

### D3. `_DTE_SCAFFOLD` vs `assign_discovery_horizon` — decoupling

They are **fully decoupled**: two different key spaces, two different call sites, no cross-reference.

- `_DTE_SCAFFOLD` (L2229–2234) is keyed `(min(tier,3), phase_letter)` and returns 21–75 **calendar days**, default 45 (L2238). Called once, inside `scan_ticker_ultimate`'s dict at L2188, writing the column `dte`. The phase argument is `phase[:1].upper()` with the literal fallback `'C'` when `phase` is empty (L2190) — a blank phase is silently treated as a spring/test.
- `assign_discovery_horizon` (L2241–2267) is keyed on `tier`, `trigger_quality`, `composite` and `wyckoff_phase`, and returns a **bucket string** `1_5d | 6_10d | 11_20d | None`. Called once, in `main()` at L2504, writing `horizon_bucket` (L2518) and `discovery_basis` (L2519–2523).
- They disagree by construction. A Tier 1 / Phase C candidate gets `dte = 38` (38 days to expiry) and `horizon_bucket = '1_5d'` (a 1–5 trading-day hold). A Tier 3 / Phase A candidate gets `dte = 75` and `horizon_bucket = '11_20d'`. There is no code path that reconciles the two, and no assertion anywhere in the file that `dte ≥ the upper bound of horizon_bucket`.
- **Which one downstream consumes:** `dte` is consumed by the packages builder and the monetisation policy per the comment at L2181–2183; `horizon_bucket` is consumed by the packages/lifecycle path and is the field the Horizon Router (stage 19) later re-derives. Within this lane both are written; neither is read back.
- `assign_discovery_horizon` is additionally **partly dead** (CON-203): it reads `signal["wyckoff_phase"]`, `signal["phase_best"]` and `signal["trigger_quality"]`, and **none of those three keys exists in the signal dict** built at L1941–2201 (the dict writes `phase` at L1955, `current_phase` at L2005 and `precor_phase` at L2076; grep for `trigger_quality` in this file returns only L2254). So `wyckoff_phase` is always `""`, `trigger_quality` is always `""`, and the branches `trigger_quality in ("STRONG","SINGLE")` (L2258) and `wyckoff_phase in ("B","C")` (L2261) can never fire. The surviving logic is purely `tier` and `composite_score`.
- And **wholly non-discarding** (CON-204): `tier` is always 0, 1, 2 or 3 by the time the router runs, because tier 4 already returned `None` at L1641. `tier in (0,1)` → `1_5d`; `tier == 2` → `6_10d`; `tier == 3` → `11_20d`. The `return None` at L2267 and the entire `NO_SIGNAL_AT_ANY_HORIZON` branch at L2505–2516 are unreachable.
- Finally, the `composite` the router reads is `signal["composite_score"]` — the **raw pre-prior** score (L1960, comment "raw (pre-prior)") — whereas the tier it also reads was assigned from `composite_adjusted` (L1630, L1637). The two inputs to one routing decision come from opposite sides of the prior adjustment.

### D4. `_reconcile_intent` Rule 3 override

`avshunter_discovery_ULTIMATE.py:329-333`:

```
if intent == 'SELL_SETUP':
    if dominant_trend == 'BULLISH' and ema_stack == 'ALIGNED' and days_above >= 40 and pct_from_low >= 25:
        return 'BUY_SETUP'
```

- **What it overrides:** the Precor engine's own `intent` output (`precor_data['intent']`, passed as `raw_intent` at L2078). It flips a bearish setup classification to a bullish one.
- **Exact condition:** four conjuncts — normalised intent is exactly `SELL_SETUP`; `_get_dominant_trend(df) == 'BULLISH'` (L234); `_get_ema_stack(df) == 'ALIGNED'` (L250); `_days_above_ema50(df) >= 40` (L262); `_pct_from_52w_low(df) >= 25` (L278). All four are computed from price bars inside this file, not from the engine.
- **Reachability:** Rule 1 (L319–321) returns `TRANSITION` first whenever either control state is `BUYERS`, so Rule 3 can only fire when *neither* engine reports buyer control — i.e. it flips SELL→BUY specifically in the case where no buyer control has been observed. [OBSERVED]
- **Docstring divergence:** the docstring at L303–304 states "60+ days above EMA50" and does not mention the `pct_from_low >= 25` conjunct at all. Verdict **FALSE**. (CON-200)
- **Additional defect:** the three rule-firing paths return the *normalised* value (`TRANSITION`, `BUY_SETUP`), but the pass-through at L335 returns `raw_intent` — the **un-normalised original**, retaining its original case and spaces (L312 computes `intent` but discards it on that path). Downstream comparisons against `'BUY_SETUP'` therefore succeed for overridden rows and may fail for untouched rows. (CON-202)
- **Direction consequence:** `precor_intent` is written at L2077 and is consumed by `contracts/direction_governance.structural_direction(precor_intent, trend)`, so Rule 3 sits on the path that resolves direction later in the pipeline.

### D5. The composite

**Coded formula (`avshunter_discovery_ULTIMATE.py:623-631`):**
```
composite_score = (wyckoff_score * 0.6) + (crabel_score * 0.4)   if crabel_score > 0
composite_score = wyckoff_score                                   otherwise
```
**Verdict on the documented `composite_score = 0.60*wyckoff_score + 0.40*crabel_score`: PARTIAL.** It is exact on the `crabel_score > 0` branch and wrong on the other. The branch introduces a discontinuity: at `crabel_score → 0⁺` the composite tends to `0.6·wyckoff`, but *at* `crabel_score = 0` it jumps to `1.0·wyckoff`, a 40 % step increase. A ticker with no measured compression therefore scores strictly higher than an otherwise identical ticker with weak measured compression. (CON-206)

Two further points on the same field:
- The `crabel_score` used in the formula is `crabel_result['score']` from `crabel_compression` (L1357–1358). The `crabel_score` **column written to the CSV** is `_crabel_score_raw`, taken from `precor_data['crabel_score']` (L1478, written L2022) — and because `'crabel_score'` appears twice as a key in the same dict literal (L1959 and L2022) the later write wins. The emitted column therefore does not reproduce the emitted `composite_score`. (CON-207)
- `composite_score` (L1960) is the raw value; `composite_adjusted` (L1961) is the value tiers were assigned from. Both are emitted, and downstream readers that key on the bare name `composite_score` get the pre-prior number.

### D6. `win_probability`

**Coded formula (`avshunter_discovery_ULTIMATE.py:634-643`):**
```
composite  = calculate_composite_score(wyckoff_score, crabel_score)
base_prob  = 40.0 + (composite * 0.25)
win_probability = min(75.0, max(35.0, base_prob))
```
**It is a bounded heuristic, not a calibrated probability.** Evidence: the sole input is the composite of two internal scoring engines; the intercept 40.0 and slope 0.25 are literals with no accompanying fit, table, or reference dataset; the docstring is "Estimate win probability" (L635) and the inline comment is "Cap at realistic levels" (L642); there is no calibration artefact, no back-test reference, no version tag, and no per-regime or per-phase term.

**Bounds:** nominally [35.0, 75.0], rounded to 1 dp at L1993. In practice the floor is unreachable — `base_prob = 40 + 0.25·composite ≥ 40.0` for any `composite ≥ 0`, and composite is a non-negative blend of two non-negative scores — so `max(35.0, ...)` is dead. The ceiling requires `composite ≥ 140.0`, outside the 0–100 range both engines emit. The realised range is therefore **40.0–65.0**, a 25-point band, monotone in composite with slope 0.25. [OBSERVED]
`NEEDS_MEASUREMENT:` `SELECT MIN(win_probability), MAX(win_probability), COUNT(*) FILTER (WHERE win_probability IN (35.0, 75.0)) FROM discovery_candidates_ultimate_<TS>.csv` — a non-zero count at either literal bound would refute the reachability analysis.

**Downstream consequence:** this heuristic is laundered into actuarial-named fields. `scripts/run_vanguard_from_packages.py:1191-1206` reads `discovery.win_probability`, divides by 100 if > 1.0, clamps to [0.30, 0.80], and assigns the single scalar to **all three** of `win_rate_5d`, `win_rate_10d` and `win_rate_20d`, then stamps `actuarial_source = ACTUARIAL_SOURCE_DISCOVERY_FALLBACK`. A structural heuristic thereby occupies fields whose names assert an empirical frequency, and the horizon dimension is flattened to a constant. (CON-208)

---

### scripts/run_vanguard_from_packages.py

**Classification:** ORCHESTRATED — subprocess stage, 1,589 lines.

**Real execution position:** stage 15 of 51, evening. Invoked by `intelligent_orchestrator.py::evening_workflow` L4183 (`run_vanguard_pipeline`), script path from `OrchestratorConfig` L434. [OBSERVED]

**Task in the process:** Reads the per-ticker package JSONs produced at stage 9, reconstructs an orchestrator-shaped payload per ticker (bars, discovery block, macro block), calls the Vanguard engine, flattens the returned layered result into one CSV row per ticker, applies a Phase-2 baton validation and a set of fallback bridges for missing actuarial outcomes, and writes `vanguard/vanguard_signals.csv` (PASS rows) plus diagnostic siblings.

**Entry points:** `main()` L1317.

**Imports (production):** `pandas`; `vanguard` package via the orchestrator adapter; helpers defined locally. · **Imported by:** none (subprocess). · **Broken/retired imports:** none observed.

**Inputs** — Files/tables read: `packages/*.package.json` via `load_package_paths` L1294 and the package index JSON; daily bars resolved from the package by `_resolve_daily_bars` L466 with `_try_load_ohlcv_from_value` L347. Upstream fields consumed (with fallback chains): `disc.get("phase") or disc.get("current_phase")` (L775); `disc.get("precor_intent") or disc.get("intent")` (L776); `disc.get("control_state","") or disc.get("precor_control","")` (L734); `disc.get("macro_regime") or disc.get("active_regime") or ""` (L737); `_ov(key)` L1125–1131 — `outcomes_sub.get(key) if not None else l2.get(key)`; `_ov("expected_value_20d") or safe_get(l2,"expected_value_20d")` (L1153). External calls: none direct; the Vanguard engine performs the actuarial DB read. Config/policy read: `MINIMUM_HEADERS` incl. `preferred_horizon` (L108) and the Phase-2 baton defaults L295–304.

**Logic and algorithms**
- Intraday-position / control-dynamics classifier, L700–719: substring matching on `dominant_event.lower()` — `"up"|"breakout"|"markup"` → `AT_RESISTANCE`/`BUYERS_STRENGTHENING`; `"down"|"breakdown"|"markdown"` → `AT_SUPPORT`/`SELLERS_STRENGTHENING`; `"support"|"accumulation"` → `AT_SUPPORT`/`BUYERS_STRENGTHENING`; `"compression"|"continuation"|"consolidat"` → `NEAR_SUPPORT`/`NEUTRAL`; `"distribution"|"resistance"` → `AT_RESISTANCE`/`SELLERS_STRENGTHENING`; else `UNKNOWN`/`NEUTRAL`. The chain is ordered, so an event string containing both `"markup"` and `"distribution"` resolves on the first match.
- Tier-demotion rule L741–751: `dominant_trend == 'BEARISH'` ∧ `'BUYER' not in control_state` ∧ `tier == 1` ∧ ¬`is_accumulation_risk_off` → tier 2, `tier_label = TIER_2_OBSERVE`, `tier_demotion_reason` stamped. The exemption `is_accumulation_risk_off` (L738–740) requires `wyckoff_phase_bucket == 'ACCUMULATION'` and `'RISK_OFF' in macro_regime`.
- Actuarial-source upgrade L1171–1178 and win-rate bridge L1180–1206.
- `_horizon_profile` L968–1001: BURST / STEADY / GRIND / FLAT from EV ratios (`ev_5d/ev_20d > 0.7` → BURST; `< 0.25` → GRIND; `ev_10d/ev_20d > 0.6` → STEADY).
- Decision branches (CALL / PUT / other-blank): this file does not branch on `direction`. `edge_direction` is copied through verbatim from Layer 2 (L1078) with no normalisation and no handling of blank / UNRESOLVED / STRANGLE. **NOT_APPLICABLE as a direction decision; recorded as GAP-208 (pass-through without vocabulary check).**

**Computations and formulas (exact)**
- `_disc_win = disc.win_probability; if _disc_win > 1.0: _disc_win /= 100.0; _disc_win = max(0.30, min(0.80, _disc_win))` then `win_rate_5d = win_rate_10d = win_rate_20d = win_probability = _disc_win` (L1191–1205). Units: fraction. Clamp [0.30, 0.80].
- `_horizon_profile` ratios as above (L978–980).
- `calculate_adx` L419, `calculate_rsi` L451, `compute_technical_enrichments` L540 — standard 14-period definitions.

**Models** — `_horizon_profile` is a 4-state lookup rule on two EV ratios with thresholds 0.7 / 0.25 / 0.6 (L978–980); no calibration source claimed, no version tag. All other quantitative content is pass-through from the Vanguard engine.

**Outputs** — `vanguard/vanguard_signals.csv` (path L1279), written by `write_csv` L177 with `MINIMUM_HEADERS` (L108ff) as a floor. Fields include `has_edge`, `edge_direction`, `failed_gate`, `no_edge_reason`, `debug_signature` (L12), `state_hash`, `n_observations`, `win_rate_20d`, `expected_value_20d`, `confidence_level` (L11), the 5d/10d horizon block (L1133–1154), `horizon_profile`, `actuarial_source`, `actuarial_schema_version`, `actuarial_schema_fingerprint`, `actuarial_truth_packet_status`, and `layer2__preferred_horizon` (default `"NONE"`, L295). Atomic promotion: **no** — `write_csv` L177 writes to the destination path directly. Schema/version field: `actuarial_schema_version` and `actuarial_schema_fingerprint` are written per row (L1176–1177); there is no CSV-level schema version. Fields carrying authority claims: `actuarial_truth_packet_status = "VALID"` set at L1178 — **FALSE**; it is set on the strength of `n_observations > 0` and *any* one of three win-rate fields being non-None, without re-reading the truth packet or re-checking the fingerprint. `actuarial_source` upgraded from `MISSING` to `V6_DB` at L1175 on the same test — **FALSE** as a provenance assertion.
- `preferred_horizon` / `layer2__preferred_horizon` is written (L108, L295) but **no `hold_days`, `horizon_bucket` or routed-hold field is written by this file** [OBSERVED — grep for `hold_days|horizon_bucket` returns no writer in this file]. The Horizon Router at stage 19 is therefore not overwritten *by this file*; the actuarial 20-day horizon reaches the CSV only as the field names `win_rate_20d` / `expected_value_20d` / `raw_prob_up_20d` / `raw_prob_down_20d`, which are outcome statistics, not hold instructions. Verdict on "the actuarial 20-day outcome horizon must not overwrite a routed hold": **HOLDS at this file**; the Layer 2 side is covered in the `vanguard/` sections.

**Handoff** — receives from `packages/*.package.json` (stage 9) and, transitively, the Discovery CSV; hands to Options Intelligence (stage 18) and the Horizon Router (stage 19). Join key: `ticker`, normalised by `_normalise_ticker` L394.

**Missing-data handling**
| Condition | Emitted value/state | file:line | §10-compliant? |
|---|---|---|---|
| Layer 2 outcomes object empty | `_ov` returns `l2.get(key)`, then `None` | L1125–1131 | N — bare `None`, which the comment at L1160 notes "the CSV reader converts to 0.0" |
| All three win rates None and actuarial source is V6_DB | re-read from the actuarial object | L1185–1188 | N/A |
| All three win rates still None | seeded from Discovery `win_probability`, clamped [0.30, 0.80] | L1195–1205 | **N** — a structural heuristic is written into empirical-frequency fields; the state should be `UNAVAILABLE_PROVIDER` or `SYNTHETIC_RESEARCH_ONLY` |
| Actuarial source MISSING but `n_obs > 0` and any rate present | upgraded to `V6_DB` + `truth_packet_status = "VALID"` | L1171–1178 | **N** — a missing-provenance state is bridged to a valid one |
| Phase-2 baton field absent | defaults injected, e.g. `layer2__preferred_horizon = "NONE"`, `layer2__raw_prob_up_20d = 0.0` | L280–304 | **N** — `0.0` for a probability bridges pending↔measured-zero |
| Package has no usable OHLCV | `_resolve_daily_bars` returns `None`; `ohlcv_rows` stays `None` | L466, L754–762 | N |

**Contradictions found here:** CON-208, CON-209
**Gaps found here:** GAP-208, GAP-209

**Comment/docstring claims audited:**
- L1156–1170 "Priority: actuarial win_rate_20d (real DB match) wins over this bridge. When actuarial rates flow through normally this block is a no-op." → **HOLDS**; the bridge is gated on `_all_missing` (L1183–1184).
- L1164–1167 "packages always carry discovery.win_probability … which is the Wyckoff structural win probability computed independently of the actuarial database" → **HOLDS** as to independence, and this is precisely the objection: an independent structural heuristic is written into `win_rate_*`.
- L1169 comment describes the bridge as seeding "real per-signal inputs" → **PARTIAL**; the value is per-signal but is a linear function of the composite (see D6), and the same scalar is written to all three horizons.
- L721–732 tier-demotion comment "Actuarial DB shows this is the highest-edge combination (Hit10 = 33.8 %, prior adjustment = +12 pts)" → **PARTIAL**. The Hit10 figure matches the Discovery comment at L657; the "+12 pts prior adjustment" it cites is the `_STATE_PRIOR_ADJUSTMENTS` entry that is never applied (CON-201). The exemption itself is coded as described (L738–745).
- L1108–1116 "We extract explicitly here so they appear as top-level headline fields" → **HOLDS** (L1133–1154).
- L11–19 header "1) vanguard_signals.csv (PASS only)" → **HOLDS**; the write is filtered to PASS rows in `main()`.

**Confidence in this section:** MEDIUM — the fallback bridges, outputs and comment verdicts are direct reads and are HIGH confidence; the claim that no routed-hold field is written rests on an exhaustive grep of this file only, and the Layer 2 emission is covered elsewhere in this lane.

# AVS-E2E-CODE-001 — Sub-auditor scratch: `vanguard/` package (+ `orchestrator/wyckoff_engine.py`)

Scope: 35 files listed in the brief. Read-only static audit. Descriptive atlas only.
Tags: OBSERVED = read directly in source. INFERRED = deduced, with basis and confidence.
No claim in this document is tagged MEASURED.

---

## PART 1 — ATLAS

### vanguard/layer2_statistical/actuarial_query.py
**Classification:** Statistical lookup engine. Sole reader of the actuarial parquet database inside Vanguard.
**Real execution position:** stage 15 of 51, evening; invoked by `vanguard/main.py::VanguardEngine.analyze` (L195), which is reached from `scripts/run_vanguard_from_packages.py`, which `intelligent_orchestrator.py::evening_workflow` launches at L4183. Also reachable from `avshunter_trap_engine.py` Phase 5.5 (L2407). OBSERVED (call site `vanguard/main.py:195`).
**Task in the process:** Converts one `StateVector` into an `ActuarialOutcomes` record by filtering a historical parquet database down to rows whose categorical state dimensions match the live state, then computing empirical probabilities, medians, expected values, Sharpe ratios, return percentiles and forward-momentum diagnostics over that sample at three horizons (5d, 10d, 20d). It also emits a match-audit block (method, stage, dimensions, similarity, sample size, confidence weight, fallback reason) and a shrinkage-calibrated probability block. It never returns `None`.
**Entry points:** `ActuarialQueryEngine.__init__(database_path=None)`; `ActuarialQueryEngine.query(state) -> ActuarialOutcomes`; module function `_empty_outcomes(match_attrs)`.
**Imports (production):** `pandas`, `pathlib.Path`, `..schemas.state_outcomes_schema.StateVector/ActuarialOutcomes`, `..config.ACTUARIAL_DATABASE_PATH`; lazy `pyarrow.parquet`, `warnings`, `logging`, `os`. · **Imported by:** `vanguard/layer2_statistical/__init__.py` (L6), `vanguard/main.py` (L15). · **Broken/retired imports:** NONE. (`avshunter_ticker_probe.py:148` imports `vanguard.layers.actuarial_query` — a package path that does not exist; that file is outside this audit's scope but the reference is dead. OBSERVED.)

**Inputs**
- Files/tables read: one parquet file. Path priority: caller-supplied `database_path` → `config.ACTUARIAL_DATABASE_PATH` = `C:\Users\ACKVerissimo\vanguard\data\actuarial_database_v7.parquet` (`vanguard/config.py:12`). Column projection restricted to `ACTUARIAL_QUERY_COLUMNS` (L53–92) when the parquet schema can be read (L250–261). OBSERVED.
- Upstream fields consumed (with fallback chains):
  - `_state_match_values` (L517–522) reads the 10 `MATCH_EXACT_DIMS` from the `StateVector` via `state.get(dim) if isinstance(state, dict) else getattr(state, dim, None)` — a dict/object dual-access fallback.
  - `_normalise_match_value` (L501–514) maps `""`, `"NONE"`, `"N/A"`, `"NA"`, `"NAN"`, `"UNKNOWN"` and NaN all to `None`. **Fallback bridging two semantic types:** an explicitly-emitted categorical `"UNKNOWN"` and a genuinely absent value both become the same "dimension not available" state (L512). OBSERVED.
  - `_available_match_dims` (L525–526) then silently *drops* any dimension whose normalised value is `None`, or that is absent from the DataFrame. The match is still labelled `EXACT` (L866).
  - `_adjust_for_intraday_context` reads `state.intraday_rows`, `state.intraday_position` (default `'UNKNOWN'`), `state.volume_profile_context` (default `'BALANCED'`), `state.control_dynamics` (default `'NEUTRAL'`) — three `getattr(..., default)` sentinel fallbacks at L1255–1257.
- External calls (API/DB, cached?): `pd.read_parquet` once per engine construction (`_load_database`, L261/263). Normalised match columns are memoised per dimension in `self._match_norm_cache` (L820–828) — cached for the lifetime of the engine object, i.e. one Vanguard run. No network calls.
- Config/policy read: `ACTUARIAL_DATABASE_PATH` only. All other thresholds are module constants in this file.

**Logic and algorithms**
- **Match ladder** — `_find_match_ladder_states` (L847–995). Named in its own docstring "Phase 2A Vanguard match ladder: EXACT -> RELAXED -> ANALOGUE -> UNKNOWN". `_find_similar_states` (L997–1005) is a pass-through to it. Exact order:
  1. **EXACT** (L861–887). Dimensions = intersection of `MATCH_EXACT_DIMS` (L17–32: `vol_regime, trend_direction, structure_quality, phase_v2, momentum_bucket, location_bucket, wyckoff_phase_bucket, trend_maturity, iv_regime, crabel_state`) with DB columns *and* non-null state values. Conjunctive equality filter (`_filter_by_dims`, L830–845). Accepted if `len(exact) >= _horizon_sample_min(None, relaxed=False)`.
  2. **RELAXED** (L889–915). Dimensions = `MATCH_RELAXED_DIMS` (L33–38: `vol_regime, trend_direction, structure_quality, wyckoff_phase_bucket`) — 4 dimensions. Accepted if `len(relaxed) >= _horizon_sample_min(None, relaxed=True)`.
  3. **ANALOGUE** (L917–966). Weighted similarity over the 9 dims in `MATCH_SIMILARITY_WEIGHTS` (L39–49) restricted to dims present in DB and non-null in state. `score = Σ(1{dim matches} · w_dim) / Σ w_dim` (L926–935). Rows kept where `score >= ANALOGUE_MIN_SIMILARITY = 0.70` (L50, L936). Accepted if `len(analogue) >= ANALOGUE_MIN_SAMPLES = 100` (L51, L940). Reported similarity is the *mean* score of the retained rows (L938), not the minimum.
  4. **UNKNOWN** (L968–995). Returns a zero-row frame tagged `method="UNKNOWN"`, `quality="INSUFFICIENT_SAMPLE"`, `signal_type="NO_EDGE"`, `momentum_tier="N/A"`, with a `fallback_reason` string concatenating all three shortfalls.
- **Minimum sample thresholds** — `_horizon_sample_min` (L553–557). `preferred_horizon` is hard-wired to `None` at L857 with the comment "preferred_horizon is deliberately not a match dimension in v6", so `_normalise_horizon(None) or "10D"` → `"10D"` always. Therefore in production: **EXACT minimum = 60 rows; RELAXED minimum = 100 rows; ANALOGUE minimum = 100 rows** (L556–557, L51). The 5D (30/60) and 20D (100/150) branches are unreachable from `query()`. OBSERVED.
- **Sample-quality label** — `_sample_quality` (L543–550): `>=300 HIGH_SAMPLE`, `>=100 MODERATE_SAMPLE`, `>=30 LOW_SAMPLE`, else `INSUFFICIENT_SAMPLE`. This is a *label only*; it does not gate the ladder.
- **Second, independent quality gate in `query()`** — L316: `if similar_states is None or len(similar_states) < 10:` returns `_empty_outcomes` with the match attrs preserved. So a tagged `RELAXED` match of ≥100 rows can never hit this, but the `UNKNOWN` zero-row frame always does.
- **State key construction** — `_state_key` (L529–530): `"|".join(f"{dim}={values.get(dim) or '*'}" for dim in dims)`. `original_state_key` is always built over the full `MATCH_EXACT_DIMS` list (L858), so absent dims appear as `dim=*`. `matched_state_key` is built from the **first row** of the matched sample over the *surviving* dims only (`_matched_key_from_sample`, L533–540) — for ANALOGUE it is instead the literal string `f"ANALOGUE>=0.70|mean_similarity={analogue_similarity}"` (L959). **Version tag:** there is no version token inside the state key. Version identity is carried separately by `StateVector.schema_version` / `bucket_schema_version` (`state_calculator.py:22,24`) and by the DB's own `calculation_version`/`schema_version` columns (`actuarial_core_v7.py:17–19`), which are not read here.
- **Outcome horizons queried** — all three. The 20d block is unconditional (L1099–1130); 5d and 10d blocks are gated on `self._has_5d_cols` / `self._has_10d_cols` (L1137, L1161), set from column presence at L274–275. **The 20-day horizon is the mandatory, always-computed horizon**; `n_observations`, `confidence_level`, `win_rate`, `kelly_fraction`, `recommended_hold_days` and `outcome_distribution` are all derived from the 20d-matured subsample only (L1096–1130). OBSERVED.
- **DB fingerprint check:** **absent from this file.** `_load_database` (L242–296) reads the parquet with no call into `vanguard/core/cache_integrity.py` or `vanguard/core/actuarial_registry.py`. The only identity checks are (a) a filename substring test `'actuarial_database_v7.parquet' not in self.database_path.lower()` which emits a `UserWarning` and continues (L231–239), and (b) a silent auto-upgrade to a sibling `actuarial_database_v7.parquet` when `database_path is None` (L200–213). The registry's `expected_schema_fingerprint` (`actuarial_registry.py:64–66`) and `validate_cache_frame` (`cache_integrity.py:65–106`) are never invoked on this path. OBSERVED. → GAP-241.
- Decision branches (CALL / PUT / other-blank): **NONE.** This file contains no direction branch of any kind. Every probability it computes (`prob_up_10pct_20d`, `prob_trend_continues_20d`, `win_rate`, `outcome_hit_*_up`) is unconditionally long-side. INFERRED (basis: full-file read, no `PUT`/`CALL`/`direction` token present; confidence HIGH).

**Computations and formulas (exact)**
- `exact_min = 60`, `relaxed_min = 100` — sessions/rows, integer (L556–557 with `preferred_horizon=None`).
- `similarity = Σ_dim (1 if db[dim]==state[dim] else 0)·w_dim / Σ_dim w_dim` (L926–935). Weights (L39–49): vol_regime .20, trend_direction .18, structure_quality .15, phase_v2 .12, momentum_bucket .10, location_bucket .08, wyckoff_phase_bucket .08, trend_maturity .05, iv_regime .04 (sum 1.00 when all present; renormalised by `total_weight` when not). Bounds [0,1], rounded to 4 dp at L938.
- `sample_confidence_bucket` — `_sample_confidence_bucket` (L571–578) using `SAMPLE_CONFIDENCE_THRESHOLDS[group]` (L114–119). Group is `_confidence_horizon_group(preferred_horizon)`; with `preferred_horizon=None` it defaults to `"20D"` → group `"11_20D"` → HIGH ≥150, MEDIUM_HIGH ≥75, MEDIUM ≥40, LOW ≥15, else THIN. `sample_size<=0` → `"UNKNOWN"`.
- **Confidence penalty formula** — `_confidence_weight` (L581–595):
  - `method == "UNKNOWN"` → `0.30` (flat).
  - `method == "ANALOGUE"` → `0.70` if `sim>=0.85` and bucket ∈ {HIGH, MEDIUM_HIGH}; else `0.60` if `sim>=0.80`; else `0.50` if `sim>=0.70`; else `0.35`.
  - otherwise → `CONFIDENCE_WEIGHTS[method][bucket]` (L121–138): EXACT {HIGH 1.00, MEDIUM_HIGH 0.90, MEDIUM 0.80, LOW 0.65, THIN 0.50, UNKNOWN 0.30}; RELAXED {0.85, 0.75, 0.65, 0.50, 0.40, 0.30}. Unlisted method/bucket → `0.30`.
  - `confidence_penalty` and `confidence_weight` are set to the **same** value (L610–614). Bounds [0.30, 1.00]. Unitless.
- **Shrinkage calibration** — `_probability_calibration` (L683–724):
  - `baseline_probability = mean(self.df[target_col])` over the **entire database population**, not the matched sample (L691–692).
  - `adjusted_prob = baseline + weight · (raw_prob_target_hit − baseline)` (L703).
  - `adjusted_expected_return = baseline_return + weight · (raw_expected_return − baseline_return)` (L704).
  - `probability_edge = adjusted_prob − baseline_probability` (L705). When `method=="UNKNOWN"`, adjusted values are forced to the baselines and `edge = 0.0` (L698–701).
  - `probability_verdict` — `_probability_verdict` (L617–626): `>=0.10 STRONG_EDGE`, `>=0.05 MODEST_EDGE`, `>0 WEAK_EDGE`, `==0 NO_STAT_EDGE`, `<0 NEGATIVE_EDGE`.
  - Horizon column selection (L657–681): 5D → `outcome_5d_return` / `outcome_hit_5pct_up_5d` / `outcome_max_drawdown_5d`; 10D → `outcome_10d_return` / `outcome_hit_7pct_up_10d` / `outcome_max_drawdown_10d`; anything else (incl. `None`) → **20D** `outcome_20d_return` / `outcome_hit_10pct_up` / `outcome_max_drawdown_20d`.
- **20-day outcomes** — `_calculate_outcomes` (L1089–1231), computed on `sample_20d = similar_states.dropna(subset=["outcome_20d_return"])` (L1096):
  - `n_observations = len(sample_20d)` (L1097).
  - `prob_up_10pct_20d = mean(outcome_hit_10pct_up)` (L1100); `prob_down_5pct_before_up_10pct = mean(outcome_hit_5pct_down_before_10up)` (L1101); `prob_trend_continues_20d = mean(outcome_20d_return > 0)` (L1102).
  - `median_gain_if_up = median(returns>0)` **else literal 0.05** (L1107); `median_loss_if_down = median(returns<=0)` **else literal −0.03** (L1108).
  - `win_rate = mean(outcome_20d_return > 0)` (L1113); `sharpe_ratio = mean/std` or 0.0 (L1114).
  - `expected_value_20d = win_rate·median_gain + (1−win_rate)·median_loss` (L1119). Units: fractional underlying return. No clamp.
  - `avg_win = mean(returns>0)` else 0.05 (L1121); `avg_loss = |mean(returns<=0)|` else 0.03 (L1122); `avg_win_loss_ratio = avg_win/avg_loss` else 1.0 (L1123).
  - `kelly_fraction = (prob_up_10pct·avg_win − (1−prob_up_10pct)·avg_loss)/avg_win`, else 0.1; then **clamped to [0.0, 0.25]** (L1125–1126). Note the Kelly numerator uses the *target-hit* probability while the payoff terms use *directional* win/loss means.
  - `recommended_hold_days = int(median(outcome_days_to_10pct)) if prob_up_10pct_20d > 0.5 else 20` (L1128). Integer trading days.
  - `confidence_level = min(1.0, n_obs/50)` (L1130). Bounds [0,1].
- **5d / 10d outcomes** (L1132–1178) mirror the 20d block on their own `dropna` subsamples, with `median_gain`/`median_loss` defaulting to `0.0` rather than 0.05/−0.03, and `ev_Xd = wr_Xd·med_gain_Xd + (1−wr_Xd)·med_loss_Xd`.
- **Return percentiles** — `_return_percentiles` (L1066–1087): 13 quantiles (p01…p99, L1058–1063) per horizon, rounded 6 dp; `n_obs_{h}` counts non-null. Empty input → every percentile `None` and `n=0` (explicitly not 0.0).
- **Forward-momentum confidence** — `query()` L394–411: `mean(rank(future_momentum_bucket) > rank(momentum_bucket))` with rank map `{LOW:0, MID:1, HIGH:2, EXTREME:3}` and `.fillna(0)`; fallback to `mean(momentum_delta > 0)` when `future_momentum_bucket` is absent. Bounds [0,1]. Set to 0.0 when `signal_type == 'NO_EDGE'`.
- **Intraday adjustment** — `_adjust_for_intraday_context` (L1233–1369):
  - `adjustment_factor` starts 1.0; multiplied by 1.6 (AT_SUPPORT with trend DOWN/SIDEWAYS), 1.3 (AT_SUPPORT otherwise), 1.2 (AT_RESISTANCE in UP), 0.7 (AT_RESISTANCE otherwise), 1.2 (NEAR_SUPPORT); ×1.3 ACCUMULATION, ×0.75 DISTRIBUTION; ×1.2 BUYERS_STRENGTHENING, ×0.8 SELLERS_STRENGTHENING (L1263–1295). **Clamped to [0.4, 2.5]** (L1297).
  - `adj_prob_up = min(0.95, prob_up · factor)` (L1299).
  - `adj_prob_down = prob_down · 1/(1+(factor−1)·0.5)` if factor>1 else `min(0.95, prob_down·(2−factor))` (L1301–1304).
  - Triple-barrier renormalisation (L1306–1314), then `adj_ev_20d = prob_target·(median_gain·factor) + prob_stop·median_loss` (L1316–1318).
  - `kelly` re-clamped to ≤0.25 (L1349); `win_rate` explicitly **not** overwritten (L1347).
  - **Fail-closed guard (L1247–1249):** returns `base_outcomes` unchanged when `state.intraday_rows == 0`.

**Models**
- Name: *Vanguard actuarial match ladder v6/Phase-2A*. Type: categorical exact-match lookup with a weighted-Hamming analogue fallback + empirical frequency estimation + linear shrinkage toward a population base rate.
- Inputs: 10 categorical state dimensions; outputs the ~40 scalar fields of `ActuarialOutcomes` plus 39 return percentiles.
- Exact parameters/weights: `MATCH_SIMILARITY_WEIGHTS` (L39–49), `ANALOGUE_MIN_SIMILARITY=0.70`, `ANALOGUE_MIN_SAMPLES=100`, `SAMPLE_CONFIDENCE_THRESHOLDS` (L114–119), `CONFIDENCE_WEIGHTS` (L121–138), sample-quality cuts 300/100/30, `confidence_level` divisor 50, Kelly clamp 0.25, adjustment clamp [0.4,2.5], probability caps 0.95.
- Calibration source claimed: none stated for the similarity weights, the confidence-weight table, or the sample thresholds. Comments cite dates ("2026-05-20", "Phase 2A") but no dataset, fit procedure, or backtest. → GAP-258 (shared with EV3).
- Version tag: none on the engine. `_has_v6_cols` (L219, L276) is a capability flag, not a version.

**Outputs**
- Files/tables written: **NONE.** Returns an `ActuarialOutcomes` dataclass in-process.
- Fields: the full `ActuarialOutcomes` surface (`schemas/state_outcomes_schema.py:180–376`) plus dynamically-attached calibration keys via `_attach_dict_to_outcomes` (L727–729) — all 15 calibration keys are declared fields (L287–302 of the schema), so no undeclared attributes are created.
- Atomic promotion? NOT_APPLICABLE (in-process return).
- Schema/version field? NOT_APPLICABLE — no version stamped on the outcome object.
- Fields carrying authority claims:
  - Docstring L142–145 `_empty_outcomes`: "Return a safe, fail-closed ActuarialOutcomes - NEVER returns None" → **HOLDS** (every return path in `query()` L306–446 returns an object).
  - Docstring L186–188: "FIXED: query() NEVER returns None" → **HOLDS**.
  - Docstring L459–472 `_tag_match`: "This is the single authoritative place where match-method information is written to a DataFrame. All return paths in `_find_similar_states()` must call this — never set .attrs directly" → **HOLDS** (all four returns at L865, L893, L941, L973 route through `_tag_match`; no other `.attrs[` assignment exists in the file).
  - Docstring L854–856: "preferred_horizon is deliberately not a match dimension in v6. It is selected after outcomes are calculated, then handed forward as layer2__preferred_horizon for routing and options DTE logic" → **PARTIAL**. The first sentence HOLDS. The second describes a downstream consumption that does occur (`ev3_stage0.py:92–97` aliases `layer2__preferred_horizon` into `horizon_bucket`), which is the mechanism behind CON-251.
  - Docstring L776–782 `_momentum_tier_from_sample`: "The retired Stage 0/1/2 code used to calculate these tiers, but it sat below an early return and never ran" → **HOLDS** as a description of the current file (no Stage 0/1/2 block remains; `_find_similar_states` is a one-line delegate).
  - Docstring L1067–1075 `_return_percentiles`: "Absent or empty input yields None for every point and n=0 — never 0.0 — since zero is a valid observed return and None means 'no observation.'" → **HOLDS** (L1080–1083).
  - Docstring L1238–1244 `_adjust_for_intraday_context` FIX 1: "Gate immediately with base_outcomes to preserve actuarial truth" → **HOLDS** as written, but see CON-253: the guard fires on *every* evening run, making the entire adjustment block dead in production.
  - Comment L1117–1118: "EV uses directional win rate … NOT prob_up_10pct" → **HOLDS** for L1119 (base path) but **FALSE for the adjusted path**, where L1318 uses `prob_target` (= adjusted `prob_up_10pct_20d`) as the target probability. The guard at L1247 means the adjusted path does not execute in production.

**Handoff**
- Receives from: `vanguard/layer2_statistical/state_calculator.py::StateVectorCalculator.calculate_state` (the `StateVector`), and the actuarial parquet built by `vanguard/core/actuarial_core_v7.py` (plus unidentified enrichment passes — see GAP-251).
- Hands to: `vanguard/main.py::VanguardEngine.analyze` → `layer_2_result` dict → `scripts/run_vanguard_from_packages.py` flattening to `layer2__*` CSV columns → `vanguard/vanguard_signals.csv`.
- Join keys: none in-process (single object). Downstream join is on `ticker` / `signal_id`.

**Missing-data handling**
| condition | emitted value/state | file:line | §10-compliant? |
|---|---|---|---|
| parquet unreadable | `self.df = None`, printed warning, engine continues | L294–296 | N |
| `self.df is None or empty` | `_empty_outcomes()` — all zeros, `lookback_period="N/A"`, `insufficient_data_reason="No actuarial data available"` | L306–307, L146–165 | N |
| `_find_similar_states` raises | `_empty_outcomes()` (match attrs lost) | L311–313 | N |
| matched sample `< 10` rows | `_empty_outcomes(attrs)`; zeros for every probability | L316–325 | N |
| `_calculate_outcomes` raises | `_empty_outcomes(attrs)` | L329–331 | N |
| `_adjust_for_intraday_context` raises | silently reverts to `base_outcomes` | L338–340 | N |
| dimension value absent/`"UNKNOWN"` | dimension dropped from the match; method still `EXACT` | L512, L526, L866 | N |
| method unresolvable | `state_match_method="UNKNOWN"`, `sample_confidence_bucket="UNKNOWN"`, `confidence_penalty=0.30` | L167–175, L607–608 | N |
| `future_momentum_bucket` column absent | `None` + empty dict + 0.0 + 0 | L1013–1019 | N |
| horizon percentile sample empty | `None` per point, `n_obs=0` | L1080–1083 | **Y** (closest to `NOT_APPLICABLE`; still not a §10 token) |
| `future_momentum_bucket` value in {"", NAN, NONE, UNKNOWN, DATA_WEAK} | filtered out, dominant bucket `""` | L769–772 | N |
| `_transition_delta_stats` column absent | `None` | L1045–1046 | N |

**Contradictions found here:** CON-240, CON-241, CON-242, CON-243, CON-245, CON-247, CON-249, CON-252, CON-253, CON-263, CON-265, CON-268, CON-269
**Gaps found here:** GAP-240, GAP-241, GAP-245, GAP-250, GAP-251
**Comment/docstring claims audited:** see "Outputs → authority claims" above — 8 claims: 5 HOLDS, 2 PARTIAL, 1 FALSE (L1117–1118 relative to the adjusted path).
**Confidence in this section:** HIGH — the whole file was read; every threshold and formula is quoted from source. The only inference is the unreachability of the 5D/20D `_horizon_sample_min` branches, which follows directly from `preferred_horizon = None` at L857 being the sole call path.

---

### vanguard/layer2_statistical/state_calculator.py
**Classification:** Feature/state constructor. Sole producer of the live `StateVector` consumed by the actuarial ladder.
**Real execution position:** stage 15 of 51, evening; invoked by `vanguard/main.py::VanguardEngine.analyze` (L194).
**Task in the process:** Converts a `VanguardInput` (price history, indicators, macro, calendar, options) plus the Layer-1 `AuctionVerdict` into a ~70-field `StateVector`: volatility regime, trend direction/maturity, structure quality, liquidity, positioning, macro regime, catalyst proximity, the v2 bucket set (`phase_v2`, `momentum_bucket`, `location_bucket`, `state_v2`, `early_candidate`), the 9-dim match extras (`iv_regime`, `volume_bucket`, `crabel_state`, `horizon_bucket`), the bucket discriminators (`adx_bucket`, `atr_pct_bucket`, `wyckoff_phase_bucket`), a 9-dimension MD5 `state_hash`, and a state confidence scalar.
**Entry points:** `StateVectorCalculator.calculate_state(vanguard_input, auction_verdict) -> StateVector`.
**Imports (production):** `pandas`, `numpy`, `hashlib`, `..schemas.state_outcomes_schema.StateVector`, `..schemas.auction_schema.AuctionVerdict`, `..schemas.input_schema.VanguardInput`, `..config.{VOLATILITY_THRESHOLDS, TREND_THRESHOLDS, STRUCTURE_THRESHOLDS}`. · **Imported by:** `vanguard/layer2_statistical/__init__.py` (L5), `vanguard/main.py` (L15). · **Broken/retired imports:** NONE.

**Inputs**
- Files/tables read: NONE (all in-memory).
- Upstream fields consumed (with fallback chains):
  - `tech.atr_percentile_rank` overrides the locally computed ATR percentile only if `0<=v<=100` (L349–352) — a **numeric←numeric** provenance switch with no provenance field emitted.
  - IV percentile chain (L360–367): `tech.ivp_252d` (×100 if ≤1.0) → `tech.iv_percentile` → `tech.iv_rank` → **literal 50.0**. Bridges *missing IV* to *median IV*.
  - `raw_wyckoff_for_trend = tech.wyckoff_phase_bucket or tech.wyckoff_phase or ''` (L71) — three-way `or` chain, bucket←raw-phase←empty.
  - `raw_wyckoff_bucket` accepted only if in {ACCUMULATION, MARKUP, DISTRIBUTION}; else recomputed from `tech.wyckoff_phase` via `_wyckoff_phase_bucket` which returns `"UNKNOWN"` for an empty string (L91–96, L831–832).
  - `_disc_crabel = tech.crabel_compression_state or tech.crabel_state` (L200–203), accepted only if in {CRABEL_READY, COILING, NONE}; otherwise a locally derived proxy (L207–213).
  - `_disc_horizon = tech.horizon_bucket` accepted only if in {SHORT, MEDIUM, LONG}; else **literal `"MEDIUM"`** (L216–220). Bridges *unrouted* to *medium horizon*.
  - `_rsi_val = getattr(tech,'rsi',50) or 50` (L125) — bridges both missing and a literal 0.0 RSI to 50.
  - `_rel_vol = structure_state.get('relative_volume', 1.0) or 1.0` (L188) — bridges zero volume to normal volume.
  - `intraday_position`/`volume_profile_context`/`control_dynamics` via `getattr(tech, ..., 'UNKNOWN'|'BALANCED'|'NEUTRAL')` (L296–298).
  - `intraday_rows=getattr(vanguard_input,'intraday_rows', 0)` (L305) — `VanguardInput` (`input_schema.py:182–215`) has **no such field** and `OrchestratorAdapter` never sets one, so this is always `0`. OBSERVED. → CON-253.
  - `macro.vix_history` presence gates the VIX percentile; empty → 50.0 (L746, L779–780).
  - `calendar.last_earnings_date` → `calendar.days_since_earnings` → `91 - days_to` proxy (L694–703). `CalendarData` (`input_schema.py:12–27`) declares neither of the first two fields, so the **91-day proxy is the only live branch**. INFERRED (basis: dataclass field list; confidence HIGH).
- External calls: `datetime.now(timezone.utc)` (L595) and `pd.Timestamp.now()` (L425–426, L696) — wall-clock reads inside a deterministic feature calculation.
- Config/policy read: `VOLATILITY_THRESHOLDS`, `TREND_THRESHOLDS`, `STRUCTURE_THRESHOLDS` (`config.py:70–90`).

**Logic and algorithms**
- **Volatility regime classifier** — `_calculate_volatility_regime` (L339–394). Weighted percentile average, thresholds 20/80.
- **Trend direction + maturity state machine** — `_calculate_trend_maturity` (L396–476) with the SIDEWAYS sub-classifier `_sideways_maturity` (L478–519), schema v2.2.0.
- **Structure quality scoring table** — `_calculate_structure_quality` (L521–634), 30+40+30 points.
- **Timing-aware volume scaler** — L590–616 (US-session partial-bar projection).
- **v2 phase/momentum/location bucketing** — L117–172, thresholds asserted to match `build_state_v2.py`.
- **9-dim MD5 hash** — `_generate_state_hash` (L851–895).
- Decision branches (CALL / PUT / other-blank): **NONE.** No direction branch exists. `trend_direction` is UP/DOWN/SIDEWAYS only (L439–444). `positioning_bias` is NET_LONG/NET_SHORT/NEUTRAL (L660–665) and, because `skew` is hard-coded `0.0` (L644) and never reassigned, the NET_LONG (`skew>0.2`) and NET_SHORT (`skew<-0.2`) arms are **unreachable**; `positioning_bias` is always `"NEUTRAL"`. OBSERVED. → GAP-253.

**Computations and formulas (exact)**
- `atr_pct = percentile(atr_current, atr_history)` else 50.0 (L345); `_percentile = (Σ 1{h<=v} / n)·100` (L783), bounds [0,100].
- `avg_pct = atr_pct·0.33 + bb_pct·0.33 + iv_pct·0.34` (L375). `regime = COMPRESSION if avg<20; EXPANSION if avg>80; else NORMAL` (L378–386). `score` = distance from the crossed threshold, or `50-|avg-50|` for NORMAL.
- `pct_from_high = (close - high_52w)/high_52w` (negative below the high); `pct_from_low = (close - low_52w)/low_52w` (L421–422). Both 0 when the denominator is ≤0.
- `days_since_high = (now - date_52w_high).days` **else 365** (L425). `TechnicalData.date_52w_high` defaults `None` and the adapter never sets it → always 365. INFERRED (basis: `input_schema.py:114–115`, `orchestrator_adapter.py:229–249`; confidence HIGH). Consequence: `maturity == "EARLY"` (needs `days_since < 30`) is unreachable via the adapter path; maturity is LATE or MIDDLE only for UP/DOWN.
- `late_pct = TREND_THRESHOLDS['late_trend_percent_from_extreme']` = **0.05** (`config.py:81`), with an explicit re-default to 0.07 if falsy (L431–433) — the docstring at L405–407 states the safe range is 0.05–0.08 and the fallback is 0.07; the live config value is 0.05, the bottom of the stated safe band.
- `direction = UP if ema21>ema50 and close>ema21 and adx>25; DOWN if ema21<ema50 and close<ema21 and adx>25; else SIDEWAYS` (L439–444).
- `strength = min(adx,100) if adx>0 else 0` (L465).
- `quality_score = [30 if above both VWAPs | 15 mixed | 0 below both] + (acceptance.score/100)·40 + [control.confidence·30 if controller!="NEUTRAL" else 10]` (L544–559). Range −0.4…100 (negative when `acceptance.score == -1`, see CON-260). Classified STRONG ≥75, NEUTRAL ≥50, else WEAK (L562–567).
- `relative_volume = adjusted_volume / avg_volume`; `adjusted = current · (390 / max(1, utc_minutes − 810))` when in-session and `current < 0.5·avg` (L607–616). Liquidity HIGH >1.5, NORMAL >0.7, else LOW.
- `phase_v2 = EARLY_TRANSITION if (atr<45 and adx<22 and bb<55); CONTINUATION if (atr>=45 and adx>=22 and rsi<72 and bb<95); else EXHAUSTION` (L117–123).
- `momentum_score = adx · atr_percentile / 100` (L133); buckets ≥45 EXTREME, ≥30 HIGH, ≥15 MID, else LOW (L138–145).
- `location_bucket`: `|pfh|<0.10 NEAR_HIGH`; `|pfl|<0.10 NEAR_LOW`; `|pfh|>0.30 and |pfl|>0.30 MID_RANGE`; else TRANSITION_ZONE (L154–161).
- `early_candidate = int(momentum==MID and location in {MID_RANGE,NEAR_LOW} and phase==EARLY_TRANSITION)` (L168–172).
- `iv_regime`: COMPRESSION→LOW_IV; EXPANSION→HIGH_IV; `atr_pct>=50`→ELEVATED_IV; else NORMAL_IV (L178–185).
- `volume_bucket`: <0.7 LOW, ≤1.5 NORMAL, ≤3.0 HIGH, else SPIKE (L189–196).
- `crabel_state` proxy: COMPRESSION+WEAK adx → CRABEL_READY; `atr_pct_bucket==LOW` and adx∈{WEAK,MODERATE} → COILING; else NONE (L208–213).
- `adx_bucket`: <20 WEAK, ≤35 MODERATE, else STRONG (L796–801). `atr_pct_bucket`: <33 LOW, ≤66 MID, else HIGH (L811–816).
- `macro_regime`: `vix<15 and spy_trend=="UP"` → RISK_ON; `vix>25 or spy_trend=="DOWN"` → RISK_OFF; else TRANSITIONAL_BULLISH / TRANSITIONAL_BEARISH / TRANSITIONAL_NEUTRAL from `_spy_bullish` and `_vix_falling = vix < vix_history[-5]` (L749–768).
- `catalyst_proximity`: `days_to<=10` PRE_10D/HIGH; `<=20` PRE_20D/HIGH; `<=30` PRE_30D/MEDIUM; `<=60` FAR/LOW; else FAR/NONE. No earnings → `days_to=-1, window=FAR, days_since=90, proximity=NONE` (L681–720).
- `state_hash = md5("_".join([vol_regime, trend_direction, trend_maturity, structure_quality, catalyst_proximity, adx_bucket, atr_pct_bucket, wyckoff_bucket, macro_regime]))[:16]` (L882–895). Ticker deliberately excluded (L856–859).
- `confidence = data_quality_score · (0.8 if last_volume < 0.5·avg else 1.0) · (0.7 + 0.3·auction.confidence)`, capped at 1.0 (L904–920).
- `state_v2 = f"{vol_regime}|{trend_direction}|{structure_quality}|{phase_v2}|{momentum_bucket}|{location_bucket}"` (L223–227).

**Models**
- Name: *Vanguard StateVector v2.2.0 / bucket schema 1.1.0* (L22–24). Type: deterministic rule set + scoring tables + MD5 fingerprint. Inputs: OHLCV, EMAs, ADX, RSI, ATR/BB percentiles, 52w extremes, VIX history, earnings calendar, auction verdict. Output: `StateVector`. Exact parameters: all quoted above plus `config.py:70–90`. Calibration source claimed: comments assert alignment with `build_state_v2.py`, `add_early_candidate.py`, and `enrich_actuarial_9dim.py` (L114–116, L135–137, L151–153, L167, L175, L207) — none of those scripts is in this audit's file list, so the assertion is unverified here. Version tag: `SCHEMA_VERSION="2.2.0"`, `BUCKET_SCHEMA_VERSION="1.1.0"`, written onto every `StateVector` (L311–312).

**Outputs**
- Files/tables written: NONE. Returns a `StateVector`.
- Fields carrying authority claims:
  - L18–21: "Increment SCHEMA_VERSION whenever the hash dimensions or bucket logic changes … written to every signal row and every DB build so future debugging can immediately answer: 'did the live schema match the DB schema when this ran?'" → **FALSE**. The DB build stamps `schema_version="actuarial_v7"` and `bucket_schema_version="2.0.0"` (`actuarial_core_v7.py:18–19`) into the *same-named* columns. The two producers use disjoint value spaces, so the stated comparison cannot be performed. → CON-267.
  - L856–876 `_generate_state_hash` docstring: "BACKWARD COMPATIBILITY: DB rows without wyckoff_phase_bucket will not match Stage 1 filter — actuarial_query falls back to Stage 2 (4-dim)" → **FALSE as a description of the current code**: `actuarial_query.py` has no Stage 1/Stage 2; it has EXACT/RELAXED/ANALOGUE/UNKNOWN, and `state_hash` is not a match dimension at all. → CON-244.
  - L306–308 "D3 FIX: wyckoff_bucket computed above — must be passed so actuarial_query Stage 1 filter can separate ACCUMULATION from MARKUP" → **PARTIAL**: the field is passed and *is* used (it is in `MATCH_EXACT_DIMS`), but the named "Stage 1 filter" no longer exists.
  - L402–408 "THRESHOLD SAFETY NOTE (permanent fix) … Safe range: 0.05–0.08 … The fallback below ensures this never silently defaults to 0" → **HOLDS** (L431–433).
  - L135–137 "Thresholds MUST match DB builder (build_state_v2.py) exactly" → cannot be verified in scope; against `actuarial_core_v7.py:162` the momentum cuts (15/30/45) **do** match. PARTIAL.
  - L151–153 "MUST match DB builder … MID_RANGE requires BOTH distances > 30%" → **HOLDS** against `actuarial_core_v7.py:163–165` (identical rule).
  - L114–116 phase_v2 thresholds → **HOLDS** against `actuarial_core_v7.py:158–160` (identical rule).
  - L266 `spread_percentile=50.0, # TODO: Calculate from microstructure data` → an acknowledged constant. → GAP-252.

**Handoff**
- Receives from: `vanguard/integration/orchestrator_adapter.py` (the `VanguardInput`) and `vanguard/layer1_auction/auction_synthesizer.py` (the `AuctionVerdict`).
- Hands to: `vanguard/layer2_statistical/actuarial_query.py::query`, `vanguard/layer2_statistical/edge_detector.py::detect_edge`, and `vanguard/main.py` (which copies 11 state fields into `layer_2_result`).
- Join keys: none (single object per ticker).

**Missing-data handling**
| condition | emitted value/state | file:line | §10-compliant? |
|---|---|---|---|
| no ATR history | `atr_percentile = 50.0` | L345 | N |
| no IV source | `iv_percentile = 50.0` | L360 | N |
| no BB history | `bb_percentile = 50.0` | L353 | N |
| no VIX history | `vix_percentile = 50.0` | L746 | N |
| empty OHLCV | `current_price = 0`, `avg_volume = 1`, `current_volume = 0` | L418, L528, L592–593 | N |
| `date_52w_high/low` absent | `days_since = 365` | L425–426 | N |
| no earnings date | `days_to=-1`, `window="FAR"`, `days_since=90`, `proximity="NONE"` | L682–687 | N |
| last-earnings unknown | `days_since = 91 - days_to` (synthetic cycle) | L703 | N |
| wyckoff phase empty | `"UNKNOWN"` | L831–832 | N |
| horizon not routed | `"MEDIUM"` | L220 | N |
| crabel not supplied | derived proxy, no provenance flag | L207–213 | N |
| microstructure absent | `spread_percentile = 50.0` (TODO) | L266 | N |
| options UOA absent | `pc_ratio=1.0, pc_oi=1.0, skew=0.0, gex=0.0, dex=0.0, bias="NEUTRAL"` | L642–665 | N |
| intraday absent | `intraday_position="UNKNOWN"`, `volume_profile_context="BALANCED"`, `control_dynamics="NEUTRAL"`, `intraday_rows=0` | L296–305 | N |

**Contradictions found here:** CON-240, CON-241, CON-242, CON-243, CON-244, CON-250, CON-253, CON-267, CON-278
**Gaps found here:** GAP-240, GAP-252, GAP-253
**Comment/docstring claims audited:** 8 claims — 3 HOLDS, 3 PARTIAL, 2 FALSE (L18–21, L856–876).
**Confidence in this section:** HIGH — whole file read; the two unreachability findings (`positioning_bias`, `maturity=="EARLY"`) are direct consequences of quoted constants and of the adapter's constructor argument list.

---

### vanguard/main.py
**Classification:** Stage orchestrator / signal assembler. The only place Layer 1, Layer 2 and the edge detector are wired together, and the sole producer of the `VanguardSignal` payload.
**Real execution position:** stage 15 of 51, evening; `VanguardEngine` is constructed and `.analyze()` called by `scripts/run_vanguard_from_packages.py`, launched by `intelligent_orchestrator.py::evening_workflow` (L4183, config L434). Also reachable from `avshunter_trap_engine.py` Phase 5.5 (L2407).
**Task in the process:** Validates the actuarial database contract at construction, then per ticker: synthesises the auction verdict, computes the state vector, queries the actuarial ladder, derives sample-confidence and preferred-horizon labels, runs edge detection, promotes an exported edge-quality label, assigns a verdict/recommendation pair from a sample-size + edge-quality ladder, and returns a `VanguardSignal` whose `layer_2_result` dict is the payload that becomes the `layer2__*` columns of `vanguard/vanguard_signals.csv`.
**Entry points:** `VanguardEngine.__init__(actuarial_db_path=None)`; `VanguardEngine.analyze(vanguard_input) -> VanguardSignal`; `analyze_ticker(...)`; helpers `_sample_confidence_bucket(n)`, `_select_preferred_horizon(outcomes)`.
**Imports (production):** `.schemas.input_schema.VanguardInput`, `.schemas.trade_schema.VanguardSignal` and (lazily, L310) `EdgeAssessment`, `.layer1_auction.AuctionStateSynthesizer`, `.layer2_statistical.{StateVectorCalculator, ActuarialQueryEngine, EdgeDetector}`, `dataclasses`, `pathlib`, `.config.{ACTUARIAL_DATABASE_PATH, ACTUARIAL_DATABASE_FILENAME, REQUIRED_ACTUARIAL_V6_COLUMNS, OPTIONAL_ACTUARIAL_V6_COLUMNS}`; lazy `pandas`, `pyarrow.parquet`. · **Imported by:** `vanguard/__init__.py` (L11), `scripts/run_vanguard_from_packages.py`. · **Broken/retired imports:** L16–17 documents that `layer3_execution` (`TradeBuilder`) is *deliberately* not imported — the import is absent, matching the comment.

**Inputs**
- Files/tables read: the actuarial parquet, twice — once for schema validation via `pyarrow.parquet.read_schema` (L127) with a `pd.read_parquet` full-load fallback (L131–137), and once inside `ActuarialQueryEngine` (L108).
- Upstream fields consumed (with fallback chains):
  - `sample_confidence_bucket = getattr(outcomes,'sample_confidence_bucket',None) if outcomes else None) or _sample_confidence_bucket(n)` (L201–204). **Fallback bridging two vocabularies**: the actuarial bucket space is {HIGH, MEDIUM_HIGH, MEDIUM, LOW, THIN, UNKNOWN} (`actuarial_query.py:571–578`) while `_sample_confidence_bucket` (L28–41) returns {HIGH_SAMPLE, USABLE_SAMPLE, WEAK_SAMPLE, CONTEXT_ONLY, INSUFFICIENT_SAMPLE}. The `or` also fires on the string `""` and on `"UNKNOWN"`? — no, `"UNKNOWN"` is truthy, so only `None`/`""` trigger the local computation. Two disjoint vocabularies can therefore appear in the same CSV column. → CON-246.
  - 14 `getattr(outcomes, X, default)` reads at L214–229 with defaults `"UNKNOWN"`, `""`, `0.0`, `False`, `0.30`, `"NO_STAT_EDGE"`; each also has a `if outcomes else <other default>` arm producing a *third* value (`"NO_MATCH"`, `"NO_OUTCOMES"`).
  - `fallback_reason = (getattr(...,"") or "NONE")` (L225) — bridges *empty string* to the token `"NONE"`.
  - `legacy_failed_gate = getattr(edge,"failed_gate",None) or getattr(edge,"gate_failed",None)` (L367) — dual attribute-name fallback; `EdgeAssessment` declares only `failed_gate` (`trade_schema.py:23`), so the second arm is dead.
  - `intraday_rows` computed in a `try/except Exception: intraday_rows = 0` around `vanguard_input.intraday_df` (L167–171) — `VanguardInput` has no `intraday_df` attribute (`input_schema.py:182–215`), so the `except` always fires and `intraday_rows` is always 0. This value is only printed (L175); the `StateVector.intraday_rows` used downstream is computed separately in `state_calculator.py:305`. OBSERVED.
  - `probability_edge` coerced through `float(... or 0.0)` inside `try/except (TypeError, ValueError): 0.0` (L230–233).
- External calls: none beyond parquet reads.
- Config/policy read: `ACTUARIAL_DATABASE_FILENAME = "actuarial_database_v7.parquet"`, `REQUIRED_ACTUARIAL_V6_COLUMNS` (22 columns), `OPTIONAL_ACTUARIAL_V6_COLUMNS` (`config.py:266–295`).

**Logic and algorithms**
- **DB admission gate** — `__init__` L91–108: existence check → **exact filename equality** `db_path.name != ACTUARIAL_DATABASE_FILENAME` raises `RuntimeError` → `_validate_actuarial_database_contract` (column presence) → engine construction. Note the filename check is stricter than `actuarial_query.py:231`'s substring test.
- **Verdict ladder** — L378–404, evaluated in order: `n<10` → `INSUFFICIENT_SAMPLE / NO_ACTUARIAL_DATA`; `n<30` → `ACTUARIAL_CONTEXT_ONLY / THIN_SAMPLE_CONTEXT_ONLY`; `n<50` → `ACTUARIAL_WEAK_SAMPLE / WEAK_SAMPLE_NO_PROMOTION`; `statistical_has_edge and quality=="STRONG"` → `ACTUARIAL_SUPPORT / {label}_EDGE_STRONG_{horizon}`; `... "MODERATE"` → `ACTUARIAL_MODERATE / {label}_EDGE_MODERATE_{horizon}`; `discovery_flag and "WEAK"` → `ACTUARIAL_WEAK / EDGE_WEAK_CONTEXT_ONLY_{horizon}`; else `ACTUARIAL_NEUTRAL / NO_HISTORICAL_EDGE`.
- **Edge-quality promotion** — L342–366 (see formulas).
- Decision branches (CALL / PUT / other-blank): **one**, at L372–376:
  ```python
  edge_direction_label = (edge.edge_direction
      if str(edge.edge_direction).upper() in {"CALL", "PUT"} else "STAT")
  ```
  - **CALL** → label `"CALL"`, recommendation e.g. `CALL_EDGE_STRONG_10D`.
  - **PUT** → label `"PUT"`, recommendation e.g. `PUT_EDGE_MODERATE_20D`.
  - **other / blank / `"NONE"` / `"UNRESOLVED"` / `"STRANGLE"` / lower-case** → all collapse to the single token `"STAT"`. The distinct upstream reasons (no edge vs. non-directional vs. unresolved) are not preserved in the recommendation string.
  - Separately, `layer_2_result["edge_direction"]` at L523 writes `edge.edge_direction` **raw and un-normalised** — so the CSV carries `"NONE"` while `final_recommendation` carries `"STAT"`. The `_no_edge` constructor emits `"NONE"` (`edge_detector.py:648`); `_determine_direction` can only return `"CALL"` or `"PUT"` (`edge_detector.py:525–534`). Values `STRANGLE`, `UNRESOLVED`, blank are **never produced** anywhere in Vanguard. OBSERVED. → CON-271, GAP-243.
  - The `EdgeAssessment` fallback constructor at L310–322 sets `edge_direction="NONE"` — but see CON-254: that call passes four keyword arguments (`verdict_tier`, `gate_failed`, `supporting_factors`, `risk_warnings`) that are not fields of `EdgeAssessment` (`trade_schema.py:11–46`), so it would raise `TypeError`. It is unreachable because `query()` never returns `None`.

**Computations and formulas (exact)**
- `_sample_confidence_bucket(n)` (L37–41): `n>=100 HIGH_SAMPLE`, `>=50 USABLE_SAMPLE`, `>=30 WEAK_SAMPLE`, `>=10 CONTEXT_ONLY`, else `INSUFFICIENT_SAMPLE`.
- `_select_preferred_horizon(outcomes)` (L44–66): candidates `[("5D", ev_5d, wr_5d), ("10D", ev_10d, wr_10d), ("20D", ev_20d, win_rate)]`; drop any with a `None` EV or win rate; `sorted(key=(ev, wr), reverse=True)[0][0]`; **returns `"NONE"` when `outcomes is None` or no candidate survives**. All three EV/WR fields are non-`Optional` floats defaulting to `0.0` (`state_outcomes_schema.py:207–235`), so `valid` is never empty in practice and the `"NONE"` return is unreachable via the live path; ties are broken by list order after a stable sort, i.e. 5D wins a three-way all-zero tie. INFERRED (basis: dataclass defaults + `sorted` stability; confidence HIGH).
- `edge_quality` (legacy, L250–255): `STRONG` if `ev_20d>=0.03 and prob_up_10pct>=0.40`; `MODERATE` if `ev_20d>=0.015`; else `WEAK`. Gated on `n>=50` (L247), otherwise stays `"NONE"` and `discovery_flag=False`.
- `exported_edge_quality` (L347–365), in order: `bucket_edge_quality ∈ {EARLY_EXPANSION_STRONG, BUCKET_STRONG, STATISTICAL_STRONG}` → `STRONG`; `∈ {EARLY_CANDIDATE_MODERATE, STATISTICAL_MODERATE, LEGACY_MODERATE}` and not already STRONG → `MODERATE`; `n>=100 and probability_edge>=0.10` → `STRONG`; `n>=100 and probability_edge>=0.05` and not STRONG → `MODERATE`.
- `statistical_has_edge = bool(edge.has_edge or exported_edge_quality in {"STRONG","MODERATE"})` (L366).
- `_state_sig = f"{vol_regime}|{trend_direction}|{trend_maturity}|{structure_quality}"` (L410) — 4 dimensions, written as `debug_signature`; the runner independently builds a **9-dimension** `debug_signature` (`run_vanguard_from_packages.py:1094–1104`) into the same CSV column name. → CON-249 (companion).

**Models** — no model of its own; it is a wiring and labelling layer. The only fitted-looking constants are the `edge_quality` cuts (0.03 / 0.40 / 0.015) at L250–254, with no calibration source stated.

**Outputs**
- Files/tables written: **NONE directly.** Returns `VanguardSignal(ticker, timestamp, verdict, final_recommendation, layer_1_result, layer_2_result, layer_3_result=None, reasoning, execution_plan=None)` (L412–574). `scripts/run_vanguard_from_packages.py` flattens `layer_1_result`→`layer1__*`, `layer_2_result`→`layer2__*` (L1214–1216) and writes `<run_dir>/vanguard/vanguard_signals.csv` (L1279) with `csv.DictWriter` over `sorted(union of row keys)` (L183–189).
- Fields written into `layer_2_result` (L418–567), grouped: identity (`state_hash`, `debug_signature`); sample (`n_observations`, `sample_confidence_bucket`, `preferred_horizon`); match audit (12 `state_match_*` / `sample_size` / `confidence_penalty` / `confidence_weight` / `matched_state_key` / `original_state_key` / `fallback_reason`); calibration (16 `raw_*` / `baseline_probability` / `adjusted_*` / `probability_edge` / `probability_verdict`); 20d block (12 fields incl. `recommended_hold_days`); 5d block (7); 10d block (7); 39 `ret_pctl_*` + 3 `n_obs_*`; the whole nested `outcomes` dict; edge block (`has_edge`, `edge_direction`, `edge_quality`, `legacy_edge_quality`, `failed_gate`, `no_edge_reason`, `edge_gate_has_edge`, `legacy_failed_gate`, `legacy_no_edge_reason`, `statistical_support_note`); `discovery_flag`; 4 state fields; 7 v2 state fields; 9 v6 future-bucket fields; `bucket_edge_quality`.
- Atomic promotion? **NO** — the runner writes the CSV in place via `csv.DictWriter` with no temp-file-and-rename. OBSERVED (`run_vanguard_from_packages.py:183–189`). → GAP-255.
- Schema/version field? **NO** version token is placed in `layer_2_result`; `StateVector.schema_version`/`bucket_schema_version` are computed (`state_calculator.py:311–312`) but **not copied** into `layer_2_result` by the explicit field list at L539–552, so they reach the CSV only through the nested `outcomes`/`layer2__*` flatten — and `outcomes` is `ActuarialOutcomes`, which carries no schema version at all. INFERRED (basis: explicit key list L418–567; confidence HIGH). → GAP-245.
- Fields carrying authority claims:
  - L16–17: "layer3_execution (TradeBuilder) intentionally excluded — Vanguard is an intelligence layer only. Execution authority belongs to Options Intelligence → EIL → PSE → MVE" → **HOLDS** for this file (no import, `execution_plan=None`, `layer_3_result=None` at L337/L568/L573). **PARTIAL package-wide**: `vanguard/layer3_execution/__init__.py:6–7` still imports and exports `TradeBuilder` and `MultiScenarioBuilder`. → CON-248.
  - L326–335: "Vanguard authority: determine historical edge quality / sample strength / preferred horizon / probability evidence. Vanguard must NOT finalise execution, choose contracts, size risk, or issue execution-style verdicts" → **PARTIAL**. No contract or size is emitted. However `recommended_hold_days` (an integer hold length) and `kelly_fraction` (a position-size fraction) are both written into `layer_2_result` at L476 and L478, and `preferred_horizon` is written at L434 where it is later aliased into EV3's `horizon_bucket` (`ev3_stage0.py:92–97`). → CON-251, CON-252.
  - L29–35 `_sample_confidence_bucket` docstring: "Downstream consumers (EIL, MVE, PSE) must gate on this field. INSUFFICIENT_SAMPLE / CONTEXT_ONLY must never reach execution" → an instruction to other stages, not verifiable here; within this file no such gate exists. PARTIAL.
  - L45–50 `_select_preferred_horizon` docstring: "Not an execution instruction — a historical edge label for downstream routing" → **PARTIAL**: it is labelled advisory here, but `ev3_stage0.FIELD_ALIASES["horizon_bucket"]` consumes it as the horizon of record when the routed value is absent. → CON-251.
  - L113–117 `_validate_actuarial_database_contract` docstring: "Fix 2 — validate parquet schema, not just filename. A correctly named file can still be missing required canonical columns" → **HOLDS** for column presence; it does **not** check fingerprint, row count, date range, `calculation_version`, or maturity flags. → GAP-242.
  - L424–426: "win_rate_20d = P(20d_return > 0) — directional win rate; prob_up_10pct_20d = P(hit +10% within 20d) — target hit rate; These are DIFFERENT metrics — do not conflate" → **HOLDS** (matches `actuarial_query.py:1100` and L1113).
  - L428–431 FIX-04: "win_rate_5d and win_rate_10d are now written explicitly so that run_vanguard_from_packages._ov() finds them as top-level l2 keys" → **HOLDS** (L480, L488; consumed at `run_vanguard_from_packages.py:1126–1155`).
  - L510–512: "SERIALISATION: must be a plain dict — NOT the raw dataclass object" → **HOLDS** (L513–519 uses `dataclasses.asdict` with an `__dict__` fallback).
  - L435–436 Patch H: "Runner flattens these into layer2__state_match_* CSV columns automatically" → **HOLDS** (`run_vanguard_from_packages.py:1215`).

**Handoff**
- Receives from: `vanguard/integration/orchestrator_adapter.py::OrchestratorAdapter.adapt_result` (the `VanguardInput`), built by `scripts/run_vanguard_from_packages.py` from the per-ticker package JSON produced at evening stage 9 (packages, L4042) out of discovery stage 10 (L4115).
- Hands to: `scripts/run_vanguard_from_packages.py` → `vanguard/vanguard_signals.csv` → catalyst truth (stage 16), Options Intelligence (stage 18), Horizon Router (stage 19, L4208), EIL/PSE/MVE.
- Join keys: `ticker`; downstream `signal_id` where present.

**Missing-data handling**
| condition | emitted value/state | file:line | §10-compliant? |
|---|---|---|---|
| `outcomes is None` (unreachable) | `"NO_MATCH"` / `"NO_OUTCOMES"` / `0.0` / `0.30` | L214–228 | N |
| attribute absent on outcomes | `"UNKNOWN"`, `""`, `0.0`, `False`, `0.30`, `"NO_STAT_EDGE"` | L214–229 | N |
| `fallback_reason` empty | `"NONE"` | L225 | N |
| `n < 10` | verdict `INSUFFICIENT_SAMPLE`, recommendation `NO_ACTUARIAL_DATA` | L378–380 | N (closest legitimate intent; not a §10 token) |
| `n < 50` | `edge_quality` stays `"NONE"`, `discovery_flag=False` | L244–247 | N |
| direction not CALL/PUT | `"STAT"` in the recommendation, raw value in `edge_direction` | L372–376, L523 | N |
| `intraday_df` attribute missing | `intraday_rows = 0` via bare `except Exception` | L168–171 | N |
| DB file missing | `FileNotFoundError` raised — **fail-closed** | L93–97 | Y (hard stop, not a silent default) |
| DB filename wrong | `RuntimeError` raised — **fail-closed** | L99–105 | Y |
| required column missing | `RuntimeError` raised — **fail-closed** | L139–145 | Y |
| optional column missing | printed note, continues | L151–152 | N |

**Contradictions found here:** CON-246, CON-248, CON-249, CON-251, CON-252, CON-254, CON-262, CON-264, CON-271
**Gaps found here:** GAP-240, GAP-242, GAP-243, GAP-244, GAP-245, GAP-255
**Comment/docstring claims audited:** 10 claims — 5 HOLDS, 5 PARTIAL, 0 FALSE.
**Confidence in this section:** HIGH — whole file read; the CSV-write mechanics were confirmed directly in `scripts/run_vanguard_from_packages.py` (L183–189, L1214–1216, L1279).

---

### vanguard/layer2_statistical/edge_detector.py
**Classification:** Multi-gate veto engine + direction/confidence scorer. The only Vanguard component that assigns a direction.
**Real execution position:** stage 15 of 51, evening; invoked by `vanguard/main.py::VanguardEngine.analyze` (L303).
**Task in the process:** Applies six ordered gates to the state/outcomes/auction triple and returns an `EdgeAssessment` carrying `has_edge`, `edge_direction`, `edge_magnitude`, `confidence`, `right_side_score`, `failed_gate`, `no_edge_reason`, `signal_type`, `forward_momentum_confidence` and `bucket_edge_quality`. It also contains a signal-type fast path that can bypass the regime EV floor entirely.
**Entry points:** `EdgeDetector.detect_edge(state, outcomes, auction_verdict) -> EdgeAssessment`; module function `calculate_trading_costs(ticker, liquidity_tier)`; static `EdgeDetector._bucket_edge_quality(state, outcomes)`.
**Imports (production):** `..schemas.state_outcomes_schema.{StateVector, ActuarialOutcomes}`, `..schemas.auction_schema.AuctionVerdict`, `..schemas.trade_schema.EdgeAssessment`, `..config.EDGE_DETECTION_THRESHOLDS`. · **Imported by:** `vanguard/layer2_statistical/__init__.py` (L7), `vanguard/main.py` (L15). · **Broken/retired imports:** L40 `from ev_engine_v2 import EVEngineV2, ev_inputs_from_row` — a **top-level absolute import of a repo-root module** wrapped in `try/except ImportError: _EV_ENGINE_V2 = None` (L39–43). It resolves only when the repo root is on `sys.path`. The failure is silent. → CON-256.

**Inputs**
- Files/tables read: NONE.
- Upstream fields consumed (with fallback chains):
  - `macro_regime = getattr(state,'macro_regime','TRANSITIONAL') or 'TRANSITIONAL'` (L173) — bridges both *absent* and *empty-string* macro regime to the neutral regime, which selects the mid EV floor.
  - `positional = getattr(state,'positional_strategy', True)` (L188) — **default True disables the intraday penalty**; `StateVector.positional_strategy` defaults `True` (`state_outcomes_schema.py:177`), so `no_intraday` at L190–194 is always `False` and Gate 0 never downgrades the auction state. OBSERVED.
  - `signal_type = getattr(outcomes,"signal_type","NO_EDGE")` (L304); `momentum_tier = getattr(outcomes,"momentum_tier","TIER_4_FLAT")` (L325).
  - EVEngineV2 input row (L258–283) is built from 20 `getattr(..., default)` reads including `runway_pct` 2.0, `delta` 0.40, `theta` 0.01, `iv_rank` ← `state.iv_percentile` (a 0–100 value passed into a field named `iv_rank` whose own default is `0.50` — a **scale mismatch**, 0–100 versus 0–1), `composite` ← `state.value_acceptance_score` (default 50.0), and `breakeven_pass_live=True` hard-coded.
  - `_bucket_edge_quality` reads `sample_size` via `getattr(outcomes,"sample_size",0) or getattr(outcomes,"n_observations",0) or 0` (L671–675) — an `or` chain that treats a genuine sample size of 0 as "try the next source".
  - `_check_trend_exhaustion` defaults: `trend_maturity 'N/A'`, `trend_direction 'SIDEWAYS'`, `adx 0.0`, `distance_from_52w_high -1.0`, `distance_from_52w_low 1.0` (L409–413).
  - `_check_options_viability` defaults: `days_to_earnings -1`, `days_since_earnings 999`, `liquidity_condition 'NORMAL'`, `iv_percentile 50.0`, `vol_regime 'NORMAL'` (L453–457).
- External calls: `_EV_ENGINE_V2.evaluate(ev_in)` (L285) when the module imported — the result `ev_res` is **assigned and never used** (L286–288). OBSERVED.
- Config/policy read: `EDGE_DETECTION_THRESHOLDS` (`config.py:93–101`) — of its seven keys only `min_data_confidence` (0.70) is used (L215). `min_expected_value`, `min_probability_target`, `max_drawdown_tolerance`, `min_sharpe_ratio`, `min_observations`, `optimal_observations` are loaded into `self.thresholds` and never referenced. OBSERVED.

**Logic and algorithms**
- **Six-gate cascade** — `detect_edge` (L168–402), documented at L150–158:
  - **Gate 0 INTRADAY_DATA_INTEGRITY** (L187–205): sets `effective_auction_state = "SEARCHING"` and an `intraday_warning` when `intraday_rows == 0 and not positional`. Dead in production (see above).
  - **Gate 1 AUCTION_CONFLICTED** (L208–212): veto when `effective_auction_state == "CONFLICTED"`.
  - **Gate 2 DATA_CONFIDENCE** (L215–223): veto when `outcomes.confidence_level < 0.70`. Since `confidence_level = min(1, n/50)` (`actuarial_query.py:1130`), this is exactly **n < 35**. INFERRED (basis: the two quoted lines; confidence HIGH). → GAP-246.
  - **Gate 3 TREND_EXHAUSTED** (L226–231) → `_check_trend_exhaustion` (L408–446).
  - **Gate 4 OPTIONS_VIABILITY** (L234–239) → `_check_options_viability` (L452–497).
  - **Gate 5 REGIME_MINIMUM_EV** (L241–402), preceded by the signal-type fast paths.
- **Signal-type override** (L298–353), evaluated **before** the regime floors:
  - `signal_type == "CONTINUATION"` and `ev_10d > 0.0015` → immediate `_has_edge(verdict_tier='TRADE')` with `net_ev = ev_10d`.
  - `signal_type == "TRANSITION"`: `momentum_tier == "TIER_1_ACCELERATING"` and `ev_20d > 0.0030` → `_has_edge` TRADE; else `ev_20d > 0.0020` → `_setup_forming`.
  - Otherwise falls through to the regime floors.
- **Regime EV floor tables** — `REGIME_EV_FLOORS` (L89–96) and `REGIME_SETUP_FORMING_FLOORS` (L98–105), keyed on `macro_regime` with `.get(regime, TRANSITIONAL)` (L355, L372, L598) — bridges any unrecognised regime string to the mid floor.
- Decision branches (CALL / PUT / other-blank):
  - `_determine_direction` (L503–534) — the **only** direction producer in Vanguard.
    - **CALL** when `score > 15`.
    - **PUT** when `score < -15`.
    - **other/blank/tie** (`-15 <= score <= 15`): else-block L529–534 — `BUYERS`→CALL, `SELLERS`→PUT, and a final unconditional `return "CALL"`. **A neutral controller with a neutral score returns CALL.** No NONE / NEUTRAL / STRANGLE / UNRESOLVED outcome exists. → CON-270.
  - `_no_edge` (L646–652) sets `edge_direction="NONE"` — the only non-CALL/PUT value the class emits, and only on a gate veto.
  - `_check_trend_exhaustion` (L422–444): `trend_direction == "UP"` → long-exhaustion test; `== "DOWN"` → short-exhaustion test; **`SIDEWAYS` / `SIDEWAYS_BUILDING` / `SIDEWAYS_RANGING` / any other value → no veto** (falls to `return {'veto': False}` at L446). The gate is also pre-empted for every non-`"LATE"` maturity at L415–416, which includes both SIDEWAYS sub-classes emitted by `state_calculator._sideways_maturity`.
  - `_check_options_viability` has no direction branch: earnings and IV vetoes apply identically to CALL and PUT candidates.
  - `_calculate_right_side_score` (L577–582) branches on `macro_regime` only, and its `RISK_ON`/`RISK_OFF`/`TRANSITIONAL` arms miss `TRANSITIONAL_BULLISH/BEARISH/NEUTRAL` — those three regimes receive **no** macro bonus, although the EV-floor tables do enumerate them. OBSERVED.

**Computations and formulas (exact)**
- `calculate_trading_costs` (L48–62): tiers HIGH {spread .0010, slippage .0005}, NORMAL {.0025, .0015}, LOW {.0050, .0030}; returns `spread + slippage`; a hard-coded 12-symbol allowlist (L49–52) forces tier HIGH. Default-tier result: **0.0040**. Units: fraction of underlying. The value is passed to `_has_edge`/`_setup_forming` and printed in the rationale, but **never subtracted** from `net_ev`.
- `_scaled_ev_floor(base, n)` (L112–121): `conf = min(1.0, n/500)`; `floor = base·(0.65 + 0.35·conf)`. Bounds `[0.65·base, base]`.
- `REGIME_EV_FLOORS` (ev_floor, wr_floor): RISK_ON (0.0005, 0.36); TRANSITIONAL_BULLISH (0.0005, 0.36); TRANSITIONAL_NEUTRAL (0.0010, 0.38); TRANSITIONAL (0.0010, 0.38); TRANSITIONAL_BEARISH (0.0015, 0.40); RISK_OFF (0.0020, 0.43).
- `REGIME_SETUP_FORMING_FLOORS`: RISK_ON (0.0000, 0.32); TRANSITIONAL_BULLISH (0.0000, 0.32); TRANSITIONAL_NEUTRAL (0.0003, 0.34); TRANSITIONAL (0.0003, 0.34); TRANSITIONAL_BEARISH (0.0005, 0.36); RISK_OFF (0.0008, 0.38).
- `CONTINUATION_FASTPATH_EV_FLOOR = 0.0015`; `TRANSITION_SETUP_EV_FLOOR = 0.0020`; `TRANSITION_ACCELERATION_EV_FLOOR = 0.0030` (L107–109).
- `EXHAUSTION_PROXIMITY` (L125–132): RISK_ON −0.04; TRANSITIONAL_BULLISH −0.04; TRANSITIONAL_NEUTRAL −0.06; TRANSITIONAL −0.06; TRANSITIONAL_BEARISH −0.08; RISK_OFF −0.10. `EXHAUSTION_MIN_ADX = 22.0` (L134).
- `EARNINGS_BLACKOUT_DAYS = 10`; `EARNINGS_REENTRY_DAYS = 3`; `IV_SPIKE_PERCENTILE = 85`; `LIQUIDITY_MIN_CONDITION = "LOW"` (L138–141) — the last is **declared and never used** (the liquidity veto was removed at L459–464).
- `net_ev = outcomes.expected_value_20d` on **all three** branches (L288, L290, L292) — no cost subtraction, EVEngineV2 result discarded.
- `win_rate = outcomes.win_rate` (L295) — P(20d return > 0).
- TRADE: `net_ev >= ev_floor and win_rate >= wr_floor` (L360). SETUP_FORMING: `net_ev > sf_ev_floor and win_rate >= sf_wr_floor` (L376). Note the `>` versus `>=` asymmetry against the RISK_ON setup floor of exactly 0.0000, which excludes `net_ev == 0`.
- `_determine_direction` score (L504–523): `+40·control.confidence` BUYERS / `−40·control.confidence` SELLERS; `+30` (CONSISTENT*) or `+15` migration UP, `−30`/`−15` DOWN; `+20` if `prob_up_10pct_20d > 0.55`, `−20` if `< 0.35`; `+10` if trend UP and `prob_trend_continues_20d > 0.60`, `−10` if trend DOWN and the same. Approx range [−100, +100]; thresholds ±15.
- `_calculate_confidence` (L536–549): `state.confidence·0.25 + outcomes.confidence_level·0.35 + auction_conf·0.40`, `auction_conf = auction.confidence·(0.60 if no_intraday else 1.0)`. `_setup_forming` multiplies the result by 0.7 (L723). Bounds [0,1].
- `_calculate_right_side_score` (L551–589): base 50; `+25` ALIGNED / `+15` TRANSITIONING / `+5` SEARCHING; `+20·control.confidence` if controller ∈ {BUYERS, SELLERS}; `+15` CONSISTENT* / `+10` TRENDING*; `+10` if `prob_up_10pct_20d > 0.60 or < 0.30`, else `+6` if `> 0.55 or < 0.35`; `+5` if trend ≠ SIDEWAYS and `prob_trend_continues_20d > 0.65`; macro `+15`/`+15`/`+8`; a `+5` earnings-drift arm that is unreachable because `prob_drift_into_earnings` is never populated by `actuarial_query.py`. Capped at 100.0 (L589).
- `_bucket_edge_quality` (L654–694), in order: `early and bucket_n>=100 and bucket_conf>=0.55 and bucket ∈ {HIGH,EXTREME}` → `EARLY_EXPANSION_STRONG`; `bucket_n>=100 and bucket_conf>=0.60 and bucket ∈ {HIGH,EXTREME}` → `BUCKET_STRONG`; `early and bucket_n>=50 and bucket_conf>=0.50 and bucket=="MID"` → `EARLY_CANDIDATE_MODERATE`; `high_sample and prob_edge>=0.10` → `STATISTICAL_STRONG`; `high_sample and prob_edge>=0.05` → `STATISTICAL_MODERATE`; `ev_20d>=0.015` → `LEGACY_MODERATE`; else `WEAK`. `high_sample = sample_size>=100 and state_match_quality ∈ {"HIGH","HIGH_SAMPLE","MEDIUM_HIGH"}` (L676) — but `state_match_quality` is produced by `_sample_quality` with values {HIGH_SAMPLE, MODERATE_SAMPLE, LOW_SAMPLE, INSUFFICIENT_SAMPLE} (`actuarial_query.py:543–550`), so `"HIGH"` and `"MEDIUM_HIGH"` never match and `MODERATE_SAMPLE` is excluded: only `HIGH_SAMPLE` (n ≥ 300) qualifies. OBSERVED. → CON-261.

**Models**
- Name: *EdgeDetector v2.1 multi-gate*. Type: ordered rule set + additive scoring tables. Inputs: `StateVector`, `ActuarialOutcomes`, `AuctionVerdict`. Output: `EdgeAssessment`. Parameters: as listed above.
- Calibration source claimed: L68–88 asserts the EV floors were "recalibrated against live actuarial EV range", citing "run 20260415" and "run 20260502, 1486 tickers, TRANSITIONAL regime; Positive EV signals: 899/1486 (60.5%); EV range (positive): 0.055% to 0.709%; EV mean (positive): 0.176%", and states "New floors set at ~20th percentile of positive EV distribution per regime". Verdict **PARTIAL**: internally coherent (floors 0.05%–0.20% sit inside the quoted band) but no artefact, script or dataset is referenced. `_scaled_ev_floor`'s shape (0.65 + 0.35·n/500) carries **no** calibration claim.
- Version tag: `[PATCHED v2.1]` in the module docstring (L2); not emitted in any output field.

**Outputs**
- Files/tables written: NONE. Returns `EdgeAssessment`.
- Fields: `has_edge`, `edge_direction`, `edge_magnitude` (= `net_ev`), `confidence`, `right_side_score`, `failed_gate`, `no_edge_reason`, `state`, `outcomes`, `auction_verdict`, `rationale`, `signal_type`, `forward_momentum_confidence`, `bucket_edge_quality`.
- Atomic promotion? NOT_APPLICABLE. Schema/version field? NONE.
- Fields carrying authority claims:
  - L7–15 BUG-01 note: "FIX: Gate 5 now calls EVEngineV2 (the single EV authority) to compute net_ev. Falls back to actuarial outcomes.expected_value_20d - cost if EVEngineV2 is unavailable" → **FALSE**. `ev_res` is computed at L285 and discarded; all three assignments set `net_ev = outcomes.expected_value_20d` (L288, L290, L292) and no cost is subtracted on any branch. A later comment (L249–255, FIX-EV2) documents the real behaviour, so the file contradicts itself. → CON-255.
  - L19–22 "ZERO REGRESSION GUARANTEE: All gate logic, threshold constants … are UNCHANGED from the original. Only Gate 5's net_ev source is fixed. All other gates (0–4) are byte-for-byte identical." → **FALSE**. Both floor tables were changed twice afterwards (L68–88, dated 2026-04-16 and 2026-05-02); the Gate 4 liquidity veto was removed (L459–464, FIX-EV3); Gate 0 was rewritten around `positional_strategy` (L175–194); `_scaled_ev_floor` was added (L112–121, FIX RC-2). → CON-255 (second limb).
  - L25–29 "PRESERVED: … `_has_edge()`, `_setup_forming()` — unchanged" → **PARTIAL**: both now compute and pass `bucket_edge_quality` (L701, L740) and `signal_type` (L714, L738).
  - L294 "FIX 2 preserved: P(return>0) directional win rate, not target hit rate" → **HOLDS** (L295).
  - L300–303 "signal_type is set by actuarial_query Stage 0 V2 matching … getattr defaults to NO_EDGE when signal_type absent" → **PARTIAL**: it is set by the *match ladder* (`actuarial_query.py:859, 873`), not a "Stage 0"; the getattr claim HOLDS.
  - L459–464 FIX-EV3 "Liquidity condition veto removed … EIL S1 enforces liquidity at execution time" → **HOLDS** (`liquidity_condition` is read at L455 and never tested).
  - L656–663 `_bucket_edge_quality` docstring listing five labels → **PARTIAL**: seven are returned. → CON-261.
  - L117–118 "Logic: confidence = min(1.0, n/500); floor = base * (0.65 + 0.35*confidence)" → **HOLDS** (L120–121).

**Handoff**
- Receives from: `state_calculator.py` (state), `actuarial_query.py` (outcomes), `auction_synthesizer.py` (verdict), all via `main.py:303–307`.
- Hands to: `vanguard/main.py`, which writes `edge_direction`, `edge_quality`, `bucket_edge_quality`, `has_edge`, `failed_gate`, `no_edge_reason`, `rationale` into `layer_2_result`.
- Join keys: NONE.

**Missing-data handling**
| condition | emitted value/state | file:line | §10-compliant? |
|---|---|---|---|
| EVEngineV2 not importable | `_EV_ENGINE_V2 = None`, silent | L42–43 | N |
| EVEngineV2 raises | bare `except Exception`, `net_ev` unchanged | L289–290 | N |
| macro_regime absent/blank | `"TRANSITIONAL"` (mid floor) | L173 | N |
| macro_regime unrecognised | `.get(regime, TRANSITIONAL)` | L355, L372, L598 | N |
| signal_type absent | `"NO_EDGE"` | L304 | N |
| momentum_tier absent | `"TIER_4_FLAT"` | L325 | N |
| trend_maturity absent | `"N/A"` → exhaustion gate skipped | L409, L415 | N |
| days_since_earnings absent | `999` → re-entry blackout skipped | L454 | N |
| iv_percentile absent | `50.0` → IV-spike veto skipped | L456 | N |
| sample_size 0 | `or`-chain to `n_observations`, then 0 | L671–675 | N |
| gate veto | `has_edge=False`, `edge_direction="NONE"`, `failed_gate=<gate>`, `no_edge_reason=<text>` | L646–652 | N — informative, outside §10 vocabulary |

**Contradictions found here:** CON-255, CON-256, CON-261, CON-270
**Gaps found here:** GAP-240, GAP-243, GAP-246, GAP-258
**Comment/docstring claims audited:** 8 claims — 3 HOLDS, 3 PARTIAL, 2 FALSE (L7–15, L19–22).
**Confidence in this section:** HIGH — whole file read; the `high_sample` vocabulary mismatch and the dead Gate 0 both follow from constants quoted in two files.

---

### vanguard/integration/orchestrator_adapter.py
**Classification:** Input adapter / contract gate. Converts orchestrator package JSON into the `VanguardInput` dataclass.
**Real execution position:** stage 15 of 51, evening; invoked by `scripts/run_vanguard_from_packages.py` (described at its L16 as the "per-package FAIL-CLOSED … contract gate").
**Task in the process:** Normalises one package payload into `VanguardInput`: resolves ticker and price, parses the as-of timestamp, coerces OHLCV from four alternative source paths into a lower-cased numeric DataFrame, derives 52-week extremes and an ATR history when absent, and assembles `TechnicalData`, `MacroData`, `CalendarData` plus empty `OptionsData`/`MicrostructureData`. Returns a typed `AdaptResult` that never raises, or a raising legacy path.
**Entry points:** `OrchestratorAdapter.adapt_result(payload) -> AdaptResult`; `OrchestratorAdapter.adapt(payload) -> VanguardInput`; module functions `validate_ohlcv(df)`, `adapt(dict)`.
**Imports (production):** `pandas`, `logging`, `dataclasses`, `datetime`, `typing`; `..schemas.input_schema.{VanguardInput, TechnicalData, MacroData, OptionsData, CalendarData, MicrostructureData}` with an absolute-path retry (L40–54). · **Imported by:** `vanguard/integration/__init__.py` (L6), `scripts/run_vanguard_from_packages.py`. · **Broken/retired imports:** the double `try/except ImportError` at L40–55 ends in `_SCHEMAS_OK = False` plus a `log.warning`, turning an import failure into a per-row rejection rather than a process failure.

**Inputs**
- Files/tables read: NONE (receives an in-memory dict).
- Upstream fields consumed (with fallback chains):
  - `price = _f(payload["current_price"], 0.0)`; if `<= 0`, `price = _f(disc["stock_price"] or disc["price"], 0.0)` (L150–153). A payload with no usable price yields **price 0.0** and is **not** rejected.
  - `ts_raw = payload["as_of_utc"] or payload["analysis_timestamp"]`; on absence or parse failure → `datetime.now(timezone.utc)` (L155–160). **Bridges a missing/unparsable as-of timestamp to wall-clock now**, which becomes `VanguardSignal.timestamp` (`main.py:414`). → GAP-245.
  - OHLCV chain (L185–188): `technical_data.ohlcv` → `ohlcv_daily` → `timeseries.ohlcv_daily` → `ohlcv`. Empty → `_Reject(["NO_OHLCV_DATA"])`, one of only three hard rejections.
  - 52-week extremes (L198–205): `tp["high_52w"]` else `max(close.tail(252))`; the `hi52 or float(tail.max())` idiom also bridges a literal 0.0 to a computed value.
  - ATR history synthesised as `(high-low).abs().rolling(14).mean().dropna().tail(90)` inside `try/except Exception: pass` (L208–216) — a **true-range-free** proxy substituted for ATR history, silently empty on failure.
  - `vwap_daily = _f(tp["vwap_daily"] or tp["vwap_15m"], 0.0)` (L234) — bridges the daily VWAP to the 15-minute VWAP.
  - `rsi = _f(tp["rsi"], 50.0)` (L242).
  - `vix = _f(mp["vix"] or reg["vix"] or 20.0, 20.0)` (L254) — **bridges a missing VIX to a fabricated 20.0**, which then determines `macro_regime` in `state_calculator.py:749–751` (20.0 is neither `<15` nor `>25`, forcing the TRANSITIONAL_* branch). → CON-278.
  - `spy_trend = str(mp["spy_trend"] or "UNKNOWN").upper()` (L262).
  - `days_to_earnings`: `int(dte)` else `None` on `TypeError/ValueError` (L268–271).
  - `data_quality_score = _f(payload["data_quality_score"], 1.0)` (L175) — **bridges unknown data quality to perfect quality**; that value multiplies directly into `state.confidence` (`state_calculator.py:907`).
  - `wyckoff_phase_bucket` (L219–227): read from the payload, then injected **only if** `inspect.signature(TechnicalData.__init__).parameters` contains the name. `TechnicalData` (`input_schema.py:61–137`) declares no such field, so the guard always fails and the pre-computed bucket is **always dropped**, forcing `state_calculator.py:91–96` onto the raw-phase fallback. OBSERVED. → CON-279.
  - `_f` (L289–296) returns the default for `None`, non-numeric and NaN alike — one default covering three distinct conditions. `_fn` (L299–306) is the `Optional` variant, used only for `compression_ratio`.
- External calls: `datetime.now(timezone.utc)` (L158, L160).
- Config/policy read: NONE.

**Logic and algorithms**
- **Reject/accept contract** — `_Reject` (L282–287) carrying `codes` and `diag`; `adapt_result` maps it to `AdaptResult(ok=False, reason_codes=...)` and any other exception to `["ADAPTER_EXCEPTION"]` (L122–133).
- **OHLCV normaliser** — `_to_ohlcv_df` (L317–363): accepts DataFrame/list/dict, lower-cases columns, requires `{open, high, low, close, volume}`, sorts on the first of `timestamp`/`date`/`t` (treating an integer `timestamp` as epoch-ms), coerces the five columns numeric, drops rows with null `close` or `volume`.
- **Standalone `validate_ohlcv`** (L62–74) requires ≥20 rows — used only by the module-level `adapt()` (L82), **not** by `OrchestratorAdapter._build`. The class path applies no minimum-row check. OBSERVED.
- Decision branches (CALL / PUT / other-blank): **NONE.** No direction concept exists in this file.

**Computations and formulas (exact)**
- `hi52 = tp.high_52w or max(close[-252:])`; `lo52 = tp.low_52w or min(close[-252:])` (L200–205). Units: price. The 52-week extreme is taken from **closes only**, not from highs/lows.
- `atr_history = mean_14((high-low).abs())[-90:]` (L214). Units: price. A mean of daily ranges, not a Wilder ATR; omits the gap terms of true range.
- `_f(v, d) = float(v) if finite else d` (L289–296); `_fn(v) = float(v) or None` (L299–306).

**Models** — NOT_APPLICABLE (pure coercion).

**Outputs**
- Files/tables written: NONE. Returns `AdaptResult` / `VanguardInput`.
- Fields set on `VanguardInput` (L166–179): `ticker`, `analysis_timestamp`, `current_price`, `technical`, `macro`, `calendar`, `options=OptionsData()` (empty), `microstructure=MicrostructureData()` (empty), `data_quality_score`, `macro_regime`, `compression_ratio`, `wyckoff_phase`. Never set: `missing_data_fields`, `avshunter_signal`, and nothing named `intraday_rows` or `intraday_df`.
- Atomic promotion? NOT_APPLICABLE. Schema/version field? **NONE** — no contract version is stamped, and `vanguard/schemas/vanguard_contract.py`'s `CONTRACT_VERSION = "2.0"` mechanism is not used. → GAP-249.
- Fields carrying authority claims:
  - L7–14 "Two public methods required by run_vanguard_from_packages.py" → **HOLDS** (L122, L135).
  - L20–25 ROOT CAUSE FIX "This file adds the complete class implementation" → **HOLDS**.
  - L123 "Preferred path — never raises, returns AdaptResult" → **HOLDS** (bare `except Exception` at L131).
  - L108–120 class docstring documenting `technical_data: {…, wyckoff_phase_bucket, …}` → **PARTIAL**: the key is documented and read (L219) but structurally cannot reach `TechnicalData`.
  - Because `OptionsData()` and `MicrostructureData()` are always constructed empty (L173–174), every options- and tape-derived branch downstream (`_calculate_positioning_bias`, `_measure_flow_from_tns`, `_measure_aggression_from_tns`, `_measure_participant_diversity`, `_measure_volume_trend_from_tns`) is permanently on its fallback path. INFERRED (basis: the two no-argument constructor calls; confidence HIGH). → GAP-253.

**Handoff**
- Receives from: `scripts/run_vanguard_from_packages.py::build_orchestrator_like_payload` (L661), built from the evening stage-9 package JSON and the stage-10 discovery output.
- Hands to: `vanguard/main.py::VanguardEngine.analyze`.
- Join keys: `ticker` (upper-cased, L146).

**Missing-data handling**
| condition | emitted value/state | file:line | §10-compliant? |
|---|---|---|---|
| schemas not importable | reject `SCHEMA_IMPORT_FAILED` | L142–144 | N — informative rejection, not a §10 token |
| empty ticker | reject `MISSING_TICKER` | L147–148 | N (same) |
| no OHLCV in any of 4 paths | reject `NO_OHLCV_DATA` with a `tried` diagnostic | L191–195 | N (same; provenance recorded) |
| price absent/≤0 after both sources | `current_price = 0.0`, **accepted** | L150–153 | N |
| as-of timestamp absent/unparsable | `datetime.now(timezone.utc)` | L155–160 | N |
| 52w extremes absent | computed from the last 252 closes | L200–205 | N |
| ATR history uncomputable | `[]` via `except Exception: pass` | L215–216 | N |
| VIX absent | `20.0` | L254 | N |
| SPY trend absent | `"UNKNOWN"` | L262 | N |
| RSI absent | `50.0` | L242 | N |
| any other numeric absent | `0.0` | L231–243 | N |
| data_quality_score absent | `1.0` | L175 | N |
| days_to_earnings unparsable | `None` | L268–271 | N |
| `wyckoff_phase_bucket` supplied | silently discarded | L219–227 | N |
| unexpected exception | reject `ADAPTER_EXCEPTION` + `exception_type` | L131–133 | N (type recorded) |

**Contradictions found here:** CON-278, CON-279
**Gaps found here:** GAP-240, GAP-245, GAP-249, GAP-253
**Comment/docstring claims audited:** 4 claims — 3 HOLDS, 1 PARTIAL.
**Confidence in this section:** HIGH — whole file read; the `wyckoff_phase_bucket` drop and the empty `OptionsData`/`MicrostructureData` follow directly from the constructor calls and the `input_schema.py` field lists.

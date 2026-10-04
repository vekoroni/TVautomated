# AVSHUNTER Discovery-stage audit: direction-agnosticism evidence base

Read-only static audit of `/mnt/user-data/uploads/AVSHUNTER-Intelligence/` (Windows repo copy), carried out on 30 Sep 2026.
No pipeline code was executed and no files were modified. `python3.13 ast` was used only to enumerate dict keys.
Line numbers refer to the staged copy.

Design requirement under test: **Discovery must be direction-agnostic until the data assigns a direction, with no regression.**

---

## 0. Stage path, as actually wired

```
intelligent_orchestrator.py  run_evening (~5500-5960)
  Phase 0   load_scanner_manifest() :658      <- reads data/output/universe_scanner/scanner_manifest.json (if <24h)
            merge_scanner_inputs / build_augmented_universe :804   (prepends NEW GO/PROBE tickers)
            write_scanner_context(session_id)
  preflight / run-scoped macro copy  -> RUNS_DIR/<sid>/macro/macro_runtime_base.json (:318-336)
  macro normalise, quant packet, bond, USMI, merge_macro_enrichment_into_macro_latest (:2031) -- all on run-scoped copy
  scanner_context_latest.json (REDUCED field set) :5877-5921
  run_discovery() :1933  -> subprocess avshunter_discovery_ULTIMATE.py --universe --force-update --run-id [--scanner-context]
  write_scanner_context(canonical_run_id) :5938
  apply_external_intel_review_lane() :2067 -> scripts/apply_external_intel_review_lane.py  (REWRITES discovery CSV in place)
  apply_macro_enrichment_to_discovery() :1996 -> scripts/apply_macro_enrichment_to_discovery.py (REWRITES discovery CSV in place)
  validate_quality(summary) :2113  (run-level abort gate)
```

Inside Discovery, `scan_ticker_ultimate` (avshunter_discovery_ULTIMATE.py:1288) runs this sequence for each ticker:

1. `load_bars`
2. liquidity/ATR filters
3. `WyckoffEngine.analyze`
4. `process_precore_signal`
5. `crabel_compression`
6. `fuse_wyckoff_crabel`
7. `compute_asymmetry_swing` (only if fusion is LONG/SHORT)
8. `detect_early_position`
9. composite/tier
10. `validate_wyckoff_phase`
11. `_reconcile_intent`
12. `resolve_discovery_thesis_direction`
13. geometry
14. build the row

The scanner-context file that Discovery actually receives is `OUTPUT_DIR/universe_scanner/scanner_context_latest.json`, written at orchestrator :5888-5914. It lacks `scanner_primary_route`, `signal_grade_route`, `lss_*` and `iv_rank_source`, so `final_discovery_route` (discovery :2164-2169) resolves to `WATCHLIST_ONLY` for every ticker (confidence 90%). No Python consumer of `final_discovery_route` was found outside Discovery.

Discovery reads macro from `ROOT/dropbox/macro/macro_intelligence_latest.json` (discovery :2396). That file is the un-normalised base, not the run-scoped, normalised and enriched `macro_path` that the post-Discovery scripts use. As a result the Discovery `macro_*` columns and the post-Discovery enrichment come from different macro snapshots. The orchestrator exports the `AVSHUNTER_SECTOR_BIAS_MAP`, `AVSHUNTER_MACRO_QUANT_PACKET` and `AVSHUNTER_MACRO_REGIME_STATE` env vars (:1508-1516), but Discovery never reads them.

---

## 1. Module inventory

| Module | On production path? (who calls) | Purpose | Inputs → Outputs |
|---|---|---|---|
| `intelligent_orchestrator.py` | Entry point | Evening workflow. Phase 0 scanner consumer, macro prep, Discovery subprocess, two in-place CSV post-processors, quality gate. | Macro JSON, scanner manifest, universe CSV → cmd line to Discovery, `scanner_context_*.json`, QA reports |
| `avshunter_discovery_ULTIMATE.py` | YES (subprocess, `cfg.DISCOVERY_ULTIMATE`) | Per-ticker structural scan. Loads bars, applies price/liquidity/ATR filters, runs Wyckoff + Precor + Crabel + fusion + validator, then scores, tiers, derives direction and geometry, and writes the CSVs. | Universe CSV, bars (canonical DB/CSV cache/Polygon), dropbox macro JSON, scanner_context_latest → `discovery_candidates_ultimate_{ts}.csv`, `discovery_lifecycle_{ts}.csv`, `early_positions_…`, `final_watchlist_…`, `discovery_summary_…json`, `run_manifest_ultimate_…json` |
| `WyckoffEngine_3101_v2.py` | YES (discovery :43, :1331; `WyckoffEngine(min_bars=20)` :2493) | Scores phases A–E independently. Event scoring per phase, control (BUYERS/SELLERS/EQUILIBRIUM/SHIFTING), operator, trade_direction LONG/SHORT/NONE, levels. SOR-001 prior-range fix lives here. | OHLCV df → dict: current_phase, phase_evidence_strength, dominant_event, control_state, operator, trade_direction, execution_bias, stop_loss, initial_target, truth_confidence, contradictions, transition_bias… |
| `wyckoff_crabel_precor_logic_v2.py` | YES (discovery :45, :1337, wrapped in try) | Second, independent state machine (labelled "audit enrichment"). Covers control, NR7/NR4/inside-bar compression, Spring/UTAD/SOS/SOW/SC/BC events, phase, mode (ACCUMULATION/DISTRIBUTION), intent (BUY_SETUP/SELL_SETUP/TRANSITION/WAIT), transition, move age. | OHLCV (tail 180, needs ≥50 bars) → dict wyckoff_phase/_conf, wyckoff_mode, control_state, primary_event, crabel_compression_state, crabel_score, intent, transition_to, move_age_bars |
| `wyckoff_phase_validator.py` | YES (discovery :46, :1527) | Stricter adjudication. Chooses primary vs alternative phase, mode, event-sequence score, maturity, status, pseudo-transition probabilities, structural_invalidation_level. | wyckoff_data, precor_data, bars → 21 fields prefixed `wyckoff_validation_` |
| `swing_fusion.py` | YES (discovery :66, :1353; import guarded) | Claims to be the "single authority for direction+intent". direction = f(Wyckoff control, Wyckoff operator). Alignment score; intent gate. | wyckoff dict, crabel_result (typed `state`), precor (audit only) → direction, intent, alignment_score, contradictions, fusion_rule_fired, audit |
| `enums_structural.py` | YES (Wyckoff, fusion, asymmetry, discovery :68) | Canonical strings: ControlState, Direction(LONG/SHORT/NONE), Intent(BUY_SETUP/SELL_SETUP/TRANSITION/OBSERVE_ONLY/WAIT), CrabelState (incl. DATA_INSUFFICIENT), WyckoffPhase, Operator (LONG_OPERATORS={ACCUMULATION,MARKUP}, SHORT_OPERATORS={DISTRIBUTION,MARKDOWN}). | none |
| `asymmetry_gate_swing.py` | YES but functionally inert (discovery :67, :1362) | Shelf-geometry entry/stop/target/R for LONG/SHORT. **`asymmetry_pass` is algebraically always False** (§5). | direction, crabel_result (no shelf keys → 30-bar hi/lo), df → entry, stop, target1, R_to_T1, pass, shelf_* |
| `regime_threshold_injector.py` | YES (discovery :2395-2397) | Resolves the macro regime label. Threshold tables exist but are **not applied**; it only stamps `cfg.active_regime/_label`, `macro_authority`. | dropbox macro JSON → cfg attrs |
| `polygon_data_fetcher.py` | YES (discovery :44, :2488; `load_bars` :1024) | Polygon daily aggregates (adjusted), write-through to canonical DB. | ticker, from/to → OHLCV df (to_date = today; a partial session is not flagged) |
| `domain/structure_mode_phase.py` | YES (discovery :48, :1470) | `wyckoff_mode_phase_key` = `MODE:PHASE` with provenance. Unknown stays UNKNOWN/UNCONFIRMED. | precor mode, precor phase, engine phase → (key, source) |
| `domain/thesis_direction.py` | YES, indirectly (via `contracts/direction_governance.py`) | Direction vocabulary (CALL/PUT/STRANGLE/NON_DIRECTIONAL/UNRESOLVED), `normalise_direction`, `resolve_structural_direction` (precor intent × EMA trend table), FrozenThesis, validation transitions. | strings → canonical direction |
| `domain/scanner_evidence.py` | Scanner only (scanner :81). Not imported by Discovery. | `volume_concentration_side` (CALL/PUT/BALANCED/NO_VOLUME), `lead_route`. | volumes/score → labels |
| `domain/structure_episode.py` | **NOT on path** (only self-referential; no importer outside domain/tests) | C3 dated structure-episode reducer (future ontology). | StructureObservation seq → transition dicts |
| `contracts/direction_governance.py` | YES (discovery :47, :1583) | `resolve_discovery_thesis_direction` (Stage-0 freeze); later-stage GDR/resolution (Options). | fusion dir, Wyckoff dir, reconciled precor intent, EMA trend → (direction, status, basis) |
| `canonical_data/history_bridge.py` | YES (discovery `load_bars` :943-1005; polygon :178) | CDS-2 canonical price DB read / write-through / shadow parity. Disabled by default (flags). **`feature_flags.py` and `historical_prices.py` are not in the staged copy**, so they could not be verified. | ticker → df with attrs data_source/data_as_of |
| `canonical_data/structure_feature_reader.py` | **NOT on Discovery path** (only tests import `read_feature_window`) | Point-in-time feature window for historical replay (SOR-001). | sqlite, ticker, decision_session → CanonicalFeatureWindow |
| `canonical_data/discovery_publisher.py` | Post-Discovery (orchestrator `publish_cds3_discovery_worklist` :3253-3300, called ~:3529) | Publishes `discovery_lifecycle_*.csv` into the CDS control plane and the Packages worklist. Shadow unless `AVSHUNTER_STAGE_GATING_ENFORCED`. | lifecycle CSV → registry rows |
| `scripts/macro_quant_packet.py` | YES (discovery :50-60, :2407, :2182; orchestrator) | Normalises macro into 75 flat `MACRO_QUANT_CSV_FIELDS` plus per-ticker `ticker_sector_alignment`. | macro JSON (+row) → dict |
| `scripts/avshunter_universe_scanner.py` | **Out-of-band producer.** The orchestrator never executes it (only an existence check in preflight :1061). Its manifest is consumed if <24h old (`load_scanner_manifest` :658). | MarketData.app VMS/IV/LSS scanner. Emits `scanner_manifest.json`, `vms_scoreboard_latest.csv` (with `direction` CALL/PUT/NEUTRAL, score, decision, iv_rank…), `contracts_latest.csv`. It affects Discovery in three ways: (1) universe augmentation with NEW GO/PROBE tickers, (2) +5/+2 composite uplift, (3) display columns. `scanner_direction` is in the context JSON but not copied into the Discovery row. | MarketData API → CSV/JSON |
| `scripts/apply_macro_enrichment_to_discovery.py` | YES, post-Discovery, non-critical (orchestrator :1996, :5940) | Rewrites the Discovery CSV in place, adding 22 enrichment + 3 bias columns. **Overwrites `macro_direction_authority`**. | discovery CSV, run-scoped macro → same CSV |
| `scripts/apply_external_intel_review_lane.py` | YES, post-Discovery, non-critical (:2067, :5939). It runs *before* macro enrichment. | Stamps 17 `external_intel_*` columns on survivors and writes a separate `external_intel_review_candidates_*.csv` (catalyst/macro-only tickers, precor_intent=WAIT). Core membership is unchanged (verified). | discovery CSV, catalyst calendar, macro → CSVs |

---

## 2. DIRECTION INVENTORY

Classification codes:
- **(a)** produced
- **(b)** assumed/defaulted, where missing or tied input maps to a side
- **(c)** asymmetric: a bull rule with no bear mirror, or different thresholds
- **(d)** used as filter/score

### 2.1 WyckoffEngine_3101_v2.py

| ID | Line(s) | Snippet | Class | Missing mirror / note |
|---|---|---|---|---|
| W1 | 157-167 | `if current_phase in {'C','D'} … if _roc_20 > 30.0 and close > _ema50: current_phase = 'B'` | c | There is no `roc_20 < -30 and close < EMA50` rule. Only strong *up* moves are demoted from C/D, which dampens bullish D/C only. |
| W2 | 350-358 | `if df['low'].iloc[i] < range_low*0.98: break_count += 1; if next close > range_low: reclaim_count += 1` | c | No upside break or fail-back counter (`high > range_high*1.02` and next close `< range_high`), so upthrust/UTAD evidence is never measured. |
| W3 | 363-368 | follow-through fail only for `close > prior high` (up breakouts) | c | No failed-breakdown counterpart. This is a different construct from W2's reclaim. |
| W4 | 403-404 | `buyer_score += features['reclaim_count'] * 3` (unbounded) | c | **F2 CONFIRMED.** Sellers get only `+2` flat when ft_fail_rate > 0.5 (:407-408). Weights and bounds differ and there is no upthrust count. |
| W5 | 394-400, 411-415 | absorption poc>0.7 / <0.3; avg_poc >0.65 / <0.35 | – | Symmetric (OK). |
| W6 | 421-432 | `diff>3` BUYERS, `diff<-3` SELLERS, `|diff|<=1` EQUILIBRIUM | a | Symmetric thresholds. Inherits W4 bias. |
| W7 | 520-523 | Phase C score `+60` if break(low)&reclaim, `+30` break only | c | "Classic spring/UTAD" is scored only from downside breaks. |
| W8 | 715-722 | Phase C events only `if features['break_count'] > 0` (downside); SELLERS → `'UTAD'=75, 'UT'=60` | a/c | A downside break with seller control is labelled **UTAD/UT**, which is semantically an upthrust. A genuine upside UTAD cannot produce a Phase C event (it falls back to `TR=40`, :633-634). |
| W9 | 723-728 → 179 | `scores['Spring']=45; scores['UTAD']=45` then `max(event_scores, key=event_scores.get)` | b | **F3 CONFIRMED.** A tie resolves by dict insertion order, so **Spring** always wins. |
| W10 | 884-891 | `long_events=['Spring','SOS','LPS','Test','ST','AR']`; `if event in long_events and control in [BUYERS, EQUILIBRIUM]: LONG` | a/b | EQUILIBRIUM plus the tie-Spring gives **LONG** (F3). SHIFTING gives NONE. |
| W11 | 673-684 + 884 | Phase B: `low_vol_bars>=4 → ST=75, Test=70` (≥3: 65/60; ≥2: 55/50) | c/a | **F3 (Phase B) CONFIRMED.** Low-volume bars carry no side, yet 'ST'/'Test' ∈ long_events, so the result is LONG under BUYERS/EQUILIBRIUM. There is no bearish Phase B event such as ST-of-highs/UT/LPSY. ST=75 beats Absorption (≤70) and TR (≤65). This is probably the single largest structural long-bias source, because Phase B plus ≥2 low-volume bars in 10 is common. |
| W12a | 884 | `'AR'` in long_events | c | An AR after a BC (up climax) is bearish. In practice it is unreachable because AR=65 < SC/BC=70. |
| W12b | 884-885 | `short_events` contains `'BC'` but long_events lacks `'SC'` | c | Phase A: an up climax (BC=70) gives SHORT (under SELLERS/EQUIL), while a down climax (SC=70) gives NONE. This asymmetry favours **short**. |
| W13 | 687-696 | `Absorption_Up=Absorption_Down` equal scores | b | The tie picks Absorption_Up (label only). Discovery maps both to 'AR' → `ACCUMULATION_PRESSURE` (D11). |
| W14 | 740-745 | `SOS` if `> range_high*1.02`; `SOW` if `< range_low*0.98` | a | Symmetric. |
| W15 | 556-590, 599-603 | Phase D/E scoring | – | Symmetric (up/down both scored; E uses abs). |
| W16 | 930-938 | execution_bias `BULLISH`/`BEARISH`/`OBSERVE_ONLY` from control | a | Symmetric given control. |
| W17 | 1028-1036 | operator ACCUMULATION/MARKUP/DISTRIBUTION/MARKDOWN from (phase, control) | a | Symmetric given control, but inherits W4. |
| W18 | 1046-1062 | LONG: stop `20d low*0.98`, target `20d high*1.05`; SHORT: stop `20d high*1.02`, target `20d low*0.95` | a | Mirror-symmetric, but the target is an arbitrary % beyond the 20-bar extreme and not a structural measure (F9). |
| W19 | 1086-1095 | insufficient data → control EQUILIBRIUM, trade NONE, transition_bias 'B' | – | Neutral. |
| W20 | 1331 (discovery) | `analyze(…, trend_context="UNKNOWN")` | – | Phase A trend hint (:457) and regime conflicts (:866-869) are dead. |

### 2.2 wyckoff_crabel_precor_logic_v2.py

| ID | Line(s) | Snippet | Class | Missing mirror / note |
|---|---|---|---|---|
| P1 | 277 | `_output_insufficient: "wyckoff_mode": "ACCUMULATION"` (<50 bars) | b | Should be UNKNOWN. |
| P2 | 301-361 | control: slopes ±2, EVR buy/sell ×0.8, fail_breakdown/fail_breakout ×0.7, ±2.5 | a | **Symmetric**, unlike W4. |
| P3 | 441-540 | SC/BC, Spring/UTAD (upside sweep detected here), SOS/SOW | a | Symmetric. |
| P4 | 615-620 | default D for BUYERS&slope≥0 or SELLERS&slope≤0 | a | Symmetric. |
| P5 | 647-651 | range mode: `recent_ret >= 0 → ACCUMULATION` | b | A zero drift resolves to accumulation. More generally, mode is forced binary: there is no UNRESOLVED mode. |
| P6 | 691-696 | Phase C: `control=="BUYERS" → BUY_SETUP` (no mode check); `SELLERS` needs `mode=="DISTRIBUTION"` else `TRANSITION` | c | **F5 CONFIRMED.** |
| P7 | 727-732 | Phase E: `mode ACCUMULATION → BUY_SETUP` (even with SELLERS); DIST needs SELLERS/EQUILIBRIUM; fallback `BUY_SETUP` ("control wins") also for SHIFTING | b/c | **F5 CONFIRMED.** The default fallback is BUY. |
| P8 | 716-720 | Phase D: SOS/(ACC&BUYERS) tested before SOW | – | Effectively symmetric (mode follows event). |
| P9 | 774-776 | C→D conf 78 only if `net_dir >= 2` | c | Bearish follow-through (`net_dir <= -2`) gets 70. Minor; this feeds phase_align via transition conf. |
| P10 | 207-230 | emits `intent` BUY_SETUP/SELL_SETUP/TRANSITION/WAIT, `wyckoff_mode` | a | |

### 2.3 avshunter_discovery_ULTIMATE.py

| ID | Line(s) | Snippet | Class | Missing mirror / note |
|---|---|---|---|---|
| D1 | 236-249, 1572 | `_get_dominant_trend` BULLISH/BEARISH/MIXED from EMA9>21>50>200 | a | Symmetric. EMA200 is computed on whatever df exists (min_bars 30; the legacy path has ~62 bars from a 90-day lookback, :2371). **F6 CONFIRMED** (70% on bar count; depends on canonical flags not staged). |
| D2 | 252-261 | `_get_ema_stack`: `'ALIGNED' if e9>e21>e50>e200 else 'MIXED'` | c | A perfect bearish stack reads as `MIXED`. |
| D3a | 264-277 | `_days_above_ema50` | c | There is no `days_below_ema50`. |
| D3b | 280-290 | `_pct_from_52w_low` | c | There is no `pct_from_52w_high`. |
| D4 | 320-323 | Rule 1: `SELL_SETUP` and *either* control == BUYERS → `TRANSITION` | c | **F4 CONFIRMED.** No trend condition. |
| D5 | 325-329 | Rule 2: `BUY_SETUP` and either SELLERS **and** trend BEARISH → `TRANSITION` | c | Stricter than Rule 1. |
| D6 | 331-335 | Rule 3: `SELL_SETUP` → `BUY_SETUP` if BULLISH & ALIGNED & ≥40d above EMA50 & ≥25% off 52w low | a/c | **F4 CONFIRMED.** There is no BUY→SELL mirror in a mature downtrend. In combination with G4 below, SELL_SETUP has two paths to CALL (Rule 1 → TRANSITION + BULLISH → CALL; Rule 3), while BUY_SETUP has one path to PUT (Rule 2 + BEARISH). |
| D7 | 520-528 | early crabel bonus if control BUYERS or SELLERS | – | Symmetric. |
| D8 | 561-562, 593, 2247-2248 | `stop_loss = current_price * 0.97`, `stop_pct 3.0`; `signal.update(early_signal)` | b | **F8 CONFIRMED.** Every Tier-0 row gets a long-side `stop_loss`, overwriting the structural one. It **also overwrites `control_state`** with Precor's (:605) and `phase`. |
| D9 | 658-690, 1424, 2036 | granular bucket: A/B→ACCUMULATION_EARLY, C→ACCUMULATION_SPRING, D→MARKUP_ENTRY, E→MARKUP_CONTINUATION | b | **F14 CONFIRMED.** The DIST/MARKDOWN branches are unreachable because phase_raw is always a single letter or UNKNOWN. This feeds `prior_label`. |
| D10 | 818-828, 1423, 2035 | broad bucket A/B/C→ACCUMULATION, D/E→MARKUP | b | **F14.** DISTRIBUTION/MARKDOWN are unreachable. `wyckoff_phase_bucket` feeds the actuarial state hash (comment :2035), so any fix changes the hash (regression risk). |
| D11 | 693-740 | `'ST'→'TEST'` → `BULLISH_REVERSAL`; `ABSORPTION_DOWN→'AR'` → `ACCUMULATION_PRESSURE`; `TREND_CONTINUATION→'TR'` | c/b | Side-less Phase-B events get bullish family labels. |
| D12 | 745, 1490 | HIGH set includes `TEST_OF_SPRING` | c | No `TEST_OF_UTAD`. Dormant because no engine emits it. |
| D13 | 1360-1367 | asymmetry gate only if fusion LONG/SHORT | d | Inert (§5). |
| D14 | 1570-1588 | `resolve_discovery_thesis_direction(fusion, wyckoff trade_direction, reconciled precor intent, EMA trend)` | a | **Direction produced here** (frozen `direction`). |
| D15 | 1686-1706 | `vwap_acceptance_score` CALL/PUT mirrored; UNRESOLVED 0.5 | d | Symmetric between sides, but it is a direction-conditioned score. |
| D16 | 1709-1717 | `repricing_direction` CALL/PUT/COUNTER_*/UNRESOLVED | a/d | |
| D17 | 1728-1741 | `_ema_aligned` (CALL&BULLISH or PUT&BEARISH) → abnormal_repricing_score (+10 vs +3) | d | Unresolved rows are penalised, which feeds `candidate_lane` (:1947-1954). |
| D18 | 1912-1924, 2622-2623 | `lift_proxy_score` includes `vwap_acceptance*4`; used as the within-tier sort key | d | Direction-dependent ranking. Resolved rows rank above unresolved ones. |
| D19 | 1796-1800 | `structural_stop = current_price - max(atr*1.5, 2%)` (ATR_FALLBACK) | b | **F8 CONFIRMED.** A long-side stop is written to `stop_loss`/`structural_stop` for PUT, UNRESOLVED and STRANGLE rows. |
| D20 | 1801-1816 | target validity uses **Wyckoff `trade_direction`**, not `_candidate_direction` | c | Geometry and thesis can diverge. |
| D21 | 1822-1840 | governed invalidation accepted only if side-correct for CALL/PUT | a | Correct, but availability is asymmetric: validator mode defaults to ACCUMULATION (V1) → 40-bar low (a CALL-side level), and the ATR fallback is excluded. PUTs resolved from Precor with default-ACCUMULATION mode therefore get `MISSING_AUTHORITATIVE_INVALIDATION` more often than CALLs. |
| D22 | 1964-1976 | `rr = abs(target - price) / abs(price - invalidation)` | – | **F9 CONFIRMED.** `abs()` would hide a wrong-side target. |
| D23 | 2078-2089 | `discovery_direction_preliminary/_status/_basis`, `direction`, `direction_authority='DISCOVERY_GOVERNED'`, `fusion_direction/intent` | a | Vocabulary mix: LONG/SHORT (fusion), CALL/PUT/STRANGLE/UNRESOLVED (direction). **F10 CONFIRMED** (`STRANGLE` in Discovery). |
| D24 | 1984-1988, 2091-2097 | structural_stop/target and asymmetry_entry/stop/target1 emitted regardless of `direction` | – | **F9 CONFIRMED.** On `CONFLICT_REVIEW`/UNRESOLVED rows these carry the rejected side's geometry. Asymmetry values are emitted even though pass=False. |
| D25 | 2109-2113 | `precor_intent`, `precor_intent_raw`, `precor_control` | a | |
| D26 | 1872-1890, 2005 | `_etf_signal_score LEAD_LONG=+1 … AVOID=-1` → `macro_sector_advisory_score` | c | Long-framed macro display value. It has no score authority (`_sector_lift=0`). |
| D27 | 1383-1388, 1930-1935, 579-584 | Precor phase replaces Wyckoff phase if `precor_conf > wyckoff phase_evidence_strength` | – | Precor confs are constants (45-82), so Precor usually wins. The `phase_evidence_strength` column then holds Precor's constant confidence (mislabelled). Not a side rule, but it selects which engine's phase drives buckets/DTE. |
| D28 | 1390, 1595-1602, 867-869 | `trend_mat = wyckoff_data.get('trend_maturity')` | – | **Never produced** by any engine (grep). `maturity_score` is constantly 0.5 and `_LATE_TREND_PENALTY` is dead. |

### 2.4 wyckoff_phase_validator.py

| ID | Line(s) | Snippet | Class | Note |
|---|---|---|---|---|
| V1 | 81-90 | `_mode`: text match else `if control == "SELLERS": DISTRIBUTION; return "ACCUMULATION"` | b | **F7 CONFIRMED.** Missing mode plus non-seller control resolves to ACCUMULATION. Wyckoff never emits `wyckoff_mode`, so this applies whenever Precor failed. |
| V2 | 187-198 | invalidation = Wyckoff stop if present, else ACCUMULATION → 40-bar low / DISTRIBUTION → 40-bar high | b | Inherits V1 → CALL-side level by default. Feeds D21. |
| V3 | 19-32 | ACCUMULATION_EVENTS / DISTRIBUTION_EVENTS tables | – | Symmetric. |

### 2.5 swing_fusion.py

| ID | Line(s) | Snippet | Class | Note |
|---|---|---|---|---|
| F-1 | 124-135 | `BUYERS & operator∈{ACCUMULATION,MARKUP} → LONG; SELLERS & ∈{DISTRIBUTION,MARKDOWN} → SHORT` | a | **F1 CONFIRMED.** The operator is itself derived from Wyckoff control (Wyckoff :1028-1036), so fusion direction ≡ Wyckoff control whenever the phase is A–E. Precor is audit-only (:240-250). The "fusion" adds no independent evidence, and Precor's reconciliation (D4-D6) also keys on Wyckoff/Precor *control*. |
| F-2 | 158-189 | alignment +20 synergy, +10 dir/control agreement | – | Symmetric. |
| F-3 | 211-237 | intent gates | – | Symmetric. |

### 2.6 contracts/direction_governance.py and domain/thesis_direction.py

| ID | Line(s) | Snippet | Class | Note |
|---|---|---|---|---|
| G1 | dg 84-90 | preliminary: first directed of (fusion, Wyckoff trade_direction) | a | Wyckoff trade_direction adds the W9/W10/W11 LONG paths that fusion itself (EQUILIBRIUM → NONE) would not produce. |
| G2 | dg 93-128 | CONFIRMED / CONFLICT_REVIEW→UNRESOLVED / CONFIRMED_PRELIMINARY / RESOLVED_STRUCTURAL / STRANGLE | a | The table is mirror-symmetric (OK). |
| G3 | td 237-247 | `normalise_direction`: PUT tokens tested before CALL; `TRANSITION/MIXED/STRADDLE` → STRANGLE/NON_DIRECTIONAL | b | Substring matching. A text containing both a PUT and a CALL token resolves to PUT. |
| G4 | td 264-274 | `TRANSITION` + trend BULLISH → CALL, BEARISH → PUT, else STRANGLE | a | **F6 CONFIRMED.** The EMA stack decides every TRANSITION row. |

### 2.7 Scanner (out-of-band; only VMS score/decision reach the Discovery score)

| ID | Line(s) | Snippet | Class | Note |
|---|---|---|---|---|
| S1 | 1364 | `if compression and momentum_20d >= 0: call_votes += 1` | b | Zero momentum resolves to CALL. |
| S2 | 1336 | VMS score skew: `abs<0.05 → 20; skew>0 → 10; else 5` | c | Put-rich skew scores higher. This enters Discovery via the VMS uplift. |
| S3 | 2059-2064 | DC: call bonus skew>0.05 (+10), call penalty <−0.05 (−5); put bonus <−0.05 (+10), put penalty **>0.08 (−8)** | c | Different threshold/weight. |
| S4 | 2291-2292 | `above_ma20 = vms.get(...) or False` | b | Missing resolves to "below MA", a PUT-favouring default. |
| S5 | ~1670-1675 | LSS Form 4 CLUSTER_BUY +25 / SINGLE_BUY +10 / CLUSTER_SALE −15 on a side-less lead score | c | Bullish-favouring score. |
| S6 | discovery 1412-1417 | `VMS GO≥75 → +5; PROBE≥60 → +2` to composite_adjusted (tier) | d | **F10 CONFIRMED.** An option-level IV/mispricing score changes ticker tier before any thesis. |
| S7 | orch 924, 5901 | `scanner_direction` present in context; **not** copied into the Discovery row | – | OK. |

### 2.8 Macro (post-Discovery rewrite of the same CSV, and Discovery columns)

| ID | Line(s) | Snippet | Class | Note |
|---|---|---|---|---|
| M1 | enrich 212-235 (via contracts/macro_enrichment_delta.py 412-555) | `row.update({... "macro_direction_authority": ENABLED/LIMITED/DISABLED, "macro_direction_vote": CALL/PUT/ABSTAIN, "macro_raw_direction_hint": ...})` | a | **F13 CONFIRMED and extended.** This overwrites Discovery's `macro_direction_authority='NONE'` (:2002) when an enrichment delta exists (90%), contradicting the script's own "never changes existing discovery columns" docstring. |
| M2 | enrich 136-183, 238-265 | `macro_bias` CALL_TAILWIND / PUT_HEADWIND / CONTEXT_ONLY / NEUTRAL | a | Display, but side-labelled. |
| M3 | review lane 117-126 | `_direction_from_catalyst` PUT tokens (incl. NEGATIVE, VULNERABLE) tested first | a/c | Precedence asymmetric. Advisory only. |
| M4 | macro_quant_packet 493-512 | `ticker_sector_alignment` ALIGNED (preferred sector) / CONFLICTED (avoid) | c | Long-framed: an "ALIGNED" PUT is a headwind. The substring match `p in sector` is also loose. |
| M5 | discovery 2134-2135; injector 417-452 | `macro_regime`, `active_regime` columns | – | Display only; thresholds are not applied (§5). |

### 2.9 Counts

- **Asymmetric rules (c) on the core thesis path (Wyckoff + Precor + Discovery): 21.**
  - Wyckoff (9): W1, W2, W3, W4, W7, W8, W11, W12a, W12b
  - Precor (3): P6, P7, P9
  - Discovery (9): D2, D3a, D3b, D4, D5, D6, D11, D12, D20
- **Including scanner and macro display: 26** (adds S2, S3, S5, M3, M4).
- **Bullish defaults (b), where a missing or tied value maps to a bullish side: 10.**
  - W9, P1, P5, P7-fallback, D8, D9, D10, D19, V1, S1
- **Bearish defaults:** S4. W12b is short-favouring but is a (c) rule.
- **Direction producers (a):** Wyckoff trade_direction/control/operator/execution_bias, Precor intent/mode, fusion direction, `resolve_discovery_thesis_direction`, repricing_direction, macro enrichment vote/bias, scanner direction. That is 5 independent producers feeding 1 frozen `direction`, and 2 of them (Wyckoff and fusion) are the same signal.
- **Direction-as-score (d):** D13, D15, D17, D18, S6.

---

## 3. GATE INVENTORY (Discovery stage)

| # | File:line | Condition | Level | Reason code written | Correct label? |
|---|---|---|---|---|---|
| G0 | orch 5500-5515 | macro present but incoherent (`MACRO_PUBLICATION_PREFLIGHT_FAILED`) | run | log only; run aborts | – |
| G0b | orch 658-684 | scanner manifest >24h (local-vs-UTC naive age mix) | run | scanner ignored | – |
| G1 | disc 2515-2526 | `load_bars` None/empty | ticker | `NO_PRICE_DATA` / `DROPPED_TERMINAL_DATA` | yes |
| G2 | disc 1298 | `len(df) < 30` | ticker | `NO_SIGNAL_AT_ANY_HORIZON` (:2571-2580) | **no** (F15) |
| G3 | disc 1309 | price ∉ [5, 500] | ticker | same | **no** |
| G4 | disc 1313 | avg vol20 < 500k | ticker | same | **no** |
| G5 | disc 1323 | ADV$ < 2.5M ("options viability proxy") | ticker (option-motivated) | same | **no** |
| G6 | disc 1325 | ATR14 < $0.40 | ticker (option-motivated) | same | **no** |
| G7 | disc 1327 | ATR% < 1.0 | ticker (option-motivated) | same | **no** |
| G8 | disc 1637-1639 | `tier == 4` (composite_adjusted < 25) and no early signal | ticker | same | **no** (F11 hidden drop) |
| G9 | disc 2534-2546 | `assign_discovery_horizon` returns None | ticker | `NO_SIGNAL_AT_ANY_HORIZON` | **Dead code**: tiers 0-3 always map to a bucket (:2286-2293) |
| – | disc 2514-2581 | uncaught exception in `scan_ticker_ultimate` | run | crash (no `ERROR` outcome is ever produced; `lifecycle_errors` is always 0) | – |
| G10 | orch 2113-2200 | candidate_ratio < 15%, early (Tier-0) ratio < 1.5%, T1+T2 == 0 | **run abort** | `EVENING WORKFLOW ABORTED` | – **Regression hazard**: a direction-agnostic fix that shrinks Tier-0 or total counts can abort the evening run. |

Downgrades and upgrades during thesis formation (no drop):

| # | File:line | Effect | Level |
|---|---|---|---|
| U1 | disc 1630-1632 | early signal → tier 0 regardless of composite (bypasses G8) | ticker upgrade |
| U2 | disc 1412-1417 | VMS +5/+2 → tier | option-level evidence → ticker tier |
| U3 | disc 868-869 | late-trend −8 | **dead** (D28) |
| U4 | disc 891-899 | decay 3%/calendar day vs `date.today()` (cap 20%) → tier | ticker (F11). Weekend/holiday or late runs shift tiers. |
| U5 | disc 628-636 | composite `0.6w+0.4c` if c>0 else `w` | **non-monotonic** (F11): w=80,c=0 → 80; w=80,c=65 → 74. Adding compression can lower the tier. |
| U6 | disc 1946-1954 | stale → `candidate_lane=SUPPRESSED` | ticker |
| U7 | disc 2164-2169 | `final_discovery_route` → WATCHLIST_ONLY (always, see §0) | ticker label |
| U8 | Wyckoff 145-151 | best<40 or separation<10 → phase UNKNOWN | ticker |
| U9 | Wyckoff 157-169 | momentum override C/D→B (bull only, W1) | ticker |
| U10 | fusion 211-237 | OBSERVE_ONLY gates (alignment<50, UNKNOWN, evidence<30, NONE) | intent only |
| U11 | disc 320-335 | intent → TRANSITION / flip (D4-D6) | ticker |
| U12 | dg 117-121 | conflict → UNRESOLVED / CONFLICT_REVIEW | ticker |
| U13 | asym 124 | R<2 → pass False (always) → geometry falls back | ticker |
| U14 | disc 2234-2244 | rr_flag, cap 50 | ticker |
| U15 | validator 201-214, 273-277 | phase_status INVALIDATED/UNCERTAIN (emitted only; INVALIDATED *raises* p10 to ≥0.80, :282-283) | ticker |
| U16 | review lane / enrichment | no membership change (verified: `core_membership_changed: False`, rows unchanged) | – |

All Discovery drops are ticker-level. G5-G7 are *option-motivated* ticker filters. The only direct option-level input is the VMS uplift (U2). Every filter G2-G8 runs **before** any thesis and is side-agnostic in form.

---

## 4. OUTPUT CONTRACT: `discovery_candidates_ultimate_{run_id}.csv`

- Writer: `df_all.to_csv(out_candidates)` at disc :2617-2624, sorted by `tier` asc and `lift_proxy_score` desc.
- Row dict: disc :1977-2229. It has 161 literal keys, 5 of them duplicated, plus `**prefixed_validation_fields` (21) and `**macro_quant_columns_for_row` (75).
- Additional columns: `rr_flag` (:2236-2244); `early_signal` keys (:586-606) merged at :2247-2248; `horizon_bucket`, `discovery_basis`, `opportunity_label` (:2548-2555); 5 `activist_*` (:2341-2347).
- Total is about 279 columns from Discovery. The two post-processors then rewrite the CSV in place, adding about 19 (review lane) and 23 (enrichment) more.

**Duplicate keys (later value wins):**
- `crabel_score`: :1995 (Discovery ATR7/20 score *used in composite*) is overwritten by :2065 (**Precor NR7/inside-bar score**). So the CSV `crabel_score` is not the value used in `composite_score`.
- `data_source`, `is_stale`, `bar_data_asof`, `bar_data_days_old` are duplicated with the same values.

In the tables below, ★ marks a direction-bearing column (side value or side-conditioned computation).

### Identity / provenance

ticker, timestamp, tier, tier_label, sector, sector_etf, industry, data_source, data_as_of, is_stale, bar_data_source, bar_data_asof, bar_data_days_old, bar_evidence_state, bar_evidence_reason, horizon_bucket, discovery_basis, opportunity_label, candidate_lane★(via D17), final_discovery_route, signal_type (T0), entry_size (T0), activist_signal, activist_filing_date, activist_filing_type, activist_note, activist_priority_boost.

### Structure (Wyckoff / Precor / Crabel)

| Column | Direction-bearing? |
|---|---|
| phase, current_phase, phase_evidence_strength (see D27), phase_strength (T0) | |
| dominant_event, dominant_event_norm, dominant_event_bucket | |
| event_family | ★ (BULLISH_/BEARISH_ labels) |
| event_evidence_strength, event_evidence_bucket, event_quality | |
| control_state | ★ (overwritten by Precor for T0) |
| truth_confidence, truth_confidence_bucket, wyckoff_setup_quality | |
| wyckoff_execution_bias | ★ BULLISH/BEARISH |
| wyckoff_mode | ★ ACCUMULATION/DISTRIBUTION |
| wyckoff_phase_bucket | ★ (accumulation-only) |
| wyckoff_phase_granular | ★ |
| wyckoff_mode_phase_key | ★ |
| wyckoff_mode_phase_source, phase_convergence | |
| wyckoff_transition_to, wyckoff_transition_conf, precor_transition_to | |
| precor_phase | |
| precor_control | ★ |
| crabel_score (Precor, see dup), crabel_compression, crabel_pattern, crabel_bucket, crabel_state (T0) | |
| move_age_bars, move_age_bucket | |
| dominant_trend | ★ |
| ema_stack | ★ (bull-only ALIGNED) |
| days_above_ema50 | ★ |
| pct_from_52w_low | ★ |
| EMA9, EMA21, EMA50, EMA200, ATR_14, VWAP | |
| vwap_bias | ★ ABOVE/BELOW |
| volume_ratio, adx_14, atr_pct, atr_percentile_rank, adv_dollars, gap_pct, range_pct, range_expansion_vs_20d, dollar_volume_zscore | |
| compression_ratio, days_in_range, early_formation_score, conditions_met, base_conditions_count (T0) | |
| catalyst_proximity, days_to_trigger, days_to_trigger_source, distance_to_trigger_pct (T0) | |
| wyckoff_validation_* (21) | wyckoff_validation_wyckoff_structure ★, wyckoff_validation_structural_invalidation_level ★ |

### Direction

discovery_direction_preliminary★, discovery_direction_status★, discovery_direction_basis★, direction★, direction_authority, fusion_direction★, fusion_intent★, fusion_alignment_score, fusion_rule_fired★, fusion_contradictions, precor_intent★, precor_intent_raw★, repricing_direction★, wyckoff_entry_trigger★ (text "Enter LONG…").

### Geometry

stock_price, entry_price, stop_loss★ (long-side for T0/ATR fallback), structural_stop★, structural_stop_source, structural_target★, structural_target_source, governed_invalidation_spot★, governed_invalidation_source, asymmetry_pass, asymmetry_R, shelf_high, shelf_low, asymmetry_entry★, asymmetry_stop★, asymmetry_target1★, rr_underlying★, rr★, rr_confidence, rr_source, rr_flag, stop_pct (T0, long).

### Scores

wyckoff_score, composite_score, composite_adjusted (VMS/decay), prior_adjustment, prior_label (★ via bucket), lift_proxy_score★ (vwap term), win_probability (heuristic 35-75), vwap_acceptance_score★, abnormal_repricing_score★, repricing_state★, repricing_reason_codes★ (VWAP_ACCEPTANCE/REJECTION).

### Macro (Discovery-written)

macro_core_effective_delta, macro_candidate_authority, macro_direction_authority (overwritten later ★), macro_capital_authority, macro_sector_advisory_score★ (long-framed), macro_regime, active_regime, macro_abstain, plus the 75 macro-quant fields (incl. regime_distribution_bull/bear, ticker_sector_alignment★, preferred/avoid_sectors, equity_drawer_active…).

### Post-Discovery macro/external (same file)

- **Review lane:** external_intel_lane, _force_review, _source, _stage_status, _reason, **external_intel_direction_bias★**, _catalyst_status/_type/_date, _source_tier, _macro_theme_count/_ids/_roles/_pressure_label/_confirmation_required/_conflict_flags, _data_quality, external_intel_created_utc, symbol.
- **Enrichment:** macro_enrichment_* (13), macro_alignment_state★, macro_applicability, macro_direction_authority★ (overwrite), **macro_direction_vote★**, **macro_raw_direction_hint★**, macro_can_invert_direction, structure_first_required, trade_type_classification, macro_interpretation_reason, **macro_bias★**, macro_bias_source.

### Option-ish (scanner / scaffold)

vms_score, vms_decision, scanner_* (18 fields), route_source, signal_source, news_terminal_role, vol_spread, iv_rank, signal_detected_at, signal_grade, signal_hours_lead, lss_score, lss_decision, dte (from tier×phase scaffold; default phase 'C'), expiry, strike, contract_type, bid, ask, premium, iv, ivp (all None).

---

## 5. asymmetry_gate_swing.py and regime_threshold_injector.py

### asymmetry_gate_swing

It computes, for LONG, `entry = shelf_high*(1+0.003)`, `stop = shelf_low − 0.75·ATR14` and `target1 = entry + width`. SHORT is the mirror image. `crabel_result` never contains `shelf_*` (the discovery :432-447 result has no shelf keys), so the shelf is the 30-bar high/low (:81-82, :171-177).

**It is algebraically always failing.** For LONG, `R = width / (width + 0.003·shelf_high + 0.75·ATR) < 1 < min_r (2.0)`, and SHORT is identical. As a result:

- `asymmetry_pass` is always False.
- `_use_asymmetry` (disc :1772-1776) is never True.
- The `ASYMMETRY_GATE` stop/target source and the `rr_confidence='HIGH'` branch are dead code.
- entry/stop/target1 values are nonetheless emitted to the CSV (D24).

Side bias: none. The formulas are exact mirrors and the gate runs for both LONG and SHORT, but only for fusion (≡ Wyckoff control) directions. Confidence 99%, algebraic.

### regime_threshold_injector

- `resolve_regime` (:298-396) maps regime_state, risk_on_off_switch, vol_mode and dir_bias to RISK_ON, SELECTIVE_RISK_ON, TRANSITIONAL or RISK_OFF, using a recursive first-match `_find_field`.
- `apply_regime_to_config` (:417-452) **does not change any threshold**. It only sets `cfg.active_regime`, `active_regime_label`, `macro_authority='ADVISORY_ONLY'` and `macro_core_effective_delta=0.0`.
- The threshold tables at :262-288 are unused. The RISK_OFF comment "allow high-R:R PUTs" is dead.

In Discovery, `active_regime` reaches:

- `apply_state_prior_adjustment`, where it is ignored (:852-860, result unused).
- `regime_norm` (:1425), which is unused.
- `_regime_boost=0` (:1564).
- `regime_align=0.5` constant (:1592).
- `risk_off_floor`, which is logged only (:2463).
- The display columns `macro_regime` and `active_regime`.

**It does not violate "macro display-only" for membership, tier or direction.** Residual macro reach into Discovery:

1. `macro_sector_advisory_score` (display).
2. The 75 quant columns.
3. The *post-Discovery* M1/M2 rewrite, which puts a macro direction vote and authority into the Discovery CSV. This is the real F13 violation of "display-only", although it is not used for membership inside Discovery.
4. The mismatched macro snapshot (§0).

---

## 6. SOR-001 verification

| Change | Live? | Evidence |
|---|---|---|
| Prior-range Wyckoff (20 prior / 10 event bars) | **YES, default, no switch** | Wyckoff :323-342 (`anchor = df.iloc[max(0,anchor_index-20):anchor_index]`). No env/opt-in grep hits. |
| Typed Crabel state | **YES** | disc :350-447 `_typed_state` on all 4 exits (DATA_INSUFFICIENT/NONE/READY/COILING); fusion :75 `crabel.get("state")`; enums :346-360 DATA_INSUFFICIENT handled; fusion :164-165 distinct note. |
| `wyckoff_mode_phase_key` + source | **YES** | disc :1470-1474, :2037-2038; domain/structure_mode_phase.py. It is not consumed downstream (as the receipt says). |

### Effect on F2 and F3

**F2 was not fixed, and it is now more active.** The new prior range excludes the event bar, so `low < range_low*0.98` (and hence break_count/reclaim_count) is now reachable. The receipt itself says that under the old all-history range, "spring evidence [was] unreachable". The buyer-only `reclaim_count*3` bonus (:403-404) and the downside-only break counter (:350-358) therefore now fire, where previously they were effectively dormant. Confidence 85%; the old code was not available to diff.

**F3 was not fixed.** The Spring/UTAD 45/45 tie (:727-728), resolved by `max()` insertion order (:179) and the EQUILIBRIUM → LONG rule (:888), is untouched. Phase C events now fire more often because break_count is reachable, so the tie-to-LONG path is more exercised. The Phase B ST/Test long-only rule (:676-684) is untouched. UTAD is still triggered only by a *downside* break, and a true upthrust still cannot create a Phase C event.

**Typed Crabel state:** fusion uses Discovery's ATR7/20 compression. The early-position detector (:521-525) and `crabel_bucket` use Precor's NR7/inside-bar state/score. There are therefore two different Crabel definitions on the row, and the CSV `crabel_score` holds the Precor one (duplicate-key overwrite).

**mode_phase_key:** it correctly refuses a bullish default for an unknown phase. However, its mode comes from Precor, which is binary and zero-drift → ACCUMULATION (P5), with ACCUMULATION when insufficient (P1). The legacy buckets (D9/D10) remain accumulation-only and still feed the actuarial hash.

---

## 7. Re-verification of previously reported findings

| F | Status | Notes |
|---|---|---|
| F1 | CONFIRMED | fusion :124-135; operator from control (Wyckoff :1028-1036); Precor audit-only. |
| F2 | CONFIRMED (still live; *activated* by SOR-001) | :350-358, :403-404. |
| F3 | CONFIRMED | :723-728, :179, :888; Phase B :673-684. **Extension:** UTAD is triggered by a downside break (W8). |
| F4 | CONFIRMED | :320-335. Rule 3 needs `days_above >= 40` (not 60, as the docstring says). |
| F5 | CONFIRMED | Precor :691-696, :727-732 (lines unchanged). |
| F6 | CONFIRMED | td :264-274; EMA200 on ≥30 bars (disc :122, :1302-1303). |
| F7 | CONFIRMED | validator :87-90. |
| F8 | CONFIRMED | :562, :1797-1798, :2247-2248. **Extension:** T0 update also overwrites `control_state` and `phase`. |
| F9 | CONFIRMED | :1964-1976, :2091-2097, Wyckoff :1046-1062. |
| F10 | CONFIRMED | STRANGLE via td/dg; VMS uplift :1412-1417. |
| F11 | CONFIRMED | :1637-1639, :891-899 (`date.today()`), :628-636 non-monotonic. |
| F13 | CONFIRMED, and **stronger**: the post-Discovery rewrite overwrites `macro_direction_authority` and adds a macro CALL/PUT vote. Inside Discovery the regime is display-only. | |
| F14 | CONFIRMED | DIST/MARKDOWN buckets are unreachable. |
| F15 | CONFIRMED | 7 filters plus the tier-4 drop all use `NO_SIGNAL_AT_ANY_HORIZON`. The horizon-None drop is dead code. |

### Contradictions / corrections to prior reports

1. The asymmetry gate cannot pass at all (not merely "unbounded").
2. `trend_maturity` is never produced, so the late-trend penalty and maturity weighting are dead.
3. W12b (BC → SHORT with no SC → LONG) is a *short*-favouring asymmetry.
4. Precor control is symmetric; only the Wyckoff control is biased.
5. The `crabel_score` CSV column is not the composite input.
6. `final_discovery_route` is always WATCHLIST_ONLY, because of the reduced scanner-latest context.
7. Discovery and the post-scripts read different macro files.
8. The universe scanner is not executed by the orchestrator. It is consumed only through a fresh manifest.

---

## 8. Regression hazards for the solution design

- `validate_quality` run-abort thresholds (orch :565-568, :2137-2166). Changes to Tier-0 volume or candidate ratio can abort the evening run.
- `wyckoff_phase_bucket` / `wyckoff_phase_granular` feed the actuarial state hash and Vanguard. Adding DIST/MARKDOWN values changes the hash population.
- The `direction` vocabulary includes STRANGLE/UNRESOLVED consumed downstream (Options GDR `allow_non_directional_resolution`).
- `stop_loss` long-side values may be consumed downstream as-is (e.g. EIL/MP). Before changing them, the consumers need to be audited (not done here).
- Tests: tests/test_avs_sor001_*, test_directional_bias_fixes.py, test_direction_governance_contract.py, test_wyckoff_phase_validator.py, test_macro_enrichment_discovery_options.py (the last is reported unverified or hanging in the receipt).

## 9. Unverifiable items / confidence

| Item | Confidence | Reason |
|---|---|---|
| canonical_data `feature_flags.py`/`historical_prices.py` absent from the staged copy; bar count / EMA200 window | 70% | Assumed legacy 90-day ≈ 62 bars. |
| M1 overwrite occurs | 90% | Requires an enrichment delta file. |
| `final_discovery_route` always WATCHLIST_ONLY | 90% | |
| SOR-001 "activation" of F2/F3 | 85% | Inference from the receipt. |
| Scanner line ~1670-1675 (Form 4) | 95% | Relative offset. |

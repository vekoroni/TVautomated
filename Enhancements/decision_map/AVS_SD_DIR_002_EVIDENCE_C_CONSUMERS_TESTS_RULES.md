# AVSHUNTER — Regression-protection evidence base for "direction-agnostic Discovery + side-correct Vanguard"

Read-only audit of `/mnt/user-data/uploads/AVSHUNTER-Intelligence/` (30 Sep 2026). Nothing was executed or modified.
Line numbers refer to the staged tree. "Not staged" = referenced module absent from the upload (cannot be verified here).

Not staged but referenced by consumers/tests: `intelligence-lab/intelligence_lab.py`, `pipeline_interpreter/`, `execution_gate.py`,
`orchestrator/dynamic_validation.py`, `domain/pretrade_focus.py`, `avshunter/c12_outcome/`, `avshunter/c0_run/`,
`contracts/expression_candidate_packet.py`, `contracts/expression_valuation_packet.py`, `audit/avs_tev001_structural_cohort.py`,
`canonical_data/run_plan.py`, `canonical_data/option_liquidity_lifecycle.py`, `Enhancements/decision_map/OBJECTIVE_ASSURANCE_ASSESSMENT.md`
(the only place G1–G4 are defined), `REPLICATION_PLAN.md`, method notes 03/04/05. The design must re-audit these before claiming no regression.

---

## 0. The direction path today (as-built, in one diagram)

```
Discovery (avshunter_discovery_ULTIMATE.py:1570-1587)
  resolve_discovery_thesis_direction(fusion LONG/SHORT, wyckoff trade_direction, precor_intent, dominant_trend)
    -> CALL | PUT | STRANGLE | UNRESOLVED   (contracts/direction_governance.py:95-128)
  emits direction, discovery_direction_preliminary/status/basis, direction_authority='DISCOVERY_GOVERNED' (:2078-2082)
  AND conditions on that side: governed_invalidation_spot (:1829-1840), rr_underlying (:1964-1976),
       vwap_acceptance_score / repricing_direction / abnormal_repricing_score / candidate_lane (:1686-1741, :1946-1953)
        |
Vanguard (vanguard/main.py, edge_detector.py)  -- receives NO side
  _determine_direction (edge_detector.py:503-534): auction control/migration (neutral on all rows per SOR-001 §2)
       + prob_up_10pct_20d>0.55 (+20) / <0.35 (-20) + trend ; |score|<=15 and no controller -> "CALL" (:534)
  edge_quality STRONG = expected_value_20d>=0.03 AND prob_up_10pct_20d>=0.40 (main.py:249-255)  [upside-only]
  final_recommendation = f"{CALL|PUT|STAT}_EDGE_STRONG_{h}" (main.py:367-395)
  runner adds directional_force etc. via calculate_market_physics (scripts/run_vanguard_from_packages.py:1246)
        |
C5 descriptive packet (intelligent_orchestrator.py:6015-6024, CRITICAL: exception aborts Evening)
  domain/descriptive_forecast_handoff.py: direction {'CALL'->BULL,'PUT'->BEAR} exact dict lookup (:135-138)
        |
Options Intelligence parse_structural_context (scripts/avshunter_options_intelligence.py:4680-4722)
  if direction_authority=='DISCOVERY_GOVERNED': governed = Discovery direction, allow_non_directional_resolution=False
  else (legacy): governed = structural table; resolution allowed
  resolve_governed_direction(...) -> final_direction; direction not in {CALL,PUT} -> NO_DIRECTIONAL_STRATEGY,
  stand-down, no chain (:4811, :7953, :9949)
        |
EOD (_direction_evidence :1391-1466) -> Morning (validate_direction_record) -> Lab (validate + block) -> Finalizer (uniform DIR_CALC_VERSION)
```

Key consequence: **in fresh runs STRANGLE/UNRESOLVED are never resolved to a side by anyone** (Options passes
`allow_non_directional_resolution=False` for DISCOVERY_GOVERNED rows, :4691-4694). They are retained, visible, blocked, and get no chain,
no C5 forecast (DATA_INSUFFICIENT/DIRECTION_NOT_DIRECTIONAL) and no contract. Vanguard's `edge_direction` never decides the side in a fresh
run — but it still (a) populates `direction_resolution_call/put_score` + evidence JSON that `domain/pretrade_focus.project_evening_thesis`
uses to bucket the Evening thesis, (b) drives arbitration labels/`direction_conflict_gate`, (c) drives EIL `signal_type`, and
(d) is the resolving vote in every legacy-adapter path (Options legacy branch, EOD `_direction_evidence` when no `dir_calc_version`,
Morning `_ensure_governed_direction_record`).

---

## TASK A — Downstream consumer map

Usage codes: **D** display/audit · **S** score/rank input · **G** gate/exclusion/permission · **A** direction authority · **SIDE** contract side selection · **V** validation/integrity check.

### A.1 Direction vocabulary fields

| Field | Producer | Consumers (file:line) | Use | Regression risk if values/vocabulary change |
|---|---|---|---|---|
| `direction` (Discovery) | discovery_ULTIMATE:2081 via `resolve_discovery_thesis_direction` | `domain/descriptive_forecast_handoff.py:135-140` (exact `CALL`/`PUT` dict) ; Options `parse_structural_context:4679-4684` (as `discovery_preliminary`) ; `scripts/build_packages_from_discovery.py:436,473` (`contract_type` fallback) ; `intelligent_orchestrator.py:924,5901` (`scanner_direction` D) ; `contracts/handoff_contract.py:112,515` (identity field) ; lab_control `first(...)` projections | A (C5 packet side), SIDE (via Options), D | **CRITICAL.** `BULL/BEAR` in `direction` makes every descriptive-packet row `DIRECTION_NOT_DIRECTIONAL` (dict lookup is exact). Options would still work (normalise_direction maps BULL→CALL by substring, thesis_direction.py:90-93) but `discovery_preliminary` is `.upper()`-copied raw into GDR `preliminary`. A combined token such as `"BULL|BEAR"`/`"BULL_OR_BEAR"` normalises to **PUT** (PUT tokens are tested first, thesis_direction.py:90). Emitting 2 rows/ticker (one per side) raises `ValueError("duplicate ticker")` in descriptive_forecast_handoff.py:85-86 → **Evening abort** (orchestrator:6021-6024). |
| `direction_authority` | discovery:2082 (`'DISCOVERY_GOVERNED'`) | Options :4686-4702 (switches resolution OFF) ; descriptive_forecast_handoff.py:129 (must equal exactly, else `DIRECTION_NOT_GOVERNED`) | A, G | Changing the literal flips Options into the legacy adapter (resolution ON, authority `OPTIONS_INTELLIGENCE_LEGACY_ADAPTER`) and sets every C5 row `DATA_INSUFFICIENT`. If Discovery becomes direction-agnostic but keeps `DISCOVERY_GOVERNED`, **nothing downstream can ever assign a side** (resolution disabled) → 100 % stand-down. |
| `discovery_direction_status` / `_basis` / `_preliminary` | discovery:2078-2080 | Options :4679-4690 (basis into GDR `governed.basis` → record hash) ; EOD :1411 (legacy adapter) ; Morning :236 ; GDR `preliminary` block | A (basis), V (hash) | Basis text participates in `governed_direction_record_sha256`; any change alters hashes (fine per run, but breaks cross-version replay parity checks). |
| `direction_state` | **no producer in staged code** (spec §9 vocabulary SUPPORTED/OPPOSED/UNSUPPORTED/INSUFFICIENT_EVIDENCE) | none | — | New field: no regression, but must not reuse `UNRESOLVED` (legacy option-side token) as a direction_state value. |
| `thesis_direction` | not emitted as a column (module `domain/thesis_direction.py`: enum CALL/PUT/STRANGLE/NON_DIRECTIONAL/UNRESOLVED) | `FrozenThesis.__post_init__` (:149-171) accepts CALL/PUT/NON_DIRECTIONAL only; `assert_direction_continuity` (:209-245) ; `domain/ticker_forecast.from_legacy_frozen_thesis` (:110) | V, A | `FrozenThesis` rejects UNRESOLVED/STRANGLE (ValueError). BULL/BEAR pass `normalise_direction` → CALL/PUT, so tolerated. |
| `trade_direction` (Wyckoff) | WyckoffEngine (LONG/SHORT/NONE) | discovery:1571 (preliminary hint), :1801-1808 (target validity), EIL `_direction_arbitration_row:2559` alias | A (hint), G (target validity) | If Wyckoff stops emitting LONG/SHORT, preliminary hint becomes UNRESOLVED more often; structural target validity check (`_valid_target`) changes → more `PENDING_OI` targets. |
| `swing_direction` / `fusion_direction` | swing_fusion (`direction` LONG/SHORT/NONE) | discovery:1360-1363 (asymmetry gate only if LONG/SHORT), :1570 (hint), :2085 (D) ; Options :4681 fallback | A (hint), G (asymmetry geometry) | As above; asymmetry geometry is skipped when NONE → stop/target fall to Wyckoff/ATR path. |
| `precor_intent` | discovery `_reconcile_intent` :1573-1578, emitted :2111 | `structural_direction` table (thesis_direction.py:103-130) in Discovery and Options legacy branch ; Options `_direction_arbitration_oi:417-446` (BUY/SELL_SETUP vs Vanguard) ; `_macro_confirmation_overlay_oi:391` ; scoring :6973 ; EOD `_setup_type:320-338` | A, S, D | Closed mirror-symmetric table; pinned by tests. Changing intent vocabulary changes arbitration labels and EOD `setup_type`. |
| `governed_direction` / `final_direction` / GDR fields (`dir_calc_version`, `direction_policy_version/sha256`, `governed_direction_record_json/sha256`, `direction_resolution_*`) | `resolve_governed_direction` (direction_governance.py:257-373), written by Options :4707-4722, :5206-5212 | EOD `_direction_evidence:1391-1466`, `_candidate_direction:1354-1360`, `_eod_candidate_status:1251-1262` ; Morning `_ensure_governed_direction_record:220-248`, `_check_direction_integrity:251` ; lab_control :4068-4090 ; morning_handoff_finalizer.py:190-223, :930-937 (uniform `DIR_CALC_VERSION`) ; handoff_contract_audit.py:214 (hash FAIL), :764-779 (Options→Lab hash parity) ; `domain/pretrade_focus.project_evening_thesis` (call/put scores, evidence JSON; not staged; behaviour pinned by test_evening_thesis_decision) | A, SIDE, V, G | `validate_direction_record` (:376-481) requires `dir_calc_version == DIR_CALC_VERSION` **and** policy hash equality. Any change to the policy (families, thresholds, version) makes every in-flight Evening row fail Morning/Lab validation (`DIRECTION_VERSION_INVALID`, `DIRECTION_POLICY_HASH_INVALID`) and the finalizer's `direction_version_uniform` check. Release must not straddle an Evening→Morning pair, or validation must accept the prior version explicitly. It also rejects `final_direction ∉ {CALL,PUT}` (`DIRECTION_NOT_EXECUTABLE`) — so BULL/BEAR in `final_direction` would pass only after `normalise_side`, but the **flat-field vs record comparison** (:415-424) is on the raw uppercased strings: a record storing `CALL` with a flat field `BULL` fails `FLAT_FIELD_MISMATCH`. |
| `options_direction` / `canonical_direction` / `resolved_direction` / `primary_direction` | Options, EOD :1438-1442 | Morning :228-243, :1581, :1650-1674 (advisory sector alignment), :1925, :2521 (skew alignment D) ; lab_control `_side_from_value:1081-1093`, :1933, :2342, :4099 ; EIL :2559 ; EOD `_audit_side:1068-1074`, `_direction_arbitration:1076-1102`, slate skew guard :2940-2944 (warning only) | SIDE, G, D | Most consumers normalise BULL/BEAR→CALL/PUT (`_audit_side`, `_side_from_value`, `_handoff_side`), **but** set-literal checks `direction in {"CALL","PUT"}` do not: morning_gate.py:1581 (invalidation check → NOT_EVALUATED_NON_DIRECTIONAL), handoff_contract_audit.py:478/551/579/606 (invalidation audits silently skip → false green), lab_control :1933/:2342 (semantic-health counts skip → false green), EIL :2350 (missing-invalidation capital block skipped → **capital permission not withheld**), EOD :1621-1636 exit plan. |
| `structural_target` / `structural_target_source` | discovery :1766-1812, :1987-1988 (WYCKOFF / ASYMMETRY_GATE / PENDING_OI) | Options `_governed_structural_target:4545-4575` (Discovery → L1 far → 3R) ; descriptive handoff :149-152 (only if source=='WYCKOFF') ; `validate_direction_record` :452-467 (side check) ; EOD exit plan :1621-1625 (expected-move fallback target) ; lab_control various | A? no; G (side validity), S (R:R), D | Target currently exists only for one side. A symmetric design needs per-side targets; if a single `structural_target` is kept and the side flips, `validate_direction_record` returns `CALL_TARGET_NOT_ABOVE_SIGNAL`/`PUT_TARGET_NOT_BELOW_SIGNAL` → Lab BLOCK. |
| Invalidation fields: `governed_invalidation_spot/_source`, `wyckoff_validation_structural_invalidation_level`, `structural_stop(_source)`, `stop_loss`, `invalidation_price/_spot/_state` | discovery :1829-1840 (side-conditioned on `_candidate_direction`; None when UNRESOLVED), :1984-1986 ; Wyckoff validator | `contracts/thesis_geometry.select_directional_invalidation:32-82` (Options :4726; requires direction ∈ {CALL,PUT}, excludes ATR_FALLBACK) ; descriptive handoff :150-154 (only WYCKOFF_VALIDATION) ; EOD `_eod_candidate_status:1266-1270` (missing → EOD_DATA_INSUFFICIENT_REVIEW) ; EIL :2340-2360 (missing → capital NO) ; Morning :1581-1602 ; lab :4096-4110 (BLOCK) ; handoff audit :458-610 | G (only legitimate hard exclusion per R11), SIDE | `governed_invalidation_spot` is computed **only for the Discovery side**; direction-agnostic Discovery must publish **both** side-correct invalidations (or a per-geometry list), otherwise every row later assigned a side has `MISSING_AUTHORITATIVE_INVALIDATION` → Morning/Lab/EIL block. Legacy `stop_loss`/`structural_stop` ATR fallback is `current_price - dist` for all rows (discovery:1797-1800, long-only) — excluded by `thesis_geometry` today; must stay excluded. |
| `stop_loss` | discovery :1984 | Options :4604-4613 (initial parse, then overwritten by `_select_directional_invalidation`), thesis_geometry :61 (only when not ATR_FALLBACK) | SIDE | Long-biased ATR fallback; keep excluded. |
| `rr_underlying` / `rr` / `rr_source` | discovery :1964-1976, :2100-2107 (needs side target + side invalidation) | lab_control :469, :3655, :4244 (D) ; Options :10392-10394 (passthrough) ; EOD VAN_MERGE | D | Becomes None for UNRESOLVED; per-side R:R needed if displayed. |
| `wyckoff_mode`, `wyckoff_phase`, `current_phase`, `wyckoff_phase_bucket`, `wyckoff_mode_phase_key` | discovery :2033-2066 ; bucket via `_wyckoff_phase_to_broad_bucket:818` (maps A/B/C→ACCUMULATION, D/E→MARKUP regardless of mode — SOR-001 §2) | run_vanguard_from_packages :848-862, :907-915, :1100 (Vanguard state key dim 8) ; `scripts/actuarial_enrichment_pass.py:432-441` (cache key dim) ; EOD `_setup_type:326-329` ; physics `phase_text:192` ; Options `thesis_geometry_review` (reads `wyckoff_mode`, pinned by test_thesis_geometry_review_labels) ; descriptive handoff :110 (`forecast_structure_stage`) | S (actuarial match key), D, review label | Changing `wyckoff_phase_bucket` vocabulary (e.g. mode-aware DISTRIBUTION/MARKDOWN) changes actuarial state keys → match ladder EXACT/RELAXED/ANALOGUE mix, sample sizes, `edge_quality`, Options scope. v7 cache is keyed on the legacy bucket (SOR-001 §2, TEV build plan row 3). |
| `control_state` / `precor_control` | discovery :2036, :2113 | run_vanguard_from_packages :726-737 (**tier demotion only for BEARISH trend without BUYERS — asymmetric**) ; Options :4665 ; discovery `_reconcile_intent` | G (tier), A (intent) | Tier demotion rule is one-sided (no mirrored "BULLISH trend without SELLERS" demotion) — an existing bias that changes `tier` and hence Options scope (`ELIGIBLE_TIERS`, :9876). Removing/mirroring it changes population. |
| `tier` | discovery :1627-1640, :1979 ; Vanguard runner demotion :735 | Options scope `merged['tier'].isin(ELIGIBLE_TIERS)` :9876, DTE_MATRIX :4741, scoring :6881, print :7959 ; discovery output sort :2623-2632 | G (Options scope), S | Any tier change moves tickers in/out of Options scope. |
| `composite_score` / `composite_adjusted` / `win_probability` | discovery :1376 (`calculate_win_probability(wyckoff, crabel)`), :1990-1993, :2055 | Options :4614-4615, `ev_structural = win_prob*gain-(1-win_prob)*mark` :6802-6803 (legacy EV-like S), :8836-8845, :9336 ; lab_control :199, :3490, :4242 (D) | S, D | Direction-agnostic today (ticker-level). Keep unchanged to avoid regression; spec/addendum D5/D6 retire them eventually. |
| `edge_direction` / `layer2__edge_direction` / `vanguard_edge_direction` / `layer2__probability_direction` | Vanguard `EdgeDetector._determine_direction` (edge_detector.py:503-534, :707, :731) → main.py:523 → runner :1076 ; **Options re-writes all three** at :4643-4658 / :4894-4896 with its own fallback (raw_prob_up vs raw_prob_down) when Vanguard value ∉ {CALL,PUT} | `collect_resolution_evidence` (direction_governance.py:173-181, ACTUARIAL family) ; Options `_direction_arbitration_oi:407-455` ; EOD `_direction_arbitration:1076-1102` ; EIL `_direction_arbitration_row:2558-2585`, `_derive_signal_type_from_vanguard:2853-2867` (CURRENT_EDGE/FUTURE_EDGE require edge_dir ∈ {CALL,PUT}) → `momentum_tier` → EOD `_resolved_signal_type/_momentum_tier:742-760` ; physics `force_alignment` signs (physics_state_engine.py:200, :232-235) ; handoff_contract_audit.py:80 (WARN if absent) ; main.py `final_recommendation` string (`CALL_EDGE_STRONG_20D`) → Options scope `contains('EDGE_STRONG')` :9870 | A (legacy adapters), S, G (EIL signal type, arbitration `VWAP_CONFIRMATION_REQUIRED`), D | **HIGH.** (1) If Vanguard stops emitting it, Options **fabricates** one from `raw_prob_up_10d` vs `layer2__prob_down_10pct_20d/raw_prob_down_*` (:4652-4658) — a hidden direction writer that the design must remove or the "removal" is illusory. (2) EIL signal_type shifts CURRENT_EDGE→FUTURE_EDGE and FUTURE_EDGE→STRUCTURAL_MATCH for rows without CALL/PUT, changing momentum tier and EOD candidate status. (3) Evening thesis bucket (pretrade_focus) changes because call/put scores change. (4) Arbitration statuses change from AGREEMENT/CONFLICT to NO_PROBABILITY_OPINION. (5) If vocabulary becomes BULL/BEAR: `collect_resolution_evidence` normalises OK; EIL `edge_dir in {"CALL","PUT"}` does **not** (strict set) → signal_type regression; `edge_direction_label` in main.py:370 becomes `STAT`. |
| `edge_quality` / `layer2__edge_quality` / `bucket_edge_quality` / `legacy_edge_quality` | vanguard/main.py:244-366 (STRONG requires `expected_value_20d>=0.03` and `prob_up_10pct_20d>=0.40` — upside-only; promotion via bucket labels/probability_edge) | **Options scope** :9868-9870 (STRONG → scoped regardless of tier) ; Options `_is_strong_edge_probable:403`, verdict tier :470, macro overlay :389 (unused) ; descriptive handoff :125-127 (`forecast_legacy_statistical_context`, D) ; lab D | G (scope), S | Side-correcting edge_quality (BEAR measured on downside) changes which tickers enter Options scope; must be measured as a population diff, not assumed neutral. |
| `prob_up_*` (`prob_up_10pct_20d`, `prob_up_5pct_5d`, `prob_up_7pct_10d`), `raw_prob_up_*`, `raw_prob_down_*` | actuarial_query.py:708-713 (`>0`/`<0` returns; missing → **0.0**, :643-655) ; outcome columns upside-only | edge_detector `_determine_direction:515-518` ; main.py:249 ; Options :4639-4658 (direction fallback) ; phase2 baton required fields (run_vanguard_from_packages `PHASE2_REQUIRED_FLATTENED_FIELDS`; vanguard/tests/test_phase2_baton_validation.py) ; actuarial_enrichment_pass.py:205-215 ; EOD :251-256 ; lab :650, :3873 | A (via edge dir), S, V (baton) | Renaming/namespacing (SOR-001 S4) breaks baton validation and EOD/lab column lists; missing→0.0 default already violates R1. |
| `expected_value_20d` | actuarial outcomes (corrupted mean inputs per map S7/S8) | main.py:249-253 (edge_quality) ; Options `l2_ev:4638` ; runner :1072 | S, G (scope via edge_quality) | Legacy, not an EV (CLAUDE rule 5). Changing it changes Options scope. |
| `raw_prob_stop_hit` | actuarial_query.py:715 (`outcome_hit_5pct_down_before_10up` — false when +10 % never reached, SOR-001 §2) | baton fields ; EOD :258 ; lab D | D, V (baton) | Label is mis-defined; replacing requires baton/schema versioning. |
| `raw_expected_time_to_target` | actuarial_query.py:718 (median of `outcome_days_to_10pct` with 20 sentinel) | baton ; EOD :261 ; lab_control :650, :3873, :4327 (D) | D, V | 1,475/1,616 rows = 20 (sentinel). Namespace, don't silently change meaning. |
| `recommended_hold` / `recommended_hold_days` / `layer2__recommended_hold_days` | actuarial (fallback default 20 in 1,368/1,498 rows, ACK_DECISIONS D2) | Options `hold_days = l2_hold_days if >0 else dte_window[1]` :4775 ; scenario builders `_design_options_strategy` (pinned by test_vanguard_production_fixes:175) | S (DTE/hold) | D2 decided: thesis window 1–20; hold must not become thesis property. |
| `preferred_horizon` / `layer2__preferred_horizon` | actuarial_query.py:352-363 | not a match dimension (pinned test) ; EOD :247 ; morning :3833 ; horizon router | S (horizon/DTE) | Keep out of matching (test guard). |
| `layer1__auction_state`, `layer1__control__controller` | Vanguard L1 (1,480 PROFILE_CONTEXT_ONLY / 136 NOT_EVALUATED) | descriptive handoff :120-124 (control only if not PROFILE_CONTEXT_ONLY) ; edge_detector `_right_side_score:562-570`, `_determine_direction:505-513` | A (Vanguard vote), D | Currently neutral on all rows, so `_determine_direction` reduces to prob_up + trend + **CALL default**. |
| `directional_force` (PRICE_FLOW family) | `vanguard/physics_state_engine.calculate_market_physics` (:207-218; returns, trend, VWAP — same OHLC as Discovery) called by runner :1246 | `collect_resolution_evidence:211-216` (\|force\|≥5) ; lab :577, :3799 ; handoff_contract :89 | A (resolution vote), D | Physics is retired by addendum D4 yet counts as an "independent" family; it is OHLC-correlated with Discovery structure (SOR-001 §3.3: correlated families, not independent votes). |
| STRANGLE / UNRESOLVED handling | discovery via table (TRANSITION+MIXED → STRANGLE; WAIT/missing/conflict → UNRESOLVED) | Options: stand-down, `NO_DIRECTIONAL_STRATEGY`, no chain (:4811-4819, :7950-7957, :9949) ; `_ev3_direction_fields:5109-5137` (NON_DIRECTIONAL/UNRESOLVED) ; `thesis_geometry_review` → `NOT_APPLICABLE_NON_DIRECTIONAL` ; EOD `_candidate_direction` → UNRESOLVED ; EOD/EIL invalidation rules skip non-directional (test_missing_invalidation:62) ; Morning `NO_GO_DIRECTION`/`DIRECTION_INTEGRITY_FAILED` (test_direction_governance_contract:290) ; Lab: kept visible, `lab_tradeable=False`, BLOCKED, `lab_hidden_by_default` not True (test_lab_strangle_direction) ; descriptive packet `DIRECTION_NOT_DIRECTIONAL` | G (no expression), D (visible) | If the design removes STRANGLE: `normalise_direction` still maps STRADDLE/MIXED/TRANSITION/NON_DIRECTIONAL → STRANGLE (thesis_direction.py:94-99), the Lab strangle policy/tests and `_ev3_direction_fields` depend on it. More UNRESOLVED rows ⇒ fewer chain requests, fewer Options/EOD/Lab rows with contracts: a coverage change that must be reported as a population diff (replay of `20260926_173730`), not claimed as neutral. |

### A.2 How Options Intelligence selects contract side
1. `parse_structural_context` → `direction = direction_record['final_direction']` (:4718).
2. Invalidation re-resolved on that side: `_select_directional_invalidation(row, direction, entry)` (:4726; thesis_geometry.py:32-82).
3. Target: `_governed_structural_target(direction, …)` Discovery → L1 far → 3R fallback (:4545-4575) — 3R is a hurdle, not a structural target (spec §9, map S9).
4. Guard: `direction ∉ GOVERNED_DIRECTED_SIDES` → stand-down, chain never fetched (:7953; worklist :9949).
5. `select_best_contract` filters `right=='C'` for CALL, `'P'` for PUT (:5256-5263); single winner (spec §26 forbids single-contract pre-selection; TEV §5.1).
6. EOD re-checks contract side vs GDR and clears wrong-side contracts (`_contract_side`, `_invalidate_direction_dependent_contract`, EOD :1374-1466); `validate_direction_record` rejects `SELECTED_CONTRACT_DIRECTION_MISMATCH` (:475-480).

### A.3 `resolve_governed_direction` evidence requirement
- `MIN_EVIDENCE_FAMILIES = 2`, `MIN_WINNING_SHARE = 0.60`, `MIN_DIRECTION_MARGIN = 0.20` (direction_governance.py:32-34); only when `governed ∈ {STRANGLE, UNRESOLVED}` **and** `allow_non_directional_resolution` (:291-296). A directed Discovery side is never overwritten (`test_confirmed_structure_cannot_be_overwritten_by_other_evidence`).
- Families (policy hash :235): **ACTUARIAL** (Vanguard edge direction aliases, :173-181), **CATALYST** (strict provenance, :183-208), **PRICE_FLOW** (`directional_force`, :211-216), **RELATIVE_STRENGTH** (`relative_strength_20d`/`sector_relative_strength_20d`/`rs_20d`, :218-227).
- Conflicts with governing docs: spec A.2 and addendum §6.4 D2 **retire catalyst direction evidence and `relative_strength_20d`** ("Not inputs to any context"); addendum D4 retires physics (source of `directional_force`). No staged producer of `relative_strength_20d` exists. So the only live families are ACTUARIAL (Vanguard) and PRICE_FLOW (Vanguard runner physics, OHLC-derived). If Vanguard's CALL default is removed, the ACTUARIAL vote disappears on neutral rows; with PRICE_FLOW alone, **no row can satisfy two families** → legacy-adapter paths resolve nothing.
- Implementation record vs code drift: `docs/DIRECTION_GOVERNANCE_IMPLEMENTATION_20260827.md` says "Options Intelligence is the only stage that can commit the governed direction" (dir_v1.0.0); code is `dir_v1.2.0` where Discovery commits (`DISCOVERY_GOVERNED`) and Options only records. TEV-001 §2 describes `OPTIONS_INTELLIGENCE` default authority — true only of the default parameter.

### A.4 Highest-risk consumers (ranked)
1. **`domain/descriptive_forecast_handoff.py` + orchestrator :6015-6024** — exact CALL/PUT dict and `duplicate ticker` ValueError inside a *critical* Evening step: vocabulary change → all rows DATA_INSUFFICIENT; per-side rows → Evening abort.
2. **Options `parse_structural_context` :4686-4722** — `DISCOVERY_GOVERNED` disables resolution; if Discovery emits no side, nothing ever resolves; and :4652-4658 fabricates Vanguard direction when absent.
3. **`validate_direction_record` / morning_handoff_finalizer uniform version** — any policy/version change fails in-flight rows; raw-string flat-field comparison vs normalised side.
4. **Strict `in {"CALL","PUT"}` set checks** (EIL :2350 capital block, handoff_contract_audit :478-606, lab_control :1933/:2342, morning :1581, EIL :2864-2866 signal_type) — BULL/BEAR leaks produce *false-green audits and skipped capital blocks*, not crashes.
5. **Vanguard `edge_quality`/`final_recommendation` → Options scope :9864-9877** and **tier demotion :726-737** — side-correcting Vanguard changes the scoped population.
6. **`domain/pretrade_focus.project_evening_thesis`** (not staged) — Evening bucket depends on call/put scores and PRICE_FLOW evidence JSON.
7. **Actuarial key (`wyckoff_phase_bucket`, `macro_regime`)** — vocabulary change alters matching; `macro_regime` is a state-key dimension (runner :1101; enrichment pass :437-441) — existing macro-in-scoring violation of CLAUDE rule 6 / spec §26.

---

## TASK B — Existing tests

Classification: **GUARD** = must stay green unchanged · **GUARD*** = keep the business rule, update vocabulary/fixture only · **CHANGE** = must change under the design (with reason) · **BIAS** = currently encodes a bias or a retired rule.

| Test (file:line) | Pins | Class | Notes under planned design |
|---|---|---|---|
| test_direction_governance_contract.py:31 direct launch | script importability | GUARD | — |
| :61 `test_discovery_ambiguity_never_defaults_to_call` | ambiguity → UNRESOLVED, never CALL | GUARD | Core anti-bias guard; add BEAR/BULL-vocabulary twin. |
| :66 `test_structural_direction_table_is_closed_and_symmetric` | PreCOR table incl. TRANSITION+MIXED→STRANGLE | GUARD* | If STRANGLE is removed/renamed, update the one assertion; keep symmetry. |
| :75 `test_non_directional_resolution_requires_two_independent_families` | 2 families; uses **CATALYST** family | CHANGE / BIAS(retired) | Encodes catalyst as admissible direction evidence, which spec A.2/addendum D2 retire. Keep "one family never resolves"; replace the second family with a spec-admissible, side-correct C4 family. |
| :96 `test_resolution_policy_is_mirror_symmetric` | CALL/PUT mirror | GUARD* | Same catalyst dependency. |
| :123 `test_confirmed_structure_cannot_be_overwritten_by_other_evidence` | no silent flip | GUARD | Essential for "direction only by evidence, no flip". |
| :136, :150 catalyst exclusion | placeholder/unsourced catalyst excluded | GUARD (until catalyst family removed; then CHANGE to "catalyst never a family") |
| :166 hash/flat-field enforcement | record integrity | GUARD | |
| :183 Options success & stand-down both publish lineage | lineage parity | GUARD | |
| :204 target/invalidation/contract-side enforcement | side geometry | GUARD | Add BEAR/BULL vocabulary cases. |
| :220 `test_options_stage_leaves_wait_unresolved_without_contract_strategy` | WAIT→UNRESOLVED even with Vanguard CALL | GUARD | Proves one Vanguard vote cannot resolve. |
| :238 unresolved suppresses chain | no chain for non-directional | GUARD | |
| :260 EOD consumes GDR, invalidates wrong-side contract | EOD side guard | GUARD | |
| :279 execution gate blocks invalid lineage | (module not staged) | GUARD | |
| :290 Morning routes UNRESOLVED to stand-down | Morning | GUARD | |
| :312 version explicit | `DIR_CALC_VERSION` | GUARD* | Version bump expected; test stays generic. |
| test_ddd_thesis_direction.py:53 legacy vocabulary adapter | NON_DIRECTIONAL→STRANGLE, table | GUARD* | |
| :60, :76 (mirror-symmetric transitions), :80, :87, :103 continuity/no reversal | FrozenThesis semantics | GUARD | Continuity guard is the regression net for "Vanguard cannot flip". |
| test_direction_geometry_semantic_repairs.py:26 structural intent fills unresolved hint | Discovery table | CHANGE (if Discovery stops assigning) / GUARD (if kept as candidate evidence) | Design decides whether this remains Discovery's job. |
| :33 conflict fails closed, never flips | UNRESOLVED on conflict | GUARD | |
| :41 PUT invalidation from Wyckoff validator | side-aware stop | GUARD | |
| :55 ATR fallback never governed | no long-biased fallback | GUARD | |
| :67 `test_options_preserves_frozen_discovery_direction_and_rebuilds_put_geometry` | Options cannot flip DISCOVERY_GOVERNED PUT | GUARD* | If authority moves from Discovery to a C5/evidence owner, keep the invariant ("downstream cannot flip the owner's side"), update the authority literal. |
| :93, :99, :109, :120 | missingness/health/horizon | GUARD | |
| test_descriptive_forecast_handoff.py:29 | CALL→BULL projection, no option fields | GUARD* | Fixture uses `direction: CALL`; update if Discovery vocabulary changes. |
| :47 | missing target visible; non-governed → DATA_INSUFFICIENT | GUARD | |
| :63 `duplicate ticker` fails closed | one row/ticker | GUARD (constrains design) | Forbids a two-row-per-ticker BULL/BEAR emission unless the packet contract is versioned. |
| :77, :100, :131, :201 | immutability, no legacy EV in C5/C8, two-state display | GUARD | |
| test_avs_tev001_ticker_forecast.py (all 4) | C5 has no option vocabulary; BULL→CALL only at boundary; wrong-side rejected; mixed evidence recorded | GUARD | Directly encodes TEV-001 S1. |
| test_avs_tev001_structural_cohort.py (5) | option-neutral research start; pending target ≠ move; wrong-side counted; stale excluded | GUARD | Module `audit/avs_tev001_structural_cohort.py` not staged. |
| test_avs_sor001_mode_phase_identity.py (3) | mode×phase key; no fill | GUARD | |
| test_avs_sor001_wyckoff_range.py (3) | prior range excludes event bar | GUARD | |
| test_avs_sor001_feature_window.py (2) | no future bar, late revision rewound | GUARD (as-of) | |
| test_avs_sor001_crabel_fusion_contract.py (3) | typed compression state | GUARD | |
| test_wyckoff_phase_validator.py (4) | phase validation, invalidation level 94.5 | GUARD | |
| test_thesis_geometry_review_labels.py (7) | CALL-in-DISTRIBUTION / PUT-in-ACCUMULATION labelled, not gated; non-directional N/A | GUARD* | Under symmetric candidates the contradiction should become rarer; keep "label, never invent". |
| test_missing_invalidation_authority_withheld.py (4) | missing invalidation → None & capital NO; non-directional not penalised | GUARD | Uses CALL; add BULL/BEAR vocabulary to catch strict-set leaks. |
| test_evening_thesis_decision.py:53-86 | Evening bucket needs aligned PRICE_FLOW evidence; opposing call/put scores → review | CHANGE (likely) | Depends on `direction_resolution_*` produced by the governance evidence collector; if families change (Vanguard side vote removed/replaced), fixtures and possibly thresholds change. Characterise first. |
| :88-247 | frozen Evening bucket, quote lineage, Morning non-rewrite | GUARD | |
| test_lab_strangle_direction.py (9) | STRANGLE never shown as CALL/PUT; visible; blocked; policy cannot delete | GUARD* | If STRANGLE retires, rewrite as "non-directional/UNRESOLVED stays visible, blocked, never collapsed to a leg". Lab module not staged. |
| test_directional_bias_fixes.py:73-160 put-gate advisory-only | macro never gates | GUARD | Protects CLAUDE rule 6. |
| :169 CALL not tagged PUT_GATE, :190 status precedence | | GUARD | |
| :229, :248, :277 Wyckoff momentum override | **C/D→B only when 20-d ROC>30 % and price>EMA50** (WyckoffEngine_3101_v2.py:153-165) | **BIAS** | Upside-only rule with no mirrored downside rule (Invariant D). Keep until characterised; a symmetric design must either mirror or remove it, and these tests then change. |
| :334-362 slate guard | conflict haircut | GUARD | |
| :399-437 ATR drift gate | symmetric CALL/PUT adverse drift (test-local inline copy) | GUARD | |
| test_vanguard_production_fixes.py:106 | preferred_horizon not a match dim; **requires `outcome_hit_10pct_up` column** | GUARD* | Upside column requirement is fine; add mirrored downside columns, do not delete the upside one. |
| :114 match ladder momentum tier | | GUARD | |
| :150, :160 edge detection with `_auction()` BUYERS/UP | has_edge | GUARD* | Fixture is bullish-only; add bearish mirror. No test pins `_determine_direction` or its CALL default — **characterisation test missing** (required by CLAUDE.md before change). |
| :175 `_design_options_strategy("CALL", …)` dte==10 | hold days → DTE | GUARD* | Legacy scenario builder; CALL-only fixture. |
| :184 adapter preserves trend | | GUARD | |
| test_vanguard_reference_input_p2.py (4) | package/manifest byte parity on run `20260926_173730` | GUARD | Detects any unintended Discovery/package change; skipped when run absent. |
| test_package_free_evening_p4.py (9) | manifest vs packages mode | GUARD | |
| test_handoff_contract.py:50 Discovery CALL beats EIL PUT | one owner | GUARD | |
| other handoff_contract tests | merge semantics | GUARD | |
| test_actuarial_cache_v7_contract.py:108 `never_crosses_direction` | trend_direction never fuzzy-matched across sides | GUARD | |
| other v7 cache/database tests | maturity, no look-ahead, null pending labels, fail-closed duplicates | GUARD (as-of) | |
| vanguard/tests/test_actuarial_match_ladder.py:154, :177 | shrinkage uses upside target column; UNKNOWN → baseline & zero edge | GUARD* | Target column upside-only; BEAR mirror needed. UNKNOWN→baseline is a base-rate substitution (acceptable as no-skill prior, but label it). |
| vanguard/tests/test_phase2_baton_validation.py (6) | 30 required `layer2__*` baton fields incl. `raw_prob_stop_hit`, `raw_expected_time_to_target` | GUARD* | Renaming/namespacing these (SOR S4) needs a versioned baton, not deletion. |
| vanguard/tests/test_vanguard_contract.py (5) | input validation | GUARD | |

Tests that currently **encode a bias or retired rule**: Wyckoff momentum override trio (upside-only); governance catalyst-family tests (retired evidence); bullish-only Vanguard fixtures (not bias per se, but no mirror); `test_evening_thesis_decision` depends on PRICE_FLOW (retired physics) as the aligned evidence family. **No test asserts the CALL default** — its removal needs a new characterisation test first.

Missing regression guards the design should add (failing-first):
1. Descriptive packet with BULL/BEAR vocabulary and with UNRESOLVED; no Evening abort.
2. Strict-set consumers (EIL :2350, handoff audit, lab health, morning :1581) given BULL/BEAR tokens.
3. `normalise_direction` on combined tokens (`BULL|BEAR`, `BULL_OR_BEAR`) must not yield PUT.
4. Options with Vanguard edge absent must not fabricate a side (:4652-4658).
5. Vanguard `_determine_direction` characterisation (neutral → CALL today) then mirror test (neutral → NONE).
6. Mirrored price series ⇒ mirrored Vanguard outcome labels (note 01 validation 4; map S7 invariant).
7. In-flight Evening rows validated by Morning across a `DIR_CALC_VERSION` change.
8. Population diff on `20260926_173730`: counts of CALL/PUT/UNRESOLVED/STRANGLE, Options scope, chain requests, EOD candidates, Lab rows.

---

## TASK C — Governing rules (verbatim-anchored)

### C.1 Authority and process
- CLAUDE.md §"Before designing" 2: "Authority order: business decisions (ACK) → specification → method notes 01–07 → … ADDENDUM → … PIPELINE_MAP… → code. A lower document may add detail, never contradict a higher one. Conflicts on method correctness go to ACK."
- CLAUDE.md 4: "Enhance the existing pipeline; do not rebuild it beside itself. Fix existing modules in place, test-first, one defect at a time (characterise → failing business-rule test → minimal change → acceptance against reality with the outcome scorer)." (ACK D1, 17 Sep 2026)
- CLAUDE.md Working rules: "every pipeline change starts with a failing test that states the business rule in domain language; legacy behaviour being changed is pinned by a characterisation test first. A fix is accepted only when the outcome scorer shows the targeted metric moving on history and forward sessions." ; "No pipeline code changes without an approved root cause and design." ; "Configuration values (thresholds, bands, tolerances) live in versioned configuration (spec Appendix B), never as literals in domain code." (note: `MIN_EVIDENCE_FAMILIES/0.60/0.20` are literals in direction_governance.py:32-34.)
- CLAUDE.md 5: "No logic gains decision authority without passing gates G1–G4 and spec §24."
- CLAUDE.md 6: "Macro and event guards are display-only for manual review; they never influence a gate, score or rank."
- SOR-001 §6: "domain definition → failing boundary and counterexample tests → minimal implementation → component tests → upstream/downstream contract tests → offline chronological replay → integrated regression → evidence receipt. Commit is last". TEV build plan §5 same; "No grade 0/1/2 defect may remain for shipment".

### C.2 Design rules R1–R12 (END_TO_END_PIPELINE_MAP §2)
R1 "Missing is never neutral." · R2 "One owner per fact… downstream reads, never rewrites." · R3 "Units and vocabulary in the name… one enum per concept end to end." · R4 "Decide before you depend… no read-backs (no horizon from contract DTE)." · R5 "Authority is explicit… non-authoritative outputs are never read by valuation, ranking or execution." · R6 "Labels say what was measured." · R7 "Reproducible inputs… same inputs → identical outputs." · R8 "Clean release." · R9 "Fewer, owned components." · R10 "Measured against reality." · R11 "**Rank, don't gate.** Hard exclusions only for integrity, eligibility thresholds, missing invalidation and tradeability; direction state is descriptive." (enforced by test "OPPOSED thesis is valued and ranked" — not present in staged tests) · R12 "Fresh or flagged."

### C.3 Gates G1–G4 and §24
- G1–G4 definitions live in `OBJECTIVE_ASSURANCE_ASSESSMENT.md` (**not staged**). Staged references: README "design-adequacy gate (G2)"; note 06 header "Gates: G3 Verification, G4 Validation"; notes 01/02 "Validation (gate G4; replication R4)"; note 06 §7 "Acceptance protocol (gate G4)": pre-register; walk-forward with costs through production services; forward shadow ≥60 sessions (to agree); independent review; authority only if historical and forward both pass. G1 is not defined anywhere staged — obtain before citing.
- Spec §24: "BUILD → SHADOW / NON-AUTHORITATIVE → REPLICATION (R1, R4) → WALK-FORWARD AND FORWARD SHADOW VALIDATION → AUTHORITY"; "Every rule and model carries an explicit authority state: IMPLEMENTED_FOR_REPLICATION, NOT_YET_VALIDATED_FOR_PRODUCTION_AUTHORITY, SHADOW, AUTHORITATIVE". Invariant G: "No model, score or signal influences a gate, a valuation or a rank until it has passed the validation progression in §24."

### C.4 Direction ownership
- Spec §3 Invariant A table: "Candidate geometry — Market Structure Context"; "Probability / timing — Evidence Context"; "**Direction — Thesis Context**"; "A downstream context may reject an upstream object … It may not rewrite the upstream object's meaning."
- Spec §7 Output aggregate `StructureAssessment` "**must not contain: final trade direction; selected geometry; contract; EV; rank; BUY/SELL action; macro regime or macro score**". §7: "Market Structure proposes one or more candidate geometries **for each candidate direction**… It does not choose between them — the Thesis does (§9)."
- Spec §25: "Direction | Thesis | Forbidden" (downstream mutation).
- Spec §9 Direction behaviour: "Evidence opposing the proposed structural direction must not automatically flip the direction." Note 02: "Never auto-flip direction. A structurally proposed opposite direction is its own candidate geometry."
- Map S8: "No context produces TRADE / NO_EDGE verdicts or direction guesses from Vanguard. Direction comes from C3 candidate geometries and is assessed by C4/C5." "Retire: `_determine_direction` CALL default". Invariant: "mirrored inputs give mirrored outputs."
- Map S5: "direction table (Precor/Fusion/Wyckoff) with UNRESOLVED on conflict (correct)".
- TEV-001 §3: C5 owns "`TickerForecast`: BULL/BEAR/NEUTRAL_RANGE…"; C5 "May not: Name CALL/PUT…"; C6 "for BULL, long calls; for BEAR, long puts … May not: Change C5 direction". §1: "A changed underlying direction is a new thesis version, not a silent contract-side swap."
- SOR-001 §3: C3 Discovery owns "candidate geometry. **No numeric edge or option identity.**"; C3 auction (Vanguard L1) "Can confirm, oppose or leave Discovery unresolved; cannot rewrite it."; C4 (Vanguard L2) "No option EV or side selection."; C5 "Reconcile C3 and C4 into BULL/BEAR/NEUTRAL_RANGE or descriptive uncertainty".

### C.5 Explicit statements on CALL/PUT vs BULL/BEAR
- Spec §7 geometry: "`direction BULL | BEAR`". Addendum §CandidateGeometry: "Direction ∈ {BULL, BEAR}".
- Spec §26: "Thesis says BULL → execution silently converts it to PUT" (forbidden).
- TEV-001 §3: "No `CALL`, `PUT`, OCC symbol, premium, delta, spread, OI or `selected_contract` belongs in this contract. The existing `FrozenThesis` and CALL/PUT CSV fields remain behind a **versioned anti-corruption adapter** during migration; `BULL→CALL` and `BEAR→PUT` is a one-way C5→C6 mapping. Do not delete legacy fields or alter historical artefacts in place."
- SOR-001 §1: "This is not a CALL/PUT recommendation." §5: "C6 preserves… BULL→CALL, BEAR→PUT and neutral→no directional expression"; "A neutral or mixed signal cannot default to CALL. The C5 forecast has no `CALL`, `PUT`, OCC symbol, premium or option EV."; "Bearish probability is never derived from an upward-target column." §2 row 7: "Never infer a PUT's edge from an upward target metric or default no-direction to CALL."
- Note 02 pitfalls: "Default to CALL on neutral | `_determine_direction`".
- None of the documents states that **Discovery** must emit BULL/BEAR; they state C3 proposes geometries per candidate direction (BULL|BEAR) and does not choose.

### C.6 direction_state vocabulary and "rank don't gate"
- Spec §9: "Possible states: SUPPORTED, OPPOSED, UNSUPPORTED, INSUFFICIENT_EVIDENCE". "**Direction state is descriptive, not a gate.** A complete thesis with usable evidence flows to expression generation and valuation whether its state is SUPPORTED, UNSUPPORTED or OPPOSED… The one legitimate exception is INSUFFICIENT_EVIDENCE… published, recorded in the ledger as NOT_VALUED… not sent to expression generation, and its underlying outcome still matures." Note 02 thresholds: SUPPORTED if expectancy lower bound > 0; OPPOSED if upper bound < 0; UNSUPPORTED if straddles 0; INSUFFICIENT_EVIDENCE if packet null.
- Spec A.6 S1 correction; §21 "Selected geometry UNSUPPORTED or OPPOSED → thesis flows to expressions and valuation"; §26 "Evidence OPPOSED or UNSUPPORTED → thesis dropped instead of valued and ranked" forbidden. Addendum D1: "Direction conflict — Not a gate."
- TEV-001 adds `forecast_state` (QUANTIFIED/DESCRIPTIVE_ONLY/DATA_INSUFFICIENT/INVALIDATED) and `estimation_reliability_state` (5 values); `NEUTRAL_RANGE` "requires sufficient support **and** a calibrated interval… failure to find a BULL/BEAR effect alone is only UNSUPPORTED/wide evidence, not confident neutrality." TEV build plan §4 **cuts** `NEUTRAL_RANGE` as a positive prediction and reviewer 3.1 notes the extra vocabulary is not required by the spec.
- The design's proposed "UNRESOLVED" is **not** a spec direction_state; map it explicitly (e.g. geometry-level INSUFFICIENT_EVIDENCE / thesis NOT_VALUED) and keep the legacy option-side token `UNRESOLVED` separate (R3).

### C.7 Candidate geometries per direction
- Spec §7: fields `geometry_id, direction BULL|BEAR, reference_price, target_state LEVEL|NONE, target_price, invalidation_price (required; correct side), target_distance_sigma, invalidation_distance_sigma, derivation_rule, formula_version`. "No artificial target (such as a fixed R-multiple)". "A geometry without a valid invalidation level is not proposed." "Distances are expressed in volatility units".
- Spec §9 R-H selection: highest lower-bound expectancy in σ; "Choosing by probability alone is forbidden"; authority `IMPLEMENTED_FOR_REPLICATION / NOT_YET_VALIDATED_FOR_PRODUCTION_AUTHORITY` until R4. Map S9 invariant: "BULL invalidation < reference < target (mirrored BEAR)".

### C.8 Symmetry
- Spec Invariant D: "BEAR theses use mirrored evidence, mirrored barriers and mirrored valuation. No statistic, threshold or payoff may be computed upside-only and reused for the downside." Note 01: "BEAR observations use mirrored barriers and mirrored returns"; validation 4 "mirrored price series give mirrored BULL/BEAR packets". Map S7 invariant "CALL/PUT statistics mirror". SOR-001 §5 "For both BULL and BEAR geometry, target-first + adverse-first + observed event-free… reconcile."

### C.9 Thesis window 1–20
- Spec §9 "1–20 trading-session opportunity window"; "Day 20 is the maximum planned opportunity horizon, not the expected exit day"; "There is no fixed holding bucket (no 5 / 10 / 20 choice)". ACK_DECISIONS D2 (decided 18 Sep): "Thesis window 1–20 sessions, capped per contract by its last exit session." D1 (decided): C3(b) reaffirmed; hard DTE guard retired. SOR-001 §3.4: longer horizons "do not silently change the signed-off C5/C6/C8 contract". Spec A.3 R-G: "5/10/20 retained only as volatility forecast checkpoints."

### C.10 Missing is never neutral
- Spec Invariant B ("if evidence_missing: return InsufficientEvidence(reason=...)"; "A failure to compute must never be shown as a neutral or passing value"); §26 "Evidence returns no match → downstream substitutes 52%". Note 01 "never a default probability". Existing violations relevant here: `_determine_direction` neutral→CALL; `_prob_up/_prob_down` missing→0.0 (actuarial_query.py:643-655); `raw_*` defaults 0.0 (:695-718); Discovery `regime_align = 0.5` (:1591); Options fallback direction fabrication (:4652-4658).

### C.11 Macro display-only
- CLAUDE rule 6; spec §7 (StructureAssessment must not contain macro), §26 "Macro context → influences any gate, score, floor or rank"; A.2 "macro removed from decisions"; addendum D10 "Display-only… no gate, floor, score or rank (ACK)". Existing violations touching this design: `macro_regime` is an actuarial state-key dimension (runner :1093-1101 debug_signature dim 9; actuarial_enrichment_pass STATE_COLS :437-441, fallback drops it first); physics `force_alignment` uses macro label (:228-231); Vanguard edge gates with macro regime floors (map S8).

### C.12 Point-in-time / as-of
- Spec Invariant E ("only what was observable by the evidence session… resolved paths as events at their touch session; unresolved right-censored"; AM-1). Invariant F. Note 07 capture rules 1-7 ("readers request as_of explicitly"; "'Latest' files are views… never inputs to a decision"). Note 06 §3 (point-in-time, no look-ahead, purging and embargo, walk-forward, same code path). SOR-001 §4.5: "**Hard prerequisite** … every versioned historical query requires an explicit `as_of` cut, with no silent default… `ActuarialQueryEngine` currently has no such filter… No unfiltered legacy result may enter the new estimator." TEV §4.1: purge/embargo ≥ 20-session label window.

### C.13 Support floors and estimator
- Spec §8: discrete-time competing risks (Aalen–Johansen or equivalent), shrinkage to pooled states, `n_eff` in independent time blocks, block bootstrap, AMBIGUOUS counted as stop-first, BEAR mirrored, base sample = point-in-time market universe (own outcomes only calibration).
- TEV-001 §4.1 (signed off, "provisional until S0"): pooled numeric baseline ≥ **30 non-overlapping 20-session market-date blocks, 200 matured starts, 20 tickers, 4 sectors**; local/interaction ≥ **12 blocks, 40 starts**; 95 % interval wider than **0.40** ⇒ `POOLED_WIDE`; `n_eff/(n_eff+kappa)` with kappa frozen on earlier data; "do not lower floors merely to obtain forecasts". SOR-001 §3.3 restates them. TEV build plan §3.2(4): feasibility was measured on the wrong sample (195 own-run starts); spec §8 base sample is the market universe.

### C.14 Other rules the design must respect
- Spec §26 "Lab → recomputes rank or priority"; TEV §6 ticker-first Lab, no-option forecasts stay visible.
- Addendum D2: "Catalyst direction evidence and relative_strength_20d retired (ACK)." D4: "Physics retired." D9 (ACK_DECISIONS, undecided): composite signal no direction authority.
- ACK_DECISIONS D3–D9 remain **undecided**; D8 recommends V1 = long calls/puts + long shares.

---

## Conflicts between documents (direction-relevant)

| # | Conflict | Documents | Why it matters for this design |
|---|---|---|---|
| K1 | Who owns direction: spec says **Thesis (C5)** and StructureAssessment must not contain final direction; code/doc make **Discovery** the governed owner (`DISCOVERY_GOVERNED`, dir_v1.2.0); DIRECTION_GOVERNANCE_IMPLEMENTATION (27 Aug) says **Options** is sole committer; TEV-001 §2 describes Options default authority. | spec §3A/§7/§25 vs discovery:2082, Options :4686-4694, docs/DIRECTION_GOVERNANCE_IMPLEMENTATION | Design aligns code with the spec (C3 proposes, C5 decides); the implementation record and flag literal must be superseded explicitly. |
| K2 | Macro inside forecast: TEV-001 §4 item 1 "amends the older C0–C14 map… macro may condition C5's forecast"; SOR-001 §4.4 macro changes scenarios/uncertainty — vs spec §26/§7/A.2, addendum D10, CLAUDE rule 6. TEV build plan §4 **cuts** macro inside C4 pending ACK. | TEV-001, SOR-001 vs spec | A solution design cannot amend the governing spec; any direction evidence must exclude macro unless ACK amends spec (A.7 pattern). |
| K3 | Evidence families: code admits CATALYST and RELATIVE_STRENGTH and PRICE_FLOW (physics); spec A.2 / addendum D2/D4 retire them. | direction_governance.py:235 vs spec A.2, addendum §6.4 | "Direction assigned only by evidence" must use C4 packets per geometry, not the legacy family vote. |
| K4 | Direction-state vocabulary: spec 4-state; TEV adds forecast_state/reliability/NEUTRAL_RANGE; build plan cuts NEUTRAL_RANGE; code uses CALL/PUT/STRANGLE/UNRESOLVED/NON_DIRECTIONAL (two literals for non-directional). | spec §9, TEV §3, build plan §4, thesis_direction.py | R3 "one enum per concept"; design must publish a mapping table. |
| K5 | Block definition for `n_eff`: note 01 "independent time blocks (e.g. distinct weeks)"; TEV §4.1 "the older design's generic week-block bootstrap is insufficient"; ≥ 20-session blocks. | note 01 vs TEV §4.1 | Method-correctness conflict → escalate to ACK per CLAUDE rule 2. |
| K6 | Support floors not in the spec (reviewer 3.1); TEV is signed off with them as provisional. | TEV §4.1 vs build plan §3.1 | Cite as signed-off-but-provisional; S0 feasibility on the market universe. |
| K7 | Expression scope: spec §10/Q1 (calls, puts, verticals, long/short shares) vs TEV (long calls/puts only) vs ACK_DECISIONS D8 (undecided). | spec vs TEV | BEAR→short shares in spec; not in TEV. Record scope in configuration. |
| K8 | Migration style: spec document control "strangler migration"; CLAUDE rule 4 (ACK D1 17 Sep) "fix existing modules in place". | spec vs CLAUDE.md | CLAUDE/ACK decision is higher; spec text not amended. |
| K9 | 5/10/20 horizons persist in Options (DTE_MATRIX, horizon buckets 1_5d/6_10d/11_20d) and actuarial `preferred_horizon`, vs spec §9 / D2 decided. | code vs spec | Not changed by this design; must not be reintroduced into the thesis. |
| K10 | "PROFILE_CONTEXT_ONLY" L1 cannot be control (SOR-001 §5) — yet `_determine_direction` and `_right_side_score` consume L1 control/migration. | SOR-001 vs edge_detector | Removing Vanguard's own vote is consistent with SOR-001; keep L1 as context. |

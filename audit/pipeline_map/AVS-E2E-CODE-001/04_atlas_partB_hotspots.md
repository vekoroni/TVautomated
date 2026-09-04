# 04 — Atlas Part B: hotspot files

**Document:** AVS-E2E-CODE-001 · Lane B
**Scope:** the 20 files listed in `_tooling/lane_B_hotspots.txt`.
**Prior under test:** `audit/pipeline_map/AVSHUNTER_END_TO_END_DATA_LOGIC_AND_MONETISATION_REPORT_20260831.md`
(AVS-E2E-DATA-LOGIC-001). Treated as a prior to be verified, never as truth.
**Execution order source:** `03_execution_order.md`.

Tags: **OBSERVED** = read directly in code. **INFERRED** = deduced; basis and
confidence stated. Where a claim has a measurable consequence it carries
`NEEDS_MEASUREMENT:` with the query that would settle it.

---

### scripts/avshunter_options_intelligence.py

**Classification:** ORCHESTRATED analytic stage (8,836 lines).
**Real execution position:** stage 18 of 51, evening. Invoked by
`intelligent_orchestrator.py::evening_workflow` at L4197 via `run_options_intelligence`
(script path resolved from `OrchestratorConfig` L437). [OBSERVED `03_execution_order.md` §2]
**Task in the process:** Reads the merged Vanguard + Discovery signal row, parses it
into a structural context (`parse_structural_context`), derives direction through the
direction-governance contract, selects an exact option contract from a fetched chain,
computes trade economics, builds the EV3 handoff, builds the governed options-liquidity
lifecycle handoff for that exact contract, and writes the options intelligence CSVs
that every later stage consumes.

**Entry points:** `run_options_layer` (L8113); `parse_structural_context` (L3778);
`_options_liquidity_lifecycle_fields` (L4507); `_ev3_handoff_fields` (L4085);
`_resolve_asof_date` (L6384). Module `__main__` present.
**Imports (production):** `contracts.options_liquidity_lifecycle` (L122–124:
`LifecycleInputs`, `evaluate_options_liquidity_lifecycle`);
`contracts.direction_governance.resolve_governed_direction` (used L3886);
`canonical_data.OptionLiquidityLifecycleStore` (imported inline L8223, instantiated L8293).
· **Imported by:** `tests/test_ev3_options_handoff.py:195` calls
`oi._options_liquidity_lifecycle_fields` directly.
· **Broken/retired imports:** NONE observed.

**Inputs**
— Files/tables read: option chain via `fetch_chain(ticker)` (L6491); merged
Vanguard/Discovery CSV supplied by the runner (`run_options_layer` L8113, merge at L8173).
— Upstream fields consumed (with fallback chains):
`stop_loss` (L3803); `entry_price` defaulting to `stock_price` (L3802);
`stock_price` defaulting to `0` (L3801);
`layer2__recommended_hold_days` (L3832);
`layer1__scenarios__conditional_far__trigger_price` (L3826);
regime via `active_regime or regime or market_regime or vanguard_regime or 'TRANSITIONAL'` (L3798–3800);
edge direction via `vanguard_edge_direction or edge_direction or layer2__edge_direction or layer2__probability_direction` (L3841–3847);
`horizon_bucket or expected_move_window or macro_preferred_horizon` (L3907–3912);
`garch_forecast_vol`, `l3_vol_forecast`, `hv_30d`, `atm_iv`, `contract.iv`, `contract.implied_vol` (L4533–4540).
— External calls: option chain provider through `fetch_chain`; MarketData-derived
contract fields.
— Config/policy read: `DTE_MATRIX`, `DTE_DEFAULT`, `DTE_CONFIG` (L1102 comment),
`DELTA_ZONES`, `GOVERNED_DIRECTED_SIDES`.

**Logic and algorithms**
— Structural-context parser, `parse_structural_context` L3778–L4082. [OBSERVED]
— Governed direction resolution, `resolve_governed_direction` call L3886–L3899. [OBSERVED]
— DTE-window selection: tier/phase matrix then horizon override, L3902–L3923. [OBSERVED]
— Contract selection with a target-reachability filter, L4345–L4371. [OBSERVED]
— Options-liquidity lifecycle adapter, L4507–L4618. [OBSERVED]
— EV3 handoff builder with a directional invalidation repair, L4085–L4149. [OBSERVED]
— Decision branches (direction):
  * **CALL path:** `preferred_strategy = 'LONG_CALL'` (L3970/3973/3979);
    `structural_target = l1_far if l1_far > entry else target_3r` (L3987–3992);
    strike filter `strike <= structural_target` (L4351).
  * **PUT path:** `preferred_strategy = 'LONG_PUT'` (same lines, else branch);
    `structural_target = l1_far if l1_far < entry else entry - 3*stop_dist` (L3989–3994);
    strike filter `strike >= structural_target` (L4364).
  * **Other/blank path (UNRESOLVED, STRANGLE, NONE, ""):** L3965–3967
    `if direction not in GOVERNED_DIRECTED_SIDES: delta_zone = DELTA_ZONES['COMPRESSION'];
    preferred_strategy = 'NO_DIRECTIONAL_STRATEGY'`, and L3995–3996
    `else: structural_target = None`. Fail-closed. [OBSERVED]
  * `_macro_confirmation_overlay_oi` L286 `if direction != "PUT": return
    {"macro_confirmation_level": "STANDARD", ...}` — UNRESOLVED, STRANGLE, NONE and
    blank all receive the CALL/standard branch. [OBSERVED] (CON-104)

**Computations and formulas (exact)**
— `stop = float(stop_loss) if stop_loss > 0 else entry*0.97` (L3808) — currency; no
  direction term. [OBSERVED]
— `stop_dist = max(entry - stop, 0.01)` (L3819) — clamped at 0.01; assumes `stop < entry`.
  [OBSERVED]
— `target_3r = entry + 3*stop_dist` (L3822); PUT target `entry - 3*stop_dist` (L3994).
— `hold_days = l2_hold_days if l2_hold_days > 0 else dte_window[1]` (L3926) — sessions,
  integer; `dte_window[1]` is the tier/phase or horizon DTE mid-point, not a routed hold.
— `_theta_cap = int(dte_window[1] * 0.5)` (L3940); `_hold_max_final = min(_hold_max, _theta_cap)` (L3944).
— `dte_buffer_sessions = round(dte - minimum_required_dte, 2)` (L4607–4609).
— `remaining_runway_pct = round(runway_factor * 100.0, 2)` (L4611).
— EV3 invalidation mirror: `invalidation = entry - |entry - raw_stop|` for CALL,
  `entry + |entry - raw_stop|` for PUT (L4101). [OBSERVED]
— `planned_hold_sessions` = 5 / 10 / 20 from `horizon_bucket` text match (L4104–L4112);
  `None` when the bucket does not match, with `planned_hold_source = 'UNROUTED'` (L4145). [OBSERVED]
— `reach_score = 100.0 if strike <= structural_target else max(0.0, 60.0 - ((strike - structural_target)/spot)*250.0)`
  for CALL (L4837), mirrored for PUT (L4839).

**Models**
— Heston calibration, `calibrate_heston(chain_df, spot)` (L3764) inside a bare
  `try/except: pass` (L3768–3769); output `heston_params`, `heston_fit_error`.
  Calibration source claimed: none stated in code. Version tag: none. [OBSERVED]
— The maturation score is produced by the imported contract, not by this file.

**Outputs**
— Files written: `options/options_intelligence_{run_id}.csv` (`out_df.to_csv` L8481);
  `options/options_intelligence_latest.csv` (L8484); a ranked CSV (L8526); a blocked
  CSV (L8529); a rejection CSV (L8538); `options/vanguard_signals_enriched_*.csv`
  (L8684). [OBSERVED]
— Atomic promotion? **No** for all CSVs — direct `to_csv` to the final path. The only
  `os.replace` in the file is L8021 for a JSON payload. [OBSERVED]
— Schema/version field? No CSV-level schema version. Per-row version fields exist:
  `ev3_handoff_schema_version = 'ev3-options-handoff-v1'` (L4146),
  `invalidation_policy_version = 'EV3_DIRECTIONAL_STOP_V1'` (L4143),
  `lifecycle_contract_version` from the contract.
— Fields carrying authority claims: `macro_multiplier_authority = 'ADVISORY_ONLY'`
  (L273, L7657); `options_macro_authority = 'ADVISORY_ONLY'` (L6812, L7658);
  `maturation_execution_authority = False` (L4527, L4617) — **HOLDS**: the guard
  blocks on a true value (`options_liquidity_execution_guard.py:131–135`).

**Handoff** — Receives from Vanguard (`vanguard_signals.csv`) and Discovery.
Hands to the Horizon Router (stage 19), Phantom, SuperBrain passthrough, EIL, the EOD
Candidate Engine and the Lab. Join keys: `ticker`, `run_id`.

**Missing-data handling**
— Missing lifecycle input → `thesis_state='DATA_INCOMPLETE'`,
  `liquidity_state='LIFECYCLE_DATA_INCOMPLETE'`, `recovery_disposition='CONTRACT_REPAIR'`,
  `liquidity_lifecycle_reason='MISSING:'+names` (L4552–4561). §10-compliant? **Y**.
— Contract raises → `liquidity_state='LIFECYCLE_DATA_INVALID'` (L4588–4597). §10-compliant? **Y**.
— Synthetic mark → `quote_freshness='SYNTHETIC_NOT_EXECUTABLE'` and `quote_age_seconds=901.0`
  (L4566–4567, L4612). §10-compliant? **Y** (maps to SYNTHETIC_RESEARCH_ONLY).
— Missing `stop_loss` → `entry*0.97` with `stop_source='LEGACY_DEFAULT_NOT_EV_ELIGIBLE'`
  (L3808, L4018). The provenance is recorded but the value is still consumed as a real
  price by the lifecycle contract (L4549). §10-compliant? **N** (GAP-101).
— Missing horizon in the rejection-diagnostic path → `'1_5d'` (L6476). §10-compliant? **N** (GAP-104).
— Missing `structural_target` for a non-directed row → `None` (L3996). §10-compliant? **Y**.

**Contradictions found here:** CON-100, CON-101, CON-102, CON-104, CON-105
**Gaps found here:** GAP-100, GAP-101, GAP-104, GAP-105
**Comment/docstring claims audited:**
— L3781 "This is the pipeline contract — the options layer reads from here, never guesses."
  → **PARTIAL**. `stop` is guessed at L3808 when `stop_loss` is absent, and `regime`
  is guessed at L3799.
— L3901 "Derive DTE window from tier + phase, then let the horizon router override it."
  → **FALSE**. The Horizon Router executes at orchestrator L4208, i.e. *after* this
  stage (L4197). The override at L3907–3923 can only read a `horizon_bucket` that
  Discovery wrote. [OBSERVED `03_execution_order.md` §4]
— L3982–3985 "Direction-aware: CALL target must be ABOVE entry, PUT target must be
  BELOW entry" → **HOLDS** for the target (L3987–3994). The same file applies **no**
  equivalent direction rule to the stop (L3808).
— L4514–4515 "It turns missing inputs into an explicit repair state instead of
  inventing defaults." → **PARTIAL**. True for the eight keys in `required` (L4541–4561);
  but `ctx['stop']` itself was already invented upstream at L3808.
— L4563–4565 "Synthetic quotes … never current executability … the Morning Gate
  replaces this assessment with an exact MarketData quote." → **HOLDS**
  (`quote_age_seconds = 901.0` exceeds `DEFAULT_QUOTE_FRESHNESS_MAX_SECONDS = 900`,
  forcing `QUOTE_STALE`; `morning_gate.py:1888` re-evaluates).
— L3963–3964 "This prevents STRANGLE/NONE from silently falling through to LONG_PUT."
  → **HOLDS** (L3965–3967).
**Confidence in this section:** HIGH — every claim above is a direct read of the named
line; the file was located by targeted Grep and read in the regions quoted.

---

### contracts/options_liquidity_lifecycle.py

**Classification:** ORCHESTRATED contract module, side-effect free (649 lines).
**Real execution position:** not a stage. Called inside stage 18 (evening,
`avshunter_options_intelligence.py:4569`) and in the morning path
(`morning_gate.py:1888`).
**Task in the process:** Separates thesis validity, current contract executability and
maturation priority into three explicit classifications, and composes them in
`evaluate_options_liquidity_lifecycle`.

**Entry points:** `canonical_option_side` (L78), `calculate_dte_requirement` (L88),
`classify_moneyness` (L117), `calculate_expected_move_features` (L189),
`classify_current_executability` (L258), `classify_remaining_runway` (L392),
`evaluate_maturation_horizons` (L466), `evaluate_options_liquidity_lifecycle` (L577).
**Imports (production):** stdlib only (`dataclasses`, `math`, `typing`).
· **Imported by:** `scripts/avshunter_options_intelligence.py:122`, `morning_gate.py:66`,
`tests/test_options_liquidity_lifecycle.py`, `tests/test_options_crossed_quote_integration.py`.
· **Broken/retired imports:** NONE.

**Inputs** — Files/tables read: NONE. Upstream fields consumed: only the
`LifecycleInputs` dataclass fields (L552–L573). External calls: NONE.
Config/policy read: module constants L32–L38.

**Logic and algorithms**
— Side canonicalisation, fail-closed, L78–L85: anything not CALL/PUT raises. [OBSERVED]
— Executability state machine, L286–L389, ordered: no listed market → invalid DTE →
  DTE unsuitable → unknown moneyness treatment → moneyness unsuitable → no market →
  malformed quote → zero bid → crossed → stale → size → spread bands. [OBSERVED]
— Runway state machine, L430–L443: THESIS_INVALIDATED → MOVE_ALREADY_REALIZED →
  WAIT_FOR_PULLBACK → GAP_CONFIRMATION_EXTENDED → GAP_CONFIRMATION_WITH_RUNWAY →
  THESIS_UNDER_PRESSURE → THESIS_ACTIVE. [OBSERVED]
— Decision branches (direction): `direction = 1.0 if option_side == "CALL" else -1.0`
  (L418). **CALL path** and **PUT path** are both defined. **Other/blank path** cannot
  reach this function — `canonical_option_side` raises first (L85). Fail-closed. [OBSERVED]

**Computations and formulas (exact)**
— `minimum_required_dte = ceil(hold + monitor + exit_buffer)` (L107) — sessions summed
  and used as calendar days; defaults `monitor=3` (L36), `exit_buffer=5` (L37).
— `directional_distance_pct = ((strike/spot)-1)*100` for CALL, `((spot/strike)-1)*100`
  for PUT (L137–141); rounded to 6 dp (L179).
— `expected_move_pct = forecast_vol * sqrt(horizon_sessions/252)` (L209).
— `atm_distance_sigma = max(0, log-distance) / expected_move_pct` (L217–218).
— `strike_reach_score = clamp(1 - atm_distance_sigma/2) * 100`, 2 dp (L219, L228).
— `spread_pct = ((ask-bid)/((bid+ask)/2))*100` (L344–345); bands 18.0 / 25.0 (L33–34).
— `total_move = direction*(target-origin)`; `realised_move = direction*(current-origin)`;
  `invalidated = direction*(current-invalidation) <= 0` (L419–421).
— `consumed_factor = realised_move/total_move`; `remaining_factor = clamp(1-consumed_factor)` (L425–426).
— `maturation score = round(100 * reach_factor * execution_proxy * runway, 2)` (L538);
  `execution_proxy = 0.55*quote_factor + 0.45*neighbour` when a neighbour is supplied (L518).
— Quote-state weights `_LIQUIDITY_MATURATION_FACTOR` L456–L463:
  REVIEWABLE_SPREAD 0.90, LIQUIDITY_PENDING 0.70, QUOTE_STALE 0.55, ZERO_BID 0.35,
  NO_DISPLAYED_SIZE 0.55, NO_CURRENT_MARKET 0.20. [OBSERVED]

**Models** — Name: liquidity maturation score. Type: deterministic weighted product,
not a fitted model. Inputs: strike reach, quote state, runway, optional neighbour score.
Parameters/weights: as listed above. Output: `maturation_score_{1,2,3}d` bounded 0–100
with bands 60 / 35 (L539–L544). Calibration source claimed: **none** —
`"score_is_probability": False` (L229) and `MATURATION_SCORE_AUTHORITY =
"ADVISORY_NON_EXECUTION"` (L27). Version tag: `MATURATION_SCORE_VERSION =
"liquidity-maturation-deterministic-v1"` (L26).

**Outputs** — Files/tables written: NONE (pure functions). Atomic promotion?
NOT_APPLICABLE. Schema/version field? `lifecycle_contract_version =
"options-liquidity-lifecycle-v1"` (L25, emitted L643).
— Authority claims: `"execution_authority": False`,
  `"execution_authority_reason": "QUOTE_STATE_ONLY_NO_CAPITAL_AUTHORITY"` (L251–252)
  → **HOLDS**; `"maturation_may_authorize_trade": False` (L501) → **HOLDS**.

**Handoff** — Receives a `LifecycleInputs` from the options layer (evening) or the
Morning Gate. Hands back a flat dict merged into the row. Join keys: NOT_APPLICABLE.

**Missing-data handling**
— Non-finite runway price → `raise ValueError("runway prices must be finite numbers")` (L410–411).
— Non-positive runway price → `raise ValueError("runway prices must be positive")` (L413–414).
— Missing delta → `delta_band='UNKNOWN'`, `treatment='UNKNOWN_DELTA_REPAIR'` (L151–152),
  which routes to `MONEYNESS_UNSUITABLE` / `CONTRACT_REPAIR` (L304–315). §10-compliant? **Y**.
— Both bid and ask missing → `NO_CURRENT_MARKET` / MONITOR (L316–319). §10-compliant? **Y**.
— One side missing → `INVALID_QUOTE` / TERMINAL (L320–323). §10-compliant? **Y**.

**Contradictions found here:** NONE
**Gaps found here:** GAP-102, GAP-103
**Comment/docstring claims audited:**
— L11–12 "It is *not* a calibrated probability and it has no execution or capital
  authority. Only a current exact-contract assessment may return ``EXECUTABLE_NOW``."
  → **HOLDS** (L373–376 is the only `EXECUTABLE_NOW` producer, and it is inside
  `classify_current_executability`).
— L14–15 "provider-agnostic and side-effect free" → **HOLDS**.
— L79 "Return ``CALL`` or ``PUT`` and fail closed for all other strategies." → **HOLDS** (L85).
— L136 "Positive means the strike is still ahead in the thesis direction (OTM)." → **HOLDS**.
— L332–334 "Structural quote invalidity takes precedence over freshness." → **HOLDS**
  (crossed-quote test at L328 precedes the staleness test at L337).
— L96–99 "DTE is calendar time whereas the inputs are trading-session allowances. A
  conservative session sum is used" → **HOLDS** as coded (L107), and is itself the
  unit mismatch it describes.
**Confidence in this section:** HIGH — file read in full.

---

### contracts/options_liquidity_execution_guard.py

**Classification:** ORCHESTRATED contract module, fail-closed (202 lines).
**Real execution position:** not a stage. Called from `execution_gate.py:159` and
(via `action_is_within_guard`) from `morning_handoff_finalizer.py:187` and
`contracts/lab_control.py:1823`.
**Task in the process:** Converts the lifecycle evidence on a row into an execution
ceiling — CONTINUE, MANUAL_REVIEW, CONTRACT_REPAIR or BLOCK — and offers a predicate
for testing whether an emitted action is at or below that ceiling.

**Entry points:** `evaluate_olm_execution_guard` (L81), `action_is_within_guard` (L190).
**Imports (production):** stdlib only. · **Imported by:** `execution_gate.py:11`
(guard only), `contracts/lab_control.py:21` (both), `morning_handoff_finalizer.py:25` (both).
· **Broken/retired imports:** NONE.

**Inputs** — Files read: NONE. Upstream fields consumed: `lifecycle_contract_version`,
`thesis_state`, `liquidity_state`, `morning_transition_state`, `remaining_runway_state`
(L29–35), `maturation_execution_authority` (L131), `executable_now` (L178).
External calls: NONE. Config/policy read: L17–L27 constants.

**Logic and algorithms** — Ordered ceiling evaluation, L93–L187: contract presence →
terminal evidence (invalidated, realised) → maturation-authority violation → repair
transitions → defer transitions → missing transition → unrecognised transition →
version → thesis state → liquidity state → executable flag → CONTINUE.
— Decision branches (direction): NONE — this module does not branch on direction.
  CALL path, PUT path and other/blank path are identical. [OBSERVED]

**Computations and formulas (exact)** — `present = any(_text(row.get(f)) for f in
_CONTRACT_FIELDS)` (L93). No numeric computation.

**Models** — NONE.

**Outputs** — Files written: NONE. Fields emitted: `olm_guard_version`,
`olm_guard_disposition`, `olm_guard_reason`, `olm_guard_pass`,
`olm_guard_state_consistent` (L60–67). Atomic promotion? NOT_APPLICABLE.
Schema/version field? `OLM_EXECUTION_GUARD_VERSION = "olm-execution-guard-v1"` (L16).
— Authority claim: L4–7 "``CONTINUE`` is deliberately not an authorisation to trade"
  → **HOLDS**; `execution_gate.py` treats CONTINUE only as permission to proceed to
  its own checks (L180–181).

**Handoff** — Receives a row mapping. Hands `GuardDecision`. Join keys: NOT_APPLICABLE.

**Missing-data handling**
— No OLM fields and `require_contract=True` → MANUAL_REVIEW / `OLM_LIFECYCLE_REQUIRED`
  (L95–99). §10-compliant? **Y**.
— No OLM fields and `require_contract=False` → CONTINUE / `LEGACY_DIRECT_CALL_NO_OLM_CONTRACT`
  (L100–103) — fail-open by design for legacy callers. §10-compliant? **Y** (explicit token).
— Empty `morning_transition_state` → MANUAL_REVIEW / `OLM_TRANSITION_MISSING` (L147–151). **Y**.
— Unsupported lifecycle version → MANUAL_REVIEW with the version in the reason (L160–165). **Y**.

**Contradictions found here:** NONE
**Gaps found here:** GAP-106
**Comment/docstring claims audited:**
— L4–7 "``CONTINUE`` … only permits the existing Execution Gate to apply its
  direction, contract, monetisability and quote controls." → **HOLDS**.
— L111 "Terminal evidence has absolute precedence over every contradictory field."
  → **HOLDS** (L112–127 precede every other branch).
— L129–130 "A monitoring score claiming capital authority is contract corruption,
  never a reason to continue or to size up." → **HOLDS** (L131–135).
— L191 "Return whether an emitted action is equal to or safer than the ceiling."
  → **HOLDS** as coded, but the predicate is never called by `execution_gate.py` (GAP-106).
**Confidence in this section:** HIGH — file read in full.

---

### contracts/long_option_policy.py

**Classification:** ORCHESTRATED policy constants module (28 lines).
**Real execution position:** not a stage. Imported by `morning_gate.py` (emitted at L2146).
**Task in the process:** Holds the single spread and structure policy values so
Morning Gate and the Lab cannot drift.

**Entry points:** module-level constants only.
**Imports (production):** `types.MappingProxyType`. · **Imported by:** `morning_gate.py`.
· **Broken/retired imports:** NONE.
**Inputs** — Files read: NONE. Upstream fields: NONE. External calls: NONE.
Config/policy read: self.
**Logic and algorithms** — NONE. Decision branches: NONE (no direction branch;
`LONG_OPTION_ALLOWED_SIDES = {"CALL","PUT"}` L16 excludes every other value).
**Computations and formulas (exact)** — `LONG_OPTION_EXECUTABLE_SPREAD_MAX_PCT = 18.0` (L13);
`LONG_OPTION_REVIEWABLE_SPREAD_MAX_PCT = 25.0` (L14). Percent units.
**Models** — NONE.
**Outputs** — Files written: NONE. Atomic promotion? NOT_APPLICABLE.
Schema/version field? `LONG_OPTION_POLICY_VERSION = "long-options-production-v1"` (L12),
emitted by Morning Gate at `morning_gate.py:2146`.
**Handoff** — NOT_APPLICABLE.
**Missing-data handling** — NOT_APPLICABLE.
**Contradictions found here:** NONE
**Gaps found here:** NONE
**Comment/docstring claims audited:**
— L3–5 "Both Morning Gate and the Intelligence Lab import these values so spread and
  structure authority cannot drift between the two handoff stages." → **PARTIAL**:
  the same numeric values 18.0 / 25.0 are independently redeclared in
  `contracts/options_liquidity_lifecycle.py:33-34` as `DEFAULT_EXECUTABLE_SPREAD_MAX_PCT`
  and `DEFAULT_REVIEWABLE_SPREAD_MAX_PCT`, without importing this module. (GAP-107)
**Confidence in this section:** HIGH — file read in full.

---

### morning_gate.py

**Classification:** ORCHESTRATED morning stage (3,717 lines).
**Real execution position:** morning stage 2 of 3. Invoked by
`intelligent_orchestrator.py::premarket_workflow` L5799, imported inline at L5798.
[OBSERVED `03_execution_order.md` §3]
**Task in the process:** Reads the evening EOD candidate manifest, fetches live prices
and exact-contract quotes, re-hydrates the selected structure, re-evaluates the
options-liquidity lifecycle against the live spot, runs a battery of checks, and emits
one verdict / permission / route / lane per candidate.

**Entry points:** `run_morning_gate` (L2773); `run_gate` (L1957);
`_morning_liquidity_lifecycle` (L1776); the check helpers named below.
**Imports (production):** `contracts.options_liquidity_lifecycle` (L66–68);
`contracts.selected_contract_economics` (L60–63:
`evaluate_long_option_monetisability`, `hydrate_selected_structure`,
`recompute_premium_rr`); `contracts.long_option_policy`;
`contracts.direction_governance` (`resolve_governed_direction`, `validate_direction_record`);
`canonical_data` (`CanonicalFeatureFlags`, `CanonicalRegistry`,
`OptionLiquidityLifecycleStore`, `session_snapshot`) — all imported inline (L2799–2803,
L2846, L3214); `earnings_calendar_enricher` imported inline inside a try (L2242).
· **Imported by:** `intelligent_orchestrator.py` (inline). · **Broken/retired imports:** NONE.

**Inputs**
— Files/tables read: `data/output/runs/{run_id}/morning_validation/morning_candidates_{run_id}.csv`
  (L2780, read L2788); `dropbox/macro/bond_macro_state.json` (`BOND_MACRO_PATH` L83,
  loader from L1214); the macro state via `_load_macro_state` (L1177);
  `data/canonical/control_plane.sqlite` (L2809).
— Upstream fields consumed (with fallback chains):
  direction: `final_direction or canonical_direction or direction or options_direction` (L1784–1787);
  thesis spot: `thesis_spot or signal_price or underlying_price or entry_price or entry` (L1789–1792);
  target: `structural_target or target_price or target` (L1797);
  invalidation: `invalidation_spot or invalidation_price or invalidation_level or stop_loss or stop` (L1798–1801);
  hold: `remaining_hold_sessions or hold_days or l2_hold_days`, then digits parsed out of
  `hold_label or hold_period or time_horizon` (L1750–1757);
  forecast vol: `garch_forecast_vol, l3_vol_forecast, hv_30d, live_contract_iv, contract_iv, atm_iv`
  with a `>5.0 → /100` rescale (L1760–1773);
  EOD regime: `morning_macro_regime_state or macro_regime_label or macro_regime or regime_state`
  (L2113–2118) and additionally `evening_regime_state` (L1484–1490).
— External calls: live price and exact-contract quote provider via the fetch function
  passed to `hydrate_selected_structure` (L981, L1109).
— Config/policy read: `LONG_OPTION_EXECUTION_POLICY` (L2146); `MACRO_MAX_AGE_H = 14` (L85);
  `_GARCH_TRANSITION_DISCOUNT`; `DEFAULT_SPREAD_THRESHOLD` (L2775).

**Logic and algorithms**
— Governed-direction materialisation, `_ensure_governed_direction_record` L173–L201.
— Check battery, executed L2073–L2110; results stamped L2125–L2187.
— Morning lifecycle re-evaluation and transition state machine,
  `_morning_liquidity_lifecycle` L1776–L1950, transition ladder L1917–L1932.
— Verdict cascade, L2385–L2527 (17 ordered branches).
— Decision branches (direction):
  * **CALL path:** `_check_invalidation` L1467 `if direction == "CALL" and live_price <= invalidation: return False`.
  * **PUT path:** L1469 `if direction == "PUT" and live_price >= invalidation: return False`.
  * **Other/blank path (UNRESOLVED, STRANGLE, NONE, ""):** falls through to
    L1472 `return True, f"Invalidation intact …"` — **fail-open**. [OBSERVED] (CON-106)
  * `_assess_macro_context` L1536–L1545: a blank direction in a lead sector is scored
    `HEADWIND` / `-1` (L1536–1537) and in an avoid sector `HEADWIND` / `-1` (L1540–1541);
    advisory only. [OBSERVED]

**Computations and formulas (exact)**
— `iv_compression_ratio = live_iv / eod_iv`; block below 0.70 (L1737–1739).
— `abs_delta` bounds 0.20 and 0.75 (L1724–1727).
— `dte_buffer_sessions = round(dte - minimum_required_dte, 2)` (L1943).
— `remaining_runway_pct = round(runway_factor*100, 2)` (L1945).
— `macro_age_hours_gate = (now - macro_as_of)/3600`, `macro_freshness_flag = STALE`
  above `MACRO_MAX_AGE_H` (L2210–2212).
— `volume_anomaly_flag = ANOMALY` when `scanner_rvol >= 2.0` (L2234).
— `l3_vol_forecast_conf_adjusted = raw_conf * _GARCH_TRANSITION_DISCOUNT` (L2269–2270).
— `final_capital_permission = HUMAN_APPROVAL_REQUIRED | REVIEW_ONLY | NO` (L2546–2550);
  `execution_authorized = False` unconditionally (L2551).

**Models** — NONE fitted here. `_layer3_model_risk_guard` (L255) is a flag aggregator,
not a model; it emits `l3_model_risk_flags`, `l3_model_risk_flag_count`,
`l3_model_risk_capital_guard`, and a capped `l3_iv_tailwind_score_capped` (L2161–2162).

**Outputs**
— Files written: `morning_validation/morning_validated_trades_{run_id}.csv` (L2781);
  `morning_validation/morning_gate_summary_{run_id}.json` (L2782, also L677/L3668);
  a JSON payload via `path.write_text` (L450) — **non-atomic**;
  a lifecycle payload via `os.replace(temporary, payload_path)` (L2683) — **atomic**;
  SQLite writes into `control_plane.sqlite` at L2627 (`record_thesis_event`),
  L2716 (`record_contract_observation`), L2754 (`record_selection_event`).
— Atomic promotion? Mixed: **only** the L2683 payload. The two principal artefacts
  (CSV, summary JSON) are not atomically promoted. [OBSERVED]
— Schema/version field? `long_option_policy_version` (L2146); `gate_checked_at_utc` (L2122).
  No document-level schema version on the CSV.
— Fields carrying authority claims:
  `ev3_capital_authority = "ADVISORY_ONLY"` (L2080) → **HOLDS**: `_check_ev3_authority`
  returns `True` unconditionally (L252) and `ev3_pass` never appears in the verdict cascade.
  `macro_capital_authority = "ADVISORY_ONLY"` (L1552) → **HOLDS**: `macro_pass` is
  hard-assigned `True` at L2091 and macro never appears in the cascade.
  `execution_authorized = False` (L2551) → **HOLDS**.

**Handoff** — Receives `morning_candidates_{run_id}.csv` from the EOD Candidate Engine
(evening stage 40). Hands `morning_validated_trades_{run_id}.csv` to
`morning_handoff_finalizer.py` (morning stage 3) and, through the row fields
`morning_execution_permission` / `check_contract_pass`, to `execution_gate.py`.
Join keys: `run_id`, `ticker`, `contract_symbol`.

**Missing-data handling**
— `live_price is None` → `_check_invalidation` returns `(False, "CANNOT_VERIFY …")`
  (L1449–1450), then `invalidation_unverified = live_price is None` (L2355) demotes it
  to `flag_reasons` (L2365–2366) and the cascade branch L2444–2451 yields
  `verdict=FLAG, permission=WAIT, route=WAIT_LIVE_PRICE, lane=LIVE_PRICE_UNAVAILABLE`.
  Net effect: **fail-open to WAIT**, not fail-closed. §10-compliant? **Y** (PENDING_MORNING_REFRESH).
— Missing/zero `invalidation_price` → `return True, "WARN - no invalidation level on
  record; structure cannot be verified"` (L1457–1458). **Fail-open**, and the WARN text
  is not an emitted state token. §10-compliant? **N** (CON-107 / GAP-108).
— Missing `monetisability_state` → `(False, "MONETISABILITY_DATA_MISSING:…")` (L241),
  cascade branch L2436–2443 → BLOCK. **Fail-closed**. §10-compliant? **Y**.
— Missing `authority_source_stage`, `capital_authorization_state`, `capital_permission`,
  or `eod_candidate_authorized` → `(False, "…:MISSING")` (L212, L223, L225, L227) →
  BLOCK (L2385–2392). **Fail-closed**. §10-compliant? **Y**.
— Missing EOD regime → `(False, "EOD regime not recorded …")` (L1492–1493), but
  `macro_pass` is hard-set `True` at L2091 and macro is absent from the cascade, so the
  result is display-only. §10-compliant? **Y** (as an advisory), **but** see CON-108.
— Absent macro state → every macro display field `""` and
  `macro_freshness_flag = "UNAVAILABLE"` (L2219–2227). §10-compliant? **Y**.
— Absent bond state → `(True, "Bond macro state unavailable — check skipped")` (L1426–1427).
  §10-compliant? **Y** (advisory by design).
— Missing direction on a legacy row → `"UNRESOLVED"` (L187–188), never CALL. §10-compliant? **Y**.
— `earnings_calendar_enricher` import or call failure → `earnings_timing="MODULE_ERROR"`,
  `earnings_catalyst_flag="FALSE"` (L2255–2259). §10-compliant? **Y**.
— Lifecycle CDS setup failure and `stage_gating_enforced` false → warning only, no
  persistence (L2826–2833). §10-compliant? **N** (GAP-109).

**Contradictions found here:** CON-106, CON-107, CON-108
**Gaps found here:** GAP-108, GAP-109, GAP-110
**Comment/docstring claims audited:**
— L176–177 "The adapter exists only for older archived fixtures and never defaults an
  absent direction." → **HOLDS** (L187–188 assigns `UNRESOLVED`).
— L1423–1424 "Assess bond context for display and review. The result is advisory only
  and is never included in the trade authority decision." → **HOLDS**: `bond_pass` is
  stamped at L2186 and appears nowhere in L2353–L2527.
— L1502 "Publish macro context without granting or denying trade authority." → **HOLDS**
  (L1503–1508 return `True` on every path).
— L1515 "Direction-aware sector-rotation context; never a GO/NO-GO decision." → **HOLDS**
  for the GO/NO-GO half; "direction-aware" is **PARTIAL** because a blank direction is
  scored as if bearish (L1536–1541).
— L1970–1973 "Macro, regime rotation and bond intelligence never grant, deny or alter
  the trade verdict" → **HOLDS**.
— L2261 "AG-04: GARCH vol regime transition discount — DISPLAY ONLY, never modifies
  verdict" → **HOLDS** (`l3_vol_forecast_conf_adjusted` is a separate field; the raw
  `l3_vol_forecast_conf` is what `_layer3_model_risk_guard` reads at L266).
— L2203 "AG-07: Freshness flag — purely informational, never blocks or flags verdict"
  → **HOLDS**.
— L2519–2522 "GO_LIMIT … means eligible for a human-reviewed limit entry, not live
  capital authority" → **HOLDS** (L2546–2551).
— L2791–2792 "It records observations and transitions only; it cannot authorise trades."
  → **HOLDS**.
— L1445–1448 "passed=True means invalidation is intact — thesis still valid."
  → **PARTIAL**: also returned when there is no invalidation level at all (L1458) and
  when direction is neither CALL nor PUT (L1472).
**Confidence in this section:** HIGH for the check battery, the verdict cascade, the
lifecycle adapter and the write set — all read directly. MEDIUM for the completeness of
the write inventory: located by Grep on `to_csv|json.dump|os.replace|write_text` rather
than by a full read of 3,717 lines.

---

### execution_gate.py

**Classification:** ORCHESTRATED gate module (513 lines). Not called by
`premarket_workflow`; reached through the morning handoff path.
**Real execution position:** morning, downstream of `morning_gate.py`. Row-level entry
`execution_gate(row, require_olm=False)` (L152); batch entry
`run_execution_gate(signals, run_id, output_dir)` (L422) which forces
`require_olm=True` (L432). Also a CLI `__main__` (L495).
**Task in the process:** Applies the OLM ceiling, direction integrity, monetisability
identity, morning permission and six quote/greek/runway gates, then emits `final_action`.

**Entry points:** `execution_gate` (L152), `run_execution_gate` (L422), `__main__` (L495).
**Imports (production):** `contracts.direction_governance.validate_direction_record` (L10);
`contracts.options_liquidity_execution_guard.evaluate_olm_execution_guard` (L11) —
**`action_is_within_guard` is not imported**; `contracts.selected_contract_economics.contract_symbols` (L12).
· **Imported by:** reached from the morning handoff path (not from `premarket_workflow`).
· **Broken/retired imports:** NONE.

**Inputs**
— Files/tables read: the `--input` CSV in CLI mode (`_read_csv` L485, called L504).
  No macro, bond or lifecycle file is read.
— Upstream fields consumed (with fallback chains):
  quote: `live_contract_bid or live_bid or contract_bid`, and the ask/mid/delta/iv/iv_rank
  equivalents (L99–L113);
  permission: `morning_execution_permission or execution_permission or verdict` (L116–121);
  contract: `morning_selected_contract_symbol or contract_symbol or live_contract_symbol
  or recommended_contract` (L184–192), and separately
  `contract_symbol or option_symbol or recommended_contract` (L231);
  spot: `signal_price`, then `current_price or underlying_price or live_price` (L298–300);
  `campaign_verdict`, `execution_verdict`, `kelly_verdict`, `pse_final_size`,
  `monetisability_state`, `monetisability_contract_symbol`, `put_wall`, `gamma_flip`,
  `rcs_label`, `alternative_contract_1..3`.
— External calls: `get_live_option_data` (L35) is a **stub** returning `{}` with a
  one-time warning (L38). [OBSERVED]
— Config/policy read: `ExecutionGateConfig` L17–L30 (spread 0.08/0.15 as fractions;
  delta 0.20/0.30/0.60/0.85; IV 0.60/1.00; runway 0.015; target multiple 2.0).

**Logic and algorithms**
— OLM ceiling then direction integrity then monetisability identity then morning
  permission, L155–L229.
— Six numbered gates GATE-01…GATE-06, L266–L352.
— Final action selection, L356–L377.
— Decision branches (direction): the gate does **not** branch on direction. GATE-02
  uses `abs_delta` (L241, L276–279) so the **CALL path** and **PUT path** are identical
  and neither is falsely discarded. The **other/blank path** is not handled here; it is
  delegated to `validate_direction_record` (L161) whose failure returns
  `BLOCK / DIRECTION_INTEGRITY_FAILED` (L169–173). [OBSERVED]
— GATE-04 runway is computed from `put_wall` first, then `gamma_flip` (L310–315),
  with no direction term: for a PUT the "runway" to the put wall is the distance the
  thesis intends to travel, not the distance available. [OBSERVED] (CON-109)

**Computations and formulas (exact)**
— `spread_pct = (ask-bid)/max(ask,0.001)` (L247) — a **fraction of ask**, compared with
  `SPREAD_MAX = 0.15` and `SPREAD_FULL = 0.08` (L18–19). Note the lifecycle contract
  and `long_option_policy` use `(ask-bid)/mid*100` against 18.0/25.0.
— `mid = (bid+ask)/2` (L246); `_normalise_ratio` divides by 100 above 5.0 (L91–95).
— `runway_pct = |(spot - put_wall)/spot|` or `|(spot - gamma_flip)/spot|` (L311, L314).
— `target_move_pct = (mid * 2.0)/max(spot,0.001)` (L334).
— `penalty` multiplicative: 0.5 wide spread (L272), 0.75 delta outside core (L281),
  0.5 IV extreme (L287), 0.75 IV elevated with rank>80 (L292), 0.5 low runway (L318),
  0.75 above gamma flip outside a trending regime (L328), 0.5 target exceeds runway
  (L346); floored at 0.25 and rounded to 4 dp (L354).
— `actionable_rate = actionable/max(len(gated),1)` 4 dp (L455).

**Models** — NONE.

**Outputs**
— Files written: `execution_gated_{run_id}.csv` (L457); `execution_actionable_{run_id}.csv`
  (L460, only when non-empty); `execution_gate_summary_{run_id}.json` (L462–464).
— Atomic promotion? **No** — `_write_csv` opens the final path directly (L478).
— Schema/version field? `gate_version = GATE_VERSION` per row (L413) and in the summary
  (L448); `GATE_VERSION = "1.4.0"` (L15).
— Fields carrying authority claims: `final_action`, `preservation_gate = True` (L142, L415).
  `olm_guard_*` fields are merged onto every row (L160). Claim "GATE-03: IV, advisory
  only." (L284) → **HOLDS** (IV only adjusts `penalty` and `warnings`).

**Handoff** — Receives the Morning Gate row (permission, monetisability, OLM and
live-contract fields). Hands `final_action`, `gate_size_penalty`, `gate_warnings` and the
`live_*` echo fields onward. Join keys: `ticker`, `run_id`, contract symbol.

**Missing-data handling**
— OLM absent and `require_olm=True` → `MANUAL_REVIEW` via `_preserve` (L180–181 on the
  guard's `OLM_LIFECYCLE_REQUIRED`). §10-compliant? **Y**.
— Direction record invalid → `BLOCK / DIRECTION_INTEGRITY_FAILED:{reason}` (L169–173).
  **Fail-closed**. §10-compliant? **Y**.
— `monetisability_state` in {DATA_MISSING, CONTRACT_REPAIR} → `CONTRACT_REPAIR` (L206–211). **Y**.
— `monetisability_state` empty while permission is GO/GO_LIMIT/PROBE →
  `CONTRACT_REPAIR / MONETISABILITY_STATE_MISSING` (L212–215). **Y**.
— No live quote in the row and the stub returns `{}` → `CONTRACT_REPAIR /
  LIVE_CONTRACT_DATA_MISSING` (L233–236). **Fail-closed**. §10-compliant? **Y**.
— `ask <= 0 or bid < 0` → `CONTRACT_REPAIR / LIVE_CONTRACT_QUOTE_INVALID` (L244–245). **Y**.
— Spot missing → `MANUAL_REVIEW / UNDERLYING_PRICE_MISSING` (L299–302). **Y**.
— `campaign_verdict` empty and permission not GO/GO_LIMIT/PROBE →
  `MANUAL_REVIEW / CAMPAIGN_VERDICT_MISSING` (L254–262). **Y**.
— `campaign_verdict` empty **and** permission GO/GO_LIMIT → `campaign` is **manufactured**
  as `"READY_EXECUTE"` and `execution` as `"BUY_NOW"` (L255–257); PROBE →
  `"READY_PROBE"`/`"BUY_SMALL"` (L258–260). §10-compliant? **N** (GAP-111).
— No `put_wall` and no `gamma_flip` → `runway_pct = 0.0`, `runway_source = "NONE"`
  (L308–309) and GATE-04 and GATE-06 are both skipped (L316, L335). A missing input is
  emitted as the number `0.0`. §10-compliant? **N** — mitigated by the companion
  `runway_source` token. (GAP-112)
— Any exception → `MANUAL_REVIEW / GATE_EXCEPTION:{type}` (L417–419). **Y**.
— `iv_rank` missing → default `50.0` (L112); `contract_multiplier`-style neutral default.
  §10-compliant? **N** (GAP-113).

**Contradictions found here:** CON-109, CON-110, CON-111
**Gaps found here:** GAP-106, GAP-111, GAP-112, GAP-113
**Comment/docstring claims audited:**
— L2 module docstring "AVSHUNTER - EXECUTION GATE v1.1.0" and L499 argparse description
  "AVSHUNTER Execution Gate v1.1" vs `GATE_VERSION = "1.4.0"` (L15) → **FALSE** (CON-110).
— L38 "get_live_option_data() is the STUB. Wire in MarketData.app or Tastytrade before
  live trading." → **HOLDS** (L40 `return {}`).
— L156–158 "Evaluate OLM for every production row so even an independently blocked
  direction row retains complete guard lineage." → **HOLDS** (L159–160 precede L161).
— L275 "GATE-02: Delta. Use absolute delta so PUT contracts are not falsely discarded."
  → **HOLDS** (L241, L276, L279).
— L284 "GATE-03: IV, advisory only." → **HOLDS**.
— L429–431 "a production handoff cannot silently bypass OLM because fields are absent."
  → **HOLDS** for presence (L432 `require_olm=True`), **PARTIAL** for the ceiling:
  `action_is_within_guard` is never called here, so a `final_action` computed after a
  `CONTINUE` is never re-tested against the ceiling (GAP-106).
— L247–252 of `options_liquidity_execution_guard.py` "Keeping this explicit avoids
  reviving the retired multi-authority conflict in downstream CSV consumers." →
  **PARTIAL** in this consumer: the guard's own fields are carried, but the gate's
  `final_action` is not checked against them.
**Confidence in this section:** HIGH — file read in full.

---

### contracts/selected_contract_economics.py

**Classification:** ORCHESTRATED contract module, provider-agnostic (606 lines).
**Real execution position:** not a stage. Called from `morning_gate.py` only:
`hydrate_selected_structure` at L981 and L1109, `recompute_premium_rr` at L3553,
`evaluate_long_option_monetisability` at L3556. `contract_symbols` is also called from
`execution_gate.py:184` and `:193`.
**Task in the process:** Parses the selected OCC structure, hydrates every leg from one
exact-symbol quote function, and derives premium R:R and a conservative
target-intrinsic monetisability verdict for the exact contract.

**Entry points:** `normalise_occ_symbol` (L46), `contract_symbols` (L51),
`parse_occ_symbol` (L73), `canonical_structure` (L89), `economics_evaluation_id` (L108),
`parse_selected_structure` (L127), `hydrate_selected_structure` (L267),
`recompute_premium_rr` (L430), `evaluate_long_option_monetisability` (L507).
**Imports (production):** stdlib only. · **Imported by:** `morning_gate.py:59-63`,
`execution_gate.py:12`. · **Broken/retired imports:** NONE.

**Inputs**
— Files/tables read: **NONE**. The module never opens a file; every quote arrives
  through the injected `fetch_contract` callable (L269, called L288). [OBSERVED]
— Upstream fields consumed by `_quote_record` (L212–L254) — **all `live_contract_*`**:
  `live_contract_bid`, `live_contract_ask`, `live_contract_mid`, `live_contract_bid_size`,
  `live_contract_ask_size`, `live_contract_iv`, `live_contract_delta`,
  `live_contract_gamma`, `live_contract_theta`, `live_contract_vega`,
  `live_contract_oi`, `live_contract_volume`, `live_contract_multiplier`,
  `live_contract_provider_updated`, plus `live_options_fetched_at`, `live_options_source`,
  `contract_bid_size_quality`, `contract_ask_size_quality`, `contract_quote_quality`.
  **No completed-session chain field is read** — no `close`, `chain_*`, `eod_*` or
  `settlement_*` key appears anywhere in the module. [OBSERVED]
— Row fields consumed by the two economics functions:
  `canonical_direction or resolved_direction or direction` (L441–442, L542–543);
  `live_price or entry_spot or signal_price or underlying_price` (L444–446);
  `target_spot or target_price or structural_target` (L447–449, L546–548).
— External calls: the injected `fetch_contract` only.
— Config/policy read: `MONETISABILITY_MIN_PROFIT_PCT = 20.0` (L21).

**Logic and algorithms**
— OCC parsing and structure canonicalisation, L73–L209.
— Leg-by-leg hydration with a hard source gate, L287–L309.
— Vertical aggregation, L321–L385.
— Premium R:R recomputation, L430–L504.
— Monetisability classification, L507–L606.
— Decision branches (direction):
  * **CALL path:** vertical sorted ascending by strike, structure forced to
    `BULL_CALL_DEBIT` (L189–191); R:R `target_value = max(target_spot - strike, 0)` (L472);
    monetisability `breakeven = strike + entry_ask`, `target_clears_breakeven =
    target_spot > breakeven` (L568–571).
  * **PUT path:** vertical sorted descending, `BEAR_PUT_DEBIT` (L192–194); R:R
    `target_value = max(strike - target_spot, 0)` (L472); monetisability
    `breakeven = strike - entry_ask`, `target_clears_breakeven = target_spot < breakeven`
    (L572–575).
  * **Other/blank path:** `side = ""` (L138, L443, L545). A two-leg structure with an
    unresolved side → `FAILED / VERTICAL_DIRECTION_UNRESOLVED` (L195–201). A single leg
    with an unresolved side skips the leg-direction check entirely (L157 `if side and …`)
    and then fails later at `recompute_premium_rr` L450–454
    (`SELECTED_RR_THESIS_INPUT_MISSING`) and `evaluate_long_option_monetisability`
    L550–556 (`DIRECTION_TARGET_OR_LONG_LEG_MISSING`). **Fail-closed at the economics
    step, fail-open at the leg-consistency step.** [OBSERVED] (GAP-114)

**Computations and formulas (exact)**
— `strike = int(occ_strike)/1000.0` (L85).
— `mid = (bid+ask)/2` when absent (L217–218); invalid two-sided quote raises (L219–220).
— `dte = expiry - quote_time[:10]` in **days** (L222) — derived from the quote timestamp,
  not from a session clock.
— `spread_fraction_mid = (ask-bid)/mid` (L241) — a fraction, not a percent; converted at
  `live_contract_spread_pct = spread_fraction_mid * 100.0` (L410).
— Vertical: `entry_debit = long.ask - short.bid` (L330);
  `exit_credit = max(long.bid - short.ask, 0)` (L331); `mid = long.mid - short.mid` (L332);
  `spread_fraction_mid = (entry_debit - exit_credit)/mid` (L368).
— R:R: `option_gain = target_value - entry_debit`; `rr = option_gain/entry_debit` (L489–490),
  emitted 6 dp as `rr_premium_expected`, `rr_options` and `rr_predicted` (L500–502).
— Monetisability: `target_profit = target_intrinsic - entry_ask` (L577);
  `target_profit_pct = target_profit/entry_ask*100` (L578); bands: `NOT_MONETISABLE`
  when breakeven not cleared or profit ≤ 0 (L579–582), `LIMITED` below 20.0 % (L583–586),
  `MONETISABLE` otherwise (L587–590).
— `economics_evaluation_id = "ECI1:"+sha256(ticker|direction|structure|symbols)[:24]` (L121–124).
— `_snapshot_id = "QUOTE1:"+sha256(structure|per-leg symbol,timestamp,bid,ask,mid,source)[:24]` (L257–264).

**Models** — Monetisability uses **expiry intrinsic value** as the target payoff, not an
option-pricing model. Stated at L515–L518. Version tag
`MONETISABILITY_CALCULATION_VERSION = "selected-contract-monetisability-v1"` (L20).
Calibration source claimed: none, and none required.

**Outputs** — Files written: NONE. Atomic promotion? NOT_APPLICABLE.
Schema/version field? `HYDRATION_SCHEMA_VERSION = "selected-contract-hydration-v1"` (L22,
emitted L392), `RR_CALCULATION_VERSION` (L19, emitted L495),
`MONETISABILITY_CALCULATION_VERSION` (L20, emitted L521).
— Authority claims: none asserted in field values; the module emits states, not permissions.

**Handoff** — Receives the Morning Gate row plus an injected exact-symbol quote
function. Hands `live_contract_*`, `selected_*`, `rr_*` and `monetisability_*` fields
back into the Morning Gate row, and thence into `execution_gate.py` which compares
`monetisability_contract_symbol` with the selected symbol (L193–197).
Join keys: the OCC symbol; `selected_structure_id` / `monetisability_evaluation_id`.

**Missing-data handling**
— No selected contract → `FAILED / NO_SELECTED_CONTRACT` (L140–146). §10-compliant? **Y**.
— Malformed OCC → `FAILED / INVALID_OCC_SYMBOL` (L149–156). **Y**.
— Leg side disagrees with the row direction → `SELECTED_LEG_DIRECTION_MISMATCH` (L157–163). **Y**.
— Quote source empty or `MARKETDATA_NO_QUOTE` / `MARKETDATA_FAILED` →
  `FAILED / SELECTED_LEG_QUOTE_UNAVAILABLE:{symbol}:{source}` (L290–298). **Fail-closed**. **Y**.
— Invalid two-sided quote → `SELECTED_LEG_QUOTE_INVALID` (L299–309). **Y**.
— Not hydrated → `monetisability_state = "DATA_MISSING"` (L527–533). **Y**.
— Structure not `LONG_SINGLE` → `monetisability_state = "CONTRACT_REPAIR" /
  PRODUCTION_REQUIRES_LONG_SINGLE` (L534–540). **Y**.
— Missing `live_contract_multiplier` → `or 100.0` (L249). A missing provider value
  becomes a real number. §10-compliant? **N** (GAP-115).

**Contradictions found here:** CON-112
**Gaps found here:** GAP-114, GAP-115
**Comment/docstring claims audited:**
— L3–6 "The morning gate uses this module after a structure has been selected. It is
  deliberately provider-agnostic … No alternative contract is allowed to populate the
  selected structure unless every selected leg has been hydrated successfully."
  → **HOLDS**: L287–309 returns FAILED on the first bad leg and never appends a partial set.
— L344–345 "For a debit-spread entry the displayed capacity is constrained by the
  long-leg ask and short-leg bid." → **HOLDS** (L346–349).
— L513–518 "This deliberately avoids a future option-pricing model. The entry uses the
  current ask and the target value uses expiry intrinsic value, producing a conservative,
  deterministic answer that is recomputed whenever hydration selects a different OCC
  contract." → **HOLDS** as coded, with the qualification that "conservative" is only
  true where the hold ends at expiry; a pre-expiry exit retains extrinsic value the
  calculation discards.
— L434 "Calculate premium return-to-risk for the exact hydrated structure." → **HOLDS**.
**Confidence in this section:** HIGH — the module was read in full across two passes.

---

### canonical_data/option_liquidity_lifecycle.py

**Classification:** ORCHESTRATED canonical-data store, SQLite-backed (1,042 lines).
**Real execution position:** not a stage. Instantiated in the evening at
`scripts/avshunter_options_intelligence.py:8293` and in the morning at
`morning_gate.py:2823`, both behind `CanonicalFeatureFlags`.
**Task in the process:** Persists the option thesis lifecycle — thesis events, contract
observations and contract-selection events — as append-only, hash-verified records in
`data/canonical/control_plane.sqlite`.

**Entry points:** `OptionLiquidityLifecycleStore` (L254) with `initialise` (L260),
`latest_thesis` (L484), `latest_observation` (L495), `latest_selection` (L507),
`record_thesis_event` (L518), `record_contract_observation` (L635),
`record_selection_event` (L844), `should_fetch` (L970), `active_monitor_worklist` (L1001).
**Imports (production):** `sqlite3`, `canonical_data.CanonicalRegistry`, the shared
`parse_utc` / `utc_now` / `iso_utc` helpers. · **Imported by:** re-exported through
`canonical_data/__init__.py`; used by `morning_gate.py` and
`scripts/avshunter_options_intelligence.py`. · **Broken/retired imports:** NONE.

**Inputs** — Files/tables read: `data/canonical/control_plane.sqlite` tables
`option_thesis_events`, `option_contract_observations`, `option_contract_selections`,
`run_registry`. Upstream fields consumed: the keyword arguments of the three record
methods. External calls: NONE. Config/policy read: `CanonicalFeatureFlags` at the call
sites (`morning_gate.py:2805-2807`).

**Logic and algorithms**
— Immutable-content check by `event_id` hash: identical content is reused, differing
  content raises `OptionLifecycleConflict` (L575–583). [OBSERVED]
— Optimistic concurrency by `version` (L594–597). [OBSERVED]
— Terminal-state invariants: a terminal `thesis_state` requires
  `MonitorState.TERMINAL` and vice versa (L546–549). [OBSERVED]
— **Terminal supersession:** L592–593
  `if latest.thesis_state in TERMINAL_THESIS_STATES: raise OptionLifecycleConflict("terminal
  thesis cannot be reactivated")`. There is **no correction, supersession, amendment or
  reopen path** anywhere in the module. [OBSERVED]
— Identity immutability: `ticker` and `direction` are immutable for an existing
  `thesis_id` (L598–601). [OBSERVED]
— Decision branches (direction): `_normalise_direction` (L208–212) raises
  `DatasetValidationError("direction must be CALL or PUT")` for anything else.
  **CALL path** and **PUT path** are stored identically; the **other/blank path**
  cannot be persisted at all. Fail-closed. [OBSERVED]

**Computations and formulas (exact)**
— `event_id = _hash("OPTION_THESIS_EVENT_V1", thesis_id, event_key)` (L551).
— `payload_hash = _hash("OPTION_THESIS_PAYLOAD_V1", canonical_json(payload without
  recorded_at))` (L568–572) — the timestamp is deliberately excluded from identity.
— `version = latest.version + 1`, else `1` (L602, L608).
— `recorded_at = parse_utc(recorded_at) or utc_now()` (L544) — the caller may supply the
  instant; absent a caller value the wall clock is used.

**Models** — NONE.

**Outputs**
— Tables written: `option_thesis_events` (INSERT L611–627), plus the observation and
  selection inserts in `record_contract_observation` (L635) and `record_selection_event`
  (L844). Those three are the **only** writers in the module. [OBSERVED]
— Atomic promotion? Each INSERT is inside `self.registry.connection()` (L574), one
  transaction per record. There is **no** single transaction spanning a terminal thesis
  event and its final observation — they are two separate writes from the caller
  (`morning_gate.py:2627` then `:2716`). [OBSERVED]
— Schema/version field? The hash domain strings `OPTION_THESIS_EVENT_V1` /
  `OPTION_THESIS_PAYLOAD_V1` (L551, L570) act as the version tag; there is no explicit
  `schema_version` column on `option_thesis_events`.
— Fields carrying authority claims: `metadata.maturation_execution_authority = False`
  written by the evening caller (`avshunter_options_intelligence.py:7891`) → **HOLDS**.

**Handoff** — Receives from the options layer (evening) and the Morning Gate (morning).
Hands nothing to a downstream stage in the evening run; the store is read by
`should_fetch` / `active_monitor_worklist` for later sessions.
**Join keys: `thesis_id`.** Composed by the callers as
`f"{ticker}:{side}:{as_of or 'UNKNOWN_SESSION'}"` where
`as_of = _resolve_asof_date(signal_row)` =
`asof_date or signal_date or run_date or timestamp[:10]`, else `''`
(`avshunter_options_intelligence.py:4521`, `:6403-6413`), and in the morning as
`row['thesis_id'] or f"{ticker}:{side or 'UNRESOLVED'}:{asof_date or run_id or 'UNKNOWN_SESSION'}"`
(`morning_gate.py:1811-1814`). **Identity is therefore keyed on the row's as-of/run
date, not on `session_clock.last_completed_session`.** [OBSERVED] (GAP-116)

**Missing-data handling**
— Empty `thesis_id`, `event_key`, `run_id`, `ticker` or `reason_code` →
  `DatasetValidationError("… is required")` (L194–198). §10-compliant? **Y**.
— Direction not CALL/PUT → `DatasetValidationError` (L210–211). **Y**.
— `structural_target` / `invalidation_spot` may be `None` (L529–530, L542–543) — persisted
  as SQL NULL, not as 0. §10-compliant? **Y**.
— `recorded_at` absent → wall clock (L544). §10-compliant? **N** (GAP-117).
— Terminal thesis + a later event → **exception**, not a state. §10-compliant? **N** —
  §10 has no vocabulary for "supersession refused". (GAP-118)

**Contradictions found here:** NONE
**Gaps found here:** GAP-116, GAP-117, GAP-118
**Comment/docstring claims audited:**
— "terminal thesis cannot be reactivated" (L593) → **HOLDS**, and is the reason no
  correction path exists.
— "ticker and direction are immutable for an existing thesis" (L599–600) → **HOLDS** (L598).
**Confidence in this section:** HIGH for the writer inventory, the terminal invariant and
the identity key — all read directly. MEDIUM for the completeness of the observation and
selection method bodies: their signatures and call sites were read, their full bodies
(L635–L969) were not read line by line.

---

### canonical_data/session_clock.py

**Classification:** ORCHESTRATED shared calendar utility, dependency-free (177 lines).
**Real execution position:** not a stage. Called from `morning_gate.py:2849` and
`:3219`, `canonical_data/bundle_freshness.py:50`, `contracts/quote_change_evidence.py:177`
and `:190`.
**Task in the process:** Provides the XNYS session calendar, the current session state,
the last completed session, and a semantic freshness verdict.

**Entry points:** `xnys_holidays` (L76), `is_xnys_session` (L96), `is_early_close` (L100),
`previous_xnys_session` (L116), `session_bounds` (L123), `session_snapshot` (L131),
`evaluate_freshness` (L156).
**Imports (production):** `zoneinfo`, `datetime`, `dataclasses`, `enum`.
· **Imported by:** `canonical_data/__init__.py:74-83` (re-export),
`canonical_data/bundle_freshness.py:12`, `contracts/quote_change_evidence.py:12`,
`morning_gate.py` (inline, L2846 and L3214). · **Broken/retired imports:** NONE.

**Inputs** — Files/tables read: NONE. Upstream fields consumed: NONE — the module takes
only `datetime` / `date` arguments. External calls: NONE. Config/policy read:
`live_ttl_seconds` default 60 (L162), caller-owned.

**Logic and algorithms**
— Holiday table computed arithmetically per year, L76–L93, including Juneteenth from
  2022 (L88–89) and the following-year New Year observed roll-back (L90–92).
— Early closes: day after Thanksgiving, 24 December, and the session before
  Independence Day, L100–L113.
— Session state ladder: CLOSED / PREMARKET / REGULAR / AFTER_HOURS, L138–L150,
  with premarket from 04:00 ET and after-hours to 20:00 ET (L141–142).
— **`last_completed_session` resolution:** L151
  `last_session = today if instant >= close_utc else previous_xnys_session(today)`.
  On a non-session day the snapshot short-circuits at L139 with
  `previous_xnys_session(today)`. [OBSERVED]
— Decision branches (direction): NONE. NOT_APPLICABLE.

**Computations and formulas (exact)**
— Regular close 16:00 ET, early close 13:00 ET (L127).
— `closed_minute = instant.replace(second=0, microsecond=0) - 1 minute`, only while
  REGULAR, else `None` (L152).
— `evaluate_freshness`: `as_of is None → MISSING` (L165–166); naive tz → `INVALID`
  (L167–168); future beyond 1 s → `INVALID` (L171–172); for domains
  `OPTION_CHAIN / COMPLETED_SESSION / EOD` → `EOD_CURRENT` iff
  `dataset_session == snapshot.last_completed_session`, else `STALE` (L175–176);
  otherwise `FRESH` iff age ≤ `live_ttl_seconds`, else `STALE` (L177).

**Models** — NONE.

**Outputs** — Files written: NONE. Returns a `SessionSnapshot` (L33–41) or a
`FreshnessState` (L25–31). Atomic promotion? NOT_APPLICABLE. Schema/version field? NONE.
— Authority claims: none in code. The docstring claim at L2–5 is audited below.

**Handoff** — NOT_APPLICABLE (pure library).

**Missing-data handling**
— `as_of is None` → `FreshnessState.MISSING` (L165–166). §10-compliant? **Y**.
— Naive timestamp → `FreshnessState.INVALID` (L167–168). **Y**.
— Non-session date passed to `session_bounds` → `ValueError` (L124–125). **Y**.

**Contradictions found here:** CON-113
**Gaps found here:** GAP-119, GAP-120
**Comment/docstring claims audited:**
— L2–5 "Shared XNYS session clock … The calendar implementation is dependency-free and
  covers regular US equity holidays, observed dates, early closes and US DST through
  ``zoneinfo``." → **HOLDS** for the calendar. **PARTIAL** for "shared": of the twenty
  Lane-B files, only `morning_gate.py` imports it. `scripts/avshunter_options_intelligence.py`,
  `eod_candidate_engine.py`, `trigger_layer.py`, `macro_horizon_router.py`,
  `execution_gate.py`, `intelligence-lab/intelligence_lab.py`,
  `contracts/lab_control.py`, `contracts/selected_contract_economics.py` and
  `canonical_data/option_liquidity_lifecycle.py` do not. [OBSERVED, by Grep for
  `session_clock|last_completed_session|session_snapshot|evaluate_freshness` across `*.py`]
— L164 "Apply semantic freshness; TTL seeds remain caller-owned configuration."
  → **HOLDS** (L162 default is a parameter).
**Confidence in this section:** HIGH — file read in full; the import census is a
repository-wide Grep.

---

### wyckoff_phase_validator.py

**Classification:** ORCHESTRATED analytic helper (316 lines).
**Real execution position:** not a stage of its own. Called from the Discovery layer
(the strict adjudicator above the permissive discovery Wyckoff engines).
**Task in the process:** Adjudicates a Wyckoff phase claim into a correctness score, a
maturity score, a phase status, transition probabilities and a structural invalidation
level.

**Entry points:** `validate_wyckoff_phase` (L217), `prefixed_validation_fields` (L314).
**Imports (production):** `pandas`. · **Imported by:** the Discovery layer.
· **Broken/retired imports:** NONE.

**Inputs** — Files/tables read: NONE; takes a `bars` DataFrame and two dicts.
Upstream fields consumed: `wyckoff_mode`, `control_state`, `current_phase`,
`phase_evidence_strength`, `event_evidence_strength`, `truth_confidence`,
`transition_bias`, `transition_confidence`, `contradictions`, `dominant_event`,
`stop_loss`, `phase_progression`; and from precor `wyckoff_phase`,
`wyckoff_phase_conf`, `primary_event`, `notes_all`, `move_age_bars`, `transition_to`,
`transition_conf`, `control_state`. External calls: NONE. Config/policy read:
`ACCUMULATION_EVENTS` / `DISTRIBUTION_EVENTS` / `EVENT_ALIASES` (L19–L38).

**Logic and algorithms**
— Mode resolution, `_mode` L81–L90.
— Phase-from-evidence arbitration between the Wyckoff engine and precor, L109–L135.
— Event-sequence scoring, L151–L167.
— Duration scoring by phase, L170–L184.
— Status ladder, `_status` L201–L214.
— Decision branches (direction): this module has no CALL/PUT axis; its equivalent is
  ACCUMULATION vs DISTRIBUTION.
  * **DISTRIBUTION path:** `_mode` L83–84 and L88–89; `_invalidation_level` L196–197
    `return round(float(recent["high"].max()), 4)` — a level **above** price.
  * **ACCUMULATION path:** `_mode` L85–86; `_invalidation_level` L194–195
    `return round(float(recent["low"].min()), 4)` — a level **below** price.
  * **Other/blank path:** there is none. `_mode` L90 `return "ACCUMULATION"` is a
    terminal default reached whenever `wyckoff_mode` is empty or unrecognised **and**
    `control_state != "SELLERS"`. `_invalidation_level`'s third branch (L198
    `return None`) is therefore unreachable through `validate_wyckoff_phase`.
    [OBSERVED] (CON-114)

**Computations and formulas (exact)**
— `correctness = seq*0.30 + price_structure*0.25 + volume_spread*0.20 +
  acceptance*0.15 + context*0.10` (L244–250), all inputs clamped 0–100 (L49–50).
— `context_score = clamp(truth_conf - len(contradictions)*8.0)` (L242).
— `acceptance_score = clamp(transition_conf)` when `phase_progression == "towards_next"`,
  else `clamp(transition_conf*0.75)` (L241).
— `maturity = required_done*100*0.35 + duration*0.20 + proximity*0.20 +
  next_phase_evidence*0.15 + exhaustion_failure*0.10` (L258–264).
— `exhaustion_failure = clamp(100 - len(contradictions)*18.0)` (L257).
— `_duration_score`: A `clamp(age*14)`, B `clamp(35+age*2)`, C `clamp(85-age*4)`,
  D `clamp(35+age*3)`, E `clamp(55+age*1.5)`, unknown `40.0`, missing age `45.0` (L170–184).
— `p10 = clamp((maturity*0.55 + transition_conf*0.45)/100, 0, 0.95)`;
  `p5 = clamp(p10*0.60, 0, 0.90)`; `p20 = clamp(p10+0.20, 0, 0.98)` (L279–281);
  on `invalidated`, floors of 0.65 / 0.80 / 0.90 are applied (L282–283).
— `bars_remaining_low = max(1, round((1-p10)*10))`;
  `bars_remaining_high = max(low+1, round((1-p5)*20))` (L285–286).
— `invalidated` when `truth_conf < 25` or (`phase_strength < 35` and
  `event_strength < 35`) or (`len(contradictions) >= 3` and `correctness < 55`) (L273–277).
— `structural_invalidation_level = stop_loss if present, else the 40-bar low
  (ACCUMULATION) or 40-bar high (DISTRIBUTION)` (L187–198, emitted L308).

**Models** — Name: Wyckoff phase adjudicator. Type: deterministic weighted score with a
hand-specified event table. Parameters/weights: as listed above. Output:
`phase_correctness_score`, `phase_maturity_score`, `phase_status`, three transition
probabilities. Calibration source claimed: **none** — the weights and the transition
probability mapping carry no stated fit or backtest. Version tag: **none**. [OBSERVED] (GAP-121)

**Outputs** — Files written: NONE. Returns the 22-key dict at L289–L311, optionally
prefixed `wyckoff_validation_` (L314–316). Atomic promotion? NOT_APPLICABLE.
Schema/version field? **NONE**.
— Authority claims: `"timeframe_alignment": "UNASSESSED"` (L309) is honest and **HOLDS**.

**Handoff** — Receives Wyckoff and precor evidence from Discovery. Hands
`structural_invalidation_level` into the Discovery stop hierarchy
(`avshunter_discovery_ULTIMATE.py:1790` reads `wyckoff_data.get('stop_loss')`), and
thence into `stop_loss` on the signal row that
`avshunter_options_intelligence.py:3803` reads. Join keys: `ticker`.

**Missing-data handling**
— No `bars` or missing high/low columns → `structural_invalidation_level = None`
  (L191–192). §10-compliant? **Y**.
— Missing `move_age_bars` → duration score `45.0` (L171–172): a missing input becomes a
  mid-range number. §10-compliant? **N** (GAP-122).
— Missing `wyckoff_mode` and `control_state` → `"ACCUMULATION"` (L90). §10-compliant?
  **N** — there is no UNRESOLVED mode. (CON-114 / GAP-123)
— Unknown phase → `_norm_phase` returns `"UNKNOWN"` (L68), `_required_events` returns
  the empty set (L95), `current_ok` becomes `True` (L154), and
  `_duration_score` returns `40.0` (L184). A phase that could not be identified scores
  as if its events were satisfied. §10-compliant? **N** (GAP-124).

**Contradictions found here:** CON-114
**Gaps found here:** GAP-121, GAP-122, GAP-123, GAP-124
**Comment/docstring claims audited:**
— L3–8 "The existing engines are intentionally permissive … this validator is
  intentionally stricter so downstream pipeline stages can separate 'looks like Phase C'
  from 'structurally valid, mature Phase C'." → **PARTIAL**: strict on events and
  contradictions, permissive on mode (L90) and on an unknown phase (L154).
— L223 "Return strict validation fields for downstream AVSHUNTER consumers." → **PARTIAL**,
  same basis.
— L315 "Return namespaced fields for wide CSV outputs without losing schema names."
  → **HOLDS** (L316).
**Confidence in this section:** HIGH — file read in full.

---

### macro_horizon_router.py

**Classification:** ORCHESTRATED analytic stage (825 lines).
**Real execution position:** stage 19 of 51, evening — **after** Options Intelligence
(stage 18). Invoked by `intelligent_orchestrator.py::evening_workflow` L4208
(`run_horizon_router`, script path from `OrchestratorConfig` L531); the routing function
itself is called at `intelligent_orchestrator.py:1501`.
**Task in the process:** Assigns each signal to one of three horizon buckets or to a
blocked channel, and returns the routed signals in memory.

**Entry points:** `extract_horizon_biases` (called `intelligent_orchestrator.py:1347`),
`route_signals_by_horizon` (L301; called `intelligent_orchestrator.py:1501`),
`log_routing_summary` (called `intelligent_orchestrator.py:1628`).
**Imports (production):** stdlib plus `pandas` imported inside `routed_to_df` (L520).
· **Imported by:** `intelligent_orchestrator.py` (by path).
· **Broken/retired imports:** NONE. **Uncalled public functions:** `routed_to_df` (L517),
`routing_summary_dict` (L543), `block_reason_counts` (L553), `make_signal_id` (L563),
`get_sector_permission` (L278) — the wiring for them exists only in a commented-out
block, L582–L646. [OBSERVED]

**Inputs**
— Files/tables read: exactly one — L331 `macro = json.loads(macro_path.read_text(encoding="utf-8"))`,
  where `macro_path` is `cfg.MACRO_FILE` supplied by the orchestrator. There is **no**
  `pd.read_csv` and no read of `macro_quant_packet.json`, `bond_macro_state.json`,
  `macro_intelligence_latest.json` or any options CSV. [OBSERVED]
— Upstream fields consumed (with fallback chains):
  `expected_holding_days or hold_days or horizon_days` (L419–423) — a hold of `0` is
  falsey and falls through; `options_direction or instrument` (L355–374);
  `vix_current` defaulting to `18.0` (L436); `dte`.
  **`horizon_bucket` is never read** — Grep returns only the docstring (L19), the two
  writes in the uncalled `routed_to_df` (L528, L538), and the commented-out block
  (L633, L640). [OBSERVED]
  **`expected_move_window` and `macro_preferred_horizon` do not appear in this file at all.** [OBSERVED]
— External calls: NONE.
— Config/policy read: `ROUTER_VERSION = "macro_horizon_router_v1.2_macro_advisory"` (L43).

**Logic and algorithms**
— Bias extraction with a whole-block fallback from `horizon_routing` to
  `extras.forward_bias`, L199–L264.
— Instrument normalisation and blocking, L355–L374.
— Bucket assignment, L438–L445.
— Decision branches (direction):
  * **CALL path:** L356–357 `CALL` / `LONG_CALL` → `"CALL"`.
  * **PUT path:** L358–359 `PUT` / `LONG_PUT` → `"PUT"`.
  * **Other/blank path:** `STRANGLE` → L361–363 `continue` — the signal is **silently
    dropped**, with no blocked row emitted [OBSERVED]; every other value including blank
    → blocked with `block_reason=f"INVALID_INSTRUMENT:{raw_inst or 'EMPTY'}"` (L371).
  * After normalisation **direction is never consulted again**; the code states this at
    L482 `# Otherwise: route unconditionally. No PUT/CALL secondary gates.` [OBSERVED]

**Computations and formulas (exact)**
— Primary bucket from hold-days, L443:
  `horizon = "1_5d" if hold_days <= 5 else ("6_10d" if hold_days <= 10 else "11_20d")` —
  thresholds **5 and 10**, in sessions.
— Fallback bucket from DTE, L445:
  `horizon = "1_5d" if dte <= 21 else ("6_10d" if dte <= 55 else "11_20d")` —
  thresholds **21 and 55**, in calendar days.
— `_clamp` on size multiplier to [0, 1.5] (L218, L122–125).
— **The routed set is not `{5,10,20}`.** That literal exists only downstream, at
  `intelligent_orchestrator.py:2807` `_hold_by_bucket = {"1_5d": 5, "6_10d": 10, "11_20d": 20}`.
  The `11_20d` bucket therefore acquires a 20-session hold that the router never
  computed. [OBSERVED] (CON-115)

**Models** — NONE.

**Outputs**
— Files written: **NONE.** Grep for `to_csv|open(|write` over the module returns no
  match. It returns `dict[str, list[RoutedSignal]]`. The
  `horizon_{bucket}_{run_id}.csv` artefacts are written by the orchestrator at
  `intelligent_orchestrator.py:1524`, with the bucket **forced from the loop key** at
  L1533 `_out_row["horizon_bucket"] = _bucket`. [OBSERVED]
— Fields carried on `RoutedSignal` (L153–164): `ticker`, `instrument`, `signal_id`,
  `horizon`, `action`, `size_multiplier`, `confirm_required`, `macro_permitted`,
  `horizon_source`, `block_reason`, `router_version`.
— Atomic promotion? NOT_APPLICABLE here; the orchestrator's
  `patch_horizon_fields_into_csv` writes directly, `patched.to_csv(target_csv, index=False)`
  (`intelligent_orchestrator.py:2818`), and **drops any existing horizon columns before
  merging** (L2781–2784), i.e. Discovery's `horizon_bucket` is unconditionally
  overwritten, then `fillna("unrouted")` (L2797). [OBSERVED]
— Schema/version field? None; `ROUTER_VERSION` is stamped per signal.
— Fields carrying authority claims: `macro_permitted`. Claim L25–26 "macro remains
  standalone advisory context and cannot block a CALL/PUT or change its capital size"
  → **HOLDS** (L488 hardcodes `size_multiplier=1.0`).

**Handoff** — Receives signals from the orchestrator (sourced from the Options
Intelligence output). Hands routed signals back to the orchestrator, which writes the
horizon CSVs and patches the Discovery / Vanguard / Options / SuperBrain CSVs three
times (L4218, L4246, L4508). Join keys: `ticker`, `signal_id`.

**Missing-data handling**
— `MACRO_FILE` absent → `raise FileNotFoundError("MACRO_FILE_MISSING: …")` (L326–329). **Y**.
— Malformed macro JSON → `raise ValueError("MACRO_JSON_INVALID: …")` (L332–333). **Y**.
— Horizon key absent from the macro packet → `log.warning` + `continue` (L206–209), then
  `block("No macro bias data for this horizon")` (L460–462). **Y**.
— `go_no_go` says MONITOR / NO_GO / PROACTIVE → **mapped to `GO_SELECTIVE`**, L173–174
  `return HorizonAction.GO_SELECTIVE  # Never emit MONITOR_ONLY`. §10-compliant? **N** (CON-116).
— Missing `bullish_prob_pct` → `50.0` (L214); missing `size_multiplier` → `0.5` (L218);
  missing `confidence` → `75` (L223); missing `confirm_required` → `["LLR_TRUE"]` (L219–222);
  missing `vix_current` → `18.0` (L436); missing VIX threshold → `22.0` (L270–275).
  §10-compliant? **N** (GAP-125).
— Non-dict `extras` → `{}` silently (L182–191). **N**.
— `safe_bool` unrecognised token → `False` (L48–64): `"MAYBE"` reads as False. **N**.
— No bare `try: … except: pass` in this file. [OBSERVED]

**Contradictions found here:** CON-115, CON-116, CON-117, CON-118
**Gaps found here:** GAP-125, GAP-126, GAP-127
**Comment/docstring claims audited:**
— L25–26 "macro … cannot block a CALL/PUT or change its capital size" → **HOLDS**.
— L481 "Hard kill-switch: RISK_OFF / CRISIS regime blocks everything." → **FALSE**:
  L469–474 is `log.info(...)` with no `block()` and no `continue`; execution falls
  through to `output[horizon].append(...)` at L485. (CON-117)
— L317 "QA-FIX-6: PUT blocked when macro horizon is MONITOR_ONLY" → **FALSE**: no PUT
  branch exists (L482).
— L318 "QA-FIX-7: iv_regime normalised to upper before comparison" → **FALSE**: L435
  normalises it and it is never compared to anything.
— L321 "QA-FIX-10: routed_to_df now includes instrument + router_version" → **PARTIAL**:
  true of L524–536, but `routed_to_df` is never called.
— L477–478 "The router's ONLY job is: assign the signal to a horizon bucket and pass the
  macro size multiplier." → **PARTIAL**: the bucket is assigned; the multiplier is **not**
  passed — L488 hardcodes `1.0`, discarding `bias.size_multiplier` computed at L218. (CON-118)
— L438–441 "DTE → holding period bucket: ≤21 DTE → 1_5d; ≤55 → 6_10d; >55 → 11_20d"
  → **PARTIAL**: correct for L445 only; the primary branch L443 uses hold-day thresholds
  5/10 that the comment does not describe.
— L19–21 "FIX-PLACEHOLDER … Once wired in, these columns populate correctly." →
  **PARTIAL**: populated, but from the filename/loop key
  (`intelligent_orchestrator.py:1533`, `:2751`), not from `RoutedSignal.horizon`.
**Confidence in this section:** HIGH — delegated targeted read; every claim carries a
file:line and, where decisive, a verbatim quote. MEDIUM for the orchestrator-side
`patch_horizon_fields_into_csv` detail, which is outside this lane's file set and was
read to close the overwrite question only.

---

### trigger_layer.py

**Classification:** ORCHESTRATED analytic stage, run **twice** (1,109 lines).
**Real execution position:** stage 27 of 51 (pass 1) and stage 36 of 51 (pass 2), evening.
Pass 1 `patch_run_packages` at `intelligent_orchestrator.py:4421` (packages only,
**before** EIL). Pass 2 `enrich_csv` at `intelligent_orchestrator.py:4770`, **after** EIL
(L4690), after `inject_actuarial` (L4694) and after GARCH (L4700–4701).
[OBSERVED `03_execution_order.md` §2, §4]
**Task in the process:** Evaluates four structural triggers per row, derives a trigger
quality, score, freshness state and context state, patches the package JSONs and a
sidecar CSV in pass 1, and writes fifteen `trigger_*` columns into the EIL-enriched CSV
in pass 2.

**Entry points:** `patch_run_packages` (L920–L1051); `enrich_csv` (L780–L907);
`evaluate_triggers` (L600); `build_trigger_block` (L~640).
**Imports (production):** stdlib (`csv`, `json`, `pathlib`, `logging`, `datetime`).
· **Imported by:** `intelligent_orchestrator.py` (inline, twice).
· **Broken/retired imports:** NONE.

**Inputs**
— Files/tables read: pass 1 — `runs/{run_id}/packages/*.package.json` (glob L965, loaded
  L967–968) and an optional Vanguard CSV keyed by ticker (L939–945).
  Pass 2 — the input CSV via `csv.DictReader` (L814–817) and the pass-1 sidecar
  `runs/{run_id}/trigger_layer_summary_{run_id}.csv` via `_load_package_trigger_map`
  (L704–710). [OBSERVED]
— Upstream fields consumed (with fallback chains):
  direction resolver `_direction` L157–191 —
  `options_direction → direction → precor_intent substring → dominant_trend → vwap_bias → "NONE"`;
  EV chain L315–320 then L306–310 —
  `ev2_ev_conf_adj / fd_ev_used / ev_conf_adj / eil_ev_net / ev_final`, then actuarial,
  then GARCH 6-10d, then GARCH 1-5d, then `0.0`;
  win rate `layer2__win_rate_10d or win_rate_10d` (L331);
  `crabel_compression` defaulting to `1.0` (L366); `atr_percentile_rank` defaulting to
  `100.0` (L367); `volume_ratio_x`, `adx_14` defaulting to `0.0` (L413, L458–459);
  as-of anchor `asof_date or score_date` (L269).
— External calls: NONE.
— Config/policy read: `TRIGGER_WEIGHTS` L63–70; `QUALITY_STRONG_MIN = 3.5`,
  `QUALITY_SINGLE_MIN = 1.5` (L73–74); `TRIGGER_CSV_COLUMNS` L670–686.

**Logic and algorithms**
— Four trigger detectors: `_t1_vol_compression`, `_t2_vwap_reclaim` (L421–429),
  `_t3_range_break`, `_t4_trap` (L537–542). Evaluation order T1→T2→T3→T4 (L602–616).
— Freshness evaluation with an as-of anchor, L241–L284.
— Context-state evaluation, L223–L231.
— Decision branches (direction):
  * **CALL path:** `_t2_vwap_reclaim` L421 `and direction in ("CALL", "NONE")`;
    `_t4_trap` L537 `direction == "CALL"`.
  * **PUT path:** `_t2_vwap_reclaim` L429 `and direction in ("PUT", "NONE")`;
    `_t4_trap` L540 `direction == "PUT"`.
  * **Other/blank path:** `STRANGLE` short-circuits to `"NONE"` at L169
    `return "NONE"   # bidirectional — intentionally non-directional`; the terminal
    default is also `"NONE"` (L191). A `NONE` direction **satisfies both** L421 and L429,
    so a non-directional row is eligible for `VWAP_RECLAIM` **and** `VWAP_LOSS`, decided
    purely by `vwap_bias` / `controller`. In `_t4_trap`, `NONE` reaches L542 `return None`.
    `_t1_vol_compression` and `_t3_range_break` do not consult direction at all. [OBSERVED] (CON-119)

**Computations and formulas (exact)**
— `trigger_score = sum(TRIGGER_WEIGHTS.get(t, 1.0) for t in triggers)` (L549–551).
  Weights L63–70: `VOL_COMPRESSION 2.0`, `RANGE_BREAK_EARLY 1.5`, `RANGE_BREAK 2.0`,
  `VWAP_RECLAIM 1.5`, `VWAP_LOSS 1.5`, `TRAP 2.5`; unlisted codes contribute `1.0`.
— `trigger_quality = "STRONG" if score >= 3.5 else "SINGLE" if score >= 1.5 else "NONE"`
  (L554–565).
— `trigger_primary = max(triggers, key=lambda t: TRIGGER_WEIGHTS.get(t, 1.0))` (L575);
  ties resolve to the first in evaluation order.
— `go_eligible = is_go_eligible(triggers) and not freshness["stale"]` (L637).

**Models** — NONE.

**Outputs**
— Pass 1 writes: each `*.package.json` in place under `pkg["triggers"]`
  (`json.dump` L972–973, key set at L916); the sidecar
  `runs/{run_id}/trigger_layer_summary_{run_id}.csv` (L1035, columns L1037–1044).
  The sidecar carries 14 columns and **omits `trigger_ev_10d` and `trigger_ev_sign`**
  although `build_trigger_block` computes them (L653–658). [OBSERVED]
— Pass 2 writes: one file at `output_path`, which is L807
  `output_path = pathlib.Path(output_csv_path) if output_csv_path else input_path` —
  in production `superbrain/eil_enriched_{run_id}.csv` (`intelligent_orchestrator.py:4770`,
  path from `:4712-4715`). Columns written: all fifteen of `TRIGGER_CSV_COLUMNS`
  (L670–686), assigned L847–861. Write at L888–891.
— Atomic promotion? **No** — direct write to the input path.
— Schema/version field? NONE.
— Fields carrying authority claims: `trigger_go_eligible`. Claim L597–598 "Trigger
  observations are retained even when source data is explicitly stale; capital
  eligibility is handled separately" → **HOLDS** (`evaluate_triggers` L600–618 has no
  staleness gate; the gate is at L637).

**Handoff** — Pass 1 receives `packages/*.package.json`; hands the sidecar to pass 2.
Pass 2 receives `eil_enriched`; hands the fifteen trigger columns **only into
`eil_enriched`**. Join keys: `ticker` only (L711–713), so a ticker with more than one
contract or direction collapses to a single trigger block. [OBSERVED] (GAP-128)

**The Execution-CSV question (hotspot 5), resolved.**
`execution/execution_v3_5_{run_id}.csv` is written at
`execution_intelligence_runner.py:3280` from the orchestrator's L4690 call.
`superbrain/eil_enriched_{run_id}.csv` is written separately at
`execution_intelligence_runner.py:3594`. `enrich_csv` runs at L4770 and targets
`eil_enriched` **only**. The only post-L4770 writers of the Execution CSV add McMillan
columns (`intelligent_orchestrator.py:5019-5025`). **All fifteen trigger columns are
therefore written after the Execution CSV was finalised, and none reaches it:**
`trigger_codes`, `trigger_count`, `trigger_primary`, `trigger_quality`, `trigger_score`,
`trigger_go_eligible`, `trigger_stale`, `trigger_freshness_state`, `trigger_data_asof`,
`trigger_age_sessions`, `trigger_freshness_reason`, `trigger_context_state`,
`trigger_context_reasons`, `trigger_ev_10d`, `trigger_ev_sign`. [OBSERVED] (CON-120)

**Missing-data handling**
— Input CSV absent → `{"patched": 0, "error": "FILE_NOT_FOUND"}` + warning (L809–811);
  empty → `"EMPTY_CSV"` (L820–822). The caller receives a dict, not an exception.
  §10-compliant? **Y** as a token, **N** as a handoff (the orchestrator continues).
— Sidecar read failure → **bare swallow** L730–731 `except Exception: return {}`, with no
  log line; pass 2 silently degrades to full recomputation from flat CSV fields.
  §10-compliant? **N** (GAP-129).
— Per-package failure → `log.warning` and skip (L1015–1016); the package contributes no
  sidecar row and `stats["patched"]` is not incremented. **N**.
— Vanguard CSV load failure (L947–948) and sidecar write failure (L1049–1050) → swallowed. **N**.
— Missing win-rate → EV `0.0` (L332–333), labelled `ev_sign="ZERO"` (L654–658) —
  identical to a genuine zero EV. §10-compliant? **N** (GAP-130).
— Unknown freshness → L284 `{"state": "UNKNOWN", …, "reason": "NO_EXPLICIT_SOURCE_AGE",
  "stale": False}` — unknown treated as not stale. **N**.
— `_str` collapses `"NONE"`, `"NULL"`, `"NAN"` and `""` to the same default (L149–154);
  an explicit `NONE` and an absent field are indistinguishable. **N**.
— Sidecar `.get` defaults mix types: `"count": row.get("trigger_count", 0)`,
  `"score": row.get("trigger_score", 0)`, `"go_eligible": row.get("trigger_go_eligible", False)`,
  `"stale": row.get("trigger_stale", False)` (L714–728) — present values are `str`,
  absent values are `int`/`bool`. **N** (GAP-131).
— `count <= 0` → silently replaced by `len(trigger_list)` (L745–746), so a genuine zero
  count is overwritten. **N**.

**Contradictions found here:** CON-119, CON-120, CON-121, CON-122
**Gaps found here:** GAP-128, GAP-129, GAP-130, GAP-131, GAP-132
**Comment/docstring claims audited:**
— L5 "Phase 8.6 — sits between Actuarial Enrichment (Phase 8.5) and EDE (Phase 9.5)."
  → **FALSE**: pass 1 runs at orchestrator L4421, before EIL (L4690) and before
  `inject_actuarial` (L4694). Only pass 2 is post-actuarial. (CON-121)
— L8–11 the linear stage chain "Vanguard → Options Intelligence → EIL → Actuarial
  Enrichment → [THIS MODULE] → EDE v4.1" → **PARTIAL**: describes pass 2 only; the
  module runs twice and the first run precedes EIL.
— L36–40 "Fix 12: enrich_csv() … Fixes the pipeline wiring gap where EDE could not read
  trigger data" → **PARTIAL**: it writes the columns into `eil_enriched`, but the
  Execution CSV — which is what `build_candidate_manifest` actually reads — still never
  receives them.
— L664–667 "EDE reads the EIL CSV — trigger columns were never present there, so
  ede_trigger_count=0 for every signal" → **PARTIAL**: fixed for `eil_enriched`; the same
  condition now persists on the Execution CSV.
— L790 "If inplace=True (default) overwrites the input file." → **FALSE**: `inplace`
  (L783) is never read after the signature; L807 overwrites the input whenever
  `output_csv_path` is falsy, regardless of `inplace`. (CON-122 / GAP-132)
— L293, L306–310 "Runtime EV — never stored in database." plus a numbered four-step
  fallback → **PARTIAL**: the numbered list omits the actual first path, L315–320.
— L241–245 "`catalyst_proximity`, `days_in_range`, `asof_date`, and `score_date` are
  deliberately excluded as source-age evidence" → **PARTIAL**: true for the first two;
  `asof_date` and `score_date` **are** used, as the anchor at L269.
— L46 "Fix 5: Staleness gate — catalyst_proximity=FAR excluded." → **FALSE for v2.2**:
  superseded by L223–224 where `FAR` produces `EARLY_FORMATION_ABSENT` context and no
  staleness; the v2.0 changelog entry was not retracted.
— L569 "Returns highest-weight trigger." → **HOLDS** (L575).
— L597–598 staleness/eligibility separation → **HOLDS**.
— L792 "Returns stats dict matching patch_run_packages format for orchestrator
  compatibility." → **PARTIAL**: the success shape matches (L828–839 vs L950–961); the
  error shapes at L811 and L822 omit every key but two.
**Confidence in this section:** HIGH — delegated targeted read; the ordering conclusion
is corroborated by `03_execution_order.md` and by the runner line numbers quoted.

---

### eod_candidate_engine.py

**Classification:** ORCHESTRATED analytic stage, last of the analytic stages (2,754 lines).
**Real execution position:** stage 40 of 51, evening. Invoked by
`intelligent_orchestrator.py::evening_workflow` L5091 (banner L5049), after trigger
pass 2 (L4770) and the handoff guard (L4806). [OBSERVED `03_execution_order.md` §2]
**Task in the process:** Builds the morning candidate manifest — the single artefact the
Morning Gate consumes — by merging the final execution artefact with horizon, wall-break,
discovery and vanguard sources, classifying tier, status, conviction and permission, and
writing `morning_candidates_{run_id}.csv` plus five secondary audit artefacts.

**Entry points:** `build_candidate_manifest` (L1688–L2728); a CLI `__main__` (L2742–2749).
**Imports (production):** `contracts/handoff_contract.enrich_dataframe_with_truth_packets`;
`vanguard/physics_state_engine.ensure_physics_fields`; `macro_quant_packet`;
`pipeline_interpreter/ma_inputs_sync.on_pipeline_complete` (L2723–2724). Three of these
are behind import-time `try/except Exception` blocks (L88–109) that fall back to
un-namespaced module paths. · **Imported by:** `intelligent_orchestrator.py`.
· **Broken/retired imports:** NONE, but the fallback imports at L88–109 mean a partial
installation silently binds a different implementation. [OBSERVED] (GAP-133)

**Inputs**
— Files/tables read — **every `read_csv` inside `build_candidate_manifest` or its helpers**:
  | file:line | call | artefact |
  |---|---|---|
  | L1735 | `df = pd.read_csv(eil_path, low_memory=False)` | the `eil_path` argument — in production `execution/execution_v3_5_{run_id}.csv` (`intelligent_orchestrator.py:5091`, path from `:5053-5058`); the CLI at L2746 passes `superbrain/eil_enriched_{run_id}.csv` |
  | L1753 | `_hdf = pd.read_csv(path, low_memory=False)` in `_load_horizon_csv` (L1750–1764) | `horizon_1_5d_{run_id}.csv` and `horizon_6_10d_{run_id}.csv` only, via L1766–1767 — **`horizon_11_20d_*.csv` is never loaded** |
  | L1786 | `wbs_df = pd.read_csv(wbs_path, low_memory=False)` | `superbrain/wall_break_scores_{run_id}.csv` |
  | L1806 | `disc_df = pd.read_csv(discovery_path, low_memory=False)` | `discovery/discovery_candidates_ultimate_{run_id}.csv` |
  | L1862 | `_vdf = pd.read_csv(_vp, low_memory=False)` | first existing of L1855–1857: `options/vanguard_signals_enriched_{run_id}.csv`, `vanguard/vanguard_signals_enriched_{run_id}.csv`, `vanguard/vanguard_signals.csv` |
  There is **no `read_json` and no `open()`** anywhere in the file. `horizon_summary`
  (L1696) arrives pre-parsed from `intelligent_orchestrator.py:5072`. [OBSERVED]
— **Join to `eil_enriched`: NONE.** The production `eil_path` is the Execution CSV, stated
  explicitly at `intelligent_orchestrator.py:5091-5094` ("this path is deliberately the
  final execution artifact, never the earlier EIL frame"). The four other reads target
  horizon, WBS, discovery and vanguard. Grep for `eil_enriched` in this file returns only
  comments (L1823, L1832–1833, L2313) and the CLI argument (L2746). [OBSERVED] (CON-123)
— **Reads of `trigger_*`:** the sidecar `trigger_layer_summary_{run_id}.csv` is **never
  read** (Grep returns no match). The column reads are L902, L903, L949, L965, L1233,
  L1333, L1373, L1630, L1631, L1653, L1654, L1669, L1680, L2277–2282, L2362–2366, L2403,
  L2413, L2519, L2549 — all against the frame loaded at L1735, i.e. the Execution CSV,
  where none of those columns exists (CON-120). [OBSERVED]
— **`layer2__*` consumption:** only two fields are actually read —
  L740 `layer2__edge_direction` (third-priority fallback inside `_direction_arbitration`)
  and L702 `layer2__forward_momentum_confidence` (fourth-priority fallback in
  `_normalise_current_contract`). Every other `layer2__` occurrence is a pass-through
  name in `PHASE2_LAYER2_FIELDS` (L197–228, copied at L2325–2326) or a merge column
  (L1829–1837). **`layer2__recommended_hold_days` does not appear in this file at all**,
  and neither does `layer2__win_rate_20d`. Hold-days never enter this stage. [OBSERVED] (GAP-134)
— Config/policy read: `MIN_RR = 0.0` (L120), `EOD_CARRY_FORWARD_STATUSES`,
  `OPTIONS_MISSING_TOKENS` (L125), `GOVERNED_DIRECTED_SIDES`.

**Logic and algorithms**
— Direction evidence resolution, `_direction_evidence` L1033–L1111 (called once, L1902).
— Contract normalisation, `_normalise_current_contract` L649–L705.
— EOD status ladder, `_eod_candidate_status` L~900–L970.
— Tier classification, `classify_tier` L1626–L1686.
— Structural conviction score, `structural_conviction_score` L1529–L1620.
— Exit plan, `_exit_intelligence_plan` L1247–L1290.
— Slate direction-skew discount, L2376–L2400.
— Decision branches (direction):
  * **CALL path / PUT path / other-blank path** per construct:
    | file:line | construct | CALL | PUT | other/blank |
    |---|---|---|---|---|
    | L302–328 `_invalidation_level` | `direction != "PUT"` | below entry | above entry | **CALL-shaped** |
    | L1268, L1272–1280 `_exit_intelligence_plan` | `direction_u == "CALL"` | upward target, `t3 = max(...)*1.03` | downward | **PUT-shaped** |
    | L730–736 `_audit_side` | 8 synonyms | 9 synonyms | `return ""` |
    | L1018–1031 `_contract_side` | `"C0"` / endswith `C` / delta > 0 | `"P0"` / endswith `P` / delta < 0 | `return ""`; `delta == 0` also `""` |
    | L877–897 macro PUT gate | untouched | advisory tags `PUT_MACRO_BLOCKED` | untouched |
    | L1067–1071 | — | — | `final_direction not in GOVERNED_DIRECTED_SIDES` → `contract_reselection_required = True`, blanking 22 contract fields (L1114–1148) |
  * L1904 `row["direction"] = direction or "UNRESOLVED"` — the literal `"UNRESOLVED"`
    then enters every direction-consuming helper. [OBSERVED]
  * **The same unresolved row therefore carries a CALL-shaped invalidation (L2006,
    L2295) alongside a PUT-shaped target and exit ladder (L2049–2055), with
    `exit_invalidation_price` (L1288) holding the CALL-shaped number inside the
    PUT-shaped plan.** [OBSERVED] (CON-124)

**Computations and formulas (exact)**
— `_invalidation_level` (L302–328), verbatim decisive lines:
  L316 `if direction != "PUT" and stop < signal:` → returns the discovery stop only when
  it sits below the signal price;
  L323 `return round(signal - atr * 1.5, 2)` → level below entry;
  L327 `return round(signal * 0.97, 2)` → level 3 % below entry.
  For direction ∉ {CALL, PUT} — `UNRESOLVED`, `STRANGLE`, `NONE`, `""`, `NAN` — **every
  non-PUT test is taken, so a CALL-shaped level is returned. It does not return `None`,
  does not return `0`, and does not raise.** The terminal `return None` (L328) is reached
  only when `signal_price` is falsy and no usable stop exists, i.e. it signals missing
  price data, never an unresolved direction. It also never consults `governed_direction`,
  `final_direction`, `canonical_direction` or `selected_contract_side`. [OBSERVED]
— `dte = _flt(row, "dte", 30)` (L1918) — an invented default of 30 that then drives
  `_expected_move_window(30)` → `"1-10d"` (L265–266) and is written as the candidate's
  `dte` (L2187).
— `horizon_size_multiplier` default `1.0` (L1941–1943) — full size from absent data.
— Structural conviction: EV points, composite points, warnings points (L1563–1592);
  WBS contributes **zero** (L1571–1573 `bd["wbs"] = f"… -> advisory only"`), so the
  maximum achievable score is 85 while `round(min(100, score), 1)` (L1620) advertises a
  100 ceiling. [OBSERVED] (CON-125)
— Tier A gate L1664–1671: `ois >= 35 and rr >= 1.5 and comp >= 55 and (eil_verdict ==
  "EXECUTE" or catalyst_ready) and (trigger_ready or campaign_ready or options_power)`.
  Tier B L1676–1682: `comp >= 50` plus a five-way disjunction. Neither inspects `wbs_grade`.
— Slate discount `.mul(0.80)` (L2398).
— Merge guards L1883, L1889, L1895 test membership in a tuple containing `float("nan")`;
  since `nan != nan` that member never matches. The vanguard guard at L1895 additionally
  includes `0.0, 0`, so a vanguard column overwrites a genuine zero while the WBS and
  discovery guards do not. [OBSERVED] (CON-126)

**Models** — `structural_conviction_score` (L1529) and `_shadow_opportunity_score`
(L1373) are deterministic weighted scores. Parameters as quoted above.
Calibration source claimed: **none**. Version tag: **none**.
`_structural_conviction_score_legacy` (L1411–L1527) is dead — never called.

**Outputs**
— Primary: `morning_validation/morning_candidates_{run_id}.csv`, written L2715–2718
  `out_df.to_csv(output_path, index=False)`.
— Secondary, all conditional on `output_path`: `direction_transition_matrix_{run_id}.csv`
  (L2462–2471); `eod_dropoff_audit_{run_id}.csv` (L2527–2529);
  `missed_opportunity_shadow_book_{run_id}.csv` (L2570–2574);
  `regime_watch_{run_id}.csv` (L2592–2593);
  `morning_blocked_review_{run_id}.csv` (L2653–2657).
— **Atomic promotion? No** — no temp file, no `os.replace`; Grep for
  `os.replace|\.tmp|atomic` returns no match, for any of the six. [OBSERVED]
— **Schema/version field? None** — Grep for `schema_version` returns no match. The
  nearest provenance is `authority_source_stage` / `authority_source_path` (L2100–2101),
  with the stage derived by filename prefix at L1725–1729
  (`"FINAL_EXECUTION" if …startswith("execution_v3_5_") else "LEGACY_NONFINAL"`).
— Column list source: four layers — the ~240-key literal L1947–L2324; the dynamic append
  loops L2325–2336 (`PHASE2_LAYER2_FIELDS`, `SCANNER_FIELD_NAMES`, `PHYSICS_FIELDS`,
  `MACRO_QUANT_CSV_FIELDS`, `CATALYST_TRUTH_FIELDS`, and `ev3_authority_columns` built at
  L1737–1739 from whatever `ev3_`-prefixed columns the input happens to carry, so the
  output width varies with the input); post-frame columns L2374, L2417, L2432, L2445–2447;
  and `ensure_physics_fields` L2664 plus `enrich_dataframe_with_truth_packets` L2666–2672.
  `"signal_type"` and `"momentum_tier"` are defined twice (L2236–2237 and L2319–2320);
  the later literal silently wins. [OBSERVED] (GAP-135)
— Fields carrying authority claims: `maturation_score_is_probability` and
  `maturation_execution_authority` are hardcoded `False` regardless of input
  (L2034–2035) → **HOLDS**. `eod_candidate_authorized` / `execution_authorized` default
  `False` (L2098–2099) → **HOLDS**.

**Handoff** — Receives `execution/execution_v3_5_{run_id}.csv` plus horizon, WBS,
discovery and vanguard artefacts. Hands `morning_candidates_{run_id}.csv` to
`morning_gate.py::run_morning_gate` (`morning_gate.py:2780`).
Join keys: `ticker` for every merge (L1883, L1889, L1895); `run_id` in the filenames.

**Missing-data handling** (condition → emitted value, file:line)
— `trigger_count` absent (always, on the Execution CSV) → `0.0` (L2279), indistinguishable
  from "evaluated, zero triggers". §10-compliant? **N**.
— `trigger_score` absent → `0.0` (L2280). **N**.
— `trigger_go_eligible` absent → `""` (L2281) — not `"FALSE"`, not `"NOT_EVALUATED"`. **N**.
— `trigger_quality` / `trigger_primary` / `trigger_codes` absent → `""` (L2277–2282),
  while `trigger_layer.py:640` uses the explicit token `"NONE"` for a genuinely empty set. **N**.
— `dte` absent → `30` (L1918). **N**.
— `horizon_size_multiplier` absent → `1.0` (L1941–1943). **N**.
— `sb_warnings_count` absent → `0.0` → 10 conviction points (L1590–1592): absence scores
  identically to a clean, fully-vetted signal. **N**.
— `rr_flag` absent → `"RR_OK"` (L2220) — a positive assertion manufactured from absence. **N**.
— `wbs_grade` absent → `""`, and `_exit_intelligence_plan` L1262–1264 then selects the
  `SCALE_AT_WALL` / 60-25-15 plan as if a grade had been observed. **N**.
— Contract quote absent → three different renderings of one semantic class:
  `0.0` (L2205–2212, L2203), `nan` (L2204, L2209), and `0.0` via `_spread_pct_from_row`
  (L1151–1155). **N**.
— `horizon_bucket` absent → `"unrouted"` (L1939); `horizon_action` absent → `"UNKNOWN"`
  (L1940); `capital_permission` absent → `"MANUAL"` (L525); PCR absent → `"MISSING"` +
  `"NO_PCR_VOLUME_OR_OI_SIGNAL"` (L806, L815); `direction_integrity_status` →
  `"PENDING_MORNING_VALIDATION"` (L1096). §10-compliant? **Y** for these five.
— Horizon CSV load failure → `log.warning` and degrade to the row's own bucket or
  `"unrouted"` (L1763–1764). **Y**.
— Vanguard load failure → `log.warning`; `rr_underlying` then resolves to `0.0` (L1869–1872). **N**.
— **`SLATE_DIRECTION_SKEW_GUARD` (L2418–L2431) calls `logger.warning(...)` at L2429, but
  the module logger is bound to `log` at L116 and `logger` is never defined in this file.
  The `NameError` is discarded by the bare `except Exception: pass` at L2430–2431. The
  guard therefore can never fire, and its failure is never reported.** [OBSERVED] (GAP-136)
— Frame-level absence: `full_out_df.get(col, pd.Series(...))` (L2380, L2403, L2421–2424,
  L2533–2535, L2620–2622) silently substitutes an empty Series for a missing column, so
  the absence is invisible at runtime. **N** (GAP-137).

**Contradictions found here:** CON-123, CON-124, CON-125, CON-126, CON-127
**Gaps found here:** GAP-133, GAP-134, GAP-135, GAP-136, GAP-137, GAP-138
**Comment/docstring claims audited:**
— L22 "1. Loads the EIL-enriched CSV (or superbrain_execute as fallback)" → **FALSE**:
  production passes the Execution CSV; there is no `superbrain_execute` fallback anywhere.
— L1704–1705 "eil_path — Legacy parameter name. Production must pass the final
  execution_v3_5_{run_id}.csv authority artifact." → **HOLDS**.
— L2313 "Carried from pse_* fields in eil_enriched.csv." → **FALSE**: the source frame is
  the Execution CSV.
— L1822–1824 "rr_underlying … not propagated into eil_enriched by the EIL runner."
  → **PARTIAL**: the merge works (L1893–1896); the stated provenance no longer matches.
— L17 "EOD must not gate on live IV, spread, or drift." → **FALSE**:
  `_contract_repair_profile` L1174–1182 gates on `contract_spread_pct` /
  `eil_spread_pct_live` and sets `contract_repair_required`, which becomes the terminal
  status `EOD_THESIS_READY_REPAIR_AT_OPEN` (L940–941); `_eod_candidate_status` L943–947
  additionally gates on `liquidity_state != "EXECUTABLE_NOW"`. (CON-127)
— L44 "STRUCTURAL CONVICTION SCORE … WBS Wall Strength 15%" → **FALSE**: L1571–1573
  awards no points, yet the header table still lists six weights summing to 100 %.
— L1531–1532 "WBS and position sizing are advisory only; they do not add or remove
  conviction points." → **HOLDS**.
— L32 "TIER A — Top-quartile OIS (≥35) + RR ≥ 1.5 + WBS PROBABLE + conv_score ≥ 3"
  → **FALSE**: L1664–1671 never inspects `wbs_grade`, and `comp >= 55` is undocumented.
— L33 "TIER B — … WBS POSSIBLE + conv_score ≥ 2" → **FALSE** (L1676–1682, no WBS term).
— L34 "C — … (OIS ≥ 15, RR > 0)" → **PARTIAL**: `MIN_RR = 0.0` (L120) and the test is
  `rr < MIN_RR` (L1646), so `rr == 0` passes.
— L48–65 "OUTPUT SCHEMA (morning_candidates_{run_id}.csv) — Required by
  morning_validation.py:" then ~30 names → **PARTIAL**: the listed names are present, but
  the real width is ~240 literal keys plus six dynamic groups.
— L1720–1722 "v4.1: Horizon context is now stamped onto every candidate row"
  → **PARTIAL**: `_load_horizon_csv` is called only for 1-5d and 6-10d (L1766–1767);
  an 11-20d ticker present only in `horizon_11_20d_*.csv` falls back to `"unrouted"`. (GAP-138)
— L1746–1747 "Horizon CSV is the authoritative source; EIL CSV is the fallback" → **HOLDS** (L1939).
— L24 "Merges discovery-layer fields (stop_loss, VWAP, crabel, etc.)" → **HOLDS** (L1804–1819).
— L980–982 "The former implementation reconstructed and locked a second direction
  authority. Direction governance explicitly prohibits that behaviour." → **HOLDS**
  (L984–985; `footprint_lock_status = "DECOMMISSIONED_GDR_AUTHORITY"` L1088–1089).
— L557–559 "candidate_status is intentionally stricter than eod_candidate_status" → **HOLDS**.
— L2376–2378 "Slate-level direction conflict guard … discount all candidate scores by 20%."
  → **HOLDS** (L2398).
— L2429 "SLATE_DIRECTION_SKEW_GUARD" → **FALSE**: undefined `logger`, swallowed NameError.
— L2646 "B2 FIX: Remove EIL BLOCKED rows from morning candidates manifest" → **HOLDS** (L2648–2663).
— L989 "Compatibility shim: catalysts trigger review, not silent thesis rewrites."
  → **HOLDS**, but dead (L996 `return False`; never called).
— L999 "Consume the governed final direction without re-deriving it." → dead
  (`_candidate_direction` never called). Likewise `_side_from_text` (L1006–1016).
**Confidence in this section:** HIGH — delegated targeted read; each of the five critical
questions (reads, eil_enriched join, trigger reads, `_invalidation_level`, `layer2__`)
was resolved with a verbatim quote of the decisive line.

---

### intelligence-lab/intelligence_lab.py

**Classification:** LAB — a Flask read-path application serving already-produced run
artefacts (3,396 lines). Not an orchestrated stage.
**Real execution position:** NOT_APPLICABLE — not called by `evening_workflow` or
`premarket_workflow`. Served by `app.run(..., threaded=True, ...)` (L3396).
**Task in the process:** Loads a run's artefacts, normalises and aliases their columns
into display names, computes a priority score and ranking, and serves the result to the
cockpit UI; it also provides trade-entry and trade-exit endpoints that write to the
trade journal.

**Entry points:** the Flask routes named below; `_load_run` (L1164); `_latest_manifest`
(L341); `app.run` (L3396).
**Imports (production):** `contracts.lab_control` (L112–122) — `write_final_run_manifest`,
`load_final_run_manifest`, `apply_lab_resolution`, `apply_latest_compatible_overlays`,
`read_final_opportunity_book`; the trade journal and `outcome_capture` imported inline
via `sys.path.insert` (L2571, L2815, L3129, L3247, L3299).
**`write_final_opportunity_book` is never imported and never called here.** [OBSERVED]
· **Imported by:** NONE (application entry point). · **Broken/retired imports:** NONE;
but the `eil__` prefix is **never produced** by `_load_run` (EIL rows are the base dict,
L1184) while being read at L862–L865, L1072, L1077, L1107, L1135–L1140 — those reads are
dead in every current run and always fall through to the bare name. [OBSERVED] (GAP-139)

**Inputs**
— Files/tables read: `runs/{run_id}/superbrain/eil_enriched_*.csv`,
  `execution/execution_v3_5_*.csv`, `options/options_intelligence_*.csv`,
  `superbrain/wall_break_scores_*.csv`, `qomega/garch_forecasts_*.csv`,
  `morning_validation/morning_validated_trades_*.csv`, `morning_candidates_*.csv`,
  `core_intel/core_intel_dossiers_*.json`, `intelligence_lab/final_opportunity_book_*.json`,
  `final_run_manifest.json`, and the trade journal SQLite `_JOURNAL_DB`.
  Readers: L149 `open(path, newline='', encoding='utf-8-sig')`, L159 `open(path, encoding='utf-8')`.
— Upstream fields consumed: the `sb_*`, `opt__`, `mv__`, `wbs__`, `garch__l3_*`, `eil__`,
  `exe__`, `vg__`, `doss__`, `eod__` and `v5_*` families, catalogued in the
  pre-governance census below.
— External calls: `fetch_current_mark(pos)` (L3064) in the monitor endpoint.
— Config/policy read: `_LAB_COMPACT_PREFIXES` (L2203–2207); the STRANGLE display policy
  (default `INCLUDE_LABELLED`, L108).

**Logic and algorithms**
— Run loading and caching, `_load_run` L1164–L2166 (cache signature L1168–1171,
  store L2166).
— Direction resolution, `_side_from_value` L1397–L1411 and `_normalise_direction_value`
  L1464–L1491.
— Priority score, L866–L900.
— Convexity ladder, L1058–L1152.
— Governed-book name projection, `_governed_ui_projection` L2226–L2330.
— Decision branches (direction):
  * **PUT path:** L1403 `if "PUT" in text or "SHORT" in text or text in ("BEARISH",
    "SELL", "DOWN"):` → `return "PUT"` (L1404). PUT is tested **first**, and
    `"SHORT" in text` is a substring test, so any string containing `SHORT`
    (e.g. `SHORT_HORIZON`, `SHORT_TERM`) resolves to PUT. [OBSERVED] (CON-128)
  * **CALL path:** L1405 `if "CALL" in text or text in ("BULLISH", "BUY", "UP"):`
    → `return "CALL"` (L1406).
  * **Other/blank path:** L1411 `return "" if text in ("", "NONE", "NEUTRAL", "STRANGLE",
    "UNKNOWN") else text` — recognised non-directional markers → `""`; **anything else
    unrecognised is returned verbatim as if it were a side**. [OBSERVED] (CON-129)
  * STRANGLE: `_is_strangle_nondirectional` L1447–1449 fires only on a **present**
    marker (L1445), sets `lab_coherence_status = "STRANGLE_NONDIRECTIONAL"` (L1586–1592)
    and is protected from EOD overwrite at L1856–1867. A row with a **blank,
    non-STRANGLE** direction receives **no** `lab_coherence_status` at all. [OBSERVED] (GAP-140)
  * `_direction_coherence` L1493–L1508 flags a conflict only when **both** sides are in
    {CALL, PUT} (L1502); a blank canonical or blank source side is never flagged.
  * Counting: L2411–2415 uses substring tests (`"PUT" in direction`) while L2925–2926
    uses exact equality — blank and STRANGLE rows are counted in neither, so the sector
    call/put split and the `call_put_ratio` denominator silently exclude them. (CON-130)
  * **`direction` defaults to `"PUT"` at two sites:** L2654
    `direction = sig.get("direction","PUT").upper()` inside `api_enter_trade`
    (`/api/enter_trade`, POST) and L2771 in the unreachable block. If the `direction` key
    is **absent**, the trade is contracted and journalled as a PUT
    (`create_contract` L2674, `log_entry` L2698). [OBSERVED] (CON-131)

**Computations and formulas (exact)**
— `w_ev2 = min(max((ev_adj + 0.25) / 0.50, 0), 1) * 0.10` (L886) — EV is 10 % of the
  priority score.
— `wbs_mult = {"PROBABLE": 1.0, "POSSIBLE": 0.6, "UNLIKELY": 0.2}.get(wbs_g, 0)` (L895) —
  **`IMMINENT`, the highest grade (counted separately at L2113), is absent from the map
  and therefore scores 0, identically to an unknown grade.** [OBSERVED] (GAP-141)
— `w_gar = (1.0 if tail < -0.03 else 0.5 if abs(tail) <= 0.03 else 0.1) * 0.05` (L899) —
  a missing GARCH tailwind (`0.0`) falls into the mid bucket and scores as if measured.
— `bonus = 3 if eil_c >= 80 else 2 if eil_c >= 65 else 1 if eil_c >= 50 else 0` (L1108).
— Position size from a **defaulted** composite of 50: L1727–1729
  `eil_c = float(sig.get("eil_composite_score",50) or 50)` → `… else 35` → a non-zero
  35 % size derived from absent data. [OBSERVED] (GAP-142)
— `max_expected_mae = entry_underlying * 0.5` (L2686).

**Models** — Priority score (L866–900) and the convexity ladder (L1058–1152) are
deterministic weighted scores. Calibration source claimed: **none**. Version tag: **none**.

**Outputs — writes on the read path (hotspot 10)**
| Line | Function | Trigger | Route / methods |
|---|---|---|---|
| **346** | `_latest_manifest()` (L341) | HTTP handler, indirect | `/api/orchestrator/status` (L2492, GET) via L2494; `/api/orchestrator/manifest/latest` (L2518, GET) via L2520 |
| **1945** | `_load_run(run_id, force_reload=False)` (L1164) | HTTP handler, indirect, **on every cache miss** | `/api/run/<run_id>` (L2473, GET), `/api/run/latest` (L2477, GET), `/api/export_csv` (L2838, GET) via L2845, `/api/enter_trade` (L2565, POST) via L2598 |
| **2527** | `api_orchestrator_manifest(run_id)` | HTTP route handler, direct | `/api/orchestrator/manifest/<run_id>`, GET |
| **2604** | `api_enter_trade()` | HTTP route handler, direct | `/api/enter_trade`, POST |
All four line numbers verified. Verbatim: L346
`return manifest or write_final_run_manifest(run_id, RUNS_DIR)`; L1945
`run_manifest = write_final_run_manifest(run_id, RUNS_DIR, _infer_pipeline_mode(eil_rows, mv_rows))`;
L2527 `manifest = load_final_run_manifest(run_id, RUNS_DIR) or write_final_run_manifest(run_id, RUNS_DIR)`;
L2604 `manifest = payload.get("final_run_manifest") or write_final_run_manifest(run_id, RUNS_DIR)`.
**None is at module-import scope; none is on a background thread**; each executes in the
serving request thread. [OBSERVED]
— **L2527 has no run-directory existence guard** (contrast `_load_run` L1166
  `return {"error": f"Run folder not found: {run_id}"}`). A GET to
  `/api/orchestrator/manifest/<any string>` therefore creates
  `RUNS_DIR/<any string>/` (via `lab_control.py:1217` `run_dir.mkdir(parents=True,
  exist_ok=True)`) and writes `final_run_manifest.json` into it. [OBSERVED] (GAP-143)
— **SQLite writes:** `ALTER TABLE` DDL at L585 inside `_ensure_lab_journal_columns`
  (L579), called at L593, L724, L742 and L3318 — i.e. also from the pure-GET routes
  `/api/outcomes` (L3283) and `/api/learning_feedback` (L3370) via `_closed_trade_rows()`.
  `UPDATE trades` + commit L709–713 (`/api/enter_trade` POST, called L2709);
  `UPDATE closed_trades` + commit L727–731 (`/api/log_exit` POST, called L3205). [OBSERVED] (GAP-144)
— **Other external writers from routes:** `create_contract(` L2673 and `log_entry(` L2690
  (`/api/enter_trade` POST); `log_exit(` L3195 (`/api/log_exit` POST).
  `create_contract(` at L2780 is **unreachable** — it sits after the unconditional
  `return jsonify({` at L2710 whose dict closes at L2741; **L2743–L2805 is dead code**. [OBSERVED] (GAP-145)
— No `to_csv`, `to_json`, `os.replace`, `shutil` or `Path.write_text` appears anywhere in
  the file. `json.dump` never appears (only `json.dumps`). The CSV export at L2879–2883
  is `io.StringIO` only. [OBSERVED]
— Atomic promotion? **No** — the manifest write is `target.write_text(...)`
  (`lab_control.py:1219`), no temp file, no `os.replace`.
— Schema/version field? The Lab does not stamp one; the book carries
  `lab_schema_version = "lab_signal_book_v2"` from `lab_control.py:2908`.

**Pre-governance / prefixed column reads (hotspot 10c).** Canonical names taken from the
file's own reverse alias table `_governed_ui_projection` (L2246–L2313).
— `opt__`: prefix applied L1752. Reads at L622 (`opt__options_strategy` ← `instrument`),
  L623/L1958/L2656 (`opt__contract_strike` ← `strike`), L624/L1959/L2657/L1929
  (`opt__contract_expiry` ← `expiry`), L625/L2658 (`opt__contract_dte` ← `dte`), L626
  (`opt__premium_mid` ← `premium_mid`), L627 (`opt__contract_spread_pct` ← `spread_pct`),
  L631/L1098/L2704 (`opt__structural_target` ← `structural_target`/`target_price`),
  L1448/L1475/L1480, L1611 (`opt__final_route`), L1663–1664/L2663 (`opt__hold_urgency`),
  L1798/L1801 (written), L1076/L1081/L1087/L1088, L1428, L866, L867.
— `sb_`: L622/L1568/L1570/L1576/L1579/L2655/L2772 (`sb_instrument_now` ← `instrument`),
  L657/L1555/L1598/L1603 (`sb_campaign` ← `convexity_campaign`), L658/L1599/L1605
  (`sb_execution_mode`), L1597/L1601/L2019/L2033/L2035/L2036/L2405/L2747/L2856
  (`sb_final_verdict` ← `lab_verdict`), L1716/L1920 (`sb_conv_score` ← `convexity_score`),
  L1720 (`sb_verdict_reason` ← `entry_reason`), L1930 (`sb_checkpoint_rule`), L1929
  (`sb_time_stop_date`), L1924/L2309 (`sb_current_stage` ← `readiness_stage`),
  L1927/L2310, L1925/L2318, L1926/L2320, L1666–1677/L2328, L1734–1735, L1915–1919
  (no canonical equivalent — Lab-computed), L2321 (`sb_stages_missed = 0`, hardcoded,
  no source).
— `mv__`: prefix applied L1791 (note the `mv_` strip at L1790). Reads at L675, L676,
  L1525, L1625/L1628, L1632/L1635, L1805–1818, L933/L943/L950/L959, L1040.
— `wbs__`: prefix applied L1768. Reads at L1930, L1769–1772 (written), L868, L869,
  L1087–1088, L1097; aliases L2287–L2295.
— `garch__l3_*`: prefix applied L1784. Reads at L870 and L1082
  (`garch__l3_iv_tailwind_score` ← `garch_iv_tailwind_score`); aliases L2296–L2303.
— `eil__`: read at L862–865, L1072, L1077, L1107, L1135, L1136, L1138, L1140 — **never
  produced**, always dead (GAP-139).
— Whole prefix families are passed straight to the browser: L2203–2207.

**Handoff** — Receives run artefacts and, when present, the governed opportunity book.
Hands JSON to the browser, contract files to Vanguard (`create_contract` L2673) and rows
to the trade journal (`log_entry` L2690, `log_exit` L3195). Join keys: `run_id`, `ticker`,
`trade_idea_id` (L1958–1961).

**Missing-data handling** (selected; full census in the register)
— File absent or unreadable → `[]` / `{}` with no state token (L147, L153, L157, L163). **N**.
— Run-scoped source absent → `_glob_first` L168 `return matches[-1] if matches else None`
  — **a different run's file is silently loaded under the current `run_id`** (used at
  L1182, L1191, L1199–1203, L1212, L1236–1238, L1247, L1259–1261, L189, L195, L199). **N** (CON-132).
— Journal unreadable → `[]` (L354–355), silently disabling the duplicate-trade veto
  (`lab_control.py:1569`). **N**.
— Numeric absent → `0.0` (L442, L451, L457) and specifically L676, L681, L686, L699. **N**.
— Convexity input absent → `"N"` (L1073, L1078, L1083, L1093, L1100) — absence rendered
  as a failed check, indistinguishable from a genuine no. **N**.
— Verdict blank → `"WAIT"` (L1594–1596); campaign unmapped → `"WATCHLIST"` (L1555). **N**.
— v5 row absent → `direction_conflict = "FALSE"` (L1743–1744) — absence asserted as
  no-conflict. **N**.
— `win_rate_source` → `"ACTUARIAL"`/`"STRUCTURAL"` from a numeric presence test (L1711),
  never unknown. **N**.
— Sector missing → `"N/A"` (L2391); no executes → `concentration_flag = "NORMAL"` (L2428);
  no governed WBS → `wbs_avg_score = 0` (L2114–2115); `"win_rate_bridge_count":0` hardcoded
  (L2158). **N**.
— Entry defaults: `ev2_p_win_blended` → `0.5` (L2668, L2778); `eil_composite_score` →
  `"MODERATE"` (L2669, L2779); ADX/ATR → `20`/`50` (L2684, L2791); regime/trend/structure
  → `"TRANSITIONAL"`/`"NEUTRAL"`/`"NEUTRAL"` (L2678–2682); catalyst proximity hardcoded
  `"UNKNOWN"` (L2683); horizon → `"20D"` (L2660, L577). **N**.
— Export filter values unparseable → `except: pass` at L2861/L2866 → **the row passes the
  filter and is included**. **N** (GAP-146).
— Entry premium zero at exit → `pnl_pct = 0.0` (L3186–3187) — undefined rendered as flat. **N**.
— Explicit tokens that are §10-compliant: `"UNCATEGORISED"` (L547), `"UNKNOWN"` (L559),
  `"ALIGNMENT_NOT_AUDITED"` (L1643–1644), `"NO_MORNING_BATON"` (L1646),
  `"PENDING_MARKET_OPEN"` / `"EOD_PREP_PENDING_VALIDATION"` (L1832–1833),
  `"LEGACY_IN_MEMORY_ASSEMBLY"` (L1989–1993), `"run_not_loaded"` (L2387),
  `current_mark = None` / `action = "REVIEW"` (L3066–3079), `rr_realised = None` (L3190–3192).
— Bare `try/except: pass` or silently-swallowing handlers: L276–279, L333–334, L354–355,
  L436–437, L450–451, L456–457, L586–587, L715–716, L733–734, L748–749, L855–856, L1067,
  L1802, L1892, L2420–2421, L2651–2652, L2769, L2833, L2861, L2866, L2944, L2965,
  L3065–3066, L3072–3073, L3179–3180, L3338–3339. L715–716 and L733–734 report a failed
  journal metadata write to **stdout only**, while the HTTP response at L2710 still says
  `"ok": True`. [OBSERVED] (GAP-147)

**Contradictions found here:** CON-128, CON-129, CON-130, CON-131, CON-132, CON-133, CON-134
**Gaps found here:** GAP-139 … GAP-147
**Comment/docstring claims audited:**
— L9 "EIL/options/execution remain legacy read-only fallback sources" → **HOLDS** for
  those CSVs.
— L10 "one pipeline writer owns membership, provenance and reconciliation" → **PARTIAL**:
  true for the book, false for membership when the book is absent (L1989
  `result["lab_signal_source"] = "LEGACY_IN_MEMORY_ASSEMBLY"`), and false for the run
  manifest, which this process writes at four sites. (CON-133)
— L11 "macro and EV remain advisory; morning validation owns live action" → **PARTIAL**:
  macro is advisory (L804 `"risk_switch": "ADVISORY_ONLY"`); EV is 10 % of the priority
  score (L886) and drives ranking; and morning validation does not own live action when
  absent — L2654 proceeds to `create_contract`/`log_entry` on the Lab's own resolution.
— L1943–1944 "This is validation/normalisation only; it does not create signals."
  → **PARTIAL/FALSE as to side effects**: the very next line, L1945, writes
  `final_run_manifest.json` to disk from a browser GET. (CON-134)
— L1994–1996 "MSI display is additive and non-authoritative … the sole source of
  membership and trading authority." → **FALSE as written**: L1980
  `result["signals"] = [dict(row) for row in governed_book.get("rows", [])]` replaces
  membership wholesale, and under `lab_v3_view` the source is the v3 handoff manifest
  (L259–275), not the final opportunity book. The overlay half **HOLDS**
  (L2001, authority stamped `ADVISORY_EVIDENCE_ONLY` L2006).
— L2226–2229 "deliberately a name-only projection. It must not rescore, rerank, infer
  execution permission, or otherwise reinterpret the governed row." → **PARTIAL/FALSE**:
  it does not rerank, but it computes L2317–L2321 and synthesises
  `position_size_display` at L2323–2327 (`"0% - MORNING VALIDATION REQUIRED"` /
  `"0% - MANUAL REVIEW"`), which is an execution-permission statement.
— L1441 "Must not fire" on empty → **HOLDS** (L1445).
— L1452–1453 "options_direction is the authoritative signal for whether this setup is
  single-sided at all." → **HOLDS as scoped** (authoritative only for the non-directional
  veto, L1459). It is **not** authoritative for the side itself: it sits tenth in the
  candidate list (L1474).
— L1565 "Do not fabricate selected_contract_side; it is contract expression, not thesis
  authority." → **HOLDS in this file**; contradicted downstream by `lab_control.py:1870`,
  which places `selected_contract_side` inside the direction chain, and by L1875 / L646–671
  which re-select the contract symbol to match.
— L3011–3012 "Read-only view … no writes." → **PARTIAL**: `run_monitor` is dry-run
  (L3038), but the route makes outbound market-data calls (L3064), so "read-only" is true
  of the DB, not of the process.
— L3230–3231 "only /api/log_exit closes a journal row." → **HOLDS** (L3251 `dry_run = True`
  unconditional; the body parameter is ignored, as L3234 states).
— L256 "immutable v2 EOD book remains the review-only source." → **HOLDS narrowly**
  (`read_final_opportunity_book` L2943–2945 is read-only), but the enclosing read path
  writes the manifest.
— L277–279 "An invalid or unaccepted v3 baton must never be displayed." → **HOLDS**, with
  the caveat that the bare `except Exception:` at L276 swallows I/O and import errors
  identically to validation failures, so a transient read error silently demotes a valid
  accepted v3 baton to v2 with no state token recorded.
— L1826–1827 EOD-manifest override "should override advisory defaults when present"
  → **HOLDS**, and the direction carve-out at L1856–1867 is honoured.
— **Undocumented and contradicted:** `/api/outcomes` (L3286 "Closed trade performance
  summary") and `/api/learning_feedback` execute DDL via L3318 and L742.
**Confidence in this section:** HIGH for the write inventory, the four
`write_final_run_manifest` sites, the direction branches and the prefix census — all
verified with verbatim quotes. MEDIUM for exhaustiveness of the fallback census: the
file is 3,396 lines and the sweep was pattern-driven.

---

### contracts/lab_control.py

**Classification:** ORCHESTRATED contract module (3,003 lines).
**Real execution position:** stages 46 and 47 of 51, evening —
`write_final_run_manifest` at `intelligent_orchestrator.py:5639` (defined
`contracts/lab_control.py:1210`) and `write_final_opportunity_book` at L5654 (defined
`contracts/lab_control.py:2831`). Also called from the Lab read path
(`intelligence_lab.py` L346, L1945, L2527, L2604).
**Task in the process:** Derives the final run manifest from artefact presence, row
counts and column checks; and assembles the final opportunity book — the governed row set
the Lab displays — from a per-field source-priority merge across the run's CSVs.

**Entry points:** `build_final_run_manifest` (L1018–L1207), `write_final_run_manifest`
(L1210–L1220), `load_final_run_manifest`, `resolve_lab_tradeability` (L1374–L1765),
`apply_lab_resolution` (L1774–L1794), `opportunity_book_row` (L1860–L2350),
`write_final_opportunity_book` (L2831–L2940), `read_final_opportunity_book` (L2943–L2945),
`apply_latest_compatible_overlays`.
**Imports (production):** `contracts.options_liquidity_execution_guard` (L21 — **both**
`evaluate_olm_execution_guard` and `action_is_within_guard`);
`contracts.direction_governance.validate_direction_record`;
`pipeline_interpreter.ma_inputs_sync.on_pipeline_complete` (L2903).
· **Imported by:** `intelligent_orchestrator.py`, `intelligence-lab/intelligence_lab.py`.
· **Broken/retired imports:** NONE.

**Inputs**
— Files/tables read by `build_final_run_manifest` (via `_output_files` L944–L987):
  `<run>/discovery/*discovery*{run_id}*.csv`, `<run>/options/vanguard_signals_enriched_{run_id}.csv`
  (or any `<run>/vanguard/*.csv`), `<run>/superbrain/eil_enriched_{run_id}.csv`,
  `<run>/execution/execution_v3_5_{run_id}.csv`, `<run>/options/options_intelligence_{run_id}.csv`,
  `<run>/superbrain/AVSHUNTER_SIGNALS_V5_*.csv`,
  `<run>/morning_validation/{morning_validated_trades,morning_candidates,morning_validation_packet}_{run_id}.*`,
  `<run>/core_intel/core_intel_dossiers_{run_id}.json`,
  `<run>/superbrain/superbrain_summary_*.json`,
  `<run>/diagnostics/{dropoff_audit,handoff_contract_audit}_{run_id}.csv`,
  `<run>/macro/*.json` or `<run>/*macro*.json` (L982–986), and
  `<run>/ev3_shadow/ev3_shadow_phase_status_{run_id}.json` (L1037–1038).
— Files read by `write_final_opportunity_book` via `_lab_extract_source_paths`
  (L2377–L2390): `morning_validated_trades`, `execution_v3_5`, `superbrain/eil_enriched`,
  `superbrain/wall_break_scores`, `options/options_intelligence`,
  `options/vanguard_signals_enriched`, `vanguard/vanguard_signals_enriched`,
  `qomega/garch_forecasts`, `morning_validation/morning_candidates` — each SHA-256'd
  (L2716–2719) and manifested (L2721–2727).
— **No database reads in either writer.** [OBSERVED]
— Config/policy read: `_lab_field_source_priority` (L2535–L2575); `FINAL_BOOK_FIELDS`;
  the legacy verdict translation table L1405–L1423.

**Logic and algorithms**
— Phase status and health scoring, L1057–L1170.
— Lab tradeability resolution, `resolve_lab_tradeability` L1374–L1765 (verdict assignment
  L1617–L1731).
— Economics-identity enforcement, `_enforce_economics_identity` L866–L899.
— OLM lab guard, `_enforce_olm_lab_guard` L1798–L1857 — this is where
  `action_is_within_guard` is used, L1823
  `if action_is_within_guard(current_action, decision) and current_action in {`.
— Per-field source-priority merge, `_enrich_lab_extract_rows_from_run_sources` L2697–L2828.
— Governed display recomputation, `_recompute_governed_lab_fields` L2579–L2694.
— Decision branches (direction):
  * Direction is re-derived **three times** with **three different chains**:
    L1870 `canonical_direction = first(sig, "final_direction", "canonical_direction",
    "resolved_direction", "direction", "options_direction", "selected_contract_side",
    "option_direction")`; L2604 `direction = _side_from_value(first(row,
    "canonical_direction", "direction"))`; and L1862 for the trade-idea id, defaulting to
    `"UNKNOWN"`. None matches the Lab's own chain at `intelligence_lab.py:1464-1486`
    (no `footprint_direction`, no intent/factor inference, no STRANGLE veto). [OBSERVED] (CON-135)
  * **CALL path:** L2642 `row["wbs_break_direction"] = "UP" if direction == "CALL" else "DOWN"`;
    L2656 `aligned = (direction == "PUT" and pcr_num > 0.8) or (direction == "CALL" and pcr_num < 0.4)`.
  * **PUT path:** the WBS legacy correction applies to `direction == "PUT"` **only**
    (L2615) — see below.
  * **Other/blank path:** L2641 guards `direction in {"CALL","PUT"}` for
    `wbs_break_direction`, so a blank direction leaves it unset; but the L2615 PUT-only
    guard means **a row whose direction failed to resolve keeps the legacy five-point
    bonus** the correction exists to remove. [OBSERVED] (CON-136)

**Computations and formulas (exact)**
— Health: `health = 100`; `-= 30 * len(fatal_flags)`; `-= 8 * …`; `-= 5 * …`;
  `-= 3 * len(stale_flags)` (L1120–1125).
— `run_tradeable = not fatal_flags and not morning_validation_pending and not
  morning_validation_paper and phase_status["eil"] == "PASS" and row_counts.get("eil",0) > 0`
  (L1127–1133).
— **WBS numeric alteration:** L2615–2617
  `if pcr_unavailable and direction == "PUT" and legacy_pcr_state_missing and not
  _is_missing(row.get("wbs")): corrected_wbs = max(0.0, _f(row.get("wbs"), 0.0) - 5.0);
  row["wbs"] = round(corrected_wbs, 1)`; L2619 the same −5.0 on `wbs_f5_momentum`; and
  L2620–2625 the categorical grade **re-derived from the altered numeric**
  (`IMMINENT ≥75, PROBABLE ≥55, POSSIBLE ≥35, else UNLIKELY`). [OBSERVED]
— Re-ranking: L2365 `order = {"GO": 0, "GO_LIMIT": 1, "PROBE": 2, …}`, assigning
  `lab_rank` / `priority_rank` (L1910–1911) and overriding the Lab's own ranking.

**Models** — NONE fitted. The verdict ladder, the health score and the readiness ladder
are deterministic rule sets. Calibration source claimed: none.

**Outputs**
— `write_final_run_manifest` L1216–1219: `run_dir.mkdir(parents=True, exist_ok=True)`
  then `target.write_text(_json_safe(manifest), encoding="utf-8")` to
  `<run>/final_run_manifest.json`. **Not atomic** — no temp file, no `os.replace`, no
  lock; a concurrent reader can observe a truncated file. **No schema/version field** —
  the payload (L1172–1207) carries `run_id`, `created_at_utc`, `pipeline_mode`, but no
  `schema_version`. [OBSERVED] (GAP-148)
— `write_final_opportunity_book`: `final_opportunity_book_{run_id}.csv` (L2883–2888),
  `lab_triage_view_{run_id}.csv` (L2890–2894), `final_opportunity_book_{run_id}.json`
  (L2939 `json_path.write_text(...)`). **Three separate direct writes, no
  temp-and-rename, no cross-file transaction** — the CSV and JSON can diverge if the
  process dies between L2888 and L2939. **Schema/version field present:** L2908
  `"lab_schema_version": "lab_signal_book_v2",` and per row at L1905. [OBSERVED]
— Side-effecting external write: L2897–2905 `_ma_on_pipeline_complete(str(triage_csv_path),
  output_dir=str(out_dir))`, wrapped in `except Exception: pass` (L2904–2905) — a failed
  Pipeline Interpreter sync is silent. (GAP-149)
— Fields carrying authority claims:
  `maturation_execution_authority = False` hard-set unconditionally (L2323) → **HOLDS**.
  `macro_data_role = "ADVISORY_ONLY"` (L2182) and `macro_authority` (L2204) → **HOLDS**:
  no macro field participates in `resolve_lab_tradeability` or `_recompute_governed_lab_fields`.
  `ev3_production_authority = False` (L1205) → **HOLDS**.
  `"morning_capital_permission": run_execution_permission` (L1196) — **a capital-permission
  field set from a pipeline-completeness verdict, not from the Morning Gate**. (CON-137)

**Business logic recomputed here (hotspot 15).** This module does **not** copy; it
derives. Recomputed rather than carried:
— **Direction** — L1870, L2604, L1862 (three chains, CON-135).
— **Instrument** — L1871–1874 `aligned_instrument = _instrument_for_direction(...)`
  (L619–635), written at L1986.
— **Contract symbol** — L1875 `aligned_contract, contract_alignment_flag =
  _contract_for_direction(sig, canonical_direction)`; L646–671 **re-selects a different
  OCC symbol** when the incumbent side does not match, L666
  `return candidate, f"CONTRACT_RESELECTED_FOR_DIRECTION:{original}->{candidate}"`;
  written at L1987. [OBSERVED] (CON-138)
— **Verdict / tradeability** — L2363–2364 runs `apply_lab_resolution(sig, manifest)` for
  any signal without a pre-set verdict, deriving `lab_verdict`, `lab_tradeable`,
  `conflict_state`, `execution_lock_reason`, `requires_live_validation`, `prep_permission`
  (assignment L1617–L1731, e.g. L1641–1645 `verdict = "GO"; tradeable = True`).
— **Verdict overwritten by economics identity** — L2320 `_enforce_economics_identity`
  blanks EV (L868, L874, L878) and rewrites the verdict (L894–898 to `CONTRACT_REPAIR`
  across five fields). Run a **second** time at L2694.
— **Verdict overwritten by the OLM guard** — L2321 `_enforce_olm_lab_guard` (L1798–1857)
  rewrites verdict, action, category and sizing (L1848–1857) and can flip
  `economics_comparable` (L1840).
— **Direction integrity** — L2325 `validate_direction_record(row)`, then L2334–2348
  `lab_verdict = "BLOCKED"` (L2336), `final_action = "BLOCK"` (L2339),
  `position_size_display = "0% - direction integrity failed"` (L2343).
— **WBS score and grade** — L2615–2625 (arithmetic then re-grade).
— **WBS break direction and momentum alignment** — L2642, L2657.
— **Readiness ladder** — L2672–2687.
— **R:R contract binding** — L1894–1898 and L2810–2812.
— **Ranking** — L2365–2372.
— **Data-state tokens** — L1988, L2129, L2268, L2271, L2294, L2298, L2308.

**Fallback chains bridging two semantic types (selected).**
— L2210 `"target_price": first(sig, "target_price", "wbs__wall_price", "structural_target",
  "opt__structural_target"),` — *thesis price target ← gamma/OI wall price*.
— L2212 `"structural_target": first(sig, "structural_target", "opt__structural_target",
  "wbs__wall_price", "target_price"),` — the **mirror** of L2210. If both are absent and
  only `wbs__wall_price` exists, both columns become the wall price and appear to
  corroborate one another; if only one exists, the other silently becomes it. (CON-139)
— L2455 `"structural_target": ["structural_target", "opt__structural_target",
  "target_price", "wbs__wall_price"],` — the same bridge with `target_price` and
  `wbs__wall_price` in the **opposite order** from L2212, so the field can resolve
  differently depending on which code path filled it. (CON-140)
— L2814–2815 `if _is_missing(row.get("structural_target")) and not
  _is_missing(row.get("target_price")): row["structural_target"] = row.get("target_price")`
  — a **third** application, **not recorded in `provenance`**, so `field_provenance_json`
  (written L2826) shows `structural_target` as unsourced. (GAP-150)
— **L2291 `"trigger_quality": first(sig, "trigger_quality", "trigger_score"),` — the
  categorical←numeric bridge.** The result is consumed as a label at L597–598
  `if not _is_missing(quality) and _u(quality) not in {"0","0.0","0.00","FALSE","NO"}:
  parts.append(_s(quality))` — a numeric score is concatenated into `trigger_evidence` as
  though it were a quality word, and **any non-zero score reads as a positive quality**.
  The enrichment alias table at L2434 `"trigger_quality": ["trigger_quality"],` does
  **not** carry this fallback, so the two paths disagree. [OBSERVED] (CON-141)
— L2290 / L2293 `trigger_primary` ↔ `trigger_codes` mutual fallback — a single populated
  field makes both look populated, and `trigger_data_state` (L2294, from L1901) reports
  `AVAILABLE` on the strength of either. (CON-142)
— L2292 `"trigger_score": first(sig, "trigger_score", "trigger_count"),` — *score ← count*.
— L2295–2296 `hard_vetoes` ↔ `options_hard_vetoes` mutual, plus *options vetoes ← Lab `veto_flags`*.
— L1921–1923 a three-way cycle among `eod_candidate_status`, `execution_category` and
  `action_category`, plus *category ← route ← lane ← permission*.
— L2205–2206 `eil_signal_verdict` ↔ `eil_v3_verdict`, then *governed verdict ← advisory verdict*.
— L2213–2215 `underlying_price` ↔ `signal_price` ↔ `scanner_price` mutual — a stale
  scanner print can become the live underlying.
— L2217–2218 `runway_to_target` ↔ `runway_to_wall_pct` — a distance and a percentage.
— L2284–2286 `hold_window`, `time_horizon` and `hold_period` all drawn from
  `{horizon_bucket, hold_window, hold_label, opt__hold_label}` in different orders.
— L2783 `candidates = exact_rows if len(exact_rows) == 1 else ticker_rows if
  len(ticker_rows) == 1 else []` — *this trade idea ← any row for this ticker*, flagged
  `AMBIGUOUS_JOIN` only when >1 (L2787).
— L2769 `row[field] = "" if _is_missing(value) else value` — WBS fields **destructively
  blanked** when `wall_break_scores` has no row, discarding values `opportunity_book_row`
  had already placed at L2256–2270. (GAP-151)
— L1397 / L1405–L1423 — when `mv_execution_permission` is empty, permission is
  manufactured from a **legacy verdict translation table** (`"EXECUTE": "GO"`,
  `"STARTER": "PROBE"`, …). (CON-143)

**Handoff** — Receives the run's artefacts. Hands `final_run_manifest.json` and the
opportunity book (CSV + triage CSV + JSON) to the Lab, and the triage CSV to the Pipeline
Interpreter. Join keys: `run_id`, `trade_idea_id` (composed L1861–1866), `ticker`,
`contract_symbol`.

**Missing-data handling** — largely §10-compliant, with explicit tokens:
`"MISSING"` / `"WARN"` / `"FAIL"` (L1011–1015); `"PENDING"` / `"NOT_REQUIRED"` (L998–1001);
`"NOT_RUN"` (L1195); `"NOT_APPLICABLE_NO_SELECTED_CONTRACT"` (L1988);
`"MISSING_DATA_DEFECT"` (L2129, L2298, L2649); `"NOT_AVAILABLE"` (L2294);
`"NOT_APPLICABLE_NOT_SCORED"` (L2268); `"NOT_GOVERNED"` (L2271); `"NOT_RUN_EOD"` (L2308);
`"UNAVAILABLE"` / `"UNAVAILABLE_LEGACY_BONUS_REMOVED"` / `"UNAVAILABLE_NO_INTRADAY_PCR"`
(L2636, L2626, L2653); `"UNAVAILABLE"` for `win_rate_source` (L2664);
`"NO_ACTIONABLE_EXECUTION_CONFIRMATION"` (L1652–1655); `"EV_NOT_EVALUATED"` (L1598–1599);
`"EOD_MISSING_LIVE_SPREAD"` (L1526–1527); `SOURCE_READ_FAILED:` (L2729–2733);
`AMBIGUOUS_JOIN:` (L2765–2767); `CONTRACT_JOIN_REJECTED:` (L2800–2805). §10-compliant? **Y**.
Non-compliant residue:
— `conflict_state` absent → `"CLEAN"` (L1976) — unknown rendered as clean. **N**.
— `lab_verdict` absent → `"WAIT"` (L1912, L1915). **N**.
— Economics not comparable → `ev_predicted = ""` (L868, L874, L878) — EV blanked rather
  than tokenised; the state lives only in `economics_mismatch_reason`. **N**.
— Unknown field at write-out → `""` (L2350). **N**.
— Unscored row sorts as zero (L2369). **N**.
— Booleans absent → `False` (L1913, L1979, L2050, L2064, L2069, L2070). **N**.
— Interpreter sync failure → silent (L2904–2905). **N**.

**Contradictions found here:** CON-135 … CON-143
**Gaps found here:** GAP-148, GAP-149, GAP-150, GAP-151
**Comment/docstring claims audited:**
— L3–5 "This module is deliberately small and deterministic. It does not create signals;
  it validates and normalises the committed pipeline baton" → **PARTIAL/FALSE**: it
  creates no rows, but it creates values (L2616, L2620–2625, L2642, L2657, L1875,
  L1617–1731). "Small" is contradicted by 3,003 lines and a 482-key row literal (L1904–2319).
— L2579–2582 "These fields are direct state/alias derivatives, not new trading models.
  Missing market inputs remain explicit and can never become favourable defaults."
  → **PARTIAL**: "direct alias derivatives" is false for L2616–2625 (arithmetic then
  re-grade); "never favourable" **HOLDS** for that correction (it subtracts) and for
  L2660–2664 and L2645–2649.
— L2610–2613 the legacy-PCR correction rationale → **HOLDS within a run** (guard L2614;
  WBS re-sourced each run at L2760–2769), with the asymmetry noted at CON-136.
— L2757–2759 "WBS is producer-owned. Copied values in later handoff CSVs must never
  outrank wall_break_scores or make an unscored candidate look scored." → **HOLDS**,
  enforced by blanking at L2769, with the consequence recorded as GAP-151.
— L2535–2538 "Authoritative source order for one normalized Lab field … field-level."
  → **HOLDS** (L2540–2575).
— L2781–2782 "Ticker fallback is permitted only when that source is unambiguously
  one-to-one." → **HOLDS** (L2783), noting that "one-to-one" is measured per ticker
  within one file, not against the run.
— L889–890 "Morning permission is immutable after the Execution Gate." → **PARTIAL**:
  the guard is only `final_action` emptiness (L891); when blank, L894–898 rewrite five
  verdict fields, and `_enforce_olm_lab_guard` L1848–1857 overwrites `final_action` itself.
— L1590–1591 "R:R is retained only as research telemetry … Morning permission comes
  exclusively from final_action." → **HOLDS for R:R** (no `rr_*` term in L1617–1731);
  **PARTIAL** for the second clause — L1657–1698 branches on `mv_execution_permission`,
  which is manufactured from a legacy verdict table when empty (L1397, L1405–1423). (CON-143)
— L1802 "Verify the Execution Gate baton without granting positive authority." → **HOLDS**:
  every branch at L1830–1857 downgrades; L1823–1826 only preserves an already-restrictive action.
— L2322–2324 "Liquidity-maturation scores … must never be reinterpreted as execution or
  capital authority." → **HOLDS** (L2323 hard-set, unconditional).
— L1145–1147 "EOD prep is intentionally not execution-tradeable until live morning
  validation runs." → **HOLDS** (L1129, L1154–1158).
— L508 "ceiling is never labelled GO" → **HOLDS** (L1517–1520, L1724–1731).
**Confidence in this section:** HIGH for the two writers, the recompute inventory and the
named fallback chains — all verified with verbatim quotes. MEDIUM for exhaustiveness of
the 482-key row literal: it was sampled at the fields relevant to the hotspots, not read
key by key.

---

### swing_fusion.py

**Classification:** ORCHESTRATED analytic helper (261 lines).
**Real execution position:** not a stage. Called inside Discovery (stage 10, evening) at
`avshunter_discovery_ULTIMATE.py:1368`.
**Task in the process:** Fuses Wyckoff phase, operator, control state and Crabel state
into a direction, an intent and an alignment score, with a precor audit block attached.

**Entry points:** `fuse_wyckoff_crabel` (L~60, returns L110–117).
**Imports (production):** `enums_structural` only (L25–27).
· **Imported by (live tree, complete):** `avshunter_discovery_ULTIMATE.py` (L64, L1368,
L1377, L2039–2047); `scenario_router.py` (L92–93, L117, L143); `execution_intelligence_runner.py`
(L270, L899); `wyckoff_crabel_precor_logic_v2.py` (comments only, L9, L21, L218);
`test_macro_redesign.py` (L22). Everything else is under `backups/`.
· **Broken/retired imports:** NONE.

**Inputs** — Files/tables read: NONE. Upstream fields consumed: `current_phase`,
`operator`, `control_state`, `truth_confidence`, `phase_evidence_strength`,
`contradictions` from `wyckoff`; `state`, `score` from `crabel`; the whole `precor` dict
for audit only. External calls: NONE. Config/policy read: `enums_structural`.
**Macro read: NONE** — no import, open, read or key lookup for `bond_macro_state.json`,
`macro_quant_packet.json`, `macro_intelligence_latest.json`, regime, risk-on/off or VIX.
[OBSERVED]

**Logic and algorithms**
— Direction rule, L131–135:
  `if control == ControlState.BUYERS and operator in Operator.LONG_OPERATORS: return
  Direction.LONG` / `if control == ControlState.SELLERS and operator in
  Operator.SHORT_OPERATORS: return Direction.SHORT` / `return Direction.NONE`.
— Alignment score with penalties, L~170–187 (`return max(0.0, min(100.0, score)), notes`).
— Intent ladder, L210–235.
— Decision branches (direction):
  * **LONG path:** L131–132. * **SHORT path:** L133–134.
  * **Other/blank path:** L135 `return Direction.NONE` — every combination that is not
    BUYERS+LONG_OPERATOR or SELLERS+SHORT_OPERATOR. Fail-closed. [OBSERVED]
  * **Note the value domain is `LONG` / `SHORT` / `NONE`, not `CALL` / `PUT`.** [OBSERVED]

**Computations and formulas (exact)**
— `alignment_score` clamped to [0, 100] (L187).
— Unknown phase penalty `score -= 30` (L178–180).
— Contradiction penalty at `len(contradictions) >= 2` (L183).
— Intent: `alignment_score < 50 → OBSERVE_ONLY` (L209–210); evidence `< 30 →
  OBSERVE_ONLY` (L218); `direction == NONE` excluded at L221.

**Models** — Deterministic rule set with hand-set penalty constants. Calibration source
claimed: none. Version tag: none.

**Outputs** — Files written: NONE. Returns `direction`, `intent`, `alignment_score`,
`contradictions`, `fusion_rule_fired`, `audit` (L110–117). Atomic promotion?
NOT_APPLICABLE. Schema/version field? NONE.
— Fields carrying authority claims: none in the values. The module docstring claim is
audited below and is **FALSE**.

**Handoff** — Receives Wyckoff, Crabel and precor dicts from Discovery.
Hands `fusion_direction` / `fusion_intent` / `fusion_alignment_score` back to Discovery,
which writes `discovery_direction_preliminary` and stamps
`'direction_authority': 'DISCOVERY_PRELIMINARY_ONLY'`
(`avshunter_discovery_ULTIMATE.py:2036-2038`). Its outputs reach only sizing and lane
routing downstream (`scenario_router.py:117-143`, invoked from
`execution_intelligence_runner.py:899-902`). Join keys: `ticker`.

**Missing-data handling**
— Missing `current_phase` → `UNKNOWN` (L64), then treated as an **observed** penalty
  state (`score -= 30`, L178–180) and a blocking state (L213–214). §10-compliant? **N**.
— Missing `operator` → `UNCLEAR` (L65) → fails both operator sets → `NONE`. **Y** (fail-closed).
— Missing `control_state` → `UNKNOWN` via `ControlState.normalise` (`enums_structural.py:48`)
  → cannot produce a direction. **Y**.
— Missing `truth_confidence` / `phase_evidence_strength` → `0.0` (L68–69), numerically
  identical to measured-zero evidence; the direction is still fail-closed but the audit
  block at L101 records a fabricated `0.0`. §10-compliant? **N**.
— Missing `crabel.state` → `NONE` (L75), indistinguishable from a measured
  no-compression state. **N**.
— Non-list `contradictions` → L71–73 `list(raw_contradictions)`: **a string would be
  exploded into one entry per character**, inflating `len(contradictions)` past the `>= 2`
  penalty threshold at L183. **N**. (GAP-152)
— L235 `return Intent.OBSERVE_ONLY, "fallback — no rule matched"` is an **unreachable
  dead branch**: L221 already excludes `NONE`, so L229 or L233 always fires. (GAP-153)

**Contradictions found here:** CON-144, CON-145
**Gaps found here:** GAP-152, GAP-153, GAP-154
**Comment/docstring claims audited:**
— L6 "Single authority for direction and intent." → **FALSE**. See the trace in the
  direction-authority resolution below. (CON-144)
— L7 "Precor/WyckoffEngine feed DATA; this module makes the DECISION." → **FALSE** —
  the relationship is inverted in practice: precor's `intent`
  (`wyckoff_crabel_precor_logic_v2.py:219`) is the decisive input to `structural_direction`
  via `avshunter_discovery_ULTIMATE.py:2077-2082` →
  `scripts/avshunter_options_intelligence.py:3792` → `:3878`. (CON-145)
— L56 "Used only for audit enrichment — NEVER overrides fusion decision." (of `precor`)
  → **HOLDS locally** (precor reaches only `_extract_precor_audit`, L107, L238–248),
  **FALSE globally** by the same trace.
— L239 "Pull key precor fields for audit — never used for decisions." → **HOLDS**.
— L201 "alignment_score < 50 → OBSERVE_ONLY (fail closed, per spec)" → **HOLDS** (L209–210).
**Confidence in this section:** HIGH — file read in full; the consumer census is a
repository-wide Grep confirming five live consumers.

---

### asymmetry_gate_swing.py

**Classification:** ORCHESTRATED analytic helper (194 lines).
**Real execution position:** not a stage. Called inside Discovery (stage 10, evening);
its result feeds the stop/target hierarchy at `avshunter_discovery_ULTIMATE.py:1777-1788`.
**Task in the process:** Computes a shelf-geometry entry, stop and first target, and
returns whether the reward-to-risk clears a minimum.

**Entry points:** `compute_asymmetry_swing` (L~40, returns L136–148); `_fail` (L155–168);
`_compute_shelf` (L~170); `_compute_atr14` (L~190).
**Imports (production):** `numpy`, `pandas`, `enums_structural` (L29–33).
· **Imported by:** `avshunter_discovery_ULTIMATE.py`. · **Broken/retired imports:** NONE.

**Inputs** — Files/tables read: NONE. Upstream fields consumed: `direction`
(parameter, L50, in the `LONG`/`SHORT`/`NONE` domain), `crabel_result.shelf_high` /
`shelf_low` / `shelf_width` (L76–78), `df_daily` bars, `cfg`. External calls: NONE.
Config/policy read: `asymmetry_breakout_buffer` and two siblings via
`getattr(cfg, name, default)` (L71–73).
**Macro read: NONE.** [OBSERVED]

**Logic and algorithms**
— Shelf resolution with recomputation fallback, L76–L88.
— R:R computation and pass test, L~110–124.
— Decision branches (direction): the module **consumes** direction; it does not emit one.
  The CALL/LONG and PUT/SHORT geometry is applied inside the entry/stop/target
  construction. **Other/blank path:** `NONE` is an admissible input value and is not
  rejected at the signature; the geometry then proceeds on whichever branch the code
  falls into. [OBSERVED]

**Computations and formulas (exact)**
— `asymmetry_pass = R >= min_r` (L124).
— `shelf_width = float(shelf_high) - float(shelf_low)` when absent **or non-positive** (L87–88).
— On failure, `_fail()` returns `"R_to_T1": 0.0` (L160).

**Models** — NONE.

**Outputs** — Files written: NONE. Returns `entry`, `stop`, `target1`, `R_to_T1`,
`asymmetry_pass`, `reason`, `shelf_high`, `shelf_low`, `shelf_width`, `atr14`, `error`
(L136–148). Atomic promotion? NOT_APPLICABLE. Schema/version field? NONE.
— **Outputs no direction and no intent.** The only decision-shaped output is the boolean
  `asymmetry_pass`. [OBSERVED]

**Handoff** — Receives a direction and Crabel shelf geometry from Discovery.
Hands `stop` and `target1` into the Discovery stop/target hierarchy
(`avshunter_discovery_ULTIMATE.py:1783-1788`), which is the authoritative source of
`stop_loss` for the whole downstream pipeline. Join keys: `ticker`.

**Missing-data handling**
— Any required value missing → `_fail()` with `asymmetry_pass=False` (L155–168). **Y** for
  the boolean.
— **`_fail()` emits `"R_to_T1": 0.0` (L160) — a failure state rendered as a number,
  numerically identical to a legitimately computed zero-reward setup.** Consumed at
  `avshunter_discovery_ULTIMATE.py:2046` and, critically, at `:2059` inside an `or`
  chain — `(asymmetry_result.get('R_to_T1') or round((atr_14 * 3.0) / …, 2))` — where the
  failure `0.0` is falsy and **silently falls through to an ATR-derived R:R**.
  §10-compliant? **N**. (CON-146 / GAP-155)
— Missing shelf from Crabel → recomputed from a 30-bar high/low window (L81–82), so a
  shelf Crabel deliberately declined to emit is silently replaced. **N**.
— Missing width **and** measured non-positive width treated identically (L87–88). **N**.
— Absent config attribute → hard-coded default (L71–73), with no record of which was used
  in the returned dict. **N**.
— `_compute_shelf` L173–177 and `_compute_atr14` L193–194: `except Exception: return None`
  — a DataFrame schema error is indistinguishable from absent bars. **N**.
— `reason` carries a `"PASS: …"` / `"FAIL: …"` grammar on success and a bare cause on
  failure — two string grammars in one field (L147). **N**.

**Contradictions found here:** CON-146, CON-147
**Gaps found here:** GAP-155, GAP-156
**Comment/docstring claims audited:**
— L24 "Rule: if any required value is missing → asymmetry_pass=False, intent degrades to
  OBSERVE_ONLY." → **PARTIAL**: the first half holds (L155–168); **the second half is not
  implemented anywhere** — no `intent` is written in this file, and the caller at
  `avshunter_discovery_ULTIMATE.py:2040` copies `fusion_intent` from `fusion_result`
  with no reference to `asymmetry_result`. (GAP-156)
— L7 "Replaces ALL hardcoded stop_loss = price * 0.97 usage in discovery." → **FALSE**:
  `avshunter_discovery_ULTIMATE.py:539` `stop_loss = current_price * 0.97` is still
  present, and `scripts/avshunter_options_intelligence.py:3808`
  `stop = float(_raw_stop) if _stop_authoritative else entry*0.97` reintroduces the same
  constant one stage later. (CON-147)
**Confidence in this section:** HIGH — file read in full.

---

### contracts/direction_governance.py

**Classification:** ORCHESTRATED contract module — **the de-facto direction authority**
(510 lines).
**Real execution position:** not a stage. `structural_direction` and
`resolve_governed_direction` are called inside stage 18
(`scripts/avshunter_options_intelligence.py:3878` and `:3886`);
`validate_direction_record` is called from `execution_gate.py:161`,
`morning_gate.py:205`, `contracts/lab_control.py:2325` and
`morning_handoff_finalizer.py:162-163`; `preliminary_discovery_direction` is called
inside Discovery (`avshunter_discovery_ULTIMATE.py:1580`).
**Task in the process:** Resolves a governed direction from a closed structural table,
admits independent evidence only to break a non-directional tie, emits a hashed
resolution record, and validates that record with a direction-aware price-topology check.

**Entry points:** `normalise_side` (L66–76), `structural_direction` (L79–95),
`preliminary_discovery_direction` (L98–104), `collect_resolution_evidence` (L134–205),
`resolve_governed_direction` (L231–348), `validate_direction_record` (L~365–480).
**Imports (production):** `hashlib`, `json`, `dataclasses`, `datetime`, `typing`
(L12–16) — **no file I/O at all**. · **Imported by:**
`scripts/avshunter_options_intelligence.py:114-115`, `execution_gate.py:10`,
`morning_gate.py`, `contracts/lab_control.py`, `morning_handoff_finalizer.py`,
`eod_candidate_engine.py`, `avshunter_discovery_ULTIMATE.py`.
· **Broken/retired imports:** NONE.

**Inputs** — Files/tables read: **NONE**. Every input is a key on the passed `row`;
the admissible evidence key list is `vanguard_edge_direction`, `layer2__edge_direction`,
`layer2__probability_direction`, `edge_direction`, the catalyst fields,
`directional_force`, and `relative_strength_20d` / `sector_relative_strength_20d` /
`rs_20d` (L148–202). External calls: NONE. Config/policy read:
`DIR_CALC_VERSION` (L19); `MIN_EVIDENCE_FAMILIES = 2`, `MIN_WINNING_SHARE = 0.60`,
`MIN_DIRECTION_MARGIN = 0.20` (L30–32); `EXCLUDED_DIRECTION_EVIDENCE` (L34–40).
**Macro read: NONE — no macro key appears anywhere in the file. Direction in this
pipeline is computed with zero macro input at every stage of this chain.** [OBSERVED]

**Logic and algorithms**
— Value domain, L23–28: `CALL = "CALL"`, `PUT = "PUT"`, `STRANGLE = "STRANGLE"`,
  `UNRESOLVED = "UNRESOLVED"`.
— **Closed structural table `structural_direction(intent, trend)` L79–95:**
  | `intent` | `trend` | returns | line |
  |---|---|---|---|
  | `BUY_SETUP` | ignored | `(CALL, "precor_intent=BUY_SETUP")` | L83–84 |
  | `SELL_SETUP` | ignored | `(PUT, "precor_intent=SELL_SETUP")` | L85–86 |
  | `TRANSITION` | `BULLISH` | `(CALL, …)` | L88–89 |
  | `TRANSITION` | `BEARISH` | `(PUT, …)` | L90–91 |
  | `TRANSITION` | `MIXED` / other / empty | `(STRANGLE, …)` | L92 |
  | `WAIT` | ignored | `(UNRESOLVED, "precor_intent=WAIT")` | L93–94 |
  | anything else (`OBSERVE_ONLY`, `""`, `NONE`, unknown) | ignored | `(UNRESOLVED, f"precor_intent={intent or 'MISSING'}")` | L95 |
  **For the defaults set at `scripts/avshunter_options_intelligence.py:3792-3793`
  (`intent='WAIT'`, `trend='MIXED'`) this returns `(UNRESOLVED, "precor_intent=WAIT")`.**
  `trend='MIXED'` is consulted only on the `TRANSITION` branch; under `WAIT` it is
  discarded. `swing_fusion`'s most common intent, `OBSERVE_ONLY`, also falls through to
  L95 and yields `UNRESOLVED`. [OBSERVED]
— **Precedence inside `resolve_governed_direction`:** structural first, L258–260
  `final_direction = governed`; evidence admitted **only** when `governed` is
  non-directional, L264–272 `if governed in NON_DIRECTIONAL and (winning_side in DIRECTED
  and len(supporting_families) >= MIN_EVIDENCE_FAMILIES and winning_share >=
  MIN_WINNING_SHARE and margin >= MIN_DIRECTION_MARGIN): final_direction = winning_side`.
  Order: **governed (structural) > evidence > preliminary (never)**. A CALL or PUT from
  `structural_direction` can never be overturned by contrary evidence.
  `discovery_direction_preliminary` — the swing_fusion-derived value — is explicitly
  disqualified at L34–40. [OBSERVED]
— Decision branches (direction):
  * **CALL path:** L84, L89, L72–73 (substring), L189 (`directional_force >= 5.0`),
    L200 (`relative_strength >= 0.02`), L270 (evidence majority).
  * **PUT path:** L86, L91, L70–71, L189, L200, L270 — symmetric.
  * **Other/blank path:** L92 → `STRANGLE`; L94, L95, L76, L104 → `UNRESOLVED`;
    `_first_side` → `""` (L131). **There is definitively no path in this file where a
    missing or ambiguous direction becomes CALL.** Every route to CALL requires a
    positive assertion. [OBSERVED]
  * Validator, L465–474: `CALL_TARGET_NOT_ABOVE_SIGNAL`, `PUT_TARGET_NOT_BELOW_SIGNAL`,
    `CALL_INVALIDATION_NOT_BELOW_SIGNAL`, `PUT_INVALIDATION_NOT_ABOVE_SIGNAL` —
    symmetric and equally enforced. Non-directional → L410–411
    `return False, f"DIRECTION_NOT_EXECUTABLE:{final_direction or 'MISSING'}"`. Fail-closed.

**Computations and formulas (exact)**
— `winning_side = CALL if call_score > put_score else PUT if put_score > call_score else ""` (L249).
— `winning_share` (L252) and `margin` (L253), both `0.0` when `total == 0`.
— `directional_force` → side by sign, admitted at `abs(force) >= 5.0`, weight
  `min(1.0, …)` (L187–192).
— `relative_strength` → side by sign, admitted at `>= 0.02` (L194–202).
— Record hash: `sort_keys=True` JSON then SHA-256 (L204–205, L321).

**Models** — **NONE**, asserted at L1–2 and true: all logic is table- and
threshold-driven.

**Outputs** — Files written: NONE. `resolve_governed_direction` returns 20 flat fields
including `discovery_direction_preliminary`, `governed_direction`, `final_direction`
(L332), `direction_resolution_path` ∈ {`DIRECTION_CONFIRMED`, `UNRESOLVED`,
`DIRECTION_RESOLVED_PRECONTRACT`} (L259, L271), `direction_governance_status` ∈
{`CONFIRMED`, `NOT_RESOLVED`, `RESOLVED`} (L260, L272), `direction_resolution_confidence`
∈ {`""`, `MEDIUM`, `HIGH`} (L263, L273), `direction_resolution_chain_json`,
`governed_direction_record_sha256`, `dir_calc_version`.
Atomic promotion? NOT_APPLICABLE. Schema/version field? `DIR_CALC_VERSION` (L19),
**enforced on read** at L375–376 and at `morning_handoff_finalizer.py:653-661`.
— Authority claim: L330 `"governed_direction_authority": "OPTIONS_INTELLIGENCE"` →
  **HOLDS** — a hard-coded self-label matching the call site at
  `scripts/avshunter_options_intelligence.py:3886`.

**Handoff** — Receives `intent`, `trend` and the raw row from Options Intelligence.
Hands the 20-field record onto the options row, thence to EIL, the EOD engine, the
Morning Gate, the Execution Gate, the Lab and the handoff finalizer.
Join keys: `ticker`, `run_id`.

**Missing-data handling**
— Every unmatched structural input → `UNRESOLVED` (L94–95, L76, L104). §10-compliant? **Y**.
— Non-directional `final_direction` at validation → `DIRECTION_NOT_EXECUTABLE:{value or 'MISSING'}`
  (L410–411). **Y**.
— L47 `return "" if text.upper() in {"", "NAN", "NONE", "NULL", "N/A"} else text` — **a
  genuine categorical `"NONE"`, which is exactly what `swing_fusion.py:135` emits, becomes
  indistinguishable from absent data.** §10-compliant? **N**. (CON-148)
— L92 the audit basis reports an empty trend as `MIXED`, i.e. missing data labelled as an
  observed state. **N**.
— L194–198 `relative_strength_20d or sector_relative_strength_20d or rs_20d` — **an `or`
  chain over numerics: a genuine `0.0` relative strength is falsy and silently falls
  through, so a ticker with exactly-zero RS can be scored using a sector RS value.**
  The same defect class the codebase guards against elsewhere
  (`scenario_router.py:110`). **N**. (GAP-157)
— L369–372 `row.get("final_direction") or row.get("canonical_direction") or
  row.get("resolved_direction") or row.get("direction")` — **the validator falls back to
  the legacy `direction` column, which Discovery populates with the preliminary value and
  stamps `'direction_authority': 'DISCOVERY_PRELIMINARY_ONLY'`
  (`avshunter_discovery_ULTIMATE.py:2037-2038`). A row that lost its governed fields is
  therefore validated against Discovery's preliminary hint.** **N**. (CON-149)
— L447–464 three 4-term `or` chains over numeric prices; all suppress a legitimate `0.0`,
  and if every alias is absent `_number` returns `None` and **the CALL/PUT coherence
  checks at L465–474 are skipped entirely — fail-open**. **N**. (GAP-158)
— L358–361, L385–388, L491–493 `except (TypeError, ValueError, json.JSONDecodeError)`
  returning `[]` / `{}` — typed, but a corrupt chain and a legitimately empty chain become
  indistinguishable; L422–423 then reports
  `DIRECTION_CHANGED_WITHOUT_RESOLUTION_CHAIN`. Fail-closed on the outcome. **Y** at the
  outcome, **N** at the diagnosis.
— No `try/except: pass`, no `setdefault` anywhere in the file. [OBSERVED]

**Contradictions found here:** CON-148, CON-149, CON-150
**Gaps found here:** GAP-157, GAP-158
**Comment/docstring claims audited:**
— L1–2 "The module deliberately contains no predictive model." → **HOLDS**.
— L5–7 "Generated targets, selected contracts, Discovery defaults and other
  direction-dependent outputs are never admitted as resolution evidence." →
  **HOLDS for `collect_resolution_evidence`** (L134–205 admits none of them),
  **FALSE for `validate_direction_record`** (L369–372). (CON-149)
— L80 "Closed, fail-closed structural direction table." → **HOLDS** (L94–95).
— L99 "Return a preliminary hint without ever defaulting ambiguity to CALL." → **HOLDS**
  (L104, L131).
— L139–140 "Multiple aliases of the same underlying model are deliberately
  de-duplicated." → **HOLDS** (`_first_side` L126–131 returns on first hit).
— L204 "Stable ordering is required for reproducible hashes and replays." → **HOLDS**
  (L205, L321).
— L330 `"governed_direction_authority": "OPTIONS_INTELLIGENCE"` → **HOLDS**.
— `enums_structural.py:15` "DO NOT define these strings in any other file." → **FALSE**:
  L23–28 defines an independent CALL/PUT/STRANGLE/UNRESOLVED vocabulary without importing
  `enums_structural`; the two are bridged only by substring matching at L70–73. (CON-150)
— L70–73 the `normalise_side` bridge: **PUT tokens are tested first**, so a string
  containing both (e.g. `"BULLISH_PUT_SPREAD"`) resolves to `PUT`; it also silently
  converts intents (`BUY_SETUP`→CALL, `SELL_SETUP`→PUT) into contract sides. [OBSERVED]
**Confidence in this section:** HIGH — file read in full; the precedence conclusion is a
direct read of L258–272.

---

### The direction-authority question, resolved (hotspot 11)

**Which module the comments call "the single authority":** `swing_fusion.py:6-7`
"Single authority for direction and intent. Precor/WyckoffEngine feed DATA; this module
makes the DECISION." Restated at `avshunter_discovery_ULTIMATE.py:60` and `:1360`, and at
`wyckoff_crabel_precor_logic_v2.py:21`.

**Which module actually governs:** `contracts/direction_governance.py::structural_direction`,
whose only inputs are `precor_intent` and `dominant_trend`. Trace, each step OBSERVED:
1. Discovery stores the fusion direction as a preliminary hint only —
   `avshunter_discovery_ULTIMATE.py:1580-1583` then `:2036-2038`
   `'direction_authority': 'DISCOVERY_PRELIMINARY_ONLY'`.
2. Options Intelligence reads `precor_intent` and `dominant_trend`, **not**
   `fusion_intent` / `fusion_direction` — `scripts/avshunter_options_intelligence.py:3792-3793`.
3. `structural_direction(intent, trend)` at `:3878`.
4. `resolve_governed_direction(...)` at `:3886-3895`, `direction = final_direction`.
5. `discovery_direction_preliminary` is on the excluded-evidence list,
   `contracts/direction_governance.py:34-40`.
A repository-wide Grep confirms **exactly one live writer of `precor_intent`** —
`avshunter_discovery_ULTIMATE.py:2077`, whose `raw_intent` is `precor_data.get('intent','')`
(`:2078`). **No file in the live tree writes `precor_intent` from `fusion_intent`.** The
swing_fusion → direction chain is severed by construction. [OBSERVED]

**Verdict on the comment: FALSE.** `swing_fusion.py` is de-facto a sizing and lane input
only (`scenario_router.py:117-143`, from `execution_intelligence_runner.py:899-902`).
`wyckoff_crabel_precor_logic_v2.py:9` ("It does NOT decide direction or intent — that is
swing_fusion.py's job"), `:21`, and `:229` (`"_precor_role": "AUDIT_ENRICHMENT"  # not
decision-making`) are **FALSE** by the same trace, in the opposite direction: the precor
module's `intent` is the sole structural input to the de-facto authority.

**Macro:** none of `swing_fusion.py`, `asymmetry_gate_swing.py` or
`contracts/direction_governance.py` reads any macro state. Direction is computed with
zero macro input at every stage of this chain. [OBSERVED] (Recorded as CON-151 against
AVS-E2E-DATA-LOGIC-001 §9 if that document asserts a macro contribution to direction;
noted here as a fact, not a defect.)

---

### contracts/handoff_contract.py

**Classification:** ORCHESTRATED contract module (615 lines).
**Real execution position:** not a stage. `enrich_dataframe_with_truth_packets` is called
from `eod_candidate_engine.py:2666-2672` (stage 40, evening);
`handoff_contract_audit.py` runs as stage 44.
**Task in the process:** Receives committed fields from competing writers, applies a
priority ladder and a status ladder, records conflicts, applies seven cross-field
coherence invariants, and passes the result forward as a "truth packet".

**Entry points:** `is_missing_value` (L227–239), `normalise_status` (L242–244),
`add_field` (L348–408), `validate_required` (L431–444), `apply_sovereign_gate` (L446–456),
`finalise` (L459–), `to_flat_dict` (L469–486), `to_json_dict` (L488–502),
`from_row` (L504–525), `_apply_row_coherence` (L527–562),
`enrich_row_with_truth_packet` (L575–585), `enrich_dataframe_with_truth_packets` (L588–605).
**Imports (production):** stdlib; `pandas` imported inside a try at L601–604.
· **Imported by:** `eod_candidate_engine.py`, `handoff_contract_audit.py`.
· **Broken/retired imports:** NONE.

**Inputs** — Files/tables read: **NONE.** No `open`, no `Path`, no `requests` anywhere in
the module. The read allowlist is `TRUTH_PACKET_CARRY_FIELDS` (L216–220, derived from
L112–214), and `from_row` copies only keys already present (L519–522
`for name in TRUTH_PACKET_CARRY_FIELDS: if name in row:`). External calls: NONE.
Config/policy read: `FIELD_STATUSES` (L18), `PACKET_STATUSES` (L19), `MISSING_TOKENS`
(L20), the priority ladder L22–31 (`PRIORITY_LIVE_EXECUTION = 100` down to
`PRIORITY_FALLBACK = 10`), `SOVEREIGN_GATES` (L33–41).

**Logic and algorithms**
— Priority-and-status arbitration between competing writers, `add_field` L348–408.
— Seven cross-field coherence invariants, `_apply_row_coherence` L527–562:
  1. `eil == "BLOCKED"` and thesis in {GO, EXECUTE, FULL_EXECUTE} → `EIL_BLOCKED` → **BLOCKED**;
  2. `pse_mode == "FATAL_BLOCK"` and exec mode in {FULL_EXECUTE, REDUCED_EXECUTE, LIVE_EXECUTE}
     → `PSE_FATAL_BLOCK` → **BLOCKED**;
  3. `exec_mode == "FULL_EXECUTE"` with an empty/NONE/NAN/UNKNOWN/MISSING trigger →
     `MISSING_TRIGGER_FULL_EXECUTE` → **DEGRADED, not BLOCKED** (the gate name is not in
     the BLOCKED set at L452, despite the call passing `"BLOCKED"` as its status); (CON-152)
  4. `run_mode == "EVENING"` and `is_live_execution_validated` → `EVENING_LIVE_VALIDATION_CLAIM`
     → DEGRADED;
  5. `macro_data_quality == "CONFLICTED"` → `MACRO_CONFLICTED` → DEGRADED;
  6. upstream `handoff_integrity_status` / `verdict_coherence_status` in
     {BLOCKED, CONFLICTED, FAILED, INVALID} → `EXECUTION_INVALID` → **BLOCKED** (L545–560);
  7. `equity_drawer_active` truthy → warning only, downgrades to `PARTIAL` (L463–464, L561–562).
  **None of the seven examines any direction field.** [OBSERVED]
— Decision branches (direction): NONE in the invariants. The only direction handling is
  the identity assignment at L517
  `direction=str(row.get("direction") or row.get("options_direction") or "").strip() or None`
  — a two-alias `or` chain terminating in `None`, which nothing downstream in this module
  ever tests. CALL, PUT and blank are all handled identically: not at all. [OBSERVED]

**Computations and formulas (exact)**
— `_status_rank` L277–286: `.get(normalise_status(status), 0)`. The `0` default is
  **unreachable**, because `normalise_status` already coerces anything unknown to
  `CONFIRMED`, which maps to `6`. An unknown status therefore ranks **above** `PARTIAL`.
  [OBSERVED] (CON-153)
— `int(self.priority or PRIORITY_PACKAGE_EXISTING)` (L303) — **an explicitly passed
  priority of `0` is falsy and silently becomes 50.** (GAP-159)

**Models** — NONE.

**Outputs** — Files written: **NONE**; it returns dicts and a DataFrame.
`to_flat_dict` (L469–486) emits eight meta fields plus every carried field, including
`verdict_coherence_status = "BLOCKED" if self.errors else "OK"` (L479).
Atomic promotion? NOT_APPLICABLE.
— **Schema/version field: NONE.** The module defines no `SCHEMA_VERSION` or equivalent;
  neither `to_flat_dict` nor `to_json_dict` stamps one, and `from_row` reads none.
  **Nothing is enforced on read** — a row produced by any prior version is accepted
  without check. [OBSERVED] (GAP-160)
— **Can it block a ticker?** It can *mark* one blocked; it cannot remove it.
  `apply_sovereign_gate` L452 sets `packet_status = "BLOCKED"` for three gates; `finalise`
  L459–460 re-derives it. Whether that mark stops a ticker depends entirely on the
  consumer.

**Handoff** — Receives rows from the EOD Candidate Engine. Hands the packet fields back
into the same rows. Join keys: `ticker`, `run_id`.
— **The governed direction record is not carried at all.** `TRUTH_PACKET_CARRY_FIELDS`
  contains `option_direction`, `options_direction`, `direction_conflict_status`,
  `direction_conflict_reason`, `primary_direction`, `direction_reroute_status`,
  `direction_decision_reason`, `direction_call_score`, `direction_put_score`,
  `selected_contract_side`, `direction_alignment_status`, `direction_confirmed` — but
  **not** `governed_direction`, `final_direction`, `dir_calc_version`,
  `direction_resolution_path`, `direction_resolution_chain_json` or
  `governed_direction_record_sha256`, i.e. precisely the six fields
  `morning_handoff_finalizer.py:130-137` treats as the direction identity. A row round-
  tripped through `enrich_row_with_truth_packet` retains them only because L582 starts
  from `out = dict(row)`; a row rebuilt from `to_flat_dict` alone would lose them.
  [OBSERVED] (CON-154)

**Missing-data handling**
— `is_missing_value` L227–239: `None`, NaN and `MISSING_TOKENS` (L20) are missing; numeric
  `0` and boolean `False` are **not**. A legitimate categorical `"NONE"` is
  indistinguishable from absent data. §10-compliant? **N**.
— L235–236 **`except Exception: pass`** inside the numpy-scalar unwrap; the value then
  falls through, fails the `isinstance(value, str)` test, and is reported as **not
  missing**. **Fail-open.** **N**. (GAP-161)
— L242–244 `normalise_status`: `value if value in FIELD_STATUSES else "CONFIRMED"` —
  **an unrecognised, corrupted or typo'd status silently becomes `CONFIRMED`, the
  highest-trust rank.** **Fail-open.** **N**. (CON-155)
— L247–254 `_safe_confidence`: `except (TypeError, ValueError): v = 1.0` — non-numeric
  confidence becomes **full** confidence; NaN by contrast becomes `0.0` (L252–253). Two
  missing-data shapes given opposite treatments. **N**.
— L261–262 `except Exception: pass` in `_json_safe`. **N**.
— L366–367 `if is_missing_value(new.value): return` — a missing new value never displaces
  an existing one. **Fail-closed.** **Y**.
— L376–379 a `CONFIRMED` value is never downgraded — fail-closed, but **silent**: no
  conflict is recorded. **PARTIAL**.
— L381–392 two `CONFIRMED` values within 10 priority points → conflict recorded, original
  preserved, `packet_status = "CONFLICTED"`. **Y**.
— **L407–408 `if new.priority > current.priority: self.fields[name] = new` — a
  lower-status value from a higher-priority source silently replaces a higher-status one
  with no conflict record.** Reachable when L394's status test fails. **N**. (CON-156)
— L521 `status = "MISSING" if is_missing_value(row.get(name)) else "CONFIRMED"` — binary.
  **Four of the seven declared statuses (`PARTIAL`, `INFERRED`, `STALE`, `INVALID`) are
  unreachable via `from_row`.** §10-compliant? **N**. (GAP-162)
— L528–533 `str(row.get(...) or "").upper()` ×6 — numeric `0` and `False` become `""`
  before comparison against string sets. **N**.
— L477–480 `"handoff_integrity_notes": " | ".join(self.warnings + self.errors)` — a clean
  packet and an unpopulated packet emit the same `""`. **N**.
— L601–604 `try: import pandas … except Exception: return rows` — silently returns a list
  where a DataFrame is expected, a **container-type change on the error path**. **N**. (GAP-163)

**Contradictions found here:** CON-152, CON-153, CON-154, CON-155, CON-156
**Gaps found here:** GAP-159, GAP-160, GAP-161, GAP-162, GAP-163
**Comment/docstring claims audited:**
— L3 "The packet is the production baton" → **PARTIAL**: it carries 200+ fields but not
  the six governed-direction fields (CON-154).
— L5–6 "receive, validate, enrich, preserve, and pass forward committed fields without
  silent downgrade." → **PARTIAL**: holds at L376–379, **fails at L407–408** (CON-156).
**Confidence in this section:** HIGH — delegated targeted read with verbatim quotes at
every decisive line; the carry-field census is a direct read of L112–220.

---

### morning_handoff_finalizer.py

**Classification:** ORCHESTRATED morning stage (776 lines).
**Real execution position:** morning stage 3 of 3. Imported inline at
`intelligent_orchestrator.py:5815` and called at `:5817`.
[OBSERVED `03_execution_order.md` §3]
**Task in the process:** Runs the Execution Gate over the Morning Gate's validated rows,
re-computes the OLM guard as a drift detector, enforces field-identity across the
Execution→Lab boundary, writes the Lab manifest and opportunity book, materialises the
interpreter handoff, and emits the morning handoff summary.

**Entry points:** `finalize_morning_handoff(run_id, results, *, runs_dir, sync_interpreter)`
(L554–560); `sync_verified_morning_handoff` (L~530).
**Imports (production):** `execution_gate.run_execution_gate` (inline, L578);
`contracts.options_liquidity_execution_guard` (L25 — **both**
`evaluate_olm_execution_guard` and `action_is_within_guard`);
`contracts.direction_governance.validate_direction_record`;
`contracts.lab_control.{write_final_run_manifest, write_final_opportunity_book}`
(L633–644); `pipeline_interpreter.ma_inputs_sync` with a file-path loader fallback
(L484–497). · **Imported by:** `intelligent_orchestrator.py` (inline), `morning_gate.py`
CLI (per docstring L6–7). · **Broken/retired imports:** NONE.

**Inputs**
— Files/tables read:
  `data/output/runs/{run_id}/morning_validation/morning_validated_trades_{run_id}.csv`
  (L572–575, only when `results is None`); `{run_dir}/run_meta.json` (L383–387);
  `{run_dir}/macro_quant_packet.json` (L303–307); `REPO_ROOT/dropbox/macro` (L609);
  the `MA_Inputs` destination copies for hash verification (L506–510).
— Upstream fields consumed: the gated row's `final_action`, `morning_execution_permission`,
  the six direction-identity fields (L130–137), the OLM guard fields, five contract-symbol
  aliases (L79–89), and the macro packet's `as_of` / freshness / quality / regime fields.
— External calls: **NONE** — no network import anywhere.
— Config/policy read: `HANDOFF_VERSION = "morning-handoff-v2"` (L36);
  `EXECUTION_TO_LAB` (L38–45); `ACTIONABLE_LAB_VERDICTS`; the guarded authority-field set
  (L616–620).

**Logic and algorithms**
— Execution Gate invocation, L584–588.
— OLM drift detection, L185–205.
— Field-identity equality across the Execution→Lab boundary, L130–144.
— Direction-record validation for actionable rows, L161–171.
— Version-uniformity check, L653–661.
— MSI identity preflight, L235–299.
— Decision branches (direction):
  * The finalizer has **no CALL-specific or PUT-specific branch of its own**.
  * **CALL path / PUT path:** delegated to `validate_direction_record`
    (`contracts/direction_governance.py:465-474`), symmetric and equally enforced.
  * **Other/blank path:** a row whose `final_direction` is `UNRESOLVED`, `STRANGLE` or
    blank fails at `contracts/direction_governance.py:410-411` — **but only if the row's
    `final_action` is `BUY_NOW` or `BUY_SMALL`** (L161). For `BLOCK`, `SKIP`,
    `MANUAL_REVIEW` or `CONTRACT_REPAIR` the validator is never invoked, so a blank or
    non-directional record passes untouched. Correct for blocked rows; **fail-open for
    `MANUAL_REVIEW` and `CONTRACT_REPAIR`, which are downstream-promotable states**.
    [OBSERVED] (CON-157)
  * L130–144 compares the six direction fields for **equality**, so two rows both missing
    a field compare equal (`"" == ""`). The check confirms non-mutation, not presence: a
    run in which the Lab and the Execution Gate both drop `final_direction` passes.
    [OBSERVED] (GAP-164)

**Computations and formulas (exact)**
— `expected = EXECUTION_TO_LAB.get(action)` (L38–45, applied L115) — comparison only.
— `"morning_authority_preserved": not source_go or lab_actionable > 0` (L733).
— `session_date` from the `run_id` prefix via `strptime`, falling back to today's UTC
  date on `ValueError` (L229–232).

**Models** — NONE.

**Outputs** — All five JSON outputs use `_atomic_json` (L217–224):
`temporary.write_text(...)` then `temporary.replace(path)`. **Atomic promotion: yes.**
| Path | Line | `schema_version` |
|---|---|---|
| `{run_dir}/diagnostics/msi_identity_preflight.json` | L296–297 | `"msi_identity_preflight_v1"` (L287) |
| `{run_dir}/interpreter/handoff_status.json` | L372–380 | `"interpreter_handoff_status_v1"` (L375) |
| `{run_dir}/diagnostics/msi_production_readiness.json` | L449–450 | **none** |
| `{run_dir}/run_meta.json` (mutated in place) | L463–469 | **none added** |
| `{morning_dir}/morning_handoff_summary_{run_id}.json` | L740–742 | `HANDOFF_VERSION` (L701) |
Indirect writes: the gated CSV via `run_execution_gate(..., output_dir=run_dir / "trades")`
(L584–588); the Lab manifest and opportunity book (L633–644); the MSI handoff via
`materialize_interpreter_handoff` (L413–429); the `MA_Inputs` copies via `sync_file` (L504).
— Version enforced on read: **one** — `DIR_CALC_VERSION` uniformity across every gated
  row (L653–661). `HANDOFF_VERSION` itself is written but never read back. (GAP-165)
— Authority claim: L728 `"authority": "ADVISORY_ONLY"` → **HOLDS**, consistent with the
  guard at L613–631.

**Business logic recomputed here (not copied):**
1. **Execution action** — `run_execution_gate` at L584, the producer of `final_action`
   (`execution_gate.py:358-397`). The finalizer **is** the stage at which the morning
   execution decision is computed; it does not merely copy an upstream verdict. [OBSERVED]
2. **OLM guard disposition and reason** — recomputed independently at L185–205 and diffed
   against what the row carries: L196–205
   `if emitted_disposition != decision.disposition: mismatches.append(...)`; a divergence
   raises at L596–601. A genuine second computation used as a drift detector.
3. **Expected Lab verdict** — derived from the action via `EXECUTION_TO_LAB` (L115);
   comparison only, the Lab verdict is not overwritten.
4. **Macro advisory fields** — merged into every gated row (L622–628), then immediately
   checked: L629–631 `if before_authority != after_authority: raise MorningHandoffError(
   "Macro advisory mutated governed authority fields")`.
**Not recomputed — validated only:** direction, target, invalidation and monetisability.
`validate_direction_record` is called (L162–163) but no direction is derived; targets and
invalidation levels are checked for sign-coherence inside that validator, not recalculated.
[OBSERVED]

**Handoff** — Receives `morning_validated_trades_{run_id}.csv` (or the in-memory rows)
from the Morning Gate. Hands the gated CSV, the Lab manifest, the opportunity book, the
interpreter handoff and the summary onward. Join keys: `run_id`, `ticker`, contract symbol.

**Missing-data handling** (condition → emitted value, file:line)
— Input CSV absent (L57–58), empty (L61–62), `results` empty (L68–69), blank `run_id`
  (L569–570) → `raise MorningHandoffError`. **Fail-closed.** **Y**.
— Any counted field blank → `"MISSING"` bucket (L74). Explicit token. **Y**.
— **No contract symbol under any of five aliases → `""` (L78–89); then at L126
  `if gated_contract and gated_contract != lab_contract` — an empty gated contract
  skips the comparison entirely, so a row that lost its contract on both sides raises no
  mismatch. Fail-open.** **N**. (GAP-166)
— Unknown execution action → `f"{ticker}:UNKNOWN_EXECUTION_ACTION:{action or 'MISSING'}"`
  (L117–118). **Y**.
— Any required identity field blank on an actionable row → preflight `"FAIL"` then raise
  (L273–284, L398–406). **Y**.
— **`run_meta.json` unreadable or malformed → `run_meta = {}` (L384–387), then
  `run_kind = str(run_meta.get("run_kind") or "PRODUCTION").upper()` (L388). An unreadable
  `run_meta.json` is silently promoted to a production run, and the guard at L389–392
  then passes. The most permissive value is the default.** **N**. (CON-158)
— `macro_quant_packet.json` absent, unreadable, not a Mapping, or missing `as_of` →
  `return None` (L304–319); the caller at L428 substitutes `macro_reference or
  _macro_reference(...)`. Fail-open. **N**.
— `packet_id` absent → synthesised `f"MACRO:{packet_hash[:24]}"` (L322–326) — an
  identifier invented from a content hash. **N**.
— `macro_freshness_status` / `macro_data_quality` absent → `"UNKNOWN"` (L331–338).
  Explicit token. **Y**.
— **`macro_context_state` and `regime_state` both absent → `"NEUTRAL"` (L339–343) — a
  legitimate market reading; a consumer cannot distinguish "the packet said neutral" from
  "the packet had no regime field".** **N**. (GAP-167)
— `run_id` prefix not parseable → today's UTC date (L229–232). Fail-open. **N**.
— No actionable rows for MSI → `status: "NO_ACTIONABLE_SIGNALS"`, `actionable_rows: 0`
  (L373–379) — the zero is accompanied by a status string. **Y**.
— MSI flags off / partially set → `"DISABLED"` (L363) /
  `"SKIPPED_NON_GOVERNED_OR_PARTIAL_TEST_FLAGS"` (L458–461). **Y**.
— `MSI_LAB_V3_VIEW` ≠ `MSI_INTERPRETER_RESOLVER` → raise (L358–361). **Y**.
— Any required artefact missing on sync, or a hash mismatch → raise (L502–514). **Y**.
— Row-count divergence at any of three boundaries → raise (L589–593, L646–650, L680–684). **Y**.
— **`"source_actionable"` / `"lab_actionable"` (L714–715) are plain integers.
  `source_go == 0` is emitted identically whether no row was actionable or
  `morning_execution_permission` was absent from every row — the counter at L669–674 reads
  `str(row.get("morning_execution_permission", "")).upper()`, and a missing column yields
  `""`, which is not in the actionable set. The guard at L680 is then skipped, so a run
  that lost the permission column reports `"morning_authority_preserved": True` at L733
  on the strength of a missing field.** **N**. (CON-159)
— `"api_requests": 0` (L705) is a hard-coded constant, not a measurement. **N**.
— L274 `str(row.get("run_id") or run_id).strip()` — a falsy row `run_id` silently adopts
  the run-level id, masking the mismatch L275–276 exists to catch. **N**.
— L575 `_normalise_rows(results) if results is not None else _read_csv(morning_path)` —
  correctly uses `is not None` rather than truthiness, so an explicitly empty `results`
  list raises at L68–69 instead of silently replaying the CSV. **This is the correct
  pattern; the sites above depart from it.** **Y**.
— No `try/except: pass` and no `setdefault` anywhere in the file. [OBSERVED]

**Contradictions found here:** CON-157, CON-158, CON-159, CON-160
**Gaps found here:** GAP-164, GAP-165, GAP-166, GAP-167
**Comment/docstring claims audited:**
— L3 "This module deliberately performs no provider or API requests." → **HOLDS** — every
  import is local (L23–31, L355, L408–411, L445, L485, L578–582); corroborated by
  `"api_requests": 0` (L705).
— L6–7 "Both supported Morning entry points call this module so a Morning run cannot
  report success while leaving the Intelligence Lab on the previous EOD view." →
  **PARTIAL**: both entry points do call it, but `intelligent_orchestrator.py:5828`
  catches the exception and only logs `logger.error`, so `premarket_workflow` can still
  complete after the finalizer raises. (CON-160)
— L243 "The materializer remains the final authority." → **HOLDS**: the preflight
  (L235–299) only reports; the raise at L403–406 precedes
  `materialize_interpreter_handoff` (L413).
— L244–245 "never invents a thesis, trade idea, structure, contract, or quote snapshot
  identifier." → **HOLDS** (L261–273 only reads and tests for emptiness). Note the
  contrast at L322–326, where a *macro* `packet_id` **is** invented from a hash — outside
  the scope of this sentence.
— L604–605 "Only advisory fields are added; execution authority fields are never read from
  or mutated by this packet." → **PARTIAL**: enforced at L613–631, but the guarded set
  (L616–620) omits `final_direction`, `dir_calc_version`, `direction_resolution_path` and
  `governed_direction_record_sha256`. `governed_direction` is guarded; **`final_direction`
  — the field that actually reaches contract selection — is not.**
— L728 `"authority": "ADVISORY_ONLY"` → **HOLDS**.
**Confidence in this section:** HIGH — delegated targeted read with verbatim quotes at
every decisive line.

---

## Cross-cutting note on `contracts/` version constants

`DIR_CALC_VERSION` (`contracts/direction_governance.py:19`) is the **only** version in
the Lane-B file set that is enforced on read — at `contracts/direction_governance.py:375-376`
and `morning_handoff_finalizer.py:653-661`. Every other version constant in this lane
(`OPTIONS_LIQUIDITY_LIFECYCLE_VERSION`, `MATURATION_SCORE_VERSION`,
`OLM_EXECUTION_GUARD_VERSION`, `LONG_OPTION_POLICY_VERSION`, `HYDRATION_SCHEMA_VERSION`,
`RR_CALCULATION_VERSION`, `MONETISABILITY_CALCULATION_VERSION`, `HANDOFF_VERSION`,
`ROUTER_VERSION`, `GATE_VERSION`, `lab_schema_version`) is written and never checked —
with the single exception of `SUPPORTED_LIFECYCLE_VERSIONS`
(`contracts/options_liquidity_execution_guard.py:17`), which **is** enforced at L160–165.
[OBSERVED] (GAP-168)


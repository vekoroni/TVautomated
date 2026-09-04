# Lane B — the 15 hotspots, resolved

**Document:** AVS-E2E-CODE-001 · Lane B
Each hotspot is resolved to OBSERVED with `file:line` and a verbatim quote of the
decisive line, or marked UNTRACED with the reason. Tags: **OBSERVED** = read directly.
**INFERRED** = deduced; basis and confidence stated.

---

## 1. `LifecycleInputs` construction in `scripts/avshunter_options_intelligence.py`

**RESOLVED — OBSERVED.** Construction site: `scripts/avshunter_options_intelligence.py:4569-4586`,
inside `_options_liquidity_lifecycle_fields` (L4507), called once at L6867.

**`invalidation_spot` — is it `ctx.stop`?** Yes.
```
4549:        "invalidation_spot": _repair_alt_float(ctx.get("stop")),
4583:                invalidation_spot=float(required["invalidation_spot"]),
```
**Where `ctx.stop` comes from** — `parse_structural_context`, L3803–3808:
```
3803:    _raw_stop = _f('stop_loss')
3805:        _stop_authoritative = _raw_stop is not None and float(_raw_stop) > 0
3808:    stop        = float(_raw_stop) if _stop_authoritative else entry*0.97
```
`stop_loss` originates in Discovery. Its three producers are
`avshunter_discovery_ULTIMATE.py:1784` (asymmetry gate),
`:1798` (Wyckoff, validity-checked only for a ±25 % band at `:1794`), and
`:1803` `structural_stop = round(current_price - _atr_stop_dist, 2)` (ATR fallback).
A fourth site, `avshunter_discovery_ULTIMATE.py:539`, is `stop_loss = current_price * 0.97`.

**Which side of entry it sits on for a PUT.** `stop` is **direction-agnostic at every
producer**. The ATR fallback (`current_price - dist`) and both `× 0.97` defaults are
strictly **below** price. Discovery applies a direction check to the *target*
(`avshunter_discovery_ULTIMATE.py:1809-1813`) but **none to the stop**.
Consequently, for a PUT the invalidation is on the **wrong side of entry** unless the
Wyckoff stop happens to be above price. In `classify_remaining_runway` the effect is
deterministic — `contracts/options_liquidity_lifecycle.py:418-421`:
```
418:    direction = 1.0 if option_side == "CALL" else -1.0
421:    invalidated = direction * (current - invalidation) <= 0
```
With `side="PUT"` (direction = −1) and `invalidation < current`, `−(current −
invalidation) ≤ 0` is **True**, so `remaining_runway_state = "THESIS_INVALIDATED"` (L431).
The options layer then stamps `thesis_state = "INVALIDATED"`
(`scripts/avshunter_options_intelligence.py:4602-4603`).
This is compounded by `L3819 stop_dist = max(entry - stop, 0.01)`, which clamps to 0.01
for any stop above entry — i.e. the file's own risk distance also assumes CALL geometry.
**INFERRED (HIGH):** every PUT whose `stop_loss` was produced by the ATR fallback or
either `× 0.97` default is marked `THESIS_INVALIDATED` at EOD.
`NEEDS_MEASUREMENT: SELECT direction, thesis_state, remaining_runway_state, COUNT(*) FROM options_intelligence_<run_id>.csv GROUP BY 1,2,3` — expect PUT rows concentrated in `INVALIDATED`/`THESIS_INVALIDATED`.

**Cross-writer contradiction.** The same file computes a **direction-aware** invalidation
in `_ev3_handoff_fields`, L4095–4102:
```
4095:        if (direction == 'CALL' and raw_stop < entry) or (direction == 'PUT' and raw_stop > entry):
4101:                invalidation = entry - risk_distance if direction == 'CALL' else entry + risk_distance
4102:                invalidation_source = 'DIRECTION_MIRROR_FROM_STOP_LOSS_V1'
```
and persists **that** value to the lifecycle store, L7883–7885:
```
7883:            invalidation_spot=_repair_alt_float(
7884:                result.get("ev3_invalidation_spot") or result.get("invalidation_spot")
```
So the lifecycle contract receives the raw, un-mirrored stop while the canonical store
receives the mirrored one. Two different invalidation values on the same row.

**`remaining_hold_sessions` — routed hold or `layer2__recommended_hold_days`?**
**Neither purely; it is `layer2__recommended_hold_days` with a DTE-window fallback, and
never the routed hold.** L4546:
```
4546:        "remaining_hold_sessions": _repair_alt_float(ctx.get("hold_days")),
```
`ctx['hold_days']` is set at L3926:
```
3926:    hold_days = l2_hold_days if l2_hold_days > 0 else dte_window[1]
```
with `l2_hold_days = int(_f('layer2__recommended_hold_days', 0) or 0)` (L3832) and
`dte_window[1]` the tier/phase or horizon DTE **mid-point**. The routed set {5, 10, 20}
is computed in the *same file* at L4104–4112 as `planned_hold_sessions`, but that value
is not used here.

**`thesis_spot`, `current_spot`, `structural_target`, `dte`.**
```
4580:                thesis_spot=float(required["spot"]),
4581:                current_spot=float(required["spot"]),
```
Both are `ctx['spot']` = `float(_f('stock_price', 0) or 0)` (L3801) — **identical by
construction at EOD**, so `realised_move = 0`, `consumed_factor = 0`,
`remaining_factor = 1.0`, and `favourable_move` is always False on the evening path.
`structural_target` = `ctx['structural_target']` (L4548), set direction-aware at
L3986–3996. `dte` = `contract.get("dte")` (L4545), from the selected chain row.

---

## 2. `classify_remaining_runway` — target-side vs invalidation-side invariants

**RESOLVED — OBSERVED.** `contracts/options_liquidity_lifecycle.py:392-423`.

**Target-side invariant exists and raises** — L422–423:
```
422:    if total_move <= 0:
423:        raise ValueError("structural target must be beyond thesis spot in the option direction")
```

**Invalidation-side invariant: NONE.** The only checks touching `invalidation` are
finiteness (L410–411) and positivity (L413–414):
```
410:    if any(value is None for value in (origin, current, target, invalidation)):
411:        raise ValueError("runway prices must be finite numbers")
413:    if min(origin, current, target, invalidation) <= 0:
414:        raise ValueError("runway prices must be positive")
```
There is **no** check that `invalidation` sits on the correct side of `thesis_spot` for
the given option side — the mirror of the L422 test does not exist. A CALL-shaped stop
supplied for a PUT is accepted and silently converted into `THESIS_INVALIDATED` at L421.
This is the missing invariant that makes hotspot 1 consequential.

---

## 3. `calculate_dte_requirement` — is `remaining_hold_sessions` domain-checked against {5, 10, 20}?

**RESOLVED — OBSERVED. No.** `contracts/options_liquidity_lifecycle.py:88-114`. The only
checks are finiteness and non-negativity:
```
103:    if hold is None or monitor is None or exit_buffer is None:
104:        raise ValueError("DTE requirement inputs must be finite numbers")
105:    if hold < 0 or monitor < 0 or exit_buffer < 0:
106:        raise ValueError("DTE requirement inputs cannot be negative")
107:    minimum = math.ceil(hold + monitor + exit_buffer)
```
Any non-negative finite number is accepted. The routed set {5, 10, 20} appears nowhere in
this module. Since the caller supplies a DTE-window mid-point when
`layer2__recommended_hold_days` is absent (hotspot 1), `minimum_required_dte` is derived
from an unrouted number with no domain guard.
Note also the unit mismatch the docstring itself declares (L96–99): trading **sessions**
are summed and the result is compared against `dte`, a **calendar-day** count
(`classify_current_executability` L292 `if dte_value < minimum_dte`).

---

## 4. Horizon Router — fields written; does it read or overwrite Discovery's `horizon_bucket`?

**RESOLVED — OBSERVED. It never reads `horizon_bucket`; the value is computed
unconditionally and the orchestrator overwrites the column.**

`macro_horizon_router.py` writes **no files at all** — a Grep for `to_csv|open(|write`
over the module returns no match. It returns `dict[str, list[RoutedSignal]]`.
`RoutedSignal` fields (L153–164): `ticker`, `instrument`, `signal_id`, `horizon`,
`action`, `size_multiplier`, `confirm_required`, `macro_permitted`, `horizon_source`,
`block_reason`, `router_version`.

Bucket computed from hold-days or DTE, never read from the row — L442–445:
```
442:        if hold_days is not None and hold_days > 0:
443:            horizon = "1_5d" if hold_days <= 5 else ("6_10d" if hold_days <= 10 else "11_20d")
444:        else:
445:            horizon = "1_5d" if dte <= 21 else ("6_10d" if dte <= 55 else "11_20d")
```
Grep for `horizon_bucket` in the file returns only the docstring (L19), two writes in the
**uncalled** `routed_to_df` (L528, L538) and the commented-out integration block
(L633, L640). There is no `sig.get("horizon_bucket")` anywhere.

The orchestrator's `patch_horizon_fields_into_csv` is an **unconditional overwrite** —
`intelligent_orchestrator.py:2781-2784`:
```
2781:        # Drop stale horizon columns before merge
2782:        target_df = target_df.drop(
2783:            columns=[c for c in _horizon_cols if c in target_df.columns], errors="ignore"
2784:        )
```
then `patched["horizon_bucket"] = patched["horizon_bucket"].fillna("unrouted")` (L2797)
and `patched.to_csv(target_csv, index=False)` (L2818) — no guard, no atomic promotion.
The written bucket is forced from the loop key, not from `RoutedSignal.horizon`:
`intelligent_orchestrator.py:1533 _out_row["horizon_bucket"] = _bucket`.

Per field: `expected_move_window` and `macro_preferred_horizon` **do not appear in the
router at all**. Routed hold-days are read as inputs (L419–423) and never re-emitted;
the {5, 10, 20} mapping lives at `intelligent_orchestrator.py:2807`
`_hold_by_bucket = {"1_5d": 5, "6_10d": 10, "11_20d": 20}`. There is no `horizon_blocked`
field; the blocked channel is the bucket key `"blocked"` (L346) with the reason in
`RoutedSignal.block_reason` (L163), surfaced only by the uncalled `routed_to_df` (L531).

---

## 5. Trigger Layer — position in real order; artefact written; Execution CSV before or after?

**RESOLVED — OBSERVED. The Execution CSV is produced BEFORE trigger pass 2, and never
receives any trigger column.**

Order, each verified in code:
- Pass 1 `patch_run_packages` — `intelligent_orchestrator.py:4421` (stage 27), packages only.
- EIL — `intelligent_orchestrator.py:4690` (stage 32).
- `execution/execution_v3_5_{run_id}.csv` written at `execution_intelligence_runner.py:3280`
  `out.to_csv(args.output, index=False)`.
- `superbrain/eil_enriched_{run_id}.csv` written **separately** at
  `execution_intelligence_runner.py:3594` `eil_df.to_csv(eil_enriched, index=False)`.
- Pass 2 `enrich_csv` — `intelligent_orchestrator.py:4770`, targeting `eil_enriched` only
  (path from `:4712-4715`).

Artefacts written by the module:
- Pass 1: each `packages/*.package.json` in place (`trigger_layer.py:972-973`,
  key set at L916) and the sidecar
  `runs/{run_id}/trigger_layer_summary_{run_id}.csv` (L1035, columns L1037–1044).
  The sidecar carries 14 columns and **omits `trigger_ev_10d` and `trigger_ev_sign`**,
  although `build_trigger_block` computes them (L653–658).
- Pass 2: one file, at `trigger_layer.py:807`:
```
807:    output_path = pathlib.Path(output_csv_path) if output_csv_path else input_path
```
i.e. `eil_enriched` in place.

The only post-L4770 writers of the Execution CSV add McMillan columns
(`intelligent_orchestrator.py:5019-5025`). **All fifteen columns of
`TRIGGER_CSV_COLUMNS` (`trigger_layer.py:670-686`) therefore land in `eil_enriched` after
the Execution CSV was finalised, and none reaches it:** `trigger_codes`, `trigger_count`,
`trigger_primary`, `trigger_quality`, `trigger_score`, `trigger_go_eligible`,
`trigger_stale`, `trigger_freshness_state`, `trigger_data_asof`, `trigger_age_sessions`,
`trigger_freshness_reason`, `trigger_context_state`, `trigger_context_reasons`,
`trigger_ev_10d`, `trigger_ev_sign`.
Because `build_candidate_manifest` reads the **Execution** CSV (hotspot 6), every one of
its ~20 `trigger_*` reads resolves to a default.

---

## 6. `eod_candidate_engine.py::build_candidate_manifest`

**RESOLVED — OBSERVED.** Function spans **L1688–L2728** (`return out_df` L2728).

**Every `read_csv`:**
| file:line | call | artefact |
|---|---|---|
| L1735 | `df = pd.read_csv(eil_path, low_memory=False)` | production `execution/execution_v3_5_{run_id}.csv` |
| L1753 | `_hdf = pd.read_csv(path, low_memory=False)` in `_load_horizon_csv` | `horizon_1_5d_*` and `horizon_6_10d_*` only (L1766–1767) — `horizon_11_20d_*` never loaded |
| L1786 | `wbs_df = pd.read_csv(wbs_path, low_memory=False)` | `superbrain/wall_break_scores_{run_id}.csv` |
| L1806 | `disc_df = pd.read_csv(discovery_path, low_memory=False)` | `discovery/discovery_candidates_ultimate_{run_id}.csv` |
| L1862 | `_vdf = pd.read_csv(_vp, low_memory=False)` | first existing of L1855–1857 (vanguard enriched / vanguard signals) |
No `read_json` and no `open()` anywhere in the file.

**Join to `eil_enriched`: NONE.** Definitive — `intelligent_orchestrator.py:5091-5094`:
```
5091:                # The builder's legacy parameter name is retained for API
5092:                # compatibility; this path is deliberately the final execution
5093:                # artifact, never the earlier EIL frame.
5094:                eil_path       = _execution_authority_csv,
```
`_execution_authority_csv` is the Execution CSV (`:5053-5058`). Grep for `eil_enriched`
in `eod_candidate_engine.py` returns only comments (L1823, L1832–1833, L2313) and the
CLI-only argument (L2746).

**Every read of `trigger_*`:** the sidecar `trigger_layer_summary_{run_id}.csv` is
**never read** (Grep returns no match). Column reads: L902, L903, L949, L965, L1233,
L1333, L1373, L1630, L1631, L1653, L1654, L1669, L1680, L2277–2282, L2362–2366, L2403,
L2413, L2519, L2549 — all against the Execution CSV, where none of those columns exists.
Decisive consequences: L1653–1654 `trigger_ready` / `trigger_present` are always `False`;
L1333 `return "NO_TRIGGER_CONFIRMATION"` fires for every row reaching it; L2362–2366 every
row sorts at trigger rank 3.

**`_invalidation_level` for direction ∉ {CALL, PUT}:** `eod_candidate_engine.py:302-328`.
Decisive lines:
```
316:        if direction != "PUT" and stop < signal:
317:            return round(stop, 2)
323:        return round(signal - atr * 1.5, 2)
327:        return round(signal * 0.97, 2)
```
The function tests only equality with `"PUT"`. `UNRESOLVED`, `STRANGLE`, `NONE`, `""` and
`NAN` all take the non-PUT branch at each test and therefore receive a **CALL-shaped
level below entry**. It does **not** return `None`, does **not** return `0`, and does
**not** raise. The terminal `return None` (L328) is reached only when `signal_price` is
falsy and no usable stop exists. It never consults `governed_direction`,
`final_direction`, `canonical_direction` or `selected_contract_side` — only the raw
`row["direction"]`, which L1903–1904 sets:
```
1904:        row["direction"] = direction or "UNRESOLVED"
```
Internal contradiction: `_exit_intelligence_plan` branches the other way — L1272
`if direction_u == "CALL":` … L1280 `t3 = min(vals) * 0.97 if vals else 0.0` — so
`UNRESOLVED` takes the **PUT-shaped** else-branch there and at L1268. The same row
therefore carries a CALL-shaped `invalidation_level` (L2006) and `invalidation_eod`
(L2295) alongside a PUT-shaped target and exit ladder (L2049–2055), with
`exit_invalidation_price` (L1288) holding the CALL-shaped number inside the PUT-shaped plan.

**Where `layer2__*` fields are consumed:** two sites only.
```
740:    vanguard_side = _audit_side(_first_str(row, "vanguard_edge_direction", "layer2__edge_direction", ...))
702:    (layer2__forward_momentum_confidence — fourth-priority fallback in _normalise_current_contract)
```
Everything else is a pass-through name in `PHASE2_LAYER2_FIELDS` (L197–228, copied at
L2325–2326) or a merge column (L1829–1837). **`layer2__recommended_hold_days` does not
appear in this file at all**, nor does `layer2__win_rate_20d`. Hold-days never enter the
stage that builds the morning manifest.

---

## 7. `contracts/selected_contract_economics.py` — quote fields, EOD hydration, monetisability call sites

**RESOLVED — OBSERVED.**

**Which quote fields:** `_quote_record` (L212–254) reads **only `live_contract_*` keys**:
```
214:    bid = _number(live.get("live_contract_bid"))
215:    ask = _number(live.get("live_contract_ask"))
216:    mid = _number(live.get("live_contract_mid"))
```
plus `live_contract_bid_size`, `live_contract_ask_size`, `live_contract_iv`,
`live_contract_delta`, `live_contract_gamma`, `live_contract_theta`, `live_contract_vega`,
`live_contract_oi`, `live_contract_volume`, `live_contract_multiplier`,
`live_contract_provider_updated`, `live_options_fetched_at`, `live_options_source`,
`contract_bid_size_quality`, `contract_ask_size_quality`, `contract_quote_quality`.
**No completed-session chain field is read** — no `close`, `chain_*`, `eod_*` or
`settlement_*` key appears anywhere in the module.

**Can it hydrate from `data/canonical/options/` at EOD?** The module **never opens a
file** — every quote arrives through the injected callable, L269 and L288:
```
288:        live = dict(fetch_contract(symbol) or {})
```
So it can hydrate from any source **only** if the caller's `fetch_contract` returns a
mapping whose keys are named `live_contract_*` **and** whose `live_options_source` is not
in the rejection set, L290:
```
290:        if source in {"", "MARKETDATA_NO_QUOTE", "MARKETDATA_FAILED"}:
```
In the live tree the only callers are in `morning_gate.py` (L981, L1109), i.e. the
morning live-quote path. **No EOD caller exists.** Hydration from
`data/canonical/options/` is therefore possible in principle and **not wired in practice**.

**Where `evaluate_long_option_monetisability` is called:** exactly one live site —
`morning_gate.py:3556`. `recompute_premium_rr` at `morning_gate.py:3553`;
`hydrate_selected_structure` at `morning_gate.py:981` and `:1109`. Grep across the live
tree returns no other caller (all other hits are under `backups/`).
**Answer: morning only, never EOD.**

---

## 8. `morning_gate.py` — the checks, their inputs, and fail-open vs fail-closed

**RESOLVED — OBSERVED.** The checks are executed at L2073–L2110; results stamped at
L2125–L2187; the verdict cascade is L2385–L2527. There are eleven checks, not five.

| Check | Definition | Inputs | Missing input → | Posture |
|---|---|---|---|---|
| `_check_upstream_authority` | L208–228 | `authority_source_stage`, `final_route`, `capital_authorization_state`, `capital_permission`, `eod_candidate_authorized` | `False, "…:MISSING"` (L212, 223, 225, 227) → BLOCK (L2385–2392) | **fail-closed** |
| `_check_direction_integrity` | L204–205 → `validate_direction_record` | the governed direction record | `False, "DIRECTION_NOT_EXECUTABLE:…"` → BLOCK (L2393–2400) | **fail-closed** |
| `_check_premium_economics` → `_check_monetisability` | L244–246, L231–241 | `monetisability_state`, `monetisability_reason` | `False, "MONETISABILITY_DATA_MISSING:…"` (L241) → BLOCK (L2436–2443) | **fail-closed** |
| `_check_ev3_authority` | L249–252 | `ev3_authority_state` | `return True, f"EV3_ADVISORY_ONLY:{state or 'NOT_EVALUATED'}"` (L252) — **always True** | advisory, never blocks |
| `_check_invalidation` | L1444–1472 | `live_price`; `evening_invalidation_price or invalidation_price or invalidation_level`; direction | see below | **mixed** |
| `_check_macro` | L1479–1498 | EOD regime aliases, `current_regime` | `False, "EOD regime not recorded…"` (L1492–1493) | never reaches the cascade |
| `_check_macro_permission` | L1501–1508 | `macro_state.macro_loaded`, `macro_filter` | `return True, "MACRO_ADVISORY_UNAVAILABLE"` (L1503–1504) — **always True** | advisory |
| `_check_contract` | L1662– | `live_data` quote, spread threshold | `contract_pass=False` → FLAG/CONTRACT_REPAIR (L2492–2499) | fail-closed to FLAG |
| `_layer3_model_risk_guard` | L255– | `l3_*` fields | flags → FLAG (L2500–2507) | fail-closed to FLAG |
| `_check_bond_macro` | L1421–1437 | `bond_macro_state.json` via `BOND_MACRO_PATH` (L83) | `return True, "Bond macro state unavailable — check skipped"` (L1426–1427) | advisory |
| `_production_strategy_policy` | L~1600 | `live_data`, row | `strategy_pass=False` → BLOCK (L2401–2408) | fail-closed |

**`invalidation_price` — fail-open.** L1457–1458:
```
1457:    if not invalidation or invalidation <= 0:
1458:        return True, "WARN - no invalidation level on record; structure cannot be verified"
```
A missing invalidation level **passes** the check. The WARN text is a free-text reason,
not an emitted state token, so no downstream consumer can distinguish "verified intact"
from "could not verify".

**`live_price` — fail-closed at the check, fail-open at the cascade.** L1449–1450:
```
1449:    if live_price is None:
1450:        return False, "CANNOT_VERIFY - live price unavailable; invalidation check not confirmed"
```
but L2355 `invalidation_unverified = live_price is None` then routes it to `flag_reasons`
(L2365–2366) and the cascade branch L2444–2451 yields
`verdict=FLAG, permission=WAIT, route=WAIT_LIVE_PRICE, lane=LIVE_PRICE_UNAVAILABLE` —
**not BLOCK**. Net posture: fail-open to WAIT, with an explicit state token.

**Direction paths in `_check_invalidation`.** CALL L1467, PUT L1469:
```
1467:    if direction == "CALL" and live_price <= invalidation:
1469:    if direction == "PUT" and live_price >= invalidation:
1472:    return True, f"Invalidation intact — price {live_price:.2f} vs level {invalidation:.2f}"
```
`UNRESOLVED`, `STRANGLE`, `NONE` and blank fall through to L1472 and **pass**. Fail-open.

**Does any check read a macro file in a way that can BLOCK a ticker? NO.**
Decisive: `macro_pass` is **hard-assigned** at L2091:
```
2091:    macro_pass = True
```
and `macro_permission_pass`, `macro_change_pass`, `macro_pass` and `bond_pass` appear
**nowhere** in the block/flag accumulation (L2353–L2383) or the verdict cascade
(L2385–L2527). They are stamped as display fields only (L2136–2141, L2186–2187).
`bond_macro_state.json` is read (loader from L1214, path L83) and
`_check_bond_macro` can return `False` (L1429–1433) when `bond_trade_go` is false, but
that result is never consulted. The docstring claim at L1423–1424 ("advisory only and is
never included in the trade authority decision") **HOLDS**.

---

## 9. `execution_gate.py` — `final_action` derivation, `olm_guard_*` consumption, `action_is_within_guard`

**RESOLVED — OBSERVED.**

**How `final_action` is derived.** Two mechanisms.
(a) Twelve early `_preserve(...)` returns set it directly: `BLOCK` (L169–173, L216–217),
the OLM disposition verbatim (L180–181), `CONTRACT_REPAIR` (L197, L199–205, L206–211,
L212–215, L218–223, L236, L245, L269, L278), `MANUAL_REVIEW` (L224–229, L262, L302,
L417–419).
(b) The main ladder, L356–L377:
```
356:        if campaign == "READY_EXECUTE":
357:            if execution == "BUY_NOW" and penalty >= 0.75 and not warnings:
358:                final_action = "BUY_NOW"
359:            elif execution in ("BUY_NOW", "BUY_SMALL"):
360:                final_action = cfg_gate.PROBE_SIZE_LABEL
```
with `READY_PROBE` (L363), `WATCH` (L368) and a terminal `MANUAL_REVIEW` (L370–372), then
a `LIMITED` monetisability demotion at L374–377. The two governing inputs are
`campaign_verdict` and `execution_verdict` (L252–253), modulated by `penalty` and
`warnings` from the six gates.

**Are `olm_guard_*` fields consumed? YES.** L159–160 and L180–181:
```
159:        olm_guard = evaluate_olm_execution_guard(row, require_contract=require_olm)
160:        guarded_row = {**row, **olm_guard.as_fields()}
180:        if olm_guard.disposition != "CONTINUE":
181:            return _preserve(row, olm_guard.disposition, olm_guard.reason)
```
The five fields (`olm_guard_version`, `olm_guard_disposition`, `olm_guard_reason`,
`olm_guard_pass`, `olm_guard_state_consistent`) are merged onto every row and the
disposition is enforced as an early exit. `run_execution_gate` forces
`require_olm=True` for production batches, L432:
```
432:    gated = [execution_gate(s, require_olm=True) for s in signals]
```

**Is `action_is_within_guard` enforced? NOT IN THIS FILE.** `execution_gate.py:10-12`
imports `validate_direction_record`, `evaluate_olm_execution_guard` and
`contract_symbols` — `action_is_within_guard` is **not imported and never called**. After
a `CONTINUE` disposition, the `final_action` computed at L356–377 is never re-tested
against the ceiling. A repository-wide Grep confirms it is enforced only downstream:
```
morning_handoff_finalizer.py:187:        if not action_is_within_guard(action, decision):
contracts/lab_control.py:1823:    if action_is_within_guard(current_action, decision) and current_action in {
```
So the ceiling predicate exists, is imported by two other modules, and is absent from the
gate that produces the action it is meant to bound.

---

## 10. `intelligence_lab.py` + governed-book adapter — writes on the read path, categorical←numeric fallback, pre-governance reads

**RESOLVED — OBSERVED.**

**All four `write_final_run_manifest` line numbers verified.**
| Line | Function | Trigger | Route |
|---|---|---|---|
| 346 | `_latest_manifest()` (L341) | HTTP handler, indirect | `/api/orchestrator/status` (L2492, GET) via L2494; `/api/orchestrator/manifest/latest` (L2518, GET) via L2520 |
| 1945 | `_load_run()` (L1164) | HTTP handler, indirect, on every cache miss | `/api/run/<run_id>` (L2473, GET), `/api/run/latest` (L2477, GET), `/api/export_csv` (L2838, GET) via L2845, `/api/enter_trade` (L2565, POST) via L2598 |
| 2527 | `api_orchestrator_manifest(run_id)` | route handler, direct | `/api/orchestrator/manifest/<run_id>`, GET |
| 2604 | `api_enter_trade()` | route handler, direct | `/api/enter_trade`, POST |
Verbatim L2527:
```
2527:    manifest = load_final_run_manifest(run_id, RUNS_DIR) or write_final_run_manifest(run_id, RUNS_DIR)
```
None is at module-import scope; none is on a background thread; each runs in the serving
request thread (`app.run(..., threaded=True, ...)` L3396). **L2527 has no run-directory
existence guard**, so a GET to `/api/orchestrator/manifest/<any string>` creates
`RUNS_DIR/<any string>/` via `contracts/lab_control.py:1217` and writes
`final_run_manifest.json` into it.

**Other writes on the read path:** `ALTER TABLE` DDL at L585 (called from L593, L724,
L742 and L3318 — the last two reached from the pure-GET routes `/api/outcomes` L3283 and
`/api/learning_feedback` L3370); `UPDATE trades` + commit L709–713;
`UPDATE closed_trades` + commit L727–731; `create_contract(` L2673; `log_entry(` L2690;
`log_exit(` L3195. `create_contract(` at L2780 is unreachable — L2743–L2805 is dead code
after the unconditional `return jsonify({` at L2710.
`write_final_opportunity_book` is **never imported and never called** here; there is no
`to_csv`, `to_json`, `os.replace`, `shutil` or `Path.write_text` anywhere in the file.

**`trigger_quality ← trigger_score` — the categorical←numeric bridge is in the adapter,
not the Lab.** `contracts/lab_control.py:2291`:
```
2291:        "trigger_quality": first(sig, "trigger_quality", "trigger_score"),
```
The result is consumed as a label at `contracts/lab_control.py:597-598`
(`if not _is_missing(quality) and _u(quality) not in {"0","0.0","0.00","FALSE","NO"}:
parts.append(_s(quality))`), so a numeric score is concatenated into `trigger_evidence`
as if it were a quality word and **any non-zero score reads as a positive quality**. The
enrichment alias table at `:2434` `"trigger_quality": ["trigger_quality"],` lacks the
fallback, so the two paths disagree.
In `intelligence_lab.py` itself the equivalent line is L685, which bridges
*trigger-quality categorical ← catalyst-event-status categorical*, not numeric:
```
685:            "trigger_quality": _first_signal_value(sig, ["trigger_quality", "eod__trigger_quality", "vg__trigger_quality", "catalyst_event_status", "eod__catalyst_event_status"]),
```
Companion numeric bridges: L686 (`trigger_score ← catalyst_truth_score`, missing → `0.0`)
and `lab_control.py:2292` (`trigger_score ← trigger_count`).

**Reads under pre-governance names** (canonical from the file's own alias table,
`intelligence_lab.py:2246-2313`):
- `opt__` (prefix applied L1752): L622, L623, L624, L625, L626, L627, L631, L866, L867,
  L1076, L1081, L1087, L1088, L1098, L1428, L1448, L1475, L1480, L1611, L1663–1664,
  L1798, L1801, L1929, L1958, L1959, L2656–2658, L2663, L2704.
- `sb_`: L622, L657, L658, L1555, L1568, L1570, L1576, L1579, L1597–1605, L1666–1677,
  L1716, L1720, L1734–1735, L1915–1930, L2019, L2033–2036, L2309, L2310, L2318, L2320,
  L2321, L2328, L2405, L2655, L2747, L2772, L2856.
- `mv__` (prefix L1791): L675, L676, L933, L943, L950, L959, L1040, L1525, L1625, L1628,
  L1632, L1635, L1805–1818.
- `wbs__` (prefix L1768): L868, L869, L1087–1088, L1097, L1769–1772, L1930; aliases L2287–2295.
- `garch__l3_*` (prefix L1784): L870, L1082; aliases L2296–2303.
- `eil__`: L862, L863, L864, L865, L1072, L1077, L1107, L1135, L1136, L1138, L1140 —
  **the prefix is never produced** (EIL rows are the base dict, L1184), so all eleven
  reads are dead and always fall through to the bare name.
Whole families are passed straight to the browser at L2203–2207.

---

## 11. `swing_fusion.py`, `asymmetry_gate_swing.py`, `contracts/direction_governance.py` — who claims authority, who has it

**RESOLVED — OBSERVED.**

**Outputs.**
- `swing_fusion.fuse_wyckoff_crabel` → `direction` ∈ {`LONG`, `SHORT`, `NONE`} (L131–135),
  `intent` ∈ {`BUY_SETUP`, `SELL_SETUP`, `TRANSITION`, `OBSERVE_ONLY`} (L210–235),
  `alignment_score`, `contradictions`, `fusion_rule_fired`, `audit` (L110–117).
- `asymmetry_gate_swing.compute_asymmetry_swing` → **no direction, no intent**. It
  *consumes* `direction` as a parameter (L50). Outputs `entry`, `stop`, `target1`,
  `R_to_T1`, `asymmetry_pass`, `reason`, shelf geometry, `atr14`, `error` (L136–148).
- `contracts/direction_governance` → `CALL` / `PUT` / `STRANGLE` / `UNRESOLVED` (L23–28),
  emitted as `governed_direction`, `final_direction` (L332),
  `direction_resolution_path`, `direction_governance_status`,
  `direction_resolution_confidence`.

**Does any read macro? NO — definitively none.** No import, open, read or key lookup for
`bond_macro_state.json`, `macro_quant_packet.json`, `macro_intelligence_latest.json`,
regime, risk-on/off or VIX exists in any of the three files.
`contracts/direction_governance.py:12-16` imports only `hashlib`, `json`, `dataclasses`,
`datetime`, `typing` — no file I/O at all. Its complete admissible key list (L148–202)
contains no macro key. **Direction is computed with zero macro input at every stage of
this chain.**

**Which comments call it "the single authority":** `swing_fusion.py:6-7`
```
6: Single authority for direction and intent.
7: Precor/WyckoffEngine feed DATA; this module makes the DECISION.
```
restated at `avshunter_discovery_ULTIMATE.py:60`, `:1360`, and
`wyckoff_crabel_precor_logic_v2.py:21`.

**Which actually governs:** `contracts/direction_governance.py::structural_direction`,
driven by `precor_intent` + `dominant_trend`. Trace:
`scripts/avshunter_options_intelligence.py:3792-3793`:
```
3792:    intent      = str(_f('precor_intent', 'WAIT'))
3793:    trend       = str(_f('dominant_trend', 'MIXED'))
```
→ `:3878 governed_direction, governed_basis = structural_direction(intent, trend)`
→ `:3886 direction_record = resolve_governed_direction(...)`
→ `:3895 direction = str(direction_record['final_direction'])`.
Precedence inside `resolve_governed_direction` — `contracts/direction_governance.py:258`
`final_direction = governed`, and evidence is admitted only when `governed` is
non-directional, L264:
```
264:    if governed in NON_DIRECTIONAL and (
```
so **governed (structural) > evidence > preliminary (never)**. The swing_fusion-derived
value is explicitly disqualified, L34–35:
```
34: EXCLUDED_DIRECTION_EVIDENCE = [
35:     "discovery_direction_preliminary",
```
and Discovery itself demotes it, `avshunter_discovery_ULTIMATE.py:2038`:
```
2038:        'direction_authority':   'DISCOVERY_PRELIMINARY_ONLY',
```
A repository-wide Grep confirms **exactly one live writer of `precor_intent`** —
`avshunter_discovery_ULTIMATE.py:2077`, whose `raw_intent` is `precor_data.get('intent','')`
(`:2078`). **No file in the live tree writes `precor_intent` from `fusion_intent`.**

**Verdict: the comment is FALSE.** `swing_fusion` is de-facto a sizing and lane input
only (`scenario_router.py:117-143`, from `execution_intelligence_runner.py:899-902`).
`wyckoff_crabel_precor_logic_v2.py:9`, `:21` and `:229`
(`"_precor_role": "AUDIT_ENRICHMENT",  # not decision-making`) are FALSE in the opposite
direction: precor's `intent` is the sole structural input to the de-facto authority.
`contracts/direction_governance.py:330` `"governed_direction_authority": "OPTIONS_INTELLIGENCE"`
is the accurate self-label.

**`structural_direction` for the defaults set at L3792–3793** (`WAIT`, `MIXED`) returns
`(UNRESOLVED, "precor_intent=WAIT")` — L93–94. `trend` is consulted only on the
`TRANSITION` branch. `swing_fusion`'s most common intent, `OBSERVE_ONLY`, also falls to
L95 and yields `UNRESOLVED`, so the fail-closed default is preserved either way.

---

## 12. `wyckoff_phase_validator.py::_mode` — the terminal `ACCUMULATION` default

**RESOLVED — OBSERVED.** `wyckoff_phase_validator.py:81-90`:
```
87:    control = str(wyckoff_data.get("control_state") or (precor_data or {}).get("control_state") or "").upper()
88:    if control == "SELLERS":
89:        return "DISTRIBUTION"
90:    return "ACCUMULATION"
```
The default is reached whenever `wyckoff_mode` is empty or unrecognised **and**
`control_state != "SELLERS"`. There is no `UNKNOWN` or `UNRESOLVED` mode.

**Effect on `structural_invalidation_level`** — `_invalidation_level` L187–198:
```
193:    recent = bars.tail(40)
194:    if mode == "ACCUMULATION":
195:        return round(float(recent["low"].min()), 4)
196:    if mode == "DISTRIBUTION":
197:        return round(float(recent["high"].max()), 4)
198:    return None
```
When `wyckoff_data['stop_loss']` is absent (L188–190 is the only earlier exit), an
unresolved name receives the **40-bar low** — a level **below** price — because `_mode`
defaulted to ACCUMULATION. For a name that is in fact distributive, or for a name whose
mode simply could not be determined, this produces a bullish-shaped invalidation level.
**L198 `return None` is unreachable through `validate_wyckoff_phase`**, because `_mode`
can only return one of the two named modes.

This is the upstream origin of hotspot 1's PUT-side defect: the value is emitted as
`structural_invalidation_level` (L308), read by Discovery as `wyckoff_data['stop_loss']`
(`avshunter_discovery_ULTIMATE.py:1790`), promoted to `stop_loss` (`:1798-1799`), and read
by the options layer at `scripts/avshunter_options_intelligence.py:3803`.

---

## 13. `canonical_data/session_clock.py` — `completed_session` vs `run_id` date; wall-clock `asof_date`

**RESOLVED — OBSERVED.**

**How `last_completed_session` is resolved** — `canonical_data/session_clock.py:151`:
```
151:    last_session = today if instant >= close_utc else previous_xnys_session(today)
```
with a short-circuit for non-session days at L139
(`previous_xnys_session(today)`). `session_snapshot(now=None)` defaults to the **wall
clock**, L132:
```
132:    instant = now or datetime.now(timezone.utc)
```

**Versus the `run_id` date: the module has no notion of a run.** `run_id` appears nowhere
in `session_clock.py`. The two live call sites both call it with **no argument** and both
then prefer the *current* session over the *completed* one —
`morning_gate.py:2850` and `:3220`:
```
2850:        msi_session_date = snapshot.session_date or snapshot.last_completed_session
```
`session_date` is today's date whenever today is an XNYS session, regardless of whether
that session has completed. During a premarket run `session_date` is therefore today (an
**incomplete** session) and `last_completed_session` is never reached.

**Places where a date is stamped from the wall clock.**
- `morning_gate.py:2820` `date.today()` — a **local** date (not New York, not UTC, not the
  completed session) registered as the run's session date in `run_registry`:
```
2820:                    date.today(),
```
- `canonical_data/option_liquidity_lifecycle.py:544`
  `instant = parse_utc(recorded_at) or utc_now()` — the wall clock when the caller
  supplies no instant.
- Outside the Lane-B file set: `scripts/avshunter_superbrain_layer.py:1231`
  `asof_date = _parse_ymd(asof) or datetime.utcnow().date()`.
Within Lane B, `asof_date` itself is only **read**, never stamped from the wall clock:
`scripts/avshunter_options_intelligence.py:6403-6413` resolves it as
`asof_date → signal_date → run_date → timestamp[:10]`, else `''`.

**Adoption.** Of the twenty Lane-B files, only `morning_gate.py` imports the session
clock. `scripts/avshunter_options_intelligence.py`, `eod_candidate_engine.py`,
`trigger_layer.py`, `macro_horizon_router.py`, `execution_gate.py`,
`intelligence-lab/intelligence_lab.py`, `contracts/lab_control.py`,
`contracts/selected_contract_economics.py` and
`canonical_data/option_liquidity_lifecycle.py` do not. The other live importers are
`canonical_data/bundle_freshness.py:12` and `contracts/quote_change_evidence.py:12`.

---

## 14. `canonical_data/option_liquidity_lifecycle.py` — writers, supersession, thesis identity

**RESOLVED — OBSERVED.**

**Every writer of lifecycle events — three, all in this module:**
`record_thesis_event` (L518, INSERT at L611–627), `record_contract_observation` (L635)
and `record_selection_event` (L844). Their live call sites are:
```
scripts/avshunter_options_intelligence.py:7873:        return _CDS_LIQUIDITY_STORE.record_thesis_event(
scripts/avshunter_options_intelligence.py:8057:    observation = _CDS_LIQUIDITY_STORE.record_contract_observation(
scripts/avshunter_options_intelligence.py:8088:    _CDS_LIQUIDITY_STORE.record_selection_event(
morning_gate.py:2627:    store.record_thesis_event(
morning_gate.py:2716:    observation = store.record_contract_observation(
morning_gate.py:2754:    store.record_selection_event(
```
Both stores are created behind `CanonicalFeatureFlags` (`morning_gate.py:2805-2807`,
`scripts/avshunter_options_intelligence.py:8293`); when setup fails and
`stage_gating_enforced` is false, persistence is silently skipped
(`morning_gate.py:2826-2833`).

**Is there a supersession or correction path for terminal events? NO.**
`canonical_data/option_liquidity_lifecycle.py:592-593`:
```
592:                if latest.thesis_state in TERMINAL_THESIS_STATES:
593:                    raise OptionLifecycleConflict("terminal thesis cannot be reactivated")
```
No amend, correct, supersede or reopen method exists anywhere in the module. Content
differing from an existing `event_id` also raises rather than superseding, L579–582:
```
579:                if existing["payload_hash"] != payload_hash:
580:                    raise OptionLifecycleConflict(
581:                        f"event_key {key} already has different immutable content"
```
Terminality is enforced only inside the store, and the caller writes the terminal event
and its final observation as **two separate transactions**
(`morning_gate.py:2627` then `:2716`), so an observation belonging to a thesis closed
moments earlier raises rather than being recorded.

**Is thesis identity keyed on run date or completed session? On the row's as-of/run
date — never on the completed session.** `thesis_id` is supplied by the caller.
Evening — `scripts/avshunter_options_intelligence.py:4520-4521`:
```
4520:    as_of = _resolve_asof_date(signal_row)
4521:    thesis_id = f"{ticker}:{side}:{as_of or 'UNKNOWN_SESSION'}"
```
with `_resolve_asof_date` (L6384–6413) resolving
`asof_date → signal_date → run_date → timestamp[:10]`, else `''`.
Morning — `morning_gate.py:1811-1814`:
```
1811:    thesis_id = _s(row.get("thesis_id")) or (
1812:        f"{_u(row.get('ticker'))}:{side or 'UNRESOLVED'}:"
1813:        f"{_s(row.get('asof_date') or row.get('run_id')) or 'UNKNOWN_SESSION'}"
1814:    )
```
Neither call site consults `session_clock.last_completed_session`. A run whose `run_id`
date differs from the session it analysed produces a different `thesis_id` for the same
thesis; conversely two runs on the same calendar date collide on one `thesis_id`, and the
second is rejected by the version check at L594–597 rather than recognised as a re-run.
`ticker` and `direction` are immutable for an existing `thesis_id` (L598–601).

---

## 15. `contracts/lab_control.py` — `write_final_run_manifest` / `write_final_opportunity_book`

**RESOLVED — OBSERVED.**

**`write_final_run_manifest` (L1210–L1220).**
*Reads* (via `build_final_run_manifest` L1018–L1207 and `_output_files` L944–L987):
the discovery, vanguard, `eil_enriched`, `execution_v3_5`, `options_intelligence`, V5,
morning-validation, core-intel, superbrain-summary, dropoff-audit and
handoff-contract-audit artefacts, `<run>/macro/*.json` (L982–986), and
`<run>/ev3_shadow/ev3_shadow_phase_status_{run_id}.json` (L1037–1038). No database reads.
*Writes* L1217–1219:
```
1217:    run_dir.mkdir(parents=True, exist_ok=True)
1219:    target.write_text(_json_safe(manifest), encoding="utf-8")
```
**Not atomic** — no temp file, no `os.replace`, no lock. **No `schema_version`** in the
payload (L1172–1207).
*Business logic recomputed:* this function **derives, it does not copy**. Column-presence
and phase status (L1057, L1061–1073); contradiction detection re-derived from raw EIL rows
(L1103, L1105–1110, L1111); health scoring (L1120–1125); run tradeability (L1127–1133);
next action (L1134–1143); permissions (L1148–1163), including
**L1196 `"morning_capital_permission": run_execution_permission,` — a capital-permission
field set from a pipeline-completeness verdict, not from the Morning Gate**.

**`write_final_opportunity_book` (L2831–L2940).**
*Reads:* source-presence probes L2841–2846; then via `_lab_extract_source_paths`
(L2377–L2390): `morning_validated_trades`, `execution_v3_5`, `superbrain/eil_enriched`,
`superbrain/wall_break_scores`, `options/options_intelligence`,
`options/vanguard_signals_enriched`, `vanguard/vanguard_signals_enriched`,
`qomega/garch_forecasts`, `morning_validation/morning_candidates` — each SHA-256'd
(L2716–2719) and manifested (L2721–2727). No database reads.
*Writes:* `final_opportunity_book_{run_id}.csv` (L2883–2888),
`lab_triage_view_{run_id}.csv` (L2890–2894),
`final_opportunity_book_{run_id}.json` (L2939 `json_path.write_text(...)`), plus the
Pipeline Interpreter sync at L2903 wrapped in `except Exception: pass` (L2904–2905).
**Not atomic** — three separate direct writes, no temp-and-rename, no cross-file
transaction; the CSV and JSON can diverge. **Schema version present:** L2908
`"lab_schema_version": "lab_signal_book_v2",`, and per row at L1905.

**Is business logic recomputed there? YES, extensively.**
- **Direction re-derived three times, with three different chains** — L1870
  (`final_direction … selected_contract_side, option_direction`), L2604
  (`_side_from_value(first(row, "canonical_direction", "direction"))`), L1862 (trade-idea id).
  None matches the Lab's own chain (`intelligence_lab.py:1464-1486`).
- **Instrument rewritten** to match the re-derived direction — L1871–1874, written L1986.
- **Contract symbol re-selected** — L1875, and L666:
```
666:                return candidate, f"CONTRACT_RESELECTED_FOR_DIRECTION:{original}->{candidate}"
```
- **Verdict derived** — L2363–2364 runs `apply_lab_resolution(sig, manifest)`, i.e.
  `resolve_lab_tradeability` (L1374–L1765), whose assignment block L1617–L1731 sets
  `lab_verdict`, `lab_tradeable`, `conflict_state`, `execution_lock_reason`,
  `requires_live_validation`, `prep_permission`.
- **Verdict overwritten twice more** — `_enforce_economics_identity` (L2320, again L2694;
  blanks EV at L868/874/878, rewrites five verdict fields at L894–898) and
  `_enforce_olm_lab_guard` (L2321; rewrites verdict, action, category and sizing at
  L1848–1857).
- **Direction integrity** — L2325 `validate_direction_record(row)`, then L2336
  `lab_verdict = "BLOCKED"`, L2339 `final_action = "BLOCK"`, L2343
  `position_size_display = "0% - direction integrity failed"`.
- **WBS score altered and re-graded** — L2615–2617:
```
2616:        corrected_wbs = max(0.0, _f(row.get("wbs"), 0.0) - 5.0)
2617:        row["wbs"] = round(corrected_wbs, 1)
```
  then L2620–2625 re-derives `wbs_grade` from the altered number. Also L2619 on
  `wbs_f5_momentum`. **The correction is gated on `direction == "PUT"` (L2615), so a row
  whose direction failed to resolve keeps the legacy bonus the correction exists to remove.**
- **WBS break direction and momentum alignment synthesised** — L2642, L2657.
- **Readiness ladder** — L2672–2687. **R:R contract binding** — L1894–1898, L2810–2812.
- **Ranking** — L2365–2372 (`order = {"GO": 0, "GO_LIMIT": 1, "PROBE": 2, …}`), assigning
  `lab_rank` / `priority_rank` and overriding the Lab's own ranking.
The module docstring L3–5 ("It does not create signals; it validates and normalises the
committed pipeline baton") is therefore **PARTIAL**: it creates no rows, but it creates
values — direction, instrument, contract, verdict, score, grade, rank and sizing.

---

## Summary

**15 of 15 hotspots RESOLVED to OBSERVED. None UNTRACED.**

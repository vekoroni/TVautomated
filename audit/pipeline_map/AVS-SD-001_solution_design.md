# AVS-SD-001 — Solution Design: Pipeline Integrity Remediation

**Status:** DRAFT v0.2 for review — all AVS-E2E-CODE-001 documents received and triaged (31 Aug 2026). v0.2 absorbs the final registers (170 contradictions, 189 gaps, 1,388-claim ledger), the Lane B hotspot resolutions, the measurement tooling, and the coverage statement (123 of 306 in-scope files read; 194 generated LOW-confidence sections under GAP-618).
**Author:** Claude (chat), from AVS-E2E-DATA-LOGIC-001 (prior) and AVS-E2E-CODE-001 (atlas, code-verified).
**Evidence run:** `data/output/runs/20260831_010309/` — all exit gates replay against it. This run is EOD-only; the morning path is unmeasured until the WS0 morning baseline is captured.
**Scope:** every discrepancy in the contradictions register (170 rows), gaps register (189 rows), field-authority trace (234 rows), handoff matrix, and doc-vs-code delta, consolidated into 12 workstreams plus a per-workstream read-down of unread files in each blast radius.
**Out of scope:** new models, new data feeds, new scoring. This design changes wiring, ordering, identity, invariants, and states — never signal logic.

---

## 1. Design principles

1. **One writer per concept, enforced by machine, not by document.** Every business concept gets exactly one authoritative writer registered in a schema manifest; a CI check fails any build introducing a second. The atlas measured 111 self-declared authority writes across 15 concepts; the manifest is what makes §9 of the prior enforceable.
2. **Three-arm direction logic everywhere.** No `if direction == X … else …` survives. Every direction branch handles CALL, PUT, and OTHER (UNRESOLVED / STRANGLE / blank / NONE) with a *named* outcome. `market_structure/lifecycle.py:19-25` is the reference implementation and is adopted as the repo pattern.
3. **States, not defaults.** Where evidence is absent, emit one of the eight governed states (AVAILABLE / PENDING_MORNING_REFRESH / NOT_APPLICABLE / UNAVAILABLE_PROVIDER / DATA_DEFECT / STALE_ADVISORY / CONTRACT_REPAIR_REQUIRED / SYNTHETIC_RESEARCH_ONLY). No value of one semantic type ever substitutes for another type.
4. **Calculators stay pure; boundaries carry the fixes.** The atlas confirmed the contract calculators are sound and the defects live at call sites, joins, and ordering. This design adds invariants *inside* calculators only to make wrong inputs impossible to persist — it does not change what they compute.
5. **Immutable once promoted.** A run artefact, once promoted, is never rewritten. Enrichment produces a successor artefact with lineage, or happens before promotion.
6. **Preserve what measured sound.** `worklist_gate.py`, the OCC parser, `macro_regime_safety.py`, and the whole `market_structure/` pattern set (content-addressed identity, named degraded paths, self-declared calibration status) are protected assets: workstreams reuse them rather than reinventing.
7. **Every workstream exits by replay.** Exit gates are numeric measurements on run `20260831_010309` using the atlas's own `measurements/` scripts, promoted into a permanent regression suite.

---

## 2. WS0 — Preconditions: version control, baseline, replay harness

*Nothing in WS1+ starts until WS0 is green.*

| Change | Evidence addressed |
|---|---|
| Commit the 127 untracked live `.py` files (including the entire OLM module set); tag `baseline-20260831` | GAP-007 |
| Adopt the atlas `measurements/` m-scripts and `_tooling/` builders as `regression/` — one command replays every §11 figure and every workstream exit gate against a named run. Adaptations: parametrise the hard-coded run path/run-id; add explicit STRANGLE/UNRESOLVED counts to every direction measurement (post-WS4 the book has a four-value domain) | 10_cross_verification.md |
| Normalise the 42 UTF-8 BOMs (per `bom_files.txt` — includes `morning_gate.py` and the production Discovery import `wyckoff_crabel_precor_logic_v2.py`); all AST/lint tooling reads `utf-8-sig` | GAP-610/611 |
| Capture one governed **morning evidence run** as the morning baseline — the 20260831 run is EOD-only, so every morning-path exit gate (WS6, WS7) currently has nothing to replay against | 03_execution_order §3 |
| Freeze calculation versions and schema during WS1–WS3; any change routes through §11 change control | prior §12.5 |
| Resolve the `scenario_builder` import ambiguity by deleting the shadowed module or renaming (import binding must be deterministic before behaviour is compared pre/post) | GAP-322 |

**Exit gate:** `git status` clean; regression suite reproduces all fourteen §11 figures unchanged; import graph has no path-order-dependent bindings; morning baseline run captured and catalogued.

**Read-down rule (applies to every workstream):** 194 of 306 in-scope files have generated, unread sections (GAP-618) — absence of a finding there is not absence of a defect. Each workstream's definition of done includes reading the unread files in its own blast radius before its exit gate counts. Named priorities from the atlas's own risk statement: `scripts/macro_quant_packet.py` (39 fallback chains, 12 importers) → WS5; `canonical_data/historical_prices.py` and the time/session stampers (`history_bridge.py`, `daily_adapter.py`, `bundle_freshness.py`) → WS7; `canonical_data/option_liquidity_lifecycle.py` (1,042 lines, the *second* module named "lifecycle", CON-501) → WS1; `vanguard/layer1_auction/*` → the Market Profile decision in §12.

---## 3. WS1 — Thesis geometry and hold (the P0 economics)

The atlas resolved the last unknown: `LifecycleInputs` is built in `scripts/avshunter_options_intelligence.py` with `invalidation ← ctx["stop"]` at `:4549` and `hold ← ctx["hold_days"]` at `:4546`, while the *published* invalidation is direction-mirrored at `:4093-4102`. All 442 invalidations carry `invalidation_source = DIRECTION_MIRROR_FROM_STOP_LOSS_V1`.

**Changes**

1. `:4549` — lifecycle consumes the same mirrored, governed invalidation that is published. One value, two consumers, zero divergence. (CON-007)
2. `:4546` — lifecycle consumes the routed planned hold (`planned_hold_sessions`), not `ctx["hold_days"]`/`layer2__recommended_hold_days`. (CON-009)
3. `contracts/options_liquidity_lifecycle.py::classify_remaining_runway` — add the missing invariant, symmetric to the existing target check: `direction × (origin − invalidation) ≤ 0 → raise`. A wrong-sided stop becomes impossible to persist. (MISSING_INVARIANT class)
4. `calculate_dte_requirement` — domain-assert `remaining_hold_sessions ∈ {5, 10, 20}`; anything else raises. (CON-009 recurrence guard)
5. `:4092-4102` — third arm: direction ∉ {CALL, PUT} → `invalidation = None` **and** `invalidation_state = NOT_APPLICABLE` (today it silently stays None with no state — CON-008); lifecycle emits `NOT_EVALUATED_NON_DIRECTIONAL`, never INVALIDATED.
6. `:3801-3808` — kill the fabricated stop: when `stop_loss` is missing or ≤ 0, the code manufactures `stop = entry × 0.97` — a silent, long-sided default that then feeds the lifecycle. The lifecycle path inherits the publisher's three-branch logic instead (`MISSING_AUTHORITATIVE_STOP` → no invalidation evaluation, named state). Repoint the remaining raw-stop consumers found by Lane B: `exit_invalidation_price` (morning plan, L1288 — currently the CALL-shaped number inside PUT-shaped exit plans) and `scripts/exit_rules_engine.py:34` (structural stop ← thesis invalidation substitution).
7. Adjudicate CON-501 during the WS1 read-down: two modules are named "lifecycle" (`contracts/options_liquidity_lifecycle.py`, 649 lines, verified sound; `canonical_data/option_liquidity_lifecycle.py`, 1,042 lines, unread). One owner survives, or they are renamed to reflect disjoint duties — a second lifecycle authority is the WS4 direction problem wearing another name.

**Exit gates (replay):** false invalidations 442 → **0**; `DTE_UNSUITABLE` 657 → **≤ 32 with zero unrouted rows** (the "unrouted" arm depends on WS3 wiring the worklist gate — until then the gate is measured as "0 false invalidations, ≤ 32 + unrouted DTE rejections, unrouted count reported"); the 106 blocked book rows (all PUT) re-enter review; CALL, PUT, and STRANGLE variants of every geometry test pass; the two new invariants each demonstrably raise on the old inputs; no code path manufactures a stop.

---

## 4. WS2 — Ordering and the trigger commutation boundary

Mechanism (CON-003): EIL writes `execution_v3_5` at orchestrator `:4690`; Trigger pass 2 rewrites `eil_enriched` at `:4770`; the EOD engine reads only the Execution spine → `trigger_quality` blank 201/201, ranking computed on null.

**Design decision D1 (needs sign-off): reorder vs join.**
- **Option A (recommended):** move Trigger pass 2 before the Execution write and add the trigger block (`trigger_codes/count/primary/quality/score/go_eligible/as_of`) to `execution_schema.py` (GAP-311 closes). One spine, no join, consistent with the immutability principle (WS7) since it removes an in-place rewrite.
- **Option B (fallback if reordering has hidden dependencies):** allow-listed join (ticker + run_id) from `eil_enriched` into the EOD engine, importing only the trigger block. Faster, but adds a join key surface and leaves the rewrite in place.

Also in scope: delete the Lab fallback `trigger_quality ← trigger_score`; type-assert categorical fields reject numerics (§11.5). **Passthrough check:** the final book is written by `contracts/lab_control.py::write_final_opportunity_book` (orchestrator L5654), a separate stage after the EOD engine (L5091) — the new trigger columns must survive that writer's schema, or WS2 recreates GAP-008 (`horizon_size_multiplier` died at exactly this boundary).

**Exit gates:** `trigger_quality` populated 201/201 **in the final book** and equal to EIL's values (61/92/48 on the final population; 294/650/304 over 1,248 stated *with denominators*); ranking recomputed and diffed; no numeric ever accepted into a categorical column (regression test).

---

## 5. WS3 — Horizon completeness and the empty 11_20d lane

Two measured defects: the Router loses 292 of 1,248 tickers with no accounting (GAP-003 — §14.5 invariant fails at this boundary), and `horizon_11_20d` is empty while 20.0 is precisely the hold the lifecycle wrongly defaulted to (GAP-004).

**Changes**

1. Wire `canonical_data/worklist_gate.py` — the module that already enforces `input = passed + rejected + deferred` and holds at Discovery→Packages — at the Options→Horizon boundary. Every input ticker lands in a routed file or a named-rejection file; 292-silent-drops become impossible.
2. Adjudicate the empty 11_20d lane: establish from router thresholds whether zero 20-session routings is intended policy or a threshold defect. **Design decision D2:** if intended, the 20-session hold and its DTE window are retired from the lifecycle domain assertion ({5, 10}); if defective, thresholds are fixed and the lane repopulates. Either way, no lane may exist that nothing can reach while its hold value remains a live default elsewhere.
3. Fix the orchestrator's contradictory position comments (`:4136-4139` vs `:4151`) as part of the same change (CON-004) — the wrong assertion is the more prominent and will misdirect the next implementer.
4. Ensure `horizon_size_multiplier` either survives to the final book or is formally retired (GAP-008) — resolved jointly with D3 in WS5.
5. **Single horizon writer:** Discovery's `assign_discovery_horizon` output is renamed `preliminary_horizon_hint` (or dropped) so the Router is the sole `horizon_bucket` writer per §9 — today both stamp the same concept with no lineage.
6. **Retire Discovery's `_DTE_SCAFFOLD`:** the static `(tier, phase) → DTE` lookup at discovery line ~2188 is a third DTE opinion that never reads the horizon route and exists only to be overwritten by Options Intelligence. It is removed (or renamed `dte_placeholder_unrouted` if a schema consumer needs the column during migration); after WS3, DTE has exactly two legitimate participants — the selector's governed windows and the lifecycle's requirement formula, both keyed to the routed hold.

**Exit gates:** Options→Horizon reconciles exactly (1,248 = routed + named-rejected); `horizon_summary` accounts for 100% of inputs; D2 recorded and enforced by the WS1 domain assertion; no comment in the orchestrator asserts an order the call sequence contradicts.

---

## 6. WS4 — One direction population

The atlas found **two coexisting direction populations in the same 201-row book**: `canonical_direction`/`final_direction`/`direction` at 111 PUT / 90 CALL, and `governed_direction` at 104 CALL / 77 PUT / **20 STRANGLE** (delta B1). The 20 non-directional theses are invisible to every consumer reading the two-sided columns. Separately, 18 CALL_VS_PUT register rows share one shape: two-branch conditionals that coerce OTHER to a side.

**Changes**

1. **Single direction field set.** Direction Governance writes `direction` with domain {CALL, PUT, STRANGLE, UNRESOLVED}; `canonical_direction`/`final_direction`/`governed_direction` become read-only aliases of it or are dropped from the schema (manifest decides; no independent writers). The 20 STRANGLE rows become visible everywhere, displayed as non-directional theses.
2. **Remove the peripheral coercions** (three-arm rewrite per Principle 2): `trigger_confirmation_engine.py:289-290` (coerce→PUT, then reports the coercion as fact), `scripts/exit_rules_engine.py:56-62` (→PUT), `zero_dte/zero_dte_contract.py:368` and `short_swing/short_swing_contract.py:318` (`.get(…, "CALL")`), `short_swing_monitor.py:314` (state-file resurrection flips side), `avshunter_trap_engine.py:268-273` (directionless package takes `max(bull, bear)` and can reach CHASE — must route to a named non-directional outcome).
3. **Discovery ships the adopted decisions:** remove the CALL/PUT preliminary hint and both direction-branched scores (`vwap_acceptance_score`, `_ema_aligned` — replaced with direction-neutral equivalents), remove `repricing_direction`; Discovery emits structure only (mode, control, events, intent, mode-correct structural invalidation). `wyckoff_phase_validator._mode` terminal default `ACCUMULATION` → `UNKNOWN` with `NOT_APPLICABLE` invalidation. Also: `_reconcile_intent` Rule 3 (discovery line ~331) stops *overwriting* `SELL_SETUP → BUY_SETUP` in mature bull trends — the contradiction becomes a named flag on the row, never a rewrite of intent. Schema migration follows the WS2/GAP-008 caution: the `direction` column is consumed downstream (including via the economics `or`-chain), so Discovery emits `UNRESOLVED` as a constant, or the column is aliased in the manifest, until every reader is migrated — it is never simply deleted mid-flight.
4. **Upgrade reconciliation from agreement to validity:** `tools/msi_reconcile.py:88-90` currently passes two blank or two-STRANGLE sides as agreement; add domain validation. `tools/msi_production_readiness.py:159-163` union-of-keys check becomes per-row.
5. **Close the morning path's missing third arms** (Lane B §8): `morning_gate.py::_check_invalidation` fails open on missing `invalidation_price` (L1457-8), and direction values outside {CALL, PUT} fall through L1472 and **pass**. Both get the WS1 treatment: missing governed invalidation → named state, never a silent pass; non-directional rows → `NOT_EVALUATED_NON_DIRECTIONAL`, never implicitly cleared.

**Exit gates:** exactly one writer for direction in the authority manifest; book renders 90/111/20 with STRANGLE visible; grep-lint proves zero two-branch direction conditionals on the orchestrated path; reconcile fails on blank-blank; Discovery ranking reproduces with direction-neutral scores and the delta is documented.

---

## 7. WS5 — Macro containment (policy decision required)

The atlas verified `macro_regime_safety.py` cannot block or set direction — the letter of policy holds. But CON-006: `MACRO_DIRECTION_SIZING` (`intelligent_orchestrator.py:549-558`) applies a regime-keyed **4:1 CALL:PUT size asymmetry** (BULL → CALL 1.00 / PUT 0.25; BEAR → inverse). A 4:1 directional multiplier is directional authority in economic effect, whatever the letter says.

**Design decision D3 (needs sign-off) — three options:**
- **A. Advisory-only (consistent with your stated posture):** the multiplier is published as `macro_sizing_advisory` on the row, never applied; the human applies sizing caution. Macro's effect on capital becomes zero-by-construction.
- **B. Bounded symmetric caution:** macro may scale *total* exposure (both sides equally, e.g. 0.5× in RISK_OFF) but never one side against the other. Preserves "sizing caution" without directional effect.
- **C. Status quo, declared:** keep 4:1 but publish it and its regime key on every affected row so it is visible in the book and the ledger can later measure whether it earns its keep.

Recommendation: **A now, revisit after the outcome ledger (WS11) can price B/C empirically.** Whichever is chosen: `horizon_size_multiplier` must reach the final book or be retired (GAP-008); Discovery's five macro modulation channels are removed per the adopted decision (tier floors revert to fixed; state-prior table relocates downstream with the signal-decay term extracted and preserved); `horizon_summary.as_of_utc` stamps run identity, not macro generation time (GAP-010); macro staleness renders as `STALE_ADVISORY`, never silently consumed at 39.8 h.

**Read-down precondition:** `scripts/macro_quant_packet.py` (898 lines, 39 fallback chains, 12 importers — the atlas's highest-risk unread file) must be read before WS5's exit gate counts; its fallback chains are exactly the class WS8 purges, and it is the producer of every macro value this workstream contains.

**Exit gates:** no code path multiplies size by direction unless D3 = C, in which case the multiplier and key appear on every affected row; Discovery output reproduces with macro fully absent from scoring; a stale macro packet demonstrably changes zero eligibility decisions.

---

## 8. WS6 — EOD monetisability and the completed-session quote

Confirmed: monetisability is computed only in Morning Gate; the EOD book is blank; hydration reads `live_contract_*` fields; and the book carries no `selected_quote_timestamp_utc` on any of 201 rows (delta B4) — so the completed-session property of its quotes is unverifiable in the artefact the Lab reads.

**Changes**

1. `hydrate_selected_structure` gains an explicit quote-source parameter; an EOD path hydrates from the canonical completed-session chain and stamps `quote_snapshot_id` + `selected_quote_timestamp_utc` into the book.
2. `evaluate_long_option_monetisability` runs at EOD for every row with a contract and two-sided quote; states per Principle 3: MONETISABLE / LIMITED / NOT_MONETISABLE for the 175, CONTRACT_REPAIR/UNAVAILABLE_PROVIDER for the 26 with contracts but no valid quote, NOT_APPLICABLE for the 10 without contracts. Morning refresh overwrites nothing — it writes the morning fields beside the frozen EOD fields, stamped PENDING_MORNING_REFRESH until it arrives.
3. Every monetisability summary states its denominator (201 / 191 / 175) — the mixed-denominator defect the prior itself flagged and then committed (B3) is closed by a lint on summary emitters.

**Exit gates:** EOD book has zero blank monetisability cells (every row carries a value or a named state); timestamp column populated 201/201 and all values ≤ completed-session close; morning run leaves EOD fields byte-identical.

---

## 9. WS7 — Identity, immutability, and supersession

The atlas hardened three prior warnings into measured facts: `thesis_id` keys on RUN_DATE (927/927 rows pair an 08-31 id with 08-28 quotes; 86 tickers already hold multiple ids, seven hold three; FLYW:PUT exists under two dates); **no** supersession/correction column exists on any lifecycle table; and no artefact is immutable — six in-place rewrites plus the Lab's manifest rewrite 7h05m after run close (GAP-001, four call sites: L346, L1945, L2527, L2604).

**Changes**

1. **Thesis identity = `TICKER : STRUCTURE : COMPLETED_SESSION : thesis_version`.** Weekend reruns of the same session converge on one identity; a migration maps existing duplicate ids with lineage rather than deleting history.
2. **Append-only correction protocol** exactly as the prior's §14.4 specifies (`calculation_version`, `supersedes_event_id`, `correction_reason`, `corrected_by_run_id`, `SUPERSEDED_DATA_DEFECT`) — now known to be absent rather than assumed present. WS1's recovered 442 rows become its first production use: the false invalidations are *superseded*, never deleted.
3. **Immutability:** the three `patch_horizon_fields_into_csv` calls, `inject_actuarial_into_eil_csv`, `merge_garch_into_enriched`, and Trigger pass 2 (absorbed by WS2-A) are restructured so enrichment happens before promotion, or emits a successor artefact with `enriched_from` lineage. Promotion is atomic; post-promotion mtime change fails the run.
4. **Read paths write nothing:** the four `write_final_run_manifest` call sites are reduced to the single legitimate producer; Lab load becomes verifiably side-effect-free. Local-clock stamps (`date.today()` in exit rules CON-354, and `morning_gate.py:2820`) replaced with session-clock sources.
5. **Session-clock adoption:** `canonical_data/session_clock.py` exists and is sound, but of the twenty Lane-B files only `morning_gate.py` imports it — `trigger_layer.py`, `macro_horizon_router.py`, `execution_gate.py` and the rest stamp time their own way. WS7 makes the session clock the sole time authority for anything session-relevant, enforced by the same lint that guards fields.
6. **Read-down:** `canonical_data/historical_prices.py` (unverified revision-audit claim, GAP-703) and the stampers `history_bridge.py` / `daily_adapter.py` / `bundle_freshness.py` are unread and sit exactly where further IDENTITY findings are most likely; read before the identity migration is designed, not after.

**Exit gates:** re-running the evening pipeline on the same completed session yields byte-identical thesis identities; every artefact mtime ≤ promotion time; opening the Lab changes no file hash; the correction protocol demonstrably supersedes one of the 442 with full lineage.

---

## 10. WS8 — Fallback purge and missing states

The registers' largest categories: 43 SILENT_DEFAULT + 27 MISSING_STATE. The type-bridging subset (field-authority summary §3) is eliminated entirely; each becomes a named state or a fail-closed error:

| Bridge | Disposition |
|---|---|
| categorical ← numeric (trigger) | WS2 |
| IV level ← IV percentile; VRP vocab ← IV vocab (`:3657-3659` vs `iv_engine.py:118`) | one IV vocabulary in the manifest; cross-vocab reads fail |
| missing direction ← CALL / ← PUT (5 sites) | WS4 |
| stale ← fresh on unparseable date (`data_contract_validator.py:200-201`) | unparseable → DATA_DEFECT, fail-closed |
| missing delta ← 0.50; missing composite ← 50 → probability triple; absent alignment ← 50.0 | NOT_APPLICABLE / NOT_EVALUATED; capital-relevant consumers treat as ineligible, not average |
| pending ← zero (monetisability) | WS6 |
| structural stop ← thesis invalidation (`exit_rules_engine.py:34`) | distinct fields; substitution requires explicit state |
| null gate passing NaN/""/0 prices (`data_contract_validator.py:183-188`) | validator checks finiteness and positivity, not just `is None` |
| geometry veto exempting missing asymmetry data (`scenario_router.py:217`) | missing data fails the veto, never bypasses it |

Enforcement: a lint rule (CI) forbids new `or`-chains and `.get(x, <semantic default>)` across manifest-registered fields; the eight governed states become an enum imported from one module — which also settles `enums_structural.py` (adopt it everywhere or retire it; ten modules redefining its literals is the current worst case).

**Exit gates:** zero type-bridging fallbacks on the orchestrated path (lint green); every §10 state reachable in tests; the 24 MEDIUM-confidence register rows re-adjudicated to HIGH or closed.

---

## 11. WS9 — Dead code, forks, and verdict consolidation

1. **Quarantine or delete the 13 DEAD modules** — with priority on the two root-level fork twins (`zero_dte_screener.py`, `short_swing_screener.py`) whose looser "Sprint 3" gates exist only in the unreachable copy **but which write into the live lanes' output directories**: a manual root run silently overwrites live eligibility files. Until deleted, their output paths are isolated. `convergence_engine.py`'s triple-spec threshold contradiction dies with the module.
2. **Verdict consolidation:** of 38 self-declared verdict authorities, the effective pair is `eil_final_action`/`lab_status`. The manifest names Execution's `final_action` the sole permission authority. Lane B settled the guard question with a split verdict: `execution_gate.py` enforces the OLM *disposition* as an early exit (`require_olm=True`) but **never calls `action_is_within_guard`**; the ceiling check lives only downstream in `morning_handoff_finalizer.py:187` and `contracts/lab_control.py:1823`. WS9 adds the ceiling check at the point of emission — an action outside the guard ceiling fails inside `execution_gate.py`, not two stages later. Dead self-declarations are removed with their modules; live secondary verdicts become explicitly `display` or `advisory` typed.
3. **Comment-debt remediation** for the 47 CODE_VS_COMMENT rows on *live* modules (dead ones resolve by deletion): each row adjudicated "fix comment" or "comment was the spec — fix code," recorded in the register. The two audited-HOLDS exemplars (`registry.py`, `market_structure/params.py`) are the template.

**Exit gates:** orchestrated import graph reaches no DEAD module; no two files write one output directory; verdict manifest shows one authority + typed advisories; every register CODE_VS_COMMENT row on a live module closed with a recorded adjudication.

---

## 12. Traceability, incoming documents, and sequencing

**Finding → workstream map (themes):** CON-007/008/009, CON-501, the `entry×0.97` stop → WS1 · CON-003, GAP-311, lab_control passthrough → WS2 · GAP-003/004, CON-001/002/004, GAP-501 → WS3 · B1, 18×CALL_VS_PUT, morning third arms, Discovery direction decisions → WS4 · CON-006, GAP-008/010, macro_quant_packet read-down, Discovery macro decisions → WS5 · §11.6, B3, B4 → WS6 · §D identity/immutability, GAP-001/002, CON-354, session-clock adoption, §14.4 absence, GAP-703 → WS7 · SILENT_DEFAULT/MISSING_STATE/MISSING_INVARIANT rows → WS8 · DEAD, forks, verdict/guard enforcement, CODE_VS_COMMENT → WS9 · GAP-007/322/610/611, morning baseline, replay tooling → WS0. The full row-level annex (170 CON + 189 GAP → workstream) is generated mechanically from the final merged CSVs' `category` and `files_lines` columns using the same triage rules; rows in the 15 "other lane-emitted categories" are assigned by the file they cite.

**New-capability governance — Capability Track CT1: Market Profile Feature Engine.** The Dalton blueprint (`market_profile_quant_trade_success_blueprint.docx`, self-declared "requires empirical validation before production use") queues behind the stability window per the freeze rule, but is formally scoped now as CT1 so its intake is governed rather than ad hoc:

- **Step 1 — layer-1 audit (free now, part of the read-down):** `vanguard/layer1_auction/` (`market_profile.py`, `value_acceptance.py`, `value_migration.py`, `control_identifier.py`, `auction_synthesizer.py`) is ORCHESTRATED and already runs inside Vanguard. Establish which blueprint features it already computes, at what fidelity, and which of its outputs survive to any consumed field — the blueprint is an *audit-then-enhance* of layer 1, never a parallel build.
- **Step 2 — Phase 0/1 as a research lane:** definition freeze and the deterministic packet engine (`market_profile_features/1.0.0`) may be built during the stability window because they write only research-lane artefacts (`SYNTHETIC_RESEARCH_ONLY` per §10) and touch no production field. The blueprint's own contract principles are adopted verbatim — they are Principles 3 and 5 of this design restated.
- **Step 3 — validation is ledger-gated:** the blueprint's six hypotheses (no-trade lift, acceptance, divergence, location, persistence, day type) require exactly the Decision and Outcome Ledger this design defers to post-WS7 — MFE/MAE at governed horizons, executable option returns, counterfactuals for rejects. CT1 validation and the ledger are the same investment; neither starts meaningfully before WS7's stable thesis identity.
- **Authority collisions resolved at intake (non-negotiable):** (a) `trade_gates.state` GO/ARMED/WAIT/BLOCKED is typed **advisory evidence into fusion**, never a permission writer — `final_action` remains sole permission authority per WS9; (b) profile-derived structural invalidation (value edges, LVN/bridge levels) feeds the WS1 governed invalidation authority as *candidate inputs*, never a second invalidation writer; (c) attempt-vs-performance overlaps Wyckoff effort-vs-result — both are structure engines, so their outputs meet at the fusion layer as separately-typed evidence with one shared enum home, not as competing intent writers; (d) the blueprint's `signal decay` comparison feature must reuse Discovery's extracted decay term (WS5), not reimplement it.
- **Data prerequisite named honestly:** the engine needs 1-minute OHLCV, exchange calendars and split adjustments — an intraday feed the current EOD-bar pipeline does not consume. That is a new canonical_data ingestion path (with the same freshness/identity discipline as WS7), and it is the long pole; the blueprint's intraday checkpoints (09:35–15:30 ET) naturally serve the *morning/interpreter* path (`entry_timing_engine.py`) rather than the evening EOD thesis build.
- **MVP scope on promotion:** the blueprint's own eight-feature minimum (POC/VAH/VAL prior+current, opening location, IB and range extension, value migration/overlap, opening-type probabilities, attempt-vs-performance, balance/imbalance transition, structural invalidation + no-trade reason codes) — nothing wider until those clear the promotion gate it specifies (incremental out-of-sample lift over baseline AVSHUNTER, net of costs, on a frozen holdout).

**Protocol for future findings:** each new finding is triaged into an existing workstream by its category; a new workstream is opened only if a finding fits none (expected rare — the categories are stable). Findings that contradict this design amend it by versioned change note, not silent edit — this document practices WS7's own rule.

**Sequencing and rationale:**

| Order | Workstream | Why here |
|---|---|---|
| 0 | WS0 | Nothing is provable without version control and replay |
| 1 | WS1 | Largest measured economic suppression (106 rows, 625 false DTE); two call-site edits + two invariants |
| 2 | WS2 | Changes ranking — must be measured in isolation after WS1 |
| 3 | WS3 | Changes population — measured after WS2; D2 decided here |
| 4 | WS4 ∥ WS5 ∥ WS6 | Independent surfaces (direction schema / macro policy / EOD economics); D1 already done, D3 decided before WS5 starts |
| 5 | WS7 | Identity migration touches everything; done once the book is stable |
| 6 | WS8 ∥ WS9 | Recurrence prevention and debt; continuous after WS7 |
| — | Stability window | 10 consecutive clean evening+morning sessions, zero schema/formula change, before any new capability |

**Decision points for you (blocking):** **D1** trigger reorder vs join (WS2 — recommend reorder) · **D2** is the empty 11_20d lane policy or defect (WS3) · **D3** macro directional sizing A/B/C (WS5 — recommend A) · **D4** which direction column name survives as canonical (WS4 — recommend `direction` with the four-value domain).

**Definition of done:** all exit gates green on replay; the regression suite (every gate + all fourteen §11 figures + three-direction variants of every business-critical test) green on 10 consecutive live sessions; the authority manifest covers all 15 concepts with one writer each; the outcome ledger (next programme phase, unblocked by WS7's stable identity) begins recording against a book whose semantics no longer move.

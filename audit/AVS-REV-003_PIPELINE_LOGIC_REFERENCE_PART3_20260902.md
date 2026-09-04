# AVS-REV-003 — AVSHUNTER Pipeline Logic Reference, Part III: Direction Governance, Morning Path, EOD Manifest, SuperBrain/Macro, Lab & Scanner

**Date:** 2026-09-02
**Scope:** the ~30 remaining production logic files not covered by AVS-REV-002 (which detailed Discovery, orchestrator, both Wyckoff engines, Options Intelligence, EIL, Vanguard L1/L2, EV3). Together, AVS-REV-002 + this document detail the logic of every decision-bearing file in the 187-file production set.
**Method:** five parallel full-file reviews; every claim carries file:line evidence. Sections: A direction chain (direction_governance, swing_fusion, asymmetry gate, phase validator, sector alignment, governed states); B morning path (morning_gate, handoff finalizer, execution_gate, selected_contract_economics, OLM guard); C EOD manifest & triggers (eod_candidate_engine, trigger_layer, wall_break_scorer, catalyst_truth, trap engine, exit rules, McMillan, eod resolver); D SuperBrain/macro/GARCH/EV2/monetisation-policy pair; E Lab materializer & Phase-0 scanner.

---

## PART I — Where the pipeline is going wrong: the completed picture

With every logic file now read, the "contradicting signals, edge lost by the end" failure resolves into **five concrete mechanisms**, each fully evidenced in Parts A–E below and in AVS-REV-002.

### 1. Direction is written eleven times and reconciled zero times — and the reconciler itself has three blind spots

The governed resolver (`contracts/direction_governance.py`) is well-built but narrower than its name suggests:
- **It never challenges a directed answer.** The evidence gate runs only for STRANGLE/UNRESOLVED (L264). A governed CALL with unanimously PUT evidence ships as `DIRECTION_CONFIRMED`, with the contrary scores recorded in the same row (L336–339) — "confirmed" and "outvoted" in one record, no flag distinguishing them.
- **It never consults fusion's direction.** `structural_direction(intent, trend)` (L79–95) reads only intent × trend. Fusion can emit `direction=LONG, intent=TRANSITION`; with trend BEARISH the table returns **PUT** — governed direction opposite to fusion direction on the same row.
- **It can convert a refusal into a trade.** Fusion's fail-closed OBSERVE_ONLY becomes UNRESOLVED via the table's catch-all (L95), which is *eligible* for evidence resolution — two agreeing evidence families flip a declined name to CALL/PUT at HIGH confidence.
- The famous `VANGUARD_SUPPORT_DIRECTION_REPAIR` is **unreachable dead code** (the prefix can never match, OI:4114 vs 4002), and `DIRECTION_OVERRIDDEN` is validator vocabulary with no writer.

Downstream, the Lab materializer then **creates the two-direction-populations defect mechanically** (Section E): `canonical_direction/direction/final_direction` come from a fallback chain that includes `options_direction` and **the selected contract's side** (lab_control L1885), while `governed_direction` is a verbatim copy (L1949) — never compared. `_side_from_value` cannot represent STRANGLE (L619–631), so all 20 governed-STRANGLE rows *must* appear directional in the canonical columns. Four different direction-resolution orders coexist inside lab_control alone. And the canonical side **re-selects the contract symbol to match itself** (L661–686) — after which the economics-identity check detects the symbol mismatch and blanks EV/locks the row: a direction flip that destroys its own economics. That is the atlas's 111-PUT/90-CALL vs 104-CALL/77-PUT/20-STRANGLE finding, explained.

### 2. The evening's verdict is re-decided three more times with different rules, and each stage disagrees with the last by construction

- **Morning Gate wipes the evening economics for every hydrated row** — not just repaired ones (morning_gate 3643–3656) — and rebuilds monetisability from the **live morning ask vs the fixed EOD target at expiry intrinsic** (selected_contract_economics 568–590). Any overnight premium mark-up mechanically degrades MONETISABLE → LIMITED/NOT_MONETISABLE with no change in thesis; an IV crush "improves" it. The flip tracks the quote, not the edge.
- **Morning Gate and Execution Gate enforce different physics minutes apart.** Spread: ≤18% of mid (Morning) vs ≤15% of ask ≈16.2% of mid (Execution) — every Morning GO in the (16.2%, 18%] band flips to `COST_DESTRUCTION` the same morning. Delta: 0.20–0.75 hard (Morning) vs 0.30–0.60 soft/0.20–0.85 hard (Execution) — 0.61–0.75 passes clean then is auto-downgraded. A **missing** delta silently passes Morning (1765) and becomes `DELTA_EXTREME` CONTRACT_REPAIR at Execution (default 0.0, execution_gate 68–77/110).
- **Unknown permissions fall through the Execution Gate** (`_morning_permission` handles only literal BLOCK/FLAG plus a small mapped set): Morning FLAG lanes `MODEL_RISK_REVIEW` and `REVIEW_REQUIRED` are unmapped, so a Morning **FLAG** carrying stale EOD `READY_EXECUTE/BUY_NOW` fields can exit as **BUY_NOW**. In the opposite direction, one soft warning (spread >8% of ask, delta outside 0.30–0.60, runway <1.5%, above-gamma outside a bull regime) voids BUY_NOW → BUY_SMALL (356–372). The corridors don't nest: the two authorities flip rows in both directions on the same run.
- **The Lab then re-adjudicates anything the gate said that it doesn't recognise.** `COST_DESTRUCTION` is not in the Lab's final_action map (lab_control 1328–1337) nor its hard states — the exact defect AVS-SA-RR-001 described ("how COST_DESTRUCTION becomes GO_LIMIT") is confirmed at line level: unmapped gate verdicts fall to the research resolver and can resurface ARMED/WAIT, or GO via morning permission (1673).
- Rounding it off, a Morning GO on a legacy-lifecycle row is **guaranteed** demotion at the OLM guard (DEFER list includes `LEGACY_LIFECYCLE_NOT_EVALUATED`), and if such rows are the only GOs the finalizer **aborts the whole run** (source_go>0 ∧ lab_actionable==0, finalizer 669–684) — "edge lost by end of run" as a literal hard failure mode.

### 3. Status logic inverts its own evidence at the EOD manifest

In `eod_candidate_engine` the evaluation *order* creates contradictions: an inferred catalyst watch overlay **demotes an EIL EXECUTE** to watchlist (L1124 fires before the EXECUTE check at L1127) while the same catalyst fields count as a *positive* in tiering — Tier A + WATCH_ONLY on one row. A direction conflict returns **TRIGGER_READY with no trigger** (L1103–1105). The contrarian TRAP trigger — which fires when flow opposes the row's own setup — is GO-eligible and checked **before** EIL verdicts (trigger 578–587; eod 1116). A NaN-vs-blank test that never matches real NaNs (L2074/2080/2086) silently starves the WBS/discovery/vanguard fills. The slate-skew guard is dead (NameError swallowed, L2639–2641). RR thresholds disagree across layers (manifest floor 0.0, Tier B 1.0, Tier A 1.5, exit-rules validity 1.5) so Tier B/C rows ship stamped `RR_BELOW_1.5_REVIEW`.

### 4. Several "signals" are noise generators or dead weight wearing production labels

- **SuperBrain (144KB) is fully dead** on the nightly path — the orchestrator passthrough replaced it; zero import sites (Section D) — yet its `sb_*` vocabulary still gates downstream logic.
- WBS scores **only** `sb_final_verdict ∈ {EXECUTE, EXECUTE_WITH_RISK}` rows, and a data-missing row scores 25 → UNLIKELY (defaults sum), manufacturing pessimism instead of "unknown"; the manifest's wall fallback ignores side (`put_wall or call_wall` for CALLs).
- The scanner's GO/PROBE decision contains **zero directional input**; `scanner_direction` is a separate weak vote (momentum-0 ties break toward CALL) and OLIS can attach a wrong-side contract to a GO ticker as PRIME_LONG; LSS comp4 is a constant 25 because short-borrow data is hard-coded unavailable; VMS rewards backwardation +15 while OLIS penalises it −5 — the same feature scored in opposite directions in one file's outputs.
- Bond CHECK 4 **cannot affect the verdict** (bond_pass never enters the ladder, morning_gate 2406–2580); macro flip check is display-only with `macro_pass=True` hard-coded (2144); `regime_changed=TRUE` also prints when the EOD regime was merely missing.

### 5. Unit, vocabulary and side asymmetries corrupt comparisons at every seam

Spread lives as fraction-of-mid, percent-of-mid, and fraction-of-ask in different fields (morning 949 vs 2612 vs execution 247), with a Lab unit heuristic (×100 when ≤1, lab_control 1531) that can hard-veto a tight contract. IV/forecast-vol rescale by /100 above magnitude 5. Direction vocabularies (LONG/SHORT vs CALL/PUT vs BUY/SELL_SETUP vs BULLISH/BEARISH) are translated by at least six different mappers, one PUT-first (`normalise_side`), one that treats unknown tokens as SHORT geometry (asymmetry gate). Systematic side asymmetries: execution GATE-04 runway uses the put wall for both sides and GATE-05's bypass set is bullish-only — PUTs accrue penalties CALLs avoid; Morning Gate's CHECK 3 reads `evening_direction` first while the GDR overwrite deliberately skips that field (233–236) — an EOD direction flip makes the invalidation check test the **wrong side's inequality**, blocking "thesis invalidated" while the lifecycle says the thesis is intact.

### What this means for the rebuild

The five mechanisms map cleanly onto the scale-back: (1) one direction record with one resolution order, written once, displayed everywhere (WS4/D4 in AVS-SD-001 — this document supplies the exact lines to delete); (2) one physics rulebook shared by Morning Gate and Execution Gate — same spread basis, same delta band, closed permission vocabulary with an explicit "unknown ⇒ MANUAL_REVIEW" rule, and a Lab that refuses rather than re-adjudicates unmapped final_actions; (3) a re-ordered, table-driven EOD status ladder with the NaN merge and dead guards fixed; (4) delete SuperBrain and the dead scanner components, make WBS emit UNKNOWN not UNLIKELY; (5) one units module and one side-vocabulary module, imported everywhere — the same pattern MSI already mandates for enums.

Parts A–E follow with the complete per-file logic.

---

# SECTION A — Direction chain (direction_governance, swing_fusion, asymmetry gate, phase validator, sector alignment, governed states)

# AVSHUNTER Direction Chapter — Governed Resolver and Supporting Modules

---

## 1. `/mnt/user-data/uploads/AVSHUNTER-Intelligence/contracts/direction_governance.py` (510 lines)

### Role / invocation
Deterministic, model-free direction authority for the long-option pipeline. Invoked from `scripts/avshunter_options_intelligence.py` (imports at :117–118; `structural_direction(intent, trend)` at :3984; `resolve_governed_direction(...)` at :3992–4000). `preliminary_discovery_direction` is invoked from `avshunter_discovery_ULTIMATE.py:1580` (Stage 0 hint). Module header (L1–8) states generated targets, selected contracts and Discovery defaults are never admitted as resolution evidence.

### Constants (L19–40)
- `DIR_CALC_VERSION = "dir_v1.1.0"` (L19), `RESOLUTION_POLICY_VERSION = "strangle_resolution_v1.1.0"` (L20), `GDR_SCHEMA_VERSION = "governed_direction_record_v1"` (L21).
- Value sets: `DIRECTED = {CALL, PUT}` (L27), `NON_DIRECTIONAL = {STRANGLE, UNRESOLVED}` (L28).
- Thresholds: `MIN_EVIDENCE_FAMILIES = 2` (L30), `MIN_WINNING_SHARE = 0.60` (L31), `MIN_DIRECTION_MARGIN = 0.20` (L32).
- `EXCLUDED_DIRECTION_EVIDENCE` (L34–40): `discovery_direction_preliminary`, `footprint_direction`, `generated_target`, `selected_contract_side`, `catalyst_direction_without_independent_provenance`.

### Normalisers (L43–76)
- `_text` (L43–47): None → `""`; `"NAN"/"NONE"/"NULL"/"N/A"` (case-insensitive) → `""`. So a literal `"NONE"` direction string is treated as **missing**, not as a state.
- `_number` (L54–59): float coercion, NaN → None.
- `_truthy` (L62–63): only `"1"/"TRUE"/"YES"/"Y"/"ON"`.
- `normalise_side` (L66–76): exact match on the 4 canonical states first (L68–69); then **PUT tokens checked before CALL tokens** — any of `PUT/SELL/BEAR/SHORT` substring → PUT (L70–71); any of `CALL/BUY/BULL/LONG` → CALL (L72–73); `STRADDLE/NON_DIRECTIONAL/MIXED/TRANSITION` → STRANGLE (L74–75); everything else → UNRESOLVED (L76). Asymmetry: a string containing both token families (e.g. `"BUY_TO_SELL"`) resolves PUT because PUT is tested first.

### `structural_direction(precor_intent, trend)` — the FULL closed table (L79–95)

| intent | trend | output | basis string |
|---|---|---|---|
| `BUY_SETUP` | (any) | **CALL** | `precor_intent=BUY_SETUP` (L83–84) |
| `SELL_SETUP` | (any) | **PUT** | `precor_intent=SELL_SETUP` (L85–86) |
| `TRANSITION` | `BULLISH` | **CALL** | L88–89 |
| `TRANSITION` | `BEARISH` | **PUT** | L90–91 |
| `TRANSITION` | anything else / missing | **STRANGLE** | `trend={value or 'MIXED'}` (L92) |
| `WAIT` | (any) | **UNRESOLVED** | L93–94 |
| anything else (incl. `OBSERVE_ONLY`, missing) | (any) | **UNRESOLVED** | `precor_intent={intent or 'MISSING'}` (L95) |

Note: `OBSERVE_ONLY` (a legal fusion intent, see §2) is **not** an explicit row — it falls to the L95 catch-all as UNRESOLVED, which is then *eligible for evidence-based resolution* (see below). Trend is consulted **only** for TRANSITION; the fusion `direction` field is never consulted.

### `preliminary_discovery_direction(fusion_direction, wyckoff_direction)` (L98–104)
Iterates `(fusion_direction, wyckoff_direction)` **in that order**; returns the first value normalising to CALL or PUT; otherwise UNRESOLVED. Never defaults to CALL (docstring L99). Consequence: if fusion refused (`NONE` → UNRESOLVED after `_text` strips it) but the raw Wyckoff engine `trade_direction` is LONG, the preliminary is CALL — the hint can contradict fusion's refusal. Called at `avshunter_discovery_ULTIMATE.py:1578–1583` with `fusion_result['direction']` and `wyckoff_data['trade_direction']`.

### Evidence collection — `collect_resolution_evidence(row)` (L134–205)
One vote max per family; four families:

1. **ACTUARIAL** (L148–158): first directed value among row fields `vanguard_edge_direction`, `layer2__edge_direction`, `layer2__probability_direction`, `edge_direction`. Weight **1.0**. Source name `VANGUARD_EDGE_DIRECTION`.
2. **CATALYST** (L160–185): side from `catalyst_direction_bias` or `catalyst_trade_bias` (L183). Admitted only if ALL of:
   - `catalyst_trade_class != "STRUCTURE_ONLY_NO_CATALYST"` (L164);
   - one of: `catalyst_detected` truthy, `catalyst_data_quality ∈ {CONFIRMED, INFERRED}`, `catalyst_event_status ∈ {CONFIRMED, ACTIVE, UPCOMING}` (L165–169);
   - `catalyst_direction_independent` truthy AND `catalyst_direction_source` non-empty AND `catalyst_direction_source_field ∈ {CATALYST_DIRECTION_BIAS, TRADE_BIAS, EXPECTED_IMPACT}` (L171–182).
   Weight **1.0**.
3. **PRICE_FLOW** (L187–192): `directional_force` numeric with `|force| >= 5.0`; side = CALL if `force > 0` else PUT (L189); weight `min(1.0, max(0.50, |force|/20.0))` (L191) — 0.5 at threshold, 1.0 at |force|≥20.
4. **RELATIVE_STRENGTH** (L194–202): `relative_strength_20d or sector_relative_strength_20d or rs_20d` (or-chained at L195–197 — a legitimate `0.0` in the first field silently falls through to the next); requires `|rs| >= 0.02`; side = CALL if positive (L200); weight `min(1.0, max(0.50, |rs|/0.10))` (L201).

Sorted by `(family, source, side)` for reproducible hashing (L205). Maximum possible evidence: 4 items, total weight ≤ 4.0.

### `resolve_governed_direction(...)` — full algorithm (L231–348)
Inputs (keyword-only, L232–239): `ticker`, `run_id`, `discovery_direction` (preliminary), `governed_direction` + `governed_basis` (from `structural_direction`), `row` (raw signal row), `decided_at_utc`.

1. Normalise governed and preliminary sides (L242–243).
2. Collect evidence; `call_score` / `put_score` = sums of weights per side (L245–247).
3. `winning_side`: CALL if call>put, PUT if put>call, `""` on exact tie (L249). `winning_share = winning/total` (0.0 if no evidence, L252); `margin = (winning − losing)/total` (L253). (Note: with only two sides, `margin = 2·share − 1`, so `margin ≥ 0.20 ⇔ share ≥ 0.60` and `margin ≥ 0.50 ⇔ share ≥ 0.75` — the margin thresholds are mathematically redundant with the share thresholds.)
4. `supporting_families` = families of evidence items voting for the winner (L254–256).
5. Defaults (L258–260): `final_direction = governed`; if governed ∈ {CALL, PUT}: `resolution_path = "DIRECTION_CONFIRMED"`, `governance_status = "CONFIRMED"`; else path `"UNRESOLVED"`, status `"NOT_RESOLVED"`, confidence `""`.
6. **Resolution trigger** (L264–269): fires only when `governed ∈ {STRANGLE, UNRESOLVED}` AND winning_side is directed AND supporting families ≥ 2 AND share ≥ 0.60 AND margin ≥ 0.20. Then (L270–293): `final_direction = winning_side`, path `"DIRECTION_RESOLVED_PRECONTRACT"`, status `"RESOLVED"`, confidence `"HIGH"` iff share ≥ 0.75 and margin ≥ 0.50 else `"MEDIUM"`; a single resolution-chain entry `stage="OPTIONS_PRECONTRACT_RESOLUTION"` recording from/to, protocol, full evidence dicts, excluded evidence, scores, thresholds, reason, timestamp.
7. Builds the canonical GDR (L295–320: `dir_key`, `preliminary`, `governed` {direction, authority=`OPTIONS_INTELLIGENCE`, basis, decided_at}, `resolution_chain`, `final`, `policy` {version, sha256}), sha256-hashes the canonical JSON (L321–322), returns ~20 flat fields (L324–348) including `final_direction`, `direction_resolution_path`, `direction_governance_status`, `direction_resolution_confidence`, the four score/share/margin fields, evidence JSON, chain JSON, record JSON + hash.

**Key behaviors:**
- **STRANGLE and UNRESOLVED are emitted** only by `structural_direction` (or passed-in governed values normalising there); **they are resolved to CALL/PUT** only via the L264–269 gate.
- **A directed governed direction is never overridden.** If governed = CALL and the evidence is unanimously PUT, final stays CALL with path `DIRECTION_CONFIRMED` — the contrary scores are *recorded* (L336–339) but exert zero force. There is no repair/override branch in this module at all.
- Exact score tie → `winning_side = ""` → no resolution (L249, L265).
- Zero evidence → share 0.0 → no resolution.

### `validate_direction_record(row)` (L364–482)
- Version must equal `dir_v1.1.0` (L375–376); GDR JSON + hash present and hash matches (L378–384); policy version/sha checked in both flat fields and record (L392–399); flat fields must match record-recovered fields (L400–409).
- `final_direction` must be CALL/PUT — else `DIRECTION_NOT_EXECUTABLE` (L410–411); so STRANGLE/UNRESOLVED rows can never pass validation.
- If final == governed: chain must be **empty** and path must be `DIRECTION_CONFIRMED` (L416–420). If final ≠ governed: chain required (L422–423), last link `to` must equal final (L425–426), protocol must match (L427–428), every evidence item must carry `direction_independent: true` (L433–435), ≥2 supporting families (L438–439), share/margin re-checked against policy (L440–443), and **path must be `DIRECTION_RESOLVED_PRECONTRACT` or `DIRECTION_OVERRIDDEN`** (L444–445). `DIRECTION_OVERRIDDEN` is accepted here but is **never produced anywhere in this module** — a validator-only vocabulary for a writer that no longer exists (or lives elsewhere).
- Dependent-side invariants (L447–474): with or-chained price fields (`live_price or underlying_price or signal_price or scanner_price`, L448–451 — again 0/falsy fall-through) and target/invalidation aliases: CALL requires target > signal and invalidation < signal; PUT the mirror (L465–474).
- `selected_contract_side`/`monetisability_direction` must match final if directed (L476–481). Returns `(True, "DIRECTION_INTEGRITY_CONFIRMED")` (L482).

### `VANGUARD_SUPPORT_DIRECTION_REPAIR` — status: vestigial, not in this module
It appears **nowhere in `direction_governance.py`**. The only occurrence in the codebase is `scripts/avshunter_options_intelligence.py:4114–4115`, where an output flag `vanguard_support_direction_repair` is set true iff `direction_override_reason` starts with that prefix. But `direction_override_reason` is assigned at OI:4002–4005 as `direction_record['direction_resolution_path']` when final ≠ governed — whose only possible values are `DIRECTION_CONFIRMED`, `UNRESOLVED`, `DIRECTION_RESOLVED_PRECONTRACT`. The prefix can therefore **never match; the flag is permanently False**. The comment at OI:3981–3983 confirms the old L1/L2 repair writers ("the previous WAIT, transition and asymmetric L1/L2 repairs were hidden writers of direction") were removed and replaced by this evidence protocol. The prior review's "repair" writer is dead code retained as an audit field.

---

## 2. `/mnt/user-data/uploads/AVSHUNTER-Intelligence/swing_fusion.py` (261 lines)

### Role / invocation
"Single authority for direction and intent" at the Discovery stage (docstring L6–7). Called from `avshunter_discovery_ULTIMATE.py:1368–1372` inside a `try/except Exception` (1367–1386) that logs at **debug** level only and leaves `fusion_result = {}` — a fusion crash silently yields direction `NONE` downstream (`fusion_result.get('direction','NONE')` at discovery:1575).

### Inputs / outputs
Inputs: `wyckoff` dict (`current_phase`, `operator`, `control_state`, `truth_confidence`, `phase_evidence_strength`, `contradictions`), `crabel` dict (`state`, `score`, shelf fields), optional `precor` (audit only, L56–57 and L239 — "never used for decisions"). Output dict (L110–117): `direction ∈ {LONG, SHORT, NONE}`, `intent ∈ {BUY_SETUP, SELL_SETUP, TRANSITION, OBSERVE_ONLY}`, `alignment_score` 0–100, `contradictions` list, `fusion_rule_fired` string, `audit` dict.

### Normalisation (L64–76)
- Phase via monkey-patched `WyckoffPhase.normalise` (L255–261): exact member match else UNKNOWN. (Unconditional monkey-patch at import time, L261.)
- `operator`: raw `.upper().strip()` only — **no alias map** (L65); any variant string not exactly in `Operator.LONG_OPERATORS = {ACCUMULATION, MARKUP}` / `SHORT_OPERATORS = {DISTRIBUTION, MARKDOWN}` (enums_structural) silently produces direction NONE.
- `control` via `ControlState.normalise` (legacy `BUYERS_IN_CONTROL` etc. mapped).
- `float()` on `truth_confidence`/`phase_evidence_strength`/`score` (L68–69, 76) with defaults 0.0 for missing keys but **no try/except for non-numeric strings** — a bad value raises and is swallowed by the caller's bare except (silent NONE).

### Direction rule — `_determine_direction` (L124–135)
- `BUYERS` control AND operator ∈ {ACCUMULATION, MARKUP} → **LONG** (L131–132)
- `SELLERS` control AND operator ∈ {DISTRIBUTION, MARKDOWN} → **SHORT** (L133–134)
- Anything else (EQUILIBRIUM, SHIFTING, UNKNOWN control; mismatched control/operator) → **NONE** (L135)

### Alignment score formula — `_compute_alignment_score` (L138–187)
Start **50**; then:
- **+20** if (crabel COILING AND phase ∈ {A,B,C}) OR (crabel READY AND phase ∈ {C,D}) (L158–163); else a "synergy absent" note is appended (L165–167).
- **+10** if LONG+BUYERS or SHORT+SELLERS (L170–173). By construction of `_determine_direction`, this is automatic whenever direction ≠ NONE — a redundant bonus, so every directed candidate starts effectively at 60.
- **−30** if phase UNKNOWN (L178–180).
- **−20** if `len(contradictions) >= 2` (L183–185) — counts only the *incoming* Wyckoff contradictions; the notes generated inside this function are appended to the outward list *after* scoring (L87) and do not self-penalize, but they **do inflate** `contradictions` and `audit.contradictions_count` seen downstream.
- Clamp 0–100 (L187). Max attainable = 80.

### Intent gate — `_determine_intent` (L190–235), evaluated in order
1. `alignment_score < 50` → **OBSERVE_ONLY** ("fail closed", L209–210).
2. phase UNKNOWN → **OBSERVE_ONLY** (L213–214).
3. `evidence < 30` → **OBSERVE_ONLY** (L217–218).
4. direction NONE → **OBSERVE_ONLY** (L221–222).
5. crabel NONE AND phase ∈ {A,B,C} AND `evidence < 50` → **TRANSITION** (L225–226). Note this fires *after* the NONE gate, so TRANSITION always coexists with a directed LONG/SHORT `direction` field — but the intent string carries no direction.
6. LONG → **BUY_SETUP** (L229–230); SHORT → **SELL_SETUP** (L232–233).
7. L235 fallback is unreachable (all three Direction values handled).

The `truth_conf` and `contradictions` parameters are accepted (L195, 197) but **never used** in the body — silent dead inputs.

### Missing-data behavior
Missing phase → UNKNOWN → OBSERVE_ONLY; missing control → UNKNOWN → NONE; missing evidence → 0.0 → OBSERVE_ONLY; missing crabel state → NONE. All silent defaults, no error surfaced.

---

## 3. `/mnt/user-data/uploads/AVSHUNTER-Intelligence/asymmetry_gate_swing.py` (194 lines)

### Role / invocation
Computes entry/stop/target/R from Crabel shelf geometry + ATR14; replaces the hardcoded `stop_loss = price * 0.97` (L6–7). Called from `avshunter_discovery_ULTIMATE.py:1377–1382` only when fusion direction ∈ {LONG, SHORT}.

### Inputs / outputs
Inputs: `direction` (LONG/SHORT/NONE), `crabel_result` (shelf_high/shelf_low/shelf_width), `df_daily` (high/low/close), `cfg` (overrides `asymmetry_breakout_buffer` default **0.003**, `asymmetry_atr_k` default **0.75**, `asymmetry_min_r` default **2.0** — L39–41, 71–73). Output (L136–148): `entry, stop, target1, R_to_T1, asymmetry_pass (R ≥ min_r, L124), reason, shelf_high/low/width, atr14, error`. Failure record (`_fail`, L155–168): all Nones, `R_to_T1=0.0`, `asymmetry_pass=False`.

### Logic
1. Shelf from crabel; if `shelf_high`/`shelf_low` missing, **silently recomputed** as 30-bar max-high/min-low (`_SHELF_LOOKBACK=30`, L42; `_compute_shelf` L171–177) — a far wider range than a compression shelf, and the `reason` string never flags the substitution. `_compute_shelf` has a **bare `except Exception: return None, None`** (L176–177).
2. Missing shelf after fallback → fail (L84–85). `shelf_width` missing/≤0 → recomputed high−low (L87–88); still ≤0 → fail (L94–95).
3. ATR14 = rolling mean of true range (`_compute_atr14` L180–194); None/0 → fail (L99–100); **bare `except Exception: return None`** (L193–194).
4. direction NONE → fail (L103–104).
5. **LONG** (L107–113): `entry = shelf_high·(1+buffer)`; `stop = shelf_low − k·ATR`; `target1 = entry + shelf_width`; guard entry ≤ stop → fail; `R = (target1−entry)/(entry−stop)`.
6. **SHORT — but actually `else`** (L115–121): `entry = shelf_low·(1−buffer)`; `stop = shelf_high + k·ATR`; `target1 = entry − shelf_width`; guard stop ≤ entry → fail; `R = (entry−target1)/(stop−entry)`.

**Asymmetry:** the direction gate checks only `== Direction.NONE` (L103) then `if LONG ... else SHORT` (L107/L115). Any unexpected direction string — e.g. `"CALL"`, `"PUT"`, `"BUY"` — is silently treated as **SHORT** geometry. Current discovery call site only passes LONG/SHORT, but any future caller using the governance CALL/PUT vocabulary would get short-side entry/stop for a call idea with no error.

---

## 4. `/mnt/user-data/uploads/AVSHUNTER-Intelligence/wyckoff_phase_validator.py` (316 lines)

### Role / invocation
Strict adjudication layer above the permissive discovery Wyckoff engines (docstring L1–8). Called from `avshunter_discovery_ULTIMATE.py:1536` (`validate_wyckoff_phase`), output namespaced by `prefixed_validation_fields` (L314–316, prefix `wyckoff_validation_`).

### Inputs / outputs
Inputs: `ticker`, `bars` DataFrame, `wyckoff_data`, optional `precor_data`. Output (L289–311): `wyckoff_structure ∈ {ACCUMULATION, DISTRIBUTION}`, `wyckoff_phase ∈ {A..E, UNKNOWN}`, `phase_probability`, `alternative_phase(+probability)`, `phase_correctness_score`, `phase_maturity_score`, `phase_status ∈ {INVALIDATED, UNCERTAIN, PHASE_COMPLETE, TRANSITION_IMMINENT, LATE_ACTIVE, ACTIVE, EARLY_ACTIVE}`, `last_confirmed_event`, `event_sequence_valid`, `completed_phase_events`, `missing_phase_events`, `contradicting_evidence`, `transition_probability_{5,10,20}_bars`, `expected_bars_remaining`, `next_expected_event`, `structural_invalidation_level`, `timeframe_alignment="UNASSESSED"` (hardcoded, L309), `phase_churn_warning`.

### Core logic
- **Event tables** (L19–32): accumulation A={SC,AR,ST}, B={TR,ST,ABSORPTION}, C={SPRING,TEST}, D={SOS,LPS}, E={TREND_CONTINUATION}; distribution A={BC,AR,ST}, B same, C={UTAD,UT}, D={SOW,LPSY}, E same. Aliases L33–38.
- **`_mode`** (L81–90): text from `precor.wyckoff_mode` or `wyckoff.wyckoff_mode`; "DISTRIBUTION"/MARKDOWN/SELLERS → DISTRIBUTION; "ACCUMULATION"/MARKUP/BUYERS → ACCUMULATION; else control_state==SELLERS → DISTRIBUTION; **otherwise default ACCUMULATION (L90)** — an asymmetric bull default: EQUILIBRIUM, SHIFTING, UNKNOWN control all classify as ACCUMULATION, which flips the event table AND the invalidation side.
- **Phase adjudication `_phase_from_evidence`** (L109–135): precor phase wins if `pre_strength > wy_strength` strictly (L115); alt phase falls back to `transition_bias`/`transition_to` hint (L126–134). No unit reconciliation between `phase_evidence_strength` (0–100) and `wyckoff_phase_conf` — if precor emits 0–1 confidences it can never win.
- **Completed events** (L138–148): `dominant_event` + precor `primary_event`, plus substring mining of first 8 `notes_all` items — "ABSORPTION" adds ABSORPTION, "RANGE"/"TRADING RANGE" adds TR.
- **Sequence score** (L151–167): phases A/B: 65 if current-phase event present else 45. Phases C/D/E: `(60 if current_ok else 25) + prior_ratio·40` where prior_ratio = hit fraction of all events required through this phase.
- **Duration score** (L170–184): missing age → 45; A: `age·14`; B: `35+2·age`; C: `85−4·age` (decays); D: `35+3·age`; E: `55+1.5·age`; all clamped 0–100.
- **Correctness** (L244–250): `seq·0.30 + phase_strength·0.25 + event_strength·0.20 + acceptance·0.15 + context·0.10`; acceptance = transition_conf (×0.75 unless `phase_progression == "towards_next"`, L241); context = `truth_conf − 8·len(contradictions)` (L242).
- **Maturity** (L258–264): `required_done·100·0.35 + duration·0.20 + proximity·0.20 + next_phase_evidence·0.15 + exhaustion·0.10`; exhaustion = `100 − 18·len(contradictions)` (L257).
- **Ambiguous** (L268–272): alt phase known, not the expected next phase, and `|phase_prob − alt_prob| <= 10`. **Invalidated** (L273–277): `truth_conf < 25` OR (`phase_strength < 35` AND `event_strength < 35`) OR (≥3 contradictions AND correctness < 55).
- **Transition probabilities** (L279–283): `p10 = clamp((maturity·0.55 + transition_conf·0.45)/100, 0, 0.95)`; `p5 = min(p10·0.60, 0.90)`; `p20 = min(p10+0.20, 0.98)`; **if invalidated, forced up to ≥0.65/0.80/0.90** (L282–283) — an invalidated phase reports *high* transition probabilities; a consumer reading probabilities without checking `phase_status` reads urgency where there is invalidation.
- **Status thresholds** (L201–214): INVALIDATED; UNCERTAIN if ambiguous or correctness<60; PHASE_COMPLETE if maturity≥90; TRANSITION_IMMINENT if maturity≥76 and p10≥0.60; LATE_ACTIVE ≥61; ACTIVE ≥31; else EARLY_ACTIVE.
- **Invalidation level** (L187–198): `wyckoff.stop_loss` if present, else 40-bar min-low (ACCUMULATION) / max-high (DISTRIBUTION) — so the L90 mode default also picks which *side* the structural invalidation sits on.
- `next_expected_event` (L287) actually holds a **phase letter** (alt_phase) when available, not an event name.
- `_as_float` (L53–59) silently defaults any non-numeric to 0.0.

---

## 5. `/mnt/user-data/uploads/AVSHUNTER-Intelligence/scripts/sector_alignment.py` (488 lines)

### Role / invocation
Single source of truth for the 9-field sector alignment contract; consumed by superbrain, options intelligence (`classify_from_row` at OI:8660), EIL, FinalDecisionEngine, monetisation (docstring L7–9). Sector bias is a **sizing** input (4th multiplier in FinalDecisionEngine, L63), not a direction writer — but its BLOCK flag can veto a direction-bearing idea.

### `load_sector_bias_map(macro_json)` (L96–178)
- Primary: `sector_rotation.sector_bias_map` — keys upper-cased; values coerced to TAILWIND/NEUTRAL/HEADWIND/MIXED, **anything else silently becomes NEUTRAL** (L126–129) — a typo'd bias value is neutralised without warning.
- Fallback: derive from `sector_lead`/`sector_avoid` ETF arrays (also `extras.sector_tilt.lead_long|long|avoid`, L149–155): lead → TAILWIND, avoid → HEADWIND, and **lead overrides avoid** on conflict (L166 comment + guard) — a sector in both lists is TAILWIND.
- Neither present → empty map, warning log, everything downstream UNKNOWN (L173–176).

### `load_macro_conviction` (L181–199): searches `macro_conviction`/`conviction_score` top-level then extras; **silent default 0.60** (L199).

### `classify_sector_alignment(ticker, gics_sector, sector_bias_map, macro_conviction=0.60, macro_regime_state="")` (L206–345)
- Regime state comes from the argument **or the env var `AVSHUNTER_MACRO_REGIME_STATE`** (L237–241) — a hidden global input.
- Bias lookup (L253–272): no GICS → UNKNOWN/`unknown`; else exact key match, then **bidirectional substring partial match** over the map (first hit in dict order wins, L263–267); no hit → NEUTRAL with source `macro_json` (L268–269); empty map → UNKNOWN with source `"inferred"` (L271–272) — mislabeled (nothing is inferred; L317 note then wrongly says "no GICS sector data").
- Flags (L274–325): TAILWIND → `BOOST`; HEADWIND → warning log if conviction ∈ [0.65, 0.80) (L283–289), then **`SECTOR_RISK_OFF_BLOCK` only if regime == RISK_OFF** (L291–300), else `HEADWIND_REDUCE`; MIXED → `REDUCE`; UNKNOWN → `REDUCE`; NEUTRAL → `NEUTRAL`. Note: `HEADWIND_BLOCK_CONVICTION_THRESHOLD = 0.80` (L76) and its comment ("HEADWIND → BLOCK at ≥0.80 conviction") are **dead** — the block was redesigned to be regime-gated (comment L290), so with the env var unset HEADWIND never blocks regardless of conviction.
- Score multipliers (L66–72): TAILWIND 1.10, NEUTRAL 1.00, MIXED 0.80, HEADWIND 0.55, UNKNOWN 0.80; `alignment_score` from map with UNKNOWN fallback (L333).
- Returns the 9 fields (L335–345): `macro_sector_bias`, `sector_alignment_label`, `sector_alignment_score`, `sector_alignment_flag`, `sector_etf_mapped`, `gics_sector_norm`, `sector_bias_source`, `sector_conviction_context`, `sector_alignment_note`. Contract at L82–90 says flag values are `BLOCK | REDUCE | NEUTRAL | BOOST`, but the code actually emits `SECTOR_RISK_OFF_BLOCK` and `HEADWIND_REDUCE` — consumers matching the documented literals will miss both.

### `classify_from_row(row, ...)` (L352–415)
Sector lookup order: `gics_sector`, `gics_sector_norm`, `sector`, `scanner_sector` (undocumented in its own docstring L361–366), `gics_industry`; then ETF reverse-map fallback (`sector_etf`/`sector_etf_mapped`/`macro_sector_etf` → local `_ETF_TO_GICS` table L395–407) — the D-MACRO-SEC-002 fix so OI rows carrying only `sector_etf` don't silently classify UNKNOWN (L368–371). Self-test/regression at L422–487.

---

## 6. `/mnt/user-data/uploads/AVSHUNTER-Intelligence/contracts/governed_states.py` (41 lines)

Pure vocabulary; no logic. `_ValueEnum` (L14–16) is a str-Enum whose `__str__` returns the literal so states survive CSV/JSON boundaries (docstring L1–7).

- `GovernedDataState` (L19–27): `AVAILABLE`, `PENDING_MORNING_REFRESH`, `NOT_APPLICABLE`, `UNAVAILABLE_PROVIDER`, `DATA_DEFECT`, `STALE_ADVISORY`, `CONTRACT_REPAIR_REQUIRED`, `SYNTHETIC_RESEARCH_ONLY`.
- `LifecycleEvaluationState` (L30–34): `NOT_EVALUATED_NON_DIRECTIONAL` (the lifecycle bucket for STRANGLE/UNRESOLVED rows), `MISSING_AUTHORITATIVE_STOP` (used as `stop_source` in OI when no authoritative stop, seen at OI ~4126), `DATA_DEFECT_WRONG_SIDE`, `SUPERSEDED_DATA_DEFECT`.
- Frozensets of the literals (L37–40). Explicitly "do not grant execution or capital authority" (L3–4).

---

## Observations relevant to contradicting signals (evidence-only)

1. **The governed resolver can flip a fusion refusal into a tradeable direction.** Fusion's fail-closed outputs (`OBSERVE_ONLY` from `swing_fusion.py:209–222`) reach `structural_direction` as an unlisted intent → UNRESOLVED via the catch-all (`direction_governance.py:95`), which is *eligible* for evidence resolution (L264–269). Two agreeing families (e.g. ACTUARIAL 1.0 + RELATIVE_STRENGTH 0.5, unopposed → share 1.0) convert a name fusion declined into `final_direction=CALL/PUT` with confidence HIGH. The evening record then shows fusion OBSERVE_ONLY next to a governed directed final.

2. **Fusion direction is never consulted by the structural table.** `structural_direction(intent, trend)` (`direction_governance.py:79–95`; called at OI:3984) uses only intent and trend. Fusion's TRANSITION intent is emitted while `direction` is LONG or SHORT (`swing_fusion.py:225–226`, reachable only past the NONE gate at L221). With intent=TRANSITION and trend=BEARISH the table returns **PUT** (L90–91) even when fusion's own `direction=LONG` — a direct intra-row contradiction between `fusion_direction` and `governed_direction`.

3. **Directed governed directions are never challenged.** The resolution gate (`direction_governance.py:264`) runs only for STRANGLE/UNRESOLVED. Governed CALL with put-dominant evidence ships as `DIRECTION_CONFIRMED` while the same row carries `direction_resolution_put_score > call_score` (L336–339) — contradictory fields in one output row by design, with no flag distinguishing "confirmed with supporting evidence" from "confirmed against the evidence".

4. **The preliminary hint can contradict fusion.** `preliminary_discovery_direction` (L98–104) falls through to the raw Wyckoff engine `trade_direction` (discovery:1578–1583) when fusion is NONE — so `discovery_direction_preliminary` can be CALL while fusion said no direction. It is excluded from evidence (L35) but is still displayed/carried, adding a third direction opinion per row.

5. **`VANGUARD_SUPPORT_DIRECTION_REPAIR` is unreachable.** OI:4002–4005 sets `direction_override_reason` to a `direction_resolution_path` value; the prefix check at OI:4114–4115 can never match; `vanguard_support_direction_repair` is always False. Likewise `DIRECTION_OVERRIDDEN` is accepted by the validator (`direction_governance.py:444`) but produced nowhere — orphaned vocabulary suggesting a removed override writer.

6. **Vocabulary translation is lossy and PUT-first.** `normalise_side` (L66–76) checks PUT tokens before CALL; `_text` (L43–47) converts literal `"NONE"` to missing. `asymmetry_gate_swing.py:103–121` treats every non-NONE, non-LONG string as SHORT — a CALL/PUT-vocabulary caller would silently get short-side geometry.

7. **Silent bull default in the phase validator.** `_mode` (`wyckoff_phase_validator.py:81–90`) defaults to ACCUMULATION for unknown/equilibrium/shifting control, choosing both the event table and which *side* the structural invalidation level sits on (L187–198) — an accumulation-labelled structure can accompany a governed PUT.

8. **Invalidated phases report elevated transition probabilities** (`wyckoff_phase_validator.py:282–283`): p5/p10/p20 floored at 0.65/0.80/0.90 when invalidated — urgency-looking numbers on structurally dead reads.

9. **Silent failure paths that convert errors into NONE/UNKNOWN**: discovery's fusion wrapper `except Exception` logging at debug (discovery:1383–1386); bare excepts in `asymmetry_gate_swing.py:176–177, 193–194`; the 30-bar shelf fallback (L81–82) substituting a much wider range without flagging it in `reason`; or-chained field fallbacks that skip legitimate zeros (`direction_governance.py:195–197, 448–464`).

10. **Redundant thresholds and dead config**: `MIN_DIRECTION_MARGIN` is mathematically implied by `MIN_WINNING_SHARE` (margin = 2·share−1, L252–253); `HEADWIND_BLOCK_CONVICTION_THRESHOLD` (`sector_alignment.py:76`) is unused after the RISK_OFF redesign (L290–300), and the actual flag literals (`SECTOR_RISK_OFF_BLOCK`, `HEADWIND_REDUCE`) diverge from the documented contract (`BLOCK | REDUCE | NEUTRAL | BOOST`, L85) — a consumer matching documented literals treats headwind rows as unrecognised.


---

# SECTION B — Morning path (morning_gate, handoff finalizer, execution_gate, selected_contract_economics, OLM guard)

# AVSHUNTER Morning-Path Logic Audit

All line numbers refer to the files under `/mnt/user-data/uploads/AVSHUNTER-Intelligence/`. Spread policy constants are imported from `contracts/long_option_policy.py` (executable max **18.0%**, reviewable max **25.0%**, `LONG_SINGLE`/`CALL`/`PUT` only — lines 12–17 there).

---

## 1. `morning_gate.py` (3,895 lines) — the production Morning authorization engine

### Role / invocation
- Docstring (1–34): "Fail-closed morning validation", CHECK 0–7 enumerated; "Morning GO means MORNING_VALIDATED only"; module "never writes LIVE_AUTHORIZED".
- Entry points: CLI `main()` (3771–3890): resolves `run_id` from `--run-id` or `_latest_run_id()` (762–775, reads `data/output/latest.json` or the lexically last runs dir); requires both `POLYGON_API_KEY` and `MARKETDATA_API_KEY` (3805–3807); calls `run_morning_gate()` (3815); then imports and calls `finalize_morning_handoff(run_id, results, sync_interpreter=False)` (3817–3828), runs post-Lab score integrity (3835–3843), and only if `integrity_status == "PASS"` calls `sync_verified_morning_handoff` (3879–3882). Any exception in the handoff → `return 1`, "run is incomplete" (3887–3889).
- Also imported by the orchestrator (`run_morning_gate`), which applies the same CDS defaults as `configure_cds_runtime_for_morning_gate()` (137–169).

### Inputs
- `data/output/runs/{run_id}/morning_validation/morning_candidates_{run_id}.csv` (2900–2911) — the evening/EOD candidate rows. Missing file → `FileNotFoundError` (fail-closed, 2906–2908).
- `dropbox/macro/macro_intelligence_latest.json` (`_load_macro_state`, 1213–1245): fields `regime_state|regime_label|macro_regime`, `dir_bias`, `risk_on_off_switch`, `vol_mode`, `macro_conviction`, `sector_lead`, `sector_avoid`, `macro_filter`, `size_multiplier`, `as_of_utc`, `vix_spot`. **Any error → `{"regime_state":"UNKNOWN","macro_loaded":False}` silently (1244–1245)**.
- `dropbox/macro/bond_macro_state.json` (`_load_bond_macro`, 1248–1336): returns `{}` if missing/unreadable/older than 26h (`BOND_MACRO_MAX_AGE_H`, line 85); unparseable timestamp → `pass` and proceed with data (1282–1283, silent). If `yield_curve.stale_flag` is true, **`bond_trade_go` is forced `True`** (1301) and score/state fields suppressed.
- `avshunter_macro_enrichment_delta.json` (1339–1362) → `{TICKER: BEARISH|BULLISH}`, `{}` on any failure.
- `china_revenue_exposure.json` (1365–1377), `{}` on any failure.
- Live: Polygon equity snapshot per ticker (`_fetch_live_price`, 782–816), MarketData option quote per OCC leg (`_fetch_live_contract`, 819–869), MarketData skew chain (`_fetch_options_skew`, 1380–1431).
- Optional CDS control-plane sqlite + MSI resolver (2913–2993).

### Outputs
- `morning_validation/morning_validated_trades_{run_id}.csv` — **all rows (GO + FLAG + BLOCK)** written (3142); the header list in the docstring (22–28).
- `morning_validation/morning_gate_summary_{run_id}.json` (3161–3202, re-written at 3289 and again in `main()` 3871).
- `score_integrity_{run_id}.json` (510), `final_run_manifest.json` closure (691–759). Note manifest always sets `run_tradeable=False` and `morning_capital_permission` = `HUMAN_APPROVAL_REQUIRED` iff `go_count>0` else `NO` (737–747). **There is no per-row `tradeable=True` anywhere in this file; "tradeable" at the run level is hard-false (743).** The actionable notion is `verdict == "GO"` / `morning_execution_permission == "GO_LIMIT"`.
- CDS thesis/selection/quote persistence (`_persist_morning_liquidity_result`, 2630–2888).

### Live-quote hydration flow (`_fetch_all_live`, 1068–1206)
1. Per ticker (`fetch_one`, 1079–1192): `_fetch_live_price` — `live_price = lastTrade.p or day.c` (797–798). **Both use `_f(...) or ...` so a legitimate 0.0 falls through; if both are 0/None, `live_price` is absent → downstream FLAG/WAIT.** Any exception → `{"live_fetch_error", "live_data_source":"POLYGON_FAILED"}` (815–816) — the ticker silently proceeds without a spot.
2. OCC symbol resolution order: `evening_contract_symbol` → `contract_symbol` → `recommended_contract` → `preferred_contract` (1083–1088).
3. CDS fresh-quote reuse if a lifecycle observation for the same `thesis_id` is <60s old and matches the OCC symbol (1090–1157); reuse errors are swallowed with `log.warning` (1142–1143). Otherwise `_hydrate_live_structure` → `hydrate_selected_structure` (1016–1028) with MarketData fetch.
4. `_check_contract` is run on the primary (1164); result stamped as `primary_contract_pass/reason` (1165–1167).
5. **Contract repair**: if primary fails, `_try_live_repair_alternatives` (1031–1065) walks `alternative_contract_1..3` (1000–1013), hydrates each, and the **first alternative that passes the same `_check_contract` becomes the executable contract** (`morning_contract_repair_used=TRUE`, `morning_repair_contract_symbol`, attempts trail). If none pass, the last alternative's live data (with `morning_contract_repair_used=FALSE`) still overwrites `live` (1058–1064, 1173–1174). If the row has no primary symbol at all, alternatives are tried directly (1175–1181).
6. AG-03 skew fetch (1182–1184): ATM call/put IV ~30 days out; ratio >1.10 → `CALL_SKEW_HIGH`, <0.90 → `PUT_SKEW_HIGH` (94–97, 1416–1431); failures → `SKEW_UNAVAILABLE`.
7. MSI capture (`_capture_msi_market_observations`, 872–998) re-registers the same quote in CDS and **overwrites** `live_contract_bid_size/ask_size` and writes `morning_*`/`current_*` prefixed fields. **Unit mismatch: `morning_contract_spread_pct`/`current_contract_spread_pct` are set to `spread_fraction_mid` (a fraction, 949) while `live_contract_spread_pct` is percent (410 in economics module).**
8. Fetch failures at the future level only `log.warning` and drop the ticker from `live_map` (1196–1204) — that row then runs the gate with empty `live_data` (3077).

### Per-row gate (`run_gate`, 2010–2627) — sequence

**Stamping/overwrites first:**
- `_ensure_governed_direction_record` (209–237): if `dir_calc_version` missing, builds a legacy adapter GDR; **when `final_direction` exists it overwrites `direction`, `canonical_direction`, `resolved_direction`, `primary_direction`** (233–236). It does **not** overwrite `evening_direction`.
- All `live_data` keys are copied over the row (2032–2033) — **any same-named EOD column is overwritten by the live value.**
- Repaired contract stamping (2035–2093): overwrites `contract_symbol`, `recommended_contract`, `morning_selected_contract_symbol`, `selected_contract_side`; copies `live_contract_*` → `contract_*` (2052–2071); sets `premium_mid` to the live mid (2072); **blanks all inherited R:R/EV3 fields** (2074–2081): `rr_premium_expected, rr_options, option_rr, rr_predicted, rr_contract_symbol, rr_evaluation_id, option_gain_at_target, ev_predicted, ev3_*`; sets `ev3_status=NOT_EVALUATED_CONTRACT_CHANGED`, `economics_comparable=False`, `economics_recompute_required=TRUE` (2082–2091).
- `_apply_thesis_direction_guard` (392–458, applied at 2095):
  - GDR rows (397–408): re-stamps `final_direction` into the four direction fields; `morning_direction_lock_status = LOCKED_GDR_FINAL` if directional else `BLOCKED_GDR_NON_DIRECTIONAL`. **Morning never re-votes direction for governed rows — it locks the GDR final.**
  - Legacy rows: if `footprint_direction` ∈ {CALL,PUT} and lock status starts `LOCKED` or reroute is `MAJOR_CATALYST_DIRECTION_OVERRIDE` (419–421), and current direction differs, **morning overrides the (catalyst-driven) direction back to the footprint** across `direction/canonical/resolved/primary/evening_direction` (425–428), writes `direction_reroute_status=CATALYST_CONFLICT_THESIS_PRESERVED`, `direction_conflict_gate=VWAP_CONFIRMATION_REQUIRED` (434–440), and rewrites the leading token of `thesis_summary` (445–448).
  - If the selected contract's side (from `selected_contract_side`, then `P0`/`C0` substring of the symbol, then delta sign — `_contract_side_from_row`, 365–380) disagrees with the footprint: `morning_direction_guard_contract_side_conflict=TRUE`, `contract_repair_required=TRUE` (450–456). Note the `P0`/`C0` substring heuristic can misfire on strikes containing those digit patterns.
- Economics recompute: `hydration_attempted = "selected_structure_hydration_status" in live_data` (2096); if attempted, `_recompute_selected_contract_economics(out, live_data)` (2099; body 3638–3764):
  - **Unconditionally blanks** the inherited `rr_*`, `monetisability_*`, `ev_predicted`, `ev3_*` fields for **every hydrated row, not just repaired ones** (3643–3656). Evening monetisability is destroyed and rebuilt from the live quote.
  - If hydration != COMPLETE: `monetisability_state=DATA_MISSING`, `economics_recompute_required=TRUE`, `selected_contract_economics_ready=False`, return False (3658–3674).
  - If COMPLETE: copies `selected_*` and `live_contract_*` → `contract_*` fields, sets `contract_symbol`/`recommended_contract`/`morning_selected_contract_symbol` to the hydrated symbol (3676–3708); runs `recompute_premium_rr` (3711) and `evaluate_long_option_monetisability` (3714); monetisability != COMPLETE → not ready, return False (3716–3724). Then EV3 advisory recompute (3727–3739); `economics_comparable` requires `selected_structure_id == rr_evaluation_id == ev3 evaluation id` (3740–3749); an EV3 mismatch still leaves `economics_recompute_required="FALSE"` (3762) because EV3 has no authority.
- Lifecycle (`_morning_liquidity_lifecycle`, 1829–2003, called 2117–2123): required inputs = side, current_spot, thesis_spot, strike, target, invalidation, dte, hold, forecast_vol, selected_symbol (1888–1898). Missing any →
  - `contract_changed` → `CONTRACT_REPRICE_REQUIRED` (1901–1911);
  - legacy row (no `thesis_id`/`lifecycle_contract_version`/`liquidity_state`) → `LEGACY_LIFECYCLE_NOT_EVALUATED`, `executable_now=False` (1916–1929) — **fail-open: this state is exempted from flag reasons (2432–2435) so the row can still reach GO**;
  - otherwise `CONTRACT_REPRICE_REQUIRED` (1930–1939, fail-closed FLAG).
  - Complete inputs → `evaluate_options_liquidity_lifecycle` (1941–1957); exceptions → `LIFECYCLE_DATA_INVALID` / `CONTRACT_REPRICE_REQUIRED` (1958–1968). Transition mapping (1970–1985): `THESIS_INVALIDATED` > repriced-without-economics → `CONTRACT_REPRICE_REQUIRED` > `MOVE_ALREADY_REALIZED` > `WAIT_FOR_PULLBACK`/`GAP_CONFIRMATION_EXTENDED` > (liquidity != EXECUTABLE_NOW) → `LIQUIDITY_STILL_PENDING` > `GAP_CONFIRMATION_WITH_RUNWAY` > `EXECUTABLE_NOW`.
  - `_morning_forecast_vol` (1813–1826) silently rescales values >5.0 by /100.
  - `_morning_hold_sessions` (1794–1810) falls back to parsing digits out of `hold_label/hold_period/time_horizon` text.

### The checks (as executed, 2126–2163)

| # | Function | PASS condition | FAIL behaviour on missing data |
|---|---|---|---|
| Direction integrity | `validate_direction_record` (contracts/direction_governance.py 364–481) via 240–241, 2126 | `final_direction` ∈ {CALL,PUT}, chain consistent, target/invalidation topology valid, contract side matches | fail-closed → BLOCK |
| CHECK 0 upstream authority | 244–264 | `authority_source_stage == FINAL_EXECUTION` (247), `final_route` ∉ {OPTIONS_BLOCKED, OPTIONS_EQUITY_ONLY_BETTER} (250), `capital_authorization_state == EOD_CANDIDATE_ONLY` (258), `capital_permission == EOD_CANDIDATE_ONLY` (261), `eod_candidate_authorized` truthy (263) | any missing → fail-closed BLOCK |
| CHECK 1 monetisability | 267–277 (wrapped by `_check_premium_economics` 280–282; "R:R no longer has capital authority") | state `MONETISABLE` or `LIMITED` | `NOT_MONETISABLE` → fail; anything else → `MONETISABILITY_DATA_MISSING` fail (fail-closed BLOCK) |
| CHECK 2 EV3 | 285–288 | **always True** — advisory only. 2130–2138 forcibly sets `ev3_authority_active=False`, `ev3_capital_authority=ADVISORY_ONLY` (overwriting any upstream EV3 authority claim) |
| CHECK 3 invalidation | 1480–1516, called 2140 | direction ∈ {CALL,PUT}; invalidation (`invalidation_spot` → `ev3_invalidation_spot` → `evening_invalidation_price`) > 0; CALL: `live_price > invalidation` (1511); PUT: `live_price < invalidation` (1513) | `live_price is None` → fail but **routed to FLAG/WAIT, not BLOCK** (2417–2419, 2497–2504) — fail-safe-open on missing spot. **Missing/zero invalidation → fail-closed BLOCK** (1505–1509 + 2505–2512), but with lane `THESIS_INVALIDATED` and unlock text "Thesis invalidated by morning price action" (2510–2512) — a missing stop is mislabelled as a broken thesis. Note `if not invalidation` treats 0.0 as missing (1505). **Direction read order here is `evening_direction` first (1489)** — see observations. |
| CHECK macro flip | `_check_macro` 1523–1542 | EOD regime recorded and no base-direction flip (`_regime_flipped`, 1434–1454: only BULL↔BEAR↔NEUTRAL base changes count) | missing EOD regime → fail — but **`macro_pass` is hard-coded True (2144)** and macro never enters the ladder; only `regime_changed` display is written: `"TRUE" if not macro_change_pass` (2174), so **a missing EOD regime prints `regime_changed=TRUE` without any flip** |
| Macro permission | 1545–1552 | always True (advisory) | fail-open by design |
| CHECK 5 contract | `_check_contract` 1706–1791 | see below | quote missing → fail → FLAG `CONTRACT_REPAIR`; but combined with economics wipe it usually becomes BLOCK (see observations) |
| CHECK 4 bond | `_check_bond_macro` 1457–1473 | empty state → pass "check skipped" (1462–1463, fail-open); `bond_trade_go` False → fail | **result stamped only as `check_bond_macro_pass/reason` (2239–2240); `bond_pass` never appears in block/flag assembly (2406–2436) nor the ladder (2438–2580) — CHECK 4 is display-only and cannot affect the verdict.** Stale curve forces `bond_trade_go=True` (1301). `bond_trade_go` itself is excluded from output (2236–2238). |
| CHECK 7 Layer-3 model risk | 291–351 | no flags: `l3_forward_realised_vol < 2.50` (310), not (conf ≤ 65 and vol ≥ 1.50) (312–318), `l3_n_bars ≥ 100` (319), `abs(l3_iv_tailwind_score) ≤ 1.50` (321) | any flag → FLAG `MODEL_RISK_REVIEW`; missing inputs are skipped silently (fail-open per-metric) |

### `_check_contract` details (1706–1791)
1. `_production_strategy_policy` (1620–1676): blocks any structure containing SPREAD/VERTICAL/STRANGLE/STRADDLE/IRON_/CONDOR/BUTTERFLY/CALENDAR/DIAGONAL/RATIO/MULTI_LEG/COMPOSITE, any multi-symbol selection, or any structure ≠ `LONG_SINGLE` → `RESEARCH_ONLY_UNSUPPORTED_PRODUCTION_STRUCTURE` (1642–1657). **Strangles are therefore hard-blocked (BLOCK/RESEARCH_ONLY), never traded.** Side must resolve to CALL/PUT (1669–1670).
2. Direction-guard contract-side conflict → fail (1719–1720).
3. Vertical leg validation (1725–1746) exists in this checker (both legs' bid/ask > 0, bid ≤ ask; spread taken from `selected_max_leg_spread_pct`) even though verticals are blocked by rule 1 when `row` context is present.
4. `bid is None or ask is None` → "No live contract quote — repair contract before entry" (1748–1749); `bid<=0` (single) or `ask<=0` → invalid (1751–1752).
5. Spread: `_governed_spread_limits` (1611–1617) — executable max **18%**, review max **min(--spread-threshold, 25%)**; CLI can only tighten (102–105, 3774–3783). `spread > review_max` → fail "hard maximum" (1755–1756); **`spread > 18%` → fail "Manual liquidity review"** (1757–1761). `spread_pct is None` → both spread tests skipped (silent pass on missing spread when bid/ask present).
6. Greeks (row context, 1764–1783): `abs(delta) < 0.20` fail (too OTM); `abs(delta) > 0.75` fail (deep ITM); `delta is None` → skipped silently. `IV ≤ 0` or `> 2.50` fail; `IV None` → skipped. IV compression: `live_iv/eod_iv < 0.70` → fail "Premium actively deflating — FLAG for trader review" (1778–1783; EOD IV from `implied_volatility_eod|iv_eod|contract_iv|iv`).
7. Post-check override (2156–2161): if hydration was attempted and economics recompute incomplete, `contract_pass` is forced False regardless of the above.

`_spread_policy_state` (1679–1704) separately classifies `UNAVAILABLE` / `BLOCKED_SPREAD` (>25) / `MANUAL_LIQUIDITY_REVIEW` (18–25) / `EXECUTABLE_SPREAD` (≤18).

### Reason assembly and verdict ladder (2406–2580)
Reason lists (2406–2436): authority, direction, economics (**only appended when `not repaired_contract`**, 2415 — a repaired-then-NOT_MONETISABLE row can end BLOCK with an empty `block_reason` column), invalidation (FLAG if spot missing else BLOCK), strategy, `BLOCKED_SPREAD`, contract fail → flag, model risk → flag, lifecycle terminal → block, other lifecycle states except `EXECUTABLE_NOW`/`GAP_CONFIRMATION_WITH_RUNWAY`/`LEGACY_LIFECYCLE_NOT_EVALUATED` → flag.

Ladder (first match wins):

| Rung | Condition | verdict | `morning_execution_permission` | route / lane |
|---|---|---|---|---|
| 2438 | !authority | BLOCK | NOT_ELIGIBLE | STAND_DOWN_UPSTREAM_AUTHORITY |
| 2446 | !direction | BLOCK | NO_GO_DIRECTION | STAND_DOWN_DIRECTION |
| 2454 | !strategy | BLOCK | RESEARCH_ONLY | OPTIONS_RESEARCH_ONLY |
| 2462 | THESIS_INVALIDATED | BLOCK | BLOCKED | STAND_DOWN / THESIS_INVALIDATED |
| 2470 | MOVE_ALREADY_REALIZED | BLOCK | NO_GO_MOVE_ALREADY_REALIZED | STAND_DOWN_NO_CHASE |
| 2478 | CONTRACT_REPRICE_REQUIRED | FLAG | CONTRACT_REPAIR | REPAIR_CONTRACT |
| 2489 | !economics | BLOCK | NO_GO_ECONOMICS | STAND_DOWN_ECONOMICS / NON_MONETISABLE |
| 2497 | live_price None | FLAG | WAIT | WAIT_LIVE_PRICE / LIVE_PRICE_UNAVAILABLE |
| 2505 | !inv (spot present) | BLOCK | BLOCKED | STAND_DOWN / THESIS_INVALIDATED |
| 2513 | WAIT_FOR_PULLBACK / GAP_CONFIRMATION_EXTENDED | FLAG | WAIT | WAIT_FOR_PULLBACK |
| 2521 | LIQUIDITY_STILL_PENDING | FLAG | LIQUIDITY_STILL_PENDING | MONITOR_CONTRACT_LIQUIDITY |
| 2529 | BLOCKED_SPREAD (>25%) | BLOCK | NO_GO_LIQUIDITY | STAND_DOWN_LIQUIDITY |
| 2537 | MANUAL_LIQUIDITY_REVIEW (18–25%) | FLAG | MANUAL_LIQUIDITY_REVIEW | SPREAD_REVIEW_18_TO_25 |
| 2545 | !contract_pass | FLAG | CONTRACT_REPAIR | REPAIR_CONTRACT / SELECT_LIQUID_CONTRACT |
| 2553 | model risk | FLAG | MODEL_RISK_REVIEW | MODEL_RISK_REVIEW |
| 2561 | any other flag_reasons | FLAG | REVIEW_REQUIRED (`execution_permission`=ARMED) | REVIEW_BEFORE_ENTRY |
| 2569 | else | **GO** | **GO_LIMIT** | GO_LIMIT / MORNING_VALIDATED |

Final stamps (2582–2604): `verdict`, `morning_gate_verdict`, `execution_permission`, `morning_execution_permission`, `live_validation_state` (`CONFIRMED` iff GO), `final_capital_permission` = `HUMAN_APPROVAL_REQUIRED` (GO) / `REVIEW_ONLY` (FLAG) / `NO` (BLOCK), `execution_authorized=False` always (2604). Morning Gate itself never emits `GO_LIMIT`/`PROBE` as a *verdict* — the verdict set is exactly **GO / FLAG / BLOCK**; `GO_LIMIT` exists only as the permission/route vocabulary for GO (comment 2572–2576).

More overwrites (2606–2613): `premium_mid` and `contract_mid` set to live mid; **`spread_pct` = `live_contract_spread_pct/100` only when the value > 1, else kept raw (2612)** — a 0.9% spread is stored as `0.9` in a field otherwise holding fractions (unit ambiguity for downstream readers). `selected_long_leg`/`selected_short_leg` dicts are dropped from CSV output (2617–2618).

### Market-structure restart logic
`_market_structure_populations` (3322–3353): docstring explicitly states "A repeated Morning Gate invocation is expected to change GO/FLAG/BLOCK as prices develop"; the canonical worklist is the full candidate universe while calculation runs only for the current GO subset — restart-idempotent. Structure enrichment (3356–3486) is post-decision advisory only (comment 3109–3112). CDS persistence replay: once a thesis is terminal in the store, later reruns return `TERMINAL_REPLAY_REUSED` without recording (2684–2689).

---

## 2. `morning_handoff_finalizer.py` (777 lines)

### Role / invocation
No API calls (docstring 1–8). Called by `morning_gate.main()` with the in-memory results, or standalone CLI (`--run-id`, 753–772) replaying `morning_validated_trades_{run_id}.csv` (575).

### Core flow (`finalize_morning_handoff`, 554–750)
1. Rows: passed results or re-read CSV (575). Empty → error (62, 69).
2. **Runs the Execution Gate** on the morning rows (`run_execution_gate`, 584–588, output to `runs/{run_id}/trades/`). Row-count mismatch → `MorningHandoffError` (589–593).
3. **OLM invariant re-check** (`_olm_execution_mismatches`, 177–206): re-evaluates `evaluate_olm_execution_guard(row, require_contract=True)` per row and fails the run if any `final_action` exceeds the guard ceiling (`action_is_within_guard`) or if the emitted `olm_guard_disposition`/`olm_guard_reason` drifted (595–601).
4. Macro advisory stamping (606–631): `materialize_interpreter_macro_context`; each row gets advisory fields; a before/after snapshot of authority fields (`governed_direction`, `selected_contract_symbol`, `thesis_state`, `olm_guard_disposition`, `final_action`, `capital_permission`, `execution_permission`, `position_size_pct`) must be unchanged or the run errors (614–631).
5. Writes final run manifest + Lab opportunity book (633–644); Lab row count must equal input (646–650).
6. **Execution↔Lab reconciliation** (`_execution_lab_mismatches`, 92–174): per ticker — `lab_verdict` must equal `EXECUTION_TO_LAB[final_action]` (114–120) where the map (38–45) is `BUY_NOW→GO`, `BUY_SMALL→GO_LIMIT`, `CONTRACT_REPAIR→CONTRACT_REPAIR`, `MANUAL_REVIEW→MANUAL_REVIEW`, `BLOCK→BLOCKED`, `SKIP→BLOCKED`; `final_action` must survive verbatim (121–123); contract identity preserved (`_contract_identity`, 78–89: first non-empty of `selected_contract_symbol`, `morning_selected_contract_symbol`, `contract_symbol`, `live_contract_symbol`, `recommended_contract`, `O:` stripped) (124–129); six direction fields byte-identical (130–144); seven macro fields byte-identical (145–160); actionable rows must pass `validate_direction_record` (161–171). Plus run-level `dir_calc_version` uniformity (653–661). Any mismatch → run error.
7. **Authority-preservation invariant** (669–684): `source_go` counts rows whose `morning_execution_permission` ∈ `ACTIONABLE_LAB_VERDICTS = {GO, GO_LIMIT, PROBE}` (37); `lab_actionable` counts `lab_verdict` in the same set. **If `source_go > 0` and `lab_actionable == 0` the whole run raises `MorningHandoffError`** — i.e., if the Execution Gate downgrades every morning GO_LIMIT to MANUAL_REVIEW/CONTRACT_REPAIR, the run is declared failed rather than published with zero actionables.
8. MSI publication (`_publish_msi_handoff`, 347–476): actionable = `final_action` ∈ {BUY_NOW, BUY_SMALL} (365–370); identity preflight requires non-empty `ticker`, `thesis_id`, `trade_idea_id`, `selected_structure_id`, `selected_contract_symbol`, `selected_quote_snapshot_id` and matching `run_id` (248–299) — any miss aborts publication (398–406). Non-PRODUCTION `run_kind` refused (388–391). Independent reconciliation of the manifest must PASS (430–435).
9. Interpreter sync (`_sync_and_verify`, 479–523): copies morning CSV, `execution_gated_*.csv`, Lab triage and final book into MA_Inputs with SHA-256 verification; `sync_verified_morning_handoff` (526–551) is the deferred variant used by `morning_gate.main()`.
10. Summary JSON `morning_handoff_summary_{run_id}.json` (700–742) with verdict/permission/action counts and reconciliation block.

---

## 3. `execution_gate.py` (514 lines) — economics → `final_action`

### Role / invocation
`run_execution_gate(signals, run_id, output_dir)` (422–470), called from the finalizer with `require_olm=True` (432, comment 429–431). Outputs `execution_gated_{run_id}.csv` (all rows), `execution_actionable_{run_id}.csv` (BUY_NOW/BUY_SMALL only, 443, 459–461), `execution_gate_summary_{run_id}.json`. Config (17–31): `SPREAD_FULL=0.08`, `SPREAD_MAX=0.15`, `DELTA_HARD_MIN=0.20`, `DELTA_SOFT_MIN=0.30`, `DELTA_SOFT_MAX=0.60`, `DELTA_HARD_MAX=0.85`, `IV_ELEVATED=0.60`, `IV_EXTREME=1.00`, `MIN_RUNWAY_PCT=0.015`, `TARGET_GAIN_MULTIPLE=2.0`, `TRENDING_REGIMES={TRENDING_BULL,RISK_ON,RECOVERY,STRONG_BULL}`, `PSE_CONVICTION_MIN=0.01`, `PROBE_SIZE_LABEL="BUY_SMALL"`.

### Rule sequence (`execution_gate`, 152–419) — in order, first hit returns
1. OLM guard for every row (159–161); direction invalid → **BLOCK** `DIRECTION_INTEGRITY_FAILED:*` (163–173). Guard disposition ≠ CONTINUE → **that disposition** (`MANUAL_REVIEW`/`CONTRACT_REPAIR`/`BLOCK`) verbatim (180–181).
2. `_morning_permission` (116–129): reads `morning_execution_permission` → `execution_permission` → `verdict`; maps literal `BLOCK`→`BLOCKED`; literal `FLAG` → `CONTRACT_REPAIR` if `check_contract_pass=="FALSE"` else `ARMED`. **All other strings pass through untouched** (see observations).
3. Monetisability identity: state ∈ {MONETISABLE, LIMITED} but selected symbols empty or ≠ `monetisability_contract_symbol` symbols → **CONTRACT_REPAIR** `MONETISABILITY_CONTRACT_IDENTITY_MISMATCH` (183–197).
4. `NOT_MONETISABLE` → **CONTRACT_REPAIR** if any `alternative_contract_1..3` present (`_has_contract_alternative`, 146–150) else **BLOCK** `NOT_MONETISABLE` (198–205).
5. State ∈ {DATA_MISSING, CONTRACT_REPAIR} → **CONTRACT_REPAIR** (206–211).
6. Perm ∈ {GO, GO_LIMIT, PROBE} but state ∉ {MONETISABLE, LIMITED} → **CONTRACT_REPAIR** `MONETISABILITY_STATE_MISSING` (212–215).
7. Perm ∈ {BLOCKED, BLOCK, REJECT, REJECTED} → **BLOCK** `UPSTREAM_BLOCK` (216–217); perm `CONTRACT_REPAIR` → **CONTRACT_REPAIR** (218–223); perm ∈ {WAIT, ARMED} → **MANUAL_REVIEW** (224–229).
8. Live data from the row itself (`_live_option_data_from_row`, 98–113: `live_contract_bid|live_bid|contract_bid` etc.; `ask<=0` → `{}`); fallback `get_live_option_data` is a **stub returning `{}`** (35–40, warns once). Empty → **CONTRACT_REPAIR** `LIVE_CONTRACT_DATA_MISSING` (236). `ask<=0 or bid<0` → **CONTRACT_REPAIR** `LIVE_CONTRACT_QUOTE_INVALID` (244–245).
9. Derived: `mid=(bid+ask)/2` (246); **`spread_pct=(ask-bid)/max(ask,0.001)` — denominator is the ASK** (247), not mid as in Morning Gate. `iv` via `_normalise_ratio` (91–96: values >5 divided by 100); **`iv_rank` silently defaults to 50.0** (112, 243).
10. Campaign synthesis (252–262): missing `campaign_verdict` + perm GO/GO_LIMIT → `READY_EXECUTE`/`BUY_NOW`; perm PROBE → `READY_PROBE`/`BUY_SMALL`; otherwise **MANUAL_REVIEW** `CAMPAIGN_VERDICT_MISSING`. `campaign==REJECT` or `execution==SKIP` → **BLOCK** `UPSTREAM_VETO` (263–264).
11. GATE-01 spread: `>15%` of ask → **CONTRACT_REPAIR** `COST_DESTRUCTION` (267–269); `>8%` → warn `WARN_WIDE_SPREAD`, penalty ×0.5 (270–273).
12. GATE-02 delta (abs, so PUTs symmetric — comment 275): `<0.20` or `>0.85` → **CONTRACT_REPAIR** `DELTA_EXTREME` (276–278); outside 0.30–0.60 → warn, ×0.75 (279–282).
13. GATE-03 IV advisory: `>100%` → warn `WARN_IV_EXTREME`, ×0.5 (285–288); `>60%` **and** `iv_rank>80` → warn, ×0.75 (289–293); else no penalty.
14. Spot: `signal_price` → `current_price` → `underlying_price` → `live_price` (298–300); missing → **MANUAL_REVIEW** `UNDERLYING_PRICE_MISSING` (301–302).
15. GATE-04 runway: `put_wall>0` → `runway=|spot-put_wall|/spot` (**used for both CALL and PUT** — no direction term, 310–312); else `gamma_flip>0 and spot>gamma_flip` → same formula vs flip (313–315). `runway<1.5%` → warn, ×0.5 (316–319).
16. GATE-05 gamma: `spot>gamma_flip` and `rcs_label` not in the trending set → warn `WARN_ABOVE_GAMMA`, ×0.75 (322–331). **The bypass set contains only bullish regimes (28) — bear-trend PUTs never get the bypass.**
17. GATE-06 target vs runway: `target_move_pct = (mid × 2.0)/max(spot, 0.001)` (334) — i.e., the underlying must travel 2× the premium in absolute dollars for the premium to double (a delta≈1 assumption). If `target_move_pct > runway_pct`: conviction override (`campaign_verdict==READY_EXECUTE` ∧ `kelly_verdict` set ∧ `pse_final_size ≥ 0.01`, 62–65) → warn only; else warn + ×0.5 (335–352).
18. Penalty floored at 0.25 (354).
19. Final mapping (356–372): `READY_EXECUTE`: `execution==BUY_NOW` ∧ penalty ≥ 0.75 ∧ **no warnings** → **BUY_NOW**; `execution` ∈ {BUY_NOW, BUY_SMALL} otherwise → **BUY_SMALL**; else BUY_SMALL if conviction override else MANUAL_REVIEW. `READY_PROBE`: BUY_SMALL for {BUY_SMALL, WAIT_RETEST}, else override/MANUAL_REVIEW. `WATCH`: BUY_SMALL only with override and zero warnings, else MANUAL_REVIEW. Anything else → MANUAL_REVIEW.
20. `LIMITED` monetisability caps BUY_NOW → **BUY_SMALL**, penalty ≤ 0.5 (374–377).
21. Success row adds/overwrites `live_bid/ask/mid/spread_pct/delta/iv/iv_rank`, `runway_pct`, `runway_source`, `gamma_state`, `target_move_pct`, `gate_size_penalty`, `gate_conviction_override` (395–416).
22. **Any exception → MANUAL_REVIEW `GATE_EXCEPTION:*` (417–419) — crashes fail open to review, never BLOCK.**

`final_action` vocabulary emitted: `BUY_NOW`, `BUY_SMALL`, `MANUAL_REVIEW`, `CONTRACT_REPAIR`, `BLOCK` (`SKIP` exists only via the unused `_skip` helper, 57–60, and the Lab map). There is no explicit `GO_LIMIT`, `COST_DESTRUCTION` or `LIVE_CONTRACT_DATA_MISSING` action — those are `gate_reason` strings under `CONTRACT_REPAIR`; `GO_LIMIT` re-appears only as the Lab verdict for `BUY_SMALL`. "R:R" here is entirely the GATE-06 proxy: numerator `mid×2` (dollar premium doubling), denominator `spot`; risk denominators elsewhere: spread over **ask**, runway over **spot**.

Silent defaults / bare excepts: `_f` and `_s` swallow everything with bare `except:` (42–55); `_num_value` default 0.0 (68–77) — a missing delta becomes 0.0 → `DELTA_EXTREME` CONTRACT_REPAIR; missing `iv_rank` → 50; missing IV → 0 (no penalty).

---

## 4. `contracts/selected_contract_economics.py` (607 lines)

### Role
Provider-agnostic hydration of the exact selected structure plus deterministic trader-facing economics; used by Morning Gate after selection (docstring 1–7).

### Hydration flow (`hydrate_selected_structure`, 267–427)
1. `parse_selected_structure` (127–209): extracts OCC symbols (`contract_symbols`, 51–70 — JSON list, regex scan, or `/|,;` split), canonicalises structure (`canonical_structure`, 89–105), validates: no symbols → `NO_SELECTED_CONTRACT`; invalid OCC → `INVALID_OCC_SYMBOL`; **any leg whose parsed side ≠ the row direction → `SELECTED_LEG_DIRECTION_MISMATCH` (157–163)**; mixed expiries → `SELECTED_LEG_EXPIRY_MISMATCH` (164–170); vertical must have exactly 2 legs, single exactly 1 (171–187); 2-leg CALL sorts strikes ascending → `BULL_CALL_DEBIT`, PUT descending → `BEAR_PUT_DEBIT` (188–202).
2. Per leg fetch: source ∈ {"", MARKETDATA_NO_QUOTE, MARKETDATA_FAILED} → `SELECTED_LEG_QUOTE_UNAVAILABLE` FAILED (287–298). `_quote_record` (212–254) rejects `bid is None / ask is None / mid is None / bid<0 / ask<=0 / bid>ask / mid<=0` (219–220) — note **bid==0 is accepted here** (Morning `_check_contract` later rejects bid≤0 for singles at 1751). Computes `spread_fraction_mid=(ask-bid)/mid` (241), `dte` from quote date vs expiry (222), `contract_multiplier` defaulting to 100.0 (249, silent default).
3. Single: aggregate = the leg. Vertical: multiplier mismatch → FAILED (322–329); `entry_debit = long.ask − short.bid`, `exit_credit = max(long.bid − short.ask, 0)`, `mid = long.mid − short.mid`; `entry_debit<=0 or mid<=0` → `SELECTED_VERTICAL_DEBIT_INVALID` (330–339). Aggregate spread = `(entry_debit − exit_credit)/mid`; `max_leg_spread_fraction_mid` = worse leg (368–371); Greeks = long − short; OI/volume = min of available; IV = **long leg's IV only** (372).
4. Identity: `selected_structure_id` = `economics_evaluation_id` (108–124) = `ECI1:` + sha256 of `ticker|direction|structure|symbols` — **quote-time-independent** (same contract re-quoted keeps the same id). `selected_quote_snapshot_id` = `QUOTE1:` + sha256 over structure + per-leg (symbol, quote_timestamp, bid, ask, mid, source) (257–264) — quote-time-dependent.
5. Output fields (389–427): `selected_structure_hydration_status/reason/schema_version`, `selected_structure`, `selected_structure_id`, `selected_contract_symbol` (vertical spelled `STRUCTURE:legA/legB`, 312–315), `selected_contract_symbols` JSON, snapshot id, `selected_legs_json`, `selected_long_leg`/`selected_short_leg` dicts, and the full `live_contract_*` family including `live_contract_spread_pct = fraction × 100` (410) and `selected_max_leg_spread_pct` (411–414).

### `recompute_premium_rr` (430–504)
- Direction from `canonical_direction|resolved_direction|direction` (441–443). **Entry spot basis = `live_price` first** (444–446), then `entry_spot|signal_price|underlying_price`; target = `target_spot|target_price|structural_target`.
- Topology guard: CALL target must be above entry spot, PUT below → else `SELECTED_RR_TARGET_TOPOLOGY_INVALID` (455–461). Because entry uses the *live* morning price, an overnight gap through the EOD target fails R:R even though the thesis fields are unchanged.
- Single: `entry_debit = long ask`; `target_value = max(target−strike,0)` (CALL) / `max(strike−target,0)` (PUT) — **expiry intrinsic only, no time value** (467–472). Vertical: `entry_debit = long.ask − short.bid`; target value = capped intrinsic spread (482–488).
- `option_gain = target_value − entry_debit`; **`rr = option_gain / entry_debit`** (489–490) — denominator is the full premium at ask; there is no stop leg, so "R:R" is return-at-target with risk = 100% of premium. Writes `rr_premium_expected`, `rr_options`, `rr_predicted`, `option_gain_at_target`, `rr_evaluation_id = selected_structure_id` (492–504).

### `evaluate_long_option_monetisability` (507–606)
- LONG_SINGLE only; anything else → state `CONTRACT_REPAIR` `PRODUCTION_REQUIRES_LONG_SINGLE` (534–540). Hydration incomplete → `DATA_MISSING` (527–533). Direction/target/leg missing → `DATA_MISSING` (550–556). `entry_ask<=0` or `strike<=0` → `DATA_MISSING` (558–566).
- Formulas (568–578): CALL `breakeven = strike + ask`, `target_intrinsic = max(target−strike,0)`, clears iff `target > breakeven`; PUT `breakeven = strike − ask`, `target_intrinsic = max(strike−target,0)`, clears iff `target < breakeven`. `target_profit = intrinsic − ask`; `target_profit_pct = profit/ask × 100`.
- Classification (579–590): not clearing or profit ≤ 0 → **NOT_MONETISABLE**; `0 < profit_pct < 20.0` (`MONETISABILITY_MIN_PROFIT_PCT`, line 21) → **LIMITED** (eligible); ≥ 20% → **MONETISABLE**. **Entry basis is the current ask; target value is expiry intrinsic** — the classification is deliberately conservative (docstring 513–519) and moves every time the ask moves.

---

## 5. `contracts/options_liquidity_execution_guard.py` (206 lines)

### Role
Translates lifecycle evidence into an execution **ceiling**; `CONTINUE` "is deliberately not an authorisation to trade" (docstring 1–8). Consumed by `execution_gate.py` (per row) and re-verified by the finalizer.

### Every veto (`evaluate_olm_execution_guard`, 84–190), in precedence order
1. No OLM fields present (`_CONTRACT_FIELDS`, 32–38): with `require_contract=True` → **MANUAL_REVIEW** `OLM_LIFECYCLE_REQUIRED`; legacy default → CONTINUE `LEGACY_DIRECT_CALL_NO_OLM_CONTRACT` (96–106). Production always uses `require_contract=True` (execution_gate.py:432).
2. Terminal precedence: `transition==THESIS_INVALIDATED` or `thesis_state ∈ {INVALIDATED, THESIS_INVALIDATED}` or `runway_state==THESIS_INVALIDATED` → **BLOCK** `OLM_THESIS_INVALIDATED` (115–122); analogous **BLOCK** `OLM_MOVE_ALREADY_REALIZED` (123–130).
3. `maturation_execution_authority` truthy → **BLOCK** `OLM_MATURATION_AUTHORITY_VIOLATION` ("contract corruption", 132–138). Morning Gate always writes it False (morning_gate.py:1886, 2001).
4. Transition `CONTRACT_REPRICE_REQUIRED` → **CONTRACT_REPAIR** (140–144).
5. Transition ∈ {WAIT_FOR_PULLBACK, GAP_CONFIRMATION_EXTENDED, LIQUIDITY_STILL_PENDING, EOD_PENDING_MORNING_REQUOTE, **LEGACY_LIFECYCLE_NOT_EVALUATED**} → **MANUAL_REVIEW** (24–30, 145–149).
6. Empty transition → **MANUAL_REVIEW** `OLM_TRANSITION_MISSING` (150–154).
7. Transition ∉ {EXECUTABLE_NOW, GAP_CONFIRMATION_WITH_RUNWAY} → **BLOCK** `OLM_TRANSITION_UNRECOGNISED:*` (155–159).
8. Positive continuation requires **all** of: `lifecycle_contract_version` ∈ {OPTIONS-LIQUIDITY-LIFECYCLE-V1, V2} (163–168), `thesis_state == ACTIVE` (169–174), `liquidity_state == EXECUTABLE_NOW` (175–180), `executable_now` truthy (181–185); each miss → **MANUAL_REVIEW** with a specific reason. Else **CONTINUE** (187–190).

`action_is_within_guard` (193–205): CONTINUE allows {BUY_NOW, BUY_SMALL, MANUAL_REVIEW, CONTRACT_REPAIR, BLOCK, SKIP}; MANUAL_REVIEW allows {MANUAL_REVIEW, CONTRACT_REPAIR, BLOCK, SKIP}; CONTRACT_REPAIR allows {CONTRACT_REPAIR, BLOCK, SKIP}; BLOCK allows {BLOCK, SKIP}. Unknown disposition → nothing allowed.

---

## Observations relevant to contradicting signals and evening→morning flips (evidence only)

1. **Evening monetisability is destroyed and recomputed for every hydrated row, not just repaired ones.** `_recompute_selected_contract_economics` blanks `monetisability_state` and all `rr_*`/`ev3_*` inheritance whenever a hydration was attempted (morning_gate.py:2096–2099, 3643–3656). The rebuilt state uses the **live morning ask** against the fixed EOD `structural_target` with expiry-intrinsic-only value (selected_contract_economics.py:558, 568–590). Any overnight premium mark-up mechanically pushes `target_profit_pct` down, so evening `MONETISABLE` flips to `LIMITED` (caps at BUY_SMALL, execution_gate.py:374–377) or `NOT_MONETISABLE` (BLOCK, morning_gate.py:2489–2496) with no change in the thesis. Symmetrically, an IV crush *helps* — the sign of the flip tracks the quote, not the edge.

2. **A MarketData outage or bad quote becomes a "NO_GO_ECONOMICS" BLOCK.** Hydration failure → `monetisability_state=DATA_MISSING` (morning_gate.py:3658–3674) → `_check_monetisability` fails (270–277) → ladder rung 7 BLOCK `NO_GO_ECONOMICS` (2489–2496) unless the lifecycle happens to hit the earlier FLAG rung. The row is blocked as an economics failure although the docstring path for a missing quote is FLAG `CONTRACT_REPAIR` (1748–1749, 2545–2552). The economics rung sits **before** the contract-repair rung.

3. **Spread definitions and thresholds disagree between Morning and Execution gates.** Morning: `(ask−bid)/mid`, executable ≤ 18%, review ≤ 25% (long_option_policy.py:13–14; selected_contract_economics.py:241; morning_gate.py:1754–1761). Execution: `(ask−bid)/max(ask,0.001)`, hard cap 15% (execution_gate.py:247, 267–269). 15%-of-ask ≈ 16.2%-of-mid, so **every Morning-GO contract with mid-spread in (16.2%, 18%] is guaranteed to flip to CONTRACT_REPAIR `COST_DESTRUCTION` minutes later in the same run**, and 8%-of-ask (≈8.7% of mid) already halves size and voids BUY_NOW (357).

4. **Delta bands disagree.** Morning hard band 0.20–0.75 (morning_gate.py:1768–1771); Execution hard band 0.20–0.85, soft 0.30–0.60 (execution_gate.py:20–23, 276–282). A delta of 0.61–0.75 passes Morning clean but is warned at Execution (×0.75, and the warning alone downgrades BUY_NOW→BUY_SMALL at 357–360). Also, Execution's `_num_value` defaults a **missing** delta to 0.0 (execution_gate.py:110, 68–77) → `DELTA_EXTREME` CONTRACT_REPAIR, while Morning silently *passes* a missing delta (1765–1766) — the same absent field is a pass upstream and a repair downstream.

5. **`_morning_permission` passes unknown permissions straight through — several Morning FLAG lanes can escalate to BUY_NOW.** execution_gate.py:116–129 only special-cases the literal strings `BLOCK` and `FLAG` (used when `morning_execution_permission` is empty). Morning FLAG rows carry `morning_execution_permission` values `MODEL_RISK_REVIEW` (morning_gate.py:2556) and `REVIEW_REQUIRED` (2564) — neither is in the handled sets at execution_gate.py:212–229 — so those rows fall through to the live gates. If the EOD row still carries `campaign_verdict=READY_EXECUTE`/`execution_verdict=BUY_NOW` (252–262 uses the row's own values before synthesising), a Morning **FLAG** can exit the Execution Gate as **BUY_NOW**, i.e. the run's two authorities disagree in opposite directions on the same ticker. (The other FLAG lanes are caught indirectly: `LIQUIDITY_STILL_PENDING` by the OLM defer veto, `WAIT` by 224, `MANUAL_LIQUIDITY_REVIEW` mostly by the 15%-of-ask spread cap — but not the model-risk or catch-all-review lanes, whose OLM transition is `EXECUTABLE_NOW`.)

6. **Morning GO on a legacy row is guaranteed to be demoted.** `LEGACY_LIFECYCLE_NOT_EVALUATED` is exempted from Morning flag reasons (morning_gate.py:2432–2435) so the row can reach GO/GO_LIMIT, but the OLM guard lists that transition in `DEFER_TRANSITIONS` → MANUAL_REVIEW (options_liquidity_execution_guard.py:24–30, 145–149). Morning says GO; Execution says MANUAL_REVIEW. If such rows are the *only* GOs, `source_go>0 ∧ lab_actionable==0` and the finalizer aborts the entire run (morning_handoff_finalizer.py:669–684) — "edge lost by end of run" as a hard failure.

7. **Direction source is inconsistent inside Morning Gate itself.** The GDR path overwrites `direction/canonical/resolved/primary` with `final_direction` but **not `evening_direction`** (morning_gate.py:233–236, 398–401), yet CHECK 3 invalidation (1488–1493), `_assess_macro_context` (1560–1565) and AG-03 skew alignment (2354–2365) all read **`evening_direction` first**, while the lifecycle reads `final_direction` first (1837–1840). If EOD arbitration flipped the side after `evening_direction` was stamped, the invalidation check tests the live price against the **wrong side's** inequality (CALL `<=` vs PUT `>=`, 1511–1514): one internal check can BLOCK "thesis broken" while the lifecycle and direction record simultaneously say the (final) thesis is intact — a direct contradictory-signal mechanism.

8. **Missing invalidation is reported as a broken thesis.** With a live price but no stop, `_check_invalidation` fails `MISSING_AUTHORITATIVE_STOP` (1505–1509) and the ladder emits lane `THESIS_INVALIDATED` with unlock text "Thesis invalidated by morning price action" (2505–2512). Data absence is indistinguishable from a genuine adverse move in the output.

9. **Bond CHECK 4 cannot gate anything.** `bond_pass` is computed (2162) but never consulted in the reason lists or ladder (2406–2580); only `check_bond_macro_pass` display fields are written (2239–2240), `bond_trade_go` is dropped from output (2236–2238), and a stale curve silently forces `bond_trade_go=True` (1301). A bond FLAG in the summary alongside a GO verdict is expected, not contradictory — but reads as contradiction on the desk card.

10. **`regime_changed=TRUE` conflates a flip with missing data.** 2174 sets it from `not macro_change_pass`, and `_check_macro` also fails when the EOD regime was simply not recorded (1536–1537). Neither outcome affects the verdict (`macro_pass=True` hard-coded, 2144), so "regime flipped overnight" can appear next to GO.

11. **Repair alternatives are triggered by review-band spreads.** `_try_live_repair_alternatives` uses `_check_contract`, which fails at >18% (1757–1761); so a primary contract at 19% mid-spread (a FLAG-review condition, 2537–2544) triggers contract *replacement* at fetch time (1169–1174) — the executed symbol can drift from the evening selection for a condition Morning itself classifies as merely reviewable. Every replacement then wipes the EOD economics (2074–2091), whose recompute can in turn change the verdict (see 1).

12. **`GO_LIMIT` means different things at different stages.** Morning `GO_LIMIT` = fully validated, limit-entry-eligible (morning_gate.py:2572–2580). Lab `GO_LIMIT` = the *downgraded* label for `BUY_SMALL` (morning_handoff_finalizer.py:38–45), while a clean Morning `GO_LIMIT` that survives as `BUY_NOW` becomes Lab `GO`. The same token flips from "best outcome" to "second-tier outcome" across the handoff.

13. **A single soft warning voids BUY_NOW.** execution_gate.py:357 requires `not warnings`; spread >8% of ask, delta outside 0.30–0.60, IV>100%, runway <1.5%, above-gamma in a non-bullish regime, or target>runway each independently converts BUY_NOW→BUY_SMALL. Combined with note 3, full-size entries survive only in a narrow corridor much tighter than anything Morning enforces.

14. **Runway and gamma logic are direction-blind / bull-biased.** GATE-04 uses `|spot − put_wall|/spot` for both sides (311–312) — for a PUT the put wall is *support in the profit direction*, yet a large distance reads as "plenty of runway" and a close wall as low-runway penalty identical to a CALL. GATE-05's trending bypass set contains only bullish regimes (28, 326–331). PUT theses systematically accrue penalties that CALLs in bull trends avoid — a CALL/PUT asymmetry that shows up as unexplained BUY_SMALL downgrades on the short side.

15. **Fail-open exception handling at the last gate.** Any exception in `execution_gate` returns MANUAL_REVIEW (417–419), and `_f`/`_s` use bare `except:` (42–55); Morning's fetchers likewise swallow all exceptions (815–816, 868–869, 1408–1409). Missing `iv_rank` defaults to 50 (execution_gate.py:112) which specifically disables the IV-elevated penalty branch (290).

16. **Terminal CDS replay is sticky across intraday reruns.** Once a thesis persists as INVALIDATED/TARGET_REALIZED, later Morning reruns skip persistence with `TERMINAL_REPLAY_REUSED` (morning_gate.py:2684–2689) even though the CSV verdict is freely recomputed (3322–3341 documents that verdicts are expected to change between invocations) — store state and latest CSV can legitimately disagree after a price round-trip.

17. **Unit hazards that can flip downstream comparisons**: `out["spread_pct"]` is a fraction only when the percent value >1 (2612 — 0.9% stays `0.9`); `morning_contract_spread_pct` is a fraction while `live_contract_spread_pct` is percent (949 vs selected_contract_economics.py:410); expected-move fields are percent-vs-fraction normalised by a magnitude heuristic `0.60 ≤ move ≤ 60.0` (3563–3573); `_normalise_ratio`/`_morning_forecast_vol` rescale by /100 above magnitude 5 (execution_gate.py:91–96; morning_gate.py:1813–1826).


---

# SECTION C — EOD manifest & trigger stack

# AVSHUNTER EOD Manifest & Trigger Stack — Logic Reference

Paths under `/mnt/user-data/uploads/AVSHUNTER-Intelligence/`.

## 1. `eod_candidate_engine.py` (2,964 lines — Phase 10, EOD Candidate Engine v1.3.0)

### Role / invocation
Converts the EOD pipeline authority CSV into `morning_candidates_{run_id}.csv` for the Morning Gate. Design principle (L12–18): EOD answers only "is this structurally primed?", morning answers "is it tradeable now?". Entry points: `build_candidate_manifest()` (L1863) and CLI (L2943–2962). **The CLI does not match the docstring's production contract**: the docstring says production must pass `execution_v3_5_{run_id}.csv` (L1880–1882), and `authority_source_stage` is `FINAL_EXECUTION` only when the filename starts with `execution_v3_5_` (L1903–1908) — but the CLI passes `superbrain/eil_enriched_{run_id}.csv` (L2956), yielding `LEGACY_NONFINAL`, and passes **no** trigger overlay, vanguard, or horizon paths.

### Inputs (six sources) and join keys
All six join on **upper-cased `ticker` alone** — no run_id/date in the key, so any duplicate ticker rows collide.

| # | Source | Loader | Collision behaviour | Merge policy |
|---|---|---|---|---|
| 1 | Execution/EIL CSV (base rows) | L1914–1920 | each row processed independently | authority for everything not overridden below |
| 2 | Trigger overlay (post-Trigger-Layer EIL CSV) | `_load_trigger_authority_overlay` L738–775 | **raises** on duplicate/blank tickers (L755–759) | `row.update(trigger_map[ticker])` L2068–2069 — **unconditional overwrite** of the 10 `TRIGGER_AUTHORITY_FIELDS` (L133–144); the only source that replaces non-blank base values |
| 3 | WBS CSV | L1969–1976 | dict overwrite — last row wins | fill-if-blank only (L2072–2075), cols L1980–1986 |
| 4 | Discovery CSV | L1989–1996 | last row wins | fill-if-blank only (L2078–2081), cols L1998–2004 |
| 5 | Vanguard CSV (auto-discovered if path absent, L2033–2043) | L2044–2055 | last row wins | fill-if-blank-**or-zero** (L2084–2087) — `0.0`/`0` also treated as missing |
| 6 | Horizon CSVs 1-5d then 6-10d | `_load_horizon_csv` L1935–1952 | 6-10d file loaded second **overwrites** 1-5d entries for the same ticker (L1951–1952) | resolved at L2128–2137: horizon CSV > EIL row column > defaults `unrouted`/`UNKNOWN`/1.0 |

**Merge bug (silent):** the "blank" test for WBS/discovery/vanguard is `row.get(col) in (None, "", "nan", float("nan"))` (L2074, L2080, L2086). `float("nan") == float("nan")` is False and `in` uses `==`, so a **present-but-NaN field is never treated as blank** — WBS/discovery/vanguard can never fill it. Only truly-absent columns get filled. Vanguard's extra `0.0` clause means it *can* overwrite genuine zeros (e.g. a real `rr` of 0) — an asymmetry vs WBS/discovery.

**Precedence per field family:** trigger fields — overlay authoritative (replaces base); direction — governed direction record in the base row; WBS/discovery — base row wins if it has any non-None value including NaN; RR (`rr_underlying`) — vanguard wins over blank/zero base; horizon — horizon CSV wins for the stamped columns but **not** for status derivation (contradiction #6 below).

### Constants / floors
`MIN_OPTIONS_SCORE=15`, `MIN_RR=0.0`, `MIN_COMPOSITE=40.0` (L125–127). `TIER_A={"options_score":35,"rr":1.5,"conv":3}`, `TIER_B={25,1.0,2}` (L280–281). Carry-forward statuses L147–161; structural-block statuses L163; block/no-route/repairable token sets L165–215.

### Direction handling (locking, footprint, weighting, strangle)
- `_direction_evidence` (L1200–1278) consumes the Options Governed Direction Record from `governed_direction_record_json` (L1203–1210); if `dir_calc_version` absent, a migration adapter resolves from `options_direction`/`canonical_direction` only (L1211–1228 — explicitly "cannot consult the Discovery footprint, targets, contracts or free-text fields").
- **Footprint lock is decommissioned**: `_footprint_direction` (L1145–1152) returns the Discovery preliminary side "for audit only"; `footprint_lock_status="DECOMMISSIONED_GDR_AUTHORITY"` (L1255–1256). `_major_catalyst_can_break_footprint` (L1155–1163) is a shim that **always returns False**.
- **The historic 4:2 footprint-vs-current weighting no longer exists in this file.** `direction_call_score`/`direction_put_score` are pure copies of upstream `direction_resolution_*_score` (L1259–1260); no local re-weighting or reassertion remains.
- **Strangle/unresolved conversion:** if `final_direction` is not CALL/PUT, or the parsed contract side (`_contract_side` L1185–1198 — OCC heuristic `"P0" in text or endswith("P")`, fragile) differs from the resolved side, `direction_contract_reselection_required=TRUE` (L1234–1238) and `_invalidate_direction_dependent_contract` (L1293–1315) **wipes 30 contract fields** (list L1281–1290), sets `contract_repair_required=TRUE`, `contract_repair_status="DIRECTION_RESELECTION_REQUIRED"`. Every STRANGLE/UNRESOLVED row loses its contract and lands in the repair lane.
- `_direction_arbitration` (L905–931): option side vs Vanguard edge side; disagreement → `CONFLICT_STRUCTURE_LEADS` + `direction_conflict_gate=VWAP_CONFIRMATION_REQUIRED`. `_catalyst_direction_conflict` (L933–956). `_normalise_audit_handoff_fields` (L959–1065) combines structural/catalyst/PCR conflicts into `direction_conflict_status=MITIGATED_REQUIRES_CONFIRMATION` (L1017–1028); STAND_DOWN/BLOCK verdicts → `NOT_EVALUATED` (L1014–1016).
- **PUT-only macro asymmetry** (L1044–1064): only PUT candidates have `macro_enrichment_put_gate_permission`/`PUT_GATE_DELTA_LOCK` inspected, stamping `macro_directional_context=HEADWIND` (advisory). No CALL equivalent.
- `_invalidation_level` (L322–339): returns a stop only if direction-correct (CALL: stop<signal; PUT: stop>signal), else `None` — no ATR fallback by design.

### Contract repair profile (L1324–1395)
Score 0–45: premium>0 +5; spread ≤15% +10 / ≤25% +6 (`SPREAD_CAUTION`) else repair codes; OI ≥500 +8 / ≥50 +4 else `OI_REPAIR_NEEDED`; volume ≥50 +5 / ≥10 +3 — **both sub-50 branches only append `VOLUME_CAUTION`** (L1360–1363), so low volume can never be "severe"; delta 0<|d|<0.50 +7 else `DELTA_REPAIR_NEEDED`/`DELTA_UNKNOWN`; rr_options≥1 or gain>0 +10. Severe codes (L1377–1387) include `DELTA_UNKNOWN` — any wiped/missing-contract row is automatically `CONTRACT_REPAIR_REQUIRED`.

### Status derivation `_eod_candidate_status` (L1067–1143) — evaluation order matters
1. Options research block reason → `EOD_NO_OPTIONS_ROUTE` / `EOD_STRUCTURAL_BLOCK` / `EOD_BLOCK` (L1081–1088), via `_eod_failure_class` (L504–512).
2. `_true_fatal_block` (L614–657) → NO_OPTIONS_ROUTE / STRUCTURAL_BLOCK / `EOD_DATA_INSUFFICIENT_REVIEW`. Rescue clause L651–656: signal ∈ `{CURRENT_EDGE, FUTURE_EDGE, STRUCTURAL_MATCH, TRANSITION}` + EIL EXECUTE(_WITH_CAUTION) + OIS≥15 + rr≥0 neutralises a PSE/FD fatal label. **Vocabulary mismatch: the SCS rewards `CONTINUATION` (L1781) but `CONTINUATION` is not in the rescue set.**
3. `direction_conflict_status == UNRESOLVED` → `EOD_DATA_INSUFFICIENT_REVIEW` (L1101–1102); `MITIGATED_REQUIRES_CONFIRMATION` → **`EOD_TRIGGER_READY`** ("FIX 1: a trader note, not a kill", L1103–1105) — **even when `trigger_quality=NONE`**. This early return also skips the contract-repair check.
4. `contract_repair_required` → `EOD_THESIS_READY_REPAIR_AT_OPEN` (L1107–1108); non-`EXECUTABLE_NOW` liquidity_state → same (L1110–1114).
5. `trigger_go_eligible` → `EOD_TRIGGER_READY` (L1116–1117) — **before any EIL verdict check**.
6. `catalyst_trade_class == DATED_CATALYST_CONFIRMED`: + EIL EXECUTE/EWC → `EOD_THESIS_READY`; else `EOD_TRIGGER_READY` (L1119–1122).
7. `EVENT_CONVEXITY_WATCH` **or** quality ∈ {CONFIRMED, DATED_REVIEW, INFERRED_GOOD} → `EOD_WATCHLIST_MONETISABLE` (L1124–1125) — **fires before the EIL EXECUTE check at L1127**: a catalyst *watch* overlay demotes an EIL EXECUTE ticker to watch-only.
8. EIL `EXECUTE` → `EOD_THESIS_READY`; `EXECUTE_WITH_CAUTION` → `EOD_THESIS_READY_REPAIR_AT_OPEN` (L1127–1130).
9. `trigger_quality == STRONG` → `EOD_TRIGGER_READY` "TRIGGER_READY_BUT_EIL_NOT_EXECUTE" (L1132–1133).
10. **EOD_PROBE_CANDIDATE stamping** (L1135–1138): signal ∈ {NO_EDGE, DATA_MISSING} or momentum ∈ {TIER_4_FLAT, DATA_MISSING} **and** `horizon_bucket == "11_20d"` → `EOD_PROBE_CANDIDATE`; other horizons → `EOD_DATA_INSUFFICIENT_REVIEW`. **The `horizon_bucket` read here (L1078) is the EIL row's column — the authoritative horizon-CSV value is resolved only afterwards at L2128–2137**, so the probe decision and the stamped bucket can disagree.
11. Otherwise `EOD_WATCHLIST_MONETISABLE` (L1140–1143).

Mappings: `_handoff_lane` (L584–606); `_candidate_status_for_handoff` (L608–612, THESIS_READY → `READY_FOR_VALIDATION`); `_thesis_state_from_eod_status` (L517–535); `_morning_tasks_for_status` (L537–551); `_candidate_permission_fields` (L553–582 — sizing always 0.0 `PSE_IGNORED_MANUAL_SIZING`; capital permission defaults MANUAL per FIX 5).

### Tiering `classify_tier` (L1798–1860)
WATCH if: options block/no-route class (L1813–1815); UNRESOLVED direction conflict (L1817–1818); quality floor failed (OIS<15, rr<0, comp<40, L1821–1822); true fatal block (L1824–1825). RR = `rr_underlying` first, fallback `rr` (L1801). Then **A** (L1839–1846): OIS≥35 ∧ rr≥1.5 ∧ comp≥55 ∧ (EIL EXECUTE **or** `catalyst_ready`) ∧ (trigger STRONG/go **or** `sb_conv_score≥2` **or** OIS≥45), where `catalyst_ready` = DATED_CATALYST_CONFIRMED or quality ∈ {CONFIRMED, DATED_REVIEW, **INFERRED_GOOD**} (L1830–1833). **B** (L1851–1857): OIS≥25 ∧ rr≥1.0 ∧ comp≥50 ∧ any of (EIL execute-like | any trigger incl. SINGLE | catalyst_ready | campaign | OIS≥45). **C** otherwise. **WBS plays no role in tiering** despite the header's tier definitions (L32–35) — doc/code drift.

### Structural Conviction Score (L1704–1795)
OIS ≥35→25 / ≥25→18 / ≥15→10. RR ≥2.5→20 / ≥1.5→15 / ≥1.0→8 / >0→3. Structural: `min(10, ev2_ev_structural×80)` + composite ≥70→10/≥55→7/≥40→4. **WBS: 0 points, advisory only** (L1746–1748) — the legacy scorer that awarded WBS 15/9/3 (L1633–1643) is dead code; the header's "WBS 15%" table (L37–46) is stale. Campaign: CORE_CAMPAIGN conv≥4→10 / ≥3→8 / →5; STAGED conv≥3→4; else 2. Veto load 0→10 … ≥4→0. Actuarial: CONTINUATION+TIER_1/2→10, TIER_3→7, else 5; TRANSITION TIER_1_ACCELERATING→4 else 3; else 0. Max 95 (cap 100).

### Ranking, guards, output
- Sort: status order (L2553–2571; THESIS_READY=0 … STRUCTURAL_BLOCK=8) → tier → trigger quality → `monetisation_fit_score` desc → `scs_score` desc (L2578–2581); `slate_rank` = row order (L2584).
- `_monetisation_fit` (L1397–1412): OIS/2.5 cap 20 + rr×8 cap 20 + trigger 15/8/0 + EIL 20/12/0 + catalyst_truth/3 cap 15 + contract_quality/2.25 cap 20 + |call−put|×2 cap 10; Tier A +5, WATCH −10; ≥72 `ASYMMETRIC_EXECUTE`, ≥55 `ASYMMETRIC_REVIEW`, else `WATCH_ONLY`.
- **Slate direction-conflict guard** (L2589–2610): >50% rows MITIGATED → 20% haircut on confidence/monetisation-fit/research scores, applied **after ranking**, labels not recomputed — a label can say ASYMMETRIC_EXECUTE above a score now <72.
- **Slate skew guard is dead** (L2628–2641): calls `logger.warning` but the module logger is `log` (L122) → NameError swallowed by `except Exception: pass` — the 75%-one-side warning can never fire.
- Manifest inclusion (L2612–2627): not hard-blocked, not options-contract-blocked (`_options_blocked_for_morning_candidate` L469–479), and (trigger_go or status in carry-forward). Shadow book L1512–1583/L2742–2789; regime-watch lane L2791–2810. Cap `head(max_candidates)` (L2851–2855) then **B2 removes EIL BLOCKED rows after the cap** (L2856–2873) — blocked rows consume cap slots; the slate can be under-filled.
- Physics/truth enrichment L2874–2882; `ma_inputs_sync` best-effort with a hard-coded Windows path, swallowed on failure (L2929–2936).

### Silent defaults / overwrites
`_flt` NaN→default (L342–349); **`_first_flt` treats 0.0 as missing** (L404–409); `_str` treats "none"/"nan" as missing (L372–376) vs `_trigger_text` preserving literal NONE (L379–395). Duplicate dict keys silently overwrite: `remaining_runway_state` (L2228/2236), `quote_as_of` (L2231–2233 vs **L2248**, dropping the quote-timestamp fallback), `option_chain_dataset_id` (L2234/2251), `signal_type`/`momentum_tier` (L2445–2446 vs L2528–2529). **`wall_price` fallback ignores direction**: `wbs_wall_price or put_wall or call_wall` (L2113) — a CALL gets the put wall. Exit plan (L1414–1465): mode from WBS grade (PROBABLE→RIDE_THROUGH_WALL 40/35/25; UNLIKELY→EXIT_BEFORE_WALL 50/35/15; default SCALE_AT_WALL 60/25/15); missing target synthesised from expected move; **missing wall set = target** so t1==t2; t3 = extreme ×1.03/×0.97. `dte` defaults 30 (L2109). Bare excepts: horizon load (L1948–1949), vanguard load (L2054–2055), skew guard (L2640), regime-watch write (L2809), MA sync (L2935).

## 2. `trigger_layer.py` (1,109 lines — Trigger Layer v2.2, Phase 8.6)

Two modes: `patch_run_packages` (L920–1051) patches package JSONs + sidecar `trigger_layer_summary_{run_id}.csv`; `enrich_csv` (L780–907) writes flat `trigger_*` columns into the EIL CSV. In CSV mode a pre-existing sidecar's classification is **reused in preference to recomputation** (L689–731, L734–777) — stale sidecars propagate; only EV is refreshed from the row.

**Weights** (L63–70): VOL_COMPRESSION 2.0, RANGE_BREAK_EARLY 1.5, RANGE_BREAK 2.0, VWAP_RECLAIM 1.5, VWAP_LOSS 1.5, TRAP 2.5.
- **T1 VOL_COMPRESSION** (L350–384): crabel_state ∈ {COILING, CRABEL_READY, NR7} → fires on `crabel_compression<0.45` **or** `atr_percentile_rank<30`; state present-but-other → ratio path; state absent → requires **both** (Fix 11).
- **T2 VWAP_RECLAIM/LOSS** (L387–432): CALL requires vwap_bias=ABOVE + control_state=SHIFTING + controller BUYERS + volume≥1.1 + direction ∈ {CALL, NONE}. PUT requires vwap_bias=BELOW + control_state ∈ {**SHIFTING, SELLERS**} + controller SELLERS + volume + direction ∈ {PUT, NONE}. **The PUT gate is looser** (static SELLERS qualifies). Direction NONE rows can fire either side.
- **T3 RANGE_BREAK(_EARLY)** (L435–479): EARLY = phase ∈ {C,D} + bucket ∈ {MARKUP, ACCUMULATION} + ADX 18–28. CONFIRMED = bucket ∈ {MARKUP, **DISTRIBUTION**} + (EMA ALIGNED or volume≥1.2) + ADX ≥25. Same code regardless of side — a bearish DISTRIBUTION break and a MARKUP break are indistinguishable downstream.
- **T4 TRAP** (L482–542): requires pcr_signal present, not NEUTRAL/NONE (L505–507); bull trap = BUY intent/CALL + PCR BEARISH + failing structure + controller SELLERS; bear trap mirror. **Fires *against* the row's own setup — inherently contrarian.**

Score = Σ weights (L549–551); quality ≥3.5 STRONG / ≥1.5 SINGLE / NONE (L554–565). `trigger_primary` = max weight (L568–575). **GO-eligible** (L578–587): primary ∈ {VOL_COMPRESSION, RANGE_BREAK_EARLY, RANGE_BREAK, TRAP} — a single SINGLE-quality trigger is GO-eligible; VWAP codes alone are not. `go_eligible = eligible and not stale` (L637). **Staleness** (L238–289): explicit states, age >2 sessions, or asof-vs-anchor distance; **no evidence → UNKNOWN, stale=False** (L284) — UNKNOWN freshness does not block GO. **EV** (L292–343): despite the docstring formula, path 1 returns `ev2_ev_conf_adj|fd_ev_used|ev_conf_adj|eil_ev_net|ev_final` verbatim (L315–320); fallbacks wr×em; else 0. `_direction` (L157–191) **re-derives direction locally** (options_direction→direction→precor_intent→dominant_trend→vwap_bias; STRANGLE→NONE). Bare excepts L730–731, L1015–1016, L1049–1050.

## 3. `wall_break_scorer.py` (589 lines — Layer 4b v1.0)

**Only rows with `sb_final_verdict ∈ {EXECUTE, EXECUTE_WITH_RISK}` are scored** (L116, L394) — everything else has no WBS row. OI lookup ticker-keyed, last row wins (L404–408); merge `{**sb_row, **oi_row}` (OI overrides SB, L422). Output `wall_break_scores_{run_id}.csv` + summary (completeness metric L470–485).

**Five factors × 20** (`score_wall_break`, L142–307), silent defaults `gamma_flip_conf=0.5`, `gap=0.0`, `iv_vs_hv=1.0`, vanna 0:
- F1 vanna fuel: PUT uses only negative vanna, CALL only positive, STRANGLE magnitude (L183/191/198); full score at |vanna|=0.05.
- F2 wall weakness `(1−gfc)×20` — **default gfc 0.5 → 10 points with no data** (L203–204).
- F3 flip clearance `min(20, gap/50×20)` (L214).
- F4 vol loading: iv/hv<1 → `(1−r)×40` cap 20; else `(2−r)×10` — **default 1.0 → 10 points with no data** (L224–228).
- F5 momentum: IMMINENT 20 / APPROACHING 15 / STALLING 5 / DISTANT 5 / MOVING_AWAY 2 / unknown 5 (L99–105, L236); PCR bonus +5 (PUT pcr_vol>0.8, CALL <0.4, L107–108, L239–244) suppressed when pcr_vol_status flags OI_ONLY/NO_INTRADAY/UNAVAILABLE (L165–172).

**A fully-defaulted row scores 25 → UNLIKELY** — missing data manufactures pessimism, not "no grade". Grades: IMMINENT ≥75 / PROBABLE ≥55 / POSSIBLE ≥35 / UNLIKELY (L71–74). Wall selection direction-strict (PUT→put_wall, CALL→call_wall, else 0.0, L260–274). Phase B trigger 2% inside wall; C 0.5% through; rejection stop 0.5% back (L111–113). `pin_risk_score=(1−min(dist/10,1))×gfc×100` (L299–306). Mixed types: zero dist written `''` for `wbs_wall_dist_pct` but `0.0` for `runway_to_wall_pct` (L286/295).

## 4. `catalyst_truth_engine.py` (830 lines — catalyst_truth v1.2)

`enrich_run` (L743–815) gathers per-ticker rows from the calendar packet **plus nine pipeline artifacts including its own downstream outputs** — discovery, vanguard×2, OI, superbrain, eil_enriched, execution, `morning_candidates`, `final_opportunity_book` (L369–385) — scores each ticker, writes `catalysts/catalyst_truth_{run_id}.csv`, then **patches the same nine CSVs in place** (drop catalyst columns, left-merge by ticker, L707–740). If it runs after Phase 10, the manifest's catalyst columns are replaced with values the status logic never saw; a re-run feeds its own outputs back as sources.

Scoring `_score` (L402–704): type canonicalised L210–235 (**`wyckoff_phase_bucket` is an accepted type source, L423** — structure rows read as STRUCTURAL); detection L554 (dated ∥ packet ∥ inferred type ∥ keyword ∥ proximity ∈ {NEAR, IMMINENT, INSIDE_WINDOW, HIGH, MID}); `catalyst_inside_dte` 0≤days≤max(1,dte) (L574–578); cheap convexity (L265–272): iv_rank ≤35 ∧ (|delta|==0 **or** 0.03–0.35) — **missing delta (0.0) passes, missing IV (999) fails**; liquidity OI≥500 ∧ vol≥10 ∧ spread≤20% (L275–294). **Independent direction only** (L145–172): bias counted only from {catalyst_calendar, manual_upload, news_terminal, ma_cockpit} or explicit flag. Truth score (L614–637): detected +20; dated +20; inside DTE +15; binary×15 (EARNINGS/FDA/M&A/MACRO 0.75, COMMODITY/SECTOR 0.55, STRUCTURAL 0.25); evidence×10; confirmed +8; cheap +8; liquidity +8; ALIGNED +4 / CONFLICT −10; manual-no-date −5; weak −12. Event convexity (L639–646): binary×25 + cheap 20 + liquidity 20 + inside-DTE 20 + aligned 10 + evidence×5. Classes (L648–662): ≥75 ∧ inside ∧ liquid ∧ ¬weak → `DATED_CATALYST_CONFIRMED`/CONFIRMED; convexity ≥65 ∧ detected → `EVENT_CONVEXITY_WATCH` (`INFERRED_GOOD` when undated); detected → `STRUCTURE_WITH_CATALYST_CONTEXT`/INFERRED; manual-only → `MANUAL_NEEDS_CATALYST_PACKET`; else `STRUCTURE_ONLY_NO_CATALYST`. Broad excepts L302–303, L362–363, L179–190.

## 5. `avshunter_trap_engine.py` (422 lines — TLE, Phase 5.5)

Package enrichment after Phase 5; `tle_verdict` read by OI's CSM. `_compute_tle` never raises — exceptions yield `tle_verdict=NO_TRADE` (L64–93). Bullish signals max 12: SPRING/Phase-C-accum/SC-LPS-SOS +3; VWAP_RECLAIM trigger +2; VOL_COMPRESSION/COILING +2; COUNTER_CALL+NORMAL +2; control ∈ {BUYERS, **SHIFTING**} +2; "call wall clear" = ¬gamma_risk ∧ trend≠BEARISH +1 — **true for an empty row**. Bearish max 11: UTAD/LPSY/DIST-C-D +3; VWAP_LOSS +2; control ∈ {SELLERS, **SHIFTING**} +2; rejection (COUNTER_PUT/REJECTION **or UTAD/LPSY again — double count**) +2; weak thrust +1; negative GEX +1. **SHIFTING adds +2 to both sides** (L190, L229). Trap direction = larger side; tie>0 → CONFLICTED (L258–265). Verdicts (L276–283): ≥11 CHASE (bear side literally unreachable: needs its max), ≥7 CONFIRMATION_ENTRY, ≥4 EARLY_PROBE, else NO_TRADE. Kill switch = structural stop.

## 6. `scripts/exit_rules_engine.py` (109 lines)

Phase 10 additive fields. Target from **`structural_target` only** (L36) — never `target_price`, so targets can vanish/diverge from the manifest. Stop from `invalidation_spot`/`ev3_invalidation_spot` (L37). Theta exit = `mid×0.5/|theta|` days clamped [1,dte] (L49–52); `exit_max_dte = dte×0.5` (L54). RR validity on the underlying with **1.5 threshold** (L56–66) — stricter than the manifest floor (0.0) and Tier B (1.0), so valid Tier B/C rows get `RR_BELOW_1.5_REVIEW` (L77–78). Non-directional rows → `NOT_EVALUATED_NON_DIRECTIONAL` (L86–89). **Bare `except Exception`** collapses errors to all-None + "ERROR" (L92–100).

## 7. `mcmillan_advisory_layer.py` (439 lines)

Read-only advisory; 11 fields (L21–33). IV/GEX entry quality (L171–223): IVP normalised (≤1 → ×100), buckets <30 CHEAP / >70 EXPENSIVE; GEX ≤0.40 AMPLIFYING / ≥0.60 PINNING / `gamma_risk_flag`→AMPLIFYING; matrix CHEAP+AMPLIFYING 4 `MAXIMUM_TAILWIND` … EXPENSIVE+PINNING 1; unknowns 2 `INCOMPLETE_REVIEW`. Move/theta (L240–294): `(spot×EM×|delta| (default 0.5))/(|theta|×horizon)`; ≥10 WIDE / ≥5 MODERATE / ≥2 TIGHT / CRITICAL; missing → UNAVAILABLE. Crowd arrival (L339–387): IV_ACCEL (vs prior-run state file `avshunter_run_state.json`) + RVOL_SPIKE (≥1.5) + GAMMA_FLIP_PROXIMITY (|gap|≤5%): 3 → `LATE_CROWD_RISK`, 2 `CROWD_ARRIVING`, 1 `EARLY_CROWD_HINT`, 0 `EARLY_NO_CROWD`.

## 8. `eil_eod_resolver.py` (125 lines)

**Compatibility stub.** `get_eil_data_mode` (L34–46): LIVE iff UTC ∈ [13:30, 20:15] — fixed window, no DST/holidays (drifts an hour half the year). `resolve_eod_context`/batch (L49–85) return rows **unchanged** — consumers expecting cross-sectional EOD enrichment get nothing. `check_eod_variance` (L97–125): per-field std; <0.01 → "frozen"; non-blocking.

## Observations relevant to contradicting signals (evidence-only)

1. **Catalyst watch demotes EIL EXECUTE** (L1124–1125 fires before L1127) while the same catalyst fields count positively in tiering (L1830–1843) — Tier A + WATCH_ONLY on one row.
2. **Direction conflict → "TRIGGER_READY" with no trigger** (L1103–1105), lane TRIGGER_REQUIRED beside `trigger_quality=NONE`/`trigger_go_eligible=False`; also skips the contract-repair check, so wiped-contract conflicted rows show TRIGGER_READY with `contract_repair_required_at_open=TRUE` (L2283).
3. **TRAP is contrarian yet GO-eligible and checked before EIL** (trigger L69/L77/L521–539; eod L1116–1117): evidence the CALL side is the trapped side promotes the CALL to trigger-ready.
4. **3+ independent direction authorities per row** (GDR, trigger-layer re-derivation, TLE bull/bear, catalyst bias, Vanguard edge) reconciled only into flags, never a side; SHIFTING inflates both TLE sides simultaneously.
5. **NaN merge bug** (L2074/2080/2086) starves WBS/discovery/vanguard fills; vanguard's 0.0 clause overwrites genuine zeros — displayed values differ from the values that scored the row.
6. **Horizon used for status ≠ horizon stamped** (L1078 vs L2128–2137).
7. **Dead slate-skew guard** (NameError swallowed, L2639–2641).
8. **Post-ranking haircut without label refresh** (L2589–2610).
9. **WBS**: only EXECUTE-ish rows scored; missing data → 25/UNLIKELY not unknown; manifest wall fallback side-blind (L2113); docs claim tier/SCS weights the code no longer implements (L32–46 vs L1746–1748).
10. **Vocabulary mismatch**: rescue set excludes CONTINUATION which SCS rewards most (L655 vs L1781).
11. **RR thresholds disagree** (0.0 floor / 1.0 Tier B / 1.5 Tier A / 1.5 exit validity) and exit rules read `structural_target` while the manifest publishes `target_price`.
12. **Gamma proximity is a plus (WBS F5) and a risk (McMillan crowd) simultaneously** on the same row.
13. **Catalyst engine patches artifacts after the fact** — incl. morning_candidates — and reads its own outputs as sources on re-runs (L369–385, L737).
14. **Stale trigger sidecars propagate** (enrich_csv prefers sidecar, L818/L846); UNKNOWN freshness never blocks GO (L284).
15. **Silent dict-key overwrites** (quote_as_of L2248; runway state; dataset id; signal_type/momentum_tier).
16. **Zero-as-missing** (`_first_flt` L404–409 and `or`-chains at L1610/L1724/L1801/L2113/L2265).
17. **CALL/PUT asymmetries**: T2 PUT accepts static SELLERS (trigger L417–429); WBS PCR bands PUT>0.8 vs CALL<0.4; PUT-only macro headwind (eod L1044–1064); WBS F1 discards wrong-signed vanna per side.
18. **eil_eod_resolver is a no-op** with a DST-drifting market-hours window.
19. **Cap-then-filter under-fills the slate** (L2851–2873): blocked rows consume cap slots.


---

# SECTION D — SuperBrain, macro stack, GARCH, EV2, monetisation-policy pair

# AVSHUNTER Pipeline Logic Audit — 9 Files

All paths relative to `/mnt/user-data/uploads/AVSHUNTER-Intelligence/`. Line numbers are exact for the files as uploaded.

---

## 1. `scripts/avshunter_superbrain_layer.py` (2771 lines, v2.3.0) — Phase 8 SuperBrain

### Role / invocation status: DEPRECATED — all of its logic is DEAD on the orchestrator path
- Header banner (lines 1–25): "STATUS: DEPRECATED / BYPASSED (Phase 8d passthrough only)", retired 2026-04-28.
- **Verified in `intelligent_orchestrator.py`:** `run_superbrain_layer()` (orchestrator:2695–2702) is now a one-line delegate to `run_superbrain_passthrough(run_id)` (orchestrator:2832–2949). The passthrough copies `options_intelligence_{run_id}.csv` (or the phantom variant) to `superbrain/superbrain_enriched_{run_id}.csv`, maps `options_verdict → sb_final_verdict` (orchestrator:2875–2882), and inserts NaN placeholders for 6 contract columns (`contract_spread_pct, contract_premium, options_bid, options_ask, contract_iv, contract_delta`, orchestrator:2894–2901). The evening workflow calls `run_superbrain_passthrough(canonical_run_id)` directly (orchestrator:4497).
- **Zero import sites**: grep across the repo finds no `import avshunter_superbrain_layer` anywhere; the only references are the orchestrator config path constant (orchestrator:466) and a log message suggesting manual CLI re-run (orchestrator:3062). `resume_after_vanguard.py:137` calls the orchestrator's `run_superbrain_layer` (i.e. the passthrough), and `avshunter_ticker_probe.py:636` defines its *own unrelated* function of the same name.
- The file is therefore reachable only via manual CLI (`__main__`, lines 2740–2771). Everything below describes logic that *looks* live but does not execute in the nightly run — including the DATA_WEAK escalation gate, EV gates, convexity engine, ladder, and time-stop.

### Inputs
- CLI: `options_csv` (options_intelligence CSV), `dashboard_csv` (master dashboard keyed by `underlying`/`ticker`, lines 2317–2324), optional `run_id`, `output_dir`, `--premarket`, `--eod`, `--topn` (2744–2757).
- Per-signal fields read (via `_f`/`_s` safe extractors, 451–465): `underlying|ticker`, `options_direction|direction|dir`, `phase`, `underlying_price|spot|entry_price` (derived from `breakeven_price`+`breakeven_pct` if absent, 518–537), `iv_percentile|ivp_local_med`, `composite`, `regime`, `breakeven_pct|be_pct|be`, `phase_a_low`, `hold_label|hold`, `top_call_wall|gex_wall_call|call_wall`, `top_put_wall|gex_wall_put|put_wall`, `pcr_vol|pcr_oi`, `iv_regime`, `ivp_252d`, `iv_vs_hv`, `dw_signal`, `atr_percentile`, `iv_rank_252d|iv_rank`, `notional_buy/sell`, `structural_target`, `contract_vanna|vanna`, `volume_ratio`, `sector_regime`, `sector_5d_return`, `rr_underlying|rr`, `rr_options`, `ev_final|ev_adj|ev_adjusted`, `ev_status|ev2_ev_status`, `options_score|ois_score|contract_ois_score|score_composite`, `data_mode`, `data_source`, `mark_synthetic|contract_mark_synthetic`, `garch__l3_iv_tailwind_score|l3_iv_tailwind_score`, `horizon_bucket`, `horizon_action`, `horizon_size_multiplier`, `dte|contract_expiry|expiry|expiration|exp_date`, `asof_date|signal_date|date`, win rates 5/10/20d, `win_probability|discovery_win_probability|vanguard_win_probability`.

### Outputs
- `superbrain_enriched_<run_id>.csv` (all rows, full sb_ field set, 2159–2298), `superbrain_execute_<run_id>.csv` (EXECUTE + EXECUTE_WITH_RISK sorted by verdict > conv score > rr, 2533–2543), `superbrain_injections_<run_id>.csv` (2545–2550), `superbrain_top{N}_<run_id>.csv` (2556–2571), `superbrain_summary_<run_id>.json/.txt` (2595–2713).

### Core logic, step by step

**Constants (368–444)**: V1 move threshold 40% from Phase A low (369); runway multiplier 2.0× breakeven (370); high-IV threshold IVP > 0.70 with min runway 3.0% (371–372); TRANSITIONAL composite floor 65.0 (373); PCR CALL max 1.80 / PUT min 0.55 (374–375, QA-03 symmetric reciprocal). Convexity: ATR pct < 30 compressed (378), IV rank < 0.40 compression proxy (379), net-notional < 0.25 = absorption (380), IVP < 0.35 = cheap vol (381), gamma proximity ≤ 2.0% (382), runway > 2.0× breakeven (383). Campaign thresholds: INJECTION 5 (core), CORE 3, STAGED 1 (386–388). Ladder stages 1–5 with DTE windows 270–540/45–90/21–45/7–21/0–7 and size 20/30/30/15/5% (392–403); phase→stage map A,B→1, C→2, D→3, E→4 (412–416). Verdict order EXECUTE=5 > EXECUTE_WITH_RISK=4 > ARMED=3 > WATCHLIST=2 > STAND_DOWN=DATA_FAILURE=1 (420–428). Legacy map: EXECUTE_WITH_RISK→ARMED, DATA_FAILURE→STAND_DOWN (433–440). Time-stop 60% of DTE, checkpoint 30% (443–444).

**`_compute_execution_mode` (182–207)**: STAND_DOWN/DATA_FAILURE → BLOCKED; conviction ≥ 4 → PROBE if risk ≥ HIGH, REDUCED_EXECUTE if ≥ MEDIUM, else FULL_EXECUTE; **conviction < 4 → WAIT regardless of verdict** (207).

**EV engine import (246–257)**: sys.path fix inserts repo root so `from ev_engine_v2 import` resolves to the root copy; on any exception `_EV_ENGINE_V2_AVAILABLE=False` silently (254–257, blanket `except Exception`).

**Behavioural vetoes `apply_behavioural_vetoes` (578–779)** — all but one are WARNINGS (per the FIX-H comments), only V2_AT_WALL sets `verdict_adj`:
- V1 late entry: move from `phase_a_low` > 40% → warning (618–626); if no phase_a_low and phase E → V1_LATE_ENTRY_PROXY warning (627–633).
- V2: CALL with `call_wall <= spot` → **`verdict_adj='STAND_DOWN'`** (639–644); wall above spot but runway < 2×breakeven → warning only (645–654). PUT mirror: `put_wall >= spot` → STAND_DOWN (656–661); `put_wall < spot` with runway < required → warning (662–670).
- V3: IVP > 0.70 and runway ≤ 3% → warning (673–686). CALL/PUT runway checks asymmetric in form: PUT requires `0 < put_wall < spot` (677).
- V4: TRANSITIONAL + 0 < composite < 65 → warning, **exempted entirely when `horizon_bucket` ∈ {1_5d, 6_10d}** (692–706); the exempt branch appends an informational V4_UNCLEAR_STATE_EXEMPT string instead.
- V5: missing hold label → informational warning (709–714).
- V6: PCR contradiction — CALL and pcr_vol > 1.80, or PUT and pcr_vol < 0.55 → warning (717–731). Note pcr_vol falls back to `pcr_oi` (614–615) so OI ratio can trigger a "live volume" contradiction message.
- V7: `iv_regime == 'EVENT_PRICED'` and IVP > 0.75 → warning (738–744); `UNCERTAIN` → warning (745–750); V7b `ivp_252d > 0.85 and iv_vs_hv > 1.20` → warning (753–759).
- V8: delta-weighted OI STRONGLY_BEARISH vs CALL / STRONGLY_BULLISH vs PUT → warning (762–777).

**Convexity `compute_convexity_score` (786–994)** — 8 conditions:
- C1 compression: `atr_percentile < 30` when present; else iv_rank normalised (`/100` if > 1.0, line 829) < 0.40 (823–833).
- C2 energy: |buy−sell|/total < 0.25 when notionals present; else 0.70 < pcr_vol < 1.30 (836–847).
- C3 cheap vol: 0 < IVP < 0.35 (850–853).
- C4 gamma proximity: `abs(wall − spot)/spot ≤ 2%` (856–872) — **absolute distance, so being AT the wall passes C4 while V2 STAND_DOWNs it**.
- C5 runway: wall-based runway > 2×breakeven; falls back to `structural_target` (876–907).
- C6 vanna: |vanna| ≥ 0.04 with sign aligned (CALL +, PUT −); **missing vanna = neutral PASS** (913–928, QA-02).
- C7 volume: phase D/E requires vol_ratio ≥ 1.5; phase C ≥ 1.2; else ≥ 1.0; missing → FAIL (932–949).
- C8 sector alignment: CALL fails only on `STRONG_DOWNTREND`, PUT only on `STRONG_UPTREND`; missing → PASS (953–968). **Bug: `sector_regime = _f(signal, 'sector_regime', '')` (line 953) uses the *float* extractor — a string like "STRONG_DOWNTREND" raises ValueError inside `_f` and returns default `''`, so C8 can never fail and always neutral-passes** (also `_f(signal,'sector_etf','')` at 958/962 in the reason strings).
- Classification (971–992): all 5 core pass → CONVEXITY_INJECTION regardless of supplementary (983–984); total ≥ 6 → INJECTION (985–986); total ≥ 3 → CORE_CAMPAIGN (987); ≥ 1 → STAGED (989); else AVOID.

**Ladder `build_instrument_ladder` (1031–1179)**: current stage from phase (default 3 if unknown, 1049); stage cap by campaign — INJECTION 5, CORE 4, STAGED 2, AVOID 0 (1058–1064); earlier stages MISSED with premium-multiple foregone-value estimate (multiples 6.0/3.5/2.0/1.4/1.0, 407–409, computed 1086–1102); current stage ENTER_NOW if ≤ cap; future stages SET_ALERT with ATR alert price `spot ± atr×(2.0 + 1.5·Δstage)` or `3% + 2%·Δstage` fallback (1124–1137); horizon DTE nudge BURST/GRIND/STEADY (1001–1028).

**Time-stop `compute_time_stop` (1239–1321)**: DTE from field or expiry–asof (1198–1237, returns None if unknown — FIX-02); anchored to `asof_date` not wall clock (1261–1270); stop at 60% DTE, checkpoint at 30% (1292–1293); rule requires 40% progress to target by stop date (1297–1303).

**Verdict assembly `assemble_execution_plan` (1328–1740)** — gate chain in order:
1. DATA_WEAK (1370–1388): `ev_status == 'DATA_WEAK'` → append WARNING (weight 1.0), not a block.
2. GATE_NEGATIVE_EV (1390–1398): `ev_final < −0.10` → return EXECUTE_WITH_RISK, HIGH, size 0.
3. GATE_LOW_RR (1400–1411): `0 < rr_underlying < 0.5` → EXECUTE_WITH_RISK, HIGH, size 0. (DEP-02: uses `rr_underlying`, not `rr_options`, 1363.)
4. GATE_RR_FLOOR (1413–1443): `0 < rr < 1.5` — live mode: EXECUTE_WITH_RISK hard cap; EOD (`data_mode ∈ {EOD, AUTO}`, `data_source ∈ {EOD_PACKAGE, EOD, BACKFILL, VANGUARD}`, or synthetic mark, 1422–1427): warn `WARN_LOW_RR_EOD` and continue.
5. OIS gate (1445–1501): OIS from 4 column aliases; missing OIS in live → EXECUTE_WITH_RISK/MEDIUM; missing in EOD → warning `GATE_MISSING_OIS_EOD`. OIS < 55: live → hard cap HIGH; EOD → warning. **EOD detection `_sig_is_eod` (1464–1471) includes blank data_mode, blank data_source and `bool(_spot(signal))` — any signal with a price counts as EOD**, so the live OIS/RR gates essentially never fire in batch runs.
6. Synthetic mark (1503–1517): warning only (`QUOTE_WARNING`).
7. GATE_EXPENSIVE_VOL (1519–1536): `garch__l3_iv_tailwind_score` (or `l3_iv_tailwind_score`) > +0.15 → EXECUTE_WITH_RISK, HIGH, size 0.
8. REGIME_SIZE_DOWN (1538–1557): composite < 35 in TRANSITIONAL → warning only.
9. `veto_adj == 'STAND_DOWN'` (V2_AT_WALL) → STAND_DOWN/EXTREME (1560–1561).
10. AVOID campaign → **DATA_FAILURE**/EXTREME "BLOCK_NO_EDGE" (1564–1565) — a 0-conviction structural read is labelled a data failure.
11. A1 gate (1573–1576): STAGED + base EXECUTE → demote to ARMED in live mode; in EOD only if conv_score < 2.
12. Continuous sizing (1588–1595): INJECTION `min(100, 80+5·(cs−6))`; CORE `min(75, 55+7·(cs−4))`; STAGED `min(45, 35+5·(cs−2))`; AVOID 0.
13. Risk label weighted warnings (1614–1707): weights — V7_EVENT_IV 2.0, EVENT_PRICED 2.0, V7b 2.0, V8 2.0, V7_UNCERTAIN 1.5, V6 1.5; V1/V1_PROXY/V2_NO_RUNWAY/V2_AT_WALL/V3 1.0; V4/V5/QUOTE_WARNING/REGIME_SIZE_DOWN 0.3, V3_HIGH_IV 0.5, GATE_MISSING_OIS_EOD 0.2, DATA_WEAK 1.0, WARN_LOW_RR_EOD 0.3, WARN_LOW_OIS_EOD 0.3; unknown warnings default 0.5 (1646). Regime discount 0.5 applies to non-flow warnings only: PUT in RISK_OFF/TRANSITIONAL, CALL in RISK_ON (1656–1661); V6/V8 exempt (1671). Thresholds (FIX-PARALYSIS-04): 0 → LOW; ≤ 2.5 → MEDIUM; ≤ 4.5 without critical → HIGH; critical+standard or > 4.5 → EXTREME (1694–1707).
14. Final verdict (1710–1726): base STAND_DOWN → STAND_DOWN/EXTREME; LOW/MEDIUM risk and rr ≥ 0 → EXECUTE (synthetic mark included, 1717–1721); LOW/MEDIUM with negative rr → EXECUTE_WITH_RISK + HIGH; otherwise EXECUTE_WITH_RISK.

**Unified EV `_compute_unified_ev` (1820–1955)**: merges dashboard+signal; **discovery win-rate bridge** — if win_rate_5/10/20d all 0.0, seed all three from `win_probability` (÷100 if > 1, clamped 0.30–0.80) and stamp `win_rate_source='DISCOVERY_BRIDGE'` (1857–1876). Calls EVEngineV2; on any exception silently falls through (`except Exception: pass`, 1908–1909) to a v1 fallback chain: `ev_option = delta·(ev20d − costs) − theta − iv_pen(0.02 if ivp>0.80)`; `ev_path = ev_option·win_rate`; `ev_final = ev_path − costs`; regime multiplier 1.08/1.00/0.88 kept as sizing reference only (1914–1955).

**`process_signal` (1959–2298)**:
- Data-integrity gate (1970–2035): DATA_FAILURE only when `data_failure` flag set AND no price AND no EOD source.
- **Horizon gate (2036–2114)**: if `horizon_action == "MONITOR_ONLY"` **and `horizon_bucket != "11_20d"`** (2051) → verdict MONITOR_ONLY with hard-coded reason text "bullish_prob=54.1% NEUTRAL" (2059) — the condition is inverted relative to its own comment ("11-20D → MONITOR_ONLY override", 2043) and the probability is a frozen literal. `horizon_bucket == "blocked"` → STAND_DOWN (2082–2109).
- Output row (2159–2298) includes: `rr` = rr_underlying-first (2171), all EV fields, gates `ev_gate` (ev_final ≥ −0.10), `rr_gate` (≥ 0.5), `composite_gate` (≥ 35) (2200–2203), `qomega_gate` GO/ARMED_HALF/WAIT/BLOCKED mapping (2225–2231), `sb_execution_mode` (2274), and a `horizon_size_multiplier` fallback of **1.0 / 0.70 / 0.35 / 1.0** for 1_5d / 6_10d / 11_20d / absent (2281–2285) used only when the router's multiplier is missing.

**Runner `run_superbrain` (2347–2733)**: `eod_mode` stamps `data_mode='EOD'`/`data_source='EOD_PACKAGE'` into blank rows (2466–2470); sector-alignment module loaded from env `AVSHUNTER_SECTOR_BIAS_MAP` (2417–2445), per-row failures swallowed with `except: pass` (2483–2484).

### Silent defaults / bare excepts (this file)
- `_f` returns 0.0 for anything unparseable (451–459) — walls, PCR, IVP, composite all silently 0 → most vetoes silently don't fire on missing data.
- `_ivp` fallback structure is a no-op `pass` (540–549).
- EV import failure silent (254–257); EVEngineV2 evaluate failure silent (1908–1909); sector alignment per-row failure silent (2483–2484); stdout reconfigure `except Exception: pass` (219–223).
- `_calc_rr` catch-all returns 0.0 (472–494).

---

## 2. `macro_horizon_router.py` (825 lines, v1.2 "macro_advisory") — Phase 1B

### Role / invocation
Loaded by the orchestrator via `importlib` at Phase 1B (orchestrator:1329–1340) and called as `route_signals_by_horizon(macro_path, candidate_signals)` (orchestrator:1501). Design statement (24–27): *"macro remains standalone advisory context and cannot block a CALL/PUT or change its capital size."*

### Inputs
- `macro_path`: macro JSON. Required keys used: `horizon_routing.{1_5d,6_10d,11_20d}` each with `direction|bias`, `bullish_prob_pct`, `go_no_go`, `allowed`, `blocked`, `size_multiplier`, `confirm_required|confirmation_required`, `confidence`; else legacy `extras.forward_bias`; plus `extras.volatility.complacency_threshold|put_permission_vix_level`, `extras.sectors`, `macro_momentum_score`, `risk_on_off_switch`, `regime_state`.
- `candidate_signals`: list of dicts with `ticker`, `instrument`, `dte`, `expected_holding_days|hold_days|horizon_days`, `ltr_true`, `phase_d_confirmed`, `iv_regime`, `vix_current` (defaults 18.0, line 436).

### Outputs
`dict` of buckets `1_5d / 6_10d / 11_20d / blocked` of `RoutedSignal(ticker, instrument, signal_id, horizon, action, size_multiplier, confirm_required, macro_permitted, horizon_source, block_reason, router_version)` (152–164). `routed_to_df` (517–540) flattens with `horizon_bucket` set to `"blocked"` for non-permitted rows.

### Missing-macro behaviour
- File missing → **raises `FileNotFoundError("MACRO_FILE_MISSING…")`** (326–329); invalid JSON → raises `ValueError("MACRO_JSON_INVALID…")` (330–333). The orchestrator wraps Phase 1B in a try/except that logs "pipeline continues in legacy mode" and returns `{"success": False, legacy_mode: True}` (orchestrator:1636–1642) — **no horizon columns are stamped at all in that case**.
- `horizon_routing` key absent → warning only, legacy fallback from `extras.forward_bias` (335–339, 227–264).

### Horizon-bias extraction — the exact thresholds
**Structured path (`horizon_routing` present, 199–225)** per bucket:
- `direction` default "NEUTRAL"; `bullish_prob_pct` default **50.0** (214); `size_multiplier` default **0.5**, clamped to [0.0, 1.5] (218); `confirm_required` default `["LLR_TRUE"]` (219–222); `confidence` default 75 clamped [0,100] (223).
- `go_no_go` mapping `_go_to_action` (169–179): **any of "MONITOR", "NO_GO", "PROACTIVE" → `GO_SELECTIVE`** (comment: "Never emit MONITOR_ONLY — informational routing only", 173–174); "REDUCED"/"IF_"/"CONFIRMED" → GO_REDUCED; "GO"/"SELECTIVE" → GO_SELECTIVE; else the per-bucket default, which is GO_SELECTIVE for all three buckets (201–205, note the 11_20d default comment "Informational only — EIL owns execution decisions", 204).

**Legacy fallback (227–264)** per bucket, from `forward_bias.{short_1_5d|short_term, medium_6_10d|medium_term, long_11_20d|long_term}`; prob normalised ×100 when ≤ 1 (232–234):
- `prob ≥ 63` AND direction == "BULLISH" → **GO_SELECTIVE, size 0.65** (245–246)
- `prob ≥ 58` AND direction ∈ {BULLISH, MILDLY_BULLISH} → **GO_REDUCED, size 0.45** (247–248)
- else → **GO_SELECTIVE, size 0.5** ("Informational — no proactive block", 249–250)
- confirm_required fixed `["LLR_TRUE", "CHART_PHASE_D_MARKUP"]` (260).

These are the only bullish_prob thresholds in the file — and note **the extracted biases are never applied to routing** (see below).

### VIX / PUT permission
- `extract_vix_threshold` (267–274): `extras.volatility.complacency_threshold` or `put_permission_vix_level`, default **22.0**. It is computed at line 342 — **and never used afterward**.
- `get_sector_permission` (278–296): sector `signal == "AVOID"` or horizon "BLOCKED_ALL" → block; horizon 11_20d requires signal `BULLISH_LEAD_LONG`. **This function is never called from `route_signals_by_horizon`** — dead code.
- `macro_momentum = safe_float(macro.get("macro_momentum_score", 0.5))` (343) — read, never used.
- `ltr_true`, `phase_d_confirmed`, `iv_regime`, `vix_now` are parsed per-signal (430–436) — **all four are dead reads**; no gate consumes them.

### Instrument handling (352–374)
- `CALL|LONG_CALL → CALL`; `PUT|LONG_PUT → PUT` (356–359).
- `STRANGLE` → **silently skipped with `continue`** — not even added to `blocked` (361–363).
- Any other value → BLOCKED with `INVALID_INSTRUMENT:<raw>` (364–374).

### DTE handling (376–414)
- Missing/unparseable DTE → BLOCKED `INVALID_DTE:'<raw>'` (no silent default=7; 377–390).
- `dte <= 0` → BLOCKED `INVALID_DTE_ZERO_OR_NEGATIVE` (391–402).
- `dte > 365` → BLOCKED `INVALID_DTE_TOO_LONG` (403–414).

### Bucket assignment (416–446)
- Thesis horizon preferred: `expected_holding_days|hold_days|horizon_days` → `≤5 → 1_5d`, `≤10 → 6_10d`, else `11_20d` (442–443), source tag `THESIS_HORIZON`.
- DTE fallback: `≤21 → 1_5d`, `≤55 → 6_10d`, `>55 → 11_20d` (444–445), source tag `DTE_FALLBACK_LOW_CONFIDENCE`.
- `bias is None` for the bucket → BLOCKED "No macro bias data for this horizon" (460–462).

### The actual routing decision (464–492) — this is the critical part
- RISK_OFF/CRISIS check (467–474): **logs "macro headwind retained as advisory context only" and does nothing**. The comment block below it (476–483) still says "Hard kill-switch: RISK_OFF / CRISIS regime blocks everything" — **the comment contradicts the code; nothing is blocked**.
- Every signal that survives instrument+DTE validation is appended as:
  `action=GO_SELECTIVE, size_multiplier=1.0, confirm_required=[], macro_permitted=True` (485–492).
  **The `HorizonBias` extracted at 341 — its action, size_multiplier, allowed/blocked lists, confirm_required, bullish_prob — is entirely ignored.** The only use of `bias` is the None check at 460.
- Consequence: `MONITOR_ONLY` and `GO_REDUCED` can never appear in output; `horizon_size_multiplier` is always 1.0 or 0.0.

### Self-test contradicts the shipped logic (651–824)
The `__main__` QA suite still asserts the *old* gating regime: PUT blocked by "bearish_prob 35% < 42%" (772, 776, 782), PUT blocked on 11_20d `MONITOR_ONLY` (780), LLR-unconfirmed CALL blocked (770), COMPLACENT iv_regime block (761). None of these gates exist in `route_signals_by_horizon` any more, so this file's own QA suite fails against its own routing loop — clear evidence the PUT/LLR/VIX gates were stripped out while tests, docstrings (306–322 QA-FIX-6 "PUT blocked when macro horizon is MONITOR_ONLY") and comments were left behind.

### Downstream stamping (orchestrator side, for context)
- Orchestrator patches horizon fields into superbrain_enriched **by ticker, not signal_id** (orchestrator:1546–1580; the collision is admitted at 1519–1521) — a ticker with both CALL and PUT rows gets one bucket for both. Unmatched tickers get `horizon_bucket="unrouted"` and **`horizon_size_multiplier` default 0.0** (orchestrator:1571–1573).

---

## 3. `scripts/macro_quant_packet.py` (898 lines) — Phase 3 macro quant baton

### Role / invocation
Builds a flat "macro_quant_packet" from the raw GPT macro JSON. Called by `normalise_macro_contract.py:266` (`build_macro_quant_packet`) and consumed via `load_macro_quant_packet` / `packet_from_package` / `macro_quant_columns_for_row` by downstream row-stampers. Advisory context; no gating of its own.

### Inputs / outputs
Input: the macro JSON mapping (deep-searched with `find_field`, 124–131, which walks the whole nested tree for the first non-missing occurrence of a key — order of nesting can silently change which value wins). Output: a dict of the 57 `MACRO_QUANT_CSV_FIELDS` (24–80).

### Core logic and thresholds
- Freshness (19–20, 193–202): age ≤ **20h** FRESH; ≤ **72h** STALE; else EXPIRED; no timestamp → MISSING.
- `macro_availability` starts with "UNAVAILABLE" → returns missing packet overridden with `macro_regime_label="TRANSITIONAL"`, `risk_on_off_score=0.0`, caution `MACRO_UNAVAILABLE_ADVISORY_ONLY` (533–549).
- Regime label normalisation `_regime_label` (214–230): TRENDING_BULL/RECOVERY/SELECTIVE_RISK_ON/NEUTRAL_TO_RISK_ON → RISK_ON; TRENDING_BEAR/RISK_OFF_TILT/NEUTRAL_TO_RISK_OFF/NEUTRAL_TO_DEFENSIVE → RISK_OFF; CHOPPY_NEUTRAL/NEUTRAL/MIXED → CHOPPY; CRISIS → CRISIS; substring rules; else UNKNOWN.
- `_risk_score` (233–248), token additive on the concatenation of regime+risk_switch+macro_filter: +55 RISK_ON; +10 SELECTIVE; −25 NO_GO; −65 RISK_OFF; −100 CRISIS; **TRANSITION or CHOPPY caps score at min(score, 25)**; clamped ±100. Note "RISK_OFF" contains "RISK_ON"? No — but "RISK_ON" as substring: the string "RISK_OFF" does NOT contain "RISK_ON"; however a combined text containing both switch and regime tokens sums (+55 −65 = −10 for mixed messages).
- Liquidity pulse (251–264): label keywords first, else score ≥ 0.6 EXPANDING / ≤ 0.4 CONTRACTING; `liquidity_risk_flag = (pulse == CONTRACTING)` (578).
- VIX structure (267–279): contango > +0.05 CONTANGO / < −0.05 BACKWARDATION; vol mode (282–296): SUPPRESSED/LOW → LOW_VOL; EXPAND/ELEVATED/HIGH → VOL_EXPANSION; CONTANGO & VIX < 18 → VOL_COMPRESSION; VIX < 16 LOW_VOL / > 25 HIGH_VOL / else NORMAL_VOL.
- Dealer gamma (299–306): gex_score ≥ 0.6 POSITIVE_GAMMA / ≤ 0.4 NEGATIVE_GAMMA; `gamma_risk_flag = NEGATIVE_GAMMA` (677).
- Rates/USD/credit keyword classifiers (309–339); `credit_risk_score` = 75 TIGHTENING / 25 EASING / 50 else (592).
- Sector rotation state heuristic (342–366); `sector_tilt_score = 50 + (len(preferred) − len(avoid))·10`, clamped 0–100 (606).
- Preferred horizon `_macro_horizon` (369–400): bucket with max `bullish_prob_pct` (fallback size×100) wins; horizon_pressure FRONT/BACK_LOADED/BALANCED from size multipliers.
- Bucket clarity (403–413): equities `50 + risk_score/2`; rates_bonds 65 if rates DOWN/EASE else 45; usd_fx 65/45; credit `100 − credit_risk_score`; commodities 60 if "GOLD"/"COMMOD" appears **anywhere in the serialized JSON** (406) else 45.
- Equity drawer (429–439): ≥ 3 of {RATES_UP, USD_UP, credit TIGHTENING, risk_score < −30} → active → caution flag `EQUITY_DRAWER_ACTIVE_REQUIRES_STRONG_CONFIRMATION` (445).
- `detect_core_conflict` (476–485): if `regime_state` or `risk_on_off_switch` appears **more than once with different values anywhere in the nested JSON** → data_quality = freshness = **CONFLICTED** (633–638).
- Conflict-flag triage (488–522): "resolved" tokens (RESOLVED:, CSV PRIMARY APPLIED, IMMATERIAL, …) don't degrade quality; active flags → PARTIAL.
- `missing_macro_quant_packet` (705–769) — **defaults when macro missing**: `liquidity_risk_flag=True`, `gamma_risk_flag=True`, `equity_drawer_active=True` (pessimistic) yet **`bond_trade_go=True`** (764, optimistic), `credit_risk_score=50`, caution string `MACRO_MISSING_REVIEW_REQUIRED|MACRO_DATA_MISSING|LOW_MACRO_CONFIDENCE`.
- `merge_preserving_committed` (845–859): committed fields never overwritten; conflicts recorded in a `macro_conflicted_fields` sidecar.
- `resolve_macro_suffix_columns` (862–894): collapses `_x/_y/__vg/__opt` merge suffixes back to canonical; bare `except Exception` → `combine_first` (889–890).

---

## 4. `scripts/normalise_macro_contract.py` (330 lines) — FIX-04 macro normaliser

### Role / invocation
Pre-Phase-1 step (docstring, 30–31). Reads `macro_intelligence_latest.json`, writes 4 structured 0–1 scores + the macro_quant_packet back into the same file (in place). Without it, RegimeConsensus uses hardcoded fallbacks (net_liquidity=0.5, vix=0.8, gex=0.5, momentum=0.5 → "meaningless neutral RCS=57.5", 12–15).

### Logic
- `net_liquidity_score` (109–141): label buckets — STRONG_IMPROV/EXPANDING/ACCELERAT → 0.80; MODEST_IMPROV/IMPROVING → 0.62; STABLE/FLAT/NEUTRAL → 0.50; MODEST_DET/WEAKENING → 0.38; CONTRACTING/DETERIORATING/TIGHTENING → 0.22. Else raw `net_liquidity_delta_4w` mapped `(delta+200)/400` clipped (±$200bn range).
- `vix_regime_score` (144–158): `1 − (vix − 12)/(40 − 12)` clipped; VIX from `vix_spot|vix_5d_avg|vix_level`.
- `gex_regime_score` (161–190): `$±5bn → 0–1`; label fallback DAMPENING/POSITIVE → 0.70, AMPLIFYING/NEGATIVE → 0.30; **no data → None ("absence must not be manufactured into a neutral reading", 189)**.
- `macro_momentum_score` (193–210): **taken from `macro_conviction|conviction_score|predictability_score`** — i.e. "momentum" is literally the conviction score, ÷100 if > 1.
- Write-back rules (249–262): existing valid 0–1 value is authoritative and preserved; derived value only fills absent/invalid fields; underivable → field stays absent with warning (RCS legacy fallback for that component).
- Also stamps `macro_quant_packet` (266) and `normalised_at_utc` (265).
- `DEFAULT_MACRO_PATH` is a hardcoded Windows user path (66–68).

---

## 5. `garch_runner.py` (388 lines) — Phase 10a nightly GARCH batch

### Role / invocation
Called by orchestrator after SuperBrain passthrough (docstring 11–21: 8d SuperBrain → 8e WBS → 9 EIL → **10a GARCH** → 10b Q-OMEGA). Note the superbrain gate `GATE_EXPENSIVE_VOL` comment (superbrain:1524–1525) claims GARCH runs at "Phase 8c.5 (before SuperBrain)" — this file's own header says Phase 10a *after* SuperBrain; either way SuperBrain scoring is dead so the ordering question is moot on the current path.

### Inputs
- Ticker list: `superbrain_enriched_{run_id}.csv` (produced by the passthrough) — `ticker` column (323–324).
- IV map: `options_intelligence_{run_id}.csv` `implied_vol|contract_iv` (÷100 if > 5) (172–197). Missing/failed → `{}` with warning (180–182, 198–200).
- Regime: `regime_state|active_regime|regime` from macro JSON, default **'TRANSITIONAL'** on all failure paths (137–167, bare `except: pass` at 165–166).
- Prices: canonical history bridge first (81–86, failure logged at debug), else Polygon 252 daily bars; missing `POLYGON_API_KEY` → warn and None (88–90); one retry on 429 (102–104); any exception → debug-level swallow, None (130–132).

### Logic
- Per ticker: `compute_forward_variance(ticker, ohlcv, implied_vol=iv_map.get(t, 0.0), regime)` (281) — **missing IV silently becomes 0.0 → `iv_tailwind_score = 0.0` (neutral)** per layer3:524.
- `_audit_garch_result` (230–267): audit-only logging; validates GARCH stationarity `a ≥ 0, b ≥ 0, a+b < 1` only for method='GARCH' (250–259); never mutates values.
- Status: HAR_RV/GARCH = ok; EWMA_FALLBACK/ATR_PROXY = warn; no data = fail (283–292).
- 2 workers, 0.15s rate sleep (332–352); zero results → RuntimeError (354–356).

### Output
`runs/{run_id}/qomega/garch_forecasts_{run_id}.csv` with `l3_*` columns from `ForwardVarianceResult.to_dict()`.

---

## 6. `layer3_forward_variance.py` (551 lines) — Q-OMEGA Layer 3 forward variance

### Inputs / outputs
Input: OHLCV DataFrame (close required), `implied_vol` (annualised decimal), `regime` string. Output `ForwardVarianceResult` → dict fields `l3_forward_realised_vol`, `l3_vol_forecast_conf`, `l3_expected_move_1_5d/6_10d/11_20d`, `l3_iv_tailwind_score` (+ `_capped` ±1.50), `l3_jump_risk_flag`, `l3_method`, `l3_garch_alpha/beta`, `l3_n_bars`, `l3_model_risk_flags/-count/-capital_guard`, `l3_error` (117–151).

### Method chain (order of truth)
1. **HAR-RV primary** `_har_rv_forecast` (242–321): needs ≥ 30 returns; OLS of next-day RV on 1d/5d/22d lags over last ≤ 180 obs; forecast floored at `0.5 × mean(rv[-5:])` (286); horizon-average with decay 0.92 toward 60-day long-run mean (289–295); annualised, clipped [0.05, 2.50]. Coefficients exported as `har_b1`/`har_b5_b22` (RC-7a; NOT garch alpha/beta); `garch_alpha/beta = None` for HAR rows (484–488).
2. EGARCH fallback (343–367), then GARCH(1,1) with strict stationarity `alpha+beta < 1, alpha,beta ≥ 0, omega > 0` (369–391); both wrapped in bare `except Exception: pass` (366–367, 390–391); arch ImportError → None (335–338).
3. `n_bars ≥ 20` → EWMA λ=0.94 (394–406; < 5 returns → **hardcoded 0.25**, line 401).
4. else ATR proxy `ATR14/close/1.25` annualised (409–427; failure → **0.25**, line 427).

### Adjustments and thresholds
- Regime buffer (503–511): RISK_OFF/BEAR → **ann_vol ×1.10**; TRANSITIONAL → **×1.05**; cap 2.50. (Raising forecast RV *lowers* `iv_tailwind = IV − ann_vol`, making options look *cheaper* in RISK_OFF.)
- Expected moves (167–180, 514–517): 1-sigma % using calendar→trading conversion `days·5/7`. **`em_6_10 = move(10) − move(5)` and `em_11_20 = move(20) − move(10)` — incremental, not cumulative** (516–517); only `em_1_5` is a total move.
- IV tailwind (519–524): `implied_vol − ann_vol` if IV > 0 else 0.0. **Sign convention: positive = IV above forecast = options EXPENSIVE (headwind)**, despite the "tailwind" name (comment 520–523).
- Jump risk: 5d vol / 20d vol ≥ 1.5 (69–72, 183–191).
- Confidence (194–214): 0.40·bars + 0.35·stability + 0.25·method (HAR 100, GARCH 90, EWMA 65, ATR 35); RISK_OFF −10 (534–535).
- Model-risk flags (99–115): VOL_HARDCAP (≥ 2.50), LOW_CONF_HIGH_VOL (conf ≤ 65 and vol ≥ 1.50), THIN_HISTORY (< 100 bars), IV_TAILWIND_EXTREME (|tailwind| > 1.50).

---

## 7. `ev_engine_v2.py` (root, 423 lines, v2.2.0) — the EV engine EIL imports

### Role / invocation
Imported by `execution_intelligence_runner.py` (EIL) and (dead path) by superbrain. `scripts/` contains only `ev_engine.py` (v1), so `from ev_engine_v2 import` always resolves to this root copy.

### `ev_inputs_from_row` (73–230) — input mapping and silent defaults
- Win rates (PATCH-01, 85–91): `win_rate_{5,10,20}d` treated as **0–1 scale** (clamped [0,1] — a percent-scale 57.8 silently clamps to 1.0 = 100%); `layer2__win_rate_*` treated as 0–100 (÷100). `or`-chained so 0.0 falls through to the layer2 column.
- Expected moves (94–99): `expected_move_Nd` → `layer2__median_gain_if_up_Nd` → `median_gain_if_up_Nd` → `median_gain_if_up`.
- Horizon from DTE (102–105): dte < 15 → 5; < 25 → 10; else 20. **`dte` default 30.0** (102) → a missing DTE silently becomes horizon 20.
- `option_mid` (108): `option_mid|premium|mark|contract_premium` else **1.0**.
- Prices (110–112): `entry = signal_price` default **100.0**; `target = target_price` or `entry·(1+target_pct def 0.10)`; `stop = stop_price` or `entry·(1−stop_pct def 0.05)` — i.e. missing target/stop silently fabricates a 2:1 R:R geometry.
- V2 signal intelligence (135–187): `predictability_score` derived from momentum tier when CONTINUATION (TIER_1 72 / TIER_2 70 / TIER_3 65 / TIER_4 60; TRANSITION 58/54/52) else `predictability|composite|50`; `bmps` from momentum bucket (EXTREME 78 / HIGH 70 / MID 58 / LOW 45 / 50); calibration = `calibration_confidence|composite|50` + `fwd_momentum_conf×10`, clamped 0–100.
- Other silent defaults (196–225): flow_score 2.5; survival_prob 0.50; gamma_obstruction 0.20; path_cleanliness 0.60; delta 0.40; gamma 0.02; theta 0.01; vega 0.10; `iv_rank = iv_rank|ivp_252d|iv_percentile|0.50`; **`iv_tailwind_score` read from column `iv_tailwind_score` default 0.0** (209) — the GARCH CSV writes `l3_iv_tailwind_score` / merged as `garch__l3_iv_tailwind_score`, so unless something renames it, the EV engine's vega adjustment sees 0.0; spread_pct 0.05; drift 0.02; slippage 0.01; regime `regime_state|macro_regime|regime|'TRANSITIONAL'`; **`data_quality_score` default 100.0** (220) — absent data quality = full confidence; `breakeven_pass_live` default True (221); runway_pct default 2.0 (222); prob_breakout/rejection/drift 0.35/0.35/0.30; breakeven_pct 5.0.
- Bare excepts: `_safe` (23–27) and `b()` (77–82).

### `EVEngineV2.evaluate` (354–391) — the full formula chain
1. **Hard gates** `_hard_gates` (339–344): `breakeven_pass_live` False → BREAKEVEN_FAIL; `runway_pct ≤ 0` → ZERO_RUNWAY; `spread_pct > 0.30` → SPREAD_UNUSABLE; no contract price → NO_CONTRACT_PRICE. Blocked → `ev_final = ev_conf_adj = −1.0`, status FAIL, size 0 (367–369).
2. **Blended win prob** `_blend_win_probability` (236–243): actuarial `a` = hit rate for horizon; if all three hit rates zero → `DataQualityWarning` and **a = 0.40**; model score `ms = 0.40·predictability + 0.25·bmps + 0.20·calibration + 0.15·(flow/5)`; **p = clamp(0.55·a + 0.45·ms, 0.05, 0.95)**.
3. **Structural EV** `_struct_ev` (245–254): with expected move `em`: `rr = (target−entry)/max(entry−stop, 0.001)`; loss magnitude `lm = −em/max(rr, 0.5)`; `sev = p·em + (1−p)·lm`. Without em: `p·up − (1−p)·dn` from target/stop.
4. **Path multiplier** `_path_mult` (256–259): `clamp((clamp(survival·1.2, 0.40,1.20) + (0.80+cleanliness·0.40))/2 − gamma_obstruction·0.40, 0.40, 1.50)`; `epa = sev·pm`.
5. **Contract EV** `_contract_ev` (276–280): win leg `(|move|·delta·entry + 0.5·gamma·(move·entry)²)/premium`; lose leg `−clamp(1−delta·0.20, 0.60, 1.00)`; minus theta cost `clamp(theta·h·(1.15 if dte<21)/premium, 0, 0.80)`; plus vega adj `clamp(iv_tailwind_score/100·0.30, −0.30, +0.30)` (274) — **positive tailwind (per layer3: IV *expensive*) ADDS to contract EV**, and the ÷100 implies a 0–100 scale while layer3 emits a decimal vol difference (≤ ~1.5), making the term ≈ 0 in practice — doubly inert/wrong-signed.
6. **Contract efficiency** `ce = clamp(cev/|sev|, 0.30, 1.30)`; flag if < 0.50 (335–337).
7. **Execution multiplier** `_exec_mult` (282–291): spread > 0.20 → −0.30; > 0.10 → −0.15; > 0.05 → −0.07; −drift·2 (cap 0.15); iv_distortion > 0.10 → −0.10 / > 0.05 → −0.05; −slippage·3 (cap 0.10); clamp [0.50, 1.00].
8. **Runway penalty** (293–298): ≤ 0 → 0.50; < 0.5% → 0.25; < 1.0% → 0.12; < 2.0% → 0.05; else 0.
9. **Regime multiplier** `_regime_mult` (300–322): RISK_ON/BULLISH 1.08; TRANSITIONAL/NEUTRAL 1.00; RISK_OFF/BEARISH 0.88; FLIPPED 0.72; unknown 1.00; × drift status Stable 1.00 / Drifting 0.88 / Flipped 0.72 / **unknown 0.88** (304); + CONTINUATION tier boost 0.08/0.08/0.04/0.02; clamp [0.50, 1.20]. Note: **regime multiplier IS inside `ev_final` here** — the superbrain PATCH-07 claim that "regime removed from EV" applies only to superbrain's dead wrapper, not to the engine itself.
10. **Confidence multiplier** (324–325): `clamp(0.5·dq/100 + 0.5·calibration/100, 0.25, 1.00)`.
11. **Convexity boost** (327–333): +0.25 phase_transition; +0.20 gamma_squeeze; +0.15 if `iv_rank < 0.30 and iv_tailwind_score > 20` (scale-impossible with layer3 decimal values); + up to 0.20 for convexity_score > 0.70; clamp [1.0, 1.60]; **applied only when sev > 0** (366).
12. **Final**: `ev_final = (sev·pm·ce·em·rm·cb) − runway_penalty`; `ev_conf_adj = ev_final·cm` (371).
13. **Classification** `_classify` (346–352) on **ev_conf_adj** (not ev_final): `data_quality_score < 40` → **DATA_WEAK / size 0 / AVOID**; ≥ 0.25 → PASS_HIGH / 1.25× / STRONG; ≥ 0.10 → PASS / 1.00 / MODERATE; ≥ 0.00 → PASS_SMALL / 0.50 / WEAK; ≥ −0.10 → WEAK_PASS / WAIT / 0.25 / AVOID hint; else FAIL / 0 / AVOID.
14. Quality score `0.25·ps + 0.20·bmps + 0.20·p·100 + 0.20·pm·100/1.5 + 0.15·dq` (373–374); risk score from exec mult, gamma obstruction, survival, spread (375–376).

---

## 8. `avshunter_monetisation_policy.py` (ROOT copy, 599 lines)

### Role / invocation
Imported plainly (`from avshunter_monetisation_policy import …`) by `execution_intelligence_runner.py:381` and `test_pipeline_regression.py:496`. **Which copy wins is determined by sys.path order** — see §9. Evaluated per-row in EIL Pass 1 (`_enrich_row_for_ev`, EIL:904–915), where any exception is caught at debug level and the row proceeds with only `mp_hard_block_reason=""`.

### Rule set (v1.0)
**States** (46–55): GO, GO_SMALL, GO_LATE, WAIT, BLOCK_DATA, BLOCK_LIQUIDITY, BLOCK_ECONOMICS, BLOCK_STRUCTURE, BLOCK_EXECUTION. **Severities** (58–63): FATAL, TAX, TIMING, INFO.

**Hard-block thresholds (144–157)**: `HARD_SPREAD_BLOCK=0.20`; `HARD_DATA_LIVE_SPREAD_BLOCK=0.15`; `HARD_THETA_BLOCK=0.80`; `HARD_RUNWAY_MIN=0.0`; `HARD_BREAKEVEN_RUNWAY_RATIO=0.90`; `HARD_DTE_MIN=5`; `HARD_STRUCTURE_MIN=45.0`; **`HARD_PREMIUM_MIN=$20.00`** (157, ENHANCEMENT 4: commission ≤ 10% of position).

**Soft/tax thresholds (160–167)**: `SOFT_SPREAD_WARN=0.08`; `SOFT_THETA_WARN=0.45`; `SOFT_IVR_HIGH=0.70`; `SOFT_DRIFT_WARN=0.02`; `SOFT_DRIFT_LATE=0.04`; delta band 0.20–0.60; `SOFT_GAMMA_TIGHT=0.25`.

**Evaluate flow (169–431)** — base size from regime (433–442): RISK_OFF/FLIPPED **0.35**; TRANSITIONAL/CHOPPY/CHOPPY_NEUTRAL/DRIFTING **0.60**; RISK_ON/TRENDING_BULL/**TRENDING_BEAR**/STABLE **1.00**; unknown **0.75**. Then, in order:
1. DATA_001: `data_complete` False → BLOCK_DATA (193–195). DATA_002: stale + no live quote → BLOCK_DATA (196–198).
2. EV3 advisory (204–213): recorded as INFO only — "EV is evidence, not authority… never grant or deny capital with it."
3. STR_001 thesis False → BLOCK_STRUCTURE (219–221); STR_002 structure_confidence < 45 → BLOCK_STRUCTURE (222–224); STR_003 truth_confidence < 55 → ×0.80, −6 priority (229–233); STR_005 contradictions → ×(1 − min(0.03·n, 0.15)), −2·n (237–241).
4. OPT_001 dte < 5 → BLOCK_ECONOMICS (247–249); dte=None quietly passes as OPT_000 (251).
5. **OPT_015 premium < $20 → BLOCK_ECONOMICS FATAL** (256–266).
6. OPT_014 negative rr_raw → BLOCK_ECONOMICS (275–281).
7. OPT_002 spread > 0.20 (or 0.15 live) → BLOCK_LIQUIDITY (283–287); OPT_003 spread > 0.08 → ×0.75, −8 (288–292).
8. OPT_005 theta_drag > 0.80 → BLOCK_ECONOMICS (296–299); OPT_006 > 0.45 → ×0.80, −5 (300–304).
9. OPT_008 runway ≤ 0 or runway/breakeven < 0.90 → BLOCK_ECONOMICS (308–312); OPT_009 ratio < 1.5 → ×0.75, −7 (313–317).
10. OPT_011 iv_rank > 0.70 → ×0.85, −4 (321–325).
11. OPT_012 delta outside [0.20, 0.60] → ×0.90, −2 (327–332).
12. EXE_001 drift > 0.04 → late flag, ×0.70, −5 (339–345); EXE_002 drift > 0.02 → ×0.85, −3 (346–349).
13. EXE_004 iv_distortion > 0.80 → BLOCK_EXECUTION (353–355); EXE_005 > 0.60 → ×0.80, −4 (356–359).
14. EXE_006 |gamma_flip_gap| < 0.25 → wait flag, ×0.85, −3 (361–367).
15. Execution mode overlay (374–392): PROBE ×0.25; REDUCED_EXECUTE ×0.50; FULL_EXECUTE no-op; WAIT → wait flag; BLOCKED → BLOCK_EXECUTION.
16. Final (397–420): size clamped [0.10, 1.00]; hard block → `final_size_mult=0.0`; else state: wait_flag & size < 0.75 → WAIT; late & size < 0.85 → GO_LATE; size < 0.85 → GO_SMALL; else GO.

**Row mapper `map_options_row_to_policy_input` (449–521)**:
- **BROKEN `_int()` (463–476)**: the function body is only `v = row.get(k); if v in (None,"","nan","NaN","N/A"): return None` — the `try: return int(float(v))` lines sit as dead code *after the return* of the nested `_bool` definition. **`_int` returns `None` for every valid value.** Consequences: `dte` is always None → the DTE-too-low block **never fires** from mapped rows; `contradictions` always 0 → STR_005 never fires; `tier` always None. Present in BOTH copies (scripts: 591–604).
- theta_drag normalised ÷100 when > 1.0 (485–486); `quote_source_live` from "marketdata" substring or `live_quote` (499); premium from `contract_premium|mark` (501); rr_raw from `rr_options|rr` (508); `_win_rate`/`_ev_pct` computed (489–490) **then never used** — dead code; iv_rank read raw (505) with no 0–100→0–1 normalisation (superbrain normalises at its line 829; MP does not — a 0–100-scale iv_rank makes OPT_011 tax fire on every row).

---

## 9. `scripts/avshunter_monetisation_policy.py` (SCRIPTS copy, 736 lines) + DIFF vs root

### Which copy actually loads
`execution_intelligence_runner.py` builds sys.path by `insert(0, p)` over `[_ROOT, _VANGUARD, …, _SCRIPTS]` (EIL:157–168) — each insert pushes to front, so **`scripts/` ends up FIRST in sys.path, ahead of root**. Therefore `from avshunter_monetisation_policy import …` (EIL:381) resolves to the **scripts copy** in the live EIL run. The **root copy** is what `test_pipeline_regression.py:496` (run from root) exercises — **the regression tests validate the copy that production does not use**. The orchestrator's config also points at the scripts copy (orchestrator:469).

### Precise diff of rules / thresholds / behaviour

| Item | ROOT copy | SCRIPTS copy |
|---|---|---|
| `HARD_SPREAD_BLOCK` | **0.20** (root:144) | **0.15** (scripts:155, "aligned with scanner") |
| `HARD_DATA_LIVE_SPREAD_BLOCK` | 0.15 (root:145) | 0.15 (scripts:156) — so scripts blocks EOD/live identically; root is looser for non-live quotes |
| `SOFT_SPREAD_WARN` | **0.08** (root:160) | **0.10** (scripts:191) |
| Premium rule | **OPT_015 FATAL block: premium < $20 → BLOCK_ECONOMICS** (root:157, 256–266) | **No premium floor at all** (scripts:162–188, 304–338). Premium < $13.33 (`PREMIUM_SIZE_UP_THRESHOLD`, scripts:188) → **SIZE UP `size_mult ×= min(2.0, 13.33/premium)`, priority +3** (scripts:314–329). Then MP-01 caps: premium ≤ $0.50 → cap size at **0.25×** (OPT_MP01_MICRO, scripts:342–353); ≤ $2.00 → cap at **0.50×** (OPT_MP01_LOW, scripts:354–365). Rationale cited: T PUT $0.65 → +192% (scripts:163–166, 307) |
| **Latent crash** | n/a | **`Severity.WARNING` used at scripts:348 — the Severity enum (scripts:58–63) has no WARNING member → `AttributeError` whenever premium ≤ $0.50 and size_mult > 0.25.** In EIL this is swallowed by the per-row `except` (EIL:910–912), so the row silently loses ALL mp_* fields |
| DTE None handling | Falls into `else` OPT_000 "DTE acceptable" with value None (root:250–251) | Explicit three-branch: None → OPT_000 "No contract data — DTE gate skipped" INFO (scripts:284–302). Behaviourally identical given both copies' broken `_int()` |
| PolicyInput fields | — | adds `macro_sector_bias` (default "UNKNOWN"), `sector_alignment_score` (default 1.00), `sector_alignment_flag` (default "NEUTRAL") (scripts:119–122) |
| Sector overlay | absent | Section 6 (scripts:489–520): flags BLOCK / REDUCE / BOOST are logged as **INFO / advisory only** — even `sector_alignment_flag == "BLOCK"` does **not** block or resize (scripts:498–504) |
| `summarise_policy_output` | 7 keys (root:524–533) | + `mp_sector_rule`, `mp_sector_note` (scripts:656–670) |
| `map_options_row_to_policy_input` | no sector fields | + 3 sector fields (scripts:650–652) |
| Everything else | identical | identical — same DATA/STR/OPT/EXE rules, same regime base sizes (scripts:561–570), same execution-mode overlay, same final-state thresholds, same broken `_int()` (scripts:591–604) |

**Net behavioural divergence**: a $5-premium contract is FATALLY BLOCKED by the root copy but SIZE-UPPED ×2 (then capped 0.50×) by the scripts copy; a 17%-spread EOD quote passes the root copy (< 0.20) but is BLOCK_LIQUIDITY in the scripts copy (> 0.15); a 9% spread is taxed ×0.75 by root, clean-pass by scripts. Depending on which entry point runs (EIL live path vs regression tests vs any script importing from root cwd), the same signal gets opposite treatments.

---

## Observations relevant to contradicting signals (evidence only, with line numbers)

1. **The macro router extracts biases and then ignores them.** `extract_horizon_biases` builds per-horizon action/size/confirm (`macro_horizon_router.py:196–264`), but the routing loop appends every valid signal with hardcoded `GO_SELECTIVE, size_multiplier=1.0, confirm_required=[], macro_permitted=True` (485–492). `_go_to_action` maps MONITOR/NO_GO to GO_SELECTIVE (173–174). The macro JSON can say MONITOR_ONLY / 0.0 size; the routed rows will still say GO_SELECTIVE / 1.0.

2. **RISK_OFF/CRISIS "kill-switch" comment vs code.** Lines 481–482 say "Hard kill-switch: RISK_OFF / CRISIS regime blocks everything"; lines 467–474 only `log.info` and continue. The router's own QA suite (768–785) asserts PUT bearish-prob blocks, MONITOR_ONLY blocks, LLR blocks, and COMPLACENT blocks that no longer exist in the loop — the shipped tests fail against the shipped router.

3. **Three different horizon size multipliers for the same bucket.** Router: always 1.0 (491). SuperBrain fallback: 1.0 / 0.70 / 0.35 for 1_5d / 6_10d / 11_20d (superbrain:2281–2285). Orchestrator ticker-patch default for unrouted tickers: **0.0** (orchestrator:1571–1573). Which value a downstream consumer sees depends on which stamping path ran last.

4. **SuperBrain's MONITOR_ONLY gate condition is inverted vs its own comment and keyed to a value the router can no longer emit.** Comment: "horizon_bucket = 11_20d → override to MONITOR_ONLY" (superbrain:2043); code: fires only when `horizon_action == "MONITOR_ONLY" and _horizon_bucket != "11_20d"` (2051). The reason string hardcodes "bullish_prob=54.1% NEUTRAL" (2059) regardless of the actual macro. And since SuperBrain is bypassed (passthrough) and the router never emits MONITOR_ONLY, this gate is doubly dead.

5. **The entire SuperBrain rule stack is dead on the production path, but its column names survive.** Passthrough (orchestrator:2832–2949) writes only `sb_final_verdict = options_verdict` (2875–2878) plus NaN contract columns. `sb_risk_label`, `sb_size_pct`, `sb_conv_score`, `sb_execution_mode`, DATA_WEAK escalation (superbrain:1370–1388), the −0.10 EV gate (1390–1398), the GARCH expensive-vol gate (1519–1536) and the ladder/time-stop all silently vanish; anything downstream reading those columns gets blanks against a file whose header banner itself warns the DATA_WEAK gate "reads as live logic but is bypassed entirely" (superbrain:20–23).

6. **IV-tailwind sign and scale conflict across three modules.** layer3 defines positive tailwind = IV above forecast = *expensive/headwind* (layer3:519–524). SuperBrain's (dead) gate agrees: tailwind > +0.15 → GATE_EXPENSIVE_VOL cap (superbrain:1526–1536). But EVEngineV2's `_vega_adj` **adds** `+iv_tailwind_score/100·0.30` to contract EV (ev_engine_v2:274) — positive (expensive) IV *raises* EV — and divides by 100 as if the score were 0–100 while layer3 emits a decimal (capped ±1.50, layer3:67, 119–123), making the term ~0.0005 in practice. `_conv_boost` requires `iv_tailwind_score > 20` (ev_engine_v2:331), unreachable on layer3's scale. Also the EV engine reads column `iv_tailwind_score` (209) while the GARCH CSV emits `l3_iv_tailwind_score` (layer3:133) — three interoperating modules, three incompatible conventions for the same number.

7. **Regime affects EV in one engine and "must not" in another — and the regime vocabularies don't match.** EVEngineV2 multiplies regime (0.72–1.20) *inside* `ev_final` (ev_engine_v2:300–322, 371). SuperBrain PATCH-07 documentation claims regime was removed from EV and is sizing-only (superbrain:1820–1832) — true only of superbrain's dead fallback. MonetisationPolicy sizes by regime again (base 0.35/0.60/1.00, root:434–442 = scripts:561–570) — **regime is triple-counted on a path where both EV and MP run (EIL Pass 1, EIL:904–915 + `_compute_all_ev`)**. Vocabulary mismatch: `macro_quant_packet._regime_label` emits RISK_ON/RISK_OFF/CHOPPY/CRISIS/TRANSITIONAL (macro_quant_packet:214–230); EVEngineV2 knows RISK_ON/BULLISH/TRANSITIONAL/NEUTRAL/RISK_OFF/BEARISH/FLIPPED, unknown → 1.00 (ev_engine_v2:301–303) — CHOPPY and CRISIS both silently score 1.00 (neutral) in EV while MP would size CHOPPY at 0.60 and macro_quant scores CRISIS −100. And MP gives **TRENDING_BEAR full 1.00 base size** (root:440, scripts:568), grouped with RISK_ON.

8. **Two divergent MonetisationPolicy rulebooks are simultaneously reachable, and prod loads the untested one.** EIL's sys.path puts `scripts/` first (EIL:157–168 — `insert(0,…)` reverses the list order), so live runs use the scripts copy; `test_pipeline_regression.py:496` imports from root. Root FATALLY blocks premium < $20 (root:157, 256–266); scripts **size-ups** the same trade ×≤2.0 (scripts:314–329). Root blocks spread at 0.20, scripts at 0.15 (root:144 vs scripts:155). Opposite verdicts on the same row depending on import path.

9. **Latent AttributeError in the live MP copy silently strips all MP output for micro-premium rows.** `Severity.WARNING` (scripts:348) does not exist in the enum (scripts:58–63); the branch triggers for premium ≤ $0.50 after the size-up boost; EIL's per-row `except` (EIL:910–912) reduces the row to `mp_hard_block_reason=""` — the trade proceeds with no MP sizing, no caps, no blocks.

10. **`_int()` is broken in both MP copies** (root:463–476, scripts:591–604): returns None for all values (the int-conversion lines are dead code inside the nested `_bool`). Result: DTE < 5 hard block never fires from mapped rows, contradictions tax (STR_005) never fires, tier is always None — while `avshunter_discovery_ULTIMATE.py:2182` explicitly relies on "monetisation_policy does not hard-block on dte=0".

11. **Same feature scored as both edge and veto.** Gamma-wall proximity: convexity C4 passes when |wall−spot| ≤ 2% (superbrain:856–872) while V2 STAND_DOWNs at/through the wall (639–661) and MP's EXE_006 WAITs when gamma gap < 0.25 (root:361–367). A signal hugging the wall is simultaneously "skyrocket profile" and "zero runway".

12. **Three incompatible runway standards.** SuperBrain/convexity: runway must exceed **2.0× breakeven** (superbrain:370, 383, 899). MP: FATAL below **0.90× breakeven**, tax below 1.5× (root:308–317). EVEngineV2: absolute-percent penalties at 0.5/1.0/2.0% and hard gate only at ≤ 0 (ev_engine_v2:293–298, 341). The same runway value passes one layer and fails another.

13. **EV gate variables differ per layer.** SuperBrain gates on `ev_final < −0.10` (superbrain:1368, 1390); EVEngineV2 classifies on `ev_conf_adj = ev_final × confidence_mult` (ev_engine_v2:346–352, 371); MP explicitly refuses to use EV at all ("EV is evidence, not authority", root:203–213). A WEAK_PASS-by-`ev_conf_adj` signal can pass superbrain's `ev_final` floor, and MP will neither confirm nor veto.

14. **Win-rate scale hazard.** EVEngineV2 clamps `win_rate_*d` to [0,1] assuming fraction scale (ev_engine_v2:85–91); a percent-scale 57.8 silently becomes 1.0 (=100% win). SuperBrain's discovery bridge normalises ÷100 and clamps 0.30–0.80 (superbrain:1860–1876) — but that bridge is dead on the passthrough path, so EIL's direct `ev_inputs_from_row` sees whatever scale the CSV carries.

15. **iv_rank scale inconsistency.** SuperBrain normalises iv_rank ÷100 when > 1.0 (superbrain:829); EVEngineV2 defaults iv_rank to `ivp_252d|iv_percentile|0.50` and compares to 0.30 decimal (ev_engine_v2:208, 331); MP compares raw `iv_rank` to 0.70 decimal with no normalisation (root:321, 505) — a 0–100-scale column makes MP's high-IV tax fire on every row.

16. **Fabricated-geometry defaults in EV.** Missing target/stop → `target = entry×1.10`, `stop = entry×0.95` (ev_engine_v2:110–112); missing DTE → 30 → horizon 20 (102–105); `data_quality_score` missing → 100 (220); premium missing → $1.00 (108); regime missing → TRANSITIONAL (215). Missing data thus produces confident-looking, non-neutral EVs — while the router *blocks* missing DTE outright (macro_horizon_router:377–390). One layer treats absent DTE as fatal; the next silently invents 30.

17. **Layer3 expected-move buckets are incremental, EV expected moves are cumulative.** `l3_expected_move_6_10d = move(10) − move(5)` (layer3:516–517), while EVEngineV2's `expected_move_10d` inputs are treated as total moves over the horizon (ev_engine_v2:245–254). If layer3 outputs ever feed the `expected_move_*` chain, mid/long-horizon EVs are computed on ~⅓-size moves.

18. **RISK_OFF vol inflation flips the cheap/expensive verdict.** layer3 multiplies forecast RV ×1.10 in RISK_OFF, ×1.05 in TRANSITIONAL (layer3:507–510), which *lowers* `iv_tailwind = IV − RV` — the same option looks systematically *cheaper* precisely in the regimes where MP cuts base size to 0.35/0.60 and EV multiplies by 0.88.

19. **Ticker-level horizon patch corrupts CALL/PUT pairs.** Orchestrator maps horizon fields by ticker (`_ticker_to_raw`, orchestrator:1519–1522; `_lookup[_sig.ticker]`, 1553–1561), acknowledged "collision-unsafe when same ticker has CALL + PUT" (1519–1520) — one direction's bucket/size is stamped onto both rows, despite the router providing collision-safe `signal_id` (macro_horizon_router:449, 563–579) for exactly this purpose.

20. **CALL/PUT asymmetries in warning discounts.** Regime discount 0.5 applies to PUT in RISK_OFF **or TRANSITIONAL**, but to CALL only in RISK_ON (superbrain:1658–1661) — in TRANSITIONAL regimes PUTs get their structural warnings discounted, CALLs don't. The discount also keys on column `direction` only (1656) while the rest of the file accepts `options_direction` (498–505). (Both dead on the current path but live via CLI.)

21. **"Momentum" is conviction.** `macro_momentum_score` is derived from `macro_conviction|conviction_score|predictability_score` (normalise_macro_contract:193–210) — a confidence measure relabelled as momentum; the router reads it (macro_horizon_router:343) and never uses it.

22. **Missing-macro defaults disagree in temperament.** `missing_macro_quant_packet` sets liquidity_risk_flag=True, gamma_risk_flag=True, equity_drawer_active=True (pessimistic) yet `bond_trade_go=True` (optimistic) (macro_quant_packet:727, 739, 758, 764). Router with a missing macro *file* raises and Phase 1B degrades to "legacy mode" with **no horizon columns at all** (macro_horizon_router:326–329; orchestrator:1636–1642) — downstream then sees `horizon_bucket` absent (SuperBrain "legacy mode, process normally", superbrain:2047) or "unrouted" with multiplier 0.0 (orchestrator:1571–1573), two different fates for the same missing input.

23. **Execution-mode WAIT for EXECUTE-verdict signals.** `_compute_execution_mode` returns WAIT for any conviction < 4 (superbrain:199–207) even when the verdict is EXECUTE; MP then wait-flags on `execution_mode == "WAIT"` (root:387–389). On the passthrough path `sb_execution_mode` is never produced, so MP's overlay reads whatever `execution_mode` column happens to exist — or nothing (root:520).

24. **Bare/blanket exception swallowing at every seam** — each converts a hard failure into a silent behavioural change: EV import (superbrain:254–257), EV evaluate → v1 fallback (superbrain:1908–1909), sector alignment per-row (superbrain:2483–2484), MP per-row in EIL (EIL:910–912), regime load default TRANSITIONAL (garch_runner:165–167), price fetch → skip ticker (garch_runner:130–132), EGARCH/GARCH fits (layer3:366–367, 390–391), `_safe`/`b()` (ev_engine_v2:23–27, 77–82), `_safe_float_local` bare `except:` (root MP:178, scripts MP:209), suffix-resolution fallback (macro_quant_packet:889–890).

---

# SECTION E — Lab materializer & Phase-0 scanner

# AVSHUNTER Lab Materializer & Phase-0 Scanner — Logic Reference

## 1. `contracts/lab_control.py` (3,024 lines) — Lab materializer

### 1.1 Role / invocation
Docstring (L1–6): "does not create signals; it validates and normalises the committed pipeline baton for the human execution cockpit." Entry points: `build_final_run_manifest` (L1033) / `write_final_run_manifest` (L1225) → `final_run_manifest.json`; `resolve_lab_tradeability` (L1389) / `apply_lab_resolution` (L1783); `build_final_opportunity_book` (L2374); `write_final_opportunity_book` (L2852) → `intelligence_lab/final_opportunity_book_{run_id}.csv/.json` + `lab_triage_view_{run_id}.csv` + Interpreter sync; `read_final_opportunity_book` (L2964); `learning_feedback_from_closed_trades` (L2969).

### 1.2 Inputs
`_output_files` (L959–1002) globs per run dir: discovery CSV, `vanguard_signals_enriched` (options/ first, else vanguard/), `superbrain/eil_enriched`, `execution/execution_v3_5` (else superbrain/), `options/options_intelligence`, V5 signals, `morning_validated_trades`, `morning_candidates`, morning packet JSON, dossiers, summaries, audits, macro JSONs. Enrichment adds `wall_break_scores` and `garch_forecasts` (L2398–2411). Output contract: `FINAL_BOOK_FIELDS` (L63–461) — 232-field `lab_signal_book_v2`; triage view = same minus `source_payload_json` (L466).

### 1.3 Run manifest (L1033–1222)
Phase status per `_phase_status` (L1005–1030). Fatal flags: `EIL_OUTPUT_MISSING_OR_INVALID` (L1094), `EOD_CANDIDATE_MANIFEST_MISSING` (L1098), `LIVE_VALIDATION_MISSING` (L1113), `HARD_CONTRADICTIONS_PRESENT` (per-row `EIL_BLOCKED_GO`, `PSE_FATAL_EXEC`, `MISSING_TRIGGER_EXEC`, L1117–1133). Health score 100 −30/fatal −8/MISSING −5/WARN −3/stale (L1135–1140). `run_tradeable` (L1142–1148) requires no fatal, no pending morning validation, no paper mode, EIL PASS >0 rows. `ev3_production_authority` hard-coded False (L1220).

### 1.4 Verdict resolution — `resolve_lab_tradeability` (L1389–1780)
**Source snapshot** (L1394–1418): ~18 upstream verdict fields with alias chains. Legacy `mv__verdict` map (L1421–1438): EXECUTE→GO, STARTER→PROBE, FLAG/MANUAL_REVIEW/WATCH→WAIT, REJECT(ED)→BLOCKED. `lab_execution_status` backfilled through a **silent default cascade** (L1440–1447).

**Execution-Gate authority short-circuit** (L1469–1472 → `_resolve_execution_gate_authority` L1318–1386), mapping table (L1328–1335):

| `final_action` | lab_verdict | lab_tradeable |
|---|---|---|
| BUY_NOW | GO | True |
| BUY_SMALL | GO_LIMIT | True |
| CONTRACT_REPAIR | CONTRACT_REPAIR | False |
| MANUAL_REVIEW | MANUAL_REVIEW | False |
| BLOCK / SKIP | BLOCKED | False |
| **anything else (incl. COST_DESTRUCTION)** | **returns None → falls to research resolver** (L1336–1337) |

- **COST_DESTRUCTION is not in the map and not in `HARD_EXECUTION_STATES` (L514–523)** — a gate-blocked idea is re-adjudicated by the research resolver, which doesn't recognise it, and can emerge ARMED/WAIT — or GO via morning permission (L1673). Only trace: `final_action` copied verbatim into the book (L1932). *(This is the RR-001 "COST_DESTRUCTION becomes GO_LIMIT" defect, at line level.)*
- Non-monetisable state appends only a warning `MONETISABILITY:<state>` (L1346–1348) in this path.
- Structure policy (L1349–1362): BUY_NOW with RESEARCH_ONLY structure **keeps GO** here (advisory flag only), while the research path forces WAIT (L1729–1733) — asymmetric.
- Alignment stamped `ALIGNED_EXECUTION_GATE` (L1383) without checking morning permission.

**Research/EOD resolver** (rows with unmapped `final_action`): `looks_actionable` set (L1478–1495). `_lab_structure_policy` (L689–737): multi-leg/strangle tokens → RESEARCH_ONLY; no symbol → CONTRACT_REPAIR; invalid OCC → INVALID; **governed_side = `first(sig,"canonical_direction","direction")` or instrument side (L718–723) — never consults `governed_direction`**; side ≠ contract side → `LONG_SINGLE_DIRECTION_SIDE_MISMATCH` (L732); hydration ≠ COMPLETE → INVALID. Missing strike/expiry/premium on actionable row: EOD-without-morning → soft; else hard veto (L1510–1526). **Spread policy** (L1528–1542): `pct = spread*100 if spread <= 1 else spread` (L1531) — **unit heuristic: a percent-recorded 0.8 (0.8%) is read as 80% → hard veto `SPREAD_TOO_WIDE`**; > 25% (LAB_ABSOLUTE_SPREAD_MAX_PCT) veto; > executable ceiling → soft `MANUAL_LIQUIDITY_REVIEW`; ≤0 → UNAVAILABLE soft flag. Hard vetoes (L1544–1595): morning BLOCKED/REJECTED; `"BLOCKED" in eil_v3_verdict` (substring, L1560); verdicts in HARD_EXECUTION_STATES; PSE FATAL_BLOCK; token scan for HARD_BLOCK/FATAL/INVALID (L1576–1582 — the `for _ in [0]` loop makes only the **first** non-missing gate-text field contribute); duplicate open trade (L1584); LIVE without validation. Soft flags incl. morning CONTRACT_REPAIR/PROBE/GO_LIMIT/WAIT/ARMED, NO_LIVE_DATA/STALE, WAIT_RETEST, V5_PROBE_WITHOUT_BUY_NOW, manifest stale; EV flags advisory-only (L1605–1614: "R:R… does not decide Lab permission"). **Verdict ladder** (L1632–1713): vetoes → BLOCKED/HARD_CONFLICT; EOD exec status → EOD_EXEC (tradeable only with zero soft flags) or EOD_CAUTION; full alignment → GO; partial → ARMED; else WAIT; then **morning permission override** (L1672–1713): GO→GO unless critical-soft→ARMED; GO_LIMIT→GO_LIMIT/ARMED; PROBE→PROBE/ARMED; CONTRACT_REPAIR/ARMED/WAIT map through. (Dead branch at L1699.) EOD prep pending → `MORNING_VALIDATION_REQUIRED` (L1715–1725). Lab-only overrides (L1727–1746): RESEARCH_ONLY → WAIT; INVALID → CONTRACT_REPAIR; spread review → `MANUAL_LIQUIDITY_REVIEW`. Morning/Lab alignment map (L1261–1315).

### 1.5 Row build (L1884–2371) — **the two direction populations**

**Population A — canonical/final/direction (111 PUT / 90 CALL):**
- L1885: `canonical_direction = first(sig, "final_direction", "canonical_direction", "resolved_direction", "direction", "options_direction", "selected_contract_side", "option_direction")` — a fallback chain that includes non-governed sources: the options-phase direction and **the selected contract's side**. `first()` (L564–569) treats `NONE/UNKNOWN/MISSING/N-A/NAN/NULL` as absent (L552–554), so an upstream "UNKNOWN" governed value silently falls to the contract side.
- Written to `canonical_direction` (L1944), `direction` (L1995 — same variable), `final_direction` (L1952, re-read from sig, so it can be "" while the others are populated — they can differ even from each other).
- Population A **rewrites tradeable artefacts**: `instrument` realigned (`_instrument_for_direction` L634–650, forcing LONG_CALL/LONG_PUT, swapping sides inside spread labels) and **`contract_symbol` re-selected to match it** (`_contract_for_direction` L661–686: scans 9 symbol fields for a matching OCC side; flags `CONTRACT_RESELECTED_FOR_DIRECTION:old->new` L681 or `CONTRACT_SYMBOL_SIDE_CONFLICT` L685). `trade_idea_id` embeds it (L1875–1881).

**Population B — governed_direction (104 CALL / 77 PUT / 20 STRANGLE):**
- L1949: verbatim `first(sig, "governed_direction")` — no fallback, **no reconciliation against Population A**; same for authority/basis/resolution fields and the GDR JSON+sha (L1950–1965).
- The only cross-check is external `validate_direction_record` (L2346), whose failure **forces BLOCKED only for actionable rows** (L2350–2369: tradeable, verdict ∈ {GO, GO_LIMIT, PROBE}, or final_action ∈ {BUY_NOW, BUY_SMALL}). Non-actionable rows are published with both divergent columns and `direction_integrity_status=FAIL` (L2349).

**Divergence mechanism:**
1. Population A prefers later-phase fields and falls back to the **contract's side** — the contract tail wags the direction dog.
2. `_side_from_value` (L619–631) maps only CALL/PUT synonyms; **STRANGLE → ""** — the 20 governed-STRANGLE rows cannot be represented in Population A and resolve from the next fallback (typically the contract side), guaranteeing ≥20 disagreeing rows.
3. `_lab_structure_policy` (L718) and `_recompute_governed_lab_fields` (L2625) use a **third** chain (`canonical_direction, direction` — no final_direction, no governed); `duplicate_open_trade` (L1247, L1253) a **fourth** (canonical → resolved → footprint → …).
4. The trade-idea join key embeds direction (L1877), so diverging populations also break exact joins during enrichment → silent degradation to ticker-level joins (L2800–2804).

**CALL/PUT asymmetries:** `_side_from_value` maps SELL/SHORT → PUT (an execution token becomes a direction, L625). **PUT-only WBS correction** (L2628–2655): when intraday PCR is unavailable, PUT rows lose 5 points from `wbs`/`wbs_f5_momentum` and are re-graded (75/55/35 boundaries, L2641–2646) — evening WBS grades for PUTs can differ from the producer file, PUTs only. PCR alignment (L2677): PUT aligned iff pcr>0.8, CALL iff pcr<0.4; the 0.4–0.8 band is NOT_ALIGNED for both.

### 1.6 Field authority / source priority
(a) Per-field alias chains in the row build (e.g. `morning_execution_permission` L1969–1976; `underlying_price` L2228 — 7 fallbacks ending scanner_price/signal_price; `execution_category` L1937 falls back to `lab_verdict` — display mixes authorities). Contract-economics fields blanked unless a contract is selected (L2101–2106, L2242–2251).
(b) File-level authority in enrichment — `_lab_field_source_priority` (L2555–2596), applied **only to fields still missing** after the row build (L2796–2797), except WBS: `garch_*` → garch file; **`wbs*` → wall_break_scores exclusively and forcibly — existing copied values are overwritten/blanked** (L2777–2795); `trigger_*` → eil_enriched > execution > morning_validated > morning_candidates; `ev3_*` → OI > execution > eil > morning_candidates; `catalyst_*` → OI > vanguard > eil > execution; sector → vanguard first; options analytics → OI first (L2573–2579); **contract economics → morning_validated > OI > execution > eil** (L2580–2589); `layer2__*` → vanguard; default → morning_validated > execution > eil > OI > vanguard > WBS > garch > morning_candidates (L2592–2596). Join rules (L2798–2826): exact trade_idea_id preferred; ticker fallback only if one-to-one, else `AMBIGUOUS_JOIN`; contract-economics joins additionally require symbol-set equality else `CONTRACT_JOIN_REJECTED` (L2811–2826). Provenance stamped L2868–2900.

### 1.7 Economics identity & monetisability
`_economics_identity` (L776–860): comparable requires monetisability COMPLETE + symbol match + evaluation-id match (L826–837); EV3 alignment analogous (L838–844). `_enforce_economics_identity` (L863–914): mismatch → `ev_predicted` blanked, `lab_coherence_status=ECONOMICS_CONTRACT_MISMATCH`; **only when `final_action` is empty** (L906) is a GO/tradeable row downgraded to CONTRACT_REPAIR (L909–913) — "Morning permission is immutable after the Execution Gate" (L904–905). Run twice: row build (L2341) and after enrichment (L2715).

### 1.8 OLM guard
`_enforce_olm_lab_guard` (L1813–1872): non-CONTINUE disposition rewrites verdict (BLOCK/SKIP → BLOCKED "NO_TRADE"; CONTRACT_REPAIR → REPRICE_REQUIRED + `economics_comparable=False` L1855; else MANUAL_REVIEW/MONITOR_ONLY) and **can overwrite `final_action` itself (L1867)** — one of two places later logic mutates the gate baton (the other: direction integrity, L2360).

### 1.9 Ranking
Sort key = verdict order `{GO:0, GO_LIMIT:1, PROBE:2, MANUAL_LIQUIDITY_REVIEW:3, CONTRACT_REPAIR:4, MORNING_VALIDATION_REQUIRED:5, ARMED:6, WAIT:7, BLOCKED:8}` else **9** (L2386), then −priority_score, then ticker. **`EOD_EXEC`, `EOD_CAUTION`, `MANUAL_REVIEW` are not in the map → rank 9, sorted *below BLOCKED*** — and absent from `verdict_counts` (L2933–2935). Post-rank enrichment re-runs economics identity (L2715), which can flip verdicts after ranks are frozen.

### 1.10 Journal / interpreter handoff
Book + triage CSVs (L2904–2915); Interpreter sync via `ma_inputs_sync.on_pipeline_complete` inside `try/except: pass` (L2918–2926) — **a failed handoff is completely silent**. JSON payload with verdict counts, per-source sha256 manifest, reconciliation counters (L2737–2748, L2940–2958). `learning_feedback_from_closed_trades` (L2969–3022) aggregates win rates; warns not to loosen gates from it (L3018–3021).

### 1.11 Later-phase fields overwriting governed ones
`contract_symbol`/`instrument` realignment (§1.5); `rr_contract_symbol` re-bound (L1909–1913, L2831–2833); `notes` falls back to lock-reason → coherence notes → `sb_verdict_reason` (L2338) — narrative as notes authority; `trigger_price` synthesized from WBS phase triggers (L2613–2623); `entry_plan` from `wbs_entry_guidance` (L2609–2611); readiness stage L2688–2710. **`LAB_REQUIRED_FIELDS` (L38–61) names six `display_*`/permission fields produced nowhere in the module** — the required list and the book contract are out of sync.

### 1.12 Silent defaults / bare excepts
`_f` → 0.0 on any parse failure (L542–549); `_read_csv_rows`/`_read_json` swallow all exceptions → empty (L933–951) — a corrupt EIL file looks like "no candidates"; `first()` treats UNKNOWN/NONE as missing (L552–554); Interpreter sync `except: pass` (L2925–2926); provenance parse → `{}` (L2770–2773); spread unit heuristic (L1531); `hard_vetoes` display mixes producer and Lab-added vetoes (L2316).

---

## 2. `scripts/avshunter_universe_scanner.py` (3,203 lines) — Phase 0 VMS scanner

### 2.1 Role / invocation
Standalone two-tier options-mispricing scanner "operating INDEPENDENTLY of the main pipeline universe" (L5). CLI (L3071–3199): `--tier1` (first 75 of TIER2_UNIVERSE, L1260–1267), `--tier2` (~250 names, L144–188), `--tickers`, `--test`, `--rebuild-iv-cache`, `--dry-run`. Handshake (L33–38): writes `scanner_manifest.json`; orchestrator reads it if <24h old; NEW tickers injected into discovery; KNOWN tickers get VMS fields via the orchestrator-written scanner context. Pipeline never blocked by scanner absence.

### 2.2 Inputs / outputs
Inputs: MarketData daily candles (L1055), option chains (cached mode, strikeLimit 20, +7..+60d window, L1150–1171), historical ATM IV via local BS bisection (L830–856, rf 4%), SQLite IV cache (L478–501) seeded from `phantom_history.db` (L609–687), Form 4 JSON (L1559–1577), pipeline universe CSV for tagging (L2607–2618).
Outputs (L2840–2993): `contracts_{run_id}.csv`/`_latest` (OLIS rows, fields L2411–2460); `vms_scoreboard_{run_id}.csv`/`_latest` (per-ticker, L2666–2714, incl. `direction`/`direction_reason`, LSS fields, `scanner_primary_route`, `route_source="SCANNER_VMS"`); `scanner_manifest.json` (L2879–2946: go/probe lists, `route_source: "SCANNER_LSS"`, per-ticker dict with **empty `signal_grade` placeholders** — grading done later by signal_grader.py, L2929); `signal_history.json` (append-per-run, 90-day prune; write failure warns only, L2980–2981).

### 2.3 VMS score — `compute_vms` (L1274–1398)
ATM IV = mean IV of 10 nearest strikes, both sides, **all DTEs mixed** (L1291–1293). IV rank (L1299–1313): real if ≥10 history points → min-max percentile over 52w, confidence 0.95; else synthetic proxy vs `rv_series×1.2` range, confidence 0.65; **degenerate range → silent 0.5** (L1303, L1311). Term slope = IV(dte<14) − IV(dte>30), missing → 0.0; skew = put IV − call IV, missing → 0.0.
**Score (max 100)** (L1327–1336): IV rank <0.3 → +20 / >0.7 → 0 / else +10; vol_spread = RV−IV **binary +25 if >0**; compression +20; term_slope ≥0 → +15 else +10 (**minimum 10 always**); skew |<0.05| → +20, >0 → +10, else +5 (**put skew scores double negative skew**). Floor 15 — a ticker can never score 0.
**Decisions** (L1338–1343): GO ≥75, PROBE ≥60, WAIT ≥45, BLOCK <45 — **computed purely from volatility features, with zero directional input**.

### 2.4 scanner_direction (L1346–1375)
Vote tally: momentum_20d >+3% → +2 CALL / >0 → +1 / <−3% → +2 PUT / <0 → +1; above_ma20/ma50 → +1 each side; RSI>70 → +1 PUT / <30 → +1 CALL (mean-reversion); skew >+0.05 → +1 CALL ("calls cheap") / <−0.05 → +1 PUT; compression: momentum ≥0 → +1 CALL else +1 PUT (**exactly-zero momentum breaks toward CALL**, L1364). More call votes → CALL, more put → PUT, tie → NEUTRAL "straddle candidate". Missing inputs default 0.0/None/50 silently (L1346–1349).

### 2.5 LSS — Lead Signal Score (L1580–1751)
Weights (L1717–1721): 30% options-vol anomaly, 20% IV/skew, 15% dark-pool proxy, 15% short/Form4, 10% price-vol structure, 10% sector RS/ETF flow.
- Comp1: opts_vol_ratio ≥5→100 … ≥1.5→35, else 10; None → 0; ±sweep +15. Ratio needs ≥5 prior days in its own SQLite table — **first ~5 runs per ticker return None**; whole function one big `try/except → EMPTY` (L591–593). Sweep: call/put vol ≥2 → CALL_SWEEP, ≤0.5 → PUT_SWEEP.
- Comp2: iv_rank <0.20 → +50 / <0.35 → +30 / >0.70 → 0 / else +15; vol_spread >0.05 → +40 / >0.02 → +20 / <−0.05 → −20; |skew|>0.08 → +10.
- Comp3: dark-pool proxy (L1465–1520: large-premium +40, tight-spread-high-vol +30, open gap>2% +30; each in `except: pass`).
- Comp4: **`fetch_short_borrow_data` hard-coded unavailable (L1037–1052) → comp4 = 25 for every ticker, always** (L1668); Form 4 CLUSTER_BUY +25 / SINGLE_BUY +10 / CLUSTER_SALE −15.
- Comp5: compression +50; equity vol ratio ≥2 → +40 (≥1.5 → +20); atr_pct<0.15 → +10.
- Comp6: sector RS STRONG_OUTPERFORM 90 … MILD_UNDER 20; **`NO_MAP` (ticker absent from the 60-name SECTOR_ETF_MAP, L1405–1418) lands in the else → 0 — unmapped tickers penalised as strong underperformers**; ETF flow +20.
- Decisions (L1724–1734): LEAD_GO ≥75 → FULL_PIPELINE; LEAD_PROBE ≥60 → DISCOVERY_ONLY; LEAD_WATCH ≥45 → WATCHLIST_ONLY; LEAD_BLOCK <45 → EXCLUDED.

### 2.6 OLIS contract scoring / grades (L1754–2489)
Pre-screen (L1865–1890): VMS BLOCK; DTE <8 or >60; mid <0.04; spread ratio >0.18; moneyness >20%; OI <75; **iv_rank>0.72 rejects**; |Δ|<0.08. Components: VMI (L1893–1962: IVR 0–40, vol-spread 0–45, dual-confirm +10, REAL source +5, **backwardation −5 / contango +5 — the opposite sign to VMS's +15 for backwardation**); DC (L1965–2083: **direction mismatch multiplier 0.25** — code L1991 vs docstring 0.30 at L1976; momentum 0–30, MA 0–25, RSI 0–20, contrarian skew ±10, compression +8/+3; NEUTRAL ×0.70); CFS (L2086–2149: delta sweet spot 0.30–0.45 → 40; DTE target = 5/daily_rv clamp 14–55); PG (L2152–2229: σ-normalised breakeven 0–55, premium% 0–30, R:R-at-1σ 0–15); MM (L2232–2275: OI 0–65, spread 0–35).
Composite = 0.30·VMI + 0.25·DC + 0.20·CFS + 0.15·PG + 0.10·MM (L2364–2370), ×VMS multiplier GO 1.00/PROBE 0.85/WAIT 0.65/BLOCK 0 (L1847, L2373), −6 if spread>10% (L2376–2377).
**Grades** (L2382–2389): PRIME_LONG ≥74, SETUP_LONG ≥54, WATCH_LONG ≥36, PASS dropped. Selection (L2479–2489): with ≥2 PRIME and both sides qualifying, **deliberately returns best call + best put**; otherwise top 2 by score. A wrong-side contract retains up to 25/100 on DC → raw ceiling ≈81 > 74: **a contract against scanner_direction can grade PRIME_LONG on a GO ticker**.

### 2.7 Routing export
`_scanner_route` (L2827–2837): FULL_PIPELINE if GO or ≥75; DISCOVERY_ONLY if PROBE or ≥60; WATCHLIST_ONLY if WAIT or ≥45; else SCANNER_BLOCKED. Scoreboard `scanner_primary_route` = `lss_route or _scanner_route(...)` (L2855–2857) — **LSS wins when present: `decision=GO, scanner_primary_route=EXCLUDED` can coexist in one row**, while manifest go/probe lists are VMS-only (L2884–2887); manifest says `route_source: SCANNER_LSS` (L2905), the scoreboard column says `SCANNER_VMS` (L2858).

### 2.8 Silent defaults / bare excepts / asymmetries
- **Synthetic quotes**: chain rows without a bid but with a mid get bid/ask fabricated at mid ×0.97/×1.03 (L1220–1222) — a fake 6% spread, unflagged, scored as real downstream.
- `marketdata_get` → None on 404/402/errors (L785–807); `process_ticker` → None → **ticker silently vanishes from the scoreboard** (counted only in `no_data`, L2736–2738); worker exceptions → debug log (L2740–2743).
- Volume-anomaly whole-body except (L591–593); dark-pool `except: pass` ×3; per-contract scoring except → skip (L2462–2464); chain parse `except: continue` (L1245–1246, L2538–2539).
- Comp4 constant 25 (L1668). iv_rank degenerate → 0.5. RSI NaN → 50 (L1107). Missing MAs → spot (L1096–1097).
- Tier dedupe keeps the higher-VMS row (L3183–3188) — resolved by score, not recency.
- Asymmetries: VMS skew +10 pos vs +5 neg (L1336); compression tiebreak → CALL at momentum 0 (L1364); DC skew penalties call −5 at skew<−0.05 vs put −8 only at skew>+0.08 (L2064–2069).

---

## Observations relevant to contradicting signals (evidence-only)

1. **The two direction populations are written by two disjoint code paths and never reconciled** (lab_control L1885/L1952/L1995 vs L1949); the only integrity check hard-blocks actionable rows only (L2350–2369). This alone reproduces the audit's 111-PUT/90-CALL vs 104-CALL/77-PUT/20-STRANGLE pattern.
2. **The 20 STRANGLE rows cannot survive into the canonical column** — `_side_from_value` (L619–631) has no STRANGLE mapping; they display as directional from the contract-side fallback.
3. **The canonical population rewrites the tradeable artefacts** — instrument and contract_symbol re-selected to match the canonical side (L634–650, L661–686) — after which `_economics_identity` detects the symbol mismatch, blanks `ev_predicted` and locks the row (L826–835, L892–914): direction flip → contract re-selection → economics destroyed. A concrete "edge lost by end of run" mechanism.
4. **Four direction-resolution orders coexist in one module** (L1885, L718/L2625, L1247/L1253, L1877); the direction-embedding join key breaks exact joins when populations diverge, silently degrading field authority to ticker joins (L2800–2804).
5. **Scanner GO/PROBE has zero directional input**; `scanner_direction` is a weak vote with silent defaults; OLIS can attach a wrong-side PRIME_LONG contract and deliberately exports best-call+best-put for PRIME tickers (L2481–2487); these fields sit in the Lab's canonical fallback chain (L1885, L2228–2230).
6. **COST_DESTRUCTION and any unmapped final_action silently lose gate authority** (L1328–1337 → None; not in L514–523 or L1478–1495) and can resurface ARMED/WAIT or GO via morning permission (L1673–1683).
7. **Ranking map incomplete** (L2386): EOD_EXEC/EOD_CAUTION/MANUAL_REVIEW rank 9, below BLOCKED (8); absent from verdict_counts (L2933–2935). **Verdicts can change after ranks freeze** (L2715 after L2394).
8. **Spread unit heuristic** (L1531): percent-recorded values in (0.25, 1.0] are re-read ×100 → coin-flip hard veto across mixed producers.
9. **Scanner route vs decision contradiction is self-exported** (L2855–2857 vs L2884–2887; route_source labels disagree L2905 vs L2858).
10. **Two engines score the same feature in opposite directions**: backwardation +15 in VMS (L1335) vs −5 in OLIS VMI (L1958); put-skew earns VMS points and a CALL vote (L1336, L1362) while Lab PCR alignment reads high PCR as PUT-aligned (L2677).
11. **PUT-only WBS correction at materialization** (L2636–2655) — evening WBS grades for PUTs can differ from the producer file, PUTs only.
12. **Silent data loss everywhere upstream of verdicts**: `_read_csv_rows`/`_read_json` swallow all exceptions (L933–951); interpreter sync silent (L2919–2926); scanner drops tickers on any API failure at debug level (L2736–2743) and fabricates bid/ask from mid (L1220–1222). Run-to-run contradictions can reflect which fetches happened to fail, with no flag in the outputs.

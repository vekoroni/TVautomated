# AVSHUNTER: source of truth and decision handoff (final design, v1)

**Status:** proposed for ACK and development review. Not implemented, not release-approved. No code has been changed.
**Date:** 6 Oct 2026. **Reference population:** run `20261006_060401` (Evening and Morning).

**Inputs merged into this document:**
1. `ROOT_CAUSE_AND_DESIGN.md`, same folder; this document supersedes it.
2. The development-review design "Intelligence Lab Source-of-Truth and Decision Handoff Design" supplied by ACK on 6 Oct, reviewed in §A.
3. The whole-pipeline audit of 6 Oct: measured data flow, history of recurring defects, handoff mechanics and the fact-ownership map. §C records which parts are complete and which are pending.

**Governance:** normal CLAUDE.md test-driven and domain-driven rules apply. No waiver is assumed; the 4 Oct waiver covered the Discovery/hold round only.

---

## A. Review of the development-review design

The reviewed design is sound and is adopted as the base of this document. Points of agreement, corrections to my first draft, and additions follow.

### A1. Adopted as written
- The **five business questions** (§1) are the purpose test for every field and screen.
- **Principles** (§2), in particular:
  - underlying and option are separate assessments;
  - an unsuitable contract does not invalidate the ticker;
  - no silent fallback to superseded models;
  - preserve point-in-time history;
  - keep Wyckoff phase/event and compression in the primary view;
  - no new waiver.
- **Hypotheses RC1–RC7** (§4), with their verification requirements, and the rule **"do not classify legitimate differences between measurements as defects merely because their numbers differ"**.
- **Meanings of target, time and value** (§5), including:
  - "an anticipated two-session move with an eight-session hold allowance is not inherently contradictory";
  - "positive scenario value and negative EV can coexist";
  - "an alternative's retired authority does not prove its arithmetic is wrong".
- **Quote-age correction** (§7). This matches standing ACK decisions:
  - memory note "forward-looking, not time gates": flag quote age, never gate on it;
  - d1ee309: "quote age disclosed, never a gate".

  The review rightly asks for an inventory of every remaining quote-age effect (RC7), because the history shows quote freshness flipping four times (gate → flag → delay-adjusted gate → disclosure).
- The **narrow decision record** requirements (§8), the **Lab design** (§9), the **ranking and missing-value policy** (§10), the **build sequence S0–S8** (§11), the **regression scenarios** (§12), the **release boundaries** and the **build-complete vs shipped** definitions (§13).

### A2. Corrections to my first draft (accepted from the review)
1. **Not every difference is a conflict.**
   - My draft counted "33 GOs with target mismatch" and "1-5D vs 8-session hold" as conflicts. Several are legitimate different measurements:
     - anticipated level vs structural reference vs volatility-reachable level;
     - time to move vs hold allowance.
   - The defects are the ones where a consumer **silently substitutes** one for another, or a label hides which quantity it shows. For example:
     - monetisability valued at the legacy `target_price` and displayed as the trade's monetisability;
     - "Move Window" showing the legacy `horizon_bucket` with no basis.
   - S1 classifies each mismatch: **LEGITIMATE_DIFFERENT_MEASURE**, **SILENT_SUBSTITUTION** or **CALCULATION_DEFECT**.
2. **Anticipated value is a conditional scenario value, not an expected value.**
   - `anticipated_value_multiple_q50` is the option value *if* the underlying reaches the q50 level at the q50 time. EV3's −0.266 is probability-weighted over target, stop and timeout.
   - Both can be right at once. My draft's "rank by anticipated value alone" ignored probability and downside, so it is withdrawn.
   - Ranking now follows review §10: comparable economics, with evidence quality and downside shown, and adopted only after the conventions are verified.
3. **Labels.** "Value at median time" must not read as "median option outcome". The label becomes:
   > "Option value if the underlying reaches the q50 level at q50 time (×premium)."
4. **The audit view is not "unused".** Some advisory evidence informs the decision without owning the final fact. The audit label becomes "Alternative and supporting models", and each row states its role:
   - SUPPORTING_EVIDENCE
   - ALTERNATIVE_MODEL_NOT_GOVERNING
   - RETIRED_AUTHORITY_MEASURED_ONLY
5. **Figures are verified, not assumed.** My first draft took these from live measurement on 6 Oct; S0 re-measures them from frozen artifacts:
   - 252 MB book JSON and 213 MB CSV (file sizes);
   - 210 s and 300 MB for `/api/run/latest` (timed with curl);
   - 29 minutes for the handoff (log 16:10:16 → 16:39:56);
   - 814 to 1,359 columns (read from the artifacts).

### A3. Additions the review did not cover (from the whole-pipeline audit)
1. **The cause sits upstream of the Lab** (§B). A Lab-only decision record would hide upstream defects; the review's release recommendation says the same: "do not use presentation changes to conceal unresolved upstream defects". So S1 and S2 reach every gate, the contract-selection step and the ranking consumer, not only the Lab.
2. **Recurrence control** (§D): the review fixes this instance but not why such instances keep coming back.
3. **Direction is the working proof.** Direction got a governed owner in September, and its 14 trade-direction fields show 0 UP/DOWN conflicts on the 51 GOs. Value, time and target have no equivalent governance, and that is where the conflicts are. The design gives the same treatment to value, time and target.
4. **Spread thresholds.** The review is right not to change the spread convention silently. The thresholds were calibrated on a particular formula, so a formula change must carry its threshold re-calibration, or keep the policy formula and only label the displayed one.

---

## B. Root cause: a whole-pipeline data-flow problem, not a Lab problem

**Measured on run `20261006_060401`:**

| Stage artifact (write time) | Columns | Size |
|---|---|---|
| discovery behavioural candidates (08:17) | 66 | 41 MB |
| discovery_candidates_cds3 (08:25) | 485 | 28 MB |
| options_intelligence (12:45) | 861 | 39 MB |
| horizon 1_5d / 6_10d / 11_20d (13:05) | 1,207 each | 51 MB total |
| options_intelligence_phantom (13:44) | 1,040 | 41 MB |
| eil_enriched (15:46) | 1,296 | 47 MB |
| execution_v3_5 (15:46) | **1,359** | 48 MB |
| morning_validated_trades (16:10) | 1,186 | 40 MB |
| final_opportunity_book CSV / JSON (16:34–16:35) | 814 | **213 MB / 252 MB** |

In the Morning trades file:
- 21 direction-like columns;
- 10 target columns;
- 12 hold/horizon columns;
- 48 verdict/status columns;
- 67 value/score columns;
- 10 spread variants.

**Example:** NVMI shows five answers to "how long": planned hold 42, EV3 hold 20, `horizon_bucket` 1_5d, layer-2 horizon 5D and anticipated hold 10. Some are legitimately different measures (§A2.1), but nothing tells a consumer which one governs.

**Root causes** (RC numbers follow the review):
- **RC1, confirmed in history:** new owners were added beside old ones and consumers were never moved. For example:
  - monetisability was added "as a second advisory column" (a963e18);
  - "remove EV v2 from priority score" removed only EV v2's weight and left the retired R:R driving the Lab rank (d1ee309).
- **RC2, measured:** every stage carries the whole row forward and adds its own columns. Pending the handoff audit: which handoff mechanisms restrict what travels and which only check presence.
- **RC3, confirmed in code:**
  - `intelligence-lab/intelligence_lab.py:_finalise_lab_priority_ranking` sorts by verdict bucket, then by `_compute_priority_score`;
  - its weights are options verdict 0.22, campaign 0.16, execution 0.12, EIL 0.14, `rr_options` 0.08, options score 0.08, WBS 0.05 and GARCH 0.05;
  - Spearman correlation with anticipated value on the GOs is −0.02.
- **RC4, confirmed in code:** `morning_gate.py:2889` withholds GO only for `DOES_NOT_PAY_AT_ANTICIPATED_TIME`. Six GOs are `NOT_COMPUTED` and one is volatility-only.
- **RC5, open:** many lane-A tickers on 1w or 1mo setups carry `thesis_event_timeframe = 1d` (e.g. RARE, HWM, FISV). S1 traces whether the anticipated value is computed on the setup that qualified the lane.
- **RC6, observed:** before the Morning handoff completed, the Lab showed the Evening book as "0 executable" with no "awaiting Morning validation" label.
- **RC7, to inventory:** quote-age effects on verdict, rank or visibility.

### B2. Handoff mechanics (audit complete, read-only; file:line evidence in the audit notes)

**How data travels.** After the Options Intelligence output, every stage passes the whole row on (`dict(row)`, `{**row}`, `pd.concat(axis=1)` or `merge on ticker`):
- horizon router, orchestrator 1832;
- EV3 overlay, `apply_ev3_authority.py:196`;
- empirical EV, orchestrator 2543;
- Phantom, `phantom_engine.py:201`;
- wall break, `wall_break_scorer.py:474`;
- EIL, runner 1584 and 3622;
- Morning gate, `morning_gate.py:2294`, whose header is the union of all keys (487–501);
- execution gate, `execution_gate.py` 65, 185 and 456;
- finaliser, `morning_handoff_finalizer.py:819`.

The only true schema boundaries are the Options Intelligence output, the EOD candidate literal and the Lab's `FINAL_BOOK_FIELDS`. Each lists 300–850 names, and two of them reopen dynamically: `ev3_*` passes through, and `source_payload_json` re-embeds the row.

**Contracts check; they do not restrict.**
- `contracts/handoff_contract.py` only reports missing fields (`validate_required` 431–444) and adds about 8 truth-packet columns to every row (584–586).
- CDS-3 restricts rows, not columns.
- `thin_package` means "built in memory by reference", not fewer fields.
- `DISC_MERGE_COLS` back-fills empty values.
- `TRADE_LANE_FIELDS` names what to carry.

**Decisions append; they do not replace.**
- Both sides' direction geometry stays on the row, and the losing side is not marked.
- NOT_SCOPED rows are dropped only inside the horizon router.
- Alternative contracts are marked but ride to the Lab inside `source_payload_json`.
- The Morning contract swap overwrites in place:
  - strike, expiry and DTE are written under 3 names each;
  - `live_contract_*` stays beside `contract_*`;
  - one verdict is written under 3 names (`morning_gate_verdict`, `morning_validation_result`, `live_validation_state`).
- The execution gate's `final_action` is appended, and earlier verdicts stay unmarked.

**Consumers re-resolve facts through fallback chains with inconsistent precedence.**
- **Target:** the Lab publishes `target_price` with the wall price first (`lab_control.py:3886`) and `structural_target` with the reverse order (3889). The same row can therefore show two targets. Further chains: `selected_contract_economics.py:532/893` (valuation), `morning_gate.py:2065`, `opportunity_tier.py:119`, and `eod_candidate_engine.py:937` (defaults to 0.0).
- **Hold/horizon:** `horizon_bucket` is the contract-expiry bucket, not the thesis hold (orchestrator 1834), yet the Lab's `time_horizon` reads it first (3996). `_morning_hold_sessions` still falls back to `l2_hold_days` (`morning_gate.py:1996`).
- **Value:** `ev_predicted = first(ev3_ev_conservative_return, ev_predicted)` (`lab_control.py:3774`).
- **Invalidation:** `morning_gate.py:1702`, `execution_gate.py:126/131`, `lab_control._book_invalidation`.
- **Spread:** declared owner `long_option_policy.quote_spread_fraction`, recomputed in at least 8 places, in two units. `spread_pct` is a fraction in Options Intelligence (8014) and a percent in the Morning gate (889, 2987–3002).

**Why the book is 252 MB.**
- `"source_payload_json": _json_safe(sig)` (`lab_control.py:4074`) embeds the whole Morning row (about 1,186 fields) in every book row, and that field is itself on the allow-list (819).
- The JSON is written unfiltered (5065).

**Defects found in passing.** Logged; none fixed; each needs root-cause approval.

| ID | Defect | Evidence | Rule broken |
|---|---|---|---|
| H1 | The execution gate CSV header is taken from the first row only, with `extrasaction="ignore"`: any column missing from row 1 is silently dropped from `execution_gated_*.csv`. The in-memory Lab handoff is not affected | `execution_gate.py:537–540` | R7 reproducible inputs |
| H2 | The horizon router defaults a missing direction to `"CALL"` | orchestrator 1749–1753 | R1 missing is never neutral |
| H3 | `spread_pct` holds a fraction in one stage and a percent in another under the same name | OI 8014 vs `morning_gate.py:889` | R3 units in names |
| H4 | The Lab's two target fields use opposite precedence | `lab_control.py:3886` vs 3889 | R2 one owner |
| H5 | Bid and ask are taken from independent fallback chains, so a live bid can pair with an older ask | `execution_gate.py:150–151`, `lab_control.py:911` | R6 labels say what was measured |
| H6 | Missing target defaults to 0.0 in the EOD candidate engine | `eod_candidate_engine.py:937` | R1 |

The audit could not verify: where Phantom is called; whether the orchestrator 1852–1878 patch is a silent no-op; whether the horizon router collides on tickers with both CALL and PUT rows; runway field units. These are S1 checks.

**Answer to ACK's question ("the Lab or the whole pipeline?"):** it is the **whole pipeline's data flow and ownership**. The Lab is where the conflicts become visible, because it receives every column and chooses among them with fallback chains: `getTimeHorizon` tries six prefixed `horizon_bucket` fields before reaching anything current.

---

## C. Audit status

| Audit | Status | Use in this design |
|---|---|---|
| Measured data flow (columns, sizes, duplicates, direction conflicts) | **Complete** (§B) | Root cause, S0 baseline |
| History: why issues recur | **Complete** (§D) | Recurrence controls |
| Handoff mechanics: carry mode per stage; contracts that restrict vs only check; fate of alternatives after each decision | **Complete** (§B2) | The decision record must be emitted at each decision owner, not only at the Lab; defects H1–H6 enter S1 |
| Fact-ownership map: writers and decision-readers for value, time, target, invalidation, verdict and spread; superseded sources still deciding | **Pending** | Will become the S1 consumer list |

This document is updated in place when the two pending audits report.

---

## D. Why issues keep recurring (history audit) and the controls that stop it

**Recurring defect classes since May 2026** (commit subjects; 198 of 266 commits fell in September):

| Class | How it recurs |
|---|---|
| Hold / horizon | Redefined about 5 times in 3 weeks: per-horizon band → governed horizon → fixed 20 → Discovery-owned → reconciled → EV3 grid → no fixed 20 → horizon-true |
| Target / invalidation | Retired 3R targets came back through an alias (fd35594); "target reconciliation" is still open today |
| Value / EV | Empirical EV extended 5 times while on the retire list; EV3 extended back into valuation (28 Sep) after quarantine; today 5 value answers |
| Freshness | Gate → flag → delay-adjusted gate → disclosure |
| Lab display | 52 commits; `contracts/lab_control.py` alone has 41 commits and 146 references to superseded fields |

**What the governing documents already prescribed, on 16 Sep:**
- one owner per fact (Invariant A, R2);
- a retire list (`ev_engine_v2`, `empirical_option_ev`, the monetisation policies, the horizon router, 3R targets, Lab priority recomputation);
- packages replaced by references.

Retirement was tied to the strangler migration, which was replaced by "enhance in place" the next day (CLAUDE.md rule 4, 17 Sep). That change gave no one the job of retiring legacy code:
- 12 of the 14 files checked from the retire list still exist;
- quarantine was not enforced;
- `avshunter/c0_run/thin_package` covers the input side only (P5 not done);
- no output-side decision record was ever built.

**Process root causes:**
1. Fixes are added beside old logic; consumers are not moved.
2. The method changed mid-flight with no replacement retirement path, and the documents were not reconciled. The knowledge README still says "migrate by strangler", and decision IDs collide.
3. Core definitions (hold, target, value, freshness) changed repeatedly, and each change broke a silent consumer. The EV3 hold-bucket outage went unnoticed for 9 days.
4. Acceptance relied on synthetic tests against the spec, not on consumers or outcomes. The EV3 outage passed green suites, and a `passed` filter hid failures.
5. Wide-row handoff with no narrow contract, so a new owner is just one more column.

**Controls added to this design** (recurrence is part of "done"):
- **R-1. Superseded-field registry.** A versioned registry maps each superseded field to its owner and its allowed role (AUDIT / MEASUREMENT_ONLY). A test fails if any decision, gate, rank or primary-view reader references a superseded field. Retiring an owner and moving its consumers happen in the **same change**.
- **R-2. Glossary of core definitions.** One versioned glossary covers side, setup, invalidation, the three target types, the four clocks, the four value types and spread, each with units in the name. Changing a definition requires a listed, grep-verified consumer migration.
- **R-3. Golden replay acceptance.** A frozen stored run is replayed to the Lab payload with an approved expected-diff manifest. This is the map's planned §4 item 3, never built. The outcome scorer is used where the sample allows.
- **R-4. Document hygiene, once.** Mark the superseded sections (strangler references, the old retire list) and restate a single KEEP / CHANGE / QUARANTINE / RETIRE list with owners and dates. Use one decision-ID namespace and **one active fix programme at a time**.
- **R-5. Small, frequent commits.** d1ee309 bundled 530 files from a week of work, which makes review and bisection impractical.

---

## E. Design

### E1. Ownership

The review's §6 table is adopted. Concrete field mappings are confirmed in S1, using the ownership-map audit, before any code changes.

| Question | Authoritative content | Notes from this audit |
|---|---|---|
| Ticker direction | Governed Discovery assessment, preserved through Vanguard | Already governed; 0 conflicts. This is the model for the rest |
| Setup | Lane/setup, Wyckoff phase/event, compression, supporting evidence | Lane fields from `trade_lane`; RC5 must confirm the valued setup is the lane setup |
| Invalidation | Sourced, side-correct, with basis and time | 6 Evening candidates lack it (recurring handoff FAIL since 1 Oct) |
| Anticipated move | Selected-setup level and path, version, evidence status | Keep anticipated, structural and reachable levels separately labelled |
| Time | Anticipated time (q50/q80) and hold allowance, separately labelled | `horizon_bucket` / layer-2 / macro horizons: audit only; 72 rows missing a planned hold |
| Contract | Exact symbol, side, strike, expiry | Morning swap identity (fix E) |
| Cost | Reference bid/ask, source, quote time, declared entry assumption | Spread convention per review decision 5 |
| Scenario economics | Anticipated contract value, costs, IV/time assumptions, entry-price sensitivity, maximum entry premium for a stated objective | New display content (review §7.6–7.7); needs the formula owner confirmed (review decision 1) |
| Decision | Underlying assessment, option recommendation, human-review reasons | One verdict per assessment, with reasons |
| Trust | Cutoffs, availability, calculation status, provenance | Quote age disclosed, never a gate |

### E2. Decision record, the narrow handoff
`trade_decision_record_v1`, exactly per review §8:
- no whole-row JSON;
- no fallback chains;
- missing fields stated with reasons;
- versioned and appended;
- the frozen Evening assessment is never altered.

**Scope from the handoff audit (§B2).** One record at the end is not enough, because every gate between Discovery and the Lab also reads re-resolved, multi-name facts. Each decision owner publishes its decided facts under one canonical name and marks the alternatives (role: ALTERNATIVE / SUPERSEDED) instead of carrying them unmarked. The owners are:
- direction governance;
- Discovery lane;
- contract selection;
- Morning gate;
- execution gate.

Downstream consumers read the canonical name with no fallback chain. This is phased in per owner in S1–S2, test-first. `trade_decision_record_v1` is the final, narrow assembly of those canonical facts.

The Lab primary view, the Interpreter and the journal read the record. The full-width artifacts stay on disk for audit, replay and C12, unchanged until the separate S6 compatibility task.

### E3. Lab
Review §9 is adopted:
- **Primary card**, which keeps the structural evidence.
- **Concise grid.**
- **Lazy per-ticker audit** with model, version, measured quantity, input target and timeframe, status and role.
- **Prominent run, session and validation time.**
- **Evening-only run labelled "awaiting Morning validation".**

### E4. Ranking and missing value
Review §10 is adopted:
- **Ranking:** comparable economics within decision groups, with evidence quality and downside alongside value. It is adopted only after the conventions are verified. The server owns one ranking shared by the grid and the summary, with deterministic tie-breaks.
- **Missing option value:** `NOT_COMPUTED` and volatility-only rows get an **option-review state (FLAG)** with a precise reason. The underlying opportunity is not downgraded or hidden.

---

## F. Build sequence

Review §11 S0–S8 is adopted. This audit adds the following to the scope:

| Stage | Added scope |
|---|---|
| S0 | Freeze `20261006_060401` artifacts and record the measurement commands (§A2.5) |
| S1 | Include **every** decision consumer from the ownership audit (Morning gate, execution gate, contract selection and repair, rank, Interpreter, journal, C12), not only the Lab. Classify each mismatch (§A2.1). Trace RC5. Inventory RC7. Build the superseded-field registry (R-1) and glossary (R-2) |
| S2 | Fix only defects classed as SILENT_SUBSTITUTION or CALCULATION_DEFECT, one at a time, test-first. Remove quote-age-only effects |
| S3–S5 | As the review |
| S6 | Also finish the thin-package P5 (input side) |
| S7 | Golden replay acceptance (R-3) plus the review's population, formula, unit, cost and direction reconciliations |
| S8 | Human-run live proving. ACK runs the pipelines |

The regression scenarios are review §12 as written, plus:
- **"A decision or rank reader referencing a superseded field fails the build"** (R-1);
- **"A 1w/1mo lane setup is valued on that setup, or the gap is stated"** (RC5).

## G. Decisions for ACK and the development review

The review's §14 decisions 1–7 apply as written. Added:

8. **Recurrence controls R-1 to R-5:** adopt as part of the definition of done?
9. **One active fix programme at a time:** this programme (source of truth and decision handoff) becomes the only active one until S8, with the other open items parked on the register. Approve?
10. **Order:** repair ownership and calculation lineage first (S0–S2), then the decision record and Lab (S3–S5), as the review recommends. Confirm.

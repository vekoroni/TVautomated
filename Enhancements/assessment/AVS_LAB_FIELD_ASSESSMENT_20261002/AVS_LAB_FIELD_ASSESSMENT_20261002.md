# Intelligence Lab field assessment (2 Oct 2026)

**ACK's request:** "an assessment of all the fields in the intelligence lab … display data relevant to the trade that the trader can use to make informed decision. there seems to be a lot of redundant data. validate".

**Basis:** the final opportunity book of run `20261001_211641` (1,554 rows, 759 columns, excluding `source_payload_json`), the Lab UI (`intelligence-lab/static/*`) and the Lab server (`intelligence-lab/intelligence_lab.py`).

**Data files in this folder:**
- `lab_field_profile.csv`: one row per field, giving populated %, distinct values, top value, shown in UI, read by the server, duplicate of, and family.
- `trade_card_candidate_fields.csv`: the proposed trade card fields checked against the book.

## 1. Verdict: the redundancy is real, and the trade decision is buried

| What | Fields | Share |
|---|---|---|
| Columns in the book | 759 | 100% |
| Empty on every row | 165 | 22% |
| One constant value on every populated row (authority flags, versions, fixed labels) | 167 | 22% |
| Exact copy of another populated column | 35 | 5% |
| **Carry no row-specific information (total)** | **367** | **48%** |
| Populated, varying, distinct | ~392 | 52% |
| Neither shown in the UI nor read by the Lab server | 402 | 53% |

Even the ~392 informative fields are far more than a trader can use. Most of them are intermediate engine outputs: Wyckoff internals (30), DOI (34), EV3 (29), catalyst plumbing (27), monetisability (26), WBS components (15) and so on.

**Exact duplicates** (same values on all 1,554 rows):
- **Direction ×5:** `canonical_direction`, `discovery_direction_preliminary`, `governed_direction`, `final_direction`, `direction`.
- **Contract symbol ×5:** `contract_symbol`, `selected_contract_symbol`, `doi_governed_contract_symbol`, `contract_value_score_choice_symbol`, `monetisability_contract_symbol`.
- **Verdict ×4:** `lab_verdict`, `lab_status`, `execution_category`, `action_category`.
- **Invalidation ×3:** `forecast_invalidation_spot`, `invalidation_price`, `invalidation_spot`.
- **Mid premium ×3:** `premium_mid`, `ca_mid_per_share`, `contract_mid`.
- **Reference price ×3:** `underlying_price`, `signal_price`, `scanner_price`.
- **Horizon label ×3:** `hold_window`, `time_horizon`, `hold_period`.
- **Others:** rank ×2, DTE state ×2, ranking score ×2, spread % ×2, and further pairs (35 copies across 23 groups).

**Families that are entirely empty or constant in this book:**
- **Entirely empty:** `payoff_*` (7), `sb_*` (9), `validation_*` (9), `current_*` (8), `ms_*` (8).
- **Constant:** `maturation_*` (8 of 8). Most `usmi_*` fields are constant (14 of 17) and so are half the `macro_*` fields (11 of 24, plus 13 empty).

## 2. Gaps: fields the trader needs that the Lab does not carry or show

| Gap | Effect | Cause |
|---|---|---|
| `target_reachable`, `target_reach_ratio`, `rr_options_reachable`, `rr_underlying_reachable` (D01/D13, 2 Oct) | The scored R:R and the reachable target are invisible in the Lab | Not in `FINAL_BOOK_FIELDS` |
| `governance__verdict` (open-contract check) | A held position's governance verdict is not shown | Not in `FINAL_BOOK_FIELDS` |
| `trigger_go_eligible` | Whether the trigger qualifies for GO is not in the book | Not in `FINAL_BOOK_FIELDS` |
| Phase/Event categorisation (`thesis_category`, `thesis_phase`, `thesis_event`, `thesis_event_state`, `thesis_structure_alignment`, D10) | The trade's structural category is not visible | In the schema since 2 Oct, but not in the UI yet; the 1 Oct book predates it |
| Contract bid / ask / spread, call wall / put wall, bar data date | Execution-quality and level facts are hidden | In the book but not shown in the UI |
| `validation_transition` (0% populated), `macro_sector_alignment` (0%) | Morning validation and macro sector context are empty in the book | Morning not yet run for this book; `macro_sector_alignment` was the D03 symptom (fixed 2 Oct) |
| Behavioural candidate duration (time to activation and outcome) | No "how long" estimate per trade | The candidate lane (`options_candidate_expressions`) is separate from the book |

## 3. Proposed trader view: one trade card, eight questions, ~45 fields

Each field below already exists in the pipeline unless marked *new to book*.

| Question | Fields |
|---|---|
| **1. What, and which side?** | ticker, direction (one field), `thesis_category` ("Phase E · SOW→LPSY (activated, 1d)"), `thesis_structure_alignment`, tier |
| **2. Why now?** | `trigger_primary` (with the D04 IV flag), `trigger_quality`, `trigger_go_eligible` *(new to book)*, Morning `validation_transition`, `remaining_runway_state` |
| **3. Where am I wrong, where am I right?** | `invalidation_price`, `target_price` + `target_price_source`, `target_reachable` *(new)*, `target_reach_ratio` *(new)*, `rr_options_reachable` and `rr_underlying_reachable` *(new)* |
| **4. How long?** | `planned_hold_sessions`, contract DTE and expiry, catalyst date and whether it falls inside DTE, candidate duration q50/q80 *(new: join from the candidate lane)* |
| **5. Which contract, at what cost?** | symbol, strike, bid, ask, spread %, delta, IV, OI, volume, breakeven, `ivp_label`, quote time and freshness |
| **6. What is the context?** (advisory) | sector / sector ETF, `usmi_sector_alignment`, macro sector alignment, gamma flip and walls *with their sides* (Interpreter `level_relations`) |
| **7. What is the decision state?** | `lab_verdict`, `final_action`, `conflict_state`, `evening_thesis_bucket`, `governance__verdict` *(new to book)* |
| **8. Can I trust the data?** | quote freshness and time, bar data as-of, intraday/data status flags |

## 4. Recommendation (no deletion of functionality)
1. **Show the trade card by default.** These are the ~45 fields above, one field per fact. Pick one owner for each duplicate group: `direction`, `contract_symbol`, `lab_verdict`, `invalidation_price`, `contract_mid`, `signal_price`, `planned_hold_sessions`.
2. **Evidence drawer:** the remaining informative fields (Wyckoff internals, DOI, EV3, WBS, catalyst detail, physics), grouped by family and collapsed.
3. **Audit tier, hidden by default:** constant authority flags, versions and lineage IDs. Keep them in the book or a sidecar for traceability, per "repair, don't delete".
4. **Stop publishing the 165 always-empty columns** in the trader view, and list them in an audit note. Each one is either a dead producer or a missing join; those should be traced rather than displayed empty.
5. **Add today's decision fields to `FINAL_BOOK_FIELDS`:** the reachable target and R:Rs, governance verdict and GO eligibility. Without this, the D01/D13 fixes are invisible to the trader.

**Next step needs ACK's approval:** the trade card design (point 1) and the book-schema additions (point 5). Points 2–4 follow from point 1.

## Build receipt: trade card and schema additions (2 Oct 2026, ACK "yes")

**ACK's objective:** "for the trader to view the trade card, make an informed decision then run the interpreter instead of viewing the output folder".

**Changes** (uncommitted):
- **`contracts/lab_control.py`:** `FINAL_BOOK_FIELDS` and the book row pass through `target_reachable`, `target_reachable_state`, `target_reach_ratio`, `rr_options_reachable`, `rr_underlying_reachable`, `rr_basis`, `target_3r_scenario`, `governance__open_contract`, `governance__verdict`, `governance__reason` and `trigger_go_eligible`.
- **New `intelligence-lab/static/trade-card.js`:**
  - `renderTradeCard(s)` gives one field per fact, answering eight questions:
    1. What and which side (Phase · Event)
    2. Why now (trigger with the D04 IV flag; Morning validation and runway)
    3. Where wrong / where right (invalidation, reachable target, reach ratio, structural target, reachable R:Rs)
    4. How long
    5. Which contract at what cost (spread computed from bid/ask)
    6. Context (sector, Money Index, gamma flip and walls with side and reading)
    7. Decision state (verdict, action, conflict, open-position governance)
    8. Can I trust the data
  - A missing value is shown as such ("not recorded", "none (no target is invented)"), never as a blank.
  - `tradeCardRunInterpreter` and `tradeCardSavedReports` select the ticker and drive the existing desk flow: preview, paid-request confirmation, run-bound report shown in the Lab panel.
- **`intelligence-lab/static/index.html`:** a Trade Card tab, the default pane when a ticker opens (`openModal` now activates `mp-card`), the script include, and the card styles.

**Tests:**
- `tests/test_avs_lab_trade_card.py` (5): schema, book pass-through, default tab, an eight-question render via node (XLU fixture), and default activation.
- Four were seen red; the activation test was written after the browser check found Overview still activating.
- All 29 Lab test files and the evening-thesis tests pass.

**Live check** (Lab on port 5002, run `20261001_211641`, XLU):
- The card renders as the default view. The 1 Oct book predates the fixes, so the reachable fields and the Phase/Event category show "not recorded" / "not categorised".
- Levels read correctly: gamma flip 37.85, spot above; call wall 42, overhead resistance; put wall 25, support below.
- "View saved reports" runs read-only, with no model call.
- The desk preview for XLU (no paid call) built a 5,018-character digest with a conservative cost bound of $1.07.

**Operational note:** the running Lab server predates today's Python changes. Restart the Lab so the new book fields and the Interpreter's governed facts are served.

## Build receipt: evidence drawer and audit tier (2 Oct 2026, ACK "build the evidence drawer and audit tier")

**Changes** (uncommitted):
- **`intelligence-lab/static/trade-card.js`:**
  - `tcProfile(rows)` profiles the run's book once in the browser (single pass, cached per run, started in the background when the run loads). It classes each field as:
    - empty → listed for tracing;
    - duplicate (identical to an earlier field on every row) → audit tier, marked "same as X";
    - lineage (authority, version, policy, ids, hashes) → audit tier;
    - constant → audit tier;
    - otherwise → evidence drawer, unless it is already on the card.
  - `renderEvidenceTiers` renders a collapsed evidence drawer grouped into 21 named families (Wyckoff, Vanguard, DOI, EV3, catalyst, Morning, Options layer, market physics, market profile, timing/exits and so on), and a hidden audit tier (lineage, constant, duplicates, always-empty names).
  - Fix found in testing: "NONE" is a real state in this pipeline, so it is no longer treated as missing; only empty, NaN and null are.
- **`intelligence-lab/static/index.html`:** passes the run profile to the card, pre-profiles on run load, and adds the tier styles.

**Tests:** `tests/test_avs_lab_trade_card.py` now has 7 tests, including field tiering via node and the profile hand-off; seen red first. All Lab test files pass.

**Live check** (run `20261001_211641`, 1,554 rows):
- Evidence drawer: 405 fields in 21 families, none left in "Other".
- Audit tier: 57 lineage, 101 constant, 135 duplicate, 78 always empty.
- Profiling takes 1.85 s once per run, in the background. Rendering the card takes 4 ms; the existing modal tabs take about 0.6 s.

**Note:** these counts come from the Lab's signal rows (`ALL_SIGS`), not the book CSV, so they differ from the CSV profile in section 1.

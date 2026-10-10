# S1 receipt: define and trace (6 Oct 2026, ACK "start S0 and S1")

**Scope:** read-only. No production code changed. Reference run `20261006_060401` (frozen, S0).

## Deliverables
| Item | File | State |
|---|---|---|
| Glossary + field-role registry v0 | `GLOSSARY_AND_FIELD_ROLES_v0.md` | Draft for ACK sign-off |
| Quote-age inventory (RC7 / E13) | `S1_QUOTE_AGE_INVENTORY.md` | Complete; A1 verified in run data (17 rows) |
| Setup lineage (RC5 / E06) and open checks (E31) | `S1_SETUP_LINEAGE_AND_OPEN_CHECKS.md` | Complete; selection rule verified in code |
| Mismatch classification, all 51 GOs | `classify_mismatches.py` → `mismatch_classification_20261006_060401.csv` | Complete |

## Mismatch classification (51 GO / GO_LIMIT rows)
| Dimension | Result | Class |
|---|---|---|
| Setup lineage | 32 valued on a 1d event unrelated to the 1w/1mo lane setup; 19 consistent | **SILENT_SUBSTITUTION** |
| Thesis level | 4 levels already passed by price (NET, CYTK, BLDR, CENX); 1 missing (BIRK); 46 valid | **CALCULATION_DEFECT** (stale-event selection) |
| Target | 35 range-extreme ≠ anticipated level; 12 agree; 4 owner missing | Two **legitimate measures**, with a **substitution** in strike selection and monetisability |
| Value | 33 "PAYS" vs "NOT_MONETISABLE"; 11 no conflict; 7 owner missing | **Legitimate different measures**, but monetisability is **mislabelled as a verdict** and computed at the range extreme |
| EV3 | 36 rejected (no value); 15 valued | Legitimate different measure (supporting after rewiring, E09 b) |
| Time | **All 51 GOs show "1_5d" as the move window**, while planned holds run 6–154 sessions | **MISLABELLED.** `time_horizon` is the contract-expiry bucket, displayed as "Move Window" |

**Conclusion.** The defects concentrate in three places:
1. **Which setup is valued** (lineage and stale events). This is the root of the 7 unvalued GOs.
2. **Which level the contract is chosen and checked against** (range extreme vs anticipated level).
3. **Labels** (move window, monetisability as verdict, "FRESH", spread `_pct`, `dte_buffer_sessions`).

Most numeric "conflicts" on the card are different measures that were never labelled or given roles. That is what the glossary and registry fix.

## S2 candidate list (each needs ACK root-cause and design approval; test-first, one at a time)
Ordered by business impact:

| # | Change | Evidence | Decision basis |
|---|---|---|---|
| 1 | **Value the lane-setting setup** (or a parent-linked event); retire passed levels; replace the alphabetical tie-break | RC5: 32/51 GO; root of the 7 unvalued GOs | New: needs approval |
| 2 | **E12:** NOT_COMPUTED or volatility-only → option-review FLAG | 7 GOs | **Approved** |
| 3 | **Choose strikes and check value against the same level** (anticipated level); rename the range extreme `prior_range_extreme` (SUPPORTING) | Link 1; 35/51 | New: needs approval |
| 4 | **A1:** keep an aged underlying price, disclose its age, value with it | 17 rows blocked today | Standing rule (quote age disclose-only) |
| 5 | **H1:** execution-gate CSV writes every column | 71 columns lost | Reproducibility (R7) |
| 6 | **Morning hold fallback** to retired 5/10/20 holds and the {5,10,20} check | Link 3 | Standing decision (fixed hold retired) |
| 7 | **Execution-gate GEX warnings** downgrade BUY_NOW → BUY_SMALL | Link 4 | CLAUDE.md rule 6 |
| 8 | **E15:** spread as a fraction with the unit in its name; thresholds to config; remove the EIL 30% check | H3/H7/H10 | **Approved** |
| 9 | Labels: move window, monetisability, "FRESH", `REJECT_STALE_QUOTE`, `dte_buffer_sessions`, `dte=30` default, 0.0-for-missing runway | S1 | R6 |
| 10 | Interpreter stale-bundle TTL (A2/A3); EV3 age effects (A4/A5) | S1 quote-age inventory | Standing rule |
| 11 | Phantom writes only `phantom_*`; retire dead functions and patches | S1 open checks | Rule 5 |

Then S3–S5 (decision record, rank, Lab) as planned. **E09 b** (EV3 rewiring) is its own design item after #1 and #3, because it must use the same setup and level.

## Waiting on ACK before S2
1. **Sign-off:** glossary and field-role registry v0.
2. **Approve S2 item #1** (the lineage fix) as the first change. Alternatively, start with #2 (E12, already approved) or #5 (H1, small) while #1 is designed.
3. **E11 rank objective.** Options for when S4 builds it:
   - **(a) Evidence first:** rank by the lane's tested hit rate (holdout), then by scenario value.
   - **(b) Value first:** rank by scenario value; show hit rate and downside next to it.
   - **(c) Probability-weighted:** rank by EV3 once it is rewired and calibrated (E09 b), which overlaps (b) later.

   **Recommendation:** (a) now, because hit rate is the only figure validated on a holdout; move to (c) when EV3 is calibrated.
4. **Out-of-scope staleness rules (S1 §E):** keep or change the 2-session trigger-age gate (a literal), and the macro-age 0.85× haircut (a possible rule-6 conflict).

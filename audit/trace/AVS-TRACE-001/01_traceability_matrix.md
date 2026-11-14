# AVS-TRACE-001 · 01 · Traceability matrix: summary

The matrix is `01_traceability_matrix.csv` (944 rows, 19 columns). Every source record and the trace row it maps to is in `evidence\trace_sources.csv` (2,757 lines). The matrix is rebuilt by `evidence\build_matrix.py`; counts below are from `evidence\matrix_summary.json`.

## 1. Coverage (acceptance T1)

| Source | Records | Mapped to a trace row |
|---|---|---|
| `lessons\fix_register.csv` | 127 rows | 127 |
| `lessons\fix_inbox\*.md`, 18 Oct to 13 Nov (96 files, never triaged) | 855 candidates | 855 |
| Design, requirement, receipt and decision documents (114 files) | 1,775 ID records | 1,775 |

The 40 files in `fix_inbox\processed\` (14 to 17 Oct) were merged into the register on 17 Oct (`change_log.md:113`), so they are covered through the 127 register rows and were not re-extracted.

## 2. How the rows were built

| Row family | Rows | What it is | How the status was set |
|---|---|---|---|
| `TR-001` to `TR-041` | 41 | The headline items: the 13 Nov flaws and fixes, the unmerged branches, and the register items that recur most in the inbox. Duplicates across ID schemes are merged here. | **Verified in this review** against code, git, config and run artefacts |
| `TR-E*` | 15 | ETF package items not already covered by a headline row | Verified (see `06_ETF_fix_package_for_Codex.md`) |
| `TR-FL-*` | 14 | Lab-first fix list items A2 to A11 and C1 to C5 | Proposed; may be covered by commit `da9a922`, which does not list what it closes |
| `TR-R*` | 61 | Remaining register rows, known duplicates merged | Register closure evidence, checked against git and against later inbox reports |
| `TR-I-*` | 24 | Inbox candidates with no register row and no headline match, **grouped by lane and topic** | Proposed. Each candidate still needs its own triage |
| `TR-D*` | 689 | One row per ID defined in a document (REQ, ALG, WP, F, D, DEC, UAT-D, DISC-F, M, DOI, CDS, config approvals and so on) | **The document's own claim, not re-verified.** `status_evidence` starts `DOCUMENT_CLAIM` |
| `TR-G*` | 100 | Supporting records grouped by document (test steps, track results, premise notes, receipts, rules) | Not assessed item by item |

Two limits to state plainly:

- **689 document rows carry the document's claim, not my verification.** Checking each against code and runs was not feasible in one pass. Where an independent test (AVS-TD-001) contradicts a claim sheet, the row follows the test and says so.
- **Inbox candidates are attached, not individually adjudicated.** Of the 855, 564 attach to a headline, fix-list or register row (by the row's ID, by the reader's register match, or by keyword); 145 macro candidates sit in `TR-039`; 146 sit in 24 lane-and-topic groups. The register match is a judgement and some matches are loose. 402 candidates have no register row at all.

## 3. Counts by status

"Merged" means on the checked-out line `laneb/lab-first-handoff`. Nothing has reached `master` since 6 Sep 2026.

| Status | All rows | Verified rows (TR-0xx, TR-E, TR-FL, TR-R) | Document claims (TR-D) |
|---|---|---|---|
| **CLOSED** (code and run evidence) | **0** | 0 | 0 |
| CLOSED_OFFLINE (code and tests, no run) | 35 | 4 | 31 |
| MERGED (code on the line, no test or run cited) | 7 | 7 | 0 |
| BUILT_UNMERGED | 11 | 11 | 0 |
| APPROVED (decided or required, not built) | 216 | 7 | 209 |
| DECISION_PENDING | 23 | 7 | 16 |
| PROPOSED | 523 | 67 + 24 inbox groups | 432 |
| NOT_FOUND (claimed, evidence not in the repo) | 128 | 28 | 100 groups |
| REJECTED | 1 | 0 | 1 |

- **No item is CLOSED under the two-level rule.** 130 document rows cite a run ID somewhere; I did not re-verify them, so none is counted closed.
- 33 rows are marked `CLAIM_NOT_SUPPORTED`: a document or the register says built, closed or passed, and later evidence says otherwise.
- By monetisation impact: 441 HIGH, 199 MEDIUM, 171 LOW, 133 NONE. Of the HIGH rows, 424 are open in some form.

## 4. The 13 Nov flaws and fixes (acceptance T4)

| 13 Nov item | Trace row | Status | One line |
|---|---|---|---|
| Flaw 1: thesis clock too slow for 1 to 20 sessions | TR-001 | APPROVED | 1,499 of 2,132 rows outside the window; flag decided, pipeline flag not built |
| Flaw 2: runway is a penalty; selection in SHADOW | TR-002, TR-003 | APPROVED; DECISION_PENDING | Contract from the monetisation clock decided 12 Nov; nothing built; SHADOW to ACTIVE undecided |
| Flaw 3: illiquid contracts kept; tiers only in Lane B | TR-004 | PROPOSED | 1,697 of 2,132 saved quotes are tier C; six different spread limits in force |
| Flaw 4: stale quotes | TR-005, TR-006 | APPROVED; BUILT_UNMERGED | 900 s delay against a 900 s limit; Morning guard built, uncommitted, on no branch |
| Flaw 5a: GARCH D1 | TR-008 | BUILT_UNMERGED | `fff3a3e`, in the working tree, not run. No longer "not shipped" |
| Flaw 5b: monetisation not published | TR-009 | BUILT_UNMERGED | `b709669`, not in the working tree, not run |
| Flaw 5c: no outcome ledger | TR-010 | APPROVED | Brief issued 13 Nov; not built |
| Fix 1: Lane B on the Lab hand-off | TR-012 | CLOSED_OFFLINE | Built and tested; live flow still LEGACY |
| Fix 2: Morning 09:35 to 09:45 with a late guard | TR-006 | BUILT_UNMERGED | As flaw 4 |
| Fix 3: Tastytrade re-quote at entry | TR-007 | DECISION_PENDING | **NEW**: no earlier ID |
| Fix 4: GARCH D1 | TR-008 | BUILT_UNMERGED | As flaw 5a |
| Fix 5: contract covers q80, tiers, rank by return per premium dollar | TR-002, TR-004, TR-003 | as above | "Covers q80" is superseded by ACK's 12 Nov decision |
| Fix 6: two or three alternatives | TR-011 | PROPOSED | Projection fields added, uncommitted; none published |
| Fix 7: publish monetisation | TR-009 | BUILT_UNMERGED | As flaw 5b |
| Fix 8: window flag in the Lab | TR-001 | APPROVED | As flaw 1 |
| Fix 9: outcome ledger for every card | TR-010 | APPROVED | As flaw 5c |
| Fix 10: retire old-layout scripts and the X17 test | TR-013 | DECISION_PENDING | X17 test fails by design since 12 Nov |

Every flaw and fix maps to a trace row. Only fix 3 is new; the rest had been raised before, some many times: GARCH D1 under 12 IDs since 10 Sep, the outcome ledger under more than 20.

## 5. ID collisions to be aware of

The same short ID means different things in different documents, so the matrix joins on ID plus scheme, never on ID alone.

| ID | Meanings |
|---|---|
| D1 | Desk-gate defect (GARCH horizon); register row of 14 Oct (monetisability); fix-list decision (trading window); "GARCH D1"; INT D1; ILA-003 D1; a CLAUDE.md decision |
| D2 | Register (premium ceiling and run time); fix list (premium-cap lane) |
| A1 | INT register; config `share_price_label`; Lab-first fix list |
| B1 to B4 | INT register; Lane B Fix B; MON-004 branches |
| W1 to W7 / W0 to W4 | Register weekend items; tradeability work items |
| R1 to R12 | CLAUDE.md design rules; QA changes; DISC rules; lessons-register requirements |
| G1 to G4 | CLAUDE.md gates; options-valuation gaps G1 to G9 |
| L1 to L8 | Lessons register of 12 Oct; lessons of 13 Oct |
| C1 to C6 | Run conditions; UAT steps; thesis closers; fix-list macro items |

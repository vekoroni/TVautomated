# Intelligence Lab Audit — Executive Summary

Static analysis only, `2026-08-25`. Reference run `20260824_220616`. Full evidence: `functionality_audit.md` (Phase 1), `attribute_inventory.json` (Phase 2, 232 records), `gap_and_defect_report.md` (Phase 3).

## Field-count reconciliation
`contracts/lab_control.py:45` `FINAL_BOOK_FIELDS` = **232 fields**, no duplicates. The reference run's `final_opportunity_book_20260824_220616.json` (`rows[0]`) has **232 keys**, an exact 1:1 match to `FINAL_BOOK_FIELDS` — **no delta**. `lab_schema_version` on every one of the 1063 reference rows = `lab_signal_book_v2`, matching the governed schema name. `attribute_inventory.json` carries 496 records: the first 232, in contract order, are one-per-contract-field (`in_final_book_contract: true`); a further 264 records (`in_final_book_contract: false`) cover every legacy/pre-governance field name (`sb_*`, `mv__*`, `wbs__*`, `eil__*`, `doss__*`, `eod__*`, `exe__*`, `vg__*`, `opt__*`, `garch__l3_*`, `qomega_*`, `tce_*`, and ~92 standalone legacy names) that the templates/JS still read but which do not exist in `FINAL_BOOK_FIELDS` — required by the audit brief's Phase 2 scope ("the union of… all 232 contract fields… every field referenced in templates/JS"). The headline counts table below is scoped to the 232 contract-field records only, as specified.

## Headline counts (from `attribute_inventory.json`, 232 records)
| Metric | Count | % |
|---|---|---|
| Displayed somewhere in the live UI (literal field name found) | 110 | 47% |
| **Not** displayed anywhere in the live UI | 122 | 53% |
| Producer traced with a direct code citation | 217 | 94% |
| Producer marked UNTRACED (genuinely not locatable in this pass, mostly upstream-of-`opt__`-alias options fields) | 15 | 6% |
| Records carrying at least one logged defect | 172 | 74% |
| `authority_class = CONTROL_CRITICAL` or `PRIMARY_CONTROL` | 10 | 4% |
| `authority_class = CONTROL` | 26 | 11% |
| `authority_class = ADVISORY` | 56 | 24% |
| `authority_class = OPERATIONAL` | 67 | 29% |
| `authority_class = RISK_CONTEXT` | 47 | 20% |
| `authority_class = LINEAGE` | 26 | 11% |

**AUTHORITY_RISK / AUTHORITY_MISREPRESENTED surfaces identified: 3** — (1) EIL modal tab hardcoded "advisory, not blocking" text contradicting an actual hard-veto path (`eil_v3_verdict`, gap report Finding 3); (2) `/api/export_csv` `rr_min`/`ev_min` query filters silently inert against governed field names (gap report Gap B); (3) client-side `exportCSV()` producing a CSV with multiple always-blank columns with no warning (gap report Finding 6). None of the three alters a trade permission directly; all three misrepresent to the trader what the tool has actually verified or filtered.

## Nine expected tabs — disposition
8 of 9 **PRESENT**, exact-name match, inside the per-ticker detail modal (`switchMTab`, `index.html:552-559`): Overview, Trade Setup, Options, Convexity, Stage Ladder, Morning Val, EIL, Q-OMEGA. **"Triage" is ABSENT** — no tab of that name exists anywhere in the live template. The main dashboard's separate tab bar (`switchLab`, `index.html:381-388`) uses different names entirely (Execute Brief, Armed Monitor, Convexity Engine, Open Positions, Exit Ticket, Outcomes, Learning Loop, Run Health); the always-visible signal table above that bar is the closest functional equivalent to a "Triage" view but is not itself a tab.

## Top 10 findings (full detail in `gap_and_defect_report.md`)
1. **BLOCKER** — The 8-tab detail modal is built almost entirely from pre-governance field names (`sb_*`, `mv__*`, `wbs__*`, `eil__*`, `garch__l3_*`, `qomega_*`, `doss__*`) that do not exist in the 232-field contract or the reference run; the governed data usually *is* present under the correct name and is simply never read.
2. **HIGH** — `/api/kpi` computes its entire scoreboard from ungoverned field names (`mv_verdict`, `data_quality_state`, `no_match`, `signal_trust_score`, `mv_breakdown`); every metric silently reads as zero/None under governed-book operation.
3. **HIGH** — EIL tab hardcodes "Advisory mode active — not blocking" while `eil_v3_verdict` demonstrably contributes to a hard veto (`EIL_BLOCKED`) in `contracts/lab_control.py:1028-1030`.
4. **HIGH** — `morning_gate.py` CHECK 1 fails open on missing `invalidation_price` (not `live_price`, which is correctly fail-closed): a row can reach `morning_execution_permission="GO_LIMIT"` with its stop-level unverifiable and no flag raised.
5. **MEDIUM** — The historical "missing PCR volume grants PUT trades a 5-point WBS bonus" defect is **verified fixed** in `contracts/lab_control.py:1801-1834`, but the correction is completely invisible in the UI (`wbs_pcr_volume_state` is never displayed).
6. **MEDIUM** — The client-side "Export CSV" button produces files with permanently blank Conv_Score, Instrument, Vetoes, WBS_Grade/Score, EIL_*, and MV_* columns against governed data, with no warning.
7. **MEDIUM** — Main-table "MV" and "Drift" columns, and the Stage-Ladder/Convexity/Morning-Val/EIL modal panels, permanently show their empty/fallback state under governed data (same root cause as #1, on the always-visible surface).
8. **MEDIUM** — `morning_data_state` (the field designed to distinguish "morning not yet run" from "morning ran and rejected") is a governed, populated field that is never read by the UI; the Morning Val tab instead infers absence from dead legacy keys, collapsing three real states into one "no data" message.
9. **LOW** — Mojibake confirmed in three locations: `morning_gate.py` (source comments/f-strings, `â€”` in place of an em-dash), `execution_intelligence_runner.py:124` (same pattern), and the reference run's own committed `entry_plan` data (a literal U+FFFD replacement character). Cosmetic only — does not change any verdict or number.
10. **LOW / UNVERIFIED** — The audit brief's named "f-string exception mislabelling rows in `avshunter_options_intelligence.py`" defect was searched for directly and not located in the sections read; report neither confirms nor rules it out.

## Missing-data semantics — one-line disposition
Of the seven states named in the audit brief, `AVAILABLE` and `NOT_EVALUATED` are consistently enforced; `NOT_APPLICABLE` is enforced only as extended/suffixed variants (never the bare token); `STALE` has no representation at the 232-field level at all (it lives only in the separate run-manifest artefact); `MISSING_DATA_DEFECT` exists in code but was not exercised in the sampled run; `NEUTRAL` and `ZERO` are not established conventions (used on at most one field each, and the single `ZERO` instance is doubtful). Full table: `gap_and_defect_report.md` §F.

## What a user guide MAY claim on this evidence
- The Lab loads a governed 232-field book (`lab_signal_book_v2`) whose source assertion (`GOVERNED_FINAL_OPPORTUNITY_BOOK_V2` vs `LEGACY_IN_MEMORY_ASSEMBLY`) is genuinely data-derived, not a fixed label.
- The main signal table's Rank, Ticker, Direction, Premium, Vol State (GARCH), and Sector columns, and the Options/GEX-levels modal sub-panel, read correctly from the governed book.
- The historical missing-PCR-volume WBS bonus defect is fixed in the current codebase.
- CHECK 1's live-price gate fails closed, not open.

## What a user guide MUST NOT claim
- That the per-ticker detail modal's Stage Ladder, Morning Val, EIL, or WBS/Convexity sub-panels reliably reflect the governed book's data — for the current UI build, they largely do not (Findings 1, 7).
- That the KPI scoreboard, the client-side CSV export, or the `/api/export_csv` `rr_min`/`ev_min` filters are trustworthy under governed-book operation (Findings 2, 4, 6, Gap B).
- That the EIL tab's "advisory, not blocking" message is accurate (Finding 3).
- That a missing invalidation level is always caught before a trade reaches GO_LIMIT (Finding 4).
- That the Lab enforces a uniform seven-state missing-data vocabulary across all 232 fields — it does not; only a narrow `*_data_state` field family does.
- Anything about the f-string row-mislabelling defect in `avshunter_options_intelligence.py` — status unresolved.

## Coverage caveat
Several JS helper functions referenced by the main table's sort/display logic (`finalLabVerdict`, `getExecutionCategory`, `getEv`, `getOptionRr`, `getSectorDisplay`, `getEilDisplay`, `getTimeHorizon`, `triggerSortValue`, and others — full list `functionality_audit.md` §7) were not traced to their definitions. Their output is not asserted correct or broken beyond what each field's `displayed`/`ui_labels` evidence in `attribute_inventory.json` already shows. 15 of 232 field producers are marked UNTRACED (mostly options-chain greeks/prices whose ultimate upstream origin sits inside the un-fully-read `scripts/avshunter_options_intelligence.py`) rather than guessed.

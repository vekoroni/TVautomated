# Validation of "AVSHUNTER: document review and decision register" (6 Oct 2026)

**What this is:** a point-by-point response to the review register (`AVSHUNTER_Document_Review_and_Decision_Register.docx`, sections 1–10, E01–E34, H1–H6). The register reviewed the final design without access to the code, the run data or the development-review design. This response checks its open points against those sources: the repository at the current working tree, run `20261006_060401`, and the development-review design that ACK pasted into the session on 6 Oct.

**Rules:** read-only. Nothing in the pipeline was changed. No approvals are recorded here; decisions remain ACK's.

**Verdict on the register:** the register is accurate and fair. Every gap it names is real. Most are closed by evidence the reviewer did not have (§1–§4). The rest are genuine ACK decisions or S1 tasks (§5). Its corrections to the design are accepted (§6).

---

## 1. "Much of the design lives in another document": closed

The development-review design was supplied by ACK in the session. Its contents the register asked for are reproduced in Appendix A:
- the five business questions;
- the seven §14 decisions, verbatim;
- stages S3–S5;
- the release boundaries.

The design will carry these inline rather than "by reference". The register asked for exactly that.

The **fact-ownership map** the register calls "fundamental" was still pending when the reviewer read the design. It is now complete: `FINAL_DESIGN_PART2_FACT_OWNERSHIP_AUDIT.md`, which covers writers, decision readers, statuses, a ranked list of superseded links that still decide, and defects H7–H11. The register's §8 item 2 is therefore met, apart from the per-row checks it lists, which stay as S1 tasks.

## 2. Defects H1–H6: checked at source and in run data

| ID | Code check (current tree) | Run-data check (`20261006_060401`) | Result |
|---|---|---|---|
| H1 CSV header from first row | `execution_gate.py:537–540`: `fields = list(rows[0].keys())`, `extrasaction="ignore"` | `execution_gated_*.csv` has 1,133 columns against 1,186 in the Morning trades. **71 columns are dropped**, including `entry_premium`, `contract_symbol_original`, `breakeven_price`, `contract_quote_timestamp_utc` and `live_contract_dte` | **CONFIRMED, active.** The saved file loses evidence needed for replay |
| H2 missing direction becomes CALL | `intelligent_orchestrator.py:1749–1753`: `_first_present(row, [...], "CALL")` | All 584 UNRESOLVED-direction rows land in `horizon_blocked`, none in a tradeable horizon file | **CONFIRMED in code, latent in this run.** A downstream block saved it this time; the default is still wrong (R1) |
| H3 mixed spread units | OI `:8012–8014` writes `spread_pct` as a fraction (`quote_spread_fraction`). `morning_gate.py:889` writes a percent into the live quote fields | S0 sampling: in the saved Morning file, `contract_spread_pct` and `spread_pct` are fractions (median 0.16). Five other `*_pct` spread fields are percents (median ≈ 15.9). The policy limits are stored as 18 and 25. `contract_spread_pct_eod` straddles 1 | **CONFIRMED, refined in S0.** The `_pct` suffix holds both units across fields. The claim that `contract_spread_pct` "becomes a percent after Morning" is not confirmed in this run |
| H4 opposite target precedence | `lab_control.py:3886` (`target_price`: own, then wall, then structural) vs `:3889` (`structural_target`: structural, then wall, then target) | Not yet counted per row (S1) | **CONFIRMED in code** |
| H5 independent bid/ask chains | `execution_gate.py:150–151` (each `live_contract_* → live_* → contract_*`); `lab_control.py:911` | Not yet counted (S1) | **CONFIRMED in code** |
| H6 missing target becomes 0.0 | `eod_candidate_engine.py:936–937` `default=0.0`, guarded at `:1002` (`target <= 0` returns early) | — | **CONTAINED (corrected in S0).** A missing target is labelled `DATA_MISSING` / `EOD_ASK_STRIKE_OR_TARGET_MISSING` before any valuation. The 0.0 never reaches an output; `:1030` is only reached after the guard. Pinned in `tests/test_avs_sot_s0_characterisation.py`. A style issue only, not a defect |

The register's priority order is accepted: fabricated direction or target, incoherent quotes, spread units, target precedence, then CSV loss. H1 is raised in priority, because it is active and breaks reproducible inputs (R7).

## 3. Value conventions: answered from code (register §7, E08, E09)

**Anticipated multiple** (`domain/anticipated_move.py:172–190`):
- **What it is:** the Black–Scholes model value of the selected contract at the level reachable by the q50 time, divided by the entry ask. The level is the structural level, capped at the volatility reach for that time. The value uses the remaining time to expiry and constant contract IV.
- **What that makes it:** a **gross terminal-value ratio at model mid**. No exit spread or slippage is deducted. It is conditional on the level being reached at that time. It is **not** a net return and **not** an expected value.
- **HL example:** 1.316× means the contract would be worth about 1.32 times the ask paid, *if* the move happens, before exit costs.

**EV3 `ev_conservative_return`** (`vanguard/ev_engine_v3.py:500–545`):
- **What it is:** a **net return per unit of entry debit**, taking exit credit = model mid × (1 − half-spread − slippage).
- **How it is weighted:** probability-weighted across target-first, stop-first and timeout. It then takes the minimum of the base case and the IV-stressed case.
- **Its inputs:** EV3's own `target_spot` and `invalidation_spot`, its own session means, and the timeout exiting at the entry spot.
- **HL:** −0.266 = an expected net loss of 26.6% of premium under EV3's model. Timeout probability 0.59 dominates: the time value lost when the move does not happen in the window.

**Conclusion:**
- **Units:** the two are in different units (gross ratio vs net return) and answer different questions (conditional payoff vs probability-weighted outcome). As the register says, both can be right at the same time.
- **Display:** the design shows them under distinct labels and never side by side as "value".
- **Comparability:** any future comparison needs a common convention, declared under E08 and E10.

**q50 level and q50 time are not a joint median** (register §7). The code confirms it:
- the **time** is a duration quantile of the event occurring (`q50_bars × per_bar`);
- the **level** is the structural target, capped at volatility reach.

They are estimated separately, so the joint event is not 50% likely. The label stays conditional: "option value if the underlying reaches *level* by *time*". `anticipated_p_outcome_by_limit` is shown beside it as the probability evidence.

## 4. Other register points answered from the record

| Register point | Evidence | Result |
|---|---|---|
| E26: what does P5 complete? D and F appear to disagree | `AVS-PKG-002_P1_P4_BUILD_RECEIPT_20260927.md`: P5 = "delete the package readers/writers, retire the three scripts and the `packages` mode, update docs and the field owner matrix". It follows Morning live proving | **Input-side clean-up, not a decision record.** D and F are consistent; D's wording is corrected (§6). The same receipt names the drop-off label `PENDING_PACKAGE_BUILD` "a label that assumes packages; rename in P5". Today's drop-off audit still shows 1,814 rows under it. That is the legacy consumer the development review noted |
| §7: "keeping old files does not prove old logic governs" | Ownership audit (part 2): it traced active **readers**, not file existence. EV3 is shown to be correctly diagnostic (Morning always passes, authority forced off, execution gate does not read it). `_check_monetisability` has no caller. Superseded links that **do** decide are listed with file:line | **Accepted, and the design now rests on reader evidence, not file counts** |
| §7: direction consistency is not accuracy | — | **Accepted.** The design claims only agreement on that population. Accuracy belongs to C12 outcome measurement |
| §7: correlation is not an adequacy test | — | **Accepted.** −0.02 is kept only as evidence that the rank does not use value. The rank objective is ACK decision E11 |
| §7: large payloads are complexity, not proof of cause | `lab_control.py:4074` embeds the whole Morning row as `source_payload_json` in each book row; the JSON is written unfiltered (5065) | **Mechanism identified.** S0 separates serialisation, transfer and processing times before targets are set (E34) |
| §7: timeframe mismatch is not automatically guilty | — | **Accepted.** RC5 / E06 test "traceable consistency with the selected setup", not identical labels |
| §7: a universal ban on superseded references | — | **Accepted.** R-1 becomes a role registry (DECISION / SUPPORTING / AUDIT / MEASUREMENT_ONLY). Only unauthorised decision or primary-display use fails the build |
| §7 / decision 9: one-programme freeze | — | **Accepted as amended.** One coordinated programme for changes to shared facts and data contracts. A controlled route stays open for urgent faults and unrelated safe work, with a prioritised backlog |

## 5. E01–E34: disposition

**Key to the Status column:**
- **Answered:** settled by evidence in this response or the audits.
- **ACK:** needs a business decision.
- **S1:** a defined trace or measurement task before any change.
- **Design:** to be written into the specification before build.

| ID | Status | Note |
|---|---|---|
| E01 whole pipeline or Lab | Answered | Whole pipeline. The handoff and ownership audits show superseded sources deciding in contract selection, Morning hold, execution gate and rank |
| E02 underlying vs option | ACK (confirm) | Recommended: yes |
| E03 owner per fact | Answered / Design | Ownership map complete. Each authority needs a definition, version, accountable owner and allowed readers, written in the glossary (R-2) |
| E04 targets | Design | Three target kinds kept distinct. `resolve_target(kind=…)`. Link 1 (strike filter on the structural target) is S2 priority |
| E05 clocks | Design | Four clocks; sessions vs calendar days. H8 (`contract_dte` standing in for `dte`) to fix |
| E06 setup timeframe | S1 | Trace RC5 on RARE, HWM and FISV |
| E07 invalidation | Design / S1 | Four chains to collapse. 6 Evening rows missing it (recurring FAIL) |
| E08 scenario economics | Answered (convention), ACK (labels) | §3 |
| E09 EV3 role | Answered (current), ACK (future) | Currently diagnostic, as intended. Recommended role: MEASUREMENT_ONLY plus audit display |
| E10 entry sensitivity / maximum premium | Design / ACK | Formula and objective to be specified; never shown as fair value |
| E11 rank objective | ACK | Objective first, then formula; groups, downside, evidence quality, ties |
| E12 NOT_COMPUTED / vol-only | ACK | Recommended: option-review FLAG, underlying kept |
| E13 quote age | S1 | Inventory every direct and indirect effect |
| E14 coherent quote package | Design | H5 |
| E15 spread | Design / ACK | Fraction in the name. Current thresholds kept. H3, H7 and H10 reconciled with recalibration evidence |
| E16 Morning swap | Design | New linked assessment version. The current swap overwrites in place (strike, expiry and DTE under 3 names each) |
| E17 identity | Design | Key = run, candidate_id (ticker, timeframe, scope, setup, date), side, contract_symbol, version. Ticker alone is ambiguous: the horizon router may collide on CALL and PUT rows (S1) |
| E18 record schema | Design | Typed schema in the specification before S3 |
| E19 canonical emit points | Answered | At each decision owner (S2); record assembled at S3 |
| E20 immutability | ACK (confirm) | Recommended: append-only with supersession links |
| E21 missing and retired | Answered | Explicit missing state; role registry (§4) |
| E22 / E23 / E24 Lab | Design | As register; partial, failed and complete validation states defined |
| E25 full-width artifacts | Answered | Preserved until S6; C12 compatibility tested |
| E26 P5 | Answered | §4 |
| E27 keep / change / quarantine / retire list | Design / ACK | One reconciled list with owners and dates |
| E28 glossary | Design | R-2 |
| E29 governing documents | ACK | Mark strangler sections superseded by CLAUDE.md rule 4; one decision-ID namespace |
| E30 defect disposition | Answered / ACK | §2 plus H7–H11; repair order as register |
| E31 open investigations | S1 | Phantom path, possible no-op patch (orchestrator 1852–1878), CALL/PUT collisions, runway units, RC5, RC7 |
| E32 baseline | S0 | Freeze `20261006_060401`; commands recorded |
| E33 release | ACK | Appendix A gives the release definitions. Rollback means reverting the commit and staying on the current Lab view |
| E34 performance | S0 | Separate processing, serialisation and transfer |

## 6. Corrections to the design (register §8 "editing corrections")

The main design file is locked by another program, so these are applied when it is released:
1. **Title and status:** "final design, v1" becomes "**Proposed design v1, for review**".
2. **§C:** "two pending audits" is wrong. All four audits are complete; part 2 is merged.
3. **§D:** "P5 not done" is restated as "P5 (input-side package retirement) awaits Morning live proving; it does not create an output decision record".
4. **Numbering:** the recurrence controls R-1…R-5 are renamed **K-1…K-5**, so they cannot be confused with the specification's design rules R1–R12.
5. **Inline content:** the seven §14 decisions, the five questions, S3–S5 and the release boundaries go inline (Appendix A).
6. **New design content:** E-items marked "Design" in §5. The decision state model (underlying, option, validation stage, execution permission, review reasons) gets its own section.

## 7. Recommended decision position

The register's §10 is adopted:
- **Approve in principle:** whole-pipeline source of truth, repair before display, and recurrence controls.
- **Amend:** the one-programme rule.
- **Hold:** approval of the complete build waits for the specification additions in §5 and §6.

Nothing here is release approval, confirmation that defects are fixed, or evidence of predictive accuracy.

---

## Appendix A: content from the development-review design (supplied by ACK, 6 Oct 2026)

**Five business questions:**
1. What direction and setup does the ticker evidence support?
2. What move and path are anticipated, over what timescale?
3. Which long CALL or PUT best expresses that assessment?
4. Can the contract monetise the anticipated move, under the stated assumptions?
5. What would invalidate or materially change the assessment?

**§14 development-team review decisions (verbatim):**
1. Confirm the actual anticipated-value formula and its contractual owner.
2. Approve or amend missing-option-value handling.
3. Approve comparable-value ranking and evidence-quality treatment.
4. Confirm the primary-view and lazy-audit layout.
5. Confirm spread convention without silently changing existing policy thresholds.
6. Reproduce the reported population and performance figures.
7. Identify all affected consumers, including Interpreter, journal and outcome measurement.

Status of each against this validation:
- **1:** formula answered in §3; owner `domain/anticipated_move.py`. ACK confirms the owner.
- **2:** ACK (E12).
- **3:** ACK (E11).
- **4:** ACK.
- **5:** ACK (E15).
- **6:** S0.
- **7:** ownership map, plus S1 for Interpreter and journal.

**S3–S5 (from the review's §11):**

| Stage | Work | Acceptance |
|---|---|---|
| S3 | Implement decision records and versioned handoff | Every row reconciled; explicit missing states; provenance resolves; provisional payload budget below 10 MB |
| S4 | Implement approved ranking and missing-value policy | Deterministic shared ordering; every changed recommendation explained |
| S5 | Switch Lab primary views to decision records; lazy-load audit | One owner per displayed fact; structural evidence retained; provisional initial-load target below 10 seconds under documented conditions |

**Release boundaries (review §13):**

This work does not authorise:
- automated execution;
- unrequested provider calls or pipeline launches;
- deletion of historical runs or databases;
- replacement of formulas without approved specifications;
- disabling unrelated identity or calculation checks;
- claiming predictive accuracy from technical regression tests.

**Build complete** = implemented end to end with developer verification.

**Shipped** = regression and replay accepted, and the human-run pipeline proven with no grade 0/1/2 defects; grade 3 defects have workarounds. The commit follows the agreed release process.

# AVSHUNTER fix status register — 21 November 2026

Original audit snapshot: branch `laneb/lab-first-handoff`, HEAD `ff24d41`. This register was subsequently amended on 21 November at ACK’s request. Original findings are retained with corrected status dimensions and implementation comments. This amendment changes documentation only; no fixes are built or activated. Original audit ran no tests; the independent assessment later ran the two narrow Phantom ownership tests recorded below.

## Status and evidence rules — supersedes the original three buckets

**ACK instruction, 21 November:** this is a whole-pipeline implementation register, not a targeted volatility review. The commit/baseline work had to finish before any fix build. The 21 November reconciliation observes the commit batch complete at `f3e199e`; residual files and baseline acceptance still need disposition. ACK explicitly says **do not start building yet**. See section 8. No fix, commit, merge or activation is started by this register.

Each fix row now has six independent status fields. A source file existing, a commit, a run call, a passing test, an accepted outcome result and permission to influence decisions are different evidence.

| Dimension | Values and interpretation |
|---|---|
| Built | `YES-REPORTED`, `PARTIAL`, `NO-REPORTED`, `UNKNOWN`, `DESIGN-ONLY`; reported means original-register evidence, not independent recertification. |
| Committed | `CITED`, `OTHER-BRANCH`, `RECHECK-BASELINE`, `NOT-APPLICABLE`; a cited hash is a historical claim, not proof the effective working tree matches it. |
| Wired | `YES-REPORTED`, `PARTIAL/DEGRADED`, `NO-REPORTED`, `POLICY-DISABLED`, `UNKNOWN`; functioning output is additionally described in comments. |
| Tested | `NOT-REVERIFIED`, `2-NARROW-PASS`, `NOT-APPLICABLE`; never infer passing tests from their presence or a commit. |
| Validated | `NOT-EVIDENCED`, `REPLAY-REPORTED`, `FORWARD-PENDING`, `NOT-APPLICABLE`; run output/outcome counts are not economic acceptance. |
| Authorised | `VERIFY-DECISION`, `SHADOW-ONLY`, `OBSERVATION-ONLY`, `DECISION-PENDING`, `NOT-APPLICABLE`; a status row itself grants no authority. |

The old section 1/2/3 labels remain as **historical navigation buckets only**, not current conclusions. Use the six columns and implementation comments. Compound rows must be split into independently verifiable work items during baseline reconciliation where their components differ.

- The 19 November run used a dirty working tree; current live execution and reproducible committed release are separate facts. The old ~220-file estimate is historical, not a current count.
- A later independent review inspected HEAD `350e614`; selected volatility files then had no working-tree diff and macro triage/verifier commits existed. This is an intermediate observation, **not the completed commit baseline**. Recheck after ACK’s ongoing commit work finishes.
- Forward acceptance was not evidenced for most inspected fixes. Do not infer its universal absence. Historical receipts, output correctness and forward economic validation have separate scopes.
- Unless a row explicitly says otherwise, its tests/branch ancestry/full runtime impact have not been independently reverified. Unknown remains unknown.

Sources audited: end-to-end fix design and addendum (Sep), decision path map DM-01..38, Phase 0–8 documents, 25 Sep change register, DIR-002, BEH-001, TEV-001, SOR-001, XLU register, 7 Oct redesign, output-trust items 1–11, trade-quality register (D2…T2), lessons L1–L8 / R1–R10, Lab-004 and source-of-truth validation, options valuation G1–G9 and UAT-01..07, Phantom change list 1–11, tradeability AVS-TRADE-001, ETF reliability E1–E24, Lane B Fix B and `needs_codex`, macro delivery/board/triage documents, and the two Codex plans of 21 Nov (section 4).

---

## 0. The gaps that matter most

These are the items where the paperwork says one thing and the code or the live run says another.

| # | Gap | Evidence |
|---|---|---|
| 1 | **Shadow contract value selection (B1) produces nothing.** Every selected row is `VALUE_INPUTS_UNAVAILABLE`, forecast source `UNAVAILABLE`. | 2,032 of 2,032 rows on 19 Nov; same on 14 and 18 Nov. Cause is the stage order in Codex VOL-02 (section 4). |
| 2 | **Scenario payoffs (C1) are empty on every row.** | `scenario_state = NOT_ASSESSED`, `DOI_SCENARIOS_ABSENT`, 2,038 of 2,038. |
| 3 | **Monetisation clock (A12) is merged but never fed.** | `monetisation_clock_state = UNASSESSED_NOT_PUBLISHED` on 2,746 of 2,746; only an offline CLI supplies the packet. |
| 4 | **Crossing scenario (AVS-TRADE-001 v4) fails on a real session.** | `crossing_state = THESIS_NOT_ACTIVE` on 2,036 rows, 1,952 of which have an ACTIVE Morning thesis. Root cause not traced. |
| 5 | **Sector/USMI alignment (XLU-D03, E2) is dead.** | `UNAVAILABLE` on all 2,746 rows in four runs; the receipt claimed 219 ALIGNED. |
| 6 | **"CONFIRMED" direction with zero evidence (D2) was closed by a display rename only.** | `contracts/direction_governance.py:773-774` still writes `DIRECTION_CONFIRMED`. |
| 7 | **Decisions marked RESOLVED in September that were never built:** no EOD synthetic verdicts (D9), actuarial builder into the repo (D11), catalyst and RS20 direction evidence retired (D2 of the design). | `execution_intelligence_runner.py:346`; no builder tracked; `direction_governance.py:636-672`. |
| 8 | **Advisory publishers can still abort the Evening** (TEV-001 P0a, approved). | `intelligent_orchestrator.py` ~6316–6330 and ~6365–6384 `return False`. |
| 9 | **Missing direction still defaults to CALL in one path** (H2). | `intelligent_orchestrator.py:1761-1765`. |
| 10 | **Universe option chains are missing for 12, 16 and 20 Nov** (SPY and QQQ only), and nothing fails when that happens. | `phantom_pair_health`; readiness is a warning only. |
| 11 | **Phantom score can never reach HIGH or CONVICTION.** Maximum possible score is 67.5 against thresholds of 70 and 85. | `scripts/phantom_engine.py:106-131`; formula confirmed in this audit. New finding from Codex. |
| 12 | **Macro reproducibility needs post-commit reconciliation** (controlled scheduler, freshness gate, cost cap, triage integration T1–T7). | Historical untracked-file finding. Later macro triage/verifier commits exist; scheduler exact paths were untracked at the earlier review but are now tracked/clean at b44d96e. See section 8 for final-baseline qualifications. |
| 13 | **Two fixes exist only on other branches.** Lab timing publication (`b48db74`) and the production eligibility gate (`eb50549`). | Not ancestors of HEAD. |
| 14 | **Documents that are stale the other way** (say "not committed" or "open" but are done): G4 and G5 receipts, P0-8 §13, board gap G15, artifact-retention receipt, `pending_us_money_index_fix` folder, the weekend quote-age memory note. | Commits `666f09c`, `c175576`, `23ad527`, `1f37f1c`. |

---

## 1. Historical bucket: outstanding / incomplete

### 1.1 Run control, reproducibility, hygiene

| ID | Fix | Evidence | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| S0.4 | Injected clock in legacy code; no `date.today()` | `avshunter_discovery_ULTIMATE.py:815`, `garch_runner.py:99`, `phantom_engine.py` `score_date` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| S0.5 / R7 | Replay runner | `intelligent_orchestrator.py:8676` raises on REPLAY | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| S0.7a/b | Config-driven paths; package imports | 60 files hold the hardcoded user path; 108 use `sys.path.insert` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| P0-3 2a–2c | Single morning path integrity check; research operator mode; quarantine legacy launchers | Not built; launchers and `.bat` files tracked | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| S18.3 / S18.4 / SA-5 | Golden replay of frozen runs; real-run gate after every run; signal-accuracy audit as a recurring check | Audit script last run 14 Sep; not called by the orchestrator | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| R1, R3, R6 | Lint for missing-as-zero; units-in-names check; calibration check on anything called a probability | None found | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| P0-5 / S1.1 / ADD-N6 | Point-in-time universe with delisted names | No code | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| P0-6 / S17.1 | Ledger completeness and decision/outcome linkage (C11) | CORRECTED: `canonical_data/decision_outcome_ledger.py` and orchestrator calls exist. Audit required fields/population/lineage; absence of a module named `c11_ledger` is not absence of a ledger. | PARTIAL | RECHECK-BASELINE | YES-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | OBSERVATION-ONLY | P1 — Existing canonical ledger/learning owners; complete linkage/option labels/support/held-out evidence rather than duplicate C11/C13. |
| S17.7 | Existing learning/validation path: support, labels and held-out acceptance | CORRECTED: `canonical_data/outcome_learning.py`, `domain/outcome_learning.py` and probability services exist and produce snapshots. Missing option labels/held-out metrics and short-horizon support remain; activation disabled. | PARTIAL | RECHECK-BASELINE | YES-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | OBSERVATION-ONLY | P1 — Existing canonical ledger/learning owners; complete linkage/option labels/support/held-out evidence rather than duplicate C11/C13. |
| P0-10 | Stale and unservable universe symbols; mixed-date crash | Not fixed | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| P0-11 / S7.1 / D11 | Actuarial builder in the repo, reading the same history store; outliers excluded | No builder tracked; 310 rows over 1,000% not remediated | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| S7.5 / S7.7 | Actuarial staleness gate; retire `actuarial_live_updater.py` and empty sqlite | Refresh still manual | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| PKG-002 P5 / S6 | Delete package mode and its scripts | `packages` mode still at `intelligent_orchestrator.py:653, 3753` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| F7-skipped | 58 tickers skipped in the daily history backfill | No follow-up | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| TR-022/023, AVS-CHANGELOG-001 (rule) | Shared change log rule in agent instructions; register kept current | Log stops 18 Nov; rule not in `CLAUDE.md` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |
| RETENTION-BACKUPS | 710 backup files, none proven redundant | Receipt: 0 deleted | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Reproducibility/data clock/ledger; trace all downstream consumers before changing interfaces. |

### 1.2 Discovery, Vanguard, direction

| ID | Fix | Evidence | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| D3 / D6 / D19 / OT-11 stations 2–5 / A-step 3 | Legacy Wyckoff phase, trigger category and composite tier out of options score, trap engine, trigger T3, EOD tier | `avshunter_trap_engine.py:114`, `trigger_layer.py:468`, `compute_ois` reads `ctx['phase']`, `eod_candidate_engine.py:2084` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| DV-6b | Vanguard/EV3 key labelled `LEGACY_STATE_KEY` | Zero hits | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| Redesign Phase 6 | Scenario rules and contributors measured; legacy `assign_tier`, `calculate_win_probability` removed | Still called (`avshunter_discovery_ULTIMATE.py:1550, 1978`) | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| S5.4 / DSC-16 | Wall-clock composite decay and tiers | `date.today()` decay at `:815, 910` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| D2 (design) / DM-04 | Retire catalyst and RS20 direction evidence | `direction_governance.py:636-672` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| S4.2 / DM-35 / VNG-10 | Vanguard regime floors and match key still use `macro_regime` | `edge_detector.py:174, 356, 421`; `actuarial_query.py:74, 227` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| Phase 4 `min_price` | Remove Vanguard `min_price: 10.0` (ACK 4 Oct: no price gate) | `vanguard/config.py:213`; effect not traced | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| S1.3 | `scanner_data_quality=CONFIRMED` hardcoded | `intelligent_orchestrator.py:955, 6306` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| S2.1 | One bar reader; no stale-cache fallback | `STALE_CACHE` fallback at discovery `:1110` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| S5.2 | One Wyckoff engine | Dead copy still tracked | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| H2 | Missing direction defaults to CALL | `intelligent_orchestrator.py:1761-1765` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | STATIC+8282-SAVED-TRACE | NOT-EVIDENCED | VERIFY-DECISION | P2-DEFENSIVE — Latent caller defect reproduced; 0 defaults and 0 routed/governed side disagreements in 8,282 saved rows. Shared owner/identity follow-up BF-02, no observed wrong-side incident; see section 10. |
| DWN-03, DWN-14, VNG-15, DSC-25 | EIL tests `edge_dir in {CALL, PUT}`; enrichment trend vocabulary; `win_probability` seeding; literals in domain code | Still present; some inert | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| VNG-04 / VNG-09 / C-05 | v8 mirrored first-passage labels; per-candidate first-passage statistics | No v8 builder | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| DIR-002 R-1…R-9 | Integrated acceptance of the direction cut-over | Only R-5 run (BEAR failed by 0.002); cut-over made under the 4 Oct waiver | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| DV-1, DV-2, DV-7, A-steps 4–8 | Same-timeframe conflict keeps counter-side; both conditional triggers on the card; contributors as zero-weight fields; nesting; enhancers; Vanguard re-key | Designed 12 Oct; not built | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| N3, N4, B1 (stage design), N1, N5–N10, N12 | Entry-policy registry; entry availability; three state dimensions; reading evidence fields | Modules do not exist | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| T2 | Assessment id | Not found | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| D4a, D5 | Lane C geometry not measured; "pooled probability" (never defined) | Identified only | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| BEH evidence refresh | Duration-evidence builder inside the pipeline | Still offline | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |
| R5/L4, R7/L8, L6/R9 | Weekend-carry line; next-leg targets; one slot per cluster | Not found. All 18 lessons are still OPEN in `trade_journal.db` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Discovery/direction/horizon -> Vanguard -> OI -> EIL/Morning; inspect active versus retired path. |

### 1.3 Options valuation and contract selection

| ID | Fix | Evidence | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| G1 | Exit IV from the stored surface, not held flat | `domain/anticipated_move.py:253` `IV_HELD` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| G2 | Spread model from recorded quotes; exit on the bid | `domain/option_valuation.py:153` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| G3 / G8 | Fill probability; predicted option price per session, scored against closes | No code | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| G7 | Event-variance split instead of flat IV × 0.8 | `anticipated_move.py:242-258` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| D2 (valuation) | IV re-implied from the mid (approved 17 Oct, due 24 Oct) | No function | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| M3–M9, G9-extra, G5 switch | Seven remaining Black-Scholes copies onto the one pricer; European/American switch | No owner imports; guard test only stops new copies | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| G6 | DOI dividend basis; exit rule for ITM puts and ex-dividend | Unchanged | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| G4-open a–c | Missing-Greek defaults (θ −0.01, vega 0.05, Δ 0.35); 2,172 unverifiable rows; deep-ITM puts with 300–700% IV | `avshunter_options_intelligence.py:7222, 5753` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| OT-4b/4c, OT-7a/7b | Callers pass the observed rate everywhere; discrete dividends; wall thresholds calibrated; Morning recomputes walls | Not found | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| S10.1b / DM-18 | Quote freshness measured, not assumed `SESSION_ALIGNED` | `:6519` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| XLU-D05 | Selection rewards vega regardless of IV level | `:5785` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| B2 (delta bands), B3, B4, C2 | Delta band pre-selection; long shares as an expression; duplicate hold band; asymmetry constants | Not built | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| OA slices 3–5 | Move-to-return table; implied vs forecast move ratio; slippage and P&L attribution | No code | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| A1 | Selected contract outlasts the hold | Measured only: 1,124 contracts expire before the median move | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| W3, W4 | Pipeline `trade_window_state` and `premium_cap_state` flags (approved 12–13 Nov) | No code; Lane B proxies only | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| E9, E12 | Both index-ETF contract alternatives; ETF review view (approved D-14.3, D-14.4) | No code | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| TR-020 | PUT base rates | `ev_engine_v2.py:92-94` unchanged | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| DM-10, DM-13 / S15.5, S13.4, S13.6 / DM-11, H4, H5, S1-3, S1-5b | Vanguard target = entry price; Morning replaces thesis entry with live price; invented exit targets (1.03/0.97); zero or −1 for missing; target precedence; bid/ask fallbacks; router no-op; DTE buffer units | Lines cited in the foundation audit; all unchanged | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| S12.2 / D9 | No EOD synthetic EIL verdicts | `execution_intelligence_runner.py:346` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| S12.4, S11.6, ADD §7.1, TEV "cut" items | Retire WBS scoring, monetisation policy copies, SuperBrain passthrough, legacy EV engines, duplicate estimator modules | All tracked. Note ACK's "repair, don't delete" rule | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| TEV P0(a) | Advisory publishers never abort the Evening | Not built | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| TEV Slices C, E, G | C4 base-rate packet; C8 valuation; release proof | `NOT_ESTIMABLE` hard-coded; C8 never valued | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| D-14.7 | Codex code review of the crossing build before commit | Review file absent; `fc5faee` committed anyway | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |
| Design 15.10 | Measured clock by historical replay | No note | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Valuation/contract/exit economics -> cards/Lane B/Morning; quantify before/after at identical inputs. |

### 1.4 GEX

| ID | Fix | Evidence | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| GEX-D2, D3, D8 | Correct units and net GEX per ticker; replace ad-hoc flip confidence; proximity units | `compute_gex:3257`; `execution_intelligence.py:178` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Dealer-positioning evidence -> walls/reachability/review; verify units and active consumers, no new capital gate. |
| S3.4 / GEX-D10 | Missing GEX never becomes neutral 0.50 | `regime_consensus.py:241-243` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Dealer-positioning evidence -> walls/reachability/review; verify units and active consumers, no new capital gate. |
| S3.6 / GEX-D7, S3.1 / GEX-L4 | Retire the EIL synthetic GEX map; one engine per ticker | `execution_intelligence.py:254, 648` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Dealer-positioning evidence -> walls/reachability/review; verify units and active consumers, no new capital gate. |
| S3.3 | GEX freshness: STALE, not COMPLETE | `build_local_gex.py:203, 219` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Dealer-positioning evidence -> walls/reachability/review; verify units and active consumers, no new capital gate. |

### 1.5 Phantom and options data

| ID | Fix | Evidence | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| PH-gap / BF-12Nov | Universe chains missing for 12, 16, 20 Nov (and 28 Sep, 30 Sep, 5 Oct on samples) | SPY and QQQ only on those sessions | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Capture -> Phantom/IV/forecast/outcomes; distinguish acquisition, derivation and consumer completeness. |
| DF-5 / S2.4 / PF-3 | Run fails loudly, or flags consumers, when capture coverage drops | Warning only | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Capture -> Phantom/IV/forecast/outcomes; distinguish acquisition, derivation and consumer completeness. |
| S2.3 / ADD-N1 | Fixed nightly capture panel independent of candidates | Not built as an owned job | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Capture -> Phantom/IV/forecast/outcomes; distinguish acquisition, derivation and consumer completeness. |
| UAT-04, UAT-05 | Weekly maintenance on a legacy-schema database; readiness says FRESH with incomplete Greeks | Unchanged since `7effc2b` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Capture -> Phantom/IV/forecast/outcomes; distinguish acquisition, derivation and consumer completeness. |
| PH-6 (cause) | About 1,300 rows per night arrive with no underlying price | Labelled, cause not investigated | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Capture -> Phantom/IV/forecast/outcomes; distinguish acquisition, derivation and consumer completeness. |
| BF-old, PH-9b | Old backfill runners still unsafe; rehydrate scripts mislabelled | Unchanged | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Capture -> Phantom/IV/forecast/outcomes; distinguish acquisition, derivation and consumer completeness. |
| D16 / ADD-N2 | IV history depth; daily constant-maturity IV series for 252 sessions | Label only; see Codex VOL-04 | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Capture -> Phantom/IV/forecast/outcomes; distinguish acquisition, derivation and consumer completeness. |
| F7 (19 Sep) | Options flow half-built (`NO_PCR_DATA`) | `:9875` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Capture -> Phantom/IV/forecast/outcomes; distinguish acquisition, derivation and consumer completeness. |

### 1.6 Lane B, ledger, Lab

| ID | Fix | Evidence | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| needs_codex 1.1 | Lab publishes the monetisation fields Lane B reads | Names differ; `NOT_PUBLISHED` on 2,593 rows | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Published fields -> Lab -> Lane B -> records/outcomes; reconcile producer/consumer names and row grain. |
| needs_codex 1.3 / A4 | One repair state per row | `lb_repair_conflict` on 459 rows | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Published fields -> Lab -> Lane B -> records/outcomes; reconcile producer/consumer names and row grain. |
| needs_codex 1.5, 1.6 | Publication stage in the manifest; cluster field on the card | Absent | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Published fields -> Lab -> Lane B -> records/outcomes; reconcile producer/consumer names and row grain. |
| B8, B9 | Deep dive starts from the Lab card; fallback contract from Lab alternatives | Launcher unchanged since 20 Oct | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Published fields -> Lab -> Lane B -> records/outcomes; reconcile producer/consumer names and row grain. |
| TR-041 | Option closes carry a session-close flag | No column | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Published fields -> Lab -> Lane B -> records/outcomes; reconcile producer/consumer names and row grain. |
| A11, C1 | Projection issue flag (`NAN:EVENT_MISSING_FROM_PROJECTION`); Lab macro context degraded | Still in the manifest | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Published fields -> Lab -> Lane B -> records/outcomes; reconcile producer/consumer names and row grain. |
| AVS-LEDGER-001 L2–L5 | `card_outcomes.py`, backfill, daily run, summary | Script absent | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Published fields -> Lab -> Lane B -> records/outcomes; reconcile producer/consumer names and row grain. |
| Lab CORS/auth | Open CORS and no authentication (bind is now 127.0.0.1) | `intelligence_lab.py:124` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Published fields -> Lab -> Lane B -> records/outcomes; reconcile producer/consumer names and row grain. |
| Lab-004 acceptance | Real-run cold-load acceptance, manual proving, ACK release | No receipt | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Published fields -> Lab -> Lane B -> records/outcomes; reconcile producer/consumer names and row grain. |
| ARCH-LB fix list (21 Nov) | Lane B to intelligence-mining list, about 50 items | Marked "nothing to be built yet" | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Published fields -> Lab -> Lane B -> records/outcomes; reconcile producer/consumer names and row grain. |

### 1.7 Macro

| ID | Fix | Evidence | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| TRIAGE-T7-DISPLAY | Board template shows the T7 intelligence items | No template code | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Macro capture/delivery -> board/triage/intelligence; retain no standalone trade-authority effect. |
| USMI-SCORE-EMPTY | Money Index has no score or components since the 10 Nov rebaseline | ChatGPT side | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Macro capture/delivery -> board/triage/intelligence; retain no standalone trade-authority effect. |
| GATE-DIRECT-BUILDER | Direct `build_macro_json.py` call bypasses the freshness gate | Documented limitation | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Macro capture/delivery -> board/triage/intelligence; retain no standalone trade-authority effect. |
| STALE-RSP-BREADTH, STALE-DEPTH | RSP breadth not labelled stale on as-of builds; 37 ETFs lack 200-day depth | `macro_board/opportunity.py:40` | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Macro capture/delivery -> board/triage/intelligence; retain no standalone trade-authority effect. |
| G10, G16, G17 | Yield split into real/breakeven/term premium on the board; shared-event flag; SPY/QQQ intraday | Series collected, not used | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Macro capture/delivery -> board/triage/intelligence; retain no standalone trade-authority effect. |
| REPLAY-HOLDOUT | "✓ holdout" still shown as a positive chip | Template 242–243 | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Macro capture/delivery -> board/triage/intelligence; retain no standalone trade-authority effect. |
| MDI-14 | Retire or rebuild `macro_module_contract.json` | Still written | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Macro capture/delivery -> board/triage/intelligence; retain no standalone trade-authority effect. |
| XLU-D16, NF-1 | USMI age check; finaliser re-reads macro from the live folder | Not found | NO-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Macro capture/delivery -> board/triage/intelligence; retain no standalone trade-authority effect. |

### 1.8 Waiting on an ACK decision

| ID | Decision needed | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|
| STALE-A / B / C, STALE-BITO | Which fix for the 39 ETFs with no stored prices, and the BITO split (+98% shown on 19 Nov) | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| TRIAGE-11-UNIVERSE | Add 11 ETFs to the board universe | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| FUNDFLOW-SOURCE | A verified ETF net-flow source | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| COST-CAP | Decided by ACK on 21 Nov: USD 4 a day. Tests now read the cap from config; runbook corrected | YES-REPORTED | ANCESTOR-VERIFIED f3e199e | YES-REPORTED | 16-PASS-VERIFIED | NOT-EVIDENCED | USD4-CONFIG-DECISION | VERIFIED-NARROW — USD 4 API cost tests independently passed 16/16; no broader scheduler/producer/outcome acceptance implied. |
| RECOV-FUNDING | API credit shortfall for FULL builds | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| MDI-12 | MOVE, dispersion and correlation measures | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| Dec 4, 5, 7, 8, 9 (AVS-TRADE-001) | Value selection SHADOW→ACTIVE; rank by return per premium dollar; tastytrade live quotes on cards; in-window names first; success tests as expectancy | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| TR-005 | Delayed feed (72–76 min) fails the freshness rule and gives DO_NOT_TRADE on 14, 18, 19 Nov | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| TR-013, needs_codex §4 | Retire the 25% spread test and old-layout scripts | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| BF-A | Wider backfill chains | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| OT-4d | Fee schedule | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| Dev plan v0.2 (AR22, R0–R3, BG01–BG10), Decision Register docx decisions 1–10 | Whole plan is "proposed"; none approved | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |
| Codex plans (section 4) | Approval of root cause and design before any build | UNKNOWN | RECHECK-BASELINE | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P0-DECISION — Record the existing business decision/approval first; no implied build or new spending. |

---

## 2. Historical bucket: built with delivery, release or acceptance gaps

### 2.1 Built and wired, but producing nothing in real runs

| ID | Fix | What the run shows | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| B1 / `675b5e3` | Shadow contract value selection | 100% `VALUE_INPUTS_UNAVAILABLE` | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | SHADOW-ONLY | P1 — Observed empty/degraded output; root-cause producer, branch and consumer before proposing a fix. |
| F1 | Legacy vs shadow selection pair | Shadow half empty because B1 is dead | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | SHADOW-ONLY | P1 — Observed empty/degraded output; root-cause producer, branch and consumer before proposing a fix. |
| C1 | Scenario payoffs on every row | 100% `NOT_ASSESSED` | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Observed empty/degraded output; root-cause producer, branch and consumer before proposing a fix. |
| XLU-D03 / E2 | Sector and USMI alignment overlay | 100% `UNAVAILABLE` | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Observed empty/degraded output; root-cause producer, branch and consumer before proposing a fix. |
| A12 / W1 | Monetisation clock per row | 100% `UNASSESSED_NOT_PUBLISHED`; run never supplies the packet | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Observed empty/degraded output; root-cause producer, branch and consumer before proposing a fix. |
| Design v4 scenario | Per-contract crossing scenario at EOD and Morning | `THESIS_NOT_ACTIVE` on 2,036 rows; 2 assessed | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Observed empty/degraded output; root-cause producer, branch and consumer before proposing a fix. |
| A3 | Hold counts down | Remaining = planned on 2,032 of 2,032 | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Observed empty/degraded output; root-cause producer, branch and consumer before proposing a fix. |
| A8 / needs_codex 1.2 | Contract alternatives | Published on 2,032 rows; no consumer reads that field name | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Observed empty/degraded output; root-cause producer, branch and consumer before proposing a fix. |
| AVS-LEDGER-001 L1 | Stock outcomes on every ledger | Lapsed after 12 Nov | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Observed empty/degraded output; root-cause producer, branch and consumer before proposing a fix. |

### 2.2 Label-only or display-only closures

| ID | Fix | What was actually done | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| D2 / OT-1 | Stop CONFIRMED direction with zero evidence | Display rename; source still writes `DIRECTION_CONFIRMED` | PARTIAL | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | REVIEW-SEMANTICS — Shared DIRECTION_CONFIRMED token means final==governed and validator expects it; not a calibrated probability. Preserve schema compatibility; assess display/calibration separately, see section 10. |
| R6 / "expires before the median move" | Contract family by thesis timing | Flag `CONTRACT_EXPIRES_BEFORE_MEDIAN_TIME` only | PARTIAL | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Separate intended display/shadow policy from missing functionality; no activation to close a row. |
| OT-10.1 | Per-setup within-hold rates | Display only; lane and geometry not switched (ACK decision held) | PARTIAL | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Separate intended display/shadow policy from missing functionality; no activation to close a row. |
| R12 / S2.4 / DF-3 | Freshness gate | Report only, never blocks (ACK 19 Sep) | PARTIAL | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Separate intended display/shadow policy from missing functionality; no activation to close a row. |
| S11.5 / O2 / Item 2 | One valuation core | Shadow valuers only, no authority (by rule 5) | PARTIAL | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Separate intended display/shadow policy from missing functionality; no activation to close a row. |
| E11, R3 | Quote provenance | Evening shadow only; Morning unwired | PARTIAL | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Separate intended display/shadow policy from missing functionality; no activation to close a row. |

### 2.3 Built but not the running path, or switched off

| ID | Fix | Evidence | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| S0.1–S0.3 / P0-3 inc. 1 / R8 | One launcher, RunContext, pre-flight gate | `avshunter/c0_run/` (`198598a`); runs start with `python intelligent_orchestrator.py` | YES-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Prove actual launch/call/config path and missing output; preserve deliberate policy disablement. |
| OT-10x | Exact-option outcome capture | Env switch default "0" | YES-REPORTED | RECHECK-BASELINE | POLICY-DISABLED | NOT-REVERIFIED | NOT-EVIDENCED | OBSERVATION-ONLY | P1 — Prove actual launch/call/config path and missing output; preserve deliberate policy disablement. |
| F2, POB 1, POB 1B | Broker-side quote check; tastytrade read-only bridge | Scripts exist; nothing calls them | YES-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Prove actual launch/call/config path and missing output; preserve deliberate policy disablement. |
| USMI-VALIDATE-STEP | Validate each USMI packet before the Evening | Script exists; no runner step | YES-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Prove actual launch/call/config path and missing output; preserve deliberate policy disablement. |
| SOR feature reader, mode/phase key | As-of feature window; `wyckoff_mode_phase_key` | No production importer | YES-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Prove actual launch/call/config path and missing output; preserve deliberate policy disablement. |
| DSC-01/02/03/07/10/11/12/19/24, VNG-03, `side_assign_v1` | DIR-002 symmetric evidence on the legacy stack | Shadow; stack retired from authority on 7 Oct | YES-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Prove actual launch/call/config path and missing output; preserve deliberate policy disablement. |
| TEV Slice D, register 9 | C6 in one owner; Morning revision service | Two modules remain | YES-REPORTED | RECHECK-BASELINE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P1 — Prove actual launch/call/config path and missing output; preserve deliberate policy disablement. |

### 2.4 Only on another branch

| ID | Fix | Evidence | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| LAB-TIMING | Timing stage skipped on the trusted-receipt path | `b48db74` on `fix/lab-timing-publication-20261116`; also uncommitted in the working tree | YES-REPORTED | OTHER-BRANCH-VERIFIED | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P0-BASELINE — Reconcile branch ancestry, patch and interfaces after commit completion; no blind cherry-pick. |
| TR-016 | Production eligibility gate | `eb50549` on `fix/production-eligibility-20261112` | YES-REPORTED | OTHER-BRANCH-VERIFIED | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P0-BASELINE — Reconcile branch ancestry, patch and interfaces after commit completion; no blind cherry-pick. |
| G1 note | IV-surface root-cause note and characterisation test | Untracked in worktree `nice-wozniak-f2ce1d` | YES-REPORTED | OTHER-BRANCH | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P0-BASELINE — Reconcile branch ancestry, patch and interfaces after commit completion; no blind cherry-pick. |
| Phantom findings doc | Change list 1–11 | Untracked in worktree `affectionate-brattain-10941c`; in no branch | YES-REPORTED | OTHER-BRANCH | UNKNOWN | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P0-BASELINE — Reconcile branch ancestry, patch and interfaces after commit completion; no blind cherry-pick. |

### 2.5 Historical local/uncommitted findings — reconciled to `f3e199e` where evidenced

| ID | Fix | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|
| TRIAGE-T1, T2, T3, T5, T6, T7a–d, PEER, RETENTION | Board per-ETF intelligence file, join to the hand-off, `avs_day` and runner wiring, `check_triage` macro check, Day story names, T7 intelligence, `EW_SECTORS` peer, 10-session clean-up | YES-REPORTED | ANCESTOR-VERIFIED c0d5a45 | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | VERIFY — Committed board-to-triage source; real-session population/display acceptance remains separate. |
| SCHED-CONTROLLED, PREOPEN-1200, POSTCLOSE, EARLYCLOSE | One controlled scheduler, 12:00 UK pre-open, +30 min post-close, exchange-calendar guard. Source files now tracked at `b44d96e`; actual scheduled firing/acceptance remains separate | YES-REPORTED | ANCESTOR-VERIFIED b44d96e | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | VERIFY — Scheduler source now tracked/clean; do not infer scheduler registration or first scheduled-run acceptance from commit. |
| GATE-FRESHNESS, BUDGET-PAID-SLOT, BUDGET-AXJO, BUDGET-MISSING-CLOCK | FULL build stops on a stale refresh; preflight stops cost nothing; ^AXJO dropped; missing bar clock handled | YES-REPORTED | ANCESTOR-VERIFIED b44d96e | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | VERIFY — Tracked source and commit-reported aggregate tests; unchanged policy/actual runtime effects need scoped acceptance. |
| COST-CAP, COST-PROMPT, CASHIDX, FUNDFLOW-CONTRACT | Daily API cap; prompt compaction; cash index collector; fund-flow file contract (no source file yet) | YES-REPORTED | ANCESTOR-VERIFIED b44d96e | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | VERIFY — Source committed; cap decision confirmed USD 4 by f3e199e. A contract file does not supply absent fund-flow data. |
| RECOV-USMI-PARTIAL, RECOV-CHAT-ALIASES, RECOV-PICKUP | USMI PARTIAL label accepted; producer chat aliases; 10-minute pickup window | YES-REPORTED | ANCESTOR-VERIFIED b44d96e | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | VERIFY — Recovery source committed; unattended originals/producer-delivery acceptance remains separate. |
| BOARD-DISPLAY-1117, FRED-TEST | Absolute returns first and stale banner; corrected FRED test | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P0-BASELINE — Recheck final commit/file status and scheduler imports after ongoing commits; not a current blanket uncommitted claim. |
| IVH-3 | 30-day constant-maturity ATM IV (`_layer3_atm_iv_fields`, `garch_runner._layer3_iv_observation`) | YES-REPORTED | ANCESTOR-VERIFIED 5b3d518 | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | VERIFY — IV30 implementation committed, but late success-only estimator/forecast delivery gaps remain VOL-02/03; do not close by commit. |
| avs_verify v1.4 | Phase contract and R24 rule (reports already stamped v1.4) | YES-REPORTED | ANCESTOR-VERIFIED b4ad1b5 | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | VERIFY — Verifier source tracked/clean; does not certify fixes or baseline forward performance. |
| B7 `_b1` path fix | `today_context` paths blank on 20 Nov although the files exist | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P0-BASELINE — Recheck final commit/file status and scheduler imports after ongoing commits; not a current blanket uncommitted claim. |

### 2.6 Waiting on a manual step or real-session acceptance

| ID | What is owed | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|
| TRIAGE-T4, USMI-TEXTFLAG-PROMPT | ACK pastes the prompt text into the chat automations; no evidence it was done | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Acceptance/operational evidence owed; do not equate pending real-session evidence with absent implementation. |
| TRIAGE-E2E | T3–T5 acceptance on one real session (20 Nov context was written after the triage ran) | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Acceptance/operational evidence owed; do not equate pending real-session evidence with absent implementation. |
| UAT-01/02/03 | Close-capture rules live only in the retired local script; the post-close monitor prompt has not adopted them | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Acceptance/operational evidence owed; do not equate pending real-session evidence with absent implementation. |
| DELIV-CLOUD, RECOV-PICKUP | Unattended cloud-to-local export not yet observed | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Acceptance/operational evidence owed; do not equate pending real-session evidence with absent implementation. |
| SCHED-PREOPEN-1200 | First scheduled 12:00 UK run is Mon 23 Nov | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Acceptance/operational evidence owed; do not equate pending real-session evidence with absent implementation. |
| MPW / Dec 6 | Morning gate any time in market hours: five-session forward acceptance owed | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Acceptance/operational evidence owed; do not equate pending real-session evidence with absent implementation. |
| E1 (remainder) | Instrument identity first increment is live, but 2,206 of 2,746 rows are `UNASSESSED_CLASSIFICATION_DATES` | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Acceptance/operational evidence owed; do not equate pending real-session evidence with absent implementation. |
| Open 5 (17 Sep) | Acceptance against reality on forward sessions for the September fixes | YES-REPORTED | RECHECK-BASELINE | PARTIAL/DEGRADED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | P2 — Acceptance/operational evidence owed; do not equate pending real-session evidence with absent implementation. |

---

## 3. Historical bucket: reported committed and wired

Original audit reported committed on this branch and wired. Reconcile against the final baseline. This is not a passing-test or forward-acceptance certification.

### 3.1 Contract and options

| ID | Fix | Commit | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| E1/E2 (Sep), S10.4, DM-16 | Only two-sided contracts within the spread limit | `7210a50` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| E3/E4, E5, E7, L1–L3, DM-22, S10.6 | Missing prices stay missing; wrong-side contract removed; invalidation side-checked; fields describe the written contract | `45bcd7d`, `ff2c035`, `e0fa763` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| E6, D3, S9.5, DM-06, XLU-D01 | No invented 3R target; reachable target published | `7210a50`, `d1ee309` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| R:R removal, XLU-D13 | R:R out of every score and gate | `d1ee309` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| G4 / D4a / DM-14 / OA 1e | Provider Greeks published; Heston display-only; source labelled | `666f09c` (live: `PROVIDER_EOD_CHAIN` on 2,032 rows) | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| G5 items 1–2, UAT-06/07 | Card and Lane B priced American with the run's live rate; owned CRR tree; `--as-of` | `c175576`, `5b4fc6a`, `245e87c` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| G9-GUARD | Test blocks any new pricer | `c175576` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| S10.1c, DM-20, DI Fix 2, XLU-NF-2 | Source-aware IV-percentile owner; full comparable daily history still outstanding | `61c16b9`, `f368d47` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | VERIFY-DECISION | VERIFY — Resolver exists; cited run: 2,181 IV_HISTORY all SHORT_HISTORY, 2 RV_RANGE_PROXY, 2 unavailable, 561 blank. Daily comparable IV30 still VOL-04. |
| DI Fix 1b, 3, 4, D5; GEX-D1 | `rr_options` state; side-constrained walls; gamma flip from signed gamma; sizing reads IV percentile | `f9a7985`, `f368d47` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| OT-3, OT-4, OT-5, OT-6, OT-7 | Geometry block; one card valuation engine; SPY gamma alias removed; IV labels; gamma-weighted walls | `1f37f1c` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| OA 1a–1d, Slice 2 | Vega risk units; put "too late" check; signed breakeven; EV v2 off display; contract analytics block | `d1ee309` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| Anticipated move steps 1–5 | Earnings as disclosure; anticipated fields; runway on the anticipated level; "does the move pay" flag | `d1ee309` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| EV3-OPT3 D1/D2, MEM-swap, MEM-weekend | EV3 at hold plus move window; Morning swap writes new strike/expiry/DTE; quote age is a label | `d1ee309` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| GARCH-D1 / D13 / TR-008 | Cumulative expected moves at 5, 10, 20 sessions | `3bd7ecf` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| L3-a/b, V5–V7, DQ-12 | Forecast fallback chain; governed bounds; structural-break history | `202836b`, `db2d807`, `e1ce260` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| Design v4 shadow, R1, Design 15.7 | Crossing shadow comparison; unrounded return; crossed quote graded C | `fc5faee` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| Dec 6 / MPW | Morning gate runs any time in market hours | `d1c770c` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |
| XLU-D04, D10, D11 | Compression flags rich IV; phase/event categorise only; confirmation needs a material move | `d1ee309` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported live contract/valuation fix: recheck effective code, consumer outputs and narrow acceptance scope. |

### 3.2 Discovery, Vanguard, thesis

| ID | Fix | Commit | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| P0-01, 03, 04, 06, 07, 09; redesign Phases 1–5 | One story per thesis; thesis owns side; event triggers; Vanguard as context; no 2,000 cap; drop-off audit | `1f37f1c`, `2efec78` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| E11b / R11 / O5 | One rank owner `domain/opportunity_rank.py` | `1f37f1c` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| OT-11 station 1 | Discovery tier, order and horizon from the thesis | `1f37f1c`, `08c5a26` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| VNG-01, 02, 05, 06, 11, 12, 17; DM-02 | Thesis context into Vanguard; no CALL default; point-in-time query; typed empty samples | `d1ee309`, `1f37f1c` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| DWN-01, 02, 04, 05, 06, 08, 12, 13, 16 | Options and C5 read the thesis side; retired vote families | `d1ee309` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| BEH-001 A2-2, R-01..05, C-01..04, C-07, RQ-1/2 | Weekly and monthly timeframes; candidate ledger; no fixed 20-session hold; no price gate | `d1ee309`, `f8dd20a` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| DSC-13, 15, 20, 21 | Tier-0 never overwrites; typed eligibility codes; scan errors as rows; macro to advisory fields | `d1ee309` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| `308c166`, `43356a8` / DM-38, `2c224e9`, `dc0e5af`, `2102fd8` / DM-03, DM-27, `39f1ca8` | Field ownership; Discovery owns horizon; sector/momentum inputs; physics on measured inputs; vol regime rule | as listed | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| M-REVIEW-01 | Morning authority from the thesis | `1f37f1c` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| Phase 8 F1–F5, A-step 2, B4.2 / R1, R3 / L7 | Intraday coverage states and catch-up; OBSERVED/INFERRED labels; event clocks; opportunity ledger | `2efec78` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| A2, D2, D3 (25 Sep), INT-001 H1/H2 | No-quote label; manifest grain; book-stability diagnostic | `34c0fef`, `8ecb831`, `bb4cf50` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |
| OT-8, OT-9, OT-10.2/10.3/10.4, TR-015 | Disposition journal; earnings tiers; station inspections and quarantine; scorecard; forward calibration report | `1f37f1c`, `ff694d7` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported discovery/direction fix: verify propagation into cards/Morning and interactions with retained legacy code. |

### 3.3 Measurement, data, Phantom

| ID | Fix | Commit / evidence | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| P0-2 | Configuration registry (all values PROVISIONAL) | `8635ca1` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| P0-8, S17.2–4, C4 labels, R10 | Outcome scorer runs after every Evening | `1912f75` … `6d73429` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| P0-4 slice 1, S2.2, GEX-D9 | Open tickets keep daily marks; chain adapter date rule | `8a4b011`, `5f23e40` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| P0-1, F7 data, IVH-1 | History backfills (data) | Receipts | YES-REPORTED | EVIDENCE-NO-HASH | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| S2.6, `cdedf20` | IV history every evening; readiness report | `cdedf20` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| PH-1, 3 (6/7/14 Oct), 4, 5, 7, 8, 10; MEM-backfill | Missing Greeks computed (5.5M rows); provenance labels; every write path completes Greeks and IV; open-interest policy recorded | `7effc2b`, `79c5983`; 0 `PENDING_IV` live | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| IVH-2 / DF-1 | Evening captures about 2,650 tickers on run nights | Since 19 Oct | YES-REPORTED | EVIDENCE-NO-HASH | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| BF-safe, BF-B, BF-path, MR-1111 | Guarded backfill for 20 Oct and 9 Nov; named-contract and path supplements; 11 Nov repair | `79c5983`; receipts | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| GEX fallback | Chain session roll with labelled sentinel | `gamma_exposure_store.py:174` | YES-REPORTED | EVIDENCE-NO-HASH | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| PKG-002 P1–P4c | Manifest mode, package-free Evening | `1a06988`, `913b8ce` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| Artifact retention | Artifact-level retention | `23ad527` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |
| S0.7c, S16.2 | Untracked production import committed; old UI copies quarantined | `d1a1a09`, `43136b1` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported measurement/data fix: verify lineage, completeness, actual receipt scope and quality on final baseline. |

### 3.4 Lab, Lane B

| ID | Fix | Commit | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| LAB-004 S1–S3, accuracy 1–6, H1 | Review projection and UI; accuracy fixes; execution-gate columns | `5864ff1` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported UI/handoff fix: cold-load/consumer/record consistency; live output does not establish outcome benefit. |
| Lab bind | Served on 127.0.0.1 at the root page | `2efec78` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported UI/handoff fix: cold-load/consumer/record consistency; live output does not establish outcome benefit. |
| B0–B7, B10, TR-012, focus list, X17 tiers (TR-004) | Hand-off built from the Lab; packs; decision records; focus list; 11 Nov tiers | `1e43e6b` … `208e1d2` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported UI/handoff fix: cold-load/consumer/record consistency; live output does not establish outcome benefit. |
| E1/E17 increment 1, E16 | Instrument identity fields; leveraged/inverse labelled research-only | `4010d4d` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported UI/handoff fix: cold-load/consumer/record consistency; live output does not establish outcome benefit. |
| AVS-TRACE-001, usmi duplicates | Traceability review; duplicate book columns | `3d460c9`, `4f56bc8` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported UI/handoff fix: cold-load/consumer/record consistency; live output does not establish outcome benefit. |
| S1-2a/2b | Dead Phantom layer removed; Phantom writes only its own fields | 7 Oct | YES-REPORTED | EVIDENCE-NO-HASH | YES-REPORTED | 2-NARROW-PASS | NOT-EVIDENCED | OBSERVATION-ONLY | VERIFY — Two Phantom ownership tests passed in 20.69s; no score-threshold or economic validation implied. |

### 3.5 Macro

| ID | Fix | Commit | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| DELIV-INTAKE, DELIV-USMI-V2, USMI-TEXTFLAG-CONTRACT | Manifest intake and receipts; USMI v2 schema; text flags through a fixed vocabulary | `ca060b7`, `1f37f1c` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported macro fix: validate timestamps, delivery and intelligence scope; do not silently alter trade decisions. |
| FRED-TERMPREM, FRED-USSLIND | FRED latest-public-release policy | `ca060b7` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported macro fix: validate timestamps, delivery and intelligence scope; do not silently alter trade decisions. |
| Board gaps G1–G9, G11–G15, G18 | Dates, labels, archive, implied move, intervals, holdings, desk card | `46d28f7`, `c086806`, `1789870` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported macro fix: validate timestamps, delivery and intelligence scope; do not silently alter trade decisions. |
| REPLAY-H10 | Dollar condition respects its release day | `278d8b8` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported macro fix: validate timestamps, delivery and intelligence scope; do not silently alter trade decisions. |
| MDI-P0, MDI-09, MDI-11 | Input manifest and hashes; breadth input; events through the delivery ledger | committed | YES-REPORTED | EVIDENCE-NO-HASH | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported macro fix: validate timestamps, delivery and intelligence scope; do not silently alter trade decisions. |
| OWN-PER-ETF, OWN-CANDIDATE-MAP, OWN-LOCAL-SPLIT, OWN-LATEST-WINS | Plan and Money Index per ETF with measured correlation; candidates mapped to their ETF; measured sheet local; newest packet wins | `bad3355`, `ca060b7` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported macro fix: validate timestamps, delivery and intelligence scope; do not silently alter trade decisions. |
| E1 (25 Sep), D6/D7, Scenario M8 | Unsourced convexity hidden; GEX no longer scales size | `ad04778` | YES-REPORTED | ANCESTOR-VERIFIED | YES-REPORTED | NOT-REVERIFIED | REPLAY-REPORTED | VERIFY-DECISION | VERIFY — Reported macro fix: validate timestamps, delivery and intelligence scope; do not silently alter trade decisions. |

---

## 4. Codex plans of 21 November (reviewed as requested)

Files: `Documents\Codex\2026-11-21\re\outputs\GARCH_ordering_and_IV_benchmark_fix_plan.txt` (with Appendix VOL-1) and its companion `PHANTOM_root_causes_and_fix_plan.txt`. Both are design proposals. **Every item is Outstanding — designed, awaiting ACK approval.**

### 4.1 What I confirmed against the code

| Claim | Check |
|---|---|
| Forecast runs after Options Intelligence and after EIL; an EIL failure skips it | Confirmed: `intelligent_orchestrator.py:6880-6892` |
| The runner takes its ticker list from the post-OI SuperBrain file and uses `date.today()` | Confirmed: `garch_runner.py:27, 99, 365` |
| The 30-day IV benchmark is computed at one place only, after the early returns | Confirmed: single call at `avshunter_options_intelligence.py:9223` |
| The prior-forecast lookup has no maximum age | Confirmed: `_l3_forecast_on_disk` `:5949` |
| Selector forecast source is UNAVAILABLE on 2,032 rows | Confirmed independently by the change-register audit (B1 dead) |
| Phantom score cannot exceed about 67.5 | Confirmed: `_composite` at `phantom_engine.py:125`; 1 − (0.78 × 0.76 × 0.75 × 0.87 × 0.84) = 0.675 |
| 20 Nov has SPY and QQQ chains only | Confirmed by the Phantom audit (also 12 and 16 Nov) |
| 1,075 missing benchmarks; 426 recoverable from stored chains | **Not re-verified.** Codex's replay figures |

### 4.2 Items and how they map to this register

| ID | Fix | Existing register items it closes or overlaps | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|---|
| VOL-01 | Freeze contracts, cutoffs, fixtures | S0.2 RunContext (built, not wired) | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P1 — Design proposal only; dependency and impact review before implementation; no approved blanket build. |
| VOL-02 | Price-only forecast before Options Intelligence; current forecast injected into the valuer | **B1, F1** (dead shadow selection); B1 RCA of 25 Sep already named this as the long-term shape; S0.4 clock | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P1 — Design proposal only; dependency and impact review before implementation; no approved blanket build. |
| VOL-03 | Typed IV result at the chain boundary, on every return path | IVH-3 (uncommitted); gap 1 | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P1 — Design proposal only; dependency and impact review before implementation; no approved blanket build. |
| VOL-04 | 1/5/20-session measures; daily IV30 history; IV percentile with honest coverage | D16, ADD-N2, OT-6, DI Fix 2 (existing IV-percentile owner must be reused) | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P2 — Design proposal only; dependency and impact review before implementation; no approved blanket build. |
| VOL-05 | Better ATM estimator (fixed ±5% band fails on 498 names) | New | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P2 — Design proposal only; dependency and impact review before implementation; no approved blanket build. |
| VOL-06 | Horizon-specific forecast challengers; HAR fit-window audit | C3 (validate the forecast), GARCH-D1, Phase 6 IV/HAR-RV finding | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P2 — Design proposal only; dependency and impact review before implementation; no approved blanket build. |
| VOL-07 | One assessment id consumed by OI, C7/C8, DOI, learning | TEV Slice E, O2, C1 | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P2 — Design proposal only; dependency and impact review before implementation; no approved blanket build. |
| VOL-08 | Release and monitoring | Rule 5 gates | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P2 — Design proposal only; dependency and impact review before implementation; no approved blanket build. |
| PHANTOM-A | Normalise the score in shadow; versioned thresholds | New | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | SHADOW-ONLY | P2 — Unreachable scale confirmed; normalization remains a proposed versioned shadow experiment, not validated threshold economics. |
| PHANTOM-B1 | Truthful coverage health per session and scope | DF-5, UAT-05, S2.4 | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P1 — Design proposal only; dependency and impact review before implementation; no approved blanket build. |
| PHANTOM-B2 | Bounded, credit-capped recovery of missing sessions; generalise the guarded runner | PH-gap, BF-12Nov, BF-old | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P1-PLAN — Acquisition dependencies: final roster/request scope, reuse receipts, explicit cap/recurring allowance; do not call providers under this document. |
| PHANTOM-B3 | Owned recurring fixed-panel acquisition | S2.3, ADD-N1 | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | P1-PLAN — Acquisition dependencies: final roster/request scope, reuse receipts, explicit cap/recurring allowance; do not call providers under this document. |

### 4.3 Review comments before assigning to Codex

1. **The diagnosis is sound and explains a live gap.** VOL-02 is the root cause of B1 producing nothing since at least 14 Nov. That makes VOL-02 and VOL-03 repairs of existing functionality, not new features.
2. **Reconcile the completed baseline before editing.** Those three files were clean relative to HEAD at the later `350e614` inspection. ACK says additional commit work is in progress. Wait for it to finish, record the final revision/effective files, preserve concurrent work and recheck the intended changes. Do not commit or overwrite unrelated work to satisfy this register.
3. **Split the package.** VOL-01 to VOL-03 are plumbing with the method unchanged (about one to two weeks by Codex's own estimate). VOL-04 to VOL-06 are method changes and research; they need pre-registered hypotheses and overlap earlier work (7 Oct direction research, Phase 6, branch `claude/ivs-001-iv-surface`, the G1 note). Check those before the brief goes out.
4. **Two points conflict with standing decisions.** The plan gates quote inputs on freshness and adds a maximum-age policy; ACK's rule is to flag quote age, never gate on it. The IV solver fallback must go through the one pricer (`domain/option_valuation.py`), which today has no implied-vol function (D2 valuation, outstanding), and the guard test will reject a new solver elsewhere.
5. **Authority is respected.** Both plans keep selection SHADOW and Phantom evidence-only, and require rule 5 gates before any decision change.
6. **Credits.** PHANTOM-B2 and B3 need an explicit credit cap from ACK; nothing recurring is authorised today. PHANTOM-A and B1 cost no credits.
7. **Rules that apply to Codex too.** Failing test first, characterisation test for the legacy stage order, no pipeline edits while a run is in progress, acceptance against a real session.

---

## 5. Closed by decision or superseded (not counted as outstanding)

| Items | Closed by | Built | Committed | Wired | Tested | Validated | Authorised | Priority / pipeline impact and implementation comment |
|---|---|---|---|---|---|---|---|---|
| Strangler contexts C2–C10, C14, RAEV/EV_LB, OpportunityBook, Phases 1–5 of the September design, S18.1–2 | D1 (17 Sep), then TEV-001, DIR-002, BEH-001 and the 7 Oct redesign | UNKNOWN | NOT-APPLICABLE | UNKNOWN | NOT-APPLICABLE | NOT-APPLICABLE | VERIFY-DECISION | HOLD — Closed/superseded by a decision: verify exact decision before reopening or building. |
| D4b physics retired | Reversed: physics repaired (`dc0e5af`) | UNKNOWN | NOT-APPLICABLE | UNKNOWN | NOT-APPLICABLE | NOT-APPLICABLE | VERIFY-DECISION | HOLD — Closed/superseded by a decision: verify exact decision before reopening or building. |
| D7 hold, A2 planned-hold rule, 5b0d826 | ACK 28 Sep, 4 Oct, 12–13 Nov (hold stays as thesis runway) | UNKNOWN | NOT-APPLICABLE | UNKNOWN | NOT-APPLICABLE | NOT-APPLICABLE | VERIFY-DECISION | HOLD — Closed/superseded by a decision: verify exact decision before reopening or building. |
| S4.1, D10/D11 (addendum), E5, DM-34, REPLAY-VERDICT | Rule 6 amendment 20 Nov; "latest macro wins" | UNKNOWN | NOT-APPLICABLE | UNKNOWN | NOT-APPLICABLE | NOT-APPLICABLE | VERIFY-DECISION | HOLD — Closed/superseded by a decision: verify exact decision before reopening or building. |
| DM-25 EV3 coverage, D3 (valuation) | EV3 authority stays retired and frozen | UNKNOWN | NOT-APPLICABLE | UNKNOWN | NOT-APPLICABLE | NOT-APPLICABLE | VERIFY-DECISION | HOLD — Closed/superseded by a decision: verify exact decision before reopening or building. |
| ADD-N4 borrow data, B3 short side | No short shares | UNKNOWN | NOT-APPLICABLE | UNKNOWN | NOT-APPLICABLE | NOT-APPLICABLE | VERIFY-DECISION | HOLD — Closed/superseded by a decision: verify exact decision before reopening or building. |
| F3 sizing, Design 15.8 adoption, PH6 exits | Out of scope or tested with no benefit | UNKNOWN | NOT-APPLICABLE | UNKNOWN | NOT-APPLICABLE | NOT-APPLICABLE | VERIFY-DECISION | HOLD — Closed/superseded by a decision: verify exact decision before reopening or building. |
| DSC-04/05/06/08/09/14/17/18/22/23, D1 (25 Sep), SOR S3–S8, WP1 ENV/RAEV | 7 Oct redesign | UNKNOWN | NOT-APPLICABLE | UNKNOWN | NOT-APPLICABLE | NOT-APPLICABLE | VERIFY-DECISION | HOLD — Closed/superseded by a decision: verify exact decision before reopening or building. |
| X17-02 25% spread gate, G5 item 4 local close capture | 11 Nov tiers; post-close monitor is the one writer | UNKNOWN | NOT-APPLICABLE | UNKNOWN | NOT-APPLICABLE | NOT-APPLICABLE | VERIFY-DECISION | HOLD — Closed/superseded by a decision: verify exact decision before reopening or building. |
| H6, G4-open-d, OT-4a, N11 | Recorded as accepted or deferred | UNKNOWN | NOT-APPLICABLE | UNKNOWN | NOT-APPLICABLE | NOT-APPLICABLE | VERIFY-DECISION | HOLD — Closed/superseded by a decision: verify exact decision before reopening or building. |

---

## 6. Not determined in this audit

- **Root causes of the dead outputs** in 2.1 (C1, XLU-D03, crossing scenario, A3). B1 is explained by VOL-02; the others were observed in data only.
- **Items outside the repo:** chat automation prompts, the claude.ai post-close monitor, scheduled-task registration, ChatGPT producers, the research package for the outcome ledger.
- **ACK's original trade-quality register** (pasted 11 Oct) is not a file in the repo. N2, D17 and D5 "pooled probability" have no definition here.
- **Not traced line by line:** S0.6, S15/O6 (one morning service), DM-17/19/21/28, P0-02/05/08, recall losses a–c, VNG-07/14/16, DWN-07/15, GEX-D4/D5/D6, PH-2, PH-9, PH-11, MDI-13/15/16/17/20, E4/E8/E14/E19–E21, ILA-RC-01..08, Decision Register E01–E34.
- **Scheduler deferrals:** 122–185 "DEFERRED: writer active" lines a day on 18–20 Nov; normal contention or a defect is not established.
- **Whether legacy tier and ladder code still reaches the card** after the 9 Oct "legacy classifiers inactive" decision.
- **Uncommitted diffs inside files that also carry committed fixes** were not read, so a cited line may come from the working tree rather than the commit named.

## 7. ACK implementation instruction and whole-pipeline impact review

**Instruction recorded on 21 November:** complete the commit work already in progress before building fixes. This is a whole-pipeline review and prioritisation, not a targeted volatility-only assignment. Updating this document is authorised; starting builds, changing schedules, spending credits, activating models and committing unrelated work are not authorised by the status update.

### 7.1 P0 — mandatory baseline gate before any fix build

Current state: **COMMIT BATCH OBSERVED COMPLETE at `f3e199e`; BUILD HELD BY ACK; BASELINE QUALIFIED WITH KNOWN FIXTURE EXCEPTION AND SCOPED RESIDUALS; NOT A GREEN RELEASE. See section 10.** See section 8 for the evidence and remaining qualifications.

1. Finish the existing commit work with its current owner; do not interrupt, stage unrelated changes, switch branches or cherry-pick fixes underneath it.
2. After completion, record final branch/HEAD, relevant tracked/untracked/dirty files, release/config identity and effective import paths. Compare with the original `ff24d41` and intermediate `350e614` snapshots; neither is automatically the final baseline.
3. Reconcile all rows' Committed fields against that completed baseline, including other-branch changes and new macro/verifier commits. `CITED` means a historical commit reference; `RECHECK-BASELINE` is deliberately unresolved until this step. A clean working tree does not prove correctness, and a running dirty file is not unwired merely because it is uncommitted.
4. Preserve the effective source patch/content hashes for representative Evening and Morning runs, the expected roster and all output/input dataset/config versions. Confirm no pipeline/backfill/maintenance writer before implementation or data work.
5. Read the applicable current business decisions, including amendments that supersede older designs. Attach approved root cause/design and precise acceptance to the first build slice. This register does not reopen closed decisions or approve every proposed fix.
6. Verify a reproducible baseline with relevant existing tests and saved real-session outputs. Record exact commands/results; separate baseline failures from new regressions. Capture producer/consumer missingness and current decision behaviour before changing it.

Build-start evidence to be filled after commits finish: `[final HEAD] [owner/completion time] [effective source/config hashes] [remaining unrelated changes] [baseline commands/results] [approved first slice]`. Do not mark this gate complete on elapsed time or on this documentation edit alone.

### 7.2 Whole-pipeline impact map — required before implementation

The following is a dependency/risk map, not a claim that every runtime branch has already been independently traced. Each work item must attach its own verified path and observed effect after P0.

| Context / station | Current gaps to reconcile | Potential effect on current pipeline | What must be proved before changing it |
|---|---|---|---|
| Launch, RunContext, scheduling and release | S0.*, P0-3, replay, scheduler/untracked imports, writer contention | Wrong session/config or competing writers can invalidate every downstream result | Actual launch/import/config path for Evening, Morning and scheduled jobs; final source identity; reproducible session clock; no competing writer |
| Universe, prices, canonical market data | P0-5/10/11, outliers, stale caches, fixed capture panel | Missing/stale/invalid inputs change who is assessed and contaminate historical evidence | Expected population and exclusions, point-in-time identity, adjustment/outlier handling, exact source cutoff; no guessed symbol aliases |
| Discovery and thesis/direction | DIR/DV/BEH, no-CALL-default paths, phase/tier leakage, missing geometry | Incorrect side/horizon/levels can propagate into contract selection and Morning | Trace accepted thesis -> Vanguard -> OI -> EIL/card -> Morning; count and explain any direction/horizon/level change; verify whether legacy branches are actually reached |
| Vanguard and actuarial evidence | Builder ownership, outliers, floors/match keys, sample freshness | Unsupported probability/evidence or defaults may affect scoring and confidence | Effective query/builder inputs, clean history, missing/sample states, live consumers; no scalar probability renamed as calibration |
| Options acquisition, Phantom, IV/GEX and forecast | Capture gaps, missing underlying, benchmark early returns, VOL-02, units/defaults | Available evidence is discarded, stale evidence substituted, or forecasts arrive after valuation | Separate acquisition/projection/derivation/consumption; same-session data identities; explicit unusable states; source units and GEX convention; independent fixed-panel denominator |
| Contract valuation and economics | B1/F1, C1, shared solver/pricer, exit IV/spreads/dividends, expiry/runway | Option payoff, attractiveness and selected-versus-alternative comparison may be wrong or unassessed | Same contract/thesis/clock/costs before/after; actual consumed forecast and quote; valid source-aware Greeks; shadow versus active consumer; quantify payoff/selection differences |
| EIL, execution readiness and Morning | CALL fallback, synthetic verdicts, clock/trigger/crossing defects, advisory aborts | Could alter readiness or stop a run without a business-authorised reason | Reachability of each branch, authoritative field owner, no silent direction reset; distinguish diagnostic failure, data unavailability and a new trade gate |
| Lab, Lane B and handoff | Naming mismatch, absent clock/scenarios, repair conflicts, cached displays | Card/handoff can hide or misstate already computed evidence; downstream research may consume the wrong fields | Producer -> projection -> API/template -> Lane B field names/grain; cold-load actual session; compare displayed and source values; downstream records/outcomes linked |
| Decision ledger, outcomes and learning | Existing C11/C13 completeness; option capture disabled; support/metrics absent | Cannot reliably learn option economics or validate improvements despite many underlying records | Exact assessment/contract linkage, target-specific maturity/fit support, hypothetical vs fills, held-out metrics and authority; reuse existing owners |
| Macro, events, USMI, board and triage | Freshness/delivery/funding, component gaps, T7 display, scheduled acceptance | Intelligence may be missing/stale even when analysis exists; scheduler/cost changes can affect run availability | Validate source/observation times and delivery before display; preserve current intelligence scope; separate permitted review ordering from changes to pipeline direction/score/rank/selection |
| Retention, UI security and hygiene | Backups, CORS, launchers, duplicates, hardcoded imports/paths | Lost reproducibility, accidental exposure or deletion; wide changes can break unrelated paths | Inventory references and actual access before changes; prove restoration/replay; do not delete 'redundant' data or bulk-retire legacy code merely from an old register label |

For each candidate build, attach: producer, consumers, live entry point, impacted population and count, fields/units, existing behaviour, intended behaviour, outputs that should change, outputs/authority that must be preserved, downstream tests, rollback and observable business acceptance. An empty column or static code match is a symptom until the producer-to-consumer cause is traced.

### 7.3 Implementation priority — after the P0 gate

Priority denotes dependency and consequence, not permission to build. Unknown impact gets an investigation task before a production patch. Not every P1 item should be built simultaneously.

| Order | Work package / register items | Why this order and current-pipeline impact | Acceptance before proceeding |
|---|---|---|---|
| P0 | Finish commit baseline and reconcile status/decisions across the register | Avoid implementing against moving/uncommitted interfaces or rebuilding superseded work | Final baseline receipt and exact approved first slice; no implicit completion |
| P1-A | Trace decision-integrity paths: H2 CALL fallback, active direction/geometry/default branches, quote/contract identity, synthetic EOD readiness, advisory abort paths | Highest potential consequence is a wrong side/contract/readiness decision or avoidable run abort. Presence alone does not prove the branch is hit | Saved real-session path trace, affected rows and precise root cause; failing characterisation/business test; no new veto or authority introduced |
| P1-B | Data-truth/control: capture health/panel, source clocks/outliers, Phantom provenance/missing underlying, baseline source/config receipts | Bad input invalidates forecasts, valuation and outcome evidence; solve observable control/measurement before tuning models | All expected populations accounted for by scope/session, source quality explicit, no hidden defaults; paid recovery scoped/capped separately |
| P1-C | Restore existing evidence delivery: VOL-01..03/B1/F1; diagnose C1 scenarios, crossing, A12 clock and XLU-D03 alignment through their consumers | Dead outputs mean the pipeline cannot use data already collected. Current forecasts before OI are a concrete repair, not permission to activate shadow selection | Current forecast consumed before dependent valuation; all IV paths publish reasoned states; each other dead output has its own cause/consumer test and saved-session acceptance |
| P1-D | Operationalise existing outcome path: exact-option capture/linkage, actual source snapshots, target-specific mature outcomes | Needed to tell whether P1 fixes improved option decisions, not just labels; existing underlying records are not option P&L | Reconciled eligible/observed/missing outcomes, exact identity and cutoffs; no guessed losses/returns; support and authority explicit |
| P2-A | Shared valuation/IV inversion, dividend/exit-IV/spread issues, expiry/hold compatibility | Correct inputs must pass through consistent economics; otherwise improving a forecast cannot establish a better contract assessment | Approved shared owner/API; matched-input payoff replay and real observations/costs; keep selector SHADOW unless separately approved |
| P2-B | VOL-04..06: exact 1/5/20 measures, comparable daily IV30/percentiles, ATM interpolation and horizon-specific model challengers; Phantom score-scale shadow experiment | Measurement/model changes need clean data and known baseline; normalising a score is not proof of calibrated decisions | Pre-registered method comparison, chronological/forward evidence, units/cadence/support disclosed; changes isolated from plumbing |
| P2-C | Lab/Lane B publication conflicts, alternatives/cluster/clock names, macro intelligence display and delivery gaps | Ensure evidence reaches the human and downstream record correctly; independently urgent reliability defects can move earlier with evidence | Source-to-display and handoff equality on real sessions; scope/authority preserved; cold-load acceptance; scheduler acceptance separate |
| P3 | Independent model/economic acceptance, approved release, monitoring and rollback per context | Prevent tested code or richer output being mistaken for improved decisions | Held-out and prospective evidence matched to the specific change; operator approval and versioned rollback; no automatic authority |
| P4 | Broad refactors/deletions, hardcoded-path/import cleanup, legacy engine retirement and backup removal | Large blast radius and weak immediate benefit unless an actual live failure is demonstrated | Baseline coverage, verified references/dependencies and approved retention/retirement criteria. Escalate a specific live risk by evidence rather than postpone it categorically |

Parallel investigation/design is possible after scope is agreed; shared-file implementation must be coordinated against the completed baseline. Fix one approved causal slice at a time, preserve unrelated changes and rerun the necessary downstream checks. Do not blindly merge other-branch fixes or switch every disabled feature on.

### 7.4 Independent-review comments incorporated

1. **Ledger and learning correction:** C11/C13 implementations and orchestrator calls exist. On 19 November the learning snapshot contains 255,772 completed records (not independent trades), 20,457 fit-eligible, all `UNDERLYING_ONLY`, zero option labels; held-out metrics missing, short-horizon strata deficient, activation disabled. This validates specific outstanding linkage/support/acceptance work, not building a duplicate ledger or learner.
2. **IV-percentile qualification:** the resolver is implemented, but `iv_percentile` can still carry a labelled RV-range proxy. Cited run: 2,181 `IV_HISTORY` rows, all `SHORT_HISTORY`; two `RV_RANGE_PROXY`, two unavailable, 561 blank. Keep source/cadence/support in every consumer. A full comparable daily series remains outstanding.
3. **Volatility evidence:** 1,075 missing benchmarks/426 arithmetic recovery candidates come from the previous archived diagnostic, subject to source/quality validation. They are not 426 provider-verified values. Stage-order repair is confirmed, but other missing geometry/model inputs may remain after it; do not promise B1 is wholly resolved by ordering alone.
4. **Quote age and current evidence:** respect the standing 'flag quote age, never gate on it' business decision. No new age-only trade/contract exclusion is approved here. Explicit source age/session and refusal to label old data 'current' remain necessary. Any proposed model-use rule that changes an existing consumer's decision must identify the policy conflict for decision; future-data/identity/crossed-quote defects are distinct integrity issues.
5. **One pricing owner:** local IV solving must use/migrate to the approved shared `domain/option_valuation.py` owner; its shared inversion API is a dependency, not an excuse to add another solver. The G9 guard recognises price inversions and listed legacy copies. Keep legacy migration and new estimator method changes separately testable.
6. **Status evidence:** two existing Phantom ownership tests passed in 20.69 seconds in the independent assessment. They prove only that tested ownership behaviour; they do not validate score thresholds or trading benefit. No full-suite or universal forward-acceptance claim is made.
7. **Baseline protection:** a cited commit and a dirty live run describe different releases. Intermediate `350e614` corrected some historical uncommitted warnings; ACK's ongoing commits still must finish before builds. This document must be reconciled against the final result, not used to force a bulk commit.
8. **Authority:** intentionally shadow/observation-only functionality can be correctly built and wired. Do not turn it active to make the status green. Keep model/score/selection/execution authority per context and business decision.
9. **No targeted blind spot:** the earlier independent review was targeted; this amendment does not pretend it certified every runtime path. It expands the register and implementation prerequisites to the whole pipeline and requires each affected producer/consumer path to be assessed before patching. Section 6's unverified areas remain explicit work, not silent closures.
10. **Credits and external systems:** acquisition, recurring schedules, broker integrations and cloud prompt changes retain their existing permissions. A proposed fix, dependency or priority is not permission to spend, send, trade, delete data or edit external automation prompts.

### 7.5 Closure contract for every fix

A row can be closed for its **declared scope** only with a root cause, approved intended behaviour, completed source baseline, producer/consumer impact assessment, versioned implementation, passing relevant tests, recorded real-session/replay acceptance, any required forward/economic acceptance, exact authority and rollback. Administrative/documentation fixes may have narrower acceptance than predictive changes; do not demand predictive edge from intelligence-only display work.

Record actual before/after counts and decisions, not only a green test result. Preserve the original run and append corrected assessment revisions. If the fix changes direction, contract selection, ranking, sizing or execution permission, identify and obtain the required business authority before release. If it merely corrects displayed facts, verify equality to source and consumer behaviour under the applicable rule.

**Next action after reconciliation: resolve remaining baseline qualifications and review the proposed first build slices in section 8. ACK’s instruction remains: do not start building yet.**

## 8. Reconciled committed baseline and proposed first build slices — 21 November

**Observed commit baseline:** `laneb/lab-first-handoff` at `f3e199e636d93591065ebd6d0a2b6c4c6435f028`, committed 11:33:59 UTC. Repeated checks showed stable HEAD, nothing staged, no index lock and no Git process on the later snapshot. The commit batch **appears complete**; no external owner completion receipt was supplied. This is an observed committed-code baseline, not a clean-release or investment-validity certification.

**Build state: HOLD — ACK explicitly requested no building yet.** No code, model, agent, schedule or provider work was started by this reconciliation. If HEAD/relevant source changes, requalify the baseline.

### 8.1 Status reconciliation

64 distinct backticked commit references resolved: 62 are ancestors of HEAD, two exist but are not ancestors (`b48db74`, `eb50549`). `ANCESTOR-VERIFIED` in a row verifies the cited history relationship only; it does not certify runtime wiring, effective source equality, test success or outcomes. `EVIDENCE-NO-HASH` means an original reported closure has no independently resolved row-level commit reference. `OTHER-BRANCH-VERIFIED` is not permission to cherry-pick. Preserve the other six status meanings.

| Change | Reconciled commit/source state | What remains open |
|---|---|---|
| IV30/GARCH source | `5b3d518`; runner/OI files tracked and clean at inspection | Ordering/early-return/method/quality gaps remain; committed is not repaired |
| Final code receipt / Lab publish ordering | `b5d346d`; orchestrator tracked/clean | Verify actual consumed input/output receipts and real-run acceptance |
| Verifier phase/scope v1.4 | `b4ad1b5`; tracked/clean | Not proof every upstream fix passes |
| Macro triage T1–T7 | `c0d5a45` exists on HEAD history | Per-field output/display and scheduled acceptance remain distinct |
| Scheduler/refresh/budget/recovery | `b44d96e`; `Run-MacroSchedule.ps1`, `scripts/scheduled_macro_builds.py`, `contracts/macro_api_cost.py` now tracked/clean | Actual registration, first-run acceptance and known baseline test issue |
| Daily API cap | `f3e199e`; ACK decision USD 4/day; cost tests reported 16/16 in commit | No new provider budget or recurring authorisation is granted by this review |
| Lab timing / production eligibility | `b48db74` / `eb50549` not ancestors | Check equivalent committed/working-tree implementation and compatibility; no blind merge |
| Isolated trading-SME agents | External candidate source exists; exact production paths `contracts/lab_trading_sme.py` / `contracts/lab_main_idea_workflow.py` not tracked | Candidate freeze, qualification/evaluation/domain acceptance and explicit deployment approval |

Residual tracked changes: this register, two 2 October outcome reports, three interpreter-backup file deletions. Untracked research/data/prototypes and `data/scratch/workaround/strategy_layer.py` remain. Do not stage/discard/restore/delete them here. The baseline receipt records their paths; investigate runtime relevance rather than assume untracked means unused. A completely clean repository has **not** been established.

`b44d96e` reports 220 passing tests in 17 files and two known failing files. `f3e199e` addresses the three API-cap test failures and reports 16/16 passing. Section 10 now reproduces and diagnoses the `test_macro_completion` missing-fixture-config failure. The checked-in test remains 1 failed/5 passed; a workspace-only corrected-fixture diagnostic passes without weakening the FULL guard. These are commit-reported results, not a fresh test run in this task. Existing two narrow Phantom ownership passes remain the only independently rerun tests cited by this review.

### 8.2 First fixes proposed, with current pipeline impact

| Sequence | Fix / work item | Impact on the current pipeline | Build boundary / prerequisite |
|---|---|---|---|
| 0 — qualify | Residual-file disposition, final source/config hashes and known baseline test failure | Prevents apparent regressions from mixed source versions or incomplete fixtures | Verification first; do not change production behaviour to satisfy a broken fixture. User build hold remains |
| 0 — risk trace | H2 CALL fallback, active direction/identity/default branches and advisory abort paths | Potential wrong side/contract/readiness or avoidable run abort has highest consequence | Trace saved inputs and active callers first. A confirmed reachable wrong-side defect takes priority; no speculative blanket patch |
| 1 — first concrete engineering slice | VOL-01..03 / B1/F1: price-only current forecast before OI; typed IV assessment on all chain paths | Restores evidence for shadow contract valuation, reachability and DOI; stops a later merge pretending an earlier assessment used current data | Method unchanged, current session/cutoff/consumed IDs; preserve direction/selection/authority. Other geometry/model inputs may remain unavailable |
| 2 — truthful delivery | PHANTOM-B1 plus individually diagnosed C1/crossing/A12/alignment/Lab-Lane B field gaps | Distinguishes unassessed/missing from negative signals and exposes which evidence reaches cards/handoffs | Separate producer/consumer root cause for each dead output; no manufactured scenarios. Paid capture separate |
| 3 — outcome linkage | Existing OT-10x/C11/C12/C13 exact-contract linkage/capture policy | Enables validation of option economics and selected/nonselected comparisons, rather than relying only on stock outcomes | Reuse existing owner; no blind env-flag activation. Identity/maturity/data-availability/costs explicit |
| 4 — shared economics | G5/G9/D2 shared IV inversion, dividends/exit/quote cost semantics | One basis for pricing/IV and interpretation of whether a move pays | Approved shared pricer API; preserve quote-age policy. Not needed just to carry existing vendor IV through an early return |
| Later, separate experiment | VOL-04..06 / Phantom scale shadow | Better 1/5/20 measurements, history/percentiles, ATM estimate and forecast models | Clean baseline, pre-registered out-of-time/forward comparisons; no mixing formula/model/authority changes with plumbing |

This is an implementation proposal, not authorisation to start. Backend fixes need not wait for agent deployment. Conversely, agent prose must not be used to disguise missing backend capability.

## 9. Agentic build reconciliation — incorporate fixes through facts, roles and acceptance

### 9.1 Actual candidate and limits

Reviewed the isolated `AVSHUNTER_Trading_SME_v1_2026-11-19` package, Personas v2, `TRADING_SME_CURRENT_SCOPE.md`, `TRADING_SME_ACCEPTANCE_v1.json`, `src/contracts/lab_trading_sme.py`, `CONTEXT_CONTRACT_README.md` and `MAIN_IDEA_DEPLOYMENT_PATH.json` in the architecture-review chat outputs. This is the relevant agent candidate, not a fresh swarm or the older August automation options paper.

- Interpreter: evidence-led trading-SME analyst. Challenger: independent trading-risk SME.
- Three bounded passes, blind commitment then independent interpretation then exact-response critique.
- All 50 facts retained; 32 claims, 600-codepoint narrative, 1,500 output tokens, 32,000-byte request and 131,072-byte response limits retained. Largest reported synthetic request is 30,964 bytes; only 1,036 bytes below that request bound, **not guaranteed spare capacity for new fields**.
- Reports 39 synthetic tests passed. This is prior reported structure evidence, not a rerun, model/domain acceptance or trading expertise certification. The 12-case human review matrix is unscored.
- Deployment path is `PROPOSED_NOT_AUTHORIZED`, no scheduled hook installed, Worker3 not reactivated, no trade/capital/thesis-transition authority. Earlier bounded evaluation receipts do not approve this candidate's deployment.

### 9.2 Proposed integration register

These are proposed consumer/acceptance refinements. Existing mandate already covers some of them; prefer failure-case tests to duplicated prompt text. No persona, schema or runtime implementation is changed by adding these rows.

| ID / linked fixes | Deterministic prerequisite | Interpreter / Challenger use | Built | Committed | Wired | Tested | Validated | Authorised | Priority / impact |
|---|---|---|---|---|---|---|---|---|---|
| AG-F01 / S0.4, DF-5, PHANTOM-B1, macro delivery | Qualified run/revision, source time/session/purpose and readiness/reasons | Explain relevant evidence/limits; challenge false-current/complete claims and incompatible clocks | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | First evidence contract: prevents interpreting partial or old inputs as a complete current panel |
| AG-F02 / VOL-02..07, IVH-3, D16 | Computed RV/IV30/IVP source/window/count/cadence and matched forecast horizon | Distinguish low historical IV from forecast-relative cheapness; challenge proxy, unit and tenor errors | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | Backend first; do not ask an agent to calculate missing volatility or claim a bottom |
| AG-F03 / B1/F1, C1, G1/G2/G5/G9, runway | Exact expression, quote/cost/expiry/exit and approved valuation evidence | Explain monetisation requirements; challenge stock-right/option-loses, IV/theta/spread and absent cost evidence | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | Existing SME05/06 expectations; numerical economics remains with shared owner |
| AG-F04 / H2, D2, crossing, A3/A12 | Canonical direction and supplied approved rule/state/clock | Describe existing thesis/review state; challenge contradictions without inventing triggers or CALL defaults | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | High decision-integrity value; backend proves state before agents discuss it |
| AG-F05 / XLU-D03/E2, T7, AR22 | Qualified exposure/mapping, source independence and clocks | Supported conditional transmission; genuine counter-case rather than false balance or correlation-as-causation | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | Reuse SME01..09, qualify missing QQQ/ETF relationships rather than invent them |
| AG-F06 / OT-10x, C13, VOL-08 | Frozen prediction, mature exact outcome, cost/baseline and cohort support | Explain later errors and unknowns; challenge hindsight/cherry-picking/agreement-as-proof | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | Outcome review, not autonomous prompt/model/weight updates or self-approval |
| AG-F07 / needs_codex, B7, A8, phase contract | Exact source-to-card field/run/revision and lossless bounded packet/peer binding | Report unpublished facts/holds; critique omitted evidence without filling missing fields | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | NOT-REVERIFIED | NOT-EVIDENCED | DECISION-PENDING | Test empty today_context, renamed alternatives, mixed revisions and dropped facts |

### 9.3 Smarter build rules and proposed acceptance cases

1. Preserve two roles/three passes and the original candidate. No new agents or tools merely to cover more register rows.
2. Separate **backend fact correctness** from **agent reasoning usefulness**. Agents consume/critique owner-calculated evidence; no independent GARCH fit, IV solver, price engine, data repair, thesis transition or outcome fabrication inside a prompt.
3. Audit which qualified facts exist within the fixed 50-fact contract. Missing new options/volatility facts mean unassessed. A new packet version/metadata sidecar or changed limits require separate scope/compatibility/capacity design; do not truncate/replace the original facts or attach the whole fix register as market evidence.
4. Add proposed frozen acceptance cases: low IV percentile but IV above forecast; weekly/short history presented as daily; usable forecast/missing IV; weekend evidence not live; direction unresolved but alternative thesis valid; absent exact contract/fees/exit; stock wins/option loses; duplicated source reports; THESIS_NOT_ACTIVE disagreement; blank published handoff. Preserve hashes, cutoffs, independent blind responses and authority invariance.
5. Extend the existing SME rubric only where a precise gap is demonstrated. Current main-idea quality/domain acceptance remains open; avoid an unbounded feature stream before the frozen candidate has a bounded approved evaluation.
6. Test candidate deltas offline first, then separately approved bounded model/domain evaluation against existing report/deterministic baselines. The same packet/horizon/exposure and costs must underpin comparisons. Synthetic passes/citations do not certify trading expertise.
7. Keep quote-age flagging policy; missing/incompatible source should be explained, not converted into a new age-only trading veto. Preserve approved intelligence scope and human authority.
8. Link every proposed agent capability to its backend owner, register IDs, versioned facts, exact failure tests and independent acceptance. Release backend repairs independently where approved; agent deployment is not a prerequisite to fixing a broken data handoff.

**Current disposition:** commit batch appears finished and register history reconciled to `f3e199e`; baseline qualifications remain recorded; first slices and agent integration opportunities are now explicit. No fixes, agents, evaluation calls, schedules or deployment started.



## 10. ACK acceptance and amendments — 21 November

**ACK, 21 November:** sections 7 to 9 and `BASELINE_and_agentic_build_integration_plan_20261121.txt` are accepted as the working plan, with the six amendments below (Claude Code review of the same day). **The build hold stands.** Acceptance of the plan approves no root cause, design, spend, merge or activation; each slice still needs its own approved design and a failing test first.

| # | Amendment | Evidence | Effect on the plan |
|---|---|---|---|
| A1 | This file is the register of record. Codex wrote the reconciled version over the repo copy; it is uncommitted until ACK asks. | `git diff --stat`: 446 insertions, 285 deletions against `f3e199e` | Step 0: ACK decides when to commit it. Concurrent editors must not overwrite each other's sections. |
| A2 | The production eligibility gate (`eb50549`) is decided before slice 1, not after. | It changes 55 lines of `intelligent_orchestrator.py`, the file VOL-02 edits; also `orchestrator/production_eligibility.py`, `avshunter/c0_run/canonical_manifest.py`, `orchestrator/dynamic_dispatcher.py` | Step 0: merge, re-apply or drop, by ACK decision. |
| A3 | The Lab timing fix is on HEAD by test, not by text. | `b5d346d` carries the same `tests/test_lab_timing_publication_paths.py` as `b48db74` (0 differing lines; 2 passed on 21 Nov). `contracts/lab_review_sources.py` and `contracts/lab_review_projection.py` differ from the branch version by 43 and 12 lines. The `b5d346d` message says "same repair", which overstates it. | Branch `fix/lab-timing-publication-20261116` is not merged. Real-run acceptance of the timing publication is still owed. |
| A4 | The legacy Interpreter package is in step 0, with the publication and handoff work (AG-F07), not in P4. The agent role named "Interpreter" is a different thing from the `pipeline_interpreter` package. | Nine wiring points: five sync hooks (`eod_candidate_engine.py:3453`, `execution_intelligence_runner.py:3415` and `:3706`, `morning_validation.py:1167`, `contracts/lab_control.py:5177`, `morning_handoff_finalizer.py:735`), the Evening snapshot (`intelligent_orchestrator.py:8037`), the Lab desk and war view (`intelligence_lab.py:180`, `:189`), the manifest flag (`lab_control.py:2466`). About 900 MB copied per run; the inputs folder was 4.3 GB on 20 Nov. Last classic report: 10 Aug. | Needs an approved decommission design. Open point for ACK: whether the Lab desk and war view go with it or stay until agents replace them. "Repair, don't delete" points to switching wiring off and keeping code. |
| A5 | Two step-0 qualifications are closed. | Five residual files: the backup folder left disk on 15 Nov (day of the instructed clean-up; the log does not name the folder; content is in `c808b45`); the 2 Oct outcome report was regenerated by the scorer on 5 Oct with 815 more `NOT_YET_SCORED` records, scored counts unchanged. `test_macro_completion`: `FileNotFoundError` for `config/macro_delivery_v1.json` in the temporary folder, a fixture fault. | ACK decides whether to commit the five files. The test fixture needs a fix; production behaviour is not changed for it. |
| A6 | Slice 3 (outcome linkage) names the existing writers before any design. | The post-close monitor is the one writer of `monitor/option_closes.csv` (ACK 17 Oct); AVS-LEDGER-001 covers card outcomes; `AVSHUNTER_OPTION_OUTCOME_CAPTURE_ENABLED` defaults to "0" (`intelligent_orchestrator.py:2825`). | No second option-close writer. |

Decisions still with ACK before any build: commit of this register and the five residual files (A1, A5); `eb50549` (A2); the delayed-feed rule TR-005, which gave Morning DO_NOT_TRADE on 14, 18 and 19 Nov and conflicts with "flag quote age, never gate"; the Interpreter decommission scope (A4); a versioned agent packet, since the present one has 1,036 bytes of headroom.

Known limits of this register as it stands: the six status columns hold the same placeholder values on most rows, and rows marked `RECHECK-BASELINE` or `NOT-REVERIFIED` have not been refreshed against `f3e199e` or the test results recorded in the 21 Nov commit messages. Sections 7.3 and 8.2 carry the real priorities.

## 11. Baseline qualification and direction/default trace — completed investigation, build still held

**Final baseline reconciliation:** While preparing this update, commit `9e7849bbdef03d1bc70d36c6e387eb6860b0e636` committed the register and all five explained residual files. Its six-file diff contains no production source/config/test changes; all pinned source hashes remain checked at application. The earlier tests were run against `f3e199e`, whose production sources are unchanged. The commit decisions in section 10 A1/A5 are therefore completed, superseding the pending wording there; other ACK decisions and the build hold remain. No commit was performed by this investigation. Tracked working tree was clean immediately after that commit; this documentation update will be a new uncommitted delta.

**Disposition:** final committed baseline `9e7849bbdef03d1bc70d36c6e387eb6860b0e636` has unchanged production sources from `f3e199e636d93591065ebd6d0a2b6c4c6435f028`, selected production/config/test files have no diff from HEAD, nothing is staged and index lock is absent. Baseline qualifications are now **investigated and explicitly dispositioned**, not all erased or marked green. **No building yet**, as instructed by ACK.


### 11.0 Reconciliation with ACK amendments

Section 10 is preserved verbatim and governs the prerequisites. Before any build, ACK decisions remain on register/residual commits, eligibility commit eb50549, TR-005 quote-age policy, legacy Interpreter decommission scope and a versioned agent packet. No such decision is inferred here. Historical residual explanations in A5 close their cause investigation; committing those files remains pending, and the fixture remains unfixed.

Independent branch checks confirm eb50549 itself changes 48 added/7 removed orchestrator lines plus the three named files. Its gate rejects dirty/unavailable-code STANDARD PRODUCTION BUILD_THESIS/FINALISE before acquisition; explicit proving/test/replay/force and Morning semantics differ. Whole-file comparison to today's HEAD includes unrelated newer changes: never replace the current orchestrator with the branch copy. Selective integration must preserve current code receipts, retention, Morning timing and final Lab publication. A3 is test-equivalence only: the Lab timing test has no diff, while current implementation differs. Real-session acceptance remains outstanding.

Legacy Interpreter sync imports are confirmed at the six listed call sites, plus Evening snapshot, Lab views and manifest preparation. These are source wiring points, not nine equivalent runtime invocations; A4's wording “five sync hooks” lists six. The reported 900 MB/run, 4.3 GB and last-report date are attributed to section 10, not independently measured here. The legacy package and the new Interpreter agent are separate. Define scoped disconnection/publication compatibility before implementation; do not delete code or deactivate hooks in this task.

Outcome integration must reuse the existing post-close monitor as sole option-close writer and AVS-LEDGER-001 for card outcomes; preserve the default-disabled capture flag. Agents consume qualified facts and outcome evidence; they do not become new data writers or decision owners.

### 11.1 Verification results and residual disposition

| Qualification | Result | Consequence / remaining action |
|---|---|---|
| API cap baseline | Independently rerun: `tests/test_macro_api_cost.py`, **16 passed in 65.83s** | USD 4 config/test alignment verified narrowly; not proof of all macro scheduling/output behaviour |
| Macro-completion baseline | Independently rerun: `tests/test_macro_completion.py`, **1 failed, 5 passed in 52.04s** | Failure reproduced before archive validation because temporary root has no `config/macro_delivery_v1.json`; checked-in suite remains red |
| Fixture causal diagnostic | Existing function with original validator mock and an explicit workspace-only DATA_ONLY config resolves expected archive hash; tampered hash rejected; FULL mode still prohibited | Confirms fixture/config precondition omission. Future BF-00 changes test setup, not production guard/config. Live config is FULL; blindly copying it into a DATA_ONLY fixture is not the repair |
| Selected source baseline | Owner/adapter/router/Morning/EIL/forecast/publication sources and configs hashed, unchanged from HEAD | Receipts pin the investigation. Recheck if affected file/HEAD changes; no general full-suite or whole-estate certification |
| Register delta | Intentional documentation change | Keep separate from build code; do not auto-stage/commit |
| Historical outcome-report deltas | Two 2 October generated report files; canonical outcome code writes report artifacts | Preserve original working-tree state; not the frozen baseline or substitute for canonical labels in this build |
| Deleted interpreter backups | Three tracked backup/history residual deletions; no direct reference found in traced current entry points | Preserve state, no deletion/restoration action inferred; full restore/retention qualification remains its own scope |
| Untracked strategy layer | `data/scratch/workaround/strategy_layer.py` is a standalone/manual CLI; tracked `check_triage.py` can consume its strategy CSV on the old handoff layout | Not globally unused. Hash as a manual/external input boundary; no direct import found in traced Evening/Morning/forecast owners. Any Lane B acceptance must pin its input artifact/version or mark absent |
| Other untracked research/test/agent artifacts | Not promoted to the committed production baseline by this task | Preserve; no blanket deletion, commit or 'all unused' assertion. Isolated agent candidate stays outside production |

These qualifications are resolved to a **scope-qualified baseline with a known test-fixture exception and explicit residual boundaries**. They are not authority to ignore failures or claim a pristine release. The independent fixture diagnostic does not change the checked-in test's failure status.

### 11.2 Actual direction path and saved-session evidence

Source trace: Discovery-owned thesis -> OI `parse_structural_context` -> shared `resolve_governed_direction` -> GDR/final direction -> orchestrator horizon adapter -> router -> OI/EIL/EOD projections -> Morning shared-record validation/lock.

Current Discovery-authority records do not re-run a legacy evidence vote; OI disables non-directional re-resolution. Morning's migration adapter converts a missing explicit side to UNRESOLVED; governed rows lock to final GDR. The traced EIL physics helper reads explicit final/governed/canonical/direction values without a CALL default. This is a source/caller trace plus saved-output reconciliation, not a new live pipeline or comprehensive Morning historical replay.

| Saved run | OI rows | Horizon rows | Adapter side source | Invented CALL defaults | Directed routed/governed disagreements |
|---|---:|---:|---|---:|---:|
| `20261119_234734` | 2,746 | 2,746 | options_direction on every row | 0 | 0 |
| `20261119_000537` | 2,764 | 2,764 | options_direction on every row | 0 | 0 |
| `20261118_000634` | 2,772 | 2,772 | options_direction on every row | 0 | 0 |
| **Total** | **8,282** | **8,282** | Explicit supplied fields | **0** | **0** |

No inspected saved horizon row had a directed routed ID against a non-directed governed state. Input priority was reconstructed from archived OI output fields and compared with saved horizon IDs; original source-process execution was not rerun. These observations do not prove every historical/malformed/alternate-entry-point path safe.

**H2 remains a confirmed latent adapter defect, not an observed wrong-side incident in these runs.** The orchestrator takes instrument -> options_direction -> strategy_type -> direction, default CALL, omitting canonical_direction/final_direction from that lookup. The router itself rejects unknown instruments. Extracting the existing helper and applying local cases reproduces:
- Empty row -> CALL.
- Only canonical_direction=PUT -> CALL.
- instrument=CALL plus options_direction=PUT -> CALL.
- direction=UNRESOLVED -> UNRESOLVED, not CALL.

Use the shared direction owner, no invented default and explicit conflict/legacy policy in a future narrow repair. Do not create a new voting mechanism. A ticker-key raw-row writer and a ticker-fallback patch also present a latent same-ticker opposite-side identity risk; no collision was observed in these one-row-per-ticker saved OI artifacts. Add exact-identity regression cases rather than claim a proven incident.

**Direction-label qualification:** `DIRECTION_CONFIRMED` is the shared-record path token when final equals governed; its validator expects that token. Fresh Discovery-owned records intentionally have no re-resolution evidence chain. This does not assert calibrated win probability or predictive confidence. A display concern must not be 'fixed' by renaming the schema token or forcing an evidence vote without compatibility/approval. Track label/calibration correctness separately from side integrity.

### 11.3 Prepared first build brief — not started

Source brief: [FIRST_BUILD_BRIEF_BASELINE_VOL_DIRECTION_20261121.md](FIRST_BUILD_BRIEF_BASELINE_VOL_DIRECTION_20261121.md). Standalone review copy and JSON evidence are in this chat's outputs. This is a proposed scoped brief, not implementation permission.

| ID | Proposed change / current impact | Built | Committed | Wired | Tested | Validated | Authorised | Priority / next acceptance |
|---|---|---|---|---|---|---|---|---|
| BF-00 | Explicit DATA_ONLY test-fixture config; preserve hash/no-chaining/FULL guard; no production policy change | NO-REPORTED | NOT-APPLICABLE | NO-REPORTED | FAILURE-REPRODUCED; DIAGNOSTIC-PASS | NOT-APPLICABLE | BUILD-HELD | Prerequisite fixture-only future change; checked-in macro-completion 6/6 and cost 16/16 afterwards |
| BF-01 / VOL-01..03, B1/F1 | Current price forecast before OI, typed IV on all chain paths, actual consumed-source receipts; restores unavailable shadow valuation/DOI evidence | DESIGN-ONLY | NOT-APPLICABLE | NO-REPORTED | CHARACTERISATION-EVIDENCE | NOT-EVIDENCED | BUILD-HELD | First production slice proposed; model/estimator unchanged, saved input/current-source tests, no unexpected direction/selection/permission changes |
| BF-02 / H2, identity | Future defensive no-invented-CALL/alias-conflict and exact-merge-key repair | NO-REPORTED | NOT-APPLICABLE | NO-REPORTED | STATIC+8282-SAVED-TRACE | NOT-EVIDENCED | BUILD-HELD | Separate follow-up; malformed-input business tests plus unchanged inspected valid rows; not ahead of confirmed B1 based on an unobserved incident |

Do not combine fixture repair, malformed-input policy, model changes and agent activation into one patch. BF-01 must not silently expand acquisition, add an IV solver, widen ATM filters, alter percentile formulas, normalise Phantom scores, switch contract selection from SHADOW or add an age-only trade veto. Shared-pricer inversion remains a separate dependency if local-IV solving is later added. Other missing geometry/model inputs may keep some B1 valuations unavailable even after current forecast handoff works.

### 11.4 Agent integration in the first brief

The existing isolated Interpreter/Challenger candidate consumes/criticises qualified owner-calculated facts. It does not repair inputs, fit GARCH, invert IV, invent contracts/outcomes, choose directions or change thesis/execution authority.

- Backend supplies a valid canonical direction and truthful current forecast/IV/readiness result with identities and cutoff before dependent use.
- Interpreter explains relevance and limitations; Challenger flags a stale CALL alias, unsupported directed claim, mixed clocks/tenors, low-IVP-as-cheapness, missing exact contract/costs or unevaluated trigger.
- Proposed acceptance cases include canonical PUT-only, missing side with positive-looking macro, unresolved ticker with valid alternative thesis, prior-close versus stale forecast, usable forecast/missing IV, short sampled IV history, same ticker/two identities, stock wins/option loses and absent cost/exit input.
- Preserve two roles/three bounded passes, blind peer binding and current 50-fact/size/claim limits. If the current context contract lacks these facts, report unassessed and propose a separate versioned packet delta; do not replace facts or append unbounded metadata.
- Prior 39 synthetic passes are not acceptance of these new cases or model SME performance. No prompts, schema, source, provider calls, scheduled hook or deployment were changed.

**Build decision remains with ACK. This task investigated baseline/direction risks, ran isolated existing verification/diagnostics, updated documentation and prepared the brief only.**

## 12. ACK decision — legacy Interpreter decommission included

**ACK instruction, 21 November:** decommission the legacy Interpreter as part of these fixes because it adds to pipeline runtime. This closes the decision on whether retirement is in scope and supersedes earlier wording that leaves that decision open. It does not lift the explicit no-build hold. Scope accepted; detailed implementation/activation remains held.

**AG-F07 / BF-03 — step-0 publication/handoff workstream, ahead of agent activation.** Plan removal of active legacy dependencies: the six sync call sites, Evening interactive snapshot, legacy Lab desk/war mounts and manifest preparation flag. Trace their callers and downstream readers first; retire legacy-only views, and preserve or migrate any still-required handoff to a canonical saved artifact before disconnecting it. Do not retain active legacy hooks merely because an agent replacement is not yet deployed. The new Interpreter agent is a separate component, not a reason to keep this package running.

Expected impact: less repeated copying, snapshot generation, duplicate publication and legacy startup work in Evening/EIL/EOD/Morning/Lab paths. Exact elapsed-time and byte savings remain unmeasured; the earlier size estimates are not acceptance targets. Measure stage duration, wall time, bytes copied and invocation counts against the same frozen inputs/environment before and after, when execution is authorised.

Acceptance design: demonstrate no legacy imports/calls/copy side effects on every supported pipeline entry point; preserve canonical candidates, governed direction, forecasts, valuation, permissions, outcomes and current Lab publication; verify retired endpoint behaviour and retained reader compatibility. Review shared utilities before removal. Preserve historical evidence and code/history for rollback; bulk archive deletion is outside this retirement slice. Rollback must restore a coherent prior wiring/config version without rewriting decisions or outcomes.

| Fix | Built | Committed | Wired | Tested | Validated | Authorised |
|---|---|---|---|---|---|---|
| AG-F07 / BF-03 legacy Interpreter retirement | NO | NO | NO | STATIC-WIRING-TRACE-ONLY | RUNTIME-SAVINGS-NOT-MEASURED | SCOPE-ACCEPTED; BUILD-HELD |

This is an independent scoped change with dependency review and failing regression cases before implementation. Coordinate with eligibility/VOL-02 edits to the orchestrator; do not bundle decommissioning, volatility methodology and agent activation into one patch.

## 13. Legacy Interpreter dependency closure and decommission design

**21 November: investigation and plan prepared; build still held.** AG-F07 / BF-03 is in scope by ACK decision. Detailed plan: [LEGACY_INTERPRETER_DECOMMISSION_PLAN_20261121.md](LEGACY_INTERPRETER_DECOMMISSION_PLAN_20261121.md). It supersedes the earlier nine-point dependency grouping and clarifies what retirement preserves.

The trace covers 97 package Python files, 765 static import statements/edges, tracked external references, Interpreter-named contracts and working-tree Lab UI. Five on_pipeline_complete callers plus mandatory finalizer make six sync sites. Additional dependencies include both Morning entries, EOD freeze, nine Desk/WAR routes and UI callbacks, macro/News Terminal projections, manual prepare/watch/shadow/capture launchers, tests and source-receipt config. Static inventories and hashed evidence are retained in this chat's outputs. Visible matching processes/tasks were absent at inspection; external/manual launch closure remains a cutover check.

Critical preservation: contracts/interpreter_handoff*, interpreter_macro_context and accepted-handoff Lab readers are shared data-only publication/integrity owners, not the legacy inference package. Keep current compatible paths/schemas initially. Both Morning entry points must replace legacy-copy success with canonical integrity verification, preserving independent reconciliation and score checks. Preserve immutable EOD evidence before removing the package snapshot import; retain readiness and human review. Retire generation endpoints/UI/provider setup and launchers together; remove MA_Inputs macro targets from writers AND alignment expectations. Do not delete all interpreter-named artifacts or disable the Morning integrity gate.

Metadata-only measurement: MA_Inputs 380 files / 4,479,734,109 logical bytes; classic outputs 141 files / 18,423,464 bytes, latest modification 10 August. This is retained footprint, not per-run writes or measured runtime. Sync force-copies the primary file and recursively scans outputs; Morning adds copy/hash work; first EOD snapshot adds gzip/hash work; model/capture cost is conditional on its separate entry points. Quantify paired stage/total timing, I/O and invocation counts after execution approval; do not promise ~900 MB/run or a percentage saving.

| Work item | Built | Committed | Wired | Tested | Validated | Authorised |
|---|---|---|---|---|---|---|
| BF-03 D0–D1 caller closure and canonical/immutable handoff preservation | NO | NO | NO | STATIC-TRACE-ONLY | NOT-RUNTIME-VALIDATED | SCOPE-ACCEPTED; BUILD-HELD |
| BF-03 D2 pipeline disconnection, both Morning paths and EOD snapshot owner | NO | NO | NO | NOT-BUILT | NOT-VALIDATED | BUILD-HELD |
| BF-03 D3 UI/API/provider/launcher retirement and macro projection update | NO | NO | NO | NOT-BUILT | NOT-VALIDATED | BUILD-HELD |
| BF-03 D4 paired performance, output invariance and full-session acceptance | NO | NO | NO | NOT-RUN | NOT-VALIDATED | EXECUTION-HELD |
| BF-03 agent consumption of preserved canonical evidence | DESIGN-ONLY | NO | NO | NEW-CASES-NOT-RUN | NOT-VALIDATED | INTEGRATION-HELD |

Priority: step-0 publication/handoff workstream, coordinated with eligibility and VOL-02 orchestrator changes; retire independently of agent activation. Characterize then add failing business cases before code. Runtime retirement is accepted on zero legacy calls/writes/dispatch, preserved handoffs/permissions, measured overhead and a qualified complete session. Financial logic/agent authority changes need separate validation. Agent integration retains two roles/three bounded passes, 50 facts and blind binding, and reuses existing outcome writers; no synchronous legacy replacement or autonomous policy updates.

No code, tests, configuration, launchers, schedules, processes, prompts or agents were changed. No pipeline/model/capture/benchmark run or commit was performed. Scope accepted does not lift ACK's no-build hold.

## 14. Review outcomes and build baseline — 21 November (Claude Code)

Recorded at ACK's instruction to reconcile and baseline before the build starts. This section adds decisions and review findings; it changes no earlier section. Line endings of this file were normalised to LF in the same commit (the working copy had doubled carriage returns, which made git show a whole-file rewrite).

### 14.1 ACK decisions given on 21 November

| # | Decision | Effect |
|---|---|---|
| K1 | **The direction function must pick a direction; Lane B is where the direction is challenged.** | Supersedes the BF-02 wording that a missing side "remains explicit unknown/unresolved". The fault to remove is the constant CALL that ignores the governed direction, not the act of picking. The pick is made from evidence and labelled with how it was chosen. Open with ACK: when evidence favours neither side, pick a primary side and carry the other as the alternative, or pick one side only. This is a direction decision, so rule 5 and an approved design apply before any build. |
| K2 | **Changes to Lane B are solely Claude Code's responsibility.** | The read-only analysis package asked for in `audit/architecture/AVS-ARCH-LB-001/AVS-ARCH-LB-001_fix_list.md` (analysis.md, build_plan.md, carried_forward.csv and the rest) is not needed as a hand-over. The fix list is the brief. Codex owns the Lab and macro fixes. |
| K3 | **The legacy Interpreter is retired today**, including the Lab desk and war view. | Confirms section 12 and the scope of `LEGACY_INTERPRETER_DECOMMISSION_PLAN_20261121.md`. Codex is completing the impact trace. |
| K4 | **The two trading agents are not needed for the Lane B target chain.** | Claude Code's assessment, given to ACK on 21 Nov and not disputed. Lane B's gaps are script, data and record problems; the chat with skills already does the judgement. A blind Challenger pass on finished cards can be revisited once cards are data records and a few weeks of scored outcomes exist. |

### 14.2 Review of the first build brief and the decommission plan

| # | Finding | Evidence | Needed before build |
|---|---|---|---|
| V1 | BF-01 does not name its pre-OI worklist. | Options Intelligence reads the pinned Discovery candidates file `runs/<run>/discovery/discovery_candidates_ultimate_<run>.csv` with `vanguard/vanguard_signals.csv` (`intelligent_orchestrator.py:4018-4021`). The forecast runner reads `superbrain/superbrain_enriched_<run>.csv`, which exists only after Options Intelligence (`garch_runner.py:365`). A frozen pre-option ticker packet is also published just before Options Intelligence (`intelligent_orchestrator.py:6424-6428`). | Name one of these as the worklist in the design. Recommended: the pinned Discovery candidates file, because it is the file Options Intelligence itself reads, so the forecast population equals the Options population by construction (2,746 rows on 19 Nov). |
| V2 | Two advisory publishers end the Evening on any exception. Not dispositioned in the brief. | Pre-option forecast packet: `intelligent_orchestrator.py:6423-6437`, `return False`. C6 candidate set and C8 valuation: `:6472-6491`, `return False`. Both are described in their own comments and log lines as descriptive or advisory with no authority. The behavioural candidate packet beside them (`:6439-6446`) already records a failure and continues. TEV-001 P0(a), approved 27 Sep, asked for this and was never built. | A decision to treat both like the behavioural packet (record the failure, continue), or to keep the stop with a stated reason. Small change, same orchestrator file as BF-01 and BF-03. |
| V3 | Correction to Claude Code's earlier priority list: the mixed-date fault on stale universe symbols is **not** a run-stopper today. | Scan exceptions are written as error rows (DSC-20). The 19 Nov run had 7 `SCAN_EXCEPTION_ValueError` rows and completed. Several date parses in Discovery still have no tolerant mode (`avshunter_discovery_ULTIMATE.py:1336, 1354, 1877, 2954, 3306`). Whether those 7 rows are this fault is not established. | Not a first-build item. It costs a few tickers per run; trace the 7 rows when Discovery is next in scope. |
| V4 | The decommission plan is accepted as the design basis. It supersedes the "nine wiring points" in amendment A4, which was an incomplete grouping. | The plan adds: both Morning entry points require hash-verified Interpreter copies to report completion; the macro publisher and News Terminal write into `MA_Inputs/macro`; nine desk and war-view routes; browser controls; shadow-automation launchers. It keeps the Interpreter-named shared contracts (`contracts/interpreter_handoff.py`, `contracts/interpreter_macro_context.py`) because current Lab review and Morning read them. | See V5 to V7. |
| V5 | "Retired today" can cover disconnection, not acceptance. | The plan's own stage D4 needs paired runs on frozen inputs and one complete Evening, Morning and Lab session. 21 Nov is a Saturday; the next session is Monday 23 Nov. | Agree what "retired" means today: wiring off (D2, D3) with acceptance on Monday, or design approval today and build next week. |
| V6 | The Morning completion change is the highest-risk part. | `morning_handoff_finalizer.py:729-801` and `morning_gate.py:4730-4801` return failure when the legacy copy cannot be verified. Both entry points must switch together to verifying the canonical handoff. | Failing tests for both Morning entries before any edit; no edits while a run is in progress; done and checked before Monday's Morning run. |
| V7 | Lane B has two touch points with the Interpreter. | `tools/ticker_pack.py:87` reads `interpreter/interpreter_macro_context.json`, a shared contract the plan preserves, so packs are unaffected. `data/scratch/workaround/capture_option_closes.py:142` imports `pipeline_interpreter.live_market_reader`; that script is already retired (ACK 17 Oct) and kept as a reference. | No Lane B change is needed for the retirement, provided the shared macro contract path stays. Claude Code owns confirming this on the first session after cutover. |
| V8 | The test suite's own guard can hide a remaining caller. | `tests/conftest.py` replaces the sync function with a no-op for every test (`206bd53`). About 68 test files reference the Interpreter or its sync. | The retirement tests must assert the absence of the call, not rely on the no-op. Tests are adapted, not deleted to get a green run. |
| V9 | Earlier size figure withdrawn as a saving. | "About 900 MB per run" in amendment A4 was the size of four files present in the inputs folder for the 19 Nov run, not a measured copy cost. Codex measured the folder at 380 files and 4.48 GB. | Runtime saving is to be measured, as the plan says. |

### 14.3 Suggested build order (for ACK to confirm)

One change at a time in `intelligent_orchestrator.py`, in this order:

1. BF-00: test-fixture repair for `tests/test_macro_completion.py`. No production change.
2. ACK decision on the production eligibility gate `eb50549` (merge, re-apply selectively, or drop).
3. BF-03: legacy Interpreter retirement, stages D0 to D3, with V2 decided alongside.
4. BF-01: current volatility evidence before Options Intelligence, with the worklist named (V1).
5. BF-02: direction pick, to the design in K1 once the open fork is settled.

Still open with ACK: the delayed-feed rule TR-005 and the versioned agent packet.

### 14.4 Baseline

Code baseline for the build: `9e7849b` on `laneb/lab-first-handoff` (production sources unchanged since `f3e199e`). The commit that adds this section is documentation only. One test file is known to fail on its fixture (`tests/test_macro_completion.py`, 1 of 6), to be repaired by BF-00. Nothing is pushed.

## 15. ACK decisions and first build — 21 November (later the same day)

### 15.1 Decisions

| # | Decision (ACK, 21 Nov) | Effect |
|---|---|---|
| K5 | **BF-01 worklist approved:** the pinned Discovery candidates file `runs/<run>/discovery/discovery_candidates_ultimate_<run>.csv`. | Closes V1. The forecast population equals the Options Intelligence population by construction. BF-01 itself is still to be designed in detail and built. |
| K6 | **The pipeline must not stop on an advisory packet; build the fix.** | Closes V2 and TEV-001 P0(a). Built the same day; see 15.2. |
| K7 | **Direction: pick a primary side and carry an alternative.** | Settles the fork in K1. BF-02 becomes: choose the primary side from evidence, label how it was chosen, and carry the other side as the alternative so Lane B can challenge it. Design still to be written and approved; rule 5 applies. |
| K8 | **Legacy Interpreter: wiring off today, acceptance on Monday 23 Nov's session.** | Settles V5. Codex builds it (ACK, 21 Nov); Claude Code reviews each stage and stays out of those files. Codex starts from the commit that adds this section. |

### 15.2 First build: advisory packets never stop the Evening (TEV-001 P0(a), V2)

**Root cause.** The pre-option ticker description (C5) and the option candidate set with its valuation disposition (C6, C8) were published inline in `evening_workflow`, and any exception returned False, which ended the run. All three are advisory with no trading authority.

**Change.**

- `intelligent_orchestrator.py`: two publishers, `_publish_pre_option_forecast_packet` and `_publish_option_expression_packets`, replace the inline blocks. A failure is logged, recorded and the Evening continues. C8 is not attempted without its C6 input.
- `contracts/descriptive_forecast_packet.py`: a failure record at `runs/<run>/forecast/advisory_publication_status.json` (stage, state, reason, authority ADVISORY_ONLY, time). Only failures are written, so a healthy run produces no new file. Once the pre-option freeze is recorded as failed, the description is refused for late publication.
- `contracts/lab_control.py`: the Lab asks before publishing the description. After a recorded pre-option failure it shows the description as unavailable; it does not publish one from files that options may already have changed.

**Why the guard on late publication.** Before this change the Lab could publish the "pre-option" description itself when none existed. With the Evening no longer stopping, that path would have published it after options ran and labelled it as the pre-option view.

**What does not change.** A healthy run: same packets, same bytes, no extra file. Direction, contract selection, ranking and permissions are untouched. Later readers already treat a missing packet as unavailable (`intelligence_lab.py` returns `FORECAST_PACKET_UNAVAILABLE`; the Lab book labels the fields `descriptive_packet_unavailable`; Morning logs that the revision is unavailable).

| Item | Built | Committed | Wired | Tested | Validated | Authorised |
|---|---|---|---|---|---|---|
| TEV-001 P0(a) / V2 advisory publishers never stop the Evening | YES | see the commit that adds this section | YES (called from `evening_workflow`) | `tests/test_advisory_publishers_never_stop_evening.py` 8 passed; failed 8 of 8 before the change. `test_descriptive_forecast_handoff` 7 passed, `test_research_only_option_ev` 6 passed. Regression: `test_ev3_orchestrator_order` 5, `test_ot10_station_inspection` 12, `test_station_quarantine` 27, `test_msi_orchestrator_run_meta` 7, `test_lab_review_sources_v1` 17, `test_lab_timing_publication_paths` 2, `test_tests_do_not_write_interpreter_inputs` 2, all passed. `test_g9_no_new_option_pricer` fails as before on the untracked `strategy_layer.py`, unrelated to this change | NOT YET: no real Evening has run on it. Acceptance is the next Evening completing with the three packets published and no status file written | ACK 21 Nov ("the build and fix should be implemented") |

Not exercised by a test: the whole `evening_workflow` end to end. The wiring is checked by reading the function's source for the two calls and the absence of the two abort messages.

### 15.3 Order now

1. BF-00 test-fixture repair (hold not yet lifted).
2. ACK decision on `eb50549`.
3. BF-03 legacy Interpreter wiring off today, built by Codex and reviewed by Claude Code; acceptance Monday.
4. BF-01 volatility evidence before Options Intelligence, worklist per K5.
5. BF-02 direction pick per K7.

## 16. ACK decisions on the eligibility gate and the Evening snapshot — 21 November

| # | Decision (ACK, 21 Nov) | Effect |
|---|---|---|
| K9 | **Production eligibility gate (`eb50549`): re-apply as a warning only.** | A standard production Evening on uncommitted or unidentifiable code is not refused. It runs, and the run is labelled as not baseline eligible with the reason (`CODE_UNCOMMITTED`, `CODE_IDENTITY_UNAVAILABLE`). This changes what Codex built on 12 Nov, where `require_production_eligibility` raises before acquisition. The rest of that commit (real git cleanliness passed to planning, identity captured at launch and carried to run pinning, provisional then final eligibility labels in run metadata, manifest labelled as input capture) is kept. Re-apply selectively onto the current `intelligent_orchestrator.py`; never replace the file with the branch copy. Closes amendment A2 as a decision. |
| K10 | **Evening snapshot: keep writing it; a run's snapshot may be deleted after the next trading session.** | The writer at the end of the Evening stays (`runs/<run>/interpreter/eod_review_v1`, 107 MB for the 19 Nov run). Claude Code's reading of the instruction: the snapshot for session N becomes deletable once session N+1 has completed, so at most the latest one or two are held. Its only reader today is the legacy desk (`pipeline_interpreter/interactive_desk.py:488`), which is retired under K3. |

Build notes for Codex (owner of BF-03, per K8):

- K9 goes first, before any other orchestrator edit in BF-03, as the decommission plan's stage D0 already requires. It needs a failing test that a standard production Evening on a dirty tree starts and is labelled, and the tests in `tests/test_production_eligibility.py` from `eb50549` adapted to the warning behaviour.
- K10 is a deletion rule, so it needs its own small design before any file is removed: which owner deletes (the existing `scripts/artifact_retention.py` and `config/artifact_retention_v1.json` are the place to look first), how "next trading session completed" is established from the exchange calendar and a completed run, and a receipt for each deletion. Nothing is deleted under this register entry.
- Start from `c8631c4`. That commit changed `intelligent_orchestrator.py` and `contracts/lab_control.py`.

Still open with ACK: the delayed-feed rule TR-005, the versioned agent packet, and lifting the hold on BF-00.

## 17. Codex resumption reconciliation after commit

Observed HEAD `c8631c471b33afb81148e33b2f61d27cf02f0cca`; `2522c25` committed the reviewed register baseline and `c8631c4` added TEV-001 P0(a). No Git process/index lock found at resumption. Section 16 was already an uncommitted concurrent delta and is preserved. Reviewed source changes since the dependency trace: orchestrator, Lab control and descriptive forecast packet; other previously hashed owners match.

BF-03 remains the sole implementation focus. K9 requires warning-only provenance/eligibility integration first, preserving new advisory-failure handling. K10 requires the Evening snapshot writer to stay: its library import/compression/hash work is an explicit retained exception, not retirement failure or removable runtime savings. No generic latest-two retention deletion; a separate calendar/completed-session/receipt design is required. Retire Desk/WAR, sync duplication, legacy provider/report/capture entry points and launchers; preserve canonical Morning/Lab verification and shared macro/handoff contracts. No new agents or Lane B changes.

The decommission plan is reconciled accordingly. K8 records implementation permission, but this chat previously held building; clarification was requested on resumption. Until resolved, this reconciliation changes documentation only. Monday 23 November remains the recorded forward acceptance target, not validation already achieved. No fixes, tests, pipeline/provider/capture calls, process/task changes or commits were performed in this resumption.

## 18. BF-03 implemented after explicit chat approval

**ACK answered “Implement BF-03 now”.** The earlier direct-chat hold is lifted for this slice. Starting HEAD c8631c4 remains unchanged; changes are local/uncommitted. Full report: [BF03_LEGACY_INTERPRETER_BUILD_REPORT_20261121.md](BF03_LEGACY_INTERPRETER_BUILD_REPORT_20261121.md).

K9 warning-only provenance was built first: production continues on dirty/unidentified code with explicit baseline exclusion reasons; launch identity, provisional/final labels, immutable planning and current code receipts preserved. BF-03 removes legacy input sync/import fallbacks, preserves canonical verification on both Morning entries, retires Desk/WAR mounts and UI actions, removes MA_Inputs macro destinations, retires five batch/PowerShell wrappers and guards all 23 Python launchers before imports. K10 snapshot writer/source is unchanged. Shared handoff/macro contracts, canonical outputs, authority checks and historical evidence remain. No agent, Lane B, volatility/direction fix or retention deletion is included.

| Work | Built | Committed | Wired | Tested | Validated | Authorised |
|---|---|---|---|---|---|---|
| K9 prerequisite | YES | NO | YES-SOURCE | 23-PASS | OFFLINE-ONLY | YES |
| BF-03 pipeline/canonical handoff | YES | NO | YES-SOURCE | PASS; existing integrity checks retained | COMPONENT/OFFLINE; SESSION-PENDING | YES |
| BF-03 Desk/WAR, UI, macros, wrappers and Python launch closure | YES | NO | YES-SOURCE | 41 retirement cases plus focused regressions | OFFLINE; NEXT-START/SESSION-PENDING | YES |
| K10 snapshot retention deletion | NO | NO | NO | NOT-RUN | NOT-VALIDATED | SEPARATE-DESIGN |

Consolidated result: **192 passed, 1 skipped and 3 subtests across 19 focused suites**. Corrected an overbroad intermediate EIL edit; the final diff removes only two direct sync blocks. Exact non-sync syntax in candidate/EIL/legacy Morning producers is preserved, and actual EIL enriched Morning publication has a passing regression. Source/JS parse checks and scoped whitespace checks pass. This is not whole-pipeline or economic validation.

Isolated four-artifact 8 MiB handoff measurement, five warm-cache pairs: median 0.417 s with legacy copying versus 0.085 s canonical verification; hashes equal; zero new copy calls. Component evidence only, not a promise of full-pipeline time savings. Preserved snapshot work remains. No artifacts deleted. Visible matching Lab/legacy process check was empty; no process/task changes or live pipeline/provider/capture calls. Monday 23 November full-session acceptance and independent Claude Code review remain pending. Concurrent macro-fixture/verifier/OI changes were left untouched by BF-03; no commits or whole-tree staging.

## 19. BF-03 P2 current-review controls fixed

**ACK authorised this follow-up and its scoped commit.** Review of a179378 found that the current saved-review app still advertised saved Interpreter reports and a paid desk even though their endpoints were retired. The older card controls had been removed, but this separate consumer was missed. BF-03 itself and its K9 prerequisite were committed in a179378; section 18's uncommitted status was its pre-commit snapshot.

Removed the saved-report drawer, paid-desk link, legacy redirect and report-request branch from intelligence-lab/static/review-app.js. The five canonical drawers remain: structure, option risk, context, Morning and audit. Their canonical request/render branch and error handler are byte-identical to the pre-fix implementation; revision checks, single/search stale-response protection, zero/missing values, escaping and genuine read-error retry remain. No backend, pipeline, decision, snapshot or handoff owner changed.

Test-first result: 2 frontend failures and 10 passes before the fix; all 12 Node cases pass afterwards. They exercise actual app rendering and all five drawer families in a mocked DOM/fetch environment, error recovery and four stale-response cases. Focused Python verification: 57 passed across six suites (frontend wrapper, homepage cutover, review projection, ticker search, display accuracy and evidence sources). Two older assertions were updated to stop requiring the retired desk/report path while retaining general legacy Lab navigation, canonical API and no-forecast-dependency checks. JavaScript syntax and scoped whitespace checks pass.

| Fix | Built | Committed | Wired | Tested | Validated | Authorised |
|---|---|---|---|---|---|---|
| BF-03 P2 current-review report controls | YES | THIS-FIX-COMMIT | YES-SAVED-REVIEW | 12-NODE-CASES; 57-PYTHON-PASS | OFFLINE-BEHAVIOUR; MONDAY-DEPLOYED-UI-PENDING | YES |

The reproduced P2 is closed in source/offline verification. Monday's browser acceptance should open a current saved-review card, confirm no Interpreter/paid controls or requests, and expand all canonical evidence drawers. Full Evening/Morning acceptance remains separate. No live pipeline, provider/model/capture, retention deletion or operational process changes occurred. Only this fix's six files and this appended register section are included; the pre-existing section 16 and any other editor changes remain outside the commit.

## 20. Claude Code builds of 21 November, committed before the first Evening run on them

Recorded at ACK's instruction to commit the register before the Evening run of 21 November. Each item was built on ACK's go-ahead given the same day. None has run on a real session yet.

| Item | Commit | Built | Wired | Tested | Validated | Authorised |
|---|---|---|---|---|---|---|
| TEV-001 P0(a): advisory packets never stop the Evening | `c8631c4` | YES | YES | 8 new tests; 85 in nine related files | NOT YET: first Evening is 21 Nov | ACK 21 Nov |
| BF-00: macro completion test fixture | `13a72fc` | YES | test only | 6 of 6 (1 failed before) | not applicable | ACK 21 Nov ("fix") |
| TR-005: verifier quote age is a flag, never a gate (`timing.quote_age_policy` = FLAG) | `3f41a41` | YES | YES | 6 new tests; replay on saved Mornings 14 and 19 Nov: DO_NOT_TRADE becomes TRUST_WITH_CAVEATS, other checks identical | NOT YET: needs a Morning | ACK 21 Nov |
| VOL-03: 30-day IV benchmark on every chain path, with state and reason | `afc2ef4` | YES | YES | 14 new tests; 58 of 60 regression files (two failures predate it) | NOT YET: first Evening is 21 Nov. Expect a state on every Options row; the 19 Nov run had 1,075 blanks | ACK 21 Nov |
| VOL-02, runner half: Discovery worklist, evidence-session cutoff, receipt | `78ecd96` | YES | PARTLY: the Evening still passes the old list | 6 new tests; 79 in four forecast files | NOT YET | ACK 21 Nov (K5) |
| AVS-ENH-2026-11-21 Wave 0 (F-01 to F-05, F-09, F-10, F-29): ticket-ready list per branch, board-row collector, context refresh, stale macro state flagged | `1323f35` | YES | YES in `avs_day.ps1` preclose and eod | 28 new tests; 28 other Lane B tests; replay on saved folders | NOT YET: first session is 23 Nov | ACK 21 Nov |

Closed as decisions by ACK on 21 November: TR-005 (flag, not gate); the two trading agents stay frozen ("if we get Lane B to work as expected we will not need the agents"); BF-00.

Not built, still on the list:

- VOL-02, orchestrator half: move the forecast stage before Options Intelligence in `evening_workflow`, then feed the current forecast into contract valuation. A second cause of the dead shadow selection was found on the way: `test_b1_shadow_valuer_forecast_source` fails with `SCORE_NO_RUNWAY_ESTIMATE`, so valuation also lacks a runway estimate.
- BF-02: direction picks a primary side and carries an alternative (K7). Needs a written design and ACK's approval.
- Wave 0 parts that live outside the repo: the 15:40 push, the monitor's reason codes and quantity column, the card template (kill switch, whole-number size, one board-row shape), the write to the board. Prompt text owed to ACK.
- The rest of `2026-11-21_claude_code_brief_enhancements.md` (Part A outside Wave 0, Parts B and C) is not verified.

Review owed by Claude Code: Codex's legacy Interpreter commits `a179378` and `bbc6212` have not been reviewed against the decommission plan (deferred by ACK on 21 Nov). Their first real test is the Evening of 21 Nov and the Morning of 23 Nov.

Combined check before the run, at `1323f35`: the 14 changed pipeline modules compile and import; 167 tests across 12 files pass, including Codex's 41 retirement tests and 23 eligibility tests beside the above.

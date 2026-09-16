# Forensic Mapping — Python Codebase vs Knowledge Base

Status: **Assurance evidence — read-only, no code changed.** Prepared 16 Sep 2026.
Scope: tracked production Python in `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence` (534 files, 204,519 lines after excluding tests, audit, archive, backups, legacy and `*old*`/`*dnu*`/`*.bak*`), plus the external `C:\Users\ACKVerissimo\vanguard` repo where production depends on it.
Mapped against: `Enhancements/knowledge/AVSHUNTER_END_TO_END_DDD_BEHAVIOURAL_SPECIFICATION.md` (governing), method notes 01–07, `REPLICATION_PLAN.md`, and `REVIEW_DDD_BEHAVIOURAL_SPECIFICATION_20260916.md`.
Method: 122 requirements extracted from the documents, traced to code by six independent read-only reviews with file:line evidence; a seventh review built a reachability graph of production code and mapped modules back to the specification's bounded contexts. Key conflicts between reviews were re-verified directly (§6).

Status definitions: **IMPLEMENTED** — code does what the document requires · **PARTIAL** — some elements present · **CONTRADICTED** — code does the opposite / violates the requirement · **ABSENT** — no implementation.

---

## 1. Executive summary

| Context group | Requirements | Implemented | Partial | Contradicted | Absent |
|---|---:|---:|---:|---:|---:|
| Run context, market data, universe, sources | 21 | 0 | 9 | 9 | 3 |
| Market structure, evidence | 19 | 1 | 8 | 5 | 5 |
| Thesis, expression | 20 | 1 | 10 | 5 | 4 |
| Valuation, volatility / cheap convexity | 24 | 0 | 8 | 13 | 3 |
| Ranking, execution readiness | 20 | 0 | 7 | 11 | 2 |
| Decision ledger, outcome, validation | 18 | 2 | 13 | 0 | 3 |
| **Total** | **122** | **4 (3%)** | **55 (45%)** | **43 (35%)** | **20 (16%)** |

Reverse map (production reachability and context fit):

| Measure | Value |
|---|---|
| Production-reachable code | 268 files, 135,014 lines |
| Maps cleanly to one specification context | ~41% of production lines |
| Mixes several contexts in one module | ~36% |
| Implements something the specification does not call for | ~16% |
| Macro code still wired into production | ~6% |
| Tracked code not reachable from production (tooling, standalone, test-only, dead) | ~34% of all lines |

**Conclusion.** The codebase does not implement the specification; it implements a different design. Only 4 of 122 requirements are met. The 43 contradictions are concentrated where money is decided — valuation (13) and ranking/execution (11) — and in the foundations the whole flow depends on (single clock, immutable stage outputs, eligibility). The specification is achievable, and there are solid, reusable domain assets (§5), but it must be delivered as a rebuild of the decision path around those assets, not as edits to the legacy modules.

---

## 2. The ten most severe findings

| # | Finding | Requirements | Evidence |
|---|---|---|---|
| 1 | **Heuristic EV reaches decisions and can turn a negative contract EV positive.** A 0.30 floor on contract efficiency keeps `ev_final` positive; the result feeds `final_decision_engine` PASS/watchlist. The EIL process loads `vanguard/ev_engine_v2.py` (same defect as the root copy). | VA-13, FB-8, VA-1 | `vanguard/ev_engine_v2.py:228`, `ev_engine_v2.py:336-337,371`, `final_decision_engine.py:399`, `execution_intelligence_runner.py:161-168,216` |
| 2 | **Money measures that gate trades assume the target is hit.** Monetisability, `rr_options` and the monetisation policy's hard R:R block have no probability weighting. | VA-12, FB-4 | `contracts/selected_contract_economics.py:822-842`, `scripts/avshunter_options_intelligence.py:5746-5757`, `avshunter_monetisation_policy.py:276-282` |
| 3 | **Fabricated probabilities flow into EV.** Cache no-match returns 0.52; missing actuarial win rates are filled from Discovery's `40 + 0.25 × composite`. | EV-9, VA-14 | `[vanguard] actuarial_cache_builder.py:680-693`, `scripts/run_vanguard_from_packages.py:1195-1211`, `avshunter_discovery_ULTIMATE.py:614-623` |
| 4 | **Bearish theses scored on upside-only statistics** in the live Vanguard/EV path; four incompatible state keys; enrichment buckets disagree with v7 core. | EV-11, EV-13 | `vanguard/layer2_statistical/actuarial_query.py:666-672,1100-1113`, `scripts/actuarial_enrichment_pass.py:474-476,512-514`, `vanguard/core/actuarial_core_v7.py:21-31` |
| 5 | **No data hygiene or freshness on the evidence base.** No return winsorising in v7 (the only patch targets v6), adjustment "unverified", no point-in-time universe, no stale-DB gate — the 46.9M return passed unchecked. | EV-8, EV-14, UE-1 | `vanguard/core/actuarial_core_v7.py:42-62,268-307`, `scripts/patch_actuarial_winsorise.py:14` |
| 6 | **The thesis is shaped by the contract.** Hold falls back to DTE, is capped at 50% of DTE, the router maps DTE to horizon, time stop is 60% of DTE, and a 3R target is invented. | TH-5, TH-6, EX-2, FB-2 | `scripts/avshunter_options_intelligence.py:4190,4204-4209,4265-4268,920`, `macro_horizon_router.py:447` |
| 7 | **No single decision owner.** After the morning verdict at least six steps rewrite it (execution gate, OLM guard, three Lab book BLOCK rewrites, Lab UI resolution and re-rank); the execution gate invents `BUY_NOW` when the campaign verdict is missing. | XE-7, XE-8, RK-8 | `execution_gate.py:320-330`, `contracts/lab_control.py:2327-2399,2997-3032`, `intelligence-lab/intelligence_lab.py:2072-2105` |
| 8 | **No ranking by money.** No RAEV exists; four competing orderings (EOD status/tier, book verdict/priority, Lab bucket/score, opportunity tier); quality gates remove rows before any ranking. | RK-1, RK-3, RK-4, RK-6 | `eod_candidate_engine.py:2758-2803`, `contracts/lab_control.py:3068-3075`, `intelligence-lab/intelligence_lab.py:1186-1193`, `vanguard/layer2_statistical/edge_detector.py:355-401` |
| 9 | **No single clock; history not reproducible.** 93 wall-clock calls in decision code; replay dispatch returns "requires offline replay runner" which does not exist; today-anchored fallbacks. | RC-1, RC-6, FB-7, VL-5 | `intelligent_orchestrator.py:7426-7427`, `orchestrator/dynamic_dispatcher.py:295-298`, `eod_candidate_engine.py:885` |
| 10 | **The learning loop cannot learn.** 11 required lineage fields never written; `planned_hold_sessions` null on 100% of 7,531 candidates; 1,078 outcomes all at horizon 1; no expression P&L; non-selected expressions not recorded; no overfitting controls. | DL-2, OM-1, OM-4, DL-3, VL-6 | `canonical_data/decision_outcome_ledger.py:308-382`, `canonical_data/outcome_maturation.py:20,77-86` |

---

## 3. Traceability matrix

Locations are the principal file:line references; full per-requirement evidence is retained in the review transcripts for this date.

### 3.1 Run context, market data, universe, data sources

| REQ | Requirement | Status | Principal locations | Finding |
|---|---|---|---|---|
| RC-1 | One decision clock; no wall clock in decision code | CONTRADICTED | `avshunter_discovery_ULTIMATE.py:779,961,989,996`; `morning_gate.py:1337,1451,3042,3094,3563`; `scripts/avshunter_options_intelligence.py:913,2552,2639,3400,3517,8061`; `execution_intelligence_runner.py:337,1214` | 93 wall-clock calls; staleness, fetch windows, DTE and catalyst days computed from wall clock |
| RC-2 | Run identity fields | PARTIAL | `intelligent_orchestrator.py:2472-2521,2099-2115` | git/config identity and plan recorded; no decision_clock, data_as_of, pipeline_version |
| RC-3 | Dataset lineage fields | PARTIAL | `canonical_data/registry.py:199-249,400-408` | Canonical registry complete; macro JSON, scanner context, CSVs and bar cache unregistered |
| RC-4 | Append-only; "latest" never authoritative | CONTRADICTED | `intelligent_orchestrator.py:5039-5087,1717`; `avshunter_discovery_ULTIMATE.py:2363-2409`; `scripts/avshunter_universe_scanner.py:666` | `scanner_context_latest.json` scores Discovery; IV cache INSERT OR REPLACE |
| RC-5 | Clean release enforced | PARTIAL | `intelligent_orchestrator.py:2322-2351,2076-2095` | Dirty tree recorded and marks TEST; production not blocked |
| RC-6 | Replay = live domain path, injected clock | PARTIAL | `intelligent_orchestrator.py:7249-7251,7375-7406`; `orchestrator/dynamic_dispatcher.py:295-298` | `--as-of-utc` only feeds planner; replay runner missing |
| MD-1 | Market Data owns vendor translation | PARTIAL | `canonical_data/marketdata_stock_candles.py`; `morning_gate.py:800,838,1457` | Adapters exist; decision modules call vendors directly |
| MD-2 | Required inputs available | PARTIAL | `canonical_data/contracts.py:48-60`; `scripts/avshunter_options_intelligence.py:295` | OHLCV/chains yes; corporate actions, dividends, rates, earnings, short data incomplete or absent |
| MD-3 | Missing recorded as missing | CONTRADICTED | `avshunter_discovery_ULTIMATE.py:784-790,1056-1072`; `scripts/avshunter_options_intelligence.py:295` | Stale cache "APPROVED_FALLBACK"; silent 0.045 rate |
| MD-4 | MarketSnapshot aggregate | ABSENT | — | No snapshot type or manifest |
| UE-1 | Point-in-time universe incl. delisted | ABSENT | `intelligent_orchestrator.py:424,938-942` | Single mutable universe CSV |
| UE-2 | Eligibility reason codes | CONTRADICTED | `avshunter_discovery_ULTIMATE.py:1273-1300,2537-2546` | Filters return None → `NO_SIGNAL_AT_ANY_HORIZON` |
| UE-3 | Integrity exclusion for stale bars | CONTRADICTED | `avshunter_discovery_ULTIMATE.py:784-790,1999` | Stale bars analysed with fallback label |
| EVT-1 | Domain events with references | PARTIAL | `domain/data_projection.py:146`; `canonical_data/projection_outbox.py` | Dataset/lifecycle events only; stages hand off via CSV |
| OR-1 | Orchestrator coordinates only | CONTRADICTED | `intelligent_orchestrator.py:3555-3563,1601-1611,7007-7015` | Sets verdicts, sizing and downgrades |
| OWN-1 | No downstream mutation | CONTRADICTED | `intelligent_orchestrator.py:1611,3761-3786,7008-7015`; `scripts/apply_macro_enrichment_to_discovery.py:267-270` | Stage files rewritten in place |
| FB-7 | Replay never substitutes today's value | CONTRADICTED | `eod_candidate_engine.py:885`; `avshunter_discovery_ULTIMATE.py:989-997` | Today-anchored fallbacks |
| ADV-1 | Macro never gates/scores/ranks | PARTIAL | `vanguard/layer2_statistical/state_calculator.py:729-738`; `vanguard/physics_state_engine.py:193-260`; `scripts/avshunter_options_intelligence.py:386-409` | Vanguard regime now fixed TRANSITIONAL (floors constant); macro still in physics scores and PUT confirmation routing; `scripts/macro_quant_packet.py` imported by Discovery and EOD |
| DS-1 | Correct earnings source | CONTRADICTED | `morning_gate.py:797-827,2411-2416`; `earnings_calendar_enricher.py` | Reads non-existent Polygon field; MarketData earnings unused |
| DS-2 | Short interest/volume/borrow | ABSENT | `scripts/avshunter_universe_scanner.py:1037-1052,1653-1668` | Stub; neutral 25/100 score |
| DS-3 | Daily point-in-time IV history | PARTIAL | `scripts/avshunter_universe_scanner.py:950-995`; `scripts/avshunter_options_intelligence.py:3543-3560` | Weekly, overwritable; OI reads a run file never written |

### 3.2 Market structure and evidence

| REQ | Requirement | Status | Principal locations | Finding |
|---|---|---|---|---|
| MS-1 | Structure observations | PARTIAL | `WyckoffEngine_3101_v2.py:247-268`; `vanguard/core/actuarial_core_v7.py:126-132` | Phase/trend/shelf present; no range state, S/R not output, vol regime only in v7 core |
| MS-2 | Target and invalidation candidates | PARTIAL | `avshunter_discovery_ULTIMATE.py:1741-1809`; `asymmetry_gate_swing.py:107-121` | Single values not candidate sets; ATR stop below price for PUT |
| MS-3 | StructureAssessment aggregate | ABSENT | `domain/market_structure_evidence.py:121-161` | Flat ~150-field dict |
| MS-4 | Structure excludes direction/contract/EV/rank/action | CONTRADICTED | `avshunter_discovery_ULTIMATE.py:1948,2003,2048-2074,2183-2194` | Discovery fixes direction, tier, win probability, option fields |
| MS-5 | Pattern is hypothesis only | CONTRADICTED | `WyckoffEngine_3101_v2.py:869-878`; `actuarial_query.py:1263-1295` | Labels set direction, tier, probability multipliers |
| EV-1 | First-passage labels (high/low, ambiguous, gap) | PARTIAL | `vanguard/ev3_stage0.py:615-655,745-759,884` | High/low and ambiguous; no gap at open |
| EV-2 | Exact barrier distances | PARTIAL | `vanguard/ev3_stage0.py:36-41`; `canonical_data/outcome_maturation.py:111-169` | Population evidence on fixed % grid |
| EV-3 | Per-session probabilities 1–20 | ABSENT | `vanguard/ev3_stage0.py:42,916-926` | Horizons 5/10/20 and mean exit session only |
| EV-4 | Competing-risks estimation | ABSENT | `vanguard/ev3_stage0.py:884-892` | Raw frequencies |
| EV-5 | Overlap-aware n_eff | PARTIAL | `vanguard/ev3_stage0.py:781-784,866` | EV3 calendar blocks; live query uses raw counts |
| EV-6 | Shrinkage and uncertainty intervals | PARTIAL | `vanguard/ev3_stage0.py:867,885-892`; `actuarial_query.py:581-595` | EV3 shrinkage; no intervals; live weights heuristic |
| EV-7 | Out-of-sample calibration | PARTIAL | `canonical_data/dynamic_options_probability.py:279-294`; `scripts/ev3_calibration_report.py:96-119` | DOI/learning models only; actuarial not calibrated |
| EV-8 | Data hygiene | PARTIAL | `vanguard/core/actuarial_core_v7.py:42-62,268-307`; `scripts/patch_actuarial_winsorise.py:14` | Basic OHLC checks; no return cleaning; survivorship |
| EV-9 | No default probabilities | CONTRADICTED | `[vanguard] actuarial_cache_builder.py:680-693`; `scripts/run_vanguard_from_packages.py:1195-1211` | 0.52 and rescaled composite used |
| EV-10 | EvidencePacket aggregate | ABSENT | `actuarial_query.py:727-729` | Mutable outcomes object |
| EV-11 | BEAR mirrored statistics | CONTRADICTED | `actuarial_query.py:666-672,1100-1113` | Upside-only live stats (EV3 cache mirrors correctly) |
| EV-12 | Market-wide evidence base | **IMPLEMENTED** | `scripts/build_actuarial_v7.py:52-96` | Built across universe OHLCV |
| EV-13 | One state key / query library | CONTRADICTED | `vanguard/ev3_stage0.py:26-34`; `actuarial_query.py:17-38`; `scripts/actuarial_enrichment_pass.py:474-514` | Four keys; mismatched buckets |
| EV-14 | Evidence freshness gate | ABSENT | `scripts/validate_actuarial_v7.py:14-86` | No DB/label age check |

### 3.3 Thesis and expression

| REQ | Requirement | Status | Principal locations | Finding |
|---|---|---|---|---|
| TH-1 | Thesis before contract | PARTIAL | `scripts/avshunter_options_intelligence.py:4141-4270,6935`; `domain/thesis_direction.py:144` | Geometry before chain; hold from DTE; FrozenThesis carries contract |
| TH-2 | Direction state with CI | ABSENT | `contracts/direction_governance.py:35-37,272-299` | Vote shares, no states, no CI |
| TH-3 | No auto-flip | PARTIAL | `contracts/direction_governance.py:110-121,290-297`; `domain/thesis_direction.py:209-245` | Conflicts unresolved; STRANGLE auto-resolved by vote |
| TH-4 | Structural invalidation; missing → incomplete | PARTIAL | `contracts/thesis_geometry.py:30-63`; `avshunter_discovery_ULTIMATE.py:1791-1809` | Side-checked; legacy stop alias; missing not blocking |
| TH-5 | No artificial target | CONTRADICTED | `scripts/avshunter_options_intelligence.py:4265-4268` | 3R invented target |
| TH-6 | 1–20 session window with resolution distribution | CONTRADICTED | `scripts/avshunter_options_intelligence.py:1255-1259,4190-4216,4385-4393` | Fixed 5/10/20; DTE-derived (DOI ref enforces 1–20 at `domain/dynamic_options_intelligence.py:243`) |
| TH-7 | Thesis aggregate, frozen | ABSENT | `domain/thesis_direction.py:133-171` | Missing most fields |
| TH-8 | Versioning/supersession | PARTIAL | `domain/run_planning.py:223-236` | Version number, no supersession |
| TH-9 | Single producer of direction/target/invalidation | CONTRADICTED | discovery, options intelligence, EOD, DOI production | ≥4 writers each |
| EX-1 | Expressions generated before valuation | PARTIAL | `scripts/avshunter_options_intelligence.py:4534-4755`; `canonical_data/dynamic_options_family.py:285-346` | DOI family yes; primary path picks one contract |
| EX-2 | Instrument fits thesis | PARTIAL | `scripts/avshunter_options_intelligence.py:4190,4202-4209,920` | Hold trimmed to contract |
| EX-3 | DTE coverage rule | CONTRADICTED | `scripts/avshunter_options_intelligence.py:4566-4570,1274-1303`; `domain/option_contract_liquidity.py:205-220` | Sessions treated as DTE; widening −15 days |
| EX-4 | Scope: long options, verticals, short shares | PARTIAL | `vanguard/ev_engine_v3.py:374-476`; `domain/thesis_direction.py:90-91` | Longs yes; verticals in EV3; short shares absent |
| EX-5 | Objective tradeability only | PARTIAL | `domain/option_contract_liquidity.py:399-499`; `scripts/avshunter_options_intelligence.py:4580,6271-6288` | Delta band and far-OTM filters are quality gates |
| EX-6 | Rejected candidates auditable | PARTIAL | `domain/contract_family_generation.py:26-79` | DOI taxonomy; legacy selector drops silently |
| EX-7 | Chosen after valuation by RAEV | CONTRADICTED | `scripts/avshunter_options_intelligence.py:4700-4755` | Weighted greeks score |
| EX-8 | Missing quote/greeks not defaulted | CONTRADICTED | `scripts/avshunter_options_intelligence.py:2451-2456,4663-4676,5724-5729` | Synthetic BS marks; default greeks |
| EX-9 | Exit policy owned and valued | ABSENT | `scripts/avshunter_options_intelligence.py:899-937` | Time stop % of DTE |
| FB-2 | Short DTE never shortens thesis | ABSENT | `macro_horizon_router.py:447` | No guard |
| FB-6 | BULL never silently PUT | **IMPLEMENTED** | `domain/thesis_direction.py:209-245`; `eod_candidate_engine.py:1387-1468` | Continuity guard and reselection |

### 3.4 Valuation, volatility and cheap convexity

| REQ | Requirement | Status | Principal locations | Finding |
|---|---|---|---|---|
| VA-1 | Single owner of economics | CONTRADICTED | `ev_engine_v2.py`, `vanguard/ev_engine_v2.py`, `vanguard/ev_engine_v3.py`, `empirical_option_ev.py`, `contracts/selected_contract_economics.py`, `domain/contract_economics_v2.py`, monetisation policy | ≥7 economics producers; heuristic ones decide |
| VA-2 | Same path set per thesis | CONTRADICTED | `vanguard/ev_engine_v3.py:448-450`; `domain/contract_economics_v2.py:99-107` | Different scenario sets per module |
| VA-3 | Path-specific exit repricing; timeout not unchanged | CONTRADICTED | `vanguard/ev_engine_v3.py:234-252,647` | Timeout at entry spot; mean-day only |
| VA-4 | Explicit exit IV per path | PARTIAL | `vanguard/ev_engine_v3.py:34,642-643` | Constant IV, −15% stress only |
| VA-5 | Ask/bid, floor, commissions, borrow | PARTIAL | `vanguard/ev_engine_v3.py:349-351,424-426` | Proportional exit, no commissions, no borrow |
| VA-6 | EV, EV/R, RAEV lower bound | PARTIAL | `vanguard/ev_engine_v3.py:661-682` | Lower bound on debit; no CI output |
| VA-7 | Missing → NOT_VALUED | CONTRADICTED | `ev_engine_v2.py:108`; `scripts/avshunter_options_intelligence.py:3894-3897,5722-5729` | Widespread defaults |
| VA-8 | ExpressionValuation aggregate | ABSENT | — | Scattered `ev3_*` columns |
| VA-9 | One pricer/cost/horizon convention | CONTRADICTED | see §4.3 | 6–7 pricers, ≥4 cost and horizon conventions |
| VA-10 | Debit vertical valuation | PARTIAL | `vanguard/ev_engine_v3.py:374-476` | EV3 correct legs; other paths intrinsic |
| VA-11 | Short-share valuation | ABSENT | — | Not implemented |
| VA-12 | Target never certain | CONTRADICTED | `contracts/selected_contract_economics.py:822-842`; `avshunter_monetisation_policy.py:276-282` | Certain-target measures gate |
| VA-13 | Negative EV not made positive | CONTRADICTED | `vanguard/ev_engine_v2.py:228`; `ev_engine_v2.py:336-337,371` | 0.30 efficiency floor |
| VA-14 | Calibrated probabilities in EV | CONTRADICTED | `ev_engine_v2.py:236-243` | Heuristic blend decides |
| VC-1 | RV estimators | PARTIAL | `scripts/avshunter_options_intelligence.py:3915-3926` | Close-to-close only |
| VC-2 | Term-aware forecast vol with parameters | PARTIAL | `layer3_forward_variance.py:87-302`; `domain/volatility_budget.py:65-78` | 3 buckets; HAR coefficients not stored |
| VC-3 | IVP from daily IV history | CONTRADICTED | `scripts/avshunter_options_intelligence.py:3878-3947` | IV vs realised-vol range; defaults 50 / 20–80 |
| VC-4 | Term structure per expiry; skew decimal | CONTRADICTED | `scripts/avshunter_options_intelligence.py:3622-3645,3965-3968` | Bucket label; skew ×100 |
| VC-5 | Event variance separation | ABSENT | `vanguard/schemas/state_outcomes_schema.py:77-79` | Schema fields only |
| VC-6 | Cheap-convexity metrics | PARTIAL | `scripts/avshunter_options_intelligence.py:3905,6536-6558,5766-5781` | Model cheapness and gamma/vega per premium absent; expected move circular |
| VC-7 | Convexity explanatory; missing not pass | CONTRADICTED | `scripts/avshunter_options_intelligence.py:1099-1161`; `ev_engine_v2.py:327-333,366` | Neutral passes; EV boost up to ×1.6 |
| VC-8 | Placeholder IV / zero gamma filtered | PARTIAL | `scripts/avshunter_options_intelligence.py:2322-2331`; `vanguard/ev3_stage0.py:527-529` | Backfilled not filtered |
| FB-4 | Early target not valued at Day 20 | CONTRADICTED | `contracts/selected_contract_economics.py:722-725`; `empirical_option_ev.py:242` | Hold-end pricing |
| FB-8 | Negative EV not made positive | CONTRADICTED | `vanguard/ev_engine_v2.py:228`; `final_decision_engine.py:399,543-599` | Reaches decision |

### 3.5 Ranking and execution readiness

| REQ | Requirement | Status | Principal locations | Finding |
|---|---|---|---|---|
| RK-1 | Ranking consumes, never recreates | CONTRADICTED | `morning_gate.py:3725-3770`; `intelligence-lab/intelligence_lab.py:971-1042` | EV/probability rebuilt; Lab composite |
| RK-2 | Strongest expression by RAEV | PARTIAL | `domain/dynamic_options_ranking.py:385-413` | Deterministic utility ranking in DOI only |
| RK-3 | Across-thesis RAEV ordering | CONTRADICTED | `eod_candidate_engine.py:2758-2803`; `contracts/lab_control.py:3068-3075`; `contracts/opportunity_tier.py:279-287` | Four label/score orderings |
| RK-4 | RAEV ≤ 0 visible as NO_POSITIVE_EDGE | CONTRADICTED | `vanguard/layer2_statistical/edge_detector.py:360-401`; `intelligence_lab.py:1110-1174` | Cut upstream or hidden |
| RK-5 | Portfolio concentration | ABSENT | `eod_candidate_engine.py:2880-2887` | Side-dominance only |
| RK-6 | No quality gates before ranking | CONTRADICTED | `edge_detector.py:207-401`; `eod_candidate_engine.py:1229-1296,1963-1975`; `contracts/opportunity_tier.py:238-258`; `morning_gate.py:2560-2702`; `trigger_layer.py:48,76` | ≥12 quality gates |
| RK-7 | OpportunityBook published once, versioned | PARTIAL | `contracts/lab_control.py:3570-3748` | Schema version only; Lab rebuilds |
| RK-8 | Lab never re-ranks | CONTRADICTED | `intelligence-lab/intelligence_lab.py:2072-2105` | Re-decides and re-ranks |
| RK-9 | Hysteresis | PARTIAL | `domain/dynamic_options_ranking.py:414-437` | DOI contract level only |
| XE-1 | Revalidate, don't rewrite | CONTRADICTED | `morning_gate.py:2105-2150,2757,3725-3730` | Contract reselected; entry re-based |
| XE-2 | Invalidation first; missing stop distinct | CONTRADICTED | `morning_gate.py:1547-1571,2560-2634` | Checked late; missing stop = invalidated |
| XE-3 | Remaining window from original clock | CONTRADICTED | `morning_gate.py:1856-1869,2011` | Full planned hold reused |
| XE-4 | Revaluation then re-rank then policy | CONTRADICTED | `morning_gate.py:299-302,2186-2207,2525-2702` | Threshold ladder; EV3 advisory |
| XE-5 | Action vocabulary | PARTIAL | `domain/execution_authority.py:19-25`; `execution_gate.py:424-440` | GO/FLAG/BLOCK variants; no NO_EDGE |
| XE-6 | Execution does not own thesis/economics | PARTIAL | `morning_gate.py:3720-3780`; `execution_gate.py:402-420` | Derives window, entry, target move |
| XE-7 | Single decision owner | CONTRADICTED | `morning_handoff_finalizer.py:736-740`; `execution_gate.py:320-440`; `contracts/lab_control.py:2327-3032`; `intelligence_lab.py:2086-2093` | ≥6 overrides |
| XE-8 | Missing verdict never invented | CONTRADICTED | `execution_gate.py:320-330` | Invents READY_EXECUTE/BUY_NOW |
| XE-9 | Only authorised candidates hydrated | PARTIAL | `morning_gate.py:3062,3217-3244` | Hydrates carry-forward/watch rows too |
| SM-1 | Terminal states | PARTIAL | `eod_candidate_engine.py:1229-1291`; `morning_gate.py:2584-2618` | Mapped to reason strings; no NO_POSITIVE_EDGE |
| FB-5 | No 20-day restart | ABSENT | `morning_gate.py:1856-1869` | No position clock |

### 3.6 Decision ledger, outcome and validation

| REQ | Requirement | Status | Principal locations | Finding |
|---|---|---|---|---|
| DL-1 | Immutable record before outcome | **IMPLEMENTED** | `canonical_data/decision_outcome_ledger.py:88-158` | DB triggers block update/delete |
| DL-2 | Lineage fields | PARTIAL | `canonical_data/decision_outcome_ledger.py:308-382` | 11 fields never written; hold 100% null, completed session 65% null |
| DL-3 | All candidates, actioned flag | PARTIAL | `canonical_data/decision_outcome_ledger.py:303-307` | Non-actionable recorded; expressions not; no flag |
| DL-4 | Required fields enforced | PARTIAL | `domain/decision_outcome.py:66-73,125-135` | Envelope only |
| OM-1 | Deterministic 1–20 maturation | PARTIAL | `canonical_data/outcome_maturation.py:20,77-86,157-192` | Fixed horizons, wall clock, 26,138 duplicate observation pairs |
| OM-2 | Outcome classes | PARTIAL | `domain/decision_outcome.py:378-390` | Different vocabulary; all at horizon 1 |
| OM-3 | First-touch session | PARTIAL | `domain/decision_outcome.py:54-55,402-403` | Stored under other names |
| OM-4 | Expression P&L at bid | PARTIAL | `domain/dynamic_options_outcomes.py:438-450` | Domain builder only; ledger underlying-only |
| OM-5 | Journal fills linked; test trades quarantined | PARTIAL | `avshunter_trade_journal.py:989-997` | thesis_id link; no expression link; no quarantine |
| OM-6 | Outcome origin | PARTIAL | `canonical_data/outcome_maturation.py:110-142` | completed_session missing 65% |
| VL-1 | Direction and timing calibration | PARTIAL | `canonical_data/dynamic_options_probability.py:244-295` | DOI model only |
| VL-2 | PIT, purge/embargo, walk-forward, costs | PARTIAL | `canonical_data/outcome_learning.py:55-108` | Purge/embargo; no walk-forward, no costs |
| VL-3 | Validation never modifies decisions | **IMPLEMENTED** | `canonical_data/decision_outcome_ledger.py:88-129` | Append-only; no CORRECTION event type |
| VL-4 | Authority gated by validation | PARTIAL | `domain/outcome_learning.py:312-395`; `scripts/ev3_calibration_report.py:96-108` | EV3 calibration PASS on counts only |
| VL-5 | Replay runner | ABSENT | `intelligent_orchestrator.py:7426-7427` | Referenced, not built |
| VL-6 | Overfitting controls | ABSENT | — | No deflated Sharpe / PBO / trial count |
| VL-7 | Real-run gate, golden replay, decision tables, clock fixture | PARTIAL | `tests/golden/` | Lab export golden only; no conftest |
| VL-8 | Replication artefacts R1–R4 | ABSENT | — | Plan only |

---

## 4. Reverse map — code the specification does not call for, or mixes

### 4.1 Production modules by context fit (largest)

| Module | Lines | Fit | Note |
|---|---:|---|---|
| `scripts/avshunter_options_intelligence.py` | 9,578 | MULTI (Expression, Valuation, Volatility, Ranking, Execution) | Largest split target |
| `intelligent_orchestrator.py` | 7,511 | MULTI (Run context, Macro, Outcome, Presentation) | Makes domain decisions (OR-1) |
| `morning_gate.py` | 4,148 | MULTI (Execution, Valuation, Thesis guard, Market data) | |
| `contracts/lab_control.py` | 3,811 | MULTI (Presentation, Execution) | Rewrites decisions |
| `execution_intelligence_runner.py` | 3,714 | MULTI (Valuation, Ranking, Execution) | Loads `vanguard/ev_engine_v2.py` |
| `intelligence-lab/intelligence_lab.py` | 3,546 | MULTI (Presentation, Ledger) | Re-ranks |
| `eod_candidate_engine.py` | 3,212 | MULTI (Thesis, Expression, Ranking) | Imports macro quant packet |
| `scripts/avshunter_universe_scanner.py` | 3,203 | MULTI (Universe, Valuation, Evidence) | Own BS/IV |
| `avshunter_discovery_ULTIMATE.py` | 2,681 | MULTI (Universe, Structure, Evidence) | |
| Pipeline interpreter (commands/engine/outputs) | 6,044 | NO_CONTEXT | LLM briefs |
| `worker3/` | 6,308 | Macro advisory + NO_CONTEXT | ADVISORY_ONLY enforced |
| Diagnostics in production run (handoff/dropoff/UAT/market context) | 2,639 | NO_CONTEXT | Should become the real-run gate |
| Physics engine, regime screener, trap engine, McMillan layer, EIL strategies, WBS, core intel, phantom scripts | ~5,300 | NO_CONTEXT | Retire or re-justify through G1–G4 |
| `macro_horizon_router.py`, `scripts/macro_quant_packet.py`, macro contracts | ~3,800 | Macro | To remove from decision path |
| Clean single-context assets: canonical data core, decision ledger, DOI domain stack, option liquidity lifecycle, execution authority, run planning | ~25,000 | Single context | Reuse (§5) |

### 4.2 Not executed although present or referenced (verified)
`scripts/avshunter_superbrain_layer.py` (2,771; passthrough copies file instead), catastrophe gate (stub returns True), `premarket_intelligence_ULTIMATE`, `run_phantom_layer`, EDE/enhancement/trade-book phases (commented), preflight-only references to `execution_decision_engine`, root monetisation policy (tests only).

### 4.3 Duplicate implementations

| Concept | Copies | Production uses |
|---|---|---|
| Black-Scholes pricer | options intelligence `bs_price`/`bsm_price_vec`; universe scanner; `scripts/compute_greeks_bs.py`; `selected_contract_economics._black_scholes_value`; `domain/deterministic_option_valuation`; `macro_domain/gamma_exposure`; `desk_card.py` | Six live copies |
| EV engine | `ev_engine_v2.py` (root); `vanguard/ev_engine_v2.py`; `vanguard/ev_engine.py`; `scripts/ev_engine.py`; `vanguard/ev_engine_v3.py`; `empirical_option_ev.py`; `probability_engine.py`; DOI valuation | EIL → `vanguard/ev_engine_v2.py`; morning → EV3; DOI separate |
| Scenario builder | root; `vanguard/layer2_statistical/`; `vanguard/layer3_execution/` | EIL → `vanguard/layer3_execution/` |
| Wyckoff | root engine; `orchestrator/` copy; crabel/precor logic; phase validator | Root + crabel + validator |
| Monetisation policy | root (599); `scripts/` (736) | `scripts/` copy |
| Morning validation | `morning_gate`; `morning_validation`; `morning_validation_engine`; `trigger_confirmation_engine`; `orchestrator/dynamic_validation`; QA/smoke validators | `morning_gate` + `dynamic_validation` |
| Orchestrator | `intelligent_orchestrator.py`; `orchestrator/main.py` + `run.py`; interpreter e2e orchestrator | `intelligent_orchestrator.py` |
| Final decision / sizing | final decision engine, EDE, Kelly sizer, position sizing, trade book builder | `final_decision_engine` (via EIL) |

---

## 5. Reusable assets that already match the specification

These are aligned or close and should be the foundation of the rebuild, not discarded:

| Asset | Matches | Why reuse |
|---|---|---|
| `canonical_data/registry.py`, historical prices store with revisions, option chain store | RC-3, MD-1 | Dataset identity, lineage, no-overwrite registration |
| `canonical_data/decision_outcome_ledger.py` + `domain/decision_outcome.py` | DL-1, VL-3 | Enforced append-only ledger with identity |
| `domain/thesis_direction.py` continuity guard | FB-6, TH-3 | Prevents direction reinterpretation |
| `domain/dynamic_options_intelligence.py` `UnderlyingThesisRef` | TH-6 (partial) | Already enforces a 1–20 session thesis window |
| `domain/contract_family_generation.py` | EX-1, EX-6 | Thesis-bound candidate families with rejection taxonomy |
| `domain/deterministic_option_valuation.py` pricer, `domain/contract_economics_v2.py` scenario mechanics, `domain/volatility_budget.py` | VA-4, VA-5 (partial) | Clean pricing and timing primitives for the valuation core |
| `vanguard/ev3_stage0.py` barrier cache logic | EV-1, EV-5, EV-6, EV-11 (mirrored PUT) | First-passage labels, calendar-block n_eff, shrinkage |
| `vanguard/ev_engine_v3.py` vertical valuation and lower-bound structure | VA-6, VA-10 (partial) | Base for path-specific valuation once timeout/grid/cost defects fixed |
| `domain/dynamic_options_ranking.py` hysteresis | RK-9 | Stability mechanism |
| `canonical_data/outcome_learning.py`, `domain/outcome_learning.py`, `canonical_data/dynamic_options_probability.py` | VL-2, VL-4, EV-7 | Purge/embargo, held-out Brier/ECE gating |
| `domain/option_contract_liquidity.py`, `domain/option_liquidity_execution_guard.py`, `domain/execution_authority.py` | EX-5, XE-5 (partial) | Tradeability states and action vocabulary |
| `domain/run_planning.py`, `domain/session_authority.py` | RC-2, RC-5 (partial) | Run identity, baseline eligibility |

---

## 6. Corrections to earlier documents found during this mapping

| Earlier statement | Corrected finding | Verification |
|---|---|---|
| Root `ev_engine_v2.py` is the EV that decides; `vanguard/ev_engine_v2.py` is dead | EIL inserts `vanguard/` ahead of root on `sys.path`, so the EIL process (and `final_decision_engine` imported within it) loads **`vanguard/ev_engine_v2.py`** (314 lines). It carries the same 0.30 efficiency floor (`vanguard/ev_engine_v2.py:228`). Conclusion unchanged; module identity corrected. | `execution_intelligence_runner.py:157-168,216` read directly |
| Macro still sets Vanguard gate floors by regime | Vanguard now fixes regime at TRANSITIONAL (`vanguard/layer2_statistical/state_calculator.py:729-738`), so floors are constant; macro still reaches physics scores, PUT confirmation routing and imports of `macro_quant_packet` in Discovery/EOD | Review 1 |
| `AVS-INV-001` usage graph is a reliable inventory | Stale: 133 tracked files missing (all of `domain/`, `worker3/`, most DOI modules); its monetisation-copy and Vanguard-parse claims are wrong | Review 7 |
| Horizon router gates EIL rows on macro | In run 20260914 the only `horizon_block_reason` values are `NON_DIRECTIONAL_NOT_ROUTABLE:STRANGLE` (87) and `INVALID_INSTRUMENT:UNRESOLVED` (44) — structural, not macro; the router still reads the macro file | Run data (15 Sep) |

These corrections should be applied to `BUSINESS_DOMAIN_DESIGN_ADDENDUM.md` §7.1 and `END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md` S4/S8/S12 when the documents are next updated.

---

## 7. Implications for approving the specification

1. **The specification is the right target.** Every contradiction found is a behaviour the specification explicitly forbids (fabricated probabilities, invented targets, contract-shaped thesis, post-decision overrides, heuristic EV, unknown-as-neutral). None of the findings suggests a specification requirement is infeasible.
2. **The review changes C1–C14 are confirmed by the code:** C5 (ledger records candidates but not expressions, no actioned flag — DL-3), C6 (no expression outcome — OM-4), C7 (universe/eligibility contradicted — UE-1..3), C4 (no supersession — TH-8), C3 (DTE rule currently contradicted in the opposite direction — EX-3), C12 (macro and Lab re-ranking leaks — ADV-1, RK-8).
3. **Delivery approach:** build the specification's contexts as new, clean domain services (strangler pattern) using the §5 assets, route the pipeline through them one context at a time behind the real-run gate, and retire legacy modules as each context is replaced. Editing the 9.5k/7.5k/4.1k-line legacy modules in place would reproduce the current failure mode.
4. **First items that unblock everything else:** single decision clock and run context (RC-1, RC-6), immutable stage outputs (OWN-1), ledger lineage contract (DL-2, DL-3), evidence data hygiene and freshness (EV-8, EV-14), and replication R1/R4 on cleaned data.

---

## 8. Validation note — EV engine in production (16 Sep 2026)

Question from ACK: the pipeline is meant to use EV engine v3; is v2 actually running?

| Check | Result | Evidence |
|---|---|---|
| Design intent | EV3 was built to be the unified EV authority (NEGATIVE/INDETERMINATE block economics when enabled) | `docs/EV3_FULL_REMEDIATION_IMPLEMENTATION_20260820.md` Phase 7 |
| EV3 authority today | Permanently disabled: `authority_active = False` ("EV authority is retired"); config `EV3_AUTHORITY_ENABLED = False`; a request to enable is logged as retired. Introduced in commit `667620e` (4 Sep 2026) | `scripts/apply_ev3_authority.py:151-153`; `intelligent_orchestrator.py:467-470, 3280-3287` |
| Engine loaded by EIL | **`vanguard/ev_engine_v2.py` (v2.1.0)** — verified by importing under the runner's `sys.path` | `execution_intelligence_runner.py:157-168, 216, 440, 933` |
| Newer v2 not loaded | Root `ev_engine_v2.py` is **v2.2.0** (PATCH-05 actuarial signal integration); 121 differing lines; not imported by EIL | file headers |
| Where v2 output is used | Final decision engine input; EIL advisory field and composite; EOD candidate `ev_conf_adj`/`ev_status`; Lab EV warning (first choice); Lab priority score (10%); Lab `ev`/`ev_final`/`ev_status` display | `final_decision_engine.py:399`; `execution_intelligence_runner.py:441`; `execution_intelligence.py:565`; `eod_candidate_engine.py:2642-2643`; `contracts/lab_control.py:2104`; `intelligence-lab/intelligence_lab.py:1005, 1840-1844` |
| Run 20260914_214012: v2 verdicts | 1,449 rows: PASS_SMALL 1,280, WEAK_PASS 169, **no FAIL** | `execution/execution_v3_5_20260914_214012.csv` |
| Run 20260914_214012: EV3 verdicts | 245 contracts evaluated: **all 245 NEGATIVE_EV**; conservative return max −0.164, median −0.471; lower bound median −0.596 | Lab book `ev3_*` fields |
| Same contracts compared | Of the 245 EV3-negative contracts, v2 marked 221 PASS_SMALL and 24 WEAK_PASS; 79 are EOD_TRIGGER_READY and 166 THESIS_READY | Join on ticker |

**Conclusion — confirmed major defect (VA-1, VA-13, VA-14, FB-8).** The engine intended to measure money (EV3) is permanently advisory and says every contract it could evaluate has negative expected value; an older, heuristic engine (v2.1.0, not even the patched v2.2.0) runs in the decision path and passes every row, feeding the final decision engine, EOD candidate fields, Lab EV warning, Lab priority and the EV shown to the trader. Note: EV3 itself has known defects (timeout at unchanged spot, grid snapping, proportional exit spread), so its negative verdicts are directionally informative but must be revalidated after the valuation core is rebuilt.

**Owner clarification (16 Sep 2026).** Retiring EV3 authority on 4 Sep was a deliberate and correct decision: EV3 was not working as expected. EV authority stays off until correct EV logic is built and validated. The defect is therefore restated:

- **Not a defect:** EV3 advisory-only.
- **Defect (VA-1 restated):** retiring EV3 left the legacy v2.1.0 heuristic engine as the de facto EV voice, so the pipeline and Lab still present an "EV" / "PASS" that is not a valid expected value. Interim position: v2 output must not be treated as EV evidence anywhere; the rebuilt valuation core becomes the single EV owner and is switched on only after passing validation (knowledge note 03, replication plan, G3/G4).

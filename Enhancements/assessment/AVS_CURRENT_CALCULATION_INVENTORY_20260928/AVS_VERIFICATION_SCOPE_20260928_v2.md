# AVSHUNTER — Verification scope, v2 (update to the 28 Sep calculation inventory)

**Status:** assessment update, 28 Sep 2026 ~21:30 UTC. Not a release approval. Changes no production code, data or run.
**Supersedes for verification purposes:** `AVS_CURRENT_CALCULATIONS_LOGIC_AND_OWNERSHIP_20260928.md` (the "inventory", AST snapshot 07:41–07:45 UTC). The inventory remains the formula register; this document corrects what changed after it and defines **how each area is verified** under ACK's verification design rules (§2).

Confidence in this document: **High (≥90%)** for everything marked *reproduced* or *source-read*. **Medium** where marked *receipt claim*: the builder's statement, not re-run here.

---

## 1. What changed since the inventory snapshot

### 1.1 Source files changed after 07:45 UTC (SHA-256 recomputed against `source_manifest.jsonl`)

29 runtime owners were re-hashed. **8 changed and 21 are byte-identical** (including the orchestrator, vol, macro, DOI, C12, EV2, Options, EIL, execution gate, EOD and horizon router).

| File | Inventory bytes → now | Change | Source of explanation |
|---|---|---|---|
| `vanguard/ev3_stage0.py` | 44,315 → 45,105 | EV3 entry rule: hold must be a materialised horizon (5/10/20), no longer equal to the bucket endpoint | EV3-OPT3 receipt; *source-read* `ev3_stage0.py:358-371` |
| `vanguard/ev_engine_v3.py` | 41,229 → 50,706 | Valuation split into `_value_long_single` (:818), `_value_vertical`, `_move_window_fields` (:891); adds a second EV at the move window | EV3-OPT3 receipt; *source-read* |
| `morning_gate.py` | 192,750 → 194,857 | D2 fix: `_write_selected_contract_identity` (:3950), called from `_recompute_selected_contract_economics` (:3979/:4045) | EV3-OPT3 receipt; *source-read* |
| `contracts/lab_control.py` | 255,890 → 262,987 | EV3 move-window projection | EV3-OPT3 receipt |
| `intelligence-lab/static/index.html` | (not AST-parsed) | "Horizon" column renamed "Move window" (:371); "Hold" = planned hold in sessions (:378) | *source-read* |
| `contracts/enrichment_ledger.py` | 7,170 → 8,526 | `market_profile` ledger stage; `load_market_profile_stamps` (:159) | P1–P4 receipt §P4c |
| `scripts/build_completed_market_profiles.py` | 25,486 → 27,784 | `_worklist` (:75) from the manifest when there are no packages; `_atr14_from_canonical` (:95); ledger `_stamp` (:106) | P1–P4 receipt §P4c |
| `avshunter/c0_run/thin_package.py` | 11,789 → 15,003 | attaches `market_profile_*` from ledger/store (:148, :207); `market_profile_` removed from post-Vanguard patch prefixes (:59) | P1–P4 receipt §P4c |
| `canonical_data/option_liquidity_lifecycle.py` | 132,516 → 133,195 | LIVE-M1: a field one capture never held is an added fact, not a conflict | P1–P4 receipt §LIVE-M1 |

Status of all of the above: **TESTED_UNCOMMITTED** (receipts), so HEAD `03fd468` still does not reproduce the assessed system. Regression counts in the receipts (1,226 passed, and the P4c suites) are *receipt claims*; they were not re-run here.

### 1.2 Corrections to inventory §3.2 (latest run `20260927_205123`)

The inventory described this run before its Morning. The Morning has since run twice, and the run is now written off.

| Item | Inventory said | Now | Evidence |
|---|---|---|---|
| Morning | Pending, zero rows | 1st pass 14:51–15:07 BST **failed closed** (LIVE-M1); 2nd pass cleared the gate (488 GO / 323 FLAG / 739 BLOCK) then **failed in the handoff finaliser** (Lab reconciliation) | P1–P4 receipt; *reproduced* verdict counts from `morning_validated_trades_20260927_205123.csv` |
| Technical / semantic health | Both DEGRADED, score 92 | Technical **FAILED**, semantic DEGRADED, score **67** | `final_run_manifest.json` (created 15:08:47Z) |
| Run permission | `MORNING_VALIDATION_REQUIRED` | `BLOCKED_REPAIR_REQUIRED`; fatal flag `COMPLETED_MARKET_PROFILE_MISSING_OR_UNUSABLE` | same |
| Completed market profile | FAIL, zero rows | Root cause identified: **PKG-F5**. The manifest-mode builder got a 0-ticker worklist, and the thin package never carried profile evidence. `layer1__auction_state = NOT_EVALUATED` on all 1,616 Vanguard rows | P1–P4 receipt §PKG-F5 |
| Lab `final_action` BUY vs `lab_verdict` BLOCKED on 488/488 | (not covered) | **Correct guard behaviour**: the run-fatal flag locks every Lab row. It is not an independent Lab defect | P1–P4 receipt; my v1.1 verifier reported this as a contradiction without the cause (§5) |
| Morning contract identity | (not covered) | **D2**: 170 rows carry the Evening strike/expiry beside a different Morning OCC symbol; 0 on GO rows | *reproduced* independently from OCC symbols (§4.9); matches receipt |
| EV3 | 1,337 applicable / 0 evaluated | Unchanged for this stored run. The new engine replayed on it gives Morning 186/1,337 valued and Evening 0 (all `REJECT_QUOTE_STALE`, quotes ~50 h old) | EV3-OPT3 receipt §4 (*receipt claim*) |

**New hazard: post-run artefact overwrite.** `market_profile/completed_profile_summary_20260927_205123.json` is the path cited in the manifest's `output_files`. It was **rewritten at 16:49Z**, 100 minutes after the manifest (15:08Z), by the P4c real-scale proof (refused provider, 1,406 completed). The manifest's FAIL/0-rows describes the original file; the file on disk now describes a different computation. Any verifier that reads output paths without checking time and hash will attribute the wrong facts to the run. This is now a P0 rule (§4.1, V-RUN-04).

### 1.3 Corrections to inventory formula entries

| ID | Inventory text | Correction | Evidence |
|---|---|---|---|
| EV302 | "Requires hold exactly 5/10/20 for bucket 1_5D/6_10D/11_20D" | Now: hold ∈ {5,10,20} (materialised horizons), independent of the bucket. The contract is valued at the hold (`ev3_ev_*`, lead value) **and** at the move window (`ev3_move_window_*`, typed `NOT_EVALUATED` when it can't be valued, never copied from the hold) | `ev3_stage0.py:358-371`; `ev_engine_v3.py:891-933` |
| EV3 (new) | — | EOD quote-age gate `24*60*60` s; Morning 15 min (`ev3_stage0.py:451-467`). This rejects every contract on any Sunday Evening. **Open decision for ACK** (receipt §5): keep / widen / flag instead of reject | *source-read* |
| Hold (EO06/EO07, VOL10, EV302) | "planned hold = governed thesis window" treated as a design fact | ACK 28 Sep: hold must be analysis-determined per trade (intraday → 20+ sessions). Current code broadcasts one registry constant; see §4.14a | `intelligent_orchestrator.py:4109` |
| EV3 replay results | — | Every valued row is `NEGATIVE_EV` at the hold on three weekday replays (median ≈ −0.45); advisory, uncalibrated | *receipt claim* |
| AM06 | "spot ± .35 × max(5d move / wall / 2% proxy)" | It is a **fallback chain, not a max**: `spot − sign·max((garch_5d or wall_dist or max(spot·0.02, 0.01))·0.35, 0.01)`. A valid zero 5-day move falls through to the wall distance. Applies only when both `exit_invalidation_price` and `invalidation_level` are absent | `morning_validation.py:472-473` |
| AM06 input | — | `garch_5d` is **cumulative** (`cumulative_expected_move_pct(candidate,"1_5d")`), falling back to `expected_move_price` | `morning_validation.py:423-428` |
| §6.8 EV2 owners | root `ev_engine_v2.py`, `vanguard/ev_engine_v2.py`, `vanguard/ev_engine.py` | `vanguard/ev_engine.py` and `vanguard/ev_engine_v2.py` are **byte-identical** (15,021 B); the root copy differs (20,640 B). So there are two distinct EV2 implementations, not three | `cmp` |
| LAB (new) | — | Lab "Horizon" column is now "Move window"; "Hold" shows planned hold in sessions | `index.html:371,378` |
| OI/DOI (new) | — | Morning lifecycle store: missing-on-one-side fields are added facts (LIVE-M1). Content present on both sides that differs still fails closed | P1–P4 receipt |
| VG101–106 input (new) | — | Vanguard L1 profile evidence now reaches Vanguard via the `market_profile` ledger → thin package (P4c). Before P4c, manifest mode silently produced NOT_EVALUATED | P1–P4 receipt §P4c |

Formula claims re-read in source and **confirmed unchanged**:
- VOL02 (`n_fit=min(180,len(rv)-23)`, `Y=rv1[23:23+n_fit]`, `layer3_forward_variance.py:389-396`)
- VOL03 decay .92 (:419)
- VOL09 `days*5/7` (:296)
- VOL10 `vol·mult·sqrt(hold/252)`, hold 1–20 (`volatility_budget.py:98-117`)
- EC08 flattening `(gap/max(gap,.01))·premium·.5` (`layer4_mispricing.py:218-219`)
- MC03 `(gex+5e9)/1e10` (`normalise_macro_contract.py:181`)
- MC07: negative age still returns FRESH (`macro_quant_packet.py:228-240`)
- DOI04 median favourable + worst adverse (`deterministic_option_valuation.py:398-420`)
- OUT07: no commissions (`c12_outcome/expression.py`)
- LAB03 sort order (`lab_control.py:4176`)
- TEV08 C8 nulls (`expression_valuation_packet.py:138-158`)

---

## 2. Verification design rules (ACK, 28 Sep) and what they require

| Rule | Operational requirement for every check |
|---|---|
| **R1 Deterministic first** | A check is a test, lookup, recomputation or schema validation. Model judgment (the `avs-verifier` agent) may only *add* findings or *challenge* a deterministic result; it never produces a PASS on its own |
| **R2 Independent source material** | The oracle is primary data or an independent re-implementation: OCC symbol, raw bid/ask, canonical price store, hand worksheet. It is never the producer's own derived field, receipt or explanation. Receipts tell the verifier *where to look*, not *what is true* |
| **R3 Missing evidence ≠ pass** | Absent column, blank value, unreadable file, unresolved owner, post-run-modified artefact → `UNCERTAIN`, never PASS or silent skip |
| **R4 Verifier may abstain** | Verdict vocabulary: `PASS` / `FAIL` / `UNCERTAIN` / `NOT_APPLICABLE`. The run-level verdict is `UNVERIFIED` when any P0 check is UNCERTAIN |
| **R5 Source attribution** | Every factual verdict carries: file path, SHA-256 at read time, column(s), row keys (run_id, ticker, contract), observed value, reference value, oracle, tolerance |
| **R6 Approval outside the model** | Verifier output is advisory. No pipeline stage reads verifier output. Trade approval is ACK's; release approval is ACK's; the verifier never writes to run folders or code |
| **R7 Measure false approvals and false rejections separately** | Each rules version is scored against a labelled corpus (§6): FAR = bad items verdicted PASS ÷ bad items; FRR = good items verdicted FAIL ÷ good items; UNCERTAIN rate reported separately and never counted as either |

The inventory's three-verdict model (mathematically correct / implemented to spec / predictively useful) is kept. The verifier issues all three per calculation group, and the predictive verdict stays `UNCERTAIN` until outcome evidence exists (§4.20).

---

## 3. Four verification lanes

| Lane | When | What it proves | Tooling |
|---|---|---|---|
| **L1 Run-artefact checks** | After every Evening and every Morning | This run's book obeys invariants; recomputable fields match independent recomputation | `tools/avs_verify/avs_verify.py` (deterministic) + `avs-verifier` agent (challenge) |
| **L2 Reference-calculation tests** | On every change to a named owner | The formula reproduces an independent worksheet, including units and boundaries (inventory §8 plus §4 below) | Separate reference module under `tests/reference/`; production code never imported as its own oracle |
| **L3 Owner and wiring checks** | On every change; before any release | The live call path resolves to the owner assessed; hashes match the release snapshot; producer→consumer parity | Import resolution, source hash vs manifest, fixture flow-through |
| **L4 Predictive checks** | Weekly, once outcomes mature | Signals improve later, untouched outcomes after costs | C12 / DOI outcome ledgers; purged, embargoed cohorts |

---

## 4. Verification register by area

Legend. **Lane**: L1–L4. **Sev**: P0 = a FAIL or UNCERTAIN blocks a TRUST verdict; P1 = caveat; P2 = information. **Oracle**: the independent source. Items marked **NEW** are not in the v1.1 checker yet.

### 4.1 Run identity, timing and artefact integrity

| Check | Lane | Sev | Method / oracle | Missing-evidence verdict |
|---|---|---|---|---|
| V-RUN-01 Pipeline self-report (`run_tradeable`, permissions, `fatal_flags`, technical health) | L1 | P0 | Read `final_run_manifest.json`; report verbatim | UNCERTAIN if manifest missing |
| V-RUN-02 Evening timing: after 16:15 ET on a provider-complete session | L1 | P0 | run_id (treated as UTC; consistent with the 11 Sep run's 11:59Z cutoff)  and manifest evidence cutoff vs XNYS calendar (`avshunter/shared/xnys_calendar.py` as the independent calendar) | UNCERTAIN if neither present |
| V-RUN-03 Morning timing: thesis check pre-open; quote check 09:35–09:45 ET | L1 | P1 | manifest `created_at_utc` vs quote timestamps | UNCERTAIN |
| **NEW** V-RUN-04 Artefact integrity: every file the verifier reads, and every `output_files` path, must predate the manifest and not be modified after it | L1 | P0 | File mtime and SHA-256 vs manifest time. Any later write → UNCERTAIN for every check using that file. *Live case:* completed-profile summary rewritten 16:49Z vs manifest 15:08Z | — |
| **NEW** V-RUN-05 Code identity: the run's code hash (C0 run context / git adapter) equals a committed or recorded working-tree snapshot | L3 | P1 | `avshunter/c0_run/adapters/git.py` record vs source hashes | UNCERTAIN if not recorded (today: TESTED_UNCOMMITTED changes) |
| V-RUN-06 Manifest row counts reconcile with each book | L1 | P0 | count rows | UNCERTAIN |

### 4.2 Macro (MC01–MC17)

| Check | Lane | Sev | Method / oracle |
|---|---|---|---|
| V-MAC-01 Packet age recomputed from `as_of` vs run time; **negative age = FAIL** (MC07 labels it FRESH) | L1 | P1 | independent recompute |
| V-MAC-02 Row-level macro context coverage (inventory: 1,405 stale, 145 conflicting, 0 available) | L1 | P1 | counts from row columns; parent packet AVAILABLE does not imply row freshness |
| V-MAC-03 USMI sector mapping coverage on tradeable rows (100% `SECTOR_UNMAPPED` on 27 Sep) | L1 | P1 (known defect) | row counts |
| V-MAC-04 Authority: no gate/rank/permission reads macro fields (MC16 block language) | L3 | P0 | static call-path search from gate/rank owners; fixture that flips macro fields and asserts identical permission |
| V-MAC-05 MC01–MC15 boundaries: zero-via-`or`, VIX 26→.50, GEX `None` on no data, conviction >1 ÷100 | L2 | P1 | reference worksheet |

### 4.3 Scanner (SC01–SC09)

| Check | Lane | Sev | Method |
|---|---|---|---|
| V-SCN-01 Scanner CALL/PUT is never consumed as governed direction | L3 | P1 | call-path search; fixture flip |
| V-SCN-02 Synthetic IV-rank proxy (SC03) carries its source/confidence label to every consumer | L3 | P2 | field lineage |

### 4.4 Discovery and structure (DS01–DS22)

| Check | Lane | Sev | Method / oracle |
|---|---|---|---|
| V-DSC-01 `crabel_state` published CSV blank rate vs typed result (handoff risk) | L1 | P1 | counts per run |
| V-DSC-02 Direction present for every row reaching Options (CALL/PUT/UNRESOLVED/STRANGLE partition sums to total) | L1 | P0 | partition count |
| V-DSC-03 DS13/DS14 reference: compression uses high–low (not TR); rank is own-history | L2 | P2 | worksheet |
| V-DSC-04 DS17 "win probability" presented as heuristic wherever displayed | L3 | P1 | Lab/Interpreter label scan |

### 4.5 Vanguard L1 auction and completed profiles (VG101–VG106, P4c)

| Check | Lane | Sev | Method / oracle |
|---|---|---|---|
| **NEW** V-VG1-01 Completed-profile stage: `input_count > 0` and usable ratio ≥ 0.90, read from a summary that passes V-RUN-04 | L1 | P0 | stage summary + integrity. *27 Sep: FAIL (PKG-F5)* |
| **NEW** V-VG1-02 `layer1__auction_state` NOT_EVALUATED share among Vanguard rows. >50% = FAIL | L1 | P0 | row counts. *27 Sep: 1,616/1,616* |
| **NEW** V-VG1-03 Profile lineage: each evaluated row's `market_profile` dataset id exists in the canonical profile store for the evidence session | L1 | P1 | ledger/store lookup |
| V-VG1-04 TPO labelled time-at-price (not volume) wherever shown | L3 | P2 | label scan |

### 4.6 Vanguard L2 statistics (VG201–VG211)

| Check | Lane | Sev | Method |
|---|---|---|---|
| V-VG2-01 Match-ladder stage published per row; share of coarse fallback | L1 | P1 | counts |
| V-VG2-02 Probabilities in [0,1]; legacy 0–100 columns normalised by family | L1 | P0 | range check |
| V-VG2-03 Point-in-time: actuarial features at decision time use no later data | L4 | P0 for release | dated reconstruction via `forecast_path_reader` (revision ledger) |
| V-VG2-04 VG208 options-viability inside ticker edge: ticker verdict invariant when option data removed | L3 | P1 | fixture flip |

### 4.7 Volatility (VOL01–VOL13)

| Check | Lane | Sev | Method / oracle |
|---|---|---|---|
| V-VOL-01 Canonical `expected_move_{5,10,20}d_fraction` monotone non-decreasing per row | L1 | P0 | row check (v1.1 checks legacy GARCH increments; switch to canonical) |
| **NEW** V-VOL-02 Recompute canonical budget `σ_annual·sqrt(h/252)` from the published annual vol and compare. Reference: σ=.30 → .0422577 / .0597614 / .0845154 | L1 + L2 | P1 | independent recompute, tol 1e-6 |
| V-VOL-03 Legacy calendar increments (VOL09) never consumed as a full-horizon move | L3 | P1 | consumer trace; fixture |
| V-VOL-04 HAR fit window: early-slice vs recent-slice effect (inventory P2 finding) | L2 | P1 | dated sensitivity comparison |
| V-VOL-05 Bias multiplier unapplied unless VALIDATED + report id | L1 | P0 | `bias_multiplier_applied` false or report id present |

### 4.8 Options Intelligence and contract identity (OI01–OI13)

| Check | Lane | Sev | Method / oracle |
|---|---|---|---|
| V-OPT-01 OCC right (C/P) matches thesis direction | L1 | P0 | parse OCC symbol |
| **NEW** V-OPT-02 **OCC strike and expiry match the row's `strike`/`expiry`/`contract_*` fields** (D2). *27 Sep Morning: 170 mismatches, 0 on GO (reproduced)* | L1 | P0 on tradeable rows; P1 book-level | OCC symbol is the oracle |
| V-OPT-03 Spread recomputed as `(ask−bid)/mid` from raw bid/ask, compared with the published spread under its declared unit | L1 | P0 on unit mismatch | independent recompute |
| V-OPT-04 Delta sign vs right; |delta| band | L1 | P0 / P1 | row check |
| V-OPT-05 Multiplier: non-standard OCC contracts not priced at 100 | L1 | P1 | multiplier column vs OCC standardness |
| V-OPT-06 BS reference cases: parity, expiry intrinsic, zero-vol limit, Greek finite differences | L2 | P1 | independent pricer |

### 4.9 Legacy economics and EV2 (EC01–EC10, §6.8)

| Check | Lane | Sev | Method |
|---|---|---|---|
| V-ECO-01 `rr_options` recompute `(max(T−K,0)−mark)/mark` (CALL) from row fields | L1 | P1 | independent recompute |
| V-ECO-02 EC08 flattening: any consumer that ranks/gates on EC08 EV | L3 | P1 | consumer trace |
| **UPDATED** V-EV2-01 Owner resolution: which EV2 copy EIL actually imports (two distinct implementations: root, and vanguard ×2 identical) | L3 | P1 | runtime `module.__file__` in a fixture run |

### 4.10 EV3 (EV301–EV307, updated for option 3)

| Check | Lane | Sev | Method / oracle |
|---|---|---|---|
| **NEW** V-EV3-01 Functional coverage: weekday Evening valued count > 0. Rejection-reason partition sums to applicable rows | L1 | P1 (advisory stage) | `ev3_shadow_phase_status_*.json` + rejections CSV counts |
| **NEW** V-EV3-02 Move-window honesty: rows with `ev3_move_window_status=NOT_EVALUATED` have null `ev3_move_window_*` values, and no move-window value equals the hold value by copy (same row, both present and bit-identical → flag) | L1 | P0 | row check |
| **NEW** V-EV3-03 `ev3_hold_sessions` = the row's `planned_hold_sessions` on every EVALUATED row. The {5,10,20} restriction is itself a V-HOLD-04 finding, not a pass condition | L1 | P0 | row check |
| **NEW** V-EV3-04 Sunday-Evening quote-stale rejection reported as a policy effect (open ACK decision), not a pipeline failure | L1 | P2 | rejection reason + weekday |
| V-EV3-05 Authority: no gate, rank or permission reads `ev3_*` fields | L3 | P0 | static trace; fixture flip |
| V-EV3-06 Calibration: `INSUFFICIENT_OUTCOMES` until C12/DOI labels mature; predictive verdict UNCERTAIN | L4 | — | calibration readiness file |

### 4.11 Empirical EV shadow, DOI, TEV C3–C8

| Check | Lane | Sev | Method |
|---|---|---|---|
| V-DOI-01 `ranking_score_uncalibrated` never labelled EV or probability in Lab/Interpreter | L3 | P1 | label scan |
| V-DOI-02 DOI model activation off unless accepted (`config/doi_runtime.json`) | L1 | P0 | config read + hash |
| V-TEV-01 Governed C8 `ev_usd`/`ev_fraction`/`numeric_ev`/`best_expression` remain null until the signed design is implemented; research numbers labelled research | L1 | P0 | packet read |
| V-TEV-02 C5 frozen packet hash unchanged by Morning (append-only revision events) | L1 | P0 | hash compare |

### 4.12 Physics / probability companions (PH01–PR02)

| Check | Lane | Sev | Method |
|---|---|---|---|
| V-PHY-01 Scores named "probability"/"entropy" are displayed as heuristic scores with method label | L3 | P1 | label scan |
| V-PHY-02 PH06 macro bonus cannot change a gate/rank | L3 | P1 | fixture flip |

### 4.13 EIL, monetisation and execution ceilings (EX01–EX10)

| Check | Lane | Sev | Method / oracle |
|---|---|---|---|
| V-EXE-01 Final execution labels BUY_NOW/BUY_SMALL only on rows whose Morning permission is GO/GO_LIMIT/PROBE and whose run is not fatal | L1 | P0 | cross-field check |
| V-EXE-02 EX05 `SKIP` counted as not-evaluated, never as pass | L1 | P1 | partition |
| V-EXE-03 EX08 effective quote age recomputed from provider timestamp and verdict time | L1 | P0 (Morning) | independent recompute |

### 4.14 EOD candidates, horizon and exits (EO01–EO07)

| Check | Lane | Sev | Method |
|---|---|---|---|
| V-EOD-01 Candidate partition (thesis failure / repair / review / fatal) sums to population | L1 | P1 | counts |
| V-EOD-02 Move window, hold, DTE and expiry buffer published as separate fields; DTE ≥ hold in calendar terms | L1 | P0 | row check |
| *(replaced by §4.14a)* | | | |

### 4.14a Hold determination (corrected 28 Sep: ACK's requirement)

**Requirement (ACK, 28 Sep):** the hold is an output of the analysis, per trade. It can be anything from intraday to 20 sessions or longer. No fixed hold, no fixed cap.

**Current behaviour (source-read):**
- `intelligent_orchestrator.py:4109` sets `planned_hold_sessions = [_window] * len(patched)`, one value for every row, taken from the config registry key `outcome.window_sessions` (`:3978-3989`), source label `THESIS_WINDOW_D2`.
- 27 Sep Morning book: 1,550/1,550 rows = 20.0, source `THESIS_WINDOW_D2` (*reproduced*).
- The code comments attribute this to "ACK 18 Sep / D2". The registry key's name suggests an outcome-scoring window reused as a trade hold (*medium confidence*; ACK to confirm what D2 meant).
- A per-trade timing estimate already exists but is not used for the hold: `layer2__raw_expected_time_to_target` (27 Sep: 1,400 rows = 20, others 12–18; the 20s may be a cap, *unverified*).
- `anticipated_move_sessions` is only a 3-bucket map {5,10,20} from `horizon_bucket` (`:4102-4106`), so it cannot express intraday or >20.
- Structural limits that block an analysis-derived hold: `domain/volatility_budget.py:99` raises unless 1 ≤ hold ≤ 20 (integer sessions); EV3 accepts only hold ∈ {5,10,20} (`ev3_stage0.py:363`); `morning_gate.py:3826-3840` falls back to bucket upper bounds 5/10/20.

| Check | Lane | Sev | Method / oracle |
|---|---|---|---|
| **NEW** V-HOLD-01 Hold is derived per trade: FAIL if every tradeable row has the same hold, or if `planned_hold_source` names a config constant (e.g. `THESIS_WINDOW_D2`) rather than an analysis method | L1 | P0 (registered as a known defect until fixed, so it reports as a caveat rather than blocking every night) | distinct-value count + source label |
| **NEW** V-HOLD-02 Hold provenance: each row names the method and the inputs behind its hold (e.g. expected time to target, move window, catalyst date, vol budget) | L1 | P1 | source/method columns present and non-constant |
| **NEW** V-HOLD-03 Hold consistent with its own evidence: contract DTE ≥ hold (calendar-converted); hold not shorter than the time the analysis expects the move to take, unless the method says why | L1 | P0 for DTE < hold; P1 otherwise | row check against `expected_time_to_target`, move window, DTE |
| **NEW** V-HOLD-04 Downstream owners accept the full hold range: intraday (< 1 session), and > 20 sessions | L2/L3 | P1 | reference tests on `volatility_budget`, EV3 entry rule, Morning fallback. *Today all three reject it* |
| **NEW** V-HOLD-05 No hold mandate applied by the verifier: the old "15-day maximum" rule is withdrawn | — | — | removed from checker (`R15_HOLD_MANDATE`) |

### 4.15 Morning (AM01–AM07)

| Check | Lane | Sev | Method / oracle |
|---|---|---|---|
| **NEW** V-MOR-01 Thesis lock: direction, target, invalidation equal the same run's Evening values for the same ticker. Contract changes allowed only with `contract_repair_*` / identity rewrite recorded | L1 | P0 | join Evening file (`options_intelligence_<run>.csv` or pre-Morning candidates) on run+ticker |
| V-MOR-02 Contract identity after re-selection (V-OPT-02) | L1 | P0 | OCC oracle |
| V-MOR-03 Quote age at verdict time recomputed. Report the pipeline's own `quote_age_seconds` beside it, never instead of it | L1 | P0 when stale on both measures | independent recompute (27 Sep: 33–43 min at 15:08Z vs pipeline 13 min) |
| **NEW** V-MOR-04 AM06 synthetic invalidation never fills a governed stop: `invalidation_source` must be a sourced value on tradeable rows | L1 | P0 | source column check |
| **NEW** V-MOR-05 Lifecycle store conflicts: count `OptionLifecycleConflict` events in the run log, attributed by run id (inventory warns the shared log mixes test-fixture errors) | L1 | P1 | run-scoped log filter |
| V-MOR-06 Handoff finaliser completed (a candidates CSV alone is not Morning completion) | L1 | P0 | finaliser terminal record. *27 Sep: failed reconciliation* |

### 4.16 Intelligence Lab (LAB01–LAB08)

| Check | Lane | Sev | Method / oracle |
|---|---|---|---|
| V-LAB-01 Projection parity: Lab `opt__contract_strike/expiry/dte`, direction, verdict equal the upstream row | L1 | P0 | join Lab book to Morning book on ticker+contract |
| V-LAB-02 Duplicate headers (5 `usmi_*` on 27 Sep; identical copies) | L1 | P1 (P0 if copies differ) | header scan |
| **UPDATED** V-LAB-03 `lab_verdict` vs `final_action`: when a run-fatal flag is set, BLOCKED on every row is **expected**. Report it as a consequence of V-RUN-01, not a separate defect | L1 | P2 when explained by fatal flag, else P0 | manifest + row |
| V-LAB-04 Default sort (LAB03) is status-first, not EV-first; report as spec gap | L3 | P2 | `lab_control.py:4176` |
| V-LAB-05 UI parity JSON→API→HTML (move window, hold, EV3 lines) | L3 | P1 | browser check (receipt says passed; *receipt claim*) |

### 4.17 Interpreter / WAR (INT01–WAR05)

| Check | Lane | Sev | Method |
|---|---|---|---|
| V-INT-01 Every Interpreter claim cites eligible evidence with cut-off ≤ report time | L1 | P1 | citation schema check |
| V-INT-02 No Interpreter/WAR output changes permission | L3 | P0 | static trace |

### 4.18 Data owners (§5 of inventory)

| Check | Lane | Sev | Method |
|---|---|---|---|
| V-DAT-01 Revision-aware history: past decisions reconstructed with revisions known at the time (767-ticker volume revision of 25 Sep bar found 28 Sep) | L2/L4 | P1 | `ohlcv_daily_revisions` replay |
| V-DAT-02 Exact-contract joins never substitute nearest date or a different contract | L1 | P0 | OCC + quote date equality |

### 4.19 C12 outcomes / journal (OUT01–OUT09)

| Check | Lane | Sev | Method |
|---|---|---|---|
| V-OUT-01 First-passage labels: ambiguous → adverse and flagged; open/gap censored, never a loss | L2 | P1 | inventory §8 cumulative-incidence case |
| V-OUT-02 Quoted P&L uses multiplier (ask 2.20 / bid 2.00 ×100 = −$20) and costs are applied somewhere before any expectancy claim | L2 | P1 | worksheet |
| V-OUT-03 Every presented, rejected and missed candidate is recorded (selection-bias guard) | L1 | P1 | counts vs book |

### 4.20 Predictive usefulness

All predictive verdicts are **UNCERTAIN** until these exist: frozen temporal cohorts; purged/embargoed outcome labels; costs applied; coverage and censoring reported. The verifier reports readiness (label counts, maturity), not usefulness.

---

## 5. What my v1.1 verifier got wrong or missed on run `20260927_205123`

| v1.1 behaviour | Correct reading | Fix |
|---|---|---|
| R20 "authorities disagree 488/488" | Consequence of the run-fatal lock (PKG-F5); guard working as designed | V-LAB-03 links it to V-RUN-01 |
| Did not detect 170 wrong-strike rows | D2 defect, reproduced independently | V-OPT-02 |
| Checked legacy GARCH increments for monotonicity | Legacy increments are *by design* non-cumulative; the canonical fractions are the invariant | V-VOL-01 on `expected_move_*_fraction` |
| Optional columns missing → silent skip | Violates R3 | UNCERTAIN verdicts |
| Would have read the rewritten completed-profile summary as run evidence | Post-run overwrite | V-RUN-04 |
| R15 "hold beyond 15 calendar days" warning | Wrong rule: there is no hold cap. The real defect is that the hold is one constant (20) on every row instead of an analysis output | V-HOLD-01..05 |
| Findings carried counts, not citations | Violates R5 | structured evidence per finding |

---

## 6. Measuring false approvals and false rejections (R7)

**Labelled corpus v0** (built from evidence already in the repo; each item is *known-bad* or *known-good* with its source):

| Source | Label | Items | Evidence |
|---|---|---|---|
| D2 wrong strike/expiry | bad | 261 + 173 + 392 + 170 rows on four Morning books | EV3-OPT3 receipt table; 170 reproduced |
| Rows with OCC strike = row strike on the same books | good (for V-OPT-02 only) | 1,167 on 27 Sep | reproduced |
| PKG-F5 profile loss | bad (run-level) | run 20260927_205123 | P1–P4 receipt |
| 26 Sep profile build | good (run-level, for V-VG1-01/02) | run 20260926_173730 (1,480 profiles; run id inferred from the P4c offline proof, *medium confidence*) | P1–P4 receipt |
| Forced intraday Evening | bad (run-level) | 20260910_150045, 20260911_115904 | memory of 12 Sep correction; manifest cutoff |
| Spread unit reader test | bad for any reader that assumes percent | 10 Sep book: 1,205/1,205 spreads are fractions; a percent-assuming autodetect misread them (reader defect, not a pipeline mislabel) | 12 Sep independent review |
| Planted synthetic defects | bad | 5 rows + 4 book-level (existing synthetic runs) | `synth/` fixtures |
| Hand-verified clean GO rows | good | ≥ 30 rows, to be hand-checked by ACK | pending |

Reported per rules version: **FAR** (bad → PASS), **FRR** (good → FAIL), **UNCERTAIN rate** on each side, per check ID. A rules change ships only if FAR does not rise on any P0 check. The corpus is append-only; each new confirmed defect adds items.

---

## 7. Decisions needed from ACK (the verifier will not assume them)

1. **EV3 Sunday quote gate** (24 h EOD): keep, widen to the last completed session, or flag instead of reject. *Receipt §5.*
2. **Hold determination** *(decided 28 Sep: per-trade, analysis-determined, intraday to 20+ sessions)*. Still open: **what "D2" meant on 18 Sep**. If it was the outcome-scoring window, the hold wiring at `intelligent_orchestrator.py:4109` is a mis-implementation and needs a fix owner and a method specification (§4.14a).
3. **Tonight's Evening mode**: manifest mode with uncommitted P4c, or `AVSHUNTER_VANGUARD_INPUT_MODE=packages` rollback. *P1–P4 receipt, Readiness 18:00.* The verifier's V-VG1-01/02 will show which worked.
4. **Hand-verified good rows** for the corpus (§6), so false rejections can be measured at all.

---

## 8. Evidence read for this update

- `Enhancements/assessment/AVS_CURRENT_CALCULATION_INVENTORY_20260928/`: inventory markdown (all 710 lines), `inventory_summary.json`, `source_manifest.jsonl` (hash comparison)
- `Enhancements/assessment/AVS-EV3-OPT3_AND_CONTRACT_IDENTITY_BUILD_RECEIPT_20260928.md` (20:15 local)
- `Enhancements/assessment/AVS-PKG-002_P1_P4_BUILD_RECEIPT_20260927.md` (updated 16:53 local)
- Source read at the lines cited above (staged 28 Sep ~21:10 UTC)
- `data/output/runs/20260927_205123/final_run_manifest.json`, `morning_validation/morning_validated_trades_20260927_205123.csv`, `intelligence_lab/final_opportunity_book_20260927_205123.csv`, `market_profile/` and `ev3_shadow/` listings (mtimes)

Not done: no tests re-run, no pipeline run, no database read, no provider call. Receipt timestamps are UK local time (BST = UTC+1): the manifest's 15:08Z matches the receipt's "found 16:18" sequence, and the 16:49Z profile rewrite matches the receipt's 17:43–17:49 proof window. All times in this document are UTC unless marked BST.

# S0 receipt: freeze and measure (6 Oct 2026, ACK "start S0 and S1")

No production code was changed. The run was not modified.

## Freeze
- **Reference run:** `20261006_060401`, frozen by content hash: 1,766 files, 1,841,078,003 bytes.
  - Manifest: `s0/frozen_manifest_20261006_060401.json`.
  - Verify with: `venv\Scripts\python.exe Enhancements\assessment\AVS_LAB_SOURCE_OF_TRUTH_20261006\s0\freeze_run.py --run-id 20261006_060401 --verify`
- **Retention:** the run is outside the 14-day pruning. `prune_old_archives` deletes `data/archive` only (`intelligent_orchestrator.py:5105`).

## Baseline
- **Command:** `venv\Scripts\python.exe Enhancements\assessment\AVS_LAB_SOURCE_OF_TRUTH_20261006\s0\measure_baseline.py --run-id 20261006_060401`
- **Output:** `s0/baseline_20261006_060401.json`

| Measure | Value | Status vs earlier claims |
|---|---|---|
| Stage width (columns), rows 1,636 | discovery 514 · OI 1,075 · enriched 1,207 · EIL 1,296 · execution 1,359 · morning candidates 845 · morning validated 1,186 · execution gated 1,133 · Lab book 814 | Reproduced |
| Lab book size | CSV 212.8 MB · JSON 252.4 MB | Reproduced |
| Morning verdicts | GO 51 · FLAG 642 · BLOCK 943 | Reproduced |
| Lab verdicts | GO 24 · GO_LIMIT 27 · CONTRACT_REPAIR 19 · MANUAL_REVIEW 732 · BLOCKED 834 | Reproduced |
| GO without a computed option value (RC4 / E12) | 7: NET (volatility only), CYTK, UNP, BLDR, BIRK, ENOV, CENX | Reproduced |
| GO: anticipated PAYS and monetisability NOT_MONETISABLE | 33 | Reproduced. Different measures, not a defect count |
| GO: EV3 | 36 REJECTED · 15 evaluated · 26 negative · 0 positive | Reproduced |
| Lab rank vs anticipated-value order (Spearman) | −0.018 | Reproduced. Evidence that the rank does not use value; not an adequacy test |
| H1: columns lost from `execution_gated` | **71** | Reproduced |
| Morning timing | catalysts 1.6 min · gate 23.1 min · gate→Lab handoff **29.7 min** · total 54.4 min | Reproduced from the log |
| Lab `/api/run/latest` | 210 s / 300 MB (measured 6 Oct with curl) | Not re-run in S0: it blocks the Lab for minutes. The `--lab-url` option re-measures it under quiet conditions |

## Corrections found by measuring
1. **H3 / H7 spread units are more specific than the audit said.**
   - In the saved Morning file, `contract_spread_pct` and `spread_pct` are **fractions**: median 0.16, and on GO rows 0.087, which equals (ask−bid)/mid exactly.
   - The **percent** values sit in other `_pct` fields: `live_contract_spread_pct`, `ca_spread_pct_of_mid`, `execution_viability_spread_pct`, `spread_pct_of_mid`, `contract_spread_observed_pct`, all with median ≈ 15.9.
   - The policy limits `contract_spread_executable_max_pct` / `_review_max_pct` are stored as **18 / 25**, i.e. percent.
   - `contract_spread_pct_eod` holds values on both sides of 1 (894 of 1,492 above 1), so its unit needs a per-row check in S1.
   - The audit's claim that `contract_spread_pct` "becomes a percent after Morning" is **not** confirmed in this run.
   - The `_pct` suffix is used for both units: that is the defect.
2. **H6 is contained.** A missing target returns `DATA_MISSING` / `EOD_ASK_STRIKE_OR_TARGET_MISSING` before any valuation. The 0.0 default never reaches an output (pinned by test).
3. **Two target families on GO rows.** `target_price`, `structural_target` and the monetisability target agree with each other (source DISCOVERY_TARGET on 46 of 51, UNVERIFIED_LEGACY on 5). They differ from `thesis_outcome_level`, the anticipated move's input, by more than 1% on 36 of 45 rows.
   - Example: HPQ 36.23 vs 41.47.
   - Both families come from Discovery.
   - S1 classifies which is which measure.
4. **Probable root of some NOT_COMPUTED GOs (RC5, under S1 trace).** BLDR and CENX are PUT GOs whose 1d thesis event ("Failed Spring Continuation") has its outcome level **above** price (63.90 vs 55.63; 39.98 vs 36.94), while their lane setup is a bearish 1w/1mo SOW→LPSY. The anticipated move rejects a wrong-side level, so no value is computed, yet the row is a GO. This is passed to the S1 lineage trace.

## Characterisation tests
`tests/test_avs_sot_s0_characterisation.py`: **9 passed**. They pin today's behaviour, and each names the approved change that will flip it:
- Morning GO with a NOT_COMPUTED or volatility-only value (flips with E12); only DOES_NOT_PAY withholds GO.
- The Lab rank score moves with retired R:R and ignores the anticipated value (flips with E11).
- H1: the execution-gate CSV drops columns that are absent from the first row.
- EOD monetisability is valued at the legacy `target_spot` and is blind to the anticipated level; a missing target is labelled DATA_MISSING.
- H4: the Lab book's two target fields resolve the same inputs in opposite order.

Not pinned by a unit test (latent in this run, checked in S1 data): H2, the horizon router's CALL default. All 584 UNRESOLVED rows were routed to `horizon_blocked`.

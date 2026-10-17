# G4 build receipt — provider Greeks published, model Greeks labelled, observation history corrected

17 Oct 2026. Built test-first to the design in `G4_HESTON_GREEKS_ROOT_CAUSE_AND_DESIGN_20261017.md`. ACK approved it as recommended: keep the model Greeks as display-only `model_atm_*` fields, and append correction rows from the stored chains. This build implements decision D4 ("Heston overwrite retired; provider greeks").

**Nothing is committed.** ACK runs the next evening pipeline.

## What changed

| File | Change |
|---|---|
| `scripts/avshunter_options_intelligence.py` | `enrich_contract_with_heston_greeks` no longer writes `delta / gamma / theta / vega`. It publishes `model_atm_delta/gamma/theta/vega` with `model_greeks_basis = BS_AT_ATM_VARIANCE_DISPLAY_ONLY`. Vanna and charm now come from one correct BSM at the contract's own IV (`bsm_vanna_charm`, `vanna_charm_basis = BSM_CONTRACT_IV`); this replaces the ×(1+0.5·xi) heuristic and two wrong fallback formulas. `contract_greeks_source` returns `PROVIDER_EOD_CHAIN`, or `UNAVAILABLE` when the provider has no delta; there is no model fill. `calibrate_heston` skips Nelder-Mead explicitly on platforms without `SIGALRM`, and every proxy now records `proxy_reason`. The output row is built by `contract_greek_output_fields`, which adds the `contract_model_atm_*`, `contract_model_greeks_basis` and `contract_vanna_charm_basis` columns. |
| `canonical_data/option_liquidity_lifecycle.py` | New `record_observation_greek_correction`. It is append-only: it copies the superseded observation, replaces only the delta with the value from that ticker's MARKETDATA option chain, and links `supersedes_event_id`, reason, run and state `CORRECTED`. A new index `idx_option_observation_supersedes` is added. `latest_observation` now excludes superseded rows. |
| `canonical_data/option_outcome_maturation.py` | The exact-contract path reader excludes superseded rows, so a correction is never counted as a second quote. |
| `scripts/correct_observation_greeks_g4.py` | New one-off tool. It is a dry run by default; `--apply` writes, with one `CORRECTION` run per corrected run (`<run_id>_G4`). Chains are processed one at a time, so memory stays near 200 MB, and the plan takes about 25 minutes. It matches by contract and identical quote timestamp to the chain that the selected quote came from (`source_chain_dataset_id`), and verifies the content hash. Anything it cannot match is skipped and counted. |
| `tests/test_options_analytics_slice1.py` | The slice 1e expectation is updated: a computed model no longer changes the Greek source. |

**Tests added:**
- `tests/test_g4_heston_greeks_characterisation.py` (2): written first to pin the overwrite, then restated as the display-only model rule.
- `tests/test_g4_provider_greeks_published.py` (8): the business rules. All 8 failed before the fix.
- `tests/test_g4_observation_greek_correction.py` (8): plan, append-only supersession, readers see only the active row, the same quote in two runs corrected once per run, idempotent, agreeing or unmatched rows left alone, refuses non-chain sources.

## Evidence

**Regression run:** every test file importing a touched module, one process per file. 92 files, 960 tests: 957 passed, 3 failed, 0 errors. The 3 failures also fail on a baseline copy with the G4 changes removed, so they are pre-existing and unrelated:
- `test_avs_fix_002_stages2_5.py::test_stored_macro_rate_and_options_population_replay[20260910_150045, 20260911_115904]`: `RATE_UNAVAILABLE`.
- `test_b1_shadow_valuer_forecast_source.py::test_the_forecast_on_disk_for_the_active_run_is_used_at_age_zero`: `SCORE_NO_RUNWAY_ESTIMATE`.

**Acceptance replay** (`g4_acceptance_replay.py`): the fixed enrichment on stored selected contracts, with the stored MarketData chain for that date:

| | 15 Oct `20261015_225021` | 13 Oct `20261013_221020` |
|---|---|---|
| Published Greeks equal to the provider's | **100%** (2,153 / 2,153) | **100%** (2,156) |
| Source label | `PROVIDER_EOD_CHAIN` 100% | 100% |
| EOD repair band (\|Δ\| < 0.50, +7) changes | 379 (175 gain, 204 lose) | 388 (148 gain, 240 lose) |
| OIS vanna +3 awards before → after (changed) | 897 → 910 (87) | 894 → 897 (97) |
| EV3 theta > 20% mid / delta-sign rejects after | 0 / 0 | 0 / 0 |
| Proxy reason | 1,376 `TIMEOUT_UNSUPPORTED_ON_PLATFORM`, 777 `INSUFFICIENT_CALIBRATION_STRIKES` | — |

The display-only `model_atm_delta` reproduces the old published delta for 57–59% of contracts. The gap comes from different replay inputs, not from different logic: the evening's chain scope and ATM IV differ slightly from the full stored chain (e.g. JLL ATM IV 0.3815 vs 0.3786). It affects no published value.

This is a data-accuracy fix, and the targeted metric is agreement with the provider, now 100%. C12 outcome rates are context only.

## Observation history correction

**Dry run** (`g4_correction_dry_run_20261017.json`):
- **39,953 corrections planned** across 26 sessions (28 Aug–15 Oct). The largest error is 0.694; 2,417 rows were off by more than 0.10.
- **Skipped and counted, not guessed:**
  - 2,172 `NO_SOURCE_CHAIN_LINEAGE`: the older `live_option_quote_v1` intraday quotes from 1–17 Sep, which have no chain at the same time to verify against;
  - 5 `CHAIN_UNREADABLE_OR_INTEGRITY_FAILED`;
  - 2 `ALREADY_PROVIDER_DELTA`.

**Backup before apply:** `data/canonical/backups/control_plane_pre_g4_20261017.sqlite`. The table is append-only by trigger, so this backup is the rollback.

**Apply:** **39,953 corrections written**, exactly the dry-run plan, with one correction per superseded row. Verified in SQL:
- every correction is sourced from `OPTION_CHAIN`, with reason `G4_MODEL_DELTA_RECORDED_AS_PROVIDER`, state `CORRECTED` and version `G4_DELTA_CORRECTION_V1`;
- the table holds 314,553 rows, i.e. the 274,600 originals kept plus the corrections;
- `latest_observation` returns the provider delta (EVTL 15 Oct −0.3842, REKR −0.5588, PEPG 0.5362).

The apply ran in two passes:
1. **First pass:** a single correction run `20261017_G4_CORRECTION` stopped fail-closed after **305** rows. The cause: 6,157 quotes (12,314 rows) were recorded by two evening runs with the same thesis, contract and quote time, so their corrections collided on the store's identity and UNIQUE rule. The 305 rows are correct and properly linked, and are kept, because the table is append-only.
2. **Second pass:** **39,648** rows, using one correction run per corrected run (`<run_id>_G4`, 35 runs registered as `CORRECTION` with `corrects_run_id` in their metadata). A test now covers the two-run case.

`latest_observation` side effect, checked: a correction carries today's `observed_at`, so among rows with the same quote time it is now preferred. The only production caller, `should_fetch`, uses the quote time, which is unchanged because it is copied, and the liquidity state. Ordering among same-time rows was arbitrary before.

**Not corrected, by design:**
- The `LIVE_OPTION` `selected_option_quote_v1` JSON datasets under `data/canonical/live_options/` still hold the model Greeks for 28 Aug–15 Oct. They are content-addressed and immutable. The observation table now carries the provider delta, and its lineage points to the chain.
- Morning `EXACT_OPTION_QUOTE` rows and chain-sourced rows were already provider values.

## Defect register: what this closes and what stays open

- **Closed:**
  - G4 (Heston proxy Greeks overwrite);
  - D4's "Heston overwrite retired; provider greeks for display";
  - the observation store recording a model delta as `MARKETDATA` (rule R6);
  - the wrong fallback vanna and charm formulas.
- **Open:**
  - G5: one rate and IV basis (vanna and charm still use `RISK_FREE_RATE` 0.045).
  - Missing-Greek defaults in `compute_trade_economics` (θ −0.01, vega 0.05, Δ 0.35; rule R1).
  - D4's "explicit-IV model inside valuation", which belongs to G1.
  - The 2,172 unverifiable 1–17 Sep live-quote rows.
  - The selected deep-ITM puts with provider IV of 300–700%.

**Next evening run check:** rerun `g4_greeks_vs_provider.py <run_id> <date>` on that run. Expect 100% identical delta and `contract_greeks_source = PROVIDER_EOD_CHAIN`.

# G4 — Heston proxy Greeks overwrite the provider Greeks: root cause and fix design

17 Oct 2026. **For ACK's approval. No code changed.** This is gap G4 in `OPTIONS_VALUATION_GAP_REVIEW_20261017.md`. Replication script: `g4_greeks_vs_provider.py` in this folder (read-only).

## 1. The defect in one line

Every evening, Options Intelligence replaces the selected contract's provider delta, gamma, theta and vega with Black-Scholes Greeks computed at the ticker's at-the-money variance. The replacement ignores the contract's own IV and skew. Those Greeks then travel as `contract_delta / gamma / theta / vega` into the EOD candidate book, EV3 unit checks, the Lab and the canonical observation store, and the store labels them `MARKETDATA`.

## 2. Evidence (measured against reality)

Published Greeks were compared with the MarketData end-of-day chain for the same contract and date (`data/canonical/market_observations/option_chain/<date>`):

| | 15 Oct run `20261015_225021` | 13 Oct run `20261013_221020` |
|---|---|---|
| Selected contracts / matched to provider chain | 2,153 / 2,153 | 2,156 / 2,156 |
| Source label | 100% `HESTON_ATM_VARIANCE_MODEL` | 100% |
| Delta identical to provider | **0.0%** | **0.0%** |
| Delta abs error p50 / p90 | 0.020 / 0.125 | 0.019 / 0.116 |
| Delta off by > 0.05 / > 0.10 / > 0.20 | 25.1% / 13.7% / 4.2% | 23.0% / 12.1% / 3.9% |
| Gamma relative error p50 / p90 | 11.9% / 52.6% | 10.4% / 50.6% |
| Theta relative error p50 / p90 | 17.3% / 117% | 15.6% / 109% |
| Vega relative error p50 / p90 | 0.7% / 7.7% | 0.7% / 6.4% |
| EOD repair band (\|Δ\| < 0.50) on the wrong side | **379** | **388** |
| Delta sign flips | 1 (DCGO put published Δ 0.000, provider −0.517) | 0 |

The worst cases are skewed small caps:

| Contract | Provider Δ | Published Δ |
|---|---|---|
| EVTL put | −0.38 | −0.98 |
| REKR put | −0.56 | −0.006 |
| ALT put | −0.50 | −0.97 |
| PEPG call | 0.54 | 0.97 |

The 14 Sep decision map had already found 58 contracts off by more than 0.10, and showed that the provider delta matches an independent BS (`DECISION_PATH_MAP_20260914_214012.md:132`). The universe has grown since, and roughly 260–295 contracts per run are now off by more than 0.10.

## 3. Root cause (three layers)

1. **The model is ATM-only by construction.** `heston_greeks` (`scripts/avshunter_options_intelligence.py:2375-2453`) uses only `v0` (ATM variance) and `xi` from the Heston parameters. Delta, gamma, theta and vega are plain BS at σ = √v0 for every strike, with no dividend and r = 0.045. Even a perfect Heston fit would not change these four Greeks. The docstring's "more accurate" claim is false for any contract away from the money.
2. **The overwrite is unconditional.** `enrich_contract_with_heston_greeks` (:3966-4035), called at :8764 *after* contract selection, writes the model values over the provider's (:4022-4029) whenever parameters exist. The parameters always exist:
   - On Windows, `signal.SIGALRM` does not exist (:2274). The `AttributeError` falls to the outer `except` (:2307), which returns `_calibrate_heston_proxy`.
   - Nelder-Mead never runs (`heston_fit_error` is null on 100% of rows), yet `heston_used = True` is set.
3. **Governance gap: an approved retirement was never carried out.** ACK decision D4 says "Heston overwrite retired; provider greeks for display, explicit-IV model inside valuation" (`BUSINESS_DOMAIN_DESIGN_ADDENDUM.md:384`; `DECISION_PATH_MAP_20260914_214012.md:369` RESOLVED; `END_TO_END_PIPELINE_MAP_AND_FIX_DESIGN.md:628`). The 30 Sep analytics slice 1e added only a provenance label, `contract_greeks_source` (:3939-3947). The defect became visible, but it was not removed.

## 4. Where the wrong Greeks act

| Consumer | Use | Effect |
|---|---|---|
| `eod_candidate_engine.py:1568, 1604` `_contract_repair_profile` | +7 repair points when 0 < \|Δ\| < 0.50 | about 380 contracts per run scored on the wrong side |
| `eod_candidate_engine.py:1426` `_contract_side` | side from delta sign when the symbol is unparseable | wrong or blank side possible (DCGO Δ 0) |
| `vanguard/ev3_stage0.py:548-566` | unit checks on delta sign, gamma, and theta > 20% of mid | no reject differences on these two runs, but checked on the wrong numbers |
| `scripts/avshunter_options_intelligence.py:7110-7112` `compute_trade_economics` | theta drag, vega risk, delta | legacy economics and score inputs |
| `compute_ois` :7517-7527 | vanna ×(1 + 0.5·xi) from ATM vol: **+3 OIS points**; charm warning | vanna measured at the wrong vol |
| `evening_contract_analytics` :3950 → Lab / book | displayed Greeks, labelled `iv_source="PROVIDER_EOD_CHAIN"` | display contradicts its own label |
| `option_contract_observations` (canonical store) | stores `delta` with `source_provider = MARKETDATA` | **model value recorded as an observed quote**, 28 Aug–15 Oct (rule R6) |
| Morning (`morning_gate.py:419, 2145`) | uses live provider Greeks; **falls back to the evening `contract_delta`** when the live quote is missing | the fallback inherits the model delta |

## 5. Fix design (minimal; implements D4)

**Principle:** the provider's Greeks are the published Greeks. Model Greeks may be shown under their own names, labelled, and they never replace an observation. This follows repair-don't-delete: the calibration and the model are kept, and only the overwrite goes.

1. **Stop the overwrite.** `enrich_contract_with_heston_greeks` no longer writes `delta / gamma / theta / vega`. It publishes `model_atm_delta`, `model_atm_gamma`, `model_atm_theta` and `model_atm_vega`, plus `model_greeks_basis = "BS_AT_ATM_VARIANCE_DISPLAY_ONLY"`. These are added to the output row next to the existing `contract_*` fields. They are display-only, and no consumer reads them.
2. **Vanna and charm from the contract's own IV.** Compute both with BSM at the contract's provider IV and publish `vanna_charm_basis = "BSM_CONTRACT_IV"`.
   - Drop the unvalidated ×(1 + 0.5·xi) amplification and the ±1 clip.
   - Use one correct BSM implementation. The existing fallback formulas are both wrong: vanna is `vega·d1/(S·σ)` instead of −d2·φ(d1)/σ (:3992), and charm uses `d1` where `d2` belongs (:3997).
   - The OIS vanna rule (+3) is left as is; it now reads a vanna measured on the right vol. The change in OIS points is reported at acceptance (step 6). No new authority is added.
3. **Missing is never neutral.** If the provider has no Greeks for the selected contract, the published Greeks stay null and `contract_greeks_source = "UNAVAILABLE"`. There is no model fill. (This affected 0 of 4,309 selected contracts on the two runs, so it is a guard, not a behaviour change.)
4. **Honest calibration label.**
   - On platforms without `SIGALRM`, skip Nelder-Mead explicitly rather than through a caught `AttributeError`.
   - Record `heston_params_method = analytical_proxy` with the reason `TIMEOUT_UNSUPPORTED_ON_PLATFORM`.
   - `heston_used` keeps its meaning "model Greeks computed", and `contract_greeks_source` returns `PROVIDER_EOD_CHAIN`.
   - Full calibration is **not** enabled. It would cost seconds per ticker across about 2,000 tickers. It changes none of the four Greeks (root cause 1), and D4 retires it from the published Greeks.
5. **The observation store records only observations.** From the fix forward, `option_contract_observations.delta` is the provider's delta.
   - History (28 Aug–15 Oct, about 274,600 rows) needs ACK's choice, see §8.

## 6. Test-first plan (CLAUDE.md working rules)

1. **Characterisation (pins today's behaviour before it changes):** `tests/test_g4_heston_greeks_characterisation.py`. Given a skewed chain on a platform without `SIGALRM`:
   - calibration returns `analytical_proxy`;
   - the enriched delta equals BS at √v0 rather than the provider delta;
   - the source label reads `HESTON_ATM_VARIANCE_MODEL`.
   This test is rewritten to state the new rule when the fix lands.
2. **Failing business-rule tests** (`tests/test_g4_provider_greeks_published.py`), in domain language:
   - "The selected contract's published delta, gamma, theta and vega are the provider's quote for that contract."
   - "Model Greeks appear only under model-named fields with their basis, and never replace the provider's."
   - "A contract with no provider Greeks is published as UNAVAILABLE, never filled by a model."
   - "Vanna and charm are computed from the contract's own IV, and the basis is named."
   - "A platform that cannot time out calibration records the proxy method and the reason."
   - "The canonical option observation carries the provider's delta."
3. **Existing tests to update:** `tests/test_options_analytics_slice1.py:90-102`. The label function stays, but the production path now yields `PROVIDER_EOD_CHAIN`. Rerun these too, one file per process, counting failures explicitly:
   - `tests/test_contract_analytics_slice2.py`
   - `tests/test_ila_selected_contract_identity.py`
   - `tests/test_f7_call_put_iv_spread.py`
   - `tests/test_ev_engine_v3.py`
   - the EOD candidate tests
4. **Acceptance against reality:** rerun `g4_greeks_vs_provider.py` on the first evening run after the fix, and a replay of the stored 13 and 15 Oct chains. It passes when:
   - 100% of matched selected contracts have published Greeks identical to the provider's;
   - repair-band disagreement is 0;
   - the report lists how many OIS vanna +3 awards and EV3 unit-check outcomes changed.
   This is a data-accuracy fix, so the targeted metric is agreement with the provider. C12 outcome rates are context only and are not expected to move on their own.

## 7. Scope

**Files touched:** `scripts/avshunter_options_intelligence.py` only (`calibrate_heston` timeout path, `heston_greeks` / `enrich_contract_with_heston_greeks`, output row fields at about :9036-9044), plus the new and updated tests above. No configuration value changes. Morning, EOD, EV3 and Lab code is untouched: they start receiving provider Greeks through the existing fields.

**Not in scope** (logged as follow-ups, not part of this change):
- G5: one rate source and IV basis.
- The missing-Greek defaults in `compute_trade_economics` :7110-7112 (θ −0.01, vega 0.05, Δ 0.35). These treat a missing value as neutral (rule R1).
- The "explicit-IV model inside valuation" half of D4, which belongs to G1.
- An observation from this review: several selected contracts are deep-ITM puts on names with provider IV of 300–700% (e.g. ALT 677%, BLND 410%), and NLOP shows IV 0.0001. This is worth its own check of contract selection and IV quality.

**Timing:** the code change waits until no pipeline or Phantom backfill is running (no edits during runs).

## 8. Decisions needed from ACK

1. **Approve the root cause and the design in §5.** Recommended.
2. **Model Greeks:** keep them as labelled display-only `model_atm_*` fields (recommended, repair-don't-delete), or drop them entirely (tidy-after-build)?
3. **Observation-store history (28 Aug–15 Oct):** the choices are:
   - (a) append correction rows with the provider delta from the stored chains, using the table's existing `supersedes_event_id` / `correction_reason` columns (recommended, auditable);
   - (b) leave the history and document the caveat for replay and C12 consumers;
   - (c) both.

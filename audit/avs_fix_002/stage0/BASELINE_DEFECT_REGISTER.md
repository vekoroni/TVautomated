# AVS-FIX-002 Stage 0 baseline defect register

## Governed baseline result

Command: `C:\Python314\python.exe tools\run_governed_pytest.py -q`  
Result: **1,756 passed / 29 failed / 4 skipped / 286 subtests passed**

## Failure groups

| Group | Count | Stage disposition | Treatment |
|---|---:|---|---|
| MSI size/producer/caller “absence” characterisations | 3 | Stage 0/4 | W01, F08 and F10 fail because later production work now supplies the evidence their old tests assert must be absent. Replace with positive propagation/integration assertions; never weaken the desired behaviour. |
| MSI quote refresh/comparison and bundle projection | 16 | Stage 4–5 | W05, W07, L01/L02/L09, R05 and R06 expose a mixture of stale negative characterisations and genuine quote-comparison/read-model gaps. Reconcile each against v1.2 exact-contract refresh and Lab v4 before editing its assertion. |
| MSI vocabulary/quality states | 2 | Stage 1/4 | F04 requires a canonical positive-size vocabulary decision; F05 confirms crossed quotes currently collapse to coarse `INVALID`. v1.2 requires a named crossed-market execution defect. |
| MSI structure detection/quality characterisations | 2 | Stage 5 | L07 and related structure assertions remain governed context work. They cannot change thesis or execution authority. |
| MSI nested regression runtime | 1 | Stage 0 harness repair | R07 hardcodes `.codex_python313_runtime`, which lacks standalone application packages. Replace the hardcode with the governed production-runtime runner. |
| CDS historical-price tests | 3 | Stage 0 harness isolation | All three pass independently. Their full-suite failures are order-dependent shared-state contamination; isolate/reset the responsible state before treating any as product regressions. |
| Intelligence Lab legacy label | 1 | Stage 5 | The old literal `Quote Freshness` is absent. v1.2 requires current execution evidence and provider timestamp lineage; implement the governed concept rather than restoring a misleading stale-trade veto. |
| Other MSI presentation assertion | 1 | Stage 5 | Reconcile the exact inline-field assertion against `lab_signal_book_v4` and the separate domain-state presentation contract. |

## Rules for remediation

1. Tests that say “expected to fail”, “if this fails the finding is stale”, or assert zero production callers/producers are characterization evidence, not valid permanent success criteria.
2. Such tests must be replaced with assertions of the desired v1.2 behaviour only when the corresponding producer/consumer path is verified.
3. Genuine missing fields or coarse states remain failures until their work package closes.
4. No production calculation is changed merely to satisfy obsolete literal wording from a superseded design.
5. The complete suite must be green at Stage 7; this register is not a permanent waiver.

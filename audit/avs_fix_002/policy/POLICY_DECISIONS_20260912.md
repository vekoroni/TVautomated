# AVS-FIX-002 Governed Policy Decisions — 2026-09-12

**Owner:** ACK
**Authority:** Advisory classifications only; human execution remains mandatory.
**Approval ID:** `ACK-20260912-AVS-FIX-002`

## Approved

1. Scenario monetisability profit floor: `0.25` net return after modelled friction.
2. Preferred-contract hysteresis: switch only when the challenger improvement is at least the greater of `0.05` net-return utility units and `10% × |incumbent utility|`; terminal identity/data defects may replace immediately.

These policies classify and rank contract evidence. They do not delete a ticker thesis, grant capital, execute a trade or represent a probability.

## Evidence-gated, not approved by declaration

Forecast-volatility bias remains at multiplier `1.0`. A non-unit multiplier requires all of: owner approval; `validation_state=VALIDATED`; an immutable `validation_report_id`; and `held_out_validation_passed=true`. The implementation rejects partial/manual activation.

## Capital-allocation boundary closed

ACK confirmed that AVSHUNTER is capital-agnostic and exists to identify and explain monetisable opportunities, not allocate capital. The `capacity_v1` calculator, desk-budget configuration and Lab capacity projection are retired. Contract ask and multiplier remain contract evidence. Human execution—or a future separately governed portfolio service—owns position sizing and capital allocation.

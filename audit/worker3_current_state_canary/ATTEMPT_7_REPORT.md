# Worker3 evidence-coverage live canary — attempt 7

PASS: technical acceptance and semantic lint passed. Status is REQUIRES_HUMAN_REVIEW with zero findings, the intended advisory workflow. Production remains disabled; this run did not deploy or enable it.

One token-count preflight and one generation occurred with a $1.00 ceiling and no retries. The provider accepted the schema and returned HTTP 200. Structural validation and semantic lint passed. The result was durably saved in the disposable canary store as REVIEW_REQUIRED. JSON and HTML report routes returned 200, six wrong-identity checks returned 404, and both same-process and fresh-process replay returned the same assessment without another provider call.

Provider latency was 57.318 seconds. Usage was 95,131 input tokens and 3,178 output tokens. Recorded usage-priced cost: $0.333063. Cumulative paid-attempt list-price cost: $1.963701. The conservative preflight bound was $0.420561. No unknown cost reservation remains for this attempt. These are usage-derived list-price amounts; invoices, discounts and taxes are not verified.

The evidence-coverage blocker observed in attempt six did not recur. This is one successful live AAOI CALL canary, supported by 314 prior offline tests; it is not proof of every ticker or unattended production reliability. Human review remains required and execution_permission remains false. The production deployment and operating budget still need a concrete rollout step; no unrestricted automation or trading authority is granted by this report.

All 1,671 protected files remain unchanged. Historical attempts and the current latch are preserved. The successful assessment is exported separately for human review; the canary stores were disposable.

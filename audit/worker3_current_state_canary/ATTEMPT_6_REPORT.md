# Worker3 schema-constrained live canary — attempt 6

The technical canary passed. The assessment remains semantically BLOCKED and requires review; production remains disabled.

## Verified end to end

One token-count request and one generation were made with a $1.00 cap and no retries. The provider accepted the schema and returned HTTP 200 with complete output. Structural validation passed; the result was durably saved in the disposable canary store as REVIEW_REQUIRED. JSON and HTML report routes returned 200, all six wrong-identity route checks returned 404, and both same-process and fresh-process replay returned the same assessment without another provider call.

Provider latency: 64.695 seconds. Usage: 94,558 input tokens and 3,691 output tokens. Recorded usage-priced cost: $0.339039. Cumulative paid-attempt list-price cost: $1.630638. No unknown cost reservation remains for this attempt. Invoice amounts, discounts and taxes are not verified. The schema-inclusive conservative preflight bound was $0.418842.

## Remaining report-quality gate

Semantic review flagged three summaries with empty claim_ids:

- COMPANY: company classification and absence of catalyst evidence.
- CONTEXT: macro regime and market-context statements.
- CHANGES: absence of a previous assessment and comparison evidence.

These are the recorded semantic findings: section:CHANGES:UNCITED_SECTION_REVIEW, section:COMPANY:UNCITED_SECTION_REVIEW, section:CONTEXT:UNCITED_SECTION_REVIEW. Technical canary acceptance checks infrastructure and persistence; it does not mean semantic acceptance or deployment approval.

The next engineering step is to enforce grounded section coverage, including a principled representation of unavailable comparison evidence. Do not attach arbitrary claims merely to silence the review flags. Recheck the saved report offline before another paid run.

All 1,671 protected files remain unchanged. The canary used disposable stores; this did not deploy or enable production. The report JSON is exported separately for review.

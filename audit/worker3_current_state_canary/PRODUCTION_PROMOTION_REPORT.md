# Worker3 controlled production promotion

Status: release promoted on disk; running Intelligence Lab restart pending.

Enabled release AVS-W3-PRODUCTION-20260907-001 with Claude Sonnet 4.6, one job per activation, one call per process, a $1.00 per-call ceiling and $1.00 cumulative release ceiling. Request limits match the successful canary: 8,192 output tokens, 500,000 input bytes and a 300-second timeout. Semantic review, human review, operator approval, advisory-only authority and no execution permission remain enforced.

Revalidated and promoted the successful canary assessment into data/worker3/analyst_reports.sqlite. Its original assessment identifier, generated time, evidence, response and zero-findings status are preserved. This was an existing report import, not a new provider call or fabricated production generation. No additional API charge was incurred.

Loaded the actual production Intelligence Lab module in a fresh process and verified its report route returns HTTP 200 with the promoted assessment. The existing port-5002 process predates promotion and still returns 404 for that route. Windows denied Stop-Process for its verified Python PID 18456, so it was left running. The operator must restart Intelligence Lab using its normal launcher before this promotion becomes visible in that running app.

Report URL after restart: http://localhost:5002/worker3/report/20260906_213931/AAOI/d1dd7da9ccb8e6de48447f36113286c22cffd914c801554fbf8ec84b4c44a555

No recurring worker scheduler or bulk worklist was created. Newly dispatched jobs still require explicit operator approval and fit within the controlled release budget. This promotion does not authorize unrestricted spending or trading.

Preservation: of 1,671 protected files, only the intended provider release contract changed. Source pipeline outputs and trading data remain unchanged. The newly created Worker3 report store is separate.

Rollback: restore audit/worker3_current_state_canary/production_release_before.json to contracts/worker3_provider_release_v1.json, then restart Intelligence Lab. Retain the report database and audit evidence; disabling the release hides the optional report routes without deleting history.

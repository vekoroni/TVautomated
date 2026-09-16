# Worker3 canary attempt 4 and cost assessment

One paid generation was authorized with a $1.00 ceiling. One token-count preflight and one generation occurred, with zero retries.

The provider returned HTTP 200 in 61.746 seconds with end_turn, 83,883 input tokens and 5,106 output tokens. The response completed all eight claims and eight sections without truncation. It failed strict JSON validation because of a Markdown code fence. Removing only that fence for offline diagnosis exposed a further numeric value/unit mismatch with the source. The original response and failure state are preserved; this is not an accepted assessment.

## Costs

| Attempt | List-price API cost |
|---|---:|
| 2: client disconnected | $0.293349 |
| 3: truncated response | $0.372399 |
| 4: complete but invalid response | $0.328239 |
| Total | $0.993987 |

Rates: $3 per million input tokens and $15 per million output tokens for Claude Sonnet 4.6, verified at https://platform.claude.com/docs/en/about-claude/pricing. Attempt 4 reported standard service, global inference, and no cache tokens. Costs are calculated from recorded usage, not verified invoice amounts; discounts and taxes are excluded. A local $1.00 reservation remains for the failed job and is not an additional provider charge.

At the same token usage, 1,000 attempts would cost $328.239 in API usage alone. This is an illustrative linear extrapolation, not a production forecast: input sizes and retries vary. Cost per successful assessment remains unmeasured because this canary did not pass validation. Full TCO must additionally include hosting, storage, monitoring, maintenance, human review and any upstream data or model costs. Those costs were not measured here.

## Verification and next step

Nine existing canary tests passed. The offline harness also passed with the $1.00 cap, including fresh-process replay. All 1,671 protected files remain unchanged, and production remains disabled. The default cap remains $0.50; this run explicitly selected --max-cost-microusd 1000000. The previous latch was archived and the new attempt latch remains in place.

Next engineering work is to enforce a bare JSON output contract and diagnose the exact numeric binding mismatch against the saved response offline. No further paid generation is authorized or attempted by this report.

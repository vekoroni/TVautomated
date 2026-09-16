# Worker 3 timeout solution

The permanent workspace setting worked: attempt two's token-count request returned
HTTP 200 for claude-sonnet-4-6. The request contained 83,173 input tokens and
allowed up to 8,192 output tokens. Its preflight cost ceiling, including counting
margin, was $0.384687.

Generation then failed after 60.086 seconds without an HTTP status, response body,
or usage counters. That timing is consistent with the 60-second client timeout;
the old sanitized receipt does not prove the precise exception. The local timeout
does not establish cancellation on Anthropic's servers. Actual usage/charge is
unknown. The $0.50 reservation is a local accounting hold, not a confirmed bill.

## Implemented fix

- The canary's temporary release and prepared request now use a 300-second response
  timeout. The provider transport and release validator permit at most 300 seconds.
- The coordinator runtime derives its lease from the approved timeout plus a
  60-second validation/save margin (minimum 120 seconds). A 300-second canary gets
  a 360-second lease. This avoids discarding a late valid response because the
  former fixed 120-second lease expired.
- Transport receipts record safe TIMEOUT, CONNECTION_ERROR or DECODE_ERROR codes
  and the failure stage (sending, awaiting headers, reading or decoding). Exception
  text and credentials are not included in those diagnostics.
- UNCERTAIN charge records now persist the sanitized receipt and runtime failure
  stage, without releasing the reservation. Reopening the database retains them.
- The existing request fingerprint includes timeout configuration, so this is a
  newly prepared request configuration rather than alteration of a staged job.

No model, input evidence, output-token allowance, price schedule, one-call limit,
or $0.50 ceiling was changed. The checked-in production release is unchanged and
disabled. Prior attempt evidence and the live-attempt latch remain unchanged.
No live API request was made while implementing this fix.

## Verification

279 original Worker 3 tests passed. A further 54 configuration, macro and Worker 3
integration/regression tests passed (333 total). New tests use virtual time to
complete a response after 250 seconds, validate replay without another call,
retain timeout diagnostics and the unknown-cost reservation across database reopen,
and reject a timeout above the 300-second maximum before networking.

## Next action

Reconcile the prior uncertain request against Anthropic Console usage/billing
before authorizing another paid attempt. A newly authorized canary can then use
this longer window with the same $0.50 limit and no automatic retries. End-to-end
live acceptance remains unproven until a full valid response is received, saved,
reviewed, projected and replayed.

This addresses the demonstrated local wait/lease limitation. It cannot guarantee
provider availability or network reliability. For repeated long-running failures,
Anthropic recommends streaming or Message Batches to reduce reliance on a single
idle HTTP connection; those mechanisms require separate integration work and are
not enabled by this change.

Reference: https://platform.claude.com/docs/en/api/errors#long-requests

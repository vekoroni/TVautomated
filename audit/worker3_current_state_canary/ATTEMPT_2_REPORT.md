# Worker 3 canary rerun — attempt two

**Workspace configuration passed; full canary remains NO-GO.**

The user's new rerun authorization allowed one free token-count request and at
most one paid generation, within $0.50 and with no retries. The first attempt's
latch was preserved as LIVE_ATTEMPT_1_LATCH.json. The new latch remains in place.

- Candidate: AAOI / CALL, governed run 20260906_213931.
- Model: claude-sonnet-4-6.
- Persistent workspace configuration: loaded successfully; token-count HTTP 200.
- Counted input: 83,173 tokens.
- Output ceiling: 8,192 tokens.
- Cost ceiling including 4,096 additional input tokens: $0.384687.
- Generation requests: one. Retries: zero.
- Generation receipt: TRANSPORT_OR_DECODE_ERROR after 60,086 ms.
- No HTTP status, response envelope, or usage counters were received for generation.
- Durable terminal job state before disposable-store teardown: UNCERTAIN.
- Actual provider charge: unknown. The $0.50 reservation is retained in the exported accounting.
- Structural validation, semantic review, live report projection and completed-response replay: not reached.
- Production release: unchanged and INSTALLED_DISABLED.
- Protected files: 1,671 checked, zero changes.

The elapsed time is consistent with the configured 60-second HTTPS timeout.
The transport deliberately masks exception details, so the precise network
exception is not proven. This was a transport-stage failure, not evidence that
the model returned structurally invalid content. A missing response also does
not prove that the provider did not process or charge for the request.

The request was frozen and bound to its token-count hash. Identity and request
hashes, activation, durable events, charge reservation and sanitized receipts
are retained in live_attempt_2.json. No API key or workspace identifier is
included in this report.

No further provider request was made. Reconcile the uncertain request/charge
before authorizing another attempt. A future timeout adjustment must review
both the HTTP timeout and the job lease; increasing only one can create a
late-response/expired-lease failure. The existing completed-response replay
controls cannot recover a response that was never received.

The earlier 330 offline checks remain applicable; this rerun changed no code.
This result validates the permanent workspace setup and token-count path, but
not a completed live assessment, its evidence grounding, or trading accuracy.

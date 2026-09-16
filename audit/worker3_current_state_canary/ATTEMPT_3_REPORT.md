# Worker 3 controlled canary — attempt three

**NO-GO for production activation. Workspace and longer-timeout transport passed;
the model response was truncated and the partial output violated the v2 contract.**

## Authorized execution

The user instructed the agent to proceed after the timeout fix. The prior
attempt-two latch and evidence were preserved. Its charge remains unresolved:
the available Anthropic usage page required sign-in, and the earlier request
returned no request ID or usage receipt. No old reservation was cleared.
A separate $0.50 ceiling was recorded for this newly authorized attempt.

One free token-count request returned HTTP 200: 83,173 input tokens. Including
8,192 possible output tokens and a 4,096-input-token margin, the bound was
$0.384687. One Messages generation was made; zero retries occurred.

The exact AAOI CALL candidate from governed run 20260906_213931 was sent to
claude-sonnet-4-6 using the installed workspace setting. The temporary release
used a 300-second HTTP timeout and a 360-second durable job lease.

## Provider result

- HTTP 200 after 130.012 seconds: the former 60-second client limit was insufficient
  for this observed request duration; the new window allowed a response through.
- Exact requested model returned.
- Usage: 83,173 input tokens and 8,192 output tokens; no cache token charges reported.
- Standard-rate usage cost: $0.372399, below the $0.50 cap. This is calculated from
  the returned provider usage, not independently reconciled invoice data.
- Stop reason: max_tokens. The response ended midway through a claim and was not
  complete JSON. No valid assessment or Lab projection was accepted.
- State: UNCERTAIN under the existing conservative post-dispatch failure policy.
  The exported durable charge row retains its $0.50 reservation. The known priced
  usage is recorded separately rather than rewriting historical charge evidence.

## Offline analysis of the partial response

The response contained 21,620 characters, with 22 complete claim objects followed
by an unfinished twenty-third claim; the sections field had not been reached.
This partial-object extraction was diagnostic only. The response was not repaired,
accepted, or represented as a complete assessment.

All 22 complete claims used supporting IDs absent from the exact v2 catalog.
They copied short lab/native source identifiers instead of the complete catalog
keys with current/prior and evidence-hash prefixes. Twenty claims also contained
raw digits outside slots, which the v2 contract rejects. Thus a larger token cap
alone would not establish acceptance. Deterministic semantic review of a full
assessment, persistence of a valid assessment, Lab projection and replay were
not reached.

## Bounded prompt fix, tested offline

The v2 adapter now asks for at most eight concise claims, short section summaries,
and at most two supporting references per claim. It prioritizes completion of the
entire eight-section JSON contract. It explicitly distinguishes full catalog keys
from nested source IDs and provides two automatically generated numeric-slot
examples that pass the actual renderer. It explains that categorical observations
and whole structured documents cannot be numeric slots, and keeps dates and
identifiers in the exact identity metadata instead of repeating them in prose.

These are model instructions, not proof that a future model response will comply.
The strict validator is unchanged. All governed evidence remains present; the
model, output-token allowance and spending cap are unchanged. Request fingerprints
will capture the new instructions, and any future call must recount the changed
request before dispatch. No generation was made with the revised prompt.

Tests: 279 original Worker 3 tests + 46 integration/regression tests + 11
configuration/macro tests passed (336 total). New coverage validates the example
slots against the real renderer, unchanged complete evidence, and continued
rejection of shortened IDs and raw figures.

## Preservation and remaining action

All 1,671 protected files matched the prior hashes. The production provider release
remains unchanged and INSTALLED_DISABLED. Both previous latches and reports are
preserved; the latest live latch prevents an accidental repeat.

A further live attempt requires a new explicit authorization. First reconcile the
old uncertain charge in Anthropic usage/billing when authenticated access is
available. The revised concise prompt is ready for that next controlled test;
end-to-end live acceptance and assessment grounding remain unproven.

Evidence: live_attempt_3.json, attempt_3_preflight.json,
attempt_3_partial_response_analysis.json, attempt_3_summary.json and
attempt_3_preservation.json. None of these results establish trading accuracy or
capital permission.

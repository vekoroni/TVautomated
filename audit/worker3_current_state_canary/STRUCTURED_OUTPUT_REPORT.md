# Worker3 schema-constrained output implementation

Implemented a provider JSON schema via output_config.format. The schema fixes identity and authority fields, restricts citations to available catalog references, permits only eligible numeric/change/scenario slots in claim text, excludes raw digits and braces from qualitative summaries, and requires numeric_facts values to be JSON numbers. The prompt still requests an empty optional numeric_facts array.

The existing deterministic renderer and strict local validation remain unchanged. Citation membership in the same claim, source value equality, section coverage and semantic authority still require those local checks; the provider schema does not guarantee these cross-field relationships. Refusals and truncated responses remain failures. No automatic repair converts a failed historical response into an accepted result.

The HTTPS transport accepts only the added json_schema output configuration, retaining its existing field and budget checks. Token-count preflight now includes output_config, and the full request fingerprint prevents a changed schema from reusing a previous cost estimate.

## Offline verification

- 279 foundation tests, 22 canary/activation tests, and nine new regression tests passed: 310 total.
- Full current-data offline audit passed, including expected invalid cases, report routes and fresh-process replay.
- New claim/summary patterns reject the previously observed defective text in attempts four and five. This is a targeted grammar check against saved payloads, not provider-side compilation or a successful regeneration.
- Valid numeric, prior, change and scenario slots pass the pattern tests. Categorical, numeric-string, boolean, unavailable, structured-document and unknown slots fail.
- Current AAOI request is 273,631 bytes, including a 19,322-byte schema, below the 500,000-byte limit.
- All 1,671 protected files remain unchanged. Production is disabled. No live API or token-count requests were made during this work.

## Remaining deployment gate

Run one separately authorized live canary with a $1.00 cap and no retries. It must confirm API schema acceptance, valid assessment, durable save, report projection and replay without another provider call. Anthropic documents regex support but also internal grammar-complexity limits; only a live request can confirm compilation of this exact schema. The preflight will count the schema-inclusive request before any generation.

Implementation reference: https://platform.claude.com/docs/en/build-with-claude/structured-outputs

# Worker3 evidence-coverage fix

Added a citable system record describing whether a prior assessment was supplied. This supports an honest CHANGES claim without asserting that no earlier report exists anywhere. The record is bound to the current evidence hash and supplied prior assessment identifier. It is a structured context document, not a numeric slot.

The provider schema now requires at least one supporting evidence reference per claim and at least one claim reference per section. Instructions require focused coverage of every section, allow qualitative COMPANY and CONTEXT claims grounded in available bound documents, and prohibit unrelated citations or unsupported absence claims. Strict local structural and semantic checks remain unchanged.

The saved report's bound source document contains company sector Information Technology and macro regime TRANSITIONAL. The previous macro summary overstated that source as TRANSITIONAL_BULLISH. The diagnostic copy uses the actual values and removes unsupported extra assertions.

## Verification

279 foundation tests passed. All 35 canary, activation, structured-output and evidence-coverage tests passed, for 314 passing tests total. Four new coverage tests check initial and refresh comparison provenance, prevent comparison context from being used as a numeric slot, enforce nonempty schema references, and show that adding a CHANGES citation does not clear unrelated coverage failures.

A manually edited offline copy of the saved response has eight claims and eight sections and passes the unchanged semantic lint with status REQUIRES_HUMAN_REVIEW and zero findings. Existing claims were selected to keep one per section; summaries were narrowed to those claims. This is a diagnostic result, not a new model output, not an exhaustive truth certification, and not deployment approval. The historical response and its BLOCKED status remain unchanged.

All 1,671 protected files remain unchanged. No paid requests were made. Production remains disabled.

Adding comparison provenance changes the context fingerprint. New jobs must be prepared with the new context; do not relabel old response hashes or silently reuse old prepared jobs. A separately authorized live canary is still required to confirm newly generated section coverage before activation.

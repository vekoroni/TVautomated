# ETF reliability build: approved sequence and first increment

ACK approved the recommended policies and implementation order on 14 November 2026. Governing review: `audit/trace/AVS-TRACE-001/ETF_codex_response.md`.

Policies: macro advisory; canonical Lab rank unchanged; both contract alternatives may be displayed when Claude supplies them; leveraged/inverse/volatility products carry a visible research-only policy pending product-specific validation. This increment does not implement a new gate. Claude retains selection, expiry, Lane B and outcome-card ownership.

## Increment 1: E1/E17 identity and coverage

Root cause: the existing security-master `instrument_type` is not propagated through the Lab contract. Scanner-added names can have no master row; several existing types conflate legal wrapper and exposure. Board and options universes have different purposes with no explicit reconciliation. Filling these gaps by another ticker hand-list would create competing ownership and guessed classifications.

Design: a read-only canonical security-master adapter reads the existing CSV, its content hash and dated validity intervals. All identity lookups require an injected as-of date. Overlapping, future, missing and ambiguous classifications are explicit states. Keep the raw master type; derive only attributes explicitly encoded in a versioned type vocabulary. Do not call a legacy volatility label proof of ETF/ETN wrapper or exact leverage. Do not infer identity from a ticker's spelling or from board membership. Preserve literal NAN/SYM.

Carry the identity contract into the final book and Lab projection without altering existing fields, rank, direction, target, contract, scores or membership. Show research policy as disclosure only. Existing historical publication files are not republished or rewritten.

Reconcile the union of master book rows, board membership and actual saved book membership. Board membership does not mean options eligibility. Chain availability is assessed only when a dated, explicitly scoped saved-coverage set is supplied; otherwise NOT_ASSESSED, never NO_CHAIN. No scan of live historical databases is required for this increment.

The board's existing "Volatility products" and "Leveraged & inverse" groups can additionally set the **current review policy** to RESEARCH_ONLY, with a separate policy source/hash. This never fills legal wrapper, type, leverage or inverse facts for an unknown identity, and is explicitly not a historical decision. It avoids leaving a known board risk-group member with an ordinary review label merely because its master row is missing.

Tests first: future/expired/overlapping metadata, classification uncertainty, NAN/SYM, missing scanner names, research-only disclosure, unchanged source inputs, unchanged existing book fields/order and projection round-trip. Use temporary test directories, no providers or live DB writes.

Later increments remain in approved order: clocks/quotes and IWM trace; independent measurements; context/holdings; dividend design; timing/probability audit; cross-owner publication. Thresholds needing empirical design are not invented in increment 1. No claim of full E1/E17 closure until saved-source classification gaps and forward publication are verified.

## Shared-file coordination checkpoint

At the v2 scenario-review handover, the ETF increment already had seven additive lines changed in `contracts/lab_control.py`: import/extend the identity field list and attach dated identity disclosure after canonical ranking. No changes were made to `scripts/avshunter_options_intelligence.py`. No selection, valuation or Lane B code was edited. Those existing edits are intentionally retained; further ETF edits in both shared files are paused for coordination. The scenario v2 review was reassigned to another chat, so this chat is not doing that review. The designated scenario reviewer can inspect this checkpoint and the working diff. Claude is the designated implementation writer in those shared files for the scenario build. Future ETF increments needing shared wiring must be coordinated rather than overwriting his changes.

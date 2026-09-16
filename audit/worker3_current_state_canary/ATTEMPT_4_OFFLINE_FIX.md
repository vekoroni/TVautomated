# Worker3 offline output-contract fix

No paid requests or token-count calls were made during this work. Production remains disabled, and all 1,671 protected files remain unchanged.

The saved attempt-four response has four concrete defects:

- A Markdown code fence makes the response invalid as strict JSON.
- Eight numeric_facts values are quoted strings instead of source JSON numbers. The units match; the value types do not.
- Five slots refer to categorical observations rather than numbers or SCENARIO-kind states.
- Claims C4 and C5 use trigger_score and ask slots without including those references in their supporting evidence.

Updated worker3/adapters/claude_v2.py to request bare JSON, leave optional numeric_facts empty, explicitly distinguish number values from strings and categorical states, and require every slot reference in the same claim supporting_evidence_ids. The instructions tell the model to omit extra figures when exceeding the two-reference claim budget. Section summaries now use qualitative prose; numerical detail belongs in cited claims.

The strict validator, historical provider output, historical job state, attempt latch and production release were not relaxed or changed. Diagnostic edits to an in-memory copy are not a successful provider result. The missing-reference errors above occur in claims; earlier commentary attributing that error to section summaries was premature.

Validation: 279 foundation tests passed, plus 22 canary and activation tests. These checks verify compatibility with the existing offline workflow; they do not establish that a future model response will comply. The revised instructions still require a separately authorized live canary before activation. No additional API cost was incurred.

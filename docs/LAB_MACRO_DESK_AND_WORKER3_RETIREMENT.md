# Market Mentality desk and reversible Worker 3 decommission

The backend CSV remains an independent reconciliation input. No CSV exporter is added.

The Lab `/market-mentality` page (also available at the compatible `/macro-scenarios` link)
reads the compact `macro_board/output/lab_macro_latest.json`.
A successful current board build publishes this atomically after writing the board HTML.
Historical `--as-of` builds never replace the live desk. Page refresh and a visible-page
60-second poll read local JSON only. No provider, whole-book read or pipeline run occurs.
Board build time, observation metadata, macro revision and stale-build warnings are shown.
This revision is independent of the immutable trade-review revision. Mentality rules are
qualified interpretations with supporting, contrary and missing evidence, never probabilities,
trade direction or execution permission. Sector rotation remains in its existing view.

An already saved board can be imported offline, without executing embedded JavaScript:

    venv\Scripts\python.exe -m contracts.lab_macro_desk --from-board macro_board/output/etf_macro_board.html --output-dir macro_board/output

This command publishes only the compact display projection. Uploaded copies can be passed
by explicit path after validation. No autonomous twice-daily provider schedule is created.
Whenever the existing board build runs, the desk publication is refreshed with it.

Worker 3 code, prompts, evidence, job history and reports remain on disk. Its checked-in
integration policy is DECOMMISSIONED_RETAINED, DISABLED, with bridge/intake disabled.
The coordinator refuses job preparation. The Lab no longer imports or mounts Worker 3.
The pipeline no longer calls its per-ticker materialisation. Shared run-frozen macro evidence
is still prepared by a Worker-3-independent helper before review publication; Deep Dive is unchanged.
Provider release remains disabled. Reactivation requires explicit approval, reviewed policy
restoration and deliberate rewiring of pipeline/Lab entry points plus regression tests. Merely
setting an environment variable or re-enabling a provider release cannot restore these mounts.

Deploy by restarting only the local Lab server after tests. Do not run the evening pipeline.

## Detailed design: crowd mentality, 19 October 2026

### Scope and screen

The overview is one coherent crowd-mentality interpretation. It does not replicate the
Macroboard, sector rotation charts or Deep Dive. The screen presents:

1. Inferred mentality headline and qualified summary.
2. Separate confidence, fear/concern, directional-progress, trading-urgency and positioning assessments.
3. Behavioural relationships and disagreement across time horizons.
4. What changed since the previous comparable assessment.
5. Opening attempt, daily response and possible consequence, where measured evidence supports it.
6. Observable reaction sensitivities and what would challenge them.
7. Supporting/contrary evidence links, exclusions, observation clocks and source receipts.

### Evidence contract and rules

`contracts/lab_market_mentality.py` is a pure, deterministic rule engine. It whitelists
dated classified conditions, current-session ETF returns, daily opening/closing observations,
and dated VIX level/momentum. Narrative packets, supplied trade directions, probabilities,
OI, unverified ownership claims and news narratives are not independent evidence.

Input IDs are stable (`condition:market_breadth`, `return:SPY:1d`, `reaction:DIA`). Each
inference carries its rule version, supporting IDs, qualifying/contrary IDs, evidence gaps
and conditions that would change the view. Unusable/future/stale observations remain visible
but cannot support an inference. Methods and source dates are shown next to observations.

Three of four major indices beyond +/-0.25 percent describe broad daily progress. Matching
five-session returns beyond +/-0.50 percent describe multi-session progress. These provisional
descriptive noise floors are not calibrated forecasts. Missing coverage stays unresolved.
Low breadth plus corroborating risk-appetite or price evidence suggests fragile/selective
confidence; broad participation plus broad gains supports a wider-participation interpretation.

The board's HYG/LQD relative-return proxy is explicitly not a direct credit-spread measurement.
Realised volatility does not establish fear. Dated rising VIX supports concern as a qualified
interpretation, not proof of hedge buying. Positioning remains UNKNOWN. Urgency remains
INSUFFICIENT_EXECUTION_EVIDENCE without intraday speed, spread and executable liquidity.
Daily gap/close patterns never claim intraday acceptance, order-book absorption or verified
trapped/forced positions. No new feed is required, and missing evidence is not fabricated.

### Publication, history and clocks

`lab_market_mentality_v2` includes a calculation version, source revision, content revision,
cash session, input observations, board build time and interpretation publication time.
The existing board-build hook remains the publisher. Manual saved-HTML import uses JSON
decoding only. Repeating identical inputs is idempotent. GET requests only read saved records.

Immutable revision files are kept in `macro_board/output/mentality_history`. The latest pointer
is atomically replaced after the history file is saved. A single-writer lock prevents competing
publishers; a stale crash lock fails explicitly for operator inspection. Older builds cannot
replace newer assessments. Integrity hashes are verified on reads. The previous v1 publication
can be upgraded from its saved board; corrupt v2 publications fail closed.

Comparison requires the same rule version and measurement definition. Rebuild-only changes
are labelled as unchanged observed behaviour. Same-session corrections are labelled data
revisions, not new crowd reactions. Archived revision views are pinned and do not auto-poll.
The latest view polls every 60 seconds while visible. A recent publication is never proof
of fresh underlying observations. Source issues are shown separately.

### Trade-review isolation

The optional `.../rows/<row_key>/mentality?revision=<review_revision>` route reads exactly one
indexed frozen card plus the compact latest mentality record. It does not read the full book,
rewrite decisions, re-rank rows or grant permissions. It refuses a changed frozen review revision.
The panel preserves literal ticker identity and saved direction, including unassigned direction.
It states that Market Mentality was not recorded with these historical frozen reviews. Current
mentality is a separately dated post-run overlay, not retroactive triage evidence. A pinned link
opens the exact mentality revision shown in the panel. Failures leave the trade card usable.

### Verification and operational boundary

Test proxy definitions, missing/future/stale dates, direction/urgency independence, unknown
positioning, evidence ID resolution, same-session corrections, publication-only refresh,
idempotence, archive integrity, concurrent/older writer guards, exact-row revision pins,
authority preservation, HTML escaping, failure clearing and actual 60-second refresh logic.
Use saved local data with providers blocked. Preserve source books, trade-review publications,
databases and Worker 3 history. No evening pipeline, paid calls or recurring paid budget.

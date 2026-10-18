# Macro scenarios desk and reversible Worker 3 decommission

The backend CSV remains an independent reconciliation input. No CSV exporter is added.

The Lab `/macro-scenarios` page reads the compact `macro_board/output/lab_macro_latest.json`.
A successful current board build publishes this atomically after writing the board HTML.
Historical `--as-of` builds never replace the live desk. Page refresh and a visible-page
60-second poll read local JSON only. No provider, whole-book read or pipeline run occurs.
Board build time, observation metadata, macro revision and stale-build warnings are shown.
This revision is independent of the immutable trade-review revision. Scenario rules are
conditional interpretations with explicit evidence, confirmation and invalidation, never
probabilities, trade direction or execution permission. Sector rotation remains in its existing view.

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

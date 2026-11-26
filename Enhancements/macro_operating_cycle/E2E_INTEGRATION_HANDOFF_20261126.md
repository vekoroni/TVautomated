# End-to-end macro integration — 26 November 2026

ACK approved completion beyond the sidecar, saved data only. ADVISORY_ONLY throughout. No provider requests, paid macro analysis, pipeline execution, scheduler activation, ticker scoring or Lane B code changes.

## Delivered path

Accepted raw USMI/News/Events -> source-validated FULL analysis already saved -> reconciled narrative -> one verified publication bundle -> ETF board and Lab macro screen. The normal board builder now assembles and binds the cycle **before rendering/publishing**, not after. It does not launch another macro analysis. Historical as-of board builds still do not replace current publications.

`macro_board/cycle_publication.py` owns binding/publication, `intelligence-lab/static/macro-cycle.js` is the single shared display renderer, and `contracts/lab_macro_desk.py` reads the committed bundle. All nine narrative sections, source hashes, freshness, conflicts and explicit authored-input limitations appear on both screens. Existing crowd-proxy interpretations are retained as supporting descriptive evidence, not a second house narrative. No monetary or trading judgement is added by the renderer.

## Publication and recovery semantics

- Immutable `macro_board/output/macro_publications/<publication_id>/` contains board.html, lab.json and manifest.json. All content is hash-bound.
- `macro_publication_latest.json` is the one canonical commit marker, written only after both artifacts exist.
- `/api/lab/macro-context` and `/api/lab/macro-board` follow that same marker and verify artifacts. Corruption fails visibly; no quiet fallback to a different narrative.
- Pinned Lab revisions retain their own full narrative. Their board link carries the corresponding publication ID, not whichever board is latest later.
- `etf_macro_board.html` and `lab_macro_latest.json` remain compatibility copies. These two physical files are **not claimed to be atomically replaced together**. A failed compatibility write is reported; canonical API readers remain consistent and retry repairs the copies.
- An interrupted pre-commit publication leaves the last committed pair readable. Retrying preserves the first staged publication clock/bytes. Writer contention does not steal locks.
- Legacy direct imports cannot downgrade a coordinated publication to a narrative-free Lab view.
- The existing per-ETF/Lane B context producer and receiving code are unchanged. No new macro score, rank, veto, contract or order fields are injected.

## Saved data installed and verified

Publication: `a7bc230047cede8add1199d4396f4834aecb871af5c96f5f7366652b3ec9f2a0`.

Narrative: `macro_2026-11-25_b1bf08274c62a05e9acb538b`.

Narrative SHA: `7529e77b2d308444b4a6ec3d77bc42bdc8c60b1c64d23cee4a894f3d3006496e`.

Lab revision: `43e1343246234b22064503a435170012b99c0606c6b7d31d44139ac401ba2495`.

Reference close: 25 November; original build/information cutoff retained at 26 November 11:35:33 UTC. No re-dating of sources or rerun of AI analysis.

Feed chain VERIFIED_ALL_THREE_FEEDS: USMI 117, accepted News transport revision 1792649830, Events 48. Each raw archive SHA is verified and retained locally, each analysis-consumed SHA matches the narrative capture. Events' materialized union SHA is correctly distinct from the last original-export SHA. Raw capture evidence is retained under `accepted_feed_evidence/` and `operating_cycle/captures/`.

The original saved board payload, after removing only `macro_operating_cycle` and `macro_publication_id`, is exactly equal to the republished payload: all 115 ETF records and other existing values unchanged. Existing crowd evidence and proxy interpretation also compare exactly unchanged. Replaced compatibility files are retained by content hash under `macro_publications/legacy_captures/`; dated history/snapshots are preserved.

## Test and runtime evidence

- 127 Python tests PASS: 7 publication integration, 11 Lab macro, 29 cycle, 10 measured sheet, 63 board rules, 1 macro-never-scores, 6 interpreter advisory tests.
- Two JavaScript harnesses PASS: shared nine-section rendering, identities, missing states, escaping, revision refresh, visible-only polling, failure clearing and pinned board links.
- Actual Flask endpoints verified on localhost:5002; matching narrative ID/hash/publication, board HTTP 200, no-store.
- Browser verification: both Market Mentality and canonical ETF board display the same record, nine sections and `VERIFIED_ALL_THREE_FEEDS`.
- Test XML: `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_INTEGRATION_TESTS_20261126`.
- Only the verified local Lab web service was restarted to load the new routes. Logs: `C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\LAB_MACRO_INTEGRATION_20261126.stdout.log` and `.stderr.log`.
- MacroInputs Controlled, PreOpen and PostClose tasks all remain DISABLED. FULL, budgets and PostClose timing unchanged.

## Remaining honest limitations

The integration is operational using saved data; authored economic content is still INCOMPLETE_AUTHORED_INPUT. ACK/Claude have not supplied the authored probabilities, policy call and ETF world marks. The system displays this explicitly and does not turn conviction scores into invented probabilities. Use the Phase 1 template and outcome receipt contract. A scheduled production run remains AWAITING_RUN because schedules were deliberately kept disabled. No full-priced Fed-path feed, consensus acquisition or continuous intraday collector was built.

This is working-checkout code and verified saved publication, not a clean committed release. Previously published macro branches must be reconciled into any later isolated release with the required foundations; do not sweep unrelated Lab/Lane B changes into it.

## Claude read-only acceptance

Check the matching IDs/hashes and original source clocks on both pages, all nine sections and missing states, unchanged original ETF payload and ticker authority, failure/retry/corruption/pinned-revision tests, accepted raw versus materialized Events lineage, and disabled schedules. Do not run providers or the pipeline. The earlier SourceRead path concern was disproven: `SourceRead.file` returns Path; a real-SourceRead adapter integration test now passes.

Saved republishing command (not Macro Inputs / not a pipeline):

```powershell
Set-Location "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"; & "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\venv\Scripts\python.exe" -B "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\tools\publish_saved_macro_cycle.py" --cycle-folder "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\MACRO_CYCLE_PHASE1_FINAL_20261126" --output "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\macro_board\output"
```

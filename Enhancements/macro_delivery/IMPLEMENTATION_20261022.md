# Three-feed macro repair and delivery

Owner approval: ACK, 22 October 2026: implement the prioritised audit fixes, beginning with USMI schema and macro health, test the three feeds and integrate JSON delivery into the existing runner. The existing pickup folder remains `dropbox/macro`.

## Root cause and design

The audit found producer/consumer drift, age-only freshness presented alongside schema rejection, lost event handoffs, historical News promoted by a keyword label, and unacknowledged delivery. Preserve research content while withholding unsupported facts. No new trading, ranking, sizing, model or capital authority is introduced. Governing references: behavioural specification v1.1 C0/C1/C14 and method note 07 point-in-time capture; root CLAUDE.md advisory boundary. Stored decisions remain frozen.

The incident is covered by tests/test_macro_priority.py and fixtures/macro_delivery_20261022. USMI v2 compatibility preserves the known descriptive transition as unresolved (`None`, explicit basis/detail), accepts narrative-only global-session context without fabricating metrics, rejects non-finite numbers and exposes nested scenario context without parsing prose into executable predicates. Typed producer fields are documented in config/us_money_index_producer_v2.schema.json. Existing ambiguous/unknown flag strings remain rejected.

The builder attaches validated research context and exact source receipts; `macro_health` separates evidence availability from schema status. FRED zero coverage and missing/rejected feeds degrade health. Interpreter copies this status. The board uses USMI semantic validation and flags future dates. Bond fallback does not invent an observation date from a macro report date. Quant credit bands are explicitly labelled text-state proxies, not measured OAS.

The News keyword projection excludes historical/superseded/invalidated context from active support. The compact reader includes credit and confirmation/pathway/manual-check content. Events are carried as advisory context through the builder/frozen Interpreter and an accepted cumulative event view for the board.

## Delivery interface

`config/macro_delivery_v1.json` sets the existing pickup directory, inbox manifest, archive/receipt location, byte/timeout/retry limits and HTTPS hosts. `scripts/sync_macro_feeds.py` validates and ingests a producer manifest. It never generates research, invokes a paid model or starts a trading pipeline.

Default manifest: `dropbox/macro/incoming/manifest.json`. Data files referenced by a local manifest must remain under its directory. HTTPS manifests/data require explicit allow-listed hosts and optional `AVSH_MACRO_DELIVERY_TOKEN` bearer authentication. Cross-host redirects and embedded URL credentials are refused. Retry is bounded; response bytes are bounded and checksummed. No sandbox URL conversion or undocumented ChatGPT endpoint is used.

The manifest schema is config/macro_delivery_manifest_v1.schema.json. One envelope per feed per batch; batch multiple economic events together. Each envelope includes feed, monotonic revision, timezone-aware generation/export timestamp and exact SHA-256. New packets also include source and material_change. Retained/no-change packets reference the exact accepted hash and revision. USMI envelope revision must match its source packet_revision. Keep true source observation/generation clocks inside the payload; export time cannot be earlier than a supplied source-generation time.

Each accepted raw packet is archived unchanged. Published USMI and News bytes match those archives. Events maintain a latest record per event identity, with source hash/time; unrelated events survive corrections. The materialised event JSON is a view over that ledger. Writer lock, quarantine, duplicate/out-of-order detection, collision rejection and atomic publication protect the accepted pointers. A crash-recovery lock must be checked against the recorded PID before manual removal; it is never automatically broken.

Exit 0 means all expected deliveries completed; exit 2 means missing/rejected research; exit 1 means script/configuration failure. Missing manifests produce WAITING_FOR_MANIFEST receipts. Invalid manifests replace an old success with FAILED. Existing accepted packets remain available when a new delivery fails, but the failure receipt is retained. Do not interpret a transfer check time as a new market observation.

## Runner integration and operation

Run-MacroInputs.ps1 includes research intake before market producers. Its normal PostClose (16:30 ET) and PreOpen (08:35 ET) windows remain owned by the existing runner/calendar. A missing/rejected research delivery is visible in the final DEGRADED summary/exit 2. It does not turn into a trading veto or silently suppress valid market data.

Read-only planning:

```powershell
.\Run-MacroInputs.ps1 -Session PreOpen -PlanOnly
.\Run-MacroInputs.ps1 -Session PreOpen -ResearchDeliveryOnly -PlanOnly
```

Research intake without paid producers (inside the configured session window):

```powershell
.\Run-MacroInputs.ps1 -Session PreOpen -ResearchDeliveryOnly
```

Use the existing `-Now -Yes` or `-Force` controls only under the runner's documented operating policy. A local/synced producer publishes payloads first and the complete manifest last. The intake emits `macro_advisory_latest.json` with per-feed observation clocks and delivery state. Board source quality can display that receipt; the frozen run is not rewritten by later deliveries.

Normal scheduled passes still rebuild local market inputs. For extra premarket material changes, invoke research-only intake after producer completion. Its material_change output supports a coordinator that avoids unnecessary paid synthesis. No new recurring schedule is installed by this change.

## Producer export requirement and remaining operational boundary

The local destination is configured. The three cloud chats must still publish their actual JSON bytes and manifest to this inbox via a connected/synced destination, or expose an authenticated HTTPS manifest that the runner can retrieve. A local folder name does not itself grant the cloud tasks filesystem access. Current read_thread output supplies sandbox links, not an authenticated file-download API. No exporter credential/endpoint was provided or discovered, so cloud-to-local delivery has not been activated or claimed complete.

For each producer, keep the current research prompt, add the typed export contract, preserve source/correction timestamps, publish only complete files, and emit a retained identity on no-change checks. Export `material_change=true` on material corrections, route/scenario changes or coverage loss even if the headline score is unchanged. Agree an ET completion cadence relative to the actual exchange close and premarket checkpoints. Prove one live export/download canary per producer before unattended scheduling.

## Validation and rollback

Acceptance includes the real delivered incident fixtures, all three feeds through manifest intake -> accepted archive/view -> builder research attachment -> frozen Interpreter, event correction and unrelated-event retention, checksums, out-of-order delivery, duplicate/no-change, missing/invalid manifest, future timestamps, unsafe transport, bounded HTTPS fake transport and writer collision. The actual builder publication body is exercised with synthesis mocked at its external boundary, isolated files, schema PASS plus DEGRADED health and exact source receipts. PowerShell plan tests exercise research-only step selection; the real CLI missing-manifest test proves no model output is produced.

Focused regression suites cover previous USMI text semantics, macro domains, enrichment/snapshots, Interpreter, quant packet, bond contracts/cutoffs, market-data governance, publication alignment, runner steps/weekends and advisory-only authority. No profitability inference or model promotion follows from these engineering tests. Live paid-provider acceptance and real cloud transport canaries are separate from offline acceptance.

Changes remain uncommitted. Original edited files were copied to this chat's work/preimages with a deployment hash manifest; deployment refuses unrelated concurrent edits. Revert only this change's hunks/new owned files after preserving user edits. Do not reset the working tree, delete evidence or rewrite old run snapshots.

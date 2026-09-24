# AVS-SD-ILA-002 — Governed Evening/Morning Intelligence Lab read model

**Status:** design for review, not implemented.  
**Inputs:** `AVS-ILA-EVENING-MORNING-SOURCE-MAPPING-20260923.md`, its 926-name field register, and `AVS-ILA-UI-VALIDATION-20260923.md`.  
**Objective:** before Interpreter use, the Lab must show the complete Evening thesis, the actual Morning event and current observations, any genuine source absence, and the correct authority/advisory boundary without contradictory labels. This is a dynamic, evidence-driven MVP, not a once-per-run static report. Shares, long calls and long puts remain in scope; capital allocation remains outside this design.

## 1. Domain boundaries

The change is a read-model repair, not a new trade selector. It neither changes Discovery/Vanguard direction nor retrospectively invalidates opportunities. The bounded contexts are:

- **Thesis (Evening owner):** run/ticker/thesis identity, completed evidence session, frozen direction/target/invalidation/hold/trigger, and original selected structure. Immutable within a run except explicit supersession with event ID.
- **Morning Validation (Morning owner):** event ID and type (`PREOPEN_THESIS_CHECK` or `POSTOPEN_CONTRACT_REFRESH`), underlying observation, evidence cutoff, thesis transition, reason and data status. A post-open event can confirm/invalidate/defer the thesis; it is never rendered as a pre-open event.
- **Contract Observation (canonical market-data owner):** role-specific EOD, Morning and optional later quote for the exact selected contract, with provider timestamp, fetch timestamp, quote ID, sizes and spread. Quote recency informs execution positioning but does not by itself make a 1–20-session thesis stale.
- **Execution (Execution Gate owner):** action, permission, route, human approval and reason. Lab consumes and reconciles; it does not manufacture authority from advisory evidence.
- **Advisory analytics (macro, DOI, EV3, GARCH, WBS, Interpreter):** each retains evidence cutoff, model/packet version and explicit `ADVISORY_ONLY` authority. Different advisory conclusions may coexist and must not overwrite the thesis or execution decision.
- **Lab Presentation:** an additive, versioned projection across the above owners. It may format and label; it may not calculate a favourable missing value, change contract identity or rank out an opportunity because a UI field is absent.

## 2. Proposed additive row contract

Add a versioned `lab_event_context_v1` projection to every row of the **full** final opportunity book. Preserve all existing fields during migration. The fields below have one owner and must not be supplied by generic copied-column priority:

| Group | Required fields / semantics | EOD value | Morning value |
|---|---|---|---|
| Identity | `run_id`, `ticker`, `trade_idea_id`, `thesis_id`, `selected_structure_id`; selected contract and quote ID when applicable | frozen | same or explicit supersession |
| Frozen thesis | `evidence_session_date`, `governed_direction`, target/invalidation + source/state, `planned_hold_sessions`, EOD bucket/next condition | source values | unchanged; comparison result added separately |
| Event | `morning_execution_mode`, `validation_event_id`, `validation_transition`, `validation_reason`, `validation_data_status`, `validation_evidence_cutoff_utc` | `NOT_RUN_EOD`/null as typed; not fabricated | all present for a completed Morning row; event count reconciles |
| Underlying | `validation_current_price` plus observation ID/provider timestamp; `live_price`/`live_vwap` only for their actual observations | frozen close only | observed Morning value and clock; canonical NBBO/VWAP remain separate nullable observations |
| Exact quote | `morning_quote_timestamp_utc`, selected quote ID, symbol, bid/ask/sizes/spread; separately `current_quote_*` if another refresh exists | historical EOD quote role | current Morning exact-contract role or explicit `NO_QUOTE` |
| Decision | `morning_transition_state`, `morning_execution_permission`, `final_action`, `lab_verdict`, `lab_tradeable`, `morning_lab_alignment_status` | prep/review only | recomputed from Morning + Execution Gate; exact reconciliation |
| Advisory | macro packet ID/hash/session/as-of/quality; DOI preferred/governed symbols; EV3/GARCH/WBS/market-structure version/state; Interpreter lifecycle | EOD version | retain or append a labelled new version only if actually recalculated |
| Publication | `lab_projection_version`, `lab_publication_id`, source manifest hashes, `published_at_utc`, completeness/consistency state | EOD publication | new atomic Morning publication |

For a non-directional or unavailable event, publish the typed state and reason rather than forcing `THESIS_CONFIRMED`. For a missing source observation, publish null and `UNAVAILABLE_PROVIDER`/`NOT_EVALUATED`, never zero. The existing `field_provenance_json` should identify the semantic owner, not merely the last CSV that copied a field.

## 3. Publication and consumption flow

```text
Evening producers -> frozen candidate/quote/macro evidence
                  -> full Lab EOD book (all candidates, EOD_PREP)
Morning Gate -> 1 event + observation outcome per candidate
             -> Execution Gate decision
             -> finalizer joins by run/ticker/thesis/structure/contract/quote identity
             -> full Lab Morning book (same population, new publication ID)
             -> accepted actionable Interpreter subset (not population owner)
             -> Lab API/cache -> browser and optional Interpreter
```

The finalizer must materialize mode and validation-event facts **before** writing the full book. The full book is the sole population source for the Lab. The 359-row handoff may add allowlisted Interpreter/advisory evidence after identity checking; it may not be used as a workaround to populate only 359 of 1,550 Morning rows. Keep `PROTECTED_AUTHORITY_FIELDS` protected. The UI must not read stale EIL/Morning intermediate rows after replacing them with the governed book.

Publish atomically (temporary files, verified hashes, then manifest/pointer). A Lab cache signature must change on a new full-book publication, event/summary, or accepted overlay. If the browser/API still holds an older publication, visibly show its run ID, pipeline mode and publish time. A server restart is not a freshness mechanism.

### Dynamic MVP behavior

- Treat Evening, Morning and later observations as ordered **events**, not replacements for one mutable row. Keep the Evening thesis and its evidence cutoff frozen. Add a later observation with its own observation ID, provider time, fetch time and source status; never relabel an old quote as current merely because the Lab refreshed.
- On every accepted source publication, update the affected ticker projection and the aggregate run status. The browser must detect a changed publication ID while open and refresh the relevant ticker/list views without requiring a server restart or another Evening run. A visible refresh time and a manual refresh control are required; automatic polling may be bounded for the MVP.
- Re-evaluate only the derived display comparison that the new evidence can change: Morning-versus-Evening thesis transition, current entry positioning/quote context, and advisory narrative status. Changes to governed thesis direction, selected contract or execution permission still require their owning domain's explicit event or decision, never an implicit Lab recomputation.
- Distinguish `NO_NEW_OBSERVATION`, `SOURCE_UNAVAILABLE`, and `NEW_OBSERVATION_ACCEPTED`. A source that has not yet published a newer value does not make the prior completed-session thesis invalid or justify a fabricated zero. Show the source timestamp and the latest accepted observation beside each dynamic value.
- Accept out-of-order or repeated notifications idempotently: the same observation ID must not generate a duplicate update; an older observation must not overwrite a newer role-specific observation. A later correction is a new, linked version, preserving the previous evidence for audit and Interpreter comparison.
- Keep the MVP narrow: full-population Morning event truth, role-specific underlying/quote observations, publication refresh, and clear source status. New scoring models, automatic trade selection, capital allocation, and broker execution are later enhancements, not prerequisites for fixing the Lab.

## 4. UI field-role design and retention decision

| UI section | Display contract | Retention decision |
|---|---|---|
| Main list/header | frozen EOD thesis bucket and separate Morning result/action; selected-contract and quote state; publication timestamp | **Keep**. Never show EOD readiness as a Morning GO or vice versa. |
| Overview | EOD close/target/invalidation/hold on one side; actual Morning event ID/mode/cutoff/current price/gap/profile/transition on the other | **Keep and repair.** A completed post-open event must not say Morning `NOT RUN`; a skipped pre-open submode may say only `PREOPEN NOT RUN`. |
| Trade Setup | exact governed contract and economics, original vs current quote, role-specific quote timestamp, remaining runway | **Keep and repair.** Show quote age as execution context, not thesis expiration. |
| Options | Greeks, IV, volume, OI, bid/ask/spread with observation source and time | **Keep.** Format spread to two decimals; keep missing Greeks null. |
| Convexity | aggregate score owner/version; detailed checks only when their producer fields are present and reconciled | **Keep aggregate conditionally; hide unavailable component claims.** Do not delete history or infer component booleans from score. |
| Stage Ladder | EOD preparation versus Morning execution readiness, each with source event and conditions | **Keep and reconcile.** Stage 4 cannot be inferred solely from a projected GO missing its supporting event. |
| Morning Val | governed validation event, mode, current underlying, change from frozen close, selected quote, decision/reason | **Replace legacy pane.** Remove the obsolete `morning_validation.py` instruction after event-level UI tests pass. |
| DOI Ranking | governed selected contract and DOI alternative as separately named contracts | **Keep advisory.** No quote/economics substitution across contracts. |
| Entry Telemetry | legacy EIL diagnostics when actual evidence exists | **Conditionally hide inactive tab.** Retain producer data/audit; remove UI aliases only after Lab/Interpreter search and parity proof. |
| Q-Omega | forecast-vol differential, method/confidence, jump-risk and horizon moves | **Keep advisory, repair method mapping.** Say “forecast difference may favour long optionality, subject to pricing, path, jump risk and execution,” never “buying edge exists” from one threshold. |
| MSI Evidence | selected quote with exact timestamp/identity; Morning last/VWAP; separate canonical NBBO/VWAP; typed source absence | **Keep and repair.** A 1.49/1.58 quote cannot be paired with `MISSING` timestamp when its exact Morning timestamp exists. Show no NBBO as unavailable, not 0/0. |
| Macro | frozen packet session/as-of/quality and distinct sector/USMI advisory models; optional later packet visibly separate | **Keep.** Do not collapse neutral USMI and sector headwind or imply current-session data from a prior-session packet. |

No production/source field is approved for deletion by this design. The 266 UI-only references are a review queue, not 266 deletion approvals. Unused wall controls can be hidden after consumer parity; historical evidence, event IDs and provenance remain available for Interpreter and audit.

## 5. Consistency and failure semantics

The Lab's own action affordance must not show a clean actionable state if its displayed Morning context is missing or identity-mismatched. Introduce a **presentation integrity state**, not a new thesis veto:

- `COMPLETE`: source event, quote identity (if a quote exists), decision and full-book projection reconcile.
- `SOURCE_UNAVAILABLE`: Morning actually could not obtain a required observation; show the original Morning disposition/reason.
- `PROJECTION_INCOMPLETE`: Morning source has the event but Lab lost it. Preserve the candidate and source decision, show a prominent data-integrity warning, and withhold the Lab's one-click/actionable affordance until republished. Do **not** silently relabel the thesis invalid or remove it from the book.
- `NOT_RUN_EOD`: no Morning has run, accurately labelled.
- `NOT_APPLICABLE`: a specific submode/observation is not applicable; never a blanket Morning claim.

This distinction protects the manual-trading MVP: a UI integration defect does not erase a valid Evening thesis or source Morning record, but a trader is not misled into believing the Lab projection is complete. The source artefacts remain inspectable.

## 6. Test-driven implementation sequence and acceptance gates

1. **Red contract tests before production edits.** On frozen run `20260922_223221`, assert 1,550 Morning rows, 1,550 event files, 1,550 full-book rows; `morning_execution_mode`, event ID/transition/cutoff and current price present on every applicable Morning row. Assert 359 handoff rows do not shrink the population. Add CALL, PUT, no quote, missing invalidation, non-directional and contract reselection fixtures.
2. **Materializer fix.** Add owner-specific event fields to `contracts/lab_control.py` and Morning finalizer inputs. Do not extend the advisory overlay allowlist to smuggle governed decisions across contexts. Add exact identity and source-hash reconciliation.
3. **UI binding fix.** Render pre-open and post-open mode explicitly; rebuild Morning Val; bind selected quote timestamp by role; display live price/VWAP separately from NBBO/canonical VWAP; remove zero defaults for absent observations. Fix Q-Omega method alias and conditional wording. Hide inactive EIL tab only after its consumer tests pass.
4. **API/cache/integration tests.** Test a completed Morning run through final book -> `intelligence_lab.py` slim API -> browser field/view model, not just static JavaScript presence. Test EOD -> Morning publication switch in one long-lived Lab process; repeat without server restart. Ensure fields and row counts reconcile and no GO/NOT RUN contradiction exists.
   Test a newer exact-contract quote, unchanged source, unavailable source, duplicate event, out-of-order event and corrected event. Assert only the intended dynamic fields change, the Evening thesis remains frozen, and a browser already open sees the new publication ID and timestamp.
5. **UI proof.** With the Lab service available, replay LUNR plus at least one GO, one FLAG/review, one BLOCKED, one no-quote and one absent-Morning case. Capture Overview, Trade Setup, Morning Val and MSI panes. Check the displayed price, event, quote time, macro as-of and contract identity against source files. Compare pre-open and post-open cases separately.
6. **Regression/release.** Run focused tests, complete Lab/Interpreter regression and stored-run replay. Govern the source mapping, field register (force-add CSV), UI validation and design. Publish release manifest and rollback instructions. Do not claim production UI acceptance while the local service is unreachable.

**Exit criteria:** no row shows a Lab GO with “Morning not run” after a successful Morning event; all 1,550 rows have a correctly labelled Morning event or typed exception; exact quote time/contract matches; no missing data is fabricated as zero; inactive legacy wall panels are hidden only after consumer proof; EOD thesis and advisory authority remain unchanged.

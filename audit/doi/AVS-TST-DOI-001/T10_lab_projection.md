# T10 — Lab projection / DOI-10 implementation acceptance

**Audit:** AVS-TST-DOI-001 · track T10
**Claim under test:** AVS-SD-DOI-001 v1.1 §19, "DOI-10 Implementation acceptance (2026-09-10)"
(`docs/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md:740-758`)
**Reference run:** `20260909_071646` (pre-DOI; correctly carries no DOI tables and no DOI-projected fields)
**Date of test:** 2026-09-10
**Pipeline executed:** none. No orchestrator, morning gate, Lab server, GEX proxy or provider client was run.

---

## 1. Objective

Check the numeric and behavioural assertions of the DOI-10 acceptance paragraph against the
real run artefact, independently of what the implementation asserts about itself. Specifically:
the 235-opportunity preservation, the exactly-four accepted actionable overlay, the unchanged
canonical database hash, the ALL OPPORTUNITIES default, the DATA_UNAVAILABLE/NOT_EVALUATED
behaviour against an empty DOI schema, the governed-vs-preferred contract separation, the EIL
relabelling, the Interpreter parity, the advisory resolver's refusal of executable sessions, the
exact-source traceability exit criterion, and the "changes no direction, thesis, lifecycle,
action, size or capital field" guarantee.

Governing design rules applied throughout:

- **§1.1 non-discard** — nothing may discard, hide, permanently invalidate or automatically close
  an opportunity because of entry quality, exit timing, elapsed horizon, spread, liquidity,
  premium, IV, current price or a model score.
- **§14** — "No EIL/DOI/Phantom, timing, entry, exit, Morning Gate or Execution Gate field may
  hide or delete an Intelligence Lab row… Filters may organise views, but the unfiltered governed
  book must retain every row."
- **§17.4** — "Pipeline Interpreter receives the same governed thesis and latest contract assessment"
  (`docs/AVS-SD-DOI-001_DYNAMIC_OPTIONS_INTELLIGENCE.md:569`).
- **DOI-10 Exit** — "a trader can trace every displayed value to a thesis, contract observation and
  model version" (`…:738`).

---

## 2. Method

All work was done on copies. Nothing under `data\`, `dropbox\`, `contracts\` or the control-plane
database was written.

| Step | What |
|---|---|
| DB copy | `audit\doi\AVS-TST-DOI-001\scratch\control_plane.copy.sqlite` → `…\scratch\T10\cp_nodoi.sqlite` (my own further copy; the supplied copy was not modified) |
| Interpreter | `venv\Scripts\python.exe` (3.13.14) |
| Probes written (new files, all under `audit\doi\AVS-TST-DOI-001\`) | `tests\t10_rehearsal_probe.py`, `tests\t10_field_change_detail.py`, `tests\t10_view_filter_census.py`, `tests\t10_source_reconciliation.py`, `tests\t10_merge_fragility_probe.py`, `tests\t10_advisory_resolver_probe.py` |
| Result artefact | `audit\doi\AVS-TST-DOI-001\scratch\T10\t10_rehearsal_result.json` |

### Import-safety proof (why running the probes did not breach the no-execution rule)

The only production modules the probes import are:

- `domain/dynamic_options_projection.py` — stdlib only (`dataclasses`, `enum`, `json`, `typing`).
- `canonical_data/dynamic_options_projection.py` — stdlib only (`json`, `pathlib`, `sqlite3`, `contextlib`, `typing`) plus the above.
- `contracts/interpreter_handoff.py` — stdlib only; its own docstring states "This module contains no market-data or model calls" (lines 1-6), confirmed by `grep '^import\|^from'` (lines 8-20: `csv, hashlib, json, os, tempfile, uuid, dataclasses, datetime, enum, pathlib, typing`).
- `contracts/lab_evidence_overlay.py` — stdlib only.
- `pipeline_interpreter/evidence_resolver.py` (advisory-resolver probe) — verified statically and dynamically: a socket guard was armed before import and no provider/transport module (`marketdata_stock_candles`, `marketdata_response`, `market_observation_resolver`, `polygon_client`, `tastytrade_client`, `requests`, `httpx`, `anthropic`) appeared in `sys.modules`; `canonical_data/__init__.py:484-556` defers all provider transports behind `__getattr__`.

The projection opens the database read-only by construction:
`canonical_data/dynamic_options_projection.py:110-111` —
`uri = self.database.resolve().as_uri() + "?mode=ro"` / `sqlite3.connect(uri, uri=True)`.

### Exact commands

```
venv/Scripts/python.exe audit/doi/AVS-TST-DOI-001/tests/t10_rehearsal_probe.py
venv/Scripts/python.exe audit/doi/AVS-TST-DOI-001/tests/t10_field_change_detail.py
venv/Scripts/python.exe audit/doi/AVS-TST-DOI-001/tests/t10_view_filter_census.py
venv/Scripts/python.exe audit/doi/AVS-TST-DOI-001/tests/t10_source_reconciliation.py
venv/Scripts/python.exe audit/doi/AVS-TST-DOI-001/tests/t10_merge_fragility_probe.py
venv/Scripts/python.exe -m pytest audit/doi/AVS-TST-DOI-001/tests/t10_advisory_resolver_probe.py -x -q
venv/Scripts/python.exe -m pytest <each of the 12 DOI pack files> -q      # one file per process
```

### Artefacts and field names used

| Role | Path | Key fields |
|---|---|---|
| Governed v2 book | `data\output\runs\20260909_071646\intelligence_lab\final_opportunity_book_20260909_071646.json` (and `.csv`) | `rows`, `candidate_count`, `lab_schema_version`, `governed_direction`, `thesis_id`, `trade_idea_id`, `selected_contract_symbol`, `strike`, `expiry` |
| Accepted actionable handoff | `data\output\runs\20260909_071646\interpreter\handoff_manifest.json` → `…\intelligence_lab\lab_signal_book_v3.csv` | `run_status=ACCEPTED`, `reconciliation_status=PASS`, `ticker_count=4`, `bundle_count=4` |
| Canonical DOI store | `data\canonical\control_plane.sqlite` (path computed at `contracts/lab_control.py:3354`) | tables `doi_contract_families`, `doi_contract_assessments`, `doi_family_rankings` — **none present** |
| Projection output | 22 `doi_*` fields, `domain/dynamic_options_projection.py:67-91` | `doi_projection_state`, `doi_projection_reason`, `doi_governed_contract_symbol`, `doi_preferred_contract_symbol`, `doi_contract_alignment`, `doi_p_*`, `doi_model_uncertainty`, `doi_probability_model_id`, `doi_evidence_cutoff_utc`, `doi_input_dataset_ids_json`, `doi_alternatives_json`, `doi_authority` |
| UI | `intelligence-lab\static\index.html` (3518 lines, mtime 2026-09-10 10:24) | DOI pane lines 2678-2709; EIL pane 2712-2742; filters 1897-1929 |

---

## 3. Evidence and results per claim

### 3.1 "preserved all 235 opportunities while overlaying exactly four accepted actionable rows"

**RESULT: VERIFIED.** Both numbers reproduce exactly on copies.

```
GOVERNED BOOK (v2 payload rows)                     CALL 151 / PUT  84 / OTHER   0  (n=235)
AFTER DOI-10 merge + projection (result.signals)    CALL 151 / PUT  84 / OTHER   0  (n=235)
rows carrying lab_actionable_handoff_member = True  CALL   4 / PUT   0 / OTHER   0  (n=4)
merge_reconciliation = {"status":"PASS","full_opportunity_count":235,
                        "actionable_handoff_count":4,"actionable_rows_overlaid":4,
                        "population_preserved":true}
identities_preserved (run_id,ticker,thesis_id,trade_idea_id, ordered) = True
```

| Population | CALL | PUT | OTHER | Total |
|---|---|---|---|---|
| Governed v2 final opportunity book | 151 | 84 | 0 | **235** |
| After DOI-10 merge | 151 | 84 | 0 | **235** |
| After DOI-10 projection | 151 | 84 | 0 | **235** |
| Accepted actionable rows overlaid | **4** | **0** | **0** | **4** |

The four are `CVNA, ANET, HPE, CSCO` — **all CALL**. The acceptance paragraph does not disclose
that the overlay was exercised on one direction only; the PUT and OTHER legs of the overlay path
have **no run-artefact evidence at all**.

Queries used (`tests/t10_rehearsal_probe.py`):
`json.load(final_opportunity_book_…json)["rows"]` → 235;
`validate_handoff_manifest(handoff_manifest.json, require_accepted=True).book_rows` → 4;
`merge_all_opportunities(full_rows, actionable_rows)` (`domain/dynamic_options_projection.py:102`);
`DynamicOptionsProjectionResolver(cp_nodoi.sqlite).project_rows(merged)` (`canonical_data/dynamic_options_projection.py:102`).

Ticker uniqueness in the 235: 235 unique tickers, 235 unique `thesis_id`, 235 unique
`trade_idea_id`, 0 empty. This is why the merge succeeds — see defect **D4**.

**Confidence: HIGH.** Reproduced end-to-end on a real run artefact with the production modules.
Nothing would raise it further.

### 3.2 "the canonical database hash remained unchanged"

**RESULT: VERIFIED.**

```
sha256 before = 0f725c01208a427818ebf49c6f964de12610ed3a21010ddde4081d564629cfdc
sha256 after  = 0f725c01208a427818ebf49c6f964de12610ed3a21010ddde4081d564629cfdc
db_hash_unchanged = True
```

Cross-check — all three files are byte-identical (129,794,048 bytes):

| sha256 | file |
|---|---|
| `0f725c01…29cfdc` | `data\canonical\control_plane.sqlite` (live, read-only hash) |
| `0f725c01…29cfdc` | `audit\doi\AVS-TST-DOI-001\scratch\control_plane.copy.sqlite` |
| `0f725c01…29cfdc` | `audit\doi\AVS-TST-DOI-001\scratch\T10\cp_nodoi.sqlite` (my copy, after projection) |

**Confidence: HIGH.** The read-only URI at `canonical_data/dynamic_options_projection.py:110` is a
structural guarantee, and the hash is empirically unchanged.

### 3.3 "The UI defaults to `ALL OPPORTUNITIES`" and no filter reduces the unfiltered book

**RESULT: VERIFIED (with one latent defect, D11).**

The default is real: `intelligence-lab/static/index.html:599`
`let showAuditRows = true;      // DOI-10 defaults to the complete governed opportunity population`
and `:338` renders the button pre-activated —
`<button class="fb active" id="btn-show-audit" onclick="toggleAuditRows(this)" title="Toggle between the complete governed opportunity population and the actionable subset">All Opportunities</button>`.
`:2150` toggles the label to `Actionable Only`.

Note: the rendered label is `All Opportunities` (title case). The literal string `ALL OPPORTUNITIES`
does not exist in the UI — the acceptance paragraph quotes a label that is not on screen.

Census of every view the Lab offers, over the merged+projected 235
(`tests/t10_view_filter_census.py`, porting `index.html:1897-1929`):

| View | CALL | PUT | OTHER | n | vs 235 |
|---|---|---|---|---|---|
| **DEFAULT (All Opportunities)** | **151** | **84** | **0** | **235** | **retains every row** |
| Actionable Only toggle (`showAuditRows=false`) | 148 | 83 | 0 | 231 | −4 |
| `campaignViewMode` (Campaign card) | 0 | 0 | 0 | 0 | −235 |
| `SIGNALS` = `isActionSignal` (drives Top 5 / stats) | 4 | 0 | 0 | 4 | −231 |
| quickFilter monetisable | 113 | 67 | 0 | 180 | −55 |
| `filters.dir = CALL` | 151 | 0 | 0 | 151 | −84 |
| `filters.dir = PUT` | 0 | 84 | 0 | 84 | −151 |
| `filters.verdict = BLOCKED` | 3 | 1 | 0 | 4 | −231 |
| `filters.verdict = CONTRACT_REPAIR` | 15 | 13 | 0 | 28 | −207 |
| `filters.verdict = GO_LIMIT` | 4 | 0 | 0 | 4 | −231 |
| `filters.verdict = MANUAL_REVIEW` | 129 | 70 | 0 | 199 | −36 |
| `filters.camp = BLOCKED` | 3 | 1 | 0 | 4 | −231 |
| `filters.camp = CONTRACT_REPAIR` | 15 | 13 | 0 | 28 | −207 |
| `filters.camp = READY_LIMIT` | 4 | 0 | 0 | 4 | −231 |
| `filters.camp = WATCHLIST` | 129 | 70 | 0 | 199 | −36 |

Every one of these is an *organising* filter selected by the user, which §14 expressly permits
("Filters may organise views"). The **unfiltered** default retains all 235 — the §14 requirement.
The 4 rows hidden by `Actionable Only` are the 4 `BLOCKED` rows (CALL 3 / PUT 1), not the 4 accepted
actionable rows.

Two server-side population filters exist but are **dead in the governed path**, both inside
`_load_run` and both overwritten at `intelligence-lab/intelligence_lab.py:2110`
(`result["signals"] = [dict(row) for row in governed_book.get("rows", [])]`):

- `:1460` `_filter_to_handoff_signals` — would reduce the book to the handoff slate.
- `:2093` `if LAB_STRANGLE_POLICY == "EXCLUDE":` — would drop `lab_coherence_status == "STRANGLE_NONDIRECTIONAL"` rows. Default is `INCLUDE_LABELLED` (`:126`).

**Confidence: HIGH** for the default-view result (measured on the artefact).
**MEDIUM** for the client-side census — it is a faithful Python port of the JS, not the JS itself;
driving the real page in a browser against this run would raise it to HIGH.

### 3.4 Empty DOI schema → DATA_UNAVAILABLE / NOT_EVALUATED, no removed rows, no zero-valued evidence

**RESULT: VERIFIED (resolver) / PARTIAL (renderer, defect D9).**

The live control plane genuinely has **zero** DOI tables (11 tables total, `[x for x in tables if 'doi' in x.lower()] == []`), so the reference environment *is* the empty-schema case. Result over all 235:

```
projection_state_counts        = {"DATA_UNAVAILABLE": 235}
projection_reason_counts       = {"DOI_TABLES_NOT_ACTIVATED": 235}
  by direction                 = CALL 151 / PUT 84 / OTHER 0
projection_population_preserved= True   (235 -> 235)
doi_p_liquidity_3d             = {None: 235}
doi_p_positive_return          = {None: 235}
doi_p_target_before_invalidation = {None: 235}
doi_model_uncertainty          = {None: 235}
projection_zero_valued_evidence_rows = 0
doi_authority/decision/execution = ('ADVISORY_ONLY','NONE','HUMAN_ONLY') x 235
```

No row removed, no probability coerced to 0. `domain/dynamic_options_projection.py:56-59` raises if
the projection ever claims authority; `:64-65` raises on any probability outside [0,1]. The four
`NOT_EVALUATED` paths (`canonical_data/dynamic_options_projection.py:50-67`,
`NO_DOI_FAMILY_FOR_GOVERNED_THESIS` / `DOI_FAMILY_NOT_RANKED`) exist in source but **did not fire on
this artefact** — only `DOI_TABLES_NOT_ACTIVATED` and, for a missing file,
`CANONICAL_DOI_STORE_MISSING` (`:107`) are reachable here.

The renderer weakens this — see **D9**. `index.html:2680`
`const doiState = s['doi_projection_state'] || 'NOT_EVALUATED';` means an *absent* field (the state
of every row of this pre-DOI run as stored on disk: `doi_projection_state` is `null` on all 235 in
`final_opportunity_book_…json`) is displayed as **NOT_EVALUATED**, not `DATA_UNAVAILABLE`. The UI
therefore cannot distinguish "the projection never ran" from "the projection ran and found no family".

**Confidence: HIGH** for the resolver (artefact evidence). **HIGH** for D9 (source is unambiguous).

### 3.5 "separates the governed contract from the DOI-preferred contract, displays alignment…"

**RESULT: PARTIAL.**

The three fields are genuinely separate, in both the contract and the rendered UI
(`index.html:2696-2698`):

```html
<div class="m-field"><div class="mf-k">Governed Contract</div><div class="mf-v">${doiGoverned}</div></div>
<div class="m-field"><div class="mf-k">DOI Preferred Contract</div><div class="mf-v a">${doiPreferred}</div></div>
<div class="m-field"><div class="mf-k">Contract Alignment</div><div class="mf-v">${doiAlignment}</div></div>
```

backed by `doi_governed_contract_symbol` / `doi_preferred_contract_symbol` / `doi_contract_alignment`
(`domain/dynamic_options_projection.py:77-79`). Uncertainty, evidence cutoff, model identity and
alternatives are all present as distinct fields and rendered at `:2699-2709`. The advisory caption
at `:2692` is correct and unambiguous:

> "Human execution only. This ranking cannot change direction, invalidate the thesis, remove the
> opportunity, size the position, or grant capital."

Why PARTIAL:

1. **Separation is never exercised on the artefact.** `doi_preferred_contract_symbol` is populated on
   **0 of 235** rows; `doi_contract_alignment` is `NOT_COMPARABLE` on **235 of 235**. The
   `MATCH` / `DIFFERENT_ADVISORY` / `NO_CURRENT_CONTRACT` branches
   (`canonical_data/dynamic_options_projection.py:74`) have no run-artefact evidence.
2. **The "governed contract" it displays is wrong on 11 rows** and absent on 24 — see **D1**.

**Confidence: HIGH** that the fields are separate; **HIGH** that the comparison is unexercised.
A run with DOI tables populated is what would raise this to VERIFIED.

### 3.6 "relabels legacy EIL output as non-authoritative entry telemetry"

**RESULT: REFUTED.** Nothing is hidden; the wording is mislabelled on the surface the trader scans.

The relabelling was done in three places, all inside the per-ticker modal (two clicks deep):
`index.html:566` tab `Entry Telemetry`; `:2720` section header `Legacy Entry Telemetry — Advisory Only`;
`:2736` field label `Legacy Size Diagnostic (Non-authoritative)`; and the one fully compliant
disclaimer at `:2718`:

> "Historical microstructure classification only. It does not validate the thesis, select a
> contract, size a position, remove an opportunity, or grant capital."

Against that, the rendered strings that still assert thesis/trade authority:

| Sev | Path : line | Exact rendered literal | Reading |
|---|---|---|---|
| CRITICAL | `intelligence-lab\static\index.html:2737` | `<div class="mf-k">Advisory Only</div><div class="mf-v">${eilAdv?'YES':'NO'}</div>` → renders **`Advisory Only   NO`** | A rendered *data value* explicitly denying non-authoritative status, one line below the "(Non-authoritative)" label and inside the pane headed "Advisory Only". `eilAdv` is true only for the literal `'True'`/`'true'`; blank, numeric, `1` or `Y` all render **NO**. |
| CRITICAL | `…\index.html:2116` | `… : display==='EXECUTE'?'EXEC':'STOP';` → pill reading **`STOP`** | Signal-table column 22, the main scanning surface. Every EIL verdict that is not one of four EXECUTE variants — `BLOCKED`, `STAND_DOWN_MICROSTRUCTURE`, `WATCHLIST`, `AVOID`, and any unrecognised value — collapses to the imperative **STOP**. No tooltip, no legend, no disclaimer on that page. |
| HIGH | `…\index.html:1364`; `intelligence-lab\intelligence_lab.py:1799-1800` | `BLOCKED: 'NO_TRADE'`, `"NEGATIVE_RR": "NO_TRADE"` — rendered at `index.html:1118`, `:2407`, `:2941` | **`NEGATIVE_RR → NO_TRADE` is the §1.1 violation in its purest form: an opportunity captioned "do not trade" because of a model score.** |
| HIGH | `intelligence_lab.py:2901` → DOM at `index.html:3483` | `f"{ticker}: options_verdict=…, campaign=…, thesis=… — not tradeable"` | The literal phrase "not tradeable" reaches the trader via `errEl.textContent = data.error`. |
| HIGH | `intelligence_lab.py:2777` → same sink | `f"{ticker}: not Lab-tradeable"` | as above |
| HIGH | `…\index.html:2065`, `:2335` | raw **`BLOCKED`** in a red `p-sd` pill under the header `Verdict` | No caption or legend anywhere explains that a BLOCKED row is retained and reviewable. |
| HIGH | `…\index.html:1752-1764` (`getEilDisplay`) | fallback chain includes `final_decision_advisory_verdict`, `fd_advisory_verdict`, `fd_verdict` | A genuine thesis-level Final-Decision verdict (`fd_verdict` takes `BLOCK`) is rendered under the advisory "Entry Telemetry" header — and via the row above, as **STOP**. Authority and telemetry launder through each other in both directions. |
| MEDIUM | `intelligence_lab.py:1801-1803` → `index.html:2347`, `:3008` | `size_display = "0% - blocked"` | |
| MEDIUM | `…\index.html:2983`, `:2431`, `:2343` | `VETOED`, `⚠ Active Veto`, `⚠ VETO` | no non-authoritative caption |
| MEDIUM | `…\index.html:2660` | `Hard Rejects` | red when populated |
| MEDIUM | `…\index.html:999` | "Stand-downs are controlled by the governed Execution Gate; macro and EV remain advisory." | An **anti-disclaimer**: it affirms stand-downs are authoritative and scopes "advisory" to macro and EV only, so a reader concludes entry telemetry is *not* advisory. This is the "false advisory text" pattern the prior finding warned about. |
| LOW | `…\index.html:2742` | the compliant disclaimer at `:2718` is painted `var(--red)` (`eilColor`, `:2716`) at the bottom of the pane | red styling makes a disclaimer read as a warning about the trade |

The **backend is correct**: `contracts/dynamic_options_policy.py:39-49` converts every EIL verdict,
`BLOCKED` included, into `EIL_ADVISORY_*` disclosure flags and never a veto, and EIL is absent from
`isAuditOnlySignal()` (`index.html:1399-1417`), so it hides nothing. Grepping the live file for
`non-authoritative` returns exactly one hit (`:2736`).

**Confidence: HIGH.** Rendered literals were read, not variable names. Dead files
(`static/Archive/*`, `index*old*.html`) were excluded: `intelligence_lab.py:2595-2597` serves only
`static/index.html`.

### 3.7 §17.4 — "Supply the same latest assessment to Pipeline Interpreter"

**RESULT: VERIFIED for the 4 handoff tickers; NOT APPLICABLE for the other 231 (documented scope).**

The v3 book row and the Interpreter bundle are two serialisations of one object, by construction —
`contracts/interpreter_handoff_materializer.py:498-503`:

```python
# The v3 book and bundle are two serialisations of the same governed
# record.  Computed quote evidence must never exist only in the bundle.
book_row = dict(bundle["governed_record"])
book_row.update(identity)
book_row["lab_schema_version"] = BOOK_SCHEMA_VERSION
```

Diff of `bundle.governed_record` vs the `lab_signal_book_v3` row, all 4 tickers: 470 fields both
sides, 470 common, 0 only-in-bundle, 0 only-in-book. Ten raw string diffs per ticker, of which nine
are CSV `None`→`''` serialisation artefacts on `contract_*_change*` fields. **One genuine diff:**
`lab_schema_version` — bundle `lab_signal_book_v2`, book `lab_signal_book_v3` (defect D10b).

Assessment identity matches exactly on every ticker (`run_id`, `pipeline_mode`, `thesis_id`,
`trade_idea_id`, `selected_structure_id`, `selected_contract_symbol`, `selected_quote_snapshot_id`,
`bundle_id`, `validation_event_id`):

| Ticker | thesis_id | bundle_id | validation_event_id | evidence cutoff |
|---|---|---|---|---|
| CVNA | `CVNA:CALL:2026-09-08:OLM2` | `9ed4801c-1b31-5eb6-88dc-e918a1170339` | `validation_4048cfd62a995331570e146d` | `2026-09-09T14:00:07Z` |
| ANET | `ANET:CALL:2026-09-08:OLM2` | `d4ba2ffc-ef31-5de6-99dd-50083c20750d` | `validation_54a9d2f2931bff0b30956725` | `2026-09-09T14:00:17Z` |
| HPE  | `HPE:CALL:2026-09-08:OLM2`  | `046389ee-9348-5003-bba6-0b120078dee6` | `validation_52d363c1b00d38233f34c301` | `2026-09-09T13:59:11Z` |
| CSCO | `CSCO:CALL:2026-09-08:OLM2` | `b75da79f-93b5-5d94-a84c-c709ab5ad4d7` | `validation_bf5d21dc1f63409e5b24aa93` | `2026-09-09T13:59:05Z` |

**The Interpreter is not staler — the Lab is.** Diffing the v3 Interpreter payload against the Lab's
own full book gives 6 value diffs per ticker, and two of them run the wrong way:
`contract_bid_size` / `contract_ask_size` are CVNA 117/43, ANET 116/114, HPE 4/1269, CSCO 68/49 in
the Interpreter payload but CVNA 7.0/49.0, ANET 102.0/70.0, HPE 1.0/185.0, CSCO 94.0/94.0 in the
Lab full book — while the *same* full-book row already holds 117/43 in
`morning_contract_bid_size`/`morning_contract_ask_size`, under an unchanged
`selected_quote_snapshot_id`. See defect **D10a**. Serialisation order confirms the direction:
full book `14:01:07.207` < v3 book `14:01:21.398` < bundles `14:01:21.386-388` < manifest `14:01:21.439`.

Evidence seen firing (not merely read): with a socket guard armed,
`pipeline_interpreter.evidence_resolver.handoff_status()` with no pinned path resolved to
`20260909_071646` and returned
`{"status":"READY","ticker_count":4,"bundle_count":4,"hashes_verified":true,"run_status":"ACCEPTED"}` —
all four SHA-256s still verify. `resolve_interpreter_evidence` returned for all 4 tickers × all 4
`IntendedUse` values with `refresh_required = None`.

Population split of the gap: **in the Lab book but not in the Interpreter handoff — CALL 147 / PUT 84
/ OTHER 0 (n=231).** This is a documented scope choice ("The accepted Interpreter handoff remains
actionable-only", `docs/…:746`), not staleness: the 231 carry `validation_event_id = None`, i.e. no
Morning-Gate assessment exists for them. Selection is at `morning_handoff_finalizer.py:509-514`
(`final_action in {"BUY_NOW","BUY_SMALL"}`); full-book `final_action` distribution is
BUY_SMALL CALL 4/PUT 0, BLOCK CALL 3/PUT 1, CONTRACT_REPAIR CALL 15/PUT 13, MANUAL_REVIEW CALL 129/PUT 70.

**Confidence: HIGH.** Both artefacts were diffed field-by-field and the resolver was observed
resolving the reference run.

### 3.8 "A separate advisory resolver … explicitly rejects executable-session requests"

**RESULT: VERIFIED OFFLINE.** The refusal is a real `raise`, not a cosmetic string — but the
resolver is not wired into production (defect D8).

`pipeline_interpreter/evidence_resolver.py:282-295`:

```python
def resolve_interpreter_opportunity(
    ticker: str, *, run_id: str | None = None,
    intended_use: IntendedUse | str = IntendedUse.EOD_REVIEW,
    runs_dir: Path | str = DEFAULT_RUNS_DIR,
) -> ResolvedOpportunityEvidence:
    """Resolve any governed opportunity without pretending it is executable."""
    symbol = _text(ticker).upper()
    if not symbol:
        raise EvidenceResolutionError("TICKER_REQUIRED")
    use = intended_use if isinstance(intended_use, IntendedUse) else IntendedUse(str(intended_use).upper())
    if use not in {IntendedUse.EOD_REVIEW, IntendedUse.TRAJECTORY}:
        raise EvidenceResolutionError("FULL_BOOK_USE_NOT_ADVISORY", use.value)
```

Line 294 is a **whitelist**, so `EXECUTABLE_SESSION`, `INTRADAY_ADVISORY` and any future enum member
all fail closed; an unrecognised string fails at line 293 in the enum constructor. It executes
*before* `runs_dir` is touched (line 296 onward) — the probe proves this by passing an empty
`runs_dir` and still getting `FULL_BOOK_USE_NOT_ADVISORY` rather than a missing-book code.

```
$ venv/Scripts/python.exe -m pytest audit/doi/AVS-TST-DOI-001/tests/t10_advisory_resolver_probe.py -x -q
.............................                                            [100%]
29 passed in 10.86s
```

29 tests: network-guard arming, provider-import proof, rejection of `EXECUTABLE_SESSION` /
`INTRADAY_ADVISORY` (enum and string forms), rejection-before-file-access, `ValueError` on an
unknown `"LIVE"`, acceptance of `EOD_REVIEW` / `TRAJECTORY` with `authority == "ADVISORY_ONLY"` and
`provider_calls == 0`, and the same assertions replayed against the frozen reference run for
`VIPS, ZYME, AAOI, CAPR, MATW, GDS, CVNA` over the 235-row book (CALL 151 / PUT 84 / OTHER 0).
`CVNA` — one of the four *actionable* tickers — is equally refused an executable session there, so
the refusal is a property of the resolver, not of the row's actionability.

Rated **VERIFIED OFFLINE** rather than VERIFIED: the refusal is proven by a test I wrote, and the
reference run contains no artefact showing a production caller being refused — because there is no
production caller (D8).

**Confidence: HIGH** on the mechanism; wiring it into an Interpreter command and capturing a refusal
in a run artefact would make it VERIFIED.

### 3.9 Exit criterion — "trace every displayed value to a thesis, contract observation and model version"

**RESULT: REFUTED on this artefact.**

Ten rows traced (5 CALL — the four accepted actionable plus one governed-only; 5 PUT), against the
14 values the DOI pane renders (`index.html:2691-2709`):

| Displayed label | Field | Rows falling through to a JS fallback string |
|---|---|---|
| Ranking Mode | `doi_ranking_mode` | **10/10** → `'NOT EVALUATED'` |
| DOI Preferred Contract | `doi_preferred_contract_symbol` | **10/10** → `'—'` |
| Executable in 3 Sessions | `doi_p_liquidity_3d` | **10/10** → `'NOT EVALUATED'` |
| Positive Return | `doi_p_positive_return` | **10/10** → `'NOT EVALUATED'` |
| Target Before Invalidation | `doi_p_target_before_invalidation` | **10/10** → `'NOT EVALUATED'` |
| Model Uncertainty | `doi_model_uncertainty` | **10/10** → `'NOT EVALUATED'` |
| Evidence Cutoff | `doi_evidence_cutoff_utc` | **10/10** → `'NOT EVALUATED'` |
| Model | `doi_probability_model_id` | **10/10** → `'NOT EVALUATED'` |
| Ranked Contract Family | `doi_alternatives_json` | **10/10** → `'No ranked alternatives available.'` |
| Governed Contract | `doi_governed_contract_symbol` | **5/10** → `selected_contract_symbol` → `'—'` |
| Projection State / Contract Alignment / Authority / Reason | — | 0/10 (traceable) |

`doi_input_dataset_ids_json` is `[]` on all 235 — **no contract observation dataset ID is traceable
for any displayed value on this run**, and no model/calculation version either
(`doi_probability_model_id` empty on 235/235). The only version identifiers on the rows are
`dir_calc_version = dir_v1.2.0` and `direction_policy_version = strangle_resolution_v1.1.0`, which
belong to direction governance, not to DOI.

This is a fair consequence of the DOI tables being inactive — but it means the DOI-10 exit criterion
is **untested by the rehearsal**, and the acceptance paragraph does not say so.

The one DOI value with real content, `doi_governed_contract_symbol`, is **traceable to the wrong
thing** — see D1. Across all 235:

| | CALL | PUT | OTHER |
|---|---|---|---|
| Governed contract coherent with the row's own `strike`/`expiry` | 129 | 71 | 0 |
| **Contract symbol CONTRADICTS the row's `strike`/`expiry`/`trade_idea_id`** | **7** | **4** | **0** |
| No parseable governed contract symbol (renders `'—'`) | 15 | 9 | 0 |

**Confidence: HIGH.**

### 3.10 "DOI-10 changes no direction, thesis, lifecycle, action, size or capital field"

**RESULT: PARTIAL.** True for direction/thesis/lifecycle/size/capital on this run;
**false as written for `action`**; and **unenforced for all of them**.

The projection leg is clean: `projection_nondoi_column_changes = {}` — the resolver changes zero
non-DOI columns across all 235 rows, exactly as `row.update(projection.to_fields())` implies.

The **merge** leg mutates 24 non-DOI fields on the 4 overlaid rows:

```
PROTECTED_AUTHORITY_FIELDS mutated : 1  -> ['selected_contract_symbol']
outside OVERLAY_ALLOWED_FIELDS     : 16 -> ['bundle_id','execution_quote_human_confirmation_required',
   'execution_quote_status','execution_quote_timestamp_utc','lab_schema_version','lab_status_banner',
   'model_final_action','selected_contract_symbol','validation_current_price','validation_data_status',
   'validation_event_id','validation_evidence_cutoff_utc','validation_gap_pct',
   'validation_profile_evidence_state','validation_reason','validation_transition']
```

The two that matter against the claim:

```
### model_final_action                     <-- an ACTION field
    CVNA/ANET/HPE/CSCO   before=None  ->  after='BUY_SMALL'

### selected_contract_symbol               <-- PROTECTED_AUTHORITY_FIELD (lab_evidence_overlay.py:58)
    CVNA   before=None  ->  after='CVNA260925C00075000'
    ANET   before=None  ->  after='ANET260925C00200000'
    HPE    before=None  ->  after='HPE260925C00057000'
    CSCO   before=None  ->  after='CSCO260925C00108000'
```

Also introduced by the merge: `lab_status_banner = 'THESIS CONFIRMED — EXECUTION VIABILITY PASSED'`
on all four, and `quote_freshness` flipped `FRESH → STALE`, `comparison_status`/`change_status`
`'' → STALE`.

Every one of these is a `None → value` fill inherited from the *accepted* v3 handoff, which is the
governed authority for those rows — so the economic content is defensible. But the claim as written
("changes no … action … field") is falsified by `model_final_action`, and no mechanism enforces the
rest. See **D2** and **D3**.

**Confidence: HIGH** on the measured diff; **HIGH** on the absence of a guard (proven, D2).

### 3.11 "The 115-test DOI regression pack passed"

**RESULT: PARTIAL — the pack passes, the number is wrong.**

```
$ venv/Scripts/python.exe -m pytest <12 DOI files> --collect-only -q
124 tests collected in 23.88s
```

| File | tests | result |
|---|---|---|
| `tests/test_doi10_projection_integration.py` | 8 | 8 passed |
| `tests/test_doi11_production_integration.py` | 5 | 5 passed |
| `tests/test_doi_phase_quality_assurance.py` | 3 | 3 passed |
| `tests/test_dynamic_options_contract_family.py` | 7 | 7 passed |
| `tests/test_dynamic_options_deterministic_valuation.py` | 14 | 14 passed |
| `tests/test_dynamic_options_domain_persistence.py` | 11 | 11 passed |
| `tests/test_dynamic_options_lifecycle.py` | 16 | 16 passed |
| `tests/test_dynamic_options_non_discard_policy.py` | 4 | 4 passed |
| `tests/test_dynamic_options_observation_bridge.py` | 14 | 14 passed |
| `tests/test_dynamic_options_outcomes.py` | 16 | 16 passed |
| `tests/test_dynamic_options_probability.py` | 13 | 13 passed |
| `tests/test_dynamic_options_ranking.py` | 13 | 13 passed |
| **Total** | **124** | **124 passed, 0 failed** |

Claimed 115, actual **124**. All pass, so this is a documentation error, not a quality problem —
unless "the DOI regression pack" is a narrower set than the 12 `doi`/`dynamic_options` test modules,
in which case the acceptance paragraph does not say which. None of the 124 exercises the reference
run artefact, so this is **VERIFIED OFFLINE** at best.

**Confidence: HIGH** on the count and the pass result; **MEDIUM** on whether I enumerated the same
"pack" the author meant — a named manifest listing the pack's members would settle it.

---

## 4. Defects raised

| ID | Class | Sev | Finding |
|---|---|---|---|
| **D1** | LIN | **P1** | **The "Governed Contract" DOI-10 displays contradicts the governed trade idea on 11 of 235 rows (CALL 7 / PUT 4), including all 4 accepted actionable rows, and is absent on 24 more (CALL 15 / PUT 9).** A contract repair/roll updated `selected_contract_symbol` but left `strike`, `expiry` and `trade_idea_id` at pre-repair values. e.g. ANET: `selected_contract_symbol=ANET260925C00200000` (strike 200, expiry 2026-09-25) vs row `strike=195.0 expiry=2026-09-18` and `trade_idea_id=20260909_071646:ANET:CALL:LONG_CALL:195.0:2026-09-18`; `previous_contract_symbol=ANET260918C00195000` confirms the roll. Also IBM PUT 245 vs 230, PINS PUT 22 vs 20, GM CALL 81 vs 85. `canonical_data/dynamic_options_projection.py:23-27` picks `selected_contract_symbol` as *the* governed contract and silently discards the conflicting identity; it is then the left-hand side of the DOI alignment comparison (`:74`). A trader reading the DOI pane sees an executable OCC symbol whose strike and expiry differ from the trade idea beside it. Related: `contract_repair_action='NOT_REQUIRED'` while `contract_repair_required=True` and `contract_repair_status='CONTRACT_REPAIR_REQUIRED'` on the same rows. |
| **D2** | AUTH | **P1** | **Nothing prevents the DOI-10 merge from overwriting `governed_direction`.** `merge_all_opportunities` (`domain/dynamic_options_projection.py:112-124`) reconciles only `run_id`, `ticker`, `thesis_id`, `trade_idea_id` — and only when *both* sides are non-empty (`:119-121`) — then performs a bare `base.update(row)` (`:122`). Direction, thesis state, lifecycle, size and capital are not in the key and not protected. Proven in `tests/t10_merge_fragility_probe.py`: an actionable row carrying `governed_direction='PUT'` flips a `CALL` governed row to `PUT` and still reports `actionable_rows_overlaid=1`, `status=PASS`. The acceptance claim "DOI-10 changes no direction… field" holds for run `20260909_071646` by coincidence, not by construction. |
| **D3** | AUTH | **P2** | **The merge bypasses the repo's own overlay authority rules.** `contracts/lab_evidence_overlay.py:55-64` defines `PROTECTED_AUTHORITY_FIELDS` and `:98-103` raises `OVERLAY_AUTHORITY_FIELD` if an overlay touches one. `merge_all_opportunities` has no allow-list and no protected-field guard, and in this run it mutated `selected_contract_symbol` (a protected field) plus 15 other fields outside `OVERLAY_ALLOWED_FIELDS`, including `model_final_action` (an action field) and `lab_status_banner` ("THESIS CONFIRMED — EXECUTION VIABILITY PASSED"). Two overlay paths into the same book with contradictory rules. |
| **D4** | DEL | **P2** | **A duplicate or empty ticker silently destroys the entire DOI-10 overlay.** `domain/dynamic_options_projection.py:108-110` raises `ValueError("full opportunity book requires unique non-empty tickers")` — aborting the *whole* merge, not the offending row — and `intelligence-lab/intelligence_lab.py:317-320` swallows it with a bare `except Exception: pass`, silently serving the un-overlaid v2 book. Proven for a ticker carrying both a CALL and a PUT thesis, for a `STRANGLE` row alongside a directional one, and for a blank ticker. Given the repo runs `strangle_resolution_v1.1.0` and has a `STRANGLE_NONDIRECTIONAL` coherence state, a two-sided ticker is a legitimate population, and the failure is silent apart from `lab_signal_source` reverting to `GOVERNED_FINAL_OPPORTUNITY_BOOK_V2`. |
| **D5** | NULL | **P2** | **The merge stamps `lab_schema_version='lab_signal_book_v3'` on exactly the 4 accepted rows, and `index.html:672` `populateGovernedDisplayFields` returns early unless it is `'lab_signal_book_v2'`.** Measured: `{'lab_signal_book_v3': 4, 'lab_signal_book_v2': 231}` — CVNA, ANET, HPE, CSCO. The four most important rows therefore lose the governed display aliasing for `sb_campaign`, `sb_execution_mode`, `sector_name` and `sb_vetoes`. Introduced by DOI-10. |
| **D6** | AUTH | **P1** | **Legacy EIL output is not relabelled as non-authoritative in the rendered UI** (§3.6). Headline items: `index.html:2737` renders **`Advisory Only   NO`**; `index.html:2116` collapses every non-EXECUTE EIL verdict to the imperative pill **`STOP`** on the main scan table; `intelligence_lab.py:1799-1800` maps `NEGATIVE_RR → NO_TRADE`, captioning an opportunity "do not trade" because of a model score (direct §1.1 breach); `intelligence_lab.py:2901`/`:2777` emit "not tradeable"/"not Lab-tradeable" to the DOM; `index.html:999` is an anti-disclaimer scoping "advisory" to macro and EV only. Nothing is hidden — the defect is purely in wording, and the backend (`contracts/dynamic_options_policy.py:39-49`) is correct. |
| **D7** | DOC/TEST | **P3** | **"The 115-test DOI regression pack passed" — the pack collects 124 tests, not 115.** All 124 pass. Either the count is stale (DOI-11 added tests after it was written) or the pack's membership is undefined. No named manifest exists. |
| **D8** | DOC | **P2** | **The "separate advisory resolver" is not reachable from production.** `resolve_interpreter_opportunity` (`pipeline_interpreter/evidence_resolver.py:282`) is real and enforcing, but is omitted from `evidence_resolver.__all__` (`:344-348`) along with `ResolvedOpportunityEvidence`, and a repo-wide grep (excluding `backups/`, `_attic/`, `_cleanup_holding/`) finds callers only in the module itself and in `tests/test_doi10_projection_integration.py:128-139`. `pipeline_interpreter_commands.py:44-46` imports only `IntendedUse` and `resolve_interpreter_evidence`. The acceptance paragraph's present tense ("exposes non-actionable rows… for EOD review") overstates a facility no live command offers. |
| **D9** | NULL | **P2** | **The renderer collapses "projection never ran" into `NOT_EVALUATED`.** `index.html:2680` `const doiState = s['doi_projection_state'] \|\| 'NOT_EVALUATED';`. On this run `doi_projection_state` is `null` on all 235 rows as stored, so the UI would show NOT_EVALUATED where the resolver would have said `DATA_UNAVAILABLE / DOI_TABLES_NOT_ACTIVATED`. Same pattern on 8 further fields, and `index.html:2682` falls `doi_governed_contract_symbol` back to `selected_contract_symbol`, masking the distinction the projection took care to draw. The claim's letter is met (both states are "explicit"), its intent is not. |
| **D10** | LIN | **P2** | (a) **The Lab full book carries stale `contract_bid_size`/`contract_ask_size` that contradict its own `morning_contract_*_size` under an unchanged `selected_quote_snapshot_id`** — CVNA 7.0/49.0 in `contract_*_size` vs 117/43 in `morning_contract_*_size` and in the Interpreter payload; same on ANET, HPE, CSCO. Two different quote sizes under one snapshot id. (b) Every Interpreter bundle's `governed_record` mislabels `lab_schema_version` as `lab_signal_book_v2` (`interpreter_handoff_materializer.py:502` stamps the book but not the bundle's copy). |
| **D11** | DEL | **P3** | **Latent §14 breach: `index.html:706` reassigns the base population rather than filtering a view.** `if(!SHOW_INVALID){ ALL_SIGS = ALL_SIGS.filter(s => s.sb_schema_ok !== 'N'); }` with `SHOW_INVALID = false` by default (`:589`). Every count, stat and view — including "All Opportunities" — derives from the reduced `ALL_SIGS`, and there is no way back except the "Show invalid" checkbox. **0 rows affected on this run** (`sb_schema_ok` is `None` on all 235), so it does not fire here, but structurally it can remove rows from the book §14 says must retain every row. |
| **D12** | SYM | **P3** | **Observation, possibly by design:** on 2 of the 4 accepted actionable rows the direction evidence is 100 % weighted against the governed direction, yet the row reads `DIRECTION_CONFIRMED`. ANET: `direction_resolution_put_score=1.75`, `direction_resolution_call_score=0.0`, `direction_resolution_winning_share=1.0`, `direction_resolution_margin=1.0` — all PUT — with `final_direction=CALL`, `direction_resolution_path=DIRECTION_CONFIRMED`, `direction_conflict_status=MITIGATED_REQUIRES_CONFIRMATION`. Same shape on CSCO. `governed_direction_authority=DISCOVERY_GOVERNED` suggests discovery is designed to outrank resolution evidence; if so the label `DIRECTION_CONFIRMED` is misleading. Pre-existing v2 governance, not introduced by DOI-10, but DOI-10 displays it unflagged. |

---

## 5. Result summary

| # | Task | State | Confidence | What would raise it |
|---|---|---|---|---|
| 1 | 235 preserved, 4 overlaid | **VERIFIED** | HIGH | — (reproduced on the artefact) |
| 2 | Canonical DB hash unchanged | **VERIFIED** | HIGH | — |
| 3 | ALL OPPORTUNITIES default; no filter reduces the unfiltered book | **VERIFIED** (D11 latent) | HIGH / MEDIUM for the JS port | Drive the real page in a browser against this run |
| 4 | Empty DOI schema → DATA_UNAVAILABLE, no removed rows, no zero evidence | **VERIFIED** (resolver) / PARTIAL (renderer, D9) | HIGH | A fixture exercising the `NOT_EVALUATED` branches, which never fired here |
| 5 | Governed vs DOI-preferred contract separated, with alignment | **PARTIAL** | HIGH | A run with DOI tables populated so `MATCH`/`DIFFERENT_ADVISORY` actually fire |
| 6 | EIL relabelled as non-authoritative entry telemetry | **REFUTED** | HIGH | — |
| 7 | Interpreter receives the same latest assessment (§17.4) | **VERIFIED** (4 handoff tickers) | HIGH | — |
| 8 | Advisory resolver rejects executable-session requests | **VERIFIED OFFLINE** | HIGH | Wire it into an Interpreter command and capture a refusal in a run artefact |
| 9 | Exact source reconciliation (DOI-10 exit criterion) | **REFUTED** | HIGH | Populate `doi_input_dataset_ids` and `doi_probability_model_id`; fix D1 |
| 10 | Changes no direction/thesis/lifecycle/action/size/capital | **PARTIAL** | HIGH | Add a protected-field guard to `merge_all_opportunities` (D2, D3) |
| — | 115-test DOI regression pack passed | **PARTIAL** (124, all pass) | HIGH / MEDIUM on pack membership | A named manifest defining the pack |

**Headline numbers, as measured:**

- Governed v2 final opportunity book, run `20260909_071646`: **235 = CALL 151 / PUT 84 / OTHER 0** — matches the claim.
- Accepted actionable rows overlaid: **4 = CALL 4 / PUT 0 / OTHER 0** — matches the claim in count; the overlay was exercised on CALL only, which the claim does not disclose.
- Canonical DB sha256 before = after = `0f725c01208a427818ebf49c6f964de12610ed3a21010ddde4081d564629cfdc`.
- DOI regression pack: **124 collected, 124 passed** — the claim says 115.
- Governed contracts contradicting their own trade idea: **11 = CALL 7 / PUT 4**; absent: **24 = CALL 15 / PUT 9**.

No `EXEC-BLOCKED` outcomes: every module exercised was proven free of provider clients before it was run.
No API key value was read or echoed. No production source or existing test was modified. Nothing was committed.

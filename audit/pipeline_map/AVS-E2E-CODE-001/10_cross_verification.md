# 10 — Cross-verification of AVS-E2E-DATA-LOGIC-001 §11

Audit: **AVS-E2E-CODE-001**, lane: data-reconciler (Step 8).

Evidence run: `data/output/runs/20260831_010309/`
Control plane: `data/canonical/control_plane.sqlite` (opened `mode=ro`).

All figures below were reproduced independently from the run artefacts and the
control plane. No pipeline stage was executed. No production file was written.
Every measurement script lives in `audit/pipeline_map/AVS-E2E-CODE-001/measurements/`.

Supporting scripts not tied to a single claim:
`m00_headers.py` (header dump for all eight artefacts, writes `m00_headers.json`),
`m00b_colsearch.py` (column keyword search over that dump),
`m03b_token_scan.py` (locates which columns carry the tokens `THESIS_INVALIDATED`
and `DTE_UNSUITABLE`, so the lifecycle columns were identified rather than guessed).

---

## Verdict table

| id | claim (as stated in §11) | measured value | verdict | script | notes |
|---|---|---|---|---|---|
| 1 | Population flow 1,527 → 1,481 → 1,248 → 1,248 → 1,248 → 31 → 201 → 201; unique tickers equal to rows; duplicates zero in every artefact (§11.1) | Discovery 1,527 rows / 1,527 unique / 0 dup; Vanguard 1,481 / 1,481 / 0; Options 1,248 / 1,248 / 0; Execution 1,248 / 1,248 / 0; EIL 1,248 / 1,248 / 0; Wall Break 31 / 31 / 0; Morning candidates 201 / 201 / 0; Final book 201 / 201 / 0 | CONFIRMED | `m01_population_flow.py` | Ticker column is `ticker` in all eight artefacts. Every artefact is one row per ticker; zero duplicate tickers and zero duplicate rows anywhere. |
| 2 | 111 PUT / 90 CALL in the final 201-row book (§11.2) | `canonical_direction`, `final_direction` and `direction` each give PUT 111 / CALL 90 over 201 rows. 17 direction-ish columns examined. `governed_direction` gives PUT 104 / CALL 77 / STRANGLE 20. | CONFIRMED | `m02_direction_split.py` | Three columns yield exactly 111/90 and agree row-for-row in aggregate. `governed_direction` is a **different** population because it retains 20 `STRANGLE` rows that the canonical/final columns have collapsed to PUT/CALL. `resolved_direction` exists only in `morning_candidates`, not in the book. |
| 3 | 442 Options rows `THESIS_INVALIDATED`, of which 437 PUT and 5 CALL (§11.3) | `remaining_runway_state == THESIS_INVALIDATED`: 442 of 1,248. By `canonical_direction`: PUT 437, CALL 5. Identical split via `final_direction`, `options_direction` and `side`. | CONFIRMED | `m03_thesis_state.py`, `m03b_token_scan.py` | The literal token `THESIS_INVALIDATED` is carried by `remaining_runway_state`. The parallel column `thesis_state` carries the shorter token `INVALIDATED` on the same 442 rows. `governed_direction` splits those 442 as PUT 404 / STRANGLE 33 / CALL 5. |
| 4 | 106 of the 201 final rows blocked, all PUT (§11.3) | `lab_status == BLOCKED`: 106 of 201, `canonical_direction` PUT 106 / CALL 0. `lab_execution_status == BLOCK`: same 106. `remaining_runway_state == THESIS_INVALIDATED` in the book: same 106, all PUT. | CONFIRMED | `m04_blocked_final.py` | The remaining 95 are `MANUAL_REVIEW` 85 (CALL 83 / PUT 2) and `CONTRACT_REPAIR` 10 (CALL 7 / PUT 3). Nine further columns carry the token `BLOCK` on exactly the same 106 rows. |
| 5 | Recomputation with the published governed entry/invalidation produces zero invalidations for those 442 rows (§11.3) | Of 442: as-used predicate reproduces 442/442 invalidated; published `invalidation_spot` differs from `ctx['stop']` on 442/442; **recomputed invalidations with the published value = 0 of 442**. `invalidation_source` on all 442 is `DIRECTION_MIRROR_FROM_STOP_LOSS_V1`. | CONFIRMED | `m05_invalidation_recompute.py` | Fields identified from source, not guessed — see the "Recomputation basis" section below. Discovery join matched all 442 tickers; `underlying_price` agreed with discovery `stock_price` on 442/442, so the current-spot input is unambiguous. |
| 6 | 657 rows `DTE_UNSUITABLE`; 32 when governed 5/10/20-session holds are used (§11.4) | `liquidity_state == DTE_UNSUITABLE`: 657 of 1,248. Published `minimum_required_dte` reproduces `ceil(remaining_hold_sessions + 3 + 5)` on 657/657. Substituting `planned_hold_sessions`: **32 remain unsuitable, 625 clear, 0 unrouted, 0 missing DTE**. Final book: 145 of 201 `DTE_UNSUITABLE`. | CONFIRMED | `m06_dte_recompute.py` | `remaining_hold_sessions` actually used is 20.0 on 623 of the 657; `planned_hold_sessions` is 5.0 on 655 and 10.0 on 2. The 625 figure and the 145 book figure in §11.4 both reproduce exactly. |
| 7 | `trigger_quality` null 201/201 in morning candidates; `trigger_score == 55.0` for 191; EIL distribution 61 STRONG / 92 SINGLE / 48 NONE (§11.2, §11.5) | Morning candidates: `trigger_quality` blank 201/201; `trigger_primary` blank 201/201; `trigger_score == 55.0` on 191 of 201 (remaining 10 are `0.0`); `trigger_count` is `0.0` on 201/201. EIL over the 201 final tickers: STRONG 61, SINGLE 92, NONE 48. EIL over all 1,248 rows: SINGLE 650, NONE 304, STRONG 294. | CONFIRMED | `m07_trigger_fields.py` | Both denominators reported as requested. The 61/92/48 figure is **the 201-ticker subset**, not the full EIL frame. EIL `trigger_score == 55.0` occurs on 0 of the 201, so the `55.0` at the morning boundary does not originate from EIL. `trigger_evidence` and `trigger_state` do not exist in morning candidates; `trigger_evidence` does not exist in EIL. |
| 8 | 191 of 201 with a selected contract; 175 with positive two-sided completed-session quotes (§11.2) | `contract_symbol` populated on 191 of 201; `contract_data_state == AVAILABLE` on the same 191, `NOT_APPLICABLE_NO_SELECTED_CONTRACT` on 10. `contract_bid > 0 AND contract_ask > 0`: 175 of 201, all within the 191. | CONFIRMED | `m08_contract_and_quotes.py` | `selected_quote_timestamp_utc` is blank on 201/201 in the book, so the "completed-session" qualifier is not evidenced *in the book itself*; it is evidenced upstream in `options_intelligence` (see id 10). |
| 9 | WBS: 31 scored, 14 in the intersection with the final 201, 17 removed (§11.2, §11.3, §11.7) | `wall_break_scores`: 31 rows / 31 unique tickers. Intersection with the 201 book tickers: 14. Excluded: 17. Book rows with non-blank `wbs_break_direction`: 14 of 201. `wbs_grade == PROBABLE` on 9 rows; of those, excluded from the book: FORM, HD, SMCI, WHD. | CONFIRMED | `m09_wall_break.py` | Excluded 17: AEM, ARM, ATI, BE, BHP, CCJ, CRCL, FORM, HD, MCD, MTSI, SA, SMCI, SNPS, UUUU, WHD, WK. See the qualification below: 16 of the 17 are `THESIS_INVALIDATED`/PUT, MCD is `THESIS_ACTIVE`/CALL. |
| 10 | Options `asof_date` = 2026-08-31 while selected quote timestamps are 2026-08-28 (§11.8) | `asof_date == '2026-08-31'` on 1,248 of 1,248. `contract_quote_timestamp_utc`, `quote_timestamp_utc` and `quote_as_of` are all `2026-08-28T20:00:00Z` on 927 rows and blank on 321. `contract_quote_timestamp_source == marketdata.app.updated` on the same 927. | CONFIRMED | `m10_temporal_identity.py` | `thesis_id` in the options artefact ends in `2026-08-31` on 937 rows and is blank on 311, i.e. thesis identity carries the run date, not the 2026-08-28 session date. |
| 11 | Macro packet age ≈ 39.8 hours, labelled STALE/PARTIAL (§11.10) | `macro_quant_packet.json`: `macro_age_hours = 39.84`, `macro_freshness_status = 'STALE'`, `macro_data_quality = 'PARTIAL'`, `macro_execution_caution = 'MACRO_STALE_REVIEW_REQUIRED'`. `macro_generated_at_utc = 2026-08-29T08:12:43Z`, `macro_normalised_at_utc = 2026-08-30T23:46:20Z`. | CONFIRMED | `m11_macro_and_manifest.py` | `macro_snapshot.json` gives `as_of_utc = 2026-08-29T08:12:43Z` and `data_coverage_ratio = 0.875`. `run_meta.json` independently records `macro_freshness_status = STALE` and `macro_data_quality = PARTIAL`. |
| 12 | `final_run_manifest.json` mtime versus run close (§11.9) | `final_run_manifest.json` mtime **2026-08-31 10:02:11 local / 09:02:11 UTC**; `run_meta.json` mtime **2026-08-31 02:56:41 local / 01:56:41 UTC**. Delta **25,530 s = 7 h 05 min 30 s**. | CONFIRMED | `m11_macro_and_manifest.py` | The manifest's own `created_at_utc` is `2026-08-31T09:02:11.001221+00:00`, matching its mtime to the second — the file was rewritten, not merely touched. `run_meta.json` declares `status_updated_at_utc = 2026-08-31T01:56:41.487600+00:00` and `run_status = COMPLETED`, matching its own mtime. Every other run artefact checked (`pipeline_integrity_*.json` 02:56:06, final book 02:56:24, morning candidates 02:56:05, all local) sits inside the run window; the manifest alone sits 7 h later. |
| 13 | Control-plane lifecycle tables: counts, distinct `thesis_id`, and whether `thesis_id` embeds the RUN date or the COMPLETED SESSION date (§11.8) | 10 tables. `option_thesis_events` 1,507 rows / 1,030 distinct `thesis_id`; `option_contract_observations` 1,021 rows / 1,014 distinct; `option_contract_selection_events` 1,021 rows / 1,014 distinct. Key form is `TICKER:SIDE:YYYY-MM-DD` where the date is the **run** date. For run `20260831_010309`: 927 observations, `thesis_id` date == `quote_as_of` date on **0**, mismatched on **927**, single pair `('2026-08-31', '2026-08-28')`. | CONFIRMED | `m13_control_plane_db.py` | `FLYW` holds two identities across runs: `FLYW:PUT:2026-08-30` (run `20260830_182402`) and `FLYW:PUT:2026-08-31` (run `20260831_010309`) — the same instrument and side, split by run date. 86 tickers hold more than one `thesis_id`; seven hold three (CART, COR, CPRI, HST, O, PCRX, SBRA). Trailing-date spread across `option_thesis_events`: 2026-08-31 × 1,379, 2026-08-30 × 121, 2026-08-29 × 7. |
| 14 | Whether any supersession/correction column exists on lifecycle events | **None of** `calculation_version`, `supersedes_event_id`, `correction_reason`, `corrected_by_run_id` exists on any of the three tables. No column in any of the three tables holds a value containing `SUPERSED`. Nearest constructs: `option_thesis_events.version` (1 × 1,030, 2 × 476, 3 × 1) and `option_contract_selection_events.selection_version` (1 × 1,014, 2 × 7). | CONFIRMED (as absent) | `m13_control_plane_db.py` | Full column lists reproduced below. `thesis_state` is the only enum-like status column on `option_thesis_events` and its domain is `{ACTIVE, INVALIDATED}` only; `monitor_state` is `{ACTIVE, TERMINAL, NOT_REQUIRED}`. Neither carries a superseded or corrected member. |

**Summary: 14 of 14 CONFIRMED. No NOT_CONFIRMED and no NOT_MEASURABLE items.**

---

## Recomputation basis for id 5 (§11.3)

The claim required substituting the published governed invalidation into the
lifecycle predicate. The exact fields were established from source, read-only,
so no recomputation is fabricated:

- `contracts/options_liquidity_lifecycle.py` L418–431 — the predicate is
  `invalidated = direction * (current_spot - invalidation) <= 0`, with
  `direction = +1.0` for CALL and `-1.0` for PUT; `state = "THESIS_INVALIDATED"`
  when that predicate holds.
- `scripts/avshunter_options_intelligence.py` L4549 — the lifecycle is called with
  `invalidation_spot = _repair_alt_float(ctx.get("stop"))`, i.e. the raw stop.
- `scripts/avshunter_options_intelligence.py` L4580–4581 — `thesis_spot` and
  `current_spot` are both `ctx['spot']` at that call site.
- `scripts/avshunter_options_intelligence.py` L4085–4102 — the **published**
  `invalidation_spot` is the raw stop when it is already correctly sided,
  otherwise it is mirrored about entry
  (`invalidation_source = DIRECTION_MIRROR_FROM_STOP_LOSS_V1`), otherwise `None`
  (`MISSING_AUTHORITATIVE_STOP`).
- `scripts/avshunter_options_intelligence.py` L3801–3808, L4016 —
  `spot = stock_price`, `entry = entry_price` (defaulting to spot),
  `stop = stop_loss` when `> 0` else `entry * 0.97`.

`ctx['spot']`, `ctx['entry']` and `ctx['stop']` are not columns of
`options_intelligence_*.csv`; they were recovered from
`discovery_candidates_ultimate_*.csv` (`stock_price`, `entry_price`, `stop_loss`),
which is the frame the options stage reads. The join matched all 442 tickers, and
the published `underlying_price` agreed with the discovery `stock_price` on all 442,
so the current-spot input used in the recomputation is not in doubt.

Result: the as-used predicate reproduces all 442 invalidations exactly; the same
predicate with the published governed `invalidation_spot` produces 0 of 442.
`invalidation_source` is `DIRECTION_MIRROR_FROM_STOP_LOSS_V1` on all 442, i.e.
every one of them is a row where the raw stop was wrongly sided for its direction.
Across all 1,248 options rows, `invalidation_source` is `stop_loss` on 492,
`DIRECTION_MIRROR_FROM_STOP_LOSS_V1` on 447 and `MISSING_AUTHORITATIVE_STOP` on 309.

## Recomputation basis for id 6 (§11.4)

- `contracts/options_liquidity_lifecycle.py` L36–37 —
  `DEFAULT_MONITOR_SESSIONS = 3`, `DEFAULT_EXIT_BUFFER_SESSIONS = 5`.
- `contracts/options_liquidity_lifecycle.py` L107 —
  `minimum_required_dte = ceil(remaining_hold_sessions + monitor + exit_buffer)`.
- `contracts/options_liquidity_lifecycle.py` L292–299 — `DTE_UNSUITABLE` when
  `dte < minimum_required_dte`; this test precedes the moneyness and spread tests.
- `scripts/avshunter_options_intelligence.py` L3832, L3926 —
  `hold_days = layer2__recommended_hold_days` when `> 0`.
- `scripts/avshunter_options_intelligence.py` L4546 —
  `remaining_hold_sessions = ctx['hold_days']`.
- `scripts/avshunter_options_intelligence.py` L4104–4112 —
  `planned_hold_sessions` is 5, 10 or 20 from `horizon_bucket`, else `None`.

The published `minimum_required_dte` reproduces `ceil(remaining_hold_sessions + 8)`
on 657 of 657 rows, which validates the reconstruction before substitution.
Substituting `planned_hold_sessions` for `remaining_hold_sessions` and holding the
published contract `dte` constant leaves 32 rows unsuitable.

---

## Qualifications on otherwise-confirmed items

These are recorded for precision. None of them changes a verdict, because in each
case the numeric claim itself reproduced exactly.

### id 2 — the book carries three direction columns, and a fourth that disagrees

`canonical_direction`, `final_direction` and `direction` all give 111/90.
`governed_direction` gives PUT 104 / CALL 77 / **STRANGLE 20**, and
`governed_direction_basis` shows those 20 as `precor_intent=TRANSITION, trend=MIXED`.
§11.2 states one figure without naming a column; the figure is correct for the
three columns that reduce to a two-sided contract type, and does not hold for
`governed_direction`.

### id 3 — the label in §11.3 is a value of `remaining_runway_state`, not `thesis_state`

§11.3 says "442 Options rows classified `THESIS_INVALIDATED`". The token
`THESIS_INVALIDATED` is a value of `remaining_runway_state`. `thesis_state` holds
the value `INVALIDATED` on the identical 442 rows. Both reproduce the claim.

### id 8 — "completed-session" is not evidenced inside the book

The book's `selected_quote_timestamp_utc` is blank on 201 of 201 rows, so the
qualifier "completed-session" in §11.2 cannot be verified from the book alone.
It is verifiable one stage upstream: `options_intelligence_*.csv` carries
`quote_as_of = 2026-08-28T20:00:00Z` on all 927 rows that have a quote. The counts
191 and 175 themselves reproduce exactly from the book.

### id 9 — 16 of the 17 excluded Wall Break rows, not 17, sit on invalidated theses

§11.3 attributes the removal of "17 of the 31 Wall Break rows" to the invalidation
defect. The intersection (14) and the exclusion count (17) are exact. Checking the
options lifecycle state of the 17 excluded tickers: 16 are
`remaining_runway_state == THESIS_INVALIDATED` with `canonical_direction == PUT`;
the seventeenth, **MCD**, is `THESIS_ACTIVE` with `canonical_direction == CALL`
and therefore left the book for some other reason. The named `PROBABLE` exclusions
(WHD, HD, SMCI, FORM) are all in the invalidated 16.

### id 13 — the temporal mismatch is total, not partial

For run `20260831_010309` there is no run in which the two dates agree: 927 of 927
observations carry `thesis_id` date `2026-08-31` against `quote_as_of` date
`2026-08-28`. The consequence §11.8 predicts is already present in the store — 86
tickers hold more than one `thesis_id`, seven of them three, and `FLYW:PUT` exists
under both `2026-08-30` and `2026-08-31`.

### id 14 — full column lists

`option_thesis_events` (16): `event_id`, `event_key`, `thesis_id`, `run_id`,
`ticker`, `direction`, `thesis_state`, `monitor_state`, `reason_code`,
`structural_target`, `invalidation_spot`, `horizon_end_date`, `version`,
`recorded_at`, `metadata_json`, `payload_hash`.

`option_contract_observations` (34): `observation_id`, `thesis_id`, `run_id`,
`ticker`, `contract_symbol`, `option_side`, `quote_as_of`, `observed_at`,
`source_provider`, `source_dataset_id`, `spot`, `strike`, `expiration`, `dte`,
`delta`, `bid`, `ask`, `bid_size`, `ask_size`, `spread_pct`, `volume`,
`open_interest`, `iv`, `liquidity_state`, `maturation_score_1d`,
`maturation_score_2d`, `maturation_score_3d`, `maturation_score_is_probability`,
`maturation_probability_1d`, `maturation_probability_2d`,
`maturation_probability_3d`, `atm_distance_sigma`, `remaining_runway_pct`,
`payload_hash`.

`option_contract_selection_events` (13): `selection_event_id`, `event_key`,
`thesis_id`, `run_id`, `previous_contract_symbol`, `selected_contract_symbol`,
`selected_observation_id`, `selection_reason`, `selection_version`,
`economics_recomputed`, `selected_at`, `metadata_json`, `payload_hash`.

Full table inventory of `control_plane.sqlite`: `api_request_ledger` (10,964),
`dataset_registry` (4,834), `option_contract_observations` (1,021),
`option_contract_selection_events` (1,021), `option_thesis_events` (1,507),
`run_registry` (14), `schema_metadata` (2), `sqlite_sequence` (1),
`stage_worklist` (37,838), `ticker_lifecycle` (108,588).

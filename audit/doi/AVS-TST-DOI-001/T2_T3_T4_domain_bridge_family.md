# T2 / T3 / T4 — Domain contracts, observation bridge, family generator

Combined because the three tracks share one probe set. Interpreter for all
execution: `venv\Scripts\python.exe` (3.13.14).

Probes written for these tracks:

| Probe | Purpose |
|---|---|
| `tests/probe_t2_append_only.py` | schema/trigger census, restart re-entrancy, identity key |
| `tests/probe_t2b_trigger_fires.py` | proves the append-only triggers actually FIRE |
| `tests/test_avs_tst_doi_001_adversarial_family.py` | 8 adversarial DOI-3/DOI-4 fixtures |

---

# T2 — Domain contracts, vocabulary and persistence (invariants 11–12)

## T2.1 Vocabularies exist as their own enums and are not folded into `eil_v3_verdict`

**Contract-entry states — 9 of 9, exact.** `domain/dynamic_options_intelligence.py:30–39`
(`class ContractEntryState`) carries every §8.2 member verbatim:
`CONTRACT_MONITOR`, `CONTRACT_LIQUIDITY_DEVELOPING`, `CONTRACT_ENTRY_ACCEPTABLE`,
`CONTRACT_LIMIT_PRICE_REQUIRED`, `CONTRACT_REPAIR_REQUIRED`,
`CONTRACT_DATA_INSUFFICIENT`, `CONTRACT_DEGRADED`, `CONTRACT_SUPERSEDED`,
`CONTRACT_EXPIRED`.

**Thesis states — 7 of 8.** `domain/dynamic_options_lifecycle.py:44–51`
(`class DOIThesisConditionState`):

| §8.1 requires | Implementation | Note |
|---|---|---|
| `THESIS_DEVELOPING` | `THESIS_DEVELOPING` | exact |
| `THESIS_ACTIVE` | — | **absent** |
| `THESIS_VALIDATED` | `THESIS_CONFIRMED` | renamed |
| `THESIS_CONDITION_BREACHED` | `THESIS_CONDITION_BREACHED` | exact |
| `THESIS_RECOVERING` | `THESIS_RECOVERING` | exact |
| `TARGET_TOUCHED` | `TARGET_TOUCHED` | exact |
| `HORIZON_ELAPSED_REASSESS` | `HORIZON_ELAPSED_REASSESS` | exact |
| `THESIS_DATA_INSUFFICIENT` | `DATA_INSUFFICIENT` | renamed |

The two states whose naming the design most cared about —
`THESIS_CONDITION_BREACHED` (not "invalidated") and `HORIZON_ELAPSED_REASSESS`
(not "expired") — are present verbatim, and `THESIS_RECOVERING` exists with a
real transition at `domain/dynamic_options_lifecycle.py:409`. The gaps are
cosmetic. Raised as **DOI-D09** (`DOC`, P3).

**Not folded into `eil_v3_verdict`:** no DOI state string is ever assigned to
`eil_v3_verdict`. The legacy enum is written only by the EIL runner. §8.2's
prohibition is honoured.

**Result: `VERIFIED OFFLINE`.** Confidence HIGH.

## T2.2 `ContractCandidate` identity and append-only persistence (invariant 12)

The natural key on `doi_contract_assessments` is
`UNIQUE(family_id, contract_symbol, observation_id, calculation_version)`.
`family_id` binds to `thesis_id`, so the design's
`thesis_id + OCC + observation_dataset_id` triple is present under the field
name `observation_id` rather than `observation_dataset_id`. Equivalent, renamed.
A later observation of the same OCC carries a different `observation_id` and is
therefore a **new row**, exactly as §7.2 requires.

### Append-only is enforced in the database, and the triggers fire

`canonical_data/option_liquidity_lifecycle.py:622–698` installs a
`BEFORE UPDATE` and a `BEFORE DELETE` trigger on every DOI and legacy lifecycle
table, each `SELECT RAISE(ABORT, '<table> are append-only')`. Sixteen triggers,
eight tables.

Trigger *existence* proves nothing on an empty table — a `BEFORE` trigger never
runs if no row matches. `probe_t2b_trigger_fires.py` therefore seeds a row and
attempts a real mutation:

```
table                                seeded  UPDATE                     DELETE                     row kept
doi_contract_families                yes     blocked                    blocked                    yes
doi_contract_assessments             yes     blocked                    blocked                    yes
doi_lifecycle_events                 yes     blocked                    blocked                    yes
option_thesis_events                 yes     blocked                    blocked                    yes
option_contract_selection_events     yes     blocked                    blocked                    yes
doi_preferred_contract_decisions     no      -                          -                          (CHECK constraints blocked my seeder)
doi_outcome_labels                   no      -                          -                          (CHECK constraints blocked my seeder)
option_contract_observations         no      -                          -                          (CHECK constraints blocked my seeder)

append-only breaches: 0    RESULT: PASS
```

Five tables proven append-only **by execution**; three unproven by this probe
because my crude seeder could not satisfy their `CHECK` constraints — their
triggers exist and are identical in form. Zero breaches.

This is stronger than an application-level guard: SQL triggers cannot be
bypassed by any code path, including a future one.

**Result: invariant 12 `VERIFIED OFFLINE`.** Confidence HIGH.

## T2.3 Restart idempotency

`probe_t2_append_only.py` re-instantiates the store against the same file and
calls `initialise()` again:

```
[PASS] restart initialise()          no exception, schema re-entrant
[PASS] schema stable across restart  tables 16->16, triggers 16->16
```

All DDL is `CREATE TABLE IF NOT EXISTS` / `CREATE TRIGGER IF NOT EXISTS`, so a
restart is a no-op. **`VERIFIED OFFLINE`.** Confidence HIGH.

## T2.4 No second raw-data store (DOI-2.3)

The nine DOI tables (`doi_contract_families`, `doi_contract_assessments`,
`doi_preferred_contract_decisions`, `doi_family_rankings`,
`doi_lifecycle_events`, `doi_outcome_labels`, `doi_probability_inferences`,
`doi_probability_models`, `doi_ranking_policies`) are all created inside the
**existing** control plane alongside `option_contract_observations`. No new
database file, no new raw option-observation table. **`VERIFIED OFFLINE`.**
Confidence HIGH.

## T2.5 Dataset IDs and evidence cutoffs (invariant 11)

`doi_contract_families` declares `thesis_evidence_cutoff_utc TEXT NOT NULL`,
`evidence_cutoff_utc TEXT NOT NULL` and
`source_dataset_ids_json TEXT NOT NULL DEFAULT '[]'`. `NOT NULL` on both
cutoffs means an assessment cannot be persisted without them.

**Caveat I must state:** `source_dataset_ids_json` defaults to `'[]'`, so a
family could satisfy `NOT NULL` with an *empty* dataset-ID list. The column is
non-null; its contents are not constrained to be non-empty. I could not sample
five persisted assessments because **no DOI row exists anywhere** — the live
control plane has no DOI tables. Tracing five real assessments is
**`NOT TESTABLE` until the first evening run persists them.**

**Result: invariant 11 `PARTIAL`.** Schema binds the fields; content
unverifiable. Confidence MEDIUM.

---

# T3 — Observation bridge and reuse-first (invariant 13, §9.1–9.3)

## T3.1 Reuse-first / fetch-missing-only

Decision point: `domain/dynamic_options_intelligence.py:81–126`, analysed in
full in `T1_authority.md` §T1.6. Canonical evidence available ⇒
`REUSE_CANONICAL_EVIDENCE`, no fetch. A second call for an identical scope
cannot fetch twice: `canonical_data/dynamic_options_bridge.py:587` guards on
`key not in self._acquisition_attempts` and the key includes the scope
fingerprint, the cutoff and the manual-refresh flag (`:580–584`). A repeat
resolves to `ACQUISITION_ALREADY_ATTEMPTED` (`:634`).

**Prior finding (unstable `scope_fingerprint`, NULL `expires_at`):** the DOI
bridge builds its own composite key rather than inheriting the old cache
identity, and `physical_fetch_count` is computed conservatively — an unknown
resolution is counted as a fetch (`:597–600`). DOI did not inherit the defect.

**Result: `VERIFIED OFFLINE`.** Confidence HIGH.

## T3.2 Phantom receives dataset IDs and does not refetch

Static: the DOI transitive import closure (see `T11_production.md`) contains no
provider client and no network library. Phantom cannot refetch through DOI.
**`VERIFIED OFFLINE`.** Confidence MEDIUM — I proved DOI cannot fetch; I did
not audit Phantom's own code path.

## T3.3 PCR is scoped, never a single-contract attribute

`canonical_data/dynamic_options_bridge.py:272–295` computes PCR over
`expiry_frame` (expiry-scoped), `near_frame` (near-the-money band via
`near_money_pct`) and `target_frame` (target region via `target_region_pct`),
plus a delta-bucket scope keyed on `selected_abs_delta`. Four scopes, none of
them per-contract. **`VERIFIED OFFLINE`.** Confidence HIGH.

## T3.4 No claimed signed order flow

No producer of "order flow", "flow imbalance" or "premium flow" exists in any
DOI module. §9.3 permits premium-flow imbalance only "when actual prints
support it"; the implementation simply omits it. More conservative than the
design. **`VERIFIED OFFLINE`.** Confidence HIGH.

## T3.5 Null versus zero (invariant 7) — probe result

My fixture `test_t3_5_all_null_quote_is_data_insufficient_not_economic_zero`
builds two contracts with `bid=None, ask=None, volume=None, open_interest=None`
and asserts on the persisted audit:

```
state                 == MONITOR_NO_QUOTE      (not EXCLUDED_STRUCTURAL)
bid, ask, volume, open_interest  are all still None, and none equals 0.0
monitor_reasons contains CURRENT_QUOTE_MISSING, OPEN_INTEREST_MISSING, VOLUME_MISSING
summary: source_observations=2, family_candidates=2, structural_exclusions=0
```

**PASSES.** Nulls survive as nulls, the reason is disclosed, and the ticker
keeps both candidates. The generator source confirms it: `open_interest is None`
→ `OPEN_INTEREST_MISSING`, `elif open_interest < 50` → `LOW_OPEN_INTEREST`
(`canonical_data/dynamic_options_family.py:359–367`) — missing and low are kept
distinct.

### Four null-to-zero coercions found in the DOI path

| Location | Expression | Assessment |
|---|---|---|
| `domain/dynamic_options_lifecycle.py:354–355` | `previous.volume or 0.0`, `current.volume or 0.0` | Material-trigger comparison only. Effect is to fire *more* re-evaluation. Advisory. **DOI-D10** (`NULL`, P3) |
| `canonical_data/dynamic_options_bridge.py:280` | `abs(_number(delta) or 0.0)` | Missing delta buckets as 0 for a PCR *scope*, not an economic value. **DOI-D11** (`NULL`, P3) |
| `canonical_data/dynamic_options_production.py:227` | `dividend_yield ... or 0.0` | A genuine economic input to Black–Scholes with no "dividend unknown" quality flag. Conventional but against §5.2's letter. **DOI-D12** (`NULL`, P2) |
| `canonical_data/dynamic_options_probability.py:105` | `bid_size or 0.0`, `ask_size or 0.0` | Feature construction. **DOI-D13** (`NULL`, P3) |

Not a defect, and worth naming as good practice:
`domain/dynamic_options_ranking.py:407` sorts with
`key=(row[1] is None, -(row[1] or 0.0), symbol)` — the `is None` term orders
missing values last, so the `or 0.0` never influences the ordering of present
values.

Also noted: `canonical_data/dynamic_options_family.py:437` counts
`open_interest is None or open_interest < 50` as `retained_low_open_interest`,
merging "missing" into "low" **in the §18 diagnostic only**. The per-contract
audit keeps them separate. **DOI-D14** (`DOC`, P3).

**Result: invariant 7 `VERIFIED OFFLINE` in the family generator; `PARTIAL`
overall** because of the dividend default. Confidence HIGH.

---

# T4 — Contract-family generator (§10, invariants 8, 14)

All results below are from my own fixtures in
`tests/test_avs_tst_doi_001_adversarial_family.py`:

```
venv\Scripts\python.exe -m pytest -q ^
  audit\doi\AVS-TST-DOI-001\tests\test_avs_tst_doi_001_adversarial_family.py ^
  -k "t3_5 or t4_1 or t4_2 or t4_3 or t4_4 or t4_6"

8 passed, 14 deselected, 2 subtests passed in 9.74s
```

## T4.1 Only long single-leg contracts of the governed side (invariant 14)

`test_t4_1_put_thesis_admits_no_call_contract`: a PUT thesis fed two PUTs and
two CALLs admits `{PUT}` only; both CALLs are excluded with
`WRONG_OPTION_SIDE`, remain in the audit, and carry `display_eligible=False`.
`test_t4_1_call_thesis_admits_no_put_contract` is the mirror.

No multi-leg constructor exists anywhere in the DOI package.

**Result: invariant 14 `VERIFIED OFFLINE`.** CALL and PUT both exercised.
Confidence HIGH.

## T4.2 Only the six structural exclusions — the δ 0.40–0.60 reversal

The generator's exclusion vocabulary
(`domain/contract_family_generation.py:33–42`) is nine enum members mapping to
the design's six:

| §10 exclusion | Enum member(s) |
|---|---|
| wrong option side | `WRONG_OPTION_SIDE` |
| expired contract | `EXPIRED_CONTRACT` |
| invalid OCC identity | `INVALID_OCC_IDENTITY`, `IDENTITY_FIELD_MISMATCH` |
| DTE cannot outlive hold + buffer | `INSUFFICIENT_SESSION_RUNWAY` |
| negative or crossed quote | `NEGATIVE_QUOTE`, `CROSSED_QUOTE` |
| impossible strike/expiry | `IMPOSSIBLE_STRIKE_OR_EXPIRY`, `DUPLICATE_CONTRACT_AMBIGUOUS` |

**There is no delta band, no OI floor, no spread cap, no volume floor, and no
IV-percentile gate in the exclusion set.** The two extra members are
identity-integrity variants, not market-condition gates. The δ 0.40–0.60
single-contract preselection that cost roughly 121 tickers per run is genuinely
gone from the DOI generator.

`test_t4_2_low_oi_zero_volume_wide_spread_are_never_structural_exclusions`
feeds five contracts — zero OI, OI=1, a 99% spread, unknown OI/volume, a penny
deep-OTM strike — and asserts `structural_exclusions == 0` and
`family_candidates == 5`. **PASSES.** They are counted as retentions
(`retained_zero_volume`, `retained_low_open_interest`) per §18.

**Result: §10 compliance `VERIFIED OFFLINE`.** Confidence HIGH. This is the
single most important positive finding in the audit.

## T4.3 Wholly unusable chain leaves the ticker visible

`test_t4_3_wholly_unusable_chain_leaves_ticker_visible_with_zero_eligible`:
two expired contracts plus one crossed quote gives
`family_candidates == 0`, `structural_exclusions == 3`, `len(taxonomy) == 3`
with reasons, `display_symbols == ()`, and the family row still persisted.
The ticker survives with zero eligible contracts, exactly as §10 requires.
**PASSES. `VERIFIED OFFLINE`.** Confidence HIGH.

## T4.4 One-sided quotes monitorable but never entry-acceptable

`test_t4_4_one_sided_quote_is_monitorable_but_never_entry_acceptable`: bid-only
and ask-only contracts land in `MONITOR_ONE_SIDED`, stay family candidates,
carry `ONE_SIDED_QUOTE`, and are never `ELIGIBLE_TWO_SIDED`. The two-sided
control is. **PASSES. `VERIFIED OFFLINE`.** Confidence HIGH.

## T4.5 Family diversity and the 12-contract bound

`canonical_data/dynamic_options_family.py:132–160` (`_bounded_display`)
stratifies by `(quote_state, moneyness_bucket, expiry_bucket,
target_reachability)` — precisely the four §10 diversity axes — takes one
representative per stratum first, then fills. It is deterministic:
`sorted(candidates, key=_display_key)` then `for key in sorted(groups)`, no set
or dict iteration order anywhere.

Crucially it is a **selection, not a deletion**: `GeneratedContractFamily.__post_init__`
raises unless `set(display_symbols).issubset(admitted)` and the family's
`candidate_symbols` reconcile to the complete admitted taxonomy
(`domain/contract_family_generation.py:154–163`), and
`ContractFamilyGenerationSummary.__post_init__` raises if
`displayed_candidates > family_candidates` (`:129–130`). The full taxonomy is
persisted before the bound is applied.

**Result: DOI-11's "at most 12 per family, deterministic and diversified,
display subset not a deletion" `VERIFIED OFFLINE`.** Confidence HIGH.

## T4.6 DTE outlives hold, on the exchange calendar (invariant 9)

`canonical_data/dynamic_options_family.py:344–348`:

```python
remaining = xnys_sessions_between(session_date, expiry) if expiry else None
required_sessions = thesis.planned_hold_sessions + self.expiry_buffer_sessions   # :285
if remaining is not None and remaining < required_sessions:
    exclusions.append(StructuralExclusionReason.INSUFFICIENT_SESSION_RUNWAY)
```

Both operands are **session counts**. There is no `dte - planned_hold_sessions`
anywhere in the generator. `xnys_sessions_between` comes from
`canonical_data/session_clock.py`, a **tracked, pre-existing** 202-line real
XNYS calendar with Good Friday (`:81`), Thanksgiving (`:85`), Juneteenth
(`:89`), observed-date rules and DST via `zoneinfo` — not an approximation
constant.

My fixtures:

- `test_t4_6_session_runway_uses_exchange_calendar_over_a_holiday` asserts that
  the 10 calendar days from 2026-11-20 across Thanksgiving contain **fewer than
  10 sessions**, that Thanksgiving is not a session, and that Christmas Day
  2026 is not a session. **PASSES.**
- `test_t4_6_insufficient_runway_is_computed_in_sessions_not_days` asserts the
  near-expiry contract is excluded with `INSUFFICIENT_SESSION_RUNWAY`, the
  far-expiry one is not, and `remaining_sessions` equals
  `xnys_sessions_between(...)` and is **strictly less than** the calendar-day
  difference. **PASSES.**

**Result: invariant 9 `VERIFIED OFFLINE` inside DOI-4 and DOI-5.**
Confidence HIGH.

**Important scope limit.** The independent T5 verifier found the prohibited
arithmetic *outside* the DOI package, in three pre-existing modules. See
`T5_valuation.md` and defects **DOI-D15**, **DOI-D16**, **DOI-D17**. Invariant
9 holds for DOI's own code and is **REFUTED for the wider pipeline**.

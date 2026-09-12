# T11 — Production wiring and acceptance control (DOI-11), offline only

The orchestrator was **not** executed. Everything below is static analysis, a
read-only release assessor run against an isolated copy, and an AST-level
import-graph probe. Interpreter: `venv\Scripts\python.exe` (3.13.14).

---

## T11.1 The DOI call site and its order

**One call site.** `intelligent_orchestrator.py:4828`:

```python
if not run_dynamic_options_intelligence(canonical_run_id):
    logger.warning(
        "DOI-11 advisory integration unavailable; pipeline membership is "
        "preserved and the Lab will disclose DATA_UNAVAILABLE"
    )
```

Order, with line numbers:

| Lines | Stage |
|---|---|
| 4813–4820 | `patch_horizon_fields_into_csv(...)` — **governed horizon propagation** |
| **4828** | **`run_dynamic_options_intelligence(canonical_run_id)`** |
| 4838 | `run_ev3_governed_shadow(...)` — first downstream overlay |
| 4839 | `run_ev3_authority_overlay(...)` |

DOI sits after governed horizon propagation and before downstream overlays,
exactly as the DOI-11 status paragraph claims.

**Failure is non-fatal and non-reducing.** The function returns `False` on any
exception (`:2800–2803`, comment: *"DOI owns no trade authority. Infrastructure
failure remains visible but cannot remove an otherwise governed pipeline
opportunity."*), and the caller only logs a warning.

**The runtime contract is enforced in code, not just declared in JSON**
(`:2776–2781`):

```python
if runtime.get("enabled") is not True:              -> skip, return True
if runtime.get("provider_fetch_allowed") is not False \
   or runtime.get("canonical_reuse_only") is not True:
    logger.error("DOI-11 refuses runtime configuration with provider acquisition authority")
    return False
```

A tampered `config/doi_runtime.json` that grants provider access causes DOI to
refuse to run rather than to run with provider access.

**Result: `VERIFIED OFFLINE`.** Confidence HIGH.

## T11.2 No provider client importable from the DOI package

Probe: `tests/probe_t11_import_graph.py`. It parses the AST of all 18 DOI
modules (no execution, so nothing can reach a network), follows first-party
imports transitively, and matches every module in the closure against provider
and network token lists.

```
venv\Scripts\python.exe audit\doi\AVS-TST-DOI-001\tests\probe_t11_import_graph.py

first-party modules in the DOI transitive closure: 29
external / stdlib roots reached: 20
  __future__, collections, contextlib, dataclasses, datetime, enum, hashlib,
  itertools, json, math, numpy, pandas, pathlib, re, sklearn, sqlite3,
  statistics, types, typing, zoneinfo

--- provider-client check ---
  none: no provider client and no network library is importable
  from the DOI package, transitively.

RESULT: PASS
```

Checked for: polygon, marketdata, market_data, fred, tastytrade, anthropic,
openai, alpaca, tradier, iex, quandl; and requests, httpx, urllib, aiohttp,
socket, websocket, http.client. **Zero hits.** The 29-module closure is
entirely `domain/`, `canonical_data/` and `contracts/`; the external surface is
stdlib plus numpy, pandas, sklearn and zoneinfo.

This is the strongest form of the claim: a provider call is not merely absent,
it is **unreachable by import**. **`VERIFIED OFFLINE`.** Confidence HIGH.

## T11.3 Ticker-level data exceptions are retained

`canonical_data/dynamic_options_production.py:253–259`:

```python
except Exception as error:  # ticker exception boundary is intentional
    states["DATA_EXCEPTION_RETAINED"] += 1
    exceptions.append({
        "ticker": ticker, "error_type": type(error).__name__,
        "reason": str(error), "retained": True,
    })
```

Every non-happy path in the loop is a `continue` that increments a **state
counter**, never a removal:

| State | Trigger |
|---|---|
| `NOT_APPLICABLE_NON_DIRECTIONAL` | direction not in {CALL, PUT} (`:150–152`) |
| `FAMILY_DATA_INSUFFICIENT` | no observation or empty family (`:221–222`) |
| `FAMILY_NOT_VALUED_RATE_UNAVAILABLE` | risk-free rate missing/implausible (`:224–226`) |
| `RANKED_DETERMINISTIC` | success (`:252`) |
| `DATA_EXCEPTION_RETAINED` | any exception (`:254`) |

And the population is asserted, not merely reported —
`DOIProductionSummary.__post_init__` (`:102–106`):

```python
if self.retained_opportunities != self.unique_tickers or self.deleted_opportunities:
    raise ValueError("DOI production integration must preserve every opportunity")
if self.physical_fetch_count:
    raise ValueError("DOI production integration is canonical-reuse-only")
```

`retained_opportunities` is set to `len(frame)` unconditionally (`:266`), so the
summary cannot be constructed at all if anything was dropped.

**Note on three-direction coverage.** An `OTHER`-bucket thesis (UNRESOLVED,
STRANGLE, non-directional) is counted `NOT_APPLICABLE_NON_DIRECTIONAL` and
retained, but **receives no DOI family**. DOI coverage is CALL/PUT only, by
construction — `doi_contract_families` has
`CHECK(governed_direction IN ('CALL','PUT'))`. That is correct per §Scope
("Long single-leg CALL and PUT opportunities") and is not a defect, but it
means every DOI coverage number in this audit is structurally OTHER = 0.

**Result: `VERIFIED OFFLINE`.** Confidence HIGH.

## T11.4 The 12-contract bound is deterministic and diversified

Covered in `T2_T3_T4_domain_bridge_family.md` §T4.5.
`canonical_data/dynamic_options_family.py:132–160` stratifies on the four §10
diversity axes, uses `sorted()` twice with no set/dict iteration, and the
complete taxonomy is persisted before the bound is applied. Reconciliation
guards raise if the display set is not a subset of the admitted family.
**`VERIFIED OFFLINE`.** Confidence HIGH.

## T11.5 The read-only assessor refuses to promote a pre-DOI run

Built an isolated scratch root at
`audit/doi/AVS-TST-DOI-001/scratch/root/` containing my DB copy, a copy of
`config/doi_runtime.json` and copies of the run's `options/`,
`intelligence_lab/` and `morning_validation/` directories. The assessor opens
the database as `file:...?mode=ro` (`tools/doi11_production_readiness.py:101`)
and writes nothing unless `--output` is passed, which I did not pass.

```
venv\Scripts\python.exe tools\doi11_production_readiness.py ^
  --run-id 20260909_071646 ^
  --project-root audit\doi\AVS-TST-DOI-001\scratch\root
```

```json
{
  "status": "NOT_READY",
  "decision_authority": "NONE",
  "execution_authority": "HUMAN_ONLY",
  "checks": [
    {"name": "governed_runtime",          "status": "PASS",    "detail": "active, reuse-only, provider-free and advisory"},
    {"name": "completed_session_report",  "status": "AWAITING","detail": "no DOI-11 report for run 20260909_071646"},
    {"name": "canonical_persistence",     "status": "AWAITING","detail": "doi_contract_assessments,doi_contract_families,doi_family_rankings,doi_lifecycle_events,doi_preferred_contract_decisions"},
    {"name": "authority_separation",      "status": "AWAITING","detail": "violations=0"},
    {"name": "lab_projection",            "status": "FAIL",    "detail": "base_schema=lab_signal_book_v2 candidate_count=235 rows=235 doi_advisory_rows=0"},
    {"name": "morning_cycle",             "status": "PASS",    "detail": "...morning_validated_trades_20260909_071646.csv"}
  ]
}
```

**It refuses, and for the right reasons** — no DOI report for the run, the five
required DOI tables absent, zero DOI advisory rows in the Lab book. It does not
return a right answer for a wrong reason.

Incidental corroboration: the assessor independently measures the governed
population at **235** rows, matching my own count and the T10 reconciliation.

**Result: `VERIFIED`** — real run artefact plus source evidence. Confidence HIGH.

### One weakness in the assessor worth recording

`authority_separation` reports `AWAITING` rather than `FAIL` whenever the DOI
tables are missing, because `tables_ok` gates it
(`tools/doi11_production_readiness.py:141–144`). That is right here, but it
means the authority check is dormant until tables exist, and a
`sqlite3.Error` from a schema drift is caught at `:133–134` and converted into
`DATABASE_ERROR:...` in `missing_tables`, which again yields `AWAITING`, not
`FAIL`. The authority gate can never report a failure caused by a schema
problem. Raised as **DOI-D20** (`TEST`, P3).

## T11.6 Rollback point

| File | sha256 | Size |
|---|---|---|
| `data/canonical/control_plane.sqlite` (live) | `0f725c01…29cfdc` | 129,794,048 |
| `backups/doi_phase11_20260910/control_plane.pre_doi11.sqlite` | `0f725c01…29cfdc` | 129,794,048 |
| `backups/doi_phase1_20260910/control_plane.pre_doi2.sqlite` | `0f725c01…29cfdc` | 129,794,048 |

All three **byte-identical**. The rollback point is genuinely pre-DOI (it
contains no DOI tables), it is retained, and — because DOI has written nothing —
a rollback today is a no-op.

A documented rollback *procedure* exists only as the one-line statement in
`audit/doi/DOI_PHASE11_IMPLEMENTATION_20260910.md:29–30` naming the file. There
is no restore command, no verification step and no statement of what else must
be reverted (the DOI code is untracked, so a code rollback has no git handle —
see **DOI-D01**). Raised as **DOI-D21** (`DOC`, P2).

**Result: `PARTIAL`.** Rollback point `VERIFIED`; rollback procedure
inadequate. Confidence HIGH.

## T11.7 Release diagnostics (§18) — every aggregate must have a producer

`DOIProductionSummary` (`canonical_data/dynamic_options_production.py:88–120`)
against the §18 list:

| §18 diagnostic | Producer | Status |
|---|---|---|
| thesis count entering DOI | `input_rows`, `unique_tickers` | real |
| families generated | `family_rows` | real |
| candidates evaluated per family | `family_candidates_total`, `bounded_candidates_total` | real |
| current entry-state distribution | `counts_by_state` | real |
| contracts retained despite low OI / zero volume | `retained_low_open_interest`, `retained_zero_volume` | real |
| data-insufficient reasons | `counts_by_state`, `exceptions` | real |
| family switches and hysteresis suppressions | — | **absent from the summary** |
| probability model coverage and OOD count | — | **absent from the summary** |
| canonical reuse vs provider-call count | `canonical_reuse` real; `physical_fetch_count` **hard-coded `0`** | see below |
| reconciliation: input theses = assessed + explicitly failed | `retained_opportunities == unique_tickers` asserted | real |
| CALL/PUT distribution | — | **absent from the summary** |

Three of eleven §18 aggregates have no producer in the release summary, and
CALL/PUT distribution — the prompt's three-direction discipline — is one of
them. Raised as **DOI-D22** (`DOC`, P2).

### `physical_fetch_count` is a literal, but the guarantee is real

`:270` passes `physical_fetch_count=0` as a constant, ignoring the genuine
per-observation counter that the bridge computes at
`canonical_data/dynamic_options_bridge.py:585–600`. As a §18 diagnostic it is
vacuous — it would report 0 whatever happened.

I must be fair about what that does and does not mean. The no-fetch guarantee
is enforced **three** independent ways:

1. the production service passes `acquire_missing=None` (`:205`), and the
   bridge's fetch branch requires `acquire_missing is not None` (`:587`), so the
   branch is unreachable;
2. `:207–208` raises `UNEXPECTED_PROVIDER_FETCH` if a resolved observation
   reports any fetch, which would surface as `exception_count > 0`;
3. `DOIProductionSummary.__post_init__` raises if the field is truthy.

So a real provider call would appear as an **exception**, not as a wrong zero.
The claimed pair "0 provider calls **and** 0 exceptions" is therefore
meaningful together, even though the first number alone is not independently
produced. Raised as **DOI-D23** (`DOC`, P3), downgraded from my initial reading.

## T11.8 The six DOI-11 live rehearsal numbers

The claim: 20/20 tickers retained, 10 CALL / 10 PUT, 6,740 structurally valid
contracts audited, 240 bounded contracts valued/ranked, 20 canonical chain
reuses, 0 provider calls, 0 exceptions, 48.268 s.

`audit/doi/DOI_PHASE11_IMPLEMENTATION_20260910.md:44–54` records these as
narrative text. **There is no persisted rehearsal artefact on an isolated
database copy that I can reproduce.** The DOI-11 JSON files under `audit/doi/`
are release manifests and readiness reports, not the rehearsal's own
`DOIProductionSummary` output, and the isolated DB copy the rehearsal used was
not retained.

Per prompt §T11.8, all six numbers are **`NOT TESTABLE`**.

Reason (mandatory): reproducing them requires running
`run_completed_session_doi` against a 20-ticker options CSV and a control-plane
copy. The options CSV for that rehearsal is not identified in the document, and
constructing my own would test my input, not their claim.

### The arithmetic I pre-registered, and what it shows

`02_expectations.md` pre-registered that 20 × 12 = 240 exactly, so **240 is only
consistent with every one of the 20 families saturating the 12-contract
bound**. 6,740 / 20 = 337 structurally valid contracts per family on average,
so saturation is entirely plausible and the number is self-consistent rather
than manufactured. `DOI_PHASE11_IMPLEMENTATION_20260910.md:41–42` separately
records a wide-family unit case of "20 structurally valid / 12 valued, with all
20 retained in the family taxonomy", which is the same bound behaving as a
display subset.

"Balanced CALL/PUT" is stated as 10 CALL / 10 PUT — the strongest reading, and
it does not overclaim.

None of this makes the numbers reproducible. They remain `NOT TESTABLE` and
should not be carried into a production acceptance record until an artefact
exists. Raised as **DOI-D24** (`DOC`, P2).

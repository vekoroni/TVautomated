# 02 — Pre-registered expectations (AVS-TST-DOI-001)

**Written:** 2026-09-10, immediately after `01_comprehension.md` and **before**
any production source file, test file, schema or database was opened.
**Status: FROZEN.** This file is not edited after writing. Every correction,
surprise or reversal goes into `04_defects.md` and the track files, never here.

Purpose: record what I expect to find *before* the code can teach me what
"correct" means, so that a convenient implementation cannot retroactively
become the specification.

Conventions used below:

- **E** = expected evidence; **W** = where I expect it; **R** = what would refute.
- "artefact" means a persisted run output under `data\`/`dropbox\` or a
  rehearsal JSON, not a test fixture. Tests alone can only reach
  `VERIFIED OFFLINE`.

---

## Part A — Expectations for the fifteen §16 invariants

### Invariant 1 — DOI cannot change direction, target or invalidation

- **E:** DOI reads `governed_direction`, `target_spot`, `invalidation_spot`
  through an immutable reference object (`UnderlyingThesisRef`, §7.1) with no
  setter. No DOI module writes to the thesis table's direction/target/
  invalidation columns.
- **W:** a DOI domain module (likely `domain/dynamic_options_intelligence.py`
  and siblings); the persistence layer for theses; a static grep for writes.
- **R:** any assignment to a direction/target/invalidation field from inside a
  DOI/ranker/valuation path, or a dataclass that copies and recomputes them
  rather than referencing them. I expect a frozen dataclass; a mutable one is a
  weaker but not fatal finding.

### Invariant 2 — Macro cannot approve, block or reverse

- **E:** macro appears only as a named feature in Model A's feature vector, and
  every macro consumer in the DOI path is arithmetic (a term in a score), never
  a branch that returns early, sets a veto or empties a list.
- **W:** grep for macro/regime/`RISK_OFF`/`HEADWIND` tokens inside DOI modules.
- **R:** any `if macro_state == ...: return []`, `skip`, `veto`, `block`, or a
  macro term that can drive a utility to a sentinel that is later filtered on.
  Note: my memory of this repo says a `HEADWIND RISK_OFF-only block` exists in
  the *macro* domain. If DOI inherits or reads it as a gate, that is a defect
  against invariant 2; if DOI only reads it as a size modifier or feature, it
  is not.

### Invariant 3 — `BLOCKED` compatibility values cannot delete candidate rows

- **E:** every `eil_v3_verdict` consumer classified as advisory/telemetry.
  DOI-1's stated exit was "governed opportunity population is invariant when
  EIL, entry, exit and timing values are permuted."
- **W:** grep `eil_v3_verdict`, `BLOCKED`, `WATCHLIST`,
  `EXECUTE_WITH_CAUTION` across Lab, Interpreter, handoff guard, sovereign
  gate, Phase 10 removal logic.
- **R:** any consumer in class *deletes row*, *caps population*, *alters
  ranking or tier*, or *sets capital/size*. I expect to find at least one
  surviving legacy consumer — a codebase this size rarely removes every one —
  and I pre-register that finding even one in the first two classes is P0.

### Invariant 4 — Contract conditions cannot grant capital or discard

- **E:** no DOI output field feeds a capital, size, notional or allocation
  field. The four `decision_authority` constants present on every output type.
- **W:** DOI output dataclasses/serialisers; grep for size/capital field names
  downstream of DOI.
- **R:** a DOI value read into a sizing calculation, or a DOI state used as a
  filter predicate on the opportunity book.

### Invariant 5 — Morning Gate records state without a new quote and without deleting

- **E:** a Morning Gate path that sets a thesis state from the *underlying*
  price alone, with option-quote acquisition optional and its failure
  non-fatal.
- **W:** `morning_gate.py` and the morning manifest producer (read-only; I will
  **not** execute it).
- **R:** an option-chain fetch on the required path, or a row drop when the
  fetch fails.

### Invariant 6 — OI, volume, PCR, entry, exit, timing are never deletion gates

- **E:** these tokens appear only in ranking/confidence/evidence computations
  and in display, never in a filter that shortens a collection.
- **W:** the family generator (§10) and every list comprehension / filter in
  the DOI path.
- **R:** an OI floor, a volume floor, a spread cap or a PCR threshold used in a
  filter. Given the design says the δ 0.40–0.60 preselection is the specific
  thing being reversed, I pre-register that I expect the *old* selector still
  to exist somewhere in the tree (probably still used by the legacy path) and
  the question is whether the **DOI** family generator is free of it, and
  whether the legacy selector still runs in production alongside DOI.

### Invariant 7 — Missing data never coerced to economic zero

- **E:** `Optional[float]` throughout the observation model; explicit
  `CONTRACT_DATA_INSUFFICIENT` on missing bid/ask/IV/OI/volume; no
  `or 0`, `or 0.0`, `float(x or 0)`, `.get(k, 0)` on economic fields.
- **W:** the observation/candidate dataclasses and their construction from
  provider or canonical rows.
- **R:** any `or 0` / default-zero on bid, ask, mid, IV, OI, volume, premium,
  or a `False` default on a quality boolean that means "known good". This is
  the pattern I consider most likely to be present, because it is the most
  common way this bug survives review — so I expect to spend the most probe
  effort here.

### Invariant 8 — CALL/PUT equivalent coverage and side-correct formulas

- **E:** every scenario/valuation function branches on side and both branches
  are exercised by tests; CALL and PUT cohorts independent in DOI-8.
- **W:** the Black–Scholes/Greeks implementation; the ranker; the label builder.
- **R:** a shared formula with a sign error, a CALL-only test, or a default
  branch that treats an unknown side as CALL.

### Invariant 9 — Trading sessions never treated as calendar days

- **E:** an exchange-calendar helper used for the "DTE outlives hold" check;
  no `dte - planned_hold_sessions` anywhere.
- **W:** the family generator's exclusion 4 and the valuation time conversion.
- **R:** literal subtraction of a session count from a calendar DTE, or a
  `sessions * 1.4`-style approximation constant. An approximation constant is a
  defect (`TIME`) even if it is conservative, because §9.4 requires the exchange
  calendar.

### Invariant 10 — Contract switch forces full recomputation

- **E:** supersession constructs a **new** assessment object from the
  replacement's own observation; no field copied from the incumbent except
  identity/lineage (prior OCC, supersession reason, margin).
- **W:** the supersession/hysteresis code path.
- **R:** any `replace(old_assessment, occ=new_occ)`, `dict.update`, or reuse of
  the incumbent's premium/Greeks/IV/liquidity.

### Invariant 11 — Bind to immutable dataset IDs and evidence cutoffs

- **E:** `observation_dataset_id` and `evidence_cutoff_utc` non-null and
  required (not defaulted) on every assessment row.
- **W:** the assessment schema; five sampled rows or fixtures.
- **R:** a nullable/defaulted dataset ID, or an assessment traceable only to a
  timestamp rather than a dataset identity.

### Invariant 12 — Restart idempotent, append-only not overwritten

- **E:** no `UPDATE`/`DELETE` against family/assessment/ranking/label tables,
  or an explicit guard; a natural key that makes re-persist a no-op or an
  appended version rather than a mutation.
- **W:** the persistence/repository module; the schema DDL.
- **R:** an `INSERT OR REPLACE` / `ON CONFLICT DO UPDATE` on an append-only
  table. I pre-register `INSERT OR REPLACE` as the most likely SQLite idiom to
  find and the one I will look for first.

### Invariant 13 — Dormant/breached/elapsed stays visible, acquisition suppressed

- **E:** a suppression predicate that gates only the *fetch*, plus a
  reactivation condition on underlying price and a manual-refresh entry point,
  both present in code.
- **W:** the observation bridge (DOI-3.4).
- **R:** suppression that also removes the row, or a reactivation path that
  exists only in the design document.

### Invariant 14 — Only long single-leg CALL/PUT

- **E:** the generator emits one leg, side == governed direction, long only;
  no spread/strangle/straddle constructor.
- **W:** the family generator.
- **R:** any multi-leg structure, or a wrong-side contract surviving into a
  family. I note the prompt's three-direction discipline includes `STRANGLE` as
  an `OTHER` bucket, implying strangles exist somewhere in the governed book —
  so I expect the interesting question to be how DOI *handles* an OTHER-bucket
  thesis, not whether it generates one. I pre-register: DOI should mark such a
  thesis unsupported and **retain** it, not drop it.

### Invariant 15 — No automated exit closes or removes a human-held trade

- **E:** Exit Discipline Engine outputs are advisory records; ledger closure
  requires a human actor field.
- **W:** exit engine → ledger → Lab trace.
- **R:** an automated write of a closed/exited state to the ledger, or removal
  of a held position from the Lab.

---

## Part B — Expectations for the numeric acceptance claims (§19)

### DOI-10: 115-test pack; DOI-11: 120-test pack

- **E:** a discoverable selector (a directory such as `tests/doi/`, or a marker)
  that collects exactly 120 tests today. The 115 figure should be reachable at
  the DOI-10 commit but not necessarily now.
- **W:** `pytest --collect-only -q <selector>`.
- **R:** any count I cannot reconcile to 120 with a reasonable selector. The
  prompt is explicit that this is a finding, not a rounding error. I
  pre-register the failure modes I consider most likely, in order: (a) the pack
  is a set of files whose union is 120 only if you include tests that are not
  DOI-specific; (b) 120 counts parametrised cases inconsistently with 115;
  (c) the count includes skipped tests presented as passing.
- **Interpreter note:** the prompt mandates `C:\Python314\python.exe`. My
  standing note on this repo says pytest lives in `venv\Scripts\python.exe`
  (3.13.14). If `C:\Python314\python.exe` cannot collect the pack, I will
  report the deviation rather than silently substituting.

### DOI-10: run `20260909_071646`, 235 opportunities preserved, exactly 4 accepted actionable rows, canonical hash unchanged

- **E:** a rehearsal script and/or a persisted rehearsal JSON naming the run;
  a governed v2 book for that run with 235 rows; a projection that returns 235
  rows with 4 carrying overlay evidence; a before/after hash of the canonical DB.
- **W:** `audit/doi/` rehearsal artefacts; the run directory for
  `20260909_071646`; the Lab projection module.
- **R:** any count other than 235/4; a hash that changes; a 235 that is a
  post-filter number rather than the full governed population; or 4 actionable
  rows that came from a filter rather than an identity reconciliation.
- **Three-direction pre-registration:** I expect 235 to split CALL/PUT/OTHER
  and I expect the 4 to be concentrated on one side. A 4-row overlay that is
  4/0/0 or 0/4/0 is not itself a defect but is a `SYM` question worth raising.

### DOI-11: 20/20 tickers balanced CALL/PUT, 6,740 audited, 240 valued, 20 chains reused, 0 provider calls, 0 exceptions

- **E:** a persisted rehearsal artefact on an isolated DB copy containing these
  aggregates as fields, reproducible on my own copy.
- **W:** `audit/doi/DOI_PHASE11_*` JSON files (their existence is visible from
  the file listing; I have not opened them).
- **R:** absence of such an artefact ⇒ all six numbers are `NOT TESTABLE` per
  prompt §T11.8. Presence but non-reproducible ⇒ `REFUTED`.
- **Pre-registered arithmetic check:** 20 × 12 = 240 exactly. I will test
  whether 240 is a bound-saturation artefact. If any family had fewer than 12
  structurally valid contracts, 240 could not hold, so 240 is *only* consistent
  with every family saturating. 6,740 / 20 = 337 average, so saturation is
  plausible. If the artefact shows a family with < 12 and still totals 240,
  the number is manufactured.
- **"Balanced CALL/PUT" with 20 tickers:** I expect 10/10. Anything else needs
  the word "balanced" defended.

### DOI-11: at most 12 contracts per family in the live path

- **E:** a named constant (12) applied as a *selection* of a subset for
  valuation, with the full taxonomy persisted first; deterministic and
  diversified (same input → same subset, and the subset spans the four
  diversity axes of §10).
- **R:** the bound applied *before* the audit is persisted (that would make it a
  deletion, not a display subset); or a non-deterministic subset (set
  iteration, unstable sort, dict ordering by hash); or a subset that collapses
  onto one strike region.

### DOI-11 / DOI-8 / DOI-9: zero persisted DOI-7 labels, no accepted model, no accepted policy

- **E:** on my **copy** of the control-plane DB: label table exists, row count
  0; model table has no row with an accepted/active state; policy table
  likewise.
- **R:** any non-zero count, or any accepted row whose provenance is synthetic.
  I pre-register that a *non-empty* label table would not merely refute a
  sentence — it would mean DOI-8/9 unavailability is accidental rather than
  designed, which changes the risk assessment materially.

### DOI-11: orchestrator call site after governed horizon propagation, before downstream overlays

- **E:** a single call site in the evening orchestrator with line numbers
  bracketing it between the horizon propagation stage and the first overlay
  stage.
- **R:** a call before horizon propagation (DOI would read a stale horizon), or
  after an overlay that already consumed DOI outputs (ordering paradox), or
  more than one call site.

### DOI-11: no provider client importable from the DOI package

- **E:** a static import graph of the DOI package containing no MarketData,
  Polygon, FRED, Tastytrade or Anthropic client, transitively.
- **R:** any transitive import of a provider client, even if unused at runtime
  — the claim is about importability.

### DOI-11: read-only assessor cannot promote a pre-DOI run

- **E:** an assessor that, given `20260909_071646`, returns "pending" with the
  reason naming the missing new evening artefact and Morning Gate.
- **R:** an assessor that promotes it, or that returns "pending" for a reason
  unrelated to the run's pre-DOI status (right answer, wrong reason — that is a
  `PARTIAL`, because the guard would not hold for a different input).

### DOI-11: rollback point retained

- **E:** a pre-DOI control-plane DB file with a recorded path and hash, and a
  written rollback procedure.
- **W:** `backups/doi_phase1_20260910/control_plane.pre_doi2.sqlite` is visible
  in the tree listing; I expect the *pre-DOI* point to be that one or an
  earlier one, and I will check that the retained file is genuinely pre-DOI and
  not a mid-build snapshot.
- **R:** no procedure document, or a "pre-DOI" backup taken after DOI tables
  were already created.

---

## Part C — Expectations about the shape of the answer

Recorded so that I cannot later claim I predicted whatever I find.

1. I expect DOI's own new code to be **clean on authority** — it was written
   against this design by an implementer who read it. I expect the defects to
   sit at the **seams**: legacy consumers that were never enumerated, the Lab
   templates, the sovereign gate, and the old selector still running.
2. I expect at least one **weak or misnamed test** in the pack, because the
   prompt cites QT-D01 where a test named "all features disabled by default"
   passed while production enabled 8 of 9. I will rate every §16 test.
3. I expect the 115 → 120 test-count delta to be the least defensible number.
4. I expect `VERIFIED` (with artefact) to be reachable **only** for T10, since
   `20260909_071646` is the only real run and it is pre-DOI. Everything in
   T1–T9 and T11 should land at `VERIFIED OFFLINE` at best. If I find myself
   writing `VERIFIED` for an offline-only claim, that is my error, not a result.
5. I expect the honest verdict shape to be **YES WITH CONDITIONS**, because DOI
   is advisory by construction and the live control plane is empty — the risk
   is not that DOI is wrong but that a legacy consumer still deletes. Only a
   surviving deletion path should turn this into NO.

# DOI Phase 2 implementation record — 2026-09-10

## Scope

Implemented the domain-contract and append-only persistence slice from
`AVS-SD-DOI-001` version 1.1. This phase introduces no selector, ranking,
provider-fetch, Intelligence Lab or execution behaviour change.

## Delivered domain contracts

- `UnderlyingThesisRef` binds DOI to the governed direction, geometry, hold,
  version and evidence cutoff without allowing DOI to mutate the thesis.
- `ContractFamily` preserves the complete tested family identity, candidate
  symbols and canonical source-dataset lineage, including an empty
  data-insufficient family when no chain is available.
- `ContractAssessment` separates contract-entry state, model applicability,
  explicitly uncalibrated ranking score and calibrated probability fields.
- `PreferredContractDecision` records the preferred exact contract,
  alternatives, prior decision, hysteresis evidence and economics-recomputed
  assertion.
- Every object fixes `decision_authority=NONE`; no object can change direction,
  invalidate a thesis or grant capital.

## Persistence

The existing CDS control-plane database is extended to
`option_liquidity_lifecycle_v3`. No new database is created.

New append-only tables:

1. `doi_contract_families`
2. `doi_contract_assessments`
3. `doi_preferred_contract_decisions`

All tables have immutable identities, payload hashes, foreign-key lineage and
update/delete prevention triggers. Repeated identical writes reuse the stored
record. Reused identities with changed content fail closed. Preferred-contract
updates require optimistic version matching, prior-decision linkage and exact
economics recomputation when the contract changes.

## Verification

- DOI-2 tests: 11/11 passed.
- Existing option-liquidity lifecycle tests: 16/16 passed.
- Existing DOI authority, handoff and opportunity-book checks: 22/22 passed.
- Expanded canonical/options/handoff `unittest` regression: 71/71 passed.
- Syntax and canonical export smoke: passed.
- Existing pre-DOI2 database migration rehearsal: passed.

Migration rehearsal row counts were unchanged:

| Existing table | Before | After |
|---|---:|---:|
| `option_thesis_events` | 10,667 | 10,667 |
| `option_contract_observations` | 7,969 | 7,969 |
| `option_contract_selection_events` | 8,102 | 8,102 |

All three new DOI tables began with zero rows. The rehearsal database was a
temporary copy and was recycled after validation; the production database was
not modified during offline testing.

The broader direct-function regression encountered the already-recorded
Intelligence Lab trader-facing wording assertion. DOI-2 does not touch the Lab
UI, so this is retained as an existing non-DOI regression rather than hidden or
reclassified.

## Rollback

- Pre-change source files:
  `backups/doi_phase2_20260910/`
- Pre-DOI2 database:
  `backups/doi_phase1_20260910/control_plane.pre_doi2.sqlite`
- Database SHA-256:
  `0F725C01208A427818EBF49C6F964DE12610ED3A21010DDDE4081D564629CFDC`

## Acceptance state

DOI-2 is implemented and offline accepted. The schema will install additively
when the normal option-liquidity store next initialises. DOI-3 must now build
the governed canonical observation and Phantom projection bridge before any
contract-family producer is wired into the live Options Intelligence flow.


# DOI-4 Thesis-Conditioned Contract Family — Implementation Report

**Date:** 2026-09-10  
**Design:** AVS-SD-DOI-001 v1.1  
**Result:** OFFLINE ACCEPTED  
**Next phase:** DOI-5 deterministic scenario and valuation engine

## Delivered

- A pure domain taxonomy separating structural impossibility from temporary
  quote/activity conditions.
- A canonical application service that consumes only a governed thesis and a
  registered MarketData option-chain observation.
- Long single-leg family generation fixed to the thesis CALL or PUT side.
- XNYS-session runway evaluation using the routed 1–20 session hold plus a
  versioned eight-session monitoring/exit buffer.
- Structural exclusions for wrong side, expired/short-runway contracts,
  invalid OCC identity, negative/crossed quotes, impossible identity fields,
  and ambiguous duplicate OCC observations.
- Retention of low-OI, zero-volume, wide-spread, one-sided and no-quote
  contracts as monitorable family members when structurally valid.
- Null-preserving quote/activity handling.
- Complete per-observation taxonomy persisted in the existing append-only DOI
  contract-family record.
- A bounded, geometry/liquidity-diversified display set explicitly labelled as
  coverage, not preferred-contract ranking.
- Reconciled aggregate counts for source observations, admitted candidates,
  exclusions, quote states and retained low-activity contracts.

## Authority boundary

The generator cannot alter Discovery/Vanguard direction, invalidate the
ticker thesis, grant capital, execute a trade, choose a preferred contract, or
publish a model probability. It only produces the governed family consumed by
later valuation and ranking phases. An unavailable or entirely unusable chain
persists a `DATA_INSUFFICIENT` family instead of deleting the opportunity.

## Verification

| Check | Result |
|---|---:|
| DOI-4 CALL/PUT family tests | 7/7 PASS |
| DOI-1 to DOI-4 focused regression | 51/51 PASS |
| Expanded selected governance/handoff regression | 72/72 PASS |
| Direct DOI non-discard checks | 4/4 PASS |
| Compilation | PASS |
| Production database writes | 0 |
| Provider calls in real-data rehearsal | 0 |

The repository also contains pytest-only modules that cannot be collected by
the available Python 3.14 runtime because pytest is not installed. They were
not counted as passed. The selected unittest regression and direct DOI checks
above completed without a product failure.

## Real canonical-chain rehearsal

Using ticker `A`, completed session `2026-09-08`, and canonical dataset
`778fe0d37a39194098d0039a0aab3deae7f3a9a5e1a8b41a3b0b5ad18a50b05e`
against a temporary control plane:

- source observations audited: **242**;
- governed CALL family candidates: **89**;
- two-sided candidates: **77**;
- one-sided monitor candidates: **12**;
- retained low-OI candidates: **73**;
- retained zero-volume candidates: **76**;
- structurally excluded observations: **153**;
- bounded display candidates: **12**;
- persisted taxonomy rows: **242**.

The 153 structural exclusions comprised 121 wrong-side observations and 64
insufficient-runway observations, with overlap permitted at the reason-count
level. The population invariant itself reconciled exactly: 242 = 89 admitted
+ 153 excluded.

## Files

- `domain/contract_family_generation.py`
- `canonical_data/dynamic_options_family.py`
- `canonical_data/__init__.py`
- `tests/test_dynamic_options_contract_family.py`

## Promotion boundary

DOI-4 is deployed as an importable canonical service and remains
non-authoritative. It is not yet wired to replace the live legacy selector;
that integration follows deterministic valuation, lifecycle re-ranking and Lab
projection so a partial family implementation cannot distort current output.
DOI-5 is the next build phase.

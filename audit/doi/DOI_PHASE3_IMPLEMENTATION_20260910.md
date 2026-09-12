# DOI-3 Governed Observation Bridge — Implementation Report

**Date:** 2026-09-10  
**Design:** AVS-SD-DOI-001 v1.1  
**Result:** OFFLINE ACCEPTED  
**Next phase:** DOI-4 governed contract-family generation

## Delivered

- Canonical completed-session option-chain resolution.
- Canonical exact-contract Morning observation resolution.
- Reuse-first, fetch-missing-only acquisition decisions.
- Per-scope duplicate acquisition suppression, including restart reuse through
  the canonical registry.
- Dormant, condition-breached and horizon-elapsed acquisition suppression
  without removal of the underlying opportunity.
- Explicit underlying-price reactivation and operator manual-refresh paths.
- Expired-contract no-fetch protection.
- Deterministic individual-contract activity features.
- Chain, expiry, near-money, target-region and delta-bucket volume/OI PCR.
- PCR change and put/call IV skew.
- Explicit snapshot limitations: no invented quote-update rate, signed order
  flow or premium-flow imbalance.
- Read-only Phantom historical projection bound to a canonical dataset ID and
  a strict point-in-time cutoff.
- Explicit non-fatal Phantom unavailable/data-insufficient states.

## Authority and data ownership

- Current bid, ask, size, volume, OI and Greeks come only from registered
  canonical MarketData observations.
- Phantom contributes aggregates from observations strictly before the
  evidence cutoff. It cannot replace current option facts and has no provider
  callback.
- Every acquisition decision retains the ticker opportunity.
- DOI decision authority remains `NONE`; execution remains human-only.
- Missing numeric evidence remains null and is never converted to zero.

## Verification

| Check | Result |
|---|---:|
| DOI-3 bridge tests | 13/13 PASS |
| DOI-2 persistence tests | 11/11 PASS |
| Existing option-liquidity lifecycle tests | 16/16 PASS |
| Expanded canonical/handoff unittest selection | 69/69 PASS |
| Direct pytest-style opportunity/handoff checks | 73/73 PASS |
| Resource-leak warnings under `-W error::ResourceWarning` | 0 |
| Provider calls during real-data rehearsal | 0 |

The direct-function selection skipped five tests requiring specialised pytest
fixtures; none was reported as passed. The repository's configured virtual
environment still cannot run pytest, so the executed evidence uses Python 3.14
unittest and direct test-function invocation.

## Real-data rehearsal

The production control-plane database was copied to an isolated scratch
database. Against ticker `A`, session `2026-09-08`:

- canonical chain resolution: `CANONICAL_REUSE`;
- physical provider fetches: `0`;
- canonical rows: `242`;
- scoped total volume PCR: `2.5641025641`;
- Phantom applicability: `AVAILABLE`;
- Phantom historical rows: `230`;
- canonical lineage equality: `true`.

No production database or pipeline output was changed by the rehearsal.

## Failure found and corrected during implementation

The first Phantom fixture exposed an SQLite resource leak. A normal SQLite
transaction context commits or rolls back but does not close the connection.
The bridge now wraps the read-only connection in `contextlib.closing`; the
suite passes with resource warnings promoted to errors.

## Promotion boundary

DOI-3 is integrated as a canonical service and exported through the canonical
package. It does not yet alter contract selection, pipeline verdicts, capital
permission or Intelligence Lab rows. DOI-4 will consume the bridge to generate
and preserve governed CALL/PUT contract families.

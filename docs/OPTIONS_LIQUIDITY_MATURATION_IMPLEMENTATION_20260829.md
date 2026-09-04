# AVSHUNTER Options Liquidity Maturation — Production Implementation Record

Date: 2026-08-29  
Scope: long calls and long puts only  
Status: code-integrated; offline regression complete; next governed evening/morning run is the production acceptance run

## Purpose

Preserve a valid directional thesis when its current option contract is not yet liquid, monitor whether a usable contract develops as the underlying approaches the strike, and present the exact morning contract and quote state in the Intelligence Lab. A liquidity-maturation score is monitoring priority only. It is not a probability, trade authority, capital permission, or cap on the number of candidates.

This implementation includes the earlier end-to-end design: single-source canonical data reuse, stopped-ticker suppression, exact-contract continuity, contract-change repricing, Morning Gate transition logic, Intelligence Lab lineage, long-call/put-only policy, and append-only outcome-ready evidence.

## Governed flow

1. Options Intelligence receives only the CDS-authorised post-filter ticker worklist.
2. It resolves a same-session canonical MarketData chain before making a provider call.
3. A missing canonical chain causes one MarketData acquisition and CDS write-through. Polygon options are prohibited.
4. The chain retains zero/low-open-interest strikes. OI and volume contribute to ranking but are not acquisition or thesis-deletion gates.
5. The selector considers governed long CALL/PUT contracts with valid DTE, delta, moneyness, target reachability and a calculable mark.
6. Current quote quality classifies the exact contract as executable, reviewable, pending, stale, zero-bid, no-market or terminally unsuitable.
7. The EOD handoff preserves the thesis, exact selected contract, lifecycle state, runway, quote lineage and deterministic 1/2/3-session monitoring scores.
8. The Morning Gate refreshes the exact MarketData quote. A replacement OCC symbol is a new economic object and must be fully repriced before it can proceed.
9. The Morning Gate appends its quote observation, thesis transition and selection event to the existing CDS `control_plane.sqlite` database.
10. The Intelligence Lab displays the lifecycle and lineage fields. It fails closed on `CONTRACT_REPRICE_REQUIRED` and never infers permission from a maturation score.

## Transition precedence

1. `THESIS_INVALIDATED`
2. `CONTRACT_REPRICE_REQUIRED`
3. `MOVE_ALREADY_REALIZED`
4. `WAIT_FOR_PULLBACK` or `GAP_CONFIRMATION_EXTENDED`
5. `LIQUIDITY_STILL_PENDING`
6. `GAP_CONFIRMATION_WITH_RUNWAY`
7. `EXECUTABLE_NOW`

This order prevents a liquid quote from overriding a broken thesis, an unpriced replacement, or an overnight move that has already consumed the opportunity.

## Persistence contract

- Existing database: `data/canonical/control_plane.sqlite`
- New append-only tables: thesis events, exact-contract observations and selection events
- Canonical providers accepted for option observations: MarketData only
- Dataset types: completed-session `OPTION_CHAIN` and morning `LIVE_OPTION`
- Repeated morning runs append materially different quote events and replay identical observations idempotently
- Terminal thesis states stop future acquisition authority
- Active-monitor worklists request data only when the canonical observation is absent or stale
- No maturation table or field has execution authority

## Intelligence Lab fields

The governed final book carries, among others:

- thesis ID and thesis state
- exact current and previous contract symbols
- contract-changed flag and selection reason
- liquidity state and morning transition
- moneyness and delta band
- minimum DTE and DTE buffer
- distance to ATM in forecast-volatility units
- remaining runway and runway state
- 1/2/3-session maturation states and scores
- explicit `maturation_score_is_probability=false`
- explicit `maturation_execution_authority=false`
- quote timestamp and freshness
- contract economics recomputation status

## Operational acceptance

The next production evening run must show:

- CDS Options worklist reconciled
- MarketData/CDS as the only options-chain sources
- low-OI contracts retained as observations
- lifecycle counts present in Options Intelligence telemetry
- no synthetic/incomplete quote classified executable

The following Morning Gate run must show:

- exact-contract MarketData refreshes
- lifecycle persistence enabled in the summary
- replacement contracts either fully repriced or marked `CONTRACT_REPRICE_REQUIRED`
- pending contracts retained for monitoring rather than presented as GO
- Intelligence Lab lifecycle fields populated for every governed option candidate

## Regression evidence

- Core lifecycle calculations: 27 passing tests
- Integrated focused suite: 71 passing tests
- Morning/CDS append-only integration: 9 passing tests
- EOD lifecycle handoff: 2 passing tests
- Cross-stage regression: 124 passing tests when environment-dependent suites are isolated correctly, plus 3 passing subtests
- Functional selector probe: zero-OI/zero-volume long CALL retained and selected; OI and volume confirmed non-authoritative
- Syntax compilation: lifecycle, CDS, Options Intelligence, EOD and Morning Gate production modules clean

## Rollback

Pre-change copies are stored at:

`backups/options_liquidity_maturation_prechange_20260829`

Rollback must restore only the files in that directory and must not delete or reset unrelated user changes. CDS lifecycle tables are append-only evidence; they can remain unused if the feature flags are disabled.

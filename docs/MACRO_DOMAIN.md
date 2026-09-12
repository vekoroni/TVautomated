# AVSHUNTER Macro bounded context

## Purpose

The Macro domain supplies market, capital-flow, sector-rotation and dealer-gamma
context. It is advisory. It cannot select a ticker, change CALL/PUT direction,
select a contract, change a lifecycle state, grant capital, set position size or
write an execution verdict.

## Inputs

- `dropbox/macro/avshunter_us_money_index.json`: human/LLM-authored advisory
  assessment. Numeric fields without explicit source provenance remain visible
  but are marked `UNVERIFIED_SOURCE` and cannot become calculated evidence.
- `data/phantom/phantom_history.db`: locally stored MarketData option chains.
- Existing files in `dropbox/market_data/`: macro, rates, volatility, sector,
  liquidity and cross-asset inputs consumed by `build_macro_json.py`.

## Local GEX

`scripts/build_local_gex.py` reads the latest common completed SPY/QQQ option
session from Phantom and calculates `SWING_GEX_7_56D`. Open interest is an
exposure weight, not an admission threshold. No external request is made.

Authoritative derived evidence is written under:

`data/canonical/gamma_exposure/<session>/<ticker>/`

It is registered as `DatasetType.GAMMA_EXPOSURE` in
`data/canonical/control_plane.sqlite`, including parent option-chain dataset
identities where available.

Compatibility projections are published atomically to:

- `dropbox/market_data/avshunter_gex_proxy.csv`
- `dropbox/market_data/avshunter_gex_by_strike.csv`
- `dropbox/market_data/avshunter_gex_run_manifest.json`
- `dropbox/market_data/avshunter_gex_errors.txt`

The completed-session scope is not a 0DTE dealer-flow claim. Its calculation
version and DTE scope are present in every output.

## US Money Index

`contracts/us_money_index_contract.py` validates and normalises the sidecar.
The packet is accepted only when:

- its contract and packet type are recognised;
- timestamps are timezone-aware and ordered correctly;
- `execution_permission` is `NONE_INTELLIGENCE_ONLY`;
- it contains no capital, verdict, governed-direction, selected-contract or
  position-size fields.

The source document's tier weights and hard-veto ideas are retained beneath
`proposed_policy`, but `policy_activation` is always
`DISABLED_UNTIL_SEPARATELY_TESTED`.

The normalised packet is carried through:

- `macro_quant_packet.us_money_index`;
- package `macro.us_money_index`;
- the governed Interpreter macro context;
- allow-listed Intelligence Lab `usmi_*` fields.

Missing or invalid USMI data never aborts the core pipeline.

## Initiation

The governed refresh command is:

```powershell
python scripts\refresh_macro_context.py --session latest-completed
```

It validates USMI, calculates/reuses local GEX and invokes
`build_macro_json.py --force`. The latter retains its existing Anthropic macro
synthesis. Use these bounded alternatives for diagnostics:

```powershell
python scripts\validate_us_money_index.py
python scripts\build_local_gex.py --session latest-completed
python scripts\refresh_macro_context.py --dry-run --skip-macro-build
```

`intelligent_orchestrator.py --evening` consumes the resulting macro. It also
attaches a valid USMI sidecar defensively if the macro JSON was built before the
sidecar arrived. It does not calculate GEX and it does not turn macro into an
execution authority.

## Failure behaviour

- GEX calculation failure does not overwrite the last valid compatibility
  projection.
- A missing ticker or mixed completed session fails the GEX refresh before
  publication.
- Invalid USMI becomes `INVALID_UNAVAILABLE`; the core run continues.
- Structured Morning scenarios use three-valued evaluation. Missing evidence
  produces `UNRESOLVED`, never an inferred result.
- The Interpreter and Lab show packet identity, quality and advisory authority.

## Verification

Focused domain, existing macro, Interpreter, Lab, canonical-data and execution
authority regression suites must remain green. Authority paths must not import
the US Money Index contract.

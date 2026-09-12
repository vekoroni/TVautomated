# AVS-FIX-002 Stages 2–5 claim sheet

| Claim | Evidence | Status |
|---|---|---|
| Cumulative volatility budgets use trading sessions and fractions | `domain/volatility_budget.py`; property matrix 1–20 | PASS |
| Runtime adapters propagate canonical volatility and spread units into tiering, execution, EV and Layer 3 outputs | `contracts/opportunity_tier.py`; `execution_gate.py`; `layer3_forward_variance.py`; `trigger_layer.py`; `tests/test_avs_fix_002_runtime_adapters.py` | PASS |
| Missing numeric evidence never becomes favourable zero on v2 paths | silent-default inventory + null tests | PASS |
| DOI receives a governed macro rate per run | `canonical_data/market_rate_observation.py`; two stored runs | PASS |
| CALL and PUT economics are symmetric and advisory | 54-cell scenario tests | PASS |
| Horizon-limited contracts are retained | horizon-limited test | PASS |
| Utility is deterministic, not a probability | assessment/projection contract tests | PASS |
| Decision and fill records are distinct and append-only | SQLite integration test | PASS |
| Pipeline is capital-agnostic; legacy capacity inputs cannot enter the Lab read model | config, projection and dependency tests | PASS — owner decision 2026-09-12 |
| Macro/structure cannot grant authority | domain and presentation tests | PASS |
| Lab projection is v4 and preserves population | projector integration and existing non-discard tests | PASS OFFLINE |
| Completed-session live artefact meets all v2 coverage thresholds | next controlled pipeline cycle | AWAITING RUN |
| Morning exact-contract refresh preserves thesis and recomputes economics | next market-session cycle | AWAITING MARKET SESSION |

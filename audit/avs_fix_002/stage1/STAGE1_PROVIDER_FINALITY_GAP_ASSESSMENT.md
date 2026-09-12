# Stage 1 Provider Finality — Requirement-to-Code Gap Assessment

**Assessment date:** 2026-09-12
**Baseline:** branch `avs-fix-001`, Stage 0 commit `e6d71df`
**Scope:** REQ-WP0-01, REQ-WP0-02 and ALG-15 only

## Initial gap verdict

The pre-slice code could identify cached option-chain datasets, but it could not prove that a completed-session chain represented the provider's final view of the session. Dataset immutability and content hashes proved identity, not finality.

Confirmed initial gaps were:

1. A late individual quote could be mistaken for complete chain coverage.
2. Late-watermark coverage had no enforced threshold.
3. Official underlying close lineage was not a mandatory completion basis.
4. Per-ticker finality did not aggregate into the required 95% chain and 99% close run thresholds.
5. `run_meta_v2` contained no provider completeness evidence and could not govern baseline eligibility from it.
6. DOI could consume a canonical chain without a provider-finality decision.
7. A cached chain with incomplete timestamp coverage could be reused without one governed refresh attempt.
8. The legacy and v2 option-chain paths did not share the same finality contract.
9. ALG-15 thresholds were not loaded from the governed constants contract or represented in run configuration identity.

## Corrective design

Provider Finality is implemented as a bounded domain policy rather than as another selection score:

```text
canonical option-chain bytes + content identity
        + official underlying close identity
        + XNYS session bounds and settlement state
        + historical request mode
                         |
                         v
             per-ticker finality assessment
                         |
       +-----------------+-----------------+
       |                                   |
named residual exception             COMPLETE chain
retained, not normally valued              |
       +-----------------+-----------------+
                         v
        run aggregate: complete/expected >= 95%
             and closes/expected >= 99%
                         |
                         v
      run_meta_v2 run condition and baseline eligibility
```

The design does not discard a ticker merely because its chain is incomplete. It separates evidence retention from normal-run valuation authority. This preserves potentially developing opportunities while preventing partial provider evidence from masquerading as a completed baseline.

## Corrected code boundaries

- `domain/provider_finality.py`: pure finality policy and run aggregation.
- `canonical_data/provider_finality.py`: canonical chain/close verification and worklist assessment.
- `canonical_data/market_observation_resolver.py`: v2 cache assessment and exact one-refresh recovery.
- `canonical_data/option_chain_store.py`: legacy-path parity.
- `scripts/avshunter_options_intelligence.py`: per-row lineage and finality artefact publication.
- `intelligent_orchestrator.py`: run metadata, condition and baseline integration.
- `canonical_data/dynamic_options_bridge.py`: additive observation contract.
- `canonical_data/dynamic_options_production.py`: normal DOI authority enforcement with exception retention.
- `config/governed_constants_v1.json`: versioned ALG-15 timing and coverage thresholds.

## Regression assessment

The Stage 1 focused and integration pack passed 66 tests. The wider historical MSI audit pack is not itself a clean release suite: several tests explicitly assert that prior fixes remain missing and therefore fail when those fixes are present. Those failures were classified rather than hidden.

One genuine issue was exposed by the wider pack: a compatible resolver test double predating the additive `provider_finality` attribute caused an `AttributeError`. The consumer now uses an additive compatibility read. This does not weaken governance because the independent run aggregate still treats absent finality as unassessed and ineligible for a normal baseline.

## Residual risk and acceptance

- **Code risk:** low after focused and integration regression.
- **Data risk:** controlled; partial/missing evidence is explicitly named and cannot grant normal DOI valuation authority.
- **Operational risk:** not yet closed because no real post-change pipeline artefacts exist.
- **Governance risk:** open until new production modules are tracked by Git.

**Assessment outcome:** the requirement-to-code gap is corrected offline and integrated across both chain resolvers, Options Intelligence, DOI and run planning. Formal production acceptance requires Git tracking plus one controlled real pipeline cycle.

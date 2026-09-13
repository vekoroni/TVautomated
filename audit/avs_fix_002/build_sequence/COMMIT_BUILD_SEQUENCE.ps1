$ErrorActionPreference = "Stop"

$repo = "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
Set-Location -LiteralPath $repo

$projectionFiles = @(
    "canonical_data/__init__.py",
    "canonical_data/benchmark_option_chain.py",
    "canonical_data/decision_outcome_ledger.py",
    "canonical_data/gamma_exposure_store.py",
    "canonical_data/macro_gex_overlay.py",
    "canonical_data/market_observation_resolver.py",
    "canonical_data/marketdata_option_chain.py",
    "canonical_data/option_chain_store.py",
    "canonical_data/outcome_learning.py",
    "canonical_data/phantom_option_projection.py",
    "canonical_data/projection_outbox.py",
    "canonical_data/registry.py",
    "domain/actuarial_observation.py",
    "domain/data_projection.py",
    "orchestrator/completed_session_gex.py",
    "intelligent_orchestrator.py",
    "scripts/build_local_gex.py",
    "tools/reconcile_data_projections.py",
    "tests/test_avs_fix_002_stage6_outcome_learning.py",
    "tests/test_completed_session_database_refresh.py",
    "tests/test_database_projection_outbox.py",
    "docs/AVS-SD-DATA-PROJECTION-001_CANONICAL_DATABASE_FANOUT.md",
    "audit/avs_fix_002/data_projection/DATA_PROJECTION_IMPLEMENTATION_REPORT.md"
)

git add -- $projectionFiles
git diff --cached --check
git commit -m "feat(avs-fix-002): project canonical session data"

$completionFiles = @(
    "avshunter_db_update.py",
    "bond_macro_intelligence.py",
    "canonical_data/dynamic_options_family.py",
    "canonical_data/dynamic_options_production.py",
    "canonical_data/dynamic_options_projection.py",
    "canonical_data/dynamic_options_ranking.py",
    "canonical_data/dynamic_options_valuation.py",
    "contracts/interpreter_handoff_materializer.py",
    "contracts/interpreter_macro_context.py",
    "contracts/lab_control.py",
    "contracts/lab_evidence_overlay.py",
    "contracts/opportunity_tier.py",
    "contracts/quote_change_evidence.py",
    "contracts/selected_contract_economics.py",
    "domain/dynamic_options_ranking.py",
    "domain/lab_signal_book_v4.py",
    "domain/long_option_execution.py",
    "domain/macro_advisory_context.py",
    "domain/option_contract_liquidity.py",
    "domain/presentation.py",
    "execution_intelligence_runner.py",
    "intelligence-lab/intelligence_lab.py",
    "intelligence-lab/static/index.html",
    "morning_gate.py",
    "pipeline_interpreter/evidence_resolver.py",
    "tests/msi/test_flow.py",
    "tests/msi/test_functionality.py",
    "tests/msi/test_logic.py",
    "tests/msi/test_regression.py",
    "tests/test_avs_fix_002_quote_truth.py",
    "tests/test_avs_fix_002_stages2_5.py",
    "tests/test_cds2_historical_prices.py",
    "tests/test_doi11_production_integration.py",
    "tests/test_dynamic_options_contract_family.py",
    "tests/test_dynamic_options_lifecycle.py",
    "tests/test_dynamic_options_ranking.py",
    "tests/test_ev3_options_handoff.py",
    "tests/test_lab_monetisation_gate.py",
    "tests/test_morning_gate_authority.py",
    "tests/test_morning_gate_contract_repair.py",
    "tests/test_msi_interpreter_handoff.py",
    "tests/test_msi_quote_and_size_lineage.py",
    "audit/avs_fix_002/build_sequence/BUILD_SEQUENCE_RELEASE_REPORT_20260913.md",
    "audit/avs_fix_002/build_sequence/COMMIT_BUILD_SEQUENCE.ps1"
)

git add -- $completionFiles
git diff --cached --check
git commit -m "feat(avs-fix-002): complete monetisable pipeline integration"

& C:\Python314\python.exe tools\run_governed_pytest.py -q -p no:cacheprovider --basetemp .pt_release tests\test_avs_fix_002_stage0.py


AVSHUNTER → Orchestrator → Vanguard — Contract Pack (v2.0)
======================================================

What this is
- Strict, versioned input contract + validator for Orchestrator → Vanguard.
- Fail-closed behaviour (no silent degradation).
- Regime snapshot gating (stale/missing blocks discovery).
- Daily data integrity scoring with hard fail threshold.

Files
- vanguard_contract.py
- orchestrator_adapter_example.py
- test_vanguard_contract.py
- requirements-dev.txt

Quick start (Windows / PowerShell)
1) Install dev deps:
   pip install -r requirements-dev.txt

2) Run tests:
   pytest -q

Integration
- Make OrchestratorAdapter.build_and_validate(...) the ONLY pathway into Vanguard.
- If validation fails, raise and stop the run.
- Logs are JSONL (append-only). You can pipe into your audit/reporting later.

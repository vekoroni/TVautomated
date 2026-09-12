from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class DOIPhaseQualityAssuranceTest(unittest.TestCase):
    """Design guards for the DOI-1 through DOI-3 authority boundaries."""

    def _function_source(self, path: Path, function_name: str) -> str:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name:
                return ast.get_source_segment(source, node) or ""
        self.fail(f"{function_name} not found in {path}")

    def test_eil_runner_is_permanently_advisory(self) -> None:
        source = self._function_source(
            ROOT / "intelligent_orchestrator.py",
            "run_execution_intelligence_layer",
        )
        self.assertIn("advisory_only = True", source)
        self.assertNotIn("EIL_ADVISORY_ONLY", source)
        self.assertNotIn('cmd.append("--live")', source)
        self.assertNotIn("cmd.append('--live')", source)

    def test_observation_bridge_has_no_provider_or_network_authority(self) -> None:
        source = (ROOT / "canonical_data" / "dynamic_options_bridge.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(source)
        imported_roots: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported_roots.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported_roots.add(node.module.split(".")[0])
        self.assertTrue(
            imported_roots.isdisjoint(
                {"requests", "urllib", "httpx", "aiohttp", "marketdata", "polygon"}
            )
        )
        self.assertNotIn("API_KEY", source)

    def test_domain_contracts_cannot_gain_trading_authority(self) -> None:
        source = (ROOT / "domain" / "dynamic_options_intelligence.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('DOI_DECISION_AUTHORITY = "NONE"', source)
        self.assertIn('DOI_EXECUTION_AUTHORITY = "HUMAN_ONLY"', source)
        self.assertIn("cannot remove an opportunity", source)


if __name__ == "__main__":
    unittest.main()

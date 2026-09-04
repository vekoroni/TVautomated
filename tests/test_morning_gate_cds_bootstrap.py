from __future__ import annotations

import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from morning_gate import configure_cds_runtime_for_morning_gate


class MorningGateCanonicalBootstrapTests(unittest.TestCase):
    def test_direct_cli_defaults_match_production_cds_contract(self) -> None:
        environment: dict[str, str] = {}
        root = Path("C:/AVSHUNTER_TEST")

        runtime = configure_cds_runtime_for_morning_gate(environment, root)

        self.assertTrue(runtime["enabled"])
        self.assertTrue(runtime["write_through"])
        self.assertTrue(runtime["stage_gating_enforced"])
        self.assertEqual(runtime["ohlcv_mode"], "ACTIVE")
        self.assertEqual(environment["AVSHUNTER_CANONICAL_DATA_ENABLED"], "1")
        self.assertEqual(environment["AVSHUNTER_CANONICAL_WRITE_THROUGH"], "1")
        self.assertEqual(environment["AVSHUNTER_STAGE_GATING_ENFORCED"], "1")
        self.assertEqual(
            Path(environment["AVSHUNTER_HISTORICAL_PRICE_DB"]),
            root / "data" / "canonical" / "historical_prices.sqlite",
        )

    def test_explicit_rollback_overrides_are_preserved(self) -> None:
        environment = {
            "AVSHUNTER_CANONICAL_DATA_ENABLED": "0",
            "AVSHUNTER_CANONICAL_WRITE_THROUGH": "0",
            "AVSHUNTER_CDS2_OHLCV_MODE": "SHADOW",
            "AVSHUNTER_STAGE_GATING_ENFORCED": "0",
            "AVSHUNTER_HISTORICAL_PRICE_DB": "D:/controlled/replay.sqlite",
        }

        runtime = configure_cds_runtime_for_morning_gate(environment)

        self.assertFalse(runtime["enabled"])
        self.assertFalse(runtime["write_through"])
        self.assertFalse(runtime["stage_gating_enforced"])
        self.assertEqual(runtime["ohlcv_mode"], "SHADOW")
        self.assertEqual(runtime["database_path"], "D:/controlled/replay.sqlite")

    def test_evening_guidance_uses_complete_morning_orchestrator_entrypoint(self) -> None:
        source = (ROOT / "intelligent_orchestrator.py").read_text(
            encoding="utf-8-sig"
        )

        self.assertIn(
            '"python intelligent_orchestrator.py --morning "',
            source,
        )
        self.assertIn(
            '"Next: python intelligent_orchestrator.py --morning --run-id %s',
            source,
        )


if __name__ == "__main__":
    unittest.main()

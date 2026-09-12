from __future__ import annotations

import unittest

from position_sizing_engine import _binding_eil_block_reason, _eil_multiplier


class EILAdvisoryAuthorityTests(unittest.TestCase):
    def test_blocked_eil_never_blocks_or_resizes(self):
        row = {
            "eil_v3_verdict": "BLOCKED",
            "eil_advisory_only": False,
            "eil_liquidity_passed": False,
            "eil_defer_reason": "NO_EXECUTABLE_MARKET",
            "eil_composite_score": 0,
            "eil_size_multiplier": 0,
        }
        self.assertEqual(_binding_eil_block_reason(row), "")
        self.assertEqual(_eil_multiplier(row), 1.0)

    def test_missing_eil_never_penalises_replay(self):
        self.assertEqual(_binding_eil_block_reason({}), "")
        self.assertEqual(_eil_multiplier({}), 1.0)


if __name__ == "__main__":
    unittest.main()

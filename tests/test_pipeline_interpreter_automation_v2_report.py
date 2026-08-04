from __future__ import annotations

import csv
import json
import tempfile
import unittest

from pipeline_interpreter.automation_v2.core import interpret_ticker
from pipeline_interpreter.automation_v2.fixture_provider import FixtureResponseProvider
from pipeline_interpreter.automation_v2.models import EvidenceManifest, TickerRunRequest
from pipeline_interpreter.automation_v2.renderers import publish_complete_shadow_artifacts


def story(ticker: str) -> str:
    names = ("MACRO", "GAMMA", "LIQUIDITY", "THESIS", "CHART", "OPTIONS", "RISK", "VERDICT")
    sections = "\n".join(
        f"[SECTION_{index}_{name}]\nSection {index}"
        for index, name in enumerate(names, 1)
    )
    return f"[JUNIOR_BRIEFING_{ticker}]\n{sections}"


class EnhancedReportTests(unittest.TestCase):
    def test_structure_narrative_and_vetoes_publish_in_all_outputs(self) -> None:
        ticker = "PYPL"
        manifest = EvidenceManifest(ticker, "run", "inv", "2026-07-25T09:45:00Z")
        request = TickerRunRequest(
            ticker=ticker,
            run_id="run",
            invocation_id="inv",
            manifest=manifest,
            pipeline_row={
                "ticker": ticker,
                "option_rr": "-1.2",
                "call_wall": 50,
                "put_wall": 40,
                "gamma_flip": 44.37,
                "max_pain": 47.5,
                "trigger_primary": "VOL_COMPRESSION",
                "trigger_go_eligible": False,
            },
            lab_context={
                "wbs_score": 72.1,
                "wbs_grade": "PROBABLE",
                "nearest_wall": 50,
                "distance_to_wall": "12.4%",
                "eil_gex_score": 78,
            },
        )
        main = (
            "[TRADE_BRIEF_CSV]\n"
            "ticker,direction,final_verdict,trade_state,rr\n"
            "PYPL,CALL,GO,READY,-1.2\n"
            "[TRADE_NARRATIVE_PYPL]\nThe latest PYPL stock narrative."
        )
        result = interpret_ticker(request, FixtureResponseProvider(main, story(ticker)))
        with tempfile.TemporaryDirectory() as directory:
            output = publish_complete_shadow_artifacts(result, directory)
            html_text = next(output.glob("*.html")).read_text(encoding="utf-8")
            csv_path = next(output.glob("*trade_brief*.csv"))
            with csv_path.open(encoding="utf-8") as handle:
                row = next(csv.DictReader(handle))
            sidecar = json.loads(next(output.glob("*_interpreter.json")).read_text())

        self.assertIn("NEGATIVE_RR", result.veto_codes)
        self.assertEqual(result.effective_verdict, "STOP")
        self.assertIn("LATEST TICKER NARRATIVE", html_text)
        self.assertIn("The latest PYPL stock narrative.", html_text)
        self.assertIn("GEX &amp; WALLS", html_text)
        self.assertIn("WALL BREAK SCORE", html_text)
        self.assertIn("TRIGGER INTELLIGENCE", html_text)
        self.assertEqual(row["call_wall"], "50")
        self.assertEqual(row["wbs_grade"], "PROBABLE")
        self.assertEqual(row["trigger_primary"], "VOL_COMPRESSION")
        self.assertEqual(row["eil_action"], "STOP")
        self.assertEqual(sidecar["market_structure"]["gamma_flip"], 44.37)
        self.assertIn("The latest PYPL stock narrative.", sidecar["narrative"])


if __name__ == "__main__":
    unittest.main()

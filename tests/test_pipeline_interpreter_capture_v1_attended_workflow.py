from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pipeline_interpreter.capture_v1.attended_workflow import run_attended_capture
from pipeline_interpreter.capture_v1.contracts import WindowInfo
from pipeline_interpreter.capture_v1.ticker_market_screen import TickerMarketScreenResult


class FakeBackend:
    def discover(self, _pattern):
        return (WindowInfo(1, "Webull", 2, True, False, (0, 0, 100, 100)),)


class AttendedWorkflowTests(unittest.TestCase):
    @patch("builtins.input", side_effect=[
        "T", "T", "options", "T", "greeks", "T", "tape",
        "T", "orderbook", "T", "short", "T", "noii", "open", "close",
    ])
    def test_composes_all_capture_stages(self, _input):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "pipeline_interpreter.capture_v1.attended_workflow.WindowsShadowBackend",
            return_value=FakeBackend(),
        ), patch(
            "pipeline_interpreter.capture_v1.attended_workflow.WindowsNavigationDriver"
        ), patch(
            "pipeline_interpreter.capture_v1.attended_workflow.capture_ticker_workflow"
        ) as charts, patch(
            "pipeline_interpreter.capture_v1.attended_workflow.capture_ticker_market_screen"
        ) as screen, patch(
            "pipeline_interpreter.capture_v1.attended_workflow.capture_noii_crosses"
        ) as crosses:
            root = Path(tmp)
            chart_manifest = root / "chart.json"
            chart_manifest.write_text("{}")
            charts.return_value = (chart_manifest, ())
            screen.side_effect = lambda **kwargs: TickerMarketScreenResult(
                manifest=chart_manifest, diagnostic_image=chart_manifest,
                matched=True, finding=None,
            )
            crosses.return_value = (chart_manifest, ())
            manifest = run_attended_capture(ticker="T", output_directory=root / "capture")
            self.assertTrue(manifest.is_file())
            self.assertEqual(1, charts.call_count)
            self.assertEqual(6, screen.call_count)
            self.assertEqual(1, crosses.call_count)

    def test_shadow_can_auto_accept_ticker_and_assume_chart_open(self):
        with tempfile.TemporaryDirectory() as tmp, patch(
            "pipeline_interpreter.capture_v1.attended_workflow.WindowsShadowBackend",
            return_value=FakeBackend(),
        ), patch(
            "pipeline_interpreter.capture_v1.attended_workflow.WindowsNavigationDriver"
        ), patch(
            "pipeline_interpreter.capture_v1.attended_workflow.capture_ticker_workflow"
        ) as charts, patch(
            "pipeline_interpreter.capture_v1.attended_workflow.capture_ticker_market_screen",
            side_effect=RuntimeError("stop after chart stage"),
        ):
            root = Path(tmp)
            chart_manifest = root / "chart.json"
            chart_manifest.write_text("{}")
            charts.return_value = (chart_manifest, ())
            with self.assertRaisesRegex(RuntimeError, "stop after chart stage"):
                run_attended_capture(
                    ticker="T",
                    output_directory=root / "capture",
                    automatic_ticker_acceptance=True,
                    chart_already_open=True,
                )
            kwargs = charts.call_args.kwargs
            self.assertFalse(kwargs["establish_chart_workspace"])
            self.assertEqual("T", kwargs["verify_ticker"]("T", chart_manifest))


if __name__ == "__main__":
    unittest.main()

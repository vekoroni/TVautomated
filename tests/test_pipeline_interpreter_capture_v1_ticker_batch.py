from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline_interpreter.capture_v1.navigation import CHART_WORKSPACE_POINT
from pipeline_interpreter.capture_v1.ticker_batch import capture_ticker_workflow
from tests.test_pipeline_interpreter_capture_v1_navigation import FakeDriver, window


class WorkflowDriver(FakeDriver):
    def capture_screen_region(self, _window, destination):
        self.actions.append(("capture", destination.name))
        image = Image.effect_noise((1200, 800), 24).convert("RGB")
        # Selection verification looks for blue near every expected interval.
        for x in (490, 467, 444, 382, 350):
            for px in range(x - 8, x + 9):
                for py in range(740, 758):
                    image.putpixel((px, py), (20, 80, 240))
        image.save(destination, "PNG")


class CaptureBackend:
    def capture_window(self, _window, destination):
        image = Image.effect_noise((1400, 900), 32).convert("RGB")
        image.putpixel((10, 10), (len(destination.name) * 5 % 255, 0, 0))
        image.save(destination, "PNG")
        return "TEST_HWND"


class TickerBatchTests(unittest.TestCase):
    def test_exact_ticker_unlocks_five_timeframe_capture(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "run"
            navigator = WorkflowDriver()
            manifest, assets = capture_ticker_workflow(
                ticker="NFLX",
                window=window(),
                output_directory=output,
                verify_ticker=lambda _requested, _image: "NFLX",
                navigator=navigator,
                capture_backend=CaptureBackend(),
            )
            self.assertTrue(manifest.is_file())
            self.assertEqual(len(assets), 5)
            self.assertTrue(all(path.is_file() for path in assets))
            clicks = [action for action in navigator.actions if action[0] == "click"]
            chart_index = clicks.index(("click", CHART_WORKSPACE_POINT))
            first_timeframe_index = next(
                index
                for index, action in enumerate(clicks)
                if action[1].y == 0.934
            )
            self.assertGreater(chart_index, 0)  # ticker selection happens first
            self.assertLess(chart_index, first_timeframe_index)

    def test_mismatched_ticker_stops_without_retained_output(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "run"
            with self.assertRaisesRegex(
                RuntimeError, "TICKER_EXACT_MATCH_NOT_CONFIRMED:NFLX:NFXL"
            ):
                capture_ticker_workflow(
                    ticker="NFLX",
                    window=window(),
                    output_directory=output,
                    verify_ticker=lambda _requested, _image: "NFXL",
                    navigator=WorkflowDriver(),
                    capture_backend=CaptureBackend(),
                )
            self.assertFalse(output.exists())

    def test_chart_already_open_skips_primary_tab_click(self):
        with tempfile.TemporaryDirectory() as root:
            navigator = WorkflowDriver()
            capture_ticker_workflow(
                ticker="NFLX",
                window=window(),
                output_directory=Path(root) / "run",
                verify_ticker=lambda _requested, _image: "NFLX",
                navigator=navigator,
                capture_backend=CaptureBackend(),
                establish_chart_workspace=False,
            )
            clicks = [action for action in navigator.actions if action[0] == "click"]
            self.assertNotIn(("click", CHART_WORKSPACE_POINT), clicks)


if __name__ == "__main__":
    unittest.main()

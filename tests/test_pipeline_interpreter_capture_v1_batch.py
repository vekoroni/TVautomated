from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

from pipeline_interpreter.capture_v1.contracts import WindowInfo
from pipeline_interpreter.capture_v1.navigation import (
    CHART_WORKSPACE_POINT,
    FULL_CHART_INTERVAL_POINTS,
)
from pipeline_interpreter.capture_v1.timeframe_batch import (
    TIMEFRAME_ORDER, capture_timeframe_batch,
)


class FakeNavigator:
    def __init__(self):
        self.selected = "daily"
    def foreground(self, _window): pass
    def is_foreground(self, _window): return True
    def click_relative(self, _window, point):
        if point == CHART_WORKSPACE_POINT:
            return
        self.selected = next(k for k, v in FULL_CHART_INTERVAL_POINTS.items() if v == point)
    def capture_screen_region(self, _window, destination):
        image = Image.new("RGB", (1200, 800), "white")
        point = FULL_CHART_INTERVAL_POINTS[self.selected]
        x = round(1200 * point.x)
        y = round(800 * 0.938)
        ImageDraw.Draw(image).rectangle((x - 5, y - 4, x + 5, y + 4), fill=(20, 100, 255))
        image.save(destination, "PNG")


class FakeCapture:
    def __init__(self, navigator): self.navigator = navigator
    def discover(self, _pattern): return ()
    def capture_window(self, _window, destination):
        image = Image.effect_noise((1200, 800), 35).convert("RGB")
        ImageDraw.Draw(image).text((30, 30), self.navigator.selected, fill="white")
        image.save(destination, "PNG")
        return "FAKE_HWND"


class BatchTests(unittest.TestCase):
    def test_batch_captures_five_unique_verified_assets(self):
        with tempfile.TemporaryDirectory() as root:
            navigator = FakeNavigator()
            manifest, assets = capture_timeframe_batch(
                ticker="AAL",
                window=WindowInfo(1, "Webull", 2, True, False, (0, 0, 1200, 800)),
                output_directory=Path(root) / "batch",
                navigator=navigator,
                capture_backend=FakeCapture(navigator),
            )
            self.assertTrue(manifest.is_file())
            self.assertEqual(len(assets), 5)
            with Image.open(assets[0]) as image:
                self.assertEqual(image.size, (1034, 704))
            self.assertEqual(
                tuple(path.stem.removeprefix("AAL_") for path in assets),
                TIMEFRAME_ORDER,
            )

    def test_transient_missing_indicator_is_retried(self):
        class RetryNavigator(FakeNavigator):
            def __init__(self):
                super().__init__()
                self.captures = {}

            def capture_screen_region(self, window, destination):
                count = self.captures.get(self.selected, 0) + 1
                self.captures[self.selected] = count
                if self.selected == "1h" and count == 1:
                    Image.new("RGB", (1200, 800), "white").save(
                        destination, "PNG"
                    )
                    return
                super().capture_screen_region(window, destination)

        with tempfile.TemporaryDirectory() as root:
            navigator = RetryNavigator()
            manifest, _assets = capture_timeframe_batch(
                ticker="AAL",
                window=WindowInfo(1, "Webull", 2, True, False, (0, 0, 1200, 800)),
                output_directory=Path(root) / "batch",
                navigator=navigator,
                capture_backend=FakeCapture(navigator),
            )
            self.assertTrue(manifest.is_file())
            self.assertEqual(navigator.captures["1h"], 2)


if __name__ == "__main__":
    unittest.main()

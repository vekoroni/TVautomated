from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from PIL import Image, ImageDraw

from pipeline_interpreter.capture_v1.noii_cross import (
    NOII_CROSS_POINTS,
    NOII_CROSS_ZONE,
    capture_noii_crosses,
)
from tests.test_pipeline_interpreter_capture_v1_navigation import FakeDriver, window


class CrossDriver(FakeDriver):
    def __init__(self):
        super().__init__()
        self.phase = 0
    def click_relative(self, window, point):
        super().click_relative(window, point)
        self.phase += 1
    def capture_screen_region(self, _window, destination):
        image = Image.effect_noise((1200, 800), 24).convert("RGB")
        ImageDraw.Draw(image).text((300, 300), str(self.phase), fill="blue")
        image.save(destination, "PNG")


class NoiiCrossTests(unittest.TestCase):
    def test_only_closing_target_is_allowlisted(self):
        closing = NOII_CROSS_POINTS["close"]
        self.assertTrue(NOII_CROSS_ZONE.contains(closing))
        self.assertNotIn("open", NOII_CROSS_POINTS)

    def test_captures_two_distinct_canonical_assets(self):
        with tempfile.TemporaryDirectory() as root:
            manifest, assets = capture_noii_crosses(
                ticker="NFLX", window=window(),
                output_directory=Path(root) / "crosses",
                verify_cross=lambda phase, _image: f"{'Opening' if phase == 'open' else 'Closing'} Cross",
                driver=CrossDriver(),
            )
            self.assertTrue(manifest.is_file())
            self.assertEqual([p.name for p in assets], [
                "NFLX_orderbook_imbalance_open.png",
                "NFLX_orderbook_imbalance_close.png",
            ])

    def test_wrong_cross_label_stops_without_output(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "crosses"
            with self.assertRaisesRegex(RuntimeError, "NOII_CROSS_TYPE_MISMATCH"):
                capture_noii_crosses(
                    ticker="NFLX", window=window(), output_directory=output,
                    verify_cross=lambda _phase, _image: "Order Book",
                    driver=CrossDriver(),
                )
            self.assertFalse(output.exists())

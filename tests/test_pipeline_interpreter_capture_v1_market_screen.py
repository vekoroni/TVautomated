from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline_interpreter.capture_v1.market_screen import (
    MARKET_SCREEN_POINTS,
    TICKER_SCREEN_MISMATCH,
    map_market_screen,
    record_ticker_verification,
)
from pipeline_interpreter.capture_v1.navigation import RelativePoint
from tests.test_pipeline_interpreter_capture_v1_navigation import FakeDriver, window


class MarketScreenDriver(FakeDriver):
    def capture_screen_region(self, _window, destination):
        self.actions.append(("capture", destination.name))
        Image.effect_noise((1200, 800), 24).convert("RGB").save(
            destination, "PNG"
        )


class MarketScreenTests(unittest.TestCase):
    def test_updated_webull_tab_calibration(self):
        self.assertEqual(MARKET_SCREEN_POINTS["options"], RelativePoint(0.161, 0.046))
        self.assertEqual(MARKET_SCREEN_POINTS["tape"], RelativePoint(0.209, 0.046))
        self.assertEqual(MARKET_SCREEN_POINTS["orderbook"], RelativePoint(0.265, 0.046))
        self.assertEqual(MARKET_SCREEN_POINTS["noii"], RelativePoint(0.308, 0.046))
        self.assertEqual(MARKET_SCREEN_POINTS["short"], RelativePoint(0.583, 0.046))

    def test_each_allowlisted_screen_maps_privately(self):
        for screen, point in MARKET_SCREEN_POINTS.items():
            with self.subTest(screen=screen), tempfile.TemporaryDirectory() as root:
                driver = MarketScreenDriver()
                image, manifest = map_market_screen(
                    window=window(),
                    screen=screen,
                    output_directory=Path(root) / screen,
                    driver=driver,
                )
                self.assertEqual(driver.actions[2], ("click", point))
                with Image.open(image) as cropped:
                    self.assertEqual(cropped.size, (1034, 676))
                metadata = json.loads(manifest.read_text(encoding="utf-8"))
                self.assertFalse(metadata["uncropped_image_retained"])
                self.assertFalse(metadata["pipeline_published"])
                self.assertEqual(
                    metadata["privacy_crop"]["profile"],
                    "webull_market_screen_privacy_20260726_v1",
                )

    def test_unknown_screen_stops_before_navigation(self):
        with tempfile.TemporaryDirectory() as root:
            driver = MarketScreenDriver()
            with self.assertRaisesRegex(
                ValueError, "UNSUPPORTED_MARKET_SCREEN"
            ):
                map_market_screen(
                    window=window(),
                    screen="trade-ticket",
                    output_directory=Path(root) / "unsafe",
                    driver=driver,
                )
            self.assertEqual(driver.actions, [])

    def test_ticker_mismatch_is_flagged_and_evidence_is_retained(self):
        with tempfile.TemporaryDirectory() as root:
            image, manifest = map_market_screen(
                window=window(),
                screen="options",
                output_directory=Path(root) / "options",
                driver=MarketScreenDriver(),
            )
            matched = record_ticker_verification(
                manifest_path=manifest,
                expected_ticker="NFLX",
                observed_ticker="MT",
            )
            self.assertFalse(matched)
            self.assertTrue(image.is_file())
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "stopped")
            self.assertEqual(metadata["findings"], [TICKER_SCREEN_MISMATCH])
            self.assertFalse(metadata["pipeline_published"])

    def test_exact_screen_ticker_clears_findings(self):
        with tempfile.TemporaryDirectory() as root:
            _image, manifest = map_market_screen(
                window=window(),
                screen="options",
                output_directory=Path(root) / "options",
                driver=MarketScreenDriver(),
            )
            self.assertTrue(record_ticker_verification(
                manifest_path=manifest,
                expected_ticker="NFLX",
                observed_ticker="nflx",
            ))
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "mapped")
            self.assertEqual(metadata["findings"], [])


if __name__ == "__main__":
    unittest.main()

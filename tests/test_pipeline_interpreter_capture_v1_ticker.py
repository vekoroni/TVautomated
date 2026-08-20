from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline_interpreter.capture_v1.navigation import (
    GLOBAL_STOCK_SEARCH_POINT, switch_ticker_for_visual_review,
    ticker_virtual_keys,
)
from tests.test_pipeline_interpreter_capture_v1_navigation import FakeDriver, window


class TickerNavigationTests(unittest.TestCase):
    def test_ticker_key_sequence_preserves_exact_character_order(self):
        self.assertEqual(
            ticker_virtual_keys("NFLX"),
            (ord("N"), ord("F"), ord("L"), ord("X")),
        )

    def test_ticker_switch_submits_exact_active_result_without_down_arrow(self):
        class ValidDiagnosticDriver(FakeDriver):
            def capture_screen_region(self, _window, destination):
                self.actions.append(("capture", destination.name))
                Image.effect_noise((1200, 800), 24).convert("RGB").save(
                    destination, "PNG"
                )

        with tempfile.TemporaryDirectory() as root:
            driver = ValidDiagnosticDriver()
            image, manifest = switch_ticker_for_visual_review(
                window=window(), ticker="NFLX",
                output_directory=Path(root) / "nflx", driver=driver,
            )
            self.assertTrue(image.is_file())
            self.assertTrue(manifest.is_file())
            with Image.open(image) as cropped:
                self.assertEqual(cropped.size, (1034, 704))
            metadata = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertFalse(metadata["uncropped_image_retained"])
            self.assertEqual(
                metadata["privacy_crop"]["removed_regions"],
                [
                    "ACCOUNT_HEADER",
                    "WATCHLIST",
                    "NAVIGATION_RAIL",
                    "BOTTOM_ACCOUNT_TICKER",
                ],
            )
            self.assertIn(("click", GLOBAL_STOCK_SEARCH_POINT), driver.actions)
            self.assertIn(("replace_text", "NFLX"), driver.actions)
            self.assertIn(("enter",), driver.actions)
            self.assertNotIn(("down",), driver.actions)
            self.assertLess(
                driver.actions.index(("replace_text", "NFLX")),
                driver.actions.index(("enter",)),
            )

    def test_invalid_ticker_rejected_before_navigation(self):
        with tempfile.TemporaryDirectory() as root:
            driver = FakeDriver()
            with self.assertRaisesRegex(ValueError, "INVALID_TICKER"):
                switch_ticker_for_visual_review(
                    window=window(), ticker="AAL;BUY",
                    output_directory=Path(root) / "bad", driver=driver,
                )
            self.assertEqual(driver.actions, [])

    def test_blank_diagnostic_is_rejected_and_not_manifested(self):
        class BlankDriver(FakeDriver):
            def capture_screen_region(self, _window, destination):
                Image.new("RGB", (1200, 800), "black").save(destination, "PNG")

        with tempfile.TemporaryDirectory() as root:
            output = Path(root) / "blank"
            with self.assertRaisesRegex(RuntimeError, "TICKER_DIAGNOSTIC_INVALID"):
                switch_ticker_for_visual_review(
                    window=window(), ticker="NFLX",
                    output_directory=output, driver=BlankDriver(),
                )
            self.assertFalse((output / "ticker_switch.json").exists())
            self.assertFalse((output / "webull_NFLX_ticker_switch.png").exists())


if __name__ == "__main__":
    unittest.main()

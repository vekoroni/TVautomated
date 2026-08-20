from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline_interpreter.capture_v1.market_screen import TICKER_SCREEN_MISMATCH
from pipeline_interpreter.capture_v1.ticker_market_screen import (
    MARKET_SCREEN_TYPE_MISMATCH,
    capture_ticker_market_screen,
)
from tests.test_pipeline_interpreter_capture_v1_navigation import FakeDriver, window


class IntegratedDriver(FakeDriver):
    def capture_screen_region(self, _window, destination):
        self.actions.append(("capture", destination.name))
        Image.effect_noise((1200, 800), 24).convert("RGB").save(
            destination, "PNG"
        )


class TickerMarketScreenTests(unittest.TestCase):
    def test_exact_ticker_maps_integrated_options_screen(self):
        with tempfile.TemporaryDirectory() as root:
            result = capture_ticker_market_screen(
                ticker="NFLX",
                screen="options",
                window=window(),
                output_directory=Path(root) / "run",
                verify_screen_ticker=lambda _expected, _image: "NFLX",
                driver=IntegratedDriver(),
            )
            self.assertTrue(result.matched)
            self.assertIsNone(result.finding)
            self.assertTrue(result.diagnostic_image.is_file())
            metadata = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertEqual(metadata["status"], "mapped")
            self.assertFalse(metadata["published"])

    def test_mismatch_is_quarantined_in_final_run(self):
        with tempfile.TemporaryDirectory() as root:
            result = capture_ticker_market_screen(
                ticker="NFLX",
                screen="options",
                window=window(),
                output_directory=Path(root) / "run",
                verify_screen_ticker=lambda _expected, _image: "MUR",
                driver=IntegratedDriver(),
            )
            self.assertFalse(result.matched)
            self.assertEqual(result.finding, TICKER_SCREEN_MISMATCH)
            self.assertTrue(result.diagnostic_image.is_file())
            metadata = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertEqual(metadata["findings"], [TICKER_SCREEN_MISMATCH])
            self.assertFalse(metadata["published"])

    def test_wrong_visible_screen_type_is_quarantined(self):
        with tempfile.TemporaryDirectory() as root:
            result = capture_ticker_market_screen(
                ticker="NFLX",
                screen="tape",
                window=window(),
                output_directory=Path(root) / "run",
                verify_screen_ticker=lambda _expected, _image: "NFLX",
                verify_screen_type=lambda _expected, _image: "Order Book",
                driver=IntegratedDriver(),
            )
            self.assertFalse(result.matched)
            self.assertEqual(result.finding, MARKET_SCREEN_TYPE_MISMATCH)
            metadata = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                metadata["findings"], [MARKET_SCREEN_TYPE_MISMATCH]
            )
            self.assertFalse(metadata["published"])

    def test_time_and_sales_alias_accepts_tape_screen(self):
        with tempfile.TemporaryDirectory() as root:
            result = capture_ticker_market_screen(
                ticker="NFLX",
                screen="tape",
                window=window(),
                output_directory=Path(root) / "run",
                verify_screen_ticker=lambda _expected, _image: "NFLX",
                verify_screen_type=lambda _expected, _image: "Time & Sales",
                driver=IntegratedDriver(),
            )
            self.assertTrue(result.matched)

    def test_short_interest_alias_is_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            result = capture_ticker_market_screen(
                ticker="NFLX",
                screen="short",
                window=window(),
                output_directory=Path(root) / "run",
                verify_screen_ticker=lambda _expected, _image: "NFLX",
                verify_screen_type=lambda _expected, _image: "Short Interest",
                driver=IntegratedDriver(),
            )
            self.assertTrue(result.matched)
            metadata = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertEqual(metadata["screen"], "short")
            self.assertEqual(
                [path.name for path in result.assets], ["NFLX_short.png"]
            )
            self.assertTrue(result.assets[0].is_file())
            self.assertEqual(
                metadata["assets"][0]["role"], "SHORT_INTEREST"
            )
            self.assertFalse(metadata["published"])

    def test_short_interest_mismatch_does_not_create_canonical_asset(self):
        with tempfile.TemporaryDirectory() as root:
            result = capture_ticker_market_screen(
                ticker="NFLX",
                screen="short",
                window=window(),
                output_directory=Path(root) / "run",
                verify_screen_ticker=lambda _expected, _image: "MUR",
                verify_screen_type=lambda _expected, _image: "Short Interest",
                driver=IntegratedDriver(),
            )
            self.assertFalse(result.matched)
            self.assertEqual(result.assets, ())
            self.assertFalse((Path(root) / "run" / "NFLX_short.png").exists())

    def test_verified_greeks_screen_creates_canonical_asset(self):
        with tempfile.TemporaryDirectory() as root:
            result = capture_ticker_market_screen(
                ticker="NFLX",
                screen="greeks",
                window=window(),
                output_directory=Path(root) / "run",
                verify_screen_ticker=lambda _expected, _image: "NFLX",
                verify_screen_type=lambda _expected, _image: (
                    "Options Chain Greeks"
                ),
                driver=IntegratedDriver(),
            )
            self.assertTrue(result.matched)
            self.assertEqual(
                [path.name for path in result.assets],
                ["NFLX_options_chain_greeks.png"],
            )
            metadata = json.loads(result.manifest.read_text(encoding="utf-8"))
            self.assertEqual(
                metadata["assets"][0]["role"], "OPTIONS_CHAIN_GREEKS"
            )

    def test_plain_options_label_cannot_pass_greeks_route(self):
        with tempfile.TemporaryDirectory() as root:
            result = capture_ticker_market_screen(
                ticker="NFLX",
                screen="greeks",
                window=window(),
                output_directory=Path(root) / "run",
                verify_screen_ticker=lambda _expected, _image: "NFLX",
                verify_screen_type=lambda _expected, _image: "Options",
                driver=IntegratedDriver(),
            )
            self.assertFalse(result.matched)
            self.assertEqual(result.finding, MARKET_SCREEN_TYPE_MISMATCH)
            self.assertEqual(result.assets, ())


if __name__ == "__main__":
    unittest.main()

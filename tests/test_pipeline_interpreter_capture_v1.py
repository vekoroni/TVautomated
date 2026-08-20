from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from pipeline_interpreter.capture_v1.contracts import (
    CaptureMode, CaptureRequest, CaptureStatus, WindowInfo,
)
from pipeline_interpreter.capture_v1.service import run_capture
from pipeline_interpreter.capture_v1.windows import _title_matches


class FakeBackend:
    def __init__(self, windows=()):
        self.windows = tuple(windows)
        self.captures = 0

    def discover(self, _pattern):
        return self.windows

    def capture_window(self, _window, destination):
        self.captures += 1
        from PIL import Image, ImageDraw
        image = Image.new("RGB", (1200, 800), "black")
        draw = ImageDraw.Draw(image)
        for x in range(0, 1200, 20):
            draw.line((x, 0, 1199 - x, 799), fill=(x % 255, 120, 220), width=3)
        image.save(destination, "PNG")
        return "FAKE_WINDOW_HANDLE_CAPTURE"


def window(title="Webull", minimized=False):
    return WindowInfo(1, title, 101, True, minimized, (0, 0, 1200, 800))


class CaptureV1Tests(unittest.TestCase):
    def test_webull_title_match_excludes_diagnostic_image_viewer(self):
        self.assertTrue(_title_matches("Webull Desktop", "Webull"))
        self.assertFalse(_title_matches("webull_options_screen_map.png", "Webull"))

    def request(self, root, mode=CaptureMode.DRY_RUN, confirmed=False):
        return CaptureRequest(
            "aal", "run", "inv", Path(root), mode,
            operator_confirmed_ticker=confirmed,
            operator_confirmed_daily=confirmed,
        )

    def test_off_does_not_discover_or_capture(self):
        with tempfile.TemporaryDirectory() as root:
            backend = FakeBackend((window(),))
            result = run_capture(self.request(root, CaptureMode.OFF), backend)
            self.assertEqual(result.status, CaptureStatus.DISABLED)
            self.assertEqual(backend.captures, 0)

    def test_dry_run_requires_exactly_one_visible_window(self):
        with tempfile.TemporaryDirectory() as root:
            missing = run_capture(self.request(root), FakeBackend())
            ambiguous = run_capture(
                self.request(root), FakeBackend((window(), window("Webull Desktop")))
            )
            self.assertIn("WEBULL_WINDOW_NOT_FOUND", missing.findings)
            self.assertIn("AMBIGUOUS_WEBULL_WINDOWS:2", ambiguous.findings)

    def test_minimized_and_order_surfaces_fail_closed(self):
        with tempfile.TemporaryDirectory() as root:
            minimized = run_capture(
                self.request(root), FakeBackend((window(minimized=True),))
            )
            trading = run_capture(
                self.request(root), FakeBackend((window("Webull - Place Order"),))
            )
            self.assertIn("WEBULL_MINIMIZED", minimized.findings)
            self.assertTrue(trading.findings[0].startswith("FORBIDDEN_TRADING_SURFACE"))

    def test_shadow_capture_is_staged_and_never_published(self):
        with tempfile.TemporaryDirectory() as root:
            backend = FakeBackend((window(),))
            result = run_capture(
                self.request(root, CaptureMode.SHADOW, confirmed=True), backend
            )
            self.assertEqual(result.status, CaptureStatus.CAPTURED)
            self.assertFalse(result.published)
            self.assertEqual(backend.captures, 1)
            self.assertTrue(Path(result.manifest_path).is_file())
            self.assertEqual(Path(result.assets[0]).name, "AAL_daily.png")
            import json
            manifest = json.loads(Path(result.manifest_path).read_text())
            self.assertEqual(
                manifest["assets"][0]["capture_method"],
                "FAKE_WINDOW_HANDLE_CAPTURE",
            )

    def test_shadow_capture_requires_both_operator_attestations(self):
        with tempfile.TemporaryDirectory() as root:
            backend = FakeBackend((window(),))
            result = run_capture(self.request(root, CaptureMode.SHADOW), backend)
            self.assertEqual(result.status, CaptureStatus.STOPPED)
            self.assertIn("OPERATOR_TICKER_CONFIRMATION_REQUIRED", result.findings)
            self.assertIn("OPERATOR_DAILY_VIEW_CONFIRMATION_REQUIRED", result.findings)
            self.assertEqual(backend.captures, 0)

    def test_enabled_mode_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(ValueError):
                self.request(root, CaptureMode.ENABLED)


if __name__ == "__main__":
    unittest.main()

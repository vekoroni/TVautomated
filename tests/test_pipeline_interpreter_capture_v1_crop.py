from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from PIL import Image

from pipeline_interpreter.capture_v1.privacy_crop import crop_chart_in_place


class PrivacyCropTests(unittest.TestCase):
    def test_crop_removes_header_sidebar_and_bottom_strip(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "window.png"
            Image.new("RGB", (2000, 1200), "white").save(path, "PNG")
            metadata = crop_chart_in_place(path)
            with Image.open(path) as image:
                self.assertEqual(image.size, (1722, 1056))
            self.assertEqual(metadata["crop_box_pixels"], [274, 114, 1996, 1170])
            self.assertIn("ACCOUNT_HEADER", metadata["removed_regions"])
            self.assertIn("WATCHLIST", metadata["removed_regions"])


if __name__ == "__main__":
    unittest.main()

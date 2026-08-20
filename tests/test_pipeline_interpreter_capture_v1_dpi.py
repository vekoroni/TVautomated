from __future__ import annotations

import unittest
from unittest.mock import patch

from pipeline_interpreter.capture_v1 import dpi


class DpiTests(unittest.TestCase):
    def test_configuration_is_idempotent(self):
        original = dpi._configured
        try:
            dpi._configured = True
            with patch.object(dpi.ctypes, "windll", create=True) as windll:
                dpi.enable_per_monitor_dpi_awareness()
                self.assertFalse(windll.shcore.SetProcessDpiAwareness.called)
        finally:
            dpi._configured = original


if __name__ == "__main__":
    unittest.main()

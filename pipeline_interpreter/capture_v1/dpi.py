"""Windows DPI coordination for consistent capture and cursor coordinates."""

from __future__ import annotations

import ctypes


_configured = False


def enable_per_monitor_dpi_awareness() -> None:
    """Put window bounds, screenshots, and SetCursorPos in physical pixels."""
    global _configured
    if _configured or not hasattr(ctypes, "windll"):
        return
    configured = False
    try:
        # PROCESS_PER_MONITOR_DPI_AWARE. E_ACCESSDENIED means another module
        # configured awareness already, which is safe to treat as configured.
        result = ctypes.windll.shcore.SetProcessDpiAwareness(2)
        configured = result in (0, -2147024891)
    except (AttributeError, OSError):
        pass
    if not configured:
        try:
            configured = bool(ctypes.windll.user32.SetProcessDPIAware())
        except (AttributeError, OSError):
            pass
    if not configured:
        raise RuntimeError("DPI_AWARENESS_CONFIGURATION_FAILED")
    _configured = True


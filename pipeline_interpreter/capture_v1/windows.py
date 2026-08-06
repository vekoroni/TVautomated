"""Minimal Windows window discovery with no input or trading capability."""

from __future__ import annotations

import ctypes
from ctypes import wintypes

from .contracts import WindowInfo
from .dpi import enable_per_monitor_dpi_awareness


def _title_matches(title: str, title_pattern: str) -> bool:
    """Match the Webull application, not files whose names contain Webull."""
    title_normalized = " ".join(title.casefold().split())
    pattern_normalized = " ".join(title_pattern.casefold().split())
    if pattern_normalized == "webull":
        # The desktop client uses this stable top-level title for its main and
        # auxiliary HWNDs.  A diagnostic such as webull_options_screen_map.png
        # must never be mistaken for the application merely because a viewer
        # places the filename in its own window title.
        return title_normalized == "webull desktop"
    return pattern_normalized in title_normalized


def discover_windows(title_pattern: str) -> tuple[WindowInfo, ...]:
    """Return visible top-level windows matching the title, without activating them."""
    if not hasattr(ctypes, "windll"):
        return ()
    enable_per_monitor_dpi_awareness()
    user32 = ctypes.windll.user32
    matches: list[WindowInfo] = []
    pattern = title_pattern.casefold()
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd: int, _lparam: int) -> bool:
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buffer = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buffer, length + 1)
        title = buffer.value
        if not _title_matches(title, pattern):
            return True
        rect = wintypes.RECT()
        user32.GetWindowRect(hwnd, ctypes.byref(rect))
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        matches.append(
            WindowInfo(
                handle=int(hwnd), title=title, process_id=int(pid.value),
                visible=bool(user32.IsWindowVisible(hwnd)),
                minimized=bool(user32.IsIconic(hwnd)),
                bounds=(rect.left, rect.top, rect.right, rect.bottom),
            )
        )
        return True

    user32.EnumWindows(callback_type(callback), 0)
    return tuple(matches)

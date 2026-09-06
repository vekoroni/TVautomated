"""Screenshot backend interface and Windows shadow implementation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .contracts import WindowInfo


class CaptureBackend(Protocol):
    def discover(self, title_pattern: str) -> tuple[WindowInfo, ...]: ...
    def capture_window(self, window: WindowInfo, destination: Path) -> str: ...


@dataclass(slots=True)
class WindowsShadowBackend:
    def discover(self, title_pattern: str) -> tuple[WindowInfo, ...]:
        from .windows import discover_windows
        return discover_windows(title_pattern)

    def capture_window(self, window: WindowInfo, destination: Path) -> str:
        if window.minimized:
            raise RuntimeError("WEBULL_MINIMIZED")
        left, top, right, bottom = window.bounds
        width, height = right - left, bottom - top
        if width <= 0 or height <= 0:
            raise RuntimeError("INVALID_WINDOW_BOUNDS")
        try:
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("PILLOW_NOT_INSTALLED") from exc

        # Capture the HWND itself. ImageGrab(bbox=...) samples desktop pixels and
        # therefore records any terminal or window covering Webull.
        import ctypes
        from ctypes import wintypes

        class BitmapInfoHeader(ctypes.Structure):
            _fields_ = (
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            )

        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32
        handle_type = ctypes.c_void_p
        user32.GetWindowDC.argtypes = (wintypes.HWND,)
        user32.GetWindowDC.restype = handle_type
        user32.PrintWindow.argtypes = (wintypes.HWND, handle_type, wintypes.UINT)
        user32.PrintWindow.restype = wintypes.BOOL
        user32.ReleaseDC.argtypes = (wintypes.HWND, handle_type)
        gdi32.CreateCompatibleDC.argtypes = (handle_type,)
        gdi32.CreateCompatibleDC.restype = handle_type
        gdi32.CreateCompatibleBitmap.argtypes = (handle_type, ctypes.c_int, ctypes.c_int)
        gdi32.CreateCompatibleBitmap.restype = handle_type
        gdi32.SelectObject.argtypes = (handle_type, handle_type)
        gdi32.SelectObject.restype = handle_type
        gdi32.GetDIBits.argtypes = (
            handle_type, handle_type, wintypes.UINT, wintypes.UINT,
            ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT,
        )
        gdi32.GetDIBits.restype = ctypes.c_int
        gdi32.DeleteObject.argtypes = (handle_type,)
        gdi32.DeleteDC.argtypes = (handle_type,)
        window_dc = user32.GetWindowDC(window.handle)
        memory_dc = gdi32.CreateCompatibleDC(window_dc)
        bitmap = gdi32.CreateCompatibleBitmap(window_dc, width, height)
        previous = gdi32.SelectObject(memory_dc, bitmap)
        try:
            # PW_RENDERFULLCONTENT asks Chromium/Electron windows to render their
            # complete client surface instead of sampling the foreground desktop.
            if not user32.PrintWindow(window.handle, memory_dc, 0x00000002):
                raise RuntimeError("PRINTWINDOW_FAILED")
            header = BitmapInfoHeader()
            header.biSize = ctypes.sizeof(BitmapInfoHeader)
            header.biWidth = width
            header.biHeight = -height  # top-down bitmap
            header.biPlanes = 1
            header.biBitCount = 32
            header.biCompression = 0
            buffer = ctypes.create_string_buffer(width * height * 4)
            lines = gdi32.GetDIBits(
                memory_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0
            )
            if lines != height:
                raise RuntimeError(f"GETDIBITS_FAILED:{lines}:{height}")
            image = Image.frombuffer(
                "RGB", (width, height), buffer, "raw", "BGRX", 0, 1
            )
            image.save(destination, format="PNG")
        finally:
            gdi32.SelectObject(memory_dc, previous)
            gdi32.DeleteObject(bitmap)
            gdi32.DeleteDC(memory_dc)
            user32.ReleaseDC(window.handle, window_dc)
        return "PRINTWINDOW_HWND"


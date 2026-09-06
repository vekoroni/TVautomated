"""Allowlisted Webull navigation primitives for interactive shadow mapping."""

from __future__ import annotations

import ctypes
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .contracts import WindowInfo
from .dpi import enable_per_monitor_dpi_awareness


@dataclass(frozen=True, slots=True)
class RelativePoint:
    x: float
    y: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.x <= 1.0 or not 0.0 <= self.y <= 1.0:
            raise ValueError("relative point must be within the Webull window")


@dataclass(frozen=True, slots=True)
class SafeZone:
    name: str
    left: float
    top: float
    right: float
    bottom: float

    def contains(self, point: RelativePoint) -> bool:
        return (
            self.left <= point.x <= self.right
            and self.top <= point.y <= self.bottom
        )


@dataclass(frozen=True, slots=True)
class WebullLayoutProfile:
    profile_id: str
    ticker_field: RelativePoint
    timeframe_selector: RelativePoint
    zones: tuple[SafeZone, ...]

    def require_allowed(self, control: str, point: RelativePoint) -> None:
        zone = next((item for item in self.zones if item.name == control), None)
        if zone is None or not zone.contains(point):
            raise RuntimeError(f"UNSAFE_NAVIGATION_TARGET:{control}")


# Calibrated from the accepted 1634x1046 Webull chart capture. Coordinates are
# relative so the profile scales with the application window.
ACCEPTED_CHART_PROFILE = WebullLayoutProfile(
    profile_id="webull_chart_accepted_20260725_v1",
    ticker_field=RelativePoint(0.302, 0.234),
    timeframe_selector=RelativePoint(0.468, 0.228),
    zones=(
        SafeZone("ticker_field", 0.275, 0.19, 0.45, 0.28),
        SafeZone("timeframe_selector", 0.44, 0.19, 0.51, 0.28),
    ),
)

FULL_CHART_INTERVAL_POINTS = {
    # Recalibrated from the 1966x1280 full Webull window after the 2026-07
    # desktop update, with the Watchlists sidebar visible.
    "5m": RelativePoint(0.292, 0.934),
    "15m": RelativePoint(0.318, 0.934),
    "1h": RelativePoint(0.370, 0.934),
    "4h": RelativePoint(0.389, 0.934),
    "daily": RelativePoint(0.408, 0.934),
}
FULL_CHART_INTERVAL_ZONE = SafeZone(
    "bottom_interval_bar", 0.28, 0.91, 0.42, 0.96
)
GLOBAL_STOCK_SEARCH_POINT = RelativePoint(0.602, 0.025)
GLOBAL_STOCK_SEARCH_ZONE = SafeZone(
    "global_stock_search", 0.52, 0.005, 0.68, 0.055
)
# Primary read-only Chart workspace tab. Every timeframe batch establishes
# this state explicitly instead of inheriting Options or another prior screen.
# Full-window coordinate: the accepted chart image begins at the tab strip,
# while GetWindowRect also includes Webull's application header above it.
CHART_WORKSPACE_POINT = RelativePoint(0.123, 0.046)
CHART_WORKSPACE_ZONE = SafeZone(
    "chart_workspace", 0.10, 0.035, 0.15, 0.06
)
TICKER_CHARACTER_DELAY_SECONDS = 0.08
FOREGROUND_STABLE_SAMPLES = 3
FOREGROUND_TIMEOUT_SECONDS = 2.0
CURSOR_POSITION_RETRIES = 3
CURSOR_RETRY_DELAY_SECONDS = 0.05
CURSOR_VERIFY_TOLERANCE_PX = 2


def ticker_virtual_keys(value: str) -> tuple[int, ...]:
    """Translate a validated ticker to an ordered sequence of Windows keys."""
    keys: list[int] = []
    for character in value.upper():
        if "A" <= character <= "Z" or "0" <= character <= "9":
            keys.append(ord(character))
        elif character == ".":
            keys.append(0xBE)
        elif character == "-":
            keys.append(0xBD)
        else:
            raise ValueError(f"UNSUPPORTED_TICKER_CHARACTER:{character}")
    return tuple(keys)


class NavigationDriver(Protocol):
    def foreground(self, window: WindowInfo) -> None: ...
    def is_foreground(self, window: WindowInfo) -> bool: ...
    def click_relative(self, window: WindowInfo, point: RelativePoint) -> None: ...
    def replace_text(self, value: str) -> None: ...
    def press_down(self) -> None: ...
    def press_enter(self) -> None: ...
    def capture_screen_region(self, window: WindowInfo, destination: Path) -> None: ...


def open_chart_workspace(
    *, window: WindowInfo, driver: NavigationDriver | None = None
) -> None:
    """Establish the Chart workspace before selecting any timeframe."""
    if not CHART_WORKSPACE_ZONE.contains(CHART_WORKSPACE_POINT):
        raise RuntimeError("UNSAFE_NAVIGATION_TARGET:chart_workspace")
    driver = driver or WindowsNavigationDriver()
    driver.foreground(window)
    deadline = time.monotonic() + 2.0
    while not driver.is_foreground(window):
        if time.monotonic() >= deadline:
            raise RuntimeError("WEBULL_FOREGROUND_NOT_CONFIRMED")
        time.sleep(0.05)
    driver.click_relative(window, CHART_WORKSPACE_POINT)
    time.sleep(1.5)


class WindowsNavigationDriver:
    @staticmethod
    def _foreground_handle(user32) -> int:
        # ctypes otherwise assumes a 32-bit c_int return and can truncate HWND
        # values in a 64-bit Python process.
        user32.GetForegroundWindow.restype = ctypes.c_void_p
        return int(user32.GetForegroundWindow() or 0)

    def foreground(self, window: WindowInfo) -> None:
        enable_per_monitor_dpi_awareness()
        user32 = ctypes.windll.user32
        if not user32.SetForegroundWindow(ctypes.c_void_p(window.handle)):
            raise RuntimeError("WEBULL_FOREGROUND_FAILED")

    def is_foreground(self, window: WindowInfo) -> bool:
        user32 = ctypes.windll.user32
        return self._foreground_handle(user32) == window.handle

    @staticmethod
    def _wait_for_stable_foreground(user32, handle: int) -> None:
        """Require consecutive foreground observations before any mouse action."""
        deadline = time.monotonic() + FOREGROUND_TIMEOUT_SECONDS
        stable = 0
        while time.monotonic() < deadline:
            if WindowsNavigationDriver._foreground_handle(user32) == handle:
                stable += 1
                if stable >= FOREGROUND_STABLE_SAMPLES:
                    return
            else:
                stable = 0
            time.sleep(0.05)
        raise RuntimeError("WEBULL_FOREGROUND_NOT_STABLE")

    @staticmethod
    def _fresh_window_bounds(user32, handle: int) -> tuple[int, int, int, int]:
        """Read current HWND bounds instead of trusting discovery-time geometry."""
        class Rect(ctypes.Structure):
            _fields_ = (
                ("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long),
            )

        rect = Rect()
        hwnd = ctypes.c_void_p(handle)
        if not user32.IsWindow(hwnd) or not user32.GetWindowRect(
            hwnd, ctypes.byref(rect)
        ):
            raise RuntimeError("WEBULL_WINDOW_BOUNDS_REFRESH_FAILED")
        bounds = (int(rect.left), int(rect.top), int(rect.right), int(rect.bottom))
        if bounds[2] <= bounds[0] or bounds[3] <= bounds[1]:
            raise RuntimeError("WEBULL_WINDOW_BOUNDS_INVALID")
        return bounds

    @staticmethod
    def _cursor_positions(user32) -> tuple[tuple[int, int] | None, tuple[int, int] | None]:
        class Point(ctypes.Structure):
            _fields_ = (("x", ctypes.c_long), ("y", ctypes.c_long))

        logical_point = Point()
        logical = (
            (int(logical_point.x), int(logical_point.y))
            if user32.GetCursorPos(ctypes.byref(logical_point)) else None
        )
        physical = None
        try:
            physical_point = Point()
            if user32.GetPhysicalCursorPos(ctypes.byref(physical_point)):
                physical = (int(physical_point.x), int(physical_point.y))
        except (AttributeError, OSError):
            pass
        return logical, physical

    @staticmethod
    def _cursor_at(user32, x: int, y: int) -> bool:
        return any(
            position is not None
            and abs(position[0] - x) <= CURSOR_VERIFY_TOLERANCE_PX
            and abs(position[1] - y) <= CURSOR_VERIFY_TOLERANCE_PX
            for position in WindowsNavigationDriver._cursor_positions(user32)
        )

    @staticmethod
    def _send_input_move(user32, x: int, y: int) -> None:
        """Move to a physical virtual-desktop point using absolute SendInput."""
        class MouseInput(ctypes.Structure):
            _fields_ = (
                ("dx", ctypes.c_long), ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong), ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong), ("dwExtraInfo", ctypes.c_void_p),
            )

        class InputUnion(ctypes.Union):
            _fields_ = (("mi", MouseInput),)

        class Input(ctypes.Structure):
            _anonymous_ = ("union",)
            _fields_ = (("type", ctypes.c_ulong), ("union", InputUnion))

        virtual_left = int(user32.GetSystemMetrics(76))
        virtual_top = int(user32.GetSystemMetrics(77))
        virtual_width = int(user32.GetSystemMetrics(78))
        virtual_height = int(user32.GetSystemMetrics(79))
        if virtual_width <= 1 or virtual_height <= 1:
            raise RuntimeError("VIRTUAL_DESKTOP_BOUNDS_INVALID")
        dx = round((x - virtual_left) * 65535 / (virtual_width - 1))
        dy = round((y - virtual_top) * 65535 / (virtual_height - 1))
        move = Input(
            type=0,
            mi=MouseInput(dx, dy, 0, 0x0001 | 0x4000 | 0x8000, 0, None),
        )
        sent = int(user32.SendInput(1, ctypes.byref(move), ctypes.sizeof(Input)))
        if sent != 1:
            raise RuntimeError(f"SENDINPUT_MOVE_FAILED:{sent}/1")

    def click_relative(self, window: WindowInfo, point: RelativePoint) -> None:
        enable_per_monitor_dpi_awareness()
        user32 = ctypes.windll.user32
        if not self.is_foreground(window):
            self.foreground(window)
        self._wait_for_stable_foreground(user32, window.handle)
        left, top, right, bottom = self._fresh_window_bounds(
            user32, window.handle
        )
        x = round(left + (right - left) * point.x)
        y = round(top + (bottom - top) * point.y)
        virtual_left = int(user32.GetSystemMetrics(76))
        virtual_top = int(user32.GetSystemMetrics(77))
        virtual_right = virtual_left + int(user32.GetSystemMetrics(78))
        virtual_bottom = virtual_top + int(user32.GetSystemMetrics(79))
        if not (
            virtual_left <= x < virtual_right
            and virtual_top <= y < virtual_bottom
        ):
            raise RuntimeError(
                "CURSOR_TARGET_OUTSIDE_VIRTUAL_DESKTOP:"
                f"target={x},{y}:window={left},{top},{right},{bottom}:"
                f"virtual={virtual_left},{virtual_top},{virtual_right},{virtual_bottom}"
            )
        positioned = False
        set_cursor_result = 0
        for _attempt in range(CURSOR_POSITION_RETRIES):
            # GetWindowRect, the HWND capture backend, SetCursorPos and
            # GetCursorPos all operate in the process's DPI-aware physical
            # screen coordinate space.  Do not rescale the absolute target.
            set_cursor_result = int(bool(user32.SetCursorPos(x, y)))
            if set_cursor_result and self._cursor_at(user32, x, y):
                positioned = True
                break
            time.sleep(CURSOR_RETRY_DELAY_SECONDS)
        if self._foreground_handle(user32) != window.handle:
            raise RuntimeError("WEBULL_FOREGROUND_LOST_BEFORE_CLICK")
        if not positioned:
            # Webull/Windows can reject SetCursorPos after the application takes
            # foreground.  SendInput remains valid, but it must receive the same
            # physical target used to derive the controlâ€”not a DPI-scaled point.
            self._send_input_move(user32, x, y)
            positioned = self._cursor_at(user32, x, y)
        if not positioned:
            logical, physical = self._cursor_positions(user32)
            raise RuntimeError(
                "CURSOR_POSITION_FAILED_AFTER_SENDINPUT:"
                f"target={x},{y}:set_cursor_result={set_cursor_result}:"
                f"logical={logical}:physical={physical}:"
                f"window={left},{top},{right},{bottom}"
            )
        user32.mouse_event(0x0002, 0, 0, 0, 0)  # LEFTDOWN
        user32.mouse_event(0x0004, 0, 0, 0, 0)  # LEFTUP

    def capture_screen_region(self, window: WindowInfo, destination: Path) -> None:
        # Use the HWND-bound backend so another foreground window, taskbar state,
        # or desktop compositor cannot replace Webull with unrelated/blank pixels.
        from .backend import WindowsShadowBackend

        WindowsShadowBackend().capture_window(window, destination)

    @staticmethod
    def _tap_virtual_key(key: int) -> None:
        user32 = ctypes.windll.user32
        user32.keybd_event(key, 0, 0, 0)
        user32.keybd_event(key, 0, 0x0002, 0)

    def replace_text(self, value: str) -> None:
        user32 = ctypes.windll.user32
        user32.keybd_event(0x11, 0, 0, 0)  # CTRL down
        self._tap_virtual_key(0x41)  # A
        user32.keybd_event(0x11, 0, 0x0002, 0)  # CTRL up
        # Webull's global search can reorder characters when synthetic key events
        # arrive in the same UI tick. Pace every key so the requested ticker is
        # processed in deterministic left-to-right order.
        time.sleep(TICKER_CHARACTER_DELAY_SECONDS)
        for key in ticker_virtual_keys(value):
            self._tap_virtual_key(key)
            time.sleep(TICKER_CHARACTER_DELAY_SECONDS)

    def press_enter(self) -> None:
        self._tap_virtual_key(0x0D)

    def press_down(self) -> None:
        self._tap_virtual_key(0x28)


def map_timeframe_menu(
    *,
    window: WindowInfo,
    output_directory: Path,
    profile: WebullLayoutProfile = ACCEPTED_CHART_PROFILE,
    driver: NavigationDriver | None = None,
) -> tuple[Path, Path]:
    """Open only the timeframe menu and capture a diagnostic mapping image."""
    driver = driver or WindowsNavigationDriver()
    profile.require_allowed("timeframe_selector", profile.timeframe_selector)
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(output_directory)
    output_directory.mkdir(parents=True)
    image_path = output_directory / "webull_timeframe_menu_map.png"
    manifest_path = output_directory / "navigation_map.json"
    try:
        driver.foreground(window)
        deadline = time.monotonic() + 2.0
        while not driver.is_foreground(window):
            if time.monotonic() >= deadline:
                raise RuntimeError("WEBULL_FOREGROUND_NOT_CONFIRMED")
            time.sleep(0.05)
        # Windows may consume a click issued during the foreground transition.
        time.sleep(0.35)
        driver.click_relative(window, profile.timeframe_selector)
        time.sleep(0.75)
        driver.capture_screen_region(window, image_path)
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "capture_v1.navigation_map.1",
                    "profile_id": profile.profile_id,
                    "action": "OPEN_TIMEFRAME_MENU",
                    "allowed_control": "timeframe_selector",
                    "point": {
                        "x": profile.timeframe_selector.x,
                        "y": profile.timeframe_selector.y,
                    },
                    "diagnostic_image": image_path.name,
                    "pipeline_published": False,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return image_path, manifest_path
    except Exception:
        if image_path.exists():
            image_path.unlink()
        if manifest_path.exists():
            manifest_path.unlink()
        try:
            output_directory.rmdir()
        except OSError:
            pass
        raise


def select_bottom_timeframe(
    *,
    window: WindowInfo,
    timeframe: str,
    output_directory: Path,
    driver: NavigationDriver | None = None,
) -> tuple[Path, Path]:
    """Select one allowlisted full-chart interval and capture diagnostic evidence."""
    normalized = timeframe.strip().lower()
    point = FULL_CHART_INTERVAL_POINTS.get(normalized)
    if point is None:
        raise ValueError(f"UNSUPPORTED_TIMEFRAME:{timeframe}")
    if not FULL_CHART_INTERVAL_ZONE.contains(point):
        raise RuntimeError(f"UNSAFE_NAVIGATION_TARGET:bottom_interval_bar:{normalized}")
    driver = driver or WindowsNavigationDriver()
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(output_directory)
    output_directory.mkdir(parents=True)
    image_path = output_directory / f"webull_{normalized}_selection.png"
    manifest_path = output_directory / "timeframe_selection.json"
    try:
        driver.foreground(window)
        deadline = time.monotonic() + 2.0
        while not driver.is_foreground(window):
            if time.monotonic() >= deadline:
                raise RuntimeError("WEBULL_FOREGROUND_NOT_CONFIRMED")
            time.sleep(0.05)
        time.sleep(0.35)
        driver.click_relative(window, point)
        time.sleep(1.0)
        driver.capture_screen_region(window, image_path)
        manifest_path.write_text(
            json.dumps(
                {
                    "schema_version": "capture_v1.timeframe_selection.1",
                    "profile_id": "webull_full_chart_bottom_bar_20260725_v1",
                    "action": "SELECT_BOTTOM_TIMEFRAME",
                    "timeframe": normalized,
                    "allowed_control": "bottom_interval_bar",
                    "point": {"x": point.x, "y": point.y},
                    "diagnostic_image": image_path.name,
                    "verification": "VISUAL_REVIEW_REQUIRED",
                    "pipeline_published": False,
                },
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )
        return image_path, manifest_path
    except Exception:
        if image_path.exists():
            image_path.unlink()
        if manifest_path.exists():
            manifest_path.unlink()
        try:
            output_directory.rmdir()
        except OSError:
            pass
        raise


def switch_ticker_for_visual_review(
    *,
    window: WindowInfo,
    ticker: str,
    output_directory: Path,
    driver: NavigationDriver | None = None,
) -> tuple[Path, Path]:
    """Switch through global stock search and emit non-pipeline diagnostic evidence."""
    normalized = ticker.strip().upper()
    if not normalized or not normalized.replace(".", "").replace("-", "").isalnum():
        raise ValueError("INVALID_TICKER")
    if len(normalized) > 10:
        raise ValueError("INVALID_TICKER_LENGTH")
    if not GLOBAL_STOCK_SEARCH_ZONE.contains(GLOBAL_STOCK_SEARCH_POINT):
        raise RuntimeError("UNSAFE_NAVIGATION_TARGET:global_stock_search")
    driver = driver or WindowsNavigationDriver()
    output_directory = output_directory.resolve()
    if output_directory.exists():
        raise FileExistsError(output_directory)
    output_directory.mkdir(parents=True)
    image_path = output_directory / f"webull_{normalized}_ticker_switch.png"
    manifest_path = output_directory / "ticker_switch.json"
    try:
        driver.foreground(window)
        deadline = time.monotonic() + 2.0
        while not driver.is_foreground(window):
            if time.monotonic() >= deadline:
                raise RuntimeError("WEBULL_FOREGROUND_NOT_CONFIRMED")
            time.sleep(0.05)
        time.sleep(0.35)
        driver.click_relative(window, GLOBAL_STOCK_SEARCH_POINT)
        driver.replace_text(normalized)
        time.sleep(1.0)
        # Webull places the exact symbol at the active/default search result.
        # Pressing Down advances to the next fuzzy match (for example, an NFLX
        # request was changed to NFXL). Submit the exact active result directly.
        driver.press_enter()
        time.sleep(2.0)
        driver.capture_screen_region(window, image_path)
        from .privacy_crop import crop_chart_in_place
        from .validation import validate_png

        privacy_crop = crop_chart_in_place(image_path)
        validation = validate_png(image_path)
        if not validation.valid:
            raise RuntimeError(
                "TICKER_DIAGNOSTIC_INVALID:" + "|".join(validation.findings)
            )
        manifest_path.write_text(json.dumps({
            "schema_version": "capture_v1.ticker_switch.1",
            "action": "GLOBAL_STOCK_SEARCH",
            "requested_ticker": normalized,
            "allowed_control": "global_stock_search",
            "diagnostic_image": image_path.name,
            "verification": "VISUAL_REVIEW_REQUIRED",
            "privacy_crop": privacy_crop,
            "uncropped_image_retained": False,
            "pipeline_published": False,
        }, indent=2, sort_keys=True), encoding="utf-8")
        return image_path, manifest_path
    except Exception:
        if image_path.exists():
            image_path.unlink()
        if manifest_path.exists():
            manifest_path.unlink()
        try:
            output_directory.rmdir()
        except OSError:
            pass
        raise


import ctypes
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from pipeline_interpreter.capture_v1.contracts import WindowInfo
from pipeline_interpreter.capture_v1.navigation import (
    ACCEPTED_CHART_PROFILE,
    GLOBAL_STOCK_SEARCH_POINT,
    RelativePoint,
    SafeZone,
    WebullLayoutProfile,
    WindowsNavigationDriver,
    map_timeframe_menu,
    select_bottom_timeframe,
)


class FakeDriver:
    def __init__(self):
        self.actions = []

    def foreground(self, window):
        self.actions.append(("foreground", window.handle))

    def is_foreground(self, _window):
        self.actions.append(("foreground_check", True))
        return True

    def click_relative(self, _window, point):
        self.actions.append(("click", point))

    def capture_screen_region(self, _window, destination):
        self.actions.append(("capture", destination.name))
        Image.new("RGB", (1200, 800), "navy").save(destination, "PNG")
    def replace_text(self, value):
        self.actions.append(("replace_text", value))
    def press_enter(self):
        self.actions.append(("enter",))
    def press_down(self):
        self.actions.append(("down",))


def window():
    return WindowInfo(1, "Webull", 10, True, False, (10, 20, 1210, 820))


class NavigationMappingTests(unittest.TestCase):
    def test_mapping_clicks_only_allowlisted_timeframe_control(self):
        with tempfile.TemporaryDirectory() as root:
            driver = FakeDriver()
            image, manifest = map_timeframe_menu(
                window=window(),
                output_directory=Path(root) / "map",
                driver=driver,
            )
            self.assertTrue(image.is_file())
            self.assertTrue(manifest.is_file())
            self.assertEqual(driver.actions[0], ("foreground", 1))
            self.assertEqual(
                driver.actions[2], ("click", ACCEPTED_CHART_PROFILE.timeframe_selector)
            )

    def test_profile_rejects_point_outside_allowlisted_zone(self):
        unsafe = WebullLayoutProfile(
            "unsafe",
            ticker_field=RelativePoint(0.3, 0.23),
            timeframe_selector=RelativePoint(0.9, 0.9),
            zones=(SafeZone("timeframe_selector", 0.44, 0.19, 0.51, 0.28),),
        )
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(RuntimeError, "UNSAFE_NAVIGATION_TARGET"):
                map_timeframe_menu(
                    window=window(),
                    output_directory=Path(root) / "map",
                    profile=unsafe,
                    driver=FakeDriver(),
                )

    def test_direct_bottom_bar_selects_allowlisted_4h_only(self):
        with tempfile.TemporaryDirectory() as root:
            driver = FakeDriver()
            image, manifest = select_bottom_timeframe(
                window=window(),
                timeframe="4h",
                output_directory=Path(root) / "4h",
                driver=driver,
            )
            self.assertTrue(image.is_file())
            self.assertTrue(manifest.is_file())
            click = next(action for action in driver.actions if action[0] == "click")
            self.assertEqual(click[1], RelativePoint(0.389, 0.934))

    def test_direct_bottom_bar_rejects_unknown_timeframe(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaisesRegex(ValueError, "UNSUPPORTED_TIMEFRAME"):
                select_bottom_timeframe(
                    window=window(),
                    timeframe="2h",
                    output_directory=Path(root) / "2h",
                    driver=FakeDriver(),
                )


class FakeUser32:
    def __init__(self, *, cursor_moves=True):
        self.cursor_moves = cursor_moves
        self.cursor = (100, 100)
        self.set_cursor_calls = []
        self.mouse_events = []

    def IsWindow(self, _handle):
        return 1

    def GetWindowRect(self, _handle, rect_pointer):
        rect = rect_pointer._obj
        rect.left, rect.top, rect.right, rect.bottom = -13, -13, 3253, 2077
        return 1

    def GetSystemMetrics(self, index):
        return {76: -3840, 77: 0, 78: 7106, 79: 2160}[index]

    def SetCursorPos(self, x, y):
        self.set_cursor_calls.append((x, y))
        if self.cursor_moves:
            self.cursor = (x, y)
            return 1
        return 0

    def GetCursorPos(self, point_pointer):
        point_pointer._obj.x, point_pointer._obj.y = self.cursor
        return 1

    def GetPhysicalCursorPos(self, point_pointer):
        point_pointer._obj.x, point_pointer._obj.y = self.cursor
        return 1

    def mouse_event(self, event, *_args):
        self.mouse_events.append(event)


class WindowsNavigationDriverTests(unittest.TestCase):
    def _driver(self, user32):
        driver = WindowsNavigationDriver()
        driver.is_foreground = lambda _window: True
        driver._wait_for_stable_foreground = lambda _user32, _handle: None
        driver._foreground_handle = lambda _user32: 123
        return driver

    def test_click_uses_unscaled_physical_window_coordinate(self):
        user32 = FakeUser32()
        driver = self._driver(user32)
        fake_windll = type("Windll", (), {"user32": user32})()
        target_window = WindowInfo(
            123, "Webull", 10, True, False, (-13, -13, 3253, 2077)
        )
        with patch(
            "pipeline_interpreter.capture_v1.navigation.enable_per_monitor_dpi_awareness"
        ), patch.object(ctypes, "windll", fake_windll, create=True):
            driver.click_relative(target_window, GLOBAL_STOCK_SEARCH_POINT)

        self.assertEqual(user32.set_cursor_calls, [(1953, 39)])
        self.assertEqual(user32.mouse_events, [0x0002, 0x0004])

    def test_click_fails_closed_without_sending_mouse_click(self):
        user32 = FakeUser32(cursor_moves=False)
        driver = self._driver(user32)
        driver._send_input_move = lambda _user32, _x, _y: None
        fake_windll = type("Windll", (), {"user32": user32})()
        target_window = WindowInfo(
            123, "Webull", 10, True, False, (-13, -13, 3253, 2077)
        )
        with patch(
            "pipeline_interpreter.capture_v1.navigation.enable_per_monitor_dpi_awareness"
        ), patch.object(ctypes, "windll", fake_windll, create=True), patch(
            "pipeline_interpreter.capture_v1.navigation.time.sleep"
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                r"CURSOR_POSITION_FAILED_AFTER_SENDINPUT:target=1953,39",
            ):
                driver.click_relative(target_window, GLOBAL_STOCK_SEARCH_POINT)

        self.assertEqual(len(user32.set_cursor_calls), 3)
        self.assertEqual(user32.mouse_events, [])

    def test_send_input_fallback_uses_physical_target_and_verifies_before_click(self):
        user32 = FakeUser32(cursor_moves=False)
        driver = self._driver(user32)
        fallback_targets = []

        def fallback(_user32, x, y):
            fallback_targets.append((x, y))
            user32.cursor = (x, y)

        driver._send_input_move = fallback
        fake_windll = type("Windll", (), {"user32": user32})()
        target_window = WindowInfo(
            123, "Webull", 10, True, False, (-13, -13, 3253, 2077)
        )
        with patch(
            "pipeline_interpreter.capture_v1.navigation.enable_per_monitor_dpi_awareness"
        ), patch.object(ctypes, "windll", fake_windll, create=True), patch(
            "pipeline_interpreter.capture_v1.navigation.time.sleep"
        ):
            driver.click_relative(target_window, GLOBAL_STOCK_SEARCH_POINT)

        self.assertEqual(fallback_targets, [(1953, 39)])
        self.assertEqual(user32.mouse_events, [0x0002, 0x0004])

if __name__ == "__main__":
    unittest.main()

"""A failed Lab refresh must never leave the full-screen loader over an already-loaded page.

`#loader` is position:fixed, inset:0, z-index 9999. `showLoaderError` used to set the error
text and leave the overlay up, so after any failed refresh (a run changing while the
pipeline writes, a partial run in the selector) every click on the page was swallowed.
"""
from __future__ import annotations

from pathlib import Path

PAGE = Path(__file__).resolve().parents[1] / "intelligence-lab" / "static" / "index.html"


def test_loader_error_is_dismissable_and_auto_hides_when_a_run_is_already_displayed():
    html = PAGE.read_text(encoding="utf-8")
    body = html.split("function showLoaderError(msg)")[1].split("\nfunction ")[0]
    assert "loader-dismiss" in body
    assert "RUN_DATA" in body and "classList.add('hidden')" in body
    assert 'id="loader-dismiss"' in html

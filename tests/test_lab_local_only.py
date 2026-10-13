"""The Lab server listens on this PC only (ACK, 13 Oct 2026).

Business rule: until the secure page (login, HTTPS, same-origin, protected write endpoints) is built, the Lab is not
reachable from other devices on the network - it binds to the loopback address, never to all interfaces.
"""
import ast
from pathlib import Path

LAB = Path(__file__).resolve().parents[1] / "intelligence-lab" / "intelligence_lab.py"


def _run_calls():
    tree = ast.parse(LAB.read_text(encoding="utf-8-sig"))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "run"
            and getattr(n.func.value, "id", "") == "app"]


def test_the_lab_binds_to_loopback_only():
    calls = _run_calls()
    assert calls, "app.run not found"
    for call in calls:
        host = next((k.value.value for k in call.keywords if k.arg == "host"), None)
        assert host == "127.0.0.1", host


def test_the_lab_page_is_the_root_url_and_no_page_url_says_review():
    # ACK 13 Oct 2026: "remove the word review" - the page is served at http://localhost:5002/ only.
    tree = ast.parse(LAB.read_text(encoding="utf-8-sig"))
    routes = [d.args[0].value for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
              for d in n.decorator_list if isinstance(d, ast.Call) and getattr(d.func, "attr", "") == "route"
              and d.args and isinstance(d.args[0], ast.Constant)]
    assert "/" in routes
    assert not [r for r in routes if not r.startswith("/api/") and "review" in r.lower()]

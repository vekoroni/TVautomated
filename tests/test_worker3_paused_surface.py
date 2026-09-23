from pathlib import Path

from worker3.integration.activation import load_provider_release


ROOT = Path(__file__).resolve().parents[1]


def test_checked_in_worker3_release_is_paused() -> None:
    release = load_provider_release(ROOT / "contracts" / "worker3_provider_release_v1.json")
    assert release.enabled is False
    assert release.lab_projection_enabled is False


def test_lab_exposes_interpreter_without_worker3_controls() -> None:
    html = (ROOT / "intelligence-lab" / "static" / "index.html").read_text(encoding="utf-8")
    assert 'id="interpreter-launch"' in html
    assert 'id="worker3-launch"' not in html
    assert "data-worker3-ticker" not in html
    assert "worker3-controls.js" not in html

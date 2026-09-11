"""Optional advisory-only Flask route mount for Worker 3 reports."""
from pathlib import Path

from ..adapters.lab_reports import AnalystReports, register_lab_routes
from ..domain import ContractError
from .activation import load_provider_release


def install_worker3_lab_projection(app, repository_root, release_path=None):
    root = Path(repository_root).resolve(strict=True)
    release_path = Path(release_path or root / "contracts" / "worker3_provider_release_v1.json")
    release = load_provider_release(release_path)
    if not release.enabled or not release.lab_projection_enabled:
        return None
    data_root = (root / "data" / "worker3").resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    reports_path = (data_root / "analyst_reports.sqlite").resolve()
    if not reports_path.is_relative_to(data_root):
        raise ContractError("Worker 3 report store escaped approved directory")
    reports = AnalystReports(reports_path)
    register_lab_routes(app, reports)
    return reports

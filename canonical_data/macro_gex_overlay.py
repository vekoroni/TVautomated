"""Deterministic completed-session GEX overlay for the advisory macro packet."""

from __future__ import annotations

from datetime import date
import csv
import hashlib
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

from canonical_data.macro_publication import publish_if_authoritative


def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
    temporary = path.with_suffix(path.suffix + f".tmp-{uuid4().hex}")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True, allow_nan=False),
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _float(value: Any) -> float | None:
    try:
        return float(value) if value not in {None, ""} else None
    except (TypeError, ValueError):
        return None


def _score(regime: str, net_gex: float) -> float:
    state = str(regime).strip().upper()
    if state == "POSITIVE" or net_gex > 0:
        return 0.70
    if state == "NEGATIVE" or net_gex < 0:
        return 0.30
    return 0.50


def load_completed_gex_overlay(
    *,
    proxy_path: Path | str,
    manifest_path: Path | str,
    required_session: date,
) -> dict[str, Any]:
    """Validate and return one deterministic completed-session GEX overlay."""

    proxy_file = Path(proxy_path)
    manifest_file = Path(manifest_path)
    manifest = json.loads(manifest_file.read_text(encoding="utf-8-sig"))
    if str(manifest.get("status") or "").upper() != "COMPLETE":
        raise ValueError("GEX manifest is not complete")
    digest = hashlib.sha256(proxy_file.read_bytes()).hexdigest()
    if digest != str(manifest.get("proxy_sha256") or ""):
        raise ValueError("GEX proxy hash does not match its manifest")
    by_strike_path = Path(str(manifest.get("by_strike_path") or ""))
    if not by_strike_path.is_file():
        raise ValueError("GEX by-strike evidence is unavailable")
    by_strike_digest = hashlib.sha256(by_strike_path.read_bytes()).hexdigest()
    if by_strike_digest != str(manifest.get("by_strike_sha256") or ""):
        raise ValueError("GEX by-strike hash does not match its manifest")
    if str(manifest.get("session_date") or "") != required_session.isoformat():
        raise ValueError("GEX manifest is not for the required completed session")
    with proxy_file.open("r", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    by_ticker = {str(row.get("Ticker") or "").upper(): row for row in rows}
    if set(by_ticker) != {"SPY", "QQQ"}:
        raise ValueError("GEX proxy must contain exactly SPY and QQQ")
    for ticker, row in by_ticker.items():
        if str(row.get("Date") or "") != required_session.isoformat():
            raise ValueError(f"{ticker} GEX row is not for the required session")
        if str(row.get("Data_Status") or "").upper() != "OK":
            raise ValueError(f"{ticker} GEX row is not usable")
    spy = by_ticker["SPY"]
    net_gex = _float(spy.get("Net_GEX_Bn"))
    if net_gex is None:
        raise ValueError("SPY GEX has no numeric net exposure")
    return {
        "regime": str(spy.get("Regime") or ""),
        "net_gex_bn": net_gex,
        "gamma_flip": _float(spy.get("Gamma_Flip")),
        "stress": str(spy.get("GEX_Stress") or ""),
        "contracts_used": _float(spy.get("Contracts_Used")),
        "score": _score(str(spy.get("Regime") or ""), net_gex),
        "data_mode": "COMPLETED_SESSION",
        "data_status": "CONFIRMED",
        "session_date": required_session.isoformat(),
        "run_id": manifest.get("run_id"),
        "dataset_ids": list(manifest.get("dataset_ids") or ()),
        "proxy_sha256": digest,
        "by_strike_sha256": by_strike_digest,
        "source": "canonical_phantom_projection|avshunter_gex_proxy.csv",
        "authority": "ADVISORY_ONLY",
        "greek_derivation": spy.get("Greek_Derivation"),
        "greek_model_disclosure": spy.get("Greek_Model_Disclosure"),
        "greek_computed_contracts": _float(spy.get("Greek_Computed_Contracts")),
        "greek_unresolved_contracts": _float(spy.get("Greek_Unresolved_Contracts")),
    }


def materialize_runtime_macro(
    *,
    base_macro_path: Path | str,
    output_path: Path | str,
    required_session: date,
    overlay: dict[str, Any] | None,
    source_state: str,
    unavailable_reason: str = "",
) -> Path:
    """Create a run-scoped macro view without mutating the governed base packet."""

    base_path = Path(base_macro_path)
    target = Path(output_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    macro = json.loads(base_path.read_text(encoding="utf-8-sig"))
    base_hash = hashlib.sha256(base_path.read_bytes()).hexdigest()
    extras = macro.setdefault("extras", {})
    if overlay is not None:
        extras["gex"] = dict(overlay)
        macro["gex_regime_score"] = overlay.get("score")
        macro["gex_available"] = True
    else:
        extras["gex"] = {
            "state": "UNAVAILABLE_REQUIRED_SESSION",
            "session_date": required_session.isoformat(),
            "reason": str(unavailable_reason),
            "authority": "ADVISORY_ONLY",
        }
        macro["gex_regime_score"] = None
        macro["gex_available"] = False
    macro["runtime_gex_sync"] = {
        "contract_version": "runtime_gex_sync_v1",
        "required_session": required_session.isoformat(),
        "source_state": source_state,
        "base_macro_path": str(base_path.resolve()),
        "base_macro_sha256": base_hash,
        "authority": "ADVISORY_ONLY",
    }
    _atomic_json(target, macro)
    return target


def apply_completed_gex_overlay(
    *,
    macro_path: Path | str,
    proxy_path: Path | str,
    manifest_path: Path | str,
    required_session: date,
) -> dict[str, Any]:
    """Replace only the GEX advisory block after lineage/freshness validation."""

    macro_file = Path(macro_path)
    macro = json.loads(macro_file.read_text(encoding="utf-8-sig"))
    overlay = load_completed_gex_overlay(
        proxy_path=proxy_path,
        manifest_path=manifest_path,
        required_session=required_session,
    )
    extras = macro.setdefault("extras", {})
    extras["gex"] = overlay
    macro["gex_regime_score"] = overlay["score"]
    macro["gex_available"] = True
    _atomic_json(macro_file, macro)
    publish_if_authoritative(macro_file)
    return dict(overlay)


def invalidate_gex_overlay(
    *, macro_path: Path | str, required_session: date, reason: str
) -> None:
    """Prevent a prior-session numeric GEX value from masquerading as current."""

    macro_file = Path(macro_path)
    if not macro_file.is_file():
        return
    macro = json.loads(macro_file.read_text(encoding="utf-8-sig"))
    macro["gex_regime_score"] = None
    macro["gex_available"] = False
    extras = macro.setdefault("extras", {})
    extras["gex"] = {
        "state": "UNAVAILABLE_REQUIRED_SESSION",
        "session_date": required_session.isoformat(),
        "reason": str(reason),
        "authority": "ADVISORY_ONLY",
    }
    flags = macro.setdefault("conflict_flags", [])
    if not isinstance(flags, list):
        flags = [str(flags)]
        macro["conflict_flags"] = flags
    marker = f"DATA_COVERAGE_INCOMPLETE: [gex] required session {required_session.isoformat()} unavailable"
    if marker not in flags:
        flags.append(marker)
    _atomic_json(macro_file, macro)
    publish_if_authoritative(macro_file)


__all__ = [
    "apply_completed_gex_overlay",
    "invalidate_gex_overlay",
    "load_completed_gex_overlay",
    "materialize_runtime_macro",
]

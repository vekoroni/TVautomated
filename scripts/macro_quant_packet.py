#!/usr/bin/env python3
"""
AVSHUNTER macro quant packet helper.

Builds the Phase 3 machine-readable macro baton from the existing
macro_contract_v1_0 JSON without replacing the raw macro narrative.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Optional


MACRO_QUANT_CONTRACT_VERSION = "macro_quant_contract_v1"

FRESH_HOURS = 20.0
EXPIRED_HOURS = 72.0

MISSING_TOKENS = {"", "NONE", "NULL", "NAN", "N/A", "UNKNOWN", "MISSING"}

MACRO_QUANT_CSV_FIELDS = [
    "macro_packet_id",
    "macro_packet_sha256",
    "macro_source_fingerprint",
    "macro_as_of_utc",
    "macro_session_date",
    "macro_plain_language_advisory",
    "macro_authority",
    "macro_source_path",
    "macro_contract_version",
    "macro_generated_at_utc",
    "macro_normalised_at_utc",
    "macro_age_hours",
    "macro_freshness_status",
    "macro_confidence",
    "macro_data_quality",
    "macro_regime_label",
    "macro_regime_sub_state",
    "regime_drift_status",
    "regime_distribution_bull",
    "regime_distribution_neutral",
    "regime_distribution_bear",
    "risk_on_off_score",
    "macro_conviction_score",
    "net_liquidity_score",
    "liquidity_pulse",
    "liquidity_risk_flag",
    "vix_level",
    "vix_regime_label",
    "vix_regime_score",
    "vix_contango",
    "vix_structure_label",
    "vol_mode",
    "rates_impulse",
    "usd_state",
    "credit_state",
    "credit_risk_score",
    "gex_regime_score",
    "dealer_gamma_state",
    "gamma_risk_flag",
    "sector_rotation_state",
    "leading_sectors",
    "lagging_sectors",
    "avoid_sectors",
    "preferred_sectors",
    "sector_tilt_score",
    "ticker_sector_alignment",
    "ticker_sector_alignment_score",
    "macro_preferred_horizon",
    "horizon_pressure",
    "primary_bucket",
    "bucket_clarity_scores",
    "equity_drawer_active",
    "macro_execution_caution",
    "macro_conflict_flags",
    "macro_active_conflict_flags",
    "macro_resolved_conflict_flags",
    "bond_macro_flag",
    "bond_trade_go",
    "bond_macro_score",
    "auction_spread_risk",
    "credit_warning",
    "breakeven_adjustment_pct",
]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_iso(dt: Optional[datetime] = None) -> str:
    value = dt or utc_now()
    return value.isoformat().replace("+00:00", "Z")


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_fingerprint(source_path: str, macro: Mapping[str, Any]) -> str:
    source = Path(source_path) if source_path else None
    try:
        if source is not None and source.is_file():
            return hashlib.sha256(source.read_bytes()).hexdigest()
    except OSError:
        pass
    return _canonical_sha256(macro)


def read_json(path: Path) -> Dict[str, Any]:
    with Path(path).open("r", encoding="utf-8") as fh:
        return json.load(fh)


def write_json(path: Path, obj: Mapping[str, Any]) -> None:
    with Path(path).open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)


def _is_missing(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and value != value:
        return True
    if isinstance(value, str) and value.strip().upper() in MISSING_TOKENS:
        return True
    return False


def _walk_values(node: Any, key: str) -> Iterable[Any]:
    if isinstance(node, Mapping):
        for k, v in node.items():
            if k == key:
                yield v
            if isinstance(v, Mapping):
                yield from _walk_values(v, key)
            elif isinstance(v, list):
                for item in v:
                    yield from _walk_values(item, key)


def find_field(data: Mapping[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data and not _is_missing(data.get(key)):
            return data.get(key)
        for value in _walk_values(data, key):
            if not _is_missing(value):
                return value
    return default


def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if _is_missing(value):
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _clip(value: Optional[float], low: float = 0.0, high: float = 1.0) -> Optional[float]:
    if value is None:
        return None
    return max(low, min(high, value))


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, tuple):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str):
        raw = value.strip()
        if not raw:
            return []
        if raw.startswith("["):
            try:
                loaded = json.loads(raw)
                return _as_list(loaded)
            except Exception:
                pass
        return [part.strip() for part in raw.replace("|", ",").split(",") if part.strip()]
    return [str(value).strip()] if str(value).strip() else []


def _parse_ts(value: Any) -> Optional[datetime]:
    if _is_missing(value):
        return None
    try:
        text = str(value).replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _age_hours(generated_at: Any, now: Optional[datetime] = None) -> Optional[float]:
    ts = _parse_ts(generated_at)
    if ts is None:
        return None
    current = now or utc_now()
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    return round((current.astimezone(timezone.utc) - ts).total_seconds() / 3600.0, 2)


def _freshness_status(age_hours: Optional[float], missing: bool = False) -> str:
    if missing:
        return "MISSING"
    if age_hours is None:
        return "MISSING"
    if age_hours <= FRESH_HOURS:
        return "FRESH"
    if age_hours <= EXPIRED_HOURS:
        return "STALE"
    return "EXPIRED"


def _normalise_confidence(value: Any, default: float = 0.0) -> float:
    val = _safe_float(value, default)
    if val is None:
        val = default
    if val > 1.0:
        val = val / 100.0
    return round(max(0.0, min(1.0, val)), 4)


def _regime_label(raw: Any) -> str:
    text = str(raw or "UNKNOWN").strip().upper().replace("-", "_").replace(" ", "_")
    if text in {"TRENDING_BULL", "RECOVERY", "SELECTIVE_RISK_ON", "NEUTRAL_TO_RISK_ON"}:
        return "RISK_ON"
    if text in {"TRENDING_BEAR", "RISK_OFF_TILT", "NEUTRAL_TO_RISK_OFF", "NEUTRAL_TO_DEFENSIVE"}:
        return "RISK_OFF"
    if text in {"CHOPPY_NEUTRAL", "NEUTRAL", "MIXED"}:
        return "CHOPPY"
    if text in {"CRISIS"}:
        return "CRISIS"
    if "RISK_ON" in text:
        return "RISK_ON"
    if "RISK_OFF" in text or "DEFENSIVE" in text:
        return "RISK_OFF"
    if "TRANSITION" in text:
        return "TRANSITIONAL"
    return text if text in {"RISK_ON", "RISK_OFF", "TRANSITIONAL", "CHOPPY", "CRISIS"} else "UNKNOWN"


def _risk_score(regime: str, risk_switch: Any, macro_filter: Any) -> float:
    text = " ".join(str(v or "") for v in (regime, risk_switch, macro_filter)).upper()
    score = 0.0
    if "RISK_ON" in text:
        score += 55.0
    if "SELECTIVE" in text:
        score += 10.0
    if "NO_GO" in text or "NO-GO" in text:
        score -= 25.0
    if "RISK_OFF" in text:
        score -= 65.0
    if "CRISIS" in text:
        score -= 100.0
    if "TRANSITION" in text or "CHOPPY" in text:
        score = min(score, 25.0)
    return round(max(-100.0, min(100.0, score)), 2)


def _liquidity_pulse(label: Any, score: Optional[float]) -> str:
    text = str(label or "").upper()
    if any(x in text for x in ("EXPAND", "EASING", "IMPROV")):
        return "EXPANDING"
    if any(x in text for x in ("CONTRACT", "DRAIN", "TIGHTEN", "DETERIOR")):
        return "CONTRACTING"
    if score is not None:
        if score >= 0.6:
            return "EXPANDING"
        if score <= 0.4:
            return "CONTRACTING"
    if text:
        return "NEUTRAL"
    return "UNKNOWN"


def _vix_structure(vix_contango: Optional[float], vol_mode: Any) -> str:
    text = str(vol_mode or "").upper()
    if "BACKWARD" in text:
        return "BACKWARDATION"
    if "CONTANGO" in text:
        return "CONTANGO"
    if vix_contango is None:
        return "UNKNOWN"
    if vix_contango > 0.05:
        return "CONTANGO"
    if vix_contango < -0.05:
        return "BACKWARDATION"
    return "FLAT"


def _vol_mode(vix_level: Optional[float], vol_mode: Any, structure: str) -> str:
    text = str(vol_mode or "").upper()
    if any(x in text for x in ("SUPPRESSED", "LOW")):
        return "LOW_VOL"
    if any(x in text for x in ("EXPAND", "ELEVATED", "HIGH")):
        return "VOL_EXPANSION"
    if structure == "CONTANGO" and vix_level is not None and vix_level < 18:
        return "VOL_COMPRESSION"
    if vix_level is not None:
        if vix_level < 16:
            return "LOW_VOL"
        if vix_level > 25:
            return "HIGH_VOL"
        return "NORMAL_VOL"
    return "UNKNOWN"


def _dealer_gamma(score: Optional[float]) -> str:
    if score is None:
        return "UNKNOWN"
    if score >= 0.6:
        return "POSITIVE_GAMMA"
    if score <= 0.4:
        return "NEGATIVE_GAMMA"
    return "NEUTRAL"


def _rates_impulse(raw: Any) -> str:
    text = str(raw or "").upper()
    if any(x in text for x in ("UP", "RESTRICTIVE", "TIGHTEN", "HAWK")):
        return "RATES_UP"
    if any(x in text for x in ("DOWN", "EASE", "DOVISH", "CUT")):
        return "RATES_DOWN"
    if text:
        return "NEUTRAL"
    return "UNKNOWN"


def _usd_state(raw: Any) -> str:
    text = str(raw or "").upper()
    if any(x in text for x in ("UP", "STRONG", "STRENGTH")):
        return "USD_UP"
    if any(x in text for x in ("DOWN", "WEAK", "WEAKEN")):
        return "USD_DOWN"
    if text:
        return "NEUTRAL"
    return "UNKNOWN"


def _credit_state(raw: Any) -> str:
    text = str(raw or "").upper()
    if any(x in text for x in ("TIGHT", "STRESS", "WIDEN", "RISK_OFF")):
        return "TIGHTENING"
    if any(x in text for x in ("EASE", "NARROW", "BENIGN")):
        return "EASING"
    if text:
        return "STABLE"
    return "UNKNOWN"


def _sector_rotation_state(regime: str, preferred: list[str], avoid: list[str], rotation_signal: Any) -> str:
    text = str(rotation_signal or "").upper()
    if text and text not in MISSING_TOKENS:
        if "DEFENS" in text:
            return "DEFENSIVE_ROTATION"
        if "CYCL" in text:
            return "CYCLICAL_ROTATION"
        if "BROAD" in text and "OFF" in text:
            return "BROAD_RISK_OFF"
        if "BROAD" in text and "ON" in text:
            return "BROAD_RISK_ON"
        if "TECH" in text:
            return "TECH_LED_RISK_ON"
        if "MIXED" in text:
            return "MIXED"
    pref_text = " ".join(preferred).upper()
    if "TECH" in pref_text or "XLK" in pref_text or "QQQ" in pref_text:
        return "TECH_LED_RISK_ON"
    if regime == "RISK_OFF" and avoid:
        return "BROAD_RISK_OFF"
    if regime == "RISK_ON" and len(preferred) >= 4:
        return "BROAD_RISK_ON"
    if preferred or avoid:
        return "MIXED"
    return "UNKNOWN"


def _macro_horizon(macro: Mapping[str, Any]) -> tuple[str, str]:
    routing = macro.get("horizon_routing")
    if not isinstance(routing, Mapping):
        routing = find_field(macro, "horizon_routing", default={})
    if not isinstance(routing, Mapping):
        return "UNKNOWN", "UNKNOWN"
    best_bucket = "UNKNOWN"
    best_score = -1.0
    sizes = []
    for bucket, payload in routing.items():
        if not isinstance(payload, Mapping):
            continue
        prob = _safe_float(payload.get("bullish_prob_pct"), None)
        size = _safe_float(payload.get("size_multiplier"), None)
        if size is not None:
            sizes.append((str(bucket), size))
        score = prob if prob is not None else (size or 0.0) * 100.0
        if score > best_score:
            best_bucket = str(bucket).upper()
            best_score = score
    if not sizes:
        return best_bucket, "UNKNOWN"
    first = dict(sizes).get("1_5d", 0.0)
    mid = dict(sizes).get("6_10d", 0.0)
    long = dict(sizes).get("11_20d", 0.0)
    if first > mid and first > long:
        pressure = "FRONT_LOADED"
    elif long > first and long > mid:
        pressure = "BACK_LOADED"
    else:
        pressure = "BALANCED"
    return best_bucket, pressure


def _bucket_clarity(macro: Mapping[str, Any], risk_score: float, liquidity_score: Optional[float], credit_risk_score: float) -> Dict[str, float]:
    rates = str(find_field(macro, "rates_impulse", default="")).upper()
    usd = str(find_field(macro, "usd_state", default="")).upper()
    commodities = "GOLD" in json.dumps(macro).upper() or "COMMOD" in json.dumps(macro).upper()
    return {
        "equities": round(max(0.0, min(100.0, 50.0 + risk_score / 2.0)), 2),
        "rates_bonds": round(65.0 if any(x in rates for x in ("DOWN", "EASE")) else 45.0, 2),
        "usd_fx": round(65.0 if any(x in usd for x in ("UP", "STRONG")) else 45.0, 2),
        "credit": round(max(0.0, min(100.0, 100.0 - credit_risk_score)), 2),
        "commodities": round(60.0 if commodities else 45.0, 2),
    }


def _primary_bucket(clarity: Mapping[str, float]) -> str:
    if not clarity:
        return "UNKNOWN"
    key = max(clarity, key=lambda k: clarity.get(k, 0.0))
    return {
        "equities": "EQUITIES",
        "rates_bonds": "RATES_BONDS",
        "usd_fx": "USD_FX",
        "credit": "CREDIT",
        "commodities": "COMMODITIES",
    }.get(key, "UNKNOWN")


def _equity_drawer_active(rates: str, usd: str, credit: str, risk_score: float) -> bool:
    headwinds = 0
    if rates == "RATES_UP":
        headwinds += 1
    if usd == "USD_UP":
        headwinds += 1
    if credit == "TIGHTENING":
        headwinds += 1
    if risk_score < -30:
        headwinds += 1
    return headwinds >= 3


def _macro_execution_caution(drawer_active: bool, freshness: str, confidence: float, data_quality: str) -> str:
    cautions = []
    if drawer_active:
        cautions.append("EQUITY_DRAWER_ACTIVE_REQUIRES_STRONG_CONFIRMATION")
    if freshness in {"STALE", "EXPIRED", "MISSING", "CONFLICTED"}:
        cautions.append(f"MACRO_{freshness}_REVIEW_REQUIRED")
    if data_quality in {"MISSING", "CONFLICTED"}:
        cautions.append(f"MACRO_DATA_{data_quality}")
    if confidence < 0.4:
        cautions.append("LOW_MACRO_CONFIDENCE")
    return "|".join(cautions) if cautions else "NONE"


def _ticker_alignment(packet: Mapping[str, Any], row: Optional[Mapping[str, Any]] = None) -> tuple[str, float]:
    if not row:
        return "UNKNOWN", 0.0
    sector = str(
        row.get("gics_sector")
        or row.get("sector")
        or row.get("sector_etf")
        or row.get("sector_etf_mapped")
        or ""
    ).strip().upper()
    if not sector:
        return "UNKNOWN", 0.0
    preferred = [str(v).upper() for v in packet.get("preferred_sectors", []) or []]
    avoid = [str(v).upper() for v in packet.get("avoid_sectors", []) or []]
    if any(sector in p or p in sector for p in preferred):
        return "ALIGNED", 100.0
    if any(sector in a or a in sector for a in avoid):
        return "CONFLICTED", 0.0
    return "NEUTRAL", 50.0


def detect_core_conflict(macro: Mapping[str, Any]) -> bool:
    for key in ("regime_state", "risk_on_off_switch", "macro_conviction", "vix_contango"):
        values = []
        for value in _walk_values(macro, key):
            if not _is_missing(value):
                values.append(str(value).strip())
        unique = {v for v in values if v}
        if len(unique) > 1 and key in {"regime_state", "risk_on_off_switch"}:
            return True
    return False


def _is_resolved_conflict_flag(flag: str) -> bool:
    """Resolved macro merge notes should not degrade data quality by themselves."""
    text = str(flag or "").upper()
    active_tokens = (
        "MISSING/UNRELIABLE",
        "UNRELIABLE",
        "EXCLUDED FROM ALL CALCULATIONS",
        "PULL ERROR",
        "NO SOURCE",
    )
    if any(token in text for token in active_tokens):
        return False
    resolved_tokens = (
        "RESOLVED:",
        "_RESOLVED:",
        "CLEAR:",
        "_CLEAR:",
        "CSV PRIMARY APPLIED",
        "CSV VALUE APPLIED",
        "CSV APPLIED",
        "VALUE APPLIED",
        "SUPERSEDED BY CSV",
        "OVERRIDDEN BY CSV",
        "IMMATERIAL",
        "BOTH APPLIED CONTEXTUALLY",
        "CONSISTENT AT",
    )
    return any(token in text for token in resolved_tokens)


def _split_macro_conflict_flags(macro: Mapping[str, Any]) -> tuple[list[str], list[str], list[str]]:
    flags = _as_list(find_field(macro, "conflict_flags", default=[]))
    resolved = [flag for flag in flags if _is_resolved_conflict_flag(flag)]
    active = [flag for flag in flags if flag not in resolved]
    return flags, active, resolved


def build_macro_quant_packet(
    macro: Optional[Mapping[str, Any]],
    source_path: str | Path | None = None,
    now: Optional[datetime] = None,
) -> Dict[str, Any]:
    if not macro:
        return missing_macro_quant_packet(source_path)

    availability = str(macro.get("macro_availability") or "").strip().upper()
    if availability.startswith("UNAVAILABLE"):
        packet = missing_macro_quant_packet(source_path)
        packet.update({
            "macro_contract_version": str(
                macro.get("schema_version") or "macro_advisory_fallback_v1"
            ),
            "macro_generated_at_utc": str(
                macro.get("as_of_utc") or macro.get("generated_at") or ""
            ),
            "macro_regime_label": "TRANSITIONAL",
            "macro_regime_sub_state": "TRANSITIONAL_NEUTRAL",
            "regime_drift_status": "UNKNOWN",
            "risk_on_off_score": 0.0,
            "macro_execution_caution": "MACRO_UNAVAILABLE_ADVISORY_ONLY",
        })
        return packet

    source = str(source_path or find_field(macro, "source_path", default=""))
    generated_at = (
        find_field(macro, "as_of_utc", default=None)
        or find_field(macro, "generated_at_utc", default=None)
        or find_field(macro, "generated_at", default=None)
        or find_field(macro, "report_date", default=None)
    )
    normalised_at = find_field(macro, "normalised_at_utc", default=None)
    age = _age_hours(generated_at, now=now)
    freshness = _freshness_status(age)

    raw_regime = find_field(macro, "regime_state", "regime_label", default="UNKNOWN")
    regime = _regime_label(raw_regime)
    drift = str(find_field(macro, "regime_drift_status", default="UNKNOWN")).upper()
    risk_switch = find_field(macro, "risk_on_off_switch", "risk_on_switch", default="UNKNOWN")
    macro_filter = find_field(macro, "macro_filter", default="")
    risk_score = _risk_score(regime, risk_switch, macro_filter)

    confidence = _normalise_confidence(
        find_field(macro, "macro_conviction", "conviction_score", "predictability_score", default=0.0)
    )
    liquidity_score = _safe_float(find_field(macro, "net_liquidity_score", default=None), None)
    liquidity_score = _clip(liquidity_score, 0.0, 1.0)
    liquidity_pulse = _liquidity_pulse(
        find_field(macro, "liquidity_pulse", "liquidity_status", default="UNKNOWN"),
        liquidity_score,
    )
    liquidity_risk_flag = liquidity_pulse == "CONTRACTING"

    vix_level = _safe_float(find_field(macro, "vix_level", "vix_spot", "vix_current", "vix_5d_avg", default=None), None)
    vix_score = _safe_float(find_field(macro, "vix_regime_score", default=None), None)
    vix_score = _clip(vix_score, 0.0, 1.0)
    vix_contango = _safe_float(find_field(macro, "vix_contango", "spread", default=None), None)
    vol_raw = find_field(macro, "vol_mode", "volatility_mode", default="UNKNOWN")
    vix_structure = _vix_structure(vix_contango, vol_raw)
    vol_mode = _vol_mode(vix_level, vol_raw, vix_structure)
    vix_regime_label = str(vol_raw or vix_structure or "UNKNOWN").upper()

    rates = _rates_impulse(find_field(macro, "rates_impulse", default=None))
    usd = _usd_state(find_field(macro, "usd_state", "dollar_signal", default=None))
    credit = _credit_state(find_field(macro, "credit_state", "credit_signal", default=None))
    credit_risk_score = 75.0 if credit == "TIGHTENING" else 25.0 if credit == "EASING" else 50.0

    gex_score = _safe_float(find_field(macro, "gex_regime_score", default=None), None)
    gex_score = _clip(gex_score, 0.0, 1.0)
    dealer_gamma = _dealer_gamma(gex_score)

    sector_rotation = find_field(macro, "sector_rotation", default={})
    if not isinstance(sector_rotation, Mapping):
        sector_rotation = {}
    leading = _as_list(sector_rotation.get("strongest_sectors")) or _as_list(find_field(macro, "sector_lead", default=[]))
    lagging = _as_list(sector_rotation.get("weakest_sectors")) or _as_list(find_field(macro, "sector_avoid", default=[]))
    preferred = leading or _as_list(find_field(macro, "preferred_sectors", default=[]))
    avoid = lagging or _as_list(find_field(macro, "avoid_sectors", default=[]))
    sector_rotation_state = _sector_rotation_state(regime, preferred, avoid, sector_rotation.get("rotation_signal"))
    sector_tilt_score = round(min(100.0, max(0.0, 50.0 + (len(preferred) - len(avoid)) * 10.0)), 2)

    regime_sub_state = str(find_field(macro, "regime_sub_state", default=find_field(macro, "macro_regime_sub_state", default=regime))).upper()
    regime_distribution = find_field(macro, "regime_distribution", default={})
    if not isinstance(regime_distribution, Mapping):
        regime_distribution = {}

    macro_horizon, horizon_pressure = _macro_horizon(macro)
    clarity = _bucket_clarity(macro, risk_score, liquidity_score, credit_risk_score)
    primary_bucket = _primary_bucket(clarity)
    drawer_active = _equity_drawer_active(rates, usd, credit, risk_score)

    extras = macro.get("extras") if isinstance(macro, Mapping) else None
    bond_macro = extras.get("bond_macro") if isinstance(extras, Mapping) else None
    if not isinstance(bond_macro, Mapping):
        bond_macro = {}
    bond_macro_flag = str(bond_macro.get("bond_macro_flag") or "").strip().upper()
    bond_trade_go = bool(bond_macro.get("trade_go", True))
    bond_macro_score = _safe_float(
        bond_macro.get("bond_macro_score", bond_macro.get("macro_bond_score")), None
    )
    auction_spread_risk = bool(bond_macro.get("auction_spread_risk", False))
    bond_credit_warning = bool(bond_macro.get("credit_warning", False))
    breakeven_adjustment_pct = _safe_float(
        bond_macro.get("breakeven_adjustment_pct"), 0.0
    ) or 0.0

    has_conflict = detect_core_conflict(macro)
    flags, active_flags, resolved_flags = _split_macro_conflict_flags(macro)
    partial = bool(active_flags)
    if has_conflict:
        data_quality = "CONFLICTED"
        freshness = "CONFLICTED"
    elif partial:
        data_quality = "PARTIAL"
    else:
        data_quality = "CONFIRMED"

    packet = {
        "macro_quant_contract_version": MACRO_QUANT_CONTRACT_VERSION,
        "macro_source_path": source,
        "macro_contract_version": str(find_field(macro, "contract_version", default="UNKNOWN")),
        "macro_generated_at_utc": str(generated_at or ""),
        "macro_normalised_at_utc": str(normalised_at or utc_iso(now)),
        "macro_age_hours": age,
        "macro_freshness_status": freshness,
        "macro_confidence": confidence,
        "macro_data_quality": data_quality,
        "macro_regime_label": regime,
        "macro_regime_sub_state": regime_sub_state or regime,
        "regime_drift_status": drift or "UNKNOWN",
        "regime_distribution_bull": _safe_float(regime_distribution.get("bull"), None),
        "regime_distribution_neutral": _safe_float(regime_distribution.get("neutral"), None),
        "regime_distribution_bear": _safe_float(regime_distribution.get("bear"), None),
        "risk_on_off_score": risk_score,
        "macro_conviction_score": round(confidence * 100.0, 2),
        "net_liquidity_score": liquidity_score,
        "liquidity_pulse": liquidity_pulse,
        "liquidity_risk_flag": bool(liquidity_risk_flag),
        "vix_level": vix_level,
        "vix_regime_label": vix_regime_label,
        "vix_regime_score": vix_score,
        "vix_contango": vix_contango,
        "vix_structure_label": vix_structure,
        "vol_mode": vol_mode,
        "rates_impulse": rates,
        "usd_state": usd,
        "credit_state": credit,
        "credit_risk_score": credit_risk_score,
        "gex_regime_score": gex_score,
        "dealer_gamma_state": dealer_gamma,
        "gamma_risk_flag": dealer_gamma == "NEGATIVE_GAMMA",
        "sector_rotation_state": sector_rotation_state,
        "leading_sectors": leading,
        "lagging_sectors": lagging,
        "avoid_sectors": avoid,
        "preferred_sectors": preferred,
        "sector_tilt_score": sector_tilt_score,
        "ticker_sector_alignment": "UNKNOWN",
        "ticker_sector_alignment_score": 0.0,
        "macro_preferred_horizon": macro_horizon,
        "horizon_pressure": horizon_pressure,
        "primary_bucket": primary_bucket,
        "bucket_clarity_scores": clarity,
        "equity_drawer_active": bool(drawer_active),
        "macro_execution_caution": _macro_execution_caution(drawer_active, freshness, confidence, data_quality),
        "macro_conflict_flags": flags,
        "macro_active_conflict_flags": active_flags,
        "macro_resolved_conflict_flags": resolved_flags,
        "bond_macro_flag": bond_macro_flag,
        "bond_trade_go": bond_trade_go,
        "bond_macro_score": bond_macro_score,
        "auction_spread_risk": auction_spread_risk,
        "credit_warning": bond_credit_warning,
        "breakeven_adjustment_pct": breakeven_adjustment_pct,
    }
    macro_as_of = str(generated_at or "")
    report_date = str(find_field(macro, "report_date", default="") or "")
    session_date = report_date[:10] if report_date else macro_as_of[:10]
    advisory = str(
        find_field(
            macro,
            "macro_plain_language_advisory",
            "notes",
            "summary",
            "macro_notes",
            default=(
                "Macro is advisory context only and does not authorize or veto "
                "a ticker trade."
            ),
        )
        or ""
    )
    source_fingerprint = _source_fingerprint(source, macro)
    packet.update({
        "macro_source_fingerprint": source_fingerprint,
        "macro_as_of_utc": macro_as_of,
        "macro_session_date": session_date,
        "macro_plain_language_advisory": advisory,
        "macro_authority": "ADVISORY_ONLY",
    })
    identity_payload = {
        key: value for key, value in packet.items()
        if key != "macro_normalised_at_utc"
    }
    packet_sha256 = _canonical_sha256(identity_payload)
    packet["macro_packet_sha256"] = packet_sha256
    packet["macro_packet_id"] = f"MACRO:{session_date or 'UNKNOWN'}:{packet_sha256[:16]}"
    return packet


def missing_macro_quant_packet(source_path: str | Path | None = None) -> Dict[str, Any]:
    return {
        "macro_packet_id": "MACRO_NOT_AVAILABLE",
        "macro_packet_sha256": "",
        "macro_source_fingerprint": "",
        "macro_as_of_utc": "",
        "macro_session_date": "",
        "macro_plain_language_advisory": (
            "Macro advisory unavailable; core ticker analysis remains independent."
        ),
        "macro_authority": "ADVISORY_ONLY",
        "macro_quant_contract_version": MACRO_QUANT_CONTRACT_VERSION,
        "macro_source_path": str(source_path or ""),
        "macro_contract_version": "UNKNOWN",
        "macro_generated_at_utc": "",
        "macro_normalised_at_utc": "",
        "macro_age_hours": None,
        "macro_freshness_status": "MISSING",
        "macro_confidence": 0.0,
        "macro_data_quality": "MISSING",
        "macro_regime_label": "UNKNOWN",
        "macro_regime_sub_state": "UNKNOWN",
        "regime_drift_status": "UNKNOWN",
        "regime_distribution_bull": None,
        "regime_distribution_neutral": None,
        "regime_distribution_bear": None,
        "risk_on_off_score": 0.0,
        "macro_conviction_score": 0.0,
        "net_liquidity_score": None,
        "liquidity_pulse": "UNKNOWN",
        "liquidity_risk_flag": True,
        "vix_level": None,
        "vix_regime_label": "UNKNOWN",
        "vix_regime_score": None,
        "vix_contango": None,
        "vix_structure_label": "UNKNOWN",
        "vol_mode": "UNKNOWN",
        "rates_impulse": "UNKNOWN",
        "usd_state": "UNKNOWN",
        "credit_state": "UNKNOWN",
        "credit_risk_score": 50.0,
        "gex_regime_score": None,
        "dealer_gamma_state": "UNKNOWN",
        "gamma_risk_flag": True,
        "sector_rotation_state": "UNKNOWN",
        "leading_sectors": [],
        "lagging_sectors": [],
        "avoid_sectors": [],
        "preferred_sectors": [],
        "sector_tilt_score": 0.0,
        "ticker_sector_alignment": "UNKNOWN",
        "ticker_sector_alignment_score": 0.0,
        "macro_preferred_horizon": "UNKNOWN",
        "horizon_pressure": "UNKNOWN",
        "primary_bucket": "UNKNOWN",
        "bucket_clarity_scores": {
            "equities": 0.0,
            "rates_bonds": 0.0,
            "usd_fx": 0.0,
            "credit": 0.0,
            "commodities": 0.0,
        },
        "equity_drawer_active": True,
        "macro_execution_caution": "MACRO_MISSING_REVIEW_REQUIRED|MACRO_DATA_MISSING|LOW_MACRO_CONFIDENCE",
        "macro_conflict_flags": [],
        "macro_active_conflict_flags": [],
        "macro_resolved_conflict_flags": [],
        "bond_macro_flag": "",
        "bond_trade_go": True,
        "bond_macro_score": None,
        "auction_spread_risk": False,
        "credit_warning": False,
        "breakeven_adjustment_pct": 0.0,
    }


def load_macro_quant_packet(path: str | Path) -> Dict[str, Any]:
    source = Path(path)
    if not source.exists():
        return missing_macro_quant_packet(source)
    try:
        raw = read_json(source)
    except Exception:
        return missing_macro_quant_packet(source)
    existing = raw.get("macro_quant_packet")
    if isinstance(existing, Mapping):
        packet = dict(existing)
        for key, value in missing_macro_quant_packet(source).items():
            packet.setdefault(key, value)
        return packet
    return build_macro_quant_packet(raw, source)


def write_macro_quant_packet_to_json(path: str | Path) -> Dict[str, Any]:
    source = Path(path)
    raw = read_json(source)
    packet = build_macro_quant_packet(raw, source)
    raw["macro_quant_packet"] = packet
    raw["macro_quant_contract_version"] = MACRO_QUANT_CONTRACT_VERSION
    raw["normalised_at_utc"] = packet["macro_normalised_at_utc"]
    write_json(source, raw)
    return packet


def packet_from_package(pkg: Mapping[str, Any]) -> Dict[str, Any]:
    packet = pkg.get("macro_quant_packet")
    if isinstance(packet, Mapping):
        return dict(packet)
    macro = pkg.get("macro")
    if isinstance(macro, Mapping):
        q = macro.get("quant_packet")
        if isinstance(q, Mapping):
            return dict(q)
        payload = macro.get("payload")
        if isinstance(payload, Mapping):
            return build_macro_quant_packet(payload, macro.get("source_path"))
    snapshot = pkg.get("macro_snapshot") or pkg.get("regime_snapshot")
    if isinstance(snapshot, Mapping):
        return build_macro_quant_packet(snapshot, "")
    return missing_macro_quant_packet("")


def add_ticker_alignment(packet: Mapping[str, Any], row: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    out = dict(packet)
    alignment, score = _ticker_alignment(out, row)
    out["ticker_sector_alignment"] = alignment
    out["ticker_sector_alignment_score"] = score
    return out


def json_safe(value: Any) -> Any:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True, ensure_ascii=False)
    if isinstance(value, bool):
        return bool(value)
    return value


def macro_quant_columns_for_row(
    packet: Optional[Mapping[str, Any]],
    row: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    base = missing_macro_quant_packet("")
    if packet:
        base.update(dict(packet))
    base = add_ticker_alignment(base, row)
    return {field: json_safe(base.get(field)) for field in MACRO_QUANT_CSV_FIELDS}


def merge_preserving_committed(target: Dict[str, Any], updates: Mapping[str, Any]) -> Dict[str, Any]:
    for key, value in updates.items():
        current = target.get(key)
        if _is_missing(current):
            target[key] = value
            continue
        if _is_missing(value):
            continue
        if current == value:
            continue
        # Preserve committed fields; write conflict audit sidecar without clobbering.
        conflicts = target.setdefault("macro_conflicted_fields", {})
        if isinstance(conflicts, dict):
            conflicts[key] = {"old_value": current, "new_value": value, "source": "macro_quant_packet"}
    return target


def resolve_macro_suffix_columns(df: Any) -> Any:
    """Collapse macro merge suffixes back to canonical column names."""
    if df is None or not hasattr(df, "columns"):
        return df
    missing_tokens = {"", "NONE", "NULL", "NAN", "N/A", "UNKNOWN", "MISSING"}
    for field in MACRO_QUANT_CSV_FIELDS:
        variants = [
            field,
            f"{field}_x",
            f"{field}_y",
            f"{field}__vg",
            f"{field}__opt",
        ]
        present = [col for col in variants if col in df.columns]
        if not present:
            continue
        if field not in df.columns:
            df[field] = df[present[0]]
        for alt in present:
            if alt == field:
                continue
            try:
                mask = df[field].isna() | df[field].astype(str).str.strip().str.upper().isin(missing_tokens)
                # RUN3 FIX: Cast column to object dtype before string assignment
                # Prevents FutureWarning: Setting an item of incompatible dtype
                df[field] = df[field].astype(object)
                df.loc[mask, field] = df.loc[mask, alt]
            except Exception:
                df[field] = df[field].combine_first(df[alt])
        drop_cols = [col for col in present if col != field and col in df.columns]
        if drop_cols:
            df.drop(columns=drop_cols, inplace=True)
    return df


def required_macro_quant_fields() -> list[str]:
    return list(MACRO_QUANT_CSV_FIELDS)

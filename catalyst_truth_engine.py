#!/usr/bin/env python
"""Catalyst Truth Engine.

This layer is a shadow/advisory enrichment pass. It does not allocate capital.
It reads the tickers already found by discovery, the option scanner, vanguard,
catalyst calendar/source packets, and downstream artifacts, then stamps a catalyst quality lens
onto every ticker it can see.

Optional operator catalyst packet:
    dropbox/inputs/catalyst_calendar_latest.csv

Recommended packet columns:
    ticker, catalyst_type, catalyst_date, catalyst_description,
    catalyst_source_confidence, catalyst_direction_bias, catalyst_binary_score
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


CATALYST_VERSION = "catalyst_truth_v1.1"

CATALYST_OUTPUT_FIELDS = [
    "catalyst_engine_version",
    "catalyst_detected",
    "catalyst_type",
    "catalyst_date",
    "days_to_catalyst",
    "catalyst_inside_dte",
    "catalyst_truth_score",
    "catalyst_binary_score",
    "catalyst_direction_bias",
    "catalyst_source_count",
    "catalyst_data_quality",
    "catalyst_trade_class",
    "event_convexity_score",
    "cheap_convexity_flag",
    "catalyst_liquidity_ok",
    "catalyst_alignment_label",
    "catalyst_reason_codes",
    "catalyst_source_fields",
    "catalyst_manual_upload",
    "catalyst_requires_live_confirmation",
    "catalyst_event_status",
    "catalyst_source_tier",
    "catalyst_source_url",
    "catalyst_ticker_role",
    "catalyst_expected_impact",
    "catalyst_failure_risk",
]

QUALITY_MAP = {
    "VERY_HIGH": 0.95,
    "HIGH": 0.85,
    "GOOD": 0.75,
    "MEDIUM": 0.60,
    "MID": 0.60,
    "MODERATE": 0.55,
    "LOW": 0.35,
    "WEAK": 0.25,
    "NONE": 0.0,
    "UNKNOWN": 0.0,
    "DATA_WEAK": 0.20,
    "CONFIRMED": 0.95,
    "ANNOUNCED": 0.90,
    "SCHEDULED": 0.90,
    "FILED": 0.85,
    "PENDING": 0.65,
    "TIER_1": 0.95,
    "TIER_2": 0.75,
    "TIER_3": 0.55,
    "RUMOR": 0.35,
    "UNCONFIRMED": 0.30,
    "WATCH_ONLY": 0.25,
    "TBD": 0.20,
    "BLOCKED": 0.0,
}


@dataclass
class SourceBundle:
    ticker: str
    rows: List[Dict[str, Any]]
    sources: List[str]


def _norm(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and math.isnan(value):
        return ""
    text = str(value).strip()
    if text.lower() in {"", "nan", "none", "null", "nat"}:
        return ""
    return text


def _upper(value: Any) -> str:
    return _norm(value).upper()


def _num(value: Any, default: float = 0.0) -> float:
    text = _norm(value).replace("%", "").replace(",", "")
    if not text:
        return default
    try:
        number = float(text)
        if math.isnan(number) or math.isinf(number):
            return default
        return number
    except Exception:
        return default


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _truthy(value: Any) -> bool:
    return _upper(value) in {"1", "TRUE", "YES", "Y", "PASS", "OK"}


def _first(rows: Iterable[Dict[str, Any]], fields: Iterable[str]) -> Tuple[str, str]:
    for field in fields:
        for row in rows:
            value = _norm(row.get(field))
            if value:
                return value, field
    return "", ""


def _parse_date(value: Any) -> Optional[date]:
    text = _norm(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y%m%d", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt).date()
        except Exception:
            pass
    try:
        parsed = pd.to_datetime(text, errors="coerce")
        if pd.isna(parsed):
            return None
        return parsed.date()
    except Exception:
        return None


def _run_date(run_id: str) -> date:
    try:
        return datetime.strptime(run_id[:8], "%Y%m%d").date()
    except Exception:
        return datetime.utcnow().date()


def _as_score(value: Any, default: float = 0.0) -> float:
    text = _upper(value)
    if text in QUALITY_MAP:
        return QUALITY_MAP[text]
    number = _num(value, default)
    if number > 1.0:
        number = number / 100.0
    return _clamp(number)


def _canonical_type(raw: Any) -> str:
    text = _upper(raw)
    if not text:
        return "NONE"
    if any(token in text for token in ("EARN", "EPS", "GUIDANCE", "REPORT")):
        return "EARNINGS"
    if any(token in text for token in ("FDA", "PDUFA", "PHASE", "TRIAL", "CLINICAL", "BIOTECH")):
        return "BIOTECH_FDA"
    if any(token in text for token in ("MERGER", "M&A", "TAKEOVER", "BUYOUT", "ACQUIS")):
        return "M_AND_A"
    if any(token in text for token in ("CPI", "FOMC", "FED", "RATE", "PAYROLL", "MACRO", "INFLATION")):
        return "MACRO_PRINT"
    if any(token in text for token in ("OIL", "GAS", "GOLD", "SILVER", "URANIUM", "COMMOD")):
        return "COMMODITY_MACRO"
    if any(token in text for token in ("SECTOR", "ROTATION", "ETF")):
        return "SECTOR_ROTATION"
    if any(
        token in text
        for token in (
            "WYCKOFF", "BREAKOUT", "COMPRESSION", "SPRING", "ACCUM",
            "RANGE", "REVERSAL", "DISTRIBUTION", "PRESSURE", "TREND",
            "NEUTRAL", "MARKUP", "MARKDOWN", "STRUCTURAL",
        )
    ):
        return "STRUCTURAL"
    return text[:48].replace(" ", "_")


def _direction_token(value: Any) -> str:
    text = _upper(value)
    if text in {"CALL", "LONG", "BULL", "BULLISH", "UP", "UPSIDE", "BUY"}:
        return "CALL"
    if text in {"PUT", "SHORT", "BEAR", "BEARISH", "DOWN", "DOWNSIDE", "SELL"}:
        return "PUT"
    if "CALL" in text or "BULL" in text or "UP" in text:
        return "CALL"
    if "PUT" in text or "BEAR" in text or "DOWN" in text:
        return "PUT"
    return ""


def _dte(rows: List[Dict[str, Any]]) -> float:
    value, _ = _first(
        rows,
        [
            "contract_dte",
            "dte",
            "ts_dte_used",
            "ts_dte_remaining_at_stop",
            "dte_remaining",
        ],
    )
    return _num(value, 0.0)


def _cheap_convexity(rows: List[Dict[str, Any]]) -> bool:
    iv_rank, _ = _first(rows, ["iv_rank", "iv_percentile", "ivp_30d", "ivp_252d", "ivp"])
    delta, _ = _first(rows, ["contract_delta", "delta"])
    iv = _num(iv_rank, 999.0)
    d = abs(_num(delta, 0.0))
    iv_ok = iv <= 35.0
    delta_ok = d == 0.0 or 0.03 <= d <= 0.35
    return iv_ok and delta_ok


def _liquidity(rows: List[Dict[str, Any]]) -> Tuple[bool, str]:
    oi, _ = _first(rows, ["contract_oi", "open_interest", "oi"])
    volume, _ = _first(rows, ["contract_volume", "volume", "option_volume"])
    spread, _ = _first(rows, ["contract_spread_pct", "spread_pct", "sprd", "bid_ask_spread_pct"])
    oi_value = _num(oi, 0.0)
    volume_value = _num(volume, 0.0)
    spread_value = _num(spread, 999.0)
    if 0 < spread_value < 1:
        spread_value *= 100.0
    ok = oi_value >= 500.0 and volume_value >= 10.0 and spread_value <= 20.0
    if ok:
        return True, "LIQUIDITY_OK"
    reasons = []
    if oi_value < 500.0:
        reasons.append("LOW_OI")
    if volume_value < 10.0:
        reasons.append("LOW_VOLUME")
    if spread_value > 20.0:
        reasons.append("WIDE_SPREAD")
    return False, "+".join(reasons) if reasons else "LIQUIDITY_UNKNOWN"


def _read_csv(path: Path, source: str) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception:
        return []
    if "ticker" not in df.columns and "symbol" in df.columns:
        df = df.rename(columns={"symbol": "ticker"})
    if "ticker" not in df.columns:
        return []
    rows: List[Dict[str, Any]] = []
    for raw in df.to_dict("records"):
        ticker = ""
        for key in ("ticker", "symbol", "affected_ticker", "target_ticker", "acquirer_ticker"):
            ticker = _upper(raw.get(key))
            if ticker:
                break
        if not ticker:
            continue
        raw["ticker"] = ticker
        raw["_catalyst_source"] = source
        rows.append(raw)
    return rows


def _load_calendar(base_dir: Path) -> List[Dict[str, Any]]:
    candidates = [
        base_dir / "dropbox" / "inputs" / "catalyst_calendar_latest.csv",
        base_dir / "dropbox" / "inputs" / "catalyst_calendar_latest.json",
        base_dir / "data" / "input" / "catalyst_calendar_latest.csv",
    ]
    for folder in [base_dir / "dropbox" / "inputs", base_dir / "data" / "input"]:
        if folder.exists():
            for pattern in [
                "avshunter_*catalyst*.csv",
                "avshunter_*event*.csv",
                "avshunter_ma_*.csv",
                "avshunter_fda_*.csv",
                "news_catalyst*.csv",
                "fda_catalyst*.csv",
            ]:
                candidates.extend(sorted(folder.glob(pattern)))
    rows: List[Dict[str, Any]] = []
    seen: set[str] = set()
    for path in candidates:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        if not path.exists():
            continue
        if path.suffix.lower() == ".json":
            try:
                payload = json.loads(path.read_text(encoding="utf-8-sig"))
                if isinstance(payload, dict):
                    payload = payload.get("catalysts") or payload.get("rows") or []
                for item in payload:
                    if isinstance(item, dict):
                        ticker = _upper(item.get("ticker") or item.get("symbol"))
                        if ticker:
                            item = dict(item)
                            item["ticker"] = ticker
                            item["_catalyst_source"] = "catalyst_calendar"
                            rows.append(item)
            except Exception:
                pass
        else:
            rows.extend(_read_csv(path, "catalyst_calendar"))
    return rows


def _source_rows(run_id: str, base_dir: Path) -> List[Dict[str, Any]]:
    run_dir = base_dir / "data" / "output" / "runs" / run_id
    sources = [
        ("discovery", run_dir / "discovery" / f"discovery_candidates_ultimate_{run_id}.csv"),
        ("vanguard_raw", run_dir / "vanguard" / "vanguard_signals.csv"),
        ("vanguard_enriched", run_dir / "options" / f"vanguard_signals_enriched_{run_id}.csv"),
        ("options_intelligence", run_dir / "options" / f"options_intelligence_{run_id}.csv"),
        ("superbrain", run_dir / "superbrain" / f"superbrain_enriched_{run_id}.csv"),
        ("eil_enriched", run_dir / "superbrain" / f"eil_enriched_{run_id}.csv"),
        ("execution", run_dir / "execution" / f"execution_v3_5_{run_id}.csv"),
        ("morning_candidates", run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv"),
        ("final_book", run_dir / "intelligence_lab" / f"final_opportunity_book_{run_id}.csv"),
    ]
    rows = _load_calendar(base_dir)
    for source, path in sources:
        rows.extend(_read_csv(path, source))
    return rows


def _group_rows(rows: List[Dict[str, Any]]) -> List[SourceBundle]:
    grouped: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    sources: Dict[str, List[str]] = defaultdict(list)
    for row in rows:
        ticker = _upper(row.get("ticker"))
        if not ticker:
            continue
        grouped[ticker].append(row)
        source = _norm(row.get("_catalyst_source"))
        if source and source not in sources[ticker]:
            sources[ticker].append(source)
    return [SourceBundle(ticker=ticker, rows=grouped[ticker], sources=sources[ticker]) for ticker in sorted(grouped)]


def _score(bundle: SourceBundle, run_dt: date) -> Dict[str, Any]:
    rows = bundle.rows
    reasons: List[str] = []
    fields: List[str] = []

    type_value, type_field = _first(
        rows,
        [
            "catalyst_type",
            "confirmed_event_type",
            "event_type",
            "deal_or_event_type",
            "corporate_event_type",
            "fda_event_type",
            "catalyst_category",
            "event_family",
            "dominant_event_norm",
            "dominant_event_bucket",
            "dominant_event",
            "options_macro_event_guards",
            "scanner_pattern_tags",
            "wyckoff_phase_bucket",
        ],
    )
    catalyst_type = _canonical_type(type_value)
    if type_field:
        fields.append(type_field)

    date_value, date_field = _first(
        rows,
        [
            "catalyst_date",
            "event_date",
            "expected_event_date",
            "decision_date",
            "pdufa_date",
            "event_window_start",
            "expected_window_start",
            "earnings_date",
            "expected_report_date",
            "macro_event_date",
        ],
    )
    catalyst_dt = _parse_date(date_value)
    if date_field:
        fields.append(date_field)

    description, desc_field = _first(
        rows,
        [
            "catalyst_description",
            "event_description",
            "event_summary",
            "headline",
            "narrative_summary",
            "dominant_event",
            "options_macro_alignment_note",
        ],
    )
    if desc_field:
        fields.append(desc_field)

    evidence_value, evidence_field = _first(
        rows,
        [
            "event_evidence_strength",
            "event_evidence_bucket",
            "truth_confidence",
            "truth_confidence_bucket",
            "event_quality",
            "catalyst_quality",
            "priority",
            "source_tier",
        ],
    )
    evidence_score = _as_score(evidence_value, 0.0)
    if evidence_field:
        fields.append(evidence_field)

    source_conf_value, source_conf_field = _first(
        rows,
        ["catalyst_source_confidence", "source_confidence", "source_quality", "source_tier"],
    )
    source_conf = _as_score(source_conf_value, 0.0) if source_conf_field else 0.0
    if source_conf_field:
        fields.append(source_conf_field)

    binary_value, binary_field = _first(
        rows,
        ["catalyst_binary_score", "event_binary_score", "binary_event_score", "binary_score"],
    )
    if binary_field:
        binary_score = _as_score(binary_value, 0.0)
        fields.append(binary_field)
    elif catalyst_type in {"EARNINGS", "BIOTECH_FDA", "M_AND_A", "MACRO_PRINT"}:
        binary_score = 0.75
    elif catalyst_type in {"COMMODITY_MACRO", "SECTOR_ROTATION"}:
        binary_score = 0.55
    elif catalyst_type == "STRUCTURAL":
        binary_score = 0.25
    else:
        binary_score = 0.0

    event_status, event_status_field = _first(
        rows,
        ["event_status", "deal_status", "catalyst_status", "fda_status", "status"],
    )
    event_status_u = _upper(event_status)
    if event_status_field:
        fields.append(event_status_field)
    confirmed_status = event_status_u in {
        "CONFIRMED",
        "ANNOUNCED",
        "SCHEDULED",
        "FILED",
        "PDUFA_SET",
        "APPROVED",
        "PENDING_DECISION",
    }
    weak_status = event_status_u in {"RUMOR", "UNCONFIRMED", "WATCH_ONLY", "TBD", "BLOCKED", "NOT_RUN"}

    source_tier, source_tier_field = _first(rows, ["source_tier", "source_quality", "source_rank"])
    if source_tier_field:
        fields.append(source_tier_field)
    source_url, source_url_field = _first(rows, ["source_url", "url", "article_url", "filing_url", "sec_url"])
    if source_url_field:
        fields.append(source_url_field)
    ticker_role, ticker_role_field = _first(rows, ["ticker_role", "role", "event_role", "beneficiary_type"])
    if ticker_role_field:
        fields.append(ticker_role_field)
    expected_impact, impact_field = _first(rows, ["expected_impact", "impact", "forward_impact", "trade_bias"])
    if impact_field:
        fields.append(impact_field)
    failure_risk, risk_field = _first(rows, ["failure_risk", "failure_risks", "risk", "missing_inputs"])
    if risk_field:
        fields.append(risk_field)

    calendar_source = "catalyst_calendar" in bundle.sources
    manual_upload = "manual_upload" in bundle.sources or calendar_source
    inferred_event = catalyst_type not in {"", "NONE"} and catalyst_type != "STRUCTURAL"
    description_event = any(
        token in _upper(description)
        for token in (
            "EARN", "EPS", "GUIDANCE", "FDA", "PDUFA", "TRIAL", "MERGER",
            "TAKEOVER", "CPI", "FOMC", "FED", "RATE DECISION", "PAYROLL",
        )
    )
    proximity_value, proximity_field = _first(rows, ["catalyst_proximity"])
    proximity_event = _upper(proximity_value) in {"NEAR", "IMMINENT", "INSIDE_WINDOW", "HIGH", "MID"}
    if proximity_field and proximity_event:
        fields.append(proximity_field)

    detected = bool(catalyst_dt or calendar_source or inferred_event or description_event or proximity_event)
    if catalyst_dt:
        reasons.append("DATED_CATALYST")
    if calendar_source:
        reasons.append("CALENDAR_PACKET")
    if manual_upload:
        reasons.append("MANUAL_TICKER")
    if confirmed_status:
        reasons.append("CONFIRMED_EVENT_STATUS")
    if weak_status:
        reasons.append("WEAK_OR_UNCONFIRMED_EVENT_STATUS")
    if inferred_event and not catalyst_dt:
        reasons.append("INFERRED_EVENT_NO_DATE")
    if not detected:
        reasons.append("NO_CATALYST_EVIDENCE")

    dte_value = _dte(rows)
    days_to_catalyst = ""
    inside_dte = False
    if catalyst_dt:
        days = (catalyst_dt - run_dt).days
        days_to_catalyst = days
        if 0 <= days <= max(1.0, dte_value):
            inside_dte = True
            reasons.append("CATALYST_INSIDE_DTE")
        elif days < 0:
            reasons.append("CATALYST_DATE_PAST")
        else:
            reasons.append("CATALYST_OUTSIDE_DTE")
    elif detected:
        reasons.append("NEEDS_DATED_CATALYST_PACKET")

    cheap = _cheap_convexity(rows)
    if cheap:
        reasons.append("CHEAP_CONVEXITY")
    else:
        reasons.append("CONVEXITY_NOT_CHEAP_OR_UNKNOWN")

    liquidity_ok, liquidity_reason = _liquidity(rows)
    reasons.append(liquidity_reason)

    direction_value, direction_field = _first(
        rows,
        [
            "catalyst_direction_bias",
            "options_direction",
            "direction",
            "fusion_direction",
            "repricing_direction",
            "layer2__edge_direction",
            "edge_direction",
        ],
    )
    direction_bias = _direction_token(direction_value)
    if direction_field:
        fields.append(direction_field)

    option_dir_value, _ = _first(rows, ["options_direction", "direction", "contract_type"])
    option_dir = _direction_token(option_dir_value)
    if not direction_bias:
        alignment = "NO_DIRECTION"
    elif option_dir and option_dir != direction_bias:
        alignment = "DIRECTION_CONFLICT"
        reasons.append("DIRECTION_CONFLICT")
    else:
        alignment = "ALIGNED"
        reasons.append("DIRECTION_ALIGNED")

    score = 0.0
    if detected:
        score += 20.0
    if catalyst_dt:
        score += 20.0
    if inside_dte:
        score += 15.0
    score += binary_score * 15.0
    score += max(evidence_score, source_conf) * 10.0
    if confirmed_status:
        score += 8.0
    if cheap:
        score += 8.0
    if liquidity_ok:
        score += 8.0
    if alignment == "ALIGNED":
        score += 4.0
    elif alignment == "DIRECTION_CONFLICT":
        score -= 10.0
    if manual_upload and not catalyst_dt:
        score -= 5.0
    if weak_status:
        score -= 12.0
    score = round(max(0.0, min(100.0, score)), 2)

    convexity_score = 0.0
    convexity_score += binary_score * 25.0
    convexity_score += 20.0 if cheap else 0.0
    convexity_score += 20.0 if liquidity_ok else 0.0
    convexity_score += 20.0 if inside_dte else 0.0
    convexity_score += 10.0 if alignment == "ALIGNED" else 0.0
    convexity_score += max(evidence_score, source_conf) * 5.0
    convexity_score = round(max(0.0, min(100.0, convexity_score)), 2)

    if score >= 75 and inside_dte and liquidity_ok and not weak_status:
        trade_class = "DATED_CATALYST_CONFIRMED"
        data_quality = "CONFIRMED"
    elif convexity_score >= 65 and detected:
        trade_class = "EVENT_CONVEXITY_WATCH"
        data_quality = "INFERRED_GOOD" if not catalyst_dt else "DATED_REVIEW"
    elif detected:
        trade_class = "STRUCTURE_WITH_CATALYST_CONTEXT"
        data_quality = "INFERRED"
    elif manual_upload:
        trade_class = "MANUAL_NEEDS_CATALYST_PACKET"
        data_quality = "MISSING_CATALYST_PACKET"
    else:
        trade_class = "STRUCTURE_ONLY_NO_CATALYST"
        data_quality = "NO_CATALYST"

    live_confirmation = not (
        trade_class == "DATED_CATALYST_CONFIRMED"
        and liquidity_ok
        and cheap
        and alignment in {"ALIGNED", "NO_DIRECTION"}
    )

    return {
        "ticker": bundle.ticker,
        "catalyst_engine_version": CATALYST_VERSION,
        "catalyst_detected": bool(detected),
        "catalyst_type": catalyst_type,
        "catalyst_date": catalyst_dt.isoformat() if catalyst_dt else "",
        "days_to_catalyst": days_to_catalyst,
        "catalyst_inside_dte": bool(inside_dte),
        "catalyst_truth_score": score,
        "catalyst_binary_score": round(binary_score, 3),
        "catalyst_direction_bias": direction_bias,
        "catalyst_source_count": len(bundle.sources),
        "catalyst_data_quality": data_quality,
        "catalyst_trade_class": trade_class,
        "event_convexity_score": convexity_score,
        "cheap_convexity_flag": bool(cheap),
        "catalyst_liquidity_ok": bool(liquidity_ok),
        "catalyst_alignment_label": alignment,
        "catalyst_reason_codes": ";".join(dict.fromkeys(reasons)),
        "catalyst_source_fields": ";".join(dict.fromkeys(fields)),
        "catalyst_manual_upload": bool(manual_upload),
        "catalyst_requires_live_confirmation": bool(live_confirmation),
        "catalyst_event_status": event_status_u,
        "catalyst_source_tier": source_tier,
        "catalyst_source_url": source_url,
        "catalyst_ticker_role": ticker_role,
        "catalyst_expected_impact": expected_impact,
        "catalyst_failure_risk": failure_risk,
        "catalyst_description": description,
        "_source_names": ";".join(bundle.sources),
    }


def _patch_csv(path: Path, catalyst_df: pd.DataFrame) -> Dict[str, Any]:
    if not path.exists():
        return {"path": str(path), "status": "missing", "matched": 0, "rows": 0}
    try:
        df = pd.read_csv(path, low_memory=False)
    except Exception as exc:
        return {"path": str(path), "status": "read_failed", "error": str(exc), "matched": 0, "rows": 0}
    if "ticker" not in df.columns:
        return {"path": str(path), "status": "no_ticker", "matched": 0, "rows": len(df)}
    slim = catalyst_df[["ticker"] + CATALYST_OUTPUT_FIELDS].copy()
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    existing = [field for field in CATALYST_OUTPUT_FIELDS if field in df.columns]
    if existing:
        df = df.drop(columns=existing)
    merged = df.merge(slim, on="ticker", how="left")
    matched = int(merged["catalyst_engine_version"].notna().sum())
    merged.to_csv(path, index=False)
    return {"path": str(path), "status": "patched", "matched": matched, "rows": len(merged)}


def _patch_targets(run_id: str, base_dir: Path, catalyst_df: pd.DataFrame) -> List[Dict[str, Any]]:
    run_dir = base_dir / "data" / "output" / "runs" / run_id
    targets = [
        run_dir / "discovery" / f"discovery_candidates_ultimate_{run_id}.csv",
        run_dir / "vanguard" / "vanguard_signals.csv",
        run_dir / "options" / f"vanguard_signals_enriched_{run_id}.csv",
        run_dir / "options" / f"options_intelligence_{run_id}.csv",
        run_dir / "superbrain" / f"superbrain_enriched_{run_id}.csv",
        run_dir / "superbrain" / f"eil_enriched_{run_id}.csv",
        run_dir / "execution" / f"execution_v3_5_{run_id}.csv",
        run_dir / "morning_validation" / f"morning_candidates_{run_id}.csv",
        run_dir / "intelligence_lab" / f"final_opportunity_book_{run_id}.csv",
    ]
    return [_patch_csv(path, catalyst_df) for path in targets]


def enrich_run(run_id: str, base_dir: Optional[Path | str] = None, patch_existing: bool = True) -> Dict[str, Any]:
    base = Path(base_dir) if base_dir else Path(__file__).resolve().parent
    run_dir = base / "data" / "output" / "runs" / run_id
    out_dir = run_dir / "catalysts"
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _source_rows(run_id, base)
    bundles = _group_rows(rows)
    run_dt = _run_date(run_id)
    scored = [_score(bundle, run_dt) for bundle in bundles]
    catalyst_df = pd.DataFrame(scored)
    if catalyst_df.empty:
        catalyst_df = pd.DataFrame(columns=["ticker"] + CATALYST_OUTPUT_FIELDS)

    output_path = out_dir / f"catalyst_truth_{run_id}.csv"
    public_cols = ["ticker"] + CATALYST_OUTPUT_FIELDS + ["catalyst_description", "_source_names"]
    for col in public_cols:
        if col not in catalyst_df.columns:
            catalyst_df[col] = ""
    catalyst_df[public_cols].to_csv(output_path, index=False)

    patch_results: List[Dict[str, Any]] = []
    if patch_existing:
        patch_results = _patch_targets(run_id, base, catalyst_df[["ticker"] + CATALYST_OUTPUT_FIELDS])

    trade_counts = Counter(catalyst_df.get("catalyst_trade_class", []))
    manual_df = catalyst_df[catalyst_df.get("catalyst_manual_upload", False) == True] if not catalyst_df.empty else catalyst_df
    detected = int(catalyst_df.get("catalyst_detected", pd.Series(dtype=bool)).astype(bool).sum())
    dated = int(catalyst_df.get("catalyst_date", pd.Series(dtype=str)).astype(str).str.len().gt(0).sum())
    inside = int(catalyst_df.get("catalyst_inside_dte", pd.Series(dtype=bool)).astype(bool).sum())
    high_truth = int((pd.to_numeric(catalyst_df.get("catalyst_truth_score", pd.Series(dtype=float)), errors="coerce").fillna(0) >= 70).sum())
    event_convexity = catalyst_df[
        pd.to_numeric(catalyst_df.get("event_convexity_score", pd.Series(dtype=float)), errors="coerce").fillna(0) >= 65
    ].copy()

    summary = {
        "run_id": run_id,
        "version": CATALYST_VERSION,
        "rows": int(len(catalyst_df)),
        "catalyst_detected": detected,
        "dated_catalysts": dated,
        "inside_dte": inside,
        "high_truth_score": high_truth,
        "event_convexity_watch": int(len(event_convexity)),
        "cheap_convexity": int(catalyst_df.get("cheap_convexity_flag", pd.Series(dtype=bool)).astype(bool).sum()),
        "liquidity_ok": int(catalyst_df.get("catalyst_liquidity_ok", pd.Series(dtype=bool)).astype(bool).sum()),
        "manual_tickers": int(len(manual_df)) if manual_df is not None else 0,
        "manual_with_detected_catalyst": int(manual_df.get("catalyst_detected", pd.Series(dtype=bool)).astype(bool).sum()) if len(manual_df) else 0,
        "manual_with_dated_catalyst": int(manual_df.get("catalyst_date", pd.Series(dtype=str)).astype(str).str.len().gt(0).sum()) if len(manual_df) else 0,
        "trade_class_counts": dict(trade_counts),
        "output_path": str(output_path),
        "patch_results": patch_results,
        "top_event_convexity": event_convexity.sort_values(
            ["event_convexity_score", "catalyst_truth_score"], ascending=False
        )
        .head(20)[
            [
                "ticker",
                "catalyst_type",
                "catalyst_date",
                "catalyst_truth_score",
                "event_convexity_score",
                "catalyst_trade_class",
                "catalyst_reason_codes",
            ]
        ]
        .to_dict("records")
        if not event_convexity.empty
        else [],
    }
    summary_path = out_dir / f"catalyst_truth_summary_{run_id}.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Catalyst Truth Engine for an AVSHUNTER run.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--base-dir", default=None)
    parser.add_argument("--no-patch", action="store_true")
    args = parser.parse_args()
    summary = enrich_run(args.run_id, args.base_dir, patch_existing=not args.no_patch)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

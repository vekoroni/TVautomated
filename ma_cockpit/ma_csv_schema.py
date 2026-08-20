from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path


REQUIRED_COLUMNS = [
    "review_date",
    "event_id",
    "event_date",
    "source_name",
    "source_tier",
    "source_url",
    "headline",
    "event_type",
    "deal_status",
    "target_company",
    "target_ticker",
    "acquirer_company",
    "acquirer_ticker",
    "sector",
    "industry",
    "deal_value",
    "premium_to_last_close",
    "consideration_type",
    "cash_stock_mix",
    "rumour_flag",
    "confirmed_flag",
    "denied_flag",
    "second_source_count",
    "strategic_logic_score",
    "regulatory_plausibility_score",
    "source_quality_score",
    "price_confirmation_score",
    "options_confirmation_score",
    "sector_consolidation_score",
    "affected_ticker",
    "affected_company",
    "affected_role",
    "beneficiary_type",
    "expected_impact_direction",
    "expected_impact_strength",
    "dbs",
    "pipeline_candidate_flag",
    "pipeline_priority",
    "pipeline_reason",
    "ma_tps",
    "ma_rcs",
    "ma_pasp_state",
    "ma_street_state",
    "ma_trade_bias",
    "ma_verdict",
    "ma_confidence",
    "long_call_candidate",
    "long_put_candidate",
    "options_liquidity_status",
    "spread_pct_mid",
    "preferred_dte_min",
    "preferred_dte_max",
    "preferred_delta_min",
    "preferred_delta_max",
    "confirmed_facts",
    "assumptions",
    "missing_inputs",
    "failure_flags",
    "manual_reviewer_notes",
    "run_through_avshunter",
    "avshunter_route",
    "created_by",
    "last_updated",
]

EVENT_TYPES = {
    "MERGER",
    "ACQUISITION",
    "TAKEOVER_RUMOUR",
    "STRATEGIC_REVIEW",
    "ACTIVIST_PRESSURE",
    "DIVESTITURE",
    "SPINOFF",
    "JOINT_VENTURE",
    "ASSET_SALE",
    "PRIVATE_EQUITY_INTEREST",
    "HOSTILE_BID",
    "MANAGEMENT_BUYOUT",
    "CONSOLIDATION_THEME",
    "ANTITRUST_BLOCK",
    "DEAL_COLLAPSE",
    "DENIAL",
    "OTHER",
}

DEAL_STATUSES = {
    "RUMOUR",
    "UNCONFIRMED",
    "REPORTED",
    "CONFIRMED",
    "AGREED",
    "COMPLETED",
    "DENIED",
    "BLOCKED",
    "COLLAPSED",
}

SOURCE_TIERS = {"TIER_1", "TIER_2", "TIER_3", "TIER_4"}

AFFECTED_ROLES = {
    "TARGET",
    "ACQUIRER",
    "PEER",
    "SUPPLIER",
    "CUSTOMER",
    "COMPETITOR",
    "SECTOR_SYMPATHY",
    "REGULATORY_RISK",
    "COLLAPSE_RISK",
    "UNKNOWN",
}

BENEFICIARY_TYPES = {
    "DIRECT_DEAL_UPSIDE",
    "ACQUIRER_SYNERGY",
    "PEER_RERATING",
    "SCARCITY_VALUE",
    "SUPPLIER_VOLUME_UPSIDE",
    "CUSTOMER_PRICING_RISK",
    "COMPETITOR_PRESSURE",
    "REGULATORY_RELIEF",
    "RUMOUR_COLLAPSE_DOWNSIDE",
    "UNKNOWN",
}

IMPACT_DIRECTIONS = {"BULLISH", "BEARISH", "MIXED", "NEUTRAL", "UNKNOWN"}
PIPELINE_PRIORITIES = {"P1", "P2", "P3", "WATCH_ONLY", "DO_NOT_RUN"}
AVSHUNTER_ROUTES = {
    "FULL_PIPELINE",
    "DISCOVERY_ONLY",
    "OPTIONS_ONLY",
    "NEWS_WATCH_ONLY",
    "BLOCKED",
}
TRUE_VALUES = {"TRUE", "YES", "Y", "1"}
WEAK_OPTIONS_VALUES = {"WEAK", "POOR", "ILLQUID", "ILLIQUID"}
GO_VALUES = {"GO", "FULL_PIPELINE", "P1"}


@dataclass
class ValidationReport:
    path: str
    valid: bool
    errors: list[str]
    warnings: list[str]
    row_count: int


def create_ma_manual_review_template(output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=REQUIRED_COLUMNS)
        writer.writeheader()
    return path


def validate_ma_manual_review_csv(path: str | Path) -> ValidationReport:
    csv_path = Path(path)
    errors: list[str] = []
    warnings: list[str] = []

    with csv_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames or []
        missing = [column for column in REQUIRED_COLUMNS if column not in columns]
        if missing:
            errors.append(f"Missing required columns: {', '.join(missing)}")
            return ValidationReport(str(csv_path), False, errors, warnings, 0)

        row_count = 0
        for row_number, row in enumerate(reader, start=2):
            row_count += 1
            _validate_row(row_number, row, errors, warnings)

    return ValidationReport(str(csv_path), not errors, errors, warnings, row_count)


def _validate_row(
    row_number: int,
    row: dict[str, str],
    errors: list[str],
    warnings: list[str],
) -> None:
    source_tier = _norm(row.get("source_tier"))
    deal_status = _norm(row.get("deal_status"))
    event_type = _norm(row.get("event_type"))
    affected_role = _norm(row.get("affected_role"))
    beneficiary_type = _norm(row.get("beneficiary_type"))
    impact = _norm(row.get("expected_impact_direction"))
    priority = _norm(row.get("pipeline_priority"))
    route = _norm(row.get("avshunter_route"))
    street_state = _norm(row.get("ma_street_state"))
    options_status = _norm(row.get("options_liquidity_status"))
    notes = row.get("manual_reviewer_notes", "")
    second_source_count = _int_or_zero(row.get("second_source_count"))

    _check_enum(row_number, "source_tier", source_tier, SOURCE_TIERS, errors)
    _check_enum(row_number, "event_type", event_type, EVENT_TYPES, errors)
    _check_enum(row_number, "deal_status", deal_status, DEAL_STATUSES, errors)
    _check_enum(row_number, "affected_role", affected_role, AFFECTED_ROLES, errors)
    _check_enum(
        row_number,
        "beneficiary_type",
        beneficiary_type,
        BENEFICIARY_TYPES,
        errors,
    )
    _check_enum(
        row_number,
        "expected_impact_direction",
        impact,
        IMPACT_DIRECTIONS,
        errors,
    )
    _check_enum(
        row_number,
        "pipeline_priority",
        priority,
        PIPELINE_PRIORITIES,
        errors,
    )
    _check_enum(row_number, "avshunter_route", route, AVSHUNTER_ROUTES, errors)

    for ticker_field in ("target_ticker", "acquirer_ticker", "affected_ticker"):
        ticker = row.get(ticker_field, "")
        if ticker and ticker != ticker.upper():
            errors.append(f"Row {row_number}: {ticker_field} must be uppercase.")

    if _is_true(row.get("confirmed_flag")) and deal_status == "RUMOUR":
        errors.append(
            f"Row {row_number}: confirmed_flag TRUE cannot be paired with "
            "deal_status RUMOUR."
        )

    if _is_true(row.get("denied_flag")) and street_state != "DENIED":
        warnings.append(
            f"Row {row_number}: denied_flag TRUE should set ma_street_state to DENIED."
        )

    if _is_true(row.get("run_through_avshunter")) and not row.get("affected_ticker"):
        errors.append(
            f"Row {row_number}: run_through_avshunter TRUE requires affected_ticker."
        )

    if source_tier == "TIER_4" and second_source_count == 0:
        if priority == "P1" or route == "FULL_PIPELINE" or _norm(row.get("ma_verdict")) == "GO":
            errors.append(
                f"Row {row_number}: TIER_4 with no second source cannot be GO, "
                "P1, or FULL_PIPELINE."
            )

    if options_status in WEAK_OPTIONS_VALUES:
        if route in {"FULL_PIPELINE", "OPTIONS_ONLY"} or _norm(row.get("ma_verdict")) == "GO":
            errors.append(
                f"Row {row_number}: weak options liquidity blocks GO, "
                "FULL_PIPELINE, and OPTIONS_ONLY."
            )

    if _is_true(row.get("long_call_candidate")) and impact == "BEARISH":
        if "explicitly justified" not in notes.lower() and "call hedge" not in notes.lower():
            errors.append(
                f"Row {row_number}: long_call_candidate TRUE conflicts with "
                "BEARISH impact without explicit note justification."
            )

    if _is_true(row.get("long_put_candidate")) and impact == "BULLISH":
        if "explicitly justified" not in notes.lower() and "put hedge" not in notes.lower():
            errors.append(
                f"Row {row_number}: long_put_candidate TRUE conflicts with "
                "BULLISH impact without explicit note justification."
            )


def _check_enum(
    row_number: int,
    field: str,
    value: str,
    allowed: set[str],
    errors: list[str],
) -> None:
    if value and value not in allowed:
        errors.append(f"Row {row_number}: invalid {field} value {value!r}.")


def _norm(value: str | None) -> str:
    return (value or "").strip().upper()


def _is_true(value: str | None) -> bool:
    return _norm(value) in TRUE_VALUES


def _int_or_zero(value: str | None) -> int:
    try:
        return int((value or "0").strip() or "0")
    except ValueError:
        return 0

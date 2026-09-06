"""Validated structured contracts recovered from legacy model responses."""

from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping

from .models import CAPITAL_DENIED, EXECUTION_NONE
from .market_structure import MARKET_STRUCTURE_FIELDS


TRADE_BRIEF_FIELDS = (
    "ticker",
    "direction",
    "final_verdict",
    "trade_state",
    "horizon",
    "dte",
    "trigger_level",
    "kill_switch_level",
    "preferred_contract",
    "premium",
    "rr",
    "iv_context",
    "ivp",
    "earnings_in_window",
    "earnings_action",
    "max_pain_risk",
    "sector_confirmation_required",
    "first_hour_rule",
    "probe_permitted",
    "initial_adverse_tolerance",
    "capital_permission",
    "narrative_summary",
    "execution_permission",
    *MARKET_STRUCTURE_FIELDS,
)

JUNIOR_SECTION_TAGS = (
    "SECTION_1_MACRO",
    "SECTION_2_GAMMA",
    "SECTION_3_LIQUIDITY",
    "SECTION_4_THESIS",
    "SECTION_5_CHART",
    "SECTION_6_OPTIONS",
    "SECTION_7_RISK",
    "SECTION_8_VERDICT",
)


class SchemaValidationError(ValueError):
    def __init__(self, findings: tuple[str, ...]) -> None:
        self.findings = findings
        super().__init__("; ".join(findings))


def _frozen(value: Mapping[str, Any]) -> Mapping[str, Any]:
    return MappingProxyType(dict(value))


@dataclass(frozen=True, slots=True)
class TradeBrief:
    ticker: str
    direction: str
    final_verdict: str
    trade_state: str
    values: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "direction", self.direction.strip().upper())
        object.__setattr__(
            self, "final_verdict", self.final_verdict.strip().upper()
        )
        object.__setattr__(self, "trade_state", self.trade_state.strip().upper())
        object.__setattr__(self, "values", _frozen(self.values))

    @classmethod
    def from_row(cls, row: Mapping[str, Any], expected_ticker: str) -> "TradeBrief":
        findings = []
        ticker = str(row.get("ticker", "")).strip().upper()
        if ticker != expected_ticker.strip().upper():
            findings.append(
                f"TRADE_BRIEF_TICKER_MISMATCH:{ticker}:{expected_ticker.upper()}"
            )
        for key in ("direction", "final_verdict", "trade_state"):
            if not str(row.get(key, "")).strip():
                findings.append(f"TRADE_BRIEF_MISSING:{key}")
        if findings:
            raise SchemaValidationError(tuple(findings))
        values = {field: row.get(field, "") for field in TRADE_BRIEF_FIELDS}
        return cls(
            ticker=ticker,
            direction=str(row["direction"]),
            final_verdict=str(row["final_verdict"]),
            trade_state=str(row["trade_state"]),
            values=values,
        )

    def sovereign_row(
        self,
        *,
        effective_verdict: str,
        veto_codes: tuple[str, ...],
        eil_action: str,
    ) -> dict[str, Any]:
        row = {field: self.values.get(field, "") for field in TRADE_BRIEF_FIELDS}
        row.update(
            {
                "ticker": self.ticker,
                "direction": self.direction,
                "final_verdict": effective_verdict,
                "trade_state": "STOPPED"
                if effective_verdict == "STOP"
                else self.trade_state,
                "execution_permission": EXECUTION_NONE,
                "capital_permission": CAPITAL_DENIED,
                "sovereign_vetoes": "|".join(veto_codes),
                "eil_action": eil_action,
            }
        )
        return row


@dataclass(frozen=True, slots=True)
class JuniorBriefing:
    ticker: str
    sections: Mapping[str, str]

    def __post_init__(self) -> None:
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "sections", _frozen(self.sections))
        missing = tuple(tag for tag in JUNIOR_SECTION_TAGS if not self.sections.get(tag))
        if missing:
            raise SchemaValidationError(
                tuple(f"JUNIOR_MISSING:{tag}" for tag in missing)
            )


"""Strict parser for the existing tagged text response contract."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass

from .models import AnalysisPayload
from .schemas import (
    JUNIOR_SECTION_TAGS,
    JuniorBriefing,
    SchemaValidationError,
    TradeBrief,
)


@dataclass(frozen=True, slots=True)
class ParsedLegacyAnalysis:
    narrative: str
    trade_brief: TradeBrief
    junior_briefing: JuniorBriefing
    raw_response: str
    raw_story: str

    def to_payload(self) -> AnalysisPayload:
        return AnalysisPayload(
            proposed_verdict=self.trade_brief.final_verdict,
            narrative=self.narrative,
            trade_brief=dict(self.trade_brief.values),
            junior_briefing=dict(self.junior_briefing.sections),
            raw_response=self.raw_response,
            raw_story=self.raw_story,
        )


def extract_section(text: str, tag: str) -> str:
    match = re.search(
        rf"\[{re.escape(tag)}\](.*?)(?=\[[A-Z0-9_]+\]|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def parse_trade_brief(text: str, ticker: str) -> TradeBrief:
    raw = extract_section(text, "TRADE_BRIEF_CSV")
    if not raw:
        raise SchemaValidationError(("MAIN_MISSING:TRADE_BRIEF_CSV",))
    cleaned_lines = [
        line
        for line in raw.splitlines()
        if line.strip() not in {"", "---", "```", "```csv"}
    ]
    rows = list(csv.DictReader(io.StringIO("\n".join(cleaned_lines))))
    if len(rows) != 1:
        raise SchemaValidationError(
            (f"TRADE_BRIEF_ROW_COUNT:{len(rows)}:expected_1",)
        )
    return TradeBrief.from_row(rows[0], ticker)


def parse_junior_briefing(text: str, ticker: str) -> JuniorBriefing:
    match = re.search(
        rf"\[JUNIOR_BRIEFING_{re.escape(ticker.upper())}\]"
        r"(.*?)(?=\[JUNIOR_BRIEFING_[A-Z0-9._-]+\]|\Z)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise SchemaValidationError(
            (f"STORY_MISSING:JUNIOR_BRIEFING_{ticker.upper()}",)
        )
    wrapper = match.group(1)
    sections = {tag: extract_section(wrapper, tag) for tag in JUNIOR_SECTION_TAGS}
    return JuniorBriefing(ticker=ticker, sections=sections)


def parse_legacy_responses(
    *, ticker: str, main_response: str, story_response: str
) -> ParsedLegacyAnalysis:
    findings = []
    narrative = extract_section(main_response, f"TRADE_NARRATIVE_{ticker.upper()}")
    if not narrative:
        findings.append(f"MAIN_MISSING:TRADE_NARRATIVE_{ticker.upper()}")
    try:
        trade_brief = parse_trade_brief(main_response, ticker)
    except SchemaValidationError as exc:
        findings.extend(exc.findings)
        trade_brief = None
    try:
        junior = parse_junior_briefing(story_response, ticker)
    except SchemaValidationError as exc:
        findings.extend(exc.findings)
        junior = None
    if findings:
        raise SchemaValidationError(tuple(findings))
    assert trade_brief is not None
    assert junior is not None
    return ParsedLegacyAnalysis(
        narrative=narrative,
        trade_brief=trade_brief,
        junior_briefing=junior,
        raw_response=main_response,
        raw_story=story_response,
    )


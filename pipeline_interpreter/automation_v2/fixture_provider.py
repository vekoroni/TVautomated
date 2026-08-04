"""Offline provider backed by captured main/story response text."""

from __future__ import annotations

from dataclasses import dataclass

from .models import AnalysisPayload, TickerRunRequest
from .market_structure import enrich_trade_brief
from .parser import parse_legacy_responses


@dataclass(frozen=True, slots=True)
class FixtureResponseProvider:
    main_response: str
    story_response: str

    def analyze(self, request: TickerRunRequest) -> AnalysisPayload:
        payload = parse_legacy_responses(
            ticker=request.ticker,
            main_response=self.main_response,
            story_response=self.story_response,
        ).to_payload()
        return AnalysisPayload(
            proposed_verdict=payload.proposed_verdict,
            narrative=payload.narrative,
            trade_brief=enrich_trade_brief(payload.trade_brief, request),
            junior_briefing=payload.junior_briefing,
            raw_response=payload.raw_response,
            raw_story=payload.raw_story,
        )

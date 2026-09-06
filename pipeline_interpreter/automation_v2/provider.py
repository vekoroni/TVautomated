"""Injected adapter for the existing Claude prompt/call workflow."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Callable, Protocol

from .models import AnalysisPayload, TickerRunRequest
from .market_structure import enrich_trade_brief
from .parser import parse_legacy_responses
from .schemas import TRADE_BRIEF_FIELDS


class PromptFactory(Protocol):
    def build_main(self, request: TickerRunRequest) -> str:
        ...

    def build_story(self, request: TickerRunRequest, main_response: str) -> str:
        ...


LegacyCall = Callable[..., str]
PromptBuilder = Callable[..., str]
StageRecorder = Callable[[str, str], None]


@dataclass(slots=True)
class LegacyEnginePromptFactory:
    """Adapt existing prompt builders while supplying one complete context.

    `single_ticker_builder` is used for both image and no-image runs. Images are
    media attachments, not a reason to select the narrower chart-only prompt.
    """

    single_ticker_builder: PromptBuilder
    story_builder: PromptBuilder

    @staticmethod
    def _options(request: TickerRunRequest) -> dict[str, str]:
        return {
            f"option_context_{index + 1}": json.dumps(dict(row), sort_keys=True)
            for index, row in enumerate(request.option_context)
        }

    @staticmethod
    def _authoritative_context(request: TickerRunRequest) -> str:
        context = {
            "ticker": request.ticker,
            "run_id": request.run_id,
            "invocation_id": request.invocation_id,
            "lab_context": dict(request.lab_context),
            "macro_context": dict(request.macro_context),
            "sector_context": dict(request.sector_context),
            "live_validation": dict(request.live_validation),
            "trader_note": request.trader_note,
            "evidence_findings": list(request.manifest.validate()),
        }
        return (
            "\n\n[AUTOMATION_V2_AUTHORITATIVE_CONTEXT]\n"
            + json.dumps(context, indent=2, sort_keys=True)
            + "\n[END_AUTOMATION_V2_AUTHORITATIVE_CONTEXT]\n"
        )

    def build_main(self, request: TickerRunRequest) -> str:
        context = self._authoritative_context(request)
        lab = json.dumps(dict(request.lab_context), indent=2, sort_keys=True)
        legacy_prompt = self.single_ticker_builder(
            request.ticker,
            dict(request.pipeline_row),
            options_data=self._options(request),
            ticker_note=request.trader_note,
            context_block=context,
            lab_context_block=lab,
            chart_images_present=bool(request.chart_assets),
        )
        header = ",".join(TRADE_BRIEF_FIELDS)
        structured_first = (
            "AUTOMATION V2 OUTPUT ORDER â€” MANDATORY:\n"
            "Your response MUST start with [TRADE_BRIEF_CSV], followed immediately "
            "by exactly one CSV header and exactly one ticker row. Do not put prose "
            "before this block. Use this exact header:\n"
            f"{header}\n"
            f"Set ticker={request.ticker}. Set execution_permission="
            "NONE_PIPELINE_INTERPRETER_ONLY and capital_permission="
            "CAPITAL_DENIED_PENDING_LIVE_CONFIRMATION. After the CSV row, emit "
            f"[TRADE_NARRATIVE_{request.ticker}] and then the full narrative. "
            "Structured output comes first so it cannot be lost to narrative "
            "length.\n\n"
        )
        return structured_first + legacy_prompt + context

    def build_story(self, request: TickerRunRequest, main_response: str) -> str:
        prompt = self.story_builder(
            ticker=request.ticker,
            pipeline_row=dict(request.pipeline_row),
            options_data=self._options(request),
            chart_images=list(request.chart_assets),
            ticker_note=request.trader_note,
            update_type="FULL",
        )
        return (
            prompt
            + self._authoritative_context(request)
            + "\n[VALIDATED_MAIN_RESPONSE_FOR_STORY]\n"
            + main_response
            + "\n[END_VALIDATED_MAIN_RESPONSE_FOR_STORY]\n"
        )


@dataclass(slots=True)
class LegacyClaudeProvider:
    """Use legacy call semantics without importing legacy process globals.

    The caller injects both prompt construction and API invocation. The same
    complete request and chart list feed both model stages, eliminating the old
    image/no-image context divergence at this boundary.
    """

    prompt_factory: PromptFactory
    api_call: LegacyCall
    model: str | None = None
    main_max_tokens: int | None = None
    story_max_tokens: int = 12000
    use_web_search: bool = True
    stage_recorder: StageRecorder | None = None

    def analyze(self, request: TickerRunRequest) -> AnalysisPayload:
        images = list(request.chart_assets)
        main_prompt = self.prompt_factory.build_main(request)
        main_response = self.api_call(
            main_prompt,
            images=images or None,
            use_web_search=self.use_web_search,
            model=self.model,
            max_tokens=self.main_max_tokens,
        )
        if self.stage_recorder:
            self.stage_recorder("main", main_response)
        story_prompt = self.prompt_factory.build_story(request, main_response)
        story_response = self.api_call(
            story_prompt,
            images=images or None,
            use_web_search=self.use_web_search,
            model=self.model,
            max_tokens=self.story_max_tokens,
        )
        if self.stage_recorder:
            self.stage_recorder("story", story_response)
        payload = parse_legacy_responses(
            ticker=request.ticker,
            main_response=main_response,
            story_response=story_response,
        ).to_payload()
        return AnalysisPayload(
            proposed_verdict=payload.proposed_verdict,
            narrative=payload.narrative,
            trade_brief=enrich_trade_brief(payload.trade_brief, request),
            junior_briefing=payload.junior_briefing,
            raw_response=payload.raw_response,
            raw_story=payload.raw_story,
        )


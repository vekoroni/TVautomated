"""Lazy construction of the existing Claude provider in shadow mode."""

from __future__ import annotations

import os
import re
from pathlib import Path

from .provider import LegacyClaudeProvider, LegacyEnginePromptFactory


def _load_repository_anthropic_key(env_path: str | Path) -> str:
    """Read one key without logging it or inheriting stale process precedence."""
    path = Path(env_path)
    if not path.is_file():
        raise RuntimeError(f"shadow credential file is missing: {path}")
    matches = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if re.match(r"^\s*(?:export\s+)?ANTHROPIC_API_KEY\s*=", line):
            value = line.split("=", 1)[1].strip()
            if len(value) >= 2 and value[0] in "\"'" and value[-1] == value[0]:
                value = value[1:-1]
            matches.append(value)
    if len(matches) != 1:
        raise RuntimeError(
            f"expected one ANTHROPIC_API_KEY definition in {path}; "
            f"found {len(matches)}"
        )
    key = matches[0]
    if not key.startswith("sk-ant-") or any(char.isspace() for char in key):
        raise RuntimeError("repository Anthropic credential has invalid format")
    return key


def create_live_shadow_provider(
    *,
    model: str | None = None,
    main_max_tokens: int | None = None,
    story_max_tokens: int = 12000,
    use_web_search: bool = True,
    stage_recorder=None,
) -> LegacyClaudeProvider:
    """Import legacy callables lazily so offline tests need no API package."""
    repository_root = Path(__file__).resolve().parents[2]
    key = _load_repository_anthropic_key(repository_root / ".env")
    # This process is the isolated shadow CLI. Override the stale inherited value
    # before importing the legacy engine, then explicitly align its module value
    # if another import loaded it earlier in this process.
    os.environ["ANTHROPIC_API_KEY"] = key
    from pipeline_interpreter import pipeline_interpreter_engine as engine

    engine.ANTHROPIC_API_KEY = key

    return LegacyClaudeProvider(
        prompt_factory=LegacyEnginePromptFactory(
            single_ticker_builder=engine.build_single_ticker_prompt,
            story_builder=engine.build_story_prompt,
        ),
        api_call=engine.call_api,
        model=model or engine.MODEL_DEEP_DIVE,
        main_max_tokens=main_max_tokens,
        story_max_tokens=story_max_tokens,
        use_web_search=use_web_search,
        stage_recorder=stage_recorder,
    )

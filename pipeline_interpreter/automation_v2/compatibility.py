"""Compatibility contracts for legacy ticker artifacts."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


MAIN_REQUIRED_SECTIONS = ("TRADE_NARRATIVE", "TRADE_BRIEF_CSV")
STORY_REQUIRED_SECTIONS = (
    "JUNIOR_BRIEFING",
    "SECTION_1_MACRO",
    "SECTION_2_GAMMA",
    "SECTION_3_LIQUIDITY",
    "SECTION_4_THESIS",
    "SECTION_5_CHART",
    "SECTION_6_OPTIONS",
    "SECTION_7_RISK",
    "SECTION_8_VERDICT",
)


@dataclass(frozen=True, slots=True)
class ArtifactContract:
    ticker: str
    main_sections: tuple[str, ...]
    story_sections: tuple[str, ...]
    missing_required: tuple[str, ...]
    files: tuple[str, ...]
    hashes: tuple[tuple[str, str], ...]
    complete: bool


def _sections(text: str) -> tuple[str, ...]:
    return tuple(dict.fromkeys(re.findall(r"\[([A-Z0-9_]+)\]", text)))


def _has_prefix(sections: tuple[str, ...], expected: str) -> bool:
    return any(section == expected or section.startswith(f"{expected}_") for section in sections)


def profile_legacy_artifacts(
    *, ticker: str, raw_response: str | Path, raw_story: str | Path, html: str | Path
) -> ArtifactContract:
    paths = tuple(Path(value) for value in (raw_response, raw_story, html))
    for path in paths:
        if not path.is_file():
            raise FileNotFoundError(path)
    main_sections = _sections(paths[0].read_text(encoding="utf-8-sig"))
    story_sections = _sections(paths[1].read_text(encoding="utf-8-sig"))
    missing = [
        f"main:{section}"
        for section in MAIN_REQUIRED_SECTIONS
        if not _has_prefix(main_sections, section)
    ]
    missing.extend(
        f"story:{section}"
        for section in STORY_REQUIRED_SECTIONS
        if not _has_prefix(story_sections, section)
    )
    hashes = []
    for path in paths:
        hashes.append((path.name, hashlib.sha256(path.read_bytes()).hexdigest()))
    return ArtifactContract(
        ticker=ticker.strip().upper(),
        main_sections=main_sections,
        story_sections=story_sections,
        missing_required=tuple(missing),
        files=tuple(path.name for path in paths),
        hashes=tuple(hashes),
        complete=not missing,
    )

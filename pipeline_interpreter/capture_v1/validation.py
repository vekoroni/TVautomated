"""Deterministic image checks applied before a capture can be manifested."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class ImageValidation:
    width: int
    height: int
    format: str
    findings: tuple[str, ...]

    @property
    def valid(self) -> bool:
        return not self.findings


def validate_png(
    path: Path,
    *,
    minimum_width: int = 800,
    minimum_height: int = 500,
    minimum_size_bytes: int = 10_000,
) -> ImageValidation:
    findings: list[str] = []
    if not path.is_file():
        return ImageValidation(0, 0, "", ("CAPTURE_FILE_MISSING",))
    if path.stat().st_size < minimum_size_bytes:
        findings.append(f"CAPTURE_FILE_TOO_SMALL:{path.stat().st_size}")
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            width, height = image.size
            image_format = image.format or ""
            extrema = image.convert("RGB").getextrema()
    except Exception as exc:
        return ImageValidation(0, 0, "", (f"INVALID_IMAGE:{type(exc).__name__}",))
    if image_format.upper() != "PNG":
        findings.append(f"INVALID_IMAGE_FORMAT:{image_format}")
    if width < minimum_width or height < minimum_height:
        findings.append(f"CAPTURE_DIMENSIONS_TOO_SMALL:{width}x{height}")
    if all(high - low <= 2 for low, high in extrema):
        findings.append("CAPTURE_APPEARS_BLANK")
    return ImageValidation(width, height, image_format, tuple(findings))

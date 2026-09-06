"""Provider-neutral MSI-7b screenshot extraction boundary.

No model implementation is activated here.  The contract permits only true
depth/order-book, NOII and broker-only tape evidence and requires explicit
operator identity confirmation before an extraction can enter a bundle.
"""

from __future__ import annotations

import hashlib
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Mapping


class ScreenType(str, Enum):
    LEVEL2_ORDER_BOOK = "LEVEL2_ORDER_BOOK"
    NOII = "NOII"
    BROKER_TAPE = "BROKER_TAPE"


class CaptureTimeProvenance(str, Enum):
    OPERATOR_DECLARED = "OPERATOR_DECLARED"
    SCREEN_VISIBLE = "SCREEN_VISIBLE"


@dataclass(frozen=True, slots=True)
class ScreenshotExtractionRequest:
    run_id: str
    ticker: str
    bundle_id: str
    screen_type: ScreenType
    image_path: Path
    capture_time_utc: str
    capture_time_provenance: CaptureTimeProvenance
    operator_confirmed_ticker: bool
    operator_confirmed_screen_type: bool
    operator_confirmed_capture_time: bool

    def __post_init__(self) -> None:
        image = Path(self.image_path).resolve()
        if not self.run_id.strip() or not self.ticker.strip() or not self.bundle_id.strip():
            raise ValueError("SCREEN_IDENTITY_REQUIRED")
        if not image.is_file():
            raise ValueError("SCREEN_IMAGE_MISSING")
        if not all((
            self.operator_confirmed_ticker,
            self.operator_confirmed_screen_type,
            self.operator_confirmed_capture_time,
        )):
            raise ValueError("SCREEN_OPERATOR_CONFIRMATION_REQUIRED")
        object.__setattr__(self, "ticker", self.ticker.strip().upper())
        object.__setattr__(self, "image_path", image)

    @property
    def image_sha256(self) -> str:
        return hashlib.sha256(self.image_path.read_bytes()).hexdigest()


@dataclass(frozen=True, slots=True)
class ScreenshotExtractionResult:
    request: ScreenshotExtractionRequest
    model_id: str
    prompt_version: str
    prompt_hash: str
    extracted: Mapping[str, Any]
    quality: str
    authority: str = "SUPPLEMENTAL_NON_AUTHORITY"


class ScreenshotExtractionAdapter(ABC):
    @abstractmethod
    def extract(self, request: ScreenshotExtractionRequest) -> ScreenshotExtractionResult:
        """Extract supplemental evidence without changing governed fields."""
        raise NotImplementedError


__all__ = [
    "CaptureTimeProvenance", "ScreenType", "ScreenshotExtractionAdapter",
    "ScreenshotExtractionRequest", "ScreenshotExtractionResult",
]


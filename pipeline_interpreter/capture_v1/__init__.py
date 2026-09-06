"""Isolated, read-only screenshot capture adapter for Pipeline Interpreter."""

from .contracts import CaptureMode, CaptureRequest, CaptureResult, CaptureStatus
from .service import run_capture

__all__ = ("CaptureMode", "CaptureRequest", "CaptureResult", "CaptureStatus", "run_capture")


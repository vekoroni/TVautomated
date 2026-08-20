# =========================
# FILE: vanguard/__init__.py
# =========================
"""
vanguard package public API

Keep this file in lock-step with vanguard/main.py exports.
This prevents ImportError regressions in orchestrator scripts.
"""

from .main import VanguardEngine, analyze_ticker

__all__ = ["VanguardEngine", "analyze_ticker"]


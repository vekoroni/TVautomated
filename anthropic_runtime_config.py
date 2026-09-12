"""Persistent non-secret Anthropic workspace selection for unattended runs.

An explicit environment setting overrides repository configuration. API keys
remain in the environment; this file never loads or stores credentials.
"""
import json
import os
from pathlib import Path
import re

CONFIG_PATH = Path(__file__).resolve().parent / "config" / "anthropic_runtime.json"


def workspace_id():
    value = os.environ.get("ANTHROPIC_WORKSPACE_ID", "").strip()
    if not value:
        try:
            config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            raise RuntimeError(
                "ANTHROPIC_WORKSPACE_ID is required: set the environment variable "
                "or configure config/anthropic_runtime.json"
            ) from None
        if type(config) is not dict or set(config) != {"workspace_id"}:
            raise RuntimeError("invalid Anthropic runtime configuration fields")
        value = config["workspace_id"]
    if type(value) is not str or re.fullmatch(r"wrkspc_[A-Za-z0-9]+", value) is None:
        raise RuntimeError("Anthropic workspace selection must be a valid wrkspc_ identifier")
    return value

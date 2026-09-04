"""Provider-independent option contract reference rules.

MarketData chains normally carry ``contractMultiplier``. When an otherwise
complete chain row omits it, the pipeline may infer the OCC standard 100-share
multiplier only for an unambiguously standard OCC symbol. Adjusted roots often
contain a numeric suffix; those and all malformed symbols remain unresolved.
"""

from __future__ import annotations

import re
from typing import Any, Dict

# Compatibility imports. New code must import from option_identity; these
# aliases let older canonical readers migrate without a second OCC parser.
from .option_identity import build_occ_symbol, normalise_occ_symbol, parse_occ_symbol


_STANDARD_OCC_RE = re.compile(
    r"^(?:O:)?(?P<root>[A-Z.]{1,6})(?P<expiry>\d{6})"
    r"(?P<side>[CP])(?P<strike>\d{8})$",
    re.IGNORECASE,
)


def infer_standard_occ_multiplier(symbol: Any) -> Dict[str, Any]:
    """Return a governed inference record for a standard OCC contract."""

    text = "" if symbol is None else str(symbol).strip().upper().replace(" ", "")
    if not _STANDARD_OCC_RE.fullmatch(text):
        return {
            "multiplier": None,
            "source": "UNRESOLVED_NONSTANDARD_OR_ADJUSTED_OCC",
            "inferred": False,
            "reason": "symbol is not an unambiguous standard OCC contract",
        }
    return {
        "multiplier": 100.0,
        "source": "OCC_STANDARD_100_INFERRED",
        "inferred": True,
        "reason": "standard OCC deliverable convention",
    }

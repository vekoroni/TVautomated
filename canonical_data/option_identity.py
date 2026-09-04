"""Single canonical compact-OCC identity owner.

Provider prefixes and spaces are boundary concerns.  Internally every option
identity is the compact uppercase OCC representation.  Numeric adjusted roots
remain distinct and are deliberately not rewritten.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import re
from typing import Any


_OCC = re.compile(
    r"^(?P<root>[A-Z0-9.]{1,12})(?P<expiry>\d{6})"
    r"(?P<side>[CP])(?P<strike>\d{8})$"
)


@dataclass(frozen=True, slots=True)
class OptionIdentity:
    symbol: str
    root: str
    expiry: date
    side: str
    strike: float

    def to_dict(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "root": self.root,
            "expiry": self.expiry.isoformat(),
            "side": self.side,
            "strike": self.strike,
        }


def normalise_occ_symbol(value: Any) -> str:
    text = "" if value is None else str(value).strip().upper().replace(" ", "")
    if text.startswith("O:"):
        text = text[2:]
    match = _OCC.fullmatch(text)
    if not match:
        raise ValueError(f"invalid OCC symbol: {value!r}")
    # Parsing the date rejects syntactically valid but impossible expiries.
    datetime.strptime(match.group("expiry"), "%y%m%d")
    return text


def parse_occ_symbol(value: Any) -> OptionIdentity:
    symbol = normalise_occ_symbol(value)
    match = _OCC.fullmatch(symbol)
    assert match is not None
    return OptionIdentity(
        symbol=symbol,
        root=match.group("root"),
        expiry=datetime.strptime(match.group("expiry"), "%y%m%d").date(),
        side="CALL" if match.group("side") == "C" else "PUT",
        strike=int(match.group("strike")) / 1000.0,
    )


def build_occ_symbol(root: Any, expiry: date | str, side: Any, strike: Any) -> str:
    clean_root = str(root).strip().upper().replace(" ", "")
    expiry_date = expiry if isinstance(expiry, date) else date.fromisoformat(str(expiry)[:10])
    side_text = str(side).strip().upper()
    side_code = "C" if side_text in {"C", "CALL"} else "P" if side_text in {"P", "PUT"} else ""
    if not clean_root or not side_code:
        raise ValueError("root and CALL/PUT side are required")
    strike_code = int(round(float(strike) * 1000.0))
    return normalise_occ_symbol(
        f"{clean_root}{expiry_date.strftime('%y%m%d')}{side_code}{strike_code:08d}"
    )

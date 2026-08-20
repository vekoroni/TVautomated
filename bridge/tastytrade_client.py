from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class TastytradeConfig:
    username: str
    password: str
    account_number: str
    paper: bool = True


def load_config_from_env() -> TastytradeConfig:
    return TastytradeConfig(
        username=os.getenv("TASTYTRADE_USERNAME", ""),
        password=os.getenv("TASTYTRADE_PASSWORD", ""),
        account_number=os.getenv("TASTYTRADE_ACCOUNT_NUMBER", ""),
        paper=os.getenv("TASTYTRADE_PAPER", "1").strip() != "0",
    )


def build_occ_symbol(ticker: str, expiry_yyyymmdd: str, call_put: str, strike: float) -> str:
    expiry = expiry_yyyymmdd.replace("-", "")[2:]
    cp = "C" if str(call_put).upper().startswith("C") else "P"
    strike_part = f"{int(round(float(strike) * 1000)):08d}"
    return f"{str(ticker).upper().ljust(6)}{expiry}{cp}{strike_part}"


class TastytradeClient:
    """Deliberately non-trading placeholder until paper/live phases are approved."""

    def __init__(self, config: TastytradeConfig | None = None):
        self.config = config or load_config_from_env()

    def assert_configured(self) -> None:
        missing = [
            name
            for name, value in {
                "TASTYTRADE_USERNAME": self.config.username,
                "TASTYTRADE_PASSWORD": self.config.password,
                "TASTYTRADE_ACCOUNT_NUMBER": self.config.account_number,
            }.items()
            if not value
        ]
        if missing:
            raise RuntimeError(f"Missing Tastytrade environment variables: {', '.join(missing)}")


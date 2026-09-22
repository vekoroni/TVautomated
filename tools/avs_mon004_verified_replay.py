"""Read-only stored-cohort replay through verified Phantom outcome revisions."""

from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime, timezone
from pathlib import Path

from canonical_data.historical_prices import DEFAULT_ADJUSTMENT
from canonical_data.phantom_outcome_source import PhantomOutcomeSourceReader
from tools.avs_mon004_canary import _sample_assessments, connect_read_only


def replay(
    control_path: Path, price_path: Path, phantom_path: Path,
) -> dict:
    now = datetime.now(timezone.utc)
    control = connect_read_only(control_path)
    prices = connect_read_only(price_path)
    reader = PhantomOutcomeSourceReader(control_path, phantom_path)
    by_horizon = {h: Counter() for h in (1, 5)}
    errors = Counter()
    sampled = 0
    try:
        for item in _sample_assessments(control):
            origin_date = date.fromisoformat(item["origin_session_date"])
            if origin_date >= now.date():
                continue
            sessions = tuple(date.fromisoformat(row[0]) for row in prices.execute(
                """SELECT trading_date FROM ohlcv_daily
                WHERE ticker=? AND trading_date>? AND bar_status='COMPLETE'
                  AND adjustment_convention=? AND observed_at<=?
                ORDER BY trading_date LIMIT 5""",
                (item["ticker"], origin_date.isoformat(),
                 DEFAULT_ADJUSTMENT, now.isoformat()),
            ))
            if not sessions:
                continue
            sampled += 1
            try:
                verified = reader.read_sessions(
                    ticker=item["ticker"],
                    contract_symbol=item["contract_symbol"],
                    sessions=sessions,
                    assessment_cutoff_utc=datetime.fromisoformat(
                        item["evidence_cutoff_utc"].replace("Z", "+00:00")
                    ),
                    evaluation_cutoff_utc=now,
                )
            except Exception as error:
                errors[f"{type(error).__name__}:{error}"] += 1
                continue
            available = {quote.observation.session_date for quote in verified}
            two_sided = {
                quote.observation.session_date for quote in verified
                if quote.observation.two_sided
            }
            for horizon in (1, 5):
                if len(sessions) < horizon:
                    by_horizon[horizon]["underlying_not_mature"] += 1
                    continue
                span = set(sessions[:horizon])
                by_horizon[horizon]["full_verified_path" if span <= available
                              else "partial_or_zero_verified_path"] += 1
                by_horizon[horizon]["full_two_sided_path" if span <= two_sided
                              else "partial_or_zero_two_sided_path"] += 1
        return {
            "as_of_utc": now.isoformat(),
            "production_access": "read-only only; no labels or source rows written",
            "sample_with_future_underlying": sampled,
            "by_horizon": {str(h): dict(value) for h, value in by_horizon.items()},
            "provenance_errors": dict(errors),
        }
    finally:
        control.close()
        prices.close()


if __name__ == "__main__":
    print(json.dumps(replay(
        Path("data/canonical/control_plane.sqlite"),
        Path("data/canonical/historical_prices.sqlite"),
        Path("data/phantom/phantom_history.db"),
    ), indent=2))

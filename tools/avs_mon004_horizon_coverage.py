"""Read-only reason census for exact-contract five-session path gaps.

This is an evidence-presence diagnostic, not a price-return backtest. The
outcome reader still checks immutable hashes and point-in-time availability.
"""

from __future__ import annotations

import json
from collections import Counter
from contextlib import closing
from datetime import date
from pathlib import Path

from canonical_data.historical_prices import DEFAULT_ADJUSTMENT
from canonical_data.option_identity import parse_occ_symbol
from tools.avs_mon004_batch_canary import select_families
from tools.avs_mon004_canary import connect_read_only


def audit(control_path: Path, price_path: Path, phantom_path: Path,
          *, per_direction: int = 50) -> dict:
    with closing(connect_read_only(control_path)) as control, \
            closing(connect_read_only(price_path)) as prices, \
            closing(connect_read_only(phantom_path)) as phantom:
        families = select_families(control, per_direction=per_direction)
        cells: dict[int, Counter[str]] = {day: Counter() for day in range(1, 6)}
        session_dates: dict[int, Counter[str]] = {day: Counter() for day in range(1, 6)}
        by_direction: dict[str, Counter[str]] = {
            "CALL": Counter(), "PUT": Counter(),
        }
        quote_cache: dict[tuple[str, str, str], str] = {}
        chain_cache: dict[tuple[str, str], bool] = {}
        absent_context: dict[int, Counter[str]] = {day: Counter() for day in range(1, 6)}
        assessed = mature = expired_cells = 0
        for family in families:
            assessments = control.execute(
                """SELECT a.contract_symbol,d.session_date AS origin_session
                FROM doi_contract_assessments AS a
                JOIN option_contract_observations AS o
                  ON o.observation_id=a.observation_id
                JOIN dataset_registry AS d ON d.dataset_id=o.source_dataset_id
                WHERE a.family_id=?""", (family["family_id"],),
            ).fetchall()
            for assessment in assessments:
                assessed += 1
                sessions = [row[0] for row in prices.execute(
                    """SELECT trading_date FROM ohlcv_daily
                    WHERE ticker=? AND trading_date>? AND bar_status='COMPLETE'
                      AND adjustment_convention=?
                    ORDER BY trading_date LIMIT 5""",
                    (family["ticker"], assessment["origin_session"],
                     DEFAULT_ADJUSTMENT),
                )]
                if len(sessions) < 5:
                    continue
                mature += 1
                expiry = parse_occ_symbol(assessment["contract_symbol"]).expiry
                for day, session in enumerate(sessions, start=1):
                    session_dates[day][session] += 1
                    key = (family["ticker"], assessment["contract_symbol"], session)
                    if key not in quote_cache:
                        registered = control.execute(
                            """SELECT 1 FROM option_contract_observations AS o
                            JOIN dataset_registry AS d
                              ON d.dataset_id=o.source_dataset_id
                            WHERE o.ticker=? AND o.contract_symbol=?
                              AND d.session_date=? LIMIT 1""", key,
                        ).fetchone()
                        revision = phantom.execute(
                            """SELECT 1 FROM canonical_option_chain_revisions
                            WHERE ticker=? AND option_symbol=? AND quote_date=?
                            LIMIT 1""", key,
                        ).fetchone()
                        raw = phantom.execute(
                            """SELECT 1 FROM chain_snapshots
                            WHERE ticker=? AND option_symbol=? AND quote_date=?
                            LIMIT 1""", key,
                        ).fetchone()
                        quote_cache[key] = (
                            "REGISTERED_OBSERVATION" if registered else
                            "CANONICAL_REVISION_PRESENT" if revision else
                            "UNVERSIONED_SNAPSHOT_ONLY" if raw else
                            "NO_EXACT_CONTRACT_QUOTE"
                        )
                    state = quote_cache[key]
                    cells[day][state] += 1
                    by_direction[family["governed_direction"]][state] += 1
                    if state == "NO_EXACT_CONTRACT_QUOTE":
                        chain_key = (family["ticker"], session)
                        if chain_key not in chain_cache:
                            chain_cache[chain_key] = bool(control.execute(
                                """SELECT 1 FROM dataset_registry WHERE
                                instrument_id=? AND session_date=?
                                AND dataset_type='OPTION_CHAIN'
                                AND completeness_status='COMPLETE' LIMIT 1""",
                                chain_key,
                            ).fetchone())
                        absent_context[day][
                            "CONTRACT_ABSENT_IN_EXISTING_CHAIN" if chain_cache[chain_key]
                            else "NO_CANONICAL_TICKER_CHAIN"
                        ] += 1
                    if date.fromisoformat(session) > expiry:
                        expired_cells += 1
                        cells[day]["AFTER_CONTRACT_EXPIRY"] += 1
        return {
            "families": len(families), "assessments": assessed,
            "five_session_mature_assessments": mature,
            "by_relative_session": {str(day): dict(counts)
                                    for day, counts in cells.items()},
            "session_dates": {str(day): dict(counts)
                              for day, counts in session_dates.items()},
            "absent_quote_context": {str(day): dict(counts)
                                     for day, counts in absent_context.items()},
            "by_direction": {key: dict(value)
                             for key, value in by_direction.items()},
            "after_expiry_cells": expired_cells,
            "caveat": "presence only; individual hashes, quote time and two-sidedness require the governed reader",
            "production_access": "read-only",
        }


if __name__ == "__main__":
    print(json.dumps(audit(
        Path("data/canonical/control_plane.sqlite"),
        Path("data/canonical/historical_prices.sqlite"),
        Path("data/phantom/phantom_history.db"),
    ), indent=2, sort_keys=True))

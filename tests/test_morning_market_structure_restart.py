from __future__ import annotations

from morning_gate import _market_structure_populations


def test_market_structure_authority_is_stable_when_go_population_changes() -> None:
    live_map = {
        "AAA": {"live_price": 101.0},
        "BBB": {"live_price": 99.0},
        "CCC": {"live_price": 50.0},
    }
    first = [
        {"ticker": "AAA", "verdict": "GO"},
        {"ticker": "BBB", "verdict": "FLAG"},
        {"ticker": "CCC", "verdict": "BLOCK"},
    ]
    second = [
        {"ticker": "AAA", "verdict": "FLAG"},
        {"ticker": "BBB", "verdict": "GO"},
        {"ticker": "CCC", "verdict": "BLOCK"},
    ]

    first_worklist, first_calculations, first_live = (
        _market_structure_populations(first, live_map)
    )
    second_worklist, second_calculations, second_live = (
        _market_structure_populations(second, live_map)
    )

    assert first_worklist == second_worklist == ("AAA", "BBB", "CCC")
    assert [row["ticker"] for row in first_calculations] == ["AAA"]
    assert [row["ticker"] for row in second_calculations] == ["BBB"]
    assert set(first_live) == {"AAA"}
    assert set(second_live) == {"BBB"}


def test_market_structure_never_calculates_without_live_data() -> None:
    worklist, calculations, calculation_live = _market_structure_populations(
        [
            {"ticker": "AAA", "verdict": "GO"},
            {"ticker": "BBB", "verdict": "GO"},
        ],
        {"AAA": {"live_price": 101.0}},
    )

    assert worklist == ("AAA",)
    assert [row["ticker"] for row in calculations] == ["AAA"]
    assert set(calculation_live) == {"AAA"}

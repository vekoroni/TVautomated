"""The anticipated-move horizon has one owner: Discovery (ACK, 18 Sep 2026).

Run 20260918_112522: the Horizon Router never receives the thesis hold days, so it bucketed every row by the
chosen contract's expiry (DTE_FALLBACK_LOW_CONFIDENCE) and overwrote horizon_bucket downstream. Because the
pipeline deliberately buys more runway than the move (64/92-day contracts), 1,036 rows whose thesis was 1-10
sessions were relabelled 11_20d. The router's expiry bucket is kept, under its own name; its block (no
direction / no instrument) is carried by horizon_action = BLOCKED.
"""

from __future__ import annotations

import pandas as pd

import intelligent_orchestrator as orch


def _patch(tmp_path, monkeypatch, target_rows, routes):
    run_id = "RUN1"
    horizon_dir = tmp_path / run_id / "horizon"
    horizon_dir.mkdir(parents=True)
    for bucket, rows in routes.items():
        pd.DataFrame(rows).to_csv(horizon_dir / f"horizon_{bucket}_{run_id}.csv", index=False)
    target = tmp_path / "target.csv"
    pd.DataFrame(target_rows).to_csv(target, index=False)
    monkeypatch.setattr(orch.cfg, "RUNS_DIR", tmp_path)
    assert orch.patch_horizon_fields_into_csv(run_id, target, "test")
    return pd.read_csv(target).set_index("ticker")


def _route(ticker, action="GO_SELECTIVE", reason=""):
    return {"ticker": ticker, "horizon_action": action, "horizon_size_multiplier": 1.0,
            "horizon_block_reason": reason, "horizon_source": "DTE_FALLBACK_LOW_CONFIDENCE",
            "router_version": "v2"}


def test_a_long_dated_contract_does_not_relabel_the_thesis_horizon(tmp_path, monkeypatch):
    out = _patch(tmp_path, monkeypatch,
                 [{"ticker": "AAA", "horizon_bucket": "1_5d"}, {"ticker": "BBB", "horizon_bucket": "6_10d"}],
                 {"11_20d": [_route("AAA")], "6_10d": [_route("BBB")]})
    assert out.loc["AAA", "horizon_bucket"] == "1_5d"
    assert out.loc["AAA", "contract_expiry_bucket"] == "11_20d"      # the router's view, under its own name
    assert out.loc["AAA", "planned_hold_sessions"] == 20              # hold unchanged: sets contract runway downstream
    assert out.loc["BBB", "horizon_bucket"] == "6_10d" and out.loc["BBB", "planned_hold_sessions"] == 10


def test_a_router_block_is_carried_by_the_action_not_by_the_horizon(tmp_path, monkeypatch):
    out = _patch(tmp_path, monkeypatch, [{"ticker": "BZ", "horizon_bucket": "1_5d"}],
                 {"blocked": [_route("BZ", "BLOCKED", "NON_DIRECTIONAL_NOT_ROUTABLE")]})
    assert out.loc["BZ", "horizon_bucket"] == "1_5d"
    assert out.loc["BZ", "horizon_action"] == "BLOCKED"
    assert out.loc["BZ", "contract_expiry_bucket"] == "blocked"
    assert out.loc["BZ", "horizon_block_reason"] == "NON_DIRECTIONAL_NOT_ROUTABLE"


def test_superbrain_stands_down_a_router_block_by_action():
    from scripts import avshunter_superbrain_layer as sb
    import inspect
    src = inspect.getsource(sb)
    assert '_horizon_bucket == "blocked" or _horizon_action == "BLOCKED"' in src


def test_eil_and_ede_honour_a_router_block_by_action():
    import execution_decision_engine as ede
    import execution_intelligence_runner as eil
    import inspect
    assert '_hb == "blocked" or _ha == "BLOCKED"' in inspect.getsource(ede)
    assert inspect.getsource(eil).count('_hb == "blocked" or _ha == "BLOCKED"') == 2


def test_the_trade_book_honours_a_router_block_by_action():
    import inspect
    import trade_book_builder as tbb
    assert '_hb == "blocked" or _ha == "BLOCKED"' in inspect.getsource(tbb)

"""EV v2 retirement completed (ACK 30 Sep "retire EV v2"; 3 Oct "go ahead with the EV v2 retirement").

CLAUDE.md rule 5 / spec §12: legacy EV v2 is not an expected value and may not be presented as, substituted for or
combined with Valuation's EV. The 30 Sep change only removed it from the Lab page; it still scored and gated.
EV v2 also invents its inputs (inventory A1/E2: +10%/-5% target/stop, $1.00 premium, data quality 100).
Business rules: rows that differ only in EV v2 score and gate identically; the plain ev / ev_final fields are
never overwritten with EV v2; EV v2 is recorded under its own ev2_* names (audit, legacy). The final decision
engine's EV ladder is already neutralised in production (fd_verdict WATCHLIST on every row).
"""
import inspect

import eod_candidate_engine as eod


def _row(**kw):
    base = {"ticker": "T", "options_score": 40, "composite": 60, "trigger_quality": "STRONG", "eil_v3_verdict": "EXECUTE"}
    base.update(kw)
    return base


def test_conviction_scores_ignore_ev2():
    for fn in (eod.structural_conviction_score, eod._structural_conviction_score_legacy):
        assert fn(_row(ev2_ev_structural=-0.2))[0] == fn(_row(ev2_ev_structural=0.3))[0]
    bd = eod.structural_conviction_score(_row(ev2_ev_structural=0.3))[1]
    assert "retired" in str(bd.get("structural_ev", "")).lower()


def test_superbrain_has_no_ev2_gate():
    import scripts.avshunter_superbrain_layer as sb
    src = inspect.getsource(sb.assemble_execution_plan)
    assert "GATE_NEGATIVE_EV" not in src
    assert "'ev_gate':              'RETIRED'" in inspect.getsource(sb)


def test_runner_never_presents_ev2_as_ev():
    import execution_intelligence_runner as r
    src = inspect.getsource(r)
    assert 'merged["ev"]       = round(_ev_val, 6)' not in src
    assert 'merged["ev_final"] = round(_ev_val, 6)' not in src


def test_trigger_layer_does_not_read_ev2_as_authoritative():
    import trigger_layer as tl
    only_ev2 = {"ev2_ev_conf_adj": 0.4, "fd_ev_used": 0.4, "eil_ev_net": 0.4, "ev_final": 0.4, "ev_conf_adj": 0.4}
    assert tl._compute_ev(only_ev2) == 0.0

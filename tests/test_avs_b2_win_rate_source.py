"""B2 (invented-values inventory, ACK 3 Oct 2026 "start the statistics labelling"): win rates say what they are.

Defect: when actuarial win rates were absent, SuperBrain copied Discovery's win_probability (40 + 0.25 x composite,
not a probability) into win_rate_5d/10d/20d, and every output labelled the source ACTUARIAL by default
(superbrain output, Lab book materializer, Lab server). Business rules:
- Unmeasured is NOT_ESTIMABLE: no composite-derived number is copied into actuarial win rates.
- The source label carries the match method: ACTUARIAL_EXACT / ACTUARIAL_RELAXED / ACTUARIAL_ANALOGUE when actuarial
  rates exist, else NOT_ESTIMABLE. Never a bare ACTUARIAL by default.
"""
import inspect

from domain.statistics_provenance import win_rate_source_label


def test_label_carries_the_match_method():
    assert win_rate_source_label({"win_rate_10d": 0.48, "layer2__state_match_method": "ANALOGUE"}) == "ACTUARIAL_ANALOGUE"
    assert win_rate_source_label({"win_rate_20d": 0.52, "actuarial_match_method": "EXACT"}) == "ACTUARIAL_EXACT"
    assert win_rate_source_label({"win_rate_20d": 0.52}) == "ACTUARIAL_METHOD_UNKNOWN"
    assert win_rate_source_label({"win_probability": 57.0}) == "NOT_ESTIMABLE"
    assert win_rate_source_label({"win_rate_10d": 0, "win_rate_20d": ""}) == "NOT_ESTIMABLE"


def test_superbrain_no_longer_bridges_and_labels_by_rule():
    import scripts.avshunter_superbrain_layer as sb
    assert "merged_row['win_rate_20d'] = _disc_win" not in inspect.getsource(sb._compute_unified_ev)
    src = inspect.getsource(sb.process_signal)
    assert "'win_rate_source':      _s(signal, 'win_rate_source') or 'ACTUARIAL'" not in src
    assert "win_rate_source_label(" in src


def test_lab_book_materializer_labels_by_rule():
    from contracts.lab_control import _recompute_governed_lab_fields
    row, prov = {"actuarial_match_method": "ANALOGUE", "actuarial_sample_size": 135617, "win_rate_10d": 0.48}, {}
    _recompute_governed_lab_fields(row, prov)
    assert row["win_rate_source"] == "ACTUARIAL_ANALOGUE"
    bare, prov2 = {}, {}
    _recompute_governed_lab_fields(bare, prov2)
    assert bare["win_rate_source"] == "NOT_ESTIMABLE"


def test_lab_server_default_uses_the_rule():
    from pathlib import Path
    src = Path(__file__).resolve().parents[1].joinpath("intelligence-lab", "intelligence_lab.py").read_text(encoding="utf-8")
    assert '"ACTUARIAL" if float(sig.get("ev2_p_win_blended",0) or 0) > 0 else "STRUCTURAL"' not in src
    assert "win_rate_source_label(" in src


def test_book_fields_are_recognised():
    """The Lab book carries win_prob_predicted with the actuarial sample and method (not the win_rate_* columns)."""
    book = {"win_prob_predicted": 0.4832, "actuarial_sample_size": 135617, "actuarial_match_method": "ANALOGUE"}
    assert win_rate_source_label(book) == "ACTUARIAL_ANALOGUE"
    assert win_rate_source_label({"win_prob_predicted": 0.55, "actuarial_sample_size": 0}) == "NOT_ESTIMABLE"

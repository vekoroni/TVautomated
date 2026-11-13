"""Minimal research runtime imports and pure helpers; no real data or workflows."""
from pathlib import Path
import importlib.util
import sys
import pytest

ROOT=Path(__file__).parents[1]
SCRIPTS=ROOT/'dropbox/macro/coaching/model/scripts'
sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('research_runtime_release',SCRIPTS/'score_decisions.py')
s=importlib.util.module_from_spec(spec);spec.loader.exec_module(s)

def test_runtime_imports_resolve_within_the_release_checkout():
    for module in (s,s.de,s.de.CD,s.BLH,s.BLH.lab_reader):
        assert Path(module.__file__).resolve().is_relative_to(ROOT.resolve())
    import backfill_report
    assert Path(backfill_report.__file__).resolve().is_relative_to(ROOT.resolve())

@pytest.mark.parametrize('bid,ask,oi,tier',[(1,1.05,100,'A'),(1,1.15,100,'B'),(1,1.3,100,'C'),(0,1,100,'C'),(1,1.05,10,'C'),(10,10.5,100,'A')])
def test_existing_liquidity_tiers_are_unchanged(bid,ask,oi,tier):
    assert s.BLH.liquidity_tier(bid,ask,oi)[0]==tier

def test_card_discovery_is_read_only_and_orders_by_saved_session(tmp_path):
    for name in ('BILI_deep_dive_2026-10-20.html','BILI_deep_dive_2026-10-14.html','~$BILI_deep_dive_2026-10-21.html'):
        (tmp_path/name).write_text('fixture')
    before=sorted(p.name for p in tmp_path.iterdir())
    cards=s.de.CD.find_cards(tmp_path)
    assert list(cards)==['BILI']
    assert [p.name for p in cards['BILI']]==['BILI_deep_dive_2026-10-14.html','BILI_deep_dive_2026-10-20.html']
    assert sorted(p.name for p in tmp_path.iterdir())==before
    assert not hasattr(s.de.CD,'ensure_decision_records')

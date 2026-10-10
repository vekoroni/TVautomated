"""P0-02 (Phase 1): one owner for compression facts.

Business rules (design §14, fact ownership register):
- The behavioural engine's compression.py is the single owner. Each timeframe reading publishes its compression
  state, episode boundaries, episode start, location and contracting side as flat fields, and Discovery's ticker
  row carries them as beh__{tf}_compression_* - the canonical compression columns.
- No new compression / NR / coil calculation may appear outside the owner. The two legacy producers that still
  feed the Discovery tier (avshunter_discovery_ULTIMATE.crabel_compression, precor _infer_crabel_compression /
  _sym_compressed) and the early-position ratio are frozen on an explicit list and retire with the tier (Phase 2).
"""
import ast
import copy
from pathlib import Path

import avshunter_discovery_ULTIMATE as disc
from domain.structure_behaviour.engine import analyse_timeframe
from domain.structure_behaviour.policy import load_policy
from test_p1_compression_episode import _bars

ROOT = Path(__file__).resolve().parents[1]
POLICY = copy.deepcopy(dict(load_policy()))
POLICY["timeframes"]["1d"]["min_bars"] = 20
FIELDS = ("Compression_State", "Compression_Box_High", "Compression_Box_Low", "Compression_Episode_Start",
          "Compression_Location", "Compression_Contracting_Side")
FROZEN_LEGACY = {("avshunter_discovery_ULTIMATE.py", "crabel_compression"),
                 ("wyckoff_crabel_precor_logic_v2.py", "_infer_crabel_compression"),
                 ("wyckoff_crabel_precor_logic_v2.py", "_sym_compressed"),
                 # trigger-layer T1 re-tests: retired in Phase 3 (trigger layer becomes an event detector)
                 ("trigger_layer.py", "_t1_vol_compression"),
                 ("trigger_layer.py", "_t1_realised_compression"),
                 ("domain/structure_behaviour/compression.py", "compression_context")}
DECISION_FILES = ["avshunter_discovery_ULTIMATE.py", "wyckoff_crabel_precor_logic_v2.py", "trigger_layer.py",
                  "eod_candidate_engine.py", "morning_gate.py", "contracts/lab_control.py",
                  "scripts/avshunter_options_intelligence.py", "swing_fusion.py", "execution_decision_engine.py"]


def test_reading_publishes_flat_compression_fields():
    r = analyse_timeframe("TEST", _bars(), "1d", POLICY)
    assert all(f in r for f in FIELDS)
    assert r["Compression_State"] == "CONTRACTING" and r["Compression_Episode_Start"] is not None


def test_discovery_row_carries_the_engines_compression_fields():
    reading = analyse_timeframe("TEST", _bars(), "1d", POLICY)
    beh = {"intraday_status": "", "candidates": [], "readings": {"1d": reading}, "handoff": {}}
    out = disc._beh001_summary_fields(beh)
    assert out["beh__1d_compression_state"] == "CONTRACTING"
    assert out["beh__1d_compression_box_high"] == reading["Compression_Box_High"]
    assert out["beh__1d_compression_episode_start"] == reading["Compression_Episode_Start"]


def test_no_new_compression_calculation_outside_the_owner():
    found = set()
    for rel in DECISION_FILES + ["domain/structure_behaviour/compression.py"]:
        p = ROOT / rel
        if not p.exists():
            continue
        for n in ast.walk(ast.parse(p.read_text(encoding="utf-8-sig", errors="ignore"))):
            if isinstance(n, ast.FunctionDef) and any(k in n.name.lower() for k in ("compress", "crabel", "nr7", "nr4")):
                if "bucket" in n.name.lower() or "fuse" in n.name.lower() or "score" in n.name.lower():
                    continue  # labelling / fusion of an existing value, not a compression calculation
                found.add((rel, n.name))
    assert found - FROZEN_LEGACY == set()

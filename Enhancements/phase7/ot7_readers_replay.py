"""Item 7 readers acceptance (run 20261008_220129): the SuperBrain runway vetoes (V2 at-wall / no-runway, V3 high-IV
runway) with the legacy raw-OI walls versus the governed walls (a level only when price confirmed it). Read-only."""
import collections
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from canonical_data.historical_prices import HistoricalPriceDatabase  # noqa: E402
from domain.option_walls import assess_option_walls, governed_walls  # noqa: E402
from scripts import avshunter_superbrain_layer as sb  # noqa: E402

RUN, SESSION, TRADE = "20261008_220129", "2026-10-08", date(2026, 10, 9)
opt = pd.read_csv(ROOT / "data/output/runs" / RUN / "options" / f"options_intelligence_{RUN}.csv", low_memory=False)
opt = opt.drop_duplicates("ticker").set_index("ticker")
con = sqlite3.connect(f"file:{(ROOT / 'data/canonical/control_plane.sqlite').as_posix()}?mode=ro", uri=True)
paths = dict(con.execute("SELECT instrument_id, storage_uri FROM dataset_registry WHERE dataset_type='OPTION_CHAIN' "
                         "AND session_date=? AND source_run_id=?", (SESSION, RUN)).fetchall())
db = HistoricalPriceDatabase(ROOT / "data/canonical/historical_prices.sqlite")
moves, n, confirmed = collections.Counter(), 0, collections.Counter()


def kinds(vetoes):
    return {v.split(":")[0] for v in vetoes if v.startswith(("V2_", "V3_"))}


for t, path in sorted(paths.items()):
    if t not in opt.index or not Path(path).is_file():
        continue
    r = {k: (None if (isinstance(v, float) and v != v) else v) for k, v in opt.loc[t].items()}
    r["direction"] = r.get("options_direction") or r.get("governed_direction")
    if str(r.get("direction") or "").upper() not in ("CALL", "PUT"):
        continue
    chain = pd.DataFrame(json.loads(Path(path).read_text(encoding="utf-8")))
    w = assess_option_walls(chain, ticker=t, spot=r.get("underlying_price"), trade_session=TRADE,
                            hold_sessions=r.get("evidence_runway_sessions"), bars=db.read(t, end_date=SESSION, bars=80),
                            chain_asof_utc=f"{SESSION}T20:00:00Z")
    legacy = {k: r.get(k) for k in ("call_wall", "put_wall", "call_wall_state", "put_wall_state", "max_pain")}
    new = {**{k: v for k, v in r.items() if k != "wall_method"}, **w, **governed_walls(w, legacy)}
    old_signal = {k: v for k, v in r.items() if k != "wall_method"}
    before, after = kinds(sb.apply_behavioural_vetoes(old_signal, {})[0]), kinds(sb.apply_behavioural_vetoes(new, {})[0])
    n += 1
    for k in before | after:
        moves[f"{k}: {'kept' if k in before and k in after else 'removed' if k in before else 'added'}"] += 1
    side = "call" if str(r.get("direction")).upper() == "CALL" else "put"
    confirmed[f"{side}_wall_level_confirmed={new[f'{side}_wall_level_confirmed']}"] += 1
out = {"run": RUN, "directed_rows": n, "veto_changes": dict(moves.most_common()), "trade_side_wall": dict(confirmed)}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2), encoding="utf-8")
print(json.dumps(out, indent=1))

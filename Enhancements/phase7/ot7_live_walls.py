"""Output-trust item 7 acceptance on run 20261008_220129: the legacy raw-OI walls against the gamma-weighted basket
walls for every ticker whose 8 Oct chain is stored. Read-only; JSON receipt beside."""
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
from domain.option_walls import assess_option_walls  # noqa: E402

RUN, SESSION, TRADE = "20261008_220129", "2026-10-08", date(2026, 10, 9)
opt = pd.read_csv(ROOT / "data/output/runs" / RUN / "options" / f"options_intelligence_{RUN}.csv", low_memory=False)
opt = opt.drop_duplicates("ticker").set_index("ticker")
con = sqlite3.connect(f"file:{(ROOT / 'data/canonical/control_plane.sqlite').as_posix()}?mode=ro", uri=True)
paths = dict(con.execute("SELECT instrument_id, storage_uri FROM dataset_registry WHERE dataset_type='OPTION_CHAIN' "
                         "AND session_date=? AND source_run_id=?", (SESSION, RUN)).fetchall())
db = HistoricalPriceDatabase(ROOT / "data/canonical/historical_prices.sqlite")
stats = collections.Counter()
status = collections.Counter()
old_far, examples = [], []
for t, path in sorted(paths.items()):
    if t not in opt.index or not Path(path).is_file():
        stats["no_options_row_or_file"] += 1
        continue
    r = opt.loc[t]
    spot = r.get("underlying_price")
    try:
        chain = pd.DataFrame(json.loads(Path(path).read_text(encoding="utf-8")))
        bars = db.read(t, end_date=SESSION, bars=80)
        hold = r.get("evidence_runway_sessions")
        w = assess_option_walls(chain, ticker=t, spot=spot, trade_session=TRADE,
                                hold_sessions=None if pd.isna(hold) else hold, bars=bars,
                                chain_asof_utc=f"{SESSION}T20:00:00Z")
    except Exception as exc:                                  # noqa: BLE001 - counted
        stats[f"error:{type(exc).__name__}"] += 1
        continue
    stats["assessed"] += 1
    for side in ("call", "put"):
        stats[f"hold_{side}:{w[f'wall_hold_{side}_state']}"] += 1
        if w[f"wall_hold_{side}_state"] == "QUALIFIED":
            status[w[f"wall_hold_{side}_price_status"]] += 1
        old = r.get(f"{side}_wall")
        if pd.notna(old) and spot and abs(float(old) / float(spot) - 1) > 0.30:
            old_far.append(t)
    if t in ("SMCI", "NVDA", "MSFT", "WYNN", "JBLU"):
        examples.append({"ticker": t, "spot": spot, "old_call": r.get("call_wall"), "old_put": r.get("put_wall"),
                         **{k: w[k] for k in ("wall_hold_call_peak", "wall_hold_call_share", "wall_hold_call_price_status",
                                              "wall_hold_put_peak", "wall_hold_put_share", "wall_hold_put_price_status",
                                              "wall_exit_date")}})
out = {"run": RUN, "chains": len(paths), "stats": dict(stats), "hold_wall_price_status": dict(status),
       "old_walls_more_than_30pct_from_spot": len(old_far), "examples": examples}
Path(__file__).with_suffix(".json").write_text(json.dumps(out, indent=2, default=str), encoding="utf-8")
print(json.dumps(out, indent=1, default=str))

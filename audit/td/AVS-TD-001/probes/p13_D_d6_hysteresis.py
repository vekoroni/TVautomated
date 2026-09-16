"""D6 — preferred/selected contract flips 10 Sep -> 11 Sep: options CSV recommended_contract by ticker (CALL/PUT/OTHER),
control_plane option_contract_selection_events reasons, margin fields, doi_preferred_contract_decisions."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d6_hysteresis.json"


def book(run):
    p = art(run, "options/options_intelligence_<run>.csv")
    df = read_csv(p, usecols=["ticker", "governed_direction", "recommended_contract", "thesis_id"]).drop_duplicates("ticker", keep="first")
    df["ticker"] = df["ticker"].astype(str).str.upper()
    return df.set_index("ticker")


if __name__ == "__main__":
    res = {}
    a, b = book(COMPARISON), book(PRIMARY)
    j = a.join(b, lsuffix="_10", rsuffix="_11", how="inner")
    both = j["recommended_contract_10"].notna() & j["recommended_contract_11"].notna()
    same_dir = j["governed_direction_10"].astype(str) == j["governed_direction_11"].astype(str)
    flip = both & same_dir & (j["recommended_contract_10"].astype(str) != j["recommended_contract_11"].astype(str))
    d = direction_bucket(j["governed_direction_11"])
    res["options_csv_flip"] = {k: {"common_tickers": int(((d == k) if k != "ALL" else pd.Series(True, index=j.index)).sum()),
                                   "both_have_contract_same_direction": int((both & same_dir & ((d == k) if k != "ALL" else True)).sum()),
                                   "flipped": int((flip & ((d == k) if k != "ALL" else True)).sum())} for k in ("ALL", "CALL", "PUT", "OTHER")}
    for k, v in res["options_csv_flip"].items():
        v["flip_rate"] = round(v["flipped"] / v["both_have_contract_same_direction"], 4) if v["both_have_contract_same_direction"] else None
    res["flip_examples"] = j.loc[flip, ["recommended_contract_10", "recommended_contract_11"]].head(8).reset_index().to_dict("records")
    # flips that are only an expiry roll vs strike change
    def parse(s):
        m = re.match(r"^([A-Z.]+)(\d{6})([CP])(\d{8})$", str(s))
        return (m.group(2), m.group(4)) if m else (None, None)
    e10 = j.loc[flip, "recommended_contract_10"].map(parse); e11 = j.loc[flip, "recommended_contract_11"].map(parse)
    res["flip_kind"] = {"expiry_changed_only": int(sum((x[0] != y[0]) and (x[1] == y[1]) for x, y in zip(e10, e11))),
                        "strike_changed_only": int(sum((x[0] == y[0]) and (x[1] != y[1]) for x, y in zip(e10, e11))),
                        "both_changed": int(sum((x[0] != y[0]) and (x[1] != y[1]) for x, y in zip(e10, e11)))}
    with ro_conn("control_plane.sqlite") as c:
        res["selection_events_by_run"] = c.execute("""SELECT run_id, COUNT(*), SUM(previous_contract_symbol IS NOT NULL AND previous_contract_symbol<>''),
            SUM(previous_contract_symbol IS NOT NULL AND previous_contract_symbol<>'' AND previous_contract_symbol<>selected_contract_symbol), SUM(supersedes_event_id IS NOT NULL)
            FROM option_contract_selection_events GROUP BY 1 ORDER BY 1""").fetchall()
        res["selection_reason_two_runs"] = c.execute("""SELECT run_id, selection_reason, COUNT(*), SUM(previous_contract_symbol<>selected_contract_symbol)
            FROM option_contract_selection_events WHERE run_id IN (?,?) GROUP BY 1,2 ORDER BY 1,3 DESC""", (PRIMARY, COMPARISON)).fetchall()
        res["selection_versions"] = c.execute("SELECT selection_version, calculation_version, COUNT(*) FROM option_contract_selection_events GROUP BY 1,2").fetchall()
        rows = c.execute("SELECT metadata_json FROM option_contract_selection_events WHERE run_id=? AND previous_contract_symbol<>selected_contract_symbol LIMIT 200", (PRIMARY,)).fetchall()
        keys = {}
        for (m,) in rows:
            try:
                for k in json.loads(m or "{}").keys():
                    keys[k] = keys.get(k, 0) + 1
            except Exception:
                pass
        res["switch_metadata_keys"] = keys
        res["switch_metadata_margin_like_keys"] = [k for k in keys if re.search(r"margin|utility|hysteresis|U_i|U_c|score", k, re.I)]
        res["switch_sample"] = c.execute("SELECT thesis_id, previous_contract_symbol, selected_contract_symbol, selection_reason, substr(metadata_json,1,400) FROM option_contract_selection_events WHERE run_id=? AND previous_contract_symbol<>selected_contract_symbol LIMIT 3", (PRIMARY,)).fetchall()
        res["switch_by_direction_primary"] = c.execute("""SELECT CASE WHEN thesis_id LIKE '%:CALL:%' THEN 'CALL' WHEN thesis_id LIKE '%:PUT:%' THEN 'PUT' ELSE 'OTHER' END d,
            COUNT(*), SUM(previous_contract_symbol IS NOT NULL AND previous_contract_symbol<>''), SUM(previous_contract_symbol<>selected_contract_symbol)
            FROM option_contract_selection_events WHERE run_id=? GROUP BY 1""", (PRIMARY,)).fetchall()
        res["doi_preferred_contract_decisions"] = c.execute("SELECT COUNT(*) FROM doi_preferred_contract_decisions").fetchone()[0]
    dump(res, OUT)
    print(json.dumps(res, indent=1, default=str)[:7000])

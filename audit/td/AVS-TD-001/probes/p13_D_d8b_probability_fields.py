"""D8b — fixed rerun of p13_D_d8 (ev3_shadow CSVs have no ticker column): probability-like columns, non-null counts, range,
CALL/PUT/OTHER, presence of calibration_state / ranking_score_kind columns."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d8b_probability_fields.json"
PAT = re.compile(r"(^|_)p_|probability|prob_|win_rate|hit_rate|calibrat|ranking_score", re.I)
FILES = {"final_opportunity_book": "intelligence_lab/final_opportunity_book_<run>.csv", "lab_signal_book_v3": "intelligence_lab/lab_signal_book_v3.csv",
         "lab_triage_view": "intelligence_lab/lab_triage_view_<run>.csv", "morning_validated_trades": "morning_validation/morning_validated_trades_<run>.csv"}


def scan(run, rel):
    p = art(run, rel)
    if not p.exists():
        return {"missing": rel}
    hdr = header(p)
    cols = [c for c in hdr if PAT.search(c)]
    dcol = next((c for c in ("governed_direction", "final_direction", "direction", "option_side") if c in hdr), None)
    df = read_csv(p, usecols=list(dict.fromkeys(cols + ([dcol] if dcol else []))))
    b = direction_bucket(df[dcol]) if dcol else pd.Series("OTHER", index=df.index)
    out = {"rows": len(df), "direction_col": dcol, "calibration_cols": [c for c in hdr if "calibrat" in c.lower()],
           "ranking_score_kind_cols": [c for c in hdr if "score_kind" in c.lower()], "columns": {}}
    for c in cols:
        s = df[c]; nn = s.notna() & s.astype(str).str.strip().ne("")
        num = pd.to_numeric(s, errors="coerce")
        rec = {"nonnull": int(nn.sum()), **{k: int((nn & (b == k)).sum()) for k in ("CALL", "PUT", "OTHER")}}
        if num.notna().any():
            rec.update(min=float(num.min()), median=float(num.median()), max=float(num.max()), unit_interval=bool(num.dropna().between(0, 1).all()))
        elif nn.any():
            rec["values"] = dict(list(vc(s[nn].astype(str)).items())[:6])
        out["columns"][c] = rec
    return out


if __name__ == "__main__":
    res = {}
    for run in (PRIMARY, COMPARISON):
        res[run] = {k: scan(run, v) for k, v in FILES.items()}
        ev = run_dir(run) / "ev3_shadow"
        res[run]["ev3_shadow"] = {f.name: scan(run, f"ev3_shadow/{f.name}") for f in sorted(ev.glob("*.csv"))} if ev.exists() else "absent"
    dump(res, OUT)
    for run, d in res.items():
        for k, v in d.items():
            if isinstance(v, dict) and "columns" in v:
                nz = {c: (r["nonnull"], r.get("CALL"), r.get("PUT"), r.get("OTHER"), r.get("min"), r.get("max")) for c, r in v["columns"].items() if r["nonnull"]}
                print(run, k, v["rows"], "calib cols:", v["calibration_cols"], "kind cols:", v["ranking_score_kind_cols"], "nonnull prob cols:", nz)
            elif isinstance(v, dict):
                for f, w in v.items():
                    if isinstance(w, dict) and "columns" in w:
                        nz = {c: (r["nonnull"], r.get("min"), r.get("max")) for c, r in w["columns"].items() if r["nonnull"]}
                        print(run, "ev3_shadow", f, w["rows"], "calib:", w["calibration_cols"], nz)

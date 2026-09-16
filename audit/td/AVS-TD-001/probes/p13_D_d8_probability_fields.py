"""D8 — probability-like columns across the primary run's books: non-null count, range, CALL/PUT/OTHER; calibration_state presence."""
from __future__ import annotations
import json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))
from p13_D_common import *  # noqa

OUT = AUD / "probes" / "p13_D_d8_probability_fields.json"
PAT = re.compile(r"^p_|_probability|prob_|p_target|p_positive|p_liquidity|win_rate|hit_rate|calibrat", re.I)
FILES = {
    "final_opportunity_book": "intelligence_lab/final_opportunity_book_<run>.csv",
    "lab_signal_book_v3": "intelligence_lab/lab_signal_book_v3.csv",
    "lab_triage_view": "intelligence_lab/lab_triage_view_<run>.csv",
    "morning_validated_trades": "morning_validation/morning_validated_trades_<run>.csv",
    "execution_gated": "trades/execution_gated_<run>.csv",
}


def scan(run: str, label: str, rel: str) -> dict:
    p = art(run, rel)
    if not p.exists():
        return {"missing": str(p)}
    hdr = header(p)
    cols = [c for c in hdr if PAT.search(c)]
    dcol = next((c for c in ("governed_direction", "final_direction", "direction") if c in hdr), None)
    df = read_csv(p, usecols=["ticker"] + cols + ([dcol] if dcol else []))
    b = direction_bucket(df[dcol]) if dcol else pd.Series("OTHER", index=df.index)
    out = {"file": rel, "rows": len(df), "n_matching_cols": len(cols), "columns": {}}
    for c in cols:
        s = df[c]
        num = pd.to_numeric(s, errors="coerce")
        nn = s.notna() & s.astype(str).str.strip().ne("")
        rec = {"nonnull": int(nn.sum()), "numeric_nonnull": int(num.notna().sum()),
               "by_dir_nonnull": {k: int((nn & (b == k)).sum()) for k in ("CALL", "PUT", "OTHER")}}
        if num.notna().any():
            rec.update({"min": float(num.min()), "median": float(num.median()), "max": float(num.max()), "in_unit_interval": bool(((num.dropna() >= 0) & (num.dropna() <= 1)).all())})
        else:
            rec["values"] = vc(s.dropna().astype(str).head(2000))
            rec["values"] = dict(list(rec["values"].items())[:8])
        out["columns"][c] = rec
    out["calibration_state_cols"] = [c for c in hdr if "calibration" in c.lower()]
    return out


if __name__ == "__main__":
    res = {}
    for label, rel in FILES.items():
        res[label] = scan(PRIMARY, label, rel)
    # ev3_shadow directory
    ev = run_dir(PRIMARY) / "ev3_shadow"
    res["ev3_shadow"] = {}
    for f in sorted(ev.glob("*")):
        if f.suffix == ".csv":
            res["ev3_shadow"][f.name] = scan(PRIMARY, f.name, f"ev3_shadow/{f.name}")
        elif f.suffix == ".json":
            try:
                j = json.load(open(f, encoding="utf-8"))
                keys = []
                def walk(o, pth=""):
                    if isinstance(o, dict):
                        for k, v in o.items():
                            if PAT.search(str(k)): keys.append((pth + "/" + k, v if not isinstance(v, (dict, list)) else type(v).__name__))
                            walk(v, pth + "/" + k)
                    elif isinstance(o, list) and o and isinstance(o[0], dict):
                        walk(o[0], pth + "[0]")
                walk(j)
                res["ev3_shadow"][f.name] = {"json_keys_matching": keys[:40]}
            except Exception as e:
                res["ev3_shadow"][f.name] = {"error": str(e)}
    # run-level calibration_state
    hits = {}
    for f in ("run_meta.json", "final_run_manifest.json", f"options/dynamic_options_intelligence_{PRIMARY}.json", f"options/options_intelligence_summary_{PRIMARY}.json", f"morning_validation/morning_gate_summary_{PRIMARY}.json"):
        p = run_dir(PRIMARY) / f
        if p.exists():
            txt = p.read_text(encoding="utf-8", errors="replace")
            hits[f] = {"calibration_state": "calibration_state" in txt, "calibrat_any": len(re.findall("calibrat", txt, re.I)), "ranking_score_kind": "ranking_score_kind" in txt}
    res["run_level_calibration_mentions"] = hits
    dump(res, OUT)
    for label, v in res.items():
        if isinstance(v, dict) and "columns" in v:
            print(label, v["rows"], {c: (r["nonnull"], r.get("min"), r.get("max")) for c, r in v["columns"].items()})
    print("ev3_shadow", {k: (v.get("rows"), list(v.get("columns", {}).keys())[:12]) if "columns" in v else v for k, v in res["ev3_shadow"].items()})
    print("calibration mentions", hits)

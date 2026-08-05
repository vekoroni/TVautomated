
import pandas as pd
from pathlib import Path

RUN_PATH = Path("data/output/runs").resolve()

def load_latest_run():
    runs = sorted(RUN_PATH.glob("*"), key=lambda x: x.stat().st_mtime, reverse=True)
    return runs[0]

def safe_load(path):
    try:
        return pd.read_csv(path)
    except:
        return pd.DataFrame()

def build_trace(run_dir):
    files = {
        "superbrain": safe_load(run_dir / f"superbrain_enriched_{run_dir.name}.csv"),
        "wbs": safe_load(run_dir / f"wall_break_scores_{run_dir.name}.csv"),
        "execution": safe_load(run_dir / f"execution_v3_5_{run_dir.name}.csv"),
        "options": safe_load(run_dir / f"options_intelligence_{run_dir.name}.csv"),
        "ede": safe_load(run_dir / f"ede_decisions_{run_dir.name}.csv"),
    }

    tickers = set()
    for df in files.values():
        if not df.empty and "ticker" in df.columns:
            tickers.update(df["ticker"].unique())

    traces = []

    for t in tickers:
        trace = {"ticker": t, "flags": []}

        # --- DISCOVERY (SUPERBRAIN)
        sb = files["superbrain"]
        if not sb.empty:
            row = sb[sb["ticker"] == t]
            if not row.empty:
                trace["discovery_score"] = float(row.iloc[0].get("composite_score", 0))
                trace["bmps"] = float(row.iloc[0].get("bmps", 0))
                trace["predictability"] = float(row.iloc[0].get("predictability", 0))

        # --- STRUCTURE (WBS)
        wbs = files["wbs"]
        if not wbs.empty:
            row = wbs[wbs["ticker"] == t]
            if not row.empty:
                trace["wbs_score"] = float(row.iloc[0].get("wbs_score", 0))
                trace["runway"] = float(row.iloc[0].get("runway_to_wall_pct", 0))

        # --- EXECUTION (EIL)
        exe = files["execution"]
        if not exe.empty:
            row = exe[exe["ticker"] == t]
            if not row.empty:
                trace["eil_score"] = float(row.iloc[0].get("eil_score", 0))
                trace["eil_verdict"] = row.iloc[0].get("eil_v3_verdict", "UNKNOWN")

        # --- OPTIONS
        opt = files["options"]
        if not opt.empty:
            row = opt[opt["ticker"] == t]
            if not row.empty:
                trace["ev"] = float(row.iloc[0].get("ev_10d", 0))
                trace["spread"] = float(row.iloc[0].get("spread_pct", 0))
                trace["delta"] = float(row.iloc[0].get("delta", 0))

        # --- FINAL DECISION (EDE)
        ede = files["ede"]
        if not ede.empty:
            row = ede[ede["ticker"] == t]
            if not row.empty:
                trace["final_score"] = float(row.iloc[0].get("final_score", 0))
                trace["final_verdict"] = row.iloc[0].get("final_verdict", "UNKNOWN")
                trace["execution_mode"] = row.iloc[0].get("execution_mode", "UNKNOWN")

        # --- AUDIT RULES

        # CRITICAL: EIL BLOCKED but final GO
        if trace.get("eil_verdict") == "BLOCKED" and trace.get("final_verdict") == "GO":
            trace["flags"].append("CRITICAL_CONTRADICTION")

        # LOW EV but GO
        if trace.get("ev", 0) < 0 and trace.get("final_verdict") == "GO":
            trace["flags"].append("NEGATIVE_EV_EXECUTED")

        # HIGH DISCOVERY but BLOCKED
        if trace.get("discovery_score", 0) > 70 and trace.get("final_verdict") in ["BLOCKED", "WAIT"]:
            trace["flags"].append("MISSED_HIGH_QUALITY")

        # SPREAD TOO HIGH
        if trace.get("spread", 0) > 8:
            trace["flags"].append("SPREAD_VIOLATION")

        # DELTA OUTSIDE RANGE
        if not (0.25 <= trace.get("delta", 0) <= 0.60):
            trace["flags"].append("DELTA_OUT_OF_RANGE")

        traces.append(trace)

    return pd.DataFrame(traces)

def run_audit():
    run_dir = load_latest_run()
    print(f"\n🔍 Auditing run: {run_dir.name}")

    df = build_trace(run_dir)

    out_path = run_dir / "audit_report.csv"
    df.to_csv(out_path, index=False)

    print(f"✅ Audit complete: {out_path}")
    print("\nTop Issues:")
    print(df["flags"].explode().value_counts().head(10))

if __name__ == "__main__":
    run_audit()
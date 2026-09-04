"""AVS-RCA-002 - environment manifest with artefact hashes. READ ONLY."""
import hashlib, json, os, pathlib, platform, sys, datetime
ROOT=pathlib.Path(".").resolve()
def h(p):
    try:
        d=hashlib.sha256()
        with open(p,"rb") as f:
            for b in iter(lambda: f.read(1<<20), b""): d.update(b)
        return d.hexdigest()
    except OSError as e: return f"ERR:{e}"
ART=[
 r"data\output\runs\20260904_004338\run_meta.json",
 r"data\output\runs\20260904_004338\final_run_manifest.json",
 r"data\output\runs\20260904_004338\pipeline_integrity_20260904_004338.json",
 r"data\output\runs\20260904_004338\truth_packet_run.json",
 r"data\output\runs\20260904_004338\options\vanguard_signals_enriched_20260904_004338.csv",
 r"data\output\runs\20260904_004338\vanguard\vanguard_signals.csv",
 r"data\output\runs\20260904_004338\options\options_intelligence_20260904_004338.csv",
 r"data\output\runs\20260904_004338\options\governed_direction_records_20260904_004338.jsonl",
 r"data\output\runs\20260904_004338\morning_validation\morning_candidates_20260904_004338.csv",
 r"data\output\runs\20260904_004338\morning_validation\missed_opportunity_shadow_book_20260904_004338.csv",
 r"data\output\runs\20260904_004338\morning_validation\eod_dropoff_audit_20260904_004338.csv",
 r"data\output\runs\20260904_004338\morning_validation\regime_watch_20260904_004338.csv",
 r"data\output\runs\20260904_004338\intelligence_lab\final_opportunity_book_20260904_004338.csv",
 r"data\output\runs\20260904_004338\diagnostics\handoff_contract_audit_20260904_004338.json",
 r"data\output\runs\20260904_004338\diagnostics\uat_audit_report_20260904_004338.json",
 r"data\output\runs\20260904_004338\diagnostics\dropoff_audit_20260904_004338.json",
 r"data\output\runs\20260902_232526\options\vanguard_signals_enriched_20260902_232526.csv",
 r"data\canonical\control_plane.sqlite",
]
SRC=["intelligent_orchestrator.py","contracts/dynamic_session_contract.py",
     "contracts/dynamic_session_authority_v1.json","vanguard/layer1_auction/auction_synthesizer.py",
     "vanguard/integration/orchestrator_adapter.py","vanguard/schemas/input_schema.py",
     "vanguard/layer2_statistical/edge_detector.py","scripts/run_vanguard_from_packages.py",
     "scripts/build_completed_market_profiles.py","scripts/avshunter_options_intelligence.py",
     "eod_candidate_engine.py","handoff_contract_audit.py","uat_audit_report.py",
     "contracts/lab_control.py","contracts/lab_evidence_overlay.py",
     "contracts/interpreter_handoff_materializer.py","contracts/selected_contract_economics.py",
     "morning_handoff_finalizer.py","orchestrator/dynamic_release.py"]
out={
 "report":"AVS-RCA-002",
 "generated_utc":datetime.datetime.now(datetime.timezone.utc).isoformat(),
 "repository":str(ROOT),
 "run_under_review":"20260904_004338",
 "baseline_run":"20260902_232526",
 "interpreter":{"executable":sys.executable,"version":sys.version,"platform":platform.platform()},
 "discipline":"read-only; no pipeline execution; no feature flag set; writes confined to audit/pipeline_map/AVS-RCA-002/ and AVS-SD-003",
 "scripts_run":sorted(p.name for p in pathlib.Path("audit/pipeline_map/AVS-RCA-002/A_scripts").glob("*.py")),
 "artefact_sha256":{a:h(a) for a in ART if os.path.exists(a)},
 "artefact_missing":[a for a in ART if not os.path.exists(a)],
 "source_sha256":{s:h(s) for s in SRC if os.path.exists(s)},
 "source_missing":[s for s in SRC if not os.path.exists(s)],
 "log_slice":{"source":"logs/orchestrator.log","run_window_utc_local":"2026-09-04 00:16:45 -> 04:47:22"},
}
p=pathlib.Path("audit/pipeline_map/AVS-RCA-002/environment.json")
p.write_text(json.dumps(out, indent=2), encoding="utf-8")
print("wrote", p, len(out["artefact_sha256"]), "artefacts,", len(out["source_sha256"]), "sources")
print("missing artefacts:", out["artefact_missing"]); print("missing sources:", out["source_missing"])

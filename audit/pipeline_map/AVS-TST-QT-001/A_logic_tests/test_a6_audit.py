"""Track A6 - replay the corrected semantic audit read-only against the
unremediated run 20260904_004338, and against a minimal healthy fixture."""
import sys, pathlib, json, tempfile, shutil
ROOT = pathlib.Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))
import pandas as pd
import handoff_contract_audit as HCA

OUT = ROOT / "audit/pipeline_map/AVS-TST-QT-001"

def replay(run_id):
    """Run the audit into a temp dir so no run artefact is written."""
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="qt001_audit_"))
    try:
        res = HCA.audit_run(run_id, runs_dir=ROOT / "data/output/runs", output_dir=tmp)
        return res
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

print("=" * 70)
print("A6 / AG-16 : corrected audit replayed on the UNREMEDIATED run 20260904_004338")
print("=" * 70)
r = replay("20260904_004338")
print("overall_status :", r.get("overall_status"))
print("fail_count     :", r.get("fail_count"))
print("warn_count     :", r.get("warn_count"))
print("status_counts  :", json.dumps(r.get("status_counts"), indent=1))
fails = [x for x in r.get("outstanding_fixes", []) if x.get("severity") == "FAIL"]
print(f"\nFAIL rows: {len(fails)}")
shadow = 0
for i, f in enumerate(fails, 1):
    st = f.get("stage"); fc = f.get("field_contract"); stt = f.get("status")
    if st == "shadow_book": shadow += 1
    print(f"  {i:2d}. stage={st:22s} field={str(fc)[:38]:38s} status={stt}")
print(f"\nshadow-book contribution to fail_count: {shadow}")
print(f"AG-16 (fail_count >= 6 AND zero shadow contribution): "
      f"{'PASS' if r.get('fail_count',0) >= 6 and shadow == 0 else 'FAIL'}")

print()
print("=" * 70)
print("A6 / AUD-02 : the same audit on the DDD run 20260905_151448")
print("=" * 70)
r2 = replay("20260905_151448")
print("overall_status :", r2.get("overall_status"))
print("fail_count     :", r2.get("fail_count"), " warn:", r2.get("warn_count"))
print("status_counts  :", json.dumps(r2.get("status_counts"), indent=1))
f2 = [x for x in r2.get("outstanding_fixes", []) if x.get("severity") == "FAIL"]
print(f"FAIL rows: {len(f2)}")
for i, f in enumerate(f2, 1):
    print(f"  {i:2d}. stage={f.get('stage'):22s} field={str(f.get('field_contract'))[:38]:38s} "
          f"status={f.get('status')}")
json.dump({"run_20260904_004338": r, "run_20260905_151448": r2},
          (OUT / "_a6_audit_replay.json").open("w", encoding="utf-8"), indent=1, default=str)

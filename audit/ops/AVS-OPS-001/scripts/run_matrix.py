"""AVS-OPS-001 verification matrix. Runs items 1-5 of section 6.
Never runs the pipeline: the only orchestrator call is --cds-startup-self-test.
Usage: run_matrix.py <outdir>
"""
import json, os, pathlib, subprocess, sys, time, glob, xml.etree.ElementTree as ET

ROOT = pathlib.Path(".").resolve()
OUT = pathlib.Path(sys.argv[1]); OUT.mkdir(parents=True, exist_ok=True)
VENV = str(ROOT / "venv" / "Scripts" / "python.exe")
PY314 = r"C:\Python314\python.exe"

ENV = {k: v for k, v in os.environ.items() if not k.startswith("AVSHUNTER_")}
ENV["PYTHONIOENCODING"] = "utf-8"
ENV["PYTHONDONTWRITEBYTECODE"] = "1"

def run(cmd, timeout=900, cwd=None):
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, errors="replace",
                           timeout=timeout, env=ENV, cwd=cwd or str(ROOT))
        return p.returncode, p.stdout, p.stderr, time.time() - t0
    except subprocess.TimeoutExpired:
        return -9, "", f"TIMEOUT after {timeout}s", time.time() - t0

results = {}

# ---- Item 1: compile check -------------------------------------------------
print("[1] compileall", flush=True)
rc, so, se, dt = run([VENV, "-m", "compileall", "-q", ".",
                      "-x", r"(_attic|backups|venv|\.codex_|\.git|node_modules|__pycache__|_cleanup_holding|Archive)"],
                     timeout=1800)
(OUT / "item1_compileall.txt").write_text(f"rc={rc}\n--stdout--\n{so}\n--stderr--\n{se}", encoding="utf-8")
err_lines = [l for l in (so + se).splitlines() if "Error" in l or "SyntaxError" in l]
results["item1_compileall"] = {"rc": rc, "error_lines": len(err_lines),
                               "errors": err_lines[:40], "seconds": round(dt, 1)}
print(f"    rc={rc} error_lines={len(err_lines)} ({dt:.0f}s)", flush=True)

# ---- Item 2: entry-point import smoke -------------------------------------
print("[2] entry-point import smoke", flush=True)
ENTRIES = {
    "intelligent_orchestrator": ("module", "intelligent_orchestrator"),
    "morning_gate": ("module", "morning_gate"),
    "intelligence_lab": ("path", "intelligence-lab/intelligence_lab.py"),
    "pipeline_interpreter": ("module", "pipeline_interpreter"),
}
item2 = {}
for name, (kind, target) in ENTRIES.items():
    if kind == "module":
        code = ("import importlib,sys;"
                f"m=importlib.import_module({target!r});"
                "print('IMPORT_OK', m.__name__)")
    else:
        code = ("import importlib.util as u,sys;"
                f"s=u.spec_from_file_location('el_probe', {target!r});"
                "m=u.module_from_spec(s);s.loader.exec_module(m);print('IMPORT_OK el_probe')")
    rc, so, se, dt = run([VENV, "-c", code], timeout=300)
    ok = "IMPORT_OK" in so
    tail = (se.strip().splitlines() or [""])[-1][:200]
    item2[name] = {"rc": rc, "import_ok": ok, "seconds": round(dt, 1), "last_stderr": tail}
    (OUT / f"item2_{name}.txt").write_text(f"rc={rc}\n--stdout--\n{so}\n--stderr--\n{se}", encoding="utf-8")
    print(f"    {name}: ok={ok} rc={rc} ({dt:.0f}s) {tail[:90]}", flush=True)
results["item2_entrypoint_imports"] = item2

# ---- Item 3: CDS startup self-test ----------------------------------------
print("[3] CDS startup self-test", flush=True)
rc, so, se, dt = run([VENV, "intelligent_orchestrator.py", "--evening",
                      "--cds-startup-self-test"], timeout=600)
(OUT / "item3_cds_selftest.txt").write_text(f"rc={rc}\n--stdout--\n{so}\n--stderr--\n{se}", encoding="utf-8")
passed = ("PASS" in so or "PASS" in se)
results["item3_cds_selftest"] = {"rc": rc, "reports_pass": passed, "seconds": round(dt, 1),
                                 "tail": (so + se).strip().splitlines()[-6:]}
print(f"    rc={rc} reports_pass={passed} ({dt:.0f}s)", flush=True)

# ---- Items 4/5: pytest, one file per process ------------------------------
files = sorted(glob.glob("tests/test_*.py")) + sorted(glob.glob("tests/qa/test_*.py")) \
        + sorted(glob.glob("tests/rca/test_*.py"))
print(f"[4/5] pytest: {len(files)} files, one process each", flush=True)
xmldir = OUT / "pytest_xml"; xmldir.mkdir(exist_ok=True)
per_file, tot = {}, {"tests": 0, "failures": 0, "errors": 0, "skipped": 0, "passed": 0}
for i, f in enumerate(files, 1):
    stem = pathlib.Path(f).stem
    sub = pathlib.Path(f).parent.name
    tag = f"{sub}__{stem}" if sub != "tests" else stem
    xml = xmldir / f"{tag}.xml"
    rc, so, se, dt = run([VENV, "-m", "pytest", f, "-q", "-p", "no:cacheprovider",
                          "--junitxml", str(xml), "-o", "addopts="], timeout=900)
    rec = {"rc": rc, "seconds": round(dt, 1), "tests": 0, "failures": 0,
           "errors": 0, "skipped": 0, "passed": 0}
    if xml.exists():
        try:
            r = ET.parse(xml).getroot()
            ts = r if r.tag == "testsuite" else (r.find("testsuite") if r.find("testsuite") is not None else r)
            rec["tests"] = int(ts.get("tests", 0)); rec["failures"] = int(ts.get("failures", 0))
            rec["errors"] = int(ts.get("errors", 0)); rec["skipped"] = int(ts.get("skipped", 0))
            rec["passed"] = rec["tests"] - rec["failures"] - rec["errors"] - rec["skipped"]
        except ET.ParseError as e:
            rec["xml_parse_error"] = str(e)
    else:
        rec["no_xml"] = True
        rec["tail"] = (so + se).strip().splitlines()[-3:]
    for k in tot:
        tot[k] += rec.get(k, 0)
    per_file[tag] = rec
    flag = "" if rec["failures"] == 0 and rec["errors"] == 0 else "  <== FAIL/ERR"
    print(f"    [{i:3d}/{len(files)}] {tag:58s} t={rec['tests']:3d} p={rec['passed']:3d} "
          f"f={rec['failures']} e={rec['errors']} s={rec['skipped']} ({dt:.0f}s){flag}", flush=True)
results["items45_pytest"] = {"file_count": len(files), "totals": tot, "per_file": per_file}

(OUT / "matrix_summary.json").write_text(json.dumps(results, indent=1), encoding="utf-8")
print("\n==== TOTALS ====")
print(json.dumps(tot, indent=1))
print("compileall error_lines:", results["item1_compileall"]["error_lines"])
print("entry imports ok:", {k: v["import_ok"] for k, v in item2.items()})
print("cds selftest pass:", results["item3_cds_selftest"]["reports_pass"])

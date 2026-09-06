# audit/ops/verify_anthropic_key.py  — reports facts about the credential, never the credential
#
# AVS-FIX-001 Part A (W4.1 closure evidence).
#
# Binding rule 2 of AVS-IMP-FIX-001: this script must never print, log or write
# the credential.  Every value it emits is a boolean, a length, an HTTP status
# or a model id.  The key itself is read into a local and used only as a header
# value for a single request; it is never placed in `report`.
#
# Exactly ONE network call is made: GET https://api.anthropic.com/v1/models.
#
# Run from a FRESH shell — the process scope must have been re-inherited from
# the User scope after the 6 Sep `setx` rotation for `process_equals_user` to
# mean anything.
import os, re, json, sys, subprocess, urllib.request, urllib.error
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
report = {}


def facts(value):
    if value is None:
        return {"present": False}
    return {"present": True, "length": len(value),
            "prefix_ok": value.startswith("sk-ant-api03-"),
            "has_ws": value != value.strip(),
            "has_crlf": ("\r" in value) or ("\n" in value),
            "has_quotes": value[:1] in "\"'" or value[-1:] in "\"'"}


# 1. scopes (Windows): read via PowerShell so we see User/Machine, not just Process
def scope(name):
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          f"[Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY','{name}')"],
                         capture_output=True, text=True).stdout.rstrip("\r\n")
    return out if out else None


report["user_scope"] = facts(scope("User"))
report["machine_scope"] = facts(scope("Machine"))
report["process_scope"] = facts(os.environ.get("ANTHROPIC_API_KEY"))

# 2. .env must not carry the key (single source rule)
env = REPO / ".env"
report["dotenv_has_line"] = env.exists() and any(
    l.strip().startswith("ANTHROPIC_API_KEY")
    for l in env.read_text(encoding="utf-8", errors="ignore").splitlines())
report["dotenv_txt_exists"] = (REPO / ".env.txt").exists()   # must be False (AVS-OPS-001)

# 3. process value must equal user value (fresh shell check)
report["process_equals_user"] = (os.environ.get("ANTHROPIC_API_KEY") == scope("User"))

# 4. one authenticated, token-free request
#
# AVS-IMP-FIX-001 binding rule 1 permits EXACTLY ONE such request in Part A.
# The probe is therefore counted in a ledger next to the result file, and a
# second attempt refuses unless --authorised-reprobe is passed (ACK's explicit
# lift of the cap).  `--offline` skips the request entirely and re-reports the
# local facts only.
LEDGER = REPO / "audit" / "ops" / "verify_anthropic_key_probe_ledger.json"
OFFLINE = "--offline" in sys.argv
AUTHORISED = "--authorised-reprobe" in sys.argv


def _probe_count():
    if not LEDGER.exists():
        return 0
    try:
        return int(json.loads(LEDGER.read_text()).get("models_probe_count", 0))
    except Exception:
        return 0


def _record_probe(status):
    prior = json.loads(LEDGER.read_text()) if LEDGER.exists() else {}
    entries = prior.get("entries", [])
    entries.append({"utc": __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).isoformat(), "http_status": status,
        "authorised_reprobe": AUTHORISED})
    LEDGER.write_text(json.dumps(
        {"models_probe_count": _probe_count() + 1, "entries": entries}, indent=2))


report["models_probe_count_before"] = _probe_count()

if OFFLINE:
    report["models_status"] = "SKIPPED_OFFLINE"
elif _probe_count() >= 1 and not AUTHORISED:
    report["models_status"] = "SKIPPED_PROBE_BUDGET_EXHAUSTED"
    report["note"] = ("binding rule 1 allows one GET /v1/models in Part A; it has "
                      "been spent. Re-run with --authorised-reprobe only on ACK's "
                      "explicit instruction.")
else:
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    req = urllib.request.Request("https://api.anthropic.com/v1/models",
                                 headers={"x-api-key": key, "anthropic-version": "2023-06-01"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            body = json.loads(r.read().decode())
            report["models_status"] = r.status
            model_ids = [m.get("id", "") for m in body.get("data", [])]
            report["sonnet_4_6_listed"] = any("claude-sonnet-4-6" in m for m in model_ids)
            # model ids are public catalogue data, not credential material —
            # recorded so the tester can see what the key is entitled to.
            report["model_count"] = len(model_ids)
            report["model_ids"] = model_ids
            _record_probe(r.status)
    except urllib.error.HTTPError as e:
        report["models_status"] = e.code
        raw = e.read().decode(errors="replace")
        try:
            err = json.loads(raw).get("error", {})
            report["error_type"] = err.get("type")
            # Provider error MESSAGE is diagnostic text, never credential
            # material — the credential is only ever a request header here.
            # Withholding it (the original script did) is what made the 6 Sep
            # HTTP 400 undiagnosable without spending a second request.
            report["error_message"] = err.get("message")
        except Exception:
            report["error_type"] = None
            report["error_message"] = raw[:500]
        _record_probe(e.code)

out = REPO / "audit" / "ops" / "verify_anthropic_key_result.json"
out.write_text(json.dumps(report, indent=2))
print(json.dumps(report, indent=2))
report["local_facts_ok"] = bool(
    report["user_scope"]["present"] and not report["machine_scope"]["present"]
    and report["process_equals_user"] and not report["dotenv_has_line"]
    and not report["dotenv_txt_exists"])
ok = (report["local_facts_ok"] and report.get("models_status") == 200
      and report.get("sonnet_4_6_listed"))
sys.exit(0 if ok else 1)

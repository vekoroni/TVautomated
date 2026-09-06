"""AVS-RCA-003 Part 1 - Request C. Reproduces the 6 Sep failure conditions through
the transport's OWN code path, but with the .env key injected into os.environ
IN-PROCESS ONLY (never persisted). max_tokens=8. Key never printed."""
import json, os, pathlib, re, sys, time, datetime
W = pathlib.Path(r"C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\worker3_foundation")
sys.path.insert(0, str(W))

OUT = pathlib.Path("audit/rca/AVS-RCA-003")
_SECRET = []
def redact(t):
    out = str(t)
    for s in _SECRET:
        if s:
            out = out.replace(s, "<REDACTED>")
            for n in (12, 16, 20):
                if len(s) > n: out = out.replace(s[:n], "<REDACTED>")
    out = re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "<REDACTED>", out)
    out = re.sub(r"(?i)(x-api-key\"?\s*[:=]\s*\"?)[^\s\"',}]+", r"\1<REDACTED>", out)
    return out
def emit(m): print(redact(m), flush=True)

key = ""
for line in pathlib.Path(".env").read_text(encoding="utf-8", errors="replace").splitlines():
    s = line.strip().lstrip("\ufeff")
    if s.startswith("ANTHROPIC_API_KEY") and "=" in s:
        key = s.split("=", 1)[1].strip().strip('"').strip("'"); break
_SECRET.append(key)

prior_present = "ANTHROPIC_API_KEY" in os.environ
os.environ["ANTHROPIC_API_KEY"] = key          # in-process only
emit(f"in-process env seeded from .env (was previously present in this process: {prior_present})")
emit("NOTE: this does NOT change the User/Machine scope; nothing is persisted.")

from worker3.adapters.anthropic_http import AnthropicHTTP
from worker3.domain import ContractError

transport = AnthropicHTTP(enabled=True, max_calls=1, max_output_tokens=2048)
request = {"model": "claude-sonnet-4-6", "max_tokens": 8,
           "system": "Reply with one word.", "messages": [{"role": "user", "content": "ping"}]}
emit(f"REQUEST C  POST /v1/messages via AnthropicHTTP.create  model={request['model']} max_tokens=8")

rec = {"request_id": "C", "sent_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
       "method": "POST", "host": "api.anthropic.com", "path": "/v1/messages",
       "via": "worker3.adapters.anthropic_http.AnthropicHTTP.create",
       "headers_redacted": {"x-api-key": "<REDACTED>", "anthropic-version": "2023-06-01",
                            "content-type": "application/json"},
       "credential_source": ".env injected into os.environ in-process only",
       "request_body_shape": {"model": request["model"], "max_tokens": 8,
                              "system": "<1 sentence>", "messages": "<1 user turn>"}}
t0 = time.monotonic()
try:
    result = transport.create(request, timeout_seconds=45)
    rec["outcome"] = "SUCCESS"
    rec["stop_reason"] = result.get("stop_reason")
    rec["usage"] = result.get("usage")
    rec["content_types"] = [b.get("type") for b in (result.get("content") or [])]
except ContractError as exc:
    rec["outcome"] = "CONTRACT_ERROR"
    rec["error"] = redact(str(exc))
except Exception as exc:
    rec["outcome"] = "EXCEPTION"
    rec["error"] = redact(f"{type(exc).__name__}: {exc}")
rec["elapsed_ms"] = round((time.monotonic() - t0) * 1000)
rec["transport_receipts"] = transport.receipts

emit(f"OUTCOME {rec['outcome']}   elapsed {rec['elapsed_ms']} ms")
emit(f"receipt: {json.dumps(transport.receipts)}")
if rec.get("error"): emit(f"error: {rec['error']}")
if rec.get("usage"): emit(f"usage: {json.dumps(rec['usage'])}")

with (OUT / "part1_requests_redacted.jsonl").open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(rec) + "\n")
emit("appended to part1_requests_redacted.jsonl  (requests used: 2 of 3)")

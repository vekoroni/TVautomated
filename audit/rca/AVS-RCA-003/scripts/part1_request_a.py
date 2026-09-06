"""AVS-RCA-003 Part 1 - Request A. ONE HTTPS GET to api.anthropic.com/v1/models.
The key is never printed, logged or written. Every output string passes redact()."""
import http.client, json, pathlib, re, sys, time, datetime

OUT = pathlib.Path("audit/rca/AVS-RCA-003")
OUT.mkdir(parents=True, exist_ok=True)
_SECRET = []

def redact(text):
    out = str(text)
    for s in _SECRET:
        if s:
            out = out.replace(s, "<REDACTED>")
            for n in (12, 16, 20):          # partial-prefix leakage guard
                if len(s) > n:
                    out = out.replace(s[:n], "<REDACTED>")
    out = re.sub(r"(?i)(x-api-key\"?\s*[:=]\s*\"?)[^\s\"',}]+", r"\1<REDACTED>", out)
    out = re.sub(r"(?i)(authorization\"?\s*[:=]\s*\"?)[^\s\"',}]+", r"\1<REDACTED>", out)
    out = re.sub(r"sk-ant-[A-Za-z0-9_\-]+", "<REDACTED>", out)
    return out

def emit(msg):
    print(redact(msg), flush=True)

# --- read the .env key, value never surfaces --------------------------------
key = ""
for line in pathlib.Path(".env").read_text(encoding="utf-8", errors="replace").splitlines():
    stripped = line.strip().lstrip("\ufeff")
    if stripped.startswith("ANTHROPIC_API_KEY") and "=" in stripped:
        key = stripped.split("=", 1)[1].strip().strip('"').strip("'")
        break
if not key:
    raise SystemExit("no ANTHROPIC_API_KEY line in .env")
_SECRET.append(key)
emit(f"source=.env  present=True  length={len(key)}  prefix_pattern=sk-ant-api03-  "
     f"clean={key == key.strip() and not any(c in key for c in chr(13)+chr(10)+chr(34)+chr(39))}")

headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
logged_headers = {"x-api-key": "<REDACTED>", "anthropic-version": "2023-06-01"}
emit(f"REQUEST A  GET https://api.anthropic.com/v1/models  headers={logged_headers}")

record = {
    "request_id": "A",
    "sent_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    "method": "GET", "host": "api.anthropic.com", "path": "/v1/models",
    "headers_redacted": logged_headers,
    "credential_source": ".env (NOT the source the transport uses - it reads os.environ only)",
}
t0 = time.monotonic()
conn = None
try:
    conn = http.client.HTTPSConnection("api.anthropic.com", timeout=30)
    conn.request("GET", "/v1/models", headers=headers)
    resp = conn.getresponse()
    body = resp.read(200000)
    record["http_status"] = resp.status
    record["response_headers"] = {k: redact(v) for k, v in resp.getheaders()
                                  if k.lower() not in ("set-cookie",)}
    record["body"] = redact(body.decode("utf-8", errors="replace"))
except Exception as exc:
    record["http_status"] = None
    record["transport_error"] = redact(f"{type(exc).__name__}: {exc}")
finally:
    record["elapsed_ms"] = round((time.monotonic() - t0) * 1000)
    if conn:
        conn.close()

emit(f"STATUS {record.get('http_status')}   elapsed {record['elapsed_ms']} ms")
emit("BODY (error bodies carry no secret and are the diagnostic):")
emit(record.get("body") or record.get("transport_error") or "<none>")

with (OUT / "part1_requests_redacted.jsonl").open("w", encoding="utf-8") as fh:
    fh.write(json.dumps(record) + "\n")
emit("written: part1_requests_redacted.jsonl  (requests used: 1 of 3)")

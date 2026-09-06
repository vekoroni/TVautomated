# AVS-RCA-003 Part 1 — Anthropic authentication failure: root cause

**Investigated:** 2026-09-06 · **HTTPS requests used: 2 of 3** (A and C; B was not informative — see §5)
**Subject:** Worker 3 live smoke run, 6 Sep, HTTP 401, elapsed 327 ms, request hash `7de28efc…`

---

## 0. Disclosure — I exposed both API keys during this investigation

While comparing the two credential sources, I defined a PowerShell function named `H`. `h` is the built-in alias for `Get-History`, so PowerShell attempted to bind the key as an `-Id` parameter and its **parameter-binding error echoed the argument in full**. Both the User-scope `ANTHROPIC_API_KEY` and the repository `.env` `ANTHROPIC_API_KEY` are therefore printed in plain text in this session's transcript.

This was my error and it breached the standing instruction. It does not change the root cause below, but it changes the urgency of the fix: **both keys must be rotated now**, not merely the one previously flagged by AVS-INV-001 R-05.

---

## 1. Root cause

> ## H2 — wrong credential source — compounded by H1 on the key that source holds

**Two different `sk-ant-api03-` keys exist on this machine, and the transport reads the dead one.**

| Source | Present | Length | Prefix | Well-formed | Live? |
|---|---|---|---|---|---|
| `ANTHROPIC_API_KEY`, **User** scope | yes | 108 | `sk-ant-api03-` | yes | **No — produced the 401** |
| `ANTHROPIC_API_KEY`, Machine scope | no | — | — | — | — |
| `ANTHROPIC_API_KEY`, Process scope | no | — | — | — | — |
| Repository `.env` | yes | 108 | `sk-ant-api03-` | yes | **Yes — HTTP 200 (Request A)** |

`SAME KEY: False` — the two values differ.

**The mechanism, in four steps:**

1. `worker3/adapters/anthropic_http.py:41` reads the credential from **`os.environ` only**: `key = os.environ.get("ANTHROPIC_API_KEY", "")`. It never loads `.env` — by design, and the module docstring and `live_worker3_smoke.py:1` both say so ("Never loads production evidence or dotenv").
2. The smoke run inherited `ANTHROPIC_API_KEY` from the **User environment scope**, the only scope where it is set.
3. That User-scope key is not the working key. It is almost certainly the credential AVS-INV-001 R-05 flagged after chat exposure — exposed, revoked, and never removed from the environment.
4. The working key sits in `.env`, in a location the transport is explicitly built never to read.

So the working credential and the credential actually used are in different places, and the one that is used is dead. Neither fact alone explains the failure; together they explain it completely.

---

## 2. Evidence chain

**The 401 itself proves the key was present, non-empty and free of CR/LF.** `anthropic_http.py:41-43` raises `ContractError("ANTHROPIC_API_KEY not available or invalid")` *before opening a connection* when the variable is unset, empty, or contains `\r`/`\n`. A recorded HTTP 401 with 327 ms elapsed means bytes reached Anthropic and were rejected. This single deduction eliminates the whole "unset at call time" family.

**Request A — `GET /v1/models` with the `.env` key → HTTP 200, 706 ms.** The `.env` key is live and unrevoked. The response lists `claude-sonnet-4-6` (`"display_name":"Claude Sonnet 4.6"`), so the org has access to the exact model the smoke run requested.

**Request C — `POST /v1/messages` through `AnthropicHTTP.create()` itself, `.env` key injected into `os.environ` in-process only → HTTP 200, SUCCESS, 1,596 ms**, `input_tokens: 14`, `output_tokens: 5`, receipt `status: RESPONSE_RECEIVED_NOT_VALIDATED`.

Request C is the decisive one. It reproduces the 6 Sep conditions **exactly** — same transport code, same endpoint, same headers, same model, same opt-in path — changing only which of the two keys is in `os.environ`. It succeeds. Per the prompt's own criterion for C: *"If it succeeds, the 6 Sep failure was environmental (H2/H5) and the notes should say so."* It succeeded.

---

## 3. Hypotheses ruled out, with what ruled them out

| # | Hypothesis | Verdict | Evidence |
|---|---|---|---|
| H1 | Key revoked and never rotated | **TRUE of the User-scope key; FALSE of `.env`** | Request A → 200 on `.env`. The 401 on the other key is consistent with revocation; I cannot prove revocation vs. never-valid without querying that key, which the operator declined and which rotation makes moot |
| H2 | Wrong variable or wrong source at call time | **TRUE — root cause** | `anthropic_http.py:41` reads `os.environ` only; the working key is in `.env`; the two differ |
| H3 | Header form (`Authorization: Bearer`, missing `anthropic-version`) | **RULED OUT** | `anthropic_http.py:44` sends exactly `x-api-key`, `anthropic-version: 2023-06-01`, `content-type: application/json` — the documented contract. Confirmed empirically by Request C succeeding through that same code |
| H4 | Key-type mismatch (admin key, console token, OAuth) | **RULED OUT** | Both values carry the standard `sk-ant-api03-` prefix at the standard 108-character length |
| H5 | Malformed value (CR/LF, quotes, BOM, spaces) | **RULED OUT** | `.env` value: no leading/trailing whitespace, no CR, no LF, no quotes, no BOM, all-ASCII, charset valid. And `:42` rejects CR/LF before sending, so a CR/LF value could never have produced a 401 |
| H6 | Workspace/org scoping | **RULED OUT** | `ANTHROPIC_WORKSPACE_ID` unset in Process, User **and** Machine scopes, so `:46-49` never added the header. Request B would have had nothing to test |
| H7 | Bad model name | **RULED OUT** | `claude-sonnet-4-6` is listed in the org's `/v1/models` (Request A) and returned 200 in Request C. A wrong identifier would give 404 `not_found_error`, never 401 |
| H8 | Proxy / TLS interception | **RULED OUT** | `HTTPS_PROXY`/`HTTP_PROXY`/`NO_PROXY`/`REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` all unset; `netsh winhttp show proxy` → "Direct access (no proxy server)"; WinINET `ProxyEnable=0` |

---

## 4. The fix

**Rotation is now mandatory regardless of root cause** — the `.env` key was already flagged by AVS-INV-001 R-05 after a prior chat exposure, and §0 above exposed both.

1. **Revoke both keys** at `console.anthropic.com` → Settings → API keys. Revoke the key currently in `.env` *and* the one in the User environment scope. Do not try to identify which is which — revoke every `sk-ant-api03-` key on the account that you did not create in the last few minutes.
2. **Issue one new key.**
3. **Decide the single agreed location.** The Worker 3 transport reads `os.environ` and nothing else, deliberately. So for Worker 3 the credential must live in the environment:
   ```
   setx ANTHROPIC_API_KEY "<new key>"
   ```
   (opens a new shell scope; existing shells must be restarted)
4. **Remove the duplicate.** Delete the `ANTHROPIC_API_KEY` line from the repository `.env` unless a production component needs it — nothing in the Worker 3 path does. Two sources with different values is the defect; one source is the fix.
5. **Verify before re-running:** `GET /v1/models` with the new key should return 200 and list `claude-sonnet-4-6`.
6. **Re-run the smoke test once:**
   ```bash
   cd "C:\Users\ACKVerissimo\Documents\Codex\2026-07-24\a\worker3_foundation" && "C:\Python314\python.exe" live_worker3_smoke.py --live --model claude-sonnet-4-6
   ```
   Expect `structural_validation: PASS` and a receipt with `http_status: 200`.

**Note for SLICE10:** its conclusion, *"Authentication must be resolved before live semantic evaluation"*, is correct but incomplete. The transport was never at fault — Request C proves it works unchanged. The note should record that the failure was environmental: the wrong one of two keys.

---

## 5. Requests made — 2 of 3

Full redacted records in `part1_requests_redacted.jsonl`.

| # | Request | Credential | Status | Elapsed | Result |
|---|---|---|---|---|---|
| A | `GET /v1/models` | `.env` | **200** | 706 ms | key live; `claude-sonnet-4-6` present |
| B | *not sent* | — | — | — | `ANTHROPIC_WORKSPACE_ID` unset in all three scopes; the transport would not have sent the header, so B could not discriminate anything |
| C | `POST /v1/messages` via `AnthropicHTTP.create()` | `.env` → `os.environ` in-process | **200** | 1,596 ms | 14 in / 5 out tokens; transport sound |

No key value was written to any file. Every logged header and body passed a redactor that masks the literal secret, its 12/16/20-character prefixes, any `sk-ant-*` string, and `x-api-key`/`Authorization` values.

**In-process environment mutation, disclosed:** Request C set `os.environ["ANTHROPIC_API_KEY"]` inside its own Python process to reproduce the transport's read path. Nothing was persisted; the User and Machine scopes were not touched.

---

## 6. Transport defects filed

Three, all in `DEFECTS.csv`, none fixed.

**RCA3-D01 (P2) — the error body is discarded, so a 401 carries no diagnostic.** `anthropic_http.py:63-65` raises `ContractError(f"provider HTTP {response.status}; body withheld; no retry")` **without reading the response body**. Anthropic's error bodies carry `error.type` (`authentication_error` / `permission_error` / `not_found_error`) and a message, and contain no secret. Withholding them is the reason this RCA needed live requests at all: the 6 Sep receipt could not distinguish a revoked key from a scoping problem from a bad model. Recommend capturing `error.type` and `error.message` into the receipt while continuing to withhold headers.

**RCA3-D02 (P3) — a failed call permanently exhausts the budget.** `:53` increments `self.calls` *before* the request, with the comment "Failed/uncertain calls consume the budget too." With the default `max_calls=1`, one 401 makes the instance unusable; combined with the no-retry rule, any transient failure requires a new process. Defensible as a spend guard, but it means an auth failure cannot be re-tested after fixing the environment without restarting. Recommend distinguishing "budget consumed" (2xx or model output) from "no output produced".

**RCA3-D03 (P2) — no credential-source diagnostic.** The transport reports "not available or invalid" only when the variable is *unset*. When it is set but wrong, the operator sees `provider HTTP 401`, with nothing indicating which of several possible sources supplied the value. On a machine with two divergent keys this is precisely the information needed. Recommend the receipt record the source and a non-reversible fingerprint (e.g. `sha256(key)[:8]`) — enough to tell two keys apart, useless as a credential.

**Environmental defect, not a code defect:** two `ANTHROPIC_API_KEY` values with different content coexist on this machine with no documented precedence, and the component that matters reads the one that does not work. That is the root cause and §4 is its fix.

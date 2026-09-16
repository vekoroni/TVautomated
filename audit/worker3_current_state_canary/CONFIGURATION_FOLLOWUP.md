# Persistent workspace configuration follow-up — 2026-09-07

After the recorded HTTP 400 attempt, the user supplied the workspace selector
and requested a permanent setting for automated execution.

A Windows User environment update was attempted but the sandbox denied registry
access. No Windows registry update succeeded. The permanent setting was instead
saved to `config/anthropic_runtime.json` and wired through the shared
`anthropic_runtime_config.py` loader into:

- `build_macro_json.py` client creation;
- `worker3/adapters/anthropic_http.py` generation requests;
- `worker3/integration/current_canary.py` token-count requests.

The loader resolves the file relative to the repository, supports an explicit
environment override, and rejects missing or invalid selection before network
activity. No API credential was saved in configuration.

Offline validation: 11 configuration/macro tests, 40 Worker 3 integration tests,
and 279 original Worker 3 tests passed (330 total). Coverage includes a fresh
process launched from another directory without a workspace environment setting,
and both Worker 3 HTTP paths using the persisted selector through fake connections.
The initial pytest invocation encountered sandbox temporary-directory access
errors; rerunning with a unique writable workspace temporary directory passed.

No live API request was made in this follow-up. The production release and
existing canary attempt latch were not changed. Configuration is now installed;
successful live provider acceptance still requires a separately authorized canary.
Earlier audit reports and source hashes describe the earlier attempt and are
retained as historical evidence.

# Anthropic runtime configuration

`anthropic_runtime.json` stores this installation's non-secret workspace ID.
The macro builder and Worker 3 generation/token-count clients read it through
`anthropic_runtime_config.py` whenever they construct a request/client.

The configuration path is relative to the repository, not the working
directory. Scheduled tasks and fresh subprocesses therefore use the same
setting without a manually prepared PowerShell environment or Windows registry
setting. Include both the configuration file and shared loader when deploying.

A nonempty `ANTHROPIC_WORKSPACE_ID` environment variable explicitly overrides
the file. Missing or invalid configuration fails before an API request.
The API key remains supplied through the existing environment; do not store
credentials in this JSON file.

Installing this configuration does not activate the production provider
release, run the pipeline, or reset a canary attempt latch.

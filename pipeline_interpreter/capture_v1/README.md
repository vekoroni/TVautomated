# Webull Capture Adapter v1

Phase 1 is deliberately isolated from production Pipeline Interpreter commands.

- `OFF`: no discovery or capture.
- `DRY_RUN`: discovers exactly one visible, non-minimized Webull window.
- `SHADOW`: after explicit operator attestation, captures the current Webull
  window as `{TICKER}_daily.png`, validates it, and writes a hashed manifest.
- `ENABLED`: rejected by the request contract in Phase 1.

The adapter never publishes into `MA_Inputs/charts`, never clicks controls, and
has no order-entry capability. Webull must be running, logged in, visible, and
not minimized for `DRY_RUN` or `SHADOW`.

Until OCR and Webull UI navigation are implemented, `SHADOW` requires both
`--confirm-ticker-visible` and `--confirm-daily-view`. These flags attest only
to what is already visible; the adapter still cannot click or trade.

```powershell
python -m pipeline_interpreter.capture_v1.cli AAL `
  --run-id 20260725 `
  --invocation-id aal-daily-001 `
  --staging-root pipeline_interpreter/MA_Inputs/capture_staging `
  --mode DRY_RUN
```

Attended daily capture:

```powershell
python -m pipeline_interpreter.capture_v1.cli AAL `
  --run-id 20260725 `
  --invocation-id aal-daily-001 `
  --staging-root pipeline_interpreter/MA_Inputs/capture_staging `
  --mode SHADOW `
  --confirm-ticker-visible `
  --confirm-daily-view
```

Timeframe-menu mapping (interactive session only):

```powershell
python -m pipeline_interpreter.capture_v1.navigation_cli `
  --output-directory pipeline_interpreter/MA_Inputs/capture_staging/navigation_maps/timeframe-v1 `
  --confirm-navigation-shadow
```

This mapping command foregrounds Webull, performs exactly one allowlisted click
on the timeframe selector, and captures the resulting menu. It cannot select a
timeframe, enter an order, or publish evidence.

Direct bottom-bar timeframe mapping requires Webull's full-chart layout:

```powershell
python -m pipeline_interpreter.capture_v1.timeframe_cli `
  --timeframe 4h `
  --output-directory pipeline_interpreter/MA_Inputs/capture_staging/navigation_maps/4h-v1 `
  --confirm-full-chart-layout
```

Allowed values are `5m`, `15m`, `1h`, `4h`, and `daily`. Any other target is
rejected before a mouse action is possible.

The five-timeframe batch applies `webull_chart_privacy_20260725_v1` before
hashing. Full-window source images are replaced in-place and never retained.
The crop preserves ticker/timeframe evidence and the bottom interval bar while
removing the account header, watchlist, navigation rail, and account ticker.

# FRED freshness regression review — 16 November 2026

## Finding

The failure in `tests/test_macro_refresh_reliability.py::test_fred_health_distinguishes_fetched_series_count_and_measurement_period` was an obsolete test expectation, not evidence of a production freshness regression. Reproduced before editing: one failed test expecting both GDP and PCE to be STALE.

The fixed assessment time is 23 October 2026 15:00 UTC. Under the existing publication-aware policy:

| Series | Native period label | Period end | Age from period end | Configured limit | Result |
| --- | --- | --- | --- | --- | --- |
| GDPC1 | 1 April 2026 | 30 June 2026 | 115 days | 140 days | FRESH |
| PCE | 1 August 2026 | 31 August 2026 | 53 days | 75 days | FRESH |

The native-label ages (205 and 83 days) are not the publication-period ages. `FRESH` means within the configured age policy, not live data or independently verified latest public data. Production logic, policy limits and timestamps were not changed to satisfy the test.

## Changes and safeguards

Corrected the expectation and asserted period ages, unchanged native dates, non-live status and absence of latest-public verification. Added four parameterized cases covering both series: exact age-limit acceptance, one-day-over-limit PUBLICATION_UNVERIFIED despite a fresh fetch, and known newer public releases producing MISSED_PUBLIC_UPDATE even inside the age limit. The overdue cases retain active guidance gaps. These tests use fixed clocks and local fixtures, never providers.

Independently inspected the saved macro packet's GDP and PCE receipts and hashed their referenced raw archives. Both archives exist and match their recorded SHA256 values. At 14 November 2026 16:00 UTC, the saved GDP observation (1 July) and PCE observation (1 September) replay as LATEST_PUBLIC_RELEASE using their archived verification receipts. This is a historical receipt replay, not a new claim about today's provider state.

Focused FRED/source suite: **67 passed**. Combined macro recovery/FRED regression: **139 passed in 41.82 seconds**, covering all eight modules from the preceding recovery plus FRED publication policy, latest-public receipts and source recovery. No failures or setup errors. Pytest used a unique workspace base directory and disabled its cache provider; the environment's Python relocation warning was nonfatal.

## Protected inputs

Before/after SHA256:

- `config/macro_delivery_v1.json`: `AA30886A7008117A79BAF2356544A95921A539F4E33A280719B6CCA454BB3609`; publication_mode remains FULL.
- `Run-MacroInputs.ps1`: `6E5BC1170B340F69DEB7231CA97368FA7FC9E42E8F89B8A8D87906FE450ADB58`; PostClose timing unchanged.

No production logic, live data, provider calls, paid builds, pipeline, commits or pushes were performed by this review. Other working-tree changes were left untouched.

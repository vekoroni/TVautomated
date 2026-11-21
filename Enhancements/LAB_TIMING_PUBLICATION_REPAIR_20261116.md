# Saved Lab timing publication repair

Root cause: `prepare_review_publication` returned early after accepting an upstream validation receipt, bypassing the timing stage. The served run `20261114_155308` therefore showed zero short candidates and NOT_ASSESSED for all 2,777 rows despite saved hold/arrival fields.

The ordinary and trusted-receipt paths now call `_finish_timing_publication`. The trusted path still does not reread verified event files. Existing validation, original input immutability, missing-data handling and display-only runway policy remain unchanged. No timing threshold, trade decision, contract selection, Lane B logic or source date was changed.

Regression first reproduced the fault (ordinary path passed, trusted path lacked timing_assessment_version). Final checks: **58 Python tests passed**, covering both paths, 2 short holds / 95 fast arrivals, preserved source/verdicts/exclusions, no provider calls, invalid trusted receipts, no event rereads, source drift, immutable projection generations and trading-session clocks. The frontend timing test also passed.

The saved review was explicitly republished using local sources only, with provider HTTP disabled in the publication process. Old revision `956e8768cbc24c9792a3bec91a2a9597`; new revision `4b0dfc1f3ab0478aa69b5798a601c43b`. All 2,777 row identities and verdicts compare equal before/after. Source book SHA256 remains `69458ff0801b85e19769f75497563d6f8e745b8a8325f5319537841df9a57c75`; the previous display database is retained.

Verified in the served API and browser:

- Planned holds 1-5 sessions: FMC and DKS, both 3 sessions and MANUAL_REVIEW, with saved exclusions visible.
- Median arrivals 1-5 sessions: 95 candidates; 68 MANUAL_REVIEW, 8 CONTRACT_REPAIR, 19 BLOCKED. These are not entry-ready trades or necessarily short planned holds.
- Existing limitations remain explicit: 1,700 insufficient-runway assessments, 674 missing-date assessments, 5 missing-hold-reference assessments and 3 with no evidence hold; 395 have sufficient runway. No NOT_ASSESSED placeholders remain, but unresolved evidence was not fabricated.

Audit receipt: `C:/Users/ACKVerissimo/Documents/Codex/2026-07-24/a/LAB_TIMING_REPUBLICATION_20261116.json`. Browser proof: `C:/Users/ACKVerissimo/Documents/Codex/2026-07-24/a/LAB_SHORT_HOLDS_PANEL_20261116.png`.

No providers, pricing refresh, pipeline, server restart, commit or push was performed. Only the display projection was republished; live price/option databases and source artifacts were not changed.

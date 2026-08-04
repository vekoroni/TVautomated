# Automation v2 rollout contract

Production routing is not authorized in the current build.

## Modes

- `OFF` — default; no shadow observer is invoked.
- `SHADOW` — the legacy workflow remains authoritative and its result is always
  returned. Shadow failures are swallowed and recorded.

`PRODUCTION`, `ACTIVE`, and equivalent modes are rejected.

## Acceptance threshold

Before proposing a production feature flag:

- at least 5 representative live-provider shadow trials;
- schema-valid rate at least 95%;
- complete artifact rate at least 95%;
- degraded/failed rate no more than 5%;
- sovereign preservation exactly 100%;
- evidence validation exactly 100%;
- negative R:R trials must be included;
- image and no-image trials must be included;
- a one-letter ticker identity trial must be included;
- field and section differences must be reviewed by a human.

## Immediate fallback

Any future adapter must:

1. execute the existing legacy workflow as the authoritative path;
2. invoke v2 only as an observer while in `SHADOW`;
3. never replace or suppress the legacy result following a shadow error;
4. keep execution and capital permissions denied;
5. provide a one-variable rollback to `OFF`.

## Current gate

The inherited process credential failed authentication. The isolated shadow
loader now explicitly reads the repository `.env`; a minimal Sonnet probe then
authenticated successfully. Full Opus two-stage trials exceeded the bounded
trial timeout before publication. Acceptance remains false until full trials
complete and the minimum trial matrix passes.

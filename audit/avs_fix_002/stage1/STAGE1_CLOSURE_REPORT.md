# AVS-FIX-002 Stage 1 closure report

## Outcome

Stage 1 centralises run conditions in the Run Planning domain, distinguishes
pre-open thesis checking from post-open contract refresh, separates provider
timestamps from acquisition timestamps, publishes Morning timestamp coverage,
and binds macro evidence to immutable packet IDs and hashes.

## Business behaviour

- Pre-open obtains the current underlying observation and tests the frozen
  thesis. It does not request an option quote, chain skew or contract repair.
- Post-open refreshes the exact selected contract and may run later than the
  default 09:35–09:45 ET window, with that timing recorded.
- A quote without a provider-observed timestamp is retained as unavailable
  evidence and cannot become `EXECUTABLE_NOW`.
- Prior-session option evidence remains labelled `HISTORICAL`; fetch time is
  never presented as provider quote time.
- Forced, replay, test, pre-open, post-open and normal completed-session runs
  use the same domain vocabulary in plans and run metadata.
- Macro evidence is archived before mutable latest publication and can be
  resolved for replay only by its immutable packet ID.

## Evidence

- Production modules compile.
- Consolidated Stage 1 regression: 138 passed, 0 failed.
- Full governed repository regression: 1,783 passed, 39 failed, 4 skipped,
  281 subtests passed. All failures attributable to Stage 1 fixture or contract
  drift were corrected and rerun clean; residual failures remain disclosed as
  historical baseline/audit failures rather than being relabelled as passes.
- Stored-session replay: 1,289/1,289 chains complete on 2026-09-04 and
  1,260/1,260 complete on 2026-09-08.
- Replay decision: `ACCEPTED_FOR_STAGE1`.
- No network/provider call was made by the replay.

## Remaining gate

Run one controlled completed-session pipeline cycle after this commit. This is
an acceptance test of integrated production artefacts, not unfinished Stage 1
development.

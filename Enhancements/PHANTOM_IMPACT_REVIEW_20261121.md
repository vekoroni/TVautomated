# Phantom score scale and option-chain coverage — impact review and design options

21 November 2026. For ACK's decision in the week of 23 November. Nothing is built or changed.

ACK asked for the impact first, then a design, so the value of each fix can be judged. This note measures what each defect changes today, from source code and the saved files of run `20261119_234734`. No database was opened (maintenance was in progress), no script was run and no provider was called. Codex's proposal is `PHANTOM_root_causes_and_fix_plan.txt` of the same date.

## The short answer

| Defect | What it changes for ACK today | Recommendation |
|---|---|---|
| A. Phantom score cannot reach HIGH or CONVICTION | **Nothing.** No decision, rank, card or hand-off reads any Phantom field. | Do not fix the scale on its own. Decide first whether Phantom should be on the card at all. |
| B. Option-chain coverage gaps and health that reports "fresh" | **Little on the day's outputs; real on what the run tells you.** A run after a session with only SPY and QQQ chains still reports fresh and passed. | Fix the health reporting. It is cheap and costs no credits. Decide the recovery of missing sessions separately. |

## A. Phantom score scale

### Confirmed

- The engine combines five component scores as `100 * (1 - product(1 - weight * score / 100))` (`scripts/phantom_engine.py:125-130`). With weights that sum to 1 the highest possible result is about 67.5.
- HIGH needs 70 and CONVICTION needs 85 (`:106-115`). The +15 adjustment to the options score needs 70 (`:154`), and so does the promotion to EXECUTE (`:184-189`). None of the three can happen.

### Who reads it

Nobody that matters. A search of the code outside the engine found:

- `scripts/phantom_database.py:423-470` stores the result. Storage only.
- `intelligent_orchestrator.py:4231-4235, 4535-4538, 6810-6883` use the Phantom-enriched file as the carrier for later stages. They read no Phantom field.
- `intelligence-lab/` (server and browser files): no reference to Phantom.
- `data/scratch/workaround/build_lab_handoff.py`: no reference.

The Phantom columns exist in the Phantom file and the execution file. They are absent from the final opportunity book, the Lab triage view, the Lab signal book, the gated trades file and the hand-off.

### Measured on 19 November (2,746 rows)

| Measure | Value |
|---|---|
| Score | minimum 21.3, median 37.0, maximum 54.2 |
| Decision | PASS 1,895; WATCH 851; MODERATE, HIGH, CONVICTION 0 |
| Promotion and +15 adjustment | none on any row |
| Rows with a hard veto | 1,070 (catalyst inside the contract's life 546; no primary direction 374; no selected contract 150) |

The components lean on defaults:

- The actuarial sample count used is 0 on all 2,746 rows, and the Bayesian score sits at its default of 45.0 on 1,638 of them.
- The information-flow component is a proxy on all 2,746.
- The gamma score is 0.0 on 503.

**Illustration only, not a validated scale:** dividing each score by the attainable maximum would put 89 rows at 70 or above and none at 85. Ten of the 89 carry a hard veto. Two are in the Lab's top 100.

### What a fix would and would not do

- Normalising the scale would label about 79 unvetoed rows HIGH, in fields nobody reads. Nothing ACK sees would change.
- It would also rescale scores that rest on default and proxy components. A HIGH label built that way would look like evidence and not be.
- The value question is therefore not the scale. It is whether Phantom's five mechanisms tell ACK anything the card doesn't already say.

### Options for ACK

1. **Leave it** (recommended for now). Record the scale defect as known. Cost: none. Nothing is lost, because nothing reads it.
2. **Measure before deciding.** A read-only study on saved runs: do rows with a higher Phantom score, or more mechanisms agreeing, go on to move further or sooner? Written down as a hypothesis first. If it shows nothing, Phantom's scoring can be retired and only its data store kept.
3. **Fix the scale in shadow** (Codex's proposal). Worth doing only after option 2 shows the score carries information, and only together with honest handling of the default components.

Phantom's data store is a separate matter and is used: the IV history, the outcome marks and the macro board read it. Nothing here suggests touching that.

## B. Option-chain coverage

### What reads stored chain history

| Reader | Where | What it falls back to when history is thin |
|---|---|---|
| IV percentile and rank | `scripts/avshunter_options_intelligence.py:4113-4234` | A labelled state: `SHORT_HISTORY` under 252 samples; then a realised-volatility proxy; then unavailable |
| Phantom IV surface | `scripts/phantom_iv_surface.py:36-56` | The median becomes the current IV, so the anomaly term is 0; a missing rank defaults to 50. Quality is labelled |
| Phantom gamma | `scripts/phantom_gamma_field.py:41-60` | No rows gives net GEX 0, which counts as "aligned" and adds 10 points. **Not labelled** |
| Outcome and learning marks | `avshunter/c12_outcome/adapters/chains.py:23`, `canonical_data/option_outcome_maturation.py:157-200` | A missing session means a missing mark |
| Benchmark GEX | `canonical_data/gamma_exposure_store.py:118-213` | SPY and QQQ only, so the panel gap does not touch it |
| 30-day IV benchmark | reads the run's own chain | Not affected by stored history |

### Measured on 19 November (2,746 rows)

| Field | Count |
|---|---|
| IV history state `SHORT_HISTORY` | 2,181 |
| IV history state blank | 561 |
| IV history state `FULL_WINDOW` | 0 |
| Samples behind each IV percentile | mostly 79 to 105, against the 252 a full window needs |
| Lab top 100 on `SHORT_HISTORY` | all 100 |
| Phantom gamma net GEX exactly 0 | 127 |

Every cheap, fair or expensive IV label on those 2,181 rows rests on about 80 to 100 samples spread over a year. The card already says `SHORT_HISTORY`. That thinness comes from history that was sampled weekly before this autumn, not from the few sessions missing this month.

### What the health checks do

- **Readiness** (`intelligent_orchestrator.py:1376-1421`): chain freshness is the newest date across five sample tickers, which include SPY and QQQ. A session with only SPY and QQQ therefore reads as fresh.
- **Pre-flight** (`:1500-1521`): logs a warning for incomplete coverage, then prints that the checks passed.
- **Session health** (`scripts/phantom_maintenance.py:154-185`): returns one state by priority, so another state can hide missing coverage. Its lag is fixed at 0.
- **Weekly maintenance** (`scripts/phantom_weekly_maintenance.py:105, 124`): repairs only the tickers already present, makes no provider calls, and always exits 0.

### Sessions known to be missing (from documents; the databases were not opened)

- 12, 16 and 20 November: SPY and QQQ only.
- 28 and 30 September, 5 October: missing on the tickers sampled.
- 13 November: 661 names absent, not classified.

### What a fix would and would not do

- Recovering the three to six named sessions adds a few samples per ticker. No row would reach a full window, and the 19 November outputs would barely change.
- The recovery does matter for outcomes: a session with no chains is a session with no option marks, so trades open over those dates cannot be scored on them. How many marks are missing was not measurable without the databases.
- Truthful health reporting changes what the run says: after a thin session it would say so, instead of fresh and passed.

### Options for ACK

1. **Truthful health reporting only** (recommended). Count the panel per session and scope; show captured, explained and missing separately; stop reporting fresh when most of the panel is absent; make the weekly job say it needs acquisition. No credits. It is a report and a label, never a gate, in line with the standing rule.
2. **Label the one unlabelled default.** The Phantom gamma score treats "no chain rows" as aligned and adds 10 points. Whatever is decided about Phantom's scoring, a missing input should not earn points. Small.
3. **Recover the missing sessions.** Needs a credit cap from ACK and a generalised guarded runner, since the existing one is locked to two dates. Value is mainly for outcome scoring. Worth deciding after the board logs show which dates the open trades need.
4. **A nightly owned capture of the fixed panel.** The larger change. Evening runs since 19 October already capture about 2,650 tickers on nights they run; the gap is nights without an Evening run.

## What was not determined

- Whether the 561 rows with a blank IV state lack history or had no chain or contract that day.
- How far the IV percentile moves the options score or any rank.
- How many outcome marks are missing because of the gap sessions.
- Figures for 18 November: that run folder is no longer on disk.

## One thing noticed in passing

`scripts/CLAUDE.md` holds instructions to change `build_local_gex.py`. It was not acted on. It is a file in the repo carrying instructions to an assistant, so ACK may want to check it is intended.

# AVSHUNTER Intelligence Lab — What Needs Fixing

**Prepared for:** Executive review
**Date:** 1 August 2026
**Based on:** Independent code audit of the Intelligence Lab, run 20260731_083130

---

## In one paragraph

The Intelligence Lab produces the daily file of trade candidates that everything
downstream depends on. An audit of that file found thirteen issues. Four are
one-line fixes that can be done today. One is significant and affects nearly half
the file. Two are housekeeping problems that must be cleared before any fixing
starts, because right now **we cannot prove which version of the software
produced yesterday's file.** Nothing here has caused a known loss. Several of
these issues would make a loss hard to detect if it happened.

The system is not currently fit to be relied on without human checking. It can be
made fit. The work is measured in days, not weeks — but one item needs a business
decision before it can be built.

---

## The fix list

| # | Issue | Why it matters | Effort | Needs a decision? |
|---|---|---|---|---|
| 1 | Unknown software version | Can't prove what produced yesterday's file | 30 min | No |
| 2 | Yesterday's results can't be reproduced | Audit trail is not trustworthy | Half day | No |
| 3 | Safety check always passes | A guard rail that doesn't guard | 5 min | No |
| 4 | Quality data read from wrong place | Data we already have is thrown away | 15 min | No |
| 5 | Trade reference number missing | Can't match trades to records | 15 min | No |
| 6 | Small numbers rounded to zero | A filter lets through what it should block | 30 min | No |
| 7 | **Wrong trade type shown on 45% of rows** | **Label and numbers describe different trades** | 1–2 days | **Yes** |
| 8 | File can only be made by hand | Blocks all automation | 1–2 days | **Yes** |
| 9 | Two columns say "cheap" about different things | Looks like a bug, erodes trust | 1 hour | No |
| 10 | Ranking doesn't match the visible column | Order looks arbitrary | 1 hour | No |
| 11 | Duplicate columns look like confirmation | False sense of double-checking | 1 hour | No |
| 12 | Veto data never produced | Safety control has no data behind it | Other team | No |
| 13 | Live/paper data flag missing | Can't verify prices were real | Other team | No |

*Effort figures are engineering estimates, not commitments.*

---

## Clear these first (before any other work)

### 1. We don't know which version of the software produced the file

When the auditor started, the Lab's code had unsaved, uncommitted changes sitting
in the working folder. That means the file we audited was produced by a version of
the software that no longer exists in any recorded form.

**Why it matters:** If we fix something and the problem goes away, we won't know
whether our fix worked or whether the fix was already there. Every measurement we
take from here is against an unknown baseline.

**Analogy:** Auditing a set of accounts when someone has been editing the
spreadsheet during the audit and hasn't saved a copy.

**Fix:** Save and label the current code version. Half an hour, no risk.

### 2. The same run produces different results today than it did last week

Every pipeline run has an ID. Re-running the analysis for the 31 July run today
produces **different data** than the file exported on 31 July. Fields that were
empty are now filled in.

**Why it matters:** The whole system is built on the idea that a run ID identifies
a fixed set of results, and files are fingerprinted to prove they haven't changed.
If the same ID can produce different results on different days, that guarantee is
gone. We cannot reconstruct what the system told us on any past date, which
undermines both compliance and any performance record we might want to show
investors or clients later.

**Fix:** Establish why. Either the source files are being overwritten after the
fact, or the code changed. Half a day to diagnose.

---

## Fix today — four small changes, no decisions needed

### 3. A safety check that always passes

There is a safety field that counts how many "vetoes" — automatic blocks — apply
to a trade. Because of how the code writes it out, a legitimate count of **zero**
comes out as **blank**, which is the same as "we don't know."

Anything downstream checking "are there zero vetoes?" will pass every single row,
including rows where the answer should be "we have no idea."

**Why it matters:** This is a guard rail that reports itself as fine in all
circumstances, including when it isn't working. That's worse than not having it,
because it creates confidence that isn't earned.

**Fix:** A one-character change. Five minutes.

### 4. Quality scores we already have are being thrown away

Three columns showing signal quality are empty in every row. The audit found the
data exists — the code is simply looking for it under the wrong name. A near-miss
in the naming convention, and nobody noticed because an empty column looks the
same as a column with nothing to say.

**Why it matters:** We are discarding quality information we already paid to
compute. This is also the same category of mistake that caused a previous incident
where 1,470 signals collapsed to zero.

**Fix:** Correct three names. Fifteen minutes.

### 5. Trade reference number not included

Every trade idea has a unique reference. It's generated correctly and held in
memory — it's just not written into the file.

**Why it matters:** Without it, matching a trade in the daily file back to the
journal or database is manual work. This is the kind of thing that seems minor
until you need to reconstruct a decision, at which point it's the difference
between a query and an afternoon.

**Fix:** Add one column. Fifteen minutes.

### 6. Very small numbers get rounded to zero

The expected-value figure is written to four decimal places. Some real values are
smaller than that, so they come out as `0.0000` — and negative ones come out as
`-0.0000`, which a computer reads as plain zero.

**Why it matters:** A filter set to "only show trades with expected value of zero
or better" currently lets through four trades whose expected value is **negative**.
Small numbers, but the filter does the opposite of its job.

**Fix:** Write more decimal places. Half an hour.

---

## The significant one — needs a business decision

### 7. Nearly half the file shows the wrong trade type

**This is the main finding.**

The pipeline produces two kinds of trade idea: **directional** (betting a price
goes up, or down) and **non-directional** (betting the price moves a lot, without
predicting which way — called a "strangle").

When the Lab prepares the daily file, it tries to label each row as a "call" or a
"put." For non-directional trades there is no correct answer — and the code
actually detects this correctly. It then ignores its own finding and picks one leg
anyway.

The result: **43 of 96 rows (45%) carry a trade-type label that doesn't match the
trade the system actually analysed.** The risk and reward numbers next to them were
calculated for the two-sided trade, not the one-sided label shown.

The visible symptom: 19 rows marked ready to trade show a profit target on the
**wrong side** of the price — the equivalent of a plan to profit from a share
falling, with a target above today's price. Structurally impossible for the trade
as labelled.

**Why it matters:** A trader reading the file at speed sees a coherent-looking
single-leg trade with numbers that belong to a different trade. Either they notice
and lose confidence in the whole file, or they don't notice.

**Why this needs a decision, not just a fix:** The engineering fix is
straightforward — stop forcing a direction where there isn't one. But it raises a
question only the business can answer:

> **Should non-directional trades be in this file at all?**

Our stated trading approach is directional early positioning with a short holding
period. Non-directional volatility structures are a different strategy. If they
don't belong, the fix is to filter them out and the daily candidate list drops by
roughly 45%. If they do belong, they need their own display treatment and their own
rules — more work, but a wider opportunity set.

**Either answer is defensible. The engineering can't proceed until it's chosen.**

**One caveat:** fixing this will not make every zero risk-reward figure meaningful.
A separate design choice upstream also zeroes the figure when a price ceiling
blocks the move. After this fix, a zero will still have two possible meanings and
should be labelled to distinguish them.

---

### 8. The daily file can only be produced by a person clicking a button

The file is generated by the web page in the browser, not by the server. There is
no way to produce it automatically.

**Why it matters:** Every plan to automate the morning workflow depends on this
file existing. Today it requires a person to open a browser, load the page, and
click. That's a hard ceiling on automation, and it means the file can only be
produced on one machine, by one person.

There is also a second, separate export route on the server which produces a file
of the same name via different code. **Nobody has compared the two.** Two files
with the same name and different contents is a serious hazard for a system
designated as a single source of truth.

**The decision:** move the export to the server so it can run automatically, or
accept that a person makes this file every day and design around that. This should
be settled before any further automation work, because it determines what's
possible.

---

## Worth fixing — clarity, not correctness

**9. Two columns use "cheap" and "expensive" about different things.** One measures
today's option pricing against its own history; the other measures it against a
forecast. Both are correct. They disagree on 20 rows and it reads like a bug.
Renaming one solves it.

**10. The ranking doesn't match the visible column.** Rank is set by combining the
trade verdict with a separate execution permission. Only the verdict is shown, so
the order looks arbitrary. Showing the actual ranking basis fixes it.

**11. Several columns are copies of each other.** A trade can appear
"triple-confirmed" across three columns that are all restatements of one decision.
That's a false sense of corroboration. Remove the duplicate, and document which
columns are independent.

---

## Not ours to fix — needs other owners

**12. The veto data is empty for every row in the system** — not just formatted
wrongly, but never produced by the upstream stage that should generate it. The
one-line fix in item 3 makes the column honest; it doesn't create the data. This
needs the options-intelligence owner.

**13. The live-versus-paper data flag is absent** from the upstream file
altogether. Our documented rule says a trade is only eligible if prices were live.
**That rule currently cannot be checked.** Needs the morning-validation owner.

---

## What this audit did not establish

Stated plainly, because it bounds how much weight to put on the above.

- **One day's data.** All findings come from a single 96-row file from 31 July.
  The main finding is backed by a clean statistical split, but no finding has been
  confirmed across multiple days. We hold an archive of past files; running the
  same checks over them is a few hours' work and would settle this.
- **Two items are unexplained.** Some empty columns and one suspicious repeated
  value could not be traced, because of the reproducibility problem in item 2.
  These were reported as unresolved rather than guessed at — the right call.
- **No fix has been tested.** Nothing has been changed. Every effort estimate
  above is pre-implementation.

---

## Recommended sequence

1. **Clear items 1 and 2** — establish a known baseline. Nothing else is
   measurable until this is done.
2. **Run the existing checks across the file archive** — confirms which findings
   are systemic and which belong to one day. Few hours, high information value.
3. **Fix items 3, 4, 5, 6** — four small changes, batched, no decisions required.
4. **Decide on item 7** (do non-directional trades belong in this file?) and
   **item 8** (server-generated or hand-made?). These are business calls.
5. **Build the item 7 fix** once decided, and re-run the audit to confirm.
6. **Items 9, 10, 11** — clarity work, low urgency.
7. **Raise items 12 and 13** with the upstream owners.

Steps 1 to 3 could complete this week. Step 4 is a conversation, not a task.

---

## Bottom line

The audit found real problems, correctly identified, with clear causes. Most are
small. One is significant and turns on a strategy question rather than an
engineering one.

The most important thing in this document is not any single defect. It is that we
currently cannot reproduce what the system told us last week. Until that is fixed,
every other measurement — including whether our fixes worked — sits on unstable
ground.

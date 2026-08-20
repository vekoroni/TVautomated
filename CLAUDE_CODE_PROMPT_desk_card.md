# Claude Code build brief — AVSHUNTER Desk Card (`desk_card.py`)

## Objective

Build a **manual pre-execution decision aid**. It reads the macro JSONs and the morning-gate
output, and prints a one-screen desk card plus a per-candidate stop viability check.

It is **read-only intelligence**. It does not generate signals, does not authorise entry, and
does not modify any pipeline file.

---

## Environment

- Windows, Python 3, PowerShell
- Repo root: `C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\`
- **Macro JSONs**: `<root>\dropbox\macro\`
- **Run outputs**: `<root>\data\output\runs\{RUN_ID}\`
- Place the script at: `<root>\desk_card.py`
- Place the wrapper at: `<root>\Run-DeskCard.ps1`
- Resolve paths relative to the script location
- Accept `--macro-dir` and `--runs-dir` to override

### Output destination

`--csv` writes into the same `morning_validation` folder as the source it read:

```
validated mode  -> <root>\data\output\runs\{RUN_ID}\morning_validation\desk_card_{RUN_ID}.csv
candidates mode -> <root>\data\output\runs\{RUN_ID}\morning_validation\desk_card_PREP_{RUN_ID}.csv
```

Distinct filenames so a prep card and an execution card can never be confused on disk.
Never write or modify any other file in that directory.

RUN_ID format is `YYYYMMDD_HHMMSS` (e.g. `20260723_072618`). To find the latest run,
enumerate subdirectories of `<root>\data\output\runs\` and take the lexicographically
greatest — the format sorts chronologically.

---

## Inputs

All optional except where stated. **Missing files must degrade, never crash.**

| File | Location | Required |
|---|---|---|
| `macro_intelligence_latest.json` | `dropbox\macro\` | No — degrade if absent |
| `bond_macro_state.json` | `dropbox\macro\` | No |
| `avshunter_macro_enrichment_delta.json` | `dropbox\macro\` | No |
| morning **candidates** CSV | `data\output\runs\{RUN_ID}\morning_validation\` | No — enables prep mode |
| `morning_validated_trades_{RUN_ID}.csv` | `data\output\runs\{RUN_ID}\morning_validation\` | No — enables execution mode |

**Both CSVs live in the same `morning_validation` folder.** The candidates file is written by
the EOD run; the validated file is written by the morning gate. Nothing else is read.

**FILENAME NOT CONFIRMED — resolve before coding.** The candidates file is referred to as the
morning candidates file; its exact name has not been verified. Glob
`data\output\runs\*\morning_validation\*.csv`, list every distinct filename pattern found,
and report them before writing any code. Candidates seen in adjacent contexts include
`premarket_candidates_YYYYMMDD.csv` — **do not assume**. Report and ask.

Do not read `options_candidates_ranked.csv`, any `vanguard_signals*` file, or anything under
`dropbox\`. The two CSVs above plus the three macro JSONs are the complete input set.

**No file is hard-required.** If the macro JSONs are absent, print:

```
+==============================================================+
| MACRO CONTEXT UNAVAILABLE                                    |
| No sector permission, size multiplier or breakeven adj.      |
| Stop viability analysis only.                                |
+==============================================================+
```

and exit 2. The stop maths needs only IV, DTE and prices.

### Fields consumed

From `macro_intelligence_latest.json`:
```
report_date, regime_state, size_multiplier, trigger_required,
sector_lead[], sector_avoid[], vix_spot, vol_mode, macro_filter,
gex_regime_score, regime_probability,
horizon_routing.{1_5d,6_10d,11_20d}.{bias,size_multiplier,action,block_conditions[]}
```

From `bond_macro_state.json`:
```
auction.{auction_today, tenors_today[], tenors_window[], breakeven_adjustment_pct,
         spread_risk_flag, note}
yield_curve.{curve_state, spread_bps, regime_implication}
zn_futures.{zn_direction, rate_regime_signal}
credit_stress.{stress_level, ratio_zscore_20d, credit_warning, credit_alert}
composite.{macro_bond_score, trade_go, morning_manifest_flag, all_warnings[]}
```

From `avshunter_macro_enrichment_delta.json` — read **only** to display, never to act on:
```
source_freshness.{status, manual_review_required}
```
Print a single line noting it is `NONE_NEWS_TERMINAL_ONLY` context.

---

## Core logic

### 1. Stop viability (the reason this script exists)

Nothing in the macro JSONs tells you whether a stop sits inside the noise. This does.

Driftless barrier maths, reflection principle:

```
sd_move_pct   = iv_pct * sqrt(horizon_days / 252)
coinflip_pct  = 0.674 * sd_move_pct          # 50% chance of being touched
p_touch       = 2 * (1 - Phi(stop_pct / sd_move_pct))
```

Use `scipy.stats.norm.cdf`, or `0.5*(1+math.erf(x/sqrt(2)))` to avoid the scipy dependency.

Reference values — **use these as unit-test assertions**:

| barrier | P(touch) |
|---|---|
| 0.50 SD | 61.7% |
| 0.674 SD | 50.0% |
| 1.00 SD | 31.7% |
| 1.50 SD | 13.4% |
| 2.00 SD | 4.6% |

Verdict bands:
- `p_touch >= 0.50` → `INSIDE_NOISE`
- `0.35 <= p_touch < 0.50` → `MARGINAL`
- `p_touch < 0.35` → `OK`

State in the output that this assumes zero drift and normal tails, so real touch
probability runs slightly **higher**. The figure is a floor.

### 2. Sector permission

Map each candidate's sector or ETF to `sector_lead` / `sector_avoid`.
Emit `LEAD`, `AVOID`, or `NEUTRAL`. **Never block on this** — it is a handicap, not a gate.

### 3. Breakeven hurdle

If `breakeven_adjustment_pct > 0`, print it prominently and flag any candidate whose
expected move (from the signal target) is within that percentage of its breakeven.

### 4. Horizon routing

Match each candidate's DTE or intended horizon to the `1_5d` / `6_10d` / `11_20d` bucket and
surface that bucket's `size_multiplier`, `action` and `block_conditions`.

### 5. Size multiplier — SURFACE THE AMBIGUITY, DO NOT RESOLVE IT

`macro_intelligence_latest.json` carries a top-level `size_multiplier` (0.7) **and** a
per-horizon `size_multiplier` (0.7 / 0.7 / 0.6). It is not established whether these
compound or replace. The operator's own convention records 0.63x for 1–10d and 0.50x for
11–20d, which matches neither reading.

Print **both** interpretations side by side and a `SIZE_AMBIGUITY: UNRESOLVED` warning:

```
Size (replace) : 0.70x
Size (compound): 0.49x
⚠ SIZE_AMBIGUITY UNRESOLVED — differs by 1.43x. Confirm against the writing code.
```

Do not pick one. Do not average them.

---

## Output

### Mode A — desk card (no arguments)

Plain text to stdout, under 40 lines. Sections: regime header, sector lead/avoid,
size block (with the ambiguity warning), auction and breakeven, bond composite, credit,
horizon routing table, data-freshness warnings.

### Mode B — single candidate

```
python desk_card.py --iv 42 --days 10 --stop 4.0 [--ticker XLE]
```
Prints the desk card plus one stop-check line.

### Mode C — batch, two sources

```
python desk_card.py --batch                            # auto-detect
python desk_card.py --batch --source candidates        # EOD prep
python desk_card.py --batch --source validated         # post-gate execution
python desk_card.py --batch --source validated --top 10 # limit FLAG section to 10 rows
```

`--top N` (default 25) applies only to the FLAG section of validated mode. The GO section
is never truncated. Has no effect in candidates mode (no gate verdict, no sections).

Both source files live in `data\output\runs\{RUN_ID}\morning_validation\`.

| Source | File | Written by | Price basis | Authority |
|---|---|---|---|---|
| `candidates` | morning candidates CSV *(name to confirm)* | EOD run | EOD close | **None — prep** |
| `validated` | `morning_validated_trades_{RUN_ID}.csv` | Morning gate | Live | Post-gate |

**Auto-detect:** if `morning_validated_trades_*.csv` exists in the latest run folder, use
`validated`; otherwise use `candidates`. Always print which was chosen and why.

### Validated mode — columns CONFIRMED against the real file

`morning_gate_verdict` takes three values in this file: `GO`, `FLAG`, `BLOCK`.

- `GO` — gate-approved. Full authority for execution timing/sizing decisions.
- `FLAG` — gate flagged the row for **manual human validation**. Not authorised, not
  rejected — the primary audience for this card's execution-mode output. The point is to
  help the operator work through the validation backlog, not to hide it.
- `BLOCK` — gate rejected. **Excluded entirely.** The card never overrides a BLOCK.

Filter:
```python
mask = df["morning_gate_verdict"].isin(["GO", "FLAG"])
```

Within that mask, GO and FLAG render as **two separate sections, never interleaved**:

- **GO section** — every GO row, no truncation, no limit.
- **FLAG section** — header `FLAG - YOUR VALIDATION REQUIRED`, every row prefixed `[FLAG]`,
  limited to `--top N` rows (default 25). Sort: lead-sector rows first, then by `P(touch)`
  ascending (worst stop viability surfaces first within each sector tier). If macro context
  is unavailable (no `sector_lead` data), sort by `P(touch)` ascending only.

**FLAG rows are not authorised. Never print the string `GO` inside a FLAG row or section.**

`live_data_mode` does NOT exist in this file. Do not reference it. Derive the basis from
column presence:

```python
if "live_contract_iv" in df.columns and pd.notna(row["live_contract_iv"]) and row["live_contract_iv"] > 0:
    basis, iv = "LIVE", row["live_contract_iv"]
else:
    basis, iv = "EOD", row["contract_iv"]
```

| Purpose | Column | Notes |
|---|---|---|
| Ticker | `ticker` | lowercase in this file |
| Gate verdict | `morning_gate_verdict` | values include `GO` |
| DTE | `dte` | float, e.g. `29.0` |
| IV (live) | `live_contract_iv` | decimal, e.g. `0.4451` |
| IV (EOD) | `contract_iv` | decimal, e.g. `0.4347` |
| Stop level | `exit_stop_price` | **price**, not a percentage |
| Price (live) | `live_price` | |
| Price (EOD) | `signal_price` | |

**Do NOT use:**
- `iv_current` — all NaN in the verified run
- `iv_rank` — a 0–100 percentile, NOT a volatility. Feeding it to `IV × sqrt(days/252)`
  produces a plausible-looking number that means nothing.

Stop percentage is derived, not read:
```python
price = row["live_price"] if basis == "LIVE" else row["signal_price"]
stop_pct = abs(price - row["exit_stop_price"]) / price * 100
```

**Flag this:** `exit_stop_price` was identical to `invalidation_eod` in every row inspected.
If that holds across the file, print once:
```
NOTE: exit_stop_price == invalidation_eod in {n}/{total} rows — stop is not
      independently computed from the invalidation level.
```

### Per-section summary lines

Printed once per section (GO, FLAG):

```
GO   stop viability: {n} OK, {n} MARGINAL, {n} INSIDE_NOISE
FLAG stop viability: {n} OK, {n} MARGINAL, {n} INSIDE_NOISE
```

### Systemic INSIDE_NOISE warning — GO rows only

If more than 30% of **GO** rows verdict as `INSIDE_NOISE`, print a warning that this points
to a pipeline issue, not candidate variance — GO rows are already gate-approved, so a high
inside-noise rate there means something upstream is wrong:

```
⚠ SYSTEMIC: {pct}% of GO rows are INSIDE_NOISE — check upstream stop-sizing logic.
```

Do **not** compute this warning against FLAG rows. FLAG variance is expected — those rows
haven't been through human review yet.

### Candidates mode — columns NOT confirmed

**Inspect the header before mapping anything.** Do not assume the candidates file shares the
validated file's schema — it is written by a different pipeline stage.

Report which columns are present for: ticker (check both `ticker` and `Ticker`), IV, DTE,
stop level, and price. If any of those five is absent, say which and stop — a stop-viability
card without IV, DTE and a stop level cannot be computed.

There is no gate verdict in this file. **Do not invent one and do not filter on one.** Every
row is a candidate, none is authorised.

### AUTHORITY BANNER — mandatory, non-negotiable

Print at both the top and the bottom of batch output.

Candidates mode:
```
+==============================================================+
| SOURCE: <filename>   (EOD PREP)                              |
| PRE-TRADE INTELLIGENCE ONLY - NOT ENTRY AUTHORISATION        |
| The morning gate has not run. No row here is authorised.     |
| Prices are EOD closes; stop distances will shift by open.    |
+==============================================================+
```

Validated mode:
```
+==============================================================+
| SOURCE: morning_validated_trades_20260723_072618.csv         |
| GO 281 | FLAG 764 (validation required) | BLOCK 23           |
| Price basis: {n} LIVE, {n} EOD                                |
+==============================================================+
```

In candidates mode, additionally:
- Prefix every candidate row with `[PREP]`
- Name the output `desk_card_PREP_{RUN_ID}.csv`, never `desk_card_{RUN_ID}.csv`
- Never print the word `GO` anywhere in the output

Rationale: both files live in the same folder with similar names. An operator glancing at a
prep card must not mistake it for an authorised list.

### Overnight drift (candidates mode)

EOD stop distances are computed from the close; spot moves overnight, so a stop reading `OK`
at EOD can read `INSIDE_NOISE` at the open. Print in candidates mode:

```
Stop verdicts are provisional. Re-run with --source validated after the gate.
```

Where both a prep card and a validated card exist for the same RUN_ID, print verdict drift:

```
VERDICT DRIFT since prep:  XLE OK -> MARGINAL   XLU MARGINAL -> INSIDE_NOISE
```

**Output columns:** ticker, sector flag, DTE bucket, basis, IV%, 1SD%, coin-flip line%,
stop%, P(touch), verdict.

Add `--csv` to write the card. Text output is the default.

### Exit codes
`0` normal · `1` unreadable/corrupt input · `2` ran with degraded inputs (macro absent)

---

## Known gotchas — these have bitten this codebase before

1. **Ticker case.** `avshunter_signals_*.csv` uses `Ticker` (capital T). Every other file uses
   lowercase `ticker`. Handle both explicitly when joining.
2. **Percentage scale.** Confidence and win-rate fields arrive on a 0–100 scale. IV may arrive
   as either a decimal (0.42) or a percentage (42). **Detect and normalise**: if the value is
   below 3.0, treat it as a decimal and multiply by 100.
3. **Duplicate index rows.** When using `.loc[]` for per-ticker lookups, guard with
   `isinstance(row, pd.DataFrame)` then `.iloc[0]`.
4. **Guard every field access.** Use `[c for c in desired if c in df.columns]`. Never assume a
   column exists.
5. **Gamma flip levels are unverified.** `block_conditions` reference SPY 720 / QQQ 677. These
   equal the lowest strike in each sampled chain and cumulative GEX never crosses zero, so the
   flip calculation is likely defaulting to `min(strike)`. Print the block condition verbatim
   but append `[LEVELS UNVERIFIED]`.
6. **Stale data — two separate checks.**
   a. If any JSON's `report_date` or `as_of_utc` is more than 2 calendar days old, print a
      `STALE INPUT` banner at the top.
   b. `macro_intelligence_latest.json` is a rolling latest with no RUN_ID; the validated CSV
      carries one. Compare the macro `report_date` against the date portion of the validated
      RUN_ID. A few hours apart is normal (different pipeline stages). **More than one
      calendar day apart means the card would apply yesterday's regime to today's
      candidates** — raise `STALE INPUT` and name both dates.

---

## Non-goals — do not build these

- No trade recommendations, no strike selection, no contract counts
- No writes to any existing pipeline file
- No network calls — read local files only
- No override of `morning_gate_verdict`; `BLOCK` stays excluded from batch mode entirely.
  `FLAG` is included (it is the primary audience for validated mode) but is always rendered
  in its own clearly-marked, unauthorised section — never merged with GO
- No new dependencies beyond `pandas` and the standard library

---

## Acceptance criteria

- [ ] Runs with only `macro_intelligence_latest.json` present
- [ ] Runs with all five inputs present
- [ ] Runs with a corrupt JSON without a traceback — prints the failure, exits 2
- [ ] Unit tests assert all five P(touch) reference values to 0.1%
- [ ] Unit test: IV supplied as 0.42 and as 42 produce identical output
- [ ] Validated mode includes GO and FLAG rows; excludes every BLOCK row entirely
- [ ] GO and FLAG render as separate sections, never interleaved
- [ ] FLAG section header reads `FLAG - YOUR VALIDATION REQUIRED`
- [ ] Every FLAG row is prefixed `[FLAG]`; the string `GO` never appears in a FLAG row or
      the FLAG section header/summary
- [ ] GO section shows all GO rows with no truncation
- [ ] FLAG section is limited to `--top N` (default 25), sorted lead-sector-first then
      `P(touch)` ascending (or `P(touch)` ascending only if macro context is unavailable)
- [ ] Banner prints all three counts: `GO {n} | FLAG {n} (validation required) | BLOCK {n}`
- [ ] Per-section stop-viability summary line printed for both GO and FLAG
- [ ] Systemic `INSIDE_NOISE` warning (>30%) is computed on GO rows only, never on FLAG
- [ ] No reference to `live_data_mode` anywhere in the code
- [ ] `iv_rank` is never used in the SD-move calculation
- [ ] IV of `0.4451` and `44.51` produce identical output (decimal detection)
- [ ] `stop_pct` derived from `exit_stop_price` and the basis-appropriate price
- [ ] Price basis (LIVE/EOD) printed per row
- [ ] Runs with the macro directory absent — prints MACRO CONTEXT UNAVAILABLE, exits 2
- [ ] Latest RUN_ID found by lexicographic sort of `data/output/runs/` subdirectories
- [ ] `--source candidates` and `--source validated` both work
- [ ] Candidates mode never prints the string `GO`
- [ ] Candidates mode prefixes every row with `[PREP]`
- [ ] Candidates writes `desk_card_PREP_{RUN_ID}.csv`, validated writes `desk_card_{RUN_ID}.csv`
- [ ] Authority banner appears top AND bottom in both modes
- [ ] Verdict drift printed when both cards exist for one RUN_ID
- [ ] Both cards write into `data/output/runs/{RUN_ID}/morning_validation/`
- [ ] No file other than the two desk_card CSVs is ever written or modified
- [ ] Macro `report_date` vs validated RUN_ID date differ by >1 day → STALE INPUT banner
- [ ] Size ambiguity warning appears whenever both multipliers are present
- [ ] Desk card fits one screen (≤40 lines)
- [ ] Completes in under 2 seconds

---

## PowerShell integration

### Direct

```powershell
Set-Location "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"
python .\desk_card.py
python .\desk_card.py --iv 42 --days 10 --stop 4.0
python .\desk_card.py --batch
```

### Wrapper — create `<root>\Run-DeskCard.ps1`

```powershell
param(
    [double]$IV, [int]$Days, [double]$Stop, [int]$Top,
    [switch]$Batch, [switch]$Csv,
    [ValidateSet("candidates","validated")][string]$Source
)
$ErrorActionPreference = "Stop"
Set-Location "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"

$args = @()
if ($Batch)  { $args += "--batch" }
if ($Source) { $args += @("--source", $Source) }
if ($Top)    { $args += @("--top", $Top) }
if ($Csv)    { $args += "--csv" }
if ($IV)     { $args += @("--iv", $IV, "--days", $Days, "--stop", $Stop) }

python .\desk_card.py @args
if ($LASTEXITCODE -eq 1) { Write-Host "DESK CARD FAILED - macro JSON missing" -ForegroundColor Red }
if ($LASTEXITCODE -eq 2) { Write-Host "DESK CARD DEGRADED - some inputs missing" -ForegroundColor Yellow }
```

Usage:
```powershell
.\Run-DeskCard.ps1                                      # desk card only
.\Run-DeskCard.ps1 -IV 42 -Days 10 -Stop 4.0            # single stop check
.\Run-DeskCard.ps1 -Batch -Source candidates -Csv       # EOD prep run
.\Run-DeskCard.ps1 -Batch -Source validated -Csv        # post-gate run
```

If execution policy blocks it:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

---

## When to run

All times **US Eastern**. Convert to local.

### Two scheduled runs

| # | When | Command | Purpose | Authority |
|---|---|---|---|---|
| 1 | Evening, after EOD run writes the candidates CSV | `.\Run-DeskCard.ps1 -Batch -Source candidates -Csv` | Prep — which stops are viable, which sectors permitted | **None** |
| 2 | Morning, after gate completes, before 09:30 ET | `.\Run-DeskCard.ps1 -Batch -Source validated -Csv` | Execution — constraints and stop viability for GO rows | Post-gate |

**Run 1** narrows the field the night before. Candidates whose stops already sit inside the
noise band can be discarded before the morning. Not an authorised list — prices are EOD
closes and the gate has not run.

**Run 2** is the run that matters. It sits between the gate and the fill: the gate decides
*whether*, the card informs *how much, which strike, what time*. Where a prep card exists for
the same RUN_ID, run 2 prints verdict drift — candidates whose stop viability changed
overnight need their stop or size revisited before the fill.

### Per-candidate, at the point of sizing

```powershell
.\Run-DeskCard.ps1 -IV 42 -Days 10 -Stop 4.0
```

Run before committing to a stop. If the verdict is `INSIDE_NOISE`, the options are: widen the
stop and cut size, shorten the horizon, or skip. Do not proceed on a coin-flip stop.

### Auction-day re-check

When `auction.auction_today` is true, spreads widen into the auction (Treasury auctions
typically settle around 13:00 ET — confirm against the actual schedule). For rate-sensitive
candidates (XLF, XLRE, XLU, long-duration names), fill in the morning session or after the
result, not into the window. Re-run the card if execution slips past midday.

### Evening — optional planning run

After the EOD pipeline and macro overlay refresh, run without arguments to see the next
session's constraints. Planning only; the morning run is authoritative because spot has moved.

### Do not run

- Before the macro overlay has refreshed — you will read yesterday's regime
- As an automated gate. This is a decision aid a human reads. It has no authority.
- **Never execute from a candidates-mode card.** It is prep. The gate has not run and no row
  on it is authorised, however good the numbers look. Both files live in the same folder —
  the `[PREP]` prefix and the `_PREP_` filename are the only things separating them.

### Optional Task Scheduler registration

```powershell
$root = "C:\Users\ACKVerissimo\AVSHUNTER-Intelligence"

# Run 1 - EOD prep. Time must be AFTER the EOD run writes the candidates CSV.
$prepAction  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-File $root\Run-DeskCard.ps1 -Batch -Source candidates -Csv"
$prepTrigger = New-ScheduledTaskTrigger -Daily -At "6:30PM"
Register-ScheduledTask -TaskName "AVSHUNTER Desk Card - EOD Prep" `
    -Action $prepAction -Trigger $prepTrigger

# Run 2 - post-gate. Time must be AFTER the morning gate completes.
$gateAction  = New-ScheduledTaskAction -Execute "powershell.exe" `
    -Argument "-File $root\Run-DeskCard.ps1 -Batch -Source validated -Csv"
$gateTrigger = New-ScheduledTaskTrigger -Daily -At "8:45AM"
Register-ScheduledTask -TaskName "AVSHUNTER Desk Card - Post Gate" `
    -Action $gateAction -Trigger $gateTrigger
```

Adjust `8:45AM` to sit after the morning gate finishes in local time. Scheduling only produces
the card — a human still reads it.

# BEH-001 Amendment A2 — scope correction and constraint register (1 Oct 2026)

Parent design: `AVS_SD_BEH_001_BEHAVIOURAL_SIGNAL_CANDIDATES_20261001.md`.

**Governing principle (ACK):** the pipeline is an assembly line. Each stage adds its own value and passes the product on, with its findings attached. A stage must not impose a constraint it does not own. A constraint introduced early travels to the end of production and defines the finished product. A constraint is legitimate only at the stage that owns it.

---

## Part 1 — Approved by ACK on 1 Oct 2026

| ID | Item | Status |
|---|---|---|
| A2-1 | **Uncapped evaluation.** Each directed candidate is followed on daily closes to its own trigger or invalidation. There is no 20-session cut-off; the research limit is 250 sessions. Time to resolution is recorded as an output. Detected candidates are compared with a random walk over the same distances. Activated candidates are compared with 50% (one risk unit before invalidation), with the opposite direction reported to expose drift. | APPROVED. Running offline (`Enhancements/direction_evidence/beh001_uncapped.py`). |
| A2-2 | **Weekly and monthly timeframes** added to the BEH-001 ladder. They are built from completed daily bars and run by the same engine. Too little history gives `NOT_EVALUATED`, never a failure. Ladder: monthly → weekly → daily → 60m → 15m → 5m. | APPROVED. Built; tests green. |

---

## Part 2 — Constraints removed inside BEH-001 scope (corrections of my build; no ACK decision needed)

These were defects that I introduced while fitting the engine into the old code path. They were not requirements.

| ID | Constraint I introduced | Correction (built, tested) |
|---|---|---|
| R-01 | The engine ran after Discovery's option-motivated eligibility filters (price, ADV, ATR), so ineligible tickers were never read | Every ticker with valid bars is read. Discovery's outcome, reason and tier travel with each candidate as attributes, not as a gate. |
| R-02 | Candidates were kept only for Discovery survivors | Candidates are published for every ticker: survivors, tier and horizon drops, eligibility drops, and per-ticker errors where the engine can still run. |
| R-03 | Timeframes stopped at daily | Weekly and monthly added (A2-2). |
| R-04 | The evaluation entered at the daily close and capped at 20 sessions | Uncapped evaluation (A2-1). |
| R-05 | Missing intraday data could have blocked a ticker | Degrades to `NOT_EVALUATED` with a reason; the other timeframes still run (ACK amendment, earlier today). |

---

## Part 3 — Constraint register: proposals for ACK decision, one at a time

Each item changes a stage outside BEH-001, so none is built until approved. "Owner" is the stage that legitimately owns the constraint.

| ID | Constraint today | Where it sits | Legitimate owner | Proposed fix | Impact to check before building | Decision |
|---|---|---|---|---|---|---|
| **C-01** | Option-motivated eligibility (price 5–500, ADV ≥ $2.5M, ATR ≥ $0.40, ATR ≥ 1%) decides which tickers leave Discovery | Discovery, stage 1 | Options (instrument liquidity and tradeability) | Discovery's survivor set is decided by behaviour. Liquidity becomes an Options-stage contract check, recorded per candidate. | More tickers flow to Vanguard and Options, so more provider requests and longer run time. The `validate_quality` ratios (DEC-6) change. Project both with the replay before switching. | ☐ Approve ☐ Reject |
| **C-02** | Tier-4 composite drop and horizon-bucket drop (`NO_SIGNAL_AT_ANY_HORIZON`) | Discovery | None; these are scores and labels, not facts | Remove both as gates. Keep composite and tier for display. A ticker survives when it has at least one directed candidate (or a monitoring observation, if you want those to travel too). | Survivor count changes; R-4 population projection required. | ☐ Approve ☐ Reject |
| **C-03** | One direction per ticker, taken from the daily reading (§7 handoff) | Discovery → C5 → Options | C6 expression search (per candidate) | Downstream receives the full candidate set. Options interrogates each directed candidate (any timeframe) for a fitting contract. The per-ticker side remains only as a summary field. | Largest change: C5 is one row per ticker, and Options picks one side per ticker today. Needs its own small design (candidate identity across C5, Options, EOD, Lab). | ☐ Approve ☐ Reject |
| **C-04** | Fixed 1–20 session thesis window (ACK D2, signed TEV-001 §5.2) | C5 and downstream | Each candidate's own evidence | Each candidate carries a measured time-to-resolution distribution from comparable history (A2-1 produces the first estimates). The option stage buys runway from it. | Amends ACK D2 and TEV-001. Depends on A2-1 results. | ☐ Approve ☐ Reject |
| **C-05** | Vanguard statistics only at 5, 10 and 20 sessions | Vanguard | Vanguard, as horizon-free evidence | Publish first-passage and time-to-event statistics per candidate geometry, with no fixed horizons (the v8 work already planned under DIR-002). | Requires the v8 label build. Display only until validated. | ☐ Approve ☐ Reject |
| **C-06** | Expiry chosen from a DTE matrix keyed by tier and phase | Options | Options, from the thesis time distribution | Expiry runway = candidate time-to-resolution (e.g. 80th percentile) plus the configured buffer. No tier or phase lookup. | Depends on C-04. Changes contract selection; outcome comparison needed. | ☐ Approve ☐ Reject |
| **C-07** | Vanguard and Options process only Discovery survivors | Orchestrator handoff | Follows C-01 and C-02 | Resolved automatically if C-01/C-02 are approved. Otherwise unchanged. | Run time. | ☐ Approve ☐ Reject |

**Suggested order if approved:** C-02 → C-01 (population first, measured with the replay), then C-04 → C-06 (time), then C-03 (candidate-level handoff; its own design), and C-05 with the Vanguard v8 work. C-07 follows C-01/C-02.

**Production during all of this:** direction stays on `legacy_rollback`. BEH-001 publishes its full candidate set alongside the existing outputs. Nothing downstream changes until an item above is approved, built, tested and replayed.

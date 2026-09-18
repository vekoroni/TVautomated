# Roll at the last exit session — first measurement (ledger trial 7, 18 Sep 2026)

Research variant, no decision authority (G1–G4). Code: `run_ledger.py` (`roll_candidates`, `follow_roll`,
`roll_returns`, `roll_summary`); record: `ledger.jsonl` trial 7. Rules: D1(a) + D2(a) as shipped (trial 6).

**Rule tested.** When a contract reaches its last exit session with the thesis still open (no stop hit, no target
reached) and sessions left in the thesis window, the model re-values every later expiry in the same direction at
today's quote over the remaining window. It uses the issue-time rules: moneyness ≤ 5% out of the money, spread
≤ 10%, and the value model capped at each contract's own last exit session. The best contract by cautious value is
chosen.

- **roll_if_worth_buying:** roll only if the chosen contract's central value at today's ask is above 0.
- **roll_always:** roll to the chosen contract regardless of its value (the sensitivity bound).

Every roll pays for itself: the old contract is sold at the bid and the new one bought at the ask with the proceeds.
The thesis keeps its original stop, target and window; per C4, the window is not restarted.

| Policy | Theses at last exit session (eligible / tickets) | Rolled | Paired difference vs exit, timed fills (eligible / tickets) |
|---|---|---|---|
| roll_if_worth_buying | 71 / 6 | 3 / 0 | +0.04 pt / 0.0 pt |
| roll_always | 71 / 6 | 52 / 4 | −1.7 pt / −1.1 pt |

Of the 71 eligible theses that reached their last exit session:

- 49 were **not worth buying** at the replacement premium;
- 19 had **no later contract** that passed the rules, because the chain holds 8–43 days to expiry;
- 3 rolled.

**Verdict: not yet measurable, so no change.**

- 51 of the 52 always-roll legs are still open. They are marked at the 17 Sep bid, not closed, because the frozen set
  ends 16 Sep and the price history ends 17 Sep.
- The sign so far is that rolling without a value test costs the round-trip spread. The value test rarely finds a
  replacement worth buying, and when it does, the effect is too small to measure.
- The variant is recorded in every future ledger run under `exit_policy_roll`. It will be re-read as forward sessions
  close the open legs.

# Phase 6 pre-registration: short holds (S), written before any result (9 Oct 2026)

**Approved:** ACK, "yes start the short-hold test". **Why:** the exit study showed the value is lost to entry and time
decay (median option peak 0.94 × entry). ACK prefers day and swing holds (7 Oct). Question: does selling after a few
sessions keep more than holding for weeks?

**Data and model:** identical to `PHASE6_EXITS_AND_CHEAP_VOL_PREREG_20261009.md`. The same X1 trades (entry Friday at
the ask), the same Black-Scholes daily path (the contract's own entry IV held, r = q = 0, sellable = model × (1 − half
the entry spread)), the same test period (2025-07-04 to 2026-08-21), block bootstrap, Holm and halves rules.

**Rules:** sell at the sellable model value at the close of the h-th session after entry, for h = 1, 2, 3, 5. If the
X1 trade already exited earlier (invalidation), the X1 exit stands.

**Family S (setup trades, ATM, test period, paired on the same trades):**
- **S-h:** mean(return under S-h − return under the modelled X1 exit) > 0, for h = 1, 2, 3, 5. Both sides are priced by
  the same model, so the model's bias (median 0.96–0.97 of actual bids) cancels.

**Reported beside it (descriptive):**
- each S-h against the actual X1 bid;
- the absolute mean return, hit rate and share ≥ +100% under each rule;
- 0.35 delta, random entries (PLACEBO), and the combination with the volatility finding (CHEAP vs RICH) at the
  best h.

**Known limits:** the same as the exit study. IV is held, so the IV crush or spike around a move is not modelled; a
short hold sells at a model value, not an observed bid. Descriptive of these rules on this history; no authority.

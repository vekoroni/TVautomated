# AVS-ARCH-LB-001 — proposed register rows, reconciled

21 November 2026. Read-only on the register. `fix_register.csv` is not edited; ACK approves any merge.

ACK asked for the 35 proposed rows to be reconciled against the existing fixes, since some may not be needed. Detail per item is in `register_entries_reconciled.csv`. The first proposal, `register_entries_proposal.csv`, is left as written.

## Result: 17 rows are needed, 18 are not

| Disposition | Count | Items |
|---|---|---|
| Keep as a new row | 13 | V-06, G2, G3, G7b, W-02, D1, E1, R-01, L-01, L-02, F1, CF-01, CF-04 |
| Keep, decided today | 2 | CF-02 (retire), CF-03 (rewrite) |
| Keep, parked | 1 | A-01 |
| Keep as closed, so it is not proposed again | 1 | R-02 |
| Merged into another row | 11 | V-07, G1, G4, G6, G7c, W-01, D1a, D1b, L-03, CF-05, and G5's scoring into L-01 and L-02 |
| Not needed as a row | 7 | V-01, V-02, V-03, V-04, V-05, W-03, G7a |

G5 is counted once, under merged. CF-06 and D1c were already left out of the first proposal.

## Why 18 are not needed

- **Five are features that already exist** (V-01 to V-05). They are live on the board. A register row is for something to fix. One change-log entry records them.
- **Three are parts of the card record** (D1a, D1b, G6) and one is how the logs are read back (L-03). ACK's own wording made them parts of D1 and of the logs.
- **Four duplicate rows the register already holds:**
  - G1: A16-04, N17-07, N17-11 and the pipeline register.
  - G7c: N17-01.
  - W-01: N17-07.
  - CF-05: N7, R14-14, N17-16, W16-04.
- **Two are absorbed by the card record and the feed** (G4, V-07).
- **One is already on the board** (G7a: a VIX and breadth read exists at `board_page_v19.html:1357-1367`).
- **One is a sequencing note** (W-03).
- **One is closed by ACK's decision** (G5: ledger scoring retired for now).

## ACK's decisions of 21 November, as recorded here

| Item | Decision |
|---|---|
| G2 | Lab order restored; focus names marked by a flag column |
| G5 | Ledger scoring retired for now. Learning leads from the board, which sees identified trades and executed trades |
| A-01 | Parked. To be defined after the end-of-week review next week |
| CF-02 | Strategy layer S1–S6 retired. Lane B gives the mining that is needed |
| CF-03 | Rewrite the X17 test for the 11 November liquidity tiers |

## The ID collisions

D1, G1, G2, G3, G4 and G6 already exist in the register with other meanings (time-value monetisability, path engine, provider Greeks, shared American engine and others). After reconciliation only three of the colliding IDs still need a row: **D1, G2 and G3**. They carry the `LB-` prefix. G1, G4 and G6 are merged and need no row, so their collisions go away.

## Proposed changes to rows the register already holds

For ACK to approve. Nothing is changed by this file.

| Row | Proposed change | Why |
|---|---|---|
| W4, W16-12, N8 | Mark Parked (ACK 21 Nov) | They are ledger scoring, which is retired for now |
| X17-02 | Correct its closure evidence | It cites a test that asserts a rule no longer in the code |
| N17-01 | Add commits `1323f35` and `bb96786`; state Built, not yet run on a session | The context refresh was built on 21 Nov |
| N7, R14-14, N17-16, W16-04 | Add commit `1323f35` as a partial build | The ticket list flags a fill with no resting exit and a quantity mismatch |
| N17-07 | Widen to the board's card-row tier | W-01 is the same need |
| A16-07, N17-15, R14-14, N6 | Note "superseded in part by LB-D1" | The card record carries the same checks and fields |

A16-03 (daily capture for every carded contract) and G8 (score predicted bids against option closes) are left alone. They overlap G5 in purpose but belong to the pipeline, and ACK's decision was about ledger scoring in Lane B.

## What this reconciliation did not do

- It did not re-verify the 37 evidence cells of the validation. It takes them as written.
- It did not open the board database, so V-05's row count and the October rows in G7b rest on the exported page and the saved decision files.
- The `LB-` prefix is the validation's suggestion. ACK has not confirmed it.

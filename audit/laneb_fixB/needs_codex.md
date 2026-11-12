# Lane B Fix B: what needs Codex (or ACK) outside Lane B's files

Written 12 Nov 2026 by Claude Code. Nothing here blocked the build. Each line has the fallback Lane B uses today.
Checked against Lab revision `f70092078e3f4a548955a08cbec131f6`, run `20261111_231951`.

## 1. Lab fields Lane B depends on and the Lab does not publish

| # | Need | Where it would go | Lane B fallback today | Fix-list item |
|---|---|---|---|---|
| 1 | `monetisation_n_q50`, `monetisation_n_q80`, `monetisation_threshold` | `card_fields` | Columns blank, `monetisation_state = NOT_PUBLISHED`; the window flag runs on `anticipated_sessions_q50`, labelled `PROXY_Q50` (all 2,132 rows) | D1 |
| 2 | Contract alternatives in Lab order, with quote, OI, sessions to expiry, time fit | Card or evidence; any column whose name starts `contract_alternative` is picked up by `check_triage.py` | A triage contract other than `contract_symbol` is a WARN. 26 of today's 90 triaged rows | A8 |
| 3 | One repair state per row | `option_risk` evidence | `lb_repair_conflict` = status `CONTRACT_REPAIR_REQUIRED` with action `NOT_REQUIRED`. 455 of 2,132 hand-off rows | A4 |
| 4 | Decision session date | Manifest | First XNYS session after `bar_data_asof` (calendar: `avshunter.shared.xnys_calendar`), cross-checked with `timing_details.expiry_reference_date`. Agreed on this run | — |
| 5 | Publication stage (Evening or Morning) and Morning-completed time | Manifest | Stage from `source_receipt.watch_inputs`; Morning completion from the file time of `morning_validation\morning_validated_trades_<run>.csv` | — |
| 6 | Cluster field | Card | `lb_group` = `sector_etf` + direction | B3 |

## 2. Lab behaviour seen while building (information for A items)

| # | Seen | Count | Item |
|---|---|---|---|
| 1 | Same field stored as a number on some rows and as text on others (`planned_hold_sessions` "52.0", `anticipated_sessions_q50` 22; `anticipated_level` 107.9199 on one row, "8.5308" on another). Blank and null both occur for "not available" | Whole book | A7 |
| 2 | Hand-off rows with no selected contract | 88 of 2,132 | A1 / A8 |
| 3 | Time fit: contract expires before the median arrival time | 1,005 of 2,132 | A1 |
| 4 | Time fit: contract expires before q80 | 481 of 2,132 | A1 |
| 5 | Saved quote fails the 11 Nov tier on open interest (under 100 or not recorded) | 1,045 of 2,132 | A1 / A8 |
| 6 | Saved quote fails on spread over 20% of mid | 616 of 2,132 | A5 |
| 7 | No arrival time published (window not assessable) | 42 of 2,132 | A7 |
| 8 | Source receipt issue `NAN:MATCHING_VALIDATION_EVENT_NOT_FOUND` | 1 | A11 |
| 9 | The Lab API answers a single card or evidence call in about 2.5 seconds (125 calls took 5 minutes) | — | — |
| 10 | Five review databases for one run in the projection folder (132 MB each) | 5 | — |

## 3. A test outside Lane B's files that now fails

`tests\test_x17_check_triage_spread_gate.py` (X17-02, 17 Oct) pins the 16 Oct rule "a trade_contract over 25% of mid is a WARN". Fix B4 removes that rule on ACK's instruction, so 4 of its 5 tests fail.

- I have not changed it: `tests\` is outside the files this brief lets me touch.
- The replacement rule is tested in `data\scratch\workaround\test_laneb_check_triage.py` (9 tests, all pass).
- Needed: ACK to say the X17 test is retired or rewritten for the 11 Nov tiers, and who does it.

## 4. Lane B scripts that still read the old hand-off layout (not in this brief)

They are not run on a Lab hand-off; `avs_day.ps1` says so when it skips them. They work unchanged with `-LegacyHandoff`.

| Script | Reads | Effect in Lab mode |
|---|---|---|
| `strategy_layer.py` (S1–S6, S6 replay) | `<TICKER>_<SIDE>.json`, `best_contract`, `half_target` | Not run; cards have no S1–S6 row |
| `compare_split_handoffs.py` | Two `split_*` folders | Not run |
| `preclose_trigger_scan.py` | The decision ledger (`half_target`, `atr`) | Runs on the ledger, which is still built; its half target is the ledger's, not the Lab's |
| `track_outcomes.py` | The decision ledger | Runs on the ledger |
| `quickkill.py`, `capture_score.py` | `best_contract`, 25% spread | Not touched |

Decision for ACK: adapt these to the Lab hand-off as a follow-up, or retire them.

# Lab hand-off switch-on: triage prompt update and run sheet

Written 13 Nov 2026 by Claude Code for ACK, who decided that day to include the Lab hand-off in the next Evening run (latest Sunday 15 Nov). Source: `audit\laneb_fixB\triage_interface.md`.

Nothing has been switched: `day_settings.json` still says `handoff_source = LEGACY`, and I have not edited the triage task. The task's prompt is not stored on this computer, so part 1 is a block to paste into it, not a full replacement.

## 1. Paste this into the triage task prompt

Put it after the step that reads `today_context.json`. Where it disagrees with older text in the prompt, this block wins.

```text
LAB HAND-OFF (from 13 Nov 2026). Read handoff_source in data\scratch\workaround\today_context.json.
If it is LEGACY, ignore this block and work as before.
If it is LAB, follow this block.

READ
- The hand-off folder is the `handoff` key: data\scratch\workaround\handoff\lab_<session>.
- Read handoff.csv with no default NA handling: NAN is a real ticker. Blank means not available; 0 is a real zero.
- Your batch is the rows where lb_batch equals the batch number, in lb_order.
- If handoff_matches_lab is false, stop and write one line to the fix inbox:
  "Lab republished: run avs_day.ps1 evening -Refresh". Do not triage a stale hand-off.
- Per-row evidence (structure, option_risk, context, morning) is in handoff_evidence.jsonl.

THE LAB'S VALUES ARE THE INPUT. NEVER REPLACE THEM.
- Target       = anticipated_level        (copy into `target`)
- First profit = anticipated_level_q50    (copy into `first_profit`)
- Contract     = contract_symbol          (copy into `trade_contract`)
- Do not compute a half target, a level cap or your own contract pick.
- If you disagree with a Lab value, say so in main_challenge. Do not change the value.

WHAT YOU ADD (live checks only)
- trigger_state: beyond trigger on a close / at trigger / not yet (against thesis_trigger_level).
- chase_state: in range / extended / chased.
- Live quote on the Lab contract: contract_bid, contract_ask, contract_oi (numbers only) and contract_quote_time_utc.
- live_gate, from the 11 Nov tiers on that live quote:
    A  spread <= 10% of mid, OI >= 100, and under a 1.50 mid the spread is <= 0.10 wide
    B  spread 10-20% of mid (or A except for the 0.10 width): tradeable with care, say so
    C  spread over 20%, no bid, or OI under 100: not tradeable at this quote
- On tier C: use a contract from a column whose name starts `contract_alternative` if the hand-off has one.
  If it has none, write trade_contract = none and the reason. Do not search for a strike yourself.
- earnings_tastytrade: the date from Tastytrade.
- cluster, cluster_role: only if your narrative cluster overrides lb_group.

FLAGS ARE INFORMATION, NOT FILTERS
- lb_window_flag, lb_over_cap, lb_saved_gate, lb_stock_tier, lb_time_fit, lb_repair_conflict, lb_runway_note.
- Use them in rank_reason and main_challenge. Never drop a row for a flag: every name in the batch gets a row.

WRITE batch<N>_triage_<session>.csv into the hand-off folder, with these columns:
  deep_mine_rank   whole numbers, consecutive, no gaps (batch 1 starts at 1; batch 2 continues from 31)
  ticker           every name of the batch, once
  ledger_id        copy of lb_ledger_id
  side             copy of direction
  lab_revision     copy of handoff_lab_revision from today_context.json
  target, first_profit, trade_contract       as above
  trigger_state, chase_state
  contract_bid, contract_ask, contract_oi, contract_quote_time_utc, live_gate
  earnings_tastytrade
  cluster, cluster_role
  main_challenge, rank_reason
  decision, decision_reason, contract_taken, entry_type, entry_premium     present and left empty
You may keep your other columns (money tags, previous card, narrative catalyst).

NO LONGER WRITTEN
  half_target, level, pays_at_half_target, ret_at_half_target_at_ask, handoff_best_contract,
  contract_spread_pct, lab_contract, and any 25% spread test.

THEN save the deep-dive prompts file: batch 1 deep_dive_prompts_<session>.md, batch N deep_dive_prompts_<session>_b<N>.md,
in the hand-off folder. Each section names the session and the hand-off folder.
```

## 2. Run sheet for this cycle

| When | Who | Line or action |
|---|---|---|
| Before the run | ACK | Paste the block in part 1 into the triage task prompt |
| Before the run | ACK | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 status -LabHandoff` |
| The run | ACK | `python intelligent_orchestrator.py --evening --plan-only`, then `python intelligent_orchestrator.py --evening` |
| After the Lab publishes | ACK | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 evening` |
| Then | ACK | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 packs -Batch 1` |
| Then | ACK | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 status` |
| After the triage | ACK | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 checktriage` |
| After the Morning run and Lab republication | ACK | `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 evening -Refresh`, then `checktriage` again |

What `status` should show before the triage runs:

| Key | Expected |
|---|---|
| `handoff_source` | LAB |
| `run_state` | not "running" |
| `lab_publication_state` | COMPLETE |
| `handoff` | `data\scratch\workaround\handoff\lab_<session>` |
| `handoff_matches_lab` | True |
| `packs_ready` | True |

The session is the first market session after the Lab's bar date. For a run on Friday 13 Nov's bars that is Monday 16 Nov, so the folder is `lab_2026-11-16`.

Back to the old chain at any time: `& C:\Users\ACKVerissimo\AVSHUNTER-Intelligence\data\scratch\workaround\avs_day.ps1 status -LegacyHandoff`

## 3. What to expect on the first Lab-first cycle

- **Many more rows.** The 11 Nov run gave 2,132 hand-off rows in 72 batches of 30, against 171 before. Only batch 1 is triaged on schedule (B5 is not built).
- **WARN lines are normal.** Tier B or C on the live quote, and any contract other than the Lab's, are WARN. On 11 Nov, 21 of batch 1's 30 saved quotes were tier C.
- **The window flag runs on a proxy** (`PROXY_Q50`) until Codex publishes the monetisation clock.
- **Cards have no S1–S6 row.** The strategy layer and the hand-off comparison still read the old layout and are skipped in Lab mode. The pre-close scan and `track_outcomes.py` run on the decision ledger, which is still built.
- **One older test fails by design:** `tests\test_x17_check_triage_spread_gate.py` pins the 25% rule that was removed. It needs ACK's word to retire or rewrite it.
- **The deep dive still rebuilds some figures itself** (B8 is not built). The triage row is Lab-first; the card is not yet.

## 4. Checked on 13 Nov

- Lane B's 48 tests pass on today's working tree, which holds Codex's uncommitted 12–13 Nov edits: 26 hand-off, 9 triage check, 7 decision records, 6 packs.
- The hand-off reader takes its field list from each publication's own manifest (`lab_reader.py:89`), so the card fields Codex has added do not break it. Not tested on a publication that carries them: none exists yet.
- Not checked: a full hand-off build on a new run. The last completed publication is run `20261111_231951`.

## 5. One decision still open (Lane B report, section 7, item 5)

The scheduled triage runs before the Morning run, so it triages the Evening publication. After the Morning republish the hand-off must be refreshed, and the triage's `lab_revision` is then the older one. My recommendation for this cycle: triage on the Evening publication as now, refresh after the Morning run, run `checktriage` again and read its revision note. Decide after seeing one cycle whether the triage should move to after the Morning run.

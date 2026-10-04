# Behavioural hierarchy — design test on SOFI (1 Oct 2026)

**What this is:** a throwaway prototype (`.claude_scratch/soc_prototype.py`), not pipeline code. It implements the layered logic: Bars → Sequences → Behaviour → Control → Phase → Event → Transition → Signal. It was run once with parameters fixed in advance (1.5×ATR swing reversal, 6-wave control window, 0.618 repair, NR4/NR7). The SOFI teaching case was used as worked examples, not as training data.

**Data:**
- Canonical daily bars to 29 Sep 2026.
- 5-minute bars for 16 sessions in Sep 2026, resampled to 60 minutes. 15 Sep is missing and 28 Sep is partial.
- The teaching right edge (30 Sep: O 15.94, H 16.17, L 15.71, C 15.72) is not in the store yet.

## Reproduced correctly
- **Daily swing structure matches the anchors.**
  - Earlier extreme 19.74 (10 Jul), then the 14.88 low (29 Jul).
  - Lower recovery peaks 19.50 → 18.71 → 17.96 ("later peak below 19.74", "successive recoveries lose ground", "failed recovery near 17.96").
- **60-minute structure matches.** The 17.96 spike (22 Sep) fails, the decline to 16.20 (teaching: ≈16.30), and the weak recovery to 16.87–16.92 (teaching: ≈16.85). This is effective downside of 9.8 ATR followed by a recovery of 38% of it.
- **Daily read matches the teaching labels:** Controller SELLERS, Phase E, maturity MATURE.
- **The 14.88 low is not labelled a Spring.** The teaching says it "needs an established support map".
- **Swings are confirmed only after the reversal**, so the replay uses only data available at the time. **The mirror test is exact:** the reflected chart reads BUYERS / E / MATURE with identical wave sizes.

## Design gaps exposed (to fix before coding)

| # | Gap | Evidence | Fix |
|---|---|---|---|
| 1 | "Repair" was measured as wave size | The daily recovery to 17.96 was 73% of the prior decline by size, so it counted as a repair. But it stayed below 18.71 and the prior balance. As a result no SOW→LPSY signal was emitted. | Measure retention and repair against **structural levels**. Did the recovery regain the level or balance area that the decline broke? Wave ratios are supporting evidence only. |
| 2 | The unconfirmed current leg was ignored | 60m read TWO-SIDED / Phase B, even though price had already broken below 16.20 | Position of the current leg relative to the structure is known now and must count. Only its end pivot is unconfirmed. |
| 3 | Flat swing list | Minor swings (18.96 inside the rally; 16.87 vs 16.92) broke the higher/lower sequence tests | Separate swing degrees. Major swings define campaign control; minor swings define the setup and trigger (NESTED_STRUCTURE). |
| 4 | No event lifecycle | Labelled "SOS" on the failed 22 Sep 60m spike, and "spring-like reclaims" on 31 Aug and 16 Sep inside the markdown | An event is a candidate until its response is observed. Failed springs become Failed-Spring Continuation (BEAR). Without this, the pipeline emits BULL springs inside a markdown, which is the old bias in a new form. |
| 5 | Phase A vs C is undecidable without range context | The 5 Aug cut gave "A or C" | Track whether a range exists and its boundaries. A = the established controller is interrupted; C = a test of a range boundary. |
| 6 | Compression without location or side | NR4/NR7 were true on 29 Sep, but the 5/20 true-range ratio (0.81) missed the visual contraction | Record where it occurs (e.g. below a falling ceiling), which side's swings are contracting, and who defends territory. Use more than one contraction measure. |
| 7 | Control quality was too literal | Down thrusts of 2.94 → 3.01 ATR were read as "strengthening", while ATR itself was falling | Use tolerance bands. Judge thrusts on structure (new extremes, retained ground) as well as size. |
| 8 | Intraday data completeness | 15 Sep missing; 28 Sep partial | Intraday timeframes need complete session capture before they carry authority. |

## Trigger state (daily, applying fix 1)
- **Candidate:** SOW→LPSY continuation, BEAR.
- **Trigger:** acceptance below 16.53. This was met by the closes on 28–29 Sep, so the candidate state is ACTIVATED.
- **Warning:** the move is MATURE, so this is late in an old move and not a fresh entry (MATURE_MOVE rule).
- **Invalidation:** acceptance back above the 17.96 recovery extreme.
- **Next anticipated logic:** a reclaim of 16.53 that is then defended would be a local Spring candidate, not a reversal of the campaign.

## Conclusion
The layered logic can be implemented and reproduces the teaching read in the places where it was implemented structurally. Gaps 1–7 are definition problems in the design, not reasons to abandon it, and they need to be written into the design before any pipeline code. A single bearish case cannot validate a detector. The next test must include bullish episodes, ranges and failed events across several tickers.

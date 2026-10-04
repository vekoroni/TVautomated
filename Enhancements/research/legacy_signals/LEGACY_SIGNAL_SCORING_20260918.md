# How the old pipeline's recommendations actually did (21 May – 2 Aug 2026)

Research only · script `Enhancements/research/legacy_signal_scoring.py` · frozen inputs in `inputs/` (sha256 in
`inputs_manifest.json`) · per-record results in `legacy_signal_scores.csv` · figures in `legacy_signal_summary.json`.

## Data

The inputs are 11 exports from ACK's OneDrive covering 9 runs. After removing duplicate exports, there are
**1,786 recommendations**: 1,107 calls and 679 puts. The underlying was scored for 1,784 of them. The option was
scored for 1,524, using an executable entry. The rest had no stored chain snapshot near entry, and they are counted
as missing, not as zero.

**Option returns are executable: buy at the ask of the first stored snapshot on or after entry, and sell at the bid
of the first snapshot on or after the horizon.** Stored chains for May–Aug are weekly, so option exits are accurate
only to within a week.

**The recorded premium in the old files is unreliable.** Only 86% of recorded premiums lie within 0.5–2× the market
mid near entry. For example, the WM 250 put was recorded at 0.05 when the market was about 21. Scored on the
recorded premium, the average put return was +145%, which is an artefact of these errors. The recorded premium is
therefore used only for comparison.

## Results

| Group | n | Underlying 20-session mean / right-direction share | Option 5 sessions median / profitable share | Option 20 sessions median / profitable share | Option ≥ +100% at 20 sessions |
|---|---|---|---|---|---|
| All recommendations | 1,786 | −0.7% / 50% | −43% / 22% | −54% / 22% | 7.0% |
| Calls | 1,107 | −1.3% / 48% | −50% / 18% | −57% / 19% | 6.7% |
| Puts | 679 | +0.3% / 54% | −32% / 30% | −49% / 27% | 7.4% |
| Top 5 per run (priority rank) | 45 | +4.1% / 59% | −41% / 24% | −50% / 18% | 7.9% |
| Rank above 10 | 1,696 | −0.9% / 49% | −43% / 22% | −54% / 22% | 6.8% |
| Verdict GO | 460 | −1.6% / 48% | −41% / 23% | −60% / 20% | 5.9% |
| Verdict ARMED | 119 | +3.3% / 68% | −27% / 36% | −33% / 36% | 10.0% |
| Verdict NEGATIVE_RR | 126 | −0.8% / 47% | −45% / 17% | −71% / 30% | 19.2% |

## What it says

1. **No directional skill overall.** The underlying moved the recommended way about 50% of the time, a coin flip,
   and the mean was slightly negative.
2. **The long options lost heavily.** The median was −43% at 5 sessions and −54% at 20 sessions, and only about 1
   in 5 was profitable. This matches the new backtest ledger (tickets −35% on quoted fills). Neither the old nor the
   new pipeline yet shows an option edge.
3. **The old verdicts did not separate winners from losers.** "GO" was no better than "EOD_CAUTION" or
   "CONTRACT_REPAIR". The old gates spent effort without adding value, which supports rank-not-gate.
4. **The top of the old ranking had some underlying signal** (top 5 per run +4.1% at 20 sessions, 59% right). The
   sample is small (45) and was not converted into option returns (median −50%). The direction may sometimes have
   been right while the option still lost to premium, spread and time decay. The ARMED group shows the same pattern
   more strongly (n = 119).
5. **About 7% of options returned +100% or more, but the median loss was large.** A long-option book lives or dies
   on its losers. That points to contract choice (runway, near the money, spread) and cheap volatility, not to more
   signals.

## Caveats

- 9 runs over 10 weeks in one market regime, so the records are highly correlated. Treat subgroup differences
  (ARMED, top 5) as hypotheses, not findings; many groups were compared.
- No stop was applied. Positions are marked at horizons, not managed.
- Weekly option snapshots make exit timing coarse.
- Excel pick lists (Top 25/50, ForwardProbability) are not yet scored; they need `openpyxl`.

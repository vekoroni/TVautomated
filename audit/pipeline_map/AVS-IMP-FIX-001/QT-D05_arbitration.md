# QT-D05 — Arbitration: independent TPO/value-area implementation vs production

**Item:** AVS-FIX-001 W0.7 · **Severity:** P3 · **Date:** 2026-09-06
**Verdict:** **Production is correct. The independent implementation was wrong. QT-D05 is closed as NOT_A_DEFECT.**

---

## 1. The disagreement

AVS-TST-QT-001 recorded that the tester's independently written TPO/value-area
calculation placed the POC and value-area boundaries **one bin lower** than the
production calculation in `market_structure/profile.py`. The tester could not
resolve it within budget and held it at P3, noting only that it was
"UNRESOLVED → arbitrated" by a test they had not been able to run, because
`tests/msi/` was outside the acceptance matrix (QT-001 D-04).

That test is now in the matrix (AVS-FIX-001 W0.3), so the arbitration can be
stated on evidence rather than inference.

## 2. The deciding evidence

`tests/msi/test_computation.py::C05C07_TpoAndVolumeAllocation`
`::test_c06_value_area_expands_from_poc_to_next_higher_adjacent_count`

Run isolated on branch `avs-fix-001`, 2026-09-06: **1 passed**.

The test is a hand-computed worked example, written independently of the
production source and carrying its full arithmetic trace in the docstring. It
pins the exact behaviour under dispute:

    counts = [1, 1, 2, 1]   (bins at prices 100, 101, 102, 103)
    poc_index = 2, total = 5, target = 5 x value_area_share (0.70) = 3.5

    step 1: below = counts[1] = 1, above = counts[3] = 1
            -> `above >= below` -> expand HIGH -> high = 3, accumulated = 3
    step 2: below = counts[1] = 1, above = n/a (high is at the top index)
            -> above = -1 < below -> expand LOW -> low = 1, accumulated = 4
            -> 4 >= 3.5, stop

    Result: value_area_low = 101.0, value_area_high = 103.0

## 3. Why production is right

Two production behaviours were in dispute, both in
`market_structure/profile.py`:

**(a) POC tie-break — `_build` line `poc_index = int(np.flatnonzero(counts == counts.max())[-1])`.**
When several bins share the maximum TPO count, production takes the **highest**
such bin (`[-1]`); the independent implementation took the lowest (`[0]`). This
is a convention, not a derivation — neither is forced by first principles — so
the repository's own committed, hand-computed test is the authority, and it
encodes `[-1]`. On this fixture the maximum is unique (bin 102), so the
tie-break is not what produced the one-bin gap; it is recorded here because it
was part of the disagreement and is the one place a future divergence could
reappear.

**(b) Value-area expansion tie-break — `_value_area`, `if above >= below`.**
This is the actual source of the one-bin difference. When the adjacent counts
above and below the current value-area edge are **equal**, production expands to
the **higher** side (`>=`). The independent implementation expanded to the lower
side (strict `>`). Step 1 of the trace above is exactly that tie: `below = 1`,
`above = 1`. Production takes the high side and finishes at [101, 103]; the
independent version takes the low side and finishes one bin lower, at
[100, 102].

The tester's own summary already conceded the point — *"arbitrated against me:
the repository's own excluded test ... passes, confirming production's
tie-break"* (`AVS-TST-QT-001_FINDINGS.md` line 67). This note records the
arbitration with the test now actually executed rather than merely cited.

## 4. Disposition

* **No code change.** `market_structure/profile.py` is unmodified by this item.
* **No test change.** `test_c06` already encodes the correct behaviour and now
  runs in the acceptance matrix on every pass (W0.3).
* QT-D05 moves to **NOT_A_DEFECT — arbitrated in favour of production**.
* The residual risk is documentary, not behavioural: neither tie-break
  convention is stated in AVS-SD-002 §10.1, which is why an independent
  implementer could pick the opposite one in good faith. Recommend adding one
  sentence to §10.1 naming both conventions ("ties expand to the higher
  adjacent bin; a tied POC resolves to the highest such bin"). Filed as a
  documentation follow-up, not a defect.

## 5. Note on the sibling finding

The same fixture's C-07 assertion **was** a genuine defect, and in the opposite
direction — see W0.3. There the test was wrong (it asserted
`ONE_MINUTE_ESTIMATED` on bars spaced 5 and 26 minutes apart) and the
production code was right. The two findings arrived together and are resolved
in opposite directions; neither outcome was assumed in advance.

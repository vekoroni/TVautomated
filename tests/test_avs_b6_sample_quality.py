"""B6 (invented-values inventory, ACK 3 Oct 2026 "go ahead with B6"): sample size says what it measured.

Defect (live, OIS in options intelligence): "Actuarial N=... - robust sample size" was printed for any N >= 200
whatever the match method (SOFI: N=132,728 from an ANALOGUE fallback whose exact sample was 0/60), and a missing or
zero sample got no penalty while N=40 got -15 (missing scored better than thin).
Business rules:
- No sample (missing / 0) is NOT_ESTIMABLE and scores like the thinnest band (-15); missing is never better than thin.
- EXACT matches keep the sample-size bands; only an EXACT N >= 200 is called robust.
- A fallback match (RELAXED / ANALOGUE / unknown method) is never called robust: its N is the pooled fallback sample,
  not this exact state; N >= 200 fallbacks take the moderate band (-5) and name the method.
"""
import inspect

import scripts.avshunter_options_intelligence as oi


def test_missing_sample_is_never_better_than_thin():
    pts, text, positive = oi.actuarial_sample_quality(None, "EXACT")
    assert pts == -15 and not positive and "NOT_ESTIMABLE" in text
    assert oi.actuarial_sample_quality(0, "EXACT")[0] == -15


def test_exact_bands_and_robust_only_for_exact():
    assert oi.actuarial_sample_quality(40, "EXACT")[0] == -15
    assert oi.actuarial_sample_quality(150, "EXACT")[0] == -5
    pts, text, positive = oi.actuarial_sample_quality(5000, "EXACT")
    assert pts == 0 and positive and "robust" in text and "exact" in text.lower()


def test_fallback_is_never_robust():
    pts, text, positive = oi.actuarial_sample_quality(132728, "ANALOGUE")
    assert pts == -5 and not positive and "ANALOGUE" in text and "robust" not in text
    assert oi.actuarial_sample_quality(80, "RELAXED")[0] == -10
    assert "METHOD_UNKNOWN" in oi.actuarial_sample_quality(500, "")[1]


def test_ois_uses_the_rule():
    src = inspect.getsource(oi.compute_ois)
    assert "actuarial_sample_quality(" in src and "robust sample size\")" not in src

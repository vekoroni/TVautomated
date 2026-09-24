"""Missing option observations must never be presented as measured zeroes."""

import json
import subprocess
from pathlib import Path


HTML = Path(__file__).resolve().parents[1] / "intelligence-lab/static/index.html"


def test_observed_number_distinguishes_missing_from_real_zero():
    source = HTML.read_text(encoding="utf-8")
    start = source.index("function formatObservedNumber(")
    end = source.index("function formatObservedFractionPercent(", start)
    end = source.index("\n}", end) + 2
    script = source[start:end] + "\nconsole.log(JSON.stringify([" + ",".join(
        f"formatObservedNumber({json.dumps(value)}, 4)" for value in
        (None, "", "NaN", "—", "0", 0, "0.3926", "garbage")
    ) + ",formatObservedFractionPercent(null, 1),formatObservedFractionPercent('0', 1)]));"
    result = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", check=True)
    assert json.loads(result.stdout) == ["—", "—", "—", "—", "0.0000", "0.0000", "0.3926", "—", "—", "0.0%"]


def test_trade_and_options_panels_use_observed_formatters():
    source = HTML.read_text(encoding="utf-8")
    assert "formatObservedNumber(opt('contract_delta'), 4)" in source
    assert "formatObservedNumber(opt('contract_gamma'), 4)" in source
    assert "formatObservedFractionPercent(opt('contract_iv'), 1)" in source
    assert "formatObservedFractionPercent(opt('atm_iv'), 1)" in source
    assert "formatObservedFractionPercent(opt('hv_30d'), 1)" in source
    assert "parseFloat(opt('contract_delta')||0).toFixed(4)" not in source

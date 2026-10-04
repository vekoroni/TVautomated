"""Rule 6 (CLAUDE.md; ACK 3 Oct 2026 "remove it"): macro never moves a gate, score or rank.

The EIL composite added +10 for macro_bias CALL_TAILWIND and -15 for PUT_HEADWIND. It was dormant (macro_bias did
not reach the EIL input) but a latent breach, and direction-blind: PUT_HEADWIND means a weak sector, which is a
tailwind for a put. Business rule: the EIL composite is identical whatever the macro bias; the bias stays display.
"""
import inspect

import execution_intelligence as eil


def test_composite_has_no_macro_modifier():
    src = inspect.getsource(eil)
    assert "_enrichment_score_modifier = +10.0" not in src
    assert "_enrichment_score_modifier = -15.0" not in src
    assert "composite = composite + _enrichment_score_modifier" not in src

"""A Wyckoff phase letter is not a directional state without its mode."""

from domain.structure_mode_phase import mode_phase_key, resolve_mode_phase_identity


def test_distribution_phase_c_cannot_alias_accumulation_phase_c():
    assert mode_phase_key("ACCUMULATION", "C") == "ACCUMULATION:C"
    assert mode_phase_key("DISTRIBUTION", "C") == "DISTRIBUTION:C"


def test_distribution_phase_e_is_not_markup_and_unknown_mode_is_not_filled():
    assert mode_phase_key("DISTRIBUTION", "E") == "DISTRIBUTION:E"
    assert mode_phase_key("UNKNOWN", "E") == "UNKNOWN:E"
    assert mode_phase_key("DISTRIBUTION", "UNKNOWN") == "DISTRIBUTION:UNCONFIRMED"


def test_cross_engine_phase_is_not_silently_paired_with_precore_mode():
    assert resolve_mode_phase_identity("DISTRIBUTION", "C", "D") == (
        "DISTRIBUTION:C", "PRECORE_MODE_PHASE"
    )
    assert resolve_mode_phase_identity("DISTRIBUTION", "", "D") == (
        "UNKNOWN:D", "ENGINE_PHASE_ONLY"
    )

from __future__ import annotations

import json

from msi_runtime import MSI_CONFIG_VERSION, MSIRuntimeFlags, active_flags


def test_all_msi_switches_default_off() -> None:
    assert active_flags({}) == MSIRuntimeFlags()
    assert not any(active_flags({}).to_dict().values())


def test_switch_parsing_and_fingerprint_are_deterministic() -> None:
    first = active_flags({"MSI_V2_CAPTURE": "true", "MSI_STRUCTURE": "1"})
    second = active_flags({"MSI_STRUCTURE": "yes", "MSI_V2_CAPTURE": "on"})
    assert first.v2_capture is True
    assert first.structure is True
    assert first.fingerprint == second.fingerprint
    assert MSI_CONFIG_VERSION == "msi-runtime-v1.1"


def test_persistent_config_is_loaded_and_environment_can_override(
    tmp_path, monkeypatch
) -> None:
    config = tmp_path / "msi_runtime.json"
    config.write_text(
        json.dumps(
            {
                "flags": {
                    "v2_capture": True,
                    "interpreter_resolver": True,
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("MSI_CONFIG_PATH", str(config))
    monkeypatch.setenv("MSI_V2_CAPTURE", "0")

    flags = active_flags()

    assert flags.v2_capture is False
    assert flags.interpreter_resolver is True

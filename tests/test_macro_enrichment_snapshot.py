import json
import ast
import logging
from pathlib import Path
from typing import Optional

import pytest

from contracts.macro_enrichment_delta import (
    find_macro_enrichment_delta, pin_macro_enrichment_delta,
    load_macro_enrichment_delta, merge_macro_enrichment_delta,
)

FIXTURE = Path(__file__).parent / 'fixtures' / 'macro_enrichment_delta_sample.json'


def setup_paths(tmp_path):
    source = tmp_path / 'dropbox' / 'macro' / 'macro_intelligence_latest.json'
    runtime = tmp_path / 'runs' / 'test_run' / 'macro' / 'macro_runtime.json'
    source.parent.mkdir(parents=True)
    runtime.parent.mkdir(parents=True)
    base = {'contract_version': 'macro_contract_v1_0', 'dir_bias': 'NEUTRAL',
            'size_multiplier': 0.5, 'trigger_required': True, 'extras': {}}
    runtime.write_text(json.dumps(base), encoding='utf-8')
    return source, runtime, base


def test_capture_merge_and_downstream_share_frozen_bytes(tmp_path):
    source, runtime, base = setup_paths(tmp_path)
    delta = source.parent / 'avshunter_macro_enrichment_delta.json'
    delta.write_bytes(FIXTURE.read_bytes())
    pinned = pin_macro_enrichment_delta(runtime, source)
    assert pinned.parent == runtime.parent
    assert pinned.read_bytes() == delta.read_bytes()
    merged = merge_macro_enrichment_delta(base, load_macro_enrichment_delta(pinned))
    assert merged['dir_bias'] == 'NEUTRAL'
    assert merged['size_multiplier'] == 0.5
    assert merged['trigger_required'] is True
    assert merged['extras']['macro_exposure_index']
    delta.write_text('{}', encoding='utf-8')
    assert pin_macro_enrichment_delta(runtime, source) == pinned
    assert find_macro_enrichment_delta(runtime) == pinned
    assert pinned.read_bytes() == FIXTURE.read_bytes()
    receipt = json.loads((runtime.parent / 'macro_enrichment_snapshot_receipt.json').read_text())
    assert receipt['state'] == 'CAPTURED'
    assert receipt['source_path'] == str(delta.resolve())
    assert len(receipt['sha256']) == 64


def test_absence_is_frozen_even_after_upload(tmp_path):
    source, runtime, _ = setup_paths(tmp_path)
    assert pin_macro_enrichment_delta(runtime, source) is None
    (source.parent / 'avshunter_macro_enrichment_delta.json').write_bytes(FIXTURE.read_bytes())
    assert pin_macro_enrichment_delta(runtime, source) is None
    assert find_macro_enrichment_delta(runtime) is None


def test_tampered_snapshot_is_rejected_by_downstream(tmp_path):
    source, runtime, _ = setup_paths(tmp_path)
    (source.parent / 'avshunter_macro_enrichment_delta.json').write_bytes(FIXTURE.read_bytes())
    pinned = pin_macro_enrichment_delta(runtime, source)
    pinned.write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='hash'):
        find_macro_enrichment_delta(runtime)


def test_invalid_packet_is_not_published(tmp_path):
    source, runtime, _ = setup_paths(tmp_path)
    (source.parent / 'avshunter_macro_enrichment_delta.json').write_text('{}', encoding='utf-8')
    with pytest.raises(ValueError, match='Invalid macro enrichment'):
        pin_macro_enrichment_delta(runtime, source)
    assert not (runtime.parent / 'macro_enrichment_delta_snapshot.json').exists()


def test_source_folder_cannot_be_overwritten(tmp_path):
    source, _, _ = setup_paths(tmp_path)
    with pytest.raises(ValueError, match='different'):
        pin_macro_enrichment_delta(source, source)


def test_real_orchestrator_merge_then_discovery_uses_snapshot(tmp_path):
    from scripts.apply_macro_enrichment_to_discovery import enrich_discovery_csv
    import csv

    source, runtime, _ = setup_paths(tmp_path)
    delta = source.parent / 'avshunter_macro_enrichment_delta.json'
    delta.write_bytes(FIXTURE.read_bytes())
    # Execute the actual orchestrator function without importing provider or
    # broker startup code. Only its quant-packet builder is isolated here.
    tree = ast.parse((FIXTURE.parents[2] / 'intelligent_orchestrator.py').read_text(encoding='utf-8-sig'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                    and n.name == 'merge_macro_enrichment_into_macro_latest')
    namespace = dict(Path=Path, Optional=Optional, json=json, logger=logging.getLogger('test'),
                     pin_macro_enrichment_delta=pin_macro_enrichment_delta,
                     find_macro_enrichment_delta=find_macro_enrichment_delta,
                     load_macro_enrichment_delta=load_macro_enrichment_delta,
                     merge_macro_enrichment_delta=merge_macro_enrichment_delta,
                     build_macro_quant_packet=lambda macro, path: {},
                     write_json=lambda path, data: path.write_text(json.dumps(data), encoding='utf-8'))
    exec(compile(ast.Module(body=[function], type_ignores=[]), 'orchestrator_merge', 'exec'), namespace)
    assert namespace[function.name](runtime, source) is True
    delta.write_text('{}', encoding='utf-8')
    discovery = runtime.parent / 'discovery.csv'
    discovery.write_text('ticker,tier,phase,precor_intent\nINTC,1,MARKUP,CALL\n', encoding='utf-8')
    result = enrich_discovery_csv(discovery, runtime)
    assert result['matched_rows'] == 1
    with discovery.open(encoding='utf-8-sig', newline='') as handle:
        row = next(csv.DictReader(handle))
    assert row['precor_intent'] == 'CALL'
    assert 'AI_CAPEX_SEMICONDUCTOR_MOMENTUM' in row['macro_enrichment_theme_ids']
    calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Name) and n.func.id == function.name]
    assert any(len(c.args) == 2 and ast.unparse(c.args[1]) == 'cfg.MACRO_FILE' for c in calls)

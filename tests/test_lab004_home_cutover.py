"""Approved Lab homepage cutover retains an explicit legacy escape hatch."""
import ast
from pathlib import Path

def test_home_is_review_and_legacy_remains_explicit():
    root=Path(__file__).resolve().parents[1]
    tree=ast.parse((root/'intelligence-lab/intelligence_lab.py').read_text(encoding='utf-8'))
    functions={n.name:ast.unparse(n) for n in tree.body if isinstance(n,ast.FunctionDef)}
    assert 'review.html' in functions['index']
    assert 'index.html' in functions['legacy_lab'] and '/legacy' in functions['legacy_lab']
    assert 'published_review_runs' in functions['api_runs']
    html=(root/'intelligence-lab/static/review.html').read_text(encoding='utf-8')
    js=(root/'intelligence-lab/static/review-app.js').read_text(encoding='utf-8')
    assert 'href="/legacy"' in html
    assert '/legacy#interpreter-panel' not in js
    assert 'LabReviewLive' in js
    live=(root/'intelligence-lab/static/review-live.js').read_text(encoding='utf-8')
    assert 'latest_review_run' in live

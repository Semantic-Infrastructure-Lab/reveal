"""Included directory I/O loss reaches analysis before projection or absence claims."""
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.ast.analysis import collect_structures
from reveal.adapters.patches.adapter import PatchesAdapter
from reveal.adapters.trace import TraceAdapter
from reveal.testability.patches import scan_patches, scan_patches_ts
from reveal.testability.report import build_testability_report
from reveal.utils.request_cache import _tree_stamp


@pytest.fixture
def tree(tmp_path):
    child = tmp_path / 'included_child'
    child.mkdir()
    (tmp_path / 'visible.py').write_text('def visible():\n    return 1\n', encoding='utf-8')
    (child / 'hidden.py').write_text('def hidden():\n    return 2\n', encoding='utf-8')
    (child / 'test_hidden.py').write_text('from unittest.mock import patch\npatch("svc.hidden")\n', encoding='utf-8')
    (child / 'hidden.test.ts').write_text('vi.mock("./svc");\n', encoding='utf-8')
    return tmp_path, child


def deny(monkeypatch, directory):
    real = os.scandir

    def scandir(path):
        if Path(path) == directory:
            raise PermissionError(13, 'controlled included child enumeration failure', str(directory))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)


def traversal_warning(result):
    warnings = result.get('meta', {}).get('warnings', [])
    return [w for w in warnings if w.get('type') == 'analysis_incomplete']


@pytest.mark.parametrize('entry,state', [('visible', 'incomplete'), ('hidden', 'failed')])
def test_trace_never_proves_absence_after_included_child_loss(tree, monkeypatch, entry, state):
    root, child = tree
    adapter = TraceAdapter(str(root), f'from={entry}')
    clean = adapter.get_structure()
    assert adapter.execution_facts(clean).completeness.value == 'complete'
    with monkeypatch.context() as context:
        deny(context, child)
        failed = adapter.get_structure()
    facts = adapter.execution_facts(failed)
    assert facts.completeness.value == state
    assert not any(cause.value == 'invalid_request' for cause in facts.failures)
    warning, = traversal_warning(failed)
    assert warning['count'] == 1 and warning['unit'] == 'directories'
    assert warning['directories'] == [child.as_posix()]
    assert 'PermissionError' in warning['message']
    assert 'files' not in warning
    assert not traversal_warning(adapter.get_structure())


@pytest.mark.parametrize('owner', ['ast', 'patches', 'report'])
def test_warning_survives_empty_or_filtered_projection(tree, monkeypatch, owner):
    root, child = tree
    deny(monkeypatch, child)
    if owner == 'ast':
        from reveal.adapters.ast.adapter import AstAdapter
        result = AstAdapter(str(root), 'name=hidden&limit=1').get_structure()
    elif owner == 'patches':
        result = PatchesAdapter(str(root), 'min=99&limit=1').get_structure()
    else:
        result = build_testability_report(str(root), [str(root)], top=1, min_patches=99)
    assert traversal_warning(result)
    assert all(w['unit'] == 'directories' for w in traversal_warning(result))
    assert not any(w.get('type') == 'analysis_failed' for w in result['meta']['warnings'])


@pytest.mark.parametrize('scan', [scan_patches, scan_patches_ts])
def test_patch_aggregates_keep_directory_loss_distinct_from_file_skips(tree, monkeypatch, scan):
    root, child = tree
    clean = scan([root])
    assert clean
    with monkeypatch.context() as context:
        deny(context, child)
        failed = scan([root])
    assert failed == [] and failed.skipped == []
    assert getattr(failed, 'traversal_failures', [])
    assert not getattr(scan([root]), 'traversal_failures', [])


def test_evidence_stamp_cannot_validate_an_incomplete_walk(tree, monkeypatch):
    root, child = tree
    assert _tree_stamp(root) is not None
    deny(monkeypatch, child)
    assert _tree_stamp(root) is None


@pytest.mark.parametrize('form', ['uri', 'command'])
@pytest.mark.parametrize('entry', ['visible', 'hidden'])
def test_actual_trace_cli_exits_analysis_failure_for_loss(tree, monkeypatch, form, entry):
    root, child = tree
    deny(monkeypatch, child)
    args = ([f'trace://{root}?from={entry}'] if form == 'uri'
            else ['trace', str(root), '--from', entry])
    result = _run_reveal_direct(*args, '--format', 'json')
    assert result.returncode == 3
    assert 'controlled included child enumeration failure' in result.stdout + result.stderr


def test_clean_single_file_sibling_and_excluded_child_are_unchanged(tree, monkeypatch):
    from reveal.utils.exclusions import exclusion_scope
    root, child = tree
    target = root / 'visible.py'
    before = TraceAdapter(str(target), 'from=visible').get_structure()
    with monkeypatch.context() as context:
        deny(context, child)
        assert TraceAdapter(str(target), 'from=visible').get_structure() == before
        with exclusion_scope(root, ['included_child']):
            kept = collect_structures(str(root))
            assert len(kept) == 1 and kept.skipped == []
            assert not getattr(kept, 'traversal_failures', [])

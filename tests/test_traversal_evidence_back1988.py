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


def test_root_enumeration_denial_is_failed_not_absent(tree, monkeypatch):
    root, _ = tree
    deny(monkeypatch, root)
    adapter = TraceAdapter(str(root), 'from=visible')
    result = adapter.get_structure()
    assert adapter.execution_facts(result).completeness.value == 'failed'
    assert traversal_warning(result)[0]['directories'] == [root.as_posix()]
    assert result['frames'][0]['resolved'] is False


def test_directory_count_exact_and_bounded_and_overlapping_roots(tree, monkeypatch):
    root, child = tree
    directories = [child]
    for index in range(6):
        directory = root / f'child{index}'
        directory.mkdir()
        directories.append(directory)
    real = os.scandir

    def denied(path):
        if Path(path) in directories:
            raise PermissionError(13, 'controlled enumeration loss', str(path))
        return real(path)

    monkeypatch.setattr(os, 'scandir', denied)
    patches = scan_patches([root, child, root])
    assert len(patches.traversal_failures) == 7
    result = build_testability_report(str(root), [str(root), str(child), str(root)])
    warning, = traversal_warning(result)
    assert warning['count'] == 7 and warning['unit'] == 'directories'
    assert len(warning['directories']) == len(warning['causes']) == 5
    assert 'unknown' in warning['message'] and 'files' not in warning


@pytest.mark.parametrize('value', [None, [('bad',)], [('child', '')], 'malformed'])
def test_malformed_traversal_evidence_cannot_prove_absence(tree, monkeypatch, value):
    from reveal.adapters.ast import analysis
    root, _ = tree
    collection = analysis.StructureList()
    collection.traversal_failures = value
    monkeypatch.setattr(analysis, 'collect_structures', lambda path: collection)
    adapter = TraceAdapter(str(root), 'from=hidden')
    result = adapter.get_structure()
    assert adapter.execution_facts(result).completeness.value == 'failed'
    assert result['meta']['errors']


def test_cache_cannot_seal_or_retain_incomplete_tree(tree, monkeypatch):
    from reveal.utils import request_cache as cache
    root, child = tree
    entries = {root: object()}
    name = 'back1988-control'
    monkeypatch.setattr(cache, '_VALIDATED', {name: (entries, entries.pop)})
    monkeypatch.setattr(cache, '_RESETTERS', {})
    monkeypatch.setattr(cache, '_STAMPS', {})
    # Future start avoids filesystem timestamp precision assumptions.
    future_ns = cache.request_started_ns() + 10**12
    with monkeypatch.context() as context:
        deny(context, child)
        cache.seal_request_caches(future_ns)
        assert (name, root) not in cache._STAMPS
    cache.seal_request_caches(future_ns)
    assert (name, root) in cache._STAMPS
    with monkeypatch.context() as context:
        deny(context, child)
        (child / 'hidden.py').write_text('def edited():\n    return 3\n', encoding='utf-8')
        cache.reset_request_caches()
    assert not entries and not cache._STAMPS


def test_callback_is_opt_in_and_policy_events_stay_distinct(tree, monkeypatch):
    from reveal.utils.path_utils import _walk_code_files, walk_tree
    root, child = tree
    deny(monkeypatch, child)
    hidden, errors = [], []
    assert list(_walk_code_files(root)) == [root / 'visible.py']
    assert list(_walk_code_files(root, on_error=errors.append, on_hidden=lambda *args: hidden.append(args)))
    assert len(errors) == 1 and Path(errors[0].filename) == child
    assert hidden == []
    errors.clear()
    assert list(walk_tree(root, on_error=errors.append))
    assert len(errors) == 1


def test_ast_outline_and_overview_keep_required_warning(tree, monkeypatch):
    from reveal.adapters.ast.adapter import AstAdapter
    from reveal.adapters.overview import OverviewAdapter
    root, child = tree
    deny(monkeypatch, child)
    result = AstAdapter(str(root), 'name=hidden').get_structure()
    assert traversal_warning(result)
    facts = OverviewAdapter.execution_facts({'meta': result['meta']})
    assert facts.completeness.value == 'incomplete'


@pytest.mark.parametrize('entry', ['visible', 'hidden'])
def test_text_trace_discloses_directory_failure_once(tree, monkeypatch, entry):
    root, child = tree
    deny(monkeypatch, child)
    result = _run_reveal_direct('trace', str(root), '--from', entry)
    assert result.returncode == 3
    assert (result.stdout + result.stderr).count('directory enumeration(s) failed') == 1


def test_empty_patches_text_qualifies_directory_loss(tree, monkeypatch):
    root, child = tree
    deny(monkeypatch, child)
    result = _run_reveal_direct(f'patches://{root}')
    assert result.returncode == 0
    assert 'No patch pressure groups in the available observations.' in result.stdout
    assert 'No patch pressure groups found.' not in result.stdout
    assert (result.stdout + result.stderr).count('directory enumeration(s) failed') == 1


def test_warning_counts_unique_directories_without_discarding_causes():
    from reveal.adapters.ast.analysis import traversal_failed_warning
    warning = traversal_failed_warning([('child', 'PermissionError: denied'),
                                        ('child', 'OSError: transient'),
                                        ('child', 'PermissionError: denied')])
    assert warning['count'] == 1
    assert 'PermissionError: denied' in warning['message']
    assert 'OSError: transient' in warning['message']


@pytest.mark.parametrize('owner', ['ast', 'patches'])
def test_error_without_filename_discloses_unknown_directory(tree, monkeypatch, owner):
    root, child = tree
    real = os.scandir

    def denied(path):
        if Path(path) == child:
            raise PermissionError('controlled error without filename')
        return real(path)

    monkeypatch.setattr(os, 'scandir', denied)
    result = (PatchesAdapter(str(root)).get_structure() if owner == 'patches'
              else TraceAdapter(str(root), 'from=visible').get_structure())
    warning, = traversal_warning(result)
    assert warning['directories'] == []
    assert warning['count'] == 0 and warning['unknown_directory_events'] == 1
    assert 'controlled error without filename' in warning['message']

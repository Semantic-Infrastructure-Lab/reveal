"""Local test/production parser evidence survives testability projections."""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct
from reveal.adapters.patches.adapter import PatchesAdapter
from reveal.adapters.testability import TestabilityAdapter as PressureAdapter
from reveal.core.treesitter_parse import GrammarUnavailable
from reveal.testability import patches
from reveal.testability.boundaries import collect_boundary_profiles
from reveal.testability.report import build_testability_report
from reveal.utils.path_utils import to_posix


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def _warning(result, kind):
    return [w for w in result['meta']['warnings'] if w.get('type') == kind]


@pytest.mark.parametrize('suffix,scan', [('.py', patches._scan_file), ('.test.ts', patches._scan_file_ts)])
def test_clean_zero_and_read_failure_are_distinct_fresh_lists(tmp_path, monkeypatch, suffix, scan):
    target = _write(tmp_path / ('test_ok' + suffix), '# clean\n' if suffix == '.py' else '// clean\n')
    clean = scan(target)
    assert clean == []
    assert clean.skipped == []
    assert clean.recovered_files == []
    real = Path.read_text

    def denied(path, *args, **kwargs):
        if path == target:
            raise PermissionError('controlled unreadable test')
        return real(path, *args, **kwargs)

    with monkeypatch.context() as context:
        context.setattr(Path, 'read_text', denied)
        failed = scan(target)
    assert failed == []
    assert len(failed.skipped) == 1
    assert failed.skipped[0][0] == to_posix(target)
    assert failed.skipped[0][1].startswith('PermissionError:')
    assert failed.recovered_files == []
    again = scan(target)
    assert again.skipped == []
    failed.skipped.clear()
    failed.recovered_files.append('changed')
    assert clean.skipped == again.skipped == []
    assert clean.recovered_files == again.recovered_files == []


@pytest.mark.parametrize('scan', [patches._scan_file, lambda path: patches.scan_patches([path])])
def test_python_syntax_error_is_retained(tmp_path, scan):
    target = _write(tmp_path / 'test_broken.py', 'def broken(:\n')
    result = scan(target)
    assert result == []
    assert result.skipped[0][0] == to_posix(target)
    assert result.skipped[0][1].startswith('SyntaxError:')
    assert result.recovered_files == []


@pytest.mark.parametrize('scan', [patches.scan_patches, patches.scan_patches_ts])
def test_ts_grammar_failure_merges_without_losing_python_or_logging(tmp_path, monkeypatch, caplog, scan):
    _write(tmp_path / 'test_ok.py', 'from unittest.mock import patch\npatch("svc.ok")\n')
    bad = _write(tmp_path / 'bad.test.ts', 'vi.mock("./svc");\n')

    def unavailable(*args, **kwargs):
        raise GrammarUnavailable('typescript', ImportError('controlled missing grammar'))

    monkeypatch.setattr(patches, 'get_tree', unavailable)
    result = scan([tmp_path])
    assert len(result) == (1 if scan is patches.scan_patches else 0)
    assert len(result.skipped) == 1
    assert result.skipped[0][0] == to_posix(bad)
    assert result.skipped[0][1].startswith('GrammarUnavailable:')
    assert 'controlled missing grammar' in result.skipped[0][1]
    assert result.recovered_files == []
    assert 'tree-sitter parse failed' in caplog.text


@pytest.mark.parametrize('scan', [patches._scan_file_ts, lambda path: patches.scan_patches([path]), lambda path: patches.scan_patches_ts([path])])
def test_actual_ts_recovery_keeps_mock_and_file_evidence(tmp_path, scan):
    target = _write(tmp_path / 'svc.test.ts', 'test("x",()=>{vi.mock("./svc");const broken=;});\n')
    uses = scan(target)
    assert len(uses) == 1
    assert uses[0].target_raw == './svc'
    assert list(uses) == uses
    assert patches.group_patches(uses, min_count=1)[0].patch_count == 1
    assert uses.skipped == []
    assert uses.recovered_files == [to_posix(target)]


@pytest.mark.parametrize('scan', [patches._scan_file_ts, lambda path: patches.scan_patches([path]), lambda path: patches.scan_patches_ts([path])])
def test_unexpected_ts_bug_still_escapes(tmp_path, monkeypatch, scan):
    target = _write(tmp_path / 'svc.test.ts', 'vi.mock("./svc");\n')

    def bug(*args, **kwargs):
        raise RuntimeError('controlled parser bug')

    monkeypatch.setattr(patches, 'get_tree', bug)
    with pytest.raises(RuntimeError, match='controlled parser bug'):
        scan(target)


def test_boundary_recovery_precedes_function_projection(tmp_path):
    target = _write(tmp_path / 'broken.ts', 'const broken = ;\n')
    profiles = collect_boundary_profiles(str(target))
    assert profiles == []
    assert profiles.skipped == []
    assert profiles.recovered_files == [to_posix(target)]
    clean = _write(tmp_path / 'clean.py', 'VALUE = 1\n')
    assert collect_boundary_profiles(str(clean)).recovered_files == []


@pytest.mark.parametrize('owner', ['testability', 'patches'])
def test_output_owners_join_exact_failure_and_recovery_counts(tmp_path, owner):
    src = _write(tmp_path / 'src' / 'broken.ts', 'const broken = ;\n')
    tests = tmp_path / 'tests'
    for index in range(7):
        _write(tests / f'test_bad{index}.py', 'def broken(:\n')
        _write(tests / f'recovered{index}.test.ts', 'vi.mock("./svc"); const broken=;\n')
    if owner == 'testability':
        result = build_testability_report(str(src.parent), [str(tests)], top=1, min_patches=1, include_unresolved=True)
        assert result['summary']['total_patch_uses'] == 7
        assert len(result['patch_hotspots']) == 1
    else:
        result = PatchesAdapter(str(tests), 'min=1&limit=1').get_structure()
        assert result['total_uses'] == 7
        assert len(result['groups']) == 1
    failed, = _warning(result, 'analysis_failed')
    assert failed['count'] == 7
    assert len(failed['files']) == 5
    assert 'SyntaxError' in failed['message']
    assert 'patch' in failed['message']
    recovered = _warning(result, 'parse_recovered')
    patch_recovery, = [w for w in recovered if w['count'] == 7]
    assert len(patch_recovery['files']) == 5
    assert len(recovered) == (2 if owner == 'testability' else 1)
    assert result['meta']['errors'] == []
    assert any(w.get('code') == ('W-TESTABILITY-2' if owner == 'testability' else 'W-PATCHES-1') for w in result['meta']['warnings'])


@pytest.mark.parametrize('owner', ['testability', 'patches'])
@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_actual_output_discloses_failure_once_and_exits_incomplete(tmp_path, owner, output_format):
    src = _write(tmp_path / 'src' / 'ok.py', 'VALUE=1\n')
    target = _write(tmp_path / 'tests' / 'test_bad.py', 'def broken(:\n')
    uri = f'testability://{src.parent}?tests={target.parent}' if owner == 'testability' else f'patches://{target.parent}'
    result = _run_reveal_direct(uri, '--format', output_format)
    # patches adopted the declared D6 path with ?view=pressure (BACK-2160): a lost test file is exit 3 in both owners.
    assert result.returncode == 3
    if output_format == 'json':
        payload = json.loads(result.stdout)
        failed, = _warning(payload, 'analysis_failed')
        assert failed['count'] == 1
    else:
        assert (result.stdout + result.stderr).count('could not be analyzed') == 1
        assert 'test_bad.py' in result.stdout + result.stderr


def test_supported_ts_zero_does_not_claim_python_only(tmp_path):
    src = _write(tmp_path / 'src' / 'ok.ts', 'export const x=1;\n')
    tests = _write(tmp_path / 'tests' / 'ok.test.ts', 'test("x",()=>{});\n')
    result = PressureAdapter(str(src.parent), f'tests={tests.parent}').get_structure()
    assert result['summary']['total_patch_uses'] == 0
    assert '_patch_note' not in result
    assert not _warning(result, 'analysis_failed')
    assert not _warning(result, 'parse_recovered')


def test_policy_exclusions_stay_outside_patch_failure_evidence(tmp_path):
    from reveal.utils.exclusions import exclusion_scope

    _write(tmp_path / 'test_good.py', 'from unittest.mock import patch\npatch("svc.ok")\n')
    _write(tmp_path / 'test_ignored.py', 'def broken(:\n')
    with exclusion_scope(tmp_path, ['test_ignored.py']):
        result = patches.scan_patches([tmp_path])
    assert len(result) == 1
    assert result.skipped == []
    assert result.recovered_files == []


@pytest.mark.parametrize('filename,source', [
    ('ok.test.ts', 'test("x",()=>{});\n'),
    ('test_bad.py', 'def broken(:\n'),
])
def test_patches_empty_text_describes_available_observations(tmp_path, filename, source):
    target = _write(tmp_path / filename, source)
    result = _run_reveal_direct(f'patches://{target}', '--format', 'text')
    assert result.returncode == (3 if target.suffix == '.py' else 0)  # the unparsable file is a lost observation
    if target.suffix == '.py':
        assert 'No patch pressure groups in the available observations.' in result.stdout
        assert 'No patch pressure groups found.' not in result.stdout
    else:
        assert 'No patch pressure groups found.' in result.stdout
        assert 'available observations' not in result.stdout
    assert 'JS/TS (jest/vitest)' in result.stdout
    assert ('could not be analyzed' in result.stdout) == (target.suffix == '.py')


@pytest.mark.parametrize('owner', ['testability', 'patches'])
@pytest.mark.parametrize('failure', ['read', 'grammar'])
def test_output_read_and_grammar_failures_do_not_leak_into_next_call(tmp_path, monkeypatch, owner, failure):
    src = _write(tmp_path / 'src' / 'ok.py', 'VALUE=1\n')
    target = _write(tmp_path / 'tests' / 'ok.test.ts', 'vi.mock("./svc");\n')
    adapter = (PressureAdapter(str(src.parent), f'tests={target.parent}&min_patches=1&include_unresolved=true')
               if owner == 'testability' else PatchesAdapter(str(target.parent), 'min=1'))
    real = Path.read_text

    def denied(path, *args, **kwargs):
        if path == target:
            raise PermissionError('controlled unreadable test')
        return real(path, *args, **kwargs)

    def unavailable(*args, **kwargs):
        raise GrammarUnavailable('typescript', ImportError('controlled missing grammar'))

    with monkeypatch.context() as context:
        if failure == 'read':
            context.setattr(Path, 'read_text', denied)
        else:
            context.setattr(patches, 'get_tree', unavailable)
        result = adapter.get_structure()
    warning, = _warning(result, 'analysis_failed')
    assert warning['count'] == 1
    assert warning['files'] == [to_posix(target)]
    assert ('PermissionError' if failure == 'read' else 'GrammarUnavailable') in warning['message']
    again = adapter.get_structure()
    assert not _warning(again, 'analysis_failed')
    assert not _warning(again, 'parse_recovered')
    assert (again['summary']['total_patch_uses'] if owner == 'testability' else again['total_uses']) == 1


@pytest.mark.parametrize('scan', [patches.scan_patches, patches.scan_patches_ts])
def test_aggregate_recovery_and_zero_reuse_is_fresh(tmp_path, scan):
    target = _write(tmp_path / 'ok.test.ts', 'vi.mock("./svc");const broken=;\n')
    first = scan([tmp_path])
    assert len(first) == 1
    assert first.recovered_files == [to_posix(target)]

    target.write_text('test("x",()=>{});\n', encoding='utf-8')
    again = scan([tmp_path])
    assert again == []
    assert again.skipped == again.recovered_files == []
    assert first.recovered_files == [to_posix(target)]


def test_gitignored_invalid_tests_are_policy_skips(tmp_path):
    from reveal.utils.gitignore import gitignore_scope

    _write(tmp_path / '.gitignore', 'test_ignored.py\n')
    _write(tmp_path / 'test_good.py', 'from unittest.mock import patch\npatch("svc.ok")\n')
    _write(tmp_path / 'test_ignored.py', 'def broken(:\n')
    with gitignore_scope(True):
        kept = patches.scan_patches([tmp_path])
    assert len(kept) == 1
    assert kept.skipped == kept.recovered_files == []
    with gitignore_scope(False):
        included = patches.scan_patches([tmp_path])
    assert len(included) == 1
    assert len(included.skipped) == 1

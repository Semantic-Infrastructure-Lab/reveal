"""Depends must retain required discovery loss without replacing observed results."""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.depends import DependsAdapter, DependsRenderer
from reveal.analyzers.imports.resolution import ProjectResolver
from reveal.utils.exclusions import exclusion_scope

pytestmark = pytest.mark.component


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding='utf-8')
    return path


def project(root, *, survivor=False):
    write(root / 'pyproject.toml', '[project]\nname="depends-loss"\n')
    target = write(root / 'target.py', 'VALUE=1\n')
    child = root / 'included_child'
    write(child / 'consumer.py', 'import target\n')
    if survivor:
        write(root / 'visible.py', 'import target\n')
    return target, child


def deny(monkeypatch, children, *, unknown=False):
    real = os.scandir
    attempts = []

    def scandir(path):
        if Path(path) in children:
            attempts.append(Path(path))
            if unknown:
                raise PermissionError('controlled Depends unlocated enumeration loss')
            raise PermissionError(13, 'controlled Depends discovery loss', str(path))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    return attempts


def warning(result):
    entries = result.get('meta', {}).get('warnings', [])
    return next((entry for entry in entries if entry.get('type') == 'analysis_incomplete'), None)


@pytest.mark.parametrize('survivor', [False, True])
def test_real_source_loss_retains_observations_and_qualifies_both_counts(tmp_path, monkeypatch, survivor):
    target, child = project(tmp_path / 'affected', survivor=survivor)
    adapter = DependsAdapter(str(target))
    clean = adapter.get_structure()
    assert clean['count'] == 1 + int(survivor)
    deny(monkeypatch, {child})
    result = adapter.get_structure()
    assert result['count'] == int(survivor)
    assert all(dep['file'] == 'visible.py' for dep in result['dependents'])
    assert result['metadata']['scan_budget']['returned'] == 1 + int(survivor)
    assert result['metadata']['scan_budget']['total'] == 1 + int(survivor)
    assert result['metadata']['scan_budget']['exact'] is False
    assert adapter._graph.traversal_failures
    assert warning(result)['directories'] == ['included_child']
    assert result['_meta']['confidence'] == 'reduced'
    assert result['undercount_possible'] is True
    assert 'missing file population is unknown' in result['warning']


def test_real_target_only_loss_cannot_certify_source_census(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    write(root / 'pyproject.toml', '[project]\nname="c-fixture"\n')
    write(root / 'visible.c', '#include "hidden.inc"\n')
    child = root / 'included_child'
    target = write(child / 'deep' / 'hidden.inc', 'int hidden(void);\n')
    adapter = DependsAdapter(str(target))
    clean = adapter.get_structure()
    assert clean['count'] == 1
    deny(monkeypatch, {child})
    result = adapter.get_structure()
    assert result['count'] == 0
    assert result['metadata']['total_files_scanned'] == clean['metadata']['total_files_scanned'] == 1
    assert result['metadata']['scan_budget']['total'] == 1
    assert result['metadata']['scan_budget']['exact'] is False
    assert warning(result)['count'] == 1


def test_actual_all_source_loss_and_unknown_location_still_positive_evidence(tmp_path, monkeypatch):
    root = tmp_path / 'affected'
    write(root / 'pyproject.toml', '[project]\nname="all-loss"\n')
    child = root / 'included_child'
    write(child / 'consumer.py', 'import decimal\n')
    deny(monkeypatch, {child}, unknown=True)
    result = DependsAdapter(str(root)).get_structure()
    assert result['metadata']['scan_budget'] == {'scope': 'scan', 'limit': 5000, 'total': 0, 'returned': 0, 'exact': False}
    assert result['metadata']['total_files_scanned'] == 0
    assert warning(result)['count'] == 0
    assert warning(result)['unknown_directory_events'] == 1
    assert result['_meta']['confidence'] == 'reduced' and result['undercount_possible']


@pytest.mark.parametrize('view', ['file', 'summary', 'top', 'dot', 'json'])
def test_actual_public_cli_views_disclose_loss_once(tmp_path, monkeypatch, view):
    root = tmp_path / 'affected'; target, child = project(root, survivor=True)
    deny(monkeypatch, {child})
    uri = 'depends://' + str(target if view in {'file', 'json'} else root)
    if view == 'top':
        uri += '?top=1'
    elif view == 'dot':
        uri += '?format=dot'
    result = run(uri, *(['--format', 'json'] if view == 'json' else []))
    assert result.returncode == 0  # existing Depends exit contract
    if view == 'json':
        payload = json.loads(result.stdout)
        assert warning(payload)['count'] == 1
    else:
        assert result.stdout.count('identified directory enumeration(s) failed') == 1
        assert 'PermissionError' in result.stdout
        if view == 'dot':
            assert result.stdout.startswith('digraph depends {\n')
            assert any(line.lstrip().startswith('//') and 'PermissionError' in line for line in result.stdout.splitlines())
            assert '"visible.py" -> "target.py";' in result.stdout
        else:
            assert 'observed' in result.stdout.lower()


def test_actual_empty_public_text_and_decorated_mcp_do_not_assert_clean(tmp_path, monkeypatch):
    pytest.importorskip('mcp')
    from reveal.mcp_server import reveal_query
    target, child = project(tmp_path / 'affected')
    deny(monkeypatch, {child})
    uri = 'depends://' + str(target)
    cli = run(uri)
    plain = reveal_query(uri)
    for text in (cli.stdout, plain):
        assert 'nothing imports this module' not in text
        assert 'may be incomplete' in text
        assert text.count('identified directory enumeration(s) failed') == 1
    provenance = json.loads(reveal_query(uri, provenance=True))
    assert warning(provenance)['count'] == 1
    assert provenance['execution']['command'].startswith('reveal depends://')


def test_same_adapter_repair_and_clean_sibling_exact(tmp_path, monkeypatch):
    target, child = project(tmp_path / 'affected')
    sibling, _ = project(tmp_path / 'sibling')
    owner = DependsAdapter(str(target)); other = DependsAdapter(str(sibling))
    baseline = owner.get_structure(); sibling_baseline = other.get_structure()
    with monkeypatch.context() as context:
        deny(context, {child})
        assert warning(owner.get_structure())
        assert other.get_structure() == sibling_baseline
    assert owner.get_structure() == baseline
    assert 'meta' not in baseline


def test_policy_excluded_directory_and_noise_unchanged(tmp_path, monkeypatch):
    target, child = project(tmp_path / 'affected')
    noise = target.parent / 'node_modules'
    write(noise / 'consumer.py', 'import target\n')
    with exclusion_scope(target.parent, ['included_child']):
        owner = DependsAdapter(str(target)); baseline = owner.get_structure()
        attempts = deny(monkeypatch, {child, noise})
        assert owner.get_structure() == baseline
        assert attempts == []
        assert not warning(baseline)


@pytest.mark.parametrize('policy', ['file_excluded', 'directory_gitignored'])
def test_soft_resolution_inputs_remain_required(tmp_path, monkeypatch, policy):
    root = tmp_path / 'affected'
    write(root / 'pyproject.toml', '[project]\nname="c-fixture"\n')
    write(root / 'visible.c', '#include "hidden.inc"\n')
    child = root / 'included_child'
    target = write(child / 'deep' / 'hidden.inc', 'int hidden(void);\n')
    if policy == 'directory_gitignored':
        (root / '.git').mkdir(); write(root / '.gitignore', 'included_child/\n')
    with exclusion_scope(root, ['included_child/deep/hidden.inc'] if policy == 'file_excluded' else []):
        owner = DependsAdapter(str(target)); assert owner.get_structure()['count'] == 1
        deny(monkeypatch, {child})
        result = owner.get_structure()
    assert result['count'] == 0 and warning(result)


def test_repeated_actual_directory_events_have_bounded_unique_display(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; target, child = project(root)
    children = {child}
    for number in range(6):
        directory = root / f'included_{number}'
        write(directory / 'consumer.py', 'import target\n'); children.add(directory)
    deny(monkeypatch, children)
    adapter = DependsAdapter(str(target))
    result = adapter.get_structure()
    entry = warning(result)
    assert len(adapter._graph.traversal_failures) == 7
    assert entry['count'] == 7 and len(entry['directories']) == 5
    assert 'and 2 more' in entry['message']
    assert result['warning'].count('identified directory enumeration(s) failed') == 1
    # The established helper remains a pair even when its FileSet had failures.
    files, index = ProjectResolver()._discover_files(root, frozenset({'.py'}))
    assert files == [target] and 'target.py' in index


def test_direct_element_projection_retains_current_graph_disclosure(tmp_path, monkeypatch):
    root = tmp_path / 'affected'; target, child = project(root, survivor=True)
    write(target, 'import decimal\n')
    owner = DependsAdapter(str(target))
    deny(monkeypatch, {child})
    owner.get_structure()
    result = owner.get_element('target.py')
    assert result is not None and warning(result)
    assert result['undercount_possible'] and result['_meta']['confidence'] == 'reduced'


@pytest.mark.parametrize('kind', ['clean', 'inferred_root', 'capped'])
def test_dot_without_directory_loss_keeps_legacy_bytes(tmp_path, monkeypatch, capsys, kind):
    root = tmp_path / 'affected'
    if kind != 'inferred_root':
        write(root / 'pyproject.toml', '[project]\nname="dot"\n')
    write(root / 'a.py', 'import decimal\n')
    write(root / 'b.py', 'import math\n')
    if kind == 'capped':
        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 1)
    result = DependsAdapter(str(root), query='format=dot').get_structure()
    if kind == 'capped':
        assert result['metadata']['scan_capped'] and 'warning' in result
    if kind == 'inferred_root':
        assert result['metadata']['root_inferred'] and 'warning' in result
    assert not warning(result)
    DependsRenderer.render_structure(result)
    assert capsys.readouterr().out == ('digraph depends {\n  rankdir=LR;\n'
                                       '  node [shape=box fontname="monospace" fontsize=10];\n}\n')

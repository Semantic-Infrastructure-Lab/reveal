"""Independent Depends consumers disclose actual required directory loss."""

import json
import os
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.depends import DependsAdapter, DependsRenderer
from reveal.utils.exclusions import exclusion_scope


def write(path, source):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source, encoding='utf-8')
    return path


def tree(root, *, positive=False, marker=True):
    if marker:
        write(root / 'pyproject.toml', '[project]\nname="depends-fixture"\n')
    target = write(root / 'target.py', 'VALUE = 1\n')
    child = root / 'included_child'
    write(child / 'hidden.py', 'import target\n')
    if positive:
        write(root / 'visible.py', 'import target\n')
    return target, child


def deny(monkeypatch, children, *, unknown=False):
    real = os.scandir
    children = {child.resolve() for child in children}
    attempts = []

    def scandir(path):
        if Path(path).resolve() in children:
            attempts.append(Path(path))
            if unknown:
                raise PermissionError('independent Depends unlocated enumeration loss')
            raise PermissionError(13, 'independent Depends required directory loss', str(path))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    return attempts


def warning(result):
    warnings = [entry for entry in result.get('meta', {}).get('warnings', [])
                if entry.get('type') == 'analysis_incomplete']
    assert len(warnings) == 1, 'one shared structured directory warning must reach the public answer'
    entry = warnings[0]
    assert entry['unit'] == 'directories'
    assert 'missing file population is unknown' in entry['message']
    assert 'PermissionError' in entry['message']
    assert result['warning'].count(entry['message']) == 1
    return entry


def rendered(result):
    out = StringIO()
    with redirect_stdout(out):
        DependsRenderer.render_structure(result)
    return out.getvalue()


@pytest.mark.parametrize('positive', [False, True])
@pytest.mark.parametrize('unknown', [False, True])
def test_file_json_preserves_observations_and_unknown_population(tmp_path, monkeypatch, positive, unknown):
    target, child = tree(tmp_path, positive=positive)
    deny(monkeypatch, [child], unknown=unknown)
    result = DependsAdapter(str(target)).get_structure()
    assert result['count'] == int(positive)
    entry = warning(result)
    assert entry['count'] == int(not unknown)
    if unknown:
        assert entry['unknown_directory_events'] == 1
        assert entry['directories'] == []
    else:
        assert entry['directories'] == ['included_child']
    assert result['undercount_possible'] is True
    assert result['_meta']['confidence'] == 'reduced'
    accounting = result['metadata']['scan_budget']
    assert accounting['total'] == accounting['returned'] == 1 + int(positive)
    assert accounting['exact'] is False
    assert result['metadata']['scan_capped'] is False


@pytest.mark.parametrize('positive', [False, True])
@pytest.mark.parametrize('scope', ['file', 'directory'])
def test_actual_text_qualifies_negative_and_positive_counts(tmp_path, monkeypatch, positive, scope):
    target, child = tree(tmp_path, positive=positive)
    deny(monkeypatch, [child])
    resource = target if scope == 'file' else tmp_path
    response = run(f'depends://{resource}?top=1', '--format', 'text')
    assert response.returncode == 0
    assert response.stdout.count('missing file population is unknown') == 1
    assert 'nothing imports this module' not in response.stdout
    assert 'No internal imports found.' not in response.stdout
    if positive:
        assert 'observed' in response.stdout.lower()


@pytest.mark.parametrize('output_format', ['text', 'json'])
def test_public_global_formats_retain_single_loss_disclosure_and_legacy_exit(tmp_path, monkeypatch, output_format):
    target, child = tree(tmp_path, positive=True)
    deny(monkeypatch, [child])
    response = run(f'depends://{target}', '--format', output_format)
    assert response.returncode == 0
    if output_format == 'json':
        result = json.loads(response.stdout)
        assert result['count'] == 1
        warning(result)
    else:
        assert response.stdout.count('missing file population is unknown') == 1


@pytest.mark.parametrize('positive', [False, True])
def test_dot_loss_is_commented_once_and_preserves_observed_edges(tmp_path, monkeypatch, positive):
    _, child = tree(tmp_path, positive=positive)
    deny(monkeypatch, [child])
    response = run(f'depends://{tmp_path}?format=dot&top=1', '--format', 'text')
    assert response.returncode == 0
    assert response.stdout.startswith('digraph depends {')
    assert response.stdout.rstrip().endswith('}')
    messages = [line for line in response.stdout.splitlines() if 'missing file population is unknown' in line]
    assert len(messages) == 1
    assert messages[0].lstrip().startswith('//')
    assert ('"visible.py" -> "target.py";' in response.stdout) == positive


@pytest.mark.parametrize('output_format', ['grep', 'typed'])
def test_unsupported_global_formats_keep_existing_rejection_without_discovery(tmp_path, monkeypatch, output_format):
    target, child = tree(tmp_path, positive=True)
    clean = run(f'depends://{target}', '--format', output_format)
    attempts = deny(monkeypatch, [child])
    lost = run(f'depends://{target}', '--format', output_format)
    assert attempts == []
    assert clean.returncode == lost.returncode == 2
    assert clean.stdout == lost.stdout and clean.stderr == lost.stderr


@pytest.mark.parametrize('mode', ['clean', 'inferred', 'capped'])
def test_clean_inferred_and_cap_only_dot_keep_exact_legacy_bytes(tmp_path, monkeypatch, mode):
    tree(tmp_path, marker=mode != 'inferred')
    if mode == 'capped':
        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 1)
    adapter = DependsAdapter(str(tmp_path), 'format=dot')
    result = adapter.get_structure()
    if mode == 'capped':
        assert result['metadata']['scan_capped'] is True
    if mode == 'inferred':
        assert result['metadata']['root_inferred'] is True
    edges = '' if mode == 'capped' else '  "included_child/hidden.py" -> "target.py";\n'
    assert rendered(result) == ('digraph depends {\n  rankdir=LR;\n'
                                '  node [shape=box fontname="monospace" fontsize=10];\n' + edges + '}\n')


@pytest.mark.parametrize('provenance', [False, True])
def test_decorated_mcp_retains_legacy_normal_answer_with_loss(tmp_path, monkeypatch, provenance):
    from reveal.mcp_server import _ToolFailure, reveal_query
    target, child = tree(tmp_path)
    deny(monkeypatch, [child])
    answer = reveal_query(f'depends://{target}', provenance=provenance)
    assert isinstance(answer, str) and not isinstance(answer, _ToolFailure)
    if provenance:
        result = json.loads(answer)
        warning(result)
        assert result['_meta']['confidence'] == 'reduced'
    else:
        assert answer.count('missing file population is unknown') == 1


def test_json_sidecar_and_provenance_keep_the_same_loss_evidence(tmp_path, monkeypatch):
    target, child = tree(tmp_path / 'project', positive=True)
    sidecar = tmp_path / 'answer.json'
    deny(monkeypatch, [child])
    response = run(f'depends://{target}?top=1', '--provenance', '--also-json', sidecar)
    assert response.returncode == 0
    result = json.loads(sidecar.read_text(encoding='utf-8'))
    assert result['count'] == 1
    warning(result)
    assert response.stdout.count('missing file population is unknown') == 1


@pytest.mark.parametrize('soft_policy', ['none', 'file_excluded', 'gitignored_directory'])
def test_deep_non_source_target_loss_retains_source_counts_and_discloses(tmp_path, monkeypatch, soft_policy):
    target = write(tmp_path / 'included_child' / 'deep' / 'hidden.inc', 'int hidden(void);\n')
    write(tmp_path / 'visible.c', '#include "hidden.inc"\n')
    write(tmp_path / 'pyproject.toml', '[project]\nname="target-fixture"\n')
    if soft_policy == 'gitignored_directory':
        write(tmp_path / '.git', '')
        write(tmp_path / '.gitignore', 'included_child/\n')
    patterns = ['included_child/deep/hidden.inc'] if soft_policy == 'file_excluded' else []
    with exclusion_scope(tmp_path, patterns):
        adapter = DependsAdapter(str(target))
        clean = adapter.get_structure()
        with monkeypatch.context() as context:
            deny(context, [tmp_path / 'included_child'])
            lost = adapter.get_structure()
        assert adapter.get_structure() == clean
    assert clean['count'] == 1 and lost['count'] == 0
    assert clean['metadata']['scan_budget']['returned'] == lost['metadata']['scan_budget']['returned'] == 1
    assert lost['metadata']['scan_budget']['exact'] is False
    warning(lost)
    assert lost['_meta']['confidence'] == 'reduced'


def test_all_source_loss_summary_has_no_fake_exactness_or_high_confidence(tmp_path, monkeypatch):
    write(tmp_path / 'pyproject.toml', '[project]\nname="all-lost"\n')
    write(tmp_path / 'included_child' / 'hidden.py', 'import decimal\n')
    deny(monkeypatch, [tmp_path / 'included_child'])
    result = DependsAdapter(str(tmp_path)).get_structure()
    assert result['modules'] == [] and result['total_modules'] == 0
    assert result['metadata']['scan_budget'] == {'scope': 'scan', 'limit': 5000, 'total': 0, 'returned': 0, 'exact': False}
    warning(result)
    assert result['undercount_possible'] is True
    assert result['_meta']['confidence'] == 'reduced'


def test_warning_directory_display_cap_does_not_invent_missing_file_count(tmp_path, monkeypatch):
    target = write(tmp_path / 'target.py', 'VALUE = 1\n')
    write(tmp_path / 'pyproject.toml', '[project]\nname="many-losses"\n')
    children = [tmp_path / f'child_{number}' for number in range(7)]
    for child in children:
        write(child / 'hidden.py', 'import target\n')
    deny(monkeypatch, children)
    result = DependsAdapter(str(target)).get_structure()
    entry = warning(result)
    assert entry['count'] == 7 and entry['directories'] == [f'child_{number}' for number in range(5)]
    assert 'and 2 more' in entry['message']
    assert result['metadata']['scan_budget']['total'] == result['metadata']['scan_budget']['returned'] == 1


def test_excluded_directory_is_not_attempted_and_clean_negative_remains_exact(tmp_path, monkeypatch):
    target, child = tree(tmp_path)
    attempts = deny(monkeypatch, [child])
    with exclusion_scope(tmp_path, ['included_child']):
        result = DependsAdapter(str(target)).get_structure()
    assert attempts == []
    assert result['count'] == 0 and result['undercount_possible'] is False
    assert result['_meta']['confidence'] == 'high'
    assert result['metadata']['scan_budget']['exact'] is True
    assert not any(w.get('type') == 'analysis_incomplete' for w in result.get('meta', {}).get('warnings', []))


def test_same_owner_repair_sibling_and_element_share_current_evidence(tmp_path, monkeypatch):
    target, child = tree(tmp_path / 'affected', positive=True)
    sibling_target, _ = tree(tmp_path / 'sibling', positive=True)
    owner = DependsAdapter(str(target))
    clean = owner.get_structure()
    sibling_clean = DependsAdapter(str(sibling_target)).get_structure()
    with monkeypatch.context() as context:
        deny(context, [child])
        result = owner.get_structure()
        assert result['count'] == 1
        warning(result)
        element = owner.get_element('target.py')
        assert element is not None and element['count'] == 1
        warning(element)
        assert DependsAdapter(str(sibling_target)).get_structure() == sibling_clean
    assert owner.get_structure() == clean


def test_clean_zero_stays_silent_and_high_confidence(tmp_path):
    target = write(tmp_path / 'target.py', 'VALUE = 1\n')
    write(tmp_path / 'pyproject.toml', '[project]\nname="zero"\n')
    result = DependsAdapter(str(target)).get_structure()
    assert result['count'] == 0 and result['undercount_possible'] is False
    assert result['_meta']['confidence'] == 'high'
    assert result['metadata']['scan_budget']['exact'] is True
    assert 'warning' not in result


@pytest.mark.parametrize('scope', ['file', 'directory'])
def test_existing_display_cut_metadata_survives_required_loss(tmp_path, monkeypatch, scope):
    target, child = tree(tmp_path, positive=True)
    if scope == 'file':
        write(tmp_path / 'second.py', 'import target\n')
    else:
        write(tmp_path / 'other.py', 'VALUE = 2\n')
        write(tmp_path / 'visible.py', 'import target\nimport other\n')
    deny(monkeypatch, [child])
    result = DependsAdapter(str(target if scope == 'file' else tmp_path), 'top=1').get_structure()
    warning(result)
    field = 'dependents' if scope == 'file' else 'modules'
    assert len(result[field]) == 1
    cuts = [w for w in result['meta']['warnings'] if w.get('type') == 'truncated' and w.get('field') == field]
    assert len(cuts) == 1 and cuts[0]['shown'] == 1 and cuts[0]['total'] == 2
    if scope == 'file':
        assert result['count'] == 2
        assert '2 observed file(s)' in rendered(result)
    else:
        assert result['total_modules'] == 2
        assert 'ranking is among observed modules' in rendered(result)


def test_real_scan_cap_and_loss_keep_only_the_existing_cap_population_increment(tmp_path, monkeypatch):
    target = write(tmp_path / 'target.py', 'VALUE = 1\n')
    write(tmp_path / 'pyproject.toml', '[project]\nname="cap-loss"\n')
    child = tmp_path / 'a_denied'
    write(child / 'hidden.py', 'import target\n')
    write(tmp_path / 'z_survivors' / 'first.py', 'import target\n')
    write(tmp_path / 'z_survivors' / 'second.py', 'import target\n')
    monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 2)
    deny(monkeypatch, [child])
    result = DependsAdapter(str(target)).get_structure()
    warning(result)
    assert result['metadata']['scan_capped'] is True
    assert result['metadata']['scan_budget'] == {'scope': 'scan', 'limit': 2, 'total': 3, 'returned': 2, 'exact': False}

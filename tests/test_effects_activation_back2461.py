"""Approved effects modes preserve existing source-based answers and controls."""
import json
from pathlib import PurePosixPath

import pytest

from conftest import _run_reveal_direct
from test_conformance_matrix import EXPECTED, LANGUAGES, _sample_path
from test_nav_traversal_consumer_back2025 import discovery_fault
from test_nav_traversal_loss_back2025 import fault
from test_transitive_walk_back2098 import twins

pytestmark = pytest.mark.component

MODES = [('--sideeffects', ()), ('--fanout', ('--in-loops',)), ('--statewrites', ('--state',))]


def _without_legacy_correction(answer, old):
    meta = answer['meta']
    notes = [w for w in meta.get('warnings', []) if w.get('type') == 'retired_spelling']
    assert len(notes) == 1 and notes[0]['field'] == 'flag:' + old
    meta['warnings'] = [w for w in meta['warnings'] if w not in notes]
    if not meta['warnings']:
        meta.pop('warnings')
    return answer


def _run(path, element, *flags):
    return _run_reveal_direct(path, *([element] if element else []), *flags)


def _same(path, element, old, new, extra=()):
    for fmt in ('json', 'text'):
        before = _run(path, element, old, *extra, '--format', fmt)
        after = _run(path, element, '--effects', *new, *extra, '--format', fmt)
        assert before.returncode == after.returncode == 0, (before.stderr, after.stderr)
        if fmt == 'json':
            canonical = json.loads(after.stdout)
            assert not any(w.get('type') == 'retired_spelling' for w in canonical['meta'].get('warnings', []))
            assert _without_legacy_correction(json.loads(before.stdout), old) == canonical
        else:
            assert before.stdout == after.stdout
        from reveal.cli.invocation import RETIREMENTS
        correction = f"note: {RETIREMENTS['flag:' + old].text}\n"
        assert before.stderr.count(correction) == 1
        assert before.stderr.replace(correction, '', 1) == after.stderr
        assert 'deprecated' not in after.stderr


@pytest.mark.parametrize('language', LANGUAGES)
@pytest.mark.parametrize('old,new', MODES)
def test_conformance_modes_preserve_complete_answers_and_independent_truth(language, old, new):
    expected = EXPECTED[language]
    element = expected['entry_function'] if old == '--sideeffects' else expected['batch_element']
    path = _sample_path(language)
    _same(path, element, old, new)
    result = _run(path, element, '--effects', *new, '--format', 'json')
    assert result.returncode == 0, result.stderr
    rows = json.loads(result.stdout)['findings']
    if old == '--fanout':
        assert len(rows) == 1
        rows = rows[0]['effects']
    truth = expected[{'--sideeffects': 'sideeffects', '--fanout': 'fanout_effects', '--statewrites': 'statewrites'}[old]]
    assert [{'kind': row['kind'], 'line': row['line']} for row in rows] == truth


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'root.py').write_text(
        'import logging\nimport left\nimport right\nstate = {}\n'
        'def entry(items):\n    logging.info("own")\n    state["x"] = 1\n'
        '    for item in items:\n        for other in items:\n            logging.info(item)\n'
        '    left.send()\n    right.send()\n'
        'def empty():\n    return 1\n', encoding='utf-8')
    (tmp_path / 'left.py').write_text('import requests\ndef send():\n    requests.get("same")\n    finish()\n'
                                      'def finish():\n    logging.info("deep")\n', encoding='utf-8')
    (tmp_path / 'right.py').write_text('import requests\ndef send():\n    requests.get("same")\n', encoding='utf-8')
    return tmp_path / 'root.py'


@pytest.mark.parametrize('old,new', MODES)
@pytest.mark.parametrize('element,extra', [('entry', ()), ('entry', ('--range', '6-10')), (':6-10', ()), (None, ())])
def test_selection_routes_keep_complete_answer(project, old, new, element, extra):
    _same(project, element, old, new, extra)


@pytest.mark.parametrize('depth', [None, 1, 8])
def test_loop_depth_keeps_nested_groups_and_pruning(project, depth):
    extra = () if depth is None else ('--depth', str(depth))
    _same(project, 'entry', '--fanout', ('--in-loops',), extra)
    result = _run(project, 'entry', '--effects', '--in-loops', *extra, '--format', 'json')
    data = json.loads(result.stdout)
    assert data['meta']['depth'] == (3 if depth is None else depth)
    assert len(data['findings']) == (1 if depth == 1 else 2)
    assert data['meta']['depth_limited'] == (depth == 1)


@pytest.mark.parametrize('depth', [None, 1, 2, 5])
def test_transitive_preserves_sources_and_breadth_order(project, depth):
    extra = ('--transitive',) + (() if depth is None else ('--depth', str(depth)))
    _same(project, 'entry', '--sideeffects', (), extra)
    data = json.loads(_run(project, 'entry', '--effects', *extra, '--format', 'json').stdout)
    children = [row for row in data['findings'] if row.get('hop', 0) > 0]
    assert [(PurePosixPath(row['file']).name, row['line'], row['hop']) for row in children] == [
        ('left.py', 3, 1), ('right.py', 3, 1)] + ([] if depth == 1 else [('left.py', 6, 2)])
    assert all('file' not in row for row in data['findings'] if row['hop'] == 0)


@pytest.mark.parametrize('flags,diagnostic', [
    (('--in-loops',), '--effects'), (('--state',), '--effects'),
    (('--effects', '--in-loops', '--state'), 'exclusive'),
    (('--effects', '--in-loops', '--transitive'), '--transitive'),
    (('--effects', '--state', '--transitive'), '--transitive'),
    (('--effects', '--depth', '1'), '--depth'),
    (('--effects', '--state', '--depth', '1'), '--depth'),
    *((('--effects', '--transitive', '--depth', value), '--depth') for value in ('0', '-1', '6', '1.5')),
    *((('--effects', '--in-loops', '--depth', value), '--depth') for value in ('0', '-1')),
    *((('--effects', flag), 'combine') for flag in ('--sideeffects', '--fanout', '--statewrites', '--boundary', '--flow')),
])
def test_invalid_requests_are_usage_errors_before_analysis(project, flags, diagnostic):
    result = _run(project, 'entry', *flags, '--format', 'json')
    assert result.returncode == 2
    assert result.stdout == ''
    assert diagnostic in result.stderr


@pytest.mark.parametrize('old,new', MODES)
def test_empty_is_success_and_legacy_names_report_one_correction(project, old, new):
    _same(project, 'empty', old, new)
    result = _run(project, 'empty', old, '--format', 'json')
    notes = [w for w in json.loads(result.stdout)['meta']['warnings'] if w['type'] == 'retired_spelling']
    assert len(notes) == 1 and notes[0]['old'] == old
    assert '--effects' in notes[0]['replacement']
    assert result.stderr.count('deprecated') == 1


def test_legacy_boundary_depth_policy_remains_unmodified(project):
    result = _run(project, 'entry', '--boundary', '--transitive', '--depth', '0', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert any(row.get('hop') == 2 for row in json.loads(result.stdout)['findings'])


def test_new_transitive_keeps_discovery_loss_warning(project, discovery_fault):
    blocked = project.parent / 'blocked'
    blocked.mkdir()
    (blocked / 'hidden.py').write_text('def hidden():\n    return 1\n', encoding='utf-8')
    discovery_fault['denied'][blocked] = blocked
    _same(project, 'entry', '--sideeffects', (), ('--transitive',))
    result = _run(project, 'entry', '--effects', '--transitive', '--format', 'json')
    assert any('directory enumeration(s) failed' in note for note in json.loads(result.stdout)['warnings'])


def test_tsx_is_only_a_mode_preservation_smoke(tmp_path):
    path = tmp_path / 'sample.tsx'
    path.write_text('function work(items) { for (const item of items) { console.log(item); } this.value = 1; }\n', encoding='utf-8')
    for old, new in MODES:
        _same(path, 'work', old, new)


def test_new_transitive_keeps_ambiguity_with_no_guessed_effects(twins):
    path = twins / 'root_amb.py'
    _same(path, 'run_amb', '--sideeffects', (), ('--transitive',))
    data = json.loads(_run(path, 'run_amb', '--effects', '--transitive', '--format', 'json').stdout)
    assert data['findings'] == []
    assert any('ambiguous' in note for note in data['warnings'])


def test_new_transitive_keeps_file_analysis_loss(project, fault):
    unreadable = project.parent / 'unreadable.py'
    unreadable.write_text('def unrelated():\n    return 1\n', encoding='utf-8')
    fault['unreadable'] = unreadable.resolve()
    _same(project, 'entry', '--sideeffects', (), ('--transitive',))
    data = json.loads(_run(project, 'entry', '--effects', '--transitive', '--format', 'json').stdout)
    assert any('could not be analyzed' in note for note in data['warnings'])


@pytest.mark.parametrize('extra', [('--meta',), ('--check',), ('--head', '1'), ('--tail', '0'),
                                  ('--grep', 'logging'), ('--name', 'entry'), ('--sort', 'name'), ('--type', 'function')])
def test_new_effects_reject_preempting_or_unused_views(project, extra):
    result = _run(project, None, '--effects', *extra, '--format', 'json')
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stdout == ''
    assert '--effects' in result.stderr
    if extra[0] in ('--head', '--tail'):
        assert '--range' in result.stderr


def test_new_effects_reject_directory_view_without_changing_legacy(project):
    rejected = _run(project.parent, None, '--effects', '--in-loops', '--format', 'json')
    assert rejected.returncode == 2, (rejected.stdout, rejected.stderr)
    assert rejected.stdout == '' and 'file' in rejected.stderr
    legacy = _run(project.parent, None, '--fanout', '--format', 'json')
    assert legacy.returncode == 0


def test_direct_handle_file_rejects_effects_when_show_meta_preempts(project):
    from reveal.cli.defaults import _default_args
    from reveal.errors import NavRequestValidationError
    from reveal.file_handler import handle_file

    with pytest.raises(NavRequestValidationError, match='--effects'):
        handle_file(str(project), 'entry', True, 'json', _default_args(effects=True))


@pytest.mark.parametrize('extra', [('--extract', 'domains'), ('--check-acl',), ('--validate-nginx-acme',),
                                  ('--global-audit',), ('--check-conflicts',), ('--cpanel-certs',), ('--diagnose',)])
def test_new_effects_reject_nginx_views_that_preempt_analysis(tmp_path, extra):
    path = tmp_path / 'nginx.conf'
    path.write_text('events {}\nhttp { server { listen 80; } }\n', encoding='utf-8')
    result = _run(path, None, '--effects', *extra)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stdout == '' and '--effects' in result.stderr


def test_new_effects_reject_frontmatter_schema_view(tmp_path):
    path, schema = tmp_path / 'guide.md', tmp_path / 'schema.json'
    path.write_text('---\ntitle: Example\n---\n# Example\n', encoding='utf-8')
    schema.write_text('{"name": "Example", "required_fields": ["title"]}', encoding='utf-8')
    result = _run(path, None, '--effects', '--validate-schema', str(schema), '--format', 'json')
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stdout == '' and '--effects' in result.stderr


@pytest.mark.parametrize('flag', ['--show-ast', '--capabilities', '--explain-file', '--decorator-stats'])
def test_new_effects_reject_early_special_modes(project, flag):
    result = _run(project, None, '--effects', flag)
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stdout == '' and '--effects' in result.stderr


@pytest.mark.parametrize('target', ['ast', 'help', 'list'])
def test_new_effects_require_a_file_target_instead_of_uri_or_batch(project, tmp_path, target):
    if target == 'ast':
        path = 'ast://' + str(project)
    elif target == 'help':
        path = 'help://quick'
    else:
        listing = tmp_path / 'targets.txt'
        listing.write_text(str(project) + '\n', encoding='utf-8')
        path = '@' + str(listing)
    result = _run(path, None, '--effects', '--format', 'json')
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert result.stdout == '' and '--effects' in result.stderr


def test_new_effects_reject_pathless_discovery_and_stdin(project):
    from conftest import _run_reveal_in

    discovery = _run_reveal_direct('--effects', '--languages', '--format', 'json')
    assert discovery.returncode == 2 and discovery.stdout == '' and '--effects' in discovery.stderr
    batch = _run_reveal_in(project.parent, '--effects', '--stdin', stdin=str(project) + '\n')
    assert batch.returncode == 2 and batch.stdout == '' and '--effects' in batch.stderr


def test_new_effects_are_not_a_subcommand_analysis(project):
    result = _run_reveal_direct('check', str(project), '--effects', '--format', 'json')
    assert result.returncode == 2 and result.stdout == '' and '--effects' in result.stderr

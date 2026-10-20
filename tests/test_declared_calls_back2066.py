"""calls is a declared noun (BACK-2066 slice C1).

Typed parameters with no coercion, exactly one mode per request, D6 exits (0 complete, 2 rejected
before analysis, 3 required analysis or output failed) and a `reveal calls` subcommand generated
from the same declaration, answering like `calls://` through the one execution owner.
"""
import json
import os
from pathlib import Path

import pytest

from conftest import _run_reveal_direct as run

APP = '''\
import os
from pkg.util import helper, fmt


def load(key):
    return os.getenv(key)


def serve(key):
    value = load(key)
    if value:
        return helper(fmt(value))
    return len(key)


def main():
    serve('HOME')
    serve('PATH')


def unused_thing():
    return 42
'''

UTIL = '''\
def helper(x):
    return fmt(x).strip()


def fmt(x):
    return str(x)


class Box:
    def open(self):
        return helper(self)

    def close(self):
        return 0
'''


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    (root / 'pkg').mkdir(parents=True)
    (root / 'app.py').write_text(APP, encoding='utf-8')
    (root / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    (root / 'pkg' / 'util.py').write_text(UTIL, encoding='utf-8')
    return root


# mode -> (subcommand flags after `calls proj`, URI query after `calls://proj?`)
MODES = {
    'target': (['--target', 'helper'], 'target=helper'),
    'target_depth': (['--target', 'fmt', '--depth', '2'], 'target=fmt&depth=2'),
    'callees': (['--callees', 'serve'], 'callees=serve'),
    'callees_builtins': (['--callees', 'serve', '--builtins'], 'callees=serve&builtins=true'),
    'root': (['--root', 'main', '--depth', '3'], 'root=main&depth=3'),
    'rank': (['--rank', 'callers', '--top', '3'], 'rank=callers&top=3'),
    'uncalled': (['--uncalled', '--type', 'function'], 'uncalled&type=function'),
    'modules': (['--modules'], 'modules'),
}


def spellings(flags, query, resource='proj'):
    return ['calls', resource, *flags], [f'calls://{resource}?{query}' if query else f'calls://{resource}']


def both(flags, query, *extra, resource='proj'):
    cli, uri = spellings(flags, query, resource)
    return run(*cli, *extra), run(*uri, *extra)


def uri_first(flags, query, *extra, resource='proj'):
    """Both spellings, the URI's answer first: its assertion is the one that fails on the old code."""
    cli, uri = both(flags, query, *extra, resource=resource)
    return uri, cli


@pytest.mark.parametrize('mode', sorted(MODES))
@pytest.mark.parametrize('provenance', [False, True])
def test_subcommand_and_uri_give_equal_json(project, mode, provenance):
    extra = ['--format', 'json', '--no-gitignore'] + (['--provenance'] if provenance else [])
    a, b = both(*MODES[mode], *extra)
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left['type'].startswith('calls_')
    if provenance:
        assert left['execution'].pop('command').startswith('reveal calls proj')
        assert right['execution'].pop('command').startswith('reveal calls://proj')
    assert left == right
    assert a.stderr == b.stderr


@pytest.mark.parametrize('mode', sorted(MODES))
def test_subcommand_and_uri_give_equal_text(project, mode):
    a, b = both(*MODES[mode], '--no-gitignore')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    assert a.stdout.strip()
    assert a.stdout == b.stdout
    assert a.stderr == b.stderr


@pytest.mark.parametrize('depth', ['abc', '1.5', 'true', ''])
def test_malformed_depth_is_usage_naming_depth(project, depth):
    for result in uri_first(['--target', 'helper', '--depth', depth], f'target=helper&depth={depth}', '--format', 'json'):
        assert result.returncode == 2, result.stderr
        assert json.loads(result.stdout)['type'] == 'calls_query'
        assert 'depth' in result.stderr
        assert 'Traceback' not in result.stderr


@pytest.mark.parametrize('depth,effective', [('9', 5), ('-2', 1), ('+3', 3), ('0', 1)])
def test_depth_is_clamped_one_to_five(project, depth, effective):
    for result in uri_first(['--target', 'helper', '--depth', depth], f'target=helper&depth={depth}', '--format', 'json'):
        assert result.returncode == 0, result.stderr
        assert json.loads(result.stdout)['depth'] == effective


def test_numeric_name_is_a_name_not_a_crash(project):
    for result in uri_first(['--target', '123'], 'target=123', '--format', 'json'):
        assert result.returncode == 0, result.stderr
        answer = json.loads(result.stdout)
        assert answer['type'] == 'calls_query'
        assert answer['target'] == '123'
        assert answer['total_callers'] == 0


@pytest.mark.parametrize('flags,query,names', [
    (['--target', 'helper', '--callees', 'serve'], 'target=helper&callees=serve', ('target', 'callees')),
    (['--root', 'main', '--target', 'helper'], 'root=main&target=helper', ('root', 'target')),
    (['--rank', 'callers', '--uncalled'], 'rank=callers&uncalled', ('rank', 'uncalled')),
    (['--modules', '--callees', 'serve'], 'modules&callees=serve', ('callees', 'modules')),
])
def test_two_modes_are_rejected_naming_both(project, flags, query, names):
    results = uri_first(flags, query, '--format', 'json')
    for result in results:
        assert result.returncode == 2, result.stderr
        answer = json.loads(result.stdout)
        assert answer['type'].startswith('calls_')
        for name in names:
            assert name in answer['error'] and name in result.stderr
    assert results[0].stdout == results[1].stdout


def test_a_false_presence_mode_is_not_a_second_mode(project):
    result = run('calls://proj?target=helper&uncalled=false', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['type'] == 'calls_query'


def test_missing_mode_is_usage(project):
    for result in uri_first([], ''):
        assert result.returncode == 2, result.stderr
        assert 'target' in result.stderr


@pytest.mark.parametrize('query', ['callees', 'target', 'root', 'target=helper&callees'])
def test_bare_name_flag_is_usage_with_its_message(project, query):
    result = run(f'calls://proj?{query}', '--format', 'json')
    assert result.returncode == 2, result.stderr
    assert 'needs a function name' in result.stderr


@pytest.mark.parametrize('flags,query', [
    (['--rank', 'callers', '--top', '-1'], 'rank=callers&top=-1'),
    (['--rank', 'callers', '--top', 'abc'], 'rank=callers&top=abc'),
    (['--rank', 'often'], 'rank=often'),
    (['--uncalled', '--type', 'klass'], 'uncalled&type=klass'),
    ([], 'callees=serve&builtins=maybe'),
    ([], 'target=helper&format=xml'),
])
def test_malformed_values_are_usage(project, flags, query):
    results = uri_first(flags, query, '--format', 'json') if flags else (run(f'calls://proj?{query}', '--format', 'json'),)
    for result in results:
        assert result.returncode == 2, result.stderr
        assert json.loads(result.stdout)['error']


def test_shorthand_selects_target_in_both_spellings(project):
    a, b = both([], '', '--format', 'json', resource='proj/pkg/util.py:fmt')
    assert a.returncode == b.returncode == 0, (a.stderr, b.stderr)
    left, right = json.loads(a.stdout), json.loads(b.stdout)
    assert left == right
    assert left['target'] == 'fmt' and left['total_callers'] == 1
    assert left['source'] == 'proj/pkg/util.py'


def test_explicit_mode_beats_the_shorthand(project):
    result = run('calls://proj/pkg/util.py:fmt?callees=helper', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert (answer['type'], answer['target']) == ('calls_callees', 'helper')


def test_ignored_depth_warning_is_unchanged(project):
    for result in uri_first(['--callees', 'serve', '--depth', '3'], 'callees=serve&depth=3'):
        assert result.returncode == 0, result.stderr
        assert "Query param 'depth' for calls:// applies to ?target and ?root only" in result.stderr


@pytest.mark.parametrize('gate,expected', [('none', 0), ('findings', 2)])
def test_fail_on_is_none_only(project, gate, expected):
    runs = [run('calls', 'proj', '--target', 'helper', '--fail-on', gate),
            run('--fail-on', gate, 'calls', 'proj', '--target', 'helper'),
            run('calls://proj?target=helper', '--fail-on', gate)]
    assert [r.returncode for r in runs] == [expected] * 3, [r.stderr for r in runs]
    if expected == 2:
        assert all('not supported' in r.stderr for r in runs)


def test_known_loss_exits_three_and_keeps_the_answer(project, monkeypatch):
    lost = project / 'lost'
    lost.mkdir()
    (lost / 'gone.py').write_text('def gone():\n    return helper(1)\n', encoding='utf-8')
    real = os.scandir

    def scandir(path='.'):
        if Path(path).resolve() == lost.resolve():
            raise PermissionError(13, 'denied for the test', str(path))
        return real(path)

    monkeypatch.setattr(os, 'scandir', scandir)
    for result in uri_first(['--target', 'helper'], 'target=helper', '--format', 'json'):
        assert result.returncode == 3, result.stderr
        answer = json.loads(result.stdout)
        assert answer['total_callers'] == 2
        assert any(w.get('type') == 'analysis_incomplete' for w in answer['meta']['warnings'])


def test_directory_named_calls_in_cwd(project):
    shadow = project.parent / 'calls'
    shadow.mkdir()
    (shadow / 'thing.py').write_text('def thing():\n    return 1\n', encoding='utf-8')
    verb = run('calls', '--uncalled', '--format', 'json', '--no-gitignore')
    assert verb.returncode == 0, verb.stderr
    assert 'note: ./calls/ exists' in verb.stderr
    assert json.loads(verb.stdout)['type'] == 'calls_uncalled'
    as_path = run('calls/', '--format', 'json')
    assert as_path.returncode == 0, as_path.stderr
    assert 'calls_' not in json.loads(as_path.stdout).get('type', '')


def test_generated_help_names_every_mode_and_its_exits():
    result = run('calls', '--help')
    assert result.returncode == 0, result.stderr
    for flag in ('--target NAME', '--callees NAME', '--root NAME', '--depth N', '--rank callers',
                 '--top N', '--uncalled', '--modules', '--builtins', '--external', '--test-framework'):
        assert flag in result.stdout, flag
    assert 'clamped 1-5' in result.stdout
    assert 'Exit codes:' in result.stdout
    assert '  3  ' in result.stdout and 'findings gate matched' not in result.stdout


def test_mcp_usage_rejection_is_a_tool_error_naming_both(project):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    response = reveal_query(f'calls://{project.as_posix()}?target=helper&callees=serve')
    assert isinstance(response, _ToolFailure)
    assert 'target' in str(response) and 'callees' in str(response)
    answer = reveal_query(f'calls://{project.as_posix()}?target=helper')
    assert not isinstance(answer, _ToolFailure)
    assert 'Callers of: helper' in answer

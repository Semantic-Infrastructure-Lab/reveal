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
    # Nothing defines or calls `123`: an absent name exits 2 since slice C2 (decision d).
    for result in uri_first(['--target', '123'], 'target=123', '--format', 'json'):
        assert result.returncode == 2, result.stderr
        assert 'Traceback' not in result.stderr
        answer = json.loads(result.stdout)
        assert answer['type'] == 'calls_query'
        assert answer['target'] == '123'
        assert answer['total_callers'] == 0
        assert answer['error'] == "Function '123' not found in proj"


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


def test_shorthand_with_an_explicit_mode_is_two_modes(project):
    # It answered the explicit mode and ignored :fmt silently until BACK-2102.
    result = run('calls://proj/pkg/util.py:fmt?callees=helper', '--format', 'json')
    assert result.returncode == 2, result.stderr
    answer = json.loads(result.stdout)
    assert answer['type'] == 'calls_callees'
    assert 'one mode per request' in answer['error']


def test_ignored_depth_warning_names_the_modes_that_walk(project):
    for result in uri_first(['--rank', 'callers', '--depth', '3'], 'rank=callers&depth=3'):
        assert result.returncode == 0, result.stderr
        assert "Query param 'depth' for calls:// applies to ?callers, ?callees and ?root only" in result.stderr


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
    assert '\n  3  ' in result.stdout
    assert '\n  1  ' not in result.stdout, 'calls has no findings gate'


def test_mcp_usage_rejection_is_a_tool_error_naming_both(project):
    pytest.importorskip('mcp')
    from reveal.mcp_server import _ToolFailure, reveal_query
    response = reveal_query(f'calls://{project.as_posix()}?target=helper&callees=serve')
    assert isinstance(response, _ToolFailure)
    assert 'target' in str(response) and 'callees' in str(response)
    answer = reveal_query(f'calls://{project.as_posix()}?target=helper')
    assert not isinstance(answer, _ToolFailure)
    assert 'Callers of: helper' in answer


# The shared ParamSpec owner gained three small pieces for this declaration.

def test_param_value_error_keeps_the_converters_message_and_others_stay_generic():
    from reveal.utils.query_parser import ParamSpec, ParamValueError

    def authored(value):
        raise ParamValueError("'x' needs a function name: x=<name>")

    def plain(value):
        raise ValueError('internal detail')

    with pytest.raises(ValueError, match="^'x' needs a function name"):
        ParamSpec('x', 'string', '', None, authored).validate(True)
    with pytest.raises(ValueError, match="^x must be a valid string, got 'v'$"):
        ParamSpec('x', 'string', '', None, plain).validate('v')


def test_an_absent_optional_choice_is_its_default_and_a_wrong_one_rejects():
    from reveal.utils.query_parser import ParamSpec, nonempty_scalar
    spec = ParamSpec('rank', 'string', '', None, nonempty_scalar, choices=('callers',))
    assert spec.validate(None) is None
    assert spec.validate('callers') == 'callers'
    with pytest.raises(ValueError, match='one of'):
        spec.validate('often')


@pytest.mark.parametrize('value,expected', [(4, 4), ('+3', 3), ('-2', 1), (' 9 ', 5), (0, 1)])
def test_clamped_whole_accepts_signed_whole_values(value, expected):
    from reveal.utils.query_parser import clamped_whole
    assert clamped_whole(value, 1, 5) == expected


@pytest.mark.parametrize('value', [True, False, 1.0, '1.5', '2.0', '1e2', 'abc', '', None])
def test_clamped_whole_rejects_everything_else(value):
    from reveal.utils.query_parser import clamped_whole
    with pytest.raises(ValueError):
        clamped_whole(value, 1, 5)


@pytest.mark.parametrize('value', ['', '   ', 'a\x00b', True, 123, None])
def test_nonempty_scalar_rejects_non_names(value):
    from reveal.utils.query_parser import nonempty_scalar
    with pytest.raises(ValueError):
        nonempty_scalar(value)

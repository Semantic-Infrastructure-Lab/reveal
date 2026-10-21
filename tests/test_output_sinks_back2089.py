"""``--output FORMAT[=PATH]`` is the output-sink spelling; ``--also-json`` is its retired JSON file sink (BACK-2089 slices 5a, 5b).

A bare FORMAT is the stdout sink (``--format``); ``json=PATH`` writes the artifact the old flag wrote. Bad sinks exit 2
before any scan; ``--also-json`` keeps answering and prints a replaced-by note. Slice 5b: ``text=PATH`` and ``grep=PATH``
render the one result a second time into a file (where the target renders that format), and several file sinks may be given.
"""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.cli.invocation import RETIREMENTS


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    return tmp_path


def _artifact(path):
    """The artifact minus the retired_spelling warning only the old spelling carries."""
    doc = json.loads(path.read_text(encoding='utf-8'))
    meta = doc.get('meta')
    if isinstance(meta, dict) and 'warnings' in meta:
        meta['warnings'] = [w for w in meta['warnings'] if w.get('code') != 'retired_spelling']
        if not meta['warnings']:
            del meta['warnings']
    if doc.get('meta') == {}:
        del doc['meta']
    return doc


@pytest.mark.parametrize('argv', [
    lambda p, out: ['check', str(p), '--output', f'json={out}'],
    lambda p, out: ['check', str(p / 'a.py'), '--output', f'json={out}'],
    lambda p, out: ['hotspots', str(p), '--output', f'json={out}'],
    lambda p, out: [f'ast://{p}', '--output', f'json={out}'],
], ids=['check-dir', 'check-file', 'declared-noun', 'uri'])
def test_a_json_file_sink_writes_what_also_json_wrote(project, tmp_path_factory, argv):
    out_new = tmp_path_factory.mktemp('new') / 'o.json'
    out_old = tmp_path_factory.mktemp('old') / 'o.json'
    new = run(*argv(project, out_new))
    old = run(*argv(project, out_old)[:-2], '--also-json', str(out_old))
    assert new.returncode == old.returncode
    assert 'deprecated' not in new.stderr, new.stderr
    assert _artifact(out_new) == _artifact(out_old)


def test_also_json_alone_answers_with_one_note(project, tmp_path):
    out = tmp_path / 'o.json'
    result = run('check', str(project), '--also-json', str(out))
    assert result.stderr.count(f'note: {RETIREMENTS["flag:--also-json"].text}') == 1, result.stderr
    assert out.exists()


def test_a_bare_format_is_the_stdout_sink(project):
    result = run('check', str(project), '--output', 'json')
    assert json.loads(result.stdout)['type'] == 'check'


@pytest.mark.parametrize('extra, needle', [
    (['--output', 'xml=x'], "unknown format 'xml'"),
    (['--output', 'json='], 'names no PATH'),
    (['--output', 'text', '--output', 'json'], 'two stdout sinks'),
    (['--output', 'grep', '--format', 'text'], 'same sink'),
    (['--output', 'text=@PATH@'], 'check writes only json file sinks'),
    (['--output', 'grep=@PATH@'], 'check writes only json file sinks'),
    (['--output', 'json=@PATH@', '--also-json', '@PATH@2'], 'both name the artifact'),
])
def test_a_bad_sink_exits_2_before_any_scan_and_writes_nothing(project, tmp_path, extra, needle):
    out = str(tmp_path / 'o.json')
    argv = [t.replace('@PATH@', out) for t in extra]
    result = run('check', str(project), *argv)
    assert result.returncode == 2, result.stderr
    assert needle in result.stderr, result.stderr
    assert result.stdout == ''
    assert not (tmp_path / 'o.json').exists()


def test_an_unwritable_json_sink_exits_3_and_keeps_the_primary_answer(project, tmp_path):
    result = run('check', str(project), '--output', f'json={tmp_path / "no-such-dir" / "o.json"}')
    assert result.returncode == 3, result.stderr
    assert 'Checked' in result.stdout


def test_a_command_that_writes_no_artifact_rejects_the_sink_and_names_it(project, tmp_path):
    result = run(str(project / 'a.py'), '--output', f'json={tmp_path / "o.json"}')
    assert result.returncode == 2
    assert '--output json=PATH' in result.stderr


# ---- slice 5b: non-JSON file sinks, several file sinks, one failure policy (BACK-2089) ----

def _assert_clean_json(text):
    return json.loads(text)


def test_a_text_file_sink_beside_a_json_stdout_holds_the_text_render(project, tmp_path):
    plain = run('hotspots', str(project), '--format', 'text')
    text_out = tmp_path / 'o.txt'
    both = run('hotspots', str(project), '--format', 'json', '--output', f'text={text_out}')
    assert both.returncode == 0, both.stderr
    assert _assert_clean_json(both.stdout)['type'] == 'hotspots_scan'
    assert text_out.read_text(encoding='utf-8') == plain.stdout
    assert plain.stdout.startswith('\nHotspots:'), plain.stdout


@pytest.mark.parametrize('kind', ['json', 'text'])
def test_a_file_sink_does_not_change_the_stdout_answer(project, tmp_path, kind):
    """Negative control: the stdout of a run with a file sink is the stdout of the same run without one."""
    bare = run('hotspots', str(project), '--format', 'json')
    sunk = run('hotspots', str(project), '--format', 'json', '--output', f'{kind}={tmp_path / "o.out"}')
    assert sunk.returncode == bare.returncode == 0, sunk.stderr

    def strip(doc):
        doc = json.loads(doc)
        doc.pop('meta', None)
        return doc
    assert strip(sunk.stdout) == strip(bare.stdout)


def test_a_grep_file_sink_on_a_uri_holds_the_grep_render(project, tmp_path):
    uri = f'ast://{project}?type=function'
    plain = run(uri, '--format', 'grep')
    grep_out = tmp_path / 'o.grep'
    both = run(uri, '--output', 'json', '--output', f'grep={grep_out}')
    assert both.returncode == plain.returncode == 0, both.stderr
    assert json.loads(both.stdout)['type']
    assert grep_out.read_text(encoding='utf-8') == plain.stdout
    assert 'a.py:1:f' in plain.stdout


def test_several_file_sinks_are_each_written_once(project, tmp_path):
    out_json, out_json2, out_text = tmp_path / 'a.json', tmp_path / 'b.json', tmp_path / 'c.txt'
    result = run('hotspots', str(project), '--output', f'json={out_json}', '--output', f'json={out_json2}',
                 '--output', f'text={out_text}')
    assert result.returncode == 0, result.stderr
    assert out_json.read_text(encoding='utf-8') == out_json2.read_text(encoding='utf-8')
    assert json.loads(out_json.read_text(encoding='utf-8'))['type'] == 'hotspots_scan'
    assert out_text.read_text(encoding='utf-8') == result.stdout


def test_several_json_sinks_on_check_are_each_written(project, tmp_path):
    first, second = tmp_path / 'a.json', tmp_path / 'b.json'
    result = run('check', str(project), '--output', f'json={first}', '--output', f'json={second}')
    assert result.returncode in (0, 1), result.stderr
    assert _artifact(first) == _artifact(second)
    assert _artifact(first)['type'] == 'check'


def test_a_format_the_target_does_not_render_is_a_sink_error_before_the_scan(project, tmp_path):
    """hotspots renders text and json only; grep=PATH is refused like --format grep, with exit 2 and no file."""
    out = tmp_path / 'o.grep'
    result = run('hotspots', str(project), '--output', f'grep={out}')
    assert result.returncode == 2, result.stderr
    assert 'grep is not supported by reveal hotspots' in result.stderr, result.stderr
    assert result.stdout == ''
    assert not out.exists()


@pytest.mark.parametrize('bad_first', [True, False], ids=['bad-first', 'bad-last'])
def test_one_failing_sink_exits_3_and_the_other_sinks_and_the_answer_survive(project, tmp_path, bad_first):
    good, bad = tmp_path / 'good.json', tmp_path / 'no-such-dir' / 'bad.txt'
    sinks = [f'text={bad}', f'json={good}'] if bad_first else [f'json={good}', f'text={bad}']
    result = run('hotspots', str(project), '--output', sinks[0], '--output', sinks[1])
    assert result.returncode == 3, result.stderr
    assert 'Hotspots:' in result.stdout
    assert json.loads(good.read_text(encoding='utf-8'))['type'] == 'hotspots_scan'
    assert str(bad) in result.stderr


def test_an_unwritable_sink_on_a_uri_exits_3_with_the_answer_not_a_traceback(project, tmp_path):
    result = run(f'ast://{project}?type=function', '--output', f'json={tmp_path / "no-such-dir" / "o.json"}')
    assert result.returncode == 3, result.stderr
    assert 'Traceback' not in result.stderr
    assert 'a.py' in result.stdout


@pytest.mark.parametrize('argv', [
    lambda p, out: ['hotspots', str(p), '--output', f'json={out}'],
    lambda p, out: ['check', str(p), '--output', f'json={out}'],
    lambda p, out: [f'ast://{p}?type=function', '--output', f'json={out}'],
], ids=['declared-noun', 'check', 'uri'])
def test_a_sink_that_was_honored_is_not_reported_as_having_no_effect(project, tmp_path, argv):
    result = run(*argv(project, tmp_path / 'o.json'))
    assert 'has no effect' not in result.stderr, result.stderr
    assert (tmp_path / 'o.json').exists()

"""``--output FORMAT[=PATH]`` is the output-sink spelling; ``--also-json`` is its retired JSON file sink (BACK-2089 slice 5a).

A bare FORMAT is the stdout sink (``--format``); ``json=PATH`` writes the artifact the old flag wrote. Bad sinks exit 2
before any scan; ``--also-json`` keeps answering and prints a replaced-by note.
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
    (['--output', 'text=@PATH@'], 'only json file sinks'),
    (['--output', 'json=@PATH@', '--output', 'json=@PATH@2'], 'only one file sink'),
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

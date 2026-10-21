"""``reveal check DIR --output text=PATH --output grep=PATH`` renders every sink from ONE scan (BACK-2145).

check builds its text, grep and json reports per ``--format`` inside the scan, so a second sink used to mean a second
scan (and exit 2 for text and grep). The DD scan paid for that three times per rule group. The scan entry point is
``file_checker._results_in_sorted_order``; a spy on it is the deterministic counter (no wall time).
"""
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.cli import file_checker

BARE_EXCEPT = 'def f():\n    try:\n        return 1\n    except:\n        pass\n'


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / 'tree'
    root.mkdir()
    (root / 'a.py').write_text(BARE_EXCEPT + '\n' + BARE_EXCEPT.replace('def f', 'def g'), encoding='utf-8')
    (root / 'b.py').write_text(BARE_EXCEPT.replace('def f', 'def h'), encoding='utf-8')
    (root / 'clean.py').write_text('def ok():\n    return 1\n', encoding='utf-8')
    (root / 'broken.py').write_text('x = (\n', encoding='utf-8')  # a partial failure the answer must disclose
    return root


@pytest.fixture
def findings_only(tree, tmp_path):
    """The same tree without the unparsable file: findings alone decide the exit code (1, or 0 when clean)."""
    root = tmp_path / 'findings'
    root.mkdir()
    for name in ('a.py', 'b.py', 'clean.py'):
        (root / name).write_text((tree / name).read_text(encoding='utf-8'), encoding='utf-8')
    return root


@pytest.fixture
def scans(monkeypatch):
    """Every call of the scan entry point, as the number of files it was handed."""
    calls = []
    real = file_checker._results_in_sorted_order

    def spy(sorted_files, *rest):
        calls.append(len(sorted_files))
        return real(sorted_files, *rest)
    monkeypatch.setattr(file_checker, '_results_in_sorted_order', spy)
    return calls


VARIANTS = [
    pytest.param(['--select', 'B'], id='select-B'),
    pytest.param(['--select', 'B,S001', '--severity', 'medium'], id='dd-maintainability'),
    pytest.param(['--select', 'C,D,I,U', '--severity', 'medium'], id='dd-risk'),
    pytest.param(['--select', 'B', '--max-items', '1'], id='max-items'),
    pytest.param(['--select', 'B', '--limit', '1', '--no-snippets'], id='limit-no-snippets'),
]


def _separate(tree, extra, fmt):
    result = run('check', str(tree), *extra, '--format', fmt)
    return result


@pytest.mark.parametrize('extra', VARIANTS)
def test_three_sinks_equal_three_separate_runs_from_one_scan(tree, tmp_path, scans, extra):
    separate = {fmt: _separate(tree, extra, fmt) for fmt in ('text', 'grep', 'json')}
    assert scans == [4, 4, 4], 'the old way is one scan per format'
    scans.clear()
    out = {fmt: tmp_path / f'o.{fmt}' for fmt in ('text', 'grep', 'json')}
    both = run('check', str(tree), *extra, *(a for fmt, p in out.items() for a in ('--output', f'{fmt}={p}')))
    assert both.returncode == separate['text'].returncode, both.stderr
    assert scans == [4], 'three sinks, one scan'
    for fmt, path in out.items():
        assert path.read_text(encoding='utf-8') == separate[fmt].stdout, fmt
    assert both.stdout == separate['text'].stdout  # the stdout answer is --format text, unchanged
    assert 'did not parse cleanly' in out['text'].read_text(encoding='utf-8')  # the partial failure is disclosed


def test_a_json_stdout_with_text_and_grep_sinks(tree, tmp_path, scans):
    text, grep = tmp_path / 'o.txt', tmp_path / 'o.grep'
    both = run('check', str(tree), '--select', 'B', '--format', 'json', '--output', f'text={text}',
               '--output', f'grep={grep}')
    assert scans == [4]
    assert json.loads(both.stdout)['type'] == 'check'
    assert text.read_text(encoding='utf-8') == _separate(tree, ['--select', 'B'], 'text').stdout
    assert grep.read_text(encoding='utf-8') == _separate(tree, ['--select', 'B'], 'grep').stdout


@pytest.mark.parametrize('extra, expected', [
    (['--select', 'B'], 1),
    (['--select', 'B', '--fail-on', 'none'], 0),
    (['--select', 'B', '--exit-zero'], 0),
    (['--select', 'S001'], 0),
])
def test_the_exit_code_is_the_same_with_and_without_sinks(findings_only, tree, tmp_path, extra, expected):
    for root, want in ((findings_only, expected), (tree, 0 if '--exit-zero' in extra else 3)):
        bare = run('check', str(root), *extra)
        sunk = run('check', str(root), *extra, '--output', f'text={tmp_path / "t"}', '--output',
                   f'grep={tmp_path / "g"}')
        assert bare.returncode == want, (extra, bare.stderr)
        assert sunk.returncode == bare.returncode, (extra, sunk.stderr)


def test_a_format_alone_is_unchanged(tree, scans):
    first = run('check', str(tree), '--select', 'B')
    assert scans == [4]
    assert first.stdout == run('check', str(tree), '--select', 'B', '--output', 'text').stdout


def test_an_unwritable_sink_exits_3_and_the_other_sinks_and_the_answer_survive(findings_only, tmp_path, scans):
    good = tmp_path / 'good.grep'
    bad = tmp_path / 'no-such-dir' / 'o.txt'
    assert run('check', str(findings_only), '--select', 'B').returncode == 1  # so the 3 below is the sink's
    scans.clear()
    result = run('check', str(findings_only), '--select', 'B', '--output', f'text={bad}', '--output', f'grep={good}')
    assert result.returncode == 3, result.stderr
    assert scans == [3]
    assert 'no-such-dir' in result.stderr  # path parts only: an OSError text doubles backslashes on Windows
    assert 'text output sink failed' in result.stderr
    assert good.read_text(encoding='utf-8') == _separate(findings_only, ['--select', 'B'], 'grep').stdout
    assert 'Checked 3 files' in result.stdout


def test_every_failing_sink_is_disclosed_once(findings_only, tmp_path):
    result = run('check', str(findings_only), '--select', 'B', '--output', f'text={tmp_path / "x" / "a"}',
                 '--output', f'grep={tmp_path / "y" / "b"}')
    assert result.returncode == 3
    assert result.stderr.count('output sink failed') == 2, result.stderr


def test_a_failing_sink_before_a_good_one_still_decides_the_exit(findings_only, tmp_path):
    result = run('check', str(findings_only), '--select', 'B', '--output', f'json={tmp_path / "x" / "a.json"}',
                 '--output', f'grep={tmp_path / "ok.grep"}')
    assert result.returncode == 3, result.stderr
    assert (tmp_path / 'ok.grep').read_text(encoding='utf-8')


def test_grep_lists_every_detection_whatever_max_items_says(tree, tmp_path):
    """grep never applied --max-items (BACK-1035); its sink must not either. Independent of the render code."""
    out = tmp_path / 'o.grep'
    run('check', str(tree), '--select', 'B', '--max-items', '1', '--output', f'grep={out}')
    assert len(out.read_text(encoding='utf-8').splitlines()) == 3


def test_a_scan_disclosure_reaches_the_text_sink_and_not_the_grep_file(tree, tmp_path):
    (tree / 'm.go').write_text('package main\nfunc main() {}\n', encoding='utf-8')
    text, grep = tmp_path / 'o.txt', tmp_path / 'o.grep'
    result = run('check', str(tree), '--select', 'T006,B', '--output', f'text={text}', '--output', f'grep={grep}')
    assert 'W-CAP-1' in result.stdout
    assert 'W-CAP-1' in text.read_text(encoding='utf-8')
    assert 'W-CAP-1' not in grep.read_text(encoding='utf-8')  # grep stays file:line:col:rule:message


def test_a_json_sink_beside_a_json_stdout_writes_nothing(tree, tmp_path):
    """BACK-1939 contract kept: the primary output already is the document."""
    out = tmp_path / 'o.json'
    result = run('check', str(tree), '--select', 'B', '--format', 'json', '--output', f'json={out}')
    assert json.loads(result.stdout)['type'] == 'check'
    assert not out.exists()


def test_an_unsupported_sink_format_exits_2_before_the_scan(tree, tmp_path, scans):
    result = run('check', str(tree), '--output', f'typed={tmp_path / "o.typed"}')
    assert result.returncode == 2, result.stderr
    assert scans == []
    assert not (tmp_path / 'o.typed').exists()


@pytest.mark.parametrize('argv', [
    lambda tree, out: ['check', str(tree / 'a.py'), '--output', f'text={out}'],
    lambda tree, out: ['check', str(tree / 'a.py'), '--output', f'grep={out}'],
    lambda tree, out: [str(tree / 'a.py'), '--check', '--output', f'text={out}'],
], ids=['check-file-text', 'check-file-grep', 'file-check-flag'])
def test_a_single_file_check_still_refuses_text_and_grep_sinks(tree, tmp_path, argv):
    """Negative control on the sibling path: run_pattern_detection writes the json document only."""
    out = tmp_path / 'o.out'
    result = run(*argv(tree, out))
    assert result.returncode == 2, result.stderr
    assert 'writes only json file sinks' in result.stderr
    assert not out.exists()


def test_a_single_file_check_keeps_its_json_sink(tree, tmp_path):
    out = tmp_path / 'o.json'
    result = run('check', str(tree / 'a.py'), '--output', f'json={out}')
    assert result.returncode == run('check', str(tree / 'a.py')).returncode, result.stderr
    assert json.loads(out.read_text(encoding='utf-8'))['type'] == 'check'


def test_a_stdin_check_still_refuses_text_and_grep_sinks(tree, tmp_path, monkeypatch):
    """Negative control on the sibling path: a --stdin --check run writes one json document, nothing else."""
    import io
    monkeypatch.setattr('sys.stdin', io.StringIO(str(tree / 'a.py') + '\n'))
    out = tmp_path / 'o.txt'
    result = run('--stdin', '--check', '--output', f'text={out}')
    assert result.returncode == 2, result.stderr
    assert 'writes only json file sinks' in result.stderr
    assert not out.exists()

"""BACK-1728: --section NAME and an element argument both name what to extract; one was dropped.

reveal reads one path and an optional element per call: `reveal a.md b.md` parses b.md as the
element of a.md. --section NAME is the element spelled as a flag, so with a second path
(`reveal a.md b.md --section X`) the run looked for an element 'b.md' in a.md and never said
that X was dropped; with a named element (`reveal a.md A --section X`) it extracted A, exited 0
and said only that --section "has no effect on the file view". There is no multi-path route
that could apply --section to each path (`--stdin` ignores --section, see the report), so the
conflict is a usage error: stderr names --section, its value and the other element, exit 2.

--links, --frontmatter and --metadata read the whole file and are not element flags; on two
paths they fail as a bare `reveal a.md b.md` does (non-zero, b.md named as a missing element),
and with an element the element view answers and the flag ledger notes the unused flag. Those
behaviours are pinned below so a change to them is a decision, not an accident.
"""

import pytest

from conftest import _run_reveal_direct

MD = '# A\ntext [l](b.md)\n## X\nmore\n'
HTML = ('<html><head><title>T</title><meta name="description" content="d"></head>'
        '<body><h1>H</h1></body></html>\n')


@pytest.fixture
def files(tmp_path):
    for name in ('a', 'b'):
        (tmp_path / f'{name}.md').write_text(f'---\ntitle: {name}\n---\n' + MD, encoding='utf-8')
        (tmp_path / f'{name}.html').write_text(HTML, encoding='utf-8')
    return tmp_path


def _assert_section_conflict(proc, value, element):
    assert proc.returncode == 2, proc.stdout + proc.stderr
    assert '--section' in proc.stderr
    assert f"'{value}'" in proc.stderr
    assert element in proc.stderr
    assert proc.stdout == ''


def test_second_path_with_section_is_refused_and_names_the_value(files):
    a, b = str(files / 'a.md'), str(files / 'b.md')
    _assert_section_conflict(_run_reveal_direct(a, b, '--section', 'X'), 'X', b)


def test_named_element_with_section_is_refused(files):
    """Was: extracted A, exit 0, with only a ledger note that --section had no effect."""
    _assert_section_conflict(_run_reveal_direct(str(files / 'a.md'), 'A', '--section', 'X'), 'X', 'A')


def test_line_suffix_with_section_is_refused(files):
    a = str(files / 'a.md')
    _assert_section_conflict(_run_reveal_direct(f'{a}:6', '--section', 'A'), 'A', ':6')


@pytest.mark.parametrize('flag,ext', [('--links', 'md'), ('--frontmatter', 'md'), ('--metadata', 'html')])
def test_whole_file_flag_on_two_paths_fails_naming_the_second(files, flag, ext, monkeypatch):
    """Relative names: an HTML element containing '/' raises an uncaught SelectorSyntaxError
    (a traceback, reported separately), which is not what this pins."""
    monkeypatch.chdir(files)
    proc = _run_reveal_direct(f'a.{ext}', f'b.{ext}', flag)
    assert proc.returncode != 0, proc.stdout
    assert f'b.{ext}' in proc.stderr
    assert proc.stdout == ''


@pytest.mark.parametrize('flag', ['--links', '--frontmatter'])
def test_whole_file_flag_with_an_element_answers_the_element_and_notes_the_flag(files, flag):
    proc = _run_reveal_direct(str(files / 'a.md'), 'X', flag)
    assert proc.returncode == 0, proc.stderr
    assert 'more' in proc.stdout
    assert f'{flag} has no effect' in proc.stderr


# Negative controls: what must not change.
def test_section_on_one_path_still_extracts(files):
    proc = _run_reveal_direct(str(files / 'a.md'), '--section', 'X')
    assert proc.returncode == 0, proc.stderr
    assert 'more' in proc.stdout


def test_element_without_section_still_extracts(files):
    proc = _run_reveal_direct(str(files / 'a.md'), 'X')
    assert proc.returncode == 0, proc.stderr
    assert 'more' in proc.stdout


@pytest.mark.parametrize('argv,ext,expect', [(['--links'], 'md', 'b.md'),
                                             (['--frontmatter', '--format', 'json'], 'md', '"title"'),
                                             (['--metadata'], 'html', 'description')])
def test_whole_file_flag_on_one_path_still_runs(files, argv, ext, expect):
    proc = _run_reveal_direct(str(files / f'a.{ext}'), *argv)
    assert proc.returncode == 0, proc.stderr
    assert expect in proc.stdout

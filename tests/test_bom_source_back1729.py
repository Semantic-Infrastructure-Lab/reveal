"""A UTF-8 BOM is an encoding mark, not Python source (BACK-1729).

CPython runs a BOM-prefixed .py file, and Windows editors write one. reveal decoded it
as 'utf-8', so U+FEFF stayed at the front of the text and the stdlib-ast parse failed
("invalid non-printable character U+FEFF"): `check` saw no tree and reported a file with
a bare `except:` as clean (exit 0), stats:// scored it 100 instead of 95, and
`reveal surface` listed the file as unparsed and lost its CLI command. The outline was
right only because tree-sitter skips the BOM.

Every case runs the file with and without the BOM: the answers must be identical.
"""
import ast
import json
import os
import subprocess
import sys

import pytest

import reveal.analyzers  # noqa: F401  (registers every analyzer)
from reveal.registry import get_analyzer
from reveal.utils.pyparse import parse_python

pytestmark = [pytest.mark.component]

BOM = b'\xef\xbb\xbf'
SOURCE = (
    'import os\n'
    '\n'
    '\n'
    'def load():\n'
    '    try:\n'
    '        return os.getcwd()\n'
    '    except:\n'
    '        return None\n'
)
BARE_EXCEPT_LINE = 7
CLI_SOURCE = (
    'import click\n'
    '\n'
    '\n'
    '@click.command()\n'
    'def cli():\n'
    '    return 1\n'
)
BROKEN = 'def broken(:\n    return 1\n'
PARSE_FAILED = 'AST parse failed'
SPELLINGS = [pytest.param(b'', id='plain'), pytest.param(BOM, id='bom')]


def _reveal(cwd, *argv):
    env = dict(os.environ, PYTHONIOENCODING='utf-8', REVEAL_NO_UPDATE_CHECK='1',
               REVEAL_DISK_CACHE='0')
    return subprocess.run([sys.executable, '-m', 'reveal', *argv], cwd=cwd, env=env,
                          capture_output=True, text=True, encoding='utf-8', timeout=120)


def _write(folder, name, prefix, text):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(prefix + text.encode('utf-8'))
    return path


@pytest.mark.parametrize('prefix', SPELLINGS)
def test_check_finds_the_bare_except_in_a_bom_file(tmp_path, prefix):
    _write(tmp_path, 'load.py', prefix, SOURCE)
    proc = _reveal(tmp_path, 'check', 'load.py', '--select', 'B001', '--format', 'json')
    assert PARSE_FAILED not in proc.stderr
    lines = [d['line'] for d in json.loads(proc.stdout)['detections']]
    assert lines == [BARE_EXCEPT_LINE], 'the BOM is not a line: B001 cites the same line'


def test_stats_scores_a_bom_file_like_the_same_file_without_one(tmp_path):
    answers = {}
    for label, prefix in (('plain', b''), ('bom', BOM)):
        _write(tmp_path / label, 'load.py', prefix, SOURCE)
        proc = _reveal(tmp_path / label, 'stats://load.py', '--format', 'json')
        assert proc.returncode == 0, proc.stderr
        assert PARSE_FAILED not in proc.stderr, label
        answers[label] = json.loads(proc.stdout)
    (plain_file,) = answers['plain']['files']
    assert plain_file['quality']['check_issues'] == 1, 'positive control: B001 counts as an issue'
    assert answers['bom'] == answers['plain']


@pytest.mark.parametrize('prefix', SPELLINGS)
def test_outline_finds_the_function_on_its_line(tmp_path, prefix):
    _write(tmp_path, 'load.py', prefix, SOURCE)
    proc = _reveal(tmp_path, 'load.py', '--format', 'json')
    assert proc.returncode == 0, proc.stderr
    functions = json.loads(proc.stdout)['structure']['functions']
    assert [(f['name'], f['line'], f['line_end']) for f in functions] == [('load', 4, 8)]


@pytest.mark.parametrize('prefix', SPELLINGS)
def test_surface_reads_the_cli_command_of_a_bom_file(tmp_path, prefix):
    _write(tmp_path / 'proj', 'app.py', prefix, CLI_SOURCE)
    proc = _reveal(tmp_path, 'surface', 'proj', '--format', 'json')
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    assert result['unparsed_files'] == []
    assert [(c['name'], c['line']) for c in result['surfaces']['cli']] == [('cli', 5)]


def test_parse_python_reads_a_bom_like_cpython_reads_the_file():
    """CPython's own reading of the bytes is the oracle, positions included."""
    data = BOM + SOURCE.encode('utf-8')
    expected = ast.dump(ast.parse(data), include_attributes=True)
    assert ast.dump(parse_python(data.decode('utf-8')), include_attributes=True) == expected


def test_the_file_seam_drops_the_bom_and_names_the_encoding(tmp_path):
    plain = _write(tmp_path / 'plain', 'load.py', b'', SOURCE)
    bom = _write(tmp_path / 'bom', 'load.py', BOM, SOURCE)
    plain_analyzer = get_analyzer(str(plain))(str(plain))
    bom_analyzer = get_analyzer(str(bom))(str(bom))
    assert bom_analyzer.content == plain_analyzer.content
    assert bom_analyzer.lines == plain_analyzer.lines
    assert bom_analyzer.get_metadata()['encoding'] == 'UTF-8-SIG'
    assert plain_analyzer.get_metadata()['encoding'] == 'UTF-8', 'negative control'


def test_only_the_leading_bom_is_an_encoding_mark(tmp_path):
    """A U+FEFF inside the text is a character of the file and stays."""
    text = 's = "\ufeff"\n'
    path = _write(tmp_path, 'zw.py', BOM, text)
    assert get_analyzer(str(path))(str(path)).content == text.rstrip('\n')
    with pytest.raises(SyntaxError):  # CPython rejects a second BOM too
        ast.parse(BOM + BOM + SOURCE.encode('utf-8'))
    with pytest.raises(SyntaxError):
        parse_python('\ufeff\ufeff' + SOURCE)


# ------------------------------------------- negative controls: real breakage still shows

@pytest.mark.parametrize('prefix', SPELLINGS)
def test_a_broken_file_still_reports_its_parse_failure(tmp_path, prefix):
    _write(tmp_path, 'broken.py', prefix, BROKEN)
    proc = _reveal(tmp_path, 'stats://broken.py', '--format', 'json')
    assert PARSE_FAILED in proc.stderr
    assert 'U+FEFF' not in proc.stderr, 'the failure is the real syntax error, not the BOM'


@pytest.mark.parametrize('prefix', SPELLINGS)
def test_surface_still_lists_a_broken_file_as_unparsed(tmp_path, prefix):
    _write(tmp_path / 'proj', 'broken.py', prefix, BROKEN)
    proc = _reveal(tmp_path, 'surface', 'proj', '--format', 'json')
    unparsed = json.loads(proc.stdout)['unparsed_files']
    assert [os.path.basename(p) for p in unparsed] == ['broken.py']

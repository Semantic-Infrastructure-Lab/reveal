"""BACK-1706: CRLF (Windows checkout) sources through structure, extraction and check.

Measured before writing: no existing test fed ``\\r\\n`` Python or Markdown to the
analyzers or ``reveal check`` (only an unrelated office-zip fixture contains the bytes).
Each case writes the same content with LF and with CRLF in separate directories and
requires identical results, then asserts no ``\\r`` leaks into any output.
"""
import json
import os
import subprocess
import sys

import pytest

# BACK-1149: end-to-end CLI behavior on checked-out sources
pytestmark = pytest.mark.integration

PY_SRC = (
    'import os\n'
    '\n'
    '\n'
    'def foo(a):\n'
    '    """Doc."""\n'
    '    x = 1\n'
    '    return x\n'
    '\n'
    '\n'
    'class K:\n'
    '    def m(self):\n'
    '        return 2\n'
)

PY_CHECK_SRC = (
    'def g():\n'
    '    try:\n'
    '        pass\n'
    '    except:\n'
    '        pass\n'
)

MD_SRC = (
    '# Title\n'
    '\n'
    'Intro text\n'
    '\n'
    '## Sub\n'
    '\n'
    'body line\n'
    '\n'
    '```python\n'
    'x = 1\n'
    '```\n'
)

MD_CHECK_SRC = '# T\n\n[x](missing.md)\n'


def _pair(tmp_path, name, text):
    """The same file as LF and as CRLF, each in its own directory (same relative name)."""
    dirs = {}
    for label, eol in (('lf', '\n'), ('crlf', '\r\n')):
        d = tmp_path / label
        d.mkdir()
        (d / name).write_bytes(text.replace('\n', eol).encode('utf-8'))
        dirs[label] = d
    assert b'\r\n' in (dirs['crlf'] / name).read_bytes()
    assert b'\r' not in (dirs['lf'] / name).read_bytes()
    return dirs


def _reveal(cwd, *args):
    env = {k: v for k, v in os.environ.items() if k != 'PYTHONPYCACHEPREFIX'}
    env['REVEAL_DISK_CACHE'] = '0'
    env['PYTHONIOENCODING'] = 'utf-8'
    return subprocess.run(
        [sys.executable, '-m', 'reveal', *args], cwd=str(cwd), env=env,
        capture_output=True, timeout=120,
    )


def _own_newlines(data):
    """Drop the platform's own line terminator: Windows text-mode stdout writes every \\n as \\r\\n.

    Only that pair goes, so a CR that leaked from CRLF source (arriving as \\r\\r\\n) still shows.
    """
    return data.replace(b'\r\n', b'\n') if sys.platform == 'win32' else data


def _both(tmp_path, name, text, *args, check=False):
    dirs = _pair(tmp_path, name, text)
    out = {}
    for label, d in dirs.items():
        r = _reveal(d, *(('check', name) if check else (name,)), *args)
        assert r.returncode in (0, 1), r.stderr.decode('utf-8', 'replace')
        stdout, stderr = _own_newlines(r.stdout), _own_newlines(r.stderr)
        assert b'\r' not in stdout, f'{label}: stray CR in stdout for {args}'
        assert b'\r' not in stderr, f'{label}: stray CR in stderr for {args}'
        out[label] = stdout.decode('utf-8')
    return out


class TestCrlfPython:
    def test_structure_matches_lf(self, tmp_path):
        out = _both(tmp_path, 'a.py', PY_SRC, '--format', 'json')
        assert json.loads(out['crlf']) == json.loads(out['lf'])

    def test_structure_line_numbers(self, tmp_path):
        out = _both(tmp_path, 'a.py', PY_SRC, '--format', 'json')
        data = json.loads(out['crlf'])
        funcs = {f['name']: f for f in data['structure']['functions']}
        assert (funcs['foo']['line'], funcs['foo']['line_end']) == (4, 7)

    def test_function_extraction_text(self, tmp_path):
        out = _both(tmp_path, 'a.py', PY_SRC, 'foo')
        assert out['crlf'] == out['lf']
        assert '      4  def foo(a):' in out['crlf']

    def test_class_extraction_json_source_has_no_cr(self, tmp_path):
        out = _both(tmp_path, 'a.py', PY_SRC, 'K', '--format', 'json')
        data = json.loads(out['crlf'])
        assert (data['line_start'], data['line_end']) == (10, 12)
        assert data['source'] == 'class K:\n    def m(self):\n        return 2'
        assert json.loads(out['lf']) == data

    def test_check_finds_same_issue_on_same_line(self, tmp_path):
        out = _both(tmp_path, 'g.py', PY_CHECK_SRC, '--format', 'json', check=True)
        crlf = json.loads(out['crlf'])
        hits = [d for d in crlf['detections'] if d['rule_code'] == 'B001']
        assert [(d['line'], d['context']) for d in hits] == [(4, 'except:')]
        assert crlf['detections'] == json.loads(out['lf'])['detections']

    def test_check_clean_control(self, tmp_path):
        out = _both(tmp_path, 'ok.py', PY_SRC, '--format', 'json', check=True)
        assert [d for d in json.loads(out['crlf'])['detections']
                if d['rule_code'] == 'B001'] == []


class TestCrlfMarkdown:
    def test_structure_matches_lf(self, tmp_path):
        out = _both(tmp_path, 'a.md', MD_SRC, '--format', 'json')
        assert json.loads(out['crlf']) == json.loads(out['lf'])

    def test_heading_line_numbers_and_text(self, tmp_path):
        out = _both(tmp_path, 'a.md', MD_SRC, '--format', 'json')
        heads = json.loads(out['crlf'])['structure']['headings']
        assert [(h['line'], h['level'], h['name']) for h in heads] == [
            (1, 1, 'Title'), (5, 2, 'Sub')]

    def test_section_extraction_text(self, tmp_path):
        out = _both(tmp_path, 'a.md', MD_SRC, 'Sub')
        assert out['crlf'] == out['lf']
        assert '      5  ## Sub' in out['crlf']
        assert '     11  ```' in out['crlf']

    def test_check_broken_link_line(self, tmp_path):
        out = _both(tmp_path, 'c.md', MD_CHECK_SRC, '--format', 'json', check=True)
        crlf = json.loads(out['crlf'])
        broken = [d for d in crlf['detections'] if 'Broken internal link' in d['message']]
        assert [(d['line'], d['message']) for d in broken] == [
            (3, 'Broken internal link: missing.md')]
        assert crlf['detections'] == json.loads(out['lf'])['detections']

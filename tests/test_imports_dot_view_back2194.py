"""``imports://<dir>?importers&format=dot``: the Graphviz module view (BACK-2194).

``calls ?modules &format=dot`` is the spelling this replaces at the BACK-1054 cut, so the view
must draw the same edges the old one did: one ``importer -> module`` edge per importer ``?importers``
lists, paths relative to the requested directory. Like ``calls://``, ``dot`` has no ``--format``
spelling: it is a URI parameter, and the warnings go to stderr so stdout stays valid Graphviz.
"""
import re
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

pytestmark = [pytest.mark.component]

EDGE = re.compile(r'^\s+"([^"]+)" -> "([^"]+)";$', re.MULTILINE)


def _write(root: Path, files: dict) -> Path:
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    return root


@pytest.fixture
def pkg(tmp_path):
    return _write(tmp_path / 'pkg', {
        'a.py': 'import b\nimport c\n',
        'b.py': 'import c\n',
        'c.py': 'X = 1\n',
        'sub/d.py': 'import b\n',
    })


def _edges(stdout: str) -> set:
    return set(EDGE.findall(stdout))


def test_dot_draws_one_edge_per_importer(pkg):
    result = _run_reveal_direct(f'imports://{pkg}?importers&scope=path&format=dot')
    assert result.returncode == 0, result.stderr
    assert result.stdout.startswith('digraph modules {')
    assert result.stdout.rstrip().endswith('}')
    assert 'rankdir=LR;' in result.stdout
    assert _edges(result.stdout) == {('a.py', 'b.py'), ('a.py', 'c.py'), ('b.py', 'c.py'), ('sub/d.py', 'b.py')}


def test_dot_edges_equal_the_calls_modules_dot_they_replace(pkg):
    old = _run_reveal_direct(f'calls://{pkg}?modules&format=dot')
    new = _run_reveal_direct(f'imports://{pkg}?importers&scope=path&format=dot')
    assert old.returncode == new.returncode == 0, (old.stderr, new.stderr)
    assert _edges(old.stdout), 'positive control: the old view draws edges on this fixture'
    assert _edges(new.stdout) == _edges(old.stdout)


def test_dot_escapes_a_quote_in_a_name(tmp_path):
    root = _write(tmp_path / 'q', {'a.py': 'import b\n', 'b.py': 'X = 1\n'})
    adapter_out = _run_reveal_direct(f'imports://{root}?importers&scope=path&format=dot')
    assert '"a.py" -> "b.py";' in adapter_out.stdout
    from reveal.adapters.imports import ImportsRenderer
    import io
    from contextlib import redirect_stdout
    buf = io.StringIO()
    with redirect_stdout(buf):
        ImportsRenderer._render_dot({'entries': [{'file': 'we"ird.py', 'importers': ['u\\v.py']}]})
    assert '"u\\\\v.py" -> "we\\"ird.py";' in buf.getvalue()


def test_dot_keeps_warnings_off_stdout(tmp_path):
    root = _write(tmp_path / 'w', {
        'package.json': '{"name": "fx"}\n',
        'src/a.js': "import { b } from './b';\nexport const a = 1;\n",
        'src/b.js': 'export const b = 1;\n',
        'src/bad.js': "import { a } from './a';\nfunction broken( {\n  return a;\n",
    })
    result = _run_reveal_direct(f'imports://{root}/src?importers&scope=path&format=dot')
    assert result.returncode == 3, result.stderr  # D6: a file parsed with errors
    assert result.stdout.startswith('digraph modules {')
    assert all(line.startswith(('digraph', '  ', '}')) for line in result.stdout.splitlines())


def test_dot_prints_meta_warnings_on_stderr(capsys):
    from reveal.adapters.imports import ImportsRenderer
    warning = {'type': 'analysis_incomplete', 'message': 'lost evidence'}
    ImportsRenderer._render_dot({'entries': [], 'meta': {'warnings': [warning]}})
    captured = capsys.readouterr()
    assert captured.out.startswith('digraph modules {')
    assert 'lost evidence' in captured.err


def test_dot_on_another_view_is_named_a_no_op(pkg):
    result = _run_reveal_direct(f'imports://{pkg}?circular&format=dot')
    assert 'digraph' not in result.stdout
    assert "'format' has no effect" in result.stdout + result.stderr


def test_unknown_format_value_is_a_usage_error(pkg):
    result = _run_reveal_direct(f'imports://{pkg}?importers&format=svg')
    assert result.returncode == 2
    assert 'format must be one of' in result.stdout + result.stderr

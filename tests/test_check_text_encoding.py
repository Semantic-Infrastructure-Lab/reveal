"""Unit tests for scripts/check_text_encoding.py (the Windows cp1252 ratchet, BACK-1354)."""
import ast
import importlib.util
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    'check_text_encoding', Path(__file__).resolve().parent.parent / 'scripts' / 'check_text_encoding.py')
cte = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(cte)


def _call(src):
    return ast.parse(src).body[0].value


@pytest.mark.parametrize('src', [
    "open('a')", "open('a', 'w')", "io.open('a')", "Path('x').read_text()", "Path('x').write_text('d')",
    "p.open()", "p.open('r')", "Path('x').read_text(encoding=None)",
    "tempfile.NamedTemporaryFile('w')", "subprocess.run(['x'], text=True)",
    "subprocess.check_output(['x'], universal_newlines=True)",
])
def test_flags_bare_text_io(src):
    assert cte.is_bare_text_io(_call(src))


@pytest.mark.parametrize('src', [
    "open('a', encoding='utf-8')", "open('a', 'rb')", "open('a', 'wb')", "open(**kw)",
    "Path('x').read_text('utf-8')", "Path('x').read_text(encoding='utf-8')",
    "Path('x').write_text('d', 'utf-8')", "opener.open('http://x')", "dist.read_text('METADATA')",
    "webbrowser.open('http://x')", "tempfile.NamedTemporaryFile('wb')",
    "subprocess.run(['x'], capture_output=True)", "subprocess.run(['x'], text=True, encoding='utf-8')",
    "subprocess.run(['x'], text=False)", "foo.bar()",
])
def test_does_not_flag_safe_or_non_file_calls(src):
    assert not cte.is_bare_text_io(_call(src))


@pytest.mark.parametrize('src, strict', [
    ("(FIXTURES_DIR / 'e.yaml').read_text()", True),
    ("(Path(__file__).parent / 'x').read_text()", True),
    ("open(Path(__file__).parent / 'x')", True),
    ("(tmp_path / 'x').read_text()", False),
    ("open(path)", False),
])
def test_strict_class_is_repo_file_reads(src, strict):
    assert cte.is_strict_site(_call(src)) is strict

"""Tests must not feed reveal env:// URIs for variables only POSIX sets.

Windows runners have no HOME, USER, SHELL, TERM or LOGNAME. A test that reads
env://HOME fails there only, so the failure first shows up on GitHub's Windows
legs after a push (BACK-1554 in 69408a70, BACK-1556 in c95b2478). Worse, a test
that never checks the URI succeeded passes there while its assertions check
nothing. Set a variable the test owns (monkeypatch.setenv / patch.dict) instead.

This scan runs on every OS, so it fails locally before the push.
"""
import ast
import re
from pathlib import Path


TESTS_DIR = Path(__file__).parent

POSIX_ONLY_VARS = ('HOME', 'USER', 'SHELL', 'TERM', 'LOGNAME')

# An input URI: the variable name is not followed by ':' (a rendered
# "env://HOME:/home/user" line from mocked data reads no environment).
_POSIX_ENV_URI = re.compile(r'env://(' + '|'.join(POSIX_ONLY_VARS) + r')(?![\w:])')


def _docstring_nodes(tree: ast.AST) -> set:
    nodes = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                nodes.add(body[0].value)
    return nodes


def find_posix_env_uris(source: str) -> list:
    """Return (lineno, var) for each non-docstring string literal naming a POSIX-only env:// URI."""
    tree = ast.parse(source)
    docstrings = _docstring_nodes(tree)
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Constant) and isinstance(node.value, str)
                and node not in docstrings):
            for match in _POSIX_ENV_URI.finditer(node.value):
                found.append((node.lineno, match.group(1)))
    return sorted(found)


def test_scanner_flags_inputs_and_skips_docs_comments_and_rendered_values():
    source = (
        '"""Module docstring mentioning env://HOME."""\n'
        '# a comment about env://HOME\n'
        "def test_x():\n"
        '    """env://USER in a docstring."""\n'
        "    write('env://PATH\\nenv://HOME\\n')\n"
        "    run('env://SHELL')\n"
        "    assert 'env://HOME:/home/user' in rendered\n"
        "    run('env://HOMEDRIVE')\n"
    )
    assert find_posix_env_uris(source) == [(5, 'HOME'), (6, 'SHELL')]


def _test_sources():
    for path in sorted(TESTS_DIR.rglob('*.py')):
        rel = path.relative_to(TESTS_DIR)
        if rel.parts[0] == 'fixtures' or path == Path(__file__):
            continue  # fixtures are sample sources; this file's own sample is the positive control
        if path.name.startswith('test_') or path.name == 'conftest.py':
            yield rel.as_posix(), path


def test_no_test_reads_a_posix_only_env_var():
    offenders = []
    for rel, path in _test_sources():
        offenders += [f'{rel}:{line} env://{var}'
                      for line, var in find_posix_env_uris(path.read_text(encoding='utf-8'))]
    assert not offenders, (
        'Tests read env:// variables Windows does not set:\n  ' + '\n  '.join(offenders)
        + '\nSet a variable the test owns (monkeypatch.setenv or patch.dict(os.environ)) and read that.'
    )

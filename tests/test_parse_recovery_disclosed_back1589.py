"""A format analyzer that overrides get_structure says when its parse was recovered (BACK-1589).

TreeSitterAnalyzer.get_structure sets ``_has_errors`` when tree-sitter recovered around a
syntax error (BACK-1084), and the file view and ``check`` say so. The analyzers that
override get_structure never set it, so an invalid JSON file printed ``Keys (1): a`` at
confidence 1.0 with no note: the answer for a valid file. The base class now wraps every
override (``TreeSitterAnalyzer.__init_subclass__``). Each case below runs one overriding
analyzer on a broken file (flagged) and on a valid one (not flagged, the control).
"""

import pytest

from reveal.registry import get_analyzer

# BACK-1149: in-process analyzer calls, not CLI/MCP surface
pytestmark = pytest.mark.component

# (file name, broken source, valid source)
CASES = [
    ('a.json', '{"a": 1,,\n "b": [}\n', '{"a": 1, "b": [2]}\n'),
    ('a.yaml', 'a: 1\nb: [1, 2\nc: }\n', 'a: 1\nb: [1, 2]\n'),
    ('a.toml', 'a = 1\n[[x\nb = \n', 'a = 1\n[x]\nb = 2\n'),
    ('a.tf', 'resource "x" "y" {\n a = \n}}\n', 'resource "x" "y" {\n  a = 1\n}\n'),
    ('a.graphql', 'type Q { a: Int \n query {{ }\n', 'type Q {\n  a: Int\n}\n'),
    ('a.proto', 'syntax = "proto3";\nmessage M { int32 a = ; }}\n',
     'syntax = "proto3";\nmessage M {\n  int32 a = 1;\n}\n'),
    ('a.zig', 'fn f( void {\n}}\n', 'fn f() void {}\n'),
    ('Dockerfile', 'FROM\nRUN [\n', 'FROM python:3.12\nRUN echo hi\n'),
]


def _structure(tmp_path, name, source):
    path = tmp_path / name
    path.write_text(source, encoding='utf-8')
    analyzer_class = get_analyzer(str(path))
    assert 'get_structure' in analyzer_class.__dict__, (
        f'{analyzer_class.__name__} no longer overrides get_structure; this case tests nothing')
    return analyzer_class(str(path)).get_structure() or {}


@pytest.mark.parametrize('name,broken,valid', CASES, ids=[c[0] for c in CASES])
def test_a_broken_file_is_flagged(tmp_path, monkeypatch, name, broken, valid):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    assert _structure(tmp_path, name, broken).get('_has_errors') is True


@pytest.mark.parametrize('name,broken,valid', CASES, ids=[c[0] for c in CASES])
def test_a_valid_file_is_not_flagged(tmp_path, monkeypatch, name, broken, valid):
    monkeypatch.setenv('REVEAL_DISK_CACHE', '0')
    assert not _structure(tmp_path, name, valid).get('_has_errors')


def test_the_file_view_says_so(tmp_path, monkeypatch):
    from conftest import _run_reveal_direct
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'broken.json').write_text('{"a": 1,,}\n', encoding='utf-8')
    out = _run_reveal_direct('broken.json').stdout
    assert 'Parse recovered' in out

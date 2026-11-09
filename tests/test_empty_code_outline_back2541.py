"""BACK-2541: a code outline whose category lists are all empty must not render as a bare header.

A grammar whose node kinds match none of an analyzer's tables parses cleanly and extracts nothing.
Zig on tree-sitter-language-pack 1.25.0 did exactly that: ``reveal FILE`` printed the file header
and nothing else, exit 0. ``{}`` already said "No structure available"; an all-empty keyed
structure is the same answer and must say the same thing. Legitimately empty files are common
(top-level PHP scripts, comment-only ``doc.go``, macro-only C headers), so this is a disclosure,
not an exit code.
"""

import pytest

from reveal.analyzers.python import PythonAnalyzer
from reveal.display.coverage import is_empty_code_outline
from reveal.display.structure import _handle_outline_mode, _handle_standard_output

LONG_SCRIPT = ''.join(f'x{i} = {i}\n' for i in range(80))


@pytest.fixture
def long_file(tmp_path):
    path = tmp_path / 'script.py'
    path.write_text(LONG_SCRIPT, encoding='utf-8')
    return path


class TestIsEmptyCodeOutline:
    @pytest.mark.parametrize('structure', [
        {'functions': []},
        {'imports': [], 'functions': [], 'classes': []},
        {'functions': [], 'meta': {'outcome': 'complete'}, '_has_errors': False},
    ])
    def test_all_empty_code_categories_qualify(self, structure):
        assert is_empty_code_outline(structure)

    @pytest.mark.parametrize('structure', [
        {},                                                  # already handled as structure-less
        {'functions': [{'name': 'f', 'line': 1}]},           # a populated outline
        {'functions': [], 'imports': [{'line': 1}]},         # one non-empty category is enough
        {'headings': []},                                    # markdown keeps its own empty view
        {'functions': [], 'headings': []},                   # not code-shaped
        {'_has_errors': True},                               # no listed category at all
        {'meta': {'outcome': 'failed'}},                     # an outcome record is not an outline
    ])
    def test_everything_else_does_not(self, structure):
        assert not is_empty_code_outline(structure)


class TestEmptyCodeOutlineRendering:
    def test_default_view_says_so_instead_of_printing_a_bare_header(self, long_file, capsys):
        analyzer = PythonAnalyzer(str(long_file))
        _handle_standard_output(analyzer, {'functions': [], 'classes': []}, 'text', False, None)
        out = capsys.readouterr().out
        assert 'No structure available' in out
        assert '81 lines' in out or '80 lines' in out

    def test_outline_view_says_so_too(self, long_file, capsys):
        analyzer = PythonAnalyzer(str(long_file))
        _handle_outline_mode(analyzer, {'functions': [], 'classes': []}, long_file, False, None)
        assert 'No structure available' in capsys.readouterr().out

    def test_matches_the_empty_dict_answer(self, long_file, capsys):
        analyzer = PythonAnalyzer(str(long_file))
        _handle_standard_output(analyzer, {}, 'text', False, None)
        bare = capsys.readouterr().out
        _handle_standard_output(analyzer, {'functions': []}, 'text', False, None)
        assert capsys.readouterr().out == bare

    def test_populated_outline_is_untouched(self, long_file, capsys):
        analyzer = PythonAnalyzer(str(long_file))
        structure = {'functions': [{'name': 'f', 'line': 1, 'line_end': 2, 'signature': '()'}]}
        _handle_standard_output(analyzer, structure, 'text', False, None)
        out = capsys.readouterr().out
        assert 'No structure available' not in out
        assert 'f' in out

    def test_json_keeps_the_explicit_empty_lists(self, long_file, capsys):
        analyzer = PythonAnalyzer(str(long_file))
        _handle_standard_output(analyzer, {'functions': []}, 'json', False, None)
        assert '"functions": []' in capsys.readouterr().out

    def test_recovery_notice_survives_an_empty_outline(self, long_file, capsys):
        analyzer = PythonAnalyzer(str(long_file))
        _handle_standard_output(analyzer, {'functions': [], '_has_errors': True}, 'text', False, None)
        out = capsys.readouterr().out
        assert 'No structure available' in out
        assert 'recover' in out.lower() or 'error' in out.lower()

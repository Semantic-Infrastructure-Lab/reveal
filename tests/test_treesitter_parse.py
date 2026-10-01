"""The parser seam, reveal/core/treesitter_parse.py (BACK-1045).

Every tree-sitter parser in reveal comes from here (the ``tree-sitter-import`` rule in
scripts/check_boundaries.py keeps it that way). These tests pin what the seam promises
its callers: a tree, or ``GrammarUnavailable`` naming the language, never a silent
``None``, and one not-yet-downloaded warning per language whoever asks first. The last
class is the harm the seam was for: a surface scan whose grammar is missing used to
report the file as clean.
"""

import sys
import textwrap
from pathlib import Path
from unittest.mock import patch

import pytest

import reveal.core.treesitter_parse as seam
from reveal.core import tree_root, _zero_arg

# BACK-1149: component-layer test -- the seam module and one adapter, in process
pytestmark = pytest.mark.component


@pytest.fixture(autouse=True)
def _fresh_seam_state():
    seam._warned_uncached.clear()
    seam._ready.clear()
    yield
    seam._warned_uncached.clear()
    seam._ready.clear()


class TestGetTree:
    def test_parses_source(self):
        root = tree_root(seam.get_tree('python', 'def f():\n    return 1\n'))
        assert _zero_arg(root, 'kind') == 'module'

    def test_unknown_language_raises_naming_it(self):
        with pytest.raises(seam.GrammarUnavailable) as caught:
            seam.get_tree('no-such-language', 'x')
        assert caught.value.language == 'no-such-language'
        assert "'no-such-language'" in str(caught.value)
        assert caught.value.cause is not None

    def test_missing_pack_raises_rather_than_importerror(self):
        with patch.dict(sys.modules, {'tree_sitter_language_pack': None}):
            with pytest.raises(seam.GrammarUnavailable) as caught:
                seam.get_tree('python', 'x = 1')
        assert isinstance(caught.value.cause, ImportError)

    def test_pack_failure_is_wrapped_with_its_cause(self):
        boom = RuntimeError('Download error: no network')
        with patch('tree_sitter_language_pack.get_parser', side_effect=boom):
            with pytest.raises(seam.GrammarUnavailable) as caught:
                seam.get_tree('python', 'x = 1')
        assert caught.value.cause is boom
        assert str(caught.value) == "no tree-sitter grammar for 'python': Download error: no network"


class TestFetchAnnouncement:
    def test_warns_once_per_language_before_a_fetch(self, caplog):
        with patch('tree_sitter_language_pack.downloaded_languages', return_value=[]):
            with caplog.at_level('WARNING', logger=seam.__name__):
                seam.get_parser('python')
                seam._ready.clear()   # a second caller in the same process, still uncached
                seam.get_parser('python')
        assert sum('not yet downloaded' in r.message for r in caplog.records) == 1

    def test_cached_grammar_does_not_warn(self, caplog):
        with patch('tree_sitter_language_pack.downloaded_languages', return_value=['python']):
            with caplog.at_level('WARNING', logger=seam.__name__):
                seam.get_parser('python')
        assert not caplog.records

    def test_has_grammar_never_announces(self, caplog):
        with patch('tree_sitter_language_pack.downloaded_languages', return_value=[]):
            with caplog.at_level('WARNING', logger=seam.__name__):
                assert seam.has_grammar('python') is True
                assert seam.has_grammar('no-such-language') is False
        assert not caplog.records

    def test_downloaded_languages_without_the_pack_is_empty(self):
        with patch.dict(sys.modules, {'tree_sitter_language_pack': None}):
            assert seam.downloaded_languages() == set()


def _go_tree(tmp_path: Path) -> Path:
    (tmp_path / 'main.go').write_text(textwrap.dedent('''\
        package main

        import "os"

        func main() {
            _ = os.Getenv("API_TOKEN")
        }
    '''), encoding='utf-8')
    return tmp_path


def _no_go_grammar():
    import tree_sitter_language_pack as tslp
    real = tslp.get_parser

    def get_parser(language):
        if language == 'go':
            raise RuntimeError('Download error: no network')
        return real(language)
    return patch('tree_sitter_language_pack.get_parser', side_effect=get_parser)


class TestMissingGrammarIsDisclosed:
    """surface:// on a Go file with no Go grammar used to report 0 entries and nothing
    else -- the same answer as a Go file with no surface."""

    def test_positive_control_go_surface_is_found(self, tmp_path):
        from reveal.adapters.surface import _scan_surface
        report = _scan_surface(_go_tree(tmp_path))
        assert any(e.get('name') == 'API_TOKEN' for e in report['surfaces']['env']), report['surfaces']['env']
        assert report['unparsed_files'] == []

    def test_file_without_a_grammar_is_reported_unparsed(self, tmp_path):
        from reveal.adapters.surface import _scan_surface
        with _no_go_grammar():
            report = _scan_surface(_go_tree(tmp_path))
        assert report['total'] == 0
        assert report['unparsed_files'] == ['main.go']
        assert any('could not be parsed' in limit for limit in report['_meta']['known_limits'])


def _go_contracts_tree(root: Path) -> Path:
    (root / 'proj').mkdir()
    (root / 'proj' / 'main.go').write_text(textwrap.dedent('''\
        package main

        type Shape interface {
            Area() float64
        }

        type Square struct{}

        func (s Square) Area() float64 { return 1 }
    '''), encoding='utf-8')
    return Path('proj')


class TestMissingGrammarIsDisclosedByContracts:
    """contracts:// on a Go tree with no Go grammar reported 0 contracts and nothing
    else, the same answer as a Go tree with no interfaces (BACK-1588)."""

    def test_positive_control_go_interface_is_found(self, tmp_path, monkeypatch):
        from reveal.adapters.contracts import _scan_contracts
        monkeypatch.chdir(tmp_path)
        report = _scan_contracts(_go_contracts_tree(tmp_path))
        assert [c['name'] for c in report['protocols']] == ['Shape']
        assert report['unparsed_files'] == []

    def test_file_without_a_grammar_is_reported_unparsed(self, tmp_path, monkeypatch, capsys):
        from reveal.adapters.contracts import ContractsAdapter, ContractsRenderer
        monkeypatch.chdir(tmp_path)
        _go_contracts_tree(tmp_path)
        with _no_go_grammar():
            result = ContractsAdapter('proj').get_structure()
        assert result['total_contracts'] == 0
        assert result['unparsed_files'] == ['proj/main.go']
        assert any(w['code'] == 'W-CONTRACTS-2' and 'proj/main.go' in w['message']
                   for w in result['meta']['warnings'])
        ContractsRenderer.render_structure(result, 'text')
        assert '1 file(s) could not be parsed and contribute no entries: proj/main.go' in capsys.readouterr().out

    def test_polyglot_tree_carries_the_unparsed_go_file_to_the_top(self, tmp_path, monkeypatch):
        from reveal.adapters.contracts import _scan_contracts
        monkeypatch.chdir(tmp_path)
        _go_contracts_tree(tmp_path)
        (tmp_path / 'proj' / 'shapes.py').write_text(
            'from abc import ABC, abstractmethod\n\n\nclass Base(ABC):\n'
            '    @abstractmethod\n    def area(self): ...\n', encoding='utf-8')
        with _no_go_grammar():
            report = _scan_contracts(Path('proj'))
        assert report['unparsed_files'] == ['proj/main.go']
        assert report['by_language']['go']['unparsed_files'] == ['proj/main.go']
        assert report['total_contracts'] == 1   # the Python ABC still counts

"""Required parser loss must survive the existing shared AST outcome boundary."""
import copy
from pathlib import Path

import pytest

from reveal import treesitter
from reveal.adapters.ast import analysis
from reveal.adapters.ast.adapter import AstAdapter
from reveal.analyzers.go import GoAnalyzer
from reveal.core.treesitter_parse import GrammarUnavailable

pytestmark = pytest.mark.component

FUNCTION = {
    'name': 'main', 'line': 3, 'line_end': 3, 'line_count': 1,
    'signature': 'func main() {}', 'calls': [],
}


@pytest.fixture
def source(tmp_path):
    path = tmp_path / 'input.go'
    path.write_text('package demo\n\nfunc main() {}\n', encoding='utf-8')
    return path


def _provide(monkeypatch, raw, *, parse_error=None):
    """A registered analyzer response, through the real two-tuple entry point."""
    class Analyzer:
        def __init__(self, path):
            self.content = 'package demo\n\nfunc main() {}\n'
            self.lines = self.content.split('\n')
            self.parse_error = parse_error

        def get_structure(self):
            return copy.deepcopy(raw)

        def get_outline(self):
            return self.get_structure()

    monkeypatch.setattr('reveal.registry.get_analyzer', lambda *args, **kwargs: Analyzer)
    monkeypatch.setattr(analysis, 'build_symbol_map', lambda path: {})


@pytest.mark.parametrize('outline', [False, True])
def test_real_unavailable_grammar_is_an_attributed_failure(source, monkeypatch, outline):
    def unavailable(language, *args, **kwargs):
        raise GrammarUnavailable(language, RuntimeError('required grammar unavailable'))

    monkeypatch.setattr(treesitter, 'get_tree', unavailable)
    structure, failure = analysis.analyze_file_outcome(str(source), outline=outline)
    assert structure is None
    assert failure and 'grammar' in failure and 'go' in failure


@pytest.mark.parametrize('outline', [False, True])
def test_empty_caught_parser_exception_is_still_a_failure(source, monkeypatch, outline):
    def broken(*args, **kwargs):
        raise RuntimeError()

    monkeypatch.setattr(treesitter, 'get_tree', broken)
    structure, failure = analysis.analyze_file_outcome(str(source), outline=outline)
    assert structure is None
    assert isinstance(failure, str) and failure.strip()


def test_parse_error_is_not_hidden_by_surviving_returned_elements(source, monkeypatch):
    _provide(monkeypatch, {'functions': [FUNCTION]}, parse_error='required parse failed')
    structure, failure = analysis.analyze_file_outcome(str(source))
    assert failure and 'required parse failed' in failure
    assert structure and [item['name'] for item in structure['elements']] == ['main']


@pytest.mark.parametrize('raw', [None, [], False, 0, ''])
def test_malformed_falsy_required_response_is_not_clean_empty(source, monkeypatch, raw):
    _provide(monkeypatch, raw)
    structure, failure = analysis.analyze_file_outcome(str(source))
    assert structure is None
    assert failure, f'malformed response {raw!r} was treated as a clean empty mapping'


@pytest.mark.parametrize('raw', [
    {'functions': 'not a collection'},
    {'functions': [None]},
    {'imports': [42]},
])
def test_malformed_consumed_categories_are_disclosed(source, monkeypatch, raw):
    _provide(monkeypatch, raw)
    structure, failure = analysis.analyze_file_outcome(str(source))
    assert structure is None
    assert failure


def test_malformed_member_keeps_valid_sibling_observations(source, monkeypatch):
    _provide(monkeypatch, {'functions': [FUNCTION, None]})
    structure, failure = analysis.analyze_file_outcome(str(source))
    assert failure
    assert structure and [item['name'] for item in structure['elements']] == ['main']


def test_required_metadata_failure_survives_flattening_and_collection(source, monkeypatch):
    _provide(monkeypatch, {
        'functions': [FUNCTION],
        'meta': {'errors': [{'code': 'analysis_failed', 'message': 'required structure branch failed'}]},
    })
    structure, failure = analysis.analyze_file_outcome(str(source))
    assert failure and 'required structure branch failed' in failure
    assert structure and [item['name'] for item in structure['elements']] == ['main']
    collected = analysis.collect_structures(str(source))
    assert [item['name'] for item in collected[0]['elements']] == ['main']
    assert collected.skipped and collected.skipped[0][0] == str(source)
    assert 'required structure branch failed' in collected.skipped[0][1]


def test_lost_grammar_reaches_existing_ast_result_beside_usable_file(tmp_path, monkeypatch):
    good = tmp_path / 'good.go'
    lost = tmp_path / 'lost.go'
    for path in (good, lost):
        path.write_text('package demo\n\nfunc main() {}\n', encoding='utf-8')
    original = treesitter.get_tree

    def parse(language, *args, **kwargs):
        if Path(kwargs.get('filename', '')).name == lost.name:
            raise GrammarUnavailable(language, RuntimeError('required fixture grammar unavailable'))
        return original(language, *args, **kwargs)

    monkeypatch.setattr(treesitter, 'get_tree', parse)
    answer = AstAdapter(str(tmp_path), 'complexity>0').get_structure()
    assert any(item['file'].endswith(good.name) for item in answer['results'])
    warnings = [entry for entry in answer['meta']['warnings'] if entry.get('type') == 'analysis_failed']
    assert len(warnings) == 1
    assert warnings[0]['files'] == [lost.as_posix()]


@pytest.mark.parametrize('outline', [False, True])
def test_clean_constant_source_remains_clean_empty(tmp_path, outline):
    path = tmp_path / 'constants.go'
    path.write_text('package demo\n\nconst Answer = 42\n', encoding='utf-8')
    assert analysis.analyze_file_outcome(str(path), outline=outline) == (None, None)


@pytest.mark.disk_cache
def test_clean_cached_go_structure_needs_no_fresh_parser(tmp_path, monkeypatch):
    monkeypatch.setenv('REVEAL_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setenv('REVEAL_DISK_CACHE', '1')
    path = tmp_path / 'constants.go'
    path.write_text('package demo\n\nconst Answer = 42\n', encoding='utf-8')
    assert GoAnalyzer(str(path)).get_structure() == {}
    treesitter._get_parse_cache().clear()

    def unexpected_parse(*args, **kwargs):
        pytest.fail('a supported cached structure must not require a fresh parser')

    monkeypatch.setattr(treesitter, 'get_tree', unexpected_parse)
    assert analysis.analyze_file_outcome(str(path)) == (None, None)


def test_clean_empty_mapping_and_unsupported_input_stay_distinct_from_failure(source, monkeypatch):
    _provide(monkeypatch, {})
    assert analysis.analyze_file_outcome(str(source)) == (None, None)
    monkeypatch.setattr('reveal.registry.get_analyzer', lambda *args, **kwargs: None)
    assert analysis.analyze_file_outcome(str(source)) == (None, None)


def test_valid_empty_categories_are_not_malformed(source, monkeypatch):
    _provide(monkeypatch, {'functions': [], 'imports': []})
    structure, failure = analysis.analyze_file_outcome(str(source))
    assert failure is None
    assert structure['elements'] == []


def test_optional_enrichment_and_harmless_metadata_do_not_fail_required_structure(source, monkeypatch):
    _provide(monkeypatch, {
        'functions': [FUNCTION], '_imports_failed': 'RuntimeError: optional import enrichment',
        'metadata': {'note': 'harmless analyzer metadata'},
        'language': 'go', 'source_summary': 42,
        'meta': {'warnings': [{'type': 'imports_failed', 'message': 'optional import enrichment'}]},
    })

    def optional_failure(path):
        raise RuntimeError('optional cross-file import enrichment')

    monkeypatch.setattr(analysis, 'build_symbol_map', optional_failure)
    structure, failure = analysis.analyze_file_outcome(str(source))
    assert failure is None
    assert [item['name'] for item in structure['elements']] == ['main']


def test_recovered_parse_retains_existing_observations_and_flag(tmp_path):
    path = tmp_path / 'recovered.py'
    path.write_text('def good():\n    return 1\n\ndef bad(:\n', encoding='utf-8')
    structure, failure = analysis.analyze_file_outcome(str(path))
    assert failure is None
    assert structure['parse_recovered'] is True
    assert any(item['name'] == 'good' for item in structure['elements'])

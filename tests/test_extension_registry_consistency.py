"""BACK-1255: extension lists must agree with the analyzer registry.

Every subsystem that claims a set of languages used to keep its own extension
list, and each one drifted when an extension was registered: surface/contracts/
M104/B005 missed .mts/.cts (BACK-1403), surface/contracts/the C++ import
extractor missed .h++, capabilities reported no element types for .mts/.kts/
.hpp, and `reveal --languages` advertised ten fallback languages (Julia, Perl,
Nim, ...) that reveal could not open. These tests fail when a consumer's list
and the registry disagree, so the next newly registered extension cannot be
silently skipped by one of them.
"""

from collections import defaultdict

import pytest

import reveal.analyzers.imports  # noqa: F401  (registers every import extractor)
from reveal.analyzers.imports.base import _EXTRACTOR_REGISTRY
from reveal.registry import (
    JS_TS_LANGUAGES,
    extensions_for_languages,
    fallback_languages,
    get_analyzer,
    get_analyzer_mapping,
    js_ts_grammar,
    language_for_extension,
)

JS_TS = extensions_for_languages(*JS_TS_LANGUAGES)


def test_extensions_for_languages_is_the_inverse_of_language_for_extension():
    for ext in extensions_for_languages('cpp', 'typescript'):
        assert language_for_extension(ext) in ('cpp', 'typescript')
    assert {'.mts', '.cts', '.ts'} == extensions_for_languages('typescript')
    assert {'.h++', '.hxx', '.hpp', '.cpp'} <= extensions_for_languages('cpp')
    assert extensions_for_languages('no-such-language') == frozenset()


@pytest.mark.parametrize('ext,grammar', [
    ('.ts', 'typescript'), ('.mts', 'typescript'), ('.cts', 'typescript'),
    ('.tsx', 'tsx'), ('.jsx', 'tsx'), ('.js', 'tsx'), ('.mjs', 'tsx'), ('.cjs', 'tsx'),
])
def test_js_ts_grammar(ext, grammar):
    assert js_ts_grammar(ext) == grammar


def test_hxx_uses_the_cpp_analyzer_not_the_fallback():
    cls = get_analyzer('x.hxx', allow_fallback=False)
    assert cls is not None and cls.__name__ == 'CppAnalyzer'
    assert '.hxx' not in fallback_languages()


def test_fallback_languages_route_to_a_fallback_analyzer():
    for ext in fallback_languages():
        cls = get_analyzer(f'x{ext}')
        assert cls is not None and getattr(cls, 'is_fallback', False), ext


def test_every_advertised_fallback_language_opens():
    """`reveal --languages` once listed Julia/Perl/Nim/... that get_analyzer()
    rejected with 'No analyzer found'."""
    from reveal.cli.languages import _get_fallback_languages
    from reveal.main import _get_tree_sitter_fallbacks
    advertised = [ext for _, exts in _get_fallback_languages() for ext in exts]
    advertised += [ext for _, ext in _get_tree_sitter_fallbacks(get_analyzer_mapping())]
    assert advertised
    for ext in advertised:
        assert get_analyzer(f'x{ext}') is not None, f'{ext} is advertised but does not open'


def test_surface_scans_every_extension_of_its_languages():
    from reveal.adapters.surface import _SURFACE_SCANNERS, _supported_coverage_languages
    scanned = set().union(*(s.extensions for s in _SURFACE_SCANNERS))
    assert extensions_for_languages(*_supported_coverage_languages()) <= scanned


def test_surface_facts_maps_every_extension_of_its_languages():
    from reveal.adapters.ast.surface_facts import EXTENSION_LANGUAGE, LANGUAGES
    for lang in LANGUAGES:
        for ext in extensions_for_languages(lang):
            assert EXTENSION_LANGUAGE.get(ext) in LANGUAGES, ext
    assert all(EXTENSION_LANGUAGE[ext] == js_ts_grammar(ext) for ext in JS_TS)


def test_contracts_extension_sets_match_the_registry():
    from reveal.adapters.contracts import _CPP_EXTENSIONS, _INTERFACE_FAMILY_EXTENSIONS
    assert JS_TS <= _INTERFACE_FAMILY_EXTENSIONS
    assert _CPP_EXTENSIONS == extensions_for_languages('cpp')


def test_rules_cover_every_extension_of_their_languages():
    from reveal.rules.bugs.B005 import B005
    from reveal.rules.maintainability.M104 import M104
    from reveal.rules.maintainability._m104_treesitter import SUPPORTED_LANGUAGES
    assert extensions_for_languages(*SUPPORTED_LANGUAGES) <= set(M104.file_patterns)
    assert JS_TS <= set(B005.file_patterns)
    from reveal.rules.bugs.B006 import B006
    assert JS_TS | extensions_for_languages('cpp') <= set(B006.file_patterns)


@pytest.mark.parametrize('ext', ['.tsx', '.mts', '.cts'])
def test_b006_flags_a_silent_catch_in_every_ts_extension(ext):
    """B006 skipped .tsx/.mts/.cts entirely; each takes the right grammar now."""
    from reveal.rules.bugs.B006 import B006
    src = 'export function f() {\n  try { g(); } catch (e) {}\n}\n'
    if ext == '.tsx':
        src += 'export const V = () => <div>{f()}</div>;\n'
    assert [d.rule_code for d in B006().check(f'x{ext}', None, src)] == ['B006']


def test_testability_scans_every_js_ts_test_extension():
    from reveal.testability.patches import _TS_TEST_EXTENSIONS
    assert _TS_TEST_EXTENSIONS == JS_TS


def test_pascal_test_suffix_languages_match_the_registry():
    from reveal.utils.path_utils import _PASCAL_TEST_SUFFIX_EXTENSIONS
    assert _PASCAL_TEST_SUFFIX_EXTENSIONS == extensions_for_languages(
        'java', 'kotlin', 'csharp', 'swift', 'php')


@pytest.mark.parametrize('languages,name', [
    (('c', 'cpp'), 'user_tests{ext}'),
    (('kotlin',), 'UserTest{ext}'),
])
def test_convention_test_file_patterns_accept_every_family_extension(languages, name):
    """conventions.py test_file_patterns re-listed extensions and missed .h++/.kts."""
    from reveal.utils.path_utils import is_test_basename_for_language
    for ext in extensions_for_languages(*languages):
        assert is_test_basename_for_language(name.format(ext=ext)), ext


# Extractor extensions deliberately outside their languages' registry family.
_EXTRACTOR_EXTRAS = {
    'PythonExtractor': {'.pyi'},     # stubs: no analyzer, but imports are real
    'CppImportExtractor': {'.mm'},   # Obj-C++ includes (BACK-664); .m stays out
}


def test_import_extractors_claim_exactly_their_languages_extensions():
    by_class = defaultdict(set)
    for ext, cls in _EXTRACTOR_REGISTRY.items():
        by_class[cls.__name__].add(ext)
    for name, exts in by_class.items():
        extras = _EXTRACTOR_EXTRAS.get(name, set())
        languages = {language_for_extension(e) for e in exts - extras} - {None}
        if not languages:
            continue
        assert exts - extras == extensions_for_languages(*languages), name


def test_capabilities_report_types_for_every_extension_of_a_language():
    from reveal.cli.introspection import _EXTRACTABLE_BY_LANGUAGE, _get_extractable_types
    for lang, types in _EXTRACTABLE_BY_LANGUAGE.items():
        for ext in extensions_for_languages(lang):
            if ext == '.tfvars':
                continue  # variables only, by design
            assert _get_extractable_types(ext, is_fallback=False) == types, ext


def test_mts_and_hpp_plus_plus_files_are_scanned_end_to_end(tmp_path):
    """The two drifts this ticket found, through the real scanners."""
    from reveal.adapters.contracts import _scan_contracts
    from reveal.adapters.surface import _scan_surface
    (tmp_path / 'svc.mts').write_text(
        'export interface Store { get(k: string): string }\n', encoding='utf-8')
    (tmp_path / 'io.h++').write_text(
        '#include <cstdlib>\nconst char* home() { return std::getenv("HOME"); }\n',
        encoding='utf-8')
    by_language = _scan_contracts(tmp_path)['by_language']
    assert [c['name'] for c in by_language['ts']['protocols']] == ['Store']
    assert 'cpp' in by_language  # the .h++ file activates the C++ scanner
    env = [e['name'] for e in _scan_surface(tmp_path)['surfaces']['env']]
    assert 'HOME' in env

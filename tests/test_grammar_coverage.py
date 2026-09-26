"""Grammar coverage (BACK-1364): the hand-typed node-kind tables are checked against the
grammars themselves.

About 30 fixes in 0.128-0.129 were one node kind missing from one table, each found in the
field (BACK-1088, 1316-1318, 1409, 1410, 1432, ...). Nothing compared the tables with the
grammars, so a grammar bump or a new language added kinds silently. The kinds come from
the installed grammars at runtime (``Language.node_kind_*``); tree-sitter-language-pack
ships no node-types.json.

Two checks:

``test_table_kinds_exist_in_a_grammar``
    Every kind in a central table exists in at least one grammar reveal can parse: a
    registered analyzer's, or a fallback one from ``TREESITTER_EXTENSION_MAP``. This
    catches typos and dead entries. Anonymous kinds count, because PHP's bare ``if`` and
    the keyword tokens in ``RETURN_NODES`` are deliberate.
``test_control_flow_kinds_are_classified``
    For each registered language, every named kind whose name holds a control-flow word
    (``CONTROL_FLOW_STEM``) is either named by a central table, listed in ``IGNORED`` with
    the reason, or listed in ``KNOWN_GAPS`` with the task that fixes it.

The central tables are the set-valued names in ``CENTRAL_MODULES``: ``core/node_taxonomy``
(the families every nav view unions), ``complexity`` and ``treesitter``. A kind that only a
rule or a per-language module knows still fails, because that knowledge belongs in a
family.

Both lists can only shrink. ``test_no_stale_entries`` fails on an entry whose kind a
central table now names, so a fix is not done until its row is deleted. It tolerates an
entry whose kind the installed grammar lacks, because the matrix also runs the oldest
supported language pack.

Limits:
- The families are cross-language, so a name classified for one grammar counts for every
  grammar. For example, Kotlin's ``try_expression`` passes because complexity names Rust's
  (BACK-1530).
- Wrapper kinds without a control-flow word, such as Kotlin ``jump_expression`` and Swift
  ``control_transfer_statement``, are out of reach of the name check (BACK-1527).
- Declaration and call kinds get the existence check only.

When ``test_control_flow_kinds_are_classified`` fails after a grammar bump or a new
language, add the kind to its family in ``core/node_taxonomy``, and to
``complexity._DECISION_TYPES`` when it is a decision. If it is not runtime control flow,
add it to ``IGNORED`` with the reason.
"""

import importlib
import re
from functools import lru_cache
from typing import Dict, FrozenSet, Iterable, Mapping, Set, Tuple

import pytest
from tree_sitter_language_pack import get_language

import reveal.analyzers  # noqa: F401  -- registers every analyzer
from reveal.registry import TREESITTER_EXTENSION_MAP, get_analyzer_mapping
from reveal.treesitter import TreeSitterAnalyzer

pytestmark = pytest.mark.conformance

CENTRAL_MODULES = ('reveal.core.node_taxonomy', 'reveal.complexity', 'reveal.treesitter')
# Set-valued names in CENTRAL_MODULES that hold something other than node kinds.
NOT_KIND_TABLES = {
    ('reveal.core.node_taxonomy', 'RUBY_ITERATOR_METHODS'): 'Ruby method names',
    ('reveal.core.node_taxonomy', 'RUBY_LOOP_METHODS'): 'Ruby method names',
}

CONTROL_FLOW_STEM = re.compile(
    r'(^|_)(if|elif|elsif|else|unless|for|foreach|while|until|loop|do|switch|case|when|'
    r'match|catch|rescue|except|try|finally|ensure|return|break|continue|throw|raise|'
    r'yield|goto|guard|defer)(_|$)')

_PART = 'part of a construct (body, header, condition, guard, parameter); the family matches the construct'
_PREPROC = 'preprocessor directive, not runtime control flow'
_NOT_PROCEDURAL = 'keyword or clause of a non-procedural language; reveal models no control flow for it'
_NAME_ONLY = 'the name holds a control-flow word, but the kind is a type, declaration or pattern'

# Kinds that are not control flow a family should hold. Durable: an entry stays until the
# grammar drops the kind.
IGNORED: Dict[str, Dict[str, str]] = {
    'bash': {'do_group': _PART},
    'c': {
        'gnu_asm_goto_list': _NAME_ONLY,
        'preproc_elif': _PREPROC, 'preproc_else': _PREPROC, 'preproc_if': _PREPROC,
    },
    'cpp': {
        'gnu_asm_goto_list': _NAME_ONLY,
        'preproc_elif': _PREPROC, 'preproc_else': _PREPROC, 'preproc_if': _PREPROC,
        'throw_specifier': _NAME_ONLY, 'trailing_return_type': _NAME_ONLY,
    },
    'csharp': {
        'catch_declaration': _PART, 'catch_filter_clause': _PART,
        'preproc_elif': _PREPROC, 'preproc_else': _PREPROC, 'preproc_if': _PREPROC,
        'preproc_if_in_attribute_list': _PREPROC,
        'switch_body': _PART, 'when_clause': _PART,
    },
    'dart': {
        'break_builtin': _PART, 'catch_parameters': _PART, 'for_loop_parts': _PART,
        'switch_block': _PART,
    },
    'gdscript': {'match_body': _PART, 'pattern_guard': _PART},
    'go': {'for_clause': _PART},
    'hcl': {kind: _NOT_PROCEDURAL for kind in (
        'for_cond', 'for_expr', 'for_intro', 'for_object_expr', 'for_tuple_expr',
        'template_else_intro', 'template_for', 'template_for_end', 'template_for_start',
        'template_if', 'template_if_end', 'template_if_intro')},
    'java': {
        'catch_formal_parameter': _PART, 'catch_type': _PART, 'guard': _PART,
        'switch_block': _PART, 'switch_block_statement_group': _PART,
    },
    'javascript': {'switch_body': _PART},
    'kotlin': {'guard_condition': _PART, 'when_condition': _PART, 'when_subject': _PART},
    'lua': {'for_generic_clause': _PART, 'for_numeric_clause': _PART},
    'markdown': {'thematic_break': _NAME_ONLY},
    'php': {
        'enum_case': _NAME_ONLY, 'match_block': _PART, 'match_condition_list': _PART,
        'switch_block': _PART,
    },
    'powershell': {kind: _PART for kind in (
        'catch_clauses', 'catch_type_list', 'for_condition', 'for_initializer',
        'for_iterator', 'foreach_parameter', 'switch_body', 'switch_clause_condition',
        'switch_clauses', 'switch_condition', 'switch_filename', 'switch_parameter',
        'switch_parameters', 'while_condition')},
    'ruby': {'do': _PART, 'if_guard': _PART, 'unless_guard': _PART},
    'rust': {'for_lifetimes': _NAME_ONLY, 'match_block': _PART},
    'scala': {
        'case_block': _PART, 'guard': _PART,
        'case_class_pattern': _NAME_ONLY, 'enum_case_definitions': _NAME_ONLY,
        'full_enum_case': _NAME_ONLY, 'simple_enum_case': _NAME_ONLY,
        'match_type': _NAME_ONLY, 'type_case_clause': _NAME_ONLY,
    },
    'sql': {kind: _NOT_PROCEDURAL for kind in (
        'keyword_case', 'keyword_do', 'keyword_else', 'keyword_except', 'keyword_for',
        'keyword_if', 'keyword_match', 'keyword_return', 'keyword_until', 'keyword_when',
        'keyword_while', 'when_clause')},
    'swift': {
        'catch_keyword': _PART, 'switch_pattern': _PART,
        'try_operator': 'marks a throwing call and does not branch (see complexity._OPERATOR_TOKEN_PARENTS)',
    },
    'tsx': {'switch_body': _PART},
    'typescript': {'switch_body': _PART},
}

# Control flow that no family holds yet. Each row names its task and is deleted by the
# fix; test_no_stale_entries enforces that.
KNOWN_GAPS: Dict[str, Dict[str, str]] = {
    'bash': {'case_item': 'BACK-1531'},
    'c': {
        'goto_statement': 'BACK-1531', 'seh_except_clause': 'BACK-1531',
        'seh_finally_clause': 'BACK-1531', 'seh_try_statement': 'BACK-1531',
    },
    'cpp': {
        'co_return_statement': 'BACK-1527', 'co_yield_statement': 'BACK-1527',
        'goto_statement': 'BACK-1531', 'seh_except_clause': 'BACK-1531',
        'seh_finally_clause': 'BACK-1531', 'seh_try_statement': 'BACK-1531',
    },
    'csharp': {'goto_statement': 'BACK-1531'},
    'dart': {
        'yield_each_statement': 'BACK-1527',
        'for_element': 'BACK-1531', 'if_element': 'BACK-1531',
        'switch_statement_case': 'BACK-1531', 'switch_statement_default': 'BACK-1531',
        'throw_expression_without_cascade': 'BACK-1531',
    },
    'elixir': {'else_block': 'BACK-1531', 'rescue_block': 'BACK-1531'},
    'go': {
        'defer_statement': 'BACK-1531', 'goto_statement': 'BACK-1531',
    },
    'java': {
        'try_with_resources_statement': 'BACK-1530',
        'switch_rule': 'BACK-1531',
    },
    'javascript': {'yield_expression': 'BACK-1527'},
    'lua': {'else_statement': 'BACK-1530', 'goto_statement': 'BACK-1531'},
    'php': {
        'yield_expression': 'BACK-1527', 'goto_statement': 'BACK-1531',
    },
    'powershell': {'invokation_foreach_expression': 'BACK-1531', 'switch_clause': 'BACK-1531'},
    'python': {'for_in_clause': 'BACK-1531', 'if_clause': 'BACK-1531'},
    'ruby': {
        'rescue_modifier': 'BACK-1530',
    },
    'rust': {
        'break_expression': 'BACK-1527', 'continue_expression': 'BACK-1527',
        'return_expression': 'BACK-1527', 'yield_expression': 'BACK-1527',
        'try_block': 'BACK-1531',
    },
    'scala': {'return_expression': 'BACK-1527'},
    'tsx': {'yield_expression': 'BACK-1527'},
    'typescript': {'yield_expression': 'BACK-1527'},
}


def _registered_languages() -> Tuple[str, ...]:
    """Grammars behind a registered (non-fallback) tree-sitter analyzer."""
    return tuple(sorted({
        cls.language for cls in get_analyzer_mapping().values()
        if isinstance(cls, type) and issubclass(cls, TreeSitterAnalyzer)
        and getattr(cls, 'language', None)}))


LANGUAGES = _registered_languages()


@lru_cache(maxsize=None)
def grammar_kinds(language: str) -> Tuple[FrozenSet[str], FrozenSet[str]]:
    """(named, all) node kinds that can appear in a tree of ``language``."""
    lang = get_language(language)
    named: Set[str] = set()
    every: Set[str] = set()
    for kind_id in range(lang.node_kind_count):
        kind = lang.node_kind_for_id(kind_id)
        if not kind or not lang.node_kind_is_visible(kind_id):
            continue
        every.add(kind)
        if lang.node_kind_is_named(kind_id):
            named.add(kind)
    return frozenset(named), frozenset(every)


# A table is a module constant (``CALL_NODE_TYPES``, ``_DECISION_TYPES``). Lowercase names are
# runtime state: treesitter's ``_warned_uncached_languages`` fills with language names while
# tests run, and read as a dead node kind 'python' depending on test order.
_CONSTANT = re.compile(r'_?[A-Z][A-Z0-9_]*')


def central_tables() -> Dict[str, FrozenSet[str]]:
    """``module.NAME -> kinds`` for every set-of-strings constant in CENTRAL_MODULES
    (dict values too)."""
    tables: Dict[str, FrozenSet[str]] = {}
    for modname in CENTRAL_MODULES:
        for name, value in vars(importlib.import_module(modname)).items():
            if (modname, name) in NOT_KIND_TABLES or not _CONSTANT.fullmatch(name):
                continue
            candidates = value.items() if isinstance(value, dict) else [(None, value)]
            for key, table in candidates:
                if isinstance(table, (set, frozenset)) and table and all(isinstance(k, str) for k in table):
                    tables[f'{modname}.{name}' + (f'[{key!r}]' if key is not None else '')] = frozenset(table)
    return tables


def classified_kinds() -> FrozenSet[str]:
    return frozenset().union(*central_tables().values())


def unexplained_kinds(named: Iterable[str], classified: FrozenSet[str],
                      *allowed: Mapping[str, str]) -> Set[str]:
    """Control-flow-named kinds in ``named`` that no table classifies and no list explains."""
    return {kind for kind in named
            if CONTROL_FLOW_STEM.search(kind) and kind not in classified
            and not any(kind in entries for entries in allowed)}


def stale_entries(named: FrozenSet[str], classified: FrozenSet[str],
                  entries: Mapping[str, str]) -> Set[str]:
    """Entries the list no longer needs: the kind is classified now, or it no longer has a
    control-flow word. A kind missing from this grammar version is tolerated."""
    return {kind for kind in entries
            if kind in named and (kind in classified or not CONTROL_FLOW_STEM.search(kind))}


def missing_kinds(table: FrozenSet[str], kinds_of: Mapping[str, FrozenSet[str]]) -> Set[str]:
    """Kinds in ``table`` that no grammar in ``kinds_of`` (language -> all kinds) defines."""
    return set(table).difference(*kinds_of.values())


# ---------------------------------------------------------------------------
# The checks
# ---------------------------------------------------------------------------

def test_every_registered_language_is_checked():
    assert len(LANGUAGES) >= 25, f'registry discovery broke: only {LANGUAGES}'
    unknown = (set(IGNORED) | set(KNOWN_GAPS)) - set(LANGUAGES)
    assert not unknown, f'entries for languages with no registered analyzer: {sorted(unknown)}'


def test_table_kinds_exist_in_a_grammar():
    kinds_of = {lang: grammar_kinds(lang)[1] for lang in LANGUAGES}
    dead = {name: missing_kinds(table, kinds_of) for name, table in central_tables().items()}
    dead = {name: kinds for name, kinds in dead.items() if kinds}
    if dead:
        # Fallback grammars are loaded only on a miss, so CI downloads no extra grammar
        # while the tables are clean.
        for lang in sorted(set(TREESITTER_EXTENSION_MAP.values()) - set(LANGUAGES)):
            try:
                kinds_of[lang] = grammar_kinds(lang)[1]
            except Exception:  # the installed pack lacks it; registry.fallback_languages skips it too
                continue
        dead = {name: missing_kinds(table, kinds_of) for name, table in central_tables().items()}
        dead = {name: sorted(kinds) for name, kinds in dead.items() if kinds}
    assert not dead, (
        f'node kinds that no grammar reveal can parse defines (a typo or a dead entry): {dead}')


@pytest.mark.parametrize('language', LANGUAGES)
def test_control_flow_kinds_are_classified(language):
    named, _ = grammar_kinds(language)
    new = unexplained_kinds(named, classified_kinds(),
                            IGNORED.get(language, {}), KNOWN_GAPS.get(language, {}))
    assert not new, (
        f'{language}: control-flow node kinds in no central table: {sorted(new)}. Add each '
        f'to its family in core/node_taxonomy (and complexity._DECISION_TYPES if it is a '
        f'decision), or to IGNORED in this file with the reason.')


@pytest.mark.parametrize('language', LANGUAGES)
def test_no_stale_entries(language):
    named, _ = grammar_kinds(language)
    classified = classified_kinds()
    stale = {name: sorted(stale_entries(named, classified, entries.get(language, {})))
             for name, entries in (('IGNORED', IGNORED), ('KNOWN_GAPS', KNOWN_GAPS))}
    stale = {name: kinds for name, kinds in stale.items() if kinds}
    assert not stale, (
        f'{language}: entries no longer needed (a central table names the kind now); '
        f'delete them: {stale}')


def test_ignored_and_known_gaps_do_not_overlap():
    both = {lang: sorted(set(IGNORED.get(lang, {})) & set(KNOWN_GAPS.get(lang, {})))
            for lang in LANGUAGES}
    assert not {lang: kinds for lang, kinds in both.items() if kinds}


def test_known_gaps_name_a_task():
    bad = {(lang, kind): task for lang, entries in KNOWN_GAPS.items()
           for kind, task in entries.items() if not re.fullmatch(r'BACK-\d+', task)}
    assert not bad


# ---------------------------------------------------------------------------
# Negative controls: each check fails on the defect it exists for
# ---------------------------------------------------------------------------

def test_runtime_state_is_not_a_table(monkeypatch):
    import reveal.treesitter
    monkeypatch.setattr(reveal.treesitter, '_warned_uncached_languages', {'python'})
    assert not any('_warned_' in name for name in central_tables())


def test_a_typo_in_a_table_is_caught():
    kinds_of = {'python': grammar_kinds('python')[1]}
    assert missing_kinds(frozenset({'if_statement', 'if_statment'}), kinds_of) == {'if_statment'}


def test_an_unclassified_control_flow_kind_is_caught():
    named = frozenset({'while_statement', 'repeat_until_statement', 'identifier'})
    assert unexplained_kinds(named, frozenset({'while_statement'})) == {'repeat_until_statement'}
    assert unexplained_kinds(named, frozenset({'while_statement'}),
                             {'repeat_until_statement': 'BACK-1'}) == set()


def test_python_grammar_flags_a_kind_removed_from_its_family():
    named, _ = grammar_kinds('python')
    assert unexplained_kinds(named, classified_kinds() - {'while_statement'},
                             IGNORED.get('python', {}), KNOWN_GAPS.get('python', {})) \
        == {'while_statement'}


def test_a_fixed_gap_is_stale_but_a_kind_the_grammar_lacks_is_not():
    named = frozenset({'do_while_statement', 'if_statement'})
    entries = {'do_while_statement': 'BACK-1', 'repeat_statement': 'BACK-2'}
    assert stale_entries(named, frozenset({'do_while_statement'}), entries) == {'do_while_statement'}
    assert stale_entries(named, frozenset(), entries) == set()

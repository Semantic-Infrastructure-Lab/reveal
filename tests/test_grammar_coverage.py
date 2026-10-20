"""Grammar coverage (BACK-1364): the hand-typed node-kind tables are checked against the
grammars themselves.

About 30 fixes in 0.128-0.129 were one node kind missing from one table, each found in the
field (BACK-1088, 1316-1318, 1409, 1410, 1432, ...). Nothing compared the tables with the
grammars, so a grammar bump or a new language added kinds silently. The kinds come from
the installed grammars at runtime (``Language.node_kind_*``); tree-sitter-language-pack
ships no node-types.json.

Three checks:

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
  grammar, and a kind that only ``complexity`` names passes although no nav family holds it.
  Ruby's ``until`` block, Lua's ``elseif_statement`` and Kotlin's ``try_expression`` all
  passed this way while --outline dropped them (BACK-1528, BACK-1530).
- Wrapper kinds without a control-flow word, such as Kotlin ``jump_expression`` and Swift
  ``control_transfer_statement``, are out of reach of the name check. Those two are
  ``node_taxonomy.JUMP_WRAPPER_NODES`` (BACK-1527).
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
        'goto_statement': 'BACK-1531', 'seh_except_clause': 'BACK-1531',
        'seh_finally_clause': 'BACK-1531', 'seh_try_statement': 'BACK-1531',
    },
    'csharp': {'goto_statement': 'BACK-1531'},
    'dart': {
        'for_element': 'BACK-1531', 'if_element': 'BACK-1531',
        'switch_statement_case': 'BACK-1531', 'switch_statement_default': 'BACK-1531',
        'throw_expression_without_cascade': 'BACK-1531',
    },
    'elixir': {'else_block': 'BACK-1531', 'rescue_block': 'BACK-1531'},
    'go': {'defer_statement': 'BACK-1531', 'goto_statement': 'BACK-1531'},
    'java': {'switch_rule': 'BACK-1531'},
    'lua': {'goto_statement': 'BACK-1531'},
    'php': {'goto_statement': 'BACK-1531'},
    'powershell': {'invokation_foreach_expression': 'BACK-1531', 'switch_clause': 'BACK-1531'},
    'python': {'for_in_clause': 'BACK-1531', 'if_clause': 'BACK-1531'},
    'rust': {'try_block': 'BACK-1531'},
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
# runtime state: treesitter's ``_warned_failed_languages`` fills with language names while
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
    monkeypatch.setattr(reveal.treesitter, '_warned_failed_languages', {'python'})
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


# ---------------------------------------------------------------------------
# Function-like kinds and the import edge scope (BACK-2076)
# ---------------------------------------------------------------------------
# node_taxonomy.edge_scope() calls an import 'local' when a LOCAL_SCOPE_NODES ancestor
# (DEF_NODES | LAMBDA_NODES) encloses it. For each grammar behind an import extractor,
# every named kind whose name holds a function-like word is in that family, explained in
# NOT_LOCAL_SCOPE, or a gap in LOCAL_SCOPE_GAPS that names its task. A new function-like
# kind from a grammar bump fails here instead of reading as module scope.

FUNCTION_LIKE_STEM = re.compile(
    r'(^|_)(function|func|fn|method|lambda|closure|constructor|arrow|init|deinit|getter|'
    r'setter|accessor|anonymous|generator)(_|$)|^(Decl|do_block)$')

_FN_PART = ('part of a function (signature, declarator, parameters, modifier, body wrapper), '
            'not the function')
_FN_NAME_ONLY = ('the name holds a function-like word, but the kind is a type, call, pattern '
                 'or initializer')
_FILE_LEVEL = 'imports are allowed only at file (or namespace) level, so no import sits in it'
_NOT_RUNTIME = 'a preprocessor macro, not a function body'

NOT_LOCAL_SCOPE: Dict[str, Dict[str, str]] = {
    'c': {'abstract_function_declarator': _FN_PART, 'function_declarator': _FN_PART,
          'init_declarator': _FN_NAME_ONLY, 'preproc_function_def': _NOT_RUNTIME},
    'cpp': {
        'abstract_function_declarator': _FN_PART, 'function_declarator': _FN_PART,
        'default_method_clause': _FN_PART, 'delete_method_clause': _FN_PART,
        'explicit_function_specifier': _FN_PART, 'init_declarator': _FN_NAME_ONLY,
        'init_statement': _FN_NAME_ONLY, 'lambda_capture_initializer': _FN_PART,
        'lambda_capture_specifier': _FN_PART, 'lambda_declarator': _FN_PART,
        'lambda_default_capture': _FN_PART, 'lambda_specifier': _FN_PART,
        'preproc_function_def': _NOT_RUNTIME,
        'template_function': _FN_NAME_ONLY, 'template_method': _FN_NAME_ONLY,
    },
    'csharp': {kind: _FILE_LEVEL for kind in (
        'accessor_declaration', 'anonymous_method_expression', 'lambda_expression',
        'local_function_statement')} | {
        'accessor_list': _FN_PART, 'arrow_expression_clause': _FN_PART,
        'constructor_initializer': _FN_PART,
        'anonymous_object_creation_expression': _FN_NAME_ONLY,
        'constructor_constraint': _FN_NAME_ONLY, 'function_pointer_parameter': _FN_NAME_ONLY,
        'function_pointer_type': _FN_NAME_ONLY, 'primary_constructor_base_type': _FN_NAME_ONLY,
    },
    # Dart's function_signature (DEF_NODES) is the sibling of its function_body, so a walk
    # up from a body never meets it; imports are file-level only, so no edge is affected.
    # function_expression (a Dart lambda) is in LOCAL_SCOPE_NODES through
    # FUNCTION_EXPRESSION_NODES, the JS/TS kind of the same name (BACK-2078).
    'dart': {kind: _FILE_LEVEL for kind in (
        'function_body', 'lambda_expression',
        'local_function_declaration', 'redirecting_factory_constructor_signature')} | {
        'function_expression_body': _FN_PART, 'method_signature': _FN_PART,
        'constructor_param': _FN_PART,
        'constructor_invocation': _FN_NAME_ONLY, 'constructor_tearoff': _FN_NAME_ONLY,
        'function_type': _FN_NAME_ONLY,
    },
    # GDScript 4 property bodies are get_body/set_body, which hold no function-like word:
    # out of this check's reach, like the wrapper kinds above (strict xfail in
    # tests/test_import_edge_scope_back2076.py, BACK-2079). getter/setter are the names.
    'gdscript': {'getter': _FN_NAME_ONLY, 'setter': _FN_NAME_ONLY},
    'go': {'func_literal': _FILE_LEVEL, 'function_type': _FN_NAME_ONLY,
           'method_elem': _FN_NAME_ONLY},
    'java': {kind: _FILE_LEVEL
             for kind in ('compact_constructor_declaration', 'lambda_expression')} | {
        'constructor_body': _FN_PART,
        'explicit_constructor_invocation': _FN_NAME_ONLY, 'method_invocation': _FN_NAME_ONLY,
        'method_reference': _FN_NAME_ONLY,
    },
    'kotlin': {kind: _FILE_LEVEL for kind in (
        'annotated_lambda', 'anonymous_function', 'anonymous_initializer', 'getter',
        'lambda_literal', 'secondary_constructor', 'setter')} | {
        'function_body': _FN_PART, 'function_modifier': _FN_PART,
        'function_value_parameters': _FN_PART, 'lambda_parameters': _FN_PART,
        'primary_constructor': _FN_PART,
        'constructor_delegation_call': _FN_NAME_ONLY, 'constructor_invocation': _FN_NAME_ONLY,
        'function_type': _FN_NAME_ONLY, 'function_type_parameters': _FN_NAME_ONLY,
    },
    'lua': {'function_call': _FN_NAME_ONLY, 'method_index_expression': _FN_NAME_ONLY,
            'table_constructor': _FN_NAME_ONLY},
    'php': {'anonymous_class': _FN_NAME_ONLY, 'anonymous_function_use_clause': _FN_PART,
            'function_call_expression': _FN_NAME_ONLY, 'function_static_declaration': _FN_PART},
    'python': {'generator_expression': _FN_NAME_ONLY, 'lambda_parameters': _FN_PART},
    'ruby': {'lambda_parameters': _FN_PART, 'method_parameters': _FN_PART,
             'setter': _FN_NAME_ONLY},
    'rust': {'closure_parameters': _FN_PART, 'function_modifiers': _FN_PART,
             'function_signature_item': 'a bodiless trait method signature',
             'function_type': _FN_NAME_ONLY, 'generic_function': _FN_NAME_ONLY},
    'scala': {'applied_constructor_type': _FN_NAME_ONLY, 'arrow_renamed_identifier': _FN_NAME_ONLY,
              'function_type': _FN_NAME_ONLY, 'generic_function': _FN_NAME_ONLY,
              'method_value': _FN_NAME_ONLY, 'type_lambda': _FN_NAME_ONLY},
    'swift': {kind: _FILE_LEVEL
              for kind in ('computed_getter', 'computed_setter', 'lambda_literal')} | {
        'function_body': _FN_PART, 'function_modifier': _FN_PART, 'getter_specifier': _FN_PART,
        'lambda_parameter': _FN_PART, 'setter_specifier': _FN_PART,
        'protocol_function_declaration': 'a bodiless protocol requirement',
        'constructor_expression': _FN_NAME_ONLY, 'constructor_suffix': _FN_NAME_ONLY,
        'function_type': _FN_NAME_ONLY, 'lambda_function_type': _FN_NAME_ONLY,
        'lambda_function_type_parameters': _FN_NAME_ONLY,
    },
    'typescript': {'abstract_method_signature': 'a bodiless signature',
                   'method_signature': 'a bodiless signature',
                   'constructor_type': _FN_NAME_ONLY, 'function_type': _FN_NAME_ONLY},
    'tsx': {'abstract_method_signature': 'a bodiless signature',
            'method_signature': 'a bodiless signature',
            'constructor_type': _FN_NAME_ONLY, 'function_type': _FN_NAME_ONLY},
}

# Function bodies an import can sit in that LOCAL_SCOPE_NODES does not hold: edge_scope()
# calls them module scope. Each row names its task and is deleted by the fix
# (tests/test_import_edge_scope_back2076.py has one strict xfail per language).
LOCAL_SCOPE_GAPS: Dict[str, Dict[str, str]] = {
    'cpp': {'lambda_expression': 'BACK-2079'},
    'php': {'anonymous_function': 'BACK-2079'},
    'ruby': {'do_block': 'BACK-2079'},
    'rust': {'closure_expression': 'BACK-2079'},
    'scala': {'lambda_expression': 'BACK-2079'},
}


def _import_languages() -> Tuple[str, ...]:
    """Grammars behind a registered import extractor."""
    from reveal.analyzers.imports.base import get_all_extensions
    mapping = get_analyzer_mapping()
    return tuple(sorted({getattr(mapping.get(ext), 'language', None)
                         for ext in get_all_extensions()} - {None}))


IMPORT_LANGUAGES = _import_languages()


def unscoped_function_kinds(named: Iterable[str], local: FrozenSet[str],
                            *allowed: Mapping[str, str]) -> Set[str]:
    """Function-like kinds in ``named`` outside ``local`` that no list explains."""
    return {kind for kind in named
            if FUNCTION_LIKE_STEM.search(kind) and kind not in local
            and not any(kind in entries for entries in allowed)}


def test_every_import_language_is_checked():
    assert len(IMPORT_LANGUAGES) >= 19, f'import extractor discovery broke: only {IMPORT_LANGUAGES}'
    unknown = (set(NOT_LOCAL_SCOPE) | set(LOCAL_SCOPE_GAPS)) - set(IMPORT_LANGUAGES)
    assert not unknown, f'entries for languages with no import extractor: {sorted(unknown)}'


@pytest.mark.parametrize('language', IMPORT_LANGUAGES)
def test_function_like_kinds_have_an_edge_scope(language):
    from reveal.core.node_taxonomy import LOCAL_SCOPE_NODES
    named, _ = grammar_kinds(language)
    new = unscoped_function_kinds(named, LOCAL_SCOPE_NODES, NOT_LOCAL_SCOPE.get(language, {}),
                                  LOCAL_SCOPE_GAPS.get(language, {}))
    assert not new, (
        f'{language}: function-like node kinds outside node_taxonomy.LOCAL_SCOPE_NODES: '
        f'{sorted(new)}. An import inside one reads as module scope. Add the kind to its '
        f'family (DEF_NODES or LAMBDA_NODES), or to NOT_LOCAL_SCOPE with the reason, or to '
        f'LOCAL_SCOPE_GAPS with its task.')


@pytest.mark.parametrize('language', IMPORT_LANGUAGES)
def test_no_stale_edge_scope_entries(language):
    from reveal.core.node_taxonomy import LOCAL_SCOPE_NODES
    named, _ = grammar_kinds(language)
    stale = {name: sorted(kind for kind in entries.get(language, {})
                          if kind in named and (kind in LOCAL_SCOPE_NODES
                                                or not FUNCTION_LIKE_STEM.search(kind)))
             for name, entries in (('NOT_LOCAL_SCOPE', NOT_LOCAL_SCOPE),
                                   ('LOCAL_SCOPE_GAPS', LOCAL_SCOPE_GAPS))}
    stale = {name: kinds for name, kinds in stale.items() if kinds}
    assert not stale, f'{language}: entries no longer needed; delete them: {stale}'


def test_edge_scope_lists_do_not_overlap_and_gaps_name_a_task():
    both = {lang: sorted(set(NOT_LOCAL_SCOPE.get(lang, {})) & set(LOCAL_SCOPE_GAPS.get(lang, {})))
            for lang in IMPORT_LANGUAGES}
    assert not {lang: kinds for lang, kinds in both.items() if kinds}
    assert not {(lang, kind): task for lang, entries in LOCAL_SCOPE_GAPS.items()
                for kind, task in entries.items() if not re.fullmatch(r'BACK-\d+', task)}


def test_an_unscoped_function_like_kind_is_caught():
    """Negative control: a kind taken out of LOCAL_SCOPE_NODES fails the check."""
    from reveal.core.node_taxonomy import LOCAL_SCOPE_NODES
    named, _ = grammar_kinds('python')
    assert unscoped_function_kinds(named, LOCAL_SCOPE_NODES - {'function_definition'},
                                   NOT_LOCAL_SCOPE['python']) == {'function_definition'}
    assert unscoped_function_kinds(frozenset({'arrow_function', 'local_lambda_block'}),
                                   frozenset({'arrow_function'})) == {'local_lambda_block'}

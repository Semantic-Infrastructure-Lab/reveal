"""Rule schema and engine for surface:// categories (BACK-1331, stage 2 of BACK-1329).

A category is a table of `Rule` rows over the neutral facts from `surface_facts`
(`Call` / `New` / `Import` / `Subshell`), one engine for every language. Adding a
language or a call shape is adding a row plus its examples, not writing a scanner walk.

    Rule(category='subprocess', lang='go',
         match=Call(receiver='exec', name=('Command', 'CommandContext')),
         entry_name='{path}',
         example='package main\\nfunc f() { exec.Command("ls") }\\n',
         counter_examples=('package main\\nfunc f(c cfg) { c.Command("x") }\\n',))

Semantics worth knowing:
  * per fact, the FIRST matching rule in table order wins (one entry per site);
  * entries are de-duplicated on (name, file, line), as the old scanners' `_add_once`;
  * `requires=ImportedFrom(m)` is provenance: the file must import module `m`
    (segment-aligned suffix, so `process::Command` matches `std::process::Command`);
  * `Call(resolved=True)` matches the import-resolved path (`import subprocess as sp;
    sp.run()` is `subprocess.run`), and only when the call's root name was imported;
  * every rule carries an `example` that must match and `counter_examples` that must not;
    `tests/test_surface_rules.py` generates its tests from these rows.

See internal-docs/design/SURFACE_RULE_TABLE_ARCHITECTURE_2026-09-20.md.
"""

import ast
import re
from functools import lru_cache
from fnmatch import fnmatchcase
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .surface_facts import CallFilter, FactCollector, NewFilter, python_facts_from_ast
from .surface_facts import Call as CallFact
from .surface_facts import Fact
from .surface_facts import Import as ImportFact
from .surface_facts import New as NewFact
from .surface_facts import Subshell as SubshellFact
from .surface_rules_model import (  # noqa: F401  (re-exported: callers use `surface_rules.Rule` etc.)
    CATEGORIES, Call, Import, ImportedFrom, Match, Names, New, Rule, Subshell, _PLACEHOLDERS,
    check_table,
)
# Rule tables import only the model, never this module (BACK-1360), so importing them here,
# at the top, cannot cycle. A new category module is added to _TABLE_MODULES, and only there.
from . import surface_rules_env, surface_rules_fs, surface_rules_imports, surface_rules_subprocess

_SEGMENT_SEPARATORS = ('::', '.', '/')


def _names(value: Names) -> Tuple[str, ...]:
    return (value,) if isinstance(value, str) else tuple(value)


def _name_matches(patterns: Tuple[str, ...], candidate: str) -> bool:
    """Empty `patterns` matches anything; entries may use `*` globs (`exec*`)."""
    return not patterns or any(fnmatchcase(candidate, p) for p in patterns)


def _segment_suffix(text: str, suffix: str) -> bool:
    """`std::process::Command` ends with `process::Command`; `myprocess::Command` does not."""
    if text == suffix:
        return True
    return any(text.endswith(sep + suffix) for sep in _SEGMENT_SEPARATORS)


# ── engine ──────────────────────────────────────────────────────────────────

def _alias_map(facts: Iterable[Fact]) -> Dict[str, str]:
    """local name -> fully qualified dotted path, from the file's Import facts."""
    aliases: Dict[str, str] = {}
    for f in facts:
        if not isinstance(f, ImportFact):
            continue
        if f.names:                       # `from a import b as c` -> c = a.b
            for n in f.names:
                aliases[f.alias or n] = f'{f.module}.{n}' if f.module else n
        else:                             # `import a.b` binds `a`; `import a.b as c` binds c
            root = f.module.split('.')[0]
            aliases[f.alias or root] = f.module if f.alias else root
    return aliases


def _resolve(call: CallFact, aliases: Dict[str, str]) -> Optional[str]:
    """Import-resolved dotted path of a call, None when its root was never imported."""
    root, _, rest = call.path.partition('.')
    if not root or root not in aliases or call.sep != '.':
        return None
    return aliases[root] + ('.' + rest if rest else '')


def _split_dotted(path: str) -> Tuple[str, str]:
    receiver, _, name = path.rpartition('.')
    return receiver, name


def _call_fields(rule_match: Call, call: CallFact,
                 aliases: Dict[str, str]) -> Optional[Dict[str, str]]:
    if rule_match.qualified is not None and call.qualified != rule_match.qualified:
        return None
    if rule_match.resolved:
        path = _resolve(call, aliases)
        if path is None:
            return None
        receiver, name = _split_dotted(path)
    else:
        path, receiver, name = call.path, call.receiver, call.name
    if rule_match.receiver is not None and receiver != rule_match.receiver:
        return None
    if rule_match.bare is False and not call.receiver and not call.chained:
        return None
    if rule_match.receiver == '' and call.chained:      # `a.b().exec()` is not a bare `exec()`
        return None
    if rule_match.receiver_endswith and not _segment_suffix(receiver, rule_match.receiver_endswith):
        return None
    if not _name_matches(_names(rule_match.name), name):
        return None
    key = next((a for a in call.args if a), None)     # first non-empty string literal
    if rule_match.string_arg and key is None:
        return None
    return {'path': path, 'receiver': receiver, 'name': name, 'key': key or ''}


def _module_matches(wanted: str, module: str) -> bool:
    if '*' in wanted:
        return fnmatchcase(module, wanted)
    return module == wanted or any(module.startswith(wanted + sep) for sep in _SEGMENT_SEPARATORS)


def _match_fields(m: Match, fact: Fact, aliases: Dict[str, str]) -> Optional[Dict[str, str]]:
    if isinstance(m, Call) and isinstance(fact, CallFact):
        return _call_fields(m, fact, aliases)
    if isinstance(m, New) and isinstance(fact, NewFact):
        return {'type': fact.type_name} if _name_matches(_names(m.type), fact.type_name) else None
    if isinstance(m, Subshell) and isinstance(fact, SubshellFact):
        return {}
    if isinstance(m, Import) and isinstance(fact, ImportFact):
        wanted = _names(m.module)
        if not wanted or any(_module_matches(w, fact.module) for w in wanted):
            return {'module': fact.module}
    return None


def _provenance_holds(rule: Rule, facts: List[Fact]) -> bool:
    if rule.requires is None:
        return True
    return any(isinstance(f, ImportFact) and _segment_suffix(f.module, rule.requires.module)
               for f in facts)


def _hits(rules: Iterable[Rule], facts: List[Fact]) -> List[Tuple[Rule, Fact, Dict[str, str]]]:
    """(rule, fact, match fields) per matching site; first rule in table order wins per fact."""
    aliases = _alias_map(facts)
    usable = [r for r in rules if _provenance_holds(r, facts)]
    out: List[Tuple[Rule, Fact, Dict[str, str]]] = []
    for fact in facts:
        for rule in usable:
            fields = _match_fields(rule.match, fact, aliases)
            if fields is not None:
                out.append((rule, fact, fields))
                break
    return out


def rule_matches(rules: Iterable[Rule], facts: List[Fact]) -> List[Tuple[Rule, Fact, str]]:
    """(rule, fact, entry name) per matching site; first rule in table order wins per fact."""
    return [(rule, fact, rule.entry_name.format(**fields))
            for rule, fact, fields in _hits(rules, facts)]


def scan_category(category: str, lang: str, facts: List[Fact],
                  file_path: str) -> List[Dict[str, Any]]:
    """Surface entries for one category of one file, in the scanners' entry shape."""
    entries: List[Dict[str, Any]] = []
    seen = set()
    for rule, fact, fields in _hits(rules_for(category, lang), facts):
        name = rule.entry_name.format(**fields)
        key = (name, fact.line)
        if key not in seen:
            seen.add(key)
            entry = {'type': rule.entry_type or category, 'name': name}
            if rule.entry_expr:
                entry['expr'] = rule.entry_expr.format(**fields)
            entry.update(file=file_path, line=fact.line)
            entries.append(entry)
    return entries


# ── registry ────────────────────────────────────────────────────────────────

# Category order here is the reporting order (`rule_categories`, `all_rules`).
_TABLE_MODULES = (
    surface_rules_subprocess,
    surface_rules_fs,
    surface_rules_env,
    surface_rules_imports,
)


def _collect_tables(modules) -> Dict[str, Tuple[Rule, ...]]:
    """Merge each module's `TABLES`; a category claimed twice is a bug, not an override."""
    tables: Dict[str, Tuple[Rule, ...]] = {}
    for module in modules:
        for category, rules in module.TABLES.items():
            if category in tables:
                raise ValueError(f'{category}: rule table defined twice (again in {module.__name__})')
            check_table(category, rules)
            tables[category] = rules
    return tables


ALL_TABLES: Dict[str, Tuple[Rule, ...]] = _collect_tables(_TABLE_MODULES)
_TABLES: Dict[str, Tuple[Rule, ...]] = dict(ALL_TABLES)   # live registry; tests swap entries


def _reset_caches() -> None:
    for cached in (_call_filter, _new_filter, _needles, rules_for, rule_categories):
        cached.cache_clear()


def register_table(category: str, rules: Tuple[Rule, ...]) -> None:
    """Install or replace a category's table in the live registry, validating it first."""
    check_table(category, rules)
    _TABLES[category] = rules
    _reset_caches()


@lru_cache(maxsize=None)
def rules_for(category: str, lang: str) -> Tuple[Rule, ...]:
    return tuple(r for r in _TABLES.get(category, ()) if r.lang == lang)


def all_rules() -> Tuple[Rule, ...]:
    return tuple(r for table in _TABLES.values() for r in table)


@lru_cache(maxsize=None)
def rule_categories(lang: str) -> Tuple[str, ...]:
    """Categories that have at least one rule for `lang` (the implemented cells)."""
    return tuple(c for c, table in _TABLES.items() if any(r.lang == lang for r in table))


def apply_rules(surfaces: Dict[str, List[Dict[str, Any]]], lang: str, facts: List[Fact],
                file_path: str) -> None:
    """Fill every rule-driven category of `surfaces` for `lang` from `facts`."""
    for category in rule_categories(lang):
        surfaces[category] = scan_category(category, lang, facts, file_path) if facts else []


@lru_cache(maxsize=None)
def _call_filter(lang: str) -> Optional[CallFilter]:
    """Cheap superset test for "could any Call rule of `lang` match this (receiver, name)?".

    Built from the tables so the fact extractor can skip most calls before doing the
    expensive part. Returns None (no filtering) when some rule can match any call name.
    """
    exact: set = set()
    globs: List[str] = []
    receivers_any_name: set = set()
    for r in (r for r in all_rules() if r.lang == lang and isinstance(r.match, Call)):
        m = r.match
        if m.resolved:
            return None                    # the source name is an alias of the rule's name
        if m.qualified is not None:
            patterns: Tuple[str, ...] = (m.qualified.replace('::', '.').rpartition('.')[2],)
        else:
            patterns = _names(m.name)
        if not patterns:
            if m.receiver:                 # nameless rule pinned to one receiver (Ruby `Open3`)
                receivers_any_name.add(m.receiver)
                continue
            return None
        for pat in patterns:
            if any(c in pat for c in '*?['):
                globs.append(pat)
            else:
                exact.add(pat)
    frozen, receivers = frozenset(exact), frozenset(receivers_any_name)

    def want(receiver: str, name: str) -> bool:
        return (name in frozen or receiver in receivers
                or any(fnmatchcase(name, g) for g in globs))
    return want


@lru_cache(maxsize=None)
def _new_filter(lang: str) -> Optional[NewFilter]:
    exact: set = set()
    for r in (r for r in all_rules() if r.lang == lang and isinstance(r.match, New)):
        patterns = _names(r.match.type)
        if not patterns or any(c in p for p in patterns for c in '*?['):
            return None
        exact.update(patterns)
    frozen = frozenset(exact)
    return lambda type_name: type_name in frozen


def _literal_prefix(pattern: str) -> str:
    for i, c in enumerate(pattern):
        if c in '*?[':
            return pattern[:i]
    return pattern


def _longest_word(text: str) -> str:
    words = re.findall(r'\w+', text)
    return max(reversed(words), key=len) if words else ''      # ties: the later word


def _rule_literals(m: Match) -> Optional[Tuple[str, ...]]:
    """Literals, at least one of which must occur in any file `m` can match (None: unknown).

    A Call rule can only match if its receiver text is in the file, and also only if one of
    its names is; pick whichever set is more selective (`Command::new`: the receiver
    `Command`, since `new` is in nearly every Rust file). Import-resolved names may be
    aliases in the source, but the imported name still appears in the import statement.
    """
    if isinstance(m, New):
        names = tuple(_literal_prefix(n) for n in _names(m.type))
        return names if names and all(names) else None
    if not isinstance(m, Call):
        return ()                          # Subshell / Import rules are not gated on text
    if m.qualified is not None:
        word = _longest_word(m.qualified)
        return (word,) if word else None
    names = tuple(_literal_prefix(n) for n in _names(m.name))
    receiver = _longest_word(m.receiver or m.receiver_endswith or '')
    if names and all(names):
        if receiver and len(receiver) > min(len(n) for n in names):
            return (receiver,)
        return names
    return (receiver,) if receiver else None


@lru_cache(maxsize=None)
def _needles(lang: str) -> Optional[Tuple[bytes, ...]]:
    """Literals of which at least one must occur in a file for a Call/New rule to match it.

    None when some rule cannot be tied to a literal (a pure glob or a nameless rule),
    meaning: do not gate on text.
    """
    needles: set = set()
    for r in (r for r in all_rules() if r.lang == lang):
        literals = _rule_literals(r.match)
        if literals is None:
            return None
        needles.update(lit.encode('utf-8') for lit in literals)
    return tuple(sorted(needles))


class RuleScan:
    """Feeds rule-driven categories from a scanner's own tree walk.

        rules = RuleScan('go', content_bytes)
        ... inside the existing walk:   if kind in rules.kinds: rules.visit(node, kind)
        rules.apply(surfaces, file_path)

    A language with no rule table pays one no-op call per node.
    """

    def __init__(self, lang: str, content: bytes) -> None:
        self._lang = lang
        self._collector = (FactCollector(lang, content, _call_filter(lang), _new_filter(lang),
                                         _needles(lang))
                           if rule_categories(lang) else None)
        # Bound straight to the collector: this runs once per node, so no extra call layer.
        self.visit = self._collector.visit if self._collector is not None else _ignore
        # Node kinds worth calling `visit` for. Test membership inline in the walk instead of
        # calling `visit` per node: nearly every node matches nothing.
        self.kinds: frozenset = (self._collector.kinds if self._collector is not None
                                 else frozenset())

    def apply(self, surfaces: Dict[str, List[Dict[str, Any]]], file_path: str) -> None:
        if self._collector is not None:
            apply_rules(surfaces, self._lang, self._collector.facts(), file_path)


def _ignore(node: Any, kind: str) -> None:
    return None


def apply_ast_rules(surfaces: Dict[str, List[Dict[str, Any]]], tree: ast.AST, file_path: str,
                    source: Optional[str] = None) -> None:
    """`apply_rules` for the Python scanner's `ast` tree.

    A given `source` gates the walk (see `_needles`); without it every call is considered.
    """
    if not rule_categories('python'):
        return
    needles = _needles('python')
    if source is not None and needles is not None \
            and not any(n.decode('utf-8') in source for n in needles):
        facts: List[Fact] = []          # no rule's module is even mentioned: nothing can match
    else:
        facts = python_facts_from_ast(tree)
    apply_rules(surfaces, 'python', facts, file_path)

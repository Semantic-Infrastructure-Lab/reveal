#!/usr/bin/env python3
"""Oracle-free graph invariants on every pinned corpus (BACK-1096).

No compiler, no recall oracle: each invariant compares two public views of one graph, so a
disagreement proves one of them wrong without knowing which. For the import languages no
recall oracle gates (kotlin, scala, csharp, swift, php, dart, lua, gdscript, zig, ruby) this
is the only regression signal. Every answer comes through the public request path
(``python -m reveal <uri> --format json``, one process per request, serial), with cwd = the
corpus root and the scan directory pinned as the project root (``&root=<scan>``). Counted
edges stay under that scan; the default view also retains resolved outside-scan facts.

  fan_in_total        imports ?rank=fan-in and ?importers (directory view): the sum of fan-in
                      equals the sum of fan-out, the edge count the answer's rule reports
                      (edge_rule.via) and the number of importer rows; every module's fan-in
                      is the same in both views and equals its importer list's length
  importers_resolved  the files whose resolved imports (the default view's ``resolved``) name
                      X under the declared scan root are importers of X (?importers); outside
                      facts remain counted separately and require the rule's disclosure.
                      Each file's out-degree read off the
                      importer lists equals its fan_out (?rank=fan-in, the forward adjacency).
                      Edges beyond a statement's first target (``resolved`` names one) are
                      counted, and sampled by importer_citations
  importer_citations  imports ?importers=X for sampled X (the targets with the most edges the
                      default view does not show, else evenly spaced): the same importer set
                      as the directory view, and every row cites a real import: a statement
                      of the default view at that line and module, or (a convention edge) a
                      line of the file naming the constant
  local_units_resolved  Rust: every statement of the default view that names an in-tree crate bare (``use
                      grep_matcher::Matcher``, not crate::/self::/super::) is ``resolved``: code that compiles
                      names a workspace crate its package lists as a dependency, or its own library, and that
                      crate has a root file. Which in-tree crates each package names is read from the corpus's
                      Cargo.toml files (crate names, dependency keys), not from Reveal (BACK-2549/2559).
                      Go: every statement whose import path lies in an in-tree module its module can name (its
                      own, a ``replace => ./dir`` target, a sibling of a go.work that uses it), longest module
                      path first, and names a package directory of the scan, resolves to exactly that
                      directory. Read from the corpus's go.mod and go.work files (BACK-2557/2558)
  package_wildcards   JVM corpora (java, kotlin, scala): every unresolved wildcard statement of the default
                      view whose prefix is a package some scanned file declares is counted in the answer's
                      ``edge_rule.package_wildcards`` (statements, importer files, per package), and the
                      disclosure counts nothing else (BACK-2506/2507). The declared packages are read from
                      the sources' ``package`` clauses, not from Reveal
  calls_inverse       calls ?rank=callers (every callee name with its callers) against
                      ?callees=FILE:NAME for sampled callers: every call a caller is indexed
                      under is in its callee list, and every callee-list call is indexed
                      under that caller (or hidden by the ranking's one-record-per-caller
                      de-duplication under the same key, counted, not a failure)
  callers_view        calls ?callers=X for sampled plain-identifier names: the same callers,
                      as (file, caller), as the ranking's entry for X
  call_targets        calls ?callees=FILE:NAME&depth=2 for sampled callers (one --stdin batch, so one import
                      analysis) against imports:// default view (unpinned: the project root calls resolves
                      from) and the outlines of the files involved, for every call spelled f or q.f:
                      a call whose q (or f) is bound only by imports from outside the tree (resolved to no
                      file, classified stdlib/unresolved) is not resolved to a project definition, unless a
                      bare f is defined in the caller's own file; a call whose q (or f) is bound only by
                      imports resolving to one file F of the scan that defines the name resolves to F; and
                      a call resolved to one definition lands on a line where its target file defines that
                      name. The binding rule is the language's own only: named entries, aliases, Python's
                      bare import; a guessed bare import (C include, Ruby require, JVM import) binds nothing.
                      The calls gate scores depth-1 call text, so this is the check on resolution TARGETS
                      (BACK-2569; BACK-2553's first commit passed the gate with four target defects)
  no_match            every declared target-naming parameter (ParamSpec.names) of imports and
                      calls, URI and CLI spelling, with a value that matches nothing: exit 2
                      and stderr names the value (BACK-2161)

A row's status: green (held over a population > 0), red (violations), empty (population 0:
no positive evidence either way), error (a request timed out or gave no JSON). Exit 3 from
reveal is a partial answer (a file parsed with errors, a capped walk): the invariant is still
evaluated, and the row is labelled partial with the reason.

  scripts/graph_invariants.py --output inv.json
  scripts/graph_invariants.py --corpus lua --corpus zig --only calls_inverse
  scripts/graph_invariants.py --cache-dir ~/.cache/reveal-inv-cache   # warm structure/graph cache

Default corpora: every import population scripts/recall_gate.py scores plus UNGATED (the same
set as scripts/imports_fold_snapshot.py). ``--cache-dir`` turns the disk cache on in that
directory (later requests of a corpus reuse its parsed files); the default is
REVEAL_DISK_CACHE=0. Wall times are measured on whatever else the machine runs (contended).
Exits 1 if any row is red or errored, else 0.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import subprocess
import sys
import time
import urllib.parse
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple

from imports_fold_snapshot import (UNGATED, _git_head, _representative_file, corpus_root, gated_corpora,
                                   parse_corpus_spec, request_env, reveal_location, run_request, scan_spelling,
                                   source_digest)

REPO_ROOT = Path(__file__).resolve().parent.parent
FORMAT_VERSION = 2
INVARIANTS = ('fan_in_total', 'importers_resolved', 'importer_citations', 'local_units_resolved', 'package_wildcards',
              'calls_inverse', 'callers_view', 'call_targets', 'no_match')
IMPORT_INVARIANTS = ('fan_in_total', 'importers_resolved', 'importer_citations', 'local_units_resolved',
                     'package_wildcards')
CALLS_INVARIANTS = ('calls_inverse', 'callers_view', 'call_targets')
DEFAULT_TIMEOUT = 1800
EXAMPLES = 5
NO_MATCH_VALUES = {'file': '__no_such_file_zz__.zzz', 'symbol': '__no_such_symbol_zz__'}
PLAIN_IDENTIFIER = re.compile(r'^[A-Za-z_][A-Za-z0-9_]*$')

Edge = Tuple[str, str]  # (importer, imported), both relative to the scan directory


# ── a row ─────────────────────────────────────────────────────────────────────

def make_row(invariant: str, population: int, violations: List[Any], **extra: Any) -> Dict[str, Any]:
    """One corpus x invariant verdict: red on any violation, empty with nothing to check."""
    status = 'red' if violations else ('green' if population > 0 else 'empty')
    row: Dict[str, Any] = {'invariant': invariant, 'status': status, 'population': population,
                           'violations': len(violations), 'examples': violations[:EXAMPLES]}
    row.update(extra)
    return row


def error_row(invariant: str, reason: str) -> Dict[str, Any]:
    return {'invariant': invariant, 'status': 'error', 'population': 0, 'violations': 0, 'examples': [],
            'reason': reason}


# ── imports: the three views ──────────────────────────────────────────────────

def importer_lists(importers: Dict[str, Any]) -> Dict[str, List[str]]:
    """module -> its importer rows, as the ?importers directory view lists them."""
    return {e['file']: list(e.get('importers') or []) for e in importers.get('entries', [])}


def rule_edge_count(answer: Dict[str, Any]) -> int:
    """The edges an answer's rule says it counted (edge_rule.via: edges by cascade stage)."""
    return sum((answer.get('edge_rule') or {}).get('via', {}).values())


def check_fan_in_total(fan_in: Dict[str, Any], importers: Dict[str, Any]) -> Dict[str, Any]:
    """Sum of fan-in == sum of fan-out == the rule's edge count == importer rows; per module the
    two views agree and fan_in is the importer list's length."""
    ranked = fan_in.get('entries', [])
    lists = importer_lists(importers)
    sums = {'rank_fan_in': sum(e['fan_in'] for e in ranked),
            'rank_fan_out': sum(e['fan_out'] for e in ranked),
            'rank_rule_edges': rule_edge_count(fan_in),
            'importers_rows': sum(len(v) for v in lists.values()),
            'importers_fan_in': sum(e.get('fan_in', 0) for e in importers.get('entries', [])),
            'importers_rule_edges': rule_edge_count(importers)}
    violations: List[Any] = []
    if len(set(sums.values())) != 1:
        violations.append({'sums_differ': sums})
    if fan_in.get('total') is not None and len(ranked) != fan_in['total']:
        violations.append({'rank_cut': [len(ranked), fan_in['total']]})
    rank_fan_in = {e['file']: e['fan_in'] for e in ranked}
    for entry in importers.get('entries', []):
        module, rows = entry['file'], lists[entry['file']]
        if entry.get('fan_in') != len(rows) or len(set(rows)) != len(rows):
            violations.append({'module': module, 'fan_in': entry.get('fan_in'), 'importer_rows': len(rows),
                               'distinct': len(set(rows))})
        if rank_fan_in.get(module) != len(rows):
            violations.append({'module': module, 'rank_fan_in': rank_fan_in.get(module), 'importer_rows': len(rows)})
    for module, count in rank_fan_in.items():
        if count and module not in lists:
            violations.append({'module': module, 'rank_fan_in': count, 'importer_rows': 0})
    return make_row('fan_in_total', sums['rank_rule_edges'], violations, sums=sums)


def resolved_edges(default_view: Dict[str, Any]) -> Tuple[Set[Edge], int]:
    """(importer, first target) of every statement the default view shows resolved, and how many
    statements that is. ``resolved`` names one target, including outside-scan facts."""
    edges: Set[Edge] = set()
    statements = 0
    for file, stmts in (default_view.get('files') or {}).items():
        for stmt in stmts:
            target = stmt.get('resolved')
            if target and target != file:
                statements += 1
                edges.add((file, target))
    return edges, statements


def importer_edges(importers: Dict[str, Any]) -> Set[Edge]:
    return {(importer, module) for module, rows in importer_lists(importers).items() for importer in rows}


def _under_scan_root(target: str, scan_dir: Path) -> bool:
    """Containment of displayed graph paths: normalize lexically, never follow target symlinks."""
    return Path(os.path.abspath(scan_dir / target)).is_relative_to(scan_dir)


def _counted_scope(forward: Set[Edge], reverse: Set[Edge], answers: Dict[str, Dict[str, Any]],
                   scan_dir: Path) -> Tuple[Set[Edge], List[Any]]:
    """Qualify the runner's pinned scope independently of the reverse answer (BACK-2340).

    First-target facts only bound the outside count from below: convention/multi-target
    edges may not appear in them. All views must nevertheless disclose the same count.
    """
    scan_dir = scan_dir.resolve()
    counted = {edge for edge in forward if _under_scan_root(edge[1], scan_dir)}
    outside = len(forward - counted)
    violations: List[Any] = []
    disclosures = {}
    for name, answer in answers.items():
        rule = answer.get('edge_rule') or {}
        root = rule.get('root')
        source = rule.get('root_source')
        scope = rule.get('scope_param')
        valid_source = (source, scope) in {('root_param', 'root'), ('path', 'path')}
        if (not isinstance(root, str) or Path(os.path.abspath(scan_dir / root)) != scan_dir or
                not valid_source or rule.get('tests_param') != 'include' or
                (name != 'default' and rule.get('lazy') != 'include')):
            violations.append({'counted_scope': name, 'root': root, 'root_source': source,
                               'scope_param': scope, 'tests_param': rule.get('tests_param'),
                               'lazy': rule.get('lazy')})
        count = rule.get('outside_root_edges')
        if type(count) is not int or count < outside:
            violations.append({'outside_root_disclosure': name, 'reported': count,
                               'observed_first_target_edges': outside})
        else:
            disclosures[name] = count
    if len(set(disclosures.values())) > 1:
        violations.append({'outside_root_disclosure': disclosures})
    for edge in sorted(reverse):
        if not _under_scan_root(edge[1], scan_dir):
            violations.append({'outside_root_importer_edge': list(edge)})
    return counted, violations


def check_importers_resolved(importers: Dict[str, Any], default_view: Dict[str, Any],
                             fan_in: Dict[str, Any], *, scan_dir: Optional[Path] = None) -> Dict[str, Any]:
    """Every counted first-target edge is an importer row, and reverse out-degree equals fan_out.

    With the runner's explicit pinned scan directory, independently qualify target containment
    and validate the declared rule. Legacy three-argument callers still compare every fact.
    """
    forward, statements = resolved_edges(default_view)
    reverse = importer_edges(importers)
    counted, violations = (forward, []) if scan_dir is None else _counted_scope(
        forward, reverse, {'importers': importers, 'default': default_view, 'fan_in': fan_in}, scan_dir)
    violations.extend({'resolved_not_an_importer': list(edge)} for edge in sorted(counted - reverse))
    out_degree = Counter(importer for importer, _ in reverse)
    fan_out = {e['file']: e['fan_out'] for e in fan_in.get('entries', [])}
    for file in sorted(set(fan_out) | set(out_degree)):
        if out_degree.get(file, 0) != fan_out.get(file, 0):
            violations.append({'file': file, 'importer_list_out_degree': out_degree.get(file, 0),
                               'rank_fan_out': fan_out.get(file)})
    beyond = reverse - counted
    return make_row('importers_resolved', len(reverse), violations, resolved_statements=statements,
                    resolved_edges=len(forward), counted_resolved_edges=len(counted),
                    outside_root_resolved_edges=len(forward - counted), edges_beyond_first_target=len(beyond),
                    beyond_examples=[list(edge) for edge in sorted(beyond)[:EXAMPLES]])


def citation_targets(importers: Dict[str, Any], default_view: Dict[str, Any], count: int) -> List[str]:
    """The ``count`` modules with the most importer edges the default view does not show (ties by
    name), topped up with evenly spaced modules so the sample is never empty when edges exist."""
    forward, _ = resolved_edges(default_view)
    lists = importer_lists(importers)
    unseen = Counter(module for importer, module in importer_edges(importers) if (importer, module) not in forward)
    chosen = [module for module, _ in sorted(unseen.items(), key=lambda item: (-item[1], item[0]))][:count]
    rest = sorted(module for module, rows in lists.items() if rows and module not in chosen)
    step = max(1, len(rest) // max(1, count - len(chosen))) if rest else 1
    return chosen + rest[::step][:count - len(chosen)]


def _statement_at(default_view: Dict[str, Any], file: str, line: Any, module: Any) -> bool:
    return any(s.get('line') == line and s.get('module') == module
               for s in (default_view.get('files') or {}).get(file, []))


def _line_names(scan_dir: Path, file: str, line: Any, module: Any) -> bool:
    """Whether line ``line`` of ``file`` contains the module's last name segment."""
    if not isinstance(line, int) or not module:
        return False
    try:
        text = (scan_dir / file).read_text(encoding='utf-8', errors='replace')
    except OSError:
        return False
    lines = text.split('\n')
    last = re.split(r'::|\.|/|\\', str(module))[-1]
    return 0 < line <= len(lines) and bool(last) and last in lines[line - 1]


def check_importer_citations(importers: Dict[str, Any], default_view: Dict[str, Any],
                             per_target: Dict[str, Dict[str, Any]], scan_dir: Path) -> Dict[str, Any]:
    """Per sampled target: the per-file answer lists the directory view's importers, and each row
    cites a statement of the default view (line and module), or for a convention edge a line of
    the file that names the constant."""
    lists = importer_lists(importers)
    violations: List[Any] = []
    rows_checked = 0
    convention_rows = 0
    for target, answer in sorted(per_target.items()):
        rows = answer.get('importers') or []
        if sorted({r['file'] for r in rows}) != sorted(lists.get(target, [])):
            violations.append({'target': target, 'per_file': len({r['file'] for r in rows}),
                               'directory_view': len(lists.get(target, []))})
        for r in rows:
            rows_checked += 1
            if _statement_at(default_view, r['file'], r.get('line'), r.get('module')):
                continue
            if set(r.get('via') or ()) == {'convention'}:
                convention_rows += 1
                if _line_names(scan_dir, r['file'], r.get('line'), r.get('module')):
                    continue
            violations.append({'target': target, 'uncited_row': {k: r.get(k) for k in ('file', 'line', 'module', 'via')}})
    return make_row('importer_citations', rows_checked, violations, targets=sorted(per_target),
                    convention_rows=convention_rows)


# ── calls ─────────────────────────────────────────────────────────────────────

Caller = Tuple[str, str]  # (file as the collection spells it, definition name)


def ranked_calls(rank: Dict[str, Any]) -> Dict[Caller, Set[Tuple[str, str]]]:
    """(file, caller) -> {(callee key, call_expr)}: the ranking read as each caller's out-edges."""
    out: Dict[Caller, Set[Tuple[str, str]]] = {}
    for entry in rank.get('entries', []):
        for rec in entry.get('callers') or []:
            out.setdefault((rec['file'], rec['caller']), set()).add((entry['name'], rec.get('call_expr')))
    return out


def sample_callers(rank: Dict[str, Any], count: int) -> List[Caller]:
    """``count`` named callers, evenly spaced over the sorted (file, caller) pairs."""
    callers = sorted(c for c in ranked_calls(rank) if c[1])
    if count <= 0 or not callers:
        return []
    return callers[::max(1, len(callers) // count)][:count]


def sample_names(rank: Dict[str, Any], count: int) -> List[str]:
    """``count`` plain-identifier callee names with a caller: half the most-called (ties by name),
    the rest evenly spaced over the other names, sorted. Only plain names: a qualified name's
    callers also include its bare name's, so it does not compare 1:1 with its ranking entry."""
    entries = [e for e in rank.get('entries', []) if e.get('callers') and PLAIN_IDENTIFIER.match(e['name'])]
    if count <= 0 or not entries:
        return []
    top = [e['name'] for e in sorted(entries, key=lambda e: (-e['caller_count'], e['name']))[:(count + 1) // 2]]
    rest = sorted(e['name'] for e in entries if e['name'] not in top)
    spread = rest[::max(1, len(rest) // max(1, count - len(top)))][:count - len(top)] if rest else []
    return top + spread


def callee_calls(answer: Dict[str, Any], caller: Caller) -> Optional[Set[str]]:
    """Every call the definitions named ``caller[1]`` in ``caller[0]`` make, or None when the
    answer has no such definition."""
    matches = [m for m in answer.get('matches') or [] if m.get('file') == caller[0] and m.get('function') == caller[1]]
    if not matches:
        return None
    return {call for m in matches for call in m.get('calls') or []}


def check_calls_inverse(rank: Dict[str, Any], callees: Dict[Caller, Dict[str, Any]]) -> Dict[str, Any]:
    """Per sampled caller Y: every call Y is indexed under is in callees(Y), and every call in
    callees(Y) is indexed under Y, unless the ranking's per-(file, caller) de-duplication kept
    another call of Y under that same key (counted as shadowed)."""
    indexed = ranked_calls(rank)
    violations: List[Any] = []
    pairs = 0
    shadowed = 0
    for caller, answer in sorted(callees.items()):
        forward = callee_calls(answer, caller)
        if forward is None:
            violations.append({'caller': list(caller), 'callees_found_no_definition': True})
            continue
        reverse = indexed.get(caller, set())
        keys = {key for key, _ in reverse}
        exprs = {expr for _, expr in reverse}
        for key, expr in sorted(reverse):
            pairs += 1
            if expr not in forward:
                violations.append({'caller': list(caller), 'indexed_not_in_callees': [key, expr]})
        for call in sorted(forward):
            pairs += 1
            if call in exprs:
                continue
            if call in keys:
                shadowed += 1
                continue
            violations.append({'caller': list(caller), 'callee_not_indexed': call})
    return make_row('calls_inverse', pairs, violations, callers_sampled=len(callees), dedup_shadowed=shadowed,
                    callers_total=len(indexed), edges_total=sum(len(v) for v in indexed.values()))


def check_callers_view(rank: Dict[str, Any], callers: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    """callers=X lists the same (file, caller) pairs as the ranking's entry for X."""
    entries = {e['name']: e for e in rank.get('entries', [])}
    violations: List[Any] = []
    population = 0
    for name, answer in sorted(callers.items()):
        got = {(r['file'], r['caller']) for level in answer.get('levels') or [] if level.get('level') == 1
               for r in level.get('callers') or []}
        want = {(r['file'], r['caller']) for r in (entries.get(name) or {}).get('callers') or []}
        population += len(want)
        if got != want:
            violations.append({'name': name, 'only_callers_view': sorted(got - want)[:EXAMPLES],
                               'only_rank': sorted(want - got)[:EXAMPLES]})
    return make_row('callers_view', population, violations, names=sorted(callers))


# ── call_targets: where a resolved call lands (BACK-2569) ─────────────────────

EXTERNAL_CLASSIFICATIONS = ('stdlib', 'unresolved')
SIMPLE_CALL = re.compile(r'^[A-Za-z_$][\w$]*(\.[A-Za-z_$][\w$]*)?$')


class NameBinding:
    """What a file's imports bind one local name to, read off imports:// default view."""

    def __init__(self) -> None:
        self.external = True
        self.targets: Set[Optional[str]] = set()
        self.imported: Set[Optional[str]] = set()  # the name the import reads in its module, None if unknown

    def add(self, stmt: Dict[str, Any], imported: Optional[str]) -> None:
        target = stmt.get('resolved')
        self.external = self.external and not target and stmt.get('classification') in EXTERNAL_CLASSIFICATIONS
        self.targets.add(target)
        self.imported.add(imported)


def statement_bindings(stmt: Dict[str, Any]) -> List[Tuple[str, Optional[str]]]:
    """(local name, name in the imported module) for each name `stmt` binds by the language's own rule:
    each entry of a named import ('X as Y' binds Y to X), the alias of a namespace or aliased import, and
    a Python bare ``import a.b`` (binds ``a``). A default import binds its local name to an export whose
    name is unknown. Any other bare import (C ``#include``, Ruby ``require``, a JVM ``import a.b.C``) binds
    a guessed name, so it binds nothing here."""
    names = [n for n in stmt.get('names') or [] if n != '*']
    if names:
        if stmt.get('type') == 'default_import':
            return [(name.strip(), None) for name in names]
        return [(entry.split(' as ')[-1].strip(), entry.split(' as ')[0].strip()) for entry in names]
    if stmt.get('alias'):
        return [(stmt['alias'], None)]
    if stmt.get('type') == 'import' and str(stmt.get('file', '')).endswith('.py'):
        return [(str(stmt.get('module') or '').split('.')[0], None)]
    return []


def view_bindings(default_view: Dict[str, Any]) -> Dict[str, Dict[str, NameBinding]]:
    """file (as the view spells it) -> local name -> binding. A name is external only when every statement
    binding it is unresolved and classified outside the tree."""
    out: Dict[str, Dict[str, NameBinding]] = {}
    for file, stmts in (default_view.get('files') or {}).items():
        names = out.setdefault(file, {})
        for stmt in stmts:
            for local, imported in statement_bindings(stmt):
                if local:
                    names.setdefault(local, NameBinding()).add(stmt, imported)
    return out


DEFINITION_LISTS = ('functions', 'methods', 'tests')  # the structure lists calls collects definitions from


def outline_names(answer: Dict[str, Any]) -> Dict[str, Set[int]]:
    """name -> the lines it is defined at, over the definition lists of a file's structure answer
    (a class is not a call target: calls never resolves ``Foo()`` to a class)."""
    names: Dict[str, Set[int]] = {}
    for key in DEFINITION_LISTS:
        items = (answer.get('structure') or {}).get(key)
        for item in items if isinstance(items, list) else []:
            if isinstance(item, dict) and item.get('name') and isinstance(item.get('line'), int):
                names.setdefault(str(item['name']).split('.')[-1], set()).add(item['line'])
    return names


def walk_edges(walks: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Every distinct call edge of the callee walks, one per (caller file, caller line, call)."""
    seen: Dict[Tuple[Any, Any, Any], Dict[str, Any]] = {}
    for walk in walks:
        for level in walk.get('levels') or []:
            for edge in level.get('callees') or []:
                seen.setdefault((edge.get('caller_file'), edge.get('caller_line'), edge.get('call_expr')), edge)
    return [seen[key] for key in sorted(seen, key=lambda k: tuple(str(p) for p in k))]


def check_call_targets(walks: Iterable[Dict[str, Any]], default_view: Dict[str, Any],
                       outlines: Dict[str, Dict[str, Set[int]]], scan: str) -> Dict[str, Any]:
    """Each call edge of the walks against the caller file's imports (imports:// default view, the scope
    calls resolves in) and the outlines of the files involved, for calls spelled ``f`` or ``q.f``:

      external_binding  q (or f) is bound only by imports from outside the tree: the call is not resolved
                        to a project definition, unless a bare f is defined in the caller's own file
      bound_file        q (or f) is bound only by imports that resolve to one file F under the scan, and F
                        defines the name: the call resolves to F (a bare f the caller's file defines may
                        resolve there instead)
      target_defines    a call resolved to one definition: the target file defines that name at that line

    ``outlines`` are keyed by the path as the walk spells it (scan-prefixed)."""
    bindings = view_bindings(default_view)
    prefix = scan.rstrip('/') + '/'
    counts = Counter()
    violations: List[Any] = []
    for edge in walk_edges(walks):
        call, caller = edge.get('call_expr') or '', edge.get('caller_file') or ''
        if not SIMPLE_CALL.match(call) or not caller.startswith(prefix):
            continue
        qualified = '.' in call
        head, tail = call.split('.')[0], call.split('.')[-1]
        resolved = bool(edge.get('resolved'))
        target = edge.get('callee_file') if resolved and not edge.get('ambiguous') else None
        shadowed = not qualified and tail in outlines.get(caller, {})
        record = {'caller': f"{caller}:{edge.get('caller_line')}", 'call': call,
                  'got': (f"{target}:{edge.get('callee_line')}" if target else
                          'ambiguous' if resolved else 'unresolved')}
        if target:
            counts['target_defines'] += 1
            if edge.get('callee_line') not in outlines.get(target, {}).get(str(edge.get('callee') or tail), set()):
                violations.append({'rule': 'target_defines', **record})
        binding = bindings.get(caller[len(prefix):], {}).get(head)
        if binding is None or shadowed:
            continue
        if binding.external:
            counts['external_binding'] += 1
            if resolved:
                violations.append({'rule': 'external_binding', **record})
            continue
        if len(binding.targets) != 1 or None in binding.targets:
            continue
        bound = prefix + next(iter(binding.targets))  # type: ignore[operator]
        name = tail if qualified or binding.imported == {None} else next(iter(binding.imported), None) or tail
        if bound.startswith(prefix + '../') or len(binding.imported) > 1 or name not in outlines.get(bound, {}):
            continue
        counts['bound_file'] += 1
        if target != bound:
            violations.append({'rule': 'bound_file', 'bound_to': bound, **record})
    population = sum(counts.values())
    return make_row('call_targets', population, violations, edges_checked=dict(sorted(counts.items())),
                    by_rule=dict(sorted(Counter(v['rule'] for v in violations).items())))


# ── no-match control ──────────────────────────────────────────────────────────

def no_match_requests(scan: str, specs: Iterable[Dict[str, Any]]) -> List[Tuple[str, str, str, List[str]]]:
    """(noun:param, spelling, value, argv) for every declared target-naming parameter."""
    out = []
    for spec in specs:
        value = NO_MATCH_VALUES[spec['names']]
        label = f"{spec['noun']}:{spec['name']}"
        spelled = _quoted(value) if spec.get('uri_codec') == 'percent' else value
        out.append((label, 'uri', value, [f"{spec['noun']}://{scan}?{spec['name']}={spelled}", '--format', 'json']))
        for flag in spec.get('flags') or ():
            out.append((label, 'cli', value, [spec['noun'], scan, flag, value, '--format', 'json']))
    return out


def check_no_match(results: List[Tuple[str, str, str, Dict[str, Any]]]) -> Dict[str, Any]:
    """Each request exited 2 and its stderr names the value it could not match."""
    violations = []
    for label, spelling, value, row in results:
        stderr = row.get('stderr') or ''
        if row.get('exit_code') != 2 or value not in stderr or 'unrecognized arguments' in stderr:
            violations.append({'param': label, 'spelling': spelling, 'exit_code': row.get('exit_code'),
                               'stderr_head': stderr[:200]})
    return make_row('no_match', len(results), violations, params=sorted({r[0] for r in results}))


# ── requests ──────────────────────────────────────────────────────────────────

def _quoted(text: str) -> str:
    """A calls name for a parameter that percent-decodes its value (uri_codec 'percent')."""
    return urllib.parse.quote(text, safe='/')


def _raw(text: str) -> Optional[str]:
    """A value for a parameter read raw (uri_codec 'raw': imports ?importers= and ?root=): as
    spelled, or None when it holds a character that would end the value (``&``, ``#``)."""
    return None if set(text) & {'&', '#'} else text


def partial_reason(answer: Optional[Dict[str, Any]]) -> Optional[str]:
    """Why an exit-3 answer is partial, from what it discloses."""
    if not isinstance(answer, dict):
        return None
    meta = answer.get('metadata') or {}
    reasons = []
    if meta.get('files_failed_count'):
        reasons.append(f"{meta['files_failed_count']} file(s) parsed with errors")
    if meta.get('files_lost_count'):
        reasons.append(f"{meta['files_lost_count']} file(s) lost")
    if (meta.get('scan_budget') or {}).get('capped'):
        reasons.append('walk capped')
    errors = (answer.get('meta') or {}).get('errors') or []
    if errors:
        reasons.append(f'{len(errors)} error(s) in meta.errors')
    return '; '.join(reasons) or None


# ── package wildcards: the disclosure against the per-file listing ────────────

JVM_SUFFIXES = frozenset({'.java', '.kt', '.kts', '.scala', '.sc'})
_PACKAGE_CLAUSE = re.compile(r'^[ \t]*package[ \t]+(object[ \t]+)?([\w.`]+)', re.MULTILINE)
_WILDCARD_LAST = frozenset({'*', '_'})


def declared_packages(text: str) -> Set[str]:
    """Packages one JVM source file declares: each ``package`` clause, chained clauses cumulatively
    (Scala ``package a`` then ``package b`` declares ``a`` and ``a.b``), and a ``package object X`` inside
    package ``P`` declares ``P.X``. ``text`` has its comments and literals blanked by the caller."""
    found: Set[str] = set()
    current = ''
    for is_object, name in _PACKAGE_CLAUSE.findall(text):
        name = name.replace('`', '')
        current = f'{current}.{name}' if current else name
        found.add(current)
        if is_object:
            current = current.rpartition('.')[0]
    return found


def scan_declared_packages(scan_dir: Path) -> Set[str]:
    """Every package the JVM sources under ``scan_dir`` declare (literals and comments blanked)."""
    from recall_oracles import jvm_strip_noise  # beside this script; only the literal blanker is shared
    packages: Set[str] = set()
    for path in sorted(scan_dir.rglob('*')):
        if path.suffix in JVM_SUFFIXES and path.is_file():
            try:
                text = path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            packages |= declared_packages(jvm_strip_noise(text))
    return packages


def has_jvm_wildcards(default_view: Dict[str, Any]) -> bool:
    """Whether the default view lists a wildcard statement (``a.b.*``, ``a.b._``) in a JVM file at all."""
    return any(Path(file).suffix in JVM_SUFFIXES and str(row.get('module') or '').rpartition('.')[2] in _WILDCARD_LAST
               for file, rows in (default_view.get('files') or {}).items() for row in rows)


def wildcard_statements(default_view: Dict[str, Any], packages: Set[str]) -> Dict[str, Dict[str, int]]:
    """package -> {file: statements} for the default view's unresolved wildcard rows (``a.b.*``, ``a.b._``)
    in a JVM file whose prefix is one of ``packages``."""
    found: Dict[str, Dict[str, int]] = {}
    for file, rows in (default_view.get('files') or {}).items():
        if Path(file).suffix not in JVM_SUFFIXES:
            continue
        for row in rows:
            head, _, last = str(row.get('module') or '').rpartition('.')
            if last in _WILDCARD_LAST and head in packages and row.get('resolved') is None:
                per_file = found.setdefault(head, {})
                per_file[file] = per_file.get(file, 0) + 1
    return found


def check_package_wildcards(default_view: Dict[str, Any], packages: Set[str]) -> Dict[str, Any]:
    """The answer's disclosure equals the wildcard statements its own per-file listing shows for a declared
    package: total statements, importer files, and the importer files of each package."""
    expected = wildcard_statements(default_view, packages)
    rule = (default_view.get('edge_rule') or {}).get('package_wildcards') or {}
    disclosed = rule.get('packages') or {}
    want = {pkg: len(files) for pkg, files in expected.items()}
    statements = sum(sum(files.values()) for files in expected.values())
    importers = len({file for files in expected.values() for file in files})
    violations: List[Any] = []
    if statements != (rule.get('statements') or 0):
        violations.append({'statements': {'listing': statements, 'disclosed': rule.get('statements') or 0}})
    if importers != (rule.get('importers') or 0):
        violations.append({'importer_files': {'listing': importers, 'disclosed': rule.get('importers') or 0}})
    for pkg in sorted(set(want) | set(disclosed)):
        if want.get(pkg, 0) != disclosed.get(pkg, 0):
            violations.append({'package': pkg, 'listing': want.get(pkg, 0), 'disclosed': disclosed.get(pkg, 0)})
    return make_row('package_wildcards', statements, violations, packages=len(want), importer_files=importers)


# The languages whose bare import names the manifest makes exact (BACK-2559): Rust's Cargo.toml, Go's go.mod.
MANIFEST_EXACT_SUFFIXES = ('.rs', '.go')


def _cargo_doc(manifest: Path) -> Dict[str, Any]:
    import tomllib
    try:
        with open(manifest, 'rb') as f:
            return tomllib.load(f)
    except (OSError, ValueError):
        return {}


def _crate_name(doc: Dict[str, Any]) -> Optional[str]:
    for table in (doc.get('lib'), doc.get('package')):
        if isinstance(table, dict) and isinstance(table.get('name'), str):
            return table['name'].replace('-', '_')
    return None


def scan_crate_scopes(scan_dir: Path) -> Dict[Path, Set[str]]:
    """Per Cargo package directory under ``scan_dir``: the in-tree crate names its code may name bare, its own
    library and every in-tree crate its manifest lists in a dependency table (keys as code spells them)."""
    docs = {m.parent.resolve(): _cargo_doc(m) for m in sorted(scan_dir.rglob('Cargo.toml'))
            if 'target' not in m.relative_to(scan_dir).parts}
    in_tree = {name for doc in docs.values() if (name := _crate_name(doc))}
    scopes: Dict[Path, Set[str]] = {}
    for directory, doc in docs.items():
        if not isinstance(doc.get('package'), dict):
            continue
        tables = [doc.get(t) for t in ('dependencies', 'dev-dependencies', 'build-dependencies')]
        tables += [platform.get(t) for platform in (doc.get('target') or {}).values() if isinstance(platform, dict)
                   for t in ('dependencies', 'dev-dependencies', 'build-dependencies')]
        # a key is the name code spells; the crate it names is `package = ...` when renamed
        keys = {key.replace('-', '_') for table in tables if isinstance(table, dict) for key, spec in table.items()
                if str(spec.get('package', key) if isinstance(spec, dict) else key).replace('-', '_') in in_tree}
        own = _crate_name(doc)
        scopes[directory] = keys | ({own} if own else set())
    return scopes


# Go: directories a module walk skips (the go tool ignores them for packages; vendored copies are not in-tree units).
_GO_SKIPPED = ('vendor', 'testdata')


def _go_directives(text: str) -> List[Tuple[str, List[str]]]:
    """(verb, arguments) per go.mod/go.work directive, block entries under their verb; comments dropped."""
    found: List[Tuple[str, List[str]]] = []
    block: Optional[str] = None
    for raw in text.split('\n'):
        words = [w.strip('"`') for w in raw.split('//', 1)[0].split()]
        if not words:
            continue
        if block is not None:
            if words == [')']:
                block = None
            else:
                found.append((block, words))
        elif words[1:] == ['(']:
            block = words[0]
        else:
            found.append((words[0], words[1:]))
    return found


def _go_local_replaces(directives: List[Tuple[str, List[str]]], base: Path) -> List[Tuple[str, Path]]:
    pairs = []
    for verb, words in directives:
        if verb == 'replace' and '=>' in words and words.index('=>') > 0 and len(words) > words.index('=>') + 1:
            target = words[words.index('=>') + 1]
            if target.startswith(('./', '../')) or Path(target).is_absolute():
                pairs.append((words[0], (base / target).resolve()))
    return pairs


def _go_text(manifest: Path) -> str:
    try:
        return manifest.read_text(encoding='utf-8')
    except (OSError, ValueError):
        return ''


def scan_go_module_scopes(scan_dir: Path) -> Dict[Path, Dict[str, Path]]:
    """Per Go module directory under ``scan_dir``: each in-tree module path its code may import, with the module
    directory it names. Its own module; each ``replace`` whose target is a module directory of the scan; and,
    when a go.work under ``scan_dir`` or the nearest one above it ``use``s the module, every other module it uses."""
    root = scan_dir.resolve()
    manifests = [m for m in sorted(root.rglob('go.mod'))
                 if not set(m.relative_to(root).parts[:-1]) & set(_GO_SKIPPED)]
    modules: Dict[Path, Tuple[str, List[Tuple[str, Path]]]] = {}
    for manifest in manifests:
        directives = _go_directives(_go_text(manifest))
        name = next((words[0] for verb, words in directives if verb == 'module' and words), None)
        if name:
            modules[manifest.parent] = (name, _go_local_replaces(directives, manifest.parent))
    works = sorted(root.rglob('go.work')) + [d / 'go.work' for d in root.parents if (d / 'go.work').is_file()][:1]
    used_by: Dict[Path, List[Tuple[Set[Path], List[Tuple[str, Path]]]]] = {}
    for work in works:
        directives = _go_directives(_go_text(work))
        used = {(work.parent / words[0]).resolve() for verb, words in directives if verb == 'use' and words}
        for directory in used:
            used_by.setdefault(directory, []).append((used, _go_local_replaces(directives, work.parent)))
    scopes: Dict[Path, Dict[str, Path]] = {}
    for directory, (name, replaces) in modules.items():
        names: Dict[str, Path] = {name: directory}
        for used, work_replaces in used_by.get(directory, []):
            for other in sorted(used):
                if other in modules:
                    names.setdefault(modules[other][0], other)
            for path, target in work_replaces:
                names.setdefault(path, target)
        for path, target in replaces:
            names.setdefault(path, target)
        scopes[directory] = {path: target for path, target in names.items() if target in modules}
    return scopes


def _go_local_target(package: str, names: Dict[str, Path]) -> Optional[Path]:
    """The package directory ``package`` names in the longest in-tree module path containing it, if any."""
    holding = [path for path in names if package == path or package.startswith(path + '/')]
    if not holding:
        return None
    path = max(holding, key=len)
    return names[path] / package[len(path):].lstrip('/')


def check_local_units_resolved(default_view: Dict[str, Any], scopes: Dict[Path, Set[str]],
                               scan_dir: Path, go_scopes: Optional[Dict[Path, Dict[str, Path]]] = None) -> Dict[str, Any]:
    """Every bare Rust statement whose first segment is an in-tree crate its package names (its own library or
    a listed dependency) names its target in ``resolved``; every Go statement whose path names a package
    directory of an in-tree module its module can import resolves to that directory."""
    population = 0
    violations: List[Any] = []
    go_scopes = go_scopes or {}
    root = scan_dir.resolve()
    for file, stmts in sorted((default_view.get('files') or {}).items()):
        if not file.endswith(MANIFEST_EXACT_SUFFIXES):
            continue
        path = (scan_dir / file).resolve()
        if file.endswith('.go'):
            go_names = next((go_scopes[d] for d in path.parents if d in go_scopes), {})
            for stmt in stmts:
                module = str(stmt.get('module') or '')
                target = _go_local_target(module, go_names)
                if target is None or not target.is_relative_to(root) or not any(target.glob('*.go')):
                    continue
                population += 1
                resolved = stmt.get('resolved')
                if not resolved or (scan_dir / resolved).resolve() != target.resolve():
                    violations.append({'file': file, 'line': stmt.get('line'), 'module': module,
                                       'resolved': resolved, 'expected': target.relative_to(root).as_posix()})
            continue
        names = next((scopes[d] for d in path.parents if d in scopes), set())
        for stmt in stmts:
            module = str(stmt.get('module') or '')
            if stmt.get('is_relative') or module.lstrip(':').split('::')[0] not in names:
                continue
            population += 1
            if not stmt.get('resolved'):
                violations.append({'file': file, 'line': stmt.get('line'), 'module': module})
    return make_row('local_units_resolved', population, violations, packages=len(scopes) + len(go_scopes))


def json_stream(text: str) -> List[Dict[str, Any]]:
    """The JSON objects of a ``--stdin --format json`` batch, which prints one document per line read."""
    decoder, pos, answers = json.JSONDecoder(), 0, []
    while True:
        while pos < len(text) and text[pos].isspace():
            pos += 1
        if pos >= len(text):
            return answers
        try:
            obj, pos = decoder.raw_decode(text, pos)
        except json.JSONDecodeError:
            return answers
        if isinstance(obj, dict):
            answers.append(obj)


class Requests:
    """Serial public requests for one corpus; keeps a short record of each."""

    def __init__(self, env: Dict[str, str], cwd: Path, timeout: float) -> None:
        self.env, self.cwd, self.timeout = env, cwd, timeout
        self.log: List[Dict[str, Any]] = []

    def get(self, argv: List[str]) -> Dict[str, Any]:
        row = run_request(argv, self.env, self.cwd, self.timeout)
        answer = row.get('json')
        self.log.append({'argv': argv, 'status': row['status'], 'exit_code': row.get('exit_code'),
                         'wall_s_contended': row.get('wall_s_contended'), 'stdout_bytes': row.get('stdout_bytes'),
                         'partial': partial_reason(answer) if row.get('exit_code') == 3 else None,
                         'stderr_head': (row.get('stderr') or '')[:300]})
        return row

    def batch(self, lines: List[str]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
        """Every JSON answer of one ``--stdin`` batch (one process, so one import analysis for all its
        walks), in order; (answers, why not) when the process gave none or timed out."""
        started = time.monotonic()
        argv = ['--stdin', '--format', 'json']
        proc = subprocess.Popen([sys.executable, '-m', 'reveal', *argv], env=self.env, cwd=str(self.cwd),
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        try:
            out, err = proc.communicate(('\n'.join(lines) + '\n').encode('utf-8'), timeout=self.timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate()
            self.log.append({'argv': argv, 'lines': len(lines), 'status': 'timeout'})
            return [], f'--stdin batch of {len(lines)}: timeout'
        answers = json_stream(out.decode('utf-8', 'replace'))
        stderr = err.decode('utf-8', 'replace')
        self.log.append({'argv': argv, 'lines': len(lines), 'status': 'ok', 'exit_code': proc.returncode,
                         'answers': len(answers), 'wall_s_contended': round(time.monotonic() - started, 2),
                         'stderr_head': stderr[:300]})
        return answers, None if answers else f'--stdin batch of {len(lines)}: exit {proc.returncode}: {stderr[:200]}'

    def answer(self, argv: List[str]) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        """The JSON answer, or (None, why not). Exit 0 and 3 answer; anything else does not."""
        row = self.get(argv)
        if row['status'] != 'ok' or row.get('exit_code') not in (0, 3) or not isinstance(row.get('json'), dict):
            return None, f"{argv[0]}: status {row['status']}, exit {row.get('exit_code')}: {(row.get('stderr') or '')[:200]}"
        return row['json'], None


def _partial_label(log: List[Dict[str, Any]]) -> Optional[str]:
    """What made any of these requests' answers partial (exit 3), or None."""
    reasons = sorted({entry['partial'] or 'exit 3' for entry in log if entry.get('exit_code') == 3})
    return '; '.join(reasons) or None


def run_imports(req: Requests, scan: str, scan_dir: Path, only: Tuple[str, ...], citations: int) -> List[Dict[str, Any]]:
    pinned = f'root={scan}'
    wanted = [inv for inv in IMPORT_INVARIANTS if inv in only]
    if not wanted:
        return []
    start = len(req.log)
    importers, err1 = req.answer([f'imports://{scan}?importers&{pinned}', '--format', 'json'])
    fan_in, err2 = req.answer([f'imports://{scan}?rank=fan-in&{pinned}', '--format', 'json'])
    default_view: Optional[Dict[str, Any]] = None
    err3 = None
    if {'importers_resolved', 'importer_citations', 'local_units_resolved', 'package_wildcards'} & set(wanted):
        default_view, err3 = req.answer([f'imports://{scan}?{pinned}', '--format', 'json'])
    rows: List[Dict[str, Any]] = []
    if 'fan_in_total' in wanted:
        rows.append(error_row('fan_in_total', err1 or err2 or '') if err1 or err2 or importers is None or fan_in is None
                    else check_fan_in_total(fan_in, importers))
    if 'importers_resolved' in wanted:
        bad = err1 or err2 or err3
        rows.append(error_row('importers_resolved', bad) if bad or importers is None or fan_in is None or default_view is None
                    else check_importers_resolved(importers, default_view, fan_in, scan_dir=scan_dir))
    if 'importer_citations' in wanted:
        if err1 or err3 or importers is None or default_view is None:
            rows.append(error_row('importer_citations', err1 or err3 or ''))
        else:
            rows.append(run_citations(req, scan, scan_dir, importers, default_view, citations))
    if 'local_units_resolved' in wanted:
        rows.append(error_row('local_units_resolved', err3 or '') if err3 or default_view is None
                    else check_local_units_resolved(default_view, scan_crate_scopes(scan_dir), scan_dir,
                                                    scan_go_module_scopes(scan_dir)))
    if 'package_wildcards' in wanted:
        rows.append(error_row('package_wildcards', err3 or '') if err3 or default_view is None
                    else check_package_wildcards(default_view, scan_declared_packages(scan_dir)
                                                     if has_jvm_wildcards(default_view) else set()))
    label = _partial_label(req.log[start:])
    for row in rows:
        row['partial'] = label
    return rows


def per_file_spelling(scan_dir: Path, module: str, importers: List[str]) -> str:
    """How to ask ?importers= for ``module``: itself, or for a package-directory module (Go answers
    per package) one file of it, which the graph maps to the package; ?importers=<dir> is the
    summary of every module under that directory, not the module's importers. The file is the first
    of the package's main suffix that is not itself an importer (a Go external test imports its own
    package, and ?importers=FILE leaves the named file out)."""
    path = scan_dir / module
    if not path.is_dir():
        return module
    rep = _representative_file(path)
    if rep is None:
        return module
    taken = set(importers)
    for candidate in sorted(path.iterdir()):
        spelled = candidate.relative_to(scan_dir).as_posix()
        if candidate.is_file() and not candidate.name.startswith('.') and candidate.suffix == rep.suffix \
                and spelled not in taken:
            return spelled
    return rep.relative_to(scan_dir).as_posix()


def run_citations(req: Requests, scan: str, scan_dir: Path, importers: Dict[str, Any],
                  default_view: Dict[str, Any], citations: int) -> Dict[str, Any]:
    pinned = f'root={scan}'
    per_target: Dict[str, Dict[str, Any]] = {}
    failed = []
    for target in citation_targets(importers, default_view, citations):
        spelled = _raw(per_file_spelling(scan_dir, target, importer_lists(importers).get(target, [])))
        if spelled is None:
            failed.append(f'{target}: a raw ?importers= value cannot spell it')
            continue
        answer, err = req.answer([f'imports://{scan}?importers={spelled}&{pinned}', '--format', 'json'])
        if answer is None:
            failed.append(err or '')
        else:
            per_target[target] = answer
    row = check_importer_citations(importers, default_view, per_target, scan_dir)
    return error_row('importer_citations', '; '.join(failed)) if failed else row


def run_call_targets(req: Requests, scan: str, callers: List[Caller]) -> Dict[str, Any]:
    """Depth-2 callee walks of the sampled callers and imports:// default view (unpinned: the project
    root calls resolves from) in one batch, then the outline of every file an edge involves."""
    if not callers:
        return make_row('call_targets', 0, [])
    walk_lines = [f'calls://{scan}?callees={_quoted(f + ":" + c)}&depth=2&builtins=true' for f, c in callers]
    answers, why = req.batch([f'imports://{scan}', *walk_lines])
    default_view = next((a for a in answers if a.get('type') == 'imports'), None)
    walks = [a for a in answers if a.get('type') == 'calls_callees' and a.get('levels')]
    if why or default_view is None:
        return error_row('call_targets', why or 'no imports:// answer in the batch')
    bindings = view_bindings(default_view)
    prefix = scan.rstrip('/') + '/'
    files: Set[str] = set()
    for edge in walk_edges(walks):
        caller = edge.get('caller_file') or ''
        files.add(caller)
        if edge.get('callee_file'):
            files.add(edge['callee_file'])
        binding = bindings.get(caller[len(prefix):], {}).get(str(edge.get('call_expr') or '').split('.')[0])
        files.update(prefix + t for t in (binding.targets if binding else ()) if t and not t.startswith('../'))
    outlines: Dict[str, Dict[str, Set[int]]] = {}
    if files:
        structures, why = req.batch(sorted(files))
        if why:
            return error_row('call_targets', why)
        outlines = {str(a['file']): outline_names(a) for a in structures if a.get('file')}
    return check_call_targets(walks, default_view, outlines, scan) | {
        'walks': len(walks), 'walks_requested': len(walk_lines), 'outlines': len(outlines)}


def run_calls(req: Requests, scan: str, only: Tuple[str, ...], n_callers: int, n_names: int,
              per_name: int, n_targets: int = 0) -> List[Dict[str, Any]]:
    wanted = [inv for inv in CALLS_INVARIANTS if inv in only]
    if not wanted:
        return []
    start = len(req.log)
    rank, err = req.answer([f'calls://{scan}?rank=callers&top=0&builtins=true&test-framework=true', '--format', 'json'])
    if rank is None:
        return [error_row(inv, err or '') for inv in wanted]
    names = sample_names(rank, n_names)
    callers_answers: Dict[str, Dict[str, Any]] = {}
    failed: List[str] = []
    if 'callers_view' in wanted or 'calls_inverse' in wanted:
        for name in names:
            answer, why = req.answer([f'calls://{scan}?callers={_quoted(name)}', '--format', 'json'])
            if answer is None:
                failed.append(why or '')
            else:
                callers_answers[name] = answer
    rows: List[Dict[str, Any]] = []
    if 'calls_inverse' in wanted:
        sampled = list(sample_callers(rank, n_callers))
        for answer in callers_answers.values():  # anchor on callers(X) too: its first callers
            for rec in sorted(((r['file'], r['caller']) for level in answer.get('levels') or []
                               for r in level.get('callers') or [] if r.get('caller')))[:per_name]:
                if rec not in sampled:
                    sampled.append(rec)
        callees: Dict[Caller, Dict[str, Any]] = {}
        inverse_failed: List[str] = []
        for caller in sampled:
            answer, why = req.answer([f'calls://{scan}?callees={_quoted(caller[0] + ":" + caller[1])}&builtins=true',
                                      '--format', 'json'])
            if answer is None:
                inverse_failed.append(why or '')
            else:
                callees[caller] = answer
        row = check_calls_inverse(rank, callees)
        rows.append(error_row('calls_inverse', '; '.join(inverse_failed)) if inverse_failed else row)
    if 'callers_view' in wanted:
        row = check_callers_view(rank, callers_answers)
        rows.append(error_row('callers_view', '; '.join(failed)) if failed else row)
    if 'call_targets' in wanted:
        rows.append(run_call_targets(req, scan, sample_callers(rank, n_targets)))
    label = _partial_label(req.log[start:])
    for row in rows:
        row['partial'] = label
    return rows


def declared_target_specs(env: Dict[str, str], cwd: Path) -> List[Dict[str, Any]]:
    """Every imports/calls ParamSpec that names a target, read from the checkout under test."""
    probe = ('import json\n'
             'from reveal.cli.routing.declared import declared_adapter_class\n'
             'out = []\n'
             'for noun in ("imports", "calls"):\n'
             '    for s in getattr(declared_adapter_class(noun), "PARAM_SPECS", ()):\n'
             '        if s.names:\n'
             '            out.append({"noun": noun, "name": s.name, "names": s.names, "uri_codec": s.uri_codec,\n'
             '                        "flags": list(s.cli.flags) if s.cli else []})\n'
             'print(json.dumps(out))\n')
    out = subprocess.run([sys.executable, '-c', probe], env=env, cwd=str(cwd), capture_output=True,
                         timeout=120, check=True)
    return json.loads(out.stdout.decode('utf-8'))


def run_no_match(req: Requests, scan: str, specs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    results = [(label, spelling, value, req.get(argv)) for label, spelling, value, argv in no_match_requests(scan, specs)]
    return [check_no_match(results)]


def run_corpus(name: str, scan_root: str, root: Path, env: Dict[str, str], args: argparse.Namespace,
               specs: List[Dict[str, Any]]) -> Dict[str, Any]:
    scan = scan_spelling(name, scan_root)
    scan_dir = root / scan
    if not scan_dir.is_dir():
        return {'status': 'missing', 'scan': scan, 'rows': []}
    req = Requests(env, root, args.timeout)
    only = tuple(args.only or INVARIANTS)
    started = time.monotonic()
    rows: List[Dict[str, Any]] = []
    rows += run_imports(req, scan, scan_dir, only, args.citations)
    rows += run_calls(req, scan, only, args.callers, args.names, args.per_name, args.target_callers)
    if 'no_match' in only:
        rows += run_no_match(req, scan, specs)
    return {'status': 'ok', 'scan': scan, 'corpus_head': _git_head(root / name), 'rows': rows,
            'requests': req.log, 'wall_s_contended': round(time.monotonic() - started, 1)}


# ── report ────────────────────────────────────────────────────────────────────

def table(report: Dict[str, Any]) -> List[str]:
    lines = [f"{'corpus':<18} {'invariant':<19} {'status':<6} {'population':>10} {'violations':>10}  partial"]
    for name, rec in report['corpora'].items():
        if rec['status'] != 'ok':
            lines.append(f"{name:<18} {'-':<19} {rec['status']}")
            continue
        for row in rec['rows']:
            lines.append(f"{name:<18} {row['invariant']:<19} {row['status']:<6} {row['population']:>10} "
                         f"{row['violations']:>10}  {row.get('partial') or ''}")
    return lines


def failing(report: Dict[str, Any]) -> bool:
    return any(row['status'] in ('red', 'error') for rec in report['corpora'].values() for row in rec['rows'])


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def run(args: argparse.Namespace) -> int:
    root = Path(args.corpus_root).expanduser().resolve() if args.corpus_root else corpus_root().resolve()
    src = Path(args.src).expanduser().resolve()
    env = request_env(src, disk_cache=bool(args.cache_dir))
    if args.cache_dir:
        env['REVEAL_CACHE_DIR'] = str(Path(args.cache_dir).expanduser().resolve())
    loaded = reveal_location(env, root)
    if os.path.normcase(str(Path(loaded).resolve())) != os.path.normcase(str(src)):
        _log(f'refusing: python -m reveal loads reveal from {loaded}, not --src {src}')
        return 2
    specs = declared_target_specs(env, root) if 'no_match' in (args.only or INVARIANTS) else []
    corpora = [parse_corpus_spec(s) for s in args.corpus] if args.corpus else (
        gated_corpora() + [(name, '.') for name in UNGATED])
    report: Dict[str, Any] = {
        'format_version': FORMAT_VERSION, 'tool': 'scripts/graph_invariants.py',
        'src': src.as_posix(), 'src_head': _git_head(src), 'src_tree_sha256': source_digest(src),
        'corpus_root': root.as_posix(), 'python': sys.version, 'platform': platform.platform(),
        'disk_cache': bool(args.cache_dir), 'invariants': list(args.only or INVARIANTS),
        'samples': {'citations': args.citations, 'callers': args.callers, 'names': args.names,
                    'per_name': args.per_name, 'target_callers': args.target_callers},
        'target_specs': specs, 'started_at': datetime.now(timezone.utc).isoformat(),
        'loadavg_start': os.getloadavg() if hasattr(os, 'getloadavg') else None,
        'wall_times': 'contended: measured on a shared machine, not a benchmark', 'corpora': {}}
    for name, scan_root in corpora:
        _log(f'{name} ({scan_spelling(name, scan_root)})')
        report['corpora'][name] = run_corpus(name, scan_root, root, env, args, specs)
        for line in table({'corpora': {name: report['corpora'][name]}})[1:]:
            _log(line)
        if args.output:
            _write(Path(args.output), report)  # after every corpus: a killed run keeps what it finished
    report['finished_at'] = datetime.now(timezone.utc).isoformat()
    if args.output:
        _write(Path(args.output), report)
    print('\n'.join(table(report)))
    return 1 if failing(report) else 0


def _write(path: Path, report: Dict[str, Any]) -> None:
    path.write_text(json.dumps(report, indent=1, sort_keys=False) + '\n', encoding='utf-8')


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', help='JSON report path (rewritten after every corpus)')
    parser.add_argument('--corpus', action='append', metavar='ID[=SCAN_ROOT]',
                        help='corpus under the corpus root (repeatable; default: gated + UNGATED)')
    parser.add_argument('--corpus-root', help='default: $REVEAL_CORPUS_DIR or ~/.cache/reveal-corpus')
    parser.add_argument('--only', action='append', choices=INVARIANTS, help='run only this invariant (repeatable)')
    parser.add_argument('--src', default=str(REPO_ROOT), help='checkout whose reveal answers (default: this one)')
    parser.add_argument('--cache-dir', help='turn the disk cache on, in this directory (default: off)')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT, help='seconds per request')
    parser.add_argument('--citations', type=int, default=3, help='per-file importer targets per corpus')
    parser.add_argument('--callers', type=int, default=6, help='evenly spaced callers whose callees are checked')
    parser.add_argument('--names', type=int, default=4, help='plain-identifier names whose callers are checked')
    parser.add_argument('--per-name', type=int, default=2, help='callers of each sampled name also checked inverse')
    parser.add_argument('--target-callers', type=int, default=40,
                        help='evenly spaced callers whose depth-2 walks call_targets checks (one batch)')
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())

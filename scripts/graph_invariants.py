#!/usr/bin/env python3
"""Oracle-free graph invariants on every pinned corpus (BACK-1096).

No compiler, no recall oracle: each invariant compares two public views of one graph, so a
disagreement proves one of them wrong without knowing which. For the import languages no
recall oracle gates (kotlin, scala, csharp, swift, php, dart, lua, gdscript, zig, ruby) this
is the only regression signal. Every answer comes through the public request path
(``python -m reveal <uri> --format json``, one process per request, serial), with cwd = the
corpus root and the scan directory pinned as the project root (``&root=<scan>``), so every
importer and every target of an answer is a file under the scan.

  fan_in_total        imports ?rank=fan-in and ?importers (directory view): the sum of fan-in
                      equals the sum of fan-out, the edge count the answer's rule reports
                      (edge_rule.via) and the number of importer rows; every module's fan-in
                      is the same in both views and equals its importer list's length
  importers_resolved  the files whose resolved imports (the default view's ``resolved``) name
                      X are importers of X (?importers); each file's out-degree read off the
                      importer lists equals its fan_out (?rank=fan-in, the forward adjacency).
                      Edges beyond a statement's first target (``resolved`` names one) are
                      counted, and sampled by importer_citations
  importer_citations  imports ?importers=X for sampled X (the targets with the most edges the
                      default view does not show, else evenly spaced): the same importer set
                      as the directory view, and every row cites a real import: a statement
                      of the default view at that line and module, or (a convention edge) a
                      line of the file naming the constant
  calls_inverse       calls ?rank=callers (every callee name with its callers) against
                      ?callees=FILE:NAME for sampled callers: every call a caller is indexed
                      under is in its callee list, and every callee-list call is indexed
                      under that caller (or hidden by the ranking's one-record-per-caller
                      de-duplication under the same key, counted, not a failure)
  callers_view        calls ?callers=X for sampled plain-identifier names: the same callers,
                      as (file, caller), as the ranking's entry for X
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
FORMAT_VERSION = 1
INVARIANTS = ('fan_in_total', 'importers_resolved', 'importer_citations', 'calls_inverse', 'callers_view',
              'no_match')
IMPORT_INVARIANTS = ('fan_in_total', 'importers_resolved', 'importer_citations')
CALLS_INVARIANTS = ('calls_inverse', 'callers_view')
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
    statements that is. ``resolved`` names a statement's first in-tree target only."""
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


def check_importers_resolved(importers: Dict[str, Any], default_view: Dict[str, Any],
                             fan_in: Dict[str, Any]) -> Dict[str, Any]:
    """Every resolved statement's edge is an importer row; per file, the importer lists' out-degree
    equals the forward fan_out. Edges no statement's first target shows are counted."""
    forward, statements = resolved_edges(default_view)
    reverse = importer_edges(importers)
    violations: List[Any] = [{'resolved_not_an_importer': list(edge)} for edge in sorted(forward - reverse)]
    out_degree = Counter(importer for importer, _ in reverse)
    fan_out = {e['file']: e['fan_out'] for e in fan_in.get('entries', [])}
    for file in sorted(set(fan_out) | set(out_degree)):
        if out_degree.get(file, 0) != fan_out.get(file, 0):
            violations.append({'file': file, 'importer_list_out_degree': out_degree.get(file, 0),
                               'rank_fan_out': fan_out.get(file)})
    beyond = reverse - forward
    return make_row('importers_resolved', len(reverse), violations, resolved_statements=statements,
                    resolved_edges=len(forward), edges_beyond_first_target=len(beyond),
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
    if {'importers_resolved', 'importer_citations'} & set(wanted):
        default_view, err3 = req.answer([f'imports://{scan}?{pinned}', '--format', 'json'])
    rows: List[Dict[str, Any]] = []
    if 'fan_in_total' in wanted:
        rows.append(error_row('fan_in_total', err1 or err2 or '') if err1 or err2 or importers is None or fan_in is None
                    else check_fan_in_total(fan_in, importers))
    if 'importers_resolved' in wanted:
        bad = err1 or err2 or err3
        rows.append(error_row('importers_resolved', bad) if bad or importers is None or fan_in is None or default_view is None
                    else check_importers_resolved(importers, default_view, fan_in))
    if 'importer_citations' in wanted:
        if err1 or err3 or importers is None or default_view is None:
            rows.append(error_row('importer_citations', err1 or err3 or ''))
        else:
            rows.append(run_citations(req, scan, scan_dir, importers, default_view, citations))
    label = _partial_label(req.log[start:])
    for row in rows:
        row['partial'] = label
    return rows


def per_file_spelling(scan_dir: Path, module: str) -> str:
    """How to ask ?importers= for ``module``: itself, or for a package-directory module (Go answers
    per package) one file of it, which the graph maps to the package; ?importers=<dir> is the
    summary of every module under that directory, not the module's importers."""
    path = scan_dir / module
    rep = _representative_file(path) if path.is_dir() else None
    return rep.relative_to(scan_dir).as_posix() if rep else module


def run_citations(req: Requests, scan: str, scan_dir: Path, importers: Dict[str, Any],
                  default_view: Dict[str, Any], citations: int) -> Dict[str, Any]:
    pinned = f'root={scan}'
    per_target: Dict[str, Dict[str, Any]] = {}
    failed = []
    for target in citation_targets(importers, default_view, citations):
        spelled = _raw(per_file_spelling(scan_dir, target))
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


def run_calls(req: Requests, scan: str, only: Tuple[str, ...], n_callers: int, n_names: int,
              per_name: int) -> List[Dict[str, Any]]:
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
    rows += run_calls(req, scan, only, args.callers, args.names, args.per_name)
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
                    'per_name': args.per_name},
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
    return run(parser.parse_args(argv))


if __name__ == '__main__':
    sys.exit(main())

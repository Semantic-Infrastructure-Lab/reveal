#!/usr/bin/env python3
"""Pre-merge snapshot of the import-graph answers BACK-1054 folds into imports:// (slice S0).

Folding depends://, deps:// and calls://?modules into imports:// must not move an answer
nobody reviewed. This tool records, per pinned corpus, every answer the fold can touch, each
through the public request path (one ``python -m reveal <uri> --format json`` process per
request, run serially), so the same tool run at a later commit can be compared row by row:

  depends_dir      depends://<scan>?root=<scan>: every module with its sorted dependents, plus
                   metadata (scan_capped, total_files_scanned, total_import_edges) and edge_rule
  depends_file     depends://<target>?root=<scan> for N deterministic targets (sorted modules of
                   the directory answer, every k-th; a package directory stands for its first file)
  imports_fan_in   imports://<scan>?rank=fan-in&lazy=include|exclude|only
  deps             deps://<scan> (base.files dropped: it is the imports default view)
  calls_modules    calls://<scan>?modules (the module edge list)
  check            reveal check <scan> --select I001,I002 (counts per rule, and the detections)

Every row keeps the exit code (3, a partial answer, is a normal verdict), a sha256 of stdout,
stderr, the parsed JSON, the item count its answer is about, and a wall time measured on
whatever else the machine was doing (labelled contended). A row whose count is 0 is listed
under ``zero_rows``: a zero is only an answer next to a positive control.

  scripts/imports_fold_snapshot.py --output base.json
  scripts/imports_fold_snapshot.py --output tip.json --src ~/export-of-tip --targets-from base.json
  scripts/imports_fold_snapshot.py --compare base.json tip.json

Corpora are the trees under $REVEAL_CORPUS_DIR (default ~/.cache/reveal-corpus,
scripts/fetch_corpus.py): every import population scripts/recall_gate.py scores (scan root from
tests/corpus/manifest.yaml) plus the ungated languages in UNGATED. ``--corpus ID[=SCAN_ROOT]``
picks others. A corpus that does not exist is recorded as missing, never skipped silently.
Requests run with cwd = the corpus root, so every path in an answer is relative to it, with
PYTHONHASHSEED=0, REVEAL_NO_CONFIG=1 and REVEAL_DISK_CACHE=0 (``--disk-cache`` leaves the
switch alone). ``--src`` names the checkout whose reveal answers (default: this one); the tool
refuses to run when ``python -m reveal`` would load reveal from anywhere else.

``--compare A B`` prints every row that changed (exit code, stdout digest, any JSON value, a
row present in one snapshot only) and exits 1 if anything changed or could not be compared,
0 when every row is identical.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import signal
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / 'tests' / 'corpus' / 'manifest.yaml'
FORMAT_VERSION = 1

KINDS = ('depends_dir', 'depends_file', 'imports_fan_in', 'deps', 'calls_modules', 'check')
LAZY_MODES = ('include', 'exclude', 'only')
CHECK_RULES = ('I001', 'I002')
# Languages with import support but no recall oracle yet: the engines differ most here.
UNGATED = ('kotlin', 'scala', 'scala-cats-effect', 'csharp', 'swift', 'php', 'dart', 'lua',
           'gdscript', 'zig', 'ruby')
DEFAULT_TARGETS = 20
DEFAULT_TIMEOUT = 3600


def corpus_root() -> Path:
    return Path(os.environ.get('REVEAL_CORPUS_DIR', Path.home() / '.cache' / 'reveal-corpus'))


def gated_corpora(manifest_path: Path = MANIFEST) -> List[Tuple[str, str]]:
    """(id, scan root) of every import population the recall gate scores."""
    import yaml
    manifest = yaml.safe_load(manifest_path.read_text(encoding='utf-8'))
    return [(entry.get('id', entry['language']), entry['recall'].get('scan_root', '.'))
            for entry in manifest['corpora'] if 'recall' in entry]


def parse_corpus_spec(spec: str) -> Tuple[str, str]:
    name, _, scan_root = spec.partition('=')
    return name, scan_root or '.'


def scan_spelling(corpus: str, scan_root: str) -> str:
    """The scan directory as typed, relative to the corpus root (the requests' cwd)."""
    return corpus if scan_root in ('', '.') else f'{corpus}/{scan_root.strip("/")}'


# ── requests ──────────────────────────────────────────────────────────────────

def request_env(src: Path, disk_cache: bool) -> Dict[str, str]:
    env = dict(os.environ)
    env['PYTHONPATH'] = str(src) + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    env['PYTHONHASHSEED'] = '0'
    env['PYTHONIOENCODING'] = 'utf-8'
    env['REVEAL_NO_CONFIG'] = '1'
    env.pop('PYTHONPYCACHEPREFIX', None)  # a mirrored pycache can serve another checkout's bytecode
    if not disk_cache:
        env['REVEAL_DISK_CACHE'] = '0'
    return env


def reveal_location(env: Dict[str, str], cwd: Path) -> str:
    """The directory ``python -m reveal`` imports reveal from under this env and cwd."""
    probe = 'import os, reveal; print(os.path.dirname(os.path.dirname(os.path.abspath(reveal.__file__))))'
    out = subprocess.run([sys.executable, '-c', probe], env=env, cwd=str(cwd), capture_output=True,
                         timeout=120, check=True)
    return out.stdout.decode('utf-8').strip()


def _kill(proc: subprocess.Popen) -> None:
    if hasattr(os, 'killpg'):
        os.killpg(proc.pid, signal.SIGKILL)  # pool workers too
    else:
        proc.kill()


def run_request(argv: List[str], env: Dict[str, str], cwd: Path, timeout: float) -> Dict[str, Any]:
    """One public request; the row records what came back, whatever came back."""
    started = time.monotonic()
    proc = subprocess.Popen([sys.executable, '-m', 'reveal', *argv], env=env, cwd=str(cwd),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            start_new_session=hasattr(os, 'killpg'))
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill(proc)
        proc.communicate()
        return {'argv': argv, 'status': 'timeout', 'exit_code': None,
                'wall_s_contended': round(time.monotonic() - started, 2)}
    row: Dict[str, Any] = {'argv': argv, 'exit_code': proc.returncode,
                           'wall_s_contended': round(time.monotonic() - started, 2),
                           'stdout_sha256': hashlib.sha256(out).hexdigest(), 'stdout_bytes': len(out),
                           'stderr': err.decode('utf-8', 'replace')}
    try:
        row['json'] = json.loads(out.decode('utf-8'))
        row['status'] = 'ok'
    except (UnicodeDecodeError, json.JSONDecodeError):
        row['status'] = 'no_json'
        row['stdout_head'] = out[:400].decode('utf-8', 'replace')
    return row


# ── what each answer counts ───────────────────────────────────────────────────

def _depends_dir_count(data: Dict[str, Any]) -> int:
    return sum(m.get('dependent_count', 0) for m in data.get('modules', []))


def _deps_count(data: Dict[str, Any]) -> int:
    return len((data.get('base') or {}).get('files') or [])


def _check_counts(data: Dict[str, Any]) -> Dict[str, int]:
    counts = {rule: 0 for rule in CHECK_RULES}
    for entry in data.get('files', []):
        for detection in entry.get('detections', []):
            code = detection.get('rule_code')
            counts[code] = counts.get(code, 0) + 1
    return counts


def summarize_row(kind: str, row: Dict[str, Any]) -> None:
    """Fill ``count`` (the number the answer is about) and any shape the answer cut."""
    data = row.get('json')
    if not isinstance(data, dict):
        row['count'] = None
        return
    if kind == 'depends_dir':
        row['count'] = _depends_dir_count(data)
        row['modules'] = len(data.get('modules', []))
        row['cut'] = len(data.get('modules', [])) != data.get('total_modules')
    elif kind == 'depends_file':
        row['count'] = data.get('count')
        row['cut'] = len(data.get('dependents', [])) != data.get('count')
    elif kind == 'imports_fan_in':
        entries = data.get('entries', [])
        row['count'] = sum(e.get('fan_in', 0) for e in entries)
        row['cut'] = data.get('total') is not None and len(entries) != data.get('total')
    elif kind == 'deps':
        row['count'] = _deps_count(data)
        if isinstance(data.get('base'), dict):
            data['base'].pop('files', None)  # the imports default view, recorded by imports_fan_in
    elif kind == 'calls_modules':
        row['count'] = len(data.get('edges', []))
        row['cut'] = data.get('total_edges') is not None and row['count'] != data.get('total_edges')
    elif kind == 'check':
        row['counts'] = _check_counts(data)
        row['count'] = sum(row['counts'].values())
        row['cut'] = bool((data.get('summary') or {}).get('items_truncated'))


# ── per-file targets ──────────────────────────────────────────────────────────

def _representative_file(directory: Path) -> Optional[Path]:
    """A package directory's first file of its most common suffix (Go answers per package)."""
    files = sorted(p for p in directory.iterdir() if p.is_file() and not p.name.startswith('.'))
    if not files:
        return None
    suffixes: Dict[str, int] = {}
    for p in files:
        suffixes[p.suffix] = suffixes.get(p.suffix, 0) + 1
    best = sorted(suffixes.items(), key=lambda item: (-item[1], item[0]))[0][0]
    return next(p for p in files if p.suffix == best)


def pick_targets(dir_answer: Dict[str, Any], scan_dir: Path, count: int, seed: int) -> List[str]:
    """``count`` modules of the directory answer: sorted by name, every k-th from ``seed % k``.

    Paths are relative to the scan directory, as the directory answer spells them.
    """
    modules = sorted({m['module'] for m in dir_answer.get('modules', [])})
    if count <= 0 or not modules:
        return []
    step = max(1, len(modules) // count)
    chosen = modules[seed % step::step][:count]
    targets = []
    for module in chosen:
        path = scan_dir / module
        if path.is_dir():
            rep = _representative_file(path)
            if rep is None:
                continue
            module = rep.relative_to(scan_dir).as_posix()
        targets.append(module)
    return sorted(dict.fromkeys(targets))


# ── one corpus ────────────────────────────────────────────────────────────────

def _quoted(path: str) -> str:
    return urllib.parse.quote(path, safe='/:')


def corpus_requests(scan: str, targets: List[str], kinds: Tuple[str, ...]) -> Iterator[Tuple[str, str, List[str]]]:
    """(kind, row key, argv) of every request after the directory answer, in run order."""
    if 'depends_file' in kinds:
        for target in targets:
            yield 'depends_file', target, [f'depends://{scan}/{target}?root={_quoted(scan)}', '--format', 'json']
    if 'imports_fan_in' in kinds:
        for mode in LAZY_MODES:
            yield 'imports_fan_in', f'lazy={mode}', [f'imports://{scan}?rank=fan-in&lazy={mode}', '--format', 'json']
    if 'deps' in kinds:
        yield 'deps', '', [f'deps://{scan}', '--format', 'json']
    if 'calls_modules' in kinds:
        yield 'calls_modules', '', [f'calls://{scan}?modules', '--format', 'json']
    if 'check' in kinds:
        yield 'check', '', ['check', scan, '--select', ','.join(CHECK_RULES), '--format', 'json']


def _git_head(path: Path) -> Optional[str]:
    try:
        out = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return None
    return out.stdout.decode('ascii', 'replace').strip() if out.returncode == 0 else None


def source_digest(src: Path) -> str:
    """sha256 over every reveal/ source file of ``src``: which code answered, git or not."""
    hasher = hashlib.sha256()
    for path in sorted((src / 'reveal').rglob('*.py')):
        hasher.update(path.relative_to(src).as_posix().encode('utf-8') + b'\0')
        hasher.update(path.read_bytes() + b'\0')
    return hasher.hexdigest()


def _log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def snapshot_corpus(name: str, scan_root: str, root: Path, env: Dict[str, str], *, kinds: Tuple[str, ...],
                    target_count: int, seed: int, fixed_targets: Optional[List[str]],
                    timeout: float) -> Dict[str, Any]:
    scan = scan_spelling(name, scan_root)
    scan_dir = root / scan
    if not scan_dir.is_dir():
        return {'status': 'missing', 'scan': scan}
    record: Dict[str, Any] = {'status': 'ok', 'scan': scan, 'corpus_head': _git_head(root / name), 'rows': {}}
    rows = record['rows']

    def run(kind: str, key: str, argv: List[str]) -> Dict[str, Any]:
        row = run_request(argv, env, root, timeout)
        summarize_row(kind, row)
        rows[f'{kind}:{key}' if key else kind] = row
        _log(f'  {name} {kind} {key} exit={row["exit_code"]} count={row.get("count")} '
             f'{row["wall_s_contended"]}s (contended)')
        return row

    dir_row = None
    if 'depends_dir' in kinds or (fixed_targets is None and 'depends_file' in kinds):
        dir_row = run('depends_dir', '', [f'depends://{scan}?root={_quoted(scan)}', '--format', 'json'])
    if fixed_targets is not None:
        targets = list(fixed_targets)
        record['targets_source'] = 'fixed'
    else:
        answer = dir_row.get('json') if dir_row else None
        targets = pick_targets(answer, scan_dir, target_count, seed) if isinstance(answer, dict) else []
        record['targets_source'] = f'every k-th sorted module, seed {seed}'
    record['targets'] = targets
    for kind, key, argv in corpus_requests(scan, targets, kinds):
        run(kind, key, argv)
    return record


def zero_rows(snapshot: Dict[str, Any]) -> List[str]:
    """Rows whose answer counted nothing (or printed no JSON): each needs a positive control."""
    found = []
    for name, record in snapshot['corpora'].items():
        for key, row in (record.get('rows') or {}).items():
            if row.get('status') != 'ok' or not row.get('count'):
                found.append(f'{name} {key}: status={row.get("status")} count={row.get("count")}')
    return found


def take_snapshot(args: argparse.Namespace) -> int:
    root = Path(args.corpus_root).expanduser().resolve() if args.corpus_root else corpus_root().resolve()
    src = Path(args.src).expanduser().resolve()
    env = request_env(src, args.disk_cache)
    loaded = reveal_location(env, root)
    if os.path.normcase(str(Path(loaded).resolve())) != os.path.normcase(str(src)):
        _log(f'refusing: python -m reveal loads reveal from {loaded}, not --src {src}')
        return 2
    specs = [parse_corpus_spec(s) for s in args.corpus] if args.corpus else (
        gated_corpora() + [(name, '.') for name in UNGATED])
    kinds = tuple(args.only) if args.only else KINDS
    fixed: Dict[str, List[str]] = {}
    if args.targets_from:
        previous = load_snapshot(Path(args.targets_from))
        fixed = {name: rec.get('targets', []) for name, rec in previous['corpora'].items()}
    started = datetime.now(timezone.utc).isoformat()
    load_start = os.getloadavg() if hasattr(os, 'getloadavg') else None
    snapshot: Dict[str, Any] = {
        'format_version': FORMAT_VERSION,
        'tool': 'scripts/imports_fold_snapshot.py',
        'src': str(src), 'src_head': _git_head(src), 'src_tree_sha256': source_digest(src),
        'corpus_root': str(root),
        'python': sys.version, 'platform': platform.platform(),
        'env': {k: env.get(k) for k in ('REVEAL_DISK_CACHE', 'REVEAL_NO_CONFIG', 'PYTHONHASHSEED',
                                        'REVEAL_MAX_WORKERS')},
        'kinds': list(kinds), 'target_count': args.targets, 'seed': args.seed,
        'started_at': started, 'loadavg_start': load_start,
        'wall_times': 'contended: measured on a shared machine, not a benchmark',
        'corpora': {},
    }
    for name, scan_root in specs:
        _log(f'{name} ({scan_spelling(name, scan_root)})')
        snapshot['corpora'][name] = snapshot_corpus(
            name, scan_root, root, env, kinds=kinds, target_count=args.targets, seed=args.seed,
            fixed_targets=fixed.get(name) if args.targets_from else None, timeout=args.timeout)
    snapshot['finished_at'] = datetime.now(timezone.utc).isoformat()
    snapshot['loadavg_end'] = os.getloadavg() if hasattr(os, 'getloadavg') else None
    snapshot['missing'] = sorted(n for n, r in snapshot['corpora'].items() if r['status'] == 'missing')
    snapshot['zero_rows'] = zero_rows(snapshot)
    write_snapshot(Path(args.output), snapshot)
    for line in snapshot['zero_rows']:
        _log(f'zero row (needs a positive control): {line}')
    if snapshot['missing']:
        _log(f'missing corpora: {", ".join(snapshot["missing"])}')
    return 0


def write_snapshot(path: Path, snapshot: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode('utf-8')
    if path.suffix == '.gz':
        data = gzip.compress(data)
    path.write_bytes(data)


def load_snapshot(path: Path) -> Dict[str, Any]:
    data = path.read_bytes()
    if path.suffix == '.gz':
        data = gzip.decompress(data)
    return json.loads(data.decode('utf-8'))


# ── compare ───────────────────────────────────────────────────────────────────

_ROW_FIELDS = ('status', 'exit_code', 'stdout_sha256', 'stderr', 'count', 'counts', 'cut')


def _item_key(item: Any, index: int) -> str:
    """A list item's identity, so one changed row is reported as that row, not as a shift."""
    if isinstance(item, dict):
        for fields in (('file', 'line'), ('file',), ('module',), ('from', 'to'), ('rule_code', 'line'),
                       ('target',), ('rule',)):
            if all(f in item for f in fields):
                return '|'.join(str(item[f]) for f in fields)
    if isinstance(item, (str, int, float)) and not isinstance(item, bool):
        return str(item)  # a sorted list of paths: the path is the row
    return f'#{index}'


def flatten(value: Any, prefix: str = '') -> Dict[str, Any]:
    """JSON leaves by path; list items keyed by their identity where they carry one."""
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for key in value:
            out.update(flatten(value[key], f'{prefix}.{key}' if prefix else str(key)))
        return out or {prefix: {}}
    if isinstance(value, list):
        out = {}
        seen: Dict[str, int] = {}
        for index, item in enumerate(value):
            key = _item_key(item, index)
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 1:
                key = f'{key}#{seen[key]}'
            out.update(flatten(item, f'{prefix}[{key}]'))
        return out or {prefix: []}
    return {prefix: value}


def diff_rows(a: Dict[str, Any], b: Dict[str, Any]) -> List[str]:
    """Every difference between two rows of the same key (wall time is never compared)."""
    changes = [f'{field}: {a.get(field)!r} -> {b.get(field)!r}'
               for field in _ROW_FIELDS if field != 'stderr' and a.get(field) != b.get(field)]
    if a.get('stderr') != b.get('stderr'):
        changes.append('stderr changed')
    if a.get('stdout_sha256') is not None and a.get('stdout_sha256') == b.get('stdout_sha256'):
        return changes  # the same bytes parse to the same JSON
    fa, fb = flatten(a.get('json')), flatten(b.get('json'))
    for path in sorted(set(fa) | set(fb)):
        if path not in fb:
            changes.append(f'json {path}: only in A')
        elif path not in fa:
            changes.append(f'json {path}: only in B')
        elif fa[path] != fb[path]:
            changes.append(f'json {path}: {fa[path]!r} -> {fb[path]!r}')
    return changes


def compare(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[List[Tuple[str, List[str]]], List[str]]:
    """(changed rows with their differences, rows that could not be compared)."""
    changed: List[Tuple[str, List[str]]] = []
    incomparable: List[str] = []
    for name in sorted(set(a['corpora']) | set(b['corpora'])):
        ra, rb = a['corpora'].get(name), b['corpora'].get(name)
        if ra is None or rb is None:
            changed.append((name, [f'corpus only in {"B" if ra is None else "A"}']))
            continue
        if ra['status'] != 'ok' or rb['status'] != 'ok':
            incomparable.append(f'{name}: status {ra["status"]} / {rb["status"]}')
            continue
        if ra.get('targets') != rb.get('targets'):
            changed.append((f'{name} targets', [f'{ra.get("targets")} -> {rb.get("targets")}']))
        rows_a, rows_b = ra['rows'], rb['rows']
        for key in sorted(set(rows_a) | set(rows_b)):
            row_a, row_b = rows_a.get(key), rows_b.get(key)
            label = f'{name} {key}'
            if row_a is None or row_b is None:
                changed.append((label, [f'row only in {"B" if row_a is None else "A"}']))
            elif 'timeout' in (row_a.get('status'), row_b.get('status')):
                incomparable.append(f'{label}: timed out ({row_a.get("status")} / {row_b.get("status")})')
            else:
                changes = diff_rows(row_a, row_b)
                if changes:
                    changed.append((label, changes))
    return changed, incomparable


def run_compare(path_a: Path, path_b: Path, shown: int) -> int:
    a, b = load_snapshot(path_a), load_snapshot(path_b)
    changed, incomparable = compare(a, b)
    rows = sum(len(r.get('rows', {})) for r in a['corpora'].values())
    for label, path, snap in (('A', path_a, a), ('B', path_b, b)):
        print(f'{label}: {path} (src_head {snap.get("src_head")}, reveal/ sha256 {snap.get("src_tree_sha256")})')
    print(f'{len(a["corpora"])} corpora, {rows} rows in A; {len(changed)} changed, '
          f'{len(incomparable)} not comparable')
    for label, changes in changed:
        print(f'CHANGED {label}: {len(changes)} difference(s)')
        for line in changes[:shown] if shown else changes:
            print(f'    {line}')
        if shown and len(changes) > shown:
            print(f'    ... {len(changes) - shown} more (--show 0 prints all)')
    for line in incomparable:
        print(f'NOT COMPARED {line}')
    return 1 if changed or incomparable else 0


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--output', help='snapshot file to write (.json, or .json.gz)')
    parser.add_argument('--compare', nargs=2, metavar=('A', 'B'), help='diff two snapshot files')
    parser.add_argument('--show', type=int, default=20, help='differences printed per changed row (0 = all)')
    parser.add_argument('--corpus', action='append', default=[], metavar='ID[=SCAN_ROOT]',
                        help='corpus under the corpus root (repeatable; default: gated + UNGATED)')
    parser.add_argument('--corpus-root', help='default $REVEAL_CORPUS_DIR or ~/.cache/reveal-corpus')
    parser.add_argument('--src', default=str(REPO_ROOT), help='checkout whose reveal answers')
    parser.add_argument('--only', action='append', choices=KINDS, help='record only these kinds (repeatable)')
    parser.add_argument('--targets', type=int, default=DEFAULT_TARGETS, help='depends:// file targets per corpus')
    parser.add_argument('--seed', type=int, default=0, help='offset of the every-k-th target rule')
    parser.add_argument('--targets-from', help='reuse the targets recorded in this snapshot')
    parser.add_argument('--timeout', type=float, default=DEFAULT_TIMEOUT, help='seconds per request')
    parser.add_argument('--disk-cache', action='store_true', help='do not force REVEAL_DISK_CACHE=0')
    args = parser.parse_args(argv)
    if args.compare:
        return run_compare(Path(args.compare[0]), Path(args.compare[1]), args.show)
    if not args.output:
        parser.error('--output is required unless --compare is given')
    return take_snapshot(args)


if __name__ == '__main__':
    raise SystemExit(main())

#!/usr/bin/env python3
"""Serial cold/warm timing sweep of reveal commands over pinned corpora (BACK-1871).

A timing is only worth quoting when the run was quiet, succeeded and produced the same
answer. Every row therefore records the exit code and a digest of stdout, a row is not `ok`
when the exit code is outside the command's allowed set, and the sweep reports any
(corpus, command) whose digest differs between cold and warm or between repeats: during
BACK-1864 two "speedups" were runs that had crashed.

  scripts/perf_sweep.py --corpus java-guava:guava/src/com/google/common/collect
  scripts/perf_sweep.py --corpus python-celery --commands overview,stats --modes cold --repeat 3
  scripts/perf_sweep.py --corpus python-celery --src ~/.cache/reveal-wt/foo --out base.jsonl
  scripts/perf_sweep.py --list

Corpora are the pinned trees under ~/.cache/reveal-corpus (scripts/fetch_corpus.py), written as
NAME or NAME:SUBPATH. Commands run one at a time as `python -m reveal`, in their own process
group, with PYTHONHASHSEED=0 and REVEAL_NO_CONFIG=1. Modes:

  cold  REVEAL_DISK_CACHE=0
  warm  one untimed priming run with the disk cache on, then the timed run

Wall time is a plain perf_counter reading (never from a cProfile run, which inflates tiny-call
code about 4x). CPU is the user+sys delta of waited-for children, so pool workers that were
joined are counted. Rows are skipped, not run, while the 1-minute load average is above
--max-load-frac of the cores (a sweep at load 10-27 produced fake timeouts).

POSIX only (resource, killpg, getloadavg). Each JSONL row also carries the ts/argv/elapsed_s/exit_code/max_workers_env keys of
~/.reveal/perf.jsonl. Compare two runs with --src (a checkout or worktree to put on
PYTHONPATH) and diff the `digest` and `min wall` columns of the two summaries.
"""
import argparse
import hashlib
import json
import os
import platform
import resource
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# name -> (argv template with {t} = the target path, allowed exit codes)
COMMANDS = {
    'structure': (['{t}'], {0}),
    'files': (['{t}', '--files'], {0}),
    'grep': (['{t}', '--grep', 'return'], {0}),
    'imports': (['imports://{t}'], {0}),
    'depends': (['depends://{t}'], {0}),
    'ast-name': (['ast://{t}?name=parse'], {0}),
    'uncalled': (['calls://{t}?uncalled'], {0}),
    'stats': (['stats://{t}'], {0}),
    'overview': (['overview://{t}'], {0}),
    'hotspots': (['hotspots://{t}'], {0}),
}
DEFAULT_COMMANDS = ['structure', 'imports', 'depends', 'ast-name', 'uncalled', 'stats', 'overview', 'hotspots']


def corpus_root() -> Path:
    return Path(os.environ.get('REVEAL_CORPUS_DIR', Path.home() / '.cache' / 'reveal-corpus'))


def resolve_target(spec: str) -> Path:
    name, _, sub = spec.partition(':')
    target = corpus_root() / name / sub if sub else corpus_root() / name
    if not target.is_dir():
        raise SystemExit(f'corpus {spec!r}: {target} is not a directory (scripts/fetch_corpus.py)')
    return target


def _git(src: Path, *args: str) -> tuple[int, str]:
    out = subprocess.run(['git', '-C', str(src), *args], capture_output=True)
    return out.returncode, out.stdout.decode('utf-8', 'replace').strip()


def source_sha(src: Path) -> str:
    rc, sha = _git(src, 'rev-parse', '--short', 'HEAD')
    _, dirty = _git(src, 'status', '--porcelain', '--', 'reveal')
    return (sha if rc == 0 else 'unknown') + ('+dirty' if dirty else '')


def child_env(src: Path, mode: str, workers: int) -> dict:
    env = dict(os.environ)
    env.update(PYTHONHASHSEED='0', REVEAL_NO_CONFIG='1', REVEAL_MAX_WORKERS=str(workers),
               PYTHONPATH=str(src) + os.pathsep + env.get('PYTHONPATH', ''))
    if mode == 'cold':
        env['REVEAL_DISK_CACHE'] = '0'
    else:
        env.pop('REVEAL_DISK_CACHE', None)
    return env


def run_once(argv: list, env: dict, timeout: float) -> dict:
    """Run one command in its own process group; return rc, timings, digest."""
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.perf_counter()
    proc = subprocess.Popen([sys.executable, '-m', 'reveal', *argv], env=env, cwd=str(REPO_ROOT),
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        os.killpg(proc.pid, signal.SIGKILL)
        out, err = proc.communicate()
    wall = time.perf_counter() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    return {
        'rc': proc.returncode, 'timed_out': timed_out, 'wall_s': round(wall, 3),
        'user_s': round(after.ru_utime - before.ru_utime, 3),
        'sys_s': round(after.ru_stime - before.ru_stime, 3),
        'digest': hashlib.sha256(out).hexdigest()[:16], 'out_bytes': len(out),
        'stderr_tail': err.decode('utf-8', 'replace')[-300:],
    }


def load_too_high(max_frac: float) -> tuple[bool, float]:
    load = os.getloadavg()[0]
    return load > (os.cpu_count() or 1) * max_frac, load


def sweep_cell(corpus, cmd_name, mode, rep, args, src, sha) -> dict:
    template, allowed = COMMANDS[cmd_name]
    argv = [a.format(t=args.targets[corpus]) for a in template]
    row = {'ts': time.time(), 'corpus': corpus, 'command': cmd_name, 'mode': mode, 'rep': rep,
           'argv': argv, 'sha': sha, 'python': platform.python_version(), 'workers': args.workers,
           'max_workers_env': str(args.workers), 'cpus': os.cpu_count()}
    busy, load = load_too_high(args.max_load_frac)
    row['load1_before'] = load
    if busy:
        row.update(status='skipped_load', ok=False)
        return row
    env = child_env(src, mode, args.workers)
    if mode == 'warm':
        run_once(argv, env, args.timeout)
    res = run_once(argv, env, args.timeout)
    row.update(res, load1_after=os.getloadavg()[0], elapsed_s=res['wall_s'], exit_code=res['rc'])
    row['cpu_s'] = round(res['user_s'] + res['sys_s'], 3)
    row['ok'] = (not res['timed_out']) and res['rc'] in allowed
    row['status'] = 'timeout' if res['timed_out'] else ('ok' if row['ok'] else f"rc={res['rc']}")
    return row


def summarize(rows: list) -> int:
    """Print min wall per cell and flag skipped, failed and digest-mismatched cells."""
    problems = 0
    cells: dict = {}
    for r in rows:
        cells.setdefault((r['corpus'], r['command']), []).append(r)
    w = max(len(c) for c, _ in cells) + 2
    print(f"{'corpus':<{w}}{'command':<11}{'mode':<6}{'min wall':>9}{'cpu':>8}{'n':>3}  digest/status", file=sys.stderr)
    for (corpus, cmd), group in cells.items():
        digests = {r['digest'] for r in group if r.get('ok')}
        if len(digests) > 1:
            problems += 1
        for mode in ('cold', 'warm'):
            sub = [r for r in group if r['mode'] == mode]
            if not sub:
                continue
            good = [r for r in sub if r.get('ok')]
            bad = [r for r in sub if not r.get('ok')]
            if bad:
                problems += 1
            best = min(good, key=lambda r: r['wall_s']) if good else None
            tail = ','.join(sorted({r['status'] for r in bad})) or (sub[0]['digest'] if len(digests) == 1 else 'MISMATCH')
            print(f"{corpus:<{w}}{cmd:<11}{mode:<6}{best['wall_s'] if best else '-':>9}"
                  f"{best['cpu_s'] if best else '-':>8}{len(sub):>3}  {tail}", file=sys.stderr)
    return problems


def parse_args(argv):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--corpus', action='append', help='NAME or NAME:SUBPATH under the corpus dir (repeatable)')
    ap.add_argument('--commands', default=','.join(DEFAULT_COMMANDS), help='comma list; --list shows the choices')
    ap.add_argument('--modes', default='cold,warm')
    ap.add_argument('--repeat', type=int, default=3, help='timed runs per cell; quote the minimum')
    ap.add_argument('--workers', type=int, default=1, help='REVEAL_MAX_WORKERS (default 1: serial)')
    ap.add_argument('--timeout', type=float, default=300.0)
    ap.add_argument('--max-load-frac', type=float, default=0.5, help='skip rows while load1 > frac * cores')
    ap.add_argument('--src', type=Path, default=REPO_ROOT, help='checkout to put on PYTHONPATH (default: this one)')
    ap.add_argument('--out', type=Path, help='append JSONL rows here (default: stderr summary only)')
    ap.add_argument('--list', action='store_true', help='list commands and exit')
    return ap.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.list:
        for name, (tmpl, allowed) in COMMANDS.items():
            print(f'{name:<11} reveal {" ".join(tmpl)}   (rc in {sorted(allowed)})')
        return 0
    if not args.corpus:
        raise SystemExit('--corpus is required (see --help)')
    names = args.commands.split(',')
    unknown = [n for n in names if n not in COMMANDS]
    modes = args.modes.split(',')
    if unknown or any(m not in ('cold', 'warm') for m in modes):
        raise SystemExit(f'unknown command(s) {unknown} or mode(s) {modes}')
    args.targets = {c: resolve_target(c) for c in args.corpus}
    src = args.src.resolve()
    sha = source_sha(src)
    print(f'sweep of {src} @ {sha}, load1 {os.getloadavg()[0]:.1f} on {os.cpu_count()} cpus', file=sys.stderr)
    rows = []
    out = args.out.open('a', encoding='utf-8') if args.out else None
    try:
        for corpus in args.corpus:
            for cmd in names:
                for mode in modes:
                    for rep in range(args.repeat):
                        row = sweep_cell(corpus, cmd, mode, rep, args, src, sha)
                        rows.append(row)
                        if out:
                            out.write(json.dumps(row) + '\n')
                            out.flush()
    finally:
        if out:
            out.close()
    return 3 if summarize(rows) else 0


if __name__ == '__main__':
    sys.exit(main())

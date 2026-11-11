#!/usr/bin/env python3
"""Run public recall signals on the rows an unpushed range touches (BACK-2516/2586).

A change that moves what counts as an import runs its gate rows before it is pushed (plan rule
10). BACK-2497 changed parse-loss counting in analyzers/imports/base.py and was pushed with four
stale baselines that only the weekly recall workflow would have caught. The calls gate
(check_calls_gate.py, BACK-2204) checks recorded evidence because its oracles are private and take
about 24 minutes; the imports gate is public and measures every row in about 5 minutes, so this
helper runs scripts/recall_gate.py itself on the selected rows and fails on a red one.

Path classes: shared infrastructure, the import engine and the gate's own inputs re-measure every
row; a language's analyzer or extractor re-measures that language's rows; anything else is
unrelated. --signal calls uses the private Calls trigger's path semantics, selecting
call_recall populations from the public manifest. Its report and audit are separate
from imports and private Calls evidence. --describe prints the selection without measuring.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_calls_gate import (  # noqa: E402  (sibling script, not a package)
    SHARED_PATHS, analyzer_languages, audit, changed_paths, git, toolchain, unpushed_base,
    path_languages as calls_path_languages,
)

# What the measurement itself reads: a change to one re-measures every row.
GATE_INPUTS = frozenset({
    'scripts/recall_gate.py', 'scripts/recall_oracles.py', 'tests/corpus/manifest.yaml',
    '.github/workflows/recall.yml', 'scripts/check_imports_gate.py', 'scripts/check_calls_gate.py',
})
# The import engine and what it shares: parse-loss counting, node access, the stdlib lists.
ENGINE_PREFIXES = ('reveal/analyzers/imports/', 'reveal/core/', 'reveal/rules/imports/', 'scripts/oracles/')
# Per-language extractors inside the engine directory narrow to their language's rows.
LANGUAGE_EXTRACTORS = frozenset({'go', 'rust', 'python', 'javascript', 'zig'})


def path_languages(path, signal='imports'):
    """None re-measures every row; an empty set is unrelated to the signal."""
    if path in GATE_INPUTS:
        return None
    if signal == 'calls':
        return None if path == 'tests/corpus/calls_baseline.json' else calls_path_languages(path)
    if path in SHARED_PATHS or path in {'tests/corpus/recall_baseline.json', 'reveal/adapters/imports.py'}:
        return None
    stem = Path(path).stem
    if path.startswith('reveal/analyzers/imports/'):
        return analyzer_languages(stem) if stem in LANGUAGE_EXTRACTORS else None
    if path.startswith(ENGINE_PREFIXES):
        return None
    if path.startswith('reveal/analyzers/') and path.endswith('.py'):
        # The extractor parses through each language's analyzer (base.get_analyzer(...).tree).
        return analyzer_languages(stem)
    return set()


def recall_rows(manifest, signal='imports'):
    """Recall corpus ids by signal and manifest language (recall_gate.corpus_key)."""
    field = 'call_recall' if signal == 'calls' else 'recall'
    rows = {}
    for entry in manifest['corpora']:
        if field in entry:
            rows.setdefault(entry['language'], []).append(entry.get('id', entry['language']))
    return rows


def select(paths, manifest, signal='imports'):
    """(sorted corpus ids, languages touched that have no recall row)."""
    rows = recall_rows(manifest, signal)
    every = sorted(key for keys in rows.values() for key in keys)
    known_languages = {entry['language'] for entry in manifest['corpora']}
    wanted, unmeasured = set(), set()
    for path in paths:
        languages = path_languages(path, signal)
        if languages is None or (signal == 'calls' and languages - known_languages):
            # Match the Calls trigger's conservative fallback for unknown shared owners.
            return every, []
        if 'typescript' in languages:
            languages = languages | {'tsx'}  # the manifest keeps the .tsx population as its own language
        for language in languages:
            if language in rows:
                wanted.update(rows[language])
            else:
                unmeasured.add(language)
    return sorted(wanted), sorted(unmeasured)


def build_request(repo, signal='imports'):
    repo, base = unpushed_base(repo)
    paths = changed_paths(repo, base)
    request = {'checkout': str(repo), 'head': git(repo, 'rev-parse', 'HEAD'), 'base': base,
               'changed_paths': paths, 'signal': signal, 'rows': [], 'no_recall_row': []}
    if any(path_languages(path, signal) != set() for path in paths):
        manifest = yaml.safe_load((repo / 'tests/corpus/manifest.yaml').read_text(encoding='utf-8'))
        request['rows'], request['no_recall_row'] = select(paths, manifest, signal)
    return request


def pinned_pack(repo):
    """The tree-sitter-language-pack version recall.yml pins, or None."""
    return _recall_pin(repo, 'tree-sitter-language-pack==')


def pinned_go(repo):
    """The Go toolchain recall.yml installs (``go1.27.3``), or None: the one the Go oracle accepts."""
    version = _recall_pin(repo, 'go-version:')
    return f'go{version}' if version else None


def _recall_pin(repo, marker):
    workflow = repo / '.github/workflows/recall.yml'
    if not workflow.exists():
        return None
    for line in workflow.read_text(encoding='utf-8').splitlines():
        if marker in line:
            return line.split(marker)[1].split()[0].strip('"\'')
    return None


def measure(repo, rows, interpreter, corpus_root, output, signal='imports'):
    """Run the gate on ROWS with INTERPRETER; returns its exit code (output streams to the terminal)."""
    pin, have = pinned_pack(repo), toolchain(interpreter)['tree_sitter_language_pack']
    if pin and pin != have:
        print(f'{signal} recall gate: WARNING language pack {have} here, recall.yml pins {pin}; a moved '
              'partial_files row may be the pack, not the change (BACK-2503): compare a base-commit run',
              file=sys.stderr)
    env = dict(os.environ)
    # The Go oracle runs exactly the toolchain recall.yml pins: prefer it where golang.org/dl installs it,
    # else whatever go is on PATH, else the system install (the oracle names a version mismatch itself).
    go_pin = pinned_go(repo)
    pinned = Path.home() / 'sdk' / go_pin / 'bin' if go_pin else None
    if pinned is not None and (pinned / 'go').exists():
        env['PATH'] = str(pinned) + os.pathsep + env.get('PATH', '')
    elif shutil.which('go', path=env.get('PATH')) is None and Path('/usr/local/go/bin/go').exists():
        env['PATH'] = env.get('PATH', '') + os.pathsep + '/usr/local/go/bin'
    command = [str(interpreter), str(repo / 'scripts/recall_gate.py'), '--corpus-root', str(corpus_root),
               '--output', str(output), '--signal', signal]
    for row in rows:
        command += ['--corpus', row]
    return subprocess.run(command, cwd=repo, env=env, check=False).returncode


def parse_args(argv):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--signal', choices=['imports', 'calls'], default='imports')
    parser.add_argument('--repo', type=Path, default=Path.cwd())
    parser.add_argument('--interpreter', type=Path, required=True,
                        help='the Python that has this checkout installed (the CI venv)')
    parser.add_argument('--corpus-root', type=Path,
                        default=Path(os.environ.get('REVEAL_CORPUS_DIR', '~/.cache/reveal-corpus')).expanduser())
    parser.add_argument('--output', type=Path)
    parser.add_argument('--describe', action='store_true')
    parser.add_argument('--skip-reason')
    parser.add_argument('--log', type=Path)
    args = parser.parse_args(argv)
    stem = 'calls-recall-gate' if args.signal == 'calls' else 'imports-gate'
    logs = Path.home() / '.cache/reveal-ci/logs'
    if args.output is None:
        args.output = logs / f'{stem}-report.json'
    if args.log is None:
        args.log = logs / f'{stem}.jsonl'
    if args.skip_reason is not None and (not args.skip_reason.strip() or args.describe):
        parser.error('--skip-reason requires a nonempty reason and cannot accompany --describe')
    return args


def main(argv=None):
    args = parse_args(argv)
    label = 'calls recall gate' if args.signal == 'calls' else 'imports gate'
    try:
        if args.skip_reason is not None:
            detail = f'{label} SKIPPED explicitly: {args.skip_reason}'
            audit(args.log, args.repo.resolve(), 'skip', detail)
            print(detail, file=sys.stderr)
            return 0
        request = build_request(args.repo, args.signal)
        if args.describe:
            print(json.dumps(request, indent=2, sort_keys=True))
            return 0
        if request['no_recall_row']:
            print(f"{label}: no recall row for {', '.join(request['no_recall_row'])} "
                  f'(no independent {args.signal} oracle; nothing to measure)', file=sys.stderr)
        if not request['rows']:
            detail = f'{label}: no {args.signal} paths with a recall row changed in the unpushed range'
            audit(args.log, args.repo.resolve(), 'pass', detail)
            print(detail)
            return 0
        rows = request['rows']
        print(f"{label}: measuring {len(rows)} row(s): {' '.join(rows)}", flush=True)
        code = measure(Path(request['checkout']), rows, args.interpreter, args.corpus_root, args.output, args.signal)
        if code:
            raise ValueError(f'recall_gate.py exited {code} on {len(rows)} row(s); report {args.output}')
        detail = f"{label}: {len(rows)} row(s) green at {request['head'][:12]}"
        audit(args.log, args.repo.resolve(), 'pass', detail)
        print(detail)
        return 0
    except (OSError, ValueError, KeyError, yaml.YAMLError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = f'{label} FAILED: {exc}'
        audit(args.log, args.repo.resolve(), 'fail', detail)
        print(detail, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())

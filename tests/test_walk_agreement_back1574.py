"""BACK-1574: every command that walks the user's target sees the file set its walk purpose defines.

The walker class (BACK-1223) came back each time a walker re-decided its own skip policy: 30
walks, two skip predicates and four pattern matchers, so ``--exclude`` needed 6 rounds of fixes
and REVEAL_IGNORE 4. Migrating every walker onto the seam is the fix; this test is the guard that
says when it is done, and that stays true after. One fixture carries every hazard, every command
runs over it with the same ``--exclude`` flags and REVEAL_IGNORE, and each command's file set
must equal its purpose's (internal-docs/design/WALKER_SEAM_2026-09-30.md):

- analysis: the files the user wants analyzed. Dot-dirs are source (BACK-1038).
- display: what a reader sees of the tree, so also what ``--grep`` searches and pack:// packs.
  Dot entries are hidden, as in ``ls`` and ``rg``.
- docs: markdown://. As analysis, but a build/ or vendor/ README is still a doc.

``KNOWN_DISAGREEMENTS`` is the live work list. It may only shrink: its cases are strict xfails,
so a fix that makes one agree fails here until its entry is deleted.
"""
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.skipif(shutil.which('git') is None, reason='git not installed')

# Each hazard directory holds one .py (with a function, a subprocess call, the grep marker and a
# long line for E501) and one .md.
HAZARDS = {
    'keep': 'plain source',
    '.github/scripts': 'code under a dot-dir',
    'gen': 'gitignored',
    'ign': 'REVEAL_IGNORE=ign/**',
    'sub/skipme': 'bare --exclude skipme, below the root',
    'pathx/deep': 'path --exclude pathx/deep',
    'src/env/common': 'ambiguous env/ whose source is only in subdirectories (BACK-1582)',
    '.venv/lib/site-packages': 'virtualenv',
    'build': 'ambiguous build/ with code at its top level',
    '.hg': 'VCS internals',
}
EXCLUDE = ['--exclude', 'skipme', '--exclude', 'pathx/deep']
REVEAL_IGNORE = 'ign/**'

_ANALYZED = {'keep', '.github/scripts', 'src/env/common', 'build'}
EXPECTED = {
    'analysis': _ANALYZED,
    'display': _ANALYZED - {'.github/scripts'},
    'docs': _ANALYZED,
}


def _dirs(paths, ext):
    """The hazard dirs a command reported, from the file paths it listed."""
    return {Path(p).parent.as_posix() for p in paths if p.endswith(ext)}


def _tree_paths(entries, prefix=''):
    for e in entries:
        path = f"{prefix}{e['name']}"
        if e.get('type') == 'dir':
            yield from _tree_paths(e.get('children') or [], path + '/')
        else:
            yield path


def _tree(root):
    return _dirs(_tree_paths(_json(root, '.', '--depth', '10')['entries']), '.py')


def _files(root):
    return _dirs((e['path'] for e in _json(root, '.', '--files')['entries']), '.py')


def _grep(root):
    return _dirs((f['path'] for f in _json(root, '.', '--grep', 'HZMARK')['files']), '.py')


def _check(root):
    payload = _json(root, 'check', '.', '--select', 'E501')
    return _dirs((f['file'] for f in payload['files']), '.py')


def _ast(root):
    return _dirs((r['file'] for r in _json(root, 'ast://.')['results']), '.py')


def _stats(root):
    return _dirs((f['file'] for f in _json(root, 'stats://.')['files']), '.py')


def _surface(root):
    hits = _json(root, 'surface://.')['surfaces']['subprocess']
    return _dirs((h['file'] for h in hits), '.py')


def _pack(root):
    return _dirs((f['relative'] if 'relative' in f else f['file']
                  for f in _json(root, 'pack://.')['files']), '.py')


def _imports(root):
    return _dirs(_json(root, 'imports://.')['files'], '.py')


def _markdown(root):
    return _dirs((r['relative_path'] for r in _json(root, 'markdown://.')['results']), '.md')


COMMANDS = {
    'tree': ('display', _tree),
    '--files': ('display', _files),
    '--grep': ('display', _grep),
    'pack://': ('display', _pack),
    'check': ('analysis', _check),
    'ast://': ('analysis', _ast),
    'stats://': ('analysis', _stats),
    'surface://': ('analysis', _surface),
    'imports://': ('analysis', _imports),
    'markdown://': ('docs', _markdown),
}

# command -> why it disagrees today, and the task that fixes it. Shrink-only.
KNOWN_DISAGREEMENTS = {
    'tree': 'PathFilter: no REVEAL_IGNORE, build/ with code always hidden (BACK-1581)',
    '--files': 'PathFilter: no REVEAL_IGNORE, build/ with code always hidden (BACK-1581)',
    '--grep': 'own walk: no REVEAL_IGNORE; nested-only env/ dropped (BACK-1581, BACK-1582)',
    'pack://': 'nested-only env/ dropped (BACK-1582)',
    'check': 'nested-only env/ dropped (BACK-1582)',
    'ast://': 'nested-only env/ dropped (BACK-1582)',
    'stats://': 'nested-only env/ dropped (BACK-1582)',
    'surface://': 'own walk drops dot-dirs; nested-only env/ dropped (BACK-1577, BACK-1582)',
    'imports://': 'own walk drops dot-dirs; nested-only env/ dropped (BACK-1580, BACK-1582)',
}


def _source(name):
    return (f'import subprocess\n\n\ndef f_{name}():\n    subprocess.run(["true"])\n'
            f'    return "HZMARK"\n# {"x" * 130}\n')


@pytest.fixture(scope='module')
def tree(tmp_path_factory):
    root = tmp_path_factory.mktemp('walk_agreement')
    for i, rel in enumerate(HAZARDS):
        (root / rel).mkdir(parents=True, exist_ok=True)
        (root / rel / f'm{i}.py').write_text(_source(i), encoding='utf-8')
        (root / rel / f'd{i}.md').write_text(f'# Doc {i}\n', encoding='utf-8')
    (root / '.venv' / 'pyvenv.cfg').write_text('home = /usr/bin\n', encoding='utf-8')
    (root / '.gitignore').write_text('gen/\n', encoding='utf-8')
    env = dict(os.environ, GIT_CONFIG_GLOBAL=os.devnull)
    subprocess.run(['git', '-C', str(root), 'init', '-q'], check=True, env=env)
    return root


@pytest.fixture
def scoped(tree, monkeypatch):
    from reveal.config import RevealConfig
    monkeypatch.setenv('GIT_CONFIG_GLOBAL', os.devnull)
    monkeypatch.setenv('REVEAL_IGNORE', REVEAL_IGNORE)
    monkeypatch.setattr(RevealConfig, '_cache', {})  # a config built before the env var
    monkeypatch.chdir(tree)
    return tree


def _json(root, *argv):
    result = _run_reveal_direct(*argv, *EXCLUDE, '--format', 'json')
    payload = json.loads(result.stdout)  # check exits 1 on findings, so judge the payload
    assert 'error' not in payload, (payload['error'], result.stderr)
    return payload


def _case(name):
    marks = [pytest.mark.xfail(strict=True, reason=KNOWN_DISAGREEMENTS[name])] \
        if name in KNOWN_DISAGREEMENTS else []
    return pytest.param(name, id=name, marks=marks)


@pytest.mark.parametrize('name', [_case(n) for n in COMMANDS])
def test_command_sees_its_purposes_file_set(scoped, name):
    purpose, files_of = COMMANDS[name]
    assert files_of(scoped) == EXPECTED[purpose]


def test_known_disagreements_name_real_commands():
    assert set(KNOWN_DISAGREEMENTS) <= set(COMMANDS)


def test_the_fixture_reaches_every_hazard(scoped):
    """Positive control: with nothing hidden, one walk sees every hazard's files (a command
    that silently returned nothing would otherwise pass as 'agreeing' on an empty set)."""
    seen = {Path(dirpath).relative_to(scoped).as_posix()
            for dirpath, _, files in os.walk(scoped) if any(f.endswith('.py') for f in files)}
    assert seen == set(HAZARDS)

"""Adapter contract harness (BACK-1513): every registered adapter, one fixture tree,
invariants checked on the result dict.

The adapter set comes from the registry, never from a hand-written list. A new adapter
fails ``test_every_registered_adapter_is_covered`` until it gets a ``FIXTURE_URIS`` row (how
to run it here) or a ``NOT_RUNNABLE`` reason. This file used to hold one hand-written class
per adapter (15 of 35). An adapter nobody listed was never checked, which is the opt-in
failure mode BACK-1363 describes.

Each run goes through ``handle_uri`` with ``--format json`` from a temp cwd, using a
relative URI. That is the same result dict the CLI and MCP produce. Runs are hermetic: HOME
points at a fixture home, and so does every adapter class attribute holding a ``Path``
under the real home (``CodexAdapter.CODEX_DB``, ``ClaudeAdapter.CONVERSATION_BASE``, ...),
since those are resolved once at import. The fixture home holds an empty Claude projects
directory and an empty Codex session DB, so claude:// and codex:// return a real (empty)
answer. Without them their result is an error, and a contract check on an error envelope
proves nothing about the adapter's normal output. Invariants:

1. ``contract``: Output Contract fields are present, and ``type`` is one the schema declares.
2. ``missing``: a nonexistent resource exits nonzero. It is never a clean empty answer
   (BACK-1321).
3. ``error_exit``: a result carrying a top-level ``error`` exits nonzero. An error must not
   read as success. The router enforces this for every adapter since BACK-1059
   (``cli/routing/uri._emit_result``); the fixture runs below are normally clean, so
   the error paths themselves are pinned in ``tests/test_result_outcome.py``.
4. ``abs_path``: no string in the result contains the fixture root's absolute path. The
   input was relative, so an absolute path is a leak (BACK-1366).
5. ``truncation``: every list that ``--head 1`` makes shorter is disclosed as a
   ``truncated`` meta warning naming it (``note_truncation``), and the text render prints
   it (BACK-1059). A cut list must not read as the whole answer.
6. ``subcommand``: every ``reveal <name>`` that answers a query (the ``COMMANDS``
   registry, run through ``main``) prints its result through
   ``cli/routing/subcommand.emit_subcommand_result``, and every cut that result records is
   printed in its text output. Runners that built their own output never checked the
   outcome, so slice 2 of BACK-1059 silently dropped ``reveal overview``'s cut line
   (BACK-1544). ``SUBCOMMAND_CUT_ARGV`` makes the fixture cut real lists, and
   ``test_the_subcommand_cut_invariant_bites`` checks that it does.
7. ``own_cap``: every list an adapter's own cap knob makes shorter is disclosed. The knob is
   the key its ``CLI_QUERY_FLAGS['all']`` lifts, or a ``top``/``limit`` its schema declares;
   the adapter runs on the wider ``wide/`` tree with the knob at 1 and uncapped. A cap the
   adapter applies itself is a ``[:N]`` the router never sees, so ``--head`` (invariant 5)
   can't expose it: ``stats://?hotspots=true&top=2`` showed 2 of 43 hotspot files as the
   whole list (BACK-1543). ``test_the_own_cap_invariant_bites`` checks that it cuts.

Violations that exist today are listed in ``KNOWN_VIOLATIONS`` as strict xfails, each
naming its task. A fix makes its case XPASS, which fails the run until the entry is
deleted. The list can only shrink.

Not covered yet (BACK-1513 follow-ups): caps with no knob (a hard-coded ``[:20]``, which
invariant 7 can't vary), consumed flags (BACK-1514), and POSIX separators on Windows.
"""

import json
import os
import shutil
import sqlite3
import subprocess
from contextlib import contextmanager, redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

import pytest

from reveal import adapters  # noqa: F401  (registers every adapter)
from conftest import production_schemes
from reveal.adapters import base as adapters_base
from reveal.cli.defaults import _default_args
from reveal.cli.invocation import COMMANDS
from reveal.cli.routing import subcommand as subcommand_seam
from reveal.cli.routing.uri import handle_uri
from reveal.main import main
from reveal.utils.results import truncations_of

pytestmark = pytest.mark.contract

# How to run each adapter against the fixture (paths relative to its root). A URI that
# names 'proj' reads the fixture tree and is subject to the abs_path invariant; the rest
# read host state (made hermetic by an empty HOME).
FIXTURE_URIS = {
    'architecture': 'architecture://proj',
    'ast': 'ast://proj',
    'calls': 'calls://proj?target=helper',
    'classify': 'classify://proj',
    'contracts': 'contracts://proj',
    'depends': 'depends://proj',
    'deps': 'deps://proj',
    'diff': 'diff://proj/app_old.py:proj/app.py',
    'git': 'git://proj/app.py',
    'hotspots': 'hotspots://proj',
    'imports': 'imports://proj',
    'json': 'json://proj/data.json',
    'markdown': 'markdown://proj',
    'overview': 'overview://proj',
    'pack': 'pack://proj',
    'patches': 'patches://proj/tests',
    'sqlite': 'sqlite://proj/app.db',
    'stats': 'stats://proj',
    'surface': 'surface://proj',
    'testability': 'testability://proj',
    'trace': 'trace://proj?from=main',
    'xlsx': 'xlsx://proj/data.xlsx',
    'claude': 'claude://sessions',
    'codex': 'codex://',
    'env': 'env://',
    'help': 'help://',
    'nginx': 'nginx://',
    'python': 'python://',
    'reveal': 'reveal://',
}

NOT_RUNNABLE = {
    'autossl': 'reads certbot renewal logs on a server',
    'cpanel': 'needs a live cPanel server',
    'domain': 'needs live DNS',
    'letsencrypt': 'reads /etc/letsencrypt on a server',
    'mysql': 'needs a live MySQL server',
    'ssl': 'needs a live TLS endpoint',
}

# Where 'scheme://nonexistent' is not a well-formed request of that adapter. git reads the
# repository from the cwd; outside one it declines as not-applicable, which exits 0 by
# design (tests/test_routing.py::test_not_applicable_exits_zero_not_one).
MISSING_URIS = {
    'diff': 'diff://nonexistent_zz_1513.py:nonexistent_zz_1513b.py',
    'trace': 'trace://nonexistent_zz_1513?from=main',
}

KNOWN_VIOLATIONS = {
    ('contract', 'codex'): 'BACK-1522',
    ('missing', 'nginx'): 'BACK-1523',
    ('missing', 'reveal'): 'BACK-1521',
    ('abs_path', 'architecture'): 'BACK-1366',
    ('abs_path', 'deps'): 'BACK-1366',
    ('abs_path', 'imports'): 'BACK-1366',
    ('abs_path', 'markdown'): 'BACK-1366',
    ('abs_path', 'overview'): 'BACK-1366',
    ('abs_path', 'stats'): 'BACK-1366',
    ('abs_path', 'testability'): 'BACK-1366',
    ('abs_path', 'xlsx'): 'BACK-1366',
    ('subcommand', 'check'): 'BACK-1545',
    ('own_cap', 'git'): 'BACK-1547',
    ('own_cap', 'overview'): 'BACK-1547',
}

# How to run each `reveal <name>` against the fixture (invariant 6). Every COMMANDS entry
# needs a row here or a NOT_A_QUERY reason.
SUBCOMMAND_ARGV = {
    'architecture': ['proj'],
    'check': ['proj'],
    'contracts': ['proj'],
    'deps': ['proj'],
    'health': ['proj'],
    'hotspots': ['proj'],
    'overview': ['proj'],
    'pack': ['proj'],
    'review': ['proj'],
    'surface': ['proj'],
    'testability': ['proj'],
    'trace': ['proj', '--from', 'main'],
}

NOT_A_QUERY = {
    'dev': 'developer tooling (scaffold, config inspection), not an answer about a target',
    'offline': 'prepares grammars for offline use, not an answer about a target',
    'scaffold': 'writes template files, not an answer about a target',
}

# Flags that make the small fixture cut a list, so the text-disclosure half of invariant 6
# is not vacuously green.
SUBCOMMAND_CUT_ARGV = {
    'hotspots': ['--top', '1', '--min-complexity', '1'],
}

# Invariant 7 runs each adapter that has a cap knob on the wider tree: its FIXTURE_URIS row
# with 'proj' read as 'wide', plus any other views listed here (a view is where a list, and
# the knob that caps it, lives: calls:// ranks only under ?uncalled or ?rank=).
OWN_CAP_URIS = {
    'calls': ['calls://wide?uncalled', 'calls://wide?rank=callers'],
    'depends': ['depends://wide/pkg/y.py'],
    'git': ['git://wide/app.py?type=history'],
    'imports': ['imports://wide?rank=fan-in'],
    'stats': ['stats://wide?hotspots=true'],
    'xlsx': ['xlsx://wide/data.xlsx?sheet=Sheet', 'xlsx://wide/data.xlsx?search=n'],
}

_REQUIRED_FIELDS = ['contract_version', 'type', 'source', 'source_type']
_UNSET = object()
_VALID_SOURCE_TYPES = {'file', 'directory', 'database', 'runtime', 'network'}


def _registered():
    return production_schemes()


def _cases(invariant, schemes):
    """Parametrize `schemes`, marking known violators as strict xfails."""
    params = []
    for scheme in schemes:
        task = KNOWN_VIOLATIONS.get((invariant, scheme))
        marks = [pytest.mark.xfail(strict=True, reason=f'{task}: known violation')] if task else []
        params.append(pytest.param(scheme, marks=marks, id=scheme))
    return params


def _build_tree(root: Path) -> None:
    proj = root / 'proj'
    (proj / 'tests').mkdir(parents=True)
    (root / 'home').mkdir()
    (root / 'home' / '.claude' / 'projects').mkdir(parents=True)
    (root / 'home' / '.codex').mkdir()
    conn = sqlite3.connect(str(root / 'home' / '.codex' / 'state_5.sqlite'))
    conn.execute(
        'CREATE TABLE threads (id TEXT, title TEXT, first_user_message TEXT, model TEXT, '
        'model_provider TEXT, reasoning_effort TEXT, tokens_used INTEGER, cwd TEXT, '
        'created_at INTEGER, updated_at INTEGER, cli_version TEXT, git_branch TEXT, '
        'approval_mode TEXT, thread_source TEXT, archived INTEGER)')
    conn.commit()
    conn.close()
    (proj / 'app.py').write_text(
        'import os\n\n\ndef main():\n    return helper()\n\n\n'
        'def helper():\n    return os.getcwd()\n', encoding='utf-8')
    (proj / 'app_old.py').write_text('def main():\n    pass\n', encoding='utf-8')
    (proj / 'tests' / 'test_app.py').write_text(
        'from unittest import mock\n\n\ndef test_main():\n'
        '    with mock.patch("app.helper"):\n        pass\n', encoding='utf-8')
    (proj / 'README.md').write_text('# Proj\n\nSee [app](app.py).\n', encoding='utf-8')
    (proj / 'data.json').write_text('{"key": "value", "items": [1, 2]}', encoding='utf-8')
    conn = sqlite3.connect(str(proj / 'app.db'))
    conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
    conn.commit()
    conn.close()
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        wb.active.append(['name', 'value'])
        wb.save(str(proj / 'data.xlsx'))
    except ImportError:
        pass
    _build_wide_tree(root / 'wide')
    if shutil.which('git'):  # the root is the repo: git:// resolves it from the cwd
        env = dict(os.environ, GIT_AUTHOR_NAME='t', GIT_AUTHOR_EMAIL='t@example.com',
                   GIT_COMMITTER_NAME='t', GIT_COMMITTER_EMAIL='t@example.com')
        for cmd in (['init', '-q'], ['add', 'proj', 'wide'], ['commit', '-q', '-m', 'init']):
            subprocess.run(['git', '-C', str(root)] + cmd, check=True, env=env,
                           capture_output=True)
        with open(root / 'wide' / 'app.py', 'a', encoding='utf-8') as f:
            f.write('\n\ndef later():\n    pass\n')
        subprocess.run(['git', '-C', str(root), 'commit', '-q', '-am', 'second'], check=True,
                       env=env, capture_output=True)


def _build_wide_tree(wide: Path) -> None:
    """Two or more of everything a cap knob cuts (invariant 7): hotspot files, complex
    functions, callers, imports, modules, patches, JSON items, sheet rows, commits. Kept
    apart from proj/ so the other invariants' fixture answers don't move."""
    (wide / 'pkg').mkdir(parents=True)
    (wide / 'tests').mkdir()
    nested = ''.join('    ' * (i + 1) + f'if x > {i}:\n' for i in range(6)) + '    ' * 7 + 'return x\n'
    branches = ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(12))
    for n in ('a', 'b', 'c'):
        (wide / f'deep_{n}.py').write_text(
            f'def deep_{n}(x):\n{nested}    return 0\n\n\n'
            f'def cx_{n}(x):\n{branches}    return -1\n', encoding='utf-8')
    (wide / 'app.py').write_text(
        'import os\nimport json\nimport sys\nfrom pkg import x, y\n\n\n'
        'def main():\n    return helper() + a() + b()\n\n\n'
        'def a():\n    return helper()\n\n\ndef b():\n    return helper()\n\n\n'
        'def helper():\n    return os.getcwd()\n\n\n'
        'def unused_one():\n    pass\n\n\ndef unused_two():\n    pass\n', encoding='utf-8')
    (wide / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    (wide / 'pkg' / 'x.py').write_text(
        'import requests\nimport yaml\nfrom pkg import y\n\n\ndef fx():\n    return y.fy()\n',
        encoding='utf-8')
    (wide / 'pkg' / 'y.py').write_text(
        'import numpy\nfrom pkg import x\n\n\ndef fy():\n    return 1\n', encoding='utf-8')
    (wide / 'tests' / 'test_app.py').write_text(
        'from unittest import mock\n\n\ndef test_main():\n'
        '    with mock.patch("app.helper"):\n        pass\n'
        '    with mock.patch("app.a"):\n        pass\n\n\n'
        'def test_b():\n    with mock.patch("app.b"):\n        pass\n', encoding='utf-8')
    (wide / 'data.json').write_text(json.dumps([{'n': i} for i in range(4)]), encoding='utf-8')
    for i in range(3):
        (wide / f'doc{i}.md').write_text(f'# Doc {i}\n\n## One\n\n## Two\n', encoding='utf-8')
    try:
        import openpyxl
        wb = openpyxl.Workbook()
        for i in range(4):
            wb.active.append([f'n{i}', i])
        wb.create_sheet('second').append(['k'])
        wb.save(str(wide / 'data.xlsx'))
    except ImportError:
        pass


class _Harness:
    def __init__(self, root: Path):
        self.root = root
        self.home = root / 'home'
        self._cache = {}
        self.needles = {str(p) for r in (root, root.resolve()) for p in (r, r.as_posix())}

    def _home_paths(self):
        """(class, attr, fake path) for adapter class attributes under the real home."""
        real = Path.home()
        for scheme in _registered():
            cls = adapters_base.get_adapter_class(scheme)
            for klass in cls.__mro__:
                for name, value in vars(klass).items():
                    if isinstance(value, Path):
                        try:
                            yield cls, name, self.home / value.relative_to(real)
                        except ValueError:
                            pass

    @contextmanager
    def _hermetic(self):
        # The language pack fixes its grammar cache directory at first use, under HOME. Use it
        # once before HOME moves, or each xdist worker downloads grammars into the empty home
        # (8s+ per worker, and a network dependency).
        from tree_sitter_language_pack import get_parser
        get_parser('python')
        cwd = os.getcwd()
        saved_env = {k: os.environ.get(k) for k in ('HOME', 'USERPROFILE')}
        redirected = [(cls, name, cls.__dict__.get(name, _UNSET), fake)
                      for cls, name, fake in self._home_paths()]
        os.environ['HOME'] = os.environ['USERPROFILE'] = str(self.home)
        for cls, name, _, fake in redirected:
            setattr(cls, name, fake)
        os.chdir(self.root)
        try:
            yield
        finally:
            os.chdir(cwd)
            for cls, name, original, _ in redirected:
                if original is _UNSET:
                    delattr(cls, name)
                else:
                    setattr(cls, name, original)
            for k, v in saved_env.items():
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v

    def run_raw(self, uri, **flags):
        """(exit code, stdout, stderr) for `uri` with CLI `flags`, run once and cached."""
        key = (uri, tuple(sorted(flags.items())))
        if key not in self._cache:
            out, err, code = StringIO(), StringIO(), 0
            with self._hermetic(), redirect_stdout(out), redirect_stderr(err):
                try:
                    handle_uri(uri, None, _default_args(**flags))
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 1
            self._cache[key] = (code, out.getvalue(), err.getvalue())
        return self._cache[key]

    def run(self, uri, **flags):
        """(exit code, parsed JSON or None, stderr) for `uri` with --format json."""
        code, out, err = self.run_raw(uri, format='json', **flags)
        try:
            payload = json.loads(out)
        except ValueError:
            payload = None
        return code, payload, err

    def run_subcommand(self, name, *argv):
        """(exit code, stdout, stderr, results) for `reveal <name> <argv>` through ``main``.

        ``results`` are the result dicts that reached ``emit_subcommand_result``, seen at
        its ``outcome_of`` call; empty when the runner printed its output some other way.
        """
        key = (name, argv)
        if key not in self._cache:
            out, err, code, results = StringIO(), StringIO(), 0, []

            def recording_outcome_of(result, _real=subcommand_seam.outcome_of):
                results.append(result)
                return _real(result)

            with self._hermetic(), redirect_stdout(out), redirect_stderr(err), \
                    pytest.MonkeyPatch.context() as mp:
                mp.setattr(subcommand_seam, 'outcome_of', recording_outcome_of)
                try:
                    main(['reveal', name, *argv])
                except SystemExit as exc:
                    code = exc.code if isinstance(exc.code, int) else 1
            self._cache[key] = (code, out.getvalue(), err.getvalue(), results)
        return self._cache[key]

    def fixture_uri(self, scheme):
        if scheme == 'xlsx' and not (self.root / 'proj' / 'data.xlsx').exists():
            pytest.skip('openpyxl not installed')
        if scheme == 'git' and not shutil.which('git'):
            pytest.skip('git not installed')
        return FIXTURE_URIS[scheme]

    def run_fixture(self, scheme, **flags):
        return self.run(self.fixture_uri(scheme), **flags)


@pytest.fixture(scope='module')
def harness(tmp_path_factory):
    root = tmp_path_factory.mktemp('contract_harness')
    _build_tree(root)
    return _Harness(root)


def _strings(obj, path=''):
    """(json-path, string) for every string value and key in `obj`."""
    if isinstance(obj, str):
        yield path, obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            yield f'{path}.<key>', str(key)
            yield from _strings(value, f'{path}.{key}')
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            yield from _strings(value, f'{path}[{i}]')


# -- coverage --------------------------------------------------------------------------

def test_every_registered_adapter_is_covered():
    registered = set(_registered())
    covered = set(FIXTURE_URIS) | set(NOT_RUNNABLE)
    assert not set(FIXTURE_URIS) & set(NOT_RUNNABLE)
    assert registered - covered == set(), (
        'New adapter(s) with no contract-harness entry: add a FIXTURE_URIS row '
        '(or a NOT_RUNNABLE reason) in tests/test_output_contract_compliance.py')
    assert covered - registered == set(), 'Harness lists adapters that are no longer registered'


def test_known_violations_name_real_cases():
    for invariant, scheme in KNOWN_VIOLATIONS:
        assert invariant in ('contract', 'missing', 'error_exit', 'abs_path', 'truncation',
                             'subcommand', 'own_cap')
        assert scheme in (SUBCOMMAND_ARGV if invariant == 'subcommand' else FIXTURE_URIS)


# -- invariants ------------------------------------------------------------------------

@pytest.mark.parametrize('scheme', _cases('contract', sorted(FIXTURE_URIS)))
def test_contract(harness, scheme):
    code, payload, err = harness.run_fixture(scheme)
    assert code == 0, f'{scheme}: exit {code}: {err[:300]}'
    assert isinstance(payload, dict), f'{scheme}: --format json did not print a JSON object'
    for field in _REQUIRED_FIELDS:
        assert payload.get(field), f'{scheme}: missing or empty contract field {field!r}'
    assert payload['source_type'] in _VALID_SOURCE_TYPES, payload['source_type']
    schema = adapters_base.get_adapter_class(scheme).get_schema() or {}
    declared = {ot['type'] for ot in schema.get('output_types', [])}
    if declared:
        assert payload['type'] in declared, (
            f"{scheme}: type {payload['type']!r} is not in the schema's output_types")


@pytest.mark.parametrize('scheme', _cases('missing', sorted(FIXTURE_URIS)))
def test_missing_resource_is_an_error(harness, scheme):
    code, _, err = harness.run(MISSING_URIS.get(scheme, f'{scheme}://nonexistent_zz_1513'))
    assert code != 0, f'{scheme}: a nonexistent resource exited 0 (stderr: {err[:200]!r})'


@pytest.mark.parametrize('scheme', _cases('error_exit', sorted(FIXTURE_URIS)))
def test_error_in_result_exits_nonzero(harness, scheme):
    code, payload, _ = harness.run_fixture(scheme)
    if isinstance(payload, dict) and payload.get('error'):
        assert code != 0, f"{scheme}: result carries error {payload['error']!r} but exited 0"


@pytest.mark.parametrize('scheme', _cases(
    'abs_path', sorted(s for s, uri in FIXTURE_URIS.items() if '://proj' in uri)))
def test_no_absolute_fixture_path_in_result(harness, scheme):
    _, payload, _ = harness.run_fixture(scheme)
    leaks = [(where, value) for where, value in _strings(payload)
             if any(needle in value for needle in harness.needles)]
    assert not leaks, f'{scheme}: absolute path in a result for a relative input: {leaks[:3]}'


def _cut_lists(full, cut):
    """Top-level lists that are shorter in `cut` than in `full`."""
    if not (isinstance(full, dict) and isinstance(cut, dict)):
        return []
    return sorted(key for key, value in full.items()
                  if isinstance(value, list) and isinstance(cut.get(key), list)
                  and len(cut[key]) < len(value))


@pytest.mark.parametrize('scheme', _cases('truncation', sorted(FIXTURE_URIS)))
def test_a_cut_list_is_disclosed(harness, scheme):
    _, full, _ = harness.run_fixture(scheme)
    _, cut, _ = harness.run_fixture(scheme, head=1)
    shortened = _cut_lists(full, cut)
    if not shortened:
        return
    disclosed = {entry.get('field') for entry in truncations_of(cut)}
    assert set(shortened) <= disclosed, (
        f'{scheme}: --head 1 cut {shortened} but the result discloses only {sorted(disclosed)}')
    _, text, _ = harness.run_raw(harness.fixture_uri(scheme), format='text', head=1)
    for field in shortened:
        assert f'⚠ Truncated {field}: ' in text, f'{scheme}: text render hides the cut of {field}'


def test_the_truncation_invariant_bites(harness):
    """Positive control: on this fixture --head 1 really cuts some adapters' lists, so
    test_a_cut_list_is_disclosed is not vacuously green."""
    expected = ['ast', 'classify', 'pack', 'reveal', 'stats']
    bitten = [scheme for scheme in expected
              if _cut_lists(harness.run_fixture(scheme)[1], harness.run_fixture(scheme, head=1)[1])]
    assert bitten == expected


# --- Invariant 6: subcommand forms (BACK-1544) ---------------------------------------------

def test_every_subcommand_is_covered():
    covered = set(SUBCOMMAND_ARGV) | set(NOT_A_QUERY)
    assert not set(SUBCOMMAND_ARGV) & set(NOT_A_QUERY)
    assert set(COMMANDS) - covered == set(), (
        'New subcommand(s) with no contract-harness entry: add a SUBCOMMAND_ARGV row '
        '(or a NOT_A_QUERY reason) in tests/test_output_contract_compliance.py')
    assert covered - set(COMMANDS) == set(), 'Harness lists subcommands that no longer exist'


@pytest.mark.parametrize('name', _cases('subcommand', sorted(SUBCOMMAND_ARGV)))
def test_subcommand_result_leaves_through_the_seam(harness, name):
    argv = SUBCOMMAND_ARGV[name] + SUBCOMMAND_CUT_ARGV.get(name, [])
    for fmt in ('json', 'text'):
        _, _, err, results = harness.run_subcommand(name, *argv, '--format', fmt)
        assert results, (
            f'reveal {name} --format {fmt} printed its result without emit_subcommand_result '
            f'(cli/routing/subcommand.py), so a failed or cut answer goes unreported. '
            f'stderr: {err[-300:]}')
    # The envelope (BACK-906) under the subcommand's own name, conforming to the same
    # contract version as its URI twin (BACK-1178: pack's said 1.0 to pack://'s 1.1).
    _, out, _, _ = harness.run_subcommand(name, *argv, '--format', 'json')
    payload = json.loads(out)
    assert [f for f in _REQUIRED_FIELDS if f not in payload] == []
    assert payload['type'] == name
    if name in FIXTURE_URIS:
        _, twin, _ = harness.run_fixture(name)
        assert payload['contract_version'] == twin['contract_version'], (
            f'reveal {name} and {name}:// disagree about the contract their payload conforms to')
    _, text, _, results = harness.run_subcommand(name, *argv, '--format', 'text')
    for entry in truncations_of(results[-1]):
        assert f"⚠ Truncated {entry['message']}" in text, (
            f"reveal {name}: the result records a cut of {entry['field']} that the text hides")


def test_the_subcommand_cut_invariant_bites(harness):
    """Positive control: with SUBCOMMAND_CUT_ARGV the fixture really cuts these
    subcommands' lists, so the text-disclosure check above is not vacuously green."""
    for name, extra in SUBCOMMAND_CUT_ARGV.items():
        _, text, _, results = harness.run_subcommand(
            name, *SUBCOMMAND_ARGV[name], *extra, '--format', 'text')
        assert results and truncations_of(results[-1]), f'reveal {name} {extra}: nothing was cut'
        assert '⚠ Truncated ' in text


# --- Invariant 7: an adapter's own cap (BACK-1543) ----------------------------------------

def _cap_knobs(scheme):
    """The query keys that cap this adapter's lists: the one --all lifts, plus a declared
    top/limit. Derived from the adapter's own declarations, never a hand-written table."""
    cls = adapters_base.get_adapter_class(scheme)
    knobs = set()
    lifted = (getattr(cls, 'CLI_QUERY_FLAGS', None) or {}).get('all')
    if lifted:
        knobs.add(lifted.partition('=')[0])
    params = (cls.get_schema() or {}).get('query_params') or {}
    return sorted(knobs | {key for key in params if key in ('top', 'limit')})


def _own_cap_uris(scheme):
    return [FIXTURE_URIS[scheme].replace('://proj', '://wide')] + OWN_CAP_URIS.get(scheme, [])


def _lists(obj, path=()):
    """(path, list) for every list in a result, two dict levels deep, meta excluded."""
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key == 'meta':
                continue
            if isinstance(value, list):
                yield path + (key,), value
            elif isinstance(value, dict) and len(path) < 2:
                yield from _lists(value, path + (key,))


def _knob_cuts(harness, scheme):
    """{'<view>?<knob>=1': ([shortened list paths], cut result)}, each view with each knob
    at 1 vs uncapped."""
    harness.fixture_uri(scheme)  # the same skips as the proj/ runs
    cuts = {}
    for uri in _own_cap_uris(scheme):
        sep = '&' if '?' in uri else '?'
        for knob in _cap_knobs(scheme):
            _, full, _ = harness.run(f'{uri}{sep}{knob}=1000000')
            _, cut, _ = harness.run(f'{uri}{sep}{knob}=1')
            whole, part = dict(_lists(full)), dict(_lists(cut))
            cuts[f'{uri}{sep}{knob}=1'] = (
                sorted(p for p, v in whole.items() if p in part and len(part[p]) < len(v)), cut)
    return cuts


@pytest.mark.parametrize('scheme', _cases('own_cap', sorted(
    s for s in FIXTURE_URIS if _cap_knobs(s))))
def test_an_adapters_own_cap_is_disclosed(harness, scheme):
    hidden = {}
    for run, (shortened, cut) in _knob_cuts(harness, scheme).items():
        disclosed = {entry.get('field') for entry in truncations_of(cut)}
        missed = ['.'.join(path) for path in shortened if path[-1] not in disclosed]
        if missed:
            hidden[run] = missed
    assert not hidden, (
        f'cut without saying so: {hidden}. Record it with note_truncation '
        f'(reveal/utils/results.py), or compose(..., cut_as=...)')


def test_the_own_cap_invariant_bites(harness):
    """Positive control: on wide/ a knob at 1 really cuts these adapters' lists, so
    test_an_adapters_own_cap_is_disclosed is not vacuously green."""
    expected = ['ast', 'calls', 'depends', 'git', 'hotspots', 'imports', 'json', 'overview',
                'patches', 'stats', 'xlsx']
    bitten = [scheme for scheme in sorted(s for s in FIXTURE_URIS if _cap_knobs(s))
              if any(shortened for shortened, _ in _knob_cuts(harness, scheme).values())]
    assert bitten == expected

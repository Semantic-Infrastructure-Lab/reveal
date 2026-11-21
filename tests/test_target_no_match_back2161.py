"""A parameter that names a target exits 2 when the target matches nothing (surface plan, rule 9; BACK-2161).

Driven from the declared parameter specs: every spec that says it names a file is run with a value
that matches nothing, in both spellings. imports://<dir>?importers=<name> used to resolve the name
against the requested directory only, so a name that missed fell through to the directory summary
and printed a clean zero with exit 0.
"""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.cli.invocation import COMMANDS
from reveal.cli.routing.declared import declared_adapter_class

# Parameters that name a target by this project's own convention; each must declare what it names, so
# a new one cannot be added without joining the no-match check.
TARGET_PARAM_NAMES = frozenset({'importers', 'imports', 'callers', 'callees'})


def target_specs():
    for noun in sorted(COMMANDS):
        cls = declared_adapter_class(noun)
        for spec in getattr(cls, 'PARAM_SPECS', ()):
            yield noun, spec


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    (root / 'pkg').mkdir(parents=True)
    (root / 'pyproject.toml').write_text('[project]\nname = "proj"\n', encoding='utf-8')
    (root / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    (root / 'pkg' / 'a.py').write_text('X = 1\n', encoding='utf-8')
    (root / 'pkg' / 'b.py').write_text('from pkg import a\n', encoding='utf-8')
    (root / 'pkg' / 'c.py').write_text('from pkg import a\n', encoding='utf-8')
    return root


def test_every_target_naming_parameter_declares_what_it_names():
    # A boolean switch names nothing (Overview's imports on|off, BACK-2622), whatever its name.
    undeclared = [f'{noun}:{spec.name}' for noun, spec in target_specs()
                  if spec.name in TARGET_PARAM_NAMES and spec.names is None and spec.type != 'boolean']
    assert not undeclared, f'declare ParamSpec(names=...) on {undeclared}'


@pytest.mark.parametrize('bogus', ['nope.py', 'pkg/nope.py', 'pkg.a'])
def test_a_file_target_that_matches_nothing_exits_2(project, bogus):
    declared = [(noun, spec) for noun, spec in target_specs() if spec.names == 'file']
    assert declared, 'no spec declares names="file"'
    for noun, spec in declared:
        for argv in ([f'{noun}://proj/pkg?{spec.name}={bogus}'], [noun, 'proj/pkg', f'--{spec.name}', bogus]):
            result = _run_reveal_direct(*argv, '--no-gitignore', '--format', 'json')
            assert result.returncode == 2, (argv, result.stdout, result.stderr)
            assert bogus in result.stderr
            assert 'matched no file' in result.stderr


def test_all_spellings_of_one_file_give_the_same_importers(project):
    """Relative to the requested directory, and relative to the scan root: the same file, one answer."""
    answers = []
    for named in ('a.py', 'pkg/a.py', 'proj/pkg/a.py'):
        out = _run_reveal_direct(f'imports://proj/pkg?importers={named}', '--no-gitignore', '--format', 'json')
        data = json.loads(out.stdout)
        answers.append(sorted(row['file'] for row in data['importers']))
    assert all(answer == answers[0] for answer in answers) and len(answers[0]) == 2


def test_a_real_file_with_no_importers_is_still_a_zero(project):
    """Negative control: the file exists and nothing imports it, so the clean zero stays honest."""
    out = _run_reveal_direct('imports://proj/pkg?importers=b.py', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0
    assert json.loads(out.stdout)['importers'] == []


KNOWN_GAPS: dict = {}


def _symbol_rows():
    for noun, param in sorted({(n, s.name) for n, s in target_specs() if s.names == 'symbol'}):
        gap = KNOWN_GAPS.get((noun, param))
        yield pytest.param(noun, param, marks=pytest.mark.xfail(strict=True, reason=gap) if gap else ())


@pytest.mark.parametrize('noun,param', list(_symbol_rows()))
def test_a_symbol_target_that_matches_nothing_exits_2(project, noun, param):
    """The contract already held for calls; this pins it so the declaration cannot drift from it."""
    result = _run_reveal_direct(f'{noun}://proj?{param}=no_such_symbol_zz', '--no-gitignore', '--format', 'json')
    assert result.returncode == 2, (noun, param, result.stdout, result.stderr)


def test_a_defined_root_with_no_calls_is_still_a_zero(project):
    """Negative control (BACK-2167): the retired calls ?root= alias exits 2 only for an absent name."""
    (project / 'pkg' / 'leaf.py').write_text('def leaf():\n    return 1\n', encoding='utf-8')
    out = _run_reveal_direct('calls://proj?root=leaf', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert json.loads(out.stdout)['total_edges'] == 0


@pytest.mark.parametrize('uri', [False, True])
@pytest.mark.parametrize('named', ['storage.py', 'src/storage.py'])
def test_cwd_and_requested_spellings_without_a_manifest(tmp_path, monkeypatch, uri, named):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'src').mkdir()
    (tmp_path / 'src/storage.py').write_text('VALUE = 1\n', encoding='utf-8')
    (tmp_path / 'src/app.py').write_text('import storage\n', encoding='utf-8')
    argv = [f'imports://src/?importers={named}'] if uri else ['imports', 'src', '--importers', named]
    out = _run_reveal_direct(*argv, '--format', 'json')
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert [r['file'] for r in json.loads(out.stdout)['importers']] == ['app.py']


@pytest.mark.parametrize('uri', [False, True])
def test_cwd_and_requested_candidates_are_ambiguous(project, uri):
    (project / 'pkg/proj/pkg').mkdir(parents=True)
    (project / 'pkg/proj/pkg/a.py').write_text('X = 2\n', encoding='utf-8')
    argv = ['imports://proj/pkg?importers=proj/pkg/a.py'] if uri else ['imports', 'proj/pkg', '--importers', 'proj/pkg/a.py']
    out = _run_reveal_direct(*argv)
    assert out.returncode == 2, (out.stdout, out.stderr)
    assert 'ambiguous' in out.stderr
    assert 'proj/pkg/a.py and a.py' in out.stderr


def test_cwd_candidate_outside_scan_root_does_not_shadow_target(project, tmp_path):
    (tmp_path / 'a.py').write_text('X = 2\n', encoding='utf-8')
    out = _run_reveal_direct('imports', 'proj/pkg', '--importers', 'a.py', '--format', 'json')
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert len(json.loads(out.stdout)['importers']) == 2


def test_missing_target_error_names_requested_directory(project):
    out = _run_reveal_direct('imports', 'proj/pkg', '--importers', 'absent.py')
    assert out.returncode == 2
    assert 'requested directory (proj/pkg)' in out.stderr


@pytest.mark.parametrize('named', ['leaf.py', 'pkg/leaf.py', 'proj/pkg/leaf.py'])
def test_calls_file_qualified_symbol_accepts_each_spelling(project, named):
    (project / 'pkg/leaf.py').write_text('def leaf():\n    return print(1)\n', encoding='utf-8')
    out = _run_reveal_direct('calls', 'proj/pkg', '--callees', f'{named}:leaf', '--format', 'json')
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert len(json.loads(out.stdout)['matches']) == 1


@pytest.mark.parametrize('named', ['target.md', 'pkg/target.md', 'proj/pkg/target.md'])
def test_markdown_backlinks_accepts_each_spelling(project, named):
    (project / 'pkg/target.md').write_text('# Target\n', encoding='utf-8')
    (project / 'pkg/source.md').write_text('[Target](target.md)\n', encoding='utf-8')
    out = _run_reveal_direct(f'markdown://proj/?backlinks={named}', '--format', 'json')
    assert out.returncode == 0, (out.stdout, out.stderr)
    assert json.loads(out.stdout)['linked_by'] == ['pkg/source.md']


@pytest.mark.parametrize('noun', ['calls', 'calls-root', 'markdown'])
def test_file_qualified_controls_reject_two_distinct_path_candidates(project, noun):
    (project / 'pkg/proj/pkg').mkdir(parents=True)
    if noun.startswith('calls'):
        for name in ('pkg/leaf.py', 'pkg/proj/pkg/leaf.py'):
            (project / name).write_text('def leaf():\n    return print(1)\n', encoding='utf-8')
        argv = (['calls://proj/pkg?root=proj/pkg/leaf.py:leaf'] if noun == 'calls-root'
                else ['calls', 'proj/pkg', '--callees', 'proj/pkg/leaf.py:leaf'])
    else:
        for name in ('pkg/target.md', 'pkg/proj/pkg/target.md'):
            (project / name).write_text('# Target\n', encoding='utf-8')
        argv = ['markdown://proj/pkg?backlinks=proj/pkg/target.md']
    out = _run_reveal_direct(*argv)
    assert out.returncode == 2, (out.stdout, out.stderr)
    assert 'ambiguous' in out.stderr
    assert 'proj/pkg/' in out.stderr and ' and ' in out.stderr

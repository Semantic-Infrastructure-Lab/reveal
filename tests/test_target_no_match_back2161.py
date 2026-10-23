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
    undeclared = [f'{noun}:{spec.name}' for noun, spec in target_specs()
                  if spec.name in TARGET_PARAM_NAMES and spec.names is None]
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


def test_the_two_spellings_of_one_file_give_the_same_importers(project):
    """Relative to the requested directory, and relative to the scan root: the same file, one answer."""
    answers = []
    for named in ('a.py', 'pkg/a.py'):
        out = _run_reveal_direct(f'imports://proj/pkg?importers={named}', '--no-gitignore', '--format', 'json')
        data = json.loads(out.stdout)
        answers.append(sorted(row['file'] for row in data['importers']))
    assert answers[0] == answers[1] and len(answers[0]) == 2


def test_a_real_file_with_no_importers_is_still_a_zero(project):
    """Negative control: the file exists and nothing imports it, so the clean zero stays honest."""
    out = _run_reveal_direct('imports://proj/pkg?importers=b.py', '--no-gitignore', '--format', 'json')
    assert out.returncode == 0
    assert json.loads(out.stdout)['importers'] == []


def test_a_symbol_target_that_matches_nothing_exits_2(project):
    """The contract already held for calls; this pins it so the declaration cannot drift from it."""
    declared = [(noun, spec) for noun, spec in target_specs() if spec.names == 'symbol']
    assert declared, 'no spec declares names="symbol"'
    for noun, spec in declared:
        result = _run_reveal_direct(f'{noun}://proj?{spec.name}=no_such_symbol_zz', '--no-gitignore',
                                    '--format', 'json')
        assert result.returncode == 2, (noun, spec.name, result.stdout, result.stderr)

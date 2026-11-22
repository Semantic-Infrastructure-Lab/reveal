"""Global --verbose on the declared nouns (BACK-2654 rule 4, COMMAND_MODEL "Detail", amended by note #17).

``--verbose`` is ``--detail full`` with its replaced-by note. Where a noun's ``verbose`` only lifts its caps
(Overview, Architecture, Hotspots, Testability, Deps) it is not detail: the noun declares ``verbose`` as a legacy word
of the control that lifts them, translated because the answers are identical (rule 16, proven below on a fixture whose
caps bind, in JSON and text, on the URI and the subcommand). One declared path carries the global flag: no noun binds
it through ``CLI_QUERY_FLAGS`` or a ``cli_flags`` opt-in.
"""
import json

import pytest

from conftest import _run_reveal_direct, without_retirement_notes
from reveal.adapters.base import get_adapter_class
from reveal.cli.invocation import COMMANDS, RETIREMENTS
from reveal.cli.routing.declared import declared_adapter_class
from reveal.defaults import UNLIMITED_TOP

NOUNS = ('architecture', 'ast', 'calls', 'claude', 'codex', 'contracts', 'deps', 'git', 'hotspots', 'imports', 'json',
         'markdown', 'metrics', 'overview', 'pack', 'patches', 'surface', 'testability', 'trace')


def _adapter(noun):
    return declared_adapter_class(noun) if noun in COMMANDS else get_adapter_class(noun)


def test_one_declared_path_carries_the_global_verbose():
    for noun in NOUNS:
        adapter = _adapter(noun)
        assert 'verbose' not in (getattr(adapter, 'CLI_QUERY_FLAGS', None) or {}), noun
        for spec in adapter.PARAM_SPECS:
            assert 'verbose' not in dict(spec.cli_flags), (noun, spec.name)
    row = RETIREMENTS['flag:--verbose']
    assert row.stage == 'note' and row.replacement.startswith('--detail full')


# (noun, the control declaring the legacy word verbose, what verbose=true translates to)
OWNERS = [('imports', 'detail', 'full'), ('git', 'detail', 'full'), ('pack', 'detail', 'full'),
          ('overview', 'all', True), ('architecture', 'all', True),
          ('hotspots', 'limit', 0), ('testability', 'limit', 0), ('deps', 'top', 0)]  # limit is their cap (BACK-2673)


@pytest.mark.parametrize('noun,owner,value', OWNERS)
def test_verbose_is_declared_once_on_the_control_it_stands_for(noun, owner, value):
    specs = _adapter(noun).PARAM_SPECS
    owners = [spec for spec in specs if 'verbose' in spec.spellings]
    assert [spec.name for spec in owners] == [owner]
    assert owners[0].canonical_value('verbose', 'true') == value
    assert f'param:{noun}.verbose' in RETIREMENTS


# --- rule 16 parity: verbose answers as the uncapping control, on a fixture where the caps bind ----------------

N = 25


@pytest.fixture
def capped(tmp_path, monkeypatch):
    """25 chained modules, each with a complexity-13 function, and 25 mock targets patched three times each: more
    rows than every default cap (overview 5, hotspots 10, deps 10, testability 20)."""
    monkeypatch.chdir(tmp_path)
    root = tmp_path / 'proj'
    (root / 'pkg').mkdir(parents=True)
    (root / 'tests').mkdir()
    (root / 'pkg' / '__init__.py').write_text('', encoding='utf-8')
    for i in range(N):
        body = '\n'.join(f'    if x == {k}:\n        return {k}' for k in range(12))
        imported = f'from pkg import mod{i - 1}\n' if i else ''
        (root / 'pkg' / f'mod{i}.py').write_text(f'{imported}import os\n\n\ndef work{i}(x):\n{body}\n    return os.sep\n',
                                                 encoding='utf-8')
    tests = ['from unittest import mock\n']
    tests += [f"@mock.patch('pkg.mod{i}.work{i}')\ndef test_{i}_{j}(m):\n    assert m\n\n"
              for i in range(N) for j in range(3)]
    (root / 'tests' / 'test_all.py').write_text('\n'.join(tests), encoding='utf-8')
    return 'proj'


def _json(*argv):
    result = _run_reveal_direct(*argv, '--format', 'json')
    return result.returncode, without_retirement_notes(json.loads(result.stdout))


def _text(*argv):
    result = _run_reveal_direct(*argv)
    return result.returncode, result.stdout


CANONICAL = {'overview': '?all=true', 'architecture': '?all=true', 'hotspots': '?top=0', 'testability': '?top=0',
             'deps': '?top=0'}


@pytest.mark.parametrize('noun', sorted(CANONICAL))
@pytest.mark.parametrize('form', ['URI --verbose', 'URI ?verbose=true', 'subcommand --verbose'])
def test_a_capping_nouns_verbose_answers_as_its_uncapping_control(capped, noun, form):
    legacy = {'URI --verbose': [f'{noun}://{capped}', '--verbose'],
              'URI ?verbose=true': [f'{noun}://{capped}?verbose=true'],
              'subcommand --verbose': [noun, capped, '--verbose']}[form]
    canonical = [f'{noun}://{capped}{CANONICAL[noun]}']
    assert _text(*canonical) != _text(f'{noun}://{capped}'), 'positive control: the default caps must bind here'
    assert _json(*legacy) == _json(*canonical)
    assert _text(*legacy) == _text(*canonical)


def test_verbose_and_a_different_cap_conflict(capped):
    result = _run_reveal_direct(f'hotspots://{capped}?top=3', '--verbose')
    assert result.returncode == 2 and 'verbose' in result.stderr and 'top' in result.stderr


# --- Caps row: 0 is uncapped on every noun (manager ruling at the L1b hand-over, epic-sorcerer-1116) -------------

@pytest.mark.parametrize('zero', [['deps://{}?top=0'], ['deps', '{}', '--top', '0']], ids=['URI', 'subcommand'])
def test_deps_top_zero_is_uncapped(capped, zero):
    """deps' ``top=0`` is the uncapped answer (it used to show no text entries), the same as a top above every
    section and as ``--all``; the default cap binds on this fixture."""
    zero = [part.format(capped) for part in zero]
    uncapped = [f'deps://{capped}?top={UNLIMITED_TOP}']
    assert _text(*uncapped) != _text(f'deps://{capped}'), 'positive control: the default cap must bind here'
    assert _text(f'deps://{capped}', '--all') == _text(*uncapped)
    assert _json(*zero) == _json(*uncapped)
    assert _text(*zero) == _text(*uncapped)
    top = next(spec for spec in _adapter('deps').PARAM_SPECS if spec.name == 'top')
    assert top.zero_policy == 'all', 'the declaration says what zero means; the schema shows it'


def test_deps_verbose_and_an_equal_top_answer_once(capped):
    """verbose is top=0 on deps: beside --top 0 it is one value, beside another top it conflicts (rule 1)."""
    once = _run_reveal_direct('deps', capped, '--top', '0', '--verbose')
    assert once.returncode == 0, once.stderr
    assert once.stdout == _text(f'deps://{capped}?top=0')[1]
    conflict = _run_reveal_direct('deps', capped, '--top', '3', '--verbose')
    assert conflict.returncode == 2 and 'top' in conflict.stderr and 'verbose' in conflict.stderr


@pytest.fixture
def surfaced(tmp_path, monkeypatch):
    """Three environment-variable reads in three directories: more entries and directories than a one-row cap."""
    monkeypatch.chdir(tmp_path)
    for i in range(3):
        (tmp_path / 'sproj' / f'd{i}').mkdir(parents=True)
        (tmp_path / 'sproj' / f'd{i}' / f'm{i}.py').write_text(f'import os\n\n\ndef f{i}():\n    return os.getenv("VAR_{i}")\n',
                                                    encoding='utf-8')
    return 'sproj'


@pytest.mark.parametrize('by', ['', 'by=dir&'])
@pytest.mark.parametrize('form', ['URI', 'subcommand'])
def test_surface_top_zero_is_uncapped(surfaced, by, form):
    """surface's ``top=0`` is the uncapped answer, its default (it used to show no text entries)."""
    default = [f'surface://{surfaced}?{by}'.rstrip('?&')]
    zero = {'URI': [f'surface://{surfaced}?{by}top=0'],
            'subcommand': ['surface', surfaced, *(['--by', 'dir'] if by else []), '--top', '0']}[form]
    capped = _text(f'surface://{surfaced}?{by}top=1')
    assert capped != _text(*default) and '2 more' in capped[1], 'positive control: a cap must bind here'
    assert _json(*zero) == _json(*default)
    assert _text(*zero) == _text(*default)
    top = next(spec for spec in _adapter('surface').PARAM_SPECS if spec.name == 'top')
    assert top.zero_policy == 'all', 'the declaration says what zero means; the schema shows it'

# --- Pack: detail=full is its per-file breakdown, keeping the JSON verbose key ------------------------------------

def test_pack_detail_full_is_its_breakdown(capped):
    rc, full = _json(f'pack://{capped}?detail=full')
    assert rc == 0 and full.get('verbose') is True
    assert _json(f'pack://{capped}', '--verbose') == (rc, full) == _json('pack', capped, '--detail', 'full')
    rc, normal = _json(f'pack://{capped}?detail=normal')
    assert rc == 0 and 'verbose' not in normal and _json(f'pack://{capped}') == (rc, normal)


# --- a detail noun: --verbose is detail=full with the note; one without full exits 2 --------------------------------

@pytest.fixture
def claude_home(tmp_path, monkeypatch):
    from claude_session_fixture import build_claude_home
    adapter = declared_adapter_class('claude')
    home = build_claude_home(tmp_path / 'home')
    monkeypatch.setattr(adapter, 'CLAUDE_HOME', home)
    monkeypatch.setattr(adapter, 'CONVERSATION_BASE', home / 'projects')


@pytest.mark.parametrize('resource', ['session/my-session/messages', 'session/my-session/message/1',
                                      'session/my-session/exchanges'])
def test_claude_verbose_is_detail_full(claude_home, resource):
    verbose = _run_reveal_direct(f'claude://{resource}', '--verbose', '--format', 'json')
    doc = json.loads(verbose.stdout)
    assert 'flag:--verbose' in [w['field'] for w in doc['meta']['warnings'] if w['code'] == 'retired_spelling']
    assert (verbose.returncode, without_retirement_notes(doc)) == _json(f'claude://{resource}?detail=full')
    text = _run_reveal_direct(f'claude://{resource}', '--verbose')
    assert text.stderr.count(f"note: {RETIREMENTS['flag:--verbose'].text}") == 1
    assert text.stdout == _text(f'claude://{resource}?detail=full')[1]


def test_claude_verbose_on_a_view_without_full_exits_2(claude_home):
    result = _run_reveal_direct('claude://session/my-session', '--verbose')
    assert result.returncode == 2 and 'detail' in result.stderr


def test_verbose_conflicts_with_a_different_detail(claude_home):
    result = _run_reveal_direct('claude://session/my-session/messages?detail=summary', '--verbose')
    assert result.returncode == 2 and '--verbose' in result.stderr and 'detail' in result.stderr


def test_a_noun_without_detail_names_it(capped):
    result = _run_reveal_direct(f'surface://{capped}', '--verbose')
    assert result.returncode == 2 and "'detail'" in result.stderr and 'supported controls' in result.stderr


def test_an_undeclared_scheme_keeps_its_own_verbose(tmp_path, monkeypatch):
    """Negative control: a scheme with no declarations is not a noun; --verbose stays its own business. env:// is
    declared since BACK-2626 and refuses it naming detail, as every noun without one does."""
    result = _run_reveal_direct('reveal://', '--verbose')
    assert result.returncode == 0 and 'detail' not in result.stderr
    monkeypatch.setenv('REVEAL_VERBOSE_PROBE', 'x')
    declared = _run_reveal_direct('env://REVEAL_VERBOSE_PROBE', '--verbose')
    assert declared.returncode == 2 and "'detail'" in declared.stderr

"""BACK-2729: the global ``--all`` binds the value ``--limit 0`` binds (Scott 2026-11-20, BACK-2622 note #3).

``--all`` is the shared uncapping word, and COMMAND_MODEL "Conflicting values" accepts equal values once, so
``--all --limit 0`` is one setting. The one owner both request forms read, ``flag_specs.declared_flag_fragment``,
gives ``--all`` its cap at the value that cap reads as every row: ``0`` where its zero uncaps, the noun's declared
value otherwise.
"""
import json

import pytest

from conftest import _run_reveal_in
from reveal.adapters.base import get_adapter_class
from reveal.cli.routing.flag_specs import FLAG_SPECS, declared_flag_fragment

ALL = next(spec for spec in FLAG_SPECS if spec.dest == 'all')


@pytest.mark.parametrize('noun,selection,fragment', [
    ('ast', '', 'limit=0'), ('git', '', 'limit=0'), ('calls', 'sort=-callers', 'limit=0'), ('metrics', '', 'limit=0'),
    ('metrics', 'view=hotspots', 'limit=0'), ('metrics', 'hotspots=true', 'top=0'), ('patches', '', 'limit=0'),
    ('hotspots', '', 'limit=0'), ('testability', '', 'limit=0'),  # testability's zero is all since ruling S4 (BACK-2774)
])
def test_all_binds_the_uncapping_zero(noun, selection, fragment):
    assert declared_flag_fragment(ALL, get_adapter_class(noun), selection) == fragment


@pytest.mark.parametrize('noun,selection,fragment', [
    # not a cap value: overview's own all switch
    ('overview', '', 'all=true'),
    # no cap the selected answer reads: satisfied quietly
    ('imports', 'sort=-fan-in', None), ('markdown', '', None),
])
def test_all_controls(noun, selection, fragment):
    assert declared_flag_fragment(ALL, get_adapter_class(noun), selection) == fragment


@pytest.fixture
def tree(tmp_path):
    pkg = tmp_path / 'pkg'
    pkg.mkdir()
    (pkg / 'a.py').write_text(''.join(f'import mod_{i}\n' for i in range(3))
                              + ''.join(f'def f_{i}():\n    return f_{i + 1}()\n\n' for i in range(30)), encoding='utf-8')
    return tmp_path


def _answer(tree, *argv):
    result = _run_reveal_in(tree, *argv, '--format', 'json')
    return result.returncode, json.loads(result.stdout), result.stderr


@pytest.mark.parametrize('request_', [
    ['imports', 'pkg', '--sort=-fan-in'], ['overview', 'pkg'], ['metrics', 'pkg'], ['calls', 'pkg', '--sort=-callers'],
])
def test_all_with_limit_0_answers_as_limit_0(tree, request_):
    _, zero, _ = _answer(tree, *request_, '--limit', '0')
    code, both, err = _answer(tree, *request_, '--all', '--limit', '0')
    assert code == 0, err
    assert both == zero


@pytest.mark.parametrize('request_', [['ast', 'pkg'], ['metrics', 'pkg'], ['calls', 'pkg', '--sort=-callers']])
def test_all_with_a_different_limit_still_conflicts(tree, request_):
    code, _, err = _answer(tree, *request_, '--all', '--limit', '2')
    assert code == 2 and '--all' in err and '--limit' in err

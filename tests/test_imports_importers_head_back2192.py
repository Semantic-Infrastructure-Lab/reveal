"""``--head``/``--tail`` cut the module rows of ``imports://DIR?importers`` and disclose the cut (BACK-2192).

``calls ?modules`` printed every edge (swift: 660,716 edges, 150 MB of JSON) and the retired
spelling gets no cap of its own; the bound on ``?importers`` is the generic row control. Before
this, ``--head`` answered "no list to slice" and ``limit=`` was an unknown parameter.
"""
import json
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

pytestmark = [pytest.mark.component]


@pytest.fixture
def mesh(tmp_path):
    """Five modules that each import the other four: five rows, twenty edges."""
    root = tmp_path / 'mesh'
    root.mkdir()
    for i in range(1, 6):
        lines = [f'import m{j}' for j in range(1, 6) if j != i] or ['X = 1']
        (root / f'm{i}.py').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return root


def _json(result):
    return json.loads(result.stdout)


def test_unbounded_importers_lists_every_module(mesh):
    doc = _json(_run_reveal_direct(f'imports://{mesh}?importers&scope=path', '--format', 'json'))
    assert len(doc['entries']) == doc['total'] == 5


@pytest.mark.parametrize('flag,expected', [(('--head', '2'), ['m1.py', 'm2.py']), (('--tail', '1'), ['m5.py'])])
def test_head_and_tail_cut_the_rows_and_say_so(mesh, flag, expected):
    result = _run_reveal_direct(f'imports://{mesh}?importers&scope=path', *flag, '--format', 'json')
    assert result.returncode == 0, result.stderr
    doc = _json(result)
    assert [e['file'] for e in doc['entries']] == expected
    assert doc['total'] == 5
    assert any(w['type'] == 'truncated' for w in doc['meta']['warnings'])
    assert 'no effect' not in result.stderr

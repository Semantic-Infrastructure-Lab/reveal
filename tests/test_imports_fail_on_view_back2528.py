"""imports --fail-on findings is refused on a view with no findings verdict (BACK-2528).

The findings views (--circular, --unused, --violations) gate: exit 1 when the answer has a row. The
default summary, --rank fan-in, --entrypoints, --components, --external and --importers have no verdict,
so --fail-on findings there exited 0 whatever the code held: a CI run that forgot --circular passed.
"""
import json

import pytest

from conftest import _run_reveal_direct as run


@pytest.fixture
def cyclic(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    pkg = tmp_path / 'proj' / 'pkg'
    pkg.mkdir(parents=True)
    (tmp_path / 'proj' / 'pyproject.toml').write_text('[project]\nname = "proj"\n', encoding='utf-8')
    (pkg / '__init__.py').write_text('', encoding='utf-8')
    (pkg / 'a.py').write_text('from pkg import b\n', encoding='utf-8')
    (pkg / 'b.py').write_text('from pkg import a\n', encoding='utf-8')
    return tmp_path


@pytest.mark.parametrize('argv', [
    ['imports', 'proj/pkg'],
    ['imports://proj/pkg'],
    ['imports', 'proj/pkg', '--rank', 'fan-in'],
    ['imports://proj/pkg?entrypoints'],
    ['imports://proj/pkg?components'],
    ['imports://proj/pkg?importers=a.py&circular'],  # ?importers wins over the findings views
])
def test_a_view_with_no_verdict_refuses_the_gate(cyclic, argv):
    result = run(*argv, '--fail-on', 'findings', '--no-gitignore', '--format', 'json')
    assert result.returncode == 2, (result.stdout, result.stderr)
    assert 'imports gates --circular, --unused and --violations' in json.loads(result.stdout)['error']


@pytest.mark.parametrize('argv', [
    ['imports', 'proj/pkg', '--circular'],
    ['imports://proj/pkg?circular'],
])
def test_a_findings_view_still_gates(cyclic, argv):
    """Positive control: the cycle a <-> b is a finding, exit 1."""
    result = run(*argv, '--fail-on', 'findings', '--no-gitignore')
    assert result.returncode == 1, (result.stdout, result.stderr)


def test_without_the_gate_every_view_answers(cyclic):
    result = run('imports', 'proj/pkg', '--no-gitignore')
    assert result.returncode == 0, result.stderr

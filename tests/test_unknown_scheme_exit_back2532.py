"""BACK-2532: an unknown URI scheme is an invalid invocation (D6 exit 2), and the hint teaches
only current schemes, never a spelling the RETIREMENTS table retires."""
import pytest

from conftest import _run_reveal_direct
from reveal.cli.invocation import RETIREMENTS

pytestmark = pytest.mark.component

RETIRED = sorted(key.split(':', 1)[1] for key in RETIREMENTS if key.startswith('scheme:'))


def _listed(stderr):
    line = next(l for l in stderr.splitlines() if l.startswith('Supported schemes:'))
    return {s.strip().removesuffix('://') for s in line.split(':', 1)[1].split(',')}


def test_unknown_scheme_exits_2_and_lists_only_current_schemes():
    result = _run_reveal_direct('nosuchscheme://x')
    assert result.returncode == 2, result.stderr
    assert 'Unsupported URI scheme: nosuchscheme://' in result.stderr
    listed = _listed(result.stderr)
    assert {'ast', 'calls', 'imports', 'metrics', 'overview'} <= listed  # positive control
    assert not listed & set(RETIRED), sorted(listed & set(RETIRED))


def test_retired_list_is_not_empty():
    # Guards the negative assertion above against a renamed table key.
    assert {'architecture', 'hotspots', 'stats'} <= set(RETIRED)


def test_api_query_hint_lists_only_current_schemes():
    from reveal.api import query
    with pytest.raises(ValueError) as caught:
        query('nosuchscheme://x')
    line = next(l for l in str(caught.value).splitlines() if l.startswith('Supported schemes:'))
    listed = {s.strip().removesuffix('://') for s in line.split(':', 1)[1].split(',')}
    assert 'ast' in listed and not listed & set(RETIRED)


def test_retired_scheme_still_answers_with_its_note(tmp_path):
    # Not part of the fix: a retired scheme keeps running with its note until the cut (D5).
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    result = _run_reveal_direct(f'stats://{tmp_path}')
    assert result.returncode == 0 and 'deprecated' in result.stderr

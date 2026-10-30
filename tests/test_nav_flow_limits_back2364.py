"""Recognition limits remain visible without expanding navigation extraction."""
import json

import pytest

from conftest import _run_reveal_direct
from test_conformance_matrix import EXPECTED, _sample_path

pytestmark = pytest.mark.component


@pytest.mark.parametrize('language', ['rust', 'zig', 'cpp'])
def test_recognized_skeleton_discloses_nonexhaustive_exit_forms(language):
    path = _sample_path(language)
    element = EXPECTED[language]['entry_function']
    result = _run_reveal_direct(path, element, '--outline', '--format', 'json')
    assert result.returncode == 0, result.stderr
    answer = json.loads(result.stdout)
    assert answer['meta']['depth_limited'] is False
    assert answer['meta']['structure_scope'] == {
        'rule': 'Recognized structural nodes; exit expressions may be omitted.',
        'exit_sites': 'Inspect --exits for candidate exit sites.',
    }


def test_literal_region_discloses_resolved_scope_only_implicit_tails():
    path = _sample_path('rust')
    named = _run_reveal_direct(path, 'process_order', '--returns', '--format', 'json')
    region = _run_reveal_direct(path, ':13-20', '--returns', '--format', 'json')
    named_answer, region_answer = json.loads(named.stdout), json.loads(region.stdout)
    # These independently expected source populations remain deliberately distinct.
    assert [row['line'] for row in named_answer['findings']] == [14, 16, 19]
    assert [row['line'] for row in region_answer['findings']] == [14, 16]
    assert region_answer['meta']['exit_scope']['mode'] == 'source_scope'
    assert region_answer['meta']['exit_scope']['implicit_tail_rule'] == (
        'Implicit tail returns are inferred only for the resolved scope, '
        'not for nested callable scopes.'
    )


def test_text_discloses_recognition_and_literal_tail_limits():
    path = _sample_path('rust')
    skeleton = _run_reveal_direct(path, 'process_order', '--outline')
    region = _run_reveal_direct(path, ':13-20', '--returns')
    assert 'Skeleton scope: Recognized structural nodes; exit expressions may be omitted.' in skeleton.stdout
    assert 'Implicit tail returns are inferred only for the resolved scope' in region.stdout


def test_file_outline_keeps_its_structural_domain():
    result = _run_reveal_direct(_sample_path('rust'), '--outline', '--format', 'json')
    assert result.returncode == 0, result.stderr
    assert 'structure_scope' not in json.loads(result.stdout).get('meta', {})

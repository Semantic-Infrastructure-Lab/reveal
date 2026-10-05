"""Pure text bodies leave format, warnings and failure emission to one seam."""
from argparse import Namespace

import pytest
from dataclasses import FrozenInstanceError

from reveal.adapters.patches import PatchesAdapter, PatchesRenderer
from reveal.cli.routing.uri import _emit_result, resolve_uri
from reveal.rendering.base import RenderOptions, capped_section

pytestmark = pytest.mark.component


def fixture_result(tmp_path):
    path = tmp_path / 'test_demo.py'
    path.write_text('from unittest.mock import patch\n@patch("service.call")\ndef test_call(mock):\n    pass\n', encoding='utf-8')
    return PatchesAdapter(str(tmp_path)).get_structure()


def test_body_is_pure_and_seam_discloses_once(tmp_path, capsys):
    result = fixture_result(tmp_path)
    body = PatchesRenderer.render_structure(result)
    assert isinstance(body, str) and 'service.call' in body
    assert not capsys.readouterr().out
    result['meta']['errors'] = [{'message': 'recorded partial scan'}]
    _emit_result(result, Namespace(format='text', also_json=None), 'patches', PatchesRenderer.render_structure)
    text = capsys.readouterr().out
    assert text.count('Patch pressure is advisory') == 1
    assert text.count('recorded partial scan') == 1


def test_real_failed_answer_emits_no_domain_body(tmp_path, capsys):
    # Router catches this adapter's actual missing-path exception.
    answer = resolve_uri(f'patches://{tmp_path / "missing"}', Namespace(format='text'))
    assert answer.result.get('error')
    assert PatchesRenderer.render_structure(answer.result) is None
    assert not capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        answer.emit()
    output = capsys.readouterr()
    assert exc.value.code == 1 and not output.out
    assert output.err.count('Error (patches://)') == 1


def test_examples_cap_is_disclosed_and_options_are_immutable(tmp_path, capsys):
    result = fixture_result(tmp_path)
    group = result['groups'][0]
    group['examples'] = [{'test_file': 'test_demo.py', 'test_name': f'test_{i}', 'line': i} for i in range(5)]
    assert '... and 2 more' in PatchesRenderer._render_text(result)
    complete = PatchesRenderer._render_text(result, RenderOptions(max_examples=None))
    assert 'test_4' in complete and 'more' not in complete
    assert not capsys.readouterr().out
    with pytest.raises(FrozenInstanceError):
        RenderOptions().max_examples = 4


def test_capped_section_zero_and_negative_control():
    assert capped_section([1, 2], 0, str) == ['    ... and 2 more']
    assert capped_section([1, 2], None, str) == ['1', '2']
    with pytest.raises(ValueError):
        capped_section([1], -1, str)

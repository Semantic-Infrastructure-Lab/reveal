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


def test_deps_body_and_seam_preserve_errors_and_cuts(tmp_path, capsys):
    from reveal.adapters.deps import DepsAdapter, DepsRenderer
    from reveal.rendering.base import emit_rendered
    (tmp_path / 'a.py').write_text('import b\nimport requests\n', encoding='utf-8')
    (tmp_path / 'b.py').write_text('import a\nimport yaml\n', encoding='utf-8')
    result = DepsAdapter(str(tmp_path)).get_structure()
    body = DepsRenderer.render_structure(result, top=1)
    assert isinstance(body, str) and '... and 1 more' in body
    assert 'Circular dependencies' in body and 'Unused imports' in body
    assert not capsys.readouterr().out
    result.setdefault('meta', {})['errors'] = [{'message': 'recorded partial dependency scan'}]
    emit_rendered(DepsRenderer.render_structure, result, 'text', top=1)
    output = capsys.readouterr().out
    assert output.count('recorded partial dependency scan') == 1
    assert output.count('Dependencies:') == 1
    # Explicit zero hides rows, retains exact remainder disclosures.
    zero = DepsRenderer.render_structure(result, top=0)
    assert '... and 2 more' in zero and 'requests ' not in zero


def test_deps_real_missing_path_is_one_failed_answer(tmp_path, capsys):
    from reveal.adapters.deps import DepsRenderer
    answer = resolve_uri(f'deps://{tmp_path / "missing"}', Namespace(format='text'))
    assert answer.result.get('error')
    assert DepsRenderer.render_structure(answer.result) is None
    assert not capsys.readouterr().out
    with pytest.raises(SystemExit) as exc:
        answer.emit()
    output = capsys.readouterr()
    assert exc.value.code == 1 and not output.out
    assert output.err.count('Error (deps://)') == 1


def test_deps_subcommand_preserves_partial_diagnostics(tmp_path, capsys):
    from functools import partial
    from reveal.adapters.deps import DepsAdapter, DepsRenderer
    from reveal.cli.routing.subcommand import emit_subcommand_result
    result = DepsAdapter(str(tmp_path)).get_structure()
    result.setdefault('meta', {})['errors'] = [{'message': 'partial deps scan'}]
    emit_subcommand_result(result, Namespace(format='text'), name='deps', source=tmp_path,
                           render=partial(DepsRenderer.render_structure, top=1))
    assert capsys.readouterr().out.count('partial deps scan') == 1


def test_shared_body_diagnostics_keep_grep_parseable(capsys):
    from reveal.rendering.base import emit_rendered
    result = {'meta': {'errors': [{'message': 'partial result'}]}}
    emit_rendered(lambda result, fmt: 'file.py:1:hit', result, 'grep')
    output = capsys.readouterr()
    assert output.out == 'file.py:1:hit\n'
    assert output.err.count('partial result') == 1


def test_contracts_returned_body_and_partial_diagnostics(tmp_path, capsys):
    from reveal.adapters.contracts import ContractsAdapter, ContractsRenderer
    from reveal.rendering.base import emit_rendered
    (tmp_path / 'api.py').write_text('from abc import ABC\nclass Service(ABC): pass\n', encoding='utf-8')
    result = ContractsAdapter(str(tmp_path)).get_structure()
    body = ContractsRenderer.render_structure(result)
    assert isinstance(body, str) and 'Service' in body
    assert not capsys.readouterr().out
    result['meta']['errors'] = [{'message': 'partial contracts scan'}]
    emit_rendered(ContractsRenderer.render_structure, result)
    output = capsys.readouterr().out
    assert output.count('partial contracts scan') == 1
    assert output.count('Contracts:') == 1


def test_contracts_missing_path_keeps_failure_details(tmp_path, capsys):
    from reveal.adapters.contracts import ContractsRenderer
    answer = resolve_uri(f'contracts://{tmp_path / "missing"}', Namespace(format='text'))
    answer.result['message'] = 'recorded contracts detail'
    answer.result['next_steps'] = ['check the source path']
    with pytest.raises(SystemExit) as exc:
        answer.emit()
    output = capsys.readouterr()
    assert exc.value.code == 1 and not output.out
    assert output.err.count('Error (contracts://)') == 1
    with pytest.raises(SystemExit):
        _emit_result(answer.result, Namespace(format='text', also_json=None),
                     'contracts', ContractsRenderer.render_structure)
    detail = capsys.readouterr()
    assert not detail.out
    assert detail.err.count('recorded contracts detail') == 1
    assert 'check the source path' in detail.err


def test_contracts_inline_notices_and_shared_errors_each_appear_once(tmp_path, capsys):
    from reveal.adapters.contracts import ContractsAdapter, ContractsRenderer
    from reveal.rendering.base import emit_rendered
    result = ContractsAdapter(str(tmp_path)).get_structure()
    result['coverage']['warning'] = 'bounded supported-language coverage'
    result['unparsed_files'] = ['missing.go']
    result['meta']['warnings'] = [
        {'code': 'W-CONTRACTS-1', 'message': result['coverage']['warning']},
        {'code': 'W-CONTRACTS-2', 'message': 'missing.go'},
        {'code': 'OTHER', 'message': 'independent warning'},
    ]
    result['meta']['errors'] = [{'message': 'partial contracts detail'}]
    emit_rendered(ContractsRenderer.render_structure, result)
    output = capsys.readouterr().out
    for text in ('bounded supported-language coverage', 'missing.go',
                 'independent warning', 'partial contracts detail'):
        assert output.count(text) == 1


def test_partial_bound_body_owned_caveats_are_not_duplicated(capsys):
    from functools import partial
    from reveal.cli.routing.subcommand import emit_subcommand_result
    from reveal.rendering.base import BaseRenderer
    from reveal.utils.warning_render import meta_warning_lines
    class InlineRenderer(BaseRenderer):
        RENDERS_META_WARNINGS = True
        @classmethod
        def _render_text(cls, result):
            return '\n'.join(meta_warning_lines(result, heading='Caveats'))
    result = {'meta': {'errors': [{'message': 'inline warning'}]}}
    emit_subcommand_result(result, Namespace(format='text'), name='demo', source='.',
                           render=partial(InlineRenderer.render_structure, format='text'))
    assert capsys.readouterr().out.count('inline warning') == 1

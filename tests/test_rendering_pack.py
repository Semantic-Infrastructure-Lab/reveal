"""Pack text shares one returned body and preserves recorded results."""
from argparse import Namespace
from functools import partial
import json

import pytest

from reveal.adapters.pack import PackAdapter
from reveal.cli.routing.subcommand import emit_subcommand_result
from reveal.cli.routing.uri import resolve_uri
from reveal.rendering.adapters.pack import PackRenderer, _format_architecture_brief
from reveal.rendering.base import emit_rendered

pytestmark = pytest.mark.component


def pack_result(tmp_path):
    (tmp_path / 'main.py').write_text('def run():\n    return 42\n', encoding='utf-8')
    return PackAdapter(str(tmp_path), 'content=true').get_structure()


def test_body_uses_recorded_content_without_reanalysis(tmp_path, monkeypatch, capsys):
    result = pack_result(tmp_path)
    result['content'][0]['content'] = 'RECORDED SNAPSHOT\n\n'
    (tmp_path / 'main.py').unlink()
    def unexpected(*args):
        pytest.fail('renderer reanalyzed a recorded result')
    monkeypatch.setattr('reveal.adapters.pack._collect_file_contents', unexpected)
    body = PackRenderer.render_structure(result)
    assert 'RECORDED SNAPSHOT\n\n' in body
    assert 'CONTENT' in body and 'main.py' in body
    assert not capsys.readouterr().out


@pytest.mark.parametrize('seam', ['uri', 'subcommand'])
def test_partial_errors_and_warnings_survive_once(tmp_path, capsys, seam):
    result = pack_result(tmp_path)
    result['meta']['errors'] = [{'message': 'partial pack scan'}]
    result['meta']['warnings'] = [{'code': 'TEST', 'message': 'recorded pack caveat'}]
    if seam == 'uri':
        emit_rendered(PackRenderer.render_structure, result)
    else:
        emit_subcommand_result(result, Namespace(format='text'), name='pack', source=tmp_path,
                               render=partial(PackRenderer.render_structure, content=True))
    output = capsys.readouterr().out
    assert output.count('partial pack scan') == 1
    assert output.count('recorded pack caveat') == 1
    assert output.count('CONTENT') == 1


@pytest.mark.parametrize('fmt', ['text', 'json'])
def test_real_missing_path_is_one_failed_answer(tmp_path, capsys, fmt):
    answer = resolve_uri(f'pack://{tmp_path / "missing"}', Namespace(format=fmt))
    assert answer.result.get('error')
    answer.result['message'] = 'recorded failure detail'
    answer.result['next_steps'] = ['check the source path']
    with pytest.raises(SystemExit) as exc:
        answer.emit()
    output = capsys.readouterr()
    assert exc.value.code == 1
    assert output.err.count('Error (pack://)') == 1
    if fmt == 'text':
        assert not output.out
    else:
        assert json.loads(output.out)['message'] == 'recorded failure detail'


def test_content_error_is_preserved_in_text_and_json(tmp_path, capsys):
    result = pack_result(tmp_path)
    result['content'][0].update(content='', error='structure analysis failed: test defect')
    assert PackRenderer.render_structure(result).count('structure analysis failed: test defect') == 1
    assert PackRenderer.render_structure(result, 'json') is None
    assert json.loads(capsys.readouterr().out)['content'][0]['error'].endswith('test defect')


@pytest.mark.parametrize('core,limit', [(True, 5), (False, 3)])
def test_architecture_hints_disclose_exact_remainders(core, limit):
    selected = [{'relative': f'file{i}.py', 'priority': 2, 'fan_in': 10 if core else 0}
                for i in range(8)]
    body = '\n'.join(_format_architecture_brief(selected))
    assert f'... and {8-limit} more' in body
    assert f'file{limit-1}.py' in body
    assert f'file{limit}.py' not in body


def test_uri_content_and_architecture_options_reach_text(tmp_path, capsys):
    (tmp_path / 'main.py').write_text('def run():\n    return 42\n', encoding='utf-8')
    answer = resolve_uri(f'pack://{tmp_path}?content=true&architecture=true', Namespace(format='text'))
    answer.emit()
    body = capsys.readouterr().out
    assert 'Architecture Hint' in body and 'CONTENT' in body and 'run' in body


def test_zero_budget_and_empty_content_are_honest(tmp_path):
    pack_result(tmp_path)
    result = PackAdapter(str(tmp_path), 'budget=0&content=true').get_structure()
    body = PackRenderer.render_structure(result)
    assert result['files'] == [] and result['meta']['skipped'] == 1
    assert 'No files fit within budget' in body
    assert result['content'] == []


@pytest.mark.parametrize('seam', ['uri', 'subcommand'])
def test_failed_renderer_preserves_details_without_domain_body(capsys, seam):
    from reveal.cli.routing.uri import _emit_result
    result = {'type': 'pack', 'error': 'source failed', 'message': 'recorded failure detail',
              'next_steps': ['check the source path']}
    with pytest.raises(SystemExit) as exc:
        if seam == 'uri':
            _emit_result(result, Namespace(format='text', also_json=None),
                         'pack', PackRenderer.render_structure)
        else:
            emit_subcommand_result(result, Namespace(format='text'), name='pack', source='src',
                                   render=PackRenderer.render_structure)
    output = capsys.readouterr()
    assert exc.value.code == 1 and not output.out
    assert output.err.count('source failed') == 1
    assert output.err.count('recorded failure detail') == 1
    assert output.err.count('check the source path') == 1

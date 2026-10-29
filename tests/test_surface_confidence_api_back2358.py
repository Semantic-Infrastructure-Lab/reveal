"""Surface omits estimates while retaining exact baseline evidence and outcomes."""
import copy
import hashlib
import json
from pathlib import PurePosixPath, PureWindowsPath

import pytest

from conftest import _run_reveal_direct as run
from reveal import api
from reveal.adapters.surface import SurfaceAdapter
from reveal.utils.results import AnalysisCompleteness
from test_surface_parse_recovery import _BROKEN
from test_surface_traversal_consumer_back2028 import fault, _project

pytestmark = pytest.mark.component

CASES = {
    'healthy': ('app.py', 'import requests\n'),
    'empty': ('app.py', 'VALUE=1\n'),
    'unsupported': ('app.lua', 'local x=1\n'),
    'parse': ('app.py', 'def broken(:\n'),
    'recovered': _BROKEN['php'],
}
# SHA256 of complete baseline3269d791 answers, normalizing only the temporary
# root and removing exactly the two confidence keys. No other field is discarded.
BASELINE = {'healthy': 'a53d0fd5c17924140cbaf6f7f480afe49dce59e9ec13dfabd92eb8204de2990f', 'empty': '75859cda56cdb49540e9b854c806cd8f685a29fe25543c987a68394d7aae0f57', 'unsupported': '37666e28b928939603201cf8434e5e6a1474239cad22b21f3410fc5c369fd77f', 'parse': '60c781588fa09819c46ac78a02f53eecb512456b97b4f5594f4676c5d517b9ec', 'recovered': '5535971ea47c863c4905b9a813bad1862ea4005b57803ff4c8377c884716b6d3'}


def _without_estimates(answer):
    answer = copy.deepcopy(answer)
    answer['meta'].pop('confidence', None)
    answer['_meta'].pop('confidence', None)
    return answer


def _digest(answer, root):
    text = json.dumps(_without_estimates(answer), sort_keys=True, ensure_ascii=False)
    for spelling in (str(root), root.as_posix()):
        text = text.replace(json.dumps(spelling, ensure_ascii=False)[1:-1], '<ROOT>')
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


def _absent(answer):
    assert 'confidence' not in answer['meta']
    assert 'confidence' not in answer['_meta']
    assert answer['meta']['parse_mode'] == 'ast+tree_sitter'
    assert answer['_meta']['analysis_kind'] == 'surface-scan'
    assert answer['_meta']['known_limits']


@pytest.mark.parametrize('case', CASES)
def test_complete_baseline_answer_survives_estimate_omission(tmp_path, case):
    name, source = CASES[case]
    (tmp_path / name).write_text(source, encoding='utf-8')
    adapter = SurfaceAdapter(str(tmp_path))
    native = adapter.get_structure()
    result = api.query(f'surface://{tmp_path}?respect_gitignore=false')
    assert result == native
    assert _digest(result, tmp_path) == BASELINE[case]
    expected = AnalysisCompleteness.INCOMPLETE if case in ('parse', 'recovered') else AnalysisCompleteness.COMPLETE
    assert adapter.execution_facts(result).completeness is expected
    _absent(result)


@pytest.mark.parametrize('stage', ['source', 'census'])
def test_loss_repair_reuse_and_siblings_keep_evidence(tmp_path, fault, stage):
    children = _project(tmp_path)
    adapter = SurfaceAdapter(str(tmp_path), 'type=env')
    clean = adapter.get_structure()
    assert clean['total'] == 2
    fault.update(stage=stage, denied=set(children))
    lost = api.query(f'surface://{tmp_path}?respect_gitignore=false', type='env')
    assert fault['events']
    assert adapter.execution_facts(lost).completeness is AnalysisCompleteness.INCOMPLETE
    assert lost['total'] == (1 if stage == 'source' else 2)
    assert any(w.get('unit') == 'directories' for w in lost['meta']['warnings'])
    _absent(lost)
    fault['denied'] = set()
    assert adapter.get_structure() == clean
    assert api.query(f'surface://{tmp_path}?respect_gitignore=false', type='env', top=0) == clean
    _absent(clean)
    sibling = api.query(f'ast://{tmp_path}?name=absent')
    assert sibling['meta']['confidence'] == 1.0


@pytest.mark.parametrize('spelling', ['noun', 'uri'])
def test_cli_json_text_and_artifact_preserve_requested_rows(tmp_path, spelling):
    _project(tmp_path)
    args = ['surface', str(tmp_path), '--type', 'env'] if spelling == 'noun' else [f'surface://{tmp_path}?type=env']
    response = run(*args, '--format', 'json', '--no-gitignore')
    assert response.returncode == 0
    result = json.loads(response.stdout)
    assert result == api.query(f'surface://{tmp_path}?respect_gitignore=false', type='env')
    assert result['total'] == 2
    _absent(result)
    artifact = tmp_path / 'answer.json'
    text_args = [*args, '--top', '0'] if spelling == 'noun' else [args[0] + '&top=0']
    text = run(*text_args, '--also-json', str(artifact), '--no-gitignore')
    assert text.returncode == 0
    assert '2 more' in text.stdout
    saved = json.loads(artifact.read_text(encoding='utf-8'))
    assert saved['surfaces'] == result['surfaces']
    _absent(saved)


def test_baseline_digest_normalizes_native_and_posix_windows_roots():
    windows = PureWindowsPath('C:/fixture/project')
    posix = PurePosixPath('/fixture/project')
    def answer(root):
        return {'meta': {'warnings': []}, '_meta': {'known_limits': ['unchanged']},
                'source': root.as_posix(), 'path': str(root),
                'nested': [str(root)]}
    assert _digest(answer(windows), windows) == _digest(answer(posix), posix)
    changed = answer(windows)
    changed['_meta']['known_limits'] = ['changed']
    assert _digest(changed, windows) != _digest(answer(posix), posix)

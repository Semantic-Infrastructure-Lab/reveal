"""A recovered parse has one warning type on every noun, and lost evidence one shared list (BACK-2664).

COMMAND_MODEL 'Degraded input' (Scott 2026-11-17): the same file tree-sitter read only through error
recovery was ``parse_recovered`` on ast:// and calls://, ``partial_parse`` on imports://, overview:// and
deps://, and ``parse_degraded`` on metrics:// and hotspots://. Metrics also called a notebook that is not
JSON ``parse_degraded`` (its analyzer's failed result sets ``_has_errors`` too), claiming recovery for a
file never parsed; hotspots named the same file twice; ``review`` exited 0 on a recovered file because
its hand-typed loss set lacked the type; calls ?modules exited 0. About a dozen nouns typed their own
loss set; they now read ``utils.results.LOST_EVIDENCE``.
"""
import json
import re
from pathlib import Path

import pytest

from conftest import _run_reveal_direct

pytestmark = pytest.mark.component

OLD_SPELLINGS = ('partial_parse', 'parse_degraded')


@pytest.fixture
def project(tmp_path):
    root = tmp_path / 'proj'
    root.mkdir()
    (root / 'ok.c').write_text('#include <stdio.h>\nint helper(int x) { return x + 1; }\n'
                               'int main(void) { return helper(2); }\n', encoding='utf-8')
    (root / 'bad.c').write_text('#include <string.h>\nint broken(int x) { return x + ; }\n'
                                'int other(void) { return broken(1); }\n', encoding='utf-8')
    return root


def _json(*args):
    result = _run_reveal_direct(*args, '--format', 'json')
    return result.returncode, json.loads(result.stdout)


def _of_type(answer, kind):
    return [w for w in answer['meta']['warnings'] if w.get('type') == kind]


@pytest.mark.parametrize('query', ['ast://{}', 'metrics://{}', 'imports://{}', 'calls://{}?rank=callers',
                                   'calls://{}?modules', 'overview://{}', 'deps://{}', 'hotspots://{}',
                                   'pack://{}?architecture=true'])
def test_every_noun_names_the_recovered_file_once_under_one_type_and_exits_3(project, query):
    code, answer = _json(query.format(project.as_posix()))
    assert code == 3, answer['meta']
    (recovered,) = _of_type(answer, 'parse_recovered')
    assert [Path(f).name for f in recovered['files']] == ['bad.c']
    assert not any(old in json.dumps(answer) for old in OLD_SPELLINGS)


def test_clean_tree_has_no_recovered_warning(project):
    """Control: the same nouns are clean once the file parses."""
    (project / 'bad.c').write_text('int broken(int x) { return x + 1; }\n', encoding='utf-8')
    for query in ('metrics://{}', 'imports://{}', 'calls://{}?modules', 'hotspots://{}'):
        code, answer = _json(query.format(project.as_posix()))
        assert code == 0 and not _of_type(answer, 'parse_recovered'), (query, answer['meta'])


def test_metrics_calls_an_unreadable_notebook_failed_not_recovered(project):
    (project / 'bad.c').unlink()
    (project / 'nb.ipynb').write_text('{not json\n', encoding='utf-8')
    code, answer = _json(f'metrics://{project.as_posix()}')
    assert code == 3
    assert not _of_type(answer, 'parse_recovered')
    (failed,) = _of_type(answer, 'analysis_failed')
    assert failed['files'] == ['nb.ipynb']
    assert 'Expecting property name' in failed['failures'][0]['reason']


def test_review_exits_3_on_a_recovered_file(project):
    result = _run_reveal_direct('review', project.as_posix(), '--format', 'json')
    assert result.returncode == 3, result.stdout[-800:]
    answer = json.loads(result.stdout)
    assert [Path(f).name for f in _of_type(answer, 'parse_recovered')[0]['files']] == ['bad.c']


def test_no_noun_hand_types_a_loss_list():
    """One list (utils.results.LOST_EVIDENCE); a second hand-typed set drifts, as about a dozen did."""
    from reveal.utils.results import LOST_EVIDENCE
    package = Path(__file__).resolve().parent.parent / 'reveal'
    named = re.compile(r"'(%s)'" % '|'.join(sorted(LOST_EVIDENCE)))
    offenders = []
    for path in sorted(package.rglob('*.py')):
        if path.name == 'results.py' and path.parent.name == 'utils':
            continue
        text = path.read_text(encoding='utf-8')
        offenders += [f'{path.relative_to(package)}: {old}' for old in OLD_SPELLINGS if f"'{old}'" in text]
        offenders += [f'{path.relative_to(package)}:{n}' for n, line in enumerate(text.split('\n'), 1)
                      if len(set(named.findall(line))) >= 2]
    assert offenders == []

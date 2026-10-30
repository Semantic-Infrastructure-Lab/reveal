"""Bound API URI resources use the declared codec without serializing bound paths."""
import json
from urllib.parse import quote

import pytest

from conftest import _run_reveal_direct as run
from reveal.api import query
from reveal.adapters.factory import _canonical_init
from reveal.adapters.overview import OverviewAdapter


@pytest.mark.parametrize('scheme', ['overview', 'surface', 'contracts'])
def test_encoded_directory_has_the_same_api_and_cli_answer(tmp_path, scheme):
    root = tmp_path / 'project Ω & %'
    root.mkdir()
    (root / 'app.py').write_text('def main():\n    return 1\n', encoding='utf-8')
    uri = f'{scheme}://{quote(root.as_posix(), safe="/:")}'
    command = run(uri, '--format', 'json')
    assert command.returncode == 0, command.stderr
    assert query(uri) == json.loads(command.stdout)


def test_encoded_question_filename_is_bound_once_and_typed_top_still_applies(tmp_path):
    path = tmp_path / 'module? & %.py'
    path.write_text('VALUE=1\n', encoding='utf-8')
    uri = f'overview://{quote(path.as_posix(), safe="/:")}'
    answer = query(uri + '?top=1', top=0)
    expected = run(uri + '?top=0', '--format', 'json')
    assert expected.returncode == 0, expected.stderr
    assert answer == json.loads(expected.stdout)
    assert answer['path'] == path.as_posix()
    assert answer['map']['components']['rows'] == []
    assert answer['map']['components']['total'] == 1


def test_existing_literal_percent_resource_wins_over_decoded_resource(tmp_path):
    for name in ('literal%20name.py', 'literal name.py'):
        (tmp_path / name).write_text('VALUE=1\n', encoding='utf-8')
    path = tmp_path / 'literal%20name.py'
    answer = query(f'overview://{path.as_posix()}', no_imports=True)
    assert answer['path'] == path.as_posix()


def test_bad_original_query_is_not_rescued_by_typed_override(tmp_path):
    path = tmp_path / 'space name.py'
    path.write_text('VALUE=1\n', encoding='utf-8')
    uri = f'overview://{quote(path.as_posix(), safe="/:")}?top=bad'
    with pytest.raises(ValueError, match='top'):
        query(uri, top=0)


def test_legacy_factory_and_already_bound_typed_paths_keep_their_spelling(tmp_path):
    class Recorder:
        RESOURCE_SPEC = OverviewAdapter.RESOURCE_SPEC
        PARAM_SPECS = OverviewAdapter.PARAM_SPECS
        CANONICAL_EMPTY_RESOURCE = '.'

        def __init__(self, resource='', query=None, *, params=None):
            self.resource, self.query, self.params = resource, query, params

    path = tmp_path / 'space name.py'
    path.write_text('VALUE=1\n', encoding='utf-8')
    encoded = quote(path.as_posix(), safe='/:')
    assert _canonical_init(Recorder, encoded).resource == encoded
    literal = str(tmp_path / 'question?name.py')
    bound = _canonical_init(Recorder, literal, params={'top': 0})
    assert bound.resource == literal and bound.params == {'top': 0}

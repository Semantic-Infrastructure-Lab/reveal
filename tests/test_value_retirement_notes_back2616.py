"""Two shared note paths a legacy spelling must reach (BACK-2616; COMMAND_MODEL "Retirement notes", D5).

1. A retired *value* of a declared control typed as its flag (``--detail summary``) notes its ``value:<noun>.<name>=<v>``
   row on the subcommand route, as the URI spelling ``?detail=summary`` does on the URI route.
2. A legacy keyword given to ``api.query`` on a resource URI with no query string (``api.query("git://f", raw=True)``)
   notes its own row: no request note will be said for that request, so the per-key note it would cover is said itself.
"""
import pytest

from reveal.cli import invocation
from reveal.cli.invocation import Invocation, Retirement, invocation_scope, noted_retirements
from reveal.cli.routing.declared import _note_retired_flags
from reveal.utils.query_parser import CliBinding, LegacySpelling, ParamSpec

DETAIL = ParamSpec('detail', 'string', 'How much', None, str, choices=('normal', 'full'),
                   legacy=(LegacySpelling('detail', value='summary'),), cli=CliBinding(('--detail',)))


class Demo:
    PARAM_SPECS = (DETAIL,)


@pytest.fixture
def value_row(monkeypatch):
    monkeypatch.setitem(invocation.RETIREMENTS, 'value:demo.detail=summary',
                        Retirement('demo --detail summary', '--detail normal'))


def flags_noted(*argv):
    with invocation_scope(Invocation.parse(['reveal', 'demo', '.', *argv]), retirements_to_stderr=False):
        _note_retired_flags('demo', Demo)
        return sorted(noted_retirements())


@pytest.mark.parametrize('argv', [('--detail', 'summary'), ('--detail=summary',)])
def test_a_retired_value_typed_as_its_flag_notes_its_value_row(value_row, argv):
    assert flags_noted(*argv) == ['value:demo.detail=summary']


def test_another_value_of_the_same_flag_notes_nothing(value_row):
    """Negative control: only the retired value has a row."""
    assert flags_noted('--detail', 'full') == []
    assert flags_noted('--detail', 'normal', 'summary') == []  # a later positional is not the flag's value


def test_a_legacy_keyword_on_a_resource_uri_without_a_query_notes_its_row(tmp_path, monkeypatch):
    pygit2 = pytest.importorskip('pygit2')
    from reveal.api import query
    repo = pygit2.init_repository(str(tmp_path))
    (tmp_path / 'a.py').write_text('def f():\n    return 1\n', encoding='utf-8')
    repo.index.add('a.py')
    repo.index.write()
    sig = pygit2.Signature('A', 'a@example.com', 1700000000, 0)
    repo.create_commit('HEAD', sig, sig, 'one', repo.index.write_tree(), [])
    monkeypatch.chdir(tmp_path)
    monkeypatch.setitem(invocation.RETIREMENTS, 'param:git.ignore', Retirement('git ?ignore=X', 'its replacement'))
    answer = query('git://a.py', view='blame', ignore='abc1234')
    assert [w['field'] for w in answer['meta']['warnings'] if w.get('code') == 'retired_spelling'] == ['param:git.ignore']
    # Control: with a query string the one request note covers the same row (BACK-2716).
    answer = query('git://a.py?view=blame', ignore='abc1234')
    assert [w['field'] for w in answer['meta']['warnings'] if w.get('code') == 'retired_spelling'] == ['request:git']

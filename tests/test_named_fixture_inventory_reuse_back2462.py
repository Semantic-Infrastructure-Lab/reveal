"""Named command inventories reuse only their own fresh fixture domain."""
import pytest

import test_example_recipes_run as recipes

pytestmark = pytest.mark.contract


def _docs(tmp_path, commands):
    (tmp_path / 'AGENT_HELP.md').write_text('```bash\n' + '\n'.join(commands) + '\n```\n', encoding='utf-8')
    return tmp_path


def _rows(params):
    return [(list(p.values), [(m.name, m.args, m.kwargs) for m in p.marks], p.id) for p in params]


def test_one_inventory_builds_domain_once_and_preserves_exact_eligibility(tmp_path, monkeypatch):
    calls = []

    def domain():
        calls.append(True)
        return {'one.py', 'two.py'}, {'HEAD'}

    monkeypatch.setattr(recipes, '_fixture_names', domain)
    docs = _docs(tmp_path, ['reveal one.py', 'reveal two.py', 'reveal missing.py',
                            'reveal one.py', 'reveal broken.py # not valid',
                            'reveal git://one.py@lost'])
    actual = _rows(recipes._named_fixture_commands(docs))
    assert actual == [
        (['reveal one.py'], [], 'AGENT_HELP.md:reveal one.py'),
        (['reveal two.py'], [], 'AGENT_HELP.md:reveal two.py'),
        (['reveal missing.py'], [('skip', (), {'reason': 'named fixture: names missing.py, which the named fixture lacks'})],
         'AGENT_HELP.md:reveal missing.py'),
        (['reveal broken.py'], [('skip', (), {'reason': 'named fixture: the doc shows it failing'})],
         'AGENT_HELP.md:reveal broken.py'),
        (['reveal git://one.py@lost'], [('skip', (), {'reason': 'named fixture: names ref lost, which the named fixture lacks'})],
         'AGENT_HELP.md:reveal git://one.py@lost'),
    ]
    assert len(calls) == 1


def test_custom_document_edits_are_visible_on_each_inventory(tmp_path):
    docs = _docs(tmp_path, ['reveal absent_first.py'])
    first = recipes._named_fixture_commands(docs)
    _docs(tmp_path, ['reveal absent_second.py'])
    second = recipes._named_fixture_commands(docs)
    assert [p.values for p in first] == [('reveal absent_first.py',)]
    assert [p.values for p in second] == [('reveal absent_second.py',)]
    assert second[0].marks[0].kwargs['reason'] == 'named fixture: names absent_second.py, which the named fixture lacks'
    assert second[0].id == 'AGENT_HELP.md:reveal absent_second.py'


def test_domain_edits_are_visible_between_inventories_and_standalone_skips(tmp_path, monkeypatch):
    import doc_command_fixture

    paths = set()
    monkeypatch.setattr(doc_command_fixture, 'named_paths', lambda: set(paths))
    monkeypatch.setattr(doc_command_fixture, 'binary_paths', lambda: set())
    docs = _docs(tmp_path, ['reveal fresh.py'])
    reason = 'named fixture: names fresh.py, which the named fixture lacks'
    assert recipes._named_fixture_commands(docs)[0].marks[0].kwargs['reason'] == reason
    assert recipes._named_fixture_skip(['reveal', 'fresh.py']) == 'names fresh.py, which the named fixture lacks'
    paths.add('fresh.py')
    assert recipes._named_fixture_commands(docs)[0].marks == []
    assert recipes._named_fixture_skip(['reveal', 'fresh.py']) is None
    paths.clear()
    assert recipes._named_fixture_commands(docs)[0].marks[0].kwargs['reason'] == reason
    assert recipes._named_fixture_skip(['reveal', 'fresh.py']) == 'names fresh.py, which the named fixture lacks'


def test_empty_and_explicitly_disclosed_inventories_keep_their_answers(tmp_path):
    docs = _docs(tmp_path, ['reveal help://quick'])
    assert recipes._named_fixture_commands(docs) == []
    _docs(tmp_path, ['reveal absent.py # not valid'])
    assert _rows(recipes._named_fixture_commands(docs)) == [
        (['reveal absent.py'], [('skip', (), {'reason': 'named fixture: the doc shows it failing'})],
         'AGENT_HELP.md:reveal absent.py')]

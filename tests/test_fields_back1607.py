"""BACK-1607: --fields is one rule for every adapter, and a name that matches nothing is said.

Before, the level --fields addressed depended on the result's shape: a result holding one
of six hand-listed list names had only its items filtered, any other only its top level.
So the guide's own examples answered ``results: [{}, {}]`` on ast:// and ``{}`` on git://,
and a name that matched nothing was dropped in silence.
"""

import json

from conftest import _run_reveal_direct

from reveal.display.formatting import select_fields


def _git_history():
    return {'contract_version': '1.1', 'type': 'git_ref', 'source': '@HEAD',
            'source_type': 'directory', 'ref': 'HEAD',
            'commit': {'hash': 'a1', 'author': 'x'},
            'history': [{'hash': 'a1', 'author': 'x', 'email': 'e', 'message': 'm'},
                        {'hash': 'b2', 'author': 'y', 'email': 'f', 'message': 'n'}],
            'meta': {'warnings': []}}


def _ast_query():
    return {'contract_version': '1.1', 'type': 'ast_query', 'source': 'src',
            'source_type': 'directory', 'total_results': 2, 'meta': {'confidence': 1.0},
            'results': [{'name': 'f', 'line': 1, 'complexity': 3, 'file': 'a.py'},
                        {'name': 'g', 'line': 9, 'complexity': 1, 'file': 'a.py'}]}


class TestSelectFields:
    def test_item_keys_of_a_list_the_rule_did_not_know(self):
        # git://?type=log answers 'history', which no hand-typed list named: {} before.
        selected, unmatched = select_fields(_git_history(), ['hash', 'author'])
        assert selected['history'] == [{'hash': 'a1', 'author': 'x'},
                                       {'hash': 'b2', 'author': 'y'}]
        assert 'commit' not in selected and 'ref' not in selected
        assert unmatched == []

    def test_top_level_keys_next_to_a_list(self):
        # The guide's ast:// example: results: [{}, {}] and no total_results before.
        selected, unmatched = select_fields(_ast_query(), ['type', 'total_results', 'results'])
        assert selected['total_results'] == 2
        assert selected['results'] == _ast_query()['results']
        assert unmatched == []

    def test_item_keys_trim_items_and_drop_other_top_level_keys(self):
        selected, unmatched = select_fields(_ast_query(), ['name', 'line'])
        assert selected['results'] == [{'name': 'f', 'line': 1}, {'name': 'g', 'line': 9}]
        assert 'total_results' not in selected
        assert unmatched == []

    def test_list_dot_key_names_an_item_key_explicitly(self):
        # 'type' is a top-level key, so it never selects in items; results.<key> does.
        result = _ast_query()
        for item in result['results']:
            item['type'] = 'function'
        selected, _ = select_fields(result, ['results.type'])
        assert selected['results'] == [{'type': 'function'}, {'type': 'function'}]
        assert selected['type'] == 'ast_query'

    def test_envelope_is_kept_on_a_top_level_selection(self):
        selected, _ = select_fields(_git_history(), ['ref'])
        assert selected == {'contract_version': '1.1', 'type': 'git_ref', 'source': '@HEAD',
                            'source_type': 'directory', 'meta': {'warnings': []}, 'ref': 'HEAD'}

    def test_nested_top_level_key(self):
        selected, unmatched = select_fields({'type': 't', 'summary': {'a': 1, 'b': 2}},
                                            ['summary.a'])
        assert selected == {'type': 't', 'summary': {'a': 1}}
        assert unmatched == []

    def test_present_none_value_counts_as_matched(self):
        selected, unmatched = select_fields({'type': 't', 'total_matches': None},
                                            ['total_matches'])
        assert selected == {'type': 't', 'total_matches': None}
        assert unmatched == []

    def test_an_empty_list_is_kept_and_not_reported(self):
        # A filter that matched no file: there are no items to check 'file' against.
        selected, unmatched = select_fields({'type': 't', 'summary': {}, 'files': []}, ['file'])
        assert selected == {'type': 't', 'files': []}
        assert unmatched == []
        # ...but an empty side list does not hide a typo when another list has items.
        _, unmatched = select_fields({'type': 't', 'errors': [], 'results': [{'a': 1}]}, ['zz'])
        assert unmatched == ['zz']

    def test_unmatched_names_are_returned(self):
        _, unmatched = select_fields(_ast_query(), ['name', 'path', 'quality_score'])
        assert unmatched == ['path', 'quality_score']


def _module(tmp_path):
    src = tmp_path / 'm.py'
    src.write_text('def alpha(x):\n    return x\n\n\ndef beta(y):\n    if y:\n        return 1\n'
                   '    return 2\n', encoding='utf-8')
    return src


class TestCli:
    def test_guide_ast_example_returns_the_named_fields(self, tmp_path):
        src = _module(tmp_path)
        r = _run_reveal_direct(f'ast://{src.as_posix()}?type=function',
                               '--fields=type,total_results,results', '--format', 'json')
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        assert data['type'] == 'ast_query'
        assert data['total_results'] == 2
        assert [item['name'] for item in data['results']] == ['alpha', 'beta']

    def test_item_fields_on_ast(self, tmp_path):
        src = _module(tmp_path)
        r = _run_reveal_direct(f'ast://{src.as_posix()}?type=function',
                               '--fields=name,line', '--format', 'json')
        data = json.loads(r.stdout)
        assert data['results'] == [{'name': 'alpha', 'line': 1}, {'name': 'beta', 'line': 5}]

    def test_unmatched_name_is_disclosed_in_result_and_on_stderr(self, tmp_path):
        src = _module(tmp_path)
        r = _run_reveal_direct(f'stats://{src.as_posix()}',
                               '--fields=file,quality_score', '--format', 'json')
        assert r.returncode == 0, r.stderr
        data = json.loads(r.stdout)
        warning, = [w for w in data['meta']['warnings'] if w['type'] == 'fields_unmatched']
        assert warning['fields'] == ['quality_score']
        assert 'quality_score matched no field' in r.stderr
        assert 'quality' in r.stderr  # names what does exist

    def test_text_format_is_left_whole_with_a_note(self, tmp_path):
        # A text renderer needs the whole result: given a selection it printed nothing
        # (stats://) or zeros (ast://), and git:// file history crashed.
        src = _module(tmp_path)
        r = _run_reveal_direct(f'ast://{src.as_posix()}?type=function', '--fields=name')
        assert r.returncode == 0, r.stderr
        assert 'alpha' in r.stdout and 'beta' in r.stdout
        assert '--fields selects fields of the JSON result' in r.stderr

    def test_failed_result_keeps_its_error(self):
        # An adapter that returns an error result: selecting from it would drop 'error',
        # and the router would report the failure as success.
        from argparse import Namespace
        from reveal.cli.routing.uri import _apply_field_selection
        result = {'contract_version': '1.1', 'type': 't', 'error': 'boom', 'detail': 'x'}
        out = _apply_field_selection(dict(result), Namespace(fields='detail', format='json'))
        assert out == result

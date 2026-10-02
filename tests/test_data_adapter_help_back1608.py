"""BACK-1608: the data-adapter help promises only what the adapters return.

The data recipes promised sqlite sample rows and xlsx header rows that neither adapter
returns, taught ``mysql://host/dbname`` although the path names a health section, and
called sqlite and mysql "the same query API". The env recipe ``reveal env:// | grep
'^DB'`` could never match: text rows are indented, and ``--format=grep`` printed the
text headings among its lines.
"""

import json

from reveal.adapters.help import HelpAdapter
from reveal.rendering.adapters.env import render_env_structure


def _help(topic):
    return json.dumps(HelpAdapter('').get_element(topic))


def test_data_recipes_promise_no_rows_and_no_mysql_database_path():
    text = _help('examples/data')
    assert 'sample rows' not in text
    assert 'header rows' not in text
    assert 'mysql://user:pass@host/dbname' not in text


def test_relationships_do_not_claim_one_query_api():
    text = _help('relationships')
    assert 'same query API' not in text
    assert 'mysql://prod/users' not in text


def test_env_recipe_uses_grep_format_lines():
    text = _help('examples/runtime')
    assert "reveal env:// | grep '^DB'" not in text
    assert "--format=grep | grep '^env://DB_'" in text


def test_env_grep_format_prints_only_variable_lines(capsys):
    data = {
        'total_count': 2,
        'categories': {
            'System': [{'name': 'HOME', 'value': '/home/u', 'sensitive': False}],
            'Custom': [{'name': 'DB_HOST', 'value': 'db', 'sensitive': False}],
        },
    }
    render_env_structure(data, 'grep')
    assert capsys.readouterr().out.splitlines() == ['env://HOME:/home/u', 'env://DB_HOST:db']

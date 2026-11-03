"""Unclassified scope is disclosed per edge and matches the selected lazy view."""
import json

import pytest

from conftest import _run_reveal_direct
from reveal.utils.path_utils import to_posix

pytestmark = pytest.mark.component


def _tree(root, files):
    root.mkdir()
    (root / '.reveal.yaml').write_text('root: true\n', encoding='utf-8')
    for name, source in files.items():
        (root / name).write_text(source, encoding='utf-8')
    return root.resolve()


@pytest.mark.parametrize('mode,count', [('include', 3), ('exclude', 2), ('only', 1)])
def test_partial_ruby_coverage_rule_matches_unknown_edge_behavior(tmp_path, mode, count):
    root = _tree(tmp_path / 'project', {
        'target.rb': '# unknown and local support\n',
        'local_target.rb': '# local only\n',
        'module_target.rb': '# module only\n',
        'source.rb': "items.each { require_relative 'target' }\n"
                     "def example\n require_relative 'target'\n require_relative 'local_target'\nend\n"
                     "require_relative 'module_target'\n",
    })
    uri = f'imports://{to_posix(root)}?importers&scope=path&lazy={mode}'
    out = _run_reveal_direct(uri, '--format', 'json')
    assert out.returncode == 0, out.stderr
    answer = json.loads(out.stdout)
    assert answer['total'] == count
    rule = answer['edge_rule']
    assert rule['unclassified_edges'] == 1
    assert rule['unclassified_languages'] == ['ruby']
    assert 'Import scope is unknown for 1 edge(s) in ruby' in rule['text']
    assert 'retained by &lazy=include and &lazy=exclude' in rule['text']
    assert 'omitted by &lazy=only' in rule['text']
    assert 'under every &lazy value' not in rule['text']
    text = _run_reveal_direct(uri)
    assert text.returncode == 0
    assert rule['text'] in text.stdout


def test_fully_classified_sibling_has_no_unknown_scope_warning(tmp_path):
    root = _tree(tmp_path / 'project', {'target.py': 'VALUE = 1\n', 'source.py': 'import target\n'})
    uri = f'imports://{to_posix(root)}?importers&scope=path'
    out = _run_reveal_direct(uri, '--format', 'json')
    assert out.returncode == 0, out.stderr
    answer = json.loads(out.stdout)
    assert answer['total'] == 1
    assert answer['edge_rule']['unclassified_edges'] == 0
    assert 'Import scope is' not in answer['edge_rule']['text']

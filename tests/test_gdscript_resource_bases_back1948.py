"""Literal resource inheritance uses GDScript's declared-base owner (BACK-1948)."""

import pytest

from reveal.analyzers.gdscript import GDScriptAnalyzer

pytestmark = pytest.mark.component

SOURCE = '''class Double extends "res://base.gd":
    pass
class Single extends 'res://other.gd':
    pass
class Qualified extends "res://base.gd".Nested:
    pass
class Named extends Other.Base:
    pass
class Outer extends "res://outer.gd":
    class Nested extends Resource:
        pass
class Plain:
    const Value = "res://unrelated.gd"
    # extends "res://comment.gd"
'''


@pytest.fixture
def analyzer(tmp_path):
    path = tmp_path / 'resources.gd'
    path.write_text(SOURCE, encoding='utf-8')
    instance = GDScriptAnalyzer(str(path))
    assert not instance.has_parse_errors()
    return instance


@pytest.mark.parametrize('name,owner,bases', [
    ('Double', None, ['"res://base.gd"']),
    ('Single', None, ["'res://other.gd'"]),
    ('Qualified', None, ['"res://base.gd".Nested']),
    ('Named', None, ['Other.Base']),
    ('Outer', None, ['"res://outer.gd"']),
    ('Nested', 'Outer', ['Resource']),
    ('Plain', None, []),
])
def test_only_declared_base_belongs_to_each_class(analyzer, name, owner, bases):
    for _ in range(2):
        item = next(item for item in analyzer.get_structure()['classes']
                    if item['name'] == name and item.get('owner') == owner)
        assert item['bases'] == bases

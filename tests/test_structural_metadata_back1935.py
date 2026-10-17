"""Annotation/base ownership controls for the BACK-1935 structural slice."""

import pytest

from reveal.analyzers.dart import DartAnalyzer
from reveal.analyzers.gdscript import GDScriptAnalyzer
from reveal.analyzers.scala import ScalaAnalyzer
from reveal.core import tree_root
from reveal.core.treesitter_compat import _zero_arg

pytestmark = pytest.mark.component


def _structure(tmp_path, analyzer_type, extension, source):
    path = tmp_path / f'sample.{extension}'
    path.write_text(source, encoding='utf-8')
    analyzer = analyzer_type(str(path))
    assert _zero_arg(tree_root(analyzer.tree), 'has_error') is False
    return analyzer.get_structure()


@pytest.mark.parametrize('analyzer_type,extension,source', [
    (DartAnalyzer, 'dart', 'class Plain {}\n'),
    (ScalaAnalyzer, 'scala', 'class Plain\n'),
    (GDScriptAnalyzer, 'gd', 'class Plain:\n    pass\n'),
], ids=['dart', 'scala', 'gdscript'])
def test_plain_class_has_no_annotation_or_base(tmp_path, analyzer_type, extension, source):
    record = _structure(tmp_path, analyzer_type, extension, source)['classes'][0]
    assert record['name'] == 'Plain'
    assert record['decorators'] == []
    assert record['bases'] == []


@pytest.mark.parametrize('analyzer_type,extension,source', [
    (DartAnalyzer, 'dart', '''@First
// A comment does not detach class metadata.
@Second("class")
class Tagged {
  @Method("method")
  void act() {}
  void plainMethod() {}
}
class Plain {}
@Last
class Other {}
'''),
    (ScalaAnalyzer, 'scala', '''@First
// A comment does not detach class metadata.
@Second("class")
class Tagged {
  @Method("method")
  def act(): Unit = {}
  def plainMethod(): Unit = {}
}
class Plain
@Last
class Other
'''),
], ids=['dart', 'scala'])
def test_class_annotations_keep_order_and_owning_declaration(
        tmp_path, analyzer_type, extension, source):
    structure = _structure(tmp_path, analyzer_type, extension, source)
    classes = {record['name']: record for record in structure['classes']}
    assert classes['Tagged']['decorators'] == ['@First', '@Second("class")']
    assert classes['Other']['decorators'] == ['@Last']
    assert classes['Plain']['decorators'] == []
    plain_method = next(f for f in structure['functions'] if f['name'] == 'plainMethod')
    assert plain_method['decorators'] == []


def test_gdscript_function_annotations_stop_at_their_own_declaration(tmp_path):
    structure = _structure(tmp_path, GDScriptAnalyzer, 'gd', '''extends Node
@rpc("any_peer")
# An adjacent comment does not detach the annotations.
@warning_ignore("unused_parameter")
func tagged(value):
    pass

func plain():
    pass

class Inner:
    func plain_method():
        pass

@rpc
func other():
    pass
''')
    functions = {record['name']: record for record in structure['functions']}
    assert functions['tagged']['decorators'] == [
        '@rpc("any_peer")', '@warning_ignore("unused_parameter")']
    assert functions['other']['decorators'] == ['@rpc']
    assert functions['plain']['decorators'] == []
    assert functions['plain_method']['decorators'] == []
    assert structure['classes'][0]['decorators'] == []


def test_gdscript_bases_belong_to_the_class_and_preserve_qualified_names(tmp_path):
    structure = _structure(tmp_path, GDScriptAnalyzer, 'gd', '''extends Node
class Base:
    class Inner:
        pass

class Child extends Base.Inner:
    pass

class Plain:
    var reference = "Base"
''')
    classes = {record['name']: record for record in structure['classes']}
    assert classes['Child']['bases'] == ['Base.Inner']
    assert classes['Base']['bases'] == []
    assert classes['Inner']['bases'] == []
    assert classes['Plain']['bases'] == []


@pytest.mark.parametrize('directive', [
    '@tool', '@icon("res://icon.svg")', '@static_unload',
    '@export_category("Group")', '@export_group("Group")', '@export_subgroup("Group")',
    '@warning_ignore_start("unused_parameter")', '@warning_ignore_restore("unused_parameter")',
])
def test_gdscript_script_and_standalone_annotations_do_not_attach_to_function(tmp_path, directive):
    structure = _structure(
        tmp_path, GDScriptAnalyzer, 'gd', f'{directive}\nfunc plain():\n    pass\n')
    assert structure['functions'][0]['decorators'] == []


def test_gdscript_script_annotation_does_not_hide_following_rpc(tmp_path):
    structure = _structure(tmp_path, GDScriptAnalyzer, 'gd', '''@warning_ignore("unused_parameter")
@tool
@rpc("any_peer")
func tagged():
    pass
''')
    assert structure['functions'][0]['decorators'] == ['@rpc("any_peer")']

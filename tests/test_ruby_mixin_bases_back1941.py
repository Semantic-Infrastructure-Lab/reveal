"""Literal declaration-level Ruby mixins use existing bases (BACK-1941)."""

import pytest

from reveal.registry import get_analyzer

pytestmark = pytest.mark.component

SOURCE = '''module Support
  module Composed
    include Core, ::Global::Tracing
    extend(ClassMethods)
    extend self
  end
  class Host < Base
    include First, Support::Second
    extend ClassMethods, Extra
    include First
    include Base
    self.include ExplicitOnly
    Other.include ReceiverOnly
    include factory()
    include dynamic_module
    include *PACKAGES
    prepend PrependOnly
    if enabled
      include ConditionalOnly
    end
    configure do
      include BlockOnly
    end
    def nested_method
      include MethodOnly
      extend MethodClassOnly
    end
    class Nested < NestedBase
      include NestedOnly
    end
  end
end
class Plain; end
class Standalone < Existing::Parent; end
class MethodCallsOnly
  def include(value); end
  def nested_method
    include MethodOnly
    extend MethodClassOnly
  end
end
class ConditionalCallsOnly
  if enabled
    include ConditionalOnly
  end
  configure do
    include BlockOnly
  end
end
'''


@pytest.fixture
def analyzer(tmp_path):
    path = tmp_path / 'mixins.rb'
    path.write_text(SOURCE, encoding='utf-8')
    instance = get_analyzer(str(path))(str(path))
    assert not instance.has_parse_errors()
    return instance


def _class(analyzer, name):
    return next(item for item in analyzer.get_structure()['classes'] if item['name'] == name)


def test_class_bases_combine_superclass_and_ordered_unique_mixins(analyzer):
    for _ in range(2):
        item = _class(analyzer, 'Host')
        assert item['bases'] == ['Base', 'First', 'Support::Second', 'ClassMethods', 'Extra']
        assert item['owner'] == 'Support'


def test_module_mixins_use_actual_existing_class_category(analyzer):
    item = _class(analyzer, 'Composed')
    assert item['bases'] == ['Core', '::Global::Tracing', 'ClassMethods']
    assert item['owner'] == 'Support'
    assert _class(analyzer, 'Support')['bases'] == []


def test_nested_class_keeps_its_own_superclass_and_mixins(analyzer):
    item = _class(analyzer, 'Nested')
    assert item['bases'] == ['NestedBase', 'NestedOnly']
    assert item['owner'] == 'Support.Host'


def test_mixin_declines_do_not_become_outer_ancestry(analyzer):
    assert not set(_class(analyzer, 'Host')['bases']) & {
        'ExplicitOnly', 'ReceiverOnly', 'factory', 'dynamic_module', 'PACKAGES',
        'PrependOnly', 'ConditionalOnly', 'BlockOnly', 'MethodOnly', 'MethodClassOnly',
        'NestedOnly', 'NestedBase', 'self',
    }


@pytest.mark.parametrize('name,expected', [
    ('Plain', []), ('Standalone', ['Existing::Parent']),
    ('MethodCallsOnly', []), ('ConditionalCallsOnly', []),
])
def test_nonmixin_sibling_scopes_keep_existing_bases(analyzer, name, expected):
    assert _class(analyzer, name)['bases'] == expected


def test_qualified_mixin_names_require_constant_only_scopes(tmp_path):
    path = tmp_path / 'qualified_mixins.rb'
    path.write_text('''class Host < namespace::Parent
  include factory()::Mixed
  include namespace::Mixed
  extend namespace::Nested::Mixed
  include ::Global::Mixed, Namespaced::Mixed
end
''', encoding='utf-8')
    instance = get_analyzer(str(path))(str(path))
    assert not instance.has_parse_errors()
    for _ in range(2):
        assert _class(instance, 'Host')['bases'] == [
            'namespace::Parent', '::Global::Mixed', 'Namespaced::Mixed',
        ]

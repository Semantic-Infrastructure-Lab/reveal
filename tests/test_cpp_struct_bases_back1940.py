"""C++ class/struct inheritance uses one declared-base owner (BACK-1940)."""

import pytest

from reveal.registry import get_analyzer

pytestmark = pytest.mark.component

SOURCE = '''struct Base {};
namespace ns { struct Other {}; template<class T> struct Template {}; }
template<class T> struct Template {};
template<class T, class U> struct Pair {};
class Existing : public Base, virtual private ns::Other {};
struct Simple : Base {};
struct Qualified : public ns::Other {};
struct Multiple : private Base, virtual public ns::Other {};
template<class T> struct Generic : Template<T> {};
template<class T> class GenericClass : public Template<T> {};
template<class T> struct QualifiedGeneric : public ns::Template<T> {};
template<class T, class U> struct Composite : Template<Pair<T, U>> {};
struct Outer : Base { struct Nested : ns::Other {}; };
struct Plain {};
class PlainClass {};
struct BodyOnly { Base member; ns::Other other; };
'''


@pytest.fixture
def analyzer(tmp_path):
    path = tmp_path / 'bases.cpp'
    path.write_text(SOURCE, encoding='utf-8')
    instance = get_analyzer(str(path))(str(path))
    assert not instance.has_parse_errors()
    return instance


@pytest.mark.parametrize('category,name,owner,expected', [
    ('structs', 'Simple', None, ['Base']),
    ('structs', 'Qualified', None, ['ns::Other']),
    ('structs', 'Multiple', None, ['Base', 'ns::Other']),
    ('structs', 'Generic', None, ['Template<T>']),
    ('classes', 'GenericClass', None, ['Template<T>']),
    ('structs', 'QualifiedGeneric', None, ['ns::Template<T>']),
    ('structs', 'Composite', None, ['Template<Pair<T, U>>']),
    ('structs', 'Outer', None, ['Base']),
    ('structs', 'Nested', 'Outer', ['ns::Other']),
])
def test_struct_and_template_bases_keep_declared_names(analyzer, category, name, owner, expected):
    for _ in range(2):
        item = next(item for item in analyzer.get_structure()[category]
                    if item['name'] == name and item.get('owner') == owner)
        assert item['bases'] == expected


def test_existing_class_bases_preserve_access_and_virtual_handling(analyzer):
    item = next(item for item in analyzer.get_structure()['classes'] if item['name'] == 'Existing')
    assert item['bases'] == ['Base', 'ns::Other']


def test_noninheriting_types_and_field_types_do_not_gain_bases(analyzer):
    structure = analyzer.get_structure()
    for category, names in [('structs', ['Plain', 'BodyOnly']), ('classes', ['PlainClass'])]:
        for name in names:
            item = next(item for item in structure[category] if item['name'] == name)
            assert item['bases'] == []

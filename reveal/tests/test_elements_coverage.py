"""Additional tests for reveal.elements coverage."""

import unittest
from reveal.elements import TypedElement, PythonElement, MarkdownElement
from reveal.type_system import RevealType, EntityDef


class TestTypedElementEdgeCases(unittest.TestCase):
    """Test edge cases in TypedElement for coverage."""

    def test_children_without_type(self):
        """Test children returns empty list when _type is None."""
        element = TypedElement(name='test', line=1, line_end=10, category='function')
        # _type not set, should return empty list
        self.assertEqual(element.children, [])

    def test_children_with_invalid_entity(self):
        """Test children returns empty list when entity_def not found."""
        # Create a type that doesn't have the element's category
        reveal_type = RevealType(name='test', extensions=['.test'], scheme='test', entities={})
        element = TypedElement(
            name='test', 
            line=1, 
            line_end=10, 
            category='unknown_category'
        )
        element._type = reveal_type
        element._siblings = []
        
        # Should return empty list since entity_def won't be found
        self.assertEqual(element.children, [])

    def test_iter_returns_children(self):
        """Test __iter__ iterates over children."""
        parent = TypedElement(name='Parent', line=1, line_end=20, category='class')
        child1 = TypedElement(name='child1', line=2, line_end=5, category='method')
        child2 = TypedElement(name='child2', line=6, line_end=9, category='method')
        
        # Set up type and siblings
        reveal_type = RevealType(
            name='test',
            extensions=['.test'],
            scheme='test',
            entities={'class': EntityDef(contains=['method'])}
        )
        parent._type = reveal_type
        child1._type = reveal_type
        child2._type = reveal_type
        parent._siblings = [parent, child1, child2]
        child1._siblings = [parent, child1, child2]
        child2._siblings = [parent, child1, child2]
        
        # Test iteration
        children_list = list(parent)
        self.assertEqual(len(children_list), 2)
        self.assertIn(child1, children_list)
        self.assertIn(child2, children_list)

    def test_getitem_returns_child_by_name(self):
        """Test __getitem__ returns child by name."""
        parent = TypedElement(name='Parent', line=1, line_end=20, category='class')
        child = TypedElement(name='target', line=2, line_end=5, category='method')
        
        reveal_type = RevealType(
            name='test',
            extensions=['.test'],
            scheme='test',
            entities={'class': EntityDef(contains=['method'])}
        )
        parent._type = reveal_type
        child._type = reveal_type
        parent._siblings = [parent, child]
        child._siblings = [parent, child]
        
        # Test __getitem__
        result = parent['target']
        self.assertEqual(result, child)
        
        # Test non-existent child
        result = parent['nonexistent']
        self.assertIsNone(result)

    def test_ancestors_generator(self):
        """Test ancestors yields all parents up the tree."""
        grandparent = TypedElement(name='GrandParent', line=1, line_end=30, category='class')
        parent = TypedElement(name='Parent', line=2, line_end=20, category='class')
        child = TypedElement(name='child', line=3, line_end=5, category='method')
        
        reveal_type = RevealType(
            name='test',
            extensions=['.test'],
            scheme='test',
            entities={
                'class': EntityDef(contains=['class', 'method']),
                'method': EntityDef(contains=[])
            }
        )
        
        for el in [grandparent, parent, child]:
            el._type = reveal_type
            el._siblings = [grandparent, parent, child]
        
        # Get ancestors
        ancestors = list(child.ancestors())
        self.assertEqual(len(ancestors), 2)
        self.assertEqual(ancestors[0], parent)
        self.assertEqual(ancestors[1], grandparent)

    def test_find_returns_none_when_not_found(self):
        """Test find returns None when element not found."""
        element = TypedElement(name='test', line=1, line_end=10, category='function')
        result = element.find_by_name('nonexistent')
        self.assertIsNone(result)

    def test_find_by_category(self):
        """Test find_by_category finds first element of category."""
        parent = TypedElement(name='Parent', line=1, line_end=30, category='class')
        method = TypedElement(name='method1', line=2, line_end=10, category='method')
        prop = TypedElement(name='prop1', line=11, line_end=15, category='property')
        
        reveal_type = RevealType(
            name='test',
            extensions=['.test'],
            scheme='test',
            entities={
                'class': EntityDef(contains=['method', 'property']),
                'method': EntityDef(contains=[]),
                'property': EntityDef(contains=[])
            }
        )
        
        for el in [parent, method, prop]:
            el._type = reveal_type
            el._siblings = [parent, method, prop]
        
        # Find by category (returns generator, not single element)
        results = list(parent.find_by_category('property'))
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0], prop)

        # Category not found
        results = list(parent.find_by_category('nonexistent'))
        self.assertEqual(len(results), 0)


class TestPythonElementEdgeCases(unittest.TestCase):
    """Test edge cases in PythonElement for coverage."""

    def test_display_category_nested_function(self):
        """Test display_category for nested function."""
        # Create a function inside a function
        outer = PythonElement(
            name='outer',
            line=1,
            line_end=20,
            category='function',
            decorators=[]
        )
        inner = PythonElement(
            name='inner',
            line=5,
            line_end=10,
            category='function',
            decorators=[]
        )
        
        reveal_type = RevealType(
            name='test',
            extensions=['.test'],
            scheme='test',
            entities={'function': EntityDef(contains=['function'])}
        )
        
        outer._type = reveal_type
        inner._type = reveal_type
        outer._siblings = [outer, inner]
        inner._siblings = [outer, inner]
        
        # Inner should be identified as nested function
        self.assertTrue(inner.is_nested_function)
        self.assertEqual(inner.display_category, 'function')

    def test_decorator_prefix_no_decorators(self):
        """Test decorator_prefix returns empty string when no decorators."""
        element = PythonElement(
            name='test',
            line=1,
            line_end=5,
            category='function',
            decorators=[]
        )
        self.assertEqual(element.decorator_prefix, '')

    def test_compact_signature_with_asterisk_args(self):
        """Test compact_signature handles *args and **kwargs."""
        element = PythonElement(
            name='test',
            line=1,
            line_end=5,
            category='function',
            signature='(*args, **kwargs)',
            decorators=[]
        )
        result = element.compact_signature
        self.assertIn('*args', result)
        self.assertIn('**kwargs', result)

    def test_return_type_no_signature(self):
        """Test return_type returns empty string when no signature."""
        element = PythonElement(
            name='test',
            line=1,
            line_end=5,
            category='function',
            signature=None,
            decorators=[]
        )
        self.assertEqual(element.return_type, '')

    def test_return_type_no_arrow(self):
        """Test return_type returns empty string when no -> in signature."""
        element = PythonElement(
            name='test',
            line=1,
            line_end=5,
            category='function',
            signature='(x, y)',
            decorators=[]
        )
        self.assertEqual(element.return_type, '')

    def test_subsections_filters_by_category(self):
        """Test subsections returns only section-category children."""
        parent = MarkdownElement(
            name='Parent',
            line=1,
            line_end=30,
            category='section',
            level=1
        )
        section = MarkdownElement(
            name='section1',
            line=2,
            line_end=10,
            category='section',
            level=2
        )
        method = MarkdownElement(
            name='method1',
            line=11,
            line_end=15,
            category='other',
            level=2
        )
        
        reveal_type = RevealType(
            name='test',
            extensions=['.test'],
            scheme='test',
            entities={
                'section': EntityDef(contains=['section', 'other']),
                'other': EntityDef(contains=[])
            }
        )
        
        for el in [parent, section, method]:
            el._type = reveal_type
            el._siblings = [parent, section, method]
        
        # Should only return sections
        subsections = parent.subsections
        self.assertEqual(len(subsections), 1)
        self.assertEqual(subsections[0], section)


if __name__ == '__main__':
    unittest.main()

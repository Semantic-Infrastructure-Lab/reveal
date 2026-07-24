"""Tests for Swift analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.swift import SwiftAnalyzer


class TestSwiftAnalyzer(unittest.TestCase):
    """Test suite for Swift source file analysis."""

    def test_extract_functions(self):
        """Should extract function definitions."""
        code = '''// Swift utilities
func add(_ a: Int, _ b: Int) -> Int {
    return a + b
}

func multiply(x: Int, y: Int) -> Int {
    return x * y
}

func printResult(value: Int) {
    print("Result: \\(value)")
}

func main() {
    let sum = add(5, 3)
    printResult(value: sum)
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract function definitions
            func_names = [f['name'] for f in functions]
            self.assertIn('add', func_names)
            self.assertIn('multiply', func_names)
            self.assertIn('printResult', func_names)
            self.assertIn('main', func_names)

        finally:
            os.unlink(temp_path)

    def test_extract_classes(self):
        """Should extract class definitions."""
        code = '''class Person {
    var name: String
    var age: Int

    init(name: String, age: Int) {
        self.name = name
        self.age = age
    }

    func greet() -> String {
        return "Hello, I'm \\(name)"
    }
}

class Student: Person {
    var grade: String

    init(name: String, age: Int, grade: String) {
        self.grade = grade
        super.init(name: name, age: age)
    }

    func study() {
        print("\\(name) is studying")
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('classes', structure)
            classes = structure['classes']

            # Should extract class definitions
            class_names = [c['name'] for c in classes]
            self.assertIn('Person', class_names)
            self.assertIn('Student', class_names)

        finally:
            os.unlink(temp_path)

    def test_extract_structs(self):
        """Should extract struct definitions."""
        code = '''struct Point {
    var x: Double
    var y: Double

    func distance() -> Double {
        return (x * x + y * y).squareRoot()
    }
}

struct Rectangle {
    var width: Double
    var height: Double

    var area: Double {
        return width * height
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Structs may be extracted as classes
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_extract_protocols(self):
        """Should handle protocol definitions."""
        code = '''protocol Greetable {
    func greet() -> String
}

protocol Identifiable {
    var id: String { get }
}

class MyClass: Greetable {
    func greet() -> String {
        return "Hello!"
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should at least extract the class
            self.assertIsInstance(structure, dict)
            if 'classes' in structure:
                class_names = [c['name'] for c in structure['classes']]
                self.assertIn('MyClass', class_names)

        finally:
            os.unlink(temp_path)

    def test_enums(self):
        """Should handle enum definitions."""
        code = '''enum Direction {
    case north
    case south
    case east
    case west
}

enum Result<T> {
    case success(T)
    case failure(Error)
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash on enum syntax
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_closures(self):
        """Should handle closures."""
        code = '''func processList(_ items: [Int], transform: (Int) -> Int) -> [Int] {
    return items.map(transform)
}

let doubled = processList([1, 2, 3]) { $0 * 2 }

let greeting = { (name: String) -> String in
    return "Hello, \\(name)!"
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract processList function
            func_names = [f['name'] for f in functions]
            self.assertIn('processList', func_names)

        finally:
            os.unlink(temp_path)

    def test_extensions(self):
        """Should handle extensions."""
        code = '''extension String {
    func reversed() -> String {
        return String(self.reversed())
    }

    var length: Int {
        return self.count
    }
}

class Calculator {
    func add(_ a: Int, _ b: Int) -> Int {
        return a + b
    }
}

extension Calculator {
    func multiply(_ a: Int, _ b: Int) -> Int {
        return a * b
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should handle extensions without crashing
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''class 日本語 {
    func こんにちは() -> String {
        return "世界🌍"
    }

    func emoji_test() -> String {
        return "👍 Swift is awesome! 🚀"
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash on UTF-8
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_generics(self):
        """Should handle generic types."""
        code = '''func swap<T>(_ a: inout T, _ b: inout T) {
    let temp = a
    a = b
    b = temp
}

class Stack<Element> {
    private var items: [Element] = []

    func push(_ item: Element) {
        items.append(item)
    }

    func pop() -> Element? {
        return items.isEmpty ? nil : items.removeLast()
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            # Should extract generic function and class
            if 'functions' in structure:
                func_names = [f['name'] for f in structure['functions']]
                self.assertIn('swap', func_names)
            if 'classes' in structure:
                class_names = [c['name'] for c in structure['classes']]
                self.assertIn('Stack', class_names)

        finally:
            os.unlink(temp_path)

    def test_extension_conformance_populates_bases(self):
        """extension Foo: Protocol { } must appear in `classes` with bases populated.

        BACK-8xx (Swift surface/contracts recall oracle): tree-sitter-swift
        parses `extension` as a 'class_declaration' node, same as class/struct/
        enum, distinguished only by a leading 'extension' token child. But its
        name is nested one level deeper (class_declaration -> user_type ->
        type_identifier) than a primary declaration's direct type_identifier
        child, so every `_name_via_*` strategy in the shared base class missed
        it, `_get_node_name` returned None, and `_extract_undecorated_classes`
        silently dropped the ENTIRE extension (not just its bases) since only
        PHP's anonymous_class gets a synthetic-name fallback for a nameless
        node. This made extension-based protocol conformance -- a common Swift
        idiom for adding conformance separately from a type's primary
        declaration -- entirely invisible to `contracts`.
        """
        code = '''protocol Drawable {
    func draw()
}

struct Circle {
    var r: Double
}

extension Circle: Drawable {
    func draw() {}
}

extension Circle {
    func area() -> Double {
        return r * r * 3.14159
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()

            classes = structure['classes']
            circle_entries = [c for c in classes if c['name'] == 'Circle']
            # Primary struct decl + BOTH extensions (conforming and bare) now
            # all resolve a name and appear -- the name-extraction fix applies
            # regardless of whether the extension declares conformance. The
            # bare `extension Circle { }` correctly still has bases == [];
            # contracts.py's `_classify_ts` filters `bases: []` classes out of
            # implementer output downstream, so it stays invisible to
            # `contracts` even though the analyzer layer now sees it.
            self.assertEqual(len(circle_entries), 3)

            struct_entry = next(c for c in circle_entries if c['line'] == 5)
            self.assertEqual(struct_entry['bases'], [])

            ext_entry = next(c for c in circle_entries if c['line'] == 9)
            self.assertEqual(ext_entry['bases'], ['Drawable'])

            bare_ext_entry = next(c for c in circle_entries if c['line'] == 13)
            self.assertEqual(bare_ext_entry['bases'], [])

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

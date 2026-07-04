"""Tests for Dart analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.dart import DartAnalyzer


class TestDartAnalyzer(unittest.TestCase):
    """Test suite for Dart source file analysis."""

    def test_extract_functions(self):
        """Should extract function definitions."""
        code = '''// Dart utilities
int add(int a, int b) {
  return a + b;
}

int multiply(int x, int y) {
  return x * y;
}

void printResult(int value) {
  print('Result: $value');
}

void main() {
  var sum = add(5, 3);
  printResult(sum);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = DartAnalyzer(temp_path)
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
  String name;
  int age;

  Person(this.name, this.age);

  String greet() {
    return 'Hello, I\\'m $name';
  }
}

class Student extends Person {
  String grade;

  Student(String name, int age, this.grade) : super(name, age);

  void study() {
    print('$name is studying');
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = DartAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('classes', structure)
            classes = structure['classes']

            # Should extract class definitions
            class_names = [c['name'] for c in classes]
            self.assertIn('Person', class_names)
            self.assertIn('Student', class_names)

        finally:
            os.unlink(temp_path)

    def test_flutter_widgets(self):
        """Should handle Flutter widget classes."""
        code = '''import 'package:flutter/material.dart';

class MyWidget extends StatelessWidget {
  final String title;

  MyWidget({required this.title});

  @override
  Widget build(BuildContext context) {
    return Text(title);
  }
}

class CounterWidget extends StatefulWidget {
  @override
  _CounterWidgetState createState() => _CounterWidgetState();
}

class _CounterWidgetState extends State<CounterWidget> {
  int _counter = 0;

  void _increment() {
    setState(() {
      _counter++;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container();
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = DartAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract widget classes
            self.assertIsInstance(structure, dict)
            if 'classes' in structure:
                class_names = [c['name'] for c in structure['classes']]
                self.assertIn('MyWidget', class_names)
                self.assertIn('CounterWidget', class_names)

        finally:
            os.unlink(temp_path)

    def test_async_functions(self):
        """Should handle async/await."""
        code = '''Future<String> fetchData() async {
  await Future.delayed(Duration(seconds: 1));
  return 'Data loaded';
}

Stream<int> countStream() async* {
  for (int i = 0; i < 10; i++) {
    await Future.delayed(Duration(milliseconds: 100));
    yield i;
  }
}

void main() async {
  var data = await fetchData();
  print(data);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = DartAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract async functions
            func_names = [f['name'] for f in functions]
            self.assertIn('fetchData', func_names)
            self.assertIn('countStream', func_names)
            self.assertIn('main', func_names)

        finally:
            os.unlink(temp_path)

    def test_mixins(self):
        """Should handle mixins."""
        code = '''mixin Musical {
  void play() {
    print('Playing music');
  }
}

mixin Aggressive {
  void attack() {
    print('Attacking!');
  }
}

class Performer with Musical {
  String name;
  Performer(this.name);
}

class Warrior with Aggressive, Musical {
  String weapon;
  Warrior(this.weapon);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = DartAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should handle mixins without crashing
            self.assertIsInstance(structure, dict)
            if 'classes' in structure:
                class_names = [c['name'] for c in structure['classes']]
                self.assertIn('Performer', class_names)
                self.assertIn('Warrior', class_names)

        finally:
            os.unlink(temp_path)

    def test_extensions(self):
        """Should handle extension methods."""
        code = '''extension StringExtension on String {
  String capitalize() {
    if (isEmpty) return this;
    return this[0].toUpperCase() + substring(1);
  }

  bool get isEmail {
    return contains('@');
  }
}

extension IntExtension on int {
  int double() {
    return this * 2;
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = DartAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should handle extensions without crashing
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_generics(self):
        """Should handle generic types."""
        code = '''class Stack<T> {
  final List<T> _items = [];

  void push(T item) {
    _items.add(item);
  }

  T? pop() {
    if (_items.isEmpty) return null;
    return _items.removeLast();
  }

  bool get isEmpty => _items.isEmpty;
}

T getFirst<T>(List<T> items) {
  return items[0];
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = DartAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            # Should extract generic class and function
            if 'classes' in structure:
                class_names = [c['name'] for c in structure['classes']]
                self.assertIn('Stack', class_names)
            if 'functions' in structure:
                func_names = [f['name'] for f in structure['functions']]
                self.assertIn('getFirst', func_names)

        finally:
            os.unlink(temp_path)

    def test_enums(self):
        """Should handle enum definitions."""
        code = '''enum Color {
  red,
  green,
  blue
}

enum Status {
  pending,
  active,
  completed;

  bool get isPending => this == Status.pending;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = DartAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash on enum syntax
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''class 日本語 {
  void こんにちは() {
    print('世界🌍');
  }

  void emoji_test() {
    print('👍 Dart is awesome! 🚀');
  }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = DartAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash on UTF-8
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_null_safety(self):
        """Should handle null safety operators."""
        code = '''String? getNullableString() {
  return null;
}

int processValue(int? value) {
  return value ?? 0;
}

void main() {
  String? name;
  int length = name?.length ?? 0;

  String greeting = name!;  // Force unwrap
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = DartAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract functions with nullable types
            func_names = [f['name'] for f in functions]
            self.assertIn('getNullableString', func_names)
            self.assertIn('processValue', func_names)
            self.assertIn('main', func_names)

        finally:
            os.unlink(temp_path)


class TestDartFunctionBodyBoundary(unittest.TestCase):
    """BACK-431 Issue G tier B dogfood finding (mysterious-probe-0703, against
    real AppFlowy source): Dart's grammar splits a function into SIBLING
    `function_signature` + `function_body` nodes, not parent/child like every
    other language. Every consumer of the raw signature node's own end
    position — get_structure()'s line_end/complexity, --outline, plain
    element extraction (`reveal file.dart funcname`), Class.method
    extraction, and every nav flag's range resolution — silently truncated
    to the one-line signature and saw the whole body as empty/out-of-range.
    """

    def _write(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            return f.name

    def test_top_level_function_line_end_spans_body(self):
        code = '''String greet(String name) {
  final upper = name.toUpperCase();
  return 'Hello, $upper!';
}
'''
        path = self._write(code)
        try:
            structure = DartAnalyzer(path).get_structure()
            fn = structure['functions'][0]
            self.assertEqual(fn['line'], 1)
            self.assertEqual(fn['line_end'], 4)
            self.assertGreater(fn['complexity'], 0)
        finally:
            os.unlink(path)

    def test_class_method_line_end_spans_body(self):
        code = '''class Foo {
  int compute(int x) {
    var y = x + 1;
    return y * 2;
  }
}
'''
        path = self._write(code)
        try:
            structure = DartAnalyzer(path).get_structure()
            method = structure['functions'][0]
            self.assertEqual(method['name'], 'compute')
            self.assertEqual(method['line'], 2)
            self.assertEqual(method['line_end'], 5)
        finally:
            os.unlink(path)

    def test_bare_name_element_extraction_returns_full_body(self):
        from reveal.display.element import _try_treesitter_extraction

        code = '''void run() {
  print('one');
  print('two');
}
'''
        path = self._write(code)
        try:
            analyzer = DartAnalyzer(path)
            result = _try_treesitter_extraction(analyzer, 'run')
            self.assertIsNotNone(result)
            self.assertEqual(result['line_start'], 1)
            self.assertEqual(result['line_end'], 4)
            self.assertIn("print('two')", result['source'])
        finally:
            os.unlink(path)

    def test_class_method_hierarchical_extraction_disambiguates_and_spans_body(self):
        """Two classes with same-named methods (a very common Dart/Flutter
        pattern — every widget has its own `build()`) — Class.method syntax
        must resolve the RIGHT one with its full body, not just the first
        same-named method found anywhere in the file."""
        from reveal.display.element import _extract_hierarchical_element

        code = '''class A {
  String build() {
    return 'from A';
  }
}

class B {
  String build() {
    final parts = ['from', 'B'];
    return parts.join(' ');
  }
}
'''
        path = self._write(code)
        try:
            analyzer = DartAnalyzer(path)
            result = _extract_hierarchical_element(analyzer, 'B.build')
            self.assertIsNotNone(result)
            self.assertEqual(result['line_start'], 8)
            self.assertEqual(result['line_end'], 11)
            self.assertIn("parts.join", result['source'])
            self.assertNotIn("from A", result['source'])
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()

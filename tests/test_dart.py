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


def _resolve_dart_func(path, element='run'):
    """Resolve a Dart function's body node the same way the CLI does —
    Dart's function_signature/function_body sibling split requires
    file_handler._resolve_func_node's swap, not a raw tree walk."""
    from reveal.file_handler import _resolve_func_node
    analyzer = DartAnalyzer(path)
    func_node, _, _ = _resolve_func_node(analyzer, element)
    content_bytes = analyzer.content.encode('utf-8')

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return func_node, get_text


class TestDartDepsExcludesMemberAccess(unittest.TestCase):
    """BACK-431 feature-breadth pass (--deps, real-corpus dogfood on
    AppFlowy's createNewPageInSpace): Dart's grammar has no member-access
    wrapper node at all — `obj.method(x)` parses as a bare `identifier`
    followed by flat sibling `selector` nodes, unlike every other supported
    language's `_MEMBER_ACCESS_KINDS`-style single-node shape. Without a
    Dart-specific exclusion, every member/method name in a chain
    (`find.byWidgetPredicate(...)`) read as its own independent undefined
    variable — one real call produced 2 bogus PARAM entries."""

    def _write(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            return f.name

    def test_deps_excludes_dotted_member_name(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        path = self._write('''\
void run(Object x) {
  final y = find.byWidgetPredicate(x);
}
''')
        try:
            func_node, get_text = _resolve_dart_func(path)
            deps = collect_deps(func_node, 1, 999, get_text)
            names = {d['var'] for d in deps}
            self.assertNotIn('byWidgetPredicate', names)
            self.assertIn('find', names)
            self.assertIn('x', names)
        finally:
            os.unlink(path)

    def test_deps_still_tracks_index_selector_contents(self):
        """A bracket index (`list[i]`) is the OTHER shape wrapped by Dart's
        assignable-selector node — unlike `.member`, its contents (`i`) are
        a real variable reference and must still be tracked."""
        from reveal.adapters.ast.nav_exits import collect_deps
        path = self._write('''\
void run(List<int> list, int i) {
  final y = list[i];
}
''')
        try:
            func_node, get_text = _resolve_dart_func(path)
            deps = collect_deps(func_node, 1, 999, get_text)
            names = {d['var'] for d in deps}
            self.assertIn('i', names)
            self.assertIn('list', names)
        finally:
            os.unlink(path)


class TestDartCallsFindsSelectorChainedCalls(unittest.TestCase):
    """BACK-431 feature-breadth pass (--calls, same AppFlowy dogfood): Dart
    has no call-expression node at all — `obj.method(x)` parses as
    `identifier` + sibling `selector(.method)` + sibling `selector((x))`,
    with no node naming "the call" as a whole. Every call in the real
    function under audit (9 of them, including `find.byWidgetPredicate`,
    `hoverOnWidget`, `renamePage`, ...) was silently invisible to --calls —
    total blindness, not a taxonomy gap, since no existing node-kind
    addition could have fixed it without reconstructing the callee from
    flat siblings."""

    def _write(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.dart', delete=False, encoding='utf-8') as f:
            f.write(code)
            return f.name

    def test_calls_finds_receiver_qualified_call(self):
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        path = self._write('''\
void run(Object x) {
  find.byWidgetPredicate(x);
}
''')
        try:
            func_node, get_text = _resolve_dart_func(path)
            calls = range_calls(func_node, 1, 999, get_text, CALL_NODE_TYPES)
            callees = [c['callee'] for c in calls]
            self.assertIn('find.byWidgetPredicate', callees)
        finally:
            os.unlink(path)

    def test_calls_collapses_chained_call_to_dotted_form(self):
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        path = self._write('''\
void run() {
  fetchThing().then((x) => x);
}
''')
        try:
            func_node, get_text = _resolve_dart_func(path)
            calls = range_calls(func_node, 1, 999, get_text, CALL_NODE_TYPES)
            callees = [c['callee'] for c in calls]
            self.assertIn('fetchThing', callees)
            self.assertIn('.then', callees)
        finally:
            os.unlink(path)

    def test_calls_ignores_bare_index_access(self):
        """`items[i]` is not a call — it must not be misreported as one."""
        from reveal.adapters.ast.nav_calls import range_calls
        from reveal.treesitter import CALL_NODE_TYPES
        path = self._write('''\
void run(List<int> items, int i) {
  final y = items[i];
}
''')
        try:
            func_node, get_text = _resolve_dart_func(path)
            calls = range_calls(func_node, 1, 999, get_text, CALL_NODE_TYPES)
            self.assertEqual(calls, [])
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()

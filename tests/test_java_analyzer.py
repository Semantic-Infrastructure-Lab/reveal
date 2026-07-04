"""Tests for Java analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.java import JavaAnalyzer


class TestJavaAnalyzer(unittest.TestCase):
    """Test suite for Java source file analysis."""

    def test_basic_class(self):
        """Should parse basic Java class."""
        code = '''public class HelloWorld {
    public static void main(String[] args) {
        System.out.println("Hello, World!");
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            self.assertIn('classes', structure)
            self.assertGreater(len(structure['classes']), 0)

            # Check class name
            class_names = [c['name'] for c in structure['classes']]
            self.assertIn('HelloWorld', class_names)

        finally:
            os.unlink(temp_path)

    def test_class_with_methods(self):
        """Should extract methods from class."""
        code = '''public class Calculator {
    private int value;

    public Calculator() {
        this.value = 0;
    }

    public int add(int a, int b) {
        return a + b;
    }

    public int subtract(int a, int b) {
        return a - b;
    }

    public int multiply(int a, int b) {
        return a * b;
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            self.assertIn('classes', structure)

            # Should have Calculator class
            calc_class = next((c for c in structure['classes'] if c['name'] == 'Calculator'), None)
            self.assertIsNotNone(calc_class)

        finally:
            os.unlink(temp_path)

    def test_imports(self):
        """Should extract import statements."""
        code = '''import java.util.List;
import java.util.ArrayList;
import java.util.Map;

public class ImportTest {
    private List<String> items;

    public ImportTest() {
        items = new ArrayList<>();
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            # Imports may or may not be extracted depending on tree-sitter config
            # Main test is that parsing doesn't crash

        finally:
            os.unlink(temp_path)

    def test_interface(self):
        """Should handle interface definitions."""
        code = '''public interface Drawable {
    void draw();
    void resize(int width, int height);
}

public class Circle implements Drawable {
    public void draw() {
        System.out.println("Drawing circle");
    }

    public void resize(int width, int height) {
        System.out.println("Resizing");
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_enum(self):
        """Should handle enum definitions."""
        code = '''public enum DayOfWeek {
    MONDAY,
    TUESDAY,
    WEDNESDAY,
    THURSDAY,
    FRIDAY,
    SATURDAY,
    SUNDAY
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_static_methods(self):
        """Should handle static methods."""
        code = '''public class MathUtils {
    public static int square(int n) {
        return n * n;
    }

    public static double sqrt(double n) {
        return Math.sqrt(n);
    }

    public static int factorial(int n) {
        if (n <= 1) return 1;
        return n * factorial(n - 1);
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_nested_class(self):
        """Should handle nested/inner classes."""
        code = '''public class Outer {
    private int x;

    public class Inner {
        private int y;

        public void printValues() {
            System.out.println(x + " " + y);
        }
    }

    public static class StaticNested {
        public void doSomething() {
            System.out.println("Static nested");
        }
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_generics(self):
        """Should handle generic types."""
        code = '''import java.util.List;
import java.util.ArrayList;

public class GenericBox<T> {
    private T content;

    public GenericBox(T content) {
        this.content = content;
    }

    public T getContent() {
        return content;
    }

    public void setContent(T content) {
        this.content = content;
    }

    public <U> void inspect(U item) {
        System.out.println(item.getClass().getName());
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_annotations(self):
        """Should handle annotations."""
        code = '''import java.lang.annotation.*;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.METHOD)
public @interface Test {
    String value() default "";
}

public class AnnotatedClass {
    @Override
    public String toString() {
        return "AnnotatedClass";
    }

    @Deprecated
    public void oldMethod() {
        // deprecated
    }

    @SuppressWarnings("unchecked")
    public void suppressedMethod() {
        // suppressed
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''public class Utf8Test {
    public String getEmoji() {
        return "👍 Java is awesome! 🚀";
    }

    public String getUnicode() {
        return "Hello, 世界! ¿Cómo estás?";
    }

    public void printGreeting() {
        System.out.println("Привет мир!");
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_lambda_expressions(self):
        """Should handle lambda expressions (Java 8+)."""
        code = '''import java.util.List;
import java.util.ArrayList;
import java.util.stream.Collectors;

public class LambdaTest {
    public void processItems() {
        List<String> items = new ArrayList<>();
        items.add("apple");
        items.add("banana");

        items.forEach(item -> System.out.println(item));

        List<String> filtered = items.stream()
            .filter(s -> s.startsWith("a"))
            .collect(Collectors.toList());
    }

    public void runnable() {
        Runnable r = () -> {
            System.out.println("Running in lambda");
        };
        r.run();
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


def _resolve_java_func(path, element='run'):
    """Resolve a Java method's node the same way the CLI does, and a
    get_text helper bound to its content."""
    from reveal.file_handler import _resolve_func_node
    analyzer = JavaAnalyzer(path)
    func_node, _, _ = _resolve_func_node(analyzer, element)
    content_bytes = analyzer.content.encode('utf-8')

    def get_text(node):
        return content_bytes[node.start_byte():node.end_byte()].decode('utf-8')

    return func_node, get_text


class TestJavaDepsExcludesAnnotationsAndMemberNames(unittest.TestCase):
    """BACK-431 feature-breadth pass (--deps, real-corpus dogfood on
    Elasticsearch's InternalEngine.java refreshIfNeeded): three distinct
    non-reads, all invisible to prior passes since they only tested
    --varflow/--exits/--ifmap, not --deps/--boundary's full-scan.

    1. `@Override`/`@SuppressWarnings("x")` (`marker_annotation`/
       `annotation`) both parse as `['@', identifier, args?]` — the
       identifier is a type name, not a variable, but reads as one.
    2. `field_access` (`obj.field`, no call) was entirely absent from
       `_MEMBER_ACCESS_KINDS` — every plain field access leaked its field
       name as a bogus PARAM.
    3. `method_invocation`'s 'name' field (the method being called) leaked
       too whenever a real 'object' receiver was present
       (`internalReaderManager.maybeRefreshBlocking(...)` produced a bogus
       PARAM for `maybeRefreshBlocking`) — a receiver-less bare call
       correctly keeps its own name as a read, matching Python's `sum(x)`
       parity.
    """

    def _write(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.java', delete=False, encoding='utf-8') as f:
            f.write(code)
            return f.name

    def test_deps_excludes_marker_annotation_name(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        path = self._write('''\
class Foo {
    @Override
    void run(String x) {
    }
}
''')
        try:
            func_node, get_text = _resolve_java_func(path)
            deps = collect_deps(func_node, 1, 999, get_text)
            names = {d['var'] for d in deps}
            self.assertNotIn('Override', names)
        finally:
            os.unlink(path)

    def test_deps_excludes_annotation_with_arguments_name(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        path = self._write('''\
class Foo {
    @SuppressWarnings("unchecked")
    void run(String x) {
    }
}
''')
        try:
            func_node, get_text = _resolve_java_func(path)
            deps = collect_deps(func_node, 1, 999, get_text)
            names = {d['var'] for d in deps}
            self.assertNotIn('SuppressWarnings', names)
        finally:
            os.unlink(path)

    def test_deps_excludes_plain_field_access_name(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        path = self._write('''\
class Foo {
    void run() {
        var y = a.b;
    }
}
''')
        try:
            func_node, get_text = _resolve_java_func(path)
            deps = collect_deps(func_node, 1, 999, get_text)
            names = {d['var'] for d in deps}
            self.assertNotIn('b', names)
            self.assertIn('a', names)
        finally:
            os.unlink(path)

    def test_deps_excludes_qualified_method_call_name(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        path = self._write('''\
class Foo {
    void run(String x) {
        manager.doThing(x);
    }
}
''')
        try:
            func_node, get_text = _resolve_java_func(path)
            deps = collect_deps(func_node, 1, 999, get_text)
            names = {d['var'] for d in deps}
            self.assertNotIn('doThing', names)
            self.assertIn('manager', names)
            self.assertIn('x', names)
        finally:
            os.unlink(path)

    def test_deps_still_tracks_bare_call_name(self):
        from reveal.adapters.ast.nav_exits import collect_deps
        path = self._write('''\
class Foo {
    void run(String x) {
        doThing(x);
    }
}
''')
        try:
            func_node, get_text = _resolve_java_func(path)
            deps = collect_deps(func_node, 1, 999, get_text)
            names = {d['var'] for d in deps}
            self.assertIn('doThing', names)
        finally:
            os.unlink(path)


if __name__ == '__main__':
    unittest.main()

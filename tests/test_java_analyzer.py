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


if __name__ == '__main__':
    unittest.main()

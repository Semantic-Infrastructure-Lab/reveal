"""Tests for Scala analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.scala import ScalaAnalyzer


class TestScalaAnalyzer(unittest.TestCase):
    """Test suite for Scala source file analysis."""

    def test_basic_class(self):
        """Should parse basic Scala class."""
        code = '''package com.example

class HelloWorld {
    def main(args: Array[String]): Unit = {
        println("Hello, World!")
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            self.assertIn('classes', structure)
            self.assertGreater(len(structure['classes']), 0)

            # Check class name
            class_names = [c['name'] for c in structure['classes']]
            self.assertIn('HelloWorld', class_names)

        finally:
            os.unlink(temp_path)

    def test_object(self):
        """Should handle Scala object (singleton)."""
        code = '''object MathUtils {
    def square(n: Int): Int = n * n

    def factorial(n: Int): Int = {
        if (n <= 1) 1
        else n * factorial(n - 1)
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            self.assertIn('functions', structure)

            # Should have functions
            func_names = [f['name'] for f in structure.get('functions', [])]
            self.assertIn('square', func_names)
            self.assertIn('factorial', func_names)

        finally:
            os.unlink(temp_path)

    def test_trait(self):
        """Should handle Scala trait definitions."""
        code = '''trait Drawable {
    def draw(): Unit
    def resize(width: Int, height: Int): Unit
}

class Circle extends Drawable {
    def draw(): Unit = {
        println("Drawing circle")
    }

    def resize(width: Int, height: Int): Unit = {
        println("Resizing")
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_case_class(self):
        """Should handle case classes."""
        code = '''case class Person(name: String, age: Int)

case class Address(
    street: String,
    city: String,
    country: String
)

case class Order(id: Int, items: List[String], total: Double) {
    def isEmpty: Boolean = items.isEmpty
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_companion_object(self):
        """Should handle companion objects."""
        code = '''class Counter private (val count: Int) {
    def increment: Counter = new Counter(count + 1)
}

object Counter {
    def apply(): Counter = new Counter(0)
    def apply(initial: Int): Counter = new Counter(initial)
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_pattern_matching(self):
        """Should handle pattern matching."""
        code = '''sealed trait Shape
case class Circle(radius: Double) extends Shape
case class Rectangle(width: Double, height: Double) extends Shape

object ShapeCalculator {
    def area(shape: Shape): Double = shape match {
        case Circle(r) => Math.PI * r * r
        case Rectangle(w, h) => w * h
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_higher_order_functions(self):
        """Should handle higher-order functions."""
        code = '''object FunctionalUtils {
    def map[A, B](list: List[A])(f: A => B): List[B] = {
        list.map(f)
    }

    def filter[A](list: List[A])(predicate: A => Boolean): List[A] = {
        list.filter(predicate)
    }

    def reduce[A](list: List[A])(op: (A, A) => A): A = {
        list.reduce(op)
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_implicits(self):
        """Should handle implicit conversions and parameters."""
        code = '''object Implicits {
    implicit class RichInt(val n: Int) extends AnyVal {
        def times(f: => Unit): Unit = (1 to n).foreach(_ => f)
    }

    implicit val defaultOrdering: Ordering[Int] = Ordering.Int
}

class Service(implicit ec: ExecutionContext) {
    def process(): Future[String] = Future("done")
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_for_comprehension(self):
        """Should handle for comprehensions."""
        code = '''object ForComprehension {
    def process(): List[Int] = {
        for {
            x <- List(1, 2, 3)
            y <- List(4, 5, 6)
            if x + y > 5
        } yield x * y
    }

    def flatMapExample(): Option[Int] = {
        for {
            a <- Some(1)
            b <- Some(2)
        } yield a + b
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''object Utf8Test {
    def getEmoji(): String = {
        "👍 Scala is awesome! 🚀"
    }

    def getUnicode(): String = {
        "Hello, 世界! ¿Cómo estás?"
    }

    def printGreeting(): Unit = {
        println("Привет мир!")
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

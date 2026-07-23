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

    def test_class_bases_populated(self):
        """BACK-645: `class Foo extends Bar with Baz` must populate bases —
        previously always returned [] for every Scala class (its
        'class_definition' node kind collides with Python's, so it silently
        fell through to Python's argument_list-shaped extraction)."""
        code = '''class Bar {}
trait Baz {}

class Foo extends Bar with Baz {
}

class Plain {
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = ScalaAnalyzer(temp_path)
            structure = analyzer.get_structure()
            classes = {c['name']: c for c in structure['classes']}

            self.assertEqual(classes['Bar']['bases'], [])
            self.assertEqual(classes['Foo']['bases'], ['Bar', 'Baz'])
            self.assertEqual(classes['Plain']['bases'], [])

        finally:
            os.unlink(temp_path)

    def test_instance_expression_callee_name(self):
        """BACK-730 note #17: Scala's `new ClassName(args)` parses to a
        distinct 'instance_expression' node (not PHP/C#/C++'s
        object_creation_expression/new_expression). get_structure()'s
        'calls' field — the one build_callers_index/calls:// actually
        depends on — must report 'new File', not the bare literal 'new'."""
        code = '''class Reader {
  def load(): Unit = {
    val f = new File("/tmp/x")
    println(f)
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
            functions = {fn['name']: fn for fn in structure['functions']}

            self.assertIn('new File', functions['load']['calls'])
            self.assertNotIn('new', functions['load']['calls'])
        finally:
            os.unlink(temp_path)

    def _structure_for(self, code):
        with tempfile.NamedTemporaryFile(mode='w', suffix='.scala', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name
        try:
            return ScalaAnalyzer(temp_path).get_structure()
        finally:
            os.unlink(temp_path)

    def test_infix_method_call_callee_name(self):
        """BACK-746 (twelfth calls-recall language): Scala infix method calls
        (`a :: b`, `list map f`, `xs filterNot p`) parse to 'infix_expression',
        a node kind that was absent from CALL_NODE_TYPES — every infix call was
        invisible to calls://. The `operator` field is the method name (an
        `identifier` for alphabetic infix, `operator_identifier` for symbolic
        operators). Emit the bare name."""
        code = '''class C {
  def run(): Unit = {
    val a = list map doubler
    val b = xs filterNot pred
    val c = x :: rest
    val d = p + q
  }
}
'''
        calls = {fn['name']: fn for fn in self._structure_for(code)['functions']}['run']['calls']
        self.assertIn('map', calls)
        self.assertIn('filterNot', calls)
        self.assertIn('::', calls)
        self.assertIn('+', calls)

    def test_qualified_constructor_callee_name(self):
        """BACK-747: `new java.io.File(...)` (a stable_type_identifier) and
        `new scala.Array[Byte](...)` (a stable_type_identifier inside a
        generic_type) must resolve to the simple type name, not be dropped."""
        code = '''class C {
  def run(): Unit = {
    val f = new java.io.File("x")
    val a = new scala.Array[Byte](8)
    val g = new Array[Int](4)
  }
}
'''
        calls = {fn['name']: fn for fn in self._structure_for(code)['functions']}['run']['calls']
        self.assertIn('new File', calls)
        self.assertIn('new Array', calls)

    def test_operator_named_method_definitions_in_outline(self):
        """BACK-746 residual: symbolic-named method definitions (`def +(o)`,
        `def ::(x)`, `def *` — Slick projections and operator overloads) use an
        `operator_identifier` name node, not an `identifier`. Without a
        dedicated name strategy they were absent from --outline/get_structure()
        (or mis-named after a body/param identifier), so any call inside their
        body had no caller scope. Each must appear under its own operator name."""
        code = '''class Vec {
  def +(o: Vec): Vec = o
  def ::(x: Int): Vec = this
  def * = (userName, repositoryName)
  def plain(): Int = 1
}
'''
        names = {fn['name'] for fn in self._structure_for(code)['functions']}
        self.assertIn('+', names)
        self.assertIn('::', names)
        self.assertIn('*', names)
        self.assertIn('plain', names)
        # The specific regression: an operator def must NOT be named after an
        # identifier in its body/params (`def +(o) = o` was mis-named "o").
        self.assertNotIn('o', names)


if __name__ == '__main__':
    unittest.main()

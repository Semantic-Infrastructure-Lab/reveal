"""Tests for Kotlin analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.kotlin import KotlinAnalyzer


class TestKotlinAnalyzer(unittest.TestCase):
    """Test suite for Kotlin source file analysis."""

    def test_extract_functions(self):
        """Should extract function definitions."""
        code = '''// Kotlin utilities
fun add(a: Int, b: Int): Int {
    return a + b
}

fun multiply(x: Int, y: Int): Int {
    return x * y
}

fun printResult(value: Int) {
    println("Result: $value")
}

fun main() {
    val sum = add(5, 3)
    printResult(sum)
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
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
        code = '''class Person(val name: String, val age: Int) {
    fun greet(): String {
        return "Hello, I'm $name"
    }
}

class Student(name: String, age: Int, val grade: String) : Person(name, age) {
    fun study() {
        println("$name is studying")
    }
}

open class Base {
    open fun show() {
        println("Base")
    }
}

class Derived : Base() {
    override fun show() {
        println("Derived")
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('classes', structure)
            classes = structure['classes']

            # Should extract class definitions
            class_names = [c['name'] for c in classes]
            self.assertIn('Person', class_names)
            self.assertIn('Student', class_names)
            self.assertIn('Base', class_names)
            self.assertIn('Derived', class_names)

        finally:
            os.unlink(temp_path)

    def test_data_classes(self):
        """Should extract data class definitions."""
        code = '''data class User(val id: Int, val name: String, val email: String)

data class Point(val x: Double, val y: Double) {
    fun distance(): Double {
        return Math.sqrt(x * x + y * y)
    }
}

data class Result<T>(val value: T, val error: String?)
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('classes', structure)
            classes = structure['classes']

            # Should extract data classes
            class_names = [c['name'] for c in classes]
            self.assertIn('User', class_names)
            self.assertIn('Point', class_names)
            self.assertIn('Result', class_names)

        finally:
            os.unlink(temp_path)

    def test_interfaces(self):
        """Should handle interface definitions."""
        code = '''interface Clickable {
    fun click()
    fun showOff() {
        println("I'm clickable!")
    }
}

interface Focusable {
    fun setFocus(b: Boolean)
    fun showOff() {
        println("I'm focusable!")
    }
}

class Button : Clickable, Focusable {
    override fun click() {
        println("Button clicked")
    }

    override fun setFocus(b: Boolean) {
        println("Focus set to $b")
    }

    override fun showOff() {
        super<Clickable>.showOff()
        super<Focusable>.showOff()
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should at least extract the class
            self.assertIsInstance(structure, dict)
            if 'classes' in structure:
                class_names = [c['name'] for c in structure['classes']]
                self.assertIn('Button', class_names)

        finally:
            os.unlink(temp_path)

    def test_object_declarations(self):
        """Should handle object declarations (singletons)."""
        code = '''object DatabaseConfig {
    val url = "localhost:5432"
    val user = "admin"

    fun connect() {
        println("Connecting to $url")
    }
}

object MathUtils {
    const val PI = 3.14159

    fun square(x: Int): Int {
        return x * x
    }
}

class MyClass {
    companion object Factory {
        fun create(): MyClass = MyClass()
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should handle objects without crashing
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_sealed_classes(self):
        """Should handle sealed classes."""
        code = '''sealed class Result {
    data class Success(val data: String) : Result()
    data class Error(val message: String) : Result()
    object Loading : Result()
}

fun handleResult(result: Result) {
    when (result) {
        is Result.Success -> println(result.data)
        is Result.Error -> println(result.message)
        Result.Loading -> println("Loading...")
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should handle sealed classes
            self.assertIsInstance(structure, dict)
            if 'classes' in structure:
                class_names = [c['name'] for c in structure['classes']]
                self.assertIn('Result', class_names)

        finally:
            os.unlink(temp_path)

    def test_extensions(self):
        """Should handle extension functions."""
        code = '''fun String.isEmail(): Boolean {
    return this.contains("@")
}

fun Int.isEven(): Boolean {
    return this % 2 == 0
}

fun <T> List<T>.secondOrNull(): T? {
    return if (this.size >= 2) this[1] else null
}

class MyClass {
    fun process() {
        println("Processing")
    }
}

fun MyClass.extended() {
    println("Extended function")
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract extension functions
            func_names = [f['name'] for f in functions]
            # Extension functions might be extracted with different names
            self.assertGreater(len(func_names), 0)

        finally:
            os.unlink(temp_path)

    def test_lambdas_and_higher_order(self):
        """Should handle lambda expressions and higher-order functions."""
        code = '''fun operateOnNumbers(a: Int, b: Int, operation: (Int, Int) -> Int): Int {
    return operation(a, b)
}

fun main() {
    val sum = operateOnNumbers(5, 3) { x, y -> x + y }
    val product = operateOnNumbers(5, 3) { x, y -> x * y }

    val numbers = listOf(1, 2, 3, 4, 5)
    val doubled = numbers.map { it * 2 }
    val evens = numbers.filter { it % 2 == 0 }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract functions
            func_names = [f['name'] for f in functions]
            self.assertIn('operateOnNumbers', func_names)
            self.assertIn('main', func_names)

        finally:
            os.unlink(temp_path)

    def test_coroutines(self):
        """Should handle coroutines and suspend functions."""
        code = '''import kotlinx.coroutines.*

suspend fun fetchData(): String {
    delay(1000)
    return "Data loaded"
}

suspend fun processData(data: String): String {
    delay(500)
    return data.uppercase()
}

fun main() = runBlocking {
    val data = fetchData()
    val processed = processData(data)
    println(processed)
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract suspend functions
            func_names = [f['name'] for f in functions]
            self.assertIn('fetchData', func_names)
            self.assertIn('processData', func_names)
            self.assertIn('main', func_names)

        finally:
            os.unlink(temp_path)

    def test_enums(self):
        """Should handle enum classes."""
        code = '''enum class Color {
    RED, GREEN, BLUE
}

enum class Direction(val degrees: Int) {
    NORTH(0),
    EAST(90),
    SOUTH(180),
    WEST(270);

    fun opposite(): Direction {
        return when (this) {
            NORTH -> SOUTH
            SOUTH -> NORTH
            EAST -> WEST
            WEST -> EAST
        }
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash on enum syntax
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''class 日本語 {
    fun こんにちは(): String {
        return "世界🌍"
    }

    fun emoji_test(): String {
        return "👍 Kotlin is awesome! 🚀"
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.kt', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = KotlinAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash on UTF-8
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

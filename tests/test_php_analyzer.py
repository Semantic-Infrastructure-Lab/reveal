"""Tests for PHP analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.php import PhpAnalyzer


class TestPhpAnalyzer(unittest.TestCase):
    """Test suite for PHP source file analysis."""

    def test_basic_function(self):
        """Should parse basic PHP function."""
        code = '''<?php
function greet($name) {
    return "Hello, " . $name . "!";
}

echo greet("World");
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            self.assertIn('functions', structure)
            self.assertGreater(len(structure['functions']), 0)

            # Check function name
            func_names = [fn['name'] for fn in structure['functions']]
            self.assertIn('greet', func_names)

        finally:
            os.unlink(temp_path)

    def test_class_definition(self):
        """Should extract class definitions."""
        code = '''<?php
class User {
    private $name;
    private $email;

    public function __construct($name, $email) {
        $this->name = $name;
        $this->email = $email;
    }

    public function getName() {
        return $this->name;
    }

    public function getEmail() {
        return $this->email;
    }

    public function setName($name) {
        $this->name = $name;
    }
}
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            self.assertIn('classes', structure)
            self.assertGreater(len(structure['classes']), 0)

            # Check class name
            class_names = [c['name'] for c in structure['classes']]
            self.assertIn('User', class_names)

        finally:
            os.unlink(temp_path)

    def test_namespace(self):
        """Should handle namespaces."""
        code = '''<?php
namespace App\\Controllers;

use App\\Models\\User;
use App\\Services\\AuthService;

class UserController {
    private $authService;

    public function __construct(AuthService $auth) {
        $this->authService = $auth;
    }

    public function index() {
        return User::all();
    }

    public function show($id) {
        return User::find($id);
    }
}
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_interface(self):
        """Should handle interface definitions."""
        code = '''<?php
interface Drawable {
    public function draw();
    public function resize($width, $height);
}

class Circle implements Drawable {
    private $radius;

    public function draw() {
        echo "Drawing circle";
    }

    public function resize($width, $height) {
        $this->radius = min($width, $height) / 2;
    }
}
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_trait(self):
        """Should handle traits."""
        code = '''<?php
trait Loggable {
    public function log($message) {
        echo "[LOG] " . $message . "\\n";
    }

    public function error($message) {
        echo "[ERROR] " . $message . "\\n";
    }
}

class Application {
    use Loggable;

    public function run() {
        $this->log("Application started");
    }
}
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_abstract_class(self):
        """Should handle abstract classes."""
        code = '''<?php
abstract class Animal {
    protected $name;

    public function __construct($name) {
        $this->name = $name;
    }

    abstract public function makeSound();

    public function getName() {
        return $this->name;
    }
}

class Dog extends Animal {
    public function makeSound() {
        return "Woof!";
    }
}

class Cat extends Animal {
    public function makeSound() {
        return "Meow!";
    }
}
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_static_methods(self):
        """Should handle static methods."""
        code = '''<?php
class MathUtils {
    public static function add($a, $b) {
        return $a + $b;
    }

    public static function multiply($a, $b) {
        return $a * $b;
    }

    public static function factorial($n) {
        if ($n <= 1) return 1;
        return $n * self::factorial($n - 1);
    }
}

echo MathUtils::add(5, 3);
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_anonymous_functions(self):
        """Should handle anonymous functions and closures."""
        code = '''<?php
$greet = function($name) {
    return "Hello, " . $name;
};

$multiplier = function($factor) {
    return function($number) use ($factor) {
        return $number * $factor;
    };
};

$double = $multiplier(2);
echo $double(5);

$numbers = [1, 2, 3, 4, 5];
$squared = array_map(function($n) {
    return $n * $n;
}, $numbers);
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_arrow_functions(self):
        """Should handle arrow functions (PHP 7.4+)."""
        code = '''<?php
$multiply = fn($x, $y) => $x * $y;

$numbers = [1, 2, 3, 4, 5];
$doubled = array_map(fn($n) => $n * 2, $numbers);

class Calculator {
    private $factor = 2;

    public function getMultiplier() {
        return fn($x) => $x * $this->factor;
    }
}
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_type_hints(self):
        """Should handle type hints (PHP 7+)."""
        code = '''<?php
declare(strict_types=1);

class TypedClass {
    private string $name;
    private int $age;
    private ?string $email;

    public function __construct(string $name, int $age, ?string $email = null) {
        $this->name = $name;
        $this->age = $age;
        $this->email = $email;
    }

    public function getName(): string {
        return $this->name;
    }

    public function getAge(): int {
        return $this->age;
    }

    public function getEmail(): ?string {
        return $this->email;
    }

    public function setEmail(?string $email): void {
        $this->email = $email;
    }
}
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''<?php
class Utf8Test {
    public function getEmoji() {
        return "👍 PHP is awesome! 🚀";
    }

    public function getUnicode() {
        return "Hello, 世界! ¿Cómo estás?";
    }

    public function printGreeting() {
        echo "Привет мир!";
    }
}
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_attributes(self):
        """Should handle attributes (PHP 8+)."""
        code = '''<?php
#[Attribute]
class Route {
    public function __construct(
        public string $path,
        public string $method = 'GET'
    ) {}
}

#[Route('/api/users', 'GET')]
class UserController {
    #[Route('/api/users/{id}', 'GET')]
    public function show(int $id) {
        return "User: " . $id;
    }

    #[Route('/api/users', 'POST')]
    public function store() {
        return "Created";
    }
}
?>
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = PhpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

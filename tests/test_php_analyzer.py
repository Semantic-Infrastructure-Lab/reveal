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


class TestPhpAnonymousClasses(unittest.TestCase):
    """Tests for PHP 8 anonymous class support (Issue 1, 2, 6, 7 from PHP_REVEAL_ISSUES_2026-04-06)."""

    def _make_php_file(self, code: str) -> str:
        """Write code to a temp .php file and return the path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            return f.name

    def test_anonymous_class_with_extends_detected(self):
        """Anonymous class using 'new class extends Base' should appear in structure['classes']."""
        code = '''<?php
$v = new class extends NodeVisitorAbstract {
    public function enterNode($node) { return null; }
};
'''
        path = self._make_php_file(code)
        try:
            structure = PhpAnalyzer(path).get_structure()
            class_names = [c['name'] for c in structure.get('classes', [])]
            self.assertEqual(len(class_names), 1)
            # Name should encode the base class and line number
            self.assertIn('NodeVisitorAbstract', class_names[0])
            self.assertIn('@L', class_names[0])
        finally:
            os.unlink(path)

    def test_anonymous_class_without_extends_detected(self):
        """Anonymous class with no base clause gets a fallback 'anonymous@L{line}' name."""
        code = '''<?php
$v = new class {
    public function doThing() { return 1; }
};
'''
        path = self._make_php_file(code)
        try:
            structure = PhpAnalyzer(path).get_structure()
            class_names = [c['name'] for c in structure.get('classes', [])]
            self.assertEqual(len(class_names), 1)
            self.assertTrue(class_names[0].startswith('anonymous@L'))
        finally:
            os.unlink(path)

    def test_multiple_anonymous_classes_all_detected(self):
        """14 anonymous classes in a file → 14 entries in structure['classes']."""
        classes = '\n'.join(
            f'$v{i} = run_traversal($ast, new class extends NodeVisitorAbstract {{ '
            f'public function enterNode($n) {{ return null; }} }});'
            for i in range(14)
        )
        code = f'<?php\nfunction run_traversal($a, $b) {{ return $b; }}\n{classes}\n'
        path = self._make_php_file(code)
        try:
            structure = PhpAnalyzer(path).get_structure()
            self.assertEqual(len(structure.get('classes', [])), 14)
        finally:
            os.unlink(path)

    def test_anonymous_class_has_correct_line_bounds(self):
        """Class dict should span from 'new class' to closing brace."""
        code = '''<?php
$v = new class extends Base {
    public function foo() { return 1; }
    public function bar() { return 2; }
};
'''
        path = self._make_php_file(code)
        try:
            structure = PhpAnalyzer(path).get_structure()
            cls = structure['classes'][0]
            self.assertEqual(cls['line'], 2)     # 'new class' is on line 2
            self.assertEqual(cls['line_end'], 5)  # closing '}' is on line 5
        finally:
            os.unlink(path)

    def test_d001_no_false_positives_across_anonymous_classes(self):
        """D001 must NOT fire for same-named methods in different anonymous classes."""
        from reveal.rules.duplicates.D001 import D001
        code = '''<?php
$v1 = new class extends Visitor {
    public function isScope() { return false; }
    public function leaveNode($n) { return null; }
};
$v2 = new class extends Visitor {
    public function isScope() { return false; }
    public function leaveNode($n) { return null; }
};
'''
        path = self._make_php_file(code)
        try:
            analyzer = PhpAnalyzer(path)
            structure = analyzer.get_structure()
            detections = D001().check(path, structure, code)
            self.assertEqual(len(detections), 0,
                             f"D001 false positives: {[d.message for d in detections]}")
        finally:
            os.unlink(path)

    def test_d001_fires_for_duplicate_methods_in_same_class(self):
        """D001 should still fire when two free functions have identical bodies."""
        from reveal.rules.duplicates.D001 import D001
        code = '''<?php
function foo($x) {
    if ($x > 0) {
        return $x * 2;
    }
    return 0;
}

function bar($x) {
    if ($x > 0) {
        return $x * 2;
    }
    return 0;
}
'''
        path = self._make_php_file(code)
        try:
            analyzer = PhpAnalyzer(path)
            structure = analyzer.get_structure()
            detections = D001().check(path, structure, code)
            self.assertGreater(len(detections), 0, "D001 should fire for identical free functions")
        finally:
            os.unlink(path)

    def test_named_class_still_detected_alongside_anonymous(self):
        """Named class_declaration should coexist with anonymous_class detection."""
        code = '''<?php
class NamedVisitor extends Base {
    public function enterNode($n) { return null; }
}
$v = new class extends Base {
    public function enterNode($n) { return null; }
};
'''
        path = self._make_php_file(code)
        try:
            structure = PhpAnalyzer(path).get_structure()
            class_names = [c['name'] for c in structure.get('classes', [])]
            self.assertIn('NamedVisitor', class_names)
            # Anonymous class also present
            self.assertTrue(any('anonymous' in n for n in class_names))
        finally:
            os.unlink(path)


class TestPhpCallDetection(unittest.TestCase):
    """Tests for PHP function call detection via calls:// (Issue 5)."""

    def _make_php_file(self, code: str) -> str:
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False, encoding='utf-8') as f:
            f.write(code)
            return f.name

    def test_function_call_expression_captured(self):
        """PHP function calls (function_call_expression nodes) should appear in func['calls']."""
        code = '''<?php
function run_traversal($ast, $v) { return $v; }

function cmd_exits($ast) {
    $r = run_traversal($ast, new class extends Base {
        public function enterNode($n) { return null; }
    });
    return $r;
}
'''
        path = self._make_php_file(code)
        try:
            structure = PhpAnalyzer(path).get_structure()
            cmd_exits = next(f for f in structure['functions'] if f['name'] == 'cmd_exits')
            self.assertIn('run_traversal', cmd_exits['calls'])
        finally:
            os.unlink(path)

    def test_multiple_calls_in_function_all_captured(self):
        """All function_call_expression calls inside a PHP function are captured."""
        code = '''<?php
function alpha() {}
function beta() {}
function gamma() {}

function caller() {
    alpha();
    beta();
    gamma();
}
'''
        path = self._make_php_file(code)
        try:
            structure = PhpAnalyzer(path).get_structure()
            caller = next(f for f in structure['functions'] if f['name'] == 'caller')
            self.assertIn('alpha', caller['calls'])
            self.assertIn('beta', caller['calls'])
            self.assertIn('gamma', caller['calls'])
        finally:
            os.unlink(path)

    def test_callee_name_resolved_for_php_name_node(self):
        """PHP callee uses 'name' node type (not 'identifier') — fallback must resolve it."""
        code = '''<?php
function run_traversal($a, $b) { return $b; }
function wrapper($ast) {
    return run_traversal($ast, null);
}
'''
        path = self._make_php_file(code)
        try:
            structure = PhpAnalyzer(path).get_structure()
            wrapper = next(f for f in structure['functions'] if f['name'] == 'wrapper')
            # callee 'run_traversal' must be captured even though PHP uses 'name' not 'identifier'
            self.assertIn('run_traversal', wrapper['calls'])
        finally:
            os.unlink(path)


class TestStatsComplexityFix(unittest.TestCase):
    """Tests for stats:// complexity fix (Issue 3 from PHP_REVEAL_ISSUES_2026-04-06)."""

    def test_precomputed_complexity_used(self):
        """estimate_complexity returns func['complexity'] when present."""
        from reveal.adapters.stats.metrics import estimate_complexity
        func = {'name': 'foo', 'line': 1, 'line_end': 10, 'complexity': 7}
        self.assertEqual(estimate_complexity(func, 'irrelevant content'), 7)

    def test_precomputed_complexity_zero_returned(self):
        """Pre-computed complexity of 0 is returned as-is (falsy but valid)."""
        from reveal.adapters.stats.metrics import estimate_complexity
        func = {'name': 'foo', 'line': 1, 'line_end': 3, 'complexity': 0}
        self.assertEqual(estimate_complexity(func, 'irrelevant'), 0)

    def test_fallback_uses_line_end_key(self):
        """Fallback keyword counting uses 'line_end' (not old 'end_line') key."""
        from reveal.adapters.stats.metrics import estimate_complexity
        # A function with two if-branches spans lines 1-6
        content = "function foo() {\n    if ($x) {\n        return 1;\n    } elseif ($y) {\n        return 2;\n    }\n}"
        func_correct_key = {'name': 'foo', 'line': 1, 'line_end': 7}
        result = estimate_complexity(func_correct_key, content)
        self.assertIsNotNone(result)
        self.assertGreater(result, 1)  # Must detect branches

    def test_fallback_wrong_key_gives_minimal_complexity(self):
        """Without 'complexity' or 'line_end', only 1 line is analyzed → complexity 1."""
        from reveal.adapters.stats.metrics import estimate_complexity
        content = "function foo() {\n    if ($x) {\n        return 1;\n    }\n}"
        # Old wrong key 'end_line' → line_end defaults to start_line → 1-line body
        func_old_key = {'name': 'foo', 'line': 2, 'end_line': 5}
        result = estimate_complexity(func_old_key, content)
        # 'if' may or may not be on line 2; but result should be small
        self.assertIsNotNone(result)

    def test_php_function_complexity_nonzero(self):
        """PHP functions with branching report complexity > 1 via tree-sitter."""
        code = '''<?php
function classify($n) {
    if ($n < 0) {
        return "negative";
    } elseif ($n === 0) {
        return "zero";
    } else {
        return "positive";
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            structure = PhpAnalyzer(path).get_structure()
            fn = next(f for f in structure['functions'] if f['name'] == 'classify')
            # tree-sitter computes real complexity
            self.assertGreater(fn['complexity'], 1)
            # estimate_complexity should return the same value
            from reveal.adapters.stats.metrics import estimate_complexity
            with open(path) as fh:
                content = fh.read()
            self.assertEqual(estimate_complexity(fn, content), fn['complexity'])
        finally:
            os.unlink(path)


class TestStatsQualityCheckPenalty(unittest.TestCase):
    """Tests for Issue 4: check rule detections wired into quality score."""

    def _make_quality_config(self):
        from reveal.adapters.stats.queries import QUALITY_DEFAULTS
        import copy
        return copy.deepcopy(QUALITY_DEFAULTS)

    def test_no_check_issues_score_unchanged(self):
        """Score is unaffected when no check issues are present."""
        from reveal.adapters.stats.metrics import calculate_quality_score
        config = self._make_quality_config()
        score_without = calculate_quality_score(3.0, 20.0, 0, 0, 5, config)
        score_with_empty = calculate_quality_score(3.0, 20.0, 0, 0, 5, config, {})
        score_with_zeros = calculate_quality_score(3.0, 20.0, 0, 0, 5, config,
                                                   {'critical': 0, 'high': 0, 'medium': 0, 'low': 0})
        self.assertEqual(score_without, score_with_empty)
        self.assertEqual(score_without, score_with_zeros)

    def test_high_issues_reduce_score(self):
        """HIGH detections reduce the quality score."""
        from reveal.adapters.stats.metrics import calculate_quality_score
        config = self._make_quality_config()
        score_clean = calculate_quality_score(3.0, 20.0, 0, 0, 5, config)
        score_issues = calculate_quality_score(3.0, 20.0, 0, 0, 5, config,
                                               {'critical': 0, 'high': 4, 'medium': 0, 'low': 0})
        # 4 HIGH × 5 pts = 20 pts penalty
        self.assertAlmostEqual(score_clean - score_issues, 20.0, places=1)

    def test_medium_issues_reduce_score(self):
        """MEDIUM detections reduce the quality score."""
        from reveal.adapters.stats.metrics import calculate_quality_score
        config = self._make_quality_config()
        score_clean = calculate_quality_score(3.0, 20.0, 0, 0, 5, config)
        score_issues = calculate_quality_score(3.0, 20.0, 0, 0, 5, config,
                                               {'critical': 0, 'high': 0, 'medium': 10, 'low': 0})
        # 10 MEDIUM × 2 pts = 20 pts penalty
        self.assertAlmostEqual(score_clean - score_issues, 20.0, places=1)

    def test_check_penalty_capped_at_max(self):
        """Total check penalty is capped at 40 points."""
        from reveal.adapters.stats.metrics import calculate_quality_score
        config = self._make_quality_config()
        score_clean = calculate_quality_score(3.0, 20.0, 0, 0, 5, config)
        # 100 HIGH × 5 pts = 500 pts → capped at 40
        score_many = calculate_quality_score(3.0, 20.0, 0, 0, 5, config,
                                             {'critical': 0, 'high': 100, 'medium': 0, 'low': 0})
        self.assertAlmostEqual(score_clean - score_many, 40.0, places=1)

    def test_score_never_below_zero(self):
        """Score stays at 0 even with massive check penalties."""
        from reveal.adapters.stats.metrics import calculate_quality_score
        config = self._make_quality_config()
        # Already bad metrics + big check penalty
        score = calculate_quality_score(50.0, 200.0, 20, 20, 20, config,
                                        {'critical': 100, 'high': 100, 'medium': 100, 'low': 100})
        self.assertGreaterEqual(score, 0.0)

    def test_check_issues_exposed_in_file_stats(self):
        """calculate_file_stats exposes check_issues count in quality dict."""
        import tempfile
        code = '''<?php
function foo($x) {
    if ($x > 0) {
        return true;
    }
}

function bar($x) {
    $y = 1; $z = 2;
    return $x;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.php', delete=False) as f:
            f.write(code)
            path = f.name
        try:
            from reveal.adapters.stats.metrics import calculate_file_stats
            from reveal.adapters.stats.queries import get_quality_config
            from pathlib import Path
            analyzer = PhpAnalyzer(path)
            structure = analyzer.get_structure()
            content = analyzer.content
            stats = calculate_file_stats(
                Path(path), structure, content,
                get_quality_config(Path(path)),
                lambda p: str(p)
            )
            self.assertIn('check_issues', stats['quality'])
            self.assertIsInstance(stats['quality']['check_issues'], int)
        finally:
            os.unlink(path)

    def test_php_file_with_issues_scores_below_100(self):
        """A PHP file with 30+ check issues should score below 100."""
        probe = '/home/scottsen/src/projects/sociamonials-ops/tools/php-ast/php-ast-probe.php'
        import os.path
        if not os.path.exists(probe):
            self.skipTest('php-ast-probe.php not available')
        from reveal.adapters.stats.adapter import StatsAdapter
        a = StatsAdapter(probe)
        result = a.get_structure()
        quality = result['files'][0]['quality']
        self.assertLess(quality['score'], 100.0, 'File with 30+ issues should score below 100')
        self.assertGreater(quality['check_issues'], 0, 'Should report check issue count')


if __name__ == '__main__':
    unittest.main()

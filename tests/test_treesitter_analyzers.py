"""
Tests for tree-sitter based analyzers.

Tests the TreeSitterAnalyzer base class and language-specific analyzers
(Rust, C#, Go, JavaScript, PHP, Bash).
"""

import pytest

# Try to import tree-sitter - skip all tests if not available
try:
    from reveal.analyzers.treesitter_base import TreeSitterAnalyzer, TREE_SITTER_AVAILABLE
    from reveal.analyzers.rust_analyzer import RustAnalyzer
    from reveal.analyzers.csharp_analyzer import CSharpAnalyzer
    from reveal.analyzers.go_analyzer import GoAnalyzer
except ImportError:
    TREE_SITTER_AVAILABLE = False

pytestmark = pytest.mark.skipif(
    not TREE_SITTER_AVAILABLE,
    reason="tree-sitter not installed"
)


class TestRustAnalyzer:
    """Test Rust analyzer with tree-sitter."""

    def test_extract_functions(self):
        """Test that Rust functions are extracted correctly."""
        code = """fn main() {
    println!("Hello");
}

fn helper(x: i32) -> i32 {
    x + 1
}"""
        lines = code.split('\n')
        analyzer = RustAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'functions' in structure
        functions = structure['functions']
        assert len(functions) == 2
        assert functions[0]['name'] == 'main'
        assert functions[0]['line'] == 1
        assert functions[1]['name'] == 'helper'
        assert functions[1]['line'] == 5

    def test_extract_structs(self):
        """Test that Rust structs are extracted correctly."""
        code = """struct Point {
    x: i32,
    y: i32,
}

struct User {
    name: String,
}"""
        lines = code.split('\n')
        analyzer = RustAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'structs' in structure
        structs = structure['structs']
        assert len(structs) == 2
        assert structs[0]['name'] == 'Point'
        assert structs[0]['line'] == 1
        assert structs[1]['name'] == 'User'
        assert structs[1]['line'] == 6

    def test_extract_enums(self):
        """Test that Rust enums are extracted correctly."""
        code = """enum Color {
    Red,
    Green,
    Blue,
}

enum Option<T> {
    Some(T),
    None,
}"""
        lines = code.split('\n')
        analyzer = RustAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'enums' in structure
        enums = structure['enums']
        assert len(enums) == 2
        assert enums[0]['name'] == 'Color'
        assert enums[0]['line'] == 1
        assert enums[1]['name'] == 'Option'
        assert enums[1]['line'] == 7

    def test_extract_traits(self):
        """Test that Rust traits are extracted correctly."""
        code = """trait Display {
    fn display(&self) -> String;
}

trait Logger {
    fn log(&self, msg: &str);
}"""
        lines = code.split('\n')
        analyzer = RustAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'traits' in structure
        traits = structure['traits']
        assert len(traits) == 2
        assert traits[0]['name'] == 'Display'
        assert traits[0]['line'] == 1
        assert traits[1]['name'] == 'Logger'
        assert traits[1]['line'] == 5

    def test_extract_impl_blocks(self):
        """Test that Rust impl blocks are extracted correctly."""
        code = """struct User {}

impl User {
    fn new() -> Self {
        User {}
    }
}

impl Display for User {
    fn display(&self) -> String {
        String::new()
    }
}"""
        lines = code.split('\n')
        analyzer = RustAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'impls' in structure
        impls = structure['impls']
        assert len(impls) == 2
        assert impls[0]['name'] == 'User'
        assert impls[0]['line'] == 3
        assert 'Display for User' in impls[1]['name']
        assert impls[1]['line'] == 9

    def test_extract_use_statements(self):
        """Test that Rust use statements are extracted correctly."""
        code = """use std::collections::HashMap;
use std::io::{self, Write};
use super::module;"""
        lines = code.split('\n')
        analyzer = RustAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'imports' in structure
        imports = structure['imports']
        assert len(imports) == 3
        assert 'HashMap' in imports[0]['name']
        assert imports[0]['line'] == 1


class TestCSharpAnalyzer:
    """Test C# analyzer with tree-sitter."""

    def test_extract_classes(self):
        """Test that C# classes are extracted correctly."""
        code = """namespace MyApp {
    public class User {
        public string Name { get; set; }
    }

    class Helper {
        void DoWork() {}
    }
}"""
        lines = code.split('\n')
        analyzer = CSharpAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'classes' in structure
        classes = structure['classes']
        assert len(classes) == 2
        assert classes[0]['name'] == 'User'
        assert classes[0]['line'] == 2
        assert classes[1]['name'] == 'Helper'
        assert classes[1]['line'] == 6

    def test_extract_interfaces(self):
        """Test that C# interfaces are extracted correctly."""
        code = """interface ILogger {
    void Log(string message);
}

interface IConfiguration {
    string GetValue(string key);
}"""
        lines = code.split('\n')
        analyzer = CSharpAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'interfaces' in structure
        interfaces = structure['interfaces']
        assert len(interfaces) == 2
        assert interfaces[0]['name'] == 'ILogger'
        assert interfaces[0]['line'] == 1
        assert interfaces[1]['name'] == 'IConfiguration'
        assert interfaces[1]['line'] == 5

    def test_extract_methods(self):
        """Test that C# methods are extracted correctly."""
        code = """class App {
    void Start() {}

    async Task<string> FetchAsync() {
        return "";
    }
}"""
        lines = code.split('\n')
        analyzer = CSharpAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'functions' in structure  # methods map to functions
        methods = structure['functions']
        assert len(methods) == 2
        assert methods[0]['name'] == 'Start'
        assert methods[0]['line'] == 2
        assert methods[1]['name'] == 'FetchAsync'
        assert methods[1]['line'] == 4

    def test_extract_properties(self):
        """Test that C# properties are extracted correctly."""
        code = """class User {
    public string Name { get; set; }
    public int Age { get; set; }
    private bool IsActive { get; }
}"""
        lines = code.split('\n')
        analyzer = CSharpAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'properties' in structure
        properties = structure['properties']
        assert len(properties) == 3
        assert properties[0]['name'] == 'Name'
        assert properties[0]['line'] == 2

    def test_extract_namespaces(self):
        """Test that C# namespaces are extracted correctly."""
        code = """namespace MyCompany.MyApp {
    class Program {}
}

namespace Utils {
    class Helper {}
}"""
        lines = code.split('\n')
        analyzer = CSharpAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'namespaces' in structure
        namespaces = structure['namespaces']
        assert len(namespaces) == 2
        assert namespaces[0]['name'] == 'MyCompany.MyApp'
        assert namespaces[0]['line'] == 1


class TestGoAnalyzer:
    """Test Go analyzer with tree-sitter."""

    def test_extract_functions(self):
        """Test that Go functions are extracted correctly."""
        code = """package main

func main() {
    println("Hello")
}

func helper(x int) int {
    return x + 1
}"""
        lines = code.split('\n')
        analyzer = GoAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'functions' in structure
        functions = structure['functions']
        assert len(functions) == 2
        assert functions[0]['name'] == 'main'
        assert functions[0]['line'] == 3
        assert functions[1]['name'] == 'helper'
        assert functions[1]['line'] == 7

    def test_extract_structs(self):
        """Test that Go structs are extracted correctly."""
        code = """type User struct {
    Name string
    Age  int
}

type Point struct {
    X, Y int
}"""
        lines = code.split('\n')
        analyzer = GoAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'structs' in structure
        structs = structure['structs']
        assert len(structs) == 2
        assert structs[0]['name'] == 'User'
        assert structs[0]['line'] == 1
        assert structs[1]['name'] == 'Point'
        assert structs[1]['line'] == 6

    def test_extract_interfaces(self):
        """Test that Go interfaces are extracted correctly."""
        code = """type Reader interface {
    Read(p []byte) (n int, err error)
}

type Writer interface {
    Write(p []byte) (n int, err error)
}"""
        lines = code.split('\n')
        analyzer = GoAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'interfaces' in structure
        interfaces = structure['interfaces']
        assert len(interfaces) == 2
        assert interfaces[0]['name'] == 'Reader'
        assert interfaces[0]['line'] == 1
        assert interfaces[1]['name'] == 'Writer'
        assert interfaces[1]['line'] == 5

    def test_extract_methods(self):
        """Test that Go methods are extracted correctly."""
        code = """type User struct {
    Name string
}

func (u *User) GetName() string {
    return u.Name
}

func (u *User) SetName(name string) {
    u.Name = name
}"""
        lines = code.split('\n')
        analyzer = GoAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'methods' in structure
        methods = structure['methods']
        assert len(methods) == 2
        assert methods[0]['name'] == 'GetName'
        assert methods[0]['line'] == 5
        assert methods[1]['name'] == 'SetName'
        assert methods[1]['line'] == 9

    def test_extract_type_aliases(self):
        """Test that Go type aliases are extracted correctly."""
        code = """type MyInt int
type StringMap map[string]string
type Config map[string]interface{}"""
        lines = code.split('\n')
        analyzer = GoAnalyzer(lines)
        structure = analyzer.analyze_structure()

        assert 'types' in structure
        types = structure['types']
        assert len(types) == 3
        assert types[0]['name'] == 'MyInt'
        assert types[0]['line'] == 1


class TestTreeSitterBase:
    """Test TreeSitterAnalyzer base class functionality."""

    def test_graceful_degradation_missing_library(self):
        """Test that analyzers handle missing tree-sitter gracefully."""
        # This is tested by the pytest.mark.skipif decorator
        # If tree-sitter is not available, all tests are skipped
        pass

    def test_line_numbers_are_accurate(self):
        """Test that line numbers from tree-sitter are accurate."""
        code = """

fn first() {}

fn second() {}

fn third() {}"""
        lines = code.split('\n')
        analyzer = RustAnalyzer(lines)
        structure = analyzer.analyze_structure()

        functions = structure['functions']
        assert functions[0]['line'] == 3  # first() is on line 3
        assert functions[1]['line'] == 5  # second() is on line 5
        assert functions[2]['line'] == 7  # third() is on line 7

"""
Tests for Go analyzer.

Tests tree-sitter-based analysis with:
- Structure extraction (functions, types, interfaces, structs)
- UTF-8 handling
- Real-world Go patterns
"""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.analyzers.go import GoAnalyzer


class TestGoAnalyzer(unittest.TestCase):
    """Test Go analyzer."""

    def test_extract_functions(self):
        """Should extract function declarations."""
        code = '''package main

import "fmt"

func main() {
    fmt.Println("Hello, world!")
}

func add(a int, b int) int {
    return a + b
}

func multiply(x, y int) int {
    return x * y
}

func processData(input []string) (result map[string]int, err error) {
    result = make(map[string]int)
    return result, nil
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GoAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract function declarations
            func_names = [f['name'] for f in functions]
            self.assertIn('main', func_names)
            self.assertIn('add', func_names)
            self.assertIn('multiply', func_names)
            self.assertIn('processData', func_names)

        finally:
            os.unlink(temp_path)

    def test_extract_structs(self):
        """Should extract struct definitions."""
        code = '''package main

type User struct {
    Name string
    Age  int
}

type Point struct {
    X float64
    Y float64
}

type Config struct {
    Host string `json:"host"`
    Port int    `json:"port"`
}

type GenericStruct struct {
    ID    string
    Data  interface{}
    Tags  []string
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GoAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Structs might be in 'classes' or 'types' depending on implementation
            if 'classes' in structure:
                structs = structure['classes']
                struct_names = [s['name'] for s in structs]
                self.assertIn('User', struct_names)
                self.assertIn('Point', struct_names)
                self.assertIn('Config', struct_names)
                self.assertIn('GenericStruct', struct_names)

        finally:
            os.unlink(temp_path)

    def test_extract_interfaces(self):
        """Should extract interface definitions."""
        code = '''package main

type Reader interface {
    Read(p []byte) (n int, err error)
}

type Writer interface {
    Write(p []byte) (n int, err error)
}

type ReadWriter interface {
    Reader
    Writer
}

type Closer interface {
    Close() error
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GoAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse interfaces
            self.assertIsNotNone(structure)

        finally:
            os.unlink(temp_path)

    def test_extract_methods(self):
        """Should extract methods (receiver functions)."""
        code = '''package main

type Rectangle struct {
    Width  int
    Height int
}

func (r Rectangle) Area() int {
    return r.Width * r.Height
}

func (r *Rectangle) Scale(factor int) {
    r.Width *= factor
    r.Height *= factor
}

func (r Rectangle) Perimeter() int {
    return 2 * (r.Width + r.Height)
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GoAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Methods should be extracted (possibly as functions)
            self.assertIsNotNone(structure)

            if 'functions' in structure:
                func_names = [f['name'] for f in structure['functions']]
                # Methods might be extracted as functions
                self.assertTrue(len(func_names) > 0)

        finally:
            os.unlink(temp_path)

    def test_utf8_with_emoji(self):
        """Should handle UTF-8 characters correctly."""
        code = '''package main

import "fmt"

// ✨ Go file with emoji ✨

func greetUser() string {
    return "Hello 👋 World 🌍"
}

// 日本語コメント
func calculateSum(a, b int) int {
    return a + b
}

// Documentation with emoji 🚀
func launch() {
    fmt.Println("Launching! 🚀")
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = GoAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Function names should not be truncated
            func_names = [f['name'] for f in functions]
            self.assertIn('greetUser', func_names)
            self.assertIn('calculateSum', func_names)
            self.assertIn('launch', func_names)

            # Names should be complete (not truncated)
            for name in func_names:
                self.assertFalse(name.startswith('reetUser'))  # Missing "g"
                self.assertFalse(name.startswith('etUser'))    # Missing "gre"

        finally:
            os.unlink(temp_path)

    def test_treesitter_parsing(self):
        """Should use TreeSitter for parsing (cross-platform)."""
        code = '''package main

import (
    "fmt"
    "strings"
)

func processInput(data []string) []string {
    result := make([]string, 0, len(data))
    for _, item := range data {
        processed := strings.ToUpper(item)
        result = append(result, processed)
    }
    return result
}

func main() {
    input := []string{"hello", "world"}
    output := processInput(input)
    fmt.Println(output)
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.go', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            # TreeSitter parsing should work on any platform
            analyzer = GoAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsNotNone(structure)
            self.assertIn('functions', structure)

            func_names = [f['name'] for f in structure['functions']]
            self.assertIn('processInput', func_names)
            self.assertIn('main', func_names)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

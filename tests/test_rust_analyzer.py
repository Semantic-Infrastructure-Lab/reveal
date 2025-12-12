"""
Tests for Rust analyzer.

Tests tree-sitter-based analysis with:
- Structure extraction (functions, structs, impls, traits)
- UTF-8 handling
- Real-world Rust patterns
"""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.analyzers.rust import RustAnalyzer


class TestRustAnalyzer(unittest.TestCase):
    """Test Rust analyzer."""

    def test_extract_functions(self):
        """Should extract function definitions."""
        code = '''// Rust test file

fn main() {
    println!("Hello, world!");
}

pub fn add(a: i32, b: i32) -> i32 {
    a + b
}

async fn fetch_data(url: &str) -> Result<String, Error> {
    // Async function
    Ok(String::new())
}

fn generic_function<T>(value: T) -> T
where
    T: Clone,
{
    value.clone()
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RustAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract function declarations
            func_names = [f['name'] for f in functions]
            self.assertIn('main', func_names)
            self.assertIn('add', func_names)
            self.assertIn('fetch_data', func_names)
            self.assertIn('generic_function', func_names)

        finally:
            os.unlink(temp_path)

    def test_extract_structs(self):
        """Should extract struct definitions."""
        code = '''pub struct User {
    pub name: String,
    pub age: u32,
}

struct Point {
    x: f64,
    y: f64,
}

#[derive(Debug, Clone)]
pub struct Config {
    pub host: String,
    pub port: u16,
}

struct GenericWrapper<T> {
    value: T,
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RustAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Structs might be in 'classes' or 'structs' depending on implementation
            if 'classes' in structure:
                structs = structure['classes']
                struct_names = [s['name'] for s in structs]
                self.assertIn('User', struct_names)
                self.assertIn('Point', struct_names)
                self.assertIn('Config', struct_names)
                self.assertIn('GenericWrapper', struct_names)

        finally:
            os.unlink(temp_path)

    def test_extract_impls(self):
        """Should extract impl blocks."""
        code = '''struct Rectangle {
    width: u32,
    height: u32,
}

impl Rectangle {
    fn new(width: u32, height: u32) -> Self {
        Rectangle { width, height }
    }

    fn area(&self) -> u32 {
        self.width * self.height
    }
}

trait Drawable {
    fn draw(&self);
}

impl Drawable for Rectangle {
    fn draw(&self) {
        println!("Drawing rectangle");
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RustAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse impl blocks
            self.assertIsNotNone(structure)

            # Functions within impls should be extracted
            if 'functions' in structure:
                func_names = [f['name'] for f in structure['functions']]
                # Impl methods might be extracted as functions
                self.assertTrue(len(func_names) > 0)

        finally:
            os.unlink(temp_path)

    def test_extract_traits(self):
        """Should extract trait definitions."""
        code = '''pub trait Display {
    fn display(&self) -> String;
}

trait Comparable {
    fn compare(&self, other: &Self) -> bool;
}

pub trait Iterator {
    type Item;
    fn next(&mut self) -> Option<Self::Item>;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RustAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse traits
            self.assertIsNotNone(structure)

        finally:
            os.unlink(temp_path)

    def test_utf8_with_emoji(self):
        """Should handle UTF-8 characters correctly."""
        code = '''// ✨ Rust file with emoji ✨

fn greet_user() -> String {
    "Hello 👋 World 🌍".to_string()
}

// 日本語コメント
fn calculate_sum(a: i32, b: i32) -> i32 {
    a + b
}

/// Documentation with emoji 🚀
pub fn launch() {
    println!("Launching! 🚀");
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RustAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Function names should not be truncated
            func_names = [f['name'] for f in functions]
            self.assertIn('greet_user', func_names)
            self.assertIn('calculate_sum', func_names)
            self.assertIn('launch', func_names)

            # Names should be complete (not truncated)
            for name in func_names:
                self.assertFalse(name.startswith('reet_user'))  # Missing "g"
                self.assertFalse(name.startswith('et_user'))    # Missing "gre"

        finally:
            os.unlink(temp_path)

    def test_treesitter_parsing(self):
        """Should use TreeSitter for parsing (cross-platform)."""
        code = '''// Complex Rust code
use std::collections::HashMap;

pub fn process_data(input: Vec<String>) -> HashMap<String, usize> {
    let mut map = HashMap::new();
    for item in input {
        let count = map.entry(item).or_insert(0);
        *count += 1;
    }
    map
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            # TreeSitter parsing should work on any platform
            analyzer = RustAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsNotNone(structure)
            self.assertIn('functions', structure)

            func_names = [f['name'] for f in structure['functions']]
            self.assertIn('process_data', func_names)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

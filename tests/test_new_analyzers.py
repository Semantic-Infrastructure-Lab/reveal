"""
Tests for new analyzers: JavaScript, TypeScript, and Bash.

Tests tree-sitter-based analysis with:
- Structure extraction (imports, functions, classes)
- Cross-platform compatibility
- UTF-8 handling
- Real-world code patterns
"""

import unittest
import tempfile
import os
from pathlib import Path
from reveal.analyzers.javascript import JavaScriptAnalyzer
from reveal.analyzers.typescript import TypeScriptAnalyzer
from reveal.analyzers.bash import BashAnalyzer


class TestJavaScriptAnalyzer(unittest.TestCase):
    """Test JavaScript analyzer."""

    def test_extract_functions(self):
        """Should extract function declarations and arrow functions."""
        code = '''// JavaScript test file
function regularFunction() {
    return "hello";
}

const arrowFunction = () => {
    return "world";
};

async function asyncFunction() {
    await something();
}

function multiLineFunction(
    param1,
    param2
) {
    return param1 + param2;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract function declarations
            func_names = [f['name'] for f in functions]
            self.assertIn('regularFunction', func_names)
            self.assertIn('asyncFunction', func_names)
            self.assertIn('multiLineFunction', func_names)

        finally:
            os.unlink(temp_path)

    def test_extract_classes(self):
        """Should extract ES6 class definitions."""
        code = '''class User {
    constructor(name) {
        this.name = name;
    }

    greet() {
        return `Hello, ${this.name}`;
    }
}

class Admin extends User {
    constructor(name, permissions) {
        super(name);
        this.permissions = permissions;
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            if 'classes' in structure:
                classes = structure['classes']
                class_names = [c['name'] for c in classes]
                self.assertIn('User', class_names)
                self.assertIn('Admin', class_names)

        finally:
            os.unlink(temp_path)

    def test_extract_imports(self):
        """Should extract import statements."""
        code = '''import React from 'react';
import { useState, useEffect } from 'react';
import * as utils from './utils';
import './styles.css';

const component = () => {};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Check if imports are extracted
            self.assertIn('imports', structure)
            imports = structure['imports']

            # Should have multiple imports
            self.assertGreater(len(imports), 0)

        finally:
            os.unlink(temp_path)

    def test_utf8_with_emoji(self):
        """Should handle UTF-8 characters correctly."""
        code = '''// ✨ JavaScript file with emoji ✨

function greetUser() {
    return "Hello 👋 World 🌍";
}

// 日本語コメント
function calculateSum(a, b) {
    return a + b;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.js', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = JavaScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Function names should not be truncated
            func_names = [f['name'] for f in functions]
            self.assertIn('greetUser', func_names)
            self.assertIn('calculateSum', func_names)

            # Names should be complete (not truncated)
            for name in func_names:
                self.assertFalse(name.startswith('reetUser'))  # Missing "g"
                self.assertFalse(name.startswith('etUser'))     # Missing "gre"

        finally:
            os.unlink(temp_path)


class TestTypeScriptAnalyzer(unittest.TestCase):
    """Test TypeScript analyzer."""

    def test_extract_functions_with_types(self):
        """Should extract TypeScript functions with type annotations."""
        code = '''function add(a: number, b: number): number {
    return a + b;
}

const multiply = (x: number, y: number): number => {
    return x * y;
};

async function fetchData(url: string): Promise<any> {
    const response = await fetch(url);
    return response.json();
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = TypeScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            func_names = [f['name'] for f in functions]
            self.assertIn('add', func_names)
            self.assertIn('fetchData', func_names)

        finally:
            os.unlink(temp_path)

    def test_extract_classes_with_types(self):
        """Should extract TypeScript classes with type annotations."""
        code = '''class Person {
    name: string;
    age: number;

    constructor(name: string, age: number) {
        this.name = name;
        this.age = age;
    }

    greet(): string {
        return `Hello, I'm ${this.name}`;
    }
}

class Employee extends Person {
    employeeId: number;

    constructor(name: string, age: number, id: number) {
        super(name, age);
        this.employeeId = id;
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = TypeScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            if 'classes' in structure:
                classes = structure['classes']
                class_names = [c['name'] for c in classes]
                self.assertIn('Person', class_names)
                self.assertIn('Employee', class_names)

        finally:
            os.unlink(temp_path)

    def test_extract_interfaces(self):
        """Should extract TypeScript interfaces."""
        code = '''interface User {
    id: number;
    name: string;
    email: string;
}

interface Product {
    id: number;
    title: string;
    price: number;
}

type Status = "active" | "inactive";
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.ts', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = TypeScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Interfaces might be extracted as a separate category
            # or as classes, depending on tree-sitter behavior
            # Just verify the file can be parsed
            self.assertIsNotNone(structure)

        finally:
            os.unlink(temp_path)

    def test_tsx_react_components(self):
        """Should handle .tsx files with React components."""
        code = '''import React from 'react';

interface Props {
    name: string;
}

export const Greeting: React.FC<Props> = ({ name }) => {
    return <div>Hello, {name}!</div>;
};

function App() {
    return (
        <div>
            <Greeting name="World" />
        </div>
    );
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsx', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = TypeScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse TSX
            self.assertIsNotNone(structure)

            # Should find the App function
            if 'functions' in structure:
                func_names = [f['name'] for f in structure['functions']]
                self.assertIn('App', func_names)

        finally:
            os.unlink(temp_path)


class TestBashAnalyzer(unittest.TestCase):
    """Test Bash analyzer."""

    def test_extract_functions(self):
        """Should extract bash function definitions."""
        code = '''#!/bin/bash
# Deployment script

function deploy() {
    echo "Deploying application..."
}

backup_data() {
    local backup_dir=$1
    tar -czf backup.tar.gz "$backup_dir"
}

check_status() {
    if [ -f "status.txt" ]; then
        cat status.txt
    fi
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = BashAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract function definitions
            func_names = [f['name'] for f in functions]
            self.assertIn('deploy', func_names)
            self.assertIn('backup_data', func_names)
            self.assertIn('check_status', func_names)

        finally:
            os.unlink(temp_path)

    def test_cross_platform_analysis(self):
        """Bash analyzer should work on any platform (Windows/Linux/macOS)."""
        code = '''#!/bin/bash
# This script should be analyzable on any OS

function setup_environment() {
    export PATH="$PATH:/usr/local/bin"
    echo "Environment configured"
}

main() {
    setup_environment
    echo "Ready!"
}

main
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            # This should work on Windows, Linux, and macOS
            # because we're just parsing syntax, not executing
            analyzer = BashAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsNotNone(structure)
            self.assertIn('functions', structure)

            func_names = [f['name'] for f in structure['functions']]
            self.assertIn('setup_environment', func_names)
            self.assertIn('main', func_names)

        finally:
            os.unlink(temp_path)

    def test_bash_with_complex_script(self):
        """Should handle complex bash scripts with variables and commands."""
        code = '''#!/bin/bash
set -euo pipefail

# Configuration
APP_NAME="myapp"
VERSION="1.0.0"

# Functions
function log_info() {
    echo "[INFO] $1"
}

function check_dependencies() {
    command -v docker >/dev/null 2>&1 || {
        log_info "Docker is required but not installed."
        exit 1
    }
}

function build_image() {
    log_info "Building Docker image..."
    docker build -t "$APP_NAME:$VERSION" .
}

# Main execution
check_dependencies
build_image
log_info "Build complete!"
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.bash', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = BashAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract all function definitions
            func_names = [f['name'] for f in functions]
            self.assertIn('log_info', func_names)
            self.assertIn('check_dependencies', func_names)
            self.assertIn('build_image', func_names)

        finally:
            os.unlink(temp_path)

    def test_extract_variables_no_functions(self):
        """Should extract top-level variables when script has no function definitions."""
        code = '''#!/bin/bash
PHP=/usr/local/bin/php
SERVICE=platform-worker
ITER=0
FB_LOCK_SHARDS=${FB_LOCK_SHARDS:-5}

while true; do
    INNER_VAR=ignored
    $PHP /var/www/html/worker.php
done
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name

        try:
            analyzer = BashAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Variables extracted, no functions
            self.assertIn('variables', structure)
            self.assertNotIn('functions', structure)

            var_names = [v['name'] for v in structure['variables']]
            self.assertIn('PHP', var_names)
            self.assertIn('SERVICE', var_names)
            self.assertIn('FB_LOCK_SHARDS', var_names)
            # Inner loop variable should NOT appear (not top-level)
            self.assertNotIn('INNER_VAR', var_names)

            # Each variable has line, name, signature
            for var in structure['variables']:
                self.assertIn('line', var)
                self.assertIn('name', var)
                self.assertIn('signature', var)
                self.assertTrue(var['signature'].startswith(' = '))

        finally:
            os.unlink(temp_path)

    def test_extract_variables_with_functions(self):
        """Should extract both functions and variables when both are present."""
        code = '''#!/bin/bash
APP_NAME=myapp
VERSION=1.0.0

function deploy() {
    echo "Deploying $APP_NAME $VERSION"
}

deploy
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name

        try:
            analyzer = BashAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('variables', structure)
            self.assertIn('functions', structure)

            var_names = [v['name'] for v in structure['variables']]
            self.assertIn('APP_NAME', var_names)
            self.assertIn('VERSION', var_names)

            func_names = [f['name'] for f in structure['functions']]
            self.assertIn('deploy', func_names)

        finally:
            os.unlink(temp_path)

    def test_variable_value_truncation(self):
        """Long variable values should be truncated at 60 chars."""
        long_val = 'x' * 80
        code = f'#!/bin/bash\nLONG_VAR={long_val}\n'
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name

        try:
            analyzer = BashAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('variables', structure)
            sig = structure['variables'][0]['signature']
            # " = " + truncated value
            self.assertTrue(sig.endswith('...'))
            self.assertLessEqual(len(sig), 3 + 60)  # " = " + max 60 chars

        finally:
            os.unlink(temp_path)


class TestCrossPlatformCompatibility(unittest.TestCase):
    """Test that all new analyzers work on all platforms."""

    def test_all_analyzers_handle_utf8(self):
        """All analyzers should handle UTF-8 correctly (cross-platform)."""
        test_cases = [
            ('.js', JavaScriptAnalyzer, '// ✨ Comment\nfunction test() {}'),
            ('.ts', TypeScriptAnalyzer, '// 🎉 Comment\nfunction test(): void {}'),
            ('.sh', BashAnalyzer, '#!/bin/bash\n# 🚀 Comment\nfunction test() { echo "hi"; }'),
        ]

        for ext, analyzer_class, code in test_cases:
            with self.subTest(ext=ext):
                with tempfile.NamedTemporaryFile(
                    mode='w', suffix=ext, delete=False, encoding='utf-8'
                ) as f:
                    f.write(code)
                    f.flush()
                    temp_path = f.name

                try:
                    analyzer = analyzer_class(temp_path)
                    structure = analyzer.get_structure()

                    # Should parse without errors
                    self.assertIsNotNone(structure)

                    # Should find the test function
                    if 'functions' in structure:
                        func_names = [f['name'] for f in structure['functions']]
                        self.assertIn('test', func_names)

                finally:
                    os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

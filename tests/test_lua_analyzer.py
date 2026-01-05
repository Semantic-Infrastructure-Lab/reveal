"""Tests for Lua analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.lua import LuaAnalyzer


class TestLuaAnalyzer(unittest.TestCase):
    """Test suite for Lua source file analysis.

    Note: Lua tree-sitter support is currently limited. These tests verify
    that the analyzer doesn't crash on various Lua syntax patterns.
    """

    def test_basic_file_parsing(self):
        """Should parse Lua files without crashing."""
        code = '''function greet()
    print("Hello, World!")
end

greet()
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = LuaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should return a dict, even if empty
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_multiple_functions(self):
        """Should handle multiple function definitions."""
        code = '''function add(a, b)
    return a + b
end

function multiply(x, y)
    return x * y
end

function printResult(value)
    print("Result: " .. tostring(value))
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = LuaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_local_functions(self):
        """Should handle local function definitions."""
        code = '''local function helper()
    return 42
end

function main()
    local value = helper()
    print(value)
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = LuaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_table_operations(self):
        """Should handle table operations."""
        code = '''local my_table = {
    name = "Alice",
    age = 30,
    city = "NYC"
}

function iterate_table(tbl)
    for k, v in pairs(tbl) do
        print(k, v)
    end
end

iterate_table(my_table)
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = LuaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_conditional_logic(self):
        """Should handle conditional statements."""
        code = '''function classify(x)
    if x > 0 then
        return "positive"
    elseif x < 0 then
        return "negative"
    else
        return "zero"
    end
end

local result = classify(10)
print(result)
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = LuaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_loops(self):
        """Should handle different loop types."""
        code = '''function sum_range(n)
    local total = 0
    for i = 1, n do
        total = total + i
    end
    return total
end

function while_loop(n)
    local i = 0
    while i < n do
        i = i + 1
    end
    return i
end

function repeat_loop(n)
    local i = 0
    repeat
        i = i + 1
    until i >= n
    return i
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = LuaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_string_operations(self):
        """Should handle string operations."""
        code = '''function concatenate(a, b)
    return a .. b
end

function multiline_string()
    local text = [[
        This is a
        multiline string
    ]]
    return text
end

local result = concatenate("Hello", " World")
print(result)
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = LuaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''-- UTF-8 test
function emoji_test()
    return "👍 Lua is awesome! 🚀"
end

function unicode_test()
    return "Hello, 世界! ¿Cómo estás?"
end

print(emoji_test())
print(unicode_test())
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.lua', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = LuaAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash on UTF-8
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

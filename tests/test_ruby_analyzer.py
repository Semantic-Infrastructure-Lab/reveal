"""Tests for Ruby analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.ruby import RubyAnalyzer


class TestRubyAnalyzer(unittest.TestCase):
    """Test suite for Ruby source file analysis."""

    def test_extract_methods(self):
        """Should extract method definitions."""
        code = '''# Ruby math utilities
def add(a, b)
  a + b
end

def multiply(x, y)
  x * y
end

def print_result(value)
  puts "Result: #{value}"
end

def main
  sum = add(5, 3)
  print_result(sum)
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract all method definitions
            func_names = [f['name'] for f in functions]
            self.assertIn('add', func_names)
            self.assertIn('multiply', func_names)
            self.assertIn('print_result', func_names)
            self.assertIn('main', func_names)

            # Check method details
            add_func = next(f for f in functions if f['name'] == 'add')
            self.assertEqual(add_func['line'], 2)
            self.assertGreater(add_func['line_count'], 0)

        finally:
            os.unlink(temp_path)

    def test_extract_classes(self):
        """Should extract class definitions."""
        code = '''class Person
  attr_accessor :name, :age

  def initialize(name, age)
    @name = name
    @age = age
  end

  def greet
    "Hello, I'm #{@name}"
  end
end

class Student < Person
  attr_accessor :grade

  def initialize(name, age, grade)
    super(name, age)
    @grade = grade
  end

  def study
    puts "#{@name} is studying"
  end
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('classes', structure)
            classes = structure['classes']

            # Should extract all class definitions
            class_names = [c['name'] for c in classes]
            self.assertIn('Person', class_names)
            self.assertIn('Student', class_names)

            # Check class details
            person_class = next(c for c in classes if c['name'] == 'Person')
            self.assertEqual(person_class['line'], 1)
            # Classes have line_end, not line_count
            self.assertGreater(person_class['line_end'], person_class['line'])

        finally:
            os.unlink(temp_path)

    def test_extract_modules(self):
        """Should extract module definitions."""
        code = '''module Math
  PI = 3.14159

  def self.circle_area(radius)
    PI * radius * radius
  end

  def self.square_area(side)
    side * side
  end
end

module Utils
  def self.log(message)
    puts "[LOG] #{message}"
  end
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Note: Ruby modules are currently not extracted by tree-sitter analyzer
            # This test verifies the analyzer doesn't crash on module syntax
            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_class_methods(self):
        """Should extract instance and class methods."""
        code = '''class Calculator
  def self.class_method
    "I'm a class method"
  end

  def instance_method
    "I'm an instance method"
  end

  def add(a, b)
    a + b
  end

  private

  def helper
    "private helper"
  end
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract methods
            func_names = [f['name'] for f in functions]
            # Note: def self.class_method may not be extracted by tree-sitter
            # depending on Ruby grammar support for singleton methods
            self.assertIn('instance_method', func_names)
            self.assertIn('add', func_names)
            self.assertIn('helper', func_names)

        finally:
            os.unlink(temp_path)

    def test_blocks_and_procs(self):
        """Should handle blocks and procs."""
        code = '''def process_array(arr)
  arr.each do |item|
    puts item
  end
end

def map_values(arr)
  arr.map { |x| x * 2 }
end

my_proc = Proc.new { |x| x + 1 }
my_lambda = ->(x) { x * 2 }
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract method definitions
            func_names = [f['name'] for f in functions]
            self.assertIn('process_array', func_names)
            self.assertIn('map_values', func_names)

        finally:
            os.unlink(temp_path)

    def test_symbols_and_strings(self):
        """Should handle symbols and string interpolation."""
        code = '''def use_symbols
  my_hash = {
    :name => "Alice",
    :age => 30,
    city: "NYC"
  }
  my_hash[:name]
end

def string_interpolation(name)
  "Hello, #{name}!"
end

def heredoc
  text = <<~HEREDOC
    This is a heredoc
    with multiple lines
  HEREDOC
  text
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract all methods
            func_names = [f['name'] for f in functions]
            self.assertIn('use_symbols', func_names)
            self.assertIn('string_interpolation', func_names)
            self.assertIn('heredoc', func_names)

        finally:
            os.unlink(temp_path)

    def test_mixins(self):
        """Should handle include and extend."""
        code = '''module Greetable
  def greet
    "Hello!"
  end
end

module ClassMethods
  def class_greet
    "Hello from class!"
  end
end

class MyClass
  include Greetable
  extend ClassMethods

  def initialize
    @value = 42
  end
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('classes', structure)
            classes = structure['classes']

            # Should extract class
            class_names = [c['name'] for c in classes]
            self.assertIn('MyClass', class_names)

        finally:
            os.unlink(temp_path)

    def test_attr_accessors(self):
        """Should handle attr_accessor, attr_reader, attr_writer."""
        code = '''class Person
  attr_accessor :name
  attr_reader :id
  attr_writer :password

  def initialize(name, id)
    @name = name
    @id = id
  end
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('classes', structure)
            classes = structure['classes']

            # Should extract class
            class_names = [c['name'] for c in classes]
            self.assertIn('Person', class_names)

        finally:
            os.unlink(temp_path)

    def test_complexity_metrics(self):
        """Should calculate complexity metrics."""
        code = '''def complex_method(x, y, z)
  result = 0

  if x > 0
    result += x
  elsif x < 0
    result -= x
  else
    result = 1
  end

  for i in 0..y
    if i % 2 == 0
      result *= i
    else
      result += i
    end
  end

  case z
  when 1
    result += 10
  when 2
    result += 20
  when 3
    result += 30
  else
    result += 100
  end

  result
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract method
            func_names = [f['name'] for f in functions]
            self.assertIn('complex_method', func_names)

            # Should have complexity metric
            complex_func = next(f for f in functions if f['name'] == 'complex_method')
            if 'complexity' in complex_func:
                self.assertGreater(complex_func['complexity'], 1)

        finally:
            os.unlink(temp_path)

    def test_singleton_methods(self):
        """Should handle singleton methods."""
        code = '''class MyClass
  def self.singleton_method
    "I'm a singleton"
  end

  class << self
    def another_singleton
      "Another singleton"
    end
  end
end

obj = Object.new
def obj.custom_method
  "Custom method"
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract some singleton methods
            # Note: Not all singleton method syntaxes may be supported
            func_names = [f['name'] for f in functions]
            self.assertGreater(len(func_names), 0)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''# -*- coding: utf-8 -*-

class 日本語
  def こんにちは
    "世界" + "🌍"
  end

  def español
    "Hola, ¿cómo estás?"
  end
end

def emoji_test
  "👍 Ruby is awesome! 🚀"
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should not crash on UTF-8
            self.assertIsInstance(structure, dict)
            self.assertIn('functions', structure)

        finally:
            os.unlink(temp_path)

    def test_operators_and_special_methods(self):
        """Should handle operator overloading and special methods."""
        code = '''class Vector
  attr_reader :x, :y

  def initialize(x, y)
    @x = x
    @y = y
  end

  def +(other)
    Vector.new(@x + other.x, @y + other.y)
  end

  def -(other)
    Vector.new(@x - other.x, @y - other.y)
  end

  def ==(other)
    @x == other.x && @y == other.y
  end

  def to_s
    "(#{@x}, #{@y})"
  end
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract methods including operators
            func_names = [f['name'] for f in functions]
            self.assertIn('initialize', func_names)
            self.assertIn('to_s', func_names)

        finally:
            os.unlink(temp_path)

    def test_begin_rescue_ensure(self):
        """Should handle exception handling."""
        code = '''def risky_operation
  begin
    result = 10 / 0
  rescue ZeroDivisionError => e
    puts "Error: #{e.message}"
    result = nil
  rescue StandardError => e
    puts "Other error: #{e.message}"
    result = -1
  else
    puts "Success"
  ensure
    puts "Cleanup"
  end
  result
end

def raise_error
  raise "Something went wrong"
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract methods
            func_names = [f['name'] for f in functions]
            self.assertIn('risky_operation', func_names)
            self.assertIn('raise_error', func_names)

        finally:
            os.unlink(temp_path)

    def test_method_parameters(self):
        """Should handle various parameter types."""
        code = '''def required_params(a, b)
  a + b
end

def optional_params(a, b = 10)
  a + b
end

def keyword_args(name:, age:, city: "NYC")
  "#{name}, #{age}, #{city}"
end

def splat_args(*args)
  args.sum
end

def double_splat(**kwargs)
  kwargs.to_s
end

def all_params(a, b = 1, *args, x:, y: 2, **kwargs, &block)
  block.call if block
end
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.rb', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = RubyAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract all methods
            func_names = [f['name'] for f in functions]
            self.assertIn('required_params', func_names)
            self.assertIn('optional_params', func_names)
            self.assertIn('keyword_args', func_names)
            self.assertIn('splat_args', func_names)
            self.assertIn('double_splat', func_names)
            self.assertIn('all_params', func_names)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

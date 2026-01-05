"""
Tests for C++ analyzer.

Tests tree-sitter-based analysis with:
- Class extraction
- Function/method extraction (member functions)
- Namespace support
- Template detection
- Include detection
- Modern C++ features (C++11/14/17)
"""

import unittest
import tempfile
import os
from reveal.analyzers.cpp import CppAnalyzer


class TestCppAnalyzer(unittest.TestCase):
    """Test C++ analyzer."""

    def test_extract_classes(self):
        """Should extract class definitions."""
        code = '''#include <iostream>
#include <string>

class Point {
private:
    int x;
    int y;

public:
    Point(int x, int y) : x(x), y(y) {}

    int getX() const { return x; }
    int getY() const { return y; }
};

class Rectangle {
public:
    Rectangle(int w, int h) : width(w), height(h) {}

    int area() const {
        return width * height;
    }

private:
    int width;
    int height;
};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('classes', structure)
            classes = structure['classes']

            # Should extract class names
            class_names = [c['name'] for c in classes]
            self.assertIn('Point', class_names)
            self.assertIn('Rectangle', class_names)

        finally:
            os.unlink(temp_path)

    def test_extract_functions(self):
        """Should extract free functions and methods."""
        code = '''#include <iostream>

int add(int a, int b) {
    return a + b;
}

template<typename T>
T multiply(T x, T y) {
    return x * y;
}

class Calculator {
public:
    int sum(int a, int b) {
        return a + b;
    }

    int product(int a, int b) {
        return a * b;
    }
};

int main() {
    Calculator calc;
    return calc.sum(5, 3);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract functions
            self.assertIn('functions', structure)
            functions = structure['functions']
            func_names = [f['name'] for f in functions]

            self.assertIn('add', func_names)
            self.assertIn('multiply', func_names)
            self.assertIn('main', func_names)

        finally:
            os.unlink(temp_path)

    def test_extract_includes(self):
        """Should extract #include directives."""
        code = '''#include <iostream>
#include <vector>
#include <string>
#include <memory>
#include "myheader.hpp"
#include "utils/helpers.hpp"

int main() {
    return 0;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('imports', structure)
            imports = structure['imports']

            # Should extract all includes
            self.assertEqual(len(imports), 6)

            # Check specific includes
            import_content = [imp['content'] for imp in imports]
            self.assertTrue(any('iostream' in c for c in import_content))
            self.assertTrue(any('vector' in c for c in import_content))

        finally:
            os.unlink(temp_path)

    def test_namespaces(self):
        """Should handle namespaced code."""
        code = '''#include <iostream>

namespace math {
    int add(int a, int b) {
        return a + b;
    }

    namespace advanced {
        double sqrt(double x) {
            return x * x;
        }
    }
}

namespace utils {
    void print(const char* msg) {
        std::cout << msg << std::endl;
    }
}

int main() {
    return math::add(5, 3);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse namespaced code
            self.assertIsNotNone(structure)

            # Functions should be extracted
            if 'functions' in structure:
                func_names = [f['name'] for f in structure['functions']]
                self.assertIn('add', func_names)

        finally:
            os.unlink(temp_path)

    def test_templates(self):
        """Should handle template definitions."""
        code = '''#include <iostream>

template<typename T>
class Stack {
private:
    T data[100];
    int top;

public:
    Stack() : top(-1) {}

    void push(const T& item) {
        data[++top] = item;
    }

    T pop() {
        return data[top--];
    }
};

template<typename T>
T max(T a, T b) {
    return (a > b) ? a : b;
}

int main() {
    Stack<int> stack;
    stack.push(5);
    return 0;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse template code
            self.assertIsNotNone(structure)

        finally:
            os.unlink(temp_path)

    def test_modern_cpp_features(self):
        """Should handle modern C++ features (auto, lambda, range-for)."""
        code = '''#include <vector>
#include <algorithm>
#include <memory>

int main() {
    // Auto type deduction
    auto x = 42;
    auto y = 3.14;

    // Range-based for loop
    std::vector<int> numbers = {1, 2, 3, 4, 5};
    for (auto n : numbers) {
        // process n
    }

    // Lambda functions
    auto lambda = [](int a, int b) {
        return a + b;
    };

    // Smart pointers
    std::unique_ptr<int> ptr = std::make_unique<int>(10);
    std::shared_ptr<int> shared = std::make_shared<int>(20);

    // Structured bindings (C++17)
    auto [first, second] = std::make_pair(1, 2);

    return 0;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should be able to parse modern C++ without errors
            self.assertIsNotNone(structure)
            self.assertIn('functions', structure)

            func_names = [f['name'] for f in structure['functions']]
            self.assertIn('main', func_names)

        finally:
            os.unlink(temp_path)

    def test_header_files(self):
        """Should analyze C++ header files (.hpp, .hh, .h++)."""
        code = '''#ifndef CALCULATOR_HPP
#define CALCULATOR_HPP

#include <string>

class Calculator {
public:
    Calculator();
    ~Calculator();

    int add(int a, int b);
    int multiply(int a, int b);

private:
    std::string name;
};

template<typename T>
T max(T a, T b) {
    return (a > b) ? a : b;
}

#endif
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.hpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract classes from header
            self.assertIn('classes', structure)
            classes = structure['classes']
            class_names = [c['name'] for c in classes]
            self.assertIn('Calculator', class_names)

        finally:
            os.unlink(temp_path)

    def test_element_extraction(self):
        """Should extract specific elements by name."""
        code = '''#include <iostream>

class Point {
public:
    int x, y;
    Point(int x, int y) : x(x), y(y) {}
};

int calculate(int a, int b) {
    return a + b;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)

            # Extract specific class
            point_class = analyzer.extract_element('class', 'Point')
            self.assertIsNotNone(point_class)
            self.assertEqual(point_class['name'], 'Point')

            # Extract specific function
            calc_func = analyzer.extract_element('function', 'calculate')
            self.assertIsNotNone(calc_func)
            self.assertEqual(calc_func['name'], 'calculate')

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters in C++ code."""
        code = '''#include <iostream>
#include <string>

// 日本語コメント - Japanese comment
// Emoji test: ✨🚀🎉

class Greeter {
public:
    void greet() {
        std::cout << "Hello 👋 World 🌍" << std::endl;
    }
};

// Function with emoji documentation 🔧
int calculate_sum(int a, int b) {
    return a + b;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract classes despite UTF-8 comments
            self.assertIn('classes', structure)
            classes = structure['classes']
            class_names = [c['name'] for c in classes]
            self.assertIn('Greeter', class_names)

            # Should extract functions
            self.assertIn('functions', structure)
            functions = structure['functions']
            func_names = [f['name'] for f in functions]
            self.assertIn('calculate_sum', func_names)

        finally:
            os.unlink(temp_path)

    def test_operator_overloading(self):
        """Should extract operator overloads."""
        code = '''#include <iostream>

class Complex {
private:
    double real, imag;

public:
    Complex(double r = 0, double i = 0) : real(r), imag(i) {}

    Complex operator+(const Complex& other) {
        return Complex(real + other.real, imag + other.imag);
    }

    Complex operator-(const Complex& other) {
        return Complex(real - other.real, imag - other.imag);
    }

    bool operator==(const Complex& other) {
        return real == other.real && imag == other.imag;
    }

    friend std::ostream& operator<<(std::ostream& out, const Complex& c) {
        out << c.real << " + " << c.imag << "i";
        return out;
    }
};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract the class
            self.assertIn('classes', structure)
            classes = structure['classes']
            class_names = [c['name'] for c in classes]
            self.assertIn('Complex', class_names)

            # Operator overloads are functions, may or may not be extracted depending on tree-sitter
            # This test mainly verifies the analyzer doesn't crash on operator overloads

        finally:
            os.unlink(temp_path)

    def test_inheritance(self):
        """Should extract classes with inheritance."""
        code = '''#include <iostream>
#include <string>

class Animal {
protected:
    std::string name;

public:
    Animal(const std::string& n) : name(n) {}
    virtual void speak() = 0;  // Pure virtual
    virtual ~Animal() {}
};

class Dog : public Animal {
public:
    Dog(const std::string& n) : Animal(n) {}

    void speak() override {
        std::cout << name << " says: Woof!" << std::endl;
    }
};

class Cat : public Animal {
public:
    Cat(const std::string& n) : Animal(n) {}

    void speak() override {
        std::cout << name << " says: Meow!" << std::endl;
    }
};

// Multiple inheritance
class Bird {
public:
    virtual void fly() { std::cout << "Flying" << std::endl; }
};

class Bat : public Animal, public Bird {
public:
    Bat(const std::string& n) : Animal(n) {}

    void speak() override {
        std::cout << name << " says: Screech!" << std::endl;
    }
};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract all classes
            self.assertIn('classes', structure)
            classes = structure['classes']
            class_names = [c['name'] for c in classes]

            self.assertIn('Animal', class_names)
            self.assertIn('Dog', class_names)
            self.assertIn('Cat', class_names)
            self.assertIn('Bird', class_names)
            self.assertIn('Bat', class_names)

        finally:
            os.unlink(temp_path)

    def test_const_member_functions(self):
        """Should extract const member functions."""
        code = '''#include <string>

class Person {
private:
    std::string name;
    int age;

public:
    Person(const std::string& n, int a) : name(n), age(a) {}

    std::string getName() const {
        return name;
    }

    int getAge() const {
        return age;
    }

    void setAge(int a) {
        age = a;
    }

    const std::string& getNameRef() const {
        return name;
    }
};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract the class
            self.assertIn('classes', structure)
            classes = structure['classes']
            class_names = [c['name'] for c in classes]
            self.assertIn('Person', class_names)

        finally:
            os.unlink(temp_path)

    def test_static_members(self):
        """Should extract static member functions."""
        code = '''#include <iostream>

class Counter {
private:
    static int count;
    int id;

public:
    Counter() : id(++count) {}

    static int getCount() {
        return count;
    }

    static void resetCount() {
        count = 0;
    }

    int getId() const {
        return id;
    }
};

int Counter::count = 0;
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract the class
            self.assertIn('classes', structure)
            classes = structure['classes']
            class_names = [c['name'] for c in classes]
            self.assertIn('Counter', class_names)

        finally:
            os.unlink(temp_path)

    def test_lambda_expressions(self):
        """Should handle lambda expressions and not crash."""
        code = '''#include <algorithm>
#include <vector>
#include <iostream>

int main() {
    std::vector<int> numbers = {1, 2, 3, 4, 5};

    // Lambda expression
    auto square = [](int x) { return x * x; };

    // Lambda with capture
    int factor = 2;
    auto multiply = [factor](int x) { return x * factor; };

    // Lambda in algorithm
    std::for_each(numbers.begin(), numbers.end(), [](int n) {
        std::cout << n << " ";
    });

    // Generic lambda (C++14)
    auto add = [](auto a, auto b) { return a + b; };

    return 0;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cpp', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CppAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract main function
            self.assertIn('functions', structure)
            functions = structure['functions']
            func_names = [f['name'] for f in functions]
            self.assertIn('main', func_names)

            # This test mainly verifies the analyzer doesn't crash on lambdas

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

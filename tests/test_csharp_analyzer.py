"""Tests for C# analyzer."""

import unittest
import tempfile
import os
from reveal.analyzers.csharp import CSharpAnalyzer


class TestCSharpAnalyzer(unittest.TestCase):
    """Test suite for C# source file analysis."""

    def test_basic_class(self):
        """Should parse basic C# class."""
        code = '''using System;

namespace HelloWorld
{
    public class Program
    {
        public static void Main(string[] args)
        {
            Console.WriteLine("Hello, World!");
        }
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CSharpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            self.assertIn('classes', structure)
            self.assertGreater(len(structure['classes']), 0)

            # Check class name
            class_names = [c['name'] for c in structure['classes']]
            self.assertIn('Program', class_names)

        finally:
            os.unlink(temp_path)

    def test_class_with_methods(self):
        """Should extract methods from class."""
        code = '''public class Calculator
{
    private int value;

    public Calculator()
    {
        this.value = 0;
    }

    public int Add(int a, int b)
    {
        return a + b;
    }

    public int Subtract(int a, int b)
    {
        return a - b;
    }

    private int Multiply(int a, int b)
    {
        return a * b;
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CSharpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)
            self.assertIn('functions', structure)

            # Should have methods
            func_names = [f['name'] for f in structure.get('functions', [])]
            self.assertIn('Add', func_names)

        finally:
            os.unlink(temp_path)

    def test_interface(self):
        """Should handle interface definitions."""
        code = '''public interface IDrawable
{
    void Draw();
    void Resize(int width, int height);
}

public class Circle : IDrawable
{
    public void Draw()
    {
        Console.WriteLine("Drawing circle");
    }

    public void Resize(int width, int height)
    {
        Console.WriteLine("Resizing");
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CSharpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_enum(self):
        """Should handle enum definitions."""
        code = '''public enum DayOfWeek
{
    Monday,
    Tuesday,
    Wednesday,
    Thursday,
    Friday,
    Saturday,
    Sunday
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CSharpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_properties(self):
        """Should handle C# properties."""
        code = '''public class Person
{
    private string _name;

    public string Name
    {
        get { return _name; }
        set { _name = value; }
    }

    public int Age { get; set; }

    public string FullName => $"{FirstName} {LastName}";

    public string FirstName { get; private set; }
    public string LastName { get; private set; }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CSharpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_generics(self):
        """Should handle generic types."""
        code = '''using System.Collections.Generic;

public class GenericBox<T>
{
    private T _content;

    public GenericBox(T content)
    {
        _content = content;
    }

    public T GetContent()
    {
        return _content;
    }

    public void SetContent(T content)
    {
        _content = content;
    }
}

public class Pair<TKey, TValue>
{
    public TKey Key { get; set; }
    public TValue Value { get; set; }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CSharpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_async_methods(self):
        """Should handle async/await methods."""
        code = '''using System.Threading.Tasks;

public class AsyncService
{
    public async Task<string> FetchDataAsync()
    {
        await Task.Delay(1000);
        return "Data fetched";
    }

    public async Task ProcessAsync()
    {
        var data = await FetchDataAsync();
        Console.WriteLine(data);
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CSharpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_attributes(self):
        """Should handle C# attributes."""
        code = '''using System;

[Serializable]
public class DataClass
{
    [Obsolete("Use NewMethod instead")]
    public void OldMethod()
    {
        // deprecated
    }

    public void NewMethod()
    {
        // current
    }
}

[AttributeUsage(AttributeTargets.Class)]
public class CustomAttribute : Attribute
{
    public string Name { get; set; }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CSharpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_linq(self):
        """Should handle LINQ expressions."""
        code = '''using System.Linq;
using System.Collections.Generic;

public class LinqExample
{
    public void ProcessItems()
    {
        var items = new List<int> { 1, 2, 3, 4, 5 };

        var even = items.Where(x => x % 2 == 0);

        var squared = from n in items
                      where n > 2
                      select n * n;
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CSharpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters properly."""
        code = '''public class Utf8Test
{
    public string GetEmoji()
    {
        return "👍 C# is awesome! 🚀";
    }

    public string GetUnicode()
    {
        return "Hello, 世界! ¿Cómo estás?";
    }

    public void PrintGreeting()
    {
        Console.WriteLine("Привет мир!");
    }
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.cs', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CSharpAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIsInstance(structure, dict)

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

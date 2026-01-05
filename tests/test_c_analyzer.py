"""
Tests for C analyzer.

Tests tree-sitter-based analysis with:
- Function extraction (definitions and declarations)
- Struct extraction
- Include detection
- Header file analysis
- UTF-8 handling
- Real-world C patterns
"""

import unittest
import tempfile
import os
from reveal.analyzers.c import CAnalyzer


class TestCAnalyzer(unittest.TestCase):
    """Test C analyzer."""

    def test_extract_functions(self):
        """Should extract function definitions."""
        code = '''#include <stdio.h>
#include <stdlib.h>

int add(int a, int b) {
    return a + b;
}

int multiply(int x, int y) {
    return x * y;
}

void printResult(int value) {
    printf("Result: %d\\n", value);
}

int main(void) {
    int sum = add(5, 3);
    printResult(sum);
    return 0;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Should extract all function definitions
            func_names = [f['name'] for f in functions]
            self.assertIn('add', func_names)
            self.assertIn('multiply', func_names)
            self.assertIn('printResult', func_names)
            self.assertIn('main', func_names)

            # Check function details
            add_func = next(f for f in functions if f['name'] == 'add')
            self.assertEqual(add_func['line'], 4)
            self.assertEqual(add_func['line_count'], 3)

        finally:
            os.unlink(temp_path)

    def test_extract_structs(self):
        """Should extract struct definitions."""
        code = '''#include <stdint.h>

struct Point {
    int x;
    int y;
};

struct Rectangle {
    struct Point top_left;
    struct Point bottom_right;
};

typedef struct {
    char name[50];
    int age;
    float height;
} Person;

struct Node {
    int data;
    struct Node *next;
};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('structs', structure)
            structs = structure['structs']

            # Should extract struct names
            struct_names = [s['name'] for s in structs]
            self.assertIn('Point', struct_names)
            self.assertIn('Rectangle', struct_names)
            self.assertIn('Node', struct_names)

        finally:
            os.unlink(temp_path)

    def test_extract_includes(self):
        """Should extract #include directives."""
        code = '''#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "myheader.h"
#include "utils/helpers.h"

int main(void) {
    return 0;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('imports', structure)
            imports = structure['imports']

            # Should extract all includes
            self.assertEqual(len(imports), 5)

            # Check specific includes
            import_content = [imp['content'] for imp in imports]
            self.assertTrue(any('stdio.h' in c for c in import_content))
            self.assertTrue(any('stdlib.h' in c for c in import_content))
            self.assertTrue(any('myheader.h' in c for c in import_content))

        finally:
            os.unlink(temp_path)

    def test_header_file(self):
        """Should analyze C header files (.h)."""
        code = '''#ifndef MYLIB_H
#define MYLIB_H

#include <stdint.h>

struct Point {
    int x;
    int y;
};

int calculate(int a, int b);
void process_data(const char *input);
void *allocate_memory(size_t size);

#endif
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.h', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract struct from header
            self.assertIn('structs', structure)
            structs = structure['structs']
            struct_names = [s['name'] for s in structs]
            self.assertIn('Point', struct_names)

            # Should extract includes
            self.assertIn('imports', structure)

        finally:
            os.unlink(temp_path)

    def test_element_extraction(self):
        """Should extract specific elements by name."""
        code = '''#include <stdio.h>

int add(int a, int b) {
    return a + b;
}

int multiply(int x, int y) {
    return x * y;
}

struct Point {
    int x;
    int y;
};
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CAnalyzer(temp_path)

            # Extract specific function
            add_func = analyzer.extract_element('function', 'add')
            self.assertIsNotNone(add_func)
            self.assertEqual(add_func['name'], 'add')
            self.assertIn('return a + b', add_func['source'])

            # Extract struct
            point_struct = analyzer.extract_element('struct', 'Point')
            self.assertIsNotNone(point_struct)
            self.assertEqual(point_struct['name'], 'Point')

        finally:
            os.unlink(temp_path)

    def test_complex_code(self):
        """Should handle complex C code with pointers, arrays, and nested structures."""
        code = '''#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_SIZE 100
#define MIN(a,b) ((a) < (b) ? (a) : (b))

typedef struct {
    char *data;
    size_t size;
    size_t capacity;
} Buffer;

Buffer* create_buffer(size_t initial_capacity) {
    Buffer *buf = (Buffer*)malloc(sizeof(Buffer));
    if (buf == NULL) {
        return NULL;
    }

    buf->data = (char*)malloc(initial_capacity);
    buf->size = 0;
    buf->capacity = initial_capacity;

    return buf;
}

void destroy_buffer(Buffer *buf) {
    if (buf != NULL) {
        free(buf->data);
        free(buf);
    }
}

int append_data(Buffer *buf, const char *data, size_t len) {
    if (buf->size + len > buf->capacity) {
        size_t new_capacity = buf->capacity * 2;
        char *new_data = (char*)realloc(buf->data, new_capacity);
        if (new_data == NULL) {
            return -1;
        }
        buf->data = new_data;
        buf->capacity = new_capacity;
    }

    memcpy(buf->data + buf->size, data, len);
    buf->size += len;
    return 0;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CAnalyzer(temp_path)
            structure = analyzer.get_structure()

            # Should extract functions
            self.assertIn('functions', structure)
            functions = structure['functions']
            func_names = [f['name'] for f in functions]
            self.assertIn('create_buffer', func_names)
            self.assertIn('destroy_buffer', func_names)
            self.assertIn('append_data', func_names)

        finally:
            os.unlink(temp_path)

    def test_utf8_handling(self):
        """Should handle UTF-8 characters in comments and strings."""
        code = '''#include <stdio.h>

// 日本語コメント - Japanese comment
// Emoji test: ✨🚀🎉

/* Multi-line comment with UTF-8:
 * Русский текст - Russian text
 * 中文 - Chinese
 * العربية - Arabic
 */

int greet_user() {
    printf("Hello 👋 World 🌍\\n");
    return 0;
}

// Function with emoji documentation 🔧
int calculate_sum(int a, int b) {
    return a + b;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Function names should be extracted correctly despite UTF-8 comments
            func_names = [f['name'] for f in functions]
            self.assertIn('greet_user', func_names)
            self.assertIn('calculate_sum', func_names)

            # Names should be complete
            for name in func_names:
                self.assertTrue(len(name) > 0)

        finally:
            os.unlink(temp_path)

    def test_static_inline_functions(self):
        """Should extract static and inline functions."""
        code = '''#include <stdio.h>

static int internal_helper(int x) {
    return x * 2;
}

inline int fast_add(int a, int b) {
    return a + b;
}

static inline int fast_multiply(int a, int b) {
    return a * b;
}

extern int public_function(void);

int main(void) {
    return internal_helper(5) + fast_add(1, 2);
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']
            func_names = [f['name'] for f in functions]

            # Should extract all function types
            self.assertIn('internal_helper', func_names)
            self.assertIn('fast_add', func_names)
            self.assertIn('fast_multiply', func_names)
            self.assertIn('main', func_names)

        finally:
            os.unlink(temp_path)

    def test_complexity_metrics(self):
        """Should calculate complexity metrics for functions."""
        code = '''#include <stdio.h>

int simple_function(int x) {
    return x + 1;
}

int complex_function(int x, int y) {
    int result = 0;

    if (x > 0) {
        for (int i = 0; i < y; i++) {
            if (i % 2 == 0) {
                result += i;
            } else {
                result -= i;
            }
        }
    } else if (x < 0) {
        while (y > 0) {
            result++;
            y--;
        }
    } else {
        result = 42;
    }

    return result;
}
'''
        with tempfile.NamedTemporaryFile(mode='w', suffix='.c', delete=False, encoding='utf-8') as f:
            f.write(code)
            f.flush()
            temp_path = f.name

        try:
            analyzer = CAnalyzer(temp_path)
            structure = analyzer.get_structure()

            self.assertIn('functions', structure)
            functions = structure['functions']

            # Find complex function
            complex_func = next(f for f in functions if f['name'] == 'complex_function')

            # Should have complexity and depth metrics
            self.assertIn('complexity', complex_func)
            self.assertIn('depth', complex_func)

            # Complex function should have higher complexity
            simple_func = next(f for f in functions if f['name'] == 'simple_function')
            self.assertGreater(complex_func['complexity'], simple_func['complexity'])

        finally:
            os.unlink(temp_path)


if __name__ == '__main__':
    unittest.main()

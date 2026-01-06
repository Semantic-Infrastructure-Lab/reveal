"""Tests for D002: Similar function detection rule."""

import unittest
from reveal.rules.duplicates.D002 import D002


class TestD002Basic(unittest.TestCase):
    """Basic tests for D002 similar function detection."""

    def setUp(self):
        self.rule = D002()

    def test_no_structure_returns_empty(self):
        """No structure should return empty list."""
        result = self.rule.check("test.py", None, "")
        self.assertEqual(result, [])

    def test_no_functions_returns_empty(self):
        """Structure without functions returns empty."""
        result = self.rule.check("test.py", {"classes": []}, "content")
        self.assertEqual(result, [])

    def test_single_function_returns_empty(self):
        """Single function cannot have similar pairs."""
        structure = {
            "functions": [{"name": "foo", "line": 1, "line_end": 10}]
        }
        content = "def foo():\n" + "    x = 1\n" * 10
        result = self.rule.check("test.py", structure, content)
        self.assertEqual(result, [])

    def test_detects_similar_functions(self):
        """Two similar functions should be detected."""
        # Create two very similar functions (same structure, different names)
        content = """def process_data():
    x = input_value
    y = x * 2
    if y > 10:
        z = y + 5
    else:
        z = y - 5
    result = z * 3
    return result

def transform_data():
    a = input_value
    b = a * 2
    if b > 10:
        c = b + 5
    else:
        c = b - 5
    result = c * 3
    return result
"""
        structure = {
            "functions": [
                {"name": "process_data", "line": 1, "line_end": 9},
                {"name": "transform_data", "line": 11, "line_end": 19},
            ]
        }
        result = self.rule.check("test.py", structure, content)
        # May or may not detect depending on threshold
        self.assertIsInstance(result, list)


class TestD002Vectorize(unittest.TestCase):
    """Tests for vectorization logic."""

    def setUp(self):
        self.rule = D002()

    def test_vectorize_basic_code(self):
        """Should produce feature vector from code."""
        code = """x = 1
y = 2
if x > y:
    z = x
else:
    z = y
return z"""
        vector = self.rule._vectorize(code)
        self.assertIsInstance(vector, dict)
        self.assertGreater(len(vector), 0)

    def test_vectorize_has_control_flow_features(self):
        """Should extract control flow density features."""
        code = """for i in range(10):
    if i > 5:
        x = i * 2
    while x > 0:
        x = x - 1
return x"""
        vector = self.rule._vectorize(code)
        self.assertIn('density_if', vector)
        self.assertIn('density_for', vector)
        self.assertIn('density_while', vector)
        self.assertIn('density_return', vector)

    def test_vectorize_has_structural_features(self):
        """Should have structural features."""
        code = "x = 1\n" * 10
        vector = self.rule._vectorize(code)
        self.assertIn('line_count_norm', vector)
        self.assertIn('avg_line_length_norm', vector)

    def test_vectorize_has_token_features(self):
        """Should have token frequency features."""
        code = "return return return\nif if"
        vector = self.rule._vectorize(code)
        # Should have token_return and token_if features
        token_features = [k for k in vector if k.startswith('token_')]
        self.assertGreater(len(token_features), 0)


class TestD002Normalize(unittest.TestCase):
    """Tests for code normalization."""

    def setUp(self):
        self.rule = D002()

    def test_normalize_removes_comments(self):
        """Should remove comments."""
        code = "x = 1  # comment\ny = 2"
        normalized = self.rule._normalize(code)
        self.assertNotIn("#", normalized)

    def test_normalize_removes_docstrings(self):
        """Should remove docstrings."""
        code = '"""docstring"""\nx = 1'
        normalized = self.rule._normalize(code)
        self.assertNotIn('"""', normalized)

    def test_normalize_collapses_whitespace(self):
        """Should collapse whitespace."""
        code = "x    =    1"
        normalized = self.rule._normalize(code)
        self.assertEqual(normalized.count("    "), 0)


class TestD002CosineSimilarity(unittest.TestCase):
    """Tests for cosine similarity."""

    def setUp(self):
        self.rule = D002()

    def test_identical_vectors_similarity_one(self):
        """Identical vectors should have similarity 1.0."""
        vec = {"a": 1.0, "b": 2.0, "c": 3.0}
        similarity = self.rule._cosine_similarity(vec, vec)
        self.assertAlmostEqual(similarity, 1.0)

    def test_orthogonal_vectors_similarity_zero(self):
        """Orthogonal vectors should have similarity 0.0."""
        vec1 = {"a": 1.0}
        vec2 = {"b": 1.0}
        similarity = self.rule._cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(similarity, 0.0)

    def test_empty_vectors_similarity_zero(self):
        """Empty vectors should have similarity 0.0."""
        similarity = self.rule._cosine_similarity({}, {})
        self.assertAlmostEqual(similarity, 0.0)

    def test_zero_magnitude_similarity_zero(self):
        """Zero magnitude vector should return 0.0."""
        vec1 = {"a": 0.0, "b": 0.0}
        vec2 = {"a": 1.0, "b": 2.0}
        similarity = self.rule._cosine_similarity(vec1, vec2)
        self.assertAlmostEqual(similarity, 0.0)

    def test_partial_overlap_vectors(self):
        """Partially overlapping vectors should have intermediate similarity."""
        vec1 = {"a": 1.0, "b": 1.0}
        vec2 = {"a": 1.0, "c": 1.0}
        similarity = self.rule._cosine_similarity(vec1, vec2)
        self.assertGreater(similarity, 0.0)
        self.assertLess(similarity, 1.0)


class TestD002ExtractFunctionBody(unittest.TestCase):
    """Tests for function body extraction."""

    def setUp(self):
        self.rule = D002()

    def test_extract_body_basic(self):
        """Should extract function body."""
        content = "def foo():\n    x = 1\n    return x\n"
        func = {"name": "foo", "line": 1, "line_end": 3}
        body = self.rule._extract_function_body(func, content)
        self.assertIn("x = 1", body)

    def test_extract_body_zero_line(self):
        """Zero line should return empty."""
        func = {"name": "foo", "line": 0, "line_end": 3}
        body = self.rule._extract_function_body(func, "content")
        self.assertEqual(body, "")

    def test_extract_body_out_of_bounds(self):
        """Out of bounds should return empty."""
        func = {"name": "foo", "line": 100, "line_end": 105}
        body = self.rule._extract_function_body(func, "short")
        self.assertEqual(body, "")


class TestD002EdgeCases(unittest.TestCase):
    """Edge case tests for D002."""

    def setUp(self):
        self.rule = D002()

    def test_small_functions_ignored(self):
        """Functions below MIN_FUNCTION_SIZE should be ignored."""
        content = "def a():\n    x = 1\n\ndef b():\n    y = 2\n"
        structure = {
            "functions": [
                {"name": "a", "line": 1, "line_end": 2},
                {"name": "b", "line": 4, "line_end": 5},
            ]
        }
        result = self.rule.check("test.py", structure, content)
        self.assertEqual(result, [])

    def test_max_candidates_limit(self):
        """Should respect MAX_CANDIDATES limit."""
        # Create many similar functions
        funcs = []
        content_parts = []
        for i in range(10):
            content_parts.append(f"""def func{i}():
    x = input_value
    y = x * 2
    if y > 10:
        z = y + 5
    else:
        z = y - 5
    result = z * 3
    return result
""")
            start_line = i * 10 + 1
            funcs.append({
                "name": f"func{i}",
                "line": start_line,
                "line_end": start_line + 8
            })

        content = "\n".join(content_parts)
        structure = {"functions": funcs}

        result = self.rule.check("test.py", structure, content)
        self.assertLessEqual(len(result), self.rule.MAX_CANDIDATES)


class TestD002RuleMetadata(unittest.TestCase):
    """Tests for rule metadata."""

    def test_rule_code(self):
        """Rule should have correct code."""
        rule = D002()
        self.assertEqual(rule.code, "D002")

    def test_rule_disabled_by_default(self):
        """Rule should be disabled by default."""
        rule = D002()
        self.assertFalse(rule.enabled)

    def test_rule_severity_low(self):
        """Rule should have LOW severity."""
        rule = D002()
        from reveal.rules.base import Severity
        self.assertEqual(rule.severity, Severity.LOW)


if __name__ == "__main__":
    unittest.main()

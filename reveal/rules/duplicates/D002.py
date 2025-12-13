"""D002: Detect similar functions using vector similarity.

Statistical approach:
- Vectorize function bodies (AST-based feature vectors)
- Compute pairwise cosine similarity
- Rank by similarity score
- Report top-k "most dupey" pairs

Optimizations:
- Uses AST features (already parsed by reveal)
- No ML dependencies (uses stdlib only)
- O(n^2) similarity computation (acceptable for <1000 functions)
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import math
import re

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class D002(BaseRule):
    """Detect similar functions using statistical similarity."""

    code = "D002"
    message = "Similar function detected"
    category = RulePrefix.D
    severity = Severity.LOW  # Lower severity than exact duplicates
    file_patterns = ['*']
    version = "1.0.0"

    # Similarity threshold (0.0 to 1.0)
    SIMILARITY_THRESHOLD = 0.75  # Report if >75% similar

    # Maximum pairs to report (prevent spam)
    MAX_PAIRS = 10

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Find similar functions and rank by similarity.

        Args:
            file_path: Path to file
            structure: Parsed structure from reveal analyzer
            content: File content

        Returns:
            List of detections, sorted by similarity (highest first)
        """
        if not structure or 'functions' not in structure:
            return []

        functions = structure['functions']
        if len(functions) < 2:
            return []

        # Extract vectors for all functions
        func_vectors = []
        for func in functions:
            func_body = self._extract_function_body(func, content)
            if not func_body or len(func_body.strip()) < 20:
                continue

            vector = self._vectorize(func_body)
            func_vectors.append((func, vector))

        # Compute pairwise similarities
        similarity_pairs = []

        for i in range(len(func_vectors)):
            for j in range(i + 1, len(func_vectors)):
                func1, vec1 = func_vectors[i]
                func2, vec2 = func_vectors[j]

                similarity = self._cosine_similarity(vec1, vec2)

                if similarity >= self.SIMILARITY_THRESHOLD:
                    similarity_pairs.append((similarity, func1, func2))

        # Sort by similarity (descending)
        similarity_pairs.sort(reverse=True, key=lambda x: x[0])

        # Generate detections for top pairs
        detections = []
        for similarity, func1, func2 in similarity_pairs[:self.MAX_PAIRS]:
            # Report the later function as "similar to" earlier one
            detections.append(Detection(
                file_path=file_path,
                line=func2.get('line', 0),
                rule_code=self.code,
                message=f"{self.message}: '{func2['name']}' is {similarity:.1%} similar to '{func1['name']}' (line {func1.get('line', 0)})",
                severity=self.severity,
                category=self.category,
                suggestion=f"Consider refactoring or extracting common logic (similarity: {similarity:.3f})",
                context=f"Similarity score: {similarity:.3f}"
            ))

        return detections

    def _extract_function_body(self, func: Dict, content: str) -> str:
        """Extract function body (without signature)."""
        start = func.get('line', 0)
        end = func.get('line_end', start)

        if start == 0 or end == 0:
            return ""

        lines = content.splitlines()
        if start > len(lines) or end > len(lines):
            return ""

        # Skip signature line
        body_lines = lines[start:end]
        return '\n'.join(body_lines) if body_lines else ""

    def _vectorize(self, code: str) -> Dict[str, float]:
        """
        Convert code to feature vector using AST-inspired features.

        Features:
        - Token frequency (TF-IDF-like)
        - Control flow patterns (if, for, while counts)
        - Structural features (nesting depth, line count)

        Returns:
            Dict mapping feature names to values (sparse vector)
        """
        # Normalize code first
        normalized = self._normalize(code)

        features = {}

        # 1. Token frequency features
        tokens = re.findall(r'\w+', normalized.lower())
        token_counts = Counter(tokens)

        # TF-IDF approximation: weight by inverse frequency
        total_tokens = len(tokens)
        for token, count in token_counts.items():
            tf = count / total_tokens if total_tokens > 0 else 0
            # Use token as feature
            features[f'token_{token}'] = tf

        # 2. Control flow features
        features['count_if'] = normalized.count('if ')
        features['count_for'] = normalized.count('for ')
        features['count_while'] = normalized.count('while ')
        features['count_return'] = normalized.count('return ')
        features['count_try'] = normalized.count('try:')

        # 3. Structural features
        features['line_count'] = len(normalized.splitlines())
        features['avg_line_length'] = sum(len(l) for l in normalized.splitlines()) / max(len(normalized.splitlines()), 1)

        # 4. Operator features
        features['count_assignments'] = normalized.count('=')
        features['count_comparisons'] = (normalized.count('==') +
                                        normalized.count('!=') +
                                        normalized.count('>=') +
                                        normalized.count('<='))

        return features

    def _normalize(self, code: str) -> str:
        """Normalize code for comparison."""
        # Remove comments
        code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)

        # Remove docstrings
        code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL)
        code = re.sub(r"'''.*?'''", '', code, flags=re.DOTALL)

        # Normalize whitespace
        code = re.sub(r'[ \t]+', ' ', code)
        code = re.sub(r'\n\s*\n', '\n', code)

        return code.strip()

    def _cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """
        Compute cosine similarity between two sparse vectors.

        Cosine similarity = dot(v1, v2) / (||v1|| * ||v2||)
        Range: 0.0 (completely different) to 1.0 (identical)

        Args:
            vec1, vec2: Sparse vectors (dicts mapping features to values)

        Returns:
            Similarity score (0.0 to 1.0)
        """
        # Get all features
        all_features = set(vec1.keys()) | set(vec2.keys())

        if not all_features:
            return 0.0

        # Compute dot product
        dot_product = sum(vec1.get(f, 0) * vec2.get(f, 0) for f in all_features)

        # Compute magnitudes
        mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

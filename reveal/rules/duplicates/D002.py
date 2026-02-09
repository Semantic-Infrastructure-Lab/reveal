"""D002: Discover potential duplicate functions worth investigating.

Discovery approach (not threshold-based detection):
- Vectorize function bodies
- Compute pairwise similarity
- Rank by "interestingness" = similarity * sqrt(size)
- Show top-k most interesting candidates for human review

Philosophy:
- No false positive/negative tradeoffs - just ranked discovery
- Longer similar functions are more interesting (more refactoring payoff)
- Human makes final call on whether to refactor
"""

import logging
from typing import List, Dict, Any, Optional
from collections import Counter
import math
import re

from ..base import BaseRule, Detection, RulePrefix, Severity

logger = logging.getLogger(__name__)


class D002(BaseRule):
    """Discover potential duplicate functions worth investigating."""

    code = "D002"
    message = "Potential duplicate candidate"
    category = RulePrefix.D
    severity = Severity.LOW  # Advisory, not a defect
    file_patterns = ['*']
    version = "2.0.0"
    enabled = False  # Opt-in only (too noisy for default checks)

    # Minimum function size to consider (skip trivial functions)
    MIN_FUNCTION_SIZE = 8  # Lines

    # Minimum similarity to even consider (very low bar, ranking does the work)
    MIN_SIMILARITY = 0.50

    # Maximum candidates to report
    MAX_CANDIDATES = 5

    def check(self,
             file_path: str,
             structure: Optional[Dict[str, Any]],
             content: str) -> List[Detection]:
        """
        Discover potential duplicate functions ranked by interestingness.

        Interestingness = similarity * sqrt(combined_size)
        - Higher similarity = more likely duplicate
        - Larger functions = more refactoring payoff

        Args:
            file_path: Path to file
            structure: Parsed structure from reveal analyzer
            content: File content

        Returns:
            List of candidates, sorted by interestingness (highest first)
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

            line_count = len(func_body.splitlines())
            if line_count < self.MIN_FUNCTION_SIZE:
                continue

            vector = self._vectorize(func_body)
            func_vectors.append((func, vector, line_count))

        # Compute pairwise similarities with interestingness score
        candidates = []

        for i in range(len(func_vectors)):
            for j in range(i + 1, len(func_vectors)):
                func1, vec1, size1 = func_vectors[i]
                func2, vec2, size2 = func_vectors[j]

                similarity = self._cosine_similarity(vec1, vec2)

                if similarity < self.MIN_SIMILARITY:
                    continue

                # Interestingness: similarity weighted by size (sqrt to not over-weight huge functions)
                combined_size = size1 + size2
                interestingness = similarity * math.sqrt(combined_size)

                candidates.append((interestingness, similarity, combined_size, func1, func2))

        # Sort by interestingness (descending)
        candidates.sort(reverse=True, key=lambda x: x[0])

        # Generate detections for top candidates
        detections = []
        for interestingness, similarity, combined_size, func1, func2 in candidates[:self.MAX_CANDIDATES]:
            detections.append(Detection(
                file_path=file_path,
                line=func2.get('line', 0),
                rule_code=self.code,
                message=f"{self.message}: '{func2['name']}' ~{similarity:.0%} similar to '{func1['name']}' (line {func1.get('line', 0)})",
                severity=self.severity,
                category=self.category,
                suggestion=f"Combined {combined_size} lines. Worth investigating if logic can be shared.",
                context=f"Interestingness: {interestingness:.1f} (similarity {similarity:.0%} × size {combined_size})"
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

        # 2. Control flow features (normalized by line count for density)
        line_count = len(normalized.splitlines())
        line_count_safe = max(line_count, 1)

        features['density_if'] = normalized.count('if ') / line_count_safe
        features['density_for'] = normalized.count('for ') / line_count_safe
        features['density_while'] = normalized.count('while ') / line_count_safe
        features['density_return'] = normalized.count('return ') / line_count_safe
        features['density_try'] = normalized.count('try:') / line_count_safe

        # 3. Structural features (normalized to 0-1 range)
        features['line_count_norm'] = min(line_count / 100.0, 1.0)  # Cap at 100 lines
        avg_len = sum(len(l) for l in normalized.splitlines()) / line_count_safe
        features['avg_line_length_norm'] = min(avg_len / 80.0, 1.0)  # Cap at 80 chars

        # 4. Operator features (normalized by line count)
        features['density_assignments'] = normalized.count('=') / line_count_safe
        features['density_comparisons'] = (normalized.count('==') +
                                          normalized.count('!=') +
                                          normalized.count('>=') +
                                          normalized.count('<=')) / line_count_safe

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

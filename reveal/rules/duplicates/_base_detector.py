"""Universal duplicate detection base classes.

Supports any file type through abstraction layers:
- Syntax: Language-specific (tokens, AST)
- Structure: Universal (control flow, complexity)
- Semantic: Universal (embeddings, intent)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional, Tuple
from enum import Enum
import numpy as np
import math
import re


class DetectionMode(Enum):
    """Detection modes by abstraction level."""
    EXACT = "exact"          # Hash-based exact matching
    STRUCTURAL = "structural"  # Structure + syntax features
    SEMANTIC = "semantic"     # Embeddings (future)


class SimilarityMetric(Enum):
    """Similarity metrics."""
    COSINE = "cosine"
    JACCARD = "jaccard"
    EUCLIDEAN = "euclidean"


@dataclass
class Chunk:
    """Comparable unit extracted from file."""
    type: str  # 'function', 'class', 'section', etc.
    name: str
    content: str
    line: int
    line_end: int
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DuplicateConfig:
    """User-configurable duplicate detection settings."""

    # Detection level
    mode: DetectionMode = DetectionMode.STRUCTURAL

    # Feature selection
    use_syntax: bool = True
    use_structural: bool = True
    use_semantic: bool = False

    # Similarity settings
    similarity_metric: SimilarityMetric = SimilarityMetric.COSINE
    threshold: float = 0.75
    adaptive_threshold: bool = True

    # Output settings
    max_results: int = 10
    min_chunk_size: int = 20
    show_scores: bool = True

    # Normalization
    normalize_whitespace: bool = True
    normalize_comments: bool = True
    normalize_identifiers: bool = False
    normalize_literals: bool = False

    # Quality feedback
    show_statistics: bool = False
    show_recommendations: bool = True

    # Language-specific overrides
    language_config: Dict[str, Any] = field(default_factory=dict)

    def effective_threshold(self, distribution: Optional[np.ndarray] = None) -> float:
        """Get effective threshold (adaptive if enabled)."""
        if not self.adaptive_threshold or distribution is None:
            return self.threshold

        # Use 80th percentile as adaptive threshold
        return float(np.percentile(distribution, 80))


@dataclass
class DistributionAnalysis:
    """Statistical analysis of similarity distribution."""
    mean: float
    median: float
    std: float
    percentiles: Dict[str, float]
    quality_score: float
    interpretation: str


class DuplicateFeatureExtractor(ABC):
    """Base class for language-agnostic duplicate detection.

    Subclass this for each file type (Python, Rust, Markdown, etc.)
    """

    def __init__(self, config: DuplicateConfig):
        self.config = config

    @abstractmethod
    def extract_chunks(self, content: str, structure: Dict) -> List[Chunk]:
        """Extract comparable units (functions, blocks, sections).

        Language-specific: What constitutes a "chunk" varies by file type.
        - Python: functions, classes, methods
        - Rust: functions, impls, traits
        - Markdown: sections by headers
        - JSON: top-level objects
        """
        pass

    @abstractmethod
    def extract_syntax_features(self, chunk: str) -> Dict[str, float]:
        """Extract language-specific syntax features.

        Examples:
        - Python: keyword counts, decorators, list comprehensions
        - Rust: lifetimes, generics, pattern matching
        - Markdown: code blocks, lists, links
        """
        pass

    def extract_structural_features(self, chunk: str) -> Dict[str, float]:
        """Extract universal structural features.

        These work for any language:
        - Nesting depth (indentation)
        - Line count
        - Branching (if/for/while patterns)
        - Complexity estimates
        """
        features: Dict[str, float] = {}

        lines = chunk.splitlines()
        features['line_count'] = len(lines)

        if lines:
            features['avg_line_length'] = sum(len(ln) for ln in lines) / len(lines)

            # Nesting depth (indentation-based, universal)
            indents = [len(ln) - len(ln.lstrip()) for ln in lines if ln.strip()]
            features['max_nesting'] = max(indents) if indents else 0
            features['avg_nesting'] = sum(indents) / len(indents) if indents else 0

        # Branching keywords (common across languages)
        branch_keywords = ['if', 'else', 'for', 'while', 'switch', 'case', 'match']
        features['branch_count'] = sum(chunk.lower().count(kw) for kw in branch_keywords)

        # Return statements (common across languages)
        features['return_count'] = chunk.lower().count('return')

        # Complexity estimate
        features['complexity'] = self._estimate_complexity(chunk)

        return features

    def extract_semantic_features(self, chunk: str) -> Dict[str, float]:
        """Extract semantic features (optional, expensive).

        Could use embeddings here if available.
        For now, placeholder for future enhancement.
        """
        # Future: Use CodeBERT or similar
        return {}

    def vectorize(self, chunk: Chunk) -> Dict[str, float]:
        """Convert chunk to feature vector based on config."""
        features = {}

        # Normalize content first
        normalized = self._normalize(chunk.content)

        if self.config.use_syntax:
            syntax_features = self.extract_syntax_features(normalized)
            features.update({f'syn_{k}': v for k, v in syntax_features.items()})

        if self.config.use_structural:
            struct_features = self.extract_structural_features(normalized)
            features.update({f'str_{k}': v for k, v in struct_features.items()})

        if self.config.use_semantic:
            semantic_features = self.extract_semantic_features(normalized)
            features.update({f'sem_{k}': v for k, v in semantic_features.items()})

        return features

    def _normalize(self, code: str) -> str:
        """Normalize code based on config."""
        if self.config.normalize_comments:
            code = self._remove_comments(code)

        if self.config.normalize_whitespace:
            code = self._normalize_whitespace(code)

        if self.config.normalize_identifiers:
            code = self._normalize_identifiers(code)

        if self.config.normalize_literals:
            code = self._normalize_literals(code)

        return code

    def _remove_comments(self, code: str) -> str:
        """Remove comments (language-agnostic heuristic)."""
        # Single-line comments
        code = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        code = re.sub(r'//.*$', '', code, flags=re.MULTILINE)
        # Block comments
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
        # Docstrings
        code = re.sub(r'""".*?"""', '', code, flags=re.DOTALL)
        code = re.sub(r"'''.*?'''", '', code, flags=re.DOTALL)
        return code

    def _normalize_whitespace(self, code: str) -> str:
        """Normalize whitespace."""
        code = re.sub(r'[ \t]+', ' ', code)
        code = re.sub(r'\n\s*\n', '\n', code)
        return code.strip()

    def _normalize_identifiers(self, code: str) -> str:
        """Rename identifiers to canonical names (expensive!)."""
        # Simple approach: replace all \w+ with var0, var1, ...
        # This is crude but effective for catching semantic duplicates
        identifiers = {}
        counter = [0]

        def replace_identifier(match):
            word = match.group(0)
            # Skip keywords
            if word in {'if', 'else', 'for', 'while', 'def', 'class', 'return', 'import'}:
                return word
            if word not in identifiers:
                identifiers[word] = f'var{counter[0]}'
                counter[0] += 1
            return identifiers[word]

        return re.sub(r'\b\w+\b', replace_identifier, code)

    def _normalize_literals(self, code: str) -> str:
        """Replace literals with type placeholders."""
        # Strings
        code = re.sub(r'"[^"]*"', 'STR', code)
        code = re.sub(r"'[^']*'", 'STR', code)
        # Numbers
        code = re.sub(r'\b\d+\.\d+\b', 'FLOAT', code)
        code = re.sub(r'\b\d+\b', 'INT', code)
        return code

    def _estimate_complexity(self, code: str) -> int:
        """Estimate cyclomatic complexity."""
        complexity = 1
        branch_keywords = ['if', 'elif', 'else', 'for', 'while', 'and', 'or', 'case', 'when']
        for kw in branch_keywords:
            complexity += code.lower().count(kw)
        return complexity

    def compute_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Compute similarity between two feature vectors."""
        if self.config.similarity_metric == SimilarityMetric.COSINE:
            return self._cosine_similarity(vec1, vec2)
        elif self.config.similarity_metric == SimilarityMetric.JACCARD:
            return self._jaccard_similarity(vec1, vec2)
        elif self.config.similarity_metric == SimilarityMetric.EUCLIDEAN:
            return self._euclidean_similarity(vec1, vec2)
        else:
            return self._cosine_similarity(vec1, vec2)

    def _cosine_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Cosine similarity for sparse vectors."""
        all_features = set(vec1.keys()) | set(vec2.keys())
        if not all_features:
            return 0.0

        dot_product = sum(vec1.get(f, 0) * vec2.get(f, 0) for f in all_features)
        mag1 = math.sqrt(sum(v ** 2 for v in vec1.values()))
        mag2 = math.sqrt(sum(v ** 2 for v in vec2.values()))

        if mag1 == 0 or mag2 == 0:
            return 0.0

        return dot_product / (mag1 * mag2)

    def _jaccard_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Jaccard similarity (set-based)."""
        keys1 = set(k for k, v in vec1.items() if v > 0)
        keys2 = set(k for k, v in vec2.items() if v > 0)

        if not keys1 and not keys2:
            return 1.0
        if not keys1 or not keys2:
            return 0.0

        intersection = len(keys1 & keys2)
        union = len(keys1 | keys2)

        return intersection / union if union > 0 else 0.0

    def _euclidean_similarity(self, vec1: Dict[str, float], vec2: Dict[str, float]) -> float:
        """Euclidean distance converted to similarity (0-1)."""
        all_features = set(vec1.keys()) | set(vec2.keys())
        if not all_features:
            return 1.0

        distance = math.sqrt(sum((vec1.get(f, 0) - vec2.get(f, 0)) ** 2 for f in all_features))

        # Convert distance to similarity (inverse exponential)
        # similarity = exp(-distance)
        return math.exp(-distance / 10)  # Normalize by dividing by 10


class DuplicateDetectionFeedback:
    """Analyze duplicate detection quality and provide recommendations."""

    def __init__(self, similarities: List[float], config: DuplicateConfig):
        self.similarities = np.array(similarities) if similarities else np.array([])
        self.config = config

    def analyze_distribution(self) -> Optional[DistributionAnalysis]:
        """Analyze similarity score distribution."""
        if len(self.similarities) == 0:
            return None

        mean = float(self.similarities.mean())
        median = float(np.median(self.similarities))
        std = float(self.similarities.std())

        percentiles = {
            '50th': float(np.percentile(self.similarities, 50)),
            '75th': float(np.percentile(self.similarities, 75)),
            '90th': float(np.percentile(self.similarities, 90)),
            '95th': float(np.percentile(self.similarities, 95)),
        }

        quality_score = self._compute_quality_score(mean, std)
        interpretation = self._interpret_distribution(mean, std)

        return DistributionAnalysis(
            mean=mean,
            median=median,
            std=std,
            percentiles=percentiles,
            quality_score=quality_score,
            interpretation=interpretation
        )

    def _compute_quality_score(self, mean: float, std: float) -> float:
        """Compute quality score (0-1, higher is better).

        Good distribution:
        - Mean around 0.4-0.6 (not too high, not too low)
        - High std (wide spread, good discrimination)
        """
        # Mean score: penalize extremes
        if 0.4 <= mean <= 0.6:
            mean_score = 1.0
        else:
            mean_score = max(0, 1.0 - abs(mean - 0.5) / 0.5)

        # Std score: higher is better
        std_score = min(1.0, std / 0.3)

        return (mean_score + std_score) / 2

    def _interpret_distribution(self, mean: float, std: float) -> str:
        """Provide human-readable interpretation."""
        if mean > 0.9:
            return "⚠️  Very high mean similarity - features not discriminative"
        elif mean > 0.7:
            return "✅ Good discrimination"
        elif mean > 0.5:
            return "✅ Excellent discrimination"
        else:
            return "⚠️  Very low similarity - may miss duplicates"

    def suggest_threshold(self) -> Tuple[float, str]:
        """Suggest optimal threshold."""
        if len(self.similarities) == 0:
            return self.config.threshold, "No data available"

        # Use 80th percentile
        suggested = float(np.percentile(self.similarities, 80))
        suggested = round(suggested * 20) / 20  # Round to 0.05

        if abs(suggested - self.config.threshold) < 0.05:
            return self.config.threshold, "Current threshold is optimal"

        return suggested, "Based on 80th percentile of distribution"

    def generate_report(self) -> str:
        """Generate comprehensive feedback report."""
        dist = self.analyze_distribution()
        if dist is None:
            return "No similarity data available"

        threshold, reason = self.suggest_threshold()

        report = []
        report.append("Similarity Distribution:")
        report.append(f"  Mean:   {dist.mean:.3f}")
        report.append(f"  Median: {dist.median:.3f}")
        report.append(f"  StdDev: {dist.std:.3f}")
        report.append(f"  Quality: {dist.quality_score:.2f}/1.0")
        report.append(f"\n  {dist.interpretation}")
        report.append(f"\nSuggested threshold: {threshold:.2f} ({reason})")

        return "\n".join(report)

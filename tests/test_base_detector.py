"""Comprehensive tests for reveal.rules.duplicates._base_detector module.

Tests cover:
- Enums (DetectionMode, SimilarityMetric)
- Data classes (Chunk, DuplicateConfig, DistributionAnalysis)
- DuplicateFeatureExtractor (normalization, features, similarity)
- DuplicateDetectionFeedback (statistics, recommendations)
"""

import pytest
import numpy as np
from typing import Dict, List

from reveal.rules.duplicates._base_detector import (
    DetectionMode,
    SimilarityMetric,
    Chunk,
    DuplicateConfig,
    DistributionAnalysis,
    DuplicateFeatureExtractor,
    DuplicateDetectionFeedback,
)


# ==============================================================================
# Test Enums
# ==============================================================================


class TestEnums:
    """Tests for DetectionMode and SimilarityMetric enums."""

    def test_detection_mode_values(self):
        """Test DetectionMode enum values."""
        assert DetectionMode.EXACT.value == "exact"
        assert DetectionMode.STRUCTURAL.value == "structural"
        assert DetectionMode.SEMANTIC.value == "semantic"

    def test_similarity_metric_values(self):
        """Test SimilarityMetric enum values."""
        assert SimilarityMetric.COSINE.value == "cosine"
        assert SimilarityMetric.JACCARD.value == "jaccard"
        assert SimilarityMetric.EUCLIDEAN.value == "euclidean"


# ==============================================================================
# Test Data Classes
# ==============================================================================


class TestChunk:
    """Tests for Chunk dataclass."""

    def test_chunk_creation(self):
        """Test creating a Chunk instance."""
        chunk = Chunk(
            type='function',
            name='test_func',
            content='def test_func(): pass',
            line=10,
            line_end=20,
            metadata={'complexity': 1}
        )

        assert chunk.type == 'function'
        assert chunk.name == 'test_func'
        assert chunk.content == 'def test_func(): pass'
        assert chunk.line == 10
        assert chunk.line_end == 20
        assert chunk.metadata['complexity'] == 1

    def test_chunk_default_metadata(self):
        """Test Chunk with default metadata."""
        chunk = Chunk(
            type='class',
            name='MyClass',
            content='class MyClass: pass',
            line=1,
            line_end=1
        )

        assert chunk.metadata == {}


class TestDuplicateConfig:
    """Tests for DuplicateConfig dataclass."""

    def test_default_config(self):
        """Test default DuplicateConfig values."""
        config = DuplicateConfig()

        assert config.mode == DetectionMode.STRUCTURAL
        assert config.use_syntax is True
        assert config.use_structural is True
        assert config.use_semantic is False
        assert config.similarity_metric == SimilarityMetric.COSINE
        assert config.threshold == 0.75
        assert config.adaptive_threshold is True
        assert config.max_results == 10
        assert config.min_chunk_size == 20

    def test_custom_config(self):
        """Test custom DuplicateConfig values."""
        config = DuplicateConfig(
            mode=DetectionMode.EXACT,
            threshold=0.9,
            adaptive_threshold=False,
            normalize_identifiers=True
        )

        assert config.mode == DetectionMode.EXACT
        assert config.threshold == 0.9
        assert config.adaptive_threshold is False
        assert config.normalize_identifiers is True

    def test_effective_threshold_not_adaptive(self):
        """Test effective_threshold when adaptive is disabled."""
        config = DuplicateConfig(threshold=0.75, adaptive_threshold=False)
        result = config.effective_threshold()

        assert result == 0.75

    def test_effective_threshold_no_distribution(self):
        """Test effective_threshold with no distribution provided."""
        config = DuplicateConfig(threshold=0.75, adaptive_threshold=True)
        result = config.effective_threshold(distribution=None)

        assert result == 0.75

    def test_effective_threshold_with_distribution(self):
        """Test effective_threshold with distribution (80th percentile)."""
        config = DuplicateConfig(threshold=0.75, adaptive_threshold=True)
        distribution = np.array([0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0])
        result = config.effective_threshold(distribution=distribution)

        # 80th percentile of [0.1, 0.2, ..., 1.0] is 0.82
        assert result == pytest.approx(0.82, abs=0.01)


# ==============================================================================
# Concrete Test Implementation
# ==============================================================================


class ConcreteFeatureExtractor(DuplicateFeatureExtractor):
    """Concrete implementation for testing."""

    def extract_chunks(self, content: str, structure: Dict) -> List[Chunk]:
        """Simple line-based chunking for testing."""
        lines = content.split('\n')
        return [
            Chunk(
                type='line',
                name=f'line_{i}',
                content=line,
                line=i,
                line_end=i
            )
            for i, line in enumerate(lines)
            if line.strip()
        ]

    def extract_syntax_features(self, chunk: str) -> Dict[str, float]:
        """Simple syntax features for testing."""
        return {
            'def_count': float(chunk.count('def')),
            'class_count': float(chunk.count('class')),
            'import_count': float(chunk.count('import')),
        }


# ==============================================================================
# Test DuplicateFeatureExtractor
# ==============================================================================


class TestDuplicateFeatureExtractor:
    """Tests for DuplicateFeatureExtractor base class."""

    def test_extract_structural_features_basic(self):
        """Test basic structural feature extraction."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())
        code = """def test():
    if True:
        return 42"""

        features = extractor.extract_structural_features(code)

        assert 'line_count' in features
        assert 'avg_line_length' in features
        assert 'max_nesting' in features
        assert 'branch_count' in features
        assert 'return_count' in features
        assert 'complexity' in features

        assert features['line_count'] == 3
        assert features['branch_count'] >= 1  # 'if' keyword
        assert features['return_count'] == 1

    def test_extract_structural_features_empty_code(self):
        """Test structural features with empty code."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())
        features = extractor.extract_structural_features("")

        assert features['line_count'] == 0  # Empty string has 0 lines after splitlines()

    def test_extract_structural_features_nesting(self):
        """Test nesting depth calculation."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())
        code = """def func():
    if True:
        while True:
            for i in range(10):
                pass"""

        features = extractor.extract_structural_features(code)

        assert features['max_nesting'] > 0
        assert features['branch_count'] >= 3  # if, while, for

    def test_vectorize_with_all_features(self):
        """Test vectorization with all features enabled."""
        config = DuplicateConfig(
            use_syntax=True,
            use_structural=True,
            use_semantic=True
        )
        extractor = ConcreteFeatureExtractor(config)
        chunk = Chunk(
            type='function',
            name='test',
            content='def test(): return 42',
            line=1,
            line_end=1
        )

        vec = extractor.vectorize(chunk)

        # Should have syntax features (prefixed with syn_)
        assert any(k.startswith('syn_') for k in vec.keys())
        # Should have structural features (prefixed with str_)
        assert any(k.startswith('str_') for k in vec.keys())
        # Semantic features would be empty but checked

    def test_vectorize_syntax_only(self):
        """Test vectorization with only syntax features."""
        config = DuplicateConfig(
            use_syntax=True,
            use_structural=False,
            use_semantic=False
        )
        extractor = ConcreteFeatureExtractor(config)
        chunk = Chunk(
            type='function',
            name='test',
            content='def test(): pass',
            line=1,
            line_end=1
        )

        vec = extractor.vectorize(chunk)

        assert any(k.startswith('syn_') for k in vec.keys())
        assert not any(k.startswith('str_') for k in vec.keys())

    def test_normalize_removes_comments(self):
        """Test comment removal normalization."""
        config = DuplicateConfig(normalize_comments=True)
        extractor = ConcreteFeatureExtractor(config)

        code = """# This is a comment
def test():  # inline comment
    '''Docstring'''
    return 42  // C++ style comment"""

        normalized = extractor._normalize(code)

        assert '#' not in normalized or normalized.count('#') < code.count('#')

    def test_normalize_whitespace(self):
        """Test whitespace normalization."""
        config = DuplicateConfig(normalize_whitespace=True, normalize_comments=False)
        extractor = ConcreteFeatureExtractor(config)

        code = """def    test():


    return     42"""

        normalized = extractor._normalize(code)

        # Multiple spaces should be reduced
        assert '    ' not in normalized or normalized.count('    ') < code.count('    ')

    def test_normalize_identifiers(self):
        """Test identifier normalization."""
        config = DuplicateConfig(
            normalize_identifiers=True,
            normalize_comments=False,
            normalize_whitespace=False
        )
        extractor = ConcreteFeatureExtractor(config)

        code = "user_name = get_user_name()"
        normalized = extractor._normalize(code)

        # Identifiers should be replaced with var0, var1, etc.
        assert 'var' in normalized
        assert 'user_name' not in normalized or normalized.count('user_name') < code.count('user_name')

    def test_normalize_literals(self):
        """Test literal normalization."""
        config = DuplicateConfig(
            normalize_literals=True,
            normalize_comments=False,
            normalize_whitespace=False,
            normalize_identifiers=False
        )
        extractor = ConcreteFeatureExtractor(config)

        code = 'x = "hello" + 42 + 3.14'
        normalized = extractor._normalize(code)

        # Strings should be replaced with STR
        assert 'STR' in normalized
        # Numbers should be replaced with INT/FLOAT
        assert 'INT' in normalized or 'FLOAT' in normalized

    def test_remove_comments_python(self):
        """Test Python comment removal."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        code = """# Single line comment
def test():
    '''Docstring'''
    x = 1  # Inline comment"""

        result = extractor._remove_comments(code)

        assert '# Single line' not in result
        assert '# Inline' not in result
        assert "'''Docstring'''" not in result

    def test_remove_comments_c_style(self):
        """Test C-style comment removal."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        code = """// Single line
int x = 42; /* Block comment */"""

        result = extractor._remove_comments(code)

        assert '//' not in result
        assert '/*' not in result

    def test_normalize_whitespace_multiple_spaces(self):
        """Test multiple space normalization."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        code = "x    =     42"
        result = extractor._normalize_whitespace(code)

        assert '    ' not in result
        assert '     ' not in result

    def test_normalize_identifiers_preserves_keywords(self):
        """Test identifier normalization preserves keywords."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        code = "if x > 0: return x else: return 0"
        result = extractor._normalize_identifiers(code)

        # Keywords should be preserved
        assert 'if' in result
        assert 'return' in result
        assert 'else' in result

    def test_normalize_literals_strings(self):
        """Test string literal normalization."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        code = '''name = "John" + 'Doe' '''
        result = extractor._normalize_literals(code)

        assert '"John"' not in result
        assert "'Doe'" not in result
        assert 'STR' in result

    def test_normalize_literals_numbers(self):
        """Test number literal normalization."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        code = "x = 42 + 3.14"
        result = extractor._normalize_literals(code)

        assert '42' not in result or 'INT' in result
        assert '3.14' not in result or 'FLOAT' in result

    def test_estimate_complexity_simple(self):
        """Test complexity estimation for simple code."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        code = "return 42"
        complexity = extractor._estimate_complexity(code)

        assert complexity == 1  # Base complexity

    def test_estimate_complexity_branches(self):
        """Test complexity estimation with branches."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        code = """if x > 0:
    return x
elif x < 0:
    return -x
else:
    return 0"""

        complexity = extractor._estimate_complexity(code)

        assert complexity > 1  # Should count if, elif, else

    def test_compute_similarity_cosine(self):
        """Test cosine similarity computation."""
        config = DuplicateConfig(similarity_metric=SimilarityMetric.COSINE)
        extractor = ConcreteFeatureExtractor(config)

        vec1 = {'a': 1.0, 'b': 2.0, 'c': 3.0}
        vec2 = {'a': 1.0, 'b': 2.0, 'c': 3.0}

        similarity = extractor.compute_similarity(vec1, vec2)

        assert similarity == pytest.approx(1.0, abs=0.01)  # Identical vectors

    def test_compute_similarity_jaccard(self):
        """Test Jaccard similarity computation."""
        config = DuplicateConfig(similarity_metric=SimilarityMetric.JACCARD)
        extractor = ConcreteFeatureExtractor(config)

        vec1 = {'a': 1.0, 'b': 1.0, 'c': 1.0}
        vec2 = {'a': 1.0, 'b': 1.0, 'd': 1.0}

        similarity = extractor.compute_similarity(vec1, vec2)

        # Intersection: {a, b} (2), Union: {a, b, c, d} (4)
        assert similarity == pytest.approx(0.5, abs=0.01)

    def test_compute_similarity_euclidean(self):
        """Test Euclidean similarity computation."""
        config = DuplicateConfig(similarity_metric=SimilarityMetric.EUCLIDEAN)
        extractor = ConcreteFeatureExtractor(config)

        vec1 = {'a': 1.0, 'b': 2.0}
        vec2 = {'a': 1.0, 'b': 2.0}

        similarity = extractor.compute_similarity(vec1, vec2)

        assert similarity > 0.9  # Close vectors should have high similarity

    def test_cosine_similarity_identical(self):
        """Test cosine similarity with identical vectors."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        vec1 = {'x': 3.0, 'y': 4.0}
        vec2 = {'x': 3.0, 'y': 4.0}

        similarity = extractor._cosine_similarity(vec1, vec2)

        assert similarity == pytest.approx(1.0, abs=0.01)

    def test_cosine_similarity_orthogonal(self):
        """Test cosine similarity with orthogonal vectors."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        vec1 = {'x': 1.0}
        vec2 = {'y': 1.0}

        similarity = extractor._cosine_similarity(vec1, vec2)

        assert similarity == pytest.approx(0.0, abs=0.01)

    def test_cosine_similarity_empty_vectors(self):
        """Test cosine similarity with empty vectors."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        similarity = extractor._cosine_similarity({}, {})

        assert similarity == 0.0

    def test_cosine_similarity_zero_magnitude(self):
        """Test cosine similarity when one vector has zero magnitude."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        vec1 = {'x': 1.0}
        vec2 = {'x': 0.0}

        similarity = extractor._cosine_similarity(vec1, vec2)

        assert similarity == 0.0

    def test_jaccard_similarity_identical_sets(self):
        """Test Jaccard similarity with identical sets."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        vec1 = {'a': 1.0, 'b': 1.0, 'c': 1.0}
        vec2 = {'a': 1.0, 'b': 1.0, 'c': 1.0}

        similarity = extractor._jaccard_similarity(vec1, vec2)

        assert similarity == 1.0

    def test_jaccard_similarity_disjoint_sets(self):
        """Test Jaccard similarity with disjoint sets."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        vec1 = {'a': 1.0}
        vec2 = {'b': 1.0}

        similarity = extractor._jaccard_similarity(vec1, vec2)

        assert similarity == 0.0

    def test_jaccard_similarity_empty_sets(self):
        """Test Jaccard similarity with empty sets."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        similarity = extractor._jaccard_similarity({}, {})

        assert similarity == 1.0  # Empty sets are considered identical

    def test_jaccard_similarity_partial_overlap(self):
        """Test Jaccard similarity with partial overlap."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        vec1 = {'a': 1.0, 'b': 1.0, 'c': 1.0}
        vec2 = {'b': 1.0, 'c': 1.0, 'd': 1.0}

        similarity = extractor._jaccard_similarity(vec1, vec2)

        # Intersection: {b, c} (2), Union: {a, b, c, d} (4)
        assert similarity == pytest.approx(0.5, abs=0.01)

    def test_euclidean_similarity_identical(self):
        """Test Euclidean similarity with identical vectors."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        vec1 = {'x': 1.0, 'y': 2.0}
        vec2 = {'x': 1.0, 'y': 2.0}

        similarity = extractor._euclidean_similarity(vec1, vec2)

        # Distance = 0, similarity = exp(0) = 1.0
        assert similarity == pytest.approx(1.0, abs=0.01)

    def test_euclidean_similarity_different(self):
        """Test Euclidean similarity with different vectors."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        vec1 = {'x': 0.0}
        vec2 = {'x': 10.0}

        similarity = extractor._euclidean_similarity(vec1, vec2)

        # Distance = 10, similarity = exp(-10/10) = exp(-1) ≈ 0.368
        assert 0.3 < similarity < 0.4

    def test_euclidean_similarity_empty_vectors(self):
        """Test Euclidean similarity with empty vectors."""
        extractor = ConcreteFeatureExtractor(DuplicateConfig())

        similarity = extractor._euclidean_similarity({}, {})

        assert similarity == 1.0


# ==============================================================================
# Test DuplicateDetectionFeedback
# ==============================================================================


class TestDuplicateDetectionFeedback:
    """Tests for DuplicateDetectionFeedback class."""

    def test_analyze_distribution_empty(self):
        """Test distribution analysis with no data."""
        feedback = DuplicateDetectionFeedback([], DuplicateConfig())
        result = feedback.analyze_distribution()

        assert result is None

    def test_analyze_distribution_basic(self):
        """Test basic distribution analysis."""
        similarities = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        feedback = DuplicateDetectionFeedback(similarities, DuplicateConfig())

        result = feedback.analyze_distribution()

        assert result is not None
        assert isinstance(result, DistributionAnalysis)
        assert result.mean == pytest.approx(0.5, abs=0.01)
        assert result.median == pytest.approx(0.5, abs=0.01)
        assert result.std > 0
        assert '50th' in result.percentiles
        assert '75th' in result.percentiles
        assert '90th' in result.percentiles
        assert '95th' in result.percentiles

    def test_analyze_distribution_percentiles(self):
        """Test percentile calculation."""
        similarities = [0.0, 0.25, 0.5, 0.75, 1.0]
        feedback = DuplicateDetectionFeedback(similarities, DuplicateConfig())

        result = feedback.analyze_distribution()

        assert result.percentiles['50th'] == pytest.approx(0.5, abs=0.01)
        assert result.percentiles['75th'] >= 0.5
        assert result.percentiles['90th'] >= result.percentiles['75th']

    def test_compute_quality_score_optimal(self):
        """Test quality score for optimal distribution."""
        feedback = DuplicateDetectionFeedback([0.5], DuplicateConfig())

        # Mean = 0.5 (optimal), std = 0.3 (good)
        score = feedback._compute_quality_score(0.5, 0.3)

        assert score > 0.5  # Should be reasonably good

    def test_compute_quality_score_extreme_mean(self):
        """Test quality score for extreme mean."""
        feedback = DuplicateDetectionFeedback([0.1], DuplicateConfig())

        score = feedback._compute_quality_score(0.1, 0.1)

        # Extreme mean should be penalized
        assert score < 1.0

    def test_interpret_distribution_high_mean(self):
        """Test interpretation for high mean similarity."""
        feedback = DuplicateDetectionFeedback([0.95], DuplicateConfig())

        interpretation = feedback._interpret_distribution(0.95, 0.1)

        assert "high mean" in interpretation.lower()

    def test_interpret_distribution_low_mean(self):
        """Test interpretation for low mean similarity."""
        feedback = DuplicateDetectionFeedback([0.1], DuplicateConfig())

        interpretation = feedback._interpret_distribution(0.1, 0.1)

        assert "low" in interpretation.lower()

    def test_interpret_distribution_good(self):
        """Test interpretation for good distribution."""
        feedback = DuplicateDetectionFeedback([0.65], DuplicateConfig())

        interpretation = feedback._interpret_distribution(0.65, 0.2)

        assert "good" in interpretation.lower() or "excellent" in interpretation.lower()

    def test_suggest_threshold_no_data(self):
        """Test threshold suggestion with no data."""
        feedback = DuplicateDetectionFeedback([], DuplicateConfig())

        threshold, reason = feedback.suggest_threshold()

        assert threshold == 0.75  # Default threshold
        assert "no data" in reason.lower()

    def test_suggest_threshold_with_data(self):
        """Test threshold suggestion with data."""
        similarities = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
        feedback = DuplicateDetectionFeedback(similarities, DuplicateConfig())

        threshold, reason = feedback.suggest_threshold()

        # Should be 80th percentile, rounded to 0.05
        assert 0.7 <= threshold <= 0.9
        assert "80th percentile" in reason.lower() or "optimal" in reason.lower()

    def test_suggest_threshold_already_optimal(self):
        """Test threshold suggestion when current is optimal."""
        # Create distribution where 80th percentile ≈ 0.75
        similarities = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.75, 0.76, 0.8]
        config = DuplicateConfig(threshold=0.75)
        feedback = DuplicateDetectionFeedback(similarities, config)

        threshold, reason = feedback.suggest_threshold()

        assert "optimal" in reason.lower()

    def test_generate_report_no_data(self):
        """Test report generation with no data."""
        feedback = DuplicateDetectionFeedback([], DuplicateConfig())

        report = feedback.generate_report()

        assert "no" in report.lower()
        assert "data" in report.lower()

    def test_generate_report_with_data(self):
        """Test report generation with data."""
        similarities = [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9]
        feedback = DuplicateDetectionFeedback(similarities, DuplicateConfig())

        report = feedback.generate_report()

        assert "Mean:" in report
        assert "Median:" in report
        assert "StdDev:" in report
        assert "Quality:" in report
        assert "threshold:" in report.lower()

#!/usr/bin/env python3
"""Statistical analysis tool for duplicate detection quality.

Measures:
- Similarity distribution
- Optimal threshold selection
- Parameter sensitivity analysis
"""

import sys
sys.path.insert(0, '/home/scottsen/src/projects/reveal/external-git')

import numpy as np
from pathlib import Path
from reveal.rules.duplicates.D002 import D002
from reveal.analyzers.python import PythonAnalyzer
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt


def analyze_similarity_distribution(test_files):
    """Analyze distribution of similarity scores."""
    rule = D002()
    all_similarities = []

    print("Analyzing similarity distribution...\n")

    for test_file in test_files:
        analyzer = PythonAnalyzer(str(test_file))
        structure = analyzer.get_structure()

        with open(test_file) as f:
            content = f.read()

        functions = structure.get('functions', [])
        if len(functions) < 2:
            continue

        # Extract all pairwise similarities
        func_vectors = []
        for func in functions:
            func_body = rule._extract_function_body(func, content)
            if func_body and len(func_body.strip()) >= 20:
                vector = rule._vectorize(func_body)
                func_vectors.append((func['name'], vector))

        # Compute all pairs
        for i in range(len(func_vectors)):
            for j in range(i + 1, len(func_vectors)):
                name1, vec1 = func_vectors[i]
                name2, vec2 = func_vectors[j]
                similarity = rule._cosine_similarity(vec1, vec2)
                all_similarities.append(similarity)

    if not all_similarities:
        print("No function pairs found!")
        return

    similarities = np.array(all_similarities)

    # Statistics
    print(f"Total function pairs analyzed: {len(similarities)}")
    print(f"\nSimilarity Statistics:")
    print(f"  Mean:   {similarities.mean():.3f}")
    print(f"  Median: {np.median(similarities):.3f}")
    print(f"  Std:    {similarities.std():.3f}")
    print(f"  Min:    {similarities.min():.3f}")
    print(f"  Max:    {similarities.max():.3f}")

    # Percentiles
    print(f"\nPercentiles:")
    for p in [50, 75, 90, 95, 99]:
        val = np.percentile(similarities, p)
        print(f"  {p}th: {val:.3f}")

    # Distribution bins
    print(f"\nDistribution:")
    bins = [0, 0.25, 0.5, 0.75, 0.9, 0.95, 1.0]
    hist, _ = np.histogram(similarities, bins=bins)
    for i, (low, high) in enumerate(zip(bins[:-1], bins[1:])):
        count = hist[i]
        pct = 100 * count / len(similarities)
        print(f"  {low:.2f} - {high:.2f}: {count:4d} ({pct:5.1f}%)")

    # Plot distribution
    plt.figure(figsize=(12, 5))

    # Histogram
    plt.subplot(1, 2, 1)
    plt.hist(similarities, bins=50, edgecolor='black', alpha=0.7)
    plt.axvline(similarities.mean(), color='red', linestyle='--', label=f'Mean: {similarities.mean():.3f}')
    plt.axvline(np.median(similarities), color='green', linestyle='--', label=f'Median: {np.median(similarities):.3f}')
    plt.axvline(0.75, color='orange', linestyle='--', label='Threshold: 0.75')
    plt.xlabel('Cosine Similarity')
    plt.ylabel('Frequency')
    plt.title('Similarity Score Distribution')
    plt.legend()
    plt.grid(alpha=0.3)

    # Cumulative distribution
    plt.subplot(1, 2, 2)
    sorted_sim = np.sort(similarities)
    cumulative = np.arange(1, len(sorted_sim) + 1) / len(sorted_sim)
    plt.plot(sorted_sim, cumulative, linewidth=2)
    plt.axhline(0.95, color='red', linestyle='--', alpha=0.5, label='95th percentile')
    plt.axvline(0.75, color='orange', linestyle='--', alpha=0.5, label='Threshold: 0.75')
    plt.xlabel('Cosine Similarity')
    plt.ylabel('Cumulative Probability')
    plt.title('Cumulative Distribution Function')
    plt.legend()
    plt.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig('/tmp/similarity_distribution.png', dpi=150)
    print(f"\n📊 Plot saved to: /tmp/similarity_distribution.png")


def test_threshold_sensitivity():
    """Test how detection rate changes with threshold."""
    print("\n" + "="*60)
    print("THRESHOLD SENSITIVITY ANALYSIS")
    print("="*60)

    # Create synthetic test cases
    test_cases = create_synthetic_tests()

    rule = D002()

    thresholds = np.arange(0.5, 1.0, 0.05)
    results = []

    for threshold in thresholds:
        rule.SIMILARITY_THRESHOLD = threshold

        detected_pairs = 0
        total_pairs = 0

        for test_file, expected_duplicates in test_cases:
            analyzer = PythonAnalyzer(str(test_file))
            structure = analyzer.get_structure()

            with open(test_file) as f:
                content = f.read()

            detections = rule.check(str(test_file), structure, content)
            detected_pairs += len(detections)
            total_pairs += expected_duplicates

        detection_rate = detected_pairs / total_pairs if total_pairs > 0 else 0
        results.append((threshold, detected_pairs, detection_rate))

        print(f"Threshold {threshold:.2f}: {detected_pairs} pairs detected ({detection_rate:.1%})")

    return results


def create_synthetic_tests():
    """Create synthetic test files with known duplicates."""
    test_dir = Path("/tmp/duplicate_tests")
    test_dir.mkdir(exist_ok=True)

    # Test 1: Exact duplicates
    test1 = test_dir / "exact_duplicates.py"
    test1.write_text("""
def func_a(x):
    result = 0
    for i in x:
        if i > 0:
            result += i
    return result

def func_b(y):
    result = 0
    for i in y:
        if i > 0:
            result += i
    return result

def unique():
    return 42
""")

    # Test 2: Similar but not exact
    test2 = test_dir / "similar_functions.py"
    test2.write_text("""
def process_a(data):
    output = []
    for item in data:
        if item is not None:
            output.append(item.strip())
    return output

def process_b(items):
    result = []
    for x in items:
        if x is not None:
            result.append(x.lower())
    return result

def totally_different():
    import json
    return json.dumps({"key": "value"})
""")

    return [
        (test1, 1),  # 1 duplicate pair expected
        (test2, 1),  # 1 similar pair expected
    ]


def measure_vector_quality():
    """Measure quality of vectorization approach."""
    print("\n" + "="*60)
    print("VECTOR QUALITY ANALYSIS")
    print("="*60)

    # Test different normalization strategies
    from reveal.rules.duplicates.D002 import D002

    test_code1 = """
    result = []
    for item in data:
        if item > 0:
            result.append(item * 2)
    return result
    """

    test_code2 = """
    output = []
    for x in items:
        if x > 0:
            output.append(x * 2)
    return output
    """

    test_code3 = """
    return [x * 2 for x in data if x > 0]
    """

    rule = D002()

    vec1 = rule._vectorize(test_code1)
    vec2 = rule._vectorize(test_code2)
    vec3 = rule._vectorize(test_code3)

    sim_1_2 = rule._cosine_similarity(vec1, vec2)
    sim_1_3 = rule._cosine_similarity(vec1, vec3)
    sim_2_3 = rule._cosine_similarity(vec2, vec3)

    print(f"\nCode 1 vs Code 2 (same logic, different vars): {sim_1_2:.3f}")
    print(f"Code 1 vs Code 3 (same logic, different style): {sim_1_3:.3f}")
    print(f"Code 2 vs Code 3 (same logic, different style): {sim_2_3:.3f}")

    print(f"\nInterpretation:")
    if sim_1_2 > 0.8:
        print(f"  ✅ Good: Catches semantic duplicates despite variable renaming")
    else:
        print(f"  ⚠️  Issue: Not catching semantic duplicates (need better normalization)")

    if sim_1_3 > 0.5:
        print(f"  ✅ Good: Detects similar logic in different styles")
    else:
        print(f"  ⚠️  Issue: Missing similarities across coding styles")


if __name__ == "__main__":
    # Find test files
    tia_path = Path("/home/scottsen/src/tia")
    test_files = list(tia_path.glob("lib/**/*.py"))[:50]  # Sample 50 files

    if test_files:
        analyze_similarity_distribution(test_files)

    # Test threshold sensitivity
    # test_threshold_sensitivity()

    # Measure vector quality
    measure_vector_quality()

    print("\n" + "="*60)
    print("RECOMMENDATIONS")
    print("="*60)
    print("""
Based on the analysis:

1. **Optimal Threshold**: Use 75th-90th percentile of similarity distribution
   - Too low: Many false positives
   - Too high: Miss semantic duplicates

2. **Feature Engineering**:
   - Current: Token frequencies + control flow + structural features
   - Could add: AST node sequences, data flow patterns

3. **Dimension Reduction**:
   - If vector has >100 features, use PCA to reduce to ~50 dimensions
   - Faster computation, similar accuracy

4. **Ranking Strategy**:
   - Always show top-k "most dupey" pairs
   - Let user adjust threshold interactively

5. **Next Steps**:
   - Collect ground truth labels (manual review of top duplicates)
   - Compute precision/recall at different thresholds
   - Optimize feature weights using labeled data
""")

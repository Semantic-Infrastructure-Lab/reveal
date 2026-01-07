# Statistical Framework for Optimizing Duplicate Detection

## Executive Summary

**Problem**: Binary "duplicate or not" is insufficient. We need:
1. **Similarity scores** (0.0 to 1.0) instead of binary classification
2. **Ranked results** ("most dupey" list for human inspection)
3. **Statistical measures** to optimize encoding, thresholds, and features

**Solution**: Multi-level approach with measurable quality metrics

---

## Three-Tier Detection System

### Tier 1: D001 - Exact Duplicates (Hash-Based)
- **Method**: Normalize → Hash → Compare
- **Speed**: ~90ms per file
- **Output**: Binary (duplicate or not)
- **Use case**: Find copy-paste with different names

### Tier 2: D002 - Similar Functions (Vector Similarity)
- **Method**: Vectorize → Cosine similarity → Rank
- **Speed**: ~100-150ms per file
- **Output**: Similarity scores (0.0-1.0), ranked list
- **Use case**: Find semantic duplicates, refactoring candidates

### Tier 3: D003 - Semantic Duplicates (Embeddings) [Future]
- **Method**: Code embeddings (CodeBERT) → Nearest neighbors
- **Speed**: ~200ms per function (with caching)
- **Output**: Semantic similarity, cross-language support
- **Use case**: Find functionally equivalent code

---

## Statistical Quality Metrics

### 1. Similarity Distribution Analysis

**Goal**: Understand the natural distribution of code similarities

```python
# Key statistics to track:
- Mean similarity: Should be ~0.3-0.5 for diverse codebase
- Median similarity: Lower is better (more discrimination)
- Std deviation: Higher is better (more spread)
- Percentiles: 75th, 90th, 95th, 99th

# Interpretation:
Mean > 0.9: ⚠️  Features not discriminative enough
Mean 0.4-0.7: ✅ Good discrimination
Mean < 0.3: ⚠️  May be under-matching
```

**TIA Results**:
```
Mean:   0.935  ⚠️  TOO HIGH - features dominated by common patterns
Median: 0.976  ⚠️  Almost everything looks similar
75th:   0.996  ⚠️  Need better features

Distribution:
  0.95-1.00: 63.5%  ← Too many high-similarity pairs
  0.75-0.90: 14.5%
  0.50-0.75:  5.0%
  0.00-0.50:  1.3%
```

**Diagnosis**: Token-based features are too coarse. Need structural features.

---

### 2. Ground Truth Validation

**Create labeled test set**:

```python
test_cases = [
    # (func1, func2, label, expected_similarity_range)

    # Exact duplicates
    ("def add(a,b): return a+b",
     "def sum(x,y): return x+y",
     "exact_duplicate", (0.95, 1.00)),

    # Semantic duplicates
    ("def add_list(items): return sum(items)",
     "def total(data): return sum(data)",
     "semantic_duplicate", (0.80, 0.95)),

    # Similar structure, different logic
    ("def add(a,b): return a+b",
     "def mul(a,b): return a*b",
     "structurally_similar", (0.50, 0.80)),

    # Completely different
    ("def add(a,b): return a+b",
     "def load_json(path): return json.load(open(path))",
     "different", (0.0, 0.30)),
]
```

**Compute Precision/Recall**:

```python
def evaluate_at_threshold(predictions, ground_truth, threshold):
    """
    Precision: Of items we flagged as duplicates, how many are correct?
    Recall: Of actual duplicates, how many did we find?
    F1: Harmonic mean of precision and recall
    """

    tp = sum((pred >= threshold) & (label == "duplicate")
             for pred, label in zip(predictions, ground_truth))
    fp = sum((pred >= threshold) & (label != "duplicate")
             for pred, label in zip(predictions, ground_truth))
    fn = sum((pred < threshold) & (label == "duplicate")
             for pred, label in zip(predictions, ground_truth))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0

    return precision, recall, f1

# Find optimal threshold
best_f1 = 0
best_threshold = 0.75

for threshold in np.arange(0.5, 1.0, 0.05):
    p, r, f1 = evaluate_at_threshold(scores, labels, threshold)
    print(f"Threshold {threshold:.2f}: P={p:.2f} R={r:.2f} F1={f1:.2f}")

    if f1 > best_f1:
        best_f1 = f1
        best_threshold = threshold

print(f"\n🎯 Optimal threshold: {best_threshold:.2f} (F1={best_f1:.2f})")
```

**Target metrics**:
- Precision > 0.80 (avoid false positives)
- Recall > 0.70 (don't miss true duplicates)
- F1 > 0.75 (balanced)

---

### 3. ROC Curve Analysis

**Plot True Positive Rate vs False Positive Rate**:

```python
from sklearn.metrics import roc_curve, auc

fpr, tpr, thresholds = roc_curve(y_true, y_scores)
roc_auc = auc(fpr, tpr)

plt.plot(fpr, tpr, label=f'ROC (AUC={roc_auc:.3f})')
plt.plot([0, 1], [0, 1], 'k--', label='Random')
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('Duplicate Detection ROC Curve')
plt.legend()

# AUC interpretation:
# 1.0: Perfect classifier
# 0.9-1.0: Excellent
# 0.8-0.9: Good
# 0.7-0.8: Fair
# 0.5-0.7: Poor
# 0.5: Random guessing
```

---

## Optimizing Parameters

### 1. Feature Engineering

**Current features (D002)**:
```python
features = {
    'token_*': tf,              # Token frequency (TF)
    'count_if': N,              # Control flow counts
    'count_for': N,
    'line_count': N,            # Structural features
    'avg_line_length': N,
}
```

**Problem**: Dominated by common tokens (if, for, return)

**Solution**: Add discriminative features:

```python
# Better features:
features = {
    # AST structural fingerprint
    'ast_node_sequence': hash(tuple(node_types)),
    'ast_depth_histogram': histogram(depths),
    'control_flow_graph_hash': hash(cfg),

    # Data flow features
    'variable_flow_patterns': extract_def_use_chains(),
    'function_call_sequence': tuple(called_functions),

    # Semantic features
    'imports_used': set(imports),
    'constants_used': set(literal_values),

    # Weighted token features (TF-IDF)
    'token_*': tf * idf,  # Weight by inverse document frequency
}
```

**Measure improvement**:
```python
# Before: mean similarity 0.935
# After: mean similarity should drop to 0.4-0.6
# And: Ground truth duplicates should cluster tighter
```

---

### 2. Embedding Dimension Optimization

**Use PCA to find intrinsic dimensionality**:

```python
from sklearn.decomposition import PCA

def find_optimal_dimensions(embeddings):
    """Find minimum dimensions that capture 95% variance."""
    pca = PCA()
    pca.fit(embeddings)

    cumulative_variance = np.cumsum(pca.explained_variance_ratio_)

    dims_90 = np.argmax(cumulative_variance >= 0.90) + 1
    dims_95 = np.argmax(cumulative_variance >= 0.95) + 1
    dims_99 = np.argmax(cumulative_variance >= 0.99) + 1

    print(f"Dimensions needed:")
    print(f"  90% variance: {dims_90}")
    print(f"  95% variance: {dims_95}")
    print(f"  99% variance: {dims_99}")

    return dims_95  # Good balance

# Example: CodeBERT uses 768 dims
# But code may only need ~128 dims for 95% variance
# → 6x speedup with minimal quality loss!
```

---

### 3. Chunk Size Optimization

**Hypothesis**: Optimal chunk = semantic unit (function, method, class)

**Measure using Silhouette Score**:

```python
from sklearn.metrics import silhouette_score

def evaluate_chunking_strategy(code, granularity):
    """
    Granularity: 'statement' | 'block' | 'function' | 'class'
    """
    chunks = extract_chunks(code, granularity)
    embeddings = [vectorize(chunk) for chunk in chunks]

    # Assign pseudo-labels (e.g., by file or module)
    labels = assign_semantic_labels(chunks)

    # Silhouette score: -1 (wrong) to 1 (perfect)
    # > 0.5: Good clustering
    # > 0.7: Excellent clustering
    score = silhouette_score(embeddings, labels)

    return score

# Test different granularities
for granularity in ['statement', 'block', 'function', 'class']:
    score = evaluate_chunking_strategy(code, granularity)
    print(f"{granularity:12s}: silhouette={score:.3f}")

# Expected result: 'function' has highest score
```

---

### 4. Normalization Strategy

**Test different normalizations**:

```python
normalizations = {
    'none': lambda c: c,
    'whitespace': normalize_whitespace,
    'comments': remove_comments,
    'identifiers': rename_identifiers_canonical,  # a→var0, b→var1
    'literals': replace_literals,  # "foo"→STR, 42→INT
    'full': full_normalization,
}

for name, normalize_fn in normalizations.items():
    # Measure:
    # 1. How many true duplicates detected?
    # 2. How many false positives?
    # 3. Mean similarity shift

    true_dups = count_true_duplicates(test_set, normalize_fn)
    false_pos = count_false_positives(test_set, normalize_fn)
    mean_sim = measure_mean_similarity(corpus, normalize_fn)

    print(f"{name:12s}: TP={true_dups} FP={false_pos} Mean={mean_sim:.3f}")

# Optimal: Maximize TP, minimize FP
```

---

## Adaptive Threshold Selection

**Problem**: Fixed threshold (0.75) may not be optimal

**Solution**: Learn threshold from data

```python
def select_optimal_threshold(similarity_matrix, validation_labels):
    """Find threshold that maximizes F1 score on validation set."""

    # Try percentile-based thresholds
    thresholds = np.percentile(similarity_matrix.flatten(), [50, 60, 70, 75, 80, 85, 90, 95])

    best_f1 = 0
    best_threshold = 0.75

    for threshold in thresholds:
        predictions = similarity_matrix >= threshold
        p, r, f1 = compute_metrics(predictions, validation_labels)

        if f1 > best_f1:
            best_f1 = f1
            best_threshold = threshold

    return best_threshold, best_f1

# Use cross-validation for robustness
thresholds_cv = []
for train, val in kfold_split(data):
    threshold, _ = select_optimal_threshold(train, val)
    thresholds_cv.append(threshold)

optimal_threshold = np.median(thresholds_cv)
print(f"🎯 Optimal threshold: {optimal_threshold:.3f}")
```

---

## Ranking Strategy: "Most Dupey" List

**Output top-k similar pairs, sorted by score**:

```python
def rank_duplicates(functions, top_k=20):
    """Return top-k most similar function pairs."""

    # Compute all pairwise similarities
    pairs = []
    for i in range(len(functions)):
        for j in range(i+1, len(functions)):
            similarity = compute_similarity(functions[i], functions[j])
            pairs.append((similarity, functions[i], functions[j]))

    # Sort by similarity (descending)
    pairs.sort(reverse=True, key=lambda x: x[0])

    # Return top-k
    return pairs[:top_k]

# Display with context
for rank, (score, func1, func2) in enumerate(rank_duplicates(functions, top_k=10), 1):
    print(f"{rank:2d}. [{score:.3f}] {func1.name:30s} ↔ {func2.name:30s}")
    print(f"     {func1.file}:{func1.line}")
    print(f"     {func2.file}:{func2.line}")
    print()
```

**Interactive threshold adjustment**:
```bash
# Show duplicates at different thresholds
reveal file.py --check --select D --threshold 0.95  # Very strict
reveal file.py --check --select D --threshold 0.80  # Moderate
reveal file.py --check --select D --threshold 0.60  # Loose (many candidates)
```

---

## Visualization for Analysis

### t-SNE 2D Projection

```python
from sklearn.manifold import TSNE

# Reduce to 2D for visualization
tsne = TSNE(n_components=2, random_state=42)
embeddings_2d = tsne.fit_transform(function_embeddings)

# Plot
plt.figure(figsize=(12, 10))
scatter = plt.scatter(embeddings_2d[:, 0], embeddings_2d[:, 1],
                     c=duplicate_labels, cmap='tab20', alpha=0.6, s=100)

# Annotate function names
for i, name in enumerate(function_names):
    plt.annotate(name, (embeddings_2d[i, 0], embeddings_2d[i, 1]),
                fontsize=8, alpha=0.7)

plt.title('Function Similarity Space (t-SNE Projection)')
plt.xlabel('Dimension 1')
plt.ylabel('Dimension 2')
plt.colorbar(scatter, label='Duplicate Group')

# Duplicates should cluster together visually
```

---

## Implementation Roadmap

### Phase 1: Statistical Instrumentation ✅
- [x] Add similarity scores to D002
- [x] Output ranked list instead of binary
- [x] Create analysis tools (`analyze_duplicate_detection.py`)

### Phase 2: Feature Engineering
- [ ] Add AST structural features
- [ ] Add control flow graph features
- [ ] Implement TF-IDF weighting
- [ ] Test on ground truth dataset

### Phase 3: Optimization
- [ ] Collect 100+ labeled duplicate pairs
- [ ] Compute precision/recall curves
- [ ] Find optimal threshold via cross-validation
- [ ] Tune feature weights

### Phase 4: Advanced
- [ ] Add CodeBERT embeddings (D003)
- [ ] Cross-file duplicate detection
- [ ] Interactive threshold tuning UI

---

## Quick Start: Measuring Your Detection Quality

```bash
# 1. Generate similarity distribution
python /tmp/analyze_duplicate_detection.py

# 2. Review the plot
open /tmp/similarity_distribution.png

# 3. Check statistics
# - Mean should be 0.4-0.7 (not 0.9!)
# - Distribution should be spread (not all high)

# 4. Test on known duplicates
reveal your_duplicates.py --check --select D

# 5. Inspect top-k "most dupey" pairs
# - Do high scores (>0.95) actually look duplicate? → Good!
# - Do low scores (<0.60) look different? → Good!
# - Do medium scores (0.70-0.85) need tuning? → Adjust threshold

# 6. Iterate on features
# - If too many false positives → Add discriminative features
# - If missing true duplicates → Improve normalization
```

---

## Key Takeaways

1. **Binary classification is insufficient** → Use similarity scores + ranking

2. **Statistics guide optimization**:
   - Distribution analysis reveals feature quality
   - Precision/recall curves find optimal threshold
   - ROC AUC measures discriminative power

3. **Feature engineering is critical**:
   - Token counts alone → poor discrimination (mean sim 0.93)
   - AST structure + control flow → better (target: mean sim 0.5)
   - Embeddings → best (semantic understanding)

4. **Ranking > Binary**:
   - Show "most dupey" list for human review
   - Let user adjust threshold interactively
   - Report confidence scores

5. **Measure everything**:
   - Ground truth labels
   - Confusion matrix
   - Parameter sensitivity
   - Ablation studies (remove features, test impact)

**Bottom line**: Don't guess. Measure. Optimize. Repeat.

# Universal Duplicate Detection Architecture for Reveal

## The Challenge

Make duplicate detection work for:
- **Any file type**: Python, Rust, JS, Go, Markdown, JSON, YAML, Nginx configs, Dockerfiles...
- **Configurable**: Users tune for their needs
- **Self-reflective**: System guides users to "do it well"

## Core Insight: Abstraction Layers

```
┌─────────────────────────────────────────────────────────┐
│ SEMANTIC LAYER (Universal)                              │
│ "What does this do?" - Embeddings, intent               │
└─────────────────────────────────────────────────────────┘
                         ▲
┌─────────────────────────────────────────────────────────┐
│ STRUCTURAL LAYER (Universal)                            │
│ Control flow, nesting, patterns, complexity             │
└─────────────────────────────────────────────────────────┘
                         ▲
┌─────────────────────────────────────────────────────────┐
│ SYNTAX LAYER (Language-specific)                        │
│ AST nodes, tokens, keywords, operators                  │
└─────────────────────────────────────────────────────────┘
```

**Key**: Lower layers are language-specific, upper layers are universal.

---

## Universal Feature Extraction

### Base Feature Extractor (Abstract)

```python
class DuplicateFeatureExtractor(ABC):
    """Base class for language-agnostic duplicate detection."""

    @abstractmethod
    def extract_chunks(self, content: str, structure: Dict) -> List[Chunk]:
        """Extract comparable units (functions, blocks, sections)."""
        pass

    @abstractmethod
    def extract_syntax_features(self, chunk: str) -> Dict[str, float]:
        """Language-specific: tokens, keywords, AST nodes."""
        pass

    def extract_structural_features(self, chunk: str) -> Dict[str, float]:
        """Universal: control flow, nesting, complexity."""
        return {
            'nesting_depth': self._max_indent_level(chunk),
            'line_count': len(chunk.splitlines()),
            'avg_line_length': self._avg_line_length(chunk),
            'branching_factor': self._count_branches(chunk),
            'cyclomatic_complexity': self._estimate_complexity(chunk),
        }

    def extract_semantic_features(self, chunk: str) -> Dict[str, float]:
        """Universal: semantic patterns (optional, expensive)."""
        # Could use embeddings here if available
        return {}

    def vectorize(self, chunk: str, config: DuplicateConfig) -> np.ndarray:
        """Combine all features into vector based on config."""
        features = {}

        if config.use_syntax:
            features.update(self.extract_syntax_features(chunk))

        if config.use_structural:
            features.update(self.extract_structural_features(chunk))

        if config.use_semantic:
            features.update(self.extract_semantic_features(chunk))

        return self._dict_to_vector(features)
```

### Language-Specific Implementations

```python
class PythonDuplicateExtractor(DuplicateFeatureExtractor):
    """Python-specific duplicate detection."""

    def extract_chunks(self, content: str, structure: Dict) -> List[Chunk]:
        """Extract functions, classes, methods."""
        chunks = []

        # Functions
        for func in structure.get('functions', []):
            chunks.append(Chunk(
                type='function',
                name=func['name'],
                content=self._extract_body(func, content),
                metadata=func
            ))

        # Classes
        for cls in structure.get('classes', []):
            chunks.append(Chunk(
                type='class',
                name=cls['name'],
                content=self._extract_body(cls, content),
                metadata=cls
            ))

        return chunks

    def extract_syntax_features(self, chunk: str) -> Dict[str, float]:
        """Python-specific tokens and patterns."""
        features = {}

        # Python keywords
        keywords = ['def', 'class', 'if', 'for', 'while', 'return', 'import', 'lambda']
        for kw in keywords:
            features[f'kw_{kw}'] = chunk.count(kw)

        # Python-specific patterns
        features['list_comprehensions'] = chunk.count('[') + chunk.count('for')
        features['decorators'] = chunk.count('@')
        features['async'] = chunk.count('async')

        # AST-based features (if structure available)
        # ...

        return features


class RustDuplicateExtractor(DuplicateFeatureExtractor):
    """Rust-specific duplicate detection."""

    def extract_chunks(self, content: str, structure: Dict) -> List[Chunk]:
        """Extract functions, impls, traits."""
        chunks = []

        for func in structure.get('functions', []):
            chunks.append(Chunk(type='function', ...))

        for impl in structure.get('impls', []):
            chunks.append(Chunk(type='impl', ...))

        return chunks

    def extract_syntax_features(self, chunk: str) -> Dict[str, float]:
        """Rust-specific tokens."""
        features = {}

        # Rust keywords
        keywords = ['fn', 'impl', 'trait', 'match', 'if', 'for', 'loop', 'let', 'mut']
        for kw in keywords:
            features[f'kw_{kw}'] = chunk.count(kw)

        # Rust-specific patterns
        features['lifetimes'] = chunk.count("'")
        features['generics'] = chunk.count('<') + chunk.count('>')
        features['pattern_matching'] = chunk.count('match')
        features['ownership'] = chunk.count('&') + chunk.count('mut')

        return features


class MarkdownDuplicateExtractor(DuplicateFeatureExtractor):
    """Markdown-specific duplicate detection."""

    def extract_chunks(self, content: str, structure: Dict) -> List[Chunk]:
        """Extract sections by headers."""
        chunks = []
        sections = self._split_by_headers(content)

        for section in sections:
            chunks.append(Chunk(
                type='section',
                name=section['header'],
                content=section['body'],
                metadata={'level': section['level']}
            ))

        return chunks

    def extract_syntax_features(self, chunk: str) -> Dict[str, float]:
        """Markdown-specific features."""
        features = {}

        # Markdown elements
        features['code_blocks'] = chunk.count('```')
        features['lists'] = chunk.count('\n- ') + chunk.count('\n* ')
        features['links'] = chunk.count('[')
        features['images'] = chunk.count('![')
        features['headers'] = chunk.count('\n#')
        features['bold'] = chunk.count('**')
        features['italic'] = chunk.count('*')

        return features
```

---

## Configuration System

### DuplicateConfig Class

```python
@dataclass
class DuplicateConfig:
    """User-configurable duplicate detection settings."""

    # Detection level
    mode: str = "structural"  # 'exact' | 'structural' | 'semantic'

    # Feature selection
    use_syntax: bool = True
    use_structural: bool = True
    use_semantic: bool = False  # Expensive

    # Similarity settings
    similarity_metric: str = "cosine"  # 'cosine' | 'jaccard' | 'euclidean'
    threshold: float = 0.75
    adaptive_threshold: bool = True  # Learn from distribution

    # Output settings
    max_results: int = 10
    min_chunk_size: int = 20  # Skip tiny chunks
    show_scores: bool = True
    rank_by: str = "similarity"  # 'similarity' | 'confidence'

    # Normalization
    normalize_whitespace: bool = True
    normalize_comments: bool = True
    normalize_identifiers: bool = False  # Rename vars to var0, var1
    normalize_literals: bool = False  # Replace with TYPE_STR, TYPE_INT

    # Quality feedback
    show_statistics: bool = False
    show_recommendations: bool = True
    calibration_mode: bool = False  # Interactive tuning

    # Language-specific overrides
    language_config: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_file(cls, path: str) -> 'DuplicateConfig':
        """Load config from YAML/JSON."""
        with open(path) as f:
            data = yaml.safe_load(f)
        return cls(**data)

    def save(self, path: str):
        """Save config to file."""
        with open(path, 'w') as f:
            yaml.dump(asdict(self), f)
```

### Configuration Files

**~/.reveal/duplicate_config.yaml**:
```yaml
# Duplicate detection configuration

# Detection mode: exact | structural | semantic
mode: structural

# Feature extraction
features:
  syntax: true        # Language-specific tokens/AST
  structural: true    # Control flow, nesting
  semantic: false     # Embeddings (slow)

# Similarity computation
similarity:
  metric: cosine      # cosine | jaccard | euclidean
  threshold: 0.75     # 0.0 to 1.0
  adaptive: true      # Auto-adjust based on distribution

# Normalization
normalize:
  whitespace: true
  comments: true
  identifiers: false  # Rename vars (slower but catches more)
  literals: false     # Replace with type placeholders

# Output
output:
  max_results: 10
  show_scores: true
  rank_by: similarity

# Quality feedback
feedback:
  show_statistics: true
  show_recommendations: true
  calibration_mode: false

# Language-specific overrides
languages:
  python:
    threshold: 0.80  # Python tends to be more similar
    normalize_identifiers: true

  rust:
    threshold: 0.70  # Rust more diverse

  markdown:
    threshold: 0.85  # Markdown very similar
    mode: exact      # Mostly want exact duplicates
```

---

## Self-Reflection System

### StatisticalFeedback Class

```python
class DuplicateDetectionFeedback:
    """Analyze duplicate detection quality and provide recommendations."""

    def __init__(self, results: List[Detection], config: DuplicateConfig):
        self.results = results
        self.config = config
        self.similarities = [r.similarity for r in results if hasattr(r, 'similarity')]

    def analyze_distribution(self) -> DistributionAnalysis:
        """Analyze similarity score distribution."""
        if not self.similarities:
            return DistributionAnalysis(status="no_data")

        sims = np.array(self.similarities)

        return DistributionAnalysis(
            mean=sims.mean(),
            median=np.median(sims),
            std=sims.std(),
            percentiles={
                '50th': np.percentile(sims, 50),
                '75th': np.percentile(sims, 75),
                '90th': np.percentile(sims, 90),
                '95th': np.percentile(sims, 95),
            },
            quality_score=self._compute_quality_score(sims),
            interpretation=self._interpret_distribution(sims)
        )

    def _interpret_distribution(self, sims: np.ndarray) -> str:
        """Provide human-readable interpretation."""
        mean = sims.mean()
        std = sims.std()

        if mean > 0.9:
            return "⚠️  Very high mean similarity - features may not be discriminative enough"
        elif mean > 0.7:
            return "✅ Good discrimination - features are working well"
        elif mean > 0.5:
            return "✅ Excellent discrimination - diverse codebase or good features"
        else:
            return "⚠️  Very low similarity - may be missing duplicates"

    def suggest_threshold(self) -> ThresholdRecommendation:
        """Suggest optimal threshold based on distribution."""
        if not self.similarities:
            return ThresholdRecommendation(
                current=self.config.threshold,
                suggested=0.75,
                reason="No data available, using default"
            )

        sims = np.array(self.similarities)

        # Use 75th-85th percentile as threshold
        # This catches top ~15-25% of pairs
        suggested = np.percentile(sims, 80)

        # Round to nearest 0.05
        suggested = round(suggested * 20) / 20

        reason = f"Based on 80th percentile of your similarity distribution"

        if abs(suggested - self.config.threshold) < 0.05:
            reason = f"Current threshold is optimal"

        return ThresholdRecommendation(
            current=self.config.threshold,
            suggested=suggested,
            reason=reason,
            impact=self._estimate_threshold_impact(suggested)
        )

    def _estimate_threshold_impact(self, new_threshold: float) -> str:
        """Estimate how many results would change."""
        current_count = len([s for s in self.similarities if s >= self.config.threshold])
        new_count = len([s for s in self.similarities if s >= new_threshold])

        delta = new_count - current_count

        if delta > 0:
            return f"Would detect {delta} more duplicate pairs"
        elif delta < 0:
            return f"Would detect {abs(delta)} fewer duplicate pairs"
        else:
            return "No change in detection count"

    def suggest_feature_improvements(self) -> List[FeatureRecommendation]:
        """Recommend feature engineering improvements."""
        recommendations = []

        # Check if distribution is too tight
        if np.std(self.similarities) < 0.15:
            recommendations.append(FeatureRecommendation(
                type="feature_engineering",
                priority="high",
                message="Low variance in similarities - add more discriminative features",
                action="Enable 'normalize_identifiers' or add AST structural features"
            ))

        # Check if mean is too high
        if np.mean(self.similarities) > 0.9:
            recommendations.append(FeatureRecommendation(
                type="normalization",
                priority="high",
                message="Mean similarity very high - features dominated by common patterns",
                action="Try TF-IDF weighting or reduce weight of common tokens"
            ))

        # Check sample size
        if len(self.similarities) < 10:
            recommendations.append(FeatureRecommendation(
                type="data",
                priority="low",
                message="Small sample size - results may not be representative",
                action="Run on more files to get better statistics"
            ))

        return recommendations

    def generate_report(self) -> str:
        """Generate comprehensive feedback report."""
        dist = self.analyze_distribution()
        threshold_rec = self.suggest_threshold()
        feature_recs = self.suggest_feature_improvements()

        report = []
        report.append("="*60)
        report.append("DUPLICATE DETECTION QUALITY REPORT")
        report.append("="*60)

        # Distribution stats
        report.append(f"\nSimilarity Distribution:")
        report.append(f"  Mean:   {dist.mean:.3f}")
        report.append(f"  Median: {dist.median:.3f}")
        report.append(f"  StdDev: {dist.std:.3f}")
        report.append(f"  75th percentile: {dist.percentiles['75th']:.3f}")
        report.append(f"  95th percentile: {dist.percentiles['95th']:.3f}")
        report.append(f"\n  {dist.interpretation}")

        # Threshold recommendation
        report.append(f"\nThreshold Recommendation:")
        report.append(f"  Current:   {threshold_rec.current:.2f}")
        report.append(f"  Suggested: {threshold_rec.suggested:.2f}")
        report.append(f"  Reason:    {threshold_rec.reason}")
        report.append(f"  Impact:    {threshold_rec.impact}")

        # Feature recommendations
        if feature_recs:
            report.append(f"\nRecommendations:")
            for rec in feature_recs:
                report.append(f"  [{rec.priority.upper()}] {rec.message}")
                report.append(f"          → {rec.action}")

        # Configuration suggestions
        report.append(f"\nSuggested Configuration:")
        report.append(f"  reveal --check --select D --threshold {threshold_rec.suggested:.2f}")

        if any(r.type == "feature_engineering" for r in feature_recs):
            report.append(f"  Consider: --normalize-identifiers")

        report.append("\n" + "="*60)

        return "\n".join(report)
```

### Usage in Reveal

```python
# In D002.check():
def check(self, file_path: str, structure: Dict, content: str) -> List[Detection]:
    """Run detection with self-reflection."""

    # ... perform duplicate detection ...

    detections = # ... list of detections ...

    # Add feedback if requested
    if self.config.show_recommendations:
        feedback = DuplicateDetectionFeedback(detections, self.config)
        report = feedback.generate_report()

        # Attach as special detection (info level)
        detections.append(Detection(
            file_path=file_path,
            line=0,
            rule_code="D000",
            message="Duplicate Detection Quality Report",
            severity=Severity.LOW,
            context=report
        ))

    return detections
```

---

## Command-Line Interface

### Configuration Commands

```bash
# Show current config
reveal --check --select D --show-config

# Use custom config
reveal --check --select D --config ~/.reveal/my_duplicate_config.yaml

# Interactive calibration
reveal --check --select D --calibrate
# → Shows distribution, suggests threshold, lets you test different values

# Threshold tuning
reveal --check --select D --threshold 0.85
reveal --check --select D --threshold auto  # Use suggested threshold

# Feature selection
reveal --check --select D --syntax --structural  # Explicit features
reveal --check --select D --semantic             # Add expensive semantic features
reveal --check --select D --mode exact           # Exact duplicates only

# Normalization
reveal --check --select D --normalize-identifiers  # Rename vars
reveal --check --select D --normalize-literals     # Replace literals

# Feedback
reveal --check --select D --show-stats           # Show distribution stats
reveal --check --select D --recommend            # Get recommendations
reveal --check --select D --explain              # Explain each detection
```

### Calibration Mode (Interactive)

```bash
$ reveal --check --select D --calibrate

Analyzing codebase...
Found 127 function pairs

Current similarity distribution:
  Mean:   0.873
  Median: 0.921
  StdDev: 0.142

⚠️  Mean similarity very high (0.873) - features may not be discriminative

Testing different thresholds:
  0.95: 34 pairs (26.8%)
  0.90: 67 pairs (52.8%)
  0.85: 89 pairs (70.1%)
  0.80: 103 pairs (81.1%)  ← Recommended
  0.75: 115 pairs (90.6%)
  0.70: 122 pairs (96.1%)

Select threshold (or 'auto' for recommended):
> 0.80

Testing with threshold 0.80...

Top 5 duplicate pairs:
  1. [0.987] process_data ↔ transform_data
  2. [0.956] validate_input ↔ check_input
  3. [0.923] format_output ↔ render_output
  4. [0.897] load_config ↔ read_config
  5. [0.862] parse_args ↔ process_args

Are these good matches? (y/n/inspect)
> inspect

Showing pair #1: process_data ↔ transform_data
Similarity: 0.987

process_data (line 45):
    result = []
    for item in data:
        if validate(item):
            result.append(transform(item))
    return result

transform_data (line 78):
    output = []
    for x in input:
        if validate(x):
            output.append(transform(x))
    return output

Is this a duplicate? (y/n)
> y

Configuration saved to ~/.reveal/duplicate_config.yaml

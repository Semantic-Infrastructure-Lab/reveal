#!/usr/bin/env python3
"""Sample emitted rule claims on a pinned corpus and score independently reviewed labels.

Sampling is deterministic and stratified by rule and top-level source directory.
The label step never infers correctness from Reveal's own rule implementation.
"""
from __future__ import annotations
import argparse
from collections import Counter, defaultdict
import hashlib
import json
from math import sqrt
from statistics import NormalDist
from pathlib import Path
import subprocess
import sys

from fetch_corpus import _load_manifest
from recall_gate import corpus_key, implementation_identity


def source_identity(root: Path, expected: str) -> None:
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                              text=True, encoding='utf-8', check=True, timeout=30).stdout.strip()
    if git('rev-parse', 'HEAD') != expected:
        raise ValueError('Corpus pin mismatch')
    if git('status', '--porcelain', '--untracked-files=normal'):
        raise ValueError('Corpus source is modified or has untracked files')


def claims_from_report(report: dict, root: Path, pin: str, rules: list[str]) -> list[dict]:
    summary = report.get('summary') or {}
    if summary.get('files_errored') or summary.get('items_truncated'):
        raise ValueError('Failed or presentation-truncated population')
    claims = []
    for file in report.get('files', []):
        if file.get('status') in ('error', 'warning', 'skipped'):
            continue
        relative = Path(file['file'])
        path = (root / relative).resolve()
        if not path.is_relative_to(root.resolve()) or not path.is_file():
            raise ValueError('Claim source is missing or escapes the corpus')
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        for finding in file.get('detections', []):
            if finding['rule_code'] not in rules:
                continue
            claim = {'file': relative.as_posix(), 'source_sha256': digest,
                     'stratum': relative.parts[0] if len(relative.parts) > 1 else '.',
                     **{key: finding.get(key) for key in ['rule_code', 'line', 'column', 'message', 'suggestion']}}
            claim['id'] = hashlib.sha256(json.dumps([pin, claim], sort_keys=True).encode()).hexdigest()[:20]
            claims.append(claim)
    if len({c['id'] for c in claims}) != len(claims):
        raise ValueError('Duplicate claim identities')
    return claims


def stratified_sample(claims: list[dict], rules: list[str], limit: int) -> list[dict]:
    if limit <= 0:
        raise ValueError('Sample size must be positive')
    selected = []
    for rule in rules:
        groups = defaultdict(list)
        for claim in claims:
            if claim['rule_code'] == rule:
                groups[claim['stratum']].append(claim)
        if not groups:
            raise ValueError(f'{rule}: no claims; select another measured rule')
        ordered = {key: sorted(group, key=lambda c: c['id']) for key, group in sorted(groups.items())}
        chosen = []
        depth = 0
        while len(chosen) < limit:
            layer = [group[depth] for group in ordered.values() if len(group) > depth]
            if not layer:
                break
            chosen.extend(layer[:limit-len(chosen)])
            depth += 1
        counts = Counter(c['stratum'] for c in chosen)
        if set(counts) != set(ordered):
            raise ValueError(f'{rule}: sample size omits a stratum; increase --per-rule')
        selected += [{**c, 'stratum_population': len(groups[c['stratum']]),
                       'stratum_sample': counts[c['stratum']]} for c in chosen]
    return selected


def sampling_interval(claims: list[dict], labels: dict) -> list:
    """Conservative weighted Wilson envelope, conditional on decided labels.

    Bonferroni adjusts the stratum intervals. Census strata have no sampling
    uncertainty; label uncertainty is reported separately by score().
    """
    strata = defaultdict(list)
    for claim in claims:
        strata[claim.get('stratum', claim['id'])].append(claim)
    z = NormalDist().inv_cdf(1 - .05 / (2 * len(strata)))
    bounds = [0.0, 0.0]
    weight = 0.0
    for group in strata.values():
        decided = [c for c in group if labels[c['id']] != 'uncertain']
        n = len(decided)
        if not n:
            continue
        p = sum(labels[c['id']] == 'tp' for c in decided) / n
        population = group[0]['stratum_population']
        sample_size = group[0]['stratum_sample']
        w = population * n / sample_size
        if sample_size == population:
            lower = upper = p
        else:
            denominator = 1 + z * z / n
            center = (p + z * z / (2 * n)) / denominator
            radius = z * sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denominator
            lower, upper = max(0.0, center - radius), min(1.0, center + radius)
        bounds[0] += w * lower
        bounds[1] += w * upper
        weight += w
    return [bound / weight for bound in bounds] if weight else [None, None]


def rater_agreement(first: dict, second: dict) -> dict:
    """Agreement on a blind reviewed subset, with three-category Cohen's kappa."""
    original = {r['id']: r['verdict'] for r in first['labels']}
    subset = second['labels']
    if not subset or len({r['id'] for r in subset}) != len(subset):
        raise ValueError('Second-rater subset must contain unique claims')
    for row in subset:
        if (row['id'] not in original or row['verdict'] not in ('tp', 'fp', 'uncertain')
                or not row.get('reason', '').strip()):
            raise ValueError('Invalid second-rater label')
    size = len(subset)
    counts_a = Counter(original[r['id']] for r in subset)
    counts_b = Counter(r['verdict'] for r in subset)
    observed = sum(original[r['id']] == r['verdict'] for r in subset) / size
    chance = sum(counts_a[k] * counts_b[k] for k in ('tp', 'fp', 'uncertain')) / (size * size)
    return {'sample_size': size, 'percent_agreement': observed * 100,
            'cohens_kappa': (observed - chance) / (1 - chance) if chance < 1 else None,
            'disagreement_ids': [r['id'] for r in subset if original[r['id']] != r['verdict']],
            'second_reviewer': second.get('reviewer'), 'method': second.get('method')}


def score(sample: dict, labels: dict, root: Path, second_labels: dict | None = None) -> dict:
    source_identity(root, sample['source']['sha'])
    expected = {c['id']: c for c in sample['claims']}
    if len(expected) != len(sample['claims']):
        raise ValueError('Duplicate sampled claim identities')
    rows = labels['labels']
    if (len({r['id'] for r in rows}) != len(rows)
            or {r['id'] for r in rows} != set(expected)):
        raise ValueError('Labels must cover each sampled claim exactly once')
    results = {}
    for rule in sample['rules']:
        counts = Counter(); weights = Counter()
        for label in rows:
            claim = expected[label['id']]
            if claim['rule_code'] != rule:
                continue
            if label['verdict'] not in ('tp', 'fp', 'uncertain') or not label.get('reason', '').strip():
                raise ValueError('Every label needs a TP/FP/uncertain verdict and reason')
            path = (root / claim['file']).resolve()
            if (not path.is_relative_to(root.resolve())
                    or hashlib.sha256(path.read_bytes()).hexdigest() != claim['source_sha256']):
                raise ValueError('Reviewed source changed')
            if not 0 < claim['stratum_sample'] <= claim['stratum_population']:
                raise ValueError('Invalid stratum counts')
            counts[label['verdict']] += 1
            weights[label['verdict']] += claim['stratum_population'] / claim['stratum_sample']
        if not counts:
            raise ValueError(f'{rule}: no reviewed claims')
        total = sum(weights.values()); decided = weights['tp'] + weights['fp']
        results[rule] = {'sample_counts': dict(counts), 'sample_size': sum(counts.values()),
                         'estimated_population': total,
                         'weighted_decidable_precision': weights['tp']/decided if decided else None,
                         'weighted_precision_bounds': [weights['tp']/total, (weights['tp']+weights['uncertain'])/total],
                         'sampling_precision_interval_95': sampling_interval(
                             [c for c in sample['claims'] if c['rule_code'] == rule],
                             {r['id']: r['verdict'] for r in rows}),
                         'sampling_method': 'Weighted Wilson stratum envelope with Bonferroni adjustment; conditional on decided labels; census strata exact'}
    report = {'source': sample['source'], 'implementation': sample['implementation'], 'rules': results,
            'interpretation': 'Stratum-weighted conformance estimates on emitted claims only. Label bounds and approximate conservative 95% sampling intervals are separate; neither establishes usefulness, recall or runtime correctness.'}
    if second_labels is not None:
        report['rater_agreement'] = rater_agreement(labels, second_labels)
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['sample', 'score'])
    parser.add_argument('--corpus-root', type=Path, required=True)
    parser.add_argument('--corpus', default='python-celery')
    parser.add_argument('--rules', nargs='+', default=['D001', 'B006', 'I001'])
    parser.add_argument('--per-rule', type=int, default=20)
    parser.add_argument('--sample', type=Path)
    parser.add_argument('--labels', type=Path)
    parser.add_argument('--second-labels', type=Path, help='Blind second-rater subset labels')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.mode == 'score' and (args.sample is None or args.labels is None):
        parser.error('score requires --sample and --labels')
    try:
        entry = next(e for e in _load_manifest()['corpora'] if corpus_key(e) == args.corpus)
        root = (args.corpus_root / args.corpus).resolve()
        source_identity(root, entry['sha'])
        if args.mode == 'score':
            sample = json.loads(args.sample.read_text(encoding='utf-8'))
            if sample['source']['sha'] != entry['sha']:
                raise ValueError('Sample pin differs from manifest')
            output = score(sample, json.loads(args.labels.read_text(encoding='utf-8')), root,
                           json.loads(args.second_labels.read_text(encoding='utf-8')) if args.second_labels else None)
        else:
            identity = implementation_identity()
            result = subprocess.run([sys.executable, '-m', 'reveal', 'check', str(root),
                                     '--select='+','.join(args.rules), '--format=json', '--no-snippets'],
                                    capture_output=True, text=True, encoding='utf-8', timeout=600)
            report = json.loads(result.stdout)
            if result.returncode not in (0, 1, 3):
                raise ValueError(f'Population command failed: {result.stderr}')
            source_identity(root, entry['sha'])
            if identity != implementation_identity():
                raise ValueError('Reveal implementation changed during measurement')
            claims = claims_from_report(report, root, entry['sha'], args.rules)
            output = {'source': {'id': args.corpus, 'sha': entry['sha'], 'repo': entry['repo']},
                      'implementation': identity, 'python': sys.version, 'rules': args.rules,
                      'population_summary': report['summary'],
                      'population_by_rule': dict(Counter(c['rule_code'] for c in claims)),
                      'excluded_files': [{k: f.get(k) for k in ('file', 'status', 'detail')}
                                         for f in report['files'] if f.get('status') in ('warning', 'error', 'skipped')],
                      'claims': stratified_sample(claims, args.rules, args.per_rule)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2)+'\n', encoding='utf-8')
    except (ValueError, OSError, KeyError, TypeError, StopIteration, subprocess.SubprocessError) as exc:
        print(f'Precision measurement failed: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

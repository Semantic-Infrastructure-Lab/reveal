"""BACK-2105: the per-language call-graph confidence constants are derived from the recall snapshot.

``defaults.CALL_GRAPH_EXTRACTION_CONFIDENCE`` was typed from recall figures recorded over several
earlier validations; the committed snapshot of 2026-10-20 (``snapshot_2026-10-20``, one harness
JSON per language pair and mode) disagreed with it for ten languages. The rule, stated in
``defaults.py``: **a language's confidence is the lowest edge recall (edges found over oracle
edges, rounded to four places) over the snapshot's callers, depth 2 and callees runs for that
language**, so the one number an answer reports never exceeds the worst measured direction.

The snapshot lives in the private repository, so the pin test below runs only where it is
reachable (the sibling ``internal-docs`` of a full checkout, or ``REVEAL_CALLS_ORACLE_SNAPSHOT``)
and skips everywhere else, CI included. The arithmetic test and the table-shape test always run.
"""
import json
import os
from pathlib import Path

import pytest

from reveal.adapters.calls.confidence import SNAPSHOT_LANGUAGES
from reveal.defaults import CALL_GRAPH_EXTRACTION_CONFIDENCE

SNAPSHOT_NAME = 'snapshot_2026-10-20'
_RELATIVE = Path('internal-docs') / 'planning' / 'dogfood-findings' / 'calls-recall-oracle' / SNAPSHOT_NAME
MODES = ('callers', 'depth2', 'callees')
# The harness pair that scores each language. Two corpora score javascript; tsx files are scored
# inside the typescript corpus. The ruby_raw_with_symbolic_expansion run is a diagnostic variant
# (the oracle's symbolic expansion kept), not a mode, and is not a figure.
PAIRS = {'javascript': ('js_excalidraw', 'js_threejs'), 'tsx': ('typescript',)}


def recall_floor(figures):
    """The rule: the lowest found/oracle over the (found, oracle) pairs, to four places.
    A run with no oracle edge scores nothing and is skipped; no figure at all is an error."""
    ratios = [found / oracle for found, oracle in figures if oracle]
    if not ratios:
        raise ValueError('no measured figure')
    return round(min(ratios), 4)


def snapshot_dir():
    named = os.environ.get('REVEAL_CALLS_ORACLE_SNAPSHOT')
    candidates = [Path(named)] if named else [Path(__file__).resolve().parents[2] / _RELATIVE]
    return next((path for path in candidates if path.is_dir()), None)


def snapshot_figures(directory, language):
    figures = []
    for pair in PAIRS.get(language, (language,)):
        for mode in MODES:
            run = json.loads((directory / mode / f'{pair}.json').read_text(encoding='utf-8'))
            assert not run['failures'] and not run['errored_targets'], (pair, mode)
            figures.append((run['total_found_edges'], run['total_oracle_edges']))
    return figures


# ------------------------------------------------------------------ always run

def test_the_rule_is_the_lowest_recall_to_four_places():
    assert recall_floor([(1000, 1000), (1000, 1000)]) == 1.0
    assert recall_floor([(684, 700), (2020, 2023), (18190, 18203)]) == 0.9771      # 0.97714
    assert recall_floor([(1792, 1866), (2068, 2155), (318, 322)]) == 0.9596        # 0.95963, not the 0.9603 of callers
    assert recall_floor([(6358, 6360), (695, 696), (5, 5)]) == 0.9986              # 0.99856 rounds up
    assert recall_floor([(0, 0), (3, 4)]) == 0.75                                  # an empty run scores nothing


def test_a_language_with_no_figure_is_an_error_not_full_confidence():
    with pytest.raises(ValueError):
        recall_floor([])
    with pytest.raises(ValueError):
        recall_floor([(0, 0)])


def test_the_table_covers_the_snapshot_languages_with_four_place_fractions():
    assert set(CALL_GRAPH_EXTRACTION_CONFIDENCE) == SNAPSHOT_LANGUAGES
    for language, value in CALL_GRAPH_EXTRACTION_CONFIDENCE.items():
        assert 0 < value <= 1 and value == round(value, 4), language


# ------------------------------------------------------- needs the private snapshot

@pytest.mark.skipif(snapshot_dir() is None,
                    reason=f'the private recall snapshot {SNAPSHOT_NAME} is not reachable from this checkout '
                           '(set REVEAL_CALLS_ORACLE_SNAPSHOT to its directory)')
@pytest.mark.parametrize('language', sorted(CALL_GRAPH_EXTRACTION_CONFIDENCE))
def test_the_constant_is_the_snapshot_floor(language):
    figures = snapshot_figures(snapshot_dir(), language)
    assert CALL_GRAPH_EXTRACTION_CONFIDENCE[language] == recall_floor(figures), (language, figures)

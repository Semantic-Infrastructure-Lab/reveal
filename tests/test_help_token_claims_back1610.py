"""BACK-1610: a token size typed next to a help page must match the page.

Shipped help gives agents a cost before they load a page ("help://quick
(~1,600 tokens)"), and the typed numbers drifted: help://quick put
help://schemas/all at ~10K (it is ~3.2K), the index put help://adapters at
~1,400 (~2,300), and help://tricks at ~3,500 (~12,900). The index's guide costs
are now measured from the files; this test measures every other claim.

A claim is a ``~N tokens`` / ``~NK tokens`` literal; it is checked against the
page named nearest before it on the same line (``help://...``, ``--agent-help``,
``--discover``), rendered in text and counted as chars / 4 (the estimate V014
and the help footer use). Comments in code and release-history lines narrate
the past and are skipped. A claim within TOLERANCE of the measured size passes.
"""

import re
from contextlib import redirect_stderr, redirect_stdout
from functools import lru_cache
from io import StringIO
from pathlib import Path

import pytest

from reveal.main import main

ROOT = Path(__file__).parent.parent
TOLERANCE = 0.30
_CLAIM = re.compile(r'~\s?([0-9][0-9,]*(?:\.[0-9]+)?)\s?(K)?\s*tokens\b', re.IGNORECASE)
_REF = re.compile(r"help://[a-z0-9_./-]*[a-z0-9/]|--agent-help\b|--discover\b")
_HISTORY = re.compile(r'^\s*(- \*\*v\d|#)')


def _shipped_files():
    yield ROOT / 'README.md'
    yield from sorted((ROOT / 'reveal' / 'docs').rglob('*.md'))
    yield from sorted(p for p in (ROOT / 'reveal').rglob('*.py'))


def _claims():
    """(where, ref, claimed_tokens) for every token claim paired with a page."""
    found = []
    for path in _shipped_files():
        is_code = path.suffix == '.py'
        for n, line in enumerate(path.read_text(encoding='utf-8').splitlines(), 1):
            stripped = line.strip()
            if _HISTORY.match(stripped) and (is_code or stripped.startswith('- **v')):
                continue
            refs = [(m.start(), m.group(0)) for m in _REF.finditer(line)]
            for claim in _CLAIM.finditer(line):
                before = [ref for pos, ref in refs if pos < claim.start()]
                if not before:
                    continue
                number = float(claim.group(1).replace(',', ''))
                tokens = int(number * 1000) if claim.group(2) else int(number)
                found.append((f'{path.relative_to(ROOT).as_posix()}:{n}', before[-1], tokens))
    return found


@lru_cache(maxsize=None)
def _measured(ref: str) -> int:
    out = StringIO()
    with redirect_stdout(out), redirect_stderr(StringIO()):
        try:
            main(['reveal', ref])
        except SystemExit:
            pass
    return len(out.getvalue()) // 4


def _within(claimed: int, actual: int) -> bool:
    return abs(claimed - actual) <= TOLERANCE * actual


def test_claims_are_found():
    # Positive control: the scan still sees the claims it is meant to check.
    refs = {ref for _, ref, _ in _claims()}
    assert {'help://quick', '--agent-help', 'help://agent/full'} <= refs


@pytest.mark.parametrize('where, ref, claimed', _claims(), ids=lambda v: str(v))
def test_typed_token_size_matches_the_page(where, ref, claimed):
    actual = _measured(ref)
    assert _within(claimed, actual), (
        f'{where} says {ref} is ~{claimed:,} tokens; it renders ~{actual:,} '
        f'(chars/4). Re-measure: reveal {ref} | wc -c')


def test_index_special_topic_costs_match_the_pages():
    """The help:// index's generated topics (quick, adapters, relationships)."""
    index = StringIO()
    with redirect_stdout(index):
        main(['reveal', 'help://'])
    text = index.getvalue()
    section = text.split('SPECIAL TOPICS', 1)[1].split('\n---', 1)[0]
    blocks = re.findall(r'^  ([a-z-]+) +- .*?Token cost: ~([0-9,]+) tokens', section, re.M | re.S)
    assert blocks, 'no special topic with a token cost found (positive control)'
    wrong = []
    for topic, claimed in blocks:
        actual = _measured(f'help://{topic}')
        if not _within(int(claimed.replace(',', '')), actual):
            wrong.append(f'help://{topic}: index says ~{claimed}, renders ~{actual:,}')
    assert not wrong, '; '.join(wrong)

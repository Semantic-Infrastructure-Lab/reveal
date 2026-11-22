"""surface text: the '… N more' hint names a way that shows the rest.

The legacy --top cut the text only, so its hint says to omit it (BACK-2623: the hint names no retiring spelling, and
a category filter never lifted the cut, so it is not offered). --limit cuts the answer itself: the heading keeps the
uncut count and the shared result-control note discloses the cut after the body.
"""

from reveal.rendering.adapters.surface import surface_text

ENTRIES = [{'type': 'env_var', 'name': n, 'expr': 'os.getenv', 'file': 'a.py', 'line': i}
           for i, n in enumerate(['A', 'B', 'C'], 1)]


def _report(surfaces, **extra):
    return {'path': '.', 'total': 3, 'surfaces': surfaces, 'matrix': {}, 'unparsed_files': [],
            'recovered_files': [], **extra}


def _hint(surfaces, top=1, **extra):
    return [line for line in surface_text(_report(surfaces, **extra), top=top).splitlines() if 'more (' in line]


def test_type_filtered_report_offers_omitting_top():
    assert _hint({'env': ENTRIES}) == ['  … 2 more (omit --top to see all)']


def test_unfiltered_report_offers_the_same_and_no_category_filter():
    surfaces = {k: [] for k in ('cli', 'http', 'mcp', 'network', 'db', 'sdk', 'fs', 'subprocess')}
    surfaces['env'] = ENTRIES
    assert _hint(surfaces) == ['  … 2 more (omit --top to see all)']


def test_a_limit_cut_keeps_the_uncut_count_and_leaves_its_disclosure_to_the_shared_note():
    cut = {'type': 'truncated', 'field': 'surfaces.env', 'shown': 1, 'total': 3, 'cause': 'limit'}
    text = surface_text(_report({'env': ENTRIES[:1]}, meta={'warnings': [cut]}))
    assert 'Environment variables (3):' in text and 'more (' not in text

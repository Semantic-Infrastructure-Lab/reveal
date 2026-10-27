"""surface text: the --top hint does not suggest the --type filter already in effect.

With `--type env` the report holds only the `env` category, so "or --type env
to see all" would show nothing more.
"""

from reveal.rendering.adapters.surface import surface_text

ENTRIES = [{'type': 'env_var', 'name': n, 'expr': 'os.getenv', 'file': 'a.py', 'line': i}
           for i, n in enumerate(['A', 'B', 'C'], 1)]


def _report(surfaces):
    return {'path': '.', 'total': 3, 'surfaces': surfaces, 'matrix': {}, 'unparsed_files': [],
            'recovered_files': []}


def _hint(surfaces):
    return [line for line in surface_text(_report(surfaces), top=1).splitlines() if 'more (use' in line]


def test_type_filtered_report_offers_only_top():
    assert _hint({'env': ENTRIES}) == ['  … 2 more (use --top 3 to see all)']


def test_unfiltered_report_still_offers_type():
    surfaces = {k: [] for k in ('cli', 'http', 'mcp', 'network', 'db', 'sdk', 'fs', 'subprocess')}
    surfaces['env'] = ENTRIES
    assert _hint(surfaces) == ['  … 2 more (use --top 3 or --type env to see all)']

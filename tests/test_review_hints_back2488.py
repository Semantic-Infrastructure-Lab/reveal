"""BACK-2488: every "see all" command `review` prints must run and return the whole list.

review cut its hotspots section with the hint ``reveal hotspots <path> --all``, and the
hotspots command rejects --all (exit 2). Run each emitted hint as a user would, and check
it answers with at least the total that review said it cut.
"""
import json
import shlex

from conftest import _run_reveal_in

_SECTION_ITEMS = {'hotspots': 'hotspots', 'complexity': 'results'}  # hotspots: metrics --hotspots (BACK-2149)


def _branchy(name):
    lines = [f'def {name}(x):']
    lines += [f"    {'if' if i == 1 else 'elif'} x == {i}: return {i}" for i in range(1, 14)]
    return '\n'.join(lines + ['    return 0', ''])


def test_every_see_all_hint_runs_and_returns_the_cut_total(tmp_path):
    proj = tmp_path / 'proj'
    proj.mkdir()
    for i in range(12):  # more than review's top-10 sections keep
        (proj / f'm{i}.py').write_text(_branchy(f'f{i}'), encoding='utf-8')

    review = _run_reveal_in(tmp_path, 'review', 'proj', '--format', 'json')
    body = json.loads(review.stdout)
    cuts = {w['field']: w for w in body['meta']['warnings']
            if w.get('type') == 'truncated' and 'see all: ' in w.get('message', '')}
    assert set(cuts) == set(_SECTION_ITEMS), body['meta']['warnings']  # positive control

    for field, warning in cuts.items():
        assert warning['total'] > warning['shown']
        hint = warning['message'].split('see all: ', 1)[1].replace('<path>', 'proj')
        argv = shlex.split(hint)
        assert argv[0] == 'reveal', hint
        result = _run_reveal_in(tmp_path, *argv[1:], '--format', 'json')
        assert result.returncode == 0, (hint, result.stderr)
        assert 'deprecated' not in result.stderr, (hint, result.stderr)  # a hint never names a retired spelling
        items = json.loads(result.stdout)[_SECTION_ITEMS[field]]
        assert len(items) >= warning['total'], (hint, len(items), warning['total'])

"""Git zoned fractional bounds mean the same instant on supported Python versions."""
from datetime import datetime, timedelta, timezone
import json

import pytest

from conftest import _run_reveal_direct as run
from reveal.adapters.git.adapter import GitAdapter
from reveal.adapters.git.queries import _date_bound

pygit2 = pytest.importorskip('pygit2')


@pytest.mark.parametrize('fraction', ['5', '50', '1234', '12345', '1234567', '0000000'])
@pytest.mark.parametrize('clock,zone,offset', [('12:00:00', 'Z', 0),
                                              ('14:00:00', '+02:00', 2),
                                              ('00:00:00', '-1200', -12)])
def test_fractional_zoned_bounds_normalize_to_microseconds(fraction, clock, zone, offset):
    micros = int(fraction[:6].ljust(6, '0'))
    local = datetime(2026, 1, 15, int(clock[:2]), microsecond=micros,
                     tzinfo=timezone(timedelta(hours=offset))).astimezone()
    expected = local.strftime('%Y-%m-%d %H:%M:%S')
    if micros:
        expected += f'.{micros:06d}'
    assert _date_bound(f'2026-01-15T{clock}.{fraction}{zone}') == expected


@pytest.fixture
def fractional_repo(tmp_path):
    repo = pygit2.init_repository(str(tmp_path))
    parents = []
    noon = int(datetime(2026, 1, 15, 12, tzinfo=timezone.utc).timestamp())
    for index, message in enumerate(('before', 'after')):
        (tmp_path / 'sample.py').write_text(f'value = {index}\n', encoding='utf-8')
        repo.index.add('sample.py')
        signature = pygit2.Signature('Reviewer', 'reviewer@example.com', noon + index, 0)
        parents = [repo.create_commit('HEAD', signature, signature, message, repo.index.write_tree(), parents)]
    return tmp_path


@pytest.mark.parametrize('query,expected', [
    ('date>2026-01-15T12:00:00.5Z', ['after']),
    ('date<2026-01-15T12:00:00.5Z', ['before']),
    ('since=2026-01-15T14:00:00.50+02:00', ['after']),
    ('until=2026-01-15T00:00:00.1234-1200', ['before']),
    ('date=2026-01-15T12:00:00.5Z..2026-01-15T12:00:01.5Z', ['after']),
])
@pytest.mark.parametrize('entry', ['adapter', 'cli'])
def test_fractional_date_queries_select_expected_commits(fractional_repo, query, expected, entry):
    query = 'type=history&' + query
    if entry == 'cli':
        result = run(f'git://{fractional_repo}?{query}', '--format', 'json')
        assert result.returncode == 0, result.stderr
        answer = json.loads(result.stdout)
    else:
        answer = GitAdapter(str(fractional_repo), query).get_structure()
    assert [row['message'] for row in answer['history']] == expected


@pytest.mark.parametrize('fraction', ['500', '500000'])
def test_previously_supported_fraction_widths_keep_same_instant(fraction):
    assert _date_bound(f'2026-01-15T12:00:00.{fraction}Z') == _date_bound('2026-01-15T12:00:00.500000Z')


@pytest.mark.parametrize('bound', ['2026-13-15T12:00:00.5Z', '2026-01-15T25:00:00.1234+02:00'])
def test_invalid_calendar_time_still_raises(bound):
    with pytest.raises(ValueError, match='not a time'):
        _date_bound(bound)

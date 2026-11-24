"""The one ``detail`` level codec (COMMAND_MODEL "How much of it", BACK-2774 ruling S1).

``detail`` is one scale on every noun. Git's converter read a boolean (a bare ``?detail`` key, the Python keyword
``detail=True``) as the old two-level spelling and left every other value to its choices; Calls needs the same reading
when its boolean ``detail`` becomes the string control normal|full, so the converter moved to the binder beside
``boolean_value`` (the second use is a move, not a copy). Behaviour-preserving for Git.
"""
import pytest

from reveal.adapters.git.params import DETAIL as GIT_DETAIL
from reveal.utils.query_binding import detail_level

pytestmark = [pytest.mark.unit]


@pytest.mark.parametrize('raw,level', [(True, 'full'), (False, 'normal'), ('normal', 'normal'), ('full', 'full'),
                                       ('raw', 'raw'), ('summary', 'summary')])
def test_a_boolean_is_the_two_level_spelling_and_a_name_stays_a_name(raw, level):
    assert detail_level(raw) == level


@pytest.mark.parametrize('raw', ['', '   ', 'a\x00b', None, 3])
def test_a_blank_or_non_text_value_is_refused(raw):
    with pytest.raises(ValueError):
        detail_level(raw)


def test_git_reads_detail_through_it_with_its_choices_and_value_entries():
    assert GIT_DETAIL.convert is detail_level
    assert GIT_DETAIL.validate(True) == 'full' and GIT_DETAIL.validate(False) == 'normal'
    assert GIT_DETAIL.canonical_value('detail', 'summary') == 'normal'  # its value-keyed legacy entry, unchanged
    with pytest.raises(ValueError, match="detail must be one of"):
        GIT_DETAIL.validate('bogus')

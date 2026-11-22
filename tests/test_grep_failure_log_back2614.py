"""A grep candidate the worker cannot read is returned as its PathFailure, which the caller discloses (markdown's
``unreadable_files``, BACK-2408). It is not logged as a WARNING too: that printed the absolute path and the OSError text
on stderr beside the JSON that already carries the failure (COMMAND_MODEL "Transports"; BACK-2614 B10)."""
import logging

from reveal.reveal_types import PathFailure
from reveal.utils import parallel
from reveal.utils.path_utils import to_posix


def test_an_unreadable_candidate_is_returned_not_logged_as_a_warning(tmp_path, caplog):
    missing = tmp_path / 'missing.md'
    with caplog.at_level(logging.WARNING):
        outcome = parallel._scan_one((missing, (b'needle',)))
    assert isinstance(outcome, PathFailure) and outcome.path == to_posix(missing)
    assert 'FileNotFoundError' in outcome.cause and to_posix(tmp_path) not in outcome.cause
    assert [record for record in caplog.records if record.levelno >= logging.WARNING] == []


def test_a_readable_candidate_is_the_sibling(tmp_path, caplog):
    match = tmp_path / 'match.md'
    match.write_bytes(b'needle')
    with caplog.at_level(logging.WARNING):
        assert parallel._scan_one((match, (b'needle',))) == match
    assert caplog.records == []

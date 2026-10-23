"""--provenance is process state; a test that sets it must not leak it into the next test (BACK-2086).

`reveal.utils.json_utils._provenance_enabled` is a module global that every in-process CLI run
sets from its flags. A test that leaves it on made the next test in the same xdist worker print an
`execution` block that `--batch` does not, so `test_batch_answers_like_the_uri[architecture]`
failed or passed by scheduling order. These two tests are order-dependent on purpose: run them
serially (`-n 0`), in file order.
"""
from reveal.utils import json_utils


def test_a_test_may_turn_provenance_on():
    json_utils.set_provenance_enabled(True)
    assert json_utils._provenance_enabled is True


def test_the_next_test_starts_with_provenance_off():
    assert json_utils._provenance_enabled is False

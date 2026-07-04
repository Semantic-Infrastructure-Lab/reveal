"""Test file — pack's handling of test files must be explicit, not a silent drop."""

from core import validate


def test_validate_rejects_none():
    try:
        validate(None)
    except ValueError:
        return
    assert False

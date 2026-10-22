"""The checkout-scan guard in conftest (BACK-2159): a test whose imports/depends scan root resolves
at the checkout or above fails at teardown unless marked ``scans_checkout``."""

import pytest

from conftest import _CHECKOUT, _is_checkout_scan_root, _run_reveal_direct

FIXTURE = _CHECKOUT / "tests" / "fixtures" / "pack" / "sample_repo"


def test_checkout_and_its_ancestors_count_as_the_checkout(tmp_path):
    assert _is_checkout_scan_root(_CHECKOUT)
    assert _is_checkout_scan_root(_CHECKOUT.parent)


def test_negative_control_a_fixture_dir_or_tmp_copy_does_not(tmp_path):
    assert not _is_checkout_scan_root(FIXTURE)
    assert not _is_checkout_scan_root(tmp_path)


@pytest.mark.scans_checkout
def test_default_scope_on_an_in_repo_fixture_resolves_at_the_checkout():
    """Without ``scope=path`` the shared climb leaves the fixture for the repo root, which is what
    the guard exists to catch; marked, it passes. Unmarked this file's run went red (2026-10-22)."""
    assert _run_reveal_direct(f"imports://{FIXTURE}", "--format", "json").returncode == 0


def test_scope_path_keeps_the_scan_inside_the_fixture():
    """Unmarked: the guard would fail this test at teardown if the scan climbed to the repo."""
    assert _run_reveal_direct(f"imports://{FIXTURE}?scope=path", "--format", "json").returncode == 0

"""scripts/ci_editable_guard.sh refuses to repoint the shared CI venv (BACK-1680).

Exercised against fake venv directories (a dist-info/direct_url.json), never the real
~/.cache/reveal-ci venv.
"""
import json
import shutil
import subprocess
from pathlib import Path

import pytest

GUARD = Path(__file__).resolve().parent.parent / "scripts" / "ci_editable_guard.sh"
CI_LOCAL = GUARD.with_name("ci-local.sh")

pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _fake_venv(root: Path, target: Path | None, editable: bool = True) -> Path:
    venv = root / "venv"
    dist = venv / "lib" / "python3.12" / "site-packages" / "reveal_cli-0.0.0.dist-info"
    dist.mkdir(parents=True)
    if target is not None:
        info = {"url": target.as_uri()}
        if editable:
            info["dir_info"] = {"editable": True}
        (dist / "direct_url.json").write_text(json.dumps(info), encoding="utf-8")
    return venv


def _guard(venv: Path, top: Path, **env):
    import os

    full = {**os.environ, **env}

    return subprocess.run(
        ["bash", "-c", f'source "{GUARD.as_posix()}"; ci_editable_guard "$1" "$2"', "_", str(venv), str(top)],
        capture_output=True, text=True, timeout=30, env=full,
    )


def test_refuses_when_editable_target_is_another_checkout(tmp_path):
    main, wt = tmp_path / "main", tmp_path / "wt"
    main.mkdir(); wt.mkdir()
    r = _guard(_fake_venv(tmp_path, main), wt)
    assert r.returncode == 1
    assert "refusing" in r.stderr and "wt-check.sh" in r.stderr
    assert main.as_posix() in r.stderr and wt.as_posix() in r.stderr


def test_allows_same_checkout_even_through_a_symlink(tmp_path):
    main = tmp_path / "main"; main.mkdir()
    link = tmp_path / "link"
    try:
        link.symlink_to(main, target_is_directory=True)
    except OSError:
        pytest.skip("symlinks unavailable")
    venv = _fake_venv(tmp_path, main)
    assert _guard(venv, main).returncode == 0
    assert _guard(venv, link).returncode == 0


@pytest.mark.parametrize("kind", ["no-venv", "no-direct-url", "not-editable"])
def test_allows_fresh_or_non_editable_venv(tmp_path, kind):
    top = tmp_path / "top"; top.mkdir()
    if kind == "no-venv":
        venv = tmp_path / "absent"
    elif kind == "no-direct-url":
        venv = _fake_venv(tmp_path, None)
    else:
        venv = _fake_venv(tmp_path, tmp_path / "other", editable=False)
    assert _guard(venv, top).returncode == 0


def test_explicit_override_allows_and_says_so(tmp_path):
    main, wt = tmp_path / "main", tmp_path / "wt"
    main.mkdir(); wt.mkdir()
    r = _guard(_fake_venv(tmp_path, main), wt, REVEAL_CI_ALLOW_REPOINT="1")
    assert r.returncode == 0 and "repointing" in r.stderr


def test_ci_local_runs_the_guard_before_touching_the_venv():
    src = CI_LOCAL.read_text(encoding="utf-8")
    guard = src.index("ci_editable_guard \"$VENV\"")
    assert guard < src.index('rm -rf "$VENV"') and guard < src.index("pip install -q --upgrade pip")

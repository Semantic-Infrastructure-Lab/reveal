"""BACK-431 Issue G tier C — repository-surface smoke coverage for the 8
structure-only languages (Shell, Dockerfile, SQL, HCL, PowerShell, Batch,
HTML, Jupyter). See internal-docs/planning/LANGUAGE_DOGFOOD_CORPUS_2026-07-02.md
(Tier C section) for the corpus mapping this test exercises.

Unlike tests/test_smoke_tier.py's full-analysis languages (which get
--outline/--varflow/--exits/etc.), every tier C analyzer advertises only
"File structure" capability (confirmed via --language-info) — there is no
per-language nav-flag surface to smoke here. The bar is: analyzer routing
works, structure view and --check don't crash, on real (not synthetic) files.

The real files live inside the large open-source repos catalogued in
tests/corpus/manifest.yaml. That corpus is NOT committed and won't exist in CI
or a fresh checkout, so each case resolves its file through corpus_paths and is
skipped (never failed) when the corpus isn't materialized. Populate it with
`python scripts/fetch_corpus.py`.

Each tier C surface is exercised by a real file that happens to live inside a
different language's corpus repo (e.g. Kubernetes, a Go repo, carries the shell
and Dockerfile examples) — the mapping is (surface -> corpus language + path).
"""

import pytest
from conftest import _run_reveal_direct
from corpus_paths import require_corpus_file

# surface -> (corpus language, *path components under that repo's root)
CASES = {
    "shell": ("go", "cluster", "get-kube.sh"),
    "dockerfile": ("go", "build", "pause", "Dockerfile"),
    "sql": ("dart", "frontend", "rust-lib", "flowy-sqlite", "migrations",
            "2024-08-05-024351_chat_message_metadata", "up.sql"),
    "hcl": ("lua", "spec", "fixtures", "perf", "terraform", "digitalocean",
            "main.tf"),
    "powershell": ("typescript", "scripts", "xterm-symlink.ps1"),
    "batch": ("java", "gradlew.bat"),
    "html": ("javascript", "editor", "index.html"),
    "jupyter": ("typescript", "extensions", "vscode-api-tests", "testWorkspace",
                "test.ipynb"),
}


def _run(*args: str):
    return _run_reveal_direct(*args)


def _assert_sane(result, desc: str) -> None:
    assert result.returncode in (0, 1), (
        f"{desc}: unexpected crash (rc={result.returncode}): {result.stderr}"
    )
    assert "Traceback (most recent call last)" not in result.stderr, (
        f"{desc}: unhandled exception:\n{result.stderr}"
    )


@pytest.fixture(params=sorted(CASES))
def case(request):
    surface = request.param
    corpus_lang, *relative = CASES[surface]
    path = require_corpus_file(corpus_lang, *relative)  # skips if absent
    return surface, path


def test_structure_non_crash(case):
    lang, path = case
    result = _run(str(path))
    _assert_sane(result, f"{lang} structure")
    assert result.stdout.strip(), f"{lang}: structure view produced no output"


def test_check_non_crash(case):
    lang, path = case
    result = _run(str(path), "--check")
    _assert_sane(result, f"{lang} --check")

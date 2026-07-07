"""PyInstaller entry point for the Windows standalone binary.

PyInstaller freezes a *script*, not a console-script entry point, and
``reveal/main.py`` uses package-relative imports (``from .registry import ...``)
that only resolve when it's imported as ``reveal.main`` rather than run as a
loose script. This tiny launcher imports the package properly so those
relative imports resolve inside the frozen build.

Mirrors the ``reveal = "reveal.main:main"`` console_scripts entry in
pyproject.toml. See .github/workflows/windows-binary.yml and BACK-495.

Must live at the repo root, not under scripts/: PyInstaller puts the entry
script's own directory on the analysis sys.path, so ``--collect-all reveal``
only discovers the ``reveal/`` package when this launcher is its sibling.
From a subdirectory, package discovery fails (428 missing-submodule errors).
"""

from reveal.main import main

if __name__ == "__main__":
    main()

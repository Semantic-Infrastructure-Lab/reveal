"""PyInstaller entry point for the Windows standalone binary.

PyInstaller freezes a *script*, not a console-script entry point, and
``reveal/main.py`` uses package-relative imports (``from .registry import ...``)
that only resolve when it's imported as ``reveal.main`` rather than run as a
loose script. This tiny launcher imports the package properly so those
relative imports resolve inside the frozen build.

Mirrors the ``reveal = "reveal.main:main"`` console_scripts entry in
pyproject.toml. See .github/workflows/windows-binary.yml and BACK-495.
"""

from reveal.main import main

if __name__ == "__main__":
    main()

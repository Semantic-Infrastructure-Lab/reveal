"""Path text with forward slashes on every OS: the one serializer, ``to_posix``. It imports nothing of reveal's, so
any layer can use it (the adapter factory names a missing path with it); ``path_utils`` re-exports it."""

from pathlib import PurePath
from typing import Union


def to_posix(path: Union[str, PurePath]) -> str:
    """Serialize a path with forward slashes on every OS.

    Use this — never ``str(path)`` — whenever a path is written to output
    (JSON, display strings), used as a dict key, or compared as a string.
    ``str(Path)`` emits backslashes on Windows, which makes reveal's output
    non-portable and breaks cross-OS string comparisons (e.g. an agent or a
    test comparing against ``'tests/foo.py'`` fails on a Windows-produced
    ``'tests\\foo.py'``). Mirrors the ad-hoc ``.replace('\\\\', '/')`` idiom
    that was scattered across the codebase, in one canonical place.

    A path *relative* to a root serializes cleanly; pass the ``relative_to()``
    result. Absolute Windows paths keep their drive (``C:/foo/bar``).
    """
    if isinstance(path, PurePath):
        return path.as_posix()
    return str(path).replace('\\', '/')

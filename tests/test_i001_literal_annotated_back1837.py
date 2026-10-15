"""BACK-1837: I001 must not count Literal[...] values or Annotated metadata as uses.

A string is a forward reference only when it is the annotation itself or a type
argument in a type position.  Strings inside ``Literal[...]`` are values and the
metadata arguments of ``Annotated[T, m1, m2]`` are not types (pyflakes/ruff agree).
"""

import pytest

from reveal.rules.imports.I001 import I001

pytestmark = pytest.mark.component


def _unused(tmp_path, source):
    path = tmp_path / "m.py"
    path.write_text(source, encoding='utf-8')
    # The suggestion reads "Remove unused import: `Name`" (backticks only for some forms).
    return sorted(d.suggestion.split(": ", 1)[1].strip("`")
                  for d in I001().check(str(path), None, source))


@pytest.mark.parametrize("annotation", [
    'Literal["Spare"]',
    'typing.Literal["Spare"]',
    'typing_extensions.Literal["Spare"]',
    'Optional[Literal["Spare"]]',
    'Literal["Spare", "Spare"]',
    'Annotated[int, "Spare"]',
    'typing.Annotated[int, "Spare"]',
    'typing_extensions.Annotated[int, "Spare"]',
    'Annotated[int, "Spare", "Spare"]',
])
def test_value_strings_are_not_uses(tmp_path, annotation):
    source = (
        "import typing\nimport typing_extensions\n"
        "from typing import Literal, Annotated, Optional\n"
        "from pkg import Spare\n"
        f"def f(x: {annotation}): ...\n"
    )
    assert "Spare" in _unused(tmp_path, source)


@pytest.mark.parametrize("annotation", [
    '"Real"',
    'Optional["Real"]',
    'List["Real"]',
    'Annotated["Real", "meta"]',
    'typing.Annotated["Real", "meta"]',
    'Optional[Annotated["Real", 1]]',
])
def test_forward_references_still_count(tmp_path, annotation):
    source = (
        "import typing\n"
        "from typing import List, Annotated, Optional\n"
        "from pkg import Real\n"
        f"def f(x: {annotation}): ...\n"
    )
    assert "Real" not in _unused(tmp_path, source)


def test_return_annotation_forward_reference_counts(tmp_path):
    source = "from pkg import Real\ndef f() -> \"Real\": ...\n"
    assert _unused(tmp_path, source) == []


def test_reviewer_fixture(tmp_path):
    source = (
        "from typing import Literal, Annotated\n"
        "from pkg_a import Spare\n"
        "from pkg_b import Meta\n"
        "from pkg_c import Real\n\n\n"
        'def f(mode: Literal["Spare"], v: Annotated[int, "Meta"]) -> "Real":\n'
        "    return mode, v\n"
    )
    assert _unused(tmp_path, source) == ["Meta", "Spare"]

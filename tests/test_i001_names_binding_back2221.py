"""BACK-2221: I001's message names the unused binding; each binding is reported once.

``from typing import List, Tuple`` with both unused stays two findings (one per name,
as ruff F401 reports them and as ``imports://?unused`` lists them) -- each now says
which name, so the two lines are no longer indistinguishable.
"""
import pytest

from reveal.rules.imports.I001 import I001

pytestmark = pytest.mark.component


def _messages(tmp_path, source):
    path = tmp_path / "m.py"
    path.write_text(source, encoding='utf-8')
    return sorted(d.message for d in I001().check(str(path), None, source))


def test_from_import_names_each_unused_binding_once(tmp_path):
    messages = _messages(tmp_path, "from typing import List, Tuple\nx = 1\n")
    assert messages == ["Unused import detected: typing.List",
                        "Unused import detected: typing.Tuple"]


def test_only_the_unused_name_of_a_partly_used_import_is_named(tmp_path):
    messages = _messages(tmp_path, "from typing import List, Tuple\nx: List = []\n")
    assert messages == ["Unused import detected: typing.Tuple"]


def test_plain_and_aliased_imports_name_the_bound_name(tmp_path):
    messages = _messages(tmp_path, "import os\nimport json as js\nfrom a import b as c\n")
    assert messages == ["Unused import detected: a.b as c",
                        "Unused import detected: json as js",
                        "Unused import detected: os"]


def test_used_imports_are_not_reported(tmp_path):
    """Negative control: nothing unused, nothing reported."""
    assert _messages(tmp_path, "import os\nfrom typing import List\nx: List = [os]\n") == []

"""BACK-1394: Python 3.14 syntax must not make stdlib-ast consumers skip a file."""

import ast
import warnings

import pytest

from reveal.adapters.calls.index import find_uncalled
from reveal.adapters.surface import _scan_surface
from reveal.utils.pyparse import downlevel_source, parse_python

PEP758 = (
    "import os\n"
    "import requests\n"
    "\n"
    "def f():\n"
    "    try:\n"
    "        requests.get('http://x')\n"
    "    except ValueError, TypeError:\n"
    "        pass\n"
    "    return os.environ.get('MQTT_HOST')\n"
)


class TestDownlevel:

    @pytest.mark.parametrize('src, expected', [
        ("try:\n    f()\nexcept A, B:\n    pass\n", "try:\n    f()\nexcept (A, B):\n    pass\n"),
        ("try:\n    f()\nexcept* A, B:\n    pass\n", "try:\n    f()\nexcept* (A, B):\n    pass\n"),
        ("try:\n    f()\nexcept m.A, errs()[0], (B, C):\n    pass\n",
         "try:\n    f()\nexcept (m.A, errs()[0], (B, C)):\n    pass\n"),
        ('x = t"hi {name!r:>10}"\n', 'x = f"hi {name!r:>10}"\n'),
        ('x = rt"{a}" + Tr"{b}" + T"""{c}"""\n', 'x = rf"{a}" + Fr"{b}" + F"""{c}"""\n'),
    ])
    def test_rewrites(self, src, expected):
        assert downlevel_source(src) == expected

    @pytest.mark.parametrize('src', [
        "try:\n    f()\nexcept (A, B):\n    pass\n",       # already parenthesized
        "try:\n    f()\nexcept A:\n    pass\n",
        "try:\n    f()\nexcept A, B as e:\n    pass\n",     # invalid in 3.14 too: left alone
        "t = 1\nprint(t, 'x')\n",                          # a variable named t
        "s = f'{x}' + 'lit'\n",
    ])
    def test_leaves_other_code_alone(self, src):
        assert downlevel_source(src) is None


class TestParsePython:

    def test_pep758_parses_with_original_line_numbers(self):
        tree = parse_python(PEP758, 'm.py')
        handler = next(n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler))
        assert handler.lineno == 7
        assert [e.id for e in handler.type.elts] == ['ValueError', 'TypeError']

    def test_template_string_interpolations_are_visible(self):
        tree = parse_python('d = {}\nx = t"{d["k"]} {g()}"\n')
        assert any(isinstance(n, ast.Call) and n.func.id == 'g' for n in ast.walk(tree))

    def test_genuinely_invalid_source_raises_the_original_error(self):
        with pytest.raises(SyntaxError) as exc:
            parse_python("try:\n    f()\nexcept A, B as e:\n    pass\n")
        assert exc.value.lineno == 3
        with pytest.raises(SyntaxError):
            parse_python('print "py2"\n')

    def test_analyzed_files_syntax_warnings_are_not_printed(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter('always')
            parse_python('import re\np = re.compile("\\d+")\n')
        assert not [w for w in caught if issubclass(w.category, SyntaxWarning)]


class TestConsumers:

    @pytest.fixture(autouse=True)
    def _no_disk_cache(self, monkeypatch):
        monkeypatch.setenv('REVEAL_DISK_CACHE', '0')

    def test_surface_sees_a_314_file(self, tmp_path):
        (tmp_path / 'c.py').write_text(PEP758, encoding='utf-8')
        report = _scan_surface(tmp_path)
        assert [e['name'] for e in report['surfaces']['network']] == ['requests']
        assert [e['name'] for e in report['surfaces']['env']] == ['MQTT_HOST']
        assert report['unparsed_files'] == []

    def test_surface_discloses_a_file_it_cannot_parse(self, tmp_path):
        (tmp_path / 'old.py').write_text('import requests\nprint "py2"\n', encoding='utf-8')
        (tmp_path / 'ok.py').write_text('import os\nx = os.environ["A"]\n', encoding='utf-8')
        report = _scan_surface(tmp_path)
        assert report['unparsed_files'] == ['old.py']
        assert any('old.py' in limit for limit in report['_meta']['known_limits'])

    def test_uncalled_sees_module_level_calls_in_a_314_file(self, tmp_path):
        (tmp_path / 'm.py').write_text(
            "import threading\n\n"
            "def worker():\n    return 1\n\n"
            "def main():\n"
            "    t = threading.Thread(target=worker)\n"
            "    try:\n        t.start()\n"
            "    except ValueError, TypeError:\n        pass\n\n"
            "if __name__ == '__main__':\n    main()\n", encoding='utf-8')
        assert find_uncalled(str(tmp_path))['entries'] == []

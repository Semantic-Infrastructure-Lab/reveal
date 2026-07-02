"""Tests for the data-driven tree-sitter import extractors.

Covers C, C++, Java, C#, PHP, and Ruby — languages handled by
``reveal/analyzers/imports/generic.py`` via per-language ``_ImportSpec`` tables
rather than bespoke parsers. See BACK-398: before this, ``imports://`` returned
a silent ``Total Files: 0`` for these languages despite docs claiming support.
"""

from pathlib import Path
from tempfile import NamedTemporaryFile

from reveal.analyzers.imports import get_extractor
from reveal.analyzers.imports.base import get_all_extensions, get_supported_languages


def _extract(code: str, suffix: str):
    with NamedTemporaryFile(mode='w', suffix=suffix, delete=False) as f:
        f.write(code)
        f.flush()
        path = Path(f.name)
    try:
        extractor = get_extractor(path)
        assert extractor is not None, f"no extractor registered for {suffix}"
        return extractor.extract_imports(path), path
    finally:
        path.unlink()


class TestRegistration:
    def test_new_languages_registered(self):
        langs = get_supported_languages()
        for lang in ('C', 'C++', 'Java', 'C#', 'PHP', 'Ruby'):
            assert lang in langs

    def test_new_extensions_registered(self):
        exts = get_all_extensions()
        for ext in ('.c', '.h', '.cpp', '.java', '.cs', '.php', '.rb'):
            assert ext in exts


class TestC:
    def test_local_and_system_includes(self):
        code = '#include <stdio.h>\n#include "server.h"\n'
        imports, _ = _extract(code, '.c')
        by_mod = {i.module_name: i for i in imports}
        assert set(by_mod) == {'stdio.h', 'server.h'}
        # Angle-bracket = system (not relative); quoted = local (relative).
        assert by_mod['stdio.h'].is_relative is False
        assert by_mod['server.h'].is_relative is True
        assert all(i.import_type == 'include' for i in imports)
        # #include is never flagged as an unused import.
        assert all(i.skip_unused for i in imports)

    def test_line_numbers(self):
        code = '\n\n#include "a.h"\n'
        imports, _ = _extract(code, '.c')
        assert len(imports) == 1
        assert imports[0].line_number == 3


class TestCpp:
    def test_includes(self):
        code = '#include <vector>\n#include "engine.hpp"\n'
        imports, _ = _extract(code, '.cpp')
        mods = {i.module_name for i in imports}
        assert mods == {'vector', 'engine.hpp'}


class TestJava:
    def test_import_and_static_import(self):
        code = (
            'package com.example;\n'
            'import java.util.List;\n'
            'import static java.lang.Math.PI;\n'
            'import java.util.*;\n'
        )
        imports, _ = _extract(code, '.java')
        mods = {i.module_name for i in imports}
        # package declaration is NOT an import; static keyword is stripped.
        assert mods == {'java.util.List', 'java.lang.Math.PI', 'java.util.*'}

    def test_aliased_via_as_not_applicable(self):
        # Java has no import alias; ensure a plain import is unaliased.
        imports, _ = _extract('import java.util.Map;\n', '.java')
        assert imports[0].alias is None


class TestCSharp:
    def test_using_directives(self):
        code = (
            'using System;\n'
            'using System.Collections.Generic;\n'
            'global using System.Linq;\n'
            'using static System.Math;\n'
            'namespace Foo { class Bar {} }\n'
        )
        imports, _ = _extract(code, '.cs')
        mods = {i.module_name for i in imports}
        # namespace declaration excluded; global/static keywords stripped.
        assert mods == {'System', 'System.Collections.Generic', 'System.Linq', 'System.Math'}

    def test_using_alias_preserves_generics(self):
        code = 'using MyList = System.Collections.Generic.List<int>;\n'
        imports, _ = _extract(code, '.cs')
        assert len(imports) == 1
        assert imports[0].alias == 'MyList'
        assert imports[0].module_name == 'System.Collections.Generic.List<int>'


class TestPhp:
    def test_use_require_include(self):
        code = (
            '<?php\n'
            'namespace App;\n'
            "require 'foo.php';\n"
            "require_once 'bar.php';\n"
            "include 'baz.php';\n"
            'use App\\Models\\User;\n'
            'use function App\\Helpers\\format;\n'
            'use App\\Models\\Post as P;\n'
        )
        imports, _ = _extract(code, '.php')
        by_mod = {i.module_name: i for i in imports}
        # bare 'App' would only come from the `namespace App;` declaration, which
        # is not an import and must be excluded.
        assert 'App' not in by_mod
        assert 'foo.php' in by_mod
        assert 'App\\Models\\User' in by_mod
        assert 'App\\Helpers\\format' in by_mod  # 'function' keyword stripped
        assert by_mod['App\\Models\\Post'].alias == 'P'  # 'as' alias

    def test_namespace_declaration_not_imported(self):
        imports, _ = _extract('<?php\nnamespace App\\Sub;\n', '.php')
        assert imports == []


class TestRuby:
    def test_require_forms(self):
        code = (
            "require 'json'\n"
            "require('yaml')\n"
            "require_relative './helper'\n"
            "load 'config.rb'\n"
            'include Enumerable\n'   # mixin, NOT an import
            'extend Forwardable\n'   # mixin, NOT an import
        )
        imports, _ = _extract(code, '.rb')
        by_mod = {i.module_name: i for i in imports}
        assert set(by_mod) == {'json', 'yaml', './helper', 'config.rb'}
        assert by_mod['./helper'].is_relative is True
        assert by_mod['json'].is_relative is False


class TestResolution:
    def test_c_include_resolves_sibling_header(self, tmp_path):
        (tmp_path / 'server.h').write_text('int x;\n')
        (tmp_path / 'server.c').write_text('#include "server.h"\nint main(){return 0;}\n')
        extractor = get_extractor(tmp_path / 'server.c')
        imports = extractor.extract_imports(tmp_path / 'server.c')
        assert len(imports) == 1
        resolved = extractor.resolve_import(imports[0], base_path=tmp_path)
        assert resolved == (tmp_path / 'server.h').resolve()

    def test_c_system_include_not_resolved(self, tmp_path):
        (tmp_path / 'a.c').write_text('#include <stdio.h>\n')
        extractor = get_extractor(tmp_path / 'a.c')
        imports = extractor.extract_imports(tmp_path / 'a.c')
        assert extractor.resolve_import(imports[0], base_path=tmp_path) is None

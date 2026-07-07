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

    def test_trailing_comment_not_folded_into_module_name(self):
        """BACK-417: a trailing comment after the include target must not leak
        into the module name — .strip('<>') can't truncate the interior."""
        code = (
            '#include <math.h> /* isnan(), isinf() */\n'
            '#include "local.h"  // a note\n'
            '#include <stdio.h>\n'
        )
        imports, _ = _extract(code, '.c')
        by_mod = {i.module_name for i in imports}
        assert by_mod == {'math.h', 'local.h', 'stdio.h'}


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

    def test_c_qualified_include_full_suffix_match_not_basename(self, tmp_path):
        """BACK-404: a qualified #include (e.g. "jemalloc/internal/util.h")
        must resolve to the file whose full trailing path matches — not
        collide with an unrelated top-level file sharing the same basename.
        """
        (tmp_path / 'src').mkdir()
        (tmp_path / 'src' / 'util.h').write_text('void redis_util(void);\n')

        vendor_dir = tmp_path / 'deps' / 'jemalloc' / 'include' / 'jemalloc' / 'internal'
        vendor_dir.mkdir(parents=True)
        (vendor_dir / 'util.h').write_text('void jemalloc_util(void);\n')
        including_file = vendor_dir / 'assert.h'
        including_file.write_text('#include "jemalloc/internal/util.h"\n')

        extractor = get_extractor(including_file)
        imports = extractor.extract_imports(including_file)
        assert len(imports) == 1
        resolved = extractor.resolve_import(
            imports[0], base_path=including_file.parent, search_paths=[tmp_path]
        )
        assert resolved == (vendor_dir / 'util.h').resolve()
        assert resolved != (tmp_path / 'src' / 'util.h').resolve()

    def test_c_bare_basename_include_still_resolves(self, tmp_path):
        """Unqualified #include "util.h" (no subdirectory) keeps the bounded
        one-level basename fallback (unchanged from BACK-398/pre-BACK-404).
        """
        (tmp_path / 'lib').mkdir()
        (tmp_path / 'lib' / 'util.h').write_text('void f(void);\n')
        (tmp_path / 'a.c').write_text('#include "util.h"\n')

        extractor = get_extractor(tmp_path / 'a.c')
        imports = extractor.extract_imports(tmp_path / 'a.c')
        resolved = extractor.resolve_import(
            imports[0], base_path=tmp_path, search_paths=[tmp_path]
        )
        assert resolved == (tmp_path / 'lib' / 'util.h').resolve()


class TestModuleResolution:
    """BACK-487/488: file-level edge resolution for the non-#include languages.

    Every case must resolve *only* to a file that exists in the tree and skip
    (return None) when the import names a package/namespace/gem with no single
    backing file — the same honest-skip contract C/C++ angle-bracket includes
    have. Resolution goes through the full ``resolve_import`` entry point with an
    explicit ``search_paths`` (the project root), mirroring ``_build_graph``.
    """

    @staticmethod
    def _resolve(root: Path, entry_rel: str, base_rel: str):
        entry = root / entry_rel
        extractor = get_extractor(entry)
        out = {}
        for stmt in extractor.extract_imports(entry):
            resolved = extractor.resolve_import(
                stmt, base_path=root / base_rel, search_paths=[root])
            out[stmt.module_name] = resolved
        return out

    def test_java_import_resolves_via_package_dir(self, tmp_path):
        """Java `import com.pkg.Type` → com/pkg/Type.java (package==dir)."""
        (tmp_path / 'src/com/app/util').mkdir(parents=True)
        (tmp_path / 'src/com/app/util/Helper.java').write_text(
            'package com.app.util;\npublic class Helper {}\n')
        (tmp_path / 'src/com/app/Main.java').write_text(
            'package com.app;\n'
            'import com.app.util.Helper;\n'
            'import java.util.List;\n')  # JDK class, no in-tree file
        res = self._resolve(tmp_path, 'src/com/app/Main.java', 'src/com/app')
        assert res['com.app.util.Helper'] == (tmp_path / 'src/com/app/util/Helper.java').resolve()
        assert res['java.util.List'] is None  # skipped, not fabricated

    def test_java_wildcard_and_static_skip(self, tmp_path):
        (tmp_path / 'p').mkdir()
        (tmp_path / 'p/A.java').write_text('package p;\nimport p.other.*;\nimport static p.M.X;\n')
        res = self._resolve(tmp_path, 'p/A.java', 'p')
        assert res['p.other.*'] is None      # wildcard package import
        assert res['p.M.X'] is None          # static member, no p/M/X.java

    def test_php_use_resolves_through_psr4_prefix(self, tmp_path):
        """PHP `use App\\Models\\User` resolves to src/Models/User.php even though
        the `App\\` vendor prefix maps to `src/` (longest unique suffix)."""
        (tmp_path / 'src/Models').mkdir(parents=True)
        (tmp_path / 'src/Models/User.php').write_text('<?php\nnamespace App\\Models;\nclass User {}\n')
        (tmp_path / 'src/Ctrl').mkdir(parents=True)
        (tmp_path / 'src/Ctrl/Home.php').write_text(
            '<?php\nnamespace App\\Ctrl;\nuse App\\Models\\User;\n')
        res = self._resolve(tmp_path, 'src/Ctrl/Home.php', 'src/Ctrl')
        assert res['App\\Models\\User'] == (tmp_path / 'src/Models/User.php').resolve()

    def test_php_require_literal_resolves_relative(self, tmp_path):
        (tmp_path / 'inc.php').write_text('<?php\n$x = 1;\n')
        (tmp_path / 'main.php').write_text("<?php\nrequire 'inc.php';\n")
        res = self._resolve(tmp_path, 'main.php', '.')
        assert res['inc.php'] == (tmp_path / 'inc.php').resolve()

    def test_php_use_ambiguous_basename_skips(self, tmp_path):
        """Two User.php under different namespaces with no distinguishing parent
        in the `use` path → ambiguous → skip (never guess an edge)."""
        (tmp_path / 'a/Models').mkdir(parents=True)
        (tmp_path / 'b/Models').mkdir(parents=True)
        (tmp_path / 'a/Models/User.php').write_text('<?php\nclass User {}\n')
        (tmp_path / 'b/Models/User.php').write_text('<?php\nclass User {}\n')
        (tmp_path / 'main.php').write_text('<?php\nuse Vendor\\User;\n')  # no "Models" parent
        res = self._resolve(tmp_path, 'main.php', '.')
        assert res['Vendor\\User'] is None

    def test_ruby_require_relative_resolves(self, tmp_path):
        (tmp_path / 'lib').mkdir()
        (tmp_path / 'lib/helper.rb').write_text('module Helper\nend\n')
        (tmp_path / 'lib/main.rb').write_text(
            "require_relative 'helper'\nrequire 'json'\n")
        res = self._resolve(tmp_path, 'lib/main.rb', 'lib')
        assert res['helper'] == (tmp_path / 'lib/helper.rb').resolve()
        assert res['json'] is None  # gem, not an in-tree file

    def test_kotlin_import_resolves_when_file_named_for_class(self, tmp_path):
        (tmp_path / 'app/com/foo').mkdir(parents=True)
        (tmp_path / 'app/com/foo/Bar.kt').write_text('package com.foo\nclass Bar\n')
        (tmp_path / 'app/com/foo/Main.kt').write_text(
            'package com.foo\nimport com.foo.Bar\nimport com.baz.*\n')
        res = self._resolve(tmp_path, 'app/com/foo/Main.kt', 'app/com/foo')
        assert res['com.foo.Bar'] == (tmp_path / 'app/com/foo/Bar.kt').resolve()
        assert res['com.baz.*'] is None

    def test_swift_single_token_module_resolves_to_lone_file(self, tmp_path):
        (tmp_path / 'Sources').mkdir()
        (tmp_path / 'Sources/Helper.swift').write_text('struct Helper {}\n')
        (tmp_path / 'Sources/Main.swift').write_text(
            'import Helper\nimport Foundation\n')
        res = self._resolve(tmp_path, 'Sources/Main.swift', 'Sources')
        assert res['Helper'] == (tmp_path / 'Sources/Helper.swift').resolve()
        assert res['Foundation'] is None  # system framework, no in-tree file

    def test_bare_basename_ambiguous_skips(self, tmp_path):
        """Swift `import Helper` with two Helper.swift in the tree → ambiguous,
        no parent to disambiguate a single-token module → skip."""
        (tmp_path / 'x').mkdir()
        (tmp_path / 'y').mkdir()
        (tmp_path / 'x/Helper.swift').write_text('struct Helper {}\n')
        (tmp_path / 'y/Helper.swift').write_text('struct Helper {}\n')
        (tmp_path / 'Main.swift').write_text('import Helper\n')
        res = self._resolve(tmp_path, 'Main.swift', '.')
        assert res['Helper'] is None

    def test_resolution_matches_with_and_without_file_index(self, tmp_path):
        """The file_index fast path (BACK-491) must resolve byte-identically to
        the os.walk fallback used by callers that pass no index."""
        (tmp_path / 'src/com/app').mkdir(parents=True)
        (tmp_path / 'src/com/app/Helper.java').write_text('package com.app;\nclass Helper {}\n')
        (tmp_path / 'src/com/app/Main.java').write_text(
            'package com.app;\nimport com.app.Helper;\n')
        extractor = get_extractor(tmp_path / 'src/com/app/Main.java')
        stmt = extractor.extract_imports(tmp_path / 'src/com/app/Main.java')[0]
        expected = (tmp_path / 'src/com/app/Helper.java').resolve()
        # No index → os.walk fallback.
        assert extractor.resolve_import(
            stmt, base_path=tmp_path / 'src/com/app', search_paths=[tmp_path]) == expected
        # With a prebuilt basename index (as _build_graph supplies).
        index = {}
        for p in tmp_path.rglob('*'):
            if p.is_file():
                index.setdefault(p.name, []).append(p)
        assert extractor.resolve_import(
            stmt, base_path=tmp_path / 'src/com/app', search_paths=[tmp_path],
            file_index=index) == expected

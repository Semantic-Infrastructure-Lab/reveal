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

    def test_back514_languages_registered(self):
        langs = get_supported_languages()
        for lang in ('Scala', 'Dart', 'GDScript', 'Lua', 'Zig'):
            assert lang in langs
        exts = get_all_extensions()
        for ext in ('.scala', '.dart', '.gd', '.lua', '.zig'):
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

    def test_include_nested_in_struct_body(self):
        """BACK-676: a #include inside a struct body isn't valid
        top-level-context grammar, so tree-sitter's C grammar degrades it
        from 'preproc_include' to the generic 'preproc_call' fallback node
        -- the same shape used for #pragma/#undef inside a body. Only the
        include must be picked up, and the #pragma sibling must not leak in
        as a bogus import."""
        code = (
            'struct Foo {\n'
            '#pragma pack(push, 1)\n'
            '#include "members.inc"\n'
            '};\n'
        )
        imports, _ = _extract(code, '.c')
        mods = {i.module_name for i in imports}
        assert mods == {'members.inc'}


class TestCpp:
    def test_includes(self):
        code = '#include <vector>\n#include "engine.hpp"\n'
        imports, _ = _extract(code, '.cpp')
        mods = {i.module_name for i in imports}
        assert mods == {'vector', 'engine.hpp'}

    def test_include_nested_in_class_body(self):
        """BACK-676: Godot's bvh_tree.h fragment-include idiom -- #include
        directives sitting inside a class body (not just at file scope)
        degrade to a 'preproc_call' fallback node in tree-sitter's C++
        grammar and were previously invisible to the import extractor."""
        code = (
            'class BVH_Tree {\n'
            'public:\n'
            '#include "bvh_pair.inc"\n'
            '#include "bvh_structs.inc"\n'
            '};\n'
        )
        imports, _ = _extract(code, '.cpp')
        mods = {i.module_name for i in imports}
        assert mods == {'bvh_pair.inc', 'bvh_structs.inc'}


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

    def test_extract_namespaces_block_scoped(self, tmp_path):
        """BACK-544: block-scoped `namespace X.Y { }` is indexed."""
        f = tmp_path / 'A.cs'
        f.write_text('namespace Foo.Bar {\n    class A {}\n}\n')
        extractor = get_extractor(f)
        assert extractor.extract_namespaces(f) == ['Foo.Bar']

    def test_extract_namespaces_file_scoped(self, tmp_path):
        """BACK-544: file-scoped `namespace X.Y;` (C# 10) is indexed too."""
        f = tmp_path / 'A.cs'
        f.write_text('namespace Foo.Baz;\n\nclass B {}\n')
        extractor = get_extractor(f)
        assert extractor.extract_namespaces(f) == ['Foo.Baz']

    def test_extract_namespaces_multiple_blocks(self, tmp_path):
        """A single file may declare more than one namespace block."""
        f = tmp_path / 'A.cs'
        f.write_text('namespace Foo { class A {} }\nnamespace Bar { class B {} }\n')
        extractor = get_extractor(f)
        assert set(extractor.extract_namespaces(f)) == {'Foo', 'Bar'}

    def test_extract_namespaces_swift_is_noop(self, tmp_path):
        """Swift has no package/namespace declaration node to scan (modules
        are a build-system concept, not a source construct) — gated by
        spec.package_node_types being empty, unlike Java/Kotlin/PHP/C#
        (BACK-547 scale-out) which now have real inventories."""
        f = tmp_path / 'a.swift'
        f.write_text('import Foundation\nclass A {}\n')
        extractor = get_extractor(f)
        assert extractor.extract_namespaces(f) == []

    def test_extract_namespaces_java_package_declaration(self, tmp_path):
        """BACK-547: Java now has its own package inventory via `package` decl."""
        f = tmp_path / 'a.java'
        f.write_text('package foo.bar;\nclass A {}\n')
        extractor = get_extractor(f)
        assert extractor.extract_namespaces(f) == ['foo.bar']


class TestSwiftModuleConvention:
    """BACK-567: Swift `import Foo` names a whole SwiftPM target. These cover the
    directory-convention primitives (no toolchain) the depends:// fan-out is
    built on: module_for_file, name sanitization, and honest-decline."""

    def _ext(self, tmp_path):
        f = tmp_path / 'x.swift'
        f.write_text('import Foundation\n')
        return get_extractor(f)

    @staticmethod
    def _stmt(module_name, file_path='/r/x.swift'):
        from reveal.analyzers.imports.types import ImportStatement
        return ImportStatement(
            file_path=Path(file_path), line_number=1, module_name=module_name,
            imported_names=[], is_relative=False, import_type='import')

    def test_module_for_file_from_sources_layout(self, tmp_path):
        ext = self._ext(tmp_path)
        p = Path('/repo/Sources/KsApi/Models/Project.swift')
        assert ext.module_for_file(p) == 'KsApi'

    def test_module_for_file_from_tests_layout(self, tmp_path):
        ext = self._ext(tmp_path)
        p = Path('/repo/Tests/LibraryTests/ClientTests.swift')
        assert ext.module_for_file(p) == 'LibraryTests'

    def test_module_for_file_nested_module_name_repeats(self, tmp_path):
        """The first component after Sources/ is the target even when a
        same-named subdirectory repeats deeper (real Library layout)."""
        ext = self._ext(tmp_path)
        p = Path('/repo/Sources/Library/Library/Tracking/Segment.swift')
        assert ext.module_for_file(p) == 'Library'

    def test_module_for_file_loose_file_in_sources_is_none(self, tmp_path):
        """A file sitting directly in Sources/ names no module (nothing follows
        the target component) — not guessed into one."""
        ext = self._ext(tmp_path)
        assert ext.module_for_file(Path('/repo/Sources/loose.swift')) is None

    def test_module_for_file_no_convention_dir_is_none(self, tmp_path):
        ext = self._ext(tmp_path)
        assert ext.module_for_file(Path('/repo/misc/a.swift')) is None

    def test_hyphen_sanitized_to_underscore(self, tmp_path):
        ext = self._ext(tmp_path)
        p = Path('/repo/Sources/Kickstarter-Framework/App.swift')
        assert ext.module_for_file(p) == 'Kickstarter_Framework'

    def test_resolve_module_targets_fans_out(self, tmp_path):
        ext = self._ext(tmp_path)
        a, b = Path('/r/Sources/KsApi/A.swift'), Path('/r/Sources/KsApi/B.swift')
        index = {'KsApi': [a, b]}
        assert set(ext.resolve_module_targets(self._stmt('KsApi'), index)) == {a, b}

    def test_resolve_module_targets_unknown_module_empty(self, tmp_path):
        ext = self._ext(tmp_path)
        assert ext.resolve_module_targets(
            self._stmt('Foundation'), {'KsApi': [Path('/r/a.swift')]}) == []

    def test_resolve_module_targets_sanitizes_import_name(self, tmp_path):
        """`import Kickstarter_Framework` resolves against the sanitized dir key
        `Kickstarter_Framework` (dir was `Kickstarter-Framework`)."""
        ext = self._ext(tmp_path)
        a = Path('/r/Sources/Kickstarter-Framework/App.swift')
        assert ext.resolve_module_targets(
            self._stmt('Kickstarter_Framework'), {'Kickstarter_Framework': [a]}) == [a]

    def test_is_intra_project_true_for_known_module(self, tmp_path):
        ext = self._ext(tmp_path)
        assert ext.is_intra_project_import(
            self._stmt('KsApi'), Path('/r'),
            project_namespaces={'KsApi', 'Library'}) is True

    def test_is_intra_project_false_for_external_module(self, tmp_path):
        ext = self._ext(tmp_path)
        assert ext.is_intra_project_import(
            self._stmt('Foundation'), Path('/r'),
            project_namespaces={'KsApi', 'Library'}) is False

    def test_is_intra_project_none_without_inventory(self, tmp_path):
        """No module inventory supplied (project_namespaces=None) → conservative
        None, never a guess."""
        ext = self._ext(tmp_path)
        assert ext.is_intra_project_import(self._stmt('KsApi'), Path('/r')) is None

    def _manifest(self, tmp_path, body):
        p = tmp_path / 'Package.swift'
        p.write_text(body)
        return get_extractor(p), p

    def test_extract_manifest_targets_name_and_path(self, tmp_path):
        ext, p = self._manifest(tmp_path, '''
            // swift-tools-version:5.9
            import PackageDescription
            let package = Package(
              name: "Api",
              targets: [
                .target(name: "Api", dependencies: [], path: "./Sources"),
                .testTarget(name: "ApiTests"),
                .target(name: "Plain"),
              ]
            )
        ''')
        got = set(ext.extract_manifest_targets(p))
        assert got == {('Api', './Sources', False),
                       ('ApiTests', None, True),
                       ('Plain', None, False)}

    def test_extract_manifest_targets_excludes_dependency_reference(self, tmp_path):
        """A `.target(name:)` inside a dependencies: array is a reference, not a
        declaration — only elements of the Package(targets:) array count."""
        ext, p = self._manifest(tmp_path, '''
            let package = Package(
              name: "P",
              targets: [
                .target(name: "A", dependencies: [.target(name: "B"), .product(name: "X", package: "y")]),
              ]
            )
        ''')
        names = [n for n, _, _ in ext.extract_manifest_targets(p)]
        assert names == ['A']  # B is a dependency reference, not declared

    def test_extract_manifest_targets_sanitizes_name(self, tmp_path):
        ext, p = self._manifest(tmp_path, '''
            let package = Package(
              name: "P",
              targets: [.target(name: "Kickstarter-Framework")]
            )
        ''')
        assert ext.extract_manifest_targets(p) == [('Kickstarter_Framework', None, False)]

    def test_extract_manifest_targets_empty_without_package_call(self, tmp_path):
        """A .swift file that isn't a manifest (no Package(...) call) yields
        nothing — the extractor doesn't scan arbitrary .target-looking calls."""
        ext = self._ext(tmp_path)
        f = tmp_path / 'x.swift'  # created by _ext with `import Foundation`
        assert ext.extract_manifest_targets(f) == []

    def test_extract_manifest_targets_falls_back_when_targets_array_is_computed(self, tmp_path):
        """BACK-669 (swift-collections second corpus): `Package(targets:)` fed
        a computed variable (`.map { $0.toTarget() }`, not a literal array) —
        the direct-array walk finds nothing, so this falls back to a
        position-independent scan for any `.target`/`.testTarget` call with
        both a literal `name:` and a literal `path:`."""
        ext, p = self._manifest(tmp_path, '''
            let _targets: [Target] = [
              .target(name: "Core", path: "Sources/Core"),
            ].map { $0 }
            let package = Package(name: "P", targets: _targets)
        ''')
        assert ext.extract_manifest_targets(p) == [('Core', 'Sources/Core', False)]

    def test_extract_manifest_targets_fallback_requires_literal_path(self, tmp_path):
        """The fallback only trusts a literal native `path:` — a custom
        builder's differently-named relocation argument (e.g. `directory:`)
        is NOT treated as equivalent (it's commonly just a directory
        *segment*, not a ready-to-use relative path — see
        `extract_manifest_target_names` for how this same case is instead
        surfaced as an honest reduced-confidence signal)."""
        ext, p = self._manifest(tmp_path, '''
            let _targets: [Target] = [
              .target(name: "_RopeModule", directory: "RopeModule"),
            ].map { $0.toTarget() }
            let package = Package(name: "P", targets: _targets)
        ''')
        assert ext.extract_manifest_targets(p) == []

    def test_extract_manifest_target_names_direct_array(self, tmp_path):
        """The broader NAME-only scan agrees with the strict scan when the
        targets array IS a literal (no fallback needed)."""
        ext, p = self._manifest(tmp_path, '''
            let package = Package(
              name: "P",
              targets: [.target(name: "Api"), .testTarget(name: "ApiTests")]
            )
        ''')
        assert ext.extract_manifest_target_names(p) == {'Api', 'ApiTests'}

    def test_extract_manifest_target_names_finds_computed_array_targets(self, tmp_path):
        """BACK-669: unlike `extract_manifest_targets`, the NAME-only scan
        finds a target declared through a computed `targets:` array —
        `_RopeModule`'s real failure mode: neither `extract_manifest_targets`
        (no literal path/directory relation it can trust) nor the directory
        convention (its on-disk dir is named `RopeModule`, not
        `_RopeModule`) can resolve it, but this at least proves the name is
        real and in-tree so the honest-decline guard can fire instead of
        staying silent."""
        ext, p = self._manifest(tmp_path, '''
            let _targets: [Target] = [
              .target(name: "_RopeModule", directory: "RopeModule"),
            ].map { $0.toTarget() }
            let package = Package(name: "P", targets: _targets)
        ''')
        assert ext.extract_manifest_target_names(p) == {'_RopeModule'}

    def test_is_intra_project_true_when_only_manifest_target_name_known(self, tmp_path):
        """BACK-669: `is_intra_project_import`'s Swift branch checks against
        whatever `project_namespaces` the caller built — which, since
        `depends.py`'s BACK-669 fix, is unioned with
        `extract_manifest_target_names`'s broader set, not just the
        directory-convention module_index keys. A module known only through
        that broader set must still classify as intra-project (reduced-
        confidence honest-decline) rather than falling through to "unknown
        external framework"."""
        ext = self._ext(tmp_path)
        assert ext.is_intra_project_import(
            self._stmt('_RopeModule'), Path('/r'),
            project_namespaces={'RopeModule', '_RopeModule'}) is True


class TestSwiftAttributedImport:
    """BACK-669 (swift-collections second corpus): a declaration-level
    attribute (`@testable`, `@_spi(...)`) directly before `import` — common
    in real Swift test files, e.g. `@_spi(Testing) @testable import Foo`.
    Pre-fix, `_build()`'s keyword-stripping tokenizer only popped tokens
    exactly matching `spec.keywords`; `@testable`/`@_spi(...)` never
    matched (an attribute's argument varies, so it can't be a fixed
    keyword), so the whole raw statement text became `module_name` —
    silently unresolvable, and (before the honest-decline fix above) not
    even flagged."""

    def test_testable_import_strips_attribute(self):
        imports, _ = _extract('@testable import Foo\n', '.swift')
        assert [i.module_name for i in imports] == ['Foo']

    def test_stacked_attributes_before_import_strip_all(self):
        """`@_spi(Testing) @testable import Foo` — two stacked attributes,
        one of them parenthesized with an argument."""
        imports, _ = _extract('@_spi(Testing) @testable import Foo\n', '.swift')
        assert [i.module_name for i in imports] == ['Foo']

    def test_plain_import_unaffected(self):
        imports, _ = _extract('import Foo\n', '.swift')
        assert [i.module_name for i in imports] == ['Foo']


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


class TestScala:
    def test_import_forms(self):
        code = (
            'import scala.collection.mutable.Map\n'
            'import scala.util.{Try, Success}\n'
            'import scala.util._\n'
        )
        imports, _ = _extract(code, '.scala')
        mods = {i.module_name for i in imports}
        assert mods == {
            'scala.collection.mutable.Map',
            'scala.util.{Try, Success}',
            'scala.util._',
        }


class TestDart:
    def test_import_forms_exclude_export(self):
        code = (
            'import "package:flutter/material.dart";\n'
            "import './helper.dart';\n"
            "export './other.dart';\n"  # not an import — out of scope for v1
        )
        imports, _ = _extract(code, '.dart')
        by_mod = {i.module_name: i for i in imports}
        assert set(by_mod) == {'package:flutter/material.dart', './helper.dart'}
        assert by_mod['./helper.dart'].is_relative is True


class TestGDScript:
    def test_extends_preload_load(self):
        code = (
            'extends "res://base.gd"\n'
            'const Helper = preload("res://helper.gd")\n'
            'var x = load("res://other.gd")\n'
        )
        imports, _ = _extract(code, '.gd')
        mods = {i.module_name for i in imports}
        assert mods == {'res://base.gd', 'res://helper.gd', 'res://other.gd'}

    def test_non_resource_load_not_an_import(self):
        """A `load` call whose callee isn't the preload/load builtin (e.g. a
        variable named `load`) must not be picked up."""
        code = 'var load = 5\nvar y = load\n'
        imports, _ = _extract(code, '.gd')
        assert imports == []


class TestLua:
    def test_require_forms(self):
        code = (
            'local a = require("a.b")\n'
            "local b = require 'a.c'\n"
        )
        imports, _ = _extract(code, '.lua')
        mods = {i.module_name for i in imports}
        assert mods == {'a.b', 'a.c'}

    def test_require_shadowed_as_variable_not_an_import(self):
        """`local require = 5` is a variable, not a call — must not be
        mistaken for an import (no `function_call` node is produced)."""
        code = 'local require = 5\n'
        imports, _ = _extract(code, '.lua')
        assert imports == []


class TestZig:
    def test_import_forms(self):
        code = (
            'const std = @import("std");\n'
            'const foo = @import("foo.zig");\n'
        )
        imports, _ = _extract(code, '.zig')
        mods = {i.module_name for i in imports}
        assert mods == {'std', 'foo.zig'}
        by_mod = {i.module_name: i for i in imports}
        assert all(i.skip_unused for i in imports)
        assert by_mod['std'].line_number == 1
        assert by_mod['foo.zig'].line_number == 2


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
        assert res['p.M.X'] is None          # static member, no p/M.java either

    def test_java_nested_type_import_resolves_to_enclosing_class(self, tmp_path):
        """BACK-551: `import a.b.Outer.Inner` names a nested type — must resolve
        to Outer.java (the file), not silently drop because there's no
        Inner.java. Java measurement loop found this class of miss."""
        (tmp_path / 'src/a/b').mkdir(parents=True)
        (tmp_path / 'src/a/b/Outer.java').write_text(
            'package a.b;\npublic class Outer { public static class Inner {} }\n')
        (tmp_path / 'src/a/b/User.java').write_text(
            'package a.b;\nimport a.b.Outer.Inner;\npublic class User {}\n')
        res = self._resolve(tmp_path, 'src/a/b/User.java', 'src/a/b')
        assert res['a.b.Outer.Inner'] == (tmp_path / 'src/a/b/Outer.java').resolve()

    def test_java_static_member_import_resolves_to_class(self, tmp_path):
        """BACK-551: `import static a.b.Outer.CONST` must resolve to Outer.java."""
        (tmp_path / 'src/a/b').mkdir(parents=True)
        (tmp_path / 'src/a/b/Outer.java').write_text(
            'package a.b;\npublic class Outer { public static final int CONST = 1; }\n')
        (tmp_path / 'src/a/b/User.java').write_text(
            'package a.b;\nimport static a.b.Outer.CONST;\npublic class User {}\n')
        res = self._resolve(tmp_path, 'src/a/b/User.java', 'src/a/b')
        assert res['a.b.Outer.CONST'] == (tmp_path / 'src/a/b/Outer.java').resolve()

    def test_java_nested_fallback_does_not_peel_into_package(self, tmp_path):
        """BACK-551 FP-safety: an unresolved `import a.b.Missing` (no Missing.java
        in-tree, `b` is a lowercase package component) must stay None — the
        member-peel must NOT strip down to the package and match a stray file
        named after a package component (never fabricate an edge)."""
        (tmp_path / 'src/a/b').mkdir(parents=True)
        # A decoy file whose stem equals a package component; the peel must not
        # reach it.
        (tmp_path / 'src/a/b.java').write_text('package a;\nclass b {}\n')
        (tmp_path / 'src/a/b/User.java').write_text(
            'package a.b;\nimport a.b.Missing;\npublic class User {}\n')
        res = self._resolve(tmp_path, 'src/a/b/User.java', 'src/a/b')
        assert res['a.b.Missing'] is None

    def test_kotlin_member_import_resolves_to_enclosing_class(self, tmp_path):
        """BACK-551: Kotlin `import a.b.Outer.member` peels to Outer.kt."""
        (tmp_path / 'src/a/b').mkdir(parents=True)
        (tmp_path / 'src/a/b/Outer.kt').write_text(
            'package a.b\nclass Outer { companion object { const val C = 1 } }\n')
        (tmp_path / 'src/a/b/User.kt').write_text(
            'package a.b\nimport a.b.Outer.C\nclass User\n')
        res = self._resolve(tmp_path, 'src/a/b/User.kt', 'src/a/b')
        assert res['a.b.Outer.C'] == (tmp_path / 'src/a/b/Outer.kt').resolve()

    def test_php_nested_fallback_disabled(self, tmp_path):
        """BACK-551: PHP does NOT get the member-peel (its `\\` namespace
        components are StudlyCaps, so the Uppercase gate can't tell package from
        type) — `use App\\Models\\User\\Missing` with no Missing.php stays None,
        never peeling to a stray Models/User file."""
        (tmp_path / 'src/App/Models').mkdir(parents=True)
        (tmp_path / 'src/App/Models/User.php').write_text('<?php\nnamespace App\\Models;\nclass User {}\n')
        (tmp_path / 'src/App/Web.php').write_text(
            '<?php\nnamespace App\\Web;\nuse App\\Models\\User\\Missing;\nclass Web {}\n')
        res = self._resolve(tmp_path, 'src/App/Web.php', 'src/App')
        assert res['App\\Models\\User\\Missing'] is None

    def test_csharp_namespace_fans_out_to_every_declaring_file(self, tmp_path):
        """BACK-544: `using Foo.Bar` names a namespace, not one type — a
        namespace declared across several files must resolve an edge to
        *every* declaring file (never fabricated, never skipped just because
        it's not unique)."""
        (tmp_path / 'Widgets').mkdir()
        (tmp_path / 'Widgets/Widget.cs').write_text('namespace Foo.Widgets {\n    class Widget {}\n}\n')
        (tmp_path / 'Widgets/Gadget.cs').write_text('namespace Foo.Widgets {\n    class Gadget {}\n}\n')
        (tmp_path / 'Main.cs').write_text('using Foo.Widgets;\n\nclass Program {}\n')

        entry = tmp_path / 'Main.cs'
        extractor = get_extractor(entry)
        namespace_index = {}
        for f in [tmp_path / 'Widgets/Widget.cs', tmp_path / 'Widgets/Gadget.cs', entry]:
            for ns in extractor.extract_namespaces(f):
                namespace_index.setdefault(ns, []).append(f)
        stmt = [s for s in extractor.extract_imports(entry) if s.module_name == 'Foo.Widgets'][0]
        targets = set(extractor.resolve_namespace_targets(stmt, namespace_index))
        assert targets == {
            (tmp_path / 'Widgets/Widget.cs').resolve(),
            (tmp_path / 'Widgets/Gadget.cs').resolve(),
        }

    def test_kotlin_top_level_function_import_resolves_via_member_index(self, tmp_path):
        """BACK-547 Kotlin measurement loop: `import a.b.foo` where `foo` is a
        top-level (free) function has NO enclosing type anywhere in the import
        string — unlike `import a.b.Outer.member` (BACK-551), there is no
        `Outer` component to peel down to, so the direct dotted match (looks
        for `foo.kt`) and the nested_member_fallback peel both fail. Real
        corpus measurement (tivi, samples/kotlin) found this class of miss at
        12% recall before the member-index fallback (99.14% after)."""
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/Utils.kt').write_text(
            'package a.b\nfun foo(x: Int): Int = x + 1\n')
        (tmp_path / 'a/b/User.kt').write_text(
            'package a.b\nimport a.b.foo\nfun useIt() = foo(1)\n')

        entry = tmp_path / 'a/b/User.kt'
        declaring = tmp_path / 'a/b/Utils.kt'
        extractor = get_extractor(entry)
        member_index = {}
        for f in [declaring, entry]:
            declared_ns = extractor.extract_namespaces(f)
            for symbol in extractor.extract_top_level_members(f):
                for ns in declared_ns:
                    member_index.setdefault((ns, symbol), []).append(f)
        stmt = [s for s in extractor.extract_imports(entry) if s.module_name == 'a.b.foo'][0]

        # Direct dotted match must fail (no foo.kt in-tree) — this is the bug
        # BACK-551's peel doesn't cover, confirming the fallback is load-bearing.
        assert extractor.resolve_import(stmt, base_path=tmp_path / 'a/b', search_paths=[tmp_path]) is None

        targets = extractor.resolve_member_targets(stmt, member_index)
        assert targets == [declaring.resolve()]

    def test_kotlin_top_level_extension_property_import_resolves(self, tmp_path):
        """Same idiom, extension property form (`val Receiver.foo: T get() = ...`)
        — the name sits inside a `variable_declaration` child, one level deeper
        than a plain function's `simple_identifier`, which
        `_top_level_member_name` must still find."""
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/Extensions.kt').write_text(
            'package a.b\nval Int.sqlValue: Long get() = this.toLong()\n')
        (tmp_path / 'a/b/User.kt').write_text(
            'package a.b\nimport a.b.sqlValue\nfun useIt() = 1.sqlValue\n')

        entry = tmp_path / 'a/b/User.kt'
        declaring = tmp_path / 'a/b/Extensions.kt'
        extractor = get_extractor(entry)
        member_index = {}
        for f in [declaring, entry]:
            declared_ns = extractor.extract_namespaces(f)
            for symbol in extractor.extract_top_level_members(f):
                for ns in declared_ns:
                    member_index.setdefault((ns, symbol), []).append(f)
        stmt = [s for s in extractor.extract_imports(entry) if s.module_name == 'a.b.sqlValue'][0]
        targets = extractor.resolve_member_targets(stmt, member_index)
        assert targets == [declaring.resolve()]

    def test_kotlin_member_index_does_not_index_class_members(self, tmp_path):
        """A method/property nested inside a class must NOT enter the
        top-level member index — it's reached via the class's own name (the
        existing nested_member_fallback path), and indexing it here would
        risk a spurious extra edge for an unrelated same-named top-level
        import elsewhere in the same package."""
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/Widget.kt').write_text(
            'package a.b\nclass Widget {\n    fun render() {}\n}\n')
        extractor = get_extractor(tmp_path / 'a/b/Widget.kt')
        assert extractor.extract_top_level_members(tmp_path / 'a/b/Widget.kt') == []

    def test_scala_lowercase_object_member_import_resolves_via_container_index(self, tmp_path):
        """BACK-557 Scala measurement loop (real corpus: samples/scala,
        GitBucket): `import a.b.container.member` where `container` is a
        lowerCamelCase top-level `object` (e.g. real code's `object
        helpers`) is NOT reached by BACK-551's nested_member_fallback peel —
        the peel's Uppercase-type gate stops at the first lowercase trailing
        component, which is exactly `container`'s name here (indistinguishable
        by name alone from a package segment). Real corpus measurement found
        this class of miss on GitBucket's `helpers.scala` (2 of 9 real
        importers silently dropped before this fix)."""
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/Utils.scala').write_text(
            'package a.b\n\nobject helpers {\n  def urlLink(x: String): String = x\n}\n')
        (tmp_path / 'a/b/User.scala').write_text(
            'package a.b\nimport a.b.helpers.urlLink\nclass User\n')

        entry = tmp_path / 'a/b/User.scala'
        declaring = tmp_path / 'a/b/Utils.scala'
        extractor = get_extractor(entry)
        member_index = {}
        sep = extractor.spec.module_separator
        for f in [declaring, entry]:
            declared_ns = extractor.extract_namespaces(f)
            for container_name, symbol in extractor.extract_container_members(f):
                for ns in declared_ns:
                    member_index.setdefault((f'{ns}{sep}{container_name}', symbol), []).append(f)
        stmt = [s for s in extractor.extract_imports(entry) if s.module_name == 'a.b.helpers.urlLink'][0]

        # Direct dotted match must fail (no urlLink.scala in-tree) and the
        # nested_member_fallback peel must also fail (its Uppercase gate
        # refuses to peel to lowercase `helpers`) — this is the bug BACK-551
        # doesn't cover, confirming the container-member fallback is load-bearing.
        assert extractor.resolve_import(stmt, base_path=tmp_path / 'a/b', search_paths=[tmp_path]) is None

        targets = extractor.resolve_member_targets(stmt, member_index)
        assert targets == [declaring.resolve()]

    def test_scala_uppercase_object_member_still_resolves_via_peel_not_container_index(self, tmp_path):
        """PascalCase containers (`object Directory`) already resolve via
        BACK-551's peel — the container-member index must not be needed (and
        this loop must not regress that existing path)."""
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/Directory.scala').write_text(
            'package a.b\n\nobject Directory {\n  def getRepositoryDir(x: String): String = x\n}\n')
        (tmp_path / 'a/b/User.scala').write_text(
            'package a.b\nimport a.b.Directory.getRepositoryDir\nclass User\n')
        res = self._resolve(tmp_path, 'a/b/User.scala', 'a/b')
        assert res['a.b.Directory.getRepositoryDir'] == (tmp_path / 'a/b/Directory.scala').resolve()

    def test_scala_container_member_index_does_not_index_nested_class_members(self, tmp_path):
        """A method declared on a class nested *inside* the object must not
        enter the container-member index — it has its own, deeper import
        path this index does not model, and indexing it here would risk a
        spurious extra edge."""
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/Widget.scala').write_text(
            'package a.b\n\nobject widget {\n'
            '  class Inner {\n    def render(): Unit = {}\n  }\n'
            '}\n')
        extractor = get_extractor(tmp_path / 'a/b/Widget.scala')
        pairs = extractor.extract_container_members(tmp_path / 'a/b/Widget.scala')
        assert ('widget', 'render') not in pairs

    def test_kotlin_has_no_container_member_fallback(self, tmp_path):
        """Kotlin's own top-level-member idiom is `member_symbol_fallback`
        (no enclosing object at all) — `container_member_fallback` must stay
        off so `extract_container_members`/its index entries are never
        populated for Kotlin, a guaranteed no-op mirroring the existing
        Java negative control below."""
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/Widget.kt').write_text(
            'package a.b\nobject helpers {\n    fun urlLink(x: String) = x\n}\n')
        extractor = get_extractor(tmp_path / 'a/b/Widget.kt')
        assert extractor.spec.container_member_fallback is False
        assert extractor.extract_container_members(tmp_path / 'a/b/Widget.kt') == []

    def test_java_has_no_member_symbol_fallback(self, tmp_path):
        """Java has no top-level-function idiom — `member_symbol_fallback`
        must stay off so `resolve_member_targets` is always a no-op, never a
        surprise new edge for a language whose members are always class-owned."""
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/User.java').write_text(
            'package a.b;\nimport a.b.foo;\npublic class User {}\n')
        extractor = get_extractor(tmp_path / 'a/b/User.java')
        stmt = extractor.extract_imports(tmp_path / 'a/b/User.java')[0]
        assert extractor.resolve_member_targets(stmt, {('a.b', 'foo'): [tmp_path / 'a/b/Elsewhere.java']}) == []

    def test_csharp_namespace_unknown_skips_not_fabricates(self, tmp_path):
        extractor = get_extractor(tmp_path / 'Main.cs')
        stmt_imports, _ = _extract('using Some.Unknown.Namespace;\n', '.cs')
        assert extractor.resolve_namespace_targets(stmt_imports[0], {}) == []

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

    def test_php_require_call_style_literal_resolves_relative(self, tmp_path):
        """BACK-680 (second-corpus overfit guard, osCommerce): the
        parenthesized call-style spelling of a bare-literal require —
        `require('includes/inc.php');`, no space before the `(` — is the
        dominant real-world form on osCommerce (534/544 statements), vs.
        only 10/1,521 in the original WordPress oracle corpus. Before this
        fix it silently resolved to zero edges: `_build()`'s keyword
        stripper splits on spaces and never matches the fused
        `require('...')` token, so `module_name` ended up as the literal
        garbage string `"require('includes/inc.php')"` (still `_looks_like_
        path`-true thanks to the embedded `/`, so a real resolution was
        attempted and correctly failed against the garbage text — never a
        wrong edge, just silently nothing)."""
        (tmp_path / 'includes').mkdir()
        (tmp_path / 'includes/inc.php').write_text('<?php\n$x = 1;\n')
        (tmp_path / 'main.php').write_text("<?php\nrequire('includes/inc.php');\n")
        res = self._resolve(tmp_path, 'main.php', '.')
        assert res['includes/inc.php'] == (tmp_path / 'includes/inc.php').resolve()

    def test_php_require_call_style_dir_concat_resolves(self, tmp_path):
        """BACK-680: the parenthesized call-style spelling of BACK-564's
        `__DIR__`-concatenation idiom — `require(__DIR__ . '/foo.php');` —
        must resolve too. Before this fix, `_concat_to_import`'s
        `_first_child_of_kind(node, 'binary_expression')` only checked
        *direct* children of the require/include node; a parenthesized
        target nests the `binary_expression` one level deeper (inside a
        `parenthesized_expression`), so this silently missed the concat
        idiom and fell through to the same broken text-tokenizer path as
        the bare-literal case above."""
        (tmp_path / 'foo.php').write_text('<?php\n$x = 1;\n')
        (tmp_path / 'main.php').write_text("<?php\nrequire(__DIR__ . '/foo.php');\n")
        res = self._resolve(tmp_path, 'main.php', '.')
        assert res['foo.php'] == (tmp_path / 'foo.php').resolve()

    def test_php_require_call_style_dynamic_honest_skip(self, tmp_path):
        """BACK-680: a call-style require whose target is neither a bare
        string literal nor a concatenation — `require($tpl->getFile('x'));`
        (osCommerce's dominant dynamic idiom, 198/544 statements) — must
        stay an honest skip (no edge), never a fabricated one, even after
        the parenthesized-target unwrapping this session added."""
        (tmp_path / 'main.php').write_text(
            "<?php\nrequire($tpl->getFile('template_top.php'));\n")
        entry = tmp_path / 'main.php'
        extractor = get_extractor(entry)
        imports = extractor.extract_imports(entry)
        assert imports == []

    def test_php_require_dir_concat_resolves(self, tmp_path):
        """BACK-564: `require __DIR__ . '/foo.php';` — the dominant real-world
        PHP require idiom (0/387 WordPress-core edges use a bare literal) —
        must resolve structurally, not just the bare-literal case above."""
        (tmp_path / 'foo.php').write_text('<?php\n$x = 1;\n')
        (tmp_path / 'main.php').write_text("<?php\nrequire __DIR__ . '/foo.php';\n")
        res = self._resolve(tmp_path, 'main.php', '.')
        assert res['foo.php'] == (tmp_path / 'foo.php').resolve()

    def test_php_require_once_dirname_file_concat_resolves(self, tmp_path):
        """`require_once dirname( __FILE__ ) . '/bar.php';` — pre-`__DIR__`
        (PHP < 5.3) spelling of the same directory-relative idiom."""
        (tmp_path / 'bar.php').write_text('<?php\n$x = 1;\n')
        (tmp_path / 'main.php').write_text(
            "<?php\nrequire_once dirname( __FILE__ ) . '/bar.php';\n")
        res = self._resolve(tmp_path, 'main.php', '.')
        assert res['bar.php'] == (tmp_path / 'bar.php').resolve()

    def test_php_require_framework_constant_concat_honest_skip(self, tmp_path):
        """`require_once ABSPATH . WPINC . '/version.php';` with NO
        `constant_index` supplied (the default, and every caller before
        BACK-565's opt-in `constant_index` kwarg existed): `ABSPATH`/`WPINC`
        are never defined anywhere in this tiny fixture, so there is nothing
        to substitute — must not crash and must not fabricate an edge, just
        honestly extract nothing for this statement. See TestPhpConstantDefines
        below for the BACK-565 case where these constants ARE indexed."""
        (tmp_path / 'wp-includes').mkdir()
        (tmp_path / 'wp-includes/version.php').write_text('<?php\n$wp_version = "1";\n')
        (tmp_path / 'main.php').write_text(
            "<?php\nrequire_once ABSPATH . WPINC . '/version.php';\n")
        entry = tmp_path / 'main.php'
        extractor = get_extractor(entry)
        imports = extractor.extract_imports(entry)
        assert imports == []

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

    def test_scala_import_resolves_via_package_dir(self, tmp_path):
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/Helper.scala').write_text('package a.b\nclass Helper\n')
        (tmp_path / 'Main.scala').write_text(
            'import a.b.Helper\n'
            'import a.b.{Foo, Bar}\n'
            'import a.b._\n'
        )
        res = self._resolve(tmp_path, 'Main.scala', '.')
        assert res['a.b.Helper'] == (tmp_path / 'a/b/Helper.scala').resolve()
        assert res['a.b.{Foo, Bar}'] is None  # selector import — skip, not fabricate
        assert res['a.b._'] is None           # wildcard import — skip

    def test_dart_relative_import_resolves_package_import_skips(self, tmp_path):
        (tmp_path / 'helper.dart').write_text('class Helper {}\n')
        (tmp_path / 'main.dart').write_text(
            "import './helper.dart';\n"
            'import "package:flutter/material.dart";\n'
        )
        res = self._resolve(tmp_path, 'main.dart', '.')
        assert res['./helper.dart'] == (tmp_path / 'helper.dart').resolve()
        # No pubspec.yaml anywhere in the tree — flutter is correctly
        # unresolvable, not a fabricated edge.
        assert res['package:flutter/material.dart'] is None

    def test_dart_package_uri_resolves_via_pubspec_self_import(self, tmp_path):
        """BACK-621: `package:<name>/x.dart` is the dominant real-world Dart
        import shape (5,989 of 6,290 in-tree imports in the AppFlowy sample
        corpus) and must resolve against the declaring package's own lib/,
        found via its pubspec.yaml `name:` field — not just relative
        literals, which covered only 301 of that corpus's imports."""
        (tmp_path / 'pubspec.yaml').write_text('name: my_app\ndescription: x\n')
        (tmp_path / 'lib/widgets').mkdir(parents=True)
        (tmp_path / 'lib/widgets/button.dart').write_text('class Button {}\n')
        (tmp_path / 'lib/main.dart').write_text(
            "import 'package:my_app/widgets/button.dart';\n"
        )
        res = self._resolve(tmp_path, 'lib/main.dart', 'lib')
        assert res['package:my_app/widgets/button.dart'] == (
            tmp_path / 'lib/widgets/button.dart').resolve()

    def test_dart_package_uri_resolves_across_sibling_package(self, tmp_path):
        """A monorepo (AppFlowy-shaped): `package:other_pkg/x.dart` from one
        package must resolve into a *different* package's lib/, keyed by
        that package's own pubspec.yaml — not just the importing file's own
        package."""
        (tmp_path / 'app').mkdir()
        (tmp_path / 'app/pubspec.yaml').write_text('name: app\n')
        (tmp_path / 'app/lib').mkdir()
        (tmp_path / 'app/lib/main.dart').write_text(
            "import 'package:shared_ui/button.dart';\n"
        )
        (tmp_path / 'packages/shared_ui').mkdir(parents=True)
        (tmp_path / 'packages/shared_ui/pubspec.yaml').write_text('name: shared_ui\n')
        (tmp_path / 'packages/shared_ui/lib').mkdir()
        (tmp_path / 'packages/shared_ui/lib/button.dart').write_text('class Button {}\n')
        res = self._resolve(tmp_path, 'app/lib/main.dart', 'app/lib')
        assert res['package:shared_ui/button.dart'] == (
            tmp_path / 'packages/shared_ui/lib/button.dart').resolve()

    def test_dart_package_uri_unknown_package_skips(self, tmp_path):
        """A `package:` URI naming no in-tree pubspec.yaml is a real external
        pub.dev dependency (e.g. `flutter` itself) — must stay None even
        when other in-tree packages exist, never fabricated onto one of
        them."""
        (tmp_path / 'pubspec.yaml').write_text('name: my_app\n')
        (tmp_path / 'lib').mkdir()
        (tmp_path / 'lib/main.dart').write_text(
            "import 'package:flutter/material.dart';\n"
        )
        res = self._resolve(tmp_path, 'lib/main.dart', 'lib')
        assert res['package:flutter/material.dart'] is None

    def test_dart_package_uri_with_show_combinator_resolves(self, tmp_path):
        """BACK-712 (drift second-corpus overfit-guard): a `show`/`hide`
        combinator clause trails the quoted URI (`import 'package:x/y.dart'
        show Foo;`) — the dominant self-limiting-import idiom in the drift
        corpus (105 pure show/hide statements, plus more combined with `as`).
        Before the fix, the generic strip-chars-off-both-ends path in
        `_build` left the trailing ` show Foo` text stuck to `module_name`
        (nothing at the *end* of the remainder was in the quote-strip set),
        producing the garbage string `"package:x/y.dart' show Foo"` — never
        resolves, a silent false negative. 88 of 1,039 sampled oracle edges
        in the drift corpus were missed by this, concentrated entirely on
        drift's own barrel file (`drift/lib/drift.dart`, the most
        show-imported target in the corpus)."""
        (tmp_path / 'pubspec.yaml').write_text('name: my_app\n')
        (tmp_path / 'lib').mkdir()
        (tmp_path / 'lib/drift.dart').write_text('class OpeningDetails {}\n')
        (tmp_path / 'lib/executor.dart').write_text(
            "import 'package:my_app/drift.dart' show OpeningDetails;\n"
        )
        res = self._resolve(tmp_path, 'lib/executor.dart', 'lib')
        assert res['package:my_app/drift.dart'] == (
            tmp_path / 'lib/drift.dart').resolve()

    def test_dart_package_uri_with_deferred_as_combinator_resolves(self, tmp_path):
        """Same shape as the `show` combinator, for Dart's `deferred as`
        lazy-import clause (`import 'package:x/y.dart' deferred as y;`) —
        the quoted URI must still resolve even with a trailing
        `deferred as alias` clause after it."""
        (tmp_path / 'pubspec.yaml').write_text('name: my_app\n')
        (tmp_path / 'lib').mkdir()
        (tmp_path / 'lib/helper.dart').write_text('class Helper {}\n')
        (tmp_path / 'lib/main.dart').write_text(
            "import 'package:my_app/helper.dart' deferred as helper;\n"
        )
        res = self._resolve(tmp_path, 'lib/main.dart', 'lib')
        assert res['package:my_app/helper.dart'] == (
            tmp_path / 'lib/helper.dart').resolve()

    def test_gdscript_extends_classname_resolves(self, tmp_path):
        """BACK-621: `extends Foo` resolves to whichever in-tree file declares
        `class_name Foo` — Godot's global class-registration convention. The
        dominant real edge shape (27 of 41) in the godot-demo-projects
        corpus, previously unresolved: a bareword `extends` only ever matched
        a literal `Foo.gd`, and Godot filenames are conventionally
        snake_case, not the PascalCase class name."""
        (tmp_path / 'project.godot').write_text('')
        (tmp_path / 'combat').mkdir()
        (tmp_path / 'combat/combatant.gd').write_text(
            'extends Node2D\nclass_name Combatant\n')
        (tmp_path / 'combat/opponent.gd').write_text('extends Combatant\n')
        res = self._resolve(tmp_path, 'combat/opponent.gd', 'combat')
        assert res['Combatant'] == (tmp_path / 'combat/combatant.gd').resolve()

    def test_gdscript_extends_builtin_class_skips(self, tmp_path):
        """`extends Node2D` (an engine builtin, not a project `class_name`)
        must stay None — never guessed onto an unrelated same-named file."""
        (tmp_path / 'project.godot').write_text('')
        (tmp_path / 'combat').mkdir()
        (tmp_path / 'combat/combatant.gd').write_text(
            'extends Node2D\nclass_name Combatant\n')
        (tmp_path / 'combat/enemy.gd').write_text('extends Node2D\n')
        res = self._resolve(tmp_path, 'combat/enemy.gd', 'combat')
        assert res['Node2D'] is None

    def test_gdscript_res_uri_resolves_against_project_root(self, tmp_path):
        """`res://` is project-root-relative, not file-relative — resolving it
        against the importing file's own directory must NOT work; only the
        project root (passed as a search path) should."""
        (tmp_path / 'project.godot').write_text('')
        (tmp_path / 'sub').mkdir()
        (tmp_path / 'sub/helper.gd').write_text('extends Node\n')
        (tmp_path / 'sub/main.gd').write_text(
            'const Helper = preload("res://sub/helper.gd")\n')
        entry = tmp_path / 'sub/main.gd'
        extractor = get_extractor(entry)
        stmt = extractor.extract_imports(entry)[0]
        # File-relative resolution (wrong root) must fail.
        assert extractor.resolve_import(stmt, base_path=entry.parent, search_paths=[]) is None
        # Project-root resolution (correct root) must succeed.
        resolved = extractor.resolve_import(
            stmt, base_path=entry.parent, search_paths=[tmp_path])
        assert resolved == (tmp_path / 'sub/helper.gd').resolve()

    def test_lua_require_dotted_path_resolves(self, tmp_path):
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/helper.lua').write_text('return {}\n')
        (tmp_path / 'main.lua').write_text(
            'local h = require("a.b.helper")\n'
            'local j = require("json")\n'
        )
        res = self._resolve(tmp_path, 'main.lua', '.')
        assert res['a.b.helper'] == (tmp_path / 'a/b/helper.lua').resolve()
        assert res['json'] is None  # not an in-tree file — skip

    def test_lua_require_directory_module_resolves_to_init(self, tmp_path):
        """BACK-621: `require("a.b")` may name a *directory* module — Lua's
        package.path `?/init.lua` convention — with no `a/b.lua` file at all.
        Confirmed on the real Kong corpus via its own rockspec module map
        (`kong.conf_loader` -> `kong/conf_loader/init.lua`); before this fix
        the dotted resolver only ever tried appending an extension to the
        last component, so every directory-module require silently resolved
        to None — a confident false negative reproduced on 5 real Kong
        targets (conf_loader, db.declarative, vaults.env, dynamic_hook,
        plugins.rate-limiting.policies)."""
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b/init.lua').write_text('return {}\n')
        (tmp_path / 'main.lua').write_text(
            'local h = require("a.b")\n')
        res = self._resolve(tmp_path, 'main.lua', '.')
        assert res['a.b'] == (tmp_path / 'a/b/init.lua').resolve()

    def test_lua_require_flat_file_wins_over_directory_module(self, tmp_path):
        """When both `a/b.lua` and `a/b/init.lua` exist, the flat file wins —
        matching require()'s real lookup order (package.path tries `?.lua`
        before `?/init.lua`) and the resolver's own ext-loop-then-index-
        fallback structure."""
        (tmp_path / 'a/b').mkdir(parents=True)
        (tmp_path / 'a/b.lua').write_text('return {}\n')
        (tmp_path / 'a/b/init.lua').write_text('return {}\n')
        (tmp_path / 'main.lua').write_text(
            'local h = require("a.b")\n')
        res = self._resolve(tmp_path, 'main.lua', '.')
        assert res['a.b'] == (tmp_path / 'a/b.lua').resolve()

    def test_lua_bare_single_token_require_prefers_directory_module(self, tmp_path):
        """BACK-711: a bare single-token `require("wibox")` with no dotted
        qualifier must resolve to the same-named directory's index file
        (`wibox/init.lua`) when one exists, not to an unrelated flat file
        elsewhere in the tree that happens to share the basename. Confirmed
        on the real AwesomeWM corpus: `require("wibox")` (393 call sites)
        was silently resolving onto `lib/awful/wibox.lua` — the tree's only
        other `wibox.lua` — via the k=1 global-uniqueness fallback, while the
        real target `lib/wibox/init.lua` showed 0 dependents."""
        (tmp_path / 'wibox').mkdir(parents=True)
        (tmp_path / 'wibox/init.lua').write_text('return {}\n')
        (tmp_path / 'awful').mkdir(parents=True)
        (tmp_path / 'awful/wibox.lua').write_text('return {}\n')
        (tmp_path / 'main.lua').write_text(
            'local w = require("wibox")\n')
        res = self._resolve(tmp_path, 'main.lua', '.')
        assert res['wibox'] == (tmp_path / 'wibox/init.lua').resolve()

    def test_lua_bare_single_token_require_prefers_true_sibling_flat_file(self, tmp_path):
        """BACK-711 companion case: when the flat file and the directory
        module are true siblings (same parent dir — `lib/beautiful.lua` next
        to `lib/beautiful/init.lua`, both real files in the AwesomeWM
        corpus), the flat file must still win, matching require()'s real
        `?.lua` before `?/init.lua` search order — the directory-index
        preference above only applies when the flat-file match is NOT a
        sibling of the directory."""
        (tmp_path / 'beautiful').mkdir(parents=True)
        (tmp_path / 'beautiful/init.lua').write_text('return {}\n')
        (tmp_path / 'beautiful.lua').write_text('return {}\n')
        (tmp_path / 'main.lua').write_text(
            'local b = require("beautiful")\n')
        res = self._resolve(tmp_path, 'main.lua', '.')
        assert res['beautiful'] == (tmp_path / 'beautiful.lua').resolve()

    def test_lua_multi_part_require_never_falls_back_to_bare_basename(self, tmp_path):
        """BACK-670: `require("resty.openssl.rand")` (an external OpenResty
        module, not in-tree) must NOT wrongly resolve onto `kong/tools/rand.lua`
        just because it's the only `rand.lua` in the tree — the multi-part
        import's real qualifying components (`resty`, `openssl`) never matched
        at any suffix, so it should skip, not guess."""
        (tmp_path / 'kong/tools').mkdir(parents=True)
        (tmp_path / 'kong/tools/rand.lua').write_text('return {}\n')
        (tmp_path / 'main.lua').write_text(
            'local r = require("resty.openssl.rand")\n')
        res = self._resolve(tmp_path, 'main.lua', '.')
        assert res['resty.openssl.rand'] is None

    def test_zig_relative_import_resolves_stdlib_skips(self, tmp_path):
        (tmp_path / 'helper.zig').write_text('pub const x = 1;\n')
        (tmp_path / 'main.zig').write_text(
            'const std = @import("std");\n'
            'const helper = @import("helper.zig");\n'
        )
        entry = tmp_path / 'main.zig'
        extractor = get_extractor(entry)
        by_mod = {}
        for stmt in extractor.extract_imports(entry):
            by_mod[stmt.module_name] = extractor.resolve_import(
                stmt, base_path=tmp_path, search_paths=[tmp_path])
        assert by_mod['helper.zig'] == (tmp_path / 'helper.zig').resolve()
        assert by_mod['std'] is None

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


class TestPhpConstantDefines:
    """BACK-565: `define()`-declared framework constants (`ABSPATH`, `WPINC`,
    ...) substituted into require/include concatenation chains.

    Mirrors ``DependsAdapter._build_constant_index``'s fixed-point shape at
    unit-test scale: extract every ``define()`` in the fixture tree via
    :meth:`extract_constant_defines`, fold into a ``name -> value`` dict, then
    pass that dict as ``constant_index`` to :meth:`extract_imports` — exactly
    what the real adapter does across a whole project.
    """

    @staticmethod
    def _constant_index(extractor, *file_paths):
        index = {}
        for _ in range(4):  # small fixed point, mirrors the real builder
            candidates = {}
            for fp in file_paths:
                for name, value in extractor.extract_constant_defines(fp, index):
                    candidates.setdefault(name, set()).add(value)
            new_index = {n: next(iter(v)) for n, v in candidates.items() if len(v) == 1}
            if new_index == index:
                break
            index = new_index
        return index

    def test_two_hop_constant_then_require_resolves(self, tmp_path):
        """`define('BASE_DIR', __DIR__ . '/lib')` then `require BASE_DIR .
        '/y.php'` — the constant itself resolves via BACK-564's `__DIR__`
        idiom, and the require resolves via BACK-565's substitution of that
        constant. Two hops, neither of which is a bare literal."""
        (tmp_path / 'lib').mkdir()
        (tmp_path / 'lib/y.php').write_text('<?php\n$x = 1;\n')
        (tmp_path / 'define.php').write_text(
            "<?php\ndefine( 'BASE_DIR', __DIR__ . '/lib' );\n")
        (tmp_path / 'main.php').write_text(
            "<?php\nrequire BASE_DIR . '/y.php';\n")
        extractor = get_extractor(tmp_path / 'main.php')
        index = self._constant_index(
            extractor, tmp_path / 'define.php', tmp_path / 'main.php')
        assert index['BASE_DIR'] == ('absolute', str((tmp_path / 'lib').resolve()))

        imports = extractor.extract_imports(tmp_path / 'main.php', constant_index=index)
        assert len(imports) == 1
        stmt = imports[0]
        assert stmt.is_relative is False
        resolved = extractor.resolve_import(
            stmt, base_path=tmp_path, search_paths=[tmp_path])
        assert resolved == (tmp_path / 'lib/y.php').resolve()

    def test_wordpress_three_operand_abspath_wpinc_chain_resolves(self, tmp_path):
        """`ABSPATH . WPINC . '/version.php'` — the real WordPress-core shape
        BACK-565 was filed for. `ABSPATH` is directory-relative via `__DIR__`,
        `WPINC` is a bare literal fragment; both must substitute into the
        3-operand chain for the whole require to resolve."""
        (tmp_path / 'wp-includes').mkdir()
        (tmp_path / 'wp-includes/version.php').write_text('<?php\n$wp_version = "1";\n')
        (tmp_path / 'wp-load.php').write_text(
            "<?php\n"
            "define( 'ABSPATH', __DIR__ . '/' );\n"
            "define( 'WPINC', 'wp-includes' );\n"
            "require_once ABSPATH . WPINC . '/version.php';\n"
        )
        entry = tmp_path / 'wp-load.php'
        extractor = get_extractor(entry)
        index = self._constant_index(extractor, entry)
        assert index['ABSPATH'] == ('absolute', str(tmp_path.resolve()))
        assert index['WPINC'] == ('literal', 'wp-includes')

        imports = extractor.extract_imports(entry, constant_index=index)
        assert len(imports) == 1
        resolved = extractor.resolve_import(
            imports[0], base_path=tmp_path, search_paths=[tmp_path])
        assert resolved == (tmp_path / 'wp-includes/version.php').resolve()

    def test_unknown_constant_still_honest_skips(self, tmp_path):
        """`require UNKNOWN_CONST . '/x.php';` where no `define()` for
        `UNKNOWN_CONST` exists anywhere in scope — even with a non-empty
        `constant_index` built from the rest of the tree, an absent name
        must not fabricate an edge."""
        (tmp_path / 'x.php').write_text('<?php\n$x = 1;\n')
        (tmp_path / 'define.php').write_text(
            "<?php\ndefine( 'OTHER_CONST', __DIR__ . '/other' );\n")
        (tmp_path / 'main.php').write_text(
            "<?php\nrequire UNKNOWN_CONST . '/x.php';\n")
        extractor = get_extractor(tmp_path / 'main.php')
        index = self._constant_index(
            extractor, tmp_path / 'define.php', tmp_path / 'main.php')
        assert 'UNKNOWN_CONST' not in index

        imports = extractor.extract_imports(tmp_path / 'main.php', constant_index=index)
        assert imports == []

    def test_ambiguous_constant_excluded_never_fabricates(self, tmp_path):
        """Two `define()` sites for the same name resolving to two genuinely
        different absolute directories (real WordPress shape: conditional
        `WP_MEMORY_LIMIT`/`WP_LANG_DIR` definitions) — the constant must be
        excluded from the index entirely, and a require built from it must
        honest-skip rather than pick one of the two candidates."""
        (tmp_path / 'a').mkdir()
        (tmp_path / 'b').mkdir()
        (tmp_path / 'a/one.php').write_text(
            "<?php\ndefine( 'AMBIG_DIR', __DIR__ . '/x' );\n")
        (tmp_path / 'b/two.php').write_text(
            "<?php\ndefine( 'AMBIG_DIR', __DIR__ . '/y' );\n")
        (tmp_path / 'main.php').write_text(
            "<?php\nrequire AMBIG_DIR . '/z.php';\n")
        extractor = get_extractor(tmp_path / 'main.php')
        index = self._constant_index(
            extractor, tmp_path / 'a/one.php', tmp_path / 'b/two.php', tmp_path / 'main.php')
        assert 'AMBIG_DIR' not in index

        imports = extractor.extract_imports(tmp_path / 'main.php', constant_index=index)
        assert imports == []

    def test_consistent_multi_site_constant_not_ambiguous(self, tmp_path):
        """Two `define()` sites for the same name that both reduce to the
        SAME real absolute directory (real WordPress shape: `ABSPATH` via
        `__DIR__ . '/'` at the project root vs. `dirname( __DIR__ ) . '/'`
        one level down) must agree, not be flagged ambiguous."""
        (tmp_path / 'admin').mkdir()
        (tmp_path / 'root_define.php').write_text(
            "<?php\ndefine( 'ABSPATH', __DIR__ . '/' );\n")
        (tmp_path / 'admin/nested_define.php').write_text(
            "<?php\ndefine( 'ABSPATH', dirname( __DIR__ ) . '/' );\n")
        extractor = get_extractor(tmp_path / 'root_define.php')
        index = self._constant_index(
            extractor, tmp_path / 'root_define.php', tmp_path / 'admin/nested_define.php')
        assert index['ABSPATH'] == ('absolute', str(tmp_path.resolve()))

    def test_dirname_with_levels_argument_resolves(self, tmp_path):
        """`dirname( __DIR__, 2 )` — real WordPress idiom
        (`wp-admin/maint/repair.php`) walking up two directory levels from
        `__DIR__` in one call, not the single-level `dirname(__DIR__)` form."""
        (tmp_path / 'wp-load.php').write_text('<?php\n$x = 1;\n')
        (tmp_path / 'wp-admin/maint').mkdir(parents=True)
        (tmp_path / 'wp-admin/maint/repair.php').write_text(
            "<?php\nrequire_once dirname( __DIR__, 2 ) . '/wp-load.php';\n")
        entry = tmp_path / 'wp-admin/maint/repair.php'
        extractor = get_extractor(entry)
        imports = extractor.extract_imports(entry)
        assert len(imports) == 1
        resolved = extractor.resolve_import(
            imports[0], base_path=entry.parent, search_paths=[tmp_path])
        assert resolved == (tmp_path / 'wp-load.php').resolve()

"""Data-driven import extraction for tree-sitter languages without a bespoke extractor.

Bespoke extractors (python.py, javascript.py, go.py, rust.py) hand-parse each
language's import grammar and resolve modules to files. That is a lot of code
per language, which is why only four existed — while IMPORTS_ADAPTER_GUIDE.md
advertised "✅ Full" support for ten. The gap showed up in dogfooding: `imports://`
returned a silent ``Total Files: 0`` for C, C++, C#, Java, PHP, and Ruby, which
reads as "clean" rather than "not scanned".

This module closes that gap the same way ``calls://`` already handles many
languages from one walker: a small per-language data table (:class:`_ImportSpec`)
naming the tree-sitter node kinds that *are* import statements, plus the leading
keyword tokens to strip. One generic walker turns each matching node into an
:class:`ImportStatement`. Adding a language is a table row and a three-line
subclass — no new parsing logic.

Scope (honest about what this delivers):
  * **Listing** of import statements for all covered languages — the primary fix
    for the silent-zero bug.
  * **File-level dependency edges** (``?circular``, fan-in) for every language
    whose imports name an *in-tree file* structurally (BACK-487/488):
      - C/C++ — ``#include "header.h"`` → sibling/searched file. Angle-bracket
        system includes (``<stdio.h>``) are intentionally not resolved.
      - Java — ``import com.pkg.Type`` → ``com/pkg/Type.java`` (package==dir is
        guaranteed by javac, so the full path-suffix match is reliable).
      - PHP — ``use App\\Models\\User`` → ``.../Models/User.php`` (longest unique
        path-suffix, tolerant of the PSR-4 vendor-root prefix); ``require``/
        ``include`` string-literal paths → file relative to the including file.
      - Ruby — ``require_relative './x'`` → ``x.rb`` relative to the file;
        ``load 'config.rb'``/``require 'lib/thing.rb'`` when they name a real
        in-tree ``.rb``. Bare ``require 'json'`` (a gem) is correctly skipped.
      - Swift — ``import Foo`` → ``Foo.swift`` when a module maps 1:1 to a file.
      - Kotlin — ``import com.pkg.Bar`` → ``com/pkg/Bar.kt`` full-suffix.
    Every case resolves *only* to a file that exists in the tree; when the
    target is a package/namespace/gem with no single backing file (Java ``.*``
    wildcards, C# ``using`` of a multi-file namespace, unresolved PSR-4 prefixes)
    the import is **skipped, never fabricated** — same honest-skip contract the
    C/C++ angle-bracket case has always had.
  * **C#** — ``using X.Y`` imports a *namespace* (a directory of files), not a
    single type. A dotted-name match still resolves the rare case a matching
    ``Y.cs`` exists; BACK-544 additionally indexes every file's declared
    ``namespace``/file-scoped-namespace and fans out an edge to *every* file
    declaring the imported namespace, closing the silent `imports://?circular`
    false-negative on C#.
  * **Unused-import detection is not claimed** for these languages — the imports
    are flagged ``skip_unused`` so they are never falsely reported as unused
    (textual ``#include`` and namespace/require imports lack reliable
    symbol-usage semantics without per-language work).

Verified node kinds against tree-sitter-language-pack 1.8.x real parses
(2026-07-02, session ancient-mission-0702).
"""

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import ClassVar, Dict, FrozenSet, List, Optional, Set, Tuple

from ...core import node_children as _children
from ...core import tree_root
from ...core.treesitter_compat import _zero_arg
from ...registry import get_analyzer
from ...utils.path_utils import is_skippable_dir
from .base import ImportsDiskCache, LanguageExtractor, register_extractor
from .types import ImportStatement

# Cross-invocation disk cache (BACK-626, extending BACK-625): same
# independent-reparse gap PythonExtractor had -- extract_imports() does not
# share TreeSitterAnalyzer.get_structure()'s structure cache (BACK-535). One
# namespace shared by every language riding this generic extractor (C/C++/
# Java/Kotlin/Scala/C#/Ruby/PHP/Swift/Dart/Lua/GDScript); the per-file
# fingerprint already keys on the file's own path, so different languages
# never collide. Bypassed when constant_index is supplied (PHP's define()
# resolution, BACK-565) -- that argument makes the result depend on more than
# the file's own contents, so it is not safe to key purely on path+mtime+size.
_IMPORTS_CACHE = ImportsDiskCache("generic_imports")

logger = logging.getLogger(__name__)

# BACK-564: sentinel distinguishing "this node's target isn't a concatenation
# expression, fall back to the ordinary text-based `_build` path" from a
# genuine `None` result ("this concatenation was classified and honestly
# skipped — do not fabricate an edge, do not fall back to text parsing
# either, since text parsing would produce a *worse*, garbage module_name").
_NOT_CONCAT = object()


@dataclass(frozen=True)
class _ImportSpec:
    """Per-language description of how imports appear in the tree-sitter grammar.

    Attributes:
        import_node_types: Node ``kind()`` values that represent a dedicated
            import statement (e.g. ``preproc_include``, ``import_declaration``).
        keywords: Leading whitespace-delimited tokens to strip from a node's
            source text before reading the module path (e.g. ``import``,
            ``using``, ``static``, ``#include``).
        call_import_names: For languages that express imports as ordinary calls
            (Ruby ``require 'json'``), the callee names that count as imports.
            Nodes of kind ``call_node_type`` are matched only when their first
            token is in this set. Empty for languages with dedicated import nodes.
        call_node_type: The tree-sitter node ``kind()`` for a call expression.
            Defaults to ``'call'`` (Ruby, GDScript); Lua's grammar names it
            ``'function_call'`` instead.
        alias_assignment: True when ``ALIAS = MODULE`` syntax assigns an alias
            (C#/C++ ``using X = Y``). The token left of ``=`` becomes the alias,
            the right side the module.
        resolve_includes: True when quoted paths should resolve to actual files
            for the dependency graph (C/C++ ``#include "foo.h"``).
        module_separator: The character joining components of a qualified
            *type* import that maps to a file path — ``.`` for Java/C#/Kotlin
            (``com.pkg.Type`` → ``com/pkg/Type.ext``), ``\\`` for PHP
            (``App\\Models\\User``). ``None`` for languages whose imports are
            only ever path-style string literals (Ruby) or single-token module
            names (Swift ``import Foo``). Enables dotted-name file resolution
            (BACK-487/488).
        source_extensions: The source-file extension(s) an unqualified module
            name maps to when resolving edges — ``{'.java'}``, ``{'.rb'}``,
            ``{'.php'}``, ``{'.cs'}``, ``{'.kt'}``, ``{'.swift'}``. Empty means
            "listing only, no edge resolution" (the pre-BACK-487 default). A
            non-empty set is the master switch that turns on
            :meth:`_resolve_module`.
        project_relative_prefix: A URI-style prefix (GDScript ``'res://'``)
            that names a path relative to the *project root*, not the
            importing file. When set and a module starts with this prefix,
            resolution strips it and tries only ``search_paths`` (never
            ``base_path``-relative) — see :meth:`_resolve_module`.
        resolve_namespaces: True when a qualified import names a *namespace*
            (a directory's worth of files) rather than one type, so
            filename-suffix matching alone under-resolves (C# ``using X.Y``,
            BACK-544). Callers with a cross-file namespace→file(s) index
            (built by scanning ``namespace_declaration``/
            ``file_scoped_namespace_declaration`` nodes, see
            :meth:`_GenericTreeSitterImportExtractor.extract_namespaces`) can
            resolve these to *every* file declaring that namespace via
            :meth:`_GenericTreeSitterImportExtractor.resolve_namespace_targets`,
            fanning out to multiple dependency edges instead of skipping.
        package_node_types: Node ``kind()`` value(s) for this language's
            package/namespace *declaration* statement (Java
            ``package_declaration``, Kotlin ``package_header``, PHP
            ``namespace_definition``; C# reuses this field for
            ``resolve_namespaces`` too, see :data:`_CSHARP_SPEC`). Unlike
            ``resolve_namespaces``, this alone does **not** enable edge
            fan-out — Java/Kotlin/PHP imports still name one type, resolved
            by :meth:`_resolve_module` as before. It only feeds the
            project-wide package index (BACK-547) that
            :meth:`is_intra_project_import` uses to turn an unresolved
            dotted import's ``None`` verdict into a precise ``True``/``False``
            instead of the honest-but-blunt "can't tell". Empty means no
            per-file package declaration to scan (Swift: modules aren't
            declared in source, so it stays ``None`` forever — correctly, not
            a gap to close).
        nested_member_fallback: True for languages whose imports can name a
            *member of* an enclosing top-level type (Java/Kotlin/Scala nested
            types ``import a.b.Outer.Inner`` and static-member imports
            ``import static a.b.Outer.CONST``). Enables :meth:`_resolve_dotted`
            to peel the trailing member/nested component down to the enclosing
            class (``Outer``) when the direct match fails (BACK-551). Off for
            PHP (``\\`` namespaces whose components are also StudlyCaps, so the
            Uppercase-type gate can't safely tell package from type) and Swift/
            Lua (no such idiom) — pending their own real-corpus measurement.
        member_node_types: Node ``kind()`` value(s) for a *top-level* member
            declaration this language allows outside any class — Kotlin
            ``function_declaration``/``property_declaration`` directly under
            ``source_file`` (unlike Java, Kotlin permits free functions and
            properties at file scope). Feeds the cross-file
            ``(package, symbol) -> [files]`` index that
            :meth:`extract_top_level_members` builds and
            :meth:`resolve_member_targets` looks up. Empty means the language
            has no such idiom (Java/C#/PHP: every importable symbol is a type,
            already covered by :meth:`_resolve_dotted`).
        member_symbol_fallback: True to use the top-level-member index as a
            last-resort fallback when both the direct dotted match and the
            ``nested_member_fallback`` enclosing-class peel fail. BACK-547
            Kotlin measurement loop: ``import a.b.foo`` where ``foo`` is a
            top-level function/property has *no* enclosing type anywhere in
            the import string (unlike ``import a.b.Outer.Inner``), so peeling
            trailing components can never find the real declaring file (e.g.
            ``Utils.kt``) — only a content-level index over ``a.b``'s files
            can. Kotlin-only (confirmed absent in real Scala 2 code — Scala
            forbids bare top-level defs outside a package object entirely,
            see ``container_member_fallback`` below for Scala's own gap;
            PHP/Swift/Lua have no such idiom either).
        member_container_node_types: Node ``kind()`` value(s) for a
            *top-level named container* whose members are reached by
            ``import a.b.Container.member`` where ``Container`` does not
            satisfy ``nested_member_fallback``'s Uppercase-type gate — Scala
            ``object_definition`` when the object is named in lowerCamelCase
            (idiomatic for a "static-helpers" object, e.g. ``object
            helpers``). Feeds :meth:`extract_container_members`. Empty means
            the language has no such gap (its containers are always
            PascalCase types, already covered by ``nested_member_fallback``).
        container_member_node_types: Node ``kind()`` value(s) for a member
            declaration *directly inside* a ``member_container_node_types``
            container's body — Scala ``function_definition``/
            ``val_definition`` inside an ``object``'s ``template_body``.
        container_member_fallback: True to synthesize
            ``(package.Container, member) -> [file]`` entries into the same
            content-scanned index :meth:`resolve_member_targets` looks up
            (BACK-557 Scala measurement loop). BACK-551's Uppercase-gated
            peel already resolves ``import a.b.Directory.getX`` (PascalCase
            container) to ``Directory.scala``, but real GitBucket code has
            ``object helpers`` — a lowerCamelCase container the peel
            deliberately refuses to reach (indistinguishable, by name alone,
            from peeling into a package segment and fabricating an edge).
            Verifying the peeled component is a *real declared container*,
            not just a same-named file, is exactly BACK-555's content-scan
            idea one level deeper — a container's own member set, rather
            than the file's top level. Scala-only; Java/Kotlin/C#/PHP/Swift
            have no lowerCamelCase-container idiom.
        same_module_undetectable: True when this language's same-module
            (same target/package) cross-file references are architecturally
            invisible to import extraction — there is no import statement to
            miss, because the whole module compiles together and files reach
            each other's top-level declarations with no syntax naming the
            source file at all (Swift: a sibling file in the same target
            needs no ``import`` to use another file's public/internal
            declarations). BACK-560: this is *not* an unresolved-import case
            (``_unresolved_intra`` never increments — nothing was extracted
            to fail resolving), so the existing ⚠ honest-decline signal,
            keyed on that counter, never fires either. A ``depends://`` query
            against such a file that has real same-module dependents still
            confidently reports "no dependents," indistinguishable from a
            genuinely dependency-free file. This flag lets the adapter emit
            an unconditional informational note instead — "this language
            can't express that edge as an import" is a different claim than
            "we tried to resolve an import and failed," so it gets a
            different (non-⚠) signal. False for every other language: their
            same-module references, if any exist, still show up as ordinary
            unresolved intra-project imports and are already covered by the
            existing honest-decline path.
        strip_attribute_prefix: True when this language allows a
            declaration-level attribute (Swift: ``@testable``, ``@_spi(Foo)``,
            ``@_implementationOnly``, ``@preconcurrency``, …) directly before
            the import keyword itself (BACK-669 swift-collections second-
            corpus finding). :meth:`_build`'s keyword-stripping tokenizer
            only pops a leading token that exactly equals one of
            ``spec.keywords``; an attribute token isn't a fixed string (its
            argument varies, ``@_spi(Testing)`` vs ``@_spi(Http)``) so it
            can't be listed there, and a real test file commonly stacks two
            (``@_spi(Testing) @testable import Foo``). Without this flag the
            un-stripped attribute text becomes part of ``module_name``
            itself (the whole statement, verbatim) — a garbage module name
            that can never match a real target, silently producing zero
            resolved edges for every such import with no honest-decline
            warning either (the statement doesn't even reach a "know we
            couldn't resolve this" path; it just names a module that looks
            uniquely unresolvable). When set, any leading token starting
            with ``@`` is stripped alongside the fixed keyword set, however
            many are stacked, before the keyword strip loop's normal exit
            condition is checked. False for every other language: none
            allows a bare-``@`` token immediately before their import
            keyword.
        convention_autoloaded: True when this language commonly resolves
            intra-project references by a file-path/name *convention* rather
            than an explicit import statement, so a low density of
            import/require statements across the tree signals that
            statement-based dependency analysis structurally undercounts.
            Ruby/Rails (Zeitwerk, the default autoloader since Rails 6) maps
            ``app/models/foo/bar.rb`` → ``Foo::Bar`` and resolves bare constant
            references with zero ``require``/``require_relative`` — in a real
            Rails app only single-digit-percent of files carry any require, so
            ``depends://`` sees almost none of the real intra-app edges.
            BACK-557: this flag lets the adapter emit a project-level coverage
            caveat (even on *positive* results, unlike the ⚠ honest-decline
            which is empty-only) when require density falls below a threshold —
            containment first, before any convention-inference recall feature.
        zeitwerk_convention: True when this language's convention-autoloaded
            references (see ``convention_autoloaded``) can additionally be
            *inferred* as edges — not just caveated — by extracting bare
            constant references from the file body and mapping each to an
            in-tree file via the path→constant convention. BACK-557 direction
            a (the recall half): gates :meth:`extract_constant_references`,
            a no-op for every language without it.
        concat_relative_node_types: Node ``kind()`` value(s) among
            ``import_node_types`` whose *target* may be built by string
            concatenation rather than a bare literal — PHP's
            ``require``/``require_once``/``include``/``include_once``
            (BACK-564). WordPress-core measurement found 0/387 real
            require/include edges use a bare string literal; every real
            statement concatenates a leading operand onto a trailing path
            fragment (``__DIR__ . '/x.php'``, ``dirname( __FILE__ ) .
            '/x.php'``, ``ABSPATH . WPINC . '/version.php'``). The ordinary
            text-based :meth:`_build` path strips quote/space characters off
            the *ends* of the whole remainder string, which cannot parse a
            concatenation expression — the leading operator/constant text
            stays embedded in ``module_name``, so it can never match a real
            file. When a node's kind is in this set, :meth:`_node_to_import`
            first tries :meth:`_concat_to_import`, which walks the AST
            structurally (mirroring :meth:`_call_to_import`'s
            structural-not-textual approach) instead of slicing text.
            Only the universal PHP magic-constant idiom (``__DIR__`` /
            ``dirname( __FILE__ )``, semantically identical to Ruby's
            ``require_relative``) is resolved; any other leading operand
            (``ABSPATH``, ``WPINC``, or anything else reveal can't classify)
            is an honest skip — never a fabricated edge, matching this
            module's "resolves only to a file that exists, or not at all"
            contract. A node with no concatenation at all (a bare string
            literal, still legal PHP) falls through unchanged to the
            existing :meth:`_build` text path. Empty means no language uses
            this idiom (every language but PHP).

            BACK-565 extends this: when the ``__DIR__``/``dirname(__FILE__)``
            single-operand idiom above doesn't match (multi-operand chains
            whose leading operand is itself a nested concatenation, e.g.
            ``ABSPATH . WPINC . '/version.php'``), :meth:`_concat_to_import`
            falls back to :meth:`_resolve_concat_operand`, which can
            substitute a *known project constant* (see
            ``constant_define_call_names`` below) for any operand and keep
            walking the chain. Still never a guess: an operand that is
            neither a literal, the magic-constant idiom, nor a constant
            already proven unambiguous project-wide is an honest skip of the
            whole statement.
        constant_define_call_names: Callee name(s) that declare a global
            constant — PHP's ``define`` (``define('ABSPATH', __DIR__ . '/')``,
            BACK-565). Feeds :meth:`_GenericTreeSitterImportExtractor.extract_constant_defines`,
            which scans every ``define()`` call in the tree once (mirroring
            the "build once, pass down" shape ``extract_namespaces``/
            ``extract_top_level_members`` already use) into a project-wide
            ``name -> ('literal', str) | ('absolute', str)`` index that
            :meth:`_resolve_concat_operand` looks up when a concatenation's
            operand is an identifier it doesn't otherwise recognize. Empty
            means no language uses this idiom (every language but PHP).
        module_dir_convention: Directory segment name(s) under which the
            immediately-following path component names a build *module/target*
            whose members are every source file beneath it — Swift SwiftPM's
            ``Sources/<Target>/**`` and ``Tests/<Target>/**`` layout
            (BACK-567). A Swift ``import Foo`` names a whole module, not a
            file, and that module is almost never a single ``Foo.swift`` (real
            targets are multi-file), so :meth:`_resolve_module`'s bare-basename
            match resolves ~0% of real cross-module imports — measured 123
            edges / 7 dependent files across a 1,961-file real corpus
            (Kickstarter iOS, 8 SwiftPM packages) despite 1,000+ real
            ``import <in-tree module>`` statements, with ``_unresolved_intra``
            stuck at 0 so not even the ⚠ honest-decline signal fired (a silent
            wrong "no dependents," the exact failure class BACK-547 exists to
            kill). When set, the adapter builds a path-derived
            ``module -> [files]`` index (:meth:`module_for_file`, no parsing —
            pure directory convention, so no Swift toolchain is needed at
            runtime, mirroring how the PHP concat fix never shells out to
            ``php``) and :meth:`resolve_module_targets` fans ``import Foo`` out
            to every file in module ``Foo`` — the same many-files fan-out C#'s
            namespace index uses. The index's module names also feed
            :meth:`is_intra_project_import`: an ``import`` of a known in-tree
            module is intra-project; anything else (``Foundation``, ``Apollo``,
            a SwiftPM registry/URL dependency) is external and correctly
            edge-less. Orthogonal to ``same_module_undetectable`` — that still
            covers *same*-target cross-file references, which genuinely have no
            import statement; this covers *cross*-module imports, which do.
            Module names are sanitized to Swift's rule (non-identifier chars →
            ``_``, so directory ``Kickstarter-Framework`` matches ``import
            Kickstarter_Framework``). Empty for every other language.
        manifest_filename: The build-manifest filename whose declared targets
            override ``module_dir_convention`` when a target sets an explicit
            source ``path:`` — Swift's ``Package.swift`` (BACK-567). The pure
            ``Sources/<Target>/`` convention is right for the common case, but
            SwiftPM lets a target relocate its sources (``.target(name:
            "GraphAPI", path: "./Sources")`` puts a *whole* ``Sources/`` tree —
            subdirs and all — in one module; ``path: "./GraphAPITestMocks"``
            puts them outside ``Sources/`` entirely). The real-corpus oracle
            (cross-checked against ``swift package dump-package``) found the
            convention alone mis-maps every such file, and — worse —
            ``import GraphAPI`` (326 real importers) then classifies as external
            and reports zero dependents with no ⚠, the silent-negative BACK-547
            forbids. When set, the adapter parses each manifest
            (:meth:`extract_manifest_targets`, structural tree-sitter walk of
            the ``.target``/``.testTarget`` calls — no toolchain, mirroring the
            PHP concat fix) for authoritative target→directory mappings and
            resolves a file's module by longest-prefix match, falling back to
            the directory convention only where no manifest target claims it.
            Empty for every other language.
        manifest_target_calls: The manifest callee name(s) that declare a build
            target — SwiftPM's ``target``, ``testTarget``, ``executableTarget``,
            ``macro``, ``plugin`` (BACK-567). Feeds
            :meth:`extract_manifest_targets`. ``testTarget`` defaults its source
            directory to ``Tests/<name>`` rather than ``Sources/<name>``; the
            rest default to ``Sources/<name>`` (both overridable by an explicit
            ``path:``). Empty for every other language.
        package_uri_scheme: A URI scheme prefix — Dart's ``package:`` — whose
            remainder is ``<package-name>/<path-under-lib>`` (BACK-621, found
            against the real AppFlowy corpus: baseline sampled recall 19.27%
            with 0 false positives, because ``_resolve_module`` had no branch
            for this shape at all — ``package:appflowy/x/y.dart`` contains a
            ``/`` and starts matching before any separator logic runs, so
            :meth:`_looks_like_path` claimed it first and tried it as a
            literal file-relative path, which a ``package:`` URI never is;
            5,989 of 1,974 files' import statements in the sample corpus used
            this shape, dwarfing the 301 relative imports the resolver
            already handled correctly). When set, :meth:`_resolve_module`
            checks this prefix *before* :meth:`_looks_like_path` (a
            ``package:`` URI is never file-relative) and resolves the
            package name against a project-wide ``name -> lib/`` index built
            once per scan from every in-tree ``package_manifest_filename``
            (Dart's ``pubspec.yaml`` ``name:`` field — the same
            authoritative-manifest role Lua's rockspec and Swift's
            ``Package.swift`` play), never fabricating a mapping for a
            package whose manifest isn't in-tree (a real pub.dev dependency
            stays correctly edge-less). Empty for every other language.
        package_manifest_filename: The per-package manifest filename
            ``package_uri_scheme`` resolution reads for a declared package
            name — Dart's ``pubspec.yaml``. Unset when ``package_uri_scheme``
            is unset.
        package_manifest_lib_dirname: The directory (relative to the
            manifest's own directory) a resolved package's URI paths are
            rooted at — Dart's ``lib`` (``package:foo/bar.dart`` →
            ``<dir-of-manifest-declaring-foo>/lib/bar.dart``). Unset when
            ``package_uri_scheme`` is unset.
        class_name_convention: When set, a single-identifier module (Swift-
            style bare basename match already tried first) that fails to
            resolve is retried against a project-wide index of every in-tree
            source file's declared global-registration name — GDScript's
            ``class_name Foo`` (BACK-621: 27 of 41 real edges in the
            godot-demo-projects corpus, the dominant shape). Godot registers
            ``class_name``-declared classes engine-wide, so ``extends Foo``/
            ``preload``-free type references elsewhere never name the
            declaring file at all — no other currently-supported language has
            this shape (a global symbol registered from an arbitrary,
            non-manifest source file, resolved by identifier alone). The
            index is built once per scan, scanning every in-tree file of
            ``source_extensions`` for a leading ``class_name NAME`` line
            (mirrors the ``package_manifest_*`` regex-not-AST convention) and
            cached on ``file_index`` the same way. A bareword ``extends Node``
            naming an engine builtin (the overwhelming majority — 410 of 438
            in the same corpus) correctly finds no entry and stays ``None``.
            Off for every other language.
        load_path_manifest_glob: Filename glob identifying a per-package
            manifest that registers its own directory as an *additional* bare-
            import search root, alongside the project root — RubyGems'
            ``*.gemspec`` (BACK-669 solidus second-corpus loop). Unlike
            ``package_manifest_filename``/``package_uri_scheme`` (Dart), this
            has no ``scheme:name/path`` prefix to key a lookup by declared
            name: a bare ``require 'spree/foo'`` doesn't say which gem it
            means, it just needs *some* in-tree gem's ``lib/`` to contain
            ``spree/foo.rb``. So every manifest's ``load_path_lib_dirname``
            becomes an unconditional extra search root, tried the same way
            the single project root already is. A single-gem project (most
            Ruby apps, e.g. Discourse) has exactly one such manifest at the
            project root, so this is a no-op widening there — it only matters
            for a multi-gem monorepo (Rails Engine gems, each with its own
            ``lib/`` on Bundler's ``$LOAD_PATH``), which the original
            single-app Discourse measurement never exercised. Unset for every
            other language.
        load_path_lib_dirname: The directory (relative to a
            ``load_path_manifest_glob`` match's own directory) that manifest
            registers as a load-path root — RubyGems' ``lib``. Unset when
            ``load_path_manifest_glob`` is unset.
        directory_index_filenames: Filename(s) that let a dotted qualified name
            resolve to a *directory module* — Lua's ``require("a.b.c")`` →
            ``a/b/c/init.lua`` when no ``a/b/c.lua`` file exists (BACK-621,
            confirmed against the real Kong corpus's own ``rockspec`` module
            map: ``kong.conf_loader`` → ``kong/conf_loader/init.lua``, not a
            flat file). :meth:`_match_dotted` only ever tried appending an
            extension to the *last* dotted component (``parts[:-1] +
            [parts[-1] + ext]``); a directory-module require has no file
            component to append the extension to — the whole dotted path
            names a directory, and the real file is one level deeper with a
            fixed name. Every project in the real corpus that groups a
            submodule under a directory (``kong/db/declarative/``,
            ``kong/vaults/env/``, ``kong/dynamic_hook/``,
            ``kong/plugins/rate-limiting/policies/``) hit this — a confident
            false negative on every statement across the whole corpus naming
            them, with no honest-decline caveat (the miss is in the *target*
            direction, not the importer's unresolved-import counter). When
            set, a failed direct match additionally tries ``parts +
            [index_filename]`` for each filename in this set via the same
            longest-unique-suffix machinery (never fabricating an edge — still
            skipped on ambiguity). Empty for every other language.
        namespaced_type_node_types: Node ``kind()`` value(s) for a top-level
            *type* declaration whose ``(declared-namespace, type-name)`` pair
            should be indexed for qualified-reference resolution beyond a
            plain ``using Namespace;`` — C#'s ``class``/``interface``/
            ``struct``/``record``/``enum`` declarations (BACK-669 C# recall
            loop). C# has two real ``using`` idioms whose target names a
            *specific type*, not a namespace: ``using static Foo.Bar.Type;``
            (imports one type's static members) and ``using Alias =
            Foo.Bar.Type;`` (a type alias — the dominant real shape, 87 of 96
            alias statements in the Jellyfin corpus). Both produce a
            ``module_name`` one component longer than any namespace the tree
            declares, so :meth:`resolve_namespace_targets` never matches, and
            :meth:`_resolve_dotted`'s directory-suffix match only succeeds
            when the physical directory layout happens to mirror the dotted
            namespace *and* the type's filename is unique tree-wide — real
            multi-project C# repos commonly violate both (a top-level
            directory named ``Project.SubProject`` embeds a literal ``.`` as
            one path component, not a nested ``Project/SubProject/``; and a
            same-named type in two different namespaces, e.g. a DTO/entity
            pair, makes the basename ambiguous). Reuses the same
            ``member_index``/:meth:`resolve_member_targets` machinery
            Kotlin/Scala's member-symbol fallback already built — feeds
            ``member_index[(declared_namespace, type_name)]`` the same way
            :meth:`extract_top_level_members` feeds
            ``member_index[(declared_namespace, function_name)]`` — gated by
            ``namespaced_type_fallback`` below so it's a no-op for every
            other language. Only a genuinely top-level type counts (parent is
            the namespace/compilation-unit level, not another type's body) —
            a nested type is out of scope for this fallback (its own
            enclosing-type peel is a distinct, unimplemented idiom, same as
            Java's ``nested_member_fallback`` which C# doesn't opt into).
        namespaced_type_fallback: True to use the ``(namespace, type)``
            member-index fallback above as a last resort when the direct
            dotted match and namespace fan-out both fail — C#-only. Shares
            :meth:`resolve_member_targets`'s split-on-last-separator lookup
            with Kotlin/Scala's member-symbol fallback (harmless overlap: the
            two flags gate mutually exclusive index keys).
        combinator_clause: When set, ``_build`` truncates the parsed remainder
            at the closing quote of its leading quoted literal before
            extracting ``module_name`` — Dart's ``show``/``hide``/``deferred
            as`` combinators (BACK-712, second-corpus overfit-guard, drift
            monorepo: ``import 'package:drift/drift.dart' show
            OpeningDetails;``). Without this, the generic keyword-strip +
            ``.strip('"\\' ')`` path only trims characters belonging to the
            strip set off each *end* of the whole remainder — a trailing
            ``show OpeningDetails`` has no such characters at its own end, so
            nothing is trimmed and ``module_name`` ends up as the literal
            garbage ``"package:drift/drift.dart' show OpeningDetails"``,
            which starts with the ``package:`` scheme but never resolves (the
            corrupted suffix isn't a real sub-path under any in-tree
            package's ``lib/``) — a silent false negative, invisible to the
            honest-decline signal for the same reason every prior loop's
            misses were. 88 of a 30-target stratified sample's 1,039 oracle
            edges (all on ``drift/lib/drift.dart``, drift's own barrel file
            and the single most `show`-imported target in the corpus) were
            missed by this before the fix. Off for every other language —
            none of C/C++/Java/C#/PHP/Ruby/Swift/Kotlin/Scala/GDScript/Lua's
            import grammars have a combinator clause after the module target,
            so their remainder never has anything trailing the quote/token to
            truncate.
    """

    import_node_types: FrozenSet[str]
    keywords: FrozenSet[str]
    call_import_names: FrozenSet[str] = field(default_factory=frozenset)
    call_node_type: str = 'call'
    alias_assignment: bool = False
    resolve_includes: bool = False
    module_separator: Optional[str] = None
    source_extensions: FrozenSet[str] = field(default_factory=frozenset)
    project_relative_prefix: Optional[str] = None
    resolve_namespaces: bool = False
    package_node_types: FrozenSet[str] = field(default_factory=frozenset)
    nested_member_fallback: bool = False
    member_node_types: FrozenSet[str] = field(default_factory=frozenset)
    member_symbol_fallback: bool = False
    member_container_node_types: FrozenSet[str] = field(default_factory=frozenset)
    container_member_node_types: FrozenSet[str] = field(default_factory=frozenset)
    container_member_fallback: bool = False
    same_module_undetectable: bool = False
    strip_attribute_prefix: bool = False
    convention_autoloaded: bool = False
    zeitwerk_convention: bool = False
    concat_relative_node_types: FrozenSet[str] = field(default_factory=frozenset)
    constant_define_call_names: FrozenSet[str] = field(default_factory=frozenset)
    module_dir_convention: FrozenSet[str] = field(default_factory=frozenset)
    manifest_filename: Optional[str] = None
    manifest_target_calls: FrozenSet[str] = field(default_factory=frozenset)
    package_uri_scheme: Optional[str] = None
    package_manifest_filename: Optional[str] = None
    package_manifest_lib_dirname: Optional[str] = None
    load_path_manifest_glob: Optional[str] = None
    load_path_lib_dirname: Optional[str] = None
    directory_index_filenames: FrozenSet[str] = field(default_factory=frozenset)
    class_name_convention: bool = False
    namespaced_type_node_types: FrozenSet[str] = field(default_factory=frozenset)
    namespaced_type_fallback: bool = False
    combinator_clause: bool = False


class _GenericTreeSitterImportExtractor(LanguageExtractor):
    """Extract imports for one language from a data-driven :class:`_ImportSpec`.

    Subclasses set ``extensions``, ``language_name``, and ``spec``. All parsing
    behaviour is inherited; there is no per-language code.
    """

    # Subclasses MUST set these.
    spec: ClassVar[_ImportSpec]

    def extract_imports(
        self,
        file_path: Path,
        constant_index: Optional[Dict[str, Tuple[str, str]]] = None,
    ) -> List[ImportStatement]:
        """Extract this file's import statements.

        ``constant_index`` (BACK-565, optional): a project-wide
        ``name -> ('literal', str) | ('absolute', str)`` map of PHP
        ``define()``-declared constants (see
        :meth:`extract_constant_defines`), built once by the caller and
        passed down the same way ``file_index`` is for resolution — used
        only by :meth:`_concat_to_import` to substitute a known constant
        into a require/include concatenation chain. ``None`` (the default,
        and every non-PHP caller) behaves exactly as before this session:
        constant-involving concatenations are honestly skipped, not
        fabricated.

        Cached cross-invocation on disk (BACK-626) when ``constant_index`` is
        ``None`` -- the common case for every caller but PHP's constant-aware
        resolution path, whose result depends on more than the file's own
        contents and so is deliberately never cached.
        """
        if constant_index is not None:
            return self._extract_imports_uncached(file_path, constant_index)
        return _IMPORTS_CACHE.get_or_compute(
            file_path, lambda: self._extract_imports_uncached(file_path, None)
        )

    def _extract_imports_uncached(
        self,
        file_path: Path,
        constant_index: Optional[Dict[str, Tuple[str, str]]],
    ) -> List[ImportStatement]:
        analyzer = self._get_analyzer(file_path)
        if analyzer is None:
            return []

        imports: List[ImportStatement] = []

        for node_type in self.spec.import_node_types:
            for node in analyzer._find_nodes_by_type(node_type):
                stmt = self._node_to_import(node, analyzer, file_path, constant_index)
                if stmt is not None:
                    imports.append(stmt)

        # Call-style imports (Ruby require/require_relative/load; Lua require;
        # GDScript preload/load).
        if self.spec.call_import_names:
            for node in analyzer._find_nodes_by_type(self.spec.call_node_type):
                stmt = self._call_to_import(node, analyzer, file_path)
                if stmt is not None:
                    imports.append(stmt)

        imports.sort(key=lambda s: s.line_number)
        return imports

    def extract_symbols(self, file_path: Path) -> Set[str]:
        """Not implemented for generic languages.

        Symbol-usage extraction (for unused-import detection) needs
        per-language semantics we do not claim here. Imports produced by this
        extractor set ``skip_unused=True`` so they are never falsely flagged.
        """
        return set()

    # --- BACK-544/547: package/namespace declaration scanning -------------

    _PACKAGE_NAME_CHILD_KINDS: ClassVar[FrozenSet[str]] = frozenset({
        'qualified_name', 'identifier', 'scoped_identifier', 'namespace_name',
        # Scala `package a.b.c` (package_clause) names its child
        # `package_identifier`, not any of the above (BACK-557).
        'package_identifier',
    })

    def extract_namespaces(self, file_path: Path) -> List[str]:
        """Package/namespace names this file declares — C# ``namespace X.Y``,
        Java ``package a.b.c;``, Kotlin ``package a.b.c``, PHP
        ``namespace App\\Models;`` — for the cross-file index that
        :meth:`resolve_namespace_targets` (C# edge fan-out, BACK-544) and
        :meth:`is_intra_project_import` (honest-decline classification,
        BACK-547) both look up.

        A file may declare more than one namespace (C# sequential/nested
        blocks); all are returned. No-op (``[]``) unless
        ``spec.package_node_types`` is set — languages with no such
        declaration node (Swift) would return empty anyway, but the gate
        avoids a pointless extra parse pass over every file of those
        languages.
        """
        if not self.spec.package_node_types:
            return []
        analyzer = self._get_analyzer(file_path)
        if analyzer is None:
            return []
        namespaces: List[str] = []
        for node_type in self.spec.package_node_types:
            for node in analyzer._find_nodes_by_type(node_type):
                for child in _children(node):
                    if child.kind() in self._PACKAGE_NAME_CHILD_KINDS:
                        namespaces.append(analyzer._get_node_text(child))
                        break
        return namespaces

    def resolve_namespace_targets(
        self,
        stmt: ImportStatement,
        namespace_index: Dict[str, List[Path]],
    ) -> List[Path]:
        """Every in-tree file declaring the namespace ``stmt`` imports (BACK-544).

        Unlike :meth:`_resolve_module`'s single-file, uniqueness-gated match,
        a namespace legitimately spans many files — ``using Foo.Bar`` depends
        on the whole namespace, not one type, so this fans out to every file
        that declares it rather than skipping when there's more than one
        (the honest-skip contract still holds: an unknown namespace returns
        ``[]``, never a guessed path). Wildcards/wildcard-shaped selectors are
        rejected the same way :meth:`_resolve_module` rejects them.
        """
        if not self.spec.resolve_namespaces:
            return []
        module = stmt.module_name
        if not module or module.endswith('*'):
            return []
        return list(namespace_index.get(module, ()))

    @staticmethod
    def _sanitize_module_name(name: str) -> str:
        """Swift's module-name rule: a target's module identifier replaces every
        non-alphanumeric-underscore character in the target name with ``_``, so
        a target directory ``Kickstarter-Framework`` is imported as
        ``Kickstarter_Framework`` (BACK-567). Applied to both the directory-
        derived key and (idempotently) the import name so they match."""
        return ''.join(c if (c.isalnum() or c == '_') else '_' for c in name)

    def module_for_file(self, file_path: Path) -> Optional[str]:
        """The build module/target a file belongs to, by directory convention
        (BACK-567) — no parsing, so it needs no language toolchain.

        Walks the path for a segment named in ``spec.module_dir_convention``
        (Swift: ``Sources``/``Tests``); the *next* component is the target
        name, sanitized to the module identifier. Returns ``None`` when the
        file isn't under such a layout (a loose script, a `Package.swift`
        itself) so it's simply not indexed — never guessed into a module.
        The next component must not be the file's own basename (a file sitting
        directly in ``Sources/`` names no module).
        """
        segments = self.spec.module_dir_convention
        if not segments:
            return None
        parts = file_path.parts
        for i, part in enumerate(parts):
            # parts[i+1] is the target name; something must follow it (parts[i+2:]
            # non-empty) for the file to live *inside* the module, not be a loose
            # file sitting directly in Sources/ that names no module.
            if part in segments and i + 2 < len(parts):
                return self._sanitize_module_name(parts[i + 1])
        return None

    def resolve_module_targets(
        self,
        stmt: ImportStatement,
        module_index: Dict[str, List[Path]],
    ) -> List[Path]:
        """Every in-tree file of the module ``stmt`` imports (BACK-567, Swift).

        A Swift ``import Foo`` names a whole module, not one file, so — like
        C#'s namespace fan-out (:meth:`resolve_namespace_targets`) — this
        returns *every* file in module ``Foo`` rather than a single guessed
        ``Foo.swift``. An import of a module not in the index (an external
        framework/dependency) returns ``[]``, never a fabricated path (the
        honest-skip contract every resolver here holds to)."""
        if not self.spec.module_dir_convention:
            return []
        module = stmt.module_name
        if not module:
            return []
        return list(module_index.get(self._sanitize_module_name(module), ()))

    def extract_manifest_targets(
        self, file_path: Path,
    ) -> List[Tuple[str, Optional[str], bool]]:
        """Targets declared in a build manifest (Swift ``Package.swift``,
        BACK-567) — the authoritative override for the directory convention
        when a target relocates its sources with an explicit ``path:``.

        Structurally walks each ``.target``/``.testTarget``/… call
        (``spec.manifest_target_calls``) for its ``name:`` and optional
        ``path:`` string-literal arguments — no manifest evaluation, no Swift
        toolchain, mirroring :meth:`_call_to_import`'s AST-not-text approach.
        Returns ``(sanitized_module_name, explicit_path_or_None, is_test)``
        per target; the caller resolves ``explicit_path`` (or the
        ``Sources/<name>`` / ``Tests/<name>`` default when ``None``) against
        the manifest's own directory. A call missing a ``name:`` literal (a
        computed name — never a guess) is skipped."""
        calls = self.spec.manifest_target_calls
        if not calls or self.spec.manifest_filename is None:
            return []
        analyzer = self._get_analyzer(file_path)
        if analyzer is None:
            return []
        # Only `.target(...)` calls that are DIRECT elements of the
        # `Package(targets: [...])` array are declarations; a `.target(name:)`
        # nested inside a `dependencies:` array is a reference to another
        # target, not a declaration of one, and must not be indexed (it has no
        # sources of its own). Scoping to the targets array's direct children
        # excludes those references structurally.
        results: List[Tuple[str, Optional[str], bool]] = []
        for pkg_call in analyzer._find_nodes_by_type('call_expression'):
            if self._manifest_callee_name(pkg_call, analyzer) != 'Package':
                continue
            targets_arr = self._manifest_labeled_array(pkg_call, analyzer, 'targets')
            if targets_arr is None:
                continue
            for node in _children(targets_arr):
                if node.kind() != 'call_expression':
                    continue
                callee = self._manifest_callee_name(node, analyzer)
                if callee not in calls:
                    continue
                name = self._manifest_string_arg(node, analyzer, 'name')
                if not name:
                    continue  # computed target name — honest skip, never guessed
                path = self._manifest_string_arg(node, analyzer, 'path')
                results.append((self._sanitize_module_name(name), path, callee == 'testTarget'))
        if results:
            return results
        # BACK-669 (swift-collections second corpus): `Package(targets:)`
        # wasn't a literal array to walk — some real Package.swift files
        # build the targets list programmatically (a small helper struct
        # plus `.map { $0.toTarget() }`) so `targets_arr` above is never
        # found. Fall back to a position-independent scan for any call
        # matching `manifest_target_calls` that carries both a literal
        # `name:` and a literal native `path:` — the same declaration-vs-
        # reference safety `_manifest_labeled_array` gets structurally
        # above (a `.target(name:)` *reference* inside a `dependencies:`
        # array never also carries a `path:`). Deliberately does NOT treat
        # a custom builder's own differently-named relocation argument
        # (e.g. swift-collections' `directory:`) as equivalent to `path:`:
        # a custom argument name commonly holds only a directory *segment*
        # later joined with a Sources/Tests root by more custom code (as
        # swift-collections' own `kind.path(for: directory)` does), not a
        # ready-to-use relative path the way PackageDescription's real
        # `path:` always is — treating it as one would silently resolve to
        # the wrong directory (see `extract_manifest_target_names` for how
        # this same case is instead surfaced as an honest reduced-
        # confidence signal rather than guessed at here).
        for node in analyzer._find_nodes_by_type('call_expression'):
            callee = self._manifest_callee_name(node, analyzer)
            if callee not in calls:
                continue
            name = self._manifest_string_arg(node, analyzer, 'name')
            if not name:
                continue  # computed target name — honest skip, never guessed
            path = self._manifest_string_arg(node, analyzer, 'path')
            if not path:
                continue  # no literal native path claim — honest skip
            results.append((self._sanitize_module_name(name), path, callee == 'testTarget'))
        return results

    def extract_manifest_target_names(self, file_path: Path) -> Set[str]:
        """Every declared target NAME anywhere in a build manifest (BACK-669
        Swift second-corpus finding, ``swift-collections``), independent of
        whether the call is a direct child of ``Package(targets: [...])``.

        :meth:`extract_manifest_targets` requires that literal-array
        position to safely resolve a target's real source directory — an
        explicit ``path:`` claim needs structural certainty about *where*
        the declaration sits, since a ``.target(name:)`` reference inside a
        ``dependencies:`` array must never be mistaken for a declaration of
        that target's sources. This method drops that positional
        requirement for a narrower purpose: some real Package.swift files
        build the ``targets:`` array *programmatically* (a small helper
        struct plus ``.map { $0.toTarget() }``, ``swift-collections``'s
        shape) rather than as a literal array, which makes
        ``extract_manifest_targets`` correctly return ``[]`` for
        resolution — but that same emptiness starves
        :meth:`is_intra_project_import`'s honest-decline check of the only
        signal it has for "this SwiftPM target is real but reveal couldn't
        resolve its files" versus "this import doesn't name an in-tree
        module at all" (the pre-fix behavior: a target whose on-disk
        directory name doesn't match its sanitized module identifier, e.g.
        target ``_RopeModule`` declared with ``directory: "RopeModule"``,
        silently produced neither a resolved edge NOR a reduced-confidence
        warning). A call matching ``spec.manifest_target_calls`` with a
        literal ``name:`` argument is safe to harvest into a NAME-ONLY
        existence set even out of position: unlike a ``path:`` claim, there
        is no over-counting risk from a same-shaped *reference*, because a
        ``.target(name: "Foo")`` naming another target inside a
        ``dependencies:`` array names a target that is, definitionally,
        also real and in-tree. Never used for file-membership fan-out
        (:meth:`resolve_module_targets`) — only to widen
        ``project_namespaces`` so an unresolvable-but-real import is
        flagged, not silently dropped."""
        calls = self.spec.manifest_target_calls
        if not calls or self.spec.manifest_filename is None:
            return set()
        analyzer = self._get_analyzer(file_path)
        if analyzer is None:
            return set()
        names: Set[str] = set()
        for node in analyzer._find_nodes_by_type('call_expression'):
            callee = self._manifest_callee_name(node, analyzer)
            if callee not in calls:
                continue
            name = self._manifest_string_arg(node, analyzer, 'name')
            if name:
                names.add(self._sanitize_module_name(name))
        return names

    @classmethod
    def _manifest_labeled_array(cls, call_node, analyzer, label: str):
        """The ``array_literal`` node of the ``label:`` argument in a call
        (``Package(targets: [...])`` → the targets array), or None."""
        suffix = cls._first_child_of_kind(call_node, 'call_suffix')
        args_parent = cls._first_child_of_kind(suffix, 'value_arguments') if suffix else None
        if args_parent is None:
            return None
        for arg in _children(args_parent):
            if arg.kind() != 'value_argument':
                continue
            arg_label = cls._first_child_of_kind(arg, 'value_argument_label')
            if arg_label is not None and analyzer._get_node_text(arg_label) == label:
                return cls._first_child_of_kind(arg, 'array_literal')
        return None

    @classmethod
    def _manifest_callee_name(cls, call_node, analyzer) -> Optional[str]:
        """The trailing identifier of a call's callee — ``target`` from a
        ``.target(...)`` prefix expression. Scans only the callee subtree (the
        children *before* the ``call_suffix`` argument list, so argument labels
        like ``name:``/``path:`` are never mistaken for it) and returns its last
        ``simple_identifier``, so both ``.target`` and a bare ``target``
        resolve. None when no such identifier exists (a computed callee)."""
        for child in _children(call_node):
            if child.kind() == 'call_suffix':
                break
            leaf = cls._last_identifier(child, analyzer)
            if leaf is not None:
                return leaf
        return None

    @classmethod
    def _last_identifier(cls, node, analyzer) -> Optional[str]:
        """Deepest-last ``simple_identifier`` text under ``node`` (its callee
        name for a dotted ``.a.b.target`` prefix), or None."""
        found: Optional[str] = None
        if node.kind() == 'simple_identifier':
            found = analyzer._get_node_text(node)
        for child in _children(node):
            leaf = cls._last_identifier(child, analyzer)
            if leaf is not None:
                found = leaf
        return found

    @classmethod
    def _manifest_string_arg(cls, call_node, analyzer, label: str) -> Optional[str]:
        """The string-literal value of the ``label:`` argument in a call, or
        None when absent or non-literal (a computed path — honest skip)."""
        suffix = cls._first_child_of_kind(call_node, 'call_suffix')
        args_parent = cls._first_child_of_kind(suffix, 'value_arguments') if suffix else None
        if args_parent is None:
            return None
        for arg in _children(args_parent):
            if arg.kind() != 'value_argument':
                continue
            arg_label = cls._first_child_of_kind(arg, 'value_argument_label')
            if arg_label is None or analyzer._get_node_text(arg_label) != label:
                continue
            literal = cls._first_child_of_kind(arg, 'line_string_literal')
            if literal is None:
                return None
            text = cls._first_child_of_kind(literal, 'line_str_text')
            return analyzer._get_node_text(text) if text is not None else ''
        return None

    def extract_top_level_members(self, file_path: Path) -> List[str]:
        """Names of top-level (file-scope, not class-scope) function/property
        declarations in this file — Kotlin's free-function idiom.

        BACK-547 Kotlin measurement loop: ``import a.b.foo`` where ``foo`` is
        a top-level ``fun``/``val``/``var`` has no enclosing class anywhere in
        the import string, so the file that declares it can only be found by
        scanning file *contents*, not by any transformation of the import
        path. This feeds the ``(package, symbol) -> [files]`` index
        :meth:`resolve_member_targets` looks up, paired with
        :meth:`extract_namespaces` for the declaring package.

        No-op (``[]``) unless ``spec.member_node_types`` is set. A node only
        counts when its immediate parent is ``source_file`` — the same node
        kinds (``function_declaration``, ``property_declaration``) also match
        methods/properties nested in a ``class_body``/``object_declaration``,
        which are reached via their class name, not a bare import, and must
        not pollute the top-level index.
        """
        if not self.spec.member_node_types:
            return []
        analyzer = self._get_analyzer(file_path)
        if analyzer is None:
            return []
        names: List[str] = []
        for node_type in self.spec.member_node_types:
            for node in analyzer._find_nodes_by_type(node_type):
                parent = node.parent()
                if parent is None or parent.kind() != 'source_file':
                    continue
                name = self._top_level_member_name(node, analyzer)
                if name:
                    names.append(name)
        return names

    @staticmethod
    def _top_level_member_name(node, analyzer) -> Optional[str]:
        """The declared symbol name for a top-level function/property node.

        A plain ``fun foo()`` (or ``fun <T> foo()``) exposes ``foo`` as a
        direct ``simple_identifier`` child. An extension function
        (``fun Receiver.foo()``) exposes the *same* shape — the receiver type
        is its own ``receiver_type``/``.`` children, never a
        ``simple_identifier`` — so "first direct ``simple_identifier`` child"
        is correct for both. A property (``val``/``var``) nests its name one
        level deeper, inside a ``variable_declaration`` child (Kotlin's
        grammar: ``val Receiver.name: Type`` → ``variable_declaration`` wraps
        ``name: Type``), so that child is checked first when present.
        """
        for child in _children(node):
            if child.kind() == 'variable_declaration':
                for grandchild in _children(child):
                    if grandchild.kind() == 'simple_identifier':
                        return analyzer._get_node_text(grandchild)
                return None
        for child in _children(node):
            if child.kind() == 'simple_identifier':
                return analyzer._get_node_text(child)
        return None

    def extract_container_members(self, file_path: Path) -> List[Tuple[str, str]]:
        """``(containerName, memberName)`` pairs for members of a top-level
        *named container* this language allows to be imported by a member
        path even though the container itself isn't reached by
        :meth:`_resolve_dotted`'s ``nested_member_fallback`` peel — Scala's
        ``object helpers`` idiom (BACK-557 GitBucket measurement loop).

        BACK-551's peel already resolves ``import a.b.Directory.getX`` (a
        PascalCase container, e.g. ``object Directory``) to ``Directory.scala``
        by treating the trailing component as "looks like a type" and
        matching it as a file. It deliberately refuses to peel to a
        lowerCamelCase trailing component (``helpers``) because, by name
        alone, that's indistinguishable from a package segment — peeling
        there could fabricate an edge to an unrelated same-named file. The
        only safe way to confirm ``helpers`` is a *real declared container*
        (not a filename coincidence) is to verify it structurally: scan for
        a top-level container node (``object_definition``) whose own name is
        ``helpers``, and pair it with each member the import might actually
        reach. This is the same content-scan discipline BACK-555's
        :meth:`extract_top_level_members` uses for Kotlin's free functions,
        one container level deeper.

        No-op (``[]``) unless ``spec.member_container_node_types`` and
        ``spec.container_member_node_types`` are both set. A container only
        counts when its immediate parent is the tree's root node (genuinely
        top-level, not a nested object) — detected as "parent has no parent
        of its own", not a hardcoded root ``kind()`` string, since that
        differs by grammar (Kotlin's tree-sitter grammar roots at
        ``source_file``; Scala's roots at ``compilation_unit``) and
        tree-sitter node equality (``==``) is unreliable across separately
        obtained wrapper objects even for the same underlying node. A member
        only counts when it is a direct child of the container's body
        wrapper (Scala ``template_body``) — a method declared on a *class
        nested inside* the object must not be indexed here (it has its own,
        deeper import path this index does not model).
        """
        if not self.spec.member_container_node_types or not self.spec.container_member_node_types:
            return []
        analyzer = self._get_analyzer(file_path)
        if analyzer is None:
            return []
        pairs: List[Tuple[str, str]] = []
        for container_type in self.spec.member_container_node_types:
            for container in analyzer._find_nodes_by_type(container_type):
                parent = container.parent()
                if parent is None or parent.parent() is not None:
                    continue
                container_name = self._direct_identifier_name(container, analyzer)
                if not container_name:
                    continue
                body = self._container_body(container)
                if body is None:
                    continue
                for member in _children(body):
                    if member.kind() not in self.spec.container_member_node_types:
                        continue
                    member_name = self._direct_identifier_name(member, analyzer)
                    if member_name:
                        pairs.append((container_name, member_name))
        return pairs

    _IDENTIFIER_KINDS: ClassVar[FrozenSet[str]] = frozenset({'identifier', 'simple_identifier'})

    @classmethod
    def _direct_identifier_name(cls, node, analyzer) -> Optional[str]:
        """First direct child whose kind is a plain identifier — the declared
        name for a Scala ``object``/``def``/``val`` node, all of which expose
        their name as a direct child (unlike Kotlin's nested property shape,
        see :meth:`_top_level_member_name`)."""
        for child in _children(node):
            if child.kind() in cls._IDENTIFIER_KINDS:
                return analyzer._get_node_text(child)
        return None

    @staticmethod
    def _container_body(node):
        """The child node holding a container's member declarations — Scala
        wraps an ``object_definition``'s members in a ``template_body``
        (``{ ... }``), one level below the ``extends``/name children."""
        for child in _children(node):
            if child.kind() == 'template_body':
                return child
        return None

    def extract_namespaced_type_names(self, file_path: Path) -> List[str]:
        """Names of genuinely top-level ``class``/``interface``/``struct``/
        ``record``/``enum`` declarations in this file — C#'s
        ``namespaced_type_fallback`` idiom (BACK-669 C# recall loop).

        Paired by the caller with :meth:`extract_namespaces` into the same
        ``member_index[(namespace, type_name)] -> [files]`` shape Kotlin's
        free-function fallback already populates, so ``using static
        Foo.Bar.Type;`` / ``using Alias = Foo.Bar.Type;`` resolve via
        :meth:`resolve_member_targets` with no new index or resolution
        method needed.

        No-op (``[]``) unless ``spec.namespaced_type_node_types`` is set. A
        node only counts when it is genuinely top-level: its parent is the
        ``compilation_unit`` (C# 10 file-scoped ``namespace X.Y;``) or a
        ``declaration_list`` whose own parent is a
        ``namespace_declaration``/``file_scoped_namespace_declaration``
        (classic block-scoped ``namespace X.Y { ... }``) — never a type
        nested inside another type's body, which names a *member of* the
        enclosing type (``Outer.Inner``), a distinct and unimplemented idiom
        this fallback does not model (same scope boundary Java's
        ``nested_member_fallback`` draws, which C# doesn't opt into).
        """
        if not self.spec.namespaced_type_node_types:
            return []
        analyzer = self._get_analyzer(file_path)
        if analyzer is None:
            return []
        names: List[str] = []
        for node_type in self.spec.namespaced_type_node_types:
            for node in analyzer._find_nodes_by_type(node_type):
                if not self._is_top_level_namespaced_type(node):
                    continue
                name = self._direct_identifier_name(node, analyzer)
                if name:
                    names.append(name)
        return names

    _NAMESPACE_BODY_KINDS: ClassVar[FrozenSet[str]] = frozenset({
        'namespace_declaration', 'file_scoped_namespace_declaration',
    })

    @classmethod
    def _is_top_level_namespaced_type(cls, node) -> bool:
        """True when *node* (a type declaration) sits directly under the
        compilation unit or a namespace body — not nested inside another
        type's own body. See :meth:`extract_namespaced_type_names`."""
        parent = node.parent()
        if parent is None:
            return False
        if _zero_arg(parent, 'kind') == 'compilation_unit':
            return True
        if _zero_arg(parent, 'kind') == 'declaration_list':
            grandparent = parent.parent()
            return grandparent is not None and _zero_arg(grandparent, 'kind') in cls._NAMESPACE_BODY_KINDS
        return False

    def resolve_member_targets(
        self,
        stmt: ImportStatement,
        member_index: Dict[Tuple[str, str], List[Path]],
    ) -> List[Path]:
        """Every in-tree file declaring the top-level symbol ``stmt`` imports.

        Last-resort fallback for Kotlin's free-function/property import idiom
        (BACK-547 measurement loop), Scala's lowerCamelCase-container member
        idiom (BACK-557), *and* C#'s ``using static``/type-alias idiom
        (BACK-669) — all three populate the same ``(package, symbol)`` shaped
        index (Scala's ``package`` component is synthesized as
        ``declared_package + separator + containerName`` by the caller, and
        C#'s ``symbol`` is a type name rather than a function/property, but
        the lookup shape is identical either way). Splits ``stmt.module_name``
        into ``(package, symbol)`` on ``spec.module_separator`` and looks up
        the content-scanned index built from :meth:`extract_top_level_members`
        / :meth:`extract_container_members` / :meth:`extract_namespaced_type_names`
        + :meth:`extract_namespaces`. Fans out to every declaring file the
        same way :meth:`resolve_namespace_targets` does — a same-named
        top-level overload/type can legitimately be declared in more than one
        file (e.g. one ``asImageModel`` extension per receiver type in a
        shared package, or a same-named DTO/entity pair in two namespaces),
        and without type inference there is no principled way to pick one, so
        this reports all of them rather than guessing or skipping. Honest-skip
        contract holds: an unindexed ``(package, symbol)`` returns ``[]``.
        """
        if not (
            self.spec.member_symbol_fallback
            or self.spec.container_member_fallback
            or self.spec.namespaced_type_fallback
        ):
            return []
        sep = self.spec.module_separator
        module = stmt.module_name
        if not sep or not module or sep not in module:
            return []
        parts = [p for p in module.split(sep) if p]
        if len(parts) < 2:
            return []
        symbol = parts[-1]
        package = sep.join(parts[:-1])
        return list(member_index.get((package, symbol), ()))

    _CONSTANT_KINDS: ClassVar[FrozenSet[str]] = frozenset({'constant', 'scope_resolution'})

    def extract_constant_references(self, file_path: Path) -> List[Tuple[int, str]]:
        """``(line_number, dotted_constant_path)`` for every bare-constant
        reference in this file's body — Ruby's Zeitwerk idiom (BACK-557
        direction a). ``Topic.find(1)`` and ``User::Anonymizer.new`` reference
        other in-tree classes with **no** ``require``/``require_relative``
        statement anywhere; Zeitwerk resolves them lazily by a file-path
        naming convention instead (:meth:`extract_imports` structurally
        cannot see these — there is no import node to find). This walks the
        whole tree collecting every ``constant``/``scope_resolution`` node,
        so the caller can look each dotted path up against a path→constant
        index built from the tree's own file layout and add an edge when it
        matches an in-tree file.

        Only the *outermost* node of a chain is kept — ``Foo::Bar::Baz`` is
        one ``scope_resolution`` nesting two more; descending into its
        children would also emit ``Foo::Bar`` and ``Bar``/``Baz`` fragments
        that don't name the actual referenced constant. A reference to the
        file's own declared class/module name resolves back to this same
        file and is filtered out by the caller (``resolved == file_path``),
        so no separate declaration-vs-usage distinction is needed here.

        No-op (``[]``) unless ``spec.zeitwerk_convention`` is set — every
        other language returns immediately, no extra parse pass incurred.
        """
        if not self.spec.zeitwerk_convention:
            return []
        analyzer = self._get_analyzer(file_path)
        if analyzer is None:
            return []
        refs: List[Tuple[int, str]] = []

        def walk(node) -> None:
            kind = node.kind()
            if kind in self._CONSTANT_KINDS:
                parent = node.parent()
                if parent is not None and parent.kind() in self._CONSTANT_KINDS:
                    return  # nested fragment of an already-captured outer chain
                text = analyzer._get_node_text(node)
                if text:
                    # BACK-669 solidus second-corpus loop: a leading `::` forces
                    # absolute (top-level) constant lookup — Ruby's disambiguator
                    # for exactly the shape a namespaced Rails Engine needs it for
                    # (`::Spree::Order` inside `module Spree` code that would
                    # otherwise risk resolving a bare `Order` to some *other*
                    # nested constant). It doesn't change *which* constant is
                    # named, only how it's looked up, so strip it before matching
                    # — zeitwerk_index keys are never prefixed with `::` (built
                    # from path segments, not source text), and without this the
                    # exact-match lookup silently misses every absolute reference.
                    refs.append((node.start_position().row + 1, text.removeprefix('::')))
                return  # don't descend into a captured chain's own fragments
            for child in _children(node):
                walk(child)

        walk(tree_root(analyzer.tree))
        return refs

    # --- internals -------------------------------------------------------

    @staticmethod
    def _get_analyzer(file_path: Path):
        """Instantiate the tree-sitter analyzer for a file, or None on failure."""
        try:
            analyzer_class = get_analyzer(str(file_path))
            if not analyzer_class:
                return None
            analyzer = analyzer_class(str(file_path))
            if not analyzer.tree:
                return None
            return analyzer
        except Exception as e:  # pragma: no cover - defensive
            logger.debug("generic import analyzer failed for %s: %s", file_path, e)
            return None

    def _node_to_import(
        self, node, analyzer, file_path: Path,
        constant_index: Optional[Dict[str, Tuple[str, str]]] = None,
    ) -> Optional[ImportStatement]:
        """Turn a dedicated import-statement node into an ImportStatement."""
        if _zero_arg(node, 'kind') == 'preproc_call':
            # BACK-676: a #include nested inside a class/struct body (e.g.
            # Godot's bvh_tree.h .inc fragment-include idiom) isn't valid
            # top-level-only preproc_include grammar, so tree-sitter's C/C++
            # grammars degrade it to the generic preproc_call fallback node
            # -- the same node shape used for #pragma/#undef/etc inside a
            # body. Only the '#include' directive is an import.
            directive = node.child(0)
            if (
                directive is None
                or _zero_arg(directive, 'kind') != 'preproc_directive'
                or analyzer._get_node_text(directive).strip() != '#include'
            ):
                return None
        if node.kind() in self.spec.concat_relative_node_types:
            result = self._concat_to_import(node, analyzer, file_path, constant_index)
            if result is not _NOT_CONCAT:
                return result
        raw = analyzer._get_node_text(node)
        return self._build(raw, node, file_path)

    # BACK-564: PHP require/include targets built by string concatenation
    # (`__DIR__ . '/x.php'`) are the dominant real-world idiom (0/387 WordPress
    # core edges use a bare literal) and the text-based `_build` path below
    # cannot parse them — it only strips characters off the ends of the whole
    # remainder string, leaving operator/constant text embedded in
    # `module_name`. These three helpers walk the AST structurally instead,
    # the same approach `_call_to_import` already uses for Ruby/Lua.

    _DIR_RELATIVE_NAME: ClassVar[str] = '__DIR__'
    _DIRNAME_CALLEE: ClassVar[str] = 'dirname'
    _FILE_CONST_NAME: ClassVar[str] = '__FILE__'

    def _concat_to_import(
        self, node, analyzer, file_path: Path,
        constant_index: Optional[Dict[str, Tuple[str, str]]] = None,
    ):
        """Structural extraction for a require/include node whose target is a
        concatenation expression (``binary_expression`` chained on ``.``).

        Returns:
          * an :class:`ImportStatement` when the concatenation resolves —
            either BACK-564's single-operand ``__DIR__``/``dirname(__FILE__)``
            idiom (``module_name`` is the trailing fragment, ``is_relative=
            True``, resolved file-relative exactly as before), or BACK-565's
            constant-substitution chain (``module_name`` is the fully
            resolved absolute path, ``is_relative=False`` — see
            :meth:`_resolve_concat_operand`).
          * ``None`` (honest skip, never a fabricated edge) when neither
            shape applies — an unknown/ambiguous framework constant, a
            variable, or any shape this doesn't recognize.
          * the module-level ``_NOT_CONCAT`` sentinel when the node's target
            is some other shape this method doesn't recognize at all (should
            not occur for well-formed PHP require/include — a defensive
            fallback to the old text-based ``_build`` path, not a designed
            case).

        BACK-680 (second-corpus overfit guard, osCommerce): a bare string
        literal target written PHP's call-style way — ``require('includes/
        foo.php');`` (the dominant real-world form: 534/544 of this corpus's
        require/include statements use parens, vs. only 10/1,521 in
        WordPress's oracle corpus) — was, before this fix, left for the
        caller's ``_NOT_CONCAT`` fallback to ``_build()``, whose keyword-
        stripping tokenizer splits the raw statement text on spaces
        (``text.split(' ')``) and pops leading tokens matching
        ``self.spec.keywords`` exactly. ``require('includes/foo.php')`` has
        no space between the ``require`` keyword and its opening paren, so
        the *entire* raw text is one token — it never equals the bare
        keyword ``'require'``, the strip loop does nothing, and
        ``module_name`` ends up as the literal garbage string
        ``"require('includes/foo.php')"``. That string still contains a
        ``/`` (from the real path inside it), so ``_looks_like_path``
        (checked later in ``_resolve_module``) still says yes and a real
        resolution is attempted — against the garbage text, which of course
        never matches a real file. **Zero edges for every parenthesized
        bare-literal require/include in the corpus, never a wrong edge, just
        silently nothing** — the same "detects the node, mis-derives what's
        inside it" failure shape BACK-564 already found for concatenation
        targets, one syntactic form later. WordPress's own oracle corpus is
        both near-parenthesis-free AND has zero bare-literal statements, so
        neither the paren-unwrapping gap nor this one ever surfaced there;
        osCommerce's parenthesized-bare-literal idiom hits both at once.
        Fixed here by handling the bare-``string`` target explicitly and
        structurally — the same AST-walk approach the concatenation idioms
        above already use — instead of ever routing a require/include target
        through ``_build()``'s text tokenizer.

        Also unwraps a ``parenthesized_expression`` wrapper before dispatch
        (tree-sitter nests a parenthesized target one level deeper than the
        unparenthesized ``require EXPR;`` form): before this fix,
        ``_first_child_of_kind(node, 'binary_expression')`` only ever checked
        *direct* children of the require/include node, so a parenthesized
        concatenation target (``require(OSCOM_BASE_DIR . 'x.php');``) also
        silently missed the concat idiom above and fell through to the same
        broken tokenizer path.
        """
        target = self._require_target_node(node)
        if target is None:
            return _NOT_CONCAT

        if _zero_arg(target, 'kind') == 'string':
            # Bare string literal — PHP's `require`/`include` semantics
            # resolve an unqualified relative path against the importing
            # file's own directory (never a project root), same as Ruby's
            # `require_relative` — hence `is_relative=True` unconditionally,
            # not gated on a leading `.` the way `_build()`'s generic path
            # requires.
            content = self._first_descendant_text(target, analyzer, ('string_content',))
            if not content:
                return None
            module_name = content.lstrip('/')
            if not module_name:
                return None
            return ImportStatement(
                file_path=file_path,
                line_number=node.start_position().row + 1,
                module_name=module_name,
                imported_names=[],
                is_relative=True,
                import_type='include',
                alias=None,
                source_line=analyzer._get_node_text(node).strip(),
                skip_unused=True,
            )

        if _zero_arg(target, 'kind') != 'binary_expression':
            # A variable (`$file`), a method/static call
            # (`$tpl->getFile(...)`, `OSCOM::getConfig(...)`), or anything
            # else this doesn't recognize — genuinely dynamic or unknown.
            # Honest skip: never fabricate an edge for it.
            return None

        concat = target

        # BACK-564 idiom, tried first and unchanged: a single-operand
        # `__DIR__ . 'x.php'` / `dirname( __FILE__ ) . 'x.php'` concatenation
        # resolves file-relative via the same machinery as Ruby's
        # `require_relative`. Checked structurally exactly as before this
        # session so this path's output (module_name/is_relative) is
        # byte-identical for every case it already handled.
        fragment = self._trailing_string_fragment(concat, analyzer)
        leading = self._leading_operand(concat)
        if fragment is not None and leading is not None and self._is_dir_relative_operand(leading, analyzer):
            module_name = fragment.lstrip('/')
            if not module_name:
                return None
            return ImportStatement(
                file_path=file_path,
                line_number=node.start_position().row + 1,
                module_name=module_name,
                imported_names=[],
                is_relative=True,
                import_type='include',
                alias=None,
                source_line=analyzer._get_node_text(node).strip(),
                skip_unused=True,
            )

        # BACK-565: not the single-operand idiom above (e.g. a 3-operand
        # `ABSPATH . WPINC . '/version.php'` chain, whose leading operand is
        # itself a nested `binary_expression`) — try resolving the whole
        # chain against `constant_index`, substituting any operand that
        # names a project constant proven to have exactly one absolute
        # value. Still never a guess: any operand that doesn't reduce to a
        # literal, the magic-constant idiom, or an indexed constant fails
        # the whole statement.
        resolved = self._resolve_concat_operand(concat, analyzer, file_path, constant_index or {})
        if resolved is None:
            return None
        anchor, tail = resolved
        if anchor is None:
            # Every operand in the chain reduced to plain text with no
            # absolute anchor anywhere (e.g. two unrecognized/ambiguous
            # constants) — nothing to resolve a file against, and this is a
            # different idiom than the file-relative one above, so don't
            # guess base_path here either.
            return None
        remainder = tail.lstrip('/')
        if not remainder:
            return None
        module_name = str(anchor / remainder)

        return ImportStatement(
            file_path=file_path,
            line_number=node.start_position().row + 1,
            module_name=module_name,
            imported_names=[],
            is_relative=False,
            import_type='include',
            alias=None,
            source_line=analyzer._get_node_text(node).strip(),
            skip_unused=True,
        )

    @staticmethod
    def _first_child_of_kind(node, kind: str):
        """First direct child of ``node`` whose kind is exactly ``kind``."""
        for child in _children(node):
            if child.kind() == kind:
                return child
        return None

    _REQUIRE_KEYWORD_KINDS: ClassVar[FrozenSet[str]] = frozenset({
        'require', 'require_once', 'include', 'include_once',
    })

    @classmethod
    def _require_target_node(cls, node):
        """The actual target expression of a require/include node — the
        first non-keyword child, unwrapping one ``parenthesized_expression``
        wrapper (PHP's ``require(EXPR);`` call-style, tree-sitter nests the
        real target one level deeper than the unparenthesized ``require
        EXPR;`` form). Returns ``None`` only for a malformed/unrecognized
        node shape (no non-keyword child, or an empty parenthesized
        expression) — the caller treats that as "don't know", not "dynamic".
        """
        for child in _children(node):
            if _zero_arg(child, 'kind') in cls._REQUIRE_KEYWORD_KINDS:
                continue
            if _zero_arg(child, 'kind') == 'parenthesized_expression':
                inner = [c for c in _children(child) if _zero_arg(c, 'kind') not in ('(', ')')]
                return inner[0] if inner else None
            return child
        return None

    @staticmethod
    def _trailing_string_fragment(binary_expr, analyzer) -> Optional[str]:
        """The rightmost operand of a (possibly chained) ``.`` concatenation,
        if it is a plain string literal — the last-appended path fragment in
        e.g. ``ABSPATH . WPINC . '/version.php'`` (the trailing ``string``
        node, tree-sitter's PHP grammar being left-associative so the
        outermost ``binary_expression``'s direct children are the *last*
        two operands). Returns ``None`` if the rightmost operand isn't a bare
        string (a variable, a call, ...).
        """
        children = _children(binary_expr)
        if not children:
            return None
        last = children[-1]
        if last.kind() != 'string':
            return None
        content = _GenericTreeSitterImportExtractor._first_descendant_text(
            last, analyzer, ('string_content',)
        )
        return content

    @staticmethod
    def _leading_operand(binary_expr):
        """The operand left of the final ``.`` in a concatenation chain — for
        ``__DIR__ . '/x.php'`` that's the ``__DIR__`` name node; for
        ``ABSPATH . WPINC . '/version.php'`` that's the nested
        ``binary_expression`` for ``ABSPATH . WPINC`` (deliberately NOT
        unwrapped further — a multi-segment leading chain never reduces to
        the single-operand ``__DIR__``/``dirname(__FILE__)`` idiom, so
        :meth:`_is_dir_relative_operand` correctly rejects it as-is).
        """
        children = _children(binary_expr)
        if len(children) < 2:
            return None
        return children[0]

    @classmethod
    def _is_dir_relative_operand(cls, operand, analyzer) -> bool:
        """True when ``operand`` is PHP's directory-relative magic-constant
        idiom: the bare ``__DIR__`` constant, or a ``dirname( __FILE__ )``
        call. Anything else (a framework constant like ``ABSPATH``, a
        variable, a nested concatenation) returns False — the caller treats
        that as an honest skip, not a guess.
        """
        kind = operand.kind()
        if kind == 'name':
            return analyzer._get_node_text(operand).strip() == cls._DIR_RELATIVE_NAME
        if kind == 'function_call_expression':
            callee = cls._first_child_of_kind(operand, 'name')
            if callee is None or analyzer._get_node_text(callee).strip() != cls._DIRNAME_CALLEE:
                return False
            args = cls._first_child_of_kind(operand, 'arguments')
            if args is None:
                return False
            arg_text = cls._first_descendant_text(args, analyzer, ('name',))
            return arg_text is not None and arg_text.strip() == cls._FILE_CONST_NAME
        return False

    # BACK-565: PHP framework-constant substitution (`ABSPATH`, `WPINC`, ...).
    # WordPress's own corpus defines these via `define()` at each bootstrap
    # file's top level, anchored at *that file's own location* — never a
    # single universal value guessed from the constant name. These three
    # helpers build (extract_constant_defines) and consume
    # (_resolve_concat_operand/_resolve_leaf_operand) a project-wide index of
    # such constants, reusing _leading_operand/_trailing_string_fragment's
    # single-level shape one level deeper for arbitrary-length chains.

    @classmethod
    def _operand_anchor(cls, operand, analyzer, file_path: Path) -> Optional[Path]:
        """The absolute directory PHP's ``__DIR__``/``dirname(__FILE__)``/
        ``dirname(__DIR__)`` magic-constant idiom names when used as a
        concatenation operand, anchored at ``file_path``'s own location —
        ``None`` when ``operand`` isn't one of these shapes (a framework
        constant, a variable, or anything else :meth:`_resolve_leaf_operand`
        must instead try against the constant index).

        ``dirname(__DIR__)`` (one directory above the current file, real
        WordPress idiom: ``wp-admin/load-scripts.php`` defines ``ABSPATH``
        this way) is new relative to :meth:`_is_dir_relative_operand`, which
        only ever needed the single-level ``__DIR__``/``dirname(__FILE__)``
        case for a *require target* directly. Both are equally derivable
        from the file's own path — no guessing involved — so recognizing it
        here is a strict widening, never a fabrication risk.

        Also handles PHP's ``dirname($path, $levels)`` two-argument form
        (real WordPress idiom: ``wp-admin/maint/repair.php`` requires
        ``dirname( __DIR__, 2 ) . '/wp-load.php'``) — ``$levels`` is a
        literal integer applying ``dirname()`` that many times, so it's
        exactly as derivable as the single-level form, just walking that
        many extra parents.
        """
        kind = operand.kind()
        if kind == 'name':
            if analyzer._get_node_text(operand).strip() == cls._DIR_RELATIVE_NAME:
                return file_path.parent
            return None
        if kind == 'function_call_expression':
            callee = cls._first_child_of_kind(operand, 'name')
            if callee is None or analyzer._get_node_text(callee).strip() != cls._DIRNAME_CALLEE:
                return None
            args = cls._first_child_of_kind(operand, 'arguments')
            if args is None:
                return None
            arg_nodes = [c for c in _children(args) if c.kind() == 'argument']
            if not arg_nodes:
                return None
            arg_text = cls._first_descendant_text(arg_nodes[0], analyzer, ('name',))
            if arg_text is None:
                return None
            arg_text = arg_text.strip()
            if arg_text == cls._FILE_CONST_NAME:
                base = file_path.parent
            elif arg_text == cls._DIR_RELATIVE_NAME:
                base = file_path.parent.parent
            else:
                return None
            levels = 1
            if len(arg_nodes) >= 2:
                levels_text = cls._first_descendant_text(arg_nodes[1], analyzer, ('integer',))
                if levels_text is None or not levels_text.strip().isdigit():
                    # A non-literal levels argument (a variable, an
                    # expression) can't be resolved without guessing.
                    return None
                levels = int(levels_text.strip())
                if levels < 1:
                    return None
            for _ in range(levels - 1):
                base = base.parent
            return base
        return None

    def _resolve_leaf_operand(
        self, node, analyzer, file_path: Path,
        known_constants: Dict[str, Tuple[str, str]],
    ) -> Optional[Tuple[Optional[Path], str]]:
        """Resolve a single (non-``.``-chained) concatenation operand.

        Returns ``(anchor, fragment)`` — ``anchor`` is the absolute
        directory the operand names (``__DIR__``-family idiom or an indexed
        ``('absolute', ...)`` constant), or ``None`` when the operand
        contributes only relative text (a bare string literal, or an
        indexed ``('literal', ...)`` constant). Returns ``None`` (not a
        tuple) when the operand can't be classified at all — a variable, an
        unrecognized call, or an identifier absent from (or ambiguous in,
        see :meth:`extract_constant_defines`) ``known_constants``: the
        caller must treat that as an honest skip of the whole statement.
        """
        kind = node.kind()
        if kind == 'string':
            content = self._first_descendant_text(node, analyzer, ('string_content',))
            if content is None:
                return None
            return (None, content)
        anchor = self._operand_anchor(node, analyzer, file_path)
        if anchor is not None:
            return (anchor, '')
        if kind == 'name':
            name = analyzer._get_node_text(node).strip()
            if name in (self._DIR_RELATIVE_NAME, self._FILE_CONST_NAME):
                # A bare __DIR__/__FILE__ that _operand_anchor already
                # rejected (e.g. bare __FILE__ names a whole file path, not
                # a directory) — not the idiom, and not a constant lookup
                # either.
                return None
            value = known_constants.get(name)
            if value is None:
                return None
            value_kind, value_data = value
            if value_kind == 'literal':
                return (None, value_data)
            return (Path(value_data), '')
        return None

    def _resolve_concat_operand(
        self, node, analyzer, file_path: Path,
        known_constants: Dict[str, Tuple[str, str]],
    ) -> Optional[Tuple[Optional[Path], str]]:
        """Resolve a (possibly chained) ``.`` concatenation expression to
        ``(anchor, fragment)`` by walking it structurally, substituting any
        operand found in ``known_constants``.

        ``anchor`` is ``None`` when nothing in the chain set an absolute
        base (pure literal/constant text — the caller decides what, if
        anything, to resolve that relative to); otherwise it's the single
        absolute directory the chain is anchored to. ``fragment`` is the
        concatenation of every operand's text, in order, with the anchor's
        own contribution folded to ``''`` (the anchor names a directory, not
        text to append). A second anchor appearing anywhere but the very
        start of the chain is a shape this doesn't model (which operand
        actually applies is ambiguous) — honest skip, ``None``.
        """
        kind = node.kind()
        if kind == 'string':
            return self._resolve_leaf_operand(node, analyzer, file_path, known_constants)
        if kind != 'binary_expression':
            return self._resolve_leaf_operand(node, analyzer, file_path, known_constants)
        children = _children(node)
        if len(children) < 2:
            return None
        left, right = children[0], children[-1]
        left_result = self._resolve_concat_operand(left, analyzer, file_path, known_constants)
        if left_result is None:
            return None
        anchor, fragment = left_result
        right_result = self._resolve_leaf_operand(right, analyzer, file_path, known_constants)
        if right_result is None:
            return None
        right_anchor, right_fragment = right_result
        if right_anchor is not None:
            if anchor is not None:
                # Two anchors in one chain (e.g. `ABSPATH . WP_CONTENT_DIR`)
                # — which one the resulting path is actually relative to is
                # ambiguous. Never guess.
                return None
            anchor = right_anchor
        return (anchor, fragment + right_fragment)

    @staticmethod
    def _first_argument_value(argument_node):
        """The real expression a PHP ``argument`` wrapper node holds — tree-
        sitter's grammar wraps each call argument in its own ``argument``
        node (e.g. ``define('X', __DIR__ . '/')``'s ``arguments`` node has
        two ``argument`` children, each with exactly one meaningful child:
        the ``string``/``binary_expression``/... the caller actually wants).
        """
        for child in _children(argument_node):
            return child
        return None

    def extract_constant_defines(
        self, file_path: Path,
        known_constants: Optional[Dict[str, Tuple[str, str]]] = None,
    ) -> List[Tuple[str, Tuple[str, str]]]:
        """``(name, ('literal', str) | ('absolute', str))`` pairs for every
        ``define('NAME', <expr>)`` call in this file (BACK-565), feeding the
        project-wide constant index :meth:`_resolve_concat_operand` looks up
        to resolve WordPress-style framework-constant require/include
        concatenations (``ABSPATH . WPINC . '/version.php'``).

        ``<expr>`` is classified the same way :meth:`_resolve_concat_operand`
        classifies any concatenation operand:
          * a bare string literal (``'wp-includes'``) → ``('literal', ...)``,
            a relative fragment anchored nowhere;
          * ``__DIR__``/``dirname(__FILE__)``/``dirname(__DIR__)``, alone or
            concatenated onto a literal tail → ``('absolute', ...)``,
            anchored at *this defining file's own location* (never a
            universal value guessed from the constant's name — the real
            corpus defines ``ABSPATH`` differently in different files, see
            BACK-565's backlog writeup);
          * a further constant reference already present in
            ``known_constants`` (real WordPress shape:
            ``WP_CONTENT_DIR = ABSPATH . 'wp-content'``,
            ``WP_PLUGIN_DIR = WP_CONTENT_DIR . '/plugins'``) → substituted
            and folded in, so the caller's fixed-point re-scan (constants
            are declared in file-walk order, not dependency order) converges
            on multi-level chains too.

        Anything else (a variable, a function call other than ``dirname``,
        a ternary, ...) is skipped for that one ``define()`` — no entry is
        produced, never a guessed one.

        No-op (``[]``) unless ``spec.constant_define_call_names`` is set —
        every language but PHP.
        """
        if not self.spec.constant_define_call_names:
            return []
        analyzer = self._get_analyzer(file_path)
        if analyzer is None:
            return []
        known = known_constants or {}
        results: List[Tuple[str, Tuple[str, str]]] = []
        for node in analyzer._find_nodes_by_type('function_call_expression'):
            callee = self._first_child_of_kind(node, 'name')
            if callee is None:
                continue
            if analyzer._get_node_text(callee).strip() not in self.spec.constant_define_call_names:
                continue
            args_node = self._first_child_of_kind(node, 'arguments')
            if args_node is None:
                continue
            arg_wrappers = [c for c in _children(args_node) if c.kind() == 'argument']
            if len(arg_wrappers) < 2:
                continue
            name_expr = self._first_argument_value(arg_wrappers[0])
            value_expr = self._first_argument_value(arg_wrappers[1])
            if name_expr is None or value_expr is None or name_expr.kind() != 'string':
                continue
            const_name = self._first_descendant_text(name_expr, analyzer, ('string_content',))
            if not const_name:
                continue
            resolved = self._resolve_concat_operand(value_expr, analyzer, file_path, known)
            if resolved is None:
                continue
            anchor, fragment = resolved
            if anchor is not None:
                value: Tuple[str, str] = ('absolute', str(anchor / fragment.lstrip('/')))
            else:
                if not fragment:
                    continue
                value = ('literal', fragment)
            results.append((const_name, value))
        return results

    def _call_to_import(self, node, analyzer, file_path: Path) -> Optional[ImportStatement]:
        """Turn a ``require``-style call node into an ImportStatement, if it is one.

        Reads the call structurally (callee identifier + string argument) so both
        ``require 'json'`` and ``require('json')`` are recognised, and nested
        calls like ``puts(require_relative 'x')`` are ignored unless they are the
        callee themselves.
        """
        callee = None
        for child in _children(node):
            if child.kind() == 'identifier':
                callee = analyzer._get_node_text(child)
                break
        if callee is None or callee not in self.spec.call_import_names:
            return None

        module = self._first_descendant_text(node, analyzer, ('string_content',))
        if not module:
            # Fall back to the whole string literal, minus quotes.
            literal = self._first_descendant_text(node, analyzer, ('string',))
            module = literal.strip('"\'') if literal else ''
        if not module:
            return None

        return ImportStatement(
            file_path=file_path,
            line_number=node.start_position().row + 1,
            module_name=module,
            imported_names=[],
            is_relative=module.startswith('.'),
            import_type='import',
            alias=None,
            source_line=analyzer._get_node_text(node).strip(),
            skip_unused=True,
        )

    @staticmethod
    def _first_descendant_text(node, analyzer, kinds) -> Optional[str]:
        """DFS pre-order: text of the first descendant whose kind is in *kinds*."""
        stack = list(reversed(_children(node)))
        while stack:
            cur = stack.pop()
            if cur.kind() in kinds:
                return analyzer._get_node_text(cur)
            stack.extend(reversed(_children(cur)))
        return None

    @staticmethod
    def _extract_include_target(remainder: str) -> Optional[str]:
        """Return the include target between the first `<..>` or `"..."` pair.

        Truncates at the first closing delimiter so a trailing comment
        (`<math.h> /* ... */`, `"x.h" // ...`) can't leak into the module name.
        Returns None if no delimited target is present (caller falls back).
        """
        for open_ch, close_ch in (('<', '>'), ('"', '"')):
            start = remainder.find(open_ch)
            if start == -1:
                continue
            end = remainder.find(close_ch, start + 1)
            if end != -1:
                return remainder[start + 1:end].strip()
        return None

    @staticmethod
    def _strip_after_quoted_literal(remainder: str) -> str:
        """Truncate at the closing quote of a leading quoted literal.

        Drops any trailing combinator clause (Dart's ``show Foo, hide Bar``/
        ``deferred as alias``) that the generic strip-chars-off-both-ends
        path in :meth:`_build` can't remove, since those characters sit at
        the *end* of the whole remainder, not adjacent to the quote. A
        remainder that doesn't start with a quote (or has no matching close)
        is returned unchanged — callers still fall back to the ordinary
        strip-chars path.
        """
        remainder = remainder.strip()
        if not remainder or remainder[0] not in ('"', "'"):
            return remainder
        quote = remainder[0]
        end = remainder.find(quote, 1)
        if end == -1:
            return remainder
        return remainder[:end + 1]

    def _build(self, raw: str, node, file_path: Path) -> Optional[ImportStatement]:
        """Parse cleaned source text into an ImportStatement (data-driven)."""
        source_line = raw.strip()
        # Collapse whitespace/newlines and drop a trailing ';'.
        text = ' '.join(source_line.split())
        if text.endswith(';'):
            text = text[:-1].rstrip()

        had_angle = '<' in text and '>' in text  # C system include marker

        # Strip leading keyword tokens (import / using / static / #include / ...).
        # BACK-669 (swift-collections second corpus): a language that allows
        # a declaration-level attribute before the import keyword itself
        # (Swift `@testable import Foo`, possibly stacked with `@_spi(...)`)
        # also strips any leading bare-`@` token, not just the fixed keyword
        # set — an attribute's argument varies, so it can never be listed in
        # `spec.keywords` as an exact string.
        tokens = text.split(' ')
        while tokens and (
            tokens[0] in self.spec.keywords
            or (self.spec.strip_attribute_prefix and tokens[0].startswith('@'))
        ):
            tokens.pop(0)
        remainder = ' '.join(tokens).strip()
        if not remainder:
            return None

        alias: Optional[str] = None

        # `Module as Alias` (Java/PHP/Python-style).
        if ' as ' in remainder:
            remainder, alias = (p.strip() for p in remainder.split(' as ', 1))
        # `Alias = Module` (C#/C++ using-alias).
        elif self.spec.alias_assignment and '=' in remainder:
            left, right = remainder.split('=', 1)
            alias = left.strip()
            remainder = right.strip()

        if self.spec.combinator_clause:
            remainder = self._strip_after_quoted_literal(remainder)

        # For a C/C++ include, extract exactly what's between the delimiters —
        # `<...>` for a system include or `"..."` for a local one — up to the
        # *first* closing delimiter. A blanket .strip() can't do this: it only
        # trims matching chars from the ends, so a trailing comment after the
        # close (e.g. Redis's `#include <math.h> /* isnan() */` or
        # `#include "x.h" // note`) leaves the interior delimiter and the comment
        # intact → module_name `math.h> /* isnan() */` (BACK-417).
        module_name = self._extract_include_target(remainder) if self.spec.resolve_includes else None
        if module_name is None:
            # Non-include (import/using) or a malformed include: strip surrounding
            # quotes (angle brackets too for includes) as before.
            strip_chars = '"\' '
            if self.spec.resolve_includes:
                strip_chars += '<>'
            module_name = remainder.strip(strip_chars)
        if not module_name:
            return None

        is_system_include = had_angle and self.spec.resolve_includes
        # Relative when it's a quoted local include, or an explicit ./.. path.
        is_relative = (
            (self.spec.resolve_includes and not is_system_include)
            or module_name.startswith('.')
        )

        return ImportStatement(
            file_path=file_path,
            line_number=node.start_position().row + 1,
            module_name=module_name,
            imported_names=[],
            is_relative=is_relative,
            import_type='include' if self.spec.resolve_includes else 'import',
            alias=alias,
            source_line=source_line,
            skip_unused=True,
        )

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        file_index: Optional[Dict[str, List[Path]]] = None,
    ) -> Optional[Path]:
        """Resolve an import to a real in-tree file (for the dependency graph).

        Dispatches by language shape:
          * ``resolve_includes`` (C/C++) → :meth:`_resolve_include` — quoted
            ``#include`` to a sibling/searched header; angle-bracket system
            includes return None.
          * ``source_extensions`` set (Java/PHP/Ruby/Swift/Kotlin, BACK-487/488)
            → :meth:`_resolve_module` — dotted type names and relative path
            literals to an in-tree source file.
          * neither → None (listing only; file-level graph not claimed).

        Returns a real, existing file every time or ``None`` — never a
        fabricated path. Self-reference filtering is the caller's job.

        ``file_index`` (BACK-491): an optional ``basename -> [full paths]`` map
        of every file under the (single) search root, prebuilt once by the
        caller (``ImportsAdapter._build_graph``) during its file-discovery walk.
        When supplied, multi-component resolution (include full-suffix match and
        dotted-name lookup alike) resolves by dict lookup instead of a full
        ``os.walk(root)`` per import — O(imports × tree) → O(tree + imports).
        The index must have been built from the same root passed in
        ``search_paths`` with the same ``SKIP_DIRECTORIES``/hidden-dir filtering
        (as ``_build_graph`` does), which makes the lookup byte-identical to the
        walk it replaces. Callers that pass no index (I002, call_graph, depends)
        fall back to the walk unchanged.
        """
        if self.spec.resolve_includes:
            return self._resolve_include(stmt, base_path, search_paths, file_index)
        if self.spec.source_extensions:
            return self._resolve_module(stmt, base_path, search_paths, file_index)
        return None

    def is_intra_project_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        project_namespaces: Optional[Set[str]] = None,
    ) -> Optional[bool]:
        """Honest-decline classification (BACK-547) by language shape:

          * C/C++ (`resolve_includes`): a quoted `#include "x"` (is_relative) is
            intra-project; an angle-bracket `<stdio.h>` system include is
            external — the same split `_resolve_include` uses. Precise.
          * Package/namespace languages (`resolve_namespaces` C#, or
            `package_node_types` Java/Kotlin/PHP): when the caller supplies
            ``project_namespaces`` (the tree's declared packages/namespaces,
            BACK-544/547's index), an import is intra-project iff the project
            declares a package equal to, nested under, or an ancestor of it —
            otherwise it's an external framework/dependency (`System.Text`,
            `java.util`, `Illuminate\\Support`, …). A trailing wildcard
            (Java `a.b.*`) is matched as an exact/ancestor package, never a
            recursive-descendant one — Java wildcard imports only reach
            classes declared directly in that package.
          * Swift: no per-file package declaration exists to scan (modules
            are a build-system concept, not a source construct), so this
            stays None (don't guess — never cry wolf)."""
        if self.spec.resolve_includes:
            return bool(stmt.is_relative)
        if (self.spec.resolve_namespaces or self.spec.package_node_types) and project_namespaces is not None:
            ns = stmt.module_name
            if not ns:
                return None
            sep = self.spec.module_separator or '.'
            wildcard = ns.endswith(sep + '*')
            if wildcard:
                # A wildcard (`import a.b.*`) only pulls in classes declared
                # directly in a.b — a declared *subpackage* (a.b.c) proves the
                # directory exists but not that a.b itself has any class, so
                # only an exact match counts here (never cry wolf on the
                # weaker signal).
                ns = ns[:-(len(sep) + 1)]
                return ns in project_namespaces
            for declared in project_namespaces:
                if declared == ns or declared.startswith(ns + sep) or ns.startswith(declared + sep):
                    return True
            return False
        if self.spec.module_dir_convention and project_namespaces is not None:
            # BACK-567 Swift: modules aren't declared in source, but the
            # directory-derived module index's key set (passed here as
            # project_namespaces) is exactly the in-tree module inventory. An
            # `import Foo` is intra-project iff Foo is one of those modules;
            # anything else (Foundation, a SwiftPM registry/URL dependency) is
            # external and correctly edge-less. In practice every in-tree
            # module resolves via resolve_module_targets, so this branch's True
            # is a defensive backstop that keeps a would-be silent miss on the
            # honest-decline path rather than the conservative None.
            module = stmt.module_name
            if not module:
                return None
            return self._sanitize_module_name(module) in project_namespaces
        return None

    def _resolve_include(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        file_index: Optional[Dict[str, List[Path]]] = None,
    ) -> Optional[Path]:
        """Resolve a quoted C/C++ ``#include`` to a real file (for the dep graph).

        System includes (``<stdio.h>``, ``is_relative=False``) return None —
        their file-level graph is not claimed. Quoted includes are looked up
        next to the including file first, then under each project search path.
        """
        if not stmt.is_relative:
            return None

        target = stmt.module_name
        # 1. Sibling of the including file (the common case in flat C trees).
        candidate = (base_path / target).resolve()
        if candidate.is_file():
            return candidate

        # 2. Under each project search path (root, then full-suffix path match).
        target_parts = Path(target).parts
        n = len(target_parts)
        for root in search_paths or []:
            candidate = (root / target).resolve()
            if candidate.is_file():
                return candidate
            if not root.is_dir():
                continue
            if n == 1:
                # Bare basename target (no qualifying directory) — bounded
                # one-level match, same as before (BACK-398).
                basename = target_parts[0]
                for child in root.iterdir():
                    if child.is_dir():
                        sub = (child / basename).resolve()
                        if sub.is_file():
                            return sub
                continue
            # BACK-404: match the candidate's full trailing path against every
            # directory component of the quoted target (e.g. "jemalloc/internal/
            # util.h"), not just its basename — a basename-only match collides
            # across vendored subtrees that happen to share a common header
            # name (util.h, config.h, types.h, ...).
            #
            # BACK-491: with a prebuilt index, iterate only the files sharing
            # this include's basename (in walk order) instead of re-walking the
            # whole tree. Because the index holds every file under `root` in the
            # same walk order and with the same skip-dir filter, the first
            # full-suffix match here is the same file the os.walk below would
            # return — just without the O(tree) scan per include.
            if file_index is not None:
                for candidate in file_index.get(target_parts[-1], ()):
                    if candidate.parts[-n:] == target_parts:
                        return candidate.resolve()
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if not is_skippable_dir(Path(dirpath), d) and not d.startswith('.')
                ]
                for fname in filenames:
                    candidate = Path(dirpath) / fname
                    if candidate.parts[-n:] == target_parts:
                        return candidate.resolve()
        return None

    # --- BACK-487/488: non-#include edge resolution ----------------------

    def _resolve_module(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> Optional[Path]:
        """Resolve a Java/PHP/Ruby/Swift/Kotlin import to an in-tree source file.

        Two shapes, distinguished structurally (never fabricating an edge):
          * **Qualified type name** joined by ``module_separator`` (Java
            ``com.pkg.Type``, PHP ``App\\Models\\User``, Kotlin
            ``com.pkg.Bar``) → :meth:`_resolve_dotted`.
          * **Path-style literal** (Ruby ``require_relative './x'``,
            ``load 'config.rb'``; PHP ``require 'lib/foo.php'``) → resolved
            relative to the including file, then project roots.
          * A single-token module (Swift ``import Foo``) is tried as a bare
            basename (``Foo.swift``) via the dotted path with one component.

        Wildcards (Java ``import a.b.*``, Scala ``import a.b._``) and selector
        imports (Scala ``import a.b.{C, D}``) name a package or multiple types
        rather than one file, and return None.
        """
        module = stmt.module_name
        if not module or module.endswith('*'):
            return None

        sep = self.spec.module_separator
        exts = self.spec.source_extensions
        prefix = self.spec.project_relative_prefix

        if prefix and module.startswith(prefix):
            # Project-root-relative virtual path (GDScript `res://...`) — never
            # file-relative, so resolve only against search_paths (the scan
            # root), skipping the base_path-relative attempt entirely.
            target = module[len(prefix):]
            return self._resolve_path_target(target, None, search_paths, exts)

        scheme = self.spec.package_uri_scheme
        if scheme and module.startswith(scheme):
            # Dart `package:name/path.dart` — must be checked before
            # `_looks_like_path` below: the remainder contains '/' and would
            # otherwise be tried (and fail) as a file-relative literal.
            return self._resolve_package_uri(module[len(scheme):], search_paths, file_index, exts)

        # Path-shaped module strings must win over namespace-separator
        # splitting, checked first: PHP's module_separator is '\' (`use
        # App\Models\User`), which collides with Windows' native path
        # separator. An absolute path built by __DIR__/constant-anchor
        # resolution (BACK-564/565, str(anchor / remainder)) renders
        # backslashes there, so on Windows `sep in module` matched first and
        # split the whole path into bogus namespace components — silently
        # resolving to None instead of the real file. No legitimate dotted/
        # namespaced import in any currently-supported language starts with
        # '.', contains '/', ends with a source extension, or is an absolute
        # filesystem path, so reordering is safe on every platform.
        if self._looks_like_path(module, exts):
            return self._resolve_path_target(module, base_path, search_paths, exts)

        if sep and sep in module:
            parts = [p for p in module.split(sep) if p]
            # Scala selector `{C, D}` / wildcard `_` name multiple targets or a
            # whole package, not one file — skip rather than leak `{...}`/`_`
            # into a bogus path.
            if parts and (parts[-1] == '_' or '{' in parts[-1]):
                return None
            return self._resolve_dotted(parts, exts, search_paths, file_index)

        # Single-token module with no separator and no path markers: try it as a
        # bare basename (Swift `import Foo` → Foo.swift; Java default-package
        # `import Foo`). Only resolves when exactly one such file exists.
        if module.isidentifier():
            resolved = self._resolve_dotted([module], exts, search_paths, file_index)
            if resolved is not None:
                return resolved
            if self.spec.class_name_convention:
                return self._resolve_class_name(module, search_paths, file_index)
            return None

        return None

    @staticmethod
    def _looks_like_path(module: str, exts: FrozenSet[str]) -> bool:
        """True when a module string is a filesystem path, not a qualified name.

        ``'/' in module`` alone misses the module strings produced by
        __DIR__/constant-anchor resolution (BACK-564/565): those are built via
        ``str(anchor / remainder)``, which renders native (backslash)
        separators on Windows, so the ``/`` check silently failed there —
        the whole statement quietly resolved to ``None`` instead of the real
        file. ``Path(module).is_absolute()`` catches that case OS-agnostically
        (pathlib parses native separators correctly per-platform) without
        touching the existing forward-slash convention relative literals
        (Ruby ``require_relative './x'``, PHP ``require 'lib/foo.php'``) rely on.
        """
        return (
            module.startswith('.')
            or '/' in module
            or any(module.endswith(e) for e in exts)
            or Path(module).is_absolute()
        )

    def _resolve_dotted(
        self,
        parts: List[str],
        exts: FrozenSet[str],
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> Optional[Path]:
        """Resolve a qualified type name (``[com, pkg, Type]``) to a source file.

        Matches the *longest* trailing path-suffix that uniquely identifies one
        in-tree file, so a PSR-4 vendor prefix (``App\\`` → ``src/``) or an
        unqualified default-package import still resolves without colliding
        across same-named types in different packages. Ambiguity at the most
        specific suffix → skip (never guess).

        BACK-551: when the direct match fails, the trailing component may name a
        *member of* an enclosing top-level type rather than a file of its own —
        Java ``import a.b.Outer.Inner`` (nested type) and
        ``import static a.b.Outer.CONST`` (static member, the ``static`` keyword
        already stripped so it arrives here as ``a.b.Outer.CONST``). The Java
        measurement loop (dogfood-findings/java-recall-oracle) found these
        silently dropped: the resolver looked for ``Inner.java``/``CONST.java``,
        which don't exist, and never fell back to ``Outer.java``. Peel trailing
        components down to the enclosing class and retry — gated to languages
        where the idiom exists (``spec.nested_member_fallback``) and by the
        Java/Kotlin/Scala convention that a *type* component is Uppercase while a
        *package* component is not, so we stop before peeling into the package
        and matching a stray lowercase-named file (never fabricate an edge).
        """
        if not parts:
            return None
        match = self._match_dotted(parts, exts, search_paths, file_index)
        if match is not None:
            return match
        if not getattr(self.spec, 'nested_member_fallback', False):
            return None
        peeled = list(parts)
        for _ in range(2):  # Outer.Inner, Outer.Inner.Deeper — rare beyond 2.
            if len(peeled) < 2:
                break
            peeled = peeled[:-1]
            # New trailing component must still look like a type (Uppercase); a
            # lowercase component means we've reached the package path — stop.
            if not peeled[-1][:1].isupper():
                break
            match = self._match_dotted(peeled, exts, search_paths, file_index)
            if match is not None:
                return match
        return None

    def _match_dotted(
        self,
        parts: List[str],
        exts: FrozenSet[str],
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> Optional[Path]:
        """Longest-unique-suffix match of ``parts`` (last = type) across exts.

        BACK-711: for a bare single-token import (``require("wibox")``, no
        qualifying prefix), the extension-appended flat-file branch can only
        match via ``_longest_unique_suffix``'s k=1 global-uniqueness fallback
        — "the only file anywhere in the tree with this basename" has no
        structural relationship to the import site. When a same-named
        directory with an index file also exists (``wibox/init.lua``), that
        directory match is checked first; the flat-file candidate is only
        preferred over it when the two are *true siblings* (same parent
        directory — e.g. ``lib/beautiful.lua`` next to ``lib/beautiful/``),
        matching real ``require()`` search order (``?.lua`` before
        ``?/init.lua``) for the case the flat file actually competes at the
        same directory level. AwesomeWM has both shapes in one corpus:
        ``lib/beautiful.lua``/``lib/beautiful/init.lua`` are true siblings
        (flat file correctly wins), while ``require("wibox")`` (393 call
        sites) was silently resolving onto the unrelated ``lib/awful/wibox.lua``
        — zero directory relationship to ``lib/wibox/`` — while the real
        target ``lib/wibox/init.lua`` showed 0 dependents.
        """
        if len(parts) == 1:
            dir_match = None
            for index_filename in self.spec.directory_index_filenames:
                target_parts = parts + [index_filename]
                match = self._longest_unique_suffix(target_parts, search_paths, file_index)
                if match is not None:
                    dir_match = match
                    break
            if dir_match is not None:
                # Sibling check by direct path existence, not
                # `_longest_unique_suffix`'s global-basename-uniqueness gate:
                # a same-named flat file elsewhere in the tree (e.g. a test
                # shim) must not block a real sibling from winning, and a
                # global "only one file with this basename" guess must not
                # win when it *isn't* the sibling either.
                sibling_dir = dir_match.parent.parent
                for ext in exts:
                    basename = parts[-1] + ext
                    for candidate in self._index_lookup(basename, search_paths, file_index):
                        resolved = candidate.resolve()
                        if resolved.parent == sibling_dir:
                            return resolved
                return dir_match
        for ext in exts:
            target_parts = parts[:-1] + [parts[-1] + ext]
            match = self._longest_unique_suffix(target_parts, search_paths, file_index)
            if match is not None:
                return match
        if len(parts) != 1:
            for index_filename in self.spec.directory_index_filenames:
                target_parts = parts + [index_filename]
                match = self._longest_unique_suffix(target_parts, search_paths, file_index)
                if match is not None:
                    return match
        return None

    def _longest_unique_suffix(
        self,
        target_parts: List[str],
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> Optional[Path]:
        """Return the file whose path ends with the longest unique suffix of
        ``target_parts`` (last element carries the extension), or None.

        A bare-basename match (k=1) is accepted only when the import had no
        qualifying prefix to begin with (a genuinely single-token module,
        e.g. Swift ``import Foo``) *and* exactly one file in the tree bears
        that basename. A multi-part import (``resty.openssl.rand``) that
        fails to match at every suffix length ``>= 2`` is never allowed to
        fall back to a global bare-basename guess — BACK-670: that produced
        false-positive edges onto same-basename in-tree files with zero path
        overlap with the import's real qualifying components (e.g. Lua
        ``resty.openssl.rand``, an external module, wrongly resolving onto
        ``kong/tools/rand.lua`` because it was the tree's only ``rand.lua``).
        If even the most specific available suffix is ambiguous, resolution
        is skipped.
        """
        basename = target_parts[-1]
        candidates = self._index_lookup(basename, search_paths, file_index)
        if not candidates:
            return None
        n = len(target_parts)
        min_k = 1 if (n == 1 and len(candidates) == 1) else 2
        for k in range(n, min_k - 1, -1):
            suffix = tuple(target_parts[-k:])
            matches = [c for c in candidates if c.parts[-k:] == suffix]
            if len(matches) == 1:
                return matches[0].resolve()
            if len(matches) > 1:
                # Already ambiguous at this (most-specific-available) suffix;
                # shorter suffixes only get more ambiguous. Skip, don't guess.
                return None
        return None

    def _resolve_path_target(
        self,
        module: str,
        base_path: Optional[Path],
        search_paths: Optional[List[Path]],
        exts: FrozenSet[str],
    ) -> Optional[Path]:
        """Resolve a path-style import literal to a real file.

        Tries the target verbatim and with each source extension appended
        (Ruby ``require_relative './helper'`` → ``helper.rb``), relative to the
        including file first, then each project root. ``base_path=None`` (GDScript
        ``res://``) skips the file-relative attempt and tries only project roots.
        """
        names = [module] + [module + e for e in exts if not module.endswith(e)]
        roots = ([base_path] if base_path is not None else []) + list(search_paths or [])
        for root in roots:
            for name in names:
                candidate = (root / name).resolve()
                if candidate.is_file():
                    return candidate
        return None

    def _resolve_package_uri(
        self,
        rest: str,
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
        exts: FrozenSet[str],
    ) -> Optional[Path]:
        """Resolve a ``package:name/path`` remainder (Dart, BACK-621) to a file.

        ``name`` is looked up in a project-wide index of every in-tree
        ``spec.package_manifest_filename`` (Dart ``pubspec.yaml``)'s declared
        ``name:``, built once per scan and cached on ``file_index`` under a
        sentinel key (never a real basename, so it can't collide) — the same
        object identity is threaded through every ``resolve_import`` call in
        one ``depends://``/``imports://`` run, so this reads each manifest at
        most once regardless of how many ``package:`` imports reference it.
        A name absent from the index is a real external pub.dev dependency —
        correctly returns ``None``, never a guess.
        """
        manifest_name = self.spec.package_manifest_filename
        lib_dirname = self.spec.package_manifest_lib_dirname
        if manifest_name is None or lib_dirname is None or '/' not in rest:
            return None
        pkg_name, sub_path = rest.split('/', 1)
        pkg_map = self._package_manifest_map(manifest_name, lib_dirname, search_paths, file_index)
        lib_dir = pkg_map.get(pkg_name)
        if lib_dir is None:
            return None
        return self._resolve_path_target(sub_path, None, [lib_dir], exts)

    _PACKAGE_MANIFEST_CACHE_KEY = '\x00package_manifest_map'
    _MANIFEST_NAME_RE = re.compile(r'^name:\s*(\S+)', re.MULTILINE)

    def _package_manifest_map(
        self,
        manifest_name: str,
        lib_dirname: str,
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> Dict[str, Path]:
        cache_key = self._PACKAGE_MANIFEST_CACHE_KEY
        if file_index is not None and cache_key in file_index:
            return file_index[cache_key]  # type: ignore[return-value]

        manifests = self._index_lookup(manifest_name, search_paths, file_index)
        pkg_map: Dict[str, Path] = {}
        for manifest_path in manifests:
            try:
                text = manifest_path.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            m = self._MANIFEST_NAME_RE.search(text)
            if not m:
                continue
            lib_dir = manifest_path.parent / lib_dirname
            if lib_dir.is_dir():
                pkg_map[m.group(1).strip()] = lib_dir

        if file_index is not None:
            file_index[cache_key] = pkg_map  # type: ignore[assignment]
        return pkg_map

    _CLASS_NAME_CACHE_KEY = '\x00class_name_index'
    _CLASS_NAME_RE = re.compile(r'^\s*class_name\s+(\w+)', re.MULTILINE)

    def _resolve_class_name(
        self,
        name: str,
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> Optional[Path]:
        """Resolve a bareword identifier (GDScript ``extends Foo``) against
        the project-wide ``class_name`` index (BACK-621). ``None`` when
        ``name`` isn't a declared ``class_name`` anywhere in-tree — an
        engine builtin (``Node``, ``Control``, ...), correctly left
        unresolved rather than guessed."""
        index = self._class_name_project_index(search_paths, file_index)
        return index.get(name)

    def _class_name_project_index(
        self,
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> Dict[str, Path]:
        """``class_name`` -> declaring file, across every in-tree source file.

        Built once per scan and cached on ``file_index`` under a sentinel key
        (same convention as :meth:`_package_manifest_map`) so a scan with many
        bareword ``extends`` statements re-reads no file twice. Unlike a
        manifest map, there's no fixed filename to look up via
        :meth:`_index_lookup` — every ``source_extensions`` file is a
        candidate declarer, so this scans the full file set (``file_index``'s
        own value union when available, else a bounded ``search_paths``
        walk) once, the same file set already being walked for import
        extraction — no separate tree walk when ``file_index`` is present.
        """
        cache_key = self._CLASS_NAME_CACHE_KEY
        if file_index is not None and cache_key in file_index:
            return file_index[cache_key]  # type: ignore[return-value]

        exts = self.spec.source_extensions
        candidates: Set[Path] = set()
        if file_index is not None:
            for paths in file_index.values():
                if not isinstance(paths, list):
                    continue  # a different resolver's cached sentinel value
                for p in paths:
                    if p.suffix in exts:
                        candidates.add(p)
        else:
            for root in search_paths or []:
                if not root.is_dir():
                    continue
                for dirpath, dirnames, filenames in os.walk(root):
                    dirnames[:] = [
                        d for d in dirnames
                        if not is_skippable_dir(Path(dirpath), d) and not d.startswith('.')
                    ]
                    for fname in filenames:
                        if Path(fname).suffix in exts:
                            candidates.add(Path(dirpath) / fname)

        index: Dict[str, Path] = {}
        for f in candidates:
            try:
                text = f.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            m = self._CLASS_NAME_RE.search(text)
            if m:
                index.setdefault(m.group(1), f.resolve())

        if file_index is not None:
            file_index[cache_key] = index  # type: ignore[assignment]
        return index

    @staticmethod
    def _index_lookup(
        basename: str,
        search_paths: Optional[List[Path]],
        file_index: Optional[Dict[str, List[Path]]],
    ) -> List[Path]:
        """All in-tree files bearing ``basename`` — via the prebuilt index when
        available (BACK-491), else a bounded walk of the search paths."""
        if file_index is not None:
            return list(file_index.get(basename, ()))
        found: List[Path] = []
        for root in search_paths or []:
            if not root.is_dir():
                continue
            for dirpath, dirnames, filenames in os.walk(root):
                dirnames[:] = [
                    d for d in dirnames
                    if not is_skippable_dir(Path(dirpath), d) and not d.startswith('.')
                ]
                if basename in filenames:
                    found.append(Path(dirpath) / basename)
        return found


# --- Language specs + registered subclasses ------------------------------
#
# Each subclass is three lines. Adding a language = add a spec + subclass.

_C_SPEC = _ImportSpec(
    # BACK-676: 'preproc_call' is the fallback node tree-sitter emits for a
    # #include inside a struct/class body (not just 'preproc_include', which
    # only covers top-level-context includes) -- filtered to '#include' only
    # in _node_to_import.
    import_node_types=frozenset({'preproc_include', 'preproc_call'}),
    keywords=frozenset({'#include'}),
    resolve_includes=True,
)

_CPP_SPEC = _ImportSpec(
    # C++20 `import mod;` is `import_declaration`; rare but cheap to include.
    # See _C_SPEC above re: 'preproc_call' (BACK-676).
    import_node_types=frozenset({'preproc_include', 'import_declaration', 'preproc_call'}),
    keywords=frozenset({'#include', 'import'}),
    resolve_includes=True,
)

_JAVA_SPEC = _ImportSpec(
    import_node_types=frozenset({'import_declaration'}),
    keywords=frozenset({'import', 'static'}),
    module_separator='.',
    source_extensions=frozenset({'.java'}),
    # BACK-551: `import a.b.Outer.Inner` / `import static a.b.Outer.CONST` name a
    # member of Outer, not a file — peel to Outer.java when the direct match fails.
    nested_member_fallback=True,
    # BACK-547 scale-out: `package_declaration` → `scoped_identifier` gives a
    # cheap project-wide package inventory, turning the honest-decline verdict
    # for an unresolved `import` from an unconditional None (no inventory) into a
    # precise True (intra-project, a real resolver miss) or False (external, e.g.
    # `java.util.List`).
    package_node_types=frozenset({'package_declaration'}),
)

_CSHARP_SPEC = _ImportSpec(
    import_node_types=frozenset({'using_directive'}),
    keywords=frozenset({'using', 'global', 'static'}),
    alias_assignment=True,
    # `using X.Y` names a namespace (a directory of files), not one type. The
    # dotted-name path below still runs first (resolves the rare case a
    # same-named `Y.cs` exists), but BACK-544 adds a namespace-declaration
    # index (`resolve_namespaces`) so the common case — a namespace spanning
    # several files — fans out to every declaring file instead of being
    # silently skipped (see resolve_namespace_targets).
    module_separator='.',
    source_extensions=frozenset({'.cs'}),
    resolve_namespaces=True,
    # BACK-547: the same declared-namespace index also backs the honest-decline
    # classification for C#.
    package_node_types=frozenset({
        'namespace_declaration', 'file_scoped_namespace_declaration',
    }),
    # BACK-669 C# recall loop (Jellyfin, real-corpus full-population diff):
    # `using static Foo.Bar.Type;` and `using Alias = Foo.Bar.Type;` (the
    # latter the dominant real shape, 87/96 real alias statements) name a
    # specific TYPE, not a namespace — resolve_namespace_targets above never
    # matches (the target has one extra dotted component), and the plain
    # dotted-suffix match only succeeds when the directory layout mirrors the
    # namespace AND the type's filename is tree-wide unique. Found missing 2
    # real edges (3 importer edges) this way: `LinkedChildType` is declared
    # in two different namespaces/files (a DB entity and a domain entity,
    # both under an `Entities/` directory), so the bare-basename fallback
    # correctly declines on ambiguity — only a namespace-scoped type index
    # can disambiguate. See namespaced_type_node_types/namespaced_type_fallback.
    namespaced_type_node_types=frozenset({
        'class_declaration', 'interface_declaration', 'struct_declaration',
        'record_declaration', 'enum_declaration',
    }),
    namespaced_type_fallback=True,
)

_PHP_SPEC = _ImportSpec(
    import_node_types=frozenset({
        'namespace_use_declaration',
        'require_expression',
        'require_once_expression',
        'include_expression',
        'include_once_expression',
    }),
    keywords=frozenset({
        'use', 'function', 'const',
        'require', 'require_once', 'include', 'include_once',
    }),
    module_separator='\\',  # `use App\Models\User`
    source_extensions=frozenset({'.php'}),
    # BACK-547 scale-out: `namespace_definition` → `namespace_name` (PSR-4
    # `namespace App\Models;`) feeds the same honest-decline inventory as
    # Java/Kotlin. (No nested_member_fallback: `\` namespace components are
    # StudlyCaps, so the Uppercase gate can't tell package from type.)
    package_node_types=frozenset({'namespace_definition'}),
    # BACK-564: real PHP require/include targets are almost never a bare
    # string literal — they're built by concatenation (`__DIR__ . '/x.php'`,
    # `ABSPATH . WPINC . '/version.php'`). See `_concat_to_import` and the
    # `_ImportSpec.concat_relative_node_types` docstring for the resolution
    # rules (only the `__DIR__`/`dirname(__FILE__)` idiom resolves; framework
    # constants like ABSPATH are an honest skip, not a fabricated edge).
    concat_relative_node_types=frozenset({
        'require_expression', 'require_once_expression',
        'include_expression', 'include_once_expression',
    }),
    # BACK-565: the ABSPATH/WPINC-family residual left after BACK-564 —
    # WordPress bootstraps these via `define('ABSPATH', __DIR__ . '/')` in
    # wp-load.php/wp-settings.php/wp-admin/*.php. See extract_constant_defines
    # and _resolve_concat_operand for the resolution rules (only a constant
    # proven to have exactly one absolute value project-wide substitutes;
    # multiple distinct values or an unrecognized expression shape is an
    # honest skip, never fabricated).
    constant_define_call_names=frozenset({'define'}),
)

_RUBY_SPEC = _ImportSpec(
    import_node_types=frozenset(),  # no dedicated node — matched as calls
    keywords=frozenset({'require', 'require_relative', 'load'}),
    call_import_names=frozenset({'require', 'require_relative', 'load'}),
    # Ruby imports are always path-style literals — no qualified-name separator.
    source_extensions=frozenset({'.rb'}),
    # BACK-557: Rails/Zeitwerk resolves most intra-app references by path→constant
    # convention with no require statement, so low require density means
    # depends:// undercounts — emit a coverage caveat.
    convention_autoloaded=True,
    # BACK-557 direction a: infer those convention-resolved edges instead of
    # only caveating their absence.
    zeitwerk_convention=True,
    # BACK-669 solidus second-corpus loop: a multi-gem monorepo (Rails Engine
    # gems, each carrying its own gemspec + lib/) registers each gem's lib/
    # on Bundler's $LOAD_PATH, so a bare `require 'spree/foo'` in one gem can
    # target another gem's lib/ tree — invisible to a resolver that only
    # tries the single project root. See load_path_manifest_glob docstring.
    load_path_manifest_glob='*.gemspec',
    load_path_lib_dirname='lib',
)

# BACK-488: Swift and Kotlin were absent from the table entirely — `imports://`,
# `architecture`, and every fan-in/circular-dep feature returned nothing for two
# of the most DD-relevant (mobile) languages. Node kinds verified against
# tree-sitter-language-pack real parses.
_SWIFT_SPEC = _ImportSpec(
    # `import Foundation` / `import struct Foo.Bar` — the whole path is the
    # import declaration; leading `struct`/`class`/`func`/etc. submodule kinds
    # are stripped as keywords.
    import_node_types=frozenset({'import_declaration'}),
    keywords=frozenset({
        'import', 'struct', 'class', 'enum', 'protocol', 'typealias',
        'func', 'let', 'var',
    }),
    # BACK-669 (swift-collections second corpus): `@testable import Foo` /
    # `@_spi(Testing) @testable import Foo` (real, common in test files) —
    # an attribute's variable argument can't be a fixed `keywords` entry, so
    # this needs its own stripping rule. See `strip_attribute_prefix`'s
    # docstring for the pre-fix failure (whole-statement garbage module
    # name, zero edges, no honest-decline warning either).
    strip_attribute_prefix=True,
    # Swift `import Foo` names a module; resolves to Foo.swift only when the
    # module maps 1:1 to a single in-tree file (skipped otherwise).
    module_separator='.',
    source_extensions=frozenset({'.swift'}),
    # BACK-560: same-module (same-target) cross-file references need no
    # `import` at all — Swift compiles a whole module together, so there is
    # no statement for extraction to miss.
    same_module_undetectable=True,
    # BACK-567: cross-module `import Foo` names a whole SwiftPM target, resolved
    # to every file under Sources/<Foo>/ or Tests/<Foo>/ by directory
    # convention (no toolchain needed). Orthogonal to same_module_undetectable
    # above — that covers same-target refs (no import at all); this covers
    # cross-target imports (a real statement that had been resolving ~0%).
    module_dir_convention=frozenset({'Sources', 'Tests'}),
    # BACK-567: Package.swift target declarations override the convention above
    # when a target relocates its sources via an explicit `path:` (real case:
    # GraphAPI's `path: "./Sources"` puts every subdir in one module).
    manifest_filename='Package.swift',
    manifest_target_calls=frozenset({
        'target', 'testTarget', 'executableTarget', 'macro', 'plugin',
    }),
)

_KOTLIN_SPEC = _ImportSpec(
    import_node_types=frozenset({'import_header'}),
    keywords=frozenset({'import'}),
    module_separator='.',  # `import com.foo.Bar`
    source_extensions=frozenset({'.kt'}),
    # BACK-551: Kotlin member imports `import a.b.Outer.member` peel to Outer.kt.
    nested_member_fallback=True,
    # BACK-547 scale-out: `package_header` → `identifier` (`package a.b.c`)
    # feeds the honest-decline package inventory, same as Java/PHP.
    package_node_types=frozenset({'package_header'}),
    # BACK-547 Kotlin measurement loop: `import a.b.foo` for a top-level
    # fun/val/var has no enclosing type in the import path at all (unlike
    # nested_member_fallback's `Outer.Inner` shape), so only a content-scanned
    # (package, symbol) index can find the declaring file.
    member_node_types=frozenset({'function_declaration', 'property_declaration'}),
    member_symbol_fallback=True,
)

# BACK-514: Lua/Scala/Dart/Zig/GDScript were absent from the table entirely —
# `imports://`, `architecture`, `surface`, and `pack` silently built their
# picture from zero files of these five languages. Node kinds verified against
# real parses (2026-07-09, session apricot-tapestry-0709); see
# internal-docs/planning/BACK-514-import-coverage-implementation.md.
_SCALA_SPEC = _ImportSpec(
    # `import a.b.C` / `import a.b.{C, D}` / `import a.b._` are all one node
    # kind; selector/wildcard forms are recognised and skipped in
    # _resolve_module (they name multiple targets, not one file).
    import_node_types=frozenset({'import_declaration'}),
    keywords=frozenset({'import'}),
    module_separator='.',
    source_extensions=frozenset({'.scala'}),
    # BACK-551: `import a.b.Outer.Inner` names a member of Outer — peel to Outer.scala.
    nested_member_fallback=True,
    # BACK-557 scale-out: `package_clause` -> `identifier`/`stable_identifier`
    # (`package a.b.c`) feeds the honest-decline package inventory (as for
    # Java/Kotlin/PHP) *and* is required to pair a file's declared package
    # with `extract_container_members`' (containerName, memberName) pairs
    # below.
    package_node_types=frozenset({'package_clause'}),
    # BACK-557 Scala measurement loop (real corpus: samples/scala, GitBucket):
    # confirmed real Scala 2/3 code has NO bare top-level def/val outside any
    # object (Scala forbids it outside a `package object`; unlike Kotlin,
    # `member_symbol_fallback`/`member_node_types` stay unset here — there is
    # nothing to index at file scope). The real, confirmed gap is one level
    # deeper: `object helpers` (a lowerCamelCase container — GitBucket's only
    # such container in-tree) whose members (`import
    # gitbucket.core.view.helpers.getApiMilestone`) BACK-551's Uppercase-gated
    # peel can never reach by design (see extract_container_members).
    member_container_node_types=frozenset({'object_definition'}),
    container_member_node_types=frozenset({'function_definition', 'val_definition'}),
    container_member_fallback=True,
)

_DART_SPEC = _ImportSpec(
    # `export`/`part` directives are separate node kinds (library_export,
    # part_directive) and are intentionally not matched here — out of scope
    # for v1 (imports only).
    import_node_types=frozenset({'import_specification'}),
    keywords=frozenset({'import'}),
    # Dart imports are path-style literals (relative `./x.dart`) or a
    # `package:name/path.dart` URI (BACK-621: the dominant real-world shape —
    # 5,989 of 6,290 in-tree imports in the AppFlowy sample corpus — resolved
    # via the project-wide pubspec.yaml `name -> lib/` index built by
    # `package_uri_scheme`/`package_manifest_filename`/
    # `package_manifest_lib_dirname` below).
    source_extensions=frozenset({'.dart'}),
    package_uri_scheme='package:',
    package_manifest_filename='pubspec.yaml',
    package_manifest_lib_dirname='lib',
    # BACK-712 (drift second-corpus overfit-guard): `show`/`hide`/`deferred
    # as` combinator clauses trail the quoted URI and corrupt module_name if
    # left in the parsed remainder — see combinator_clause's docstring.
    combinator_clause=True,
)

_GDSCRIPT_SPEC = _ImportSpec(
    # Two independent import shapes in one spec: `extends "res://base.gd"`
    # (dedicated node) and `preload(...)`/`load(...)` (call-style).
    import_node_types=frozenset({'extends_statement'}),
    keywords=frozenset({'extends'}),
    call_import_names=frozenset({'preload', 'load'}),
    source_extensions=frozenset({'.gd'}),
    # `res://` is Godot's project-root-relative virtual filesystem, not
    # file-relative — resolved only against search_paths (see _resolve_module).
    project_relative_prefix='res://',
    # BACK-621: `extends Foo` where Foo is declared `class_name Foo` in some
    # other in-tree file — Godot's global class-registration convention, the
    # dominant edge shape in the real godot-demo-projects corpus (27 of 41).
    class_name_convention=True,
)

_LUA_SPEC = _ImportSpec(
    import_node_types=frozenset(),  # no dedicated node — matched as calls
    keywords=frozenset({'require'}),
    call_import_names=frozenset({'require'}),
    call_node_type='function_call',  # Lua's call node kind, unlike Ruby's `call`
    # `require("a.b")` uses `.` as a path separator by Lua convention →
    # a/b.lua, resolved the same way Java's dotted package names are.
    module_separator='.',
    source_extensions=frozenset({'.lua'}),
    # `require("a.b")` may also name a directory module → a/b/init.lua
    # (BACK-621, package.path's `?/init.lua` pattern) when no flat a/b.lua
    # file exists — confirmed against Kong's own rockspec module map.
    directory_index_filenames=frozenset({'init.lua'}),
)


@register_extractor
class CImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.c', '.h'}
    language_name = 'C'
    spec = _C_SPEC


@register_extractor
class CppImportExtractor(_GenericTreeSitterImportExtractor):
    # BACK-664: .hh (already C++ per analyzers/cpp.py's structural
    # registration) and .mm (Obj-C++, parses with tree-sitter's 'objc'
    # grammar but produces the same preproc_include nodes as C/C++ — verified
    # empirically) were previously unresolved by the import graph.
    extensions = {'.cpp', '.cc', '.cxx', '.hpp', '.hxx', '.hh', '.mm'}
    language_name = 'C++'
    spec = _CPP_SPEC


@register_extractor
class JavaImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.java'}
    language_name = 'Java'
    spec = _JAVA_SPEC


@register_extractor
class CSharpImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.cs'}
    language_name = 'C#'
    spec = _CSHARP_SPEC


@register_extractor
class PhpImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.php'}
    language_name = 'PHP'
    spec = _PHP_SPEC


@register_extractor
class RubyImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.rb'}
    language_name = 'Ruby'
    spec = _RUBY_SPEC


@register_extractor
class SwiftImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.swift'}
    language_name = 'Swift'
    spec = _SWIFT_SPEC


@register_extractor
class KotlinImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.kt', '.kts'}
    language_name = 'Kotlin'
    spec = _KOTLIN_SPEC


@register_extractor
class ScalaImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.scala'}
    language_name = 'Scala'
    spec = _SCALA_SPEC


@register_extractor
class DartImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.dart'}
    language_name = 'Dart'
    spec = _DART_SPEC


@register_extractor
class GDScriptImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.gd'}
    language_name = 'GDScript'
    spec = _GDSCRIPT_SPEC


@register_extractor
class LuaImportExtractor(_GenericTreeSitterImportExtractor):
    extensions = {'.lua'}
    language_name = 'Lua'
    spec = _LUA_SPEC


__all__ = [
    '_ImportSpec',
    '_GenericTreeSitterImportExtractor',
    'CImportExtractor',
    'CppImportExtractor',
    'JavaImportExtractor',
    'CSharpImportExtractor',
    'PhpImportExtractor',
    'RubyImportExtractor',
    'SwiftImportExtractor',
    'KotlinImportExtractor',
    'ScalaImportExtractor',
    'DartImportExtractor',
    'GDScriptImportExtractor',
    'LuaImportExtractor',
]

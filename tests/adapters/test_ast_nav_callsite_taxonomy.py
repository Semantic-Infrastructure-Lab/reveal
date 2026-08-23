"""Nav feature tests: callsite/construct-naming regressions.

Split from test_ast_nav_probe_features.py (BACK-1151) -- covers
per-language constructor/operator/macro/HOC callsite naming and
range_calls/outline extraction regressions that don't fit the other
split files' feature groupings.
"""

"""Tests for probe-inspired nav features added in BACK-156 through BACK-160.

Covers:
  collect_exits()    -- BACK-156/159 (--exits / --flowto)
  all_var_flow()     -- BACK-160 foundation
  collect_deps()     -- BACK-160 (--deps)
  collect_mutations()-- BACK-160 (--mutations)
  render_branchmap() -- BACK-158 (--ifmap / --catchmap)
  render_exits()     -- BACK-159
  render_deps()      -- BACK-160
  render_mutations() -- BACK-160

Also covers flat-file behaviour (Change A: root_node fallback) indirectly
through the nav functions accepting root_node as scope_node.
"""

import textwrap
import unittest

import tree_sitter_language_pack as ts

import pytest
from reveal.core.treesitter_compat import _zero_arg, ts_parse, tree_root

# BACK-1149: component-layer test -- single adapter/module in isolation, no subprocess/CLI/MCP
pytestmark = pytest.mark.component


# ---------------------------------------------------------------------------
# Parse helpers (shared with test_ast_nav.py pattern)
# ---------------------------------------------------------------------------

def _parse_python(code: str):
    """Parse Python code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('python')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _find_func(root, get_text, name: str):
    """Find a function_definition node by name."""
    stack = [root.child(i) for i in range(_zero_arg(root, 'child_count'))]
    while stack:
        node = stack.pop()
        if _zero_arg(node, 'kind') == 'function_definition':
            for child in [node.child(i) for i in range(_zero_arg(node, 'child_count'))]:
                if _zero_arg(child, 'kind') == 'identifier' and get_text(child) == name:
                    return node
        stack.extend(reversed([node.child(i) for i in range(_zero_arg(node, 'child_count'))]))
    return None


# ===========================================================================
# collect_exits
# ===========================================================================

def _parse_php(code: str):
    """Parse PHP code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('php')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _parse_scala(code: str):
    """Parse Scala code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('scala')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _parse_swift(code: str):
    """Parse Swift code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('swift')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


def _parse_gdscript(code: str):
    """Parse GDScript code and return (tree, root, get_text, content_bytes)."""
    parser = ts.get_parser('gdscript')
    src = textwrap.dedent(code).lstrip('\n')
    content_bytes = src.encode('utf-8')
    tree = ts_parse(parser, src)
    root = tree_root(tree)

    def get_text(node):
        return content_bytes[_zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')].decode(
            'utf-8'
        )

    return tree, root, get_text, content_bytes


class TestFlatFileFallback(unittest.TestCase):
    """Verify that var_flow, range_calls, collect_exits, etc. accept root_node.

    This tests the language-agnostic promise from the planning doc: all nav
    functions take 'any tree-sitter node' — the root_node fallback in
    _dispatch_nav (Change A) is what makes flat-file support work.
    """

    def setUp(self):
        # Flat procedural code — no top-level function wrapper
        code = """
        errormsg = ''
        data = fetch_data()
        if data:
            try:
                result = process(data)
                errormsg = result.get('error', '')
            except Exception as e:
                errormsg = str(e)
        write_log(errormsg)
        return_value = bool(errormsg)
        """
        self._tree, self._root, self._get_text, _ = _parse_python(code)

    def test_var_flow_on_root_node(self):
        from reveal.adapters.ast.nav import var_flow
        events = var_flow(self._root, 'errormsg', 1, 999, self._get_text)
        self.assertIsInstance(events, list)
        # errormsg is written and read — should have events
        self.assertGreater(len(events), 0)
        kinds = {e['kind'] for e in events}
        self.assertIn('WRITE', kinds)

    def test_range_calls_on_root_node(self):
        from reveal.adapters.ast.nav import range_calls
        calls = range_calls(self._root, 1, 999, self._get_text)
        self.assertIsInstance(calls, list)
        # fetch_data, process, write_log, bool are calls
        self.assertGreater(len(calls), 0)
        callees = [c['callee'] for c in calls]
        self.assertTrue(any('fetch_data' in (c or '') for c in callees))

    def test_collect_exits_on_root_node(self):
        from reveal.adapters.ast.nav import collect_exits
        exits = collect_exits(self._root, 1, 999, self._get_text)
        self.assertIsInstance(exits, list)

    def test_collect_deps_on_root_node(self):
        from reveal.adapters.ast.nav import collect_deps
        deps = collect_deps(self._root, 1, 999, self._get_text)
        self.assertIsInstance(deps, list)

    def test_collect_mutations_on_root_node(self):
        from reveal.adapters.ast.nav import collect_mutations
        mutations = collect_mutations(self._root, 1, 999, self._get_text)
        self.assertIsInstance(mutations, list)

    def test_element_outline_on_root_node(self):
        from reveal.adapters.ast.nav import element_outline
        items = element_outline(self._root, self._get_text, max_depth=3)
        self.assertIsInstance(items, list)

    def test_var_flow_range_filtering_on_root(self):
        from reveal.adapters.ast.nav import var_flow
        all_events = var_flow(self._root, 'errormsg', 1, 999, self._get_text)
        # Narrow to first 2 lines — errormsg starts at line 1
        narrow = var_flow(self._root, 'errormsg', 1, 2, self._get_text)
        self.assertLessEqual(len(narrow), len(all_events))


# ===========================================================================
# _collect_identifier_names (internal helper)
# ===========================================================================

class TestBack638JavaConstructorBoundary(unittest.TestCase):
    def test_constructor_extracted_as_its_own_function(self):
        import pathlib
        import tempfile
        from reveal.analyzers.java import JavaAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'Foo.java'
            f.write_text(
                "class Foo {\n"
                "    private final int x;\n"
                "    public Foo(int x) {\n"
                "        this.x = x;\n"
                "    }\n"
                "    public void unrelatedMethod() {\n"
                "        System.out.println(\"unrelated\");\n"
                "    }\n"
                "}\n"
            )
            structure = JavaAnalyzer(str(f)).get_structure()
            names = [fn['name'] for fn in structure.get('functions', [])]
            self.assertIn('Foo', names)
            self.assertIn('unrelatedMethod', names)

    def test_constructor_boundary_excludes_sibling_method_body(self):
        import pathlib
        import tempfile
        from reveal.analyzers.java import JavaAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'Foo.java'
            f.write_text(
                "class Foo {\n"
                "    private final int x;\n"
                "    public Foo(int x) {\n"
                "        this.x = x;\n"
                "    }\n"
                "    public void unrelatedMethod() {\n"
                "        System.out.println(\"unrelated\");\n"
                "    }\n"
                "}\n"
            )
            structure = JavaAnalyzer(str(f)).get_structure()
            ctor = next(fn for fn in structure['functions'] if fn['name'] == 'Foo')
            # Regression: pre-fix, this fell through to class_declaration and
            # spanned the whole class body (through unrelatedMethod's line 8).
            self.assertLess(ctor['line_end'], 6)

    def test_constructor_declaration_in_def_nodes_taxonomy(self):
        # node_taxonomy.py side of the same fix — used by --scope's ancestor
        # chain and the composite-set KEYWORD_LABEL guard rail.
        from reveal.adapters.ast.node_taxonomy import DEF_NODES, KEYWORD_LABEL
        self.assertIn('constructor_declaration', DEF_NODES)
        self.assertEqual(KEYWORD_LABEL['constructor_declaration'], 'DEF')


# ─── BACK-641: C++ operator_name/destructor_name missing from
# _find_identifier_in_tree's name-kind lists ────────────────────────────────
# An out-of-line operator overload (`Vector2::operator==(...) { ... }`)
# declarator-nests a qualified_identifier whose `name` child is an
# `operator_name` node — not `identifier`/`field_identifier` — so the
# qualified_identifier join dropped it and returned bare "Vector2" (the
# scope qualifier only), colliding with the constructor and every other
# operator on the type. An inline destructor (`~Ref() { ... }`) name-nodes
# as `destructor_name` wrapping an inner `identifier`; plain recursion
# skipped past destructor_name and returned the inner identifier's bare
# text "Ref" (dropping the "~"), again colliding with the constructor.
# Found via the C++ sideeffects-recall-oracle loop (BACK-547 fourth
# language) while sanity-checking constructor/destructor coverage before
# trusting any recall numbers — same failure family as BACK-638, different
# mechanism (name-extraction join list, not a missing FUNCTION_NODE_TYPES
# entry).

class TestBack641CppOperatorAndDestructorNaming(unittest.TestCase):
    def test_out_of_line_operator_overload_named_correctly(self):
        import pathlib
        import tempfile
        from reveal.analyzers.cpp import CppAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'vec.cpp'
            f.write_text(
                "struct Vec {\n"
                "    int x;\n"
                "    bool operator==(const Vec &o) const;\n"
                "};\n"
                "bool Vec::operator==(const Vec &o) const {\n"
                "    return x == o.x;\n"
                "}\n"
            )
            structure = CppAnalyzer(str(f)).get_structure()
            names = [fn['name'] for fn in structure.get('functions', [])]
            self.assertIn('Vec::operator==', names)
            # Regression: pre-fix this collapsed to bare "Vec" (the scope
            # qualifier only), colliding with any constructor.
            self.assertNotIn('Vec', names)

    def test_inline_destructor_named_with_tilde(self):
        import pathlib
        import tempfile
        from reveal.analyzers.cpp import CppAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'widget.cpp'
            f.write_text(
                "class Widget {\n"
                "public:\n"
                "    Widget() {}\n"
                "    ~Widget() {}\n"
                "};\n"
            )
            structure = CppAnalyzer(str(f)).get_structure()
            names = [fn['name'] for fn in structure.get('functions', [])]
            self.assertIn('Widget', names)      # constructor
            self.assertIn('~Widget', names)      # destructor, distinct name
            # Regression: pre-fix both collapsed to the same bare "Widget",
            # making them indistinguishable to name-based lookup.
            self.assertEqual(names.count('Widget'), 1)


# ─── BACK-547 sixth loop (Ruby): `singleton_method` missing from
# FUNCTION_NODE_TYPES ───────────────────────────────────────────────────────
# `def self.foo` / `def Class.foo` parses to a DISTINCT tree-sitter-ruby node
# kind, `singleton_method`, not a same-name variant of `method` (`def foo`).
# BACK-451/477 had already added `singleton_method` to CHILD_NODE_TYPES (so
# dotted hierarchical lookup like `Class.method_name` worked), but never to
# FUNCTION_NODE_TYPES — the same cross-taxonomy fragmentation as BACK-638
# (Java/C# constructors) and BACK-519 (JS class-field arrows). Every
# `def self.x` method — the dominant Ruby/Rails idiom for module-level
# utility/service-object entry points — was entirely invisible to
# `--outline`/`get_structure()`, and a bare (non-dotted) name lookup for one
# failed outright even when the name was unique in the file. Found via the
# Ruby sideeffects-recall-oracle loop on real Discourse source: `lib/
# discourse.rb` (107 `def self.` methods) showed only 6 functions in
# `--outline` pre-fix.

class TestBack547RubySingletonMethodExtraction(unittest.TestCase):
    def _analyzer(self, src):
        import pathlib
        import tempfile
        from reveal.analyzers.ruby import RubyAnalyzer
        d = tempfile.TemporaryDirectory()
        f = pathlib.Path(d.name) / 'foo.rb'
        f.write_text(src)
        return RubyAnalyzer(str(f)), d  # keep tempdir alive via returned handle

    def test_module_level_def_self_extracted(self):
        analyzer, _tmp = self._analyzer(
            "module Discourse\n"
            "  class Utils\n"
            "    def self.execute_command(*command)\n"
            "      1\n"
            "    end\n"
            "  end\n"
            "end\n"
        )
        structure = analyzer.get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        # Regression: pre-fix, `singleton_method` wasn't in FUNCTION_NODE_TYPES
        # at all, so this method never appeared in the flat functions list.
        self.assertIn('execute_command', names)

    def test_def_self_and_class_shovel_self_both_extracted(self):
        # `def self.foo` (singleton_method) and `class << self; def foo; end;
        # end` (method, nested in singleton_class) are two different Ruby
        # idioms for the same thing -- both must be visible.
        analyzer, _tmp = self._analyzer(
            "class Foo\n"
            "  def self.bar\n"
            "    1\n"
            "  end\n"
            "\n"
            "  class << self\n"
            "    def baz\n"
            "      2\n"
            "    end\n"
            "  end\n"
            "end\n"
        )
        structure = analyzer.get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        self.assertIn('bar', names)
        self.assertIn('baz', names)

    def test_unique_name_lookup_no_longer_errors(self):
        # The user-facing symptom: `reveal file.rb method_name` erroring
        # "could not find function or method" for a `def self.x` method whose
        # name was unique in the file (confirmed live on Discourse's
        # lib/discourse.rb:allow_dev_populate?, plugins/discourse-ai/.../
        # discourse_meta_search.rb:categories, lib/stylesheet/compiler.rb:
        # compile_asset).
        analyzer, _tmp = self._analyzer(
            "class Discourse\n"
            "  def self.allow_dev_populate?\n"
            "    ENV[\"ALLOW_DEV_POPULATE\"] == \"1\"\n"
            "  end\n"
            "end\n"
        )
        structure = analyzer.get_structure()
        names = [fn['name'] for fn in structure.get('functions', [])]
        self.assertIn('allow_dev_populate?', names)


# ─── BACK-547 sixth loop (Ruby): ActiveRecord CRUD verbs + FileUtils verb gaps
# in _TAXONOMY_BY_LANG['ruby'] ───────────────────────────────────────────────
# `.where`/`.pluck`/`.find_by`/`.update_all`/`.delete_all`/`.destroy_all` were
# previously declined as "too collision-prone" without corpus evidence;
# measured instead on real Discourse source (receiver-shape sampling found
# near-exclusively Model-constant/relation-shaped receivers, no unrelated-
# domain collision). `FileUtils.rm_f`/`.rm_rf` are distinct tokens from the
# existing `fileutils.rm` pattern under segment-boundary matching.

class TestBack651CSharpOperatorDeclaration(unittest.TestCase):
    """BACK-651 (found via BACK-547 C# recall-oracle pre-flight check):
    C# operator overloads (`public static bool operator ==(...)`) parse to
    their own distinct node kind, `operator_declaration`, not a variant of
    `method_declaration` -- and unlike BACK-638's constructor gap, the node
    has no identifier-shaped name child at all (the "name" is the raw
    operator-symbol token). Both the node-type gap and the missing
    name-extraction strategy needed fixing."""

    def test_operator_overload_extracted_with_name(self):
        import pathlib
        import tempfile
        from reveal.analyzers.csharp import CSharpAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'SearchResult.cs'
            f.write_text(
                "public readonly struct SearchResult\n"
                "{\n"
                "    public static bool operator ==(SearchResult left, SearchResult right)\n"
                "    {\n"
                "        return left.Equals(right);\n"
                "    }\n"
                "\n"
                "    public static bool operator !=(SearchResult left, SearchResult right)\n"
                "    {\n"
                "        return !left.Equals(right);\n"
                "    }\n"
                "}\n"
            )
            structure = CSharpAnalyzer(str(f)).get_structure()
            names = [fn['name'] for fn in structure.get('functions', [])]
            self.assertIn('operator ==', names)
            self.assertIn('operator !=', names)

    def test_operator_boundary_excludes_sibling_operator_body(self):
        import pathlib
        import tempfile
        from reveal.analyzers.csharp import CSharpAnalyzer
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'SearchResult.cs'
            f.write_text(
                "public readonly struct SearchResult\n"
                "{\n"
                "    public static bool operator ==(SearchResult left, SearchResult right)\n"
                "    {\n"
                "        return left.Equals(right);\n"
                "    }\n"
                "\n"
                "    public static bool operator !=(SearchResult left, SearchResult right)\n"
                "    {\n"
                "        return !left.Equals(right);\n"
                "    }\n"
                "}\n"
            )
            structure = CSharpAnalyzer(str(f)).get_structure()
            op_eq = next(fn for fn in structure['functions'] if fn['name'] == 'operator ==')
            # Regression: pre-fix, operator_declaration was entirely absent
            # from FUNCTION_NODE_TYPES, so this element didn't exist at all.
            self.assertLess(op_eq['line_end'], 8)

    def test_operator_declaration_in_def_nodes_taxonomy(self):
        from reveal.adapters.ast.node_taxonomy import DEF_NODES, KEYWORD_LABEL
        self.assertIn('operator_declaration', DEF_NODES)
        self.assertEqual(KEYWORD_LABEL['operator_declaration'], 'DEF')


# ─── BACK-650: _find_element_node returned the first tree-order match for a
# bare name, with no disambiguation when multiple functions share a name —
# overloading and abstract+concrete-override pairs both hit this. Found via
# the C# sideeffects-recall-oracle loop (BACK-547 eighth loop) on real
# Jellyfin source: an abstract method and its real override shared a name
# (bare lookup returned the bodyless abstract one, hiding a LogError call),
# and an expression-bodied overload wrapper shared a name with the real
# block-bodied overload (bare lookup returned the wrapper, hiding a
# Thread.Sleep call). Fixed by preferring a candidate with a 'block'-kind
# direct child (a real body) over one without, falling back to first-match
# only when every same-named candidate is equally block-bodied or equally
# bodyless (true overloads with no signal to disambiguate).

class TestBack650OverloadDisambiguation(unittest.TestCase):
    def test_abstract_and_override_same_name_resolves_to_override(self):
        import pathlib
        import tempfile
        from reveal.analyzers.csharp import CSharpAnalyzer
        from reveal.file_handler import _find_element_node
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'BaseTunerHost.cs'
            f.write_text(
                "abstract class BaseTunerHost\n"
                "{\n"
                "    protected abstract Task<List<MediaSourceInfo>> GetChannelStreamMediaSources(\n"
                "        string channelId, CancellationToken cancellationToken);\n"
                "}\n"
                "\n"
                "class LiveTvTunerHost : BaseTunerHost\n"
                "{\n"
                "    public async Task<List<MediaSourceInfo>> GetChannelStreamMediaSources(\n"
                "        string channelId, CancellationToken cancellationToken)\n"
                "    {\n"
                "        try\n"
                "        {\n"
                "            return await GetSources(channelId);\n"
                "        }\n"
                "        catch (Exception ex)\n"
                "        {\n"
                "            Logger.LogError(ex, \"failed\");\n"
                "            throw;\n"
                "        }\n"
                "    }\n"
                "}\n"
            )
            analyzer = CSharpAnalyzer(str(f))
            node = _find_element_node(analyzer, 'GetChannelStreamMediaSources')
            self.assertIsNotNone(node)
            # Regression: pre-fix, this returned the abstract (bodyless)
            # declaration at line 3, a 1-line no-op range that hides the
            # override's entire body including the LogError call.
            self.assertGreater(_zero_arg(node, 'end_position').row, 4)

    def test_expression_bodied_and_block_bodied_overload_resolves_to_block(self):
        import pathlib
        import tempfile
        from reveal.analyzers.csharp import CSharpAnalyzer
        from reveal.file_handler import _find_element_node
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'ProgressiveFileStream.cs'
            f.write_text(
                "class ProgressiveFileStream : Stream\n"
                "{\n"
                "    public override int Read(byte[] buffer, int offset, int count)\n"
                "        => Read(buffer.AsSpan(offset, count));\n"
                "\n"
                "    public int Read(Span<byte> buffer)\n"
                "    {\n"
                "        var sw = Stopwatch.StartNew();\n"
                "        while (_stream.Length <= _position)\n"
                "        {\n"
                "            Thread.Sleep(50);\n"
                "        }\n"
                "        return 0;\n"
                "    }\n"
                "}\n"
            )
            analyzer = CSharpAnalyzer(str(f))
            node = _find_element_node(analyzer, 'Read')
            self.assertIsNotNone(node)
            # Regression: pre-fix, this returned the expression-bodied
            # wrapper at line 3-4, silently hiding the Thread.Sleep effect
            # in the real block-bodied overload below it.
            self.assertGreater(_zero_arg(node, 'end_position').row, 5)

    def test_true_overload_with_no_disambiguating_signal_falls_back_to_first(self):
        # Both candidates are equally block-bodied (real overloads, no
        # abstract/expression-bodied sibling) -- no signal to disambiguate,
        # so first tree-order match is returned, same as pre-fix behavior.
        import pathlib
        import tempfile
        from reveal.analyzers.csharp import CSharpAnalyzer
        from reveal.file_handler import _find_element_node
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'Overloads.cs'
            f.write_text(
                "class Overloads\n"
                "{\n"
                "    public void Write(string s)\n"
                "    {\n"
                "        Console.WriteLine(s);\n"
                "    }\n"
                "\n"
                "    public void Write(int i)\n"
                "    {\n"
                "        Console.WriteLine(i.ToString());\n"
                "    }\n"
                "}\n"
            )
            analyzer = CSharpAnalyzer(str(f))
            node = _find_element_node(analyzer, 'Write')
            self.assertIsNotNone(node)
            self.assertEqual(
                _zero_arg(node, 'start_position').row, 2
            )  # first Write(string s), line 3

    def test_pick_best_candidate_single_candidate_returned_directly(self):
        from reveal.file_handler import _pick_best_candidate
        self.assertEqual(_pick_best_candidate(['only']), 'only')

    def test_dart_abstract_and_override_same_name_resolves_to_override(self):
        # BACK-729: the plain 'block'-child scan above can never see a Dart
        # method's real body -- Dart's function_signature/function_body pair
        # are disjoint SIBLINGS, not parent/child (see
        # treesitter.py:_function_end_node's docstring). Without resolving
        # each candidate's paired body first, an interface+impl same-name
        # pair always fell through to the first tree-order candidate: the
        # bodyless abstract signature.
        import pathlib
        import tempfile
        from reveal.analyzers.dart import DartAnalyzer
        from reveal.file_handler import _find_element_node
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'parser.dart'
            f.write_text(
                "abstract class Parser {\n"
                "  int parse(String input);\n"
                "}\n"
                "\n"
                "class RealParser implements Parser {\n"
                "  @override\n"
                "  int parse(String input) {\n"
                "    return input.length;\n"
                "  }\n"
                "}\n"
            )
            analyzer = DartAnalyzer(str(f))
            node = _find_element_node(analyzer, 'parse')
            self.assertIsNotNone(node)
            # Regression: pre-fix, this returned the abstract signature at
            # line 2 (a 1-line node with no sibling body), not the real
            # implementation at line 7-9.
            self.assertEqual(_zero_arg(node, 'start_position').row, 6)  # 0-indexed: line 7

    def test_dart_abstract_and_override_same_name_bare_extraction_resolves_to_override(self):
        # BACK-771: display.element._find_named_node (the bare `reveal
        # file.dart name` extraction path, independent of file_handler's
        # _find_element_node fixed by BACK-729) had zero disambiguation --
        # plain next(...) over tree-order always returned the first match,
        # the bodyless abstract signature, never the concrete override.
        import pathlib
        import tempfile
        from reveal.analyzers.dart import DartAnalyzer
        from reveal.display.element import _find_named_node
        with tempfile.TemporaryDirectory() as d:
            f = pathlib.Path(d) / 'parser.dart'
            f.write_text(
                "abstract class Parser {\n"
                "  int parse(String input);\n"
                "}\n"
                "\n"
                "class RealParser implements Parser {\n"
                "  @override\n"
                "  int parse(String input) {\n"
                "    return input.length;\n"
                "  }\n"
                "}\n"
            )
            analyzer = DartAnalyzer(str(f))
            node = _find_named_node(analyzer, 'function_signature', 'parse')
            self.assertIsNotNone(node)
            # Regression: pre-fix, this returned the abstract signature at
            # line 2 (a 1-line node with no sibling body), not the real
            # implementation at line 7-9.
            self.assertEqual(_zero_arg(node, 'start_position').row, 6)  # 0-indexed: line 7


# ─── BACK-547 ninth loop (Rust sideeffects-recall-oracle, real-corpus
# measurement on Meilisearch's milli engine): `macro_invocation` (Rust's
# grammar node for `tracing::debug!(...)`, `println!(...)`, etc.) was
# entirely absent from CALL_NODE_TYPES -- every macro call was invisible to
# --calls/--sideeffects/--boundary, not just a taxonomy gap. Since Rust
# logging is done almost exclusively via macros (the `tracing`/`log`
# crates), this was the single dominant recall gap (31.58%->68.42% recall
# jump from this fix alone, before any taxonomy change). Fixed by adding
# 'macro_invocation' to CALL_NODE_TYPES and 'token_tree' (its argument
# container, not 'arguments') to _extract_first_arg's recognized kinds --
# the existing generic callee-extraction fallback already produced the
# right callee string with no further special-casing needed.

class TestBack547RustMacroInvocation(unittest.TestCase):
    def _parse(self, src):
        parser = ts.get_parser('rust')
        content_bytes = src.encode('utf-8')
        tree = ts_parse(parser, src)
        root = tree_root(tree)

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')
        return root, get_text

    def test_scoped_macro_call_visible_to_range_calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        root, get_text = self._parse(textwrap.dedent("""
        fn foo() {
            tracing::debug!("processing {} docs", 5);
        }
        """).lstrip('\n'))
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        # Regression: pre-fix, macro_invocation wasn't in CALL_NODE_TYPES at
        # all, so this list was empty -- the macro call was invisible.
        self.assertIn('tracing::debug', callees)

    def test_bare_macro_call_visible_to_range_calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        root, get_text = self._parse(textwrap.dedent("""
        fn foo() {
            println!("world");
        }
        """).lstrip('\n'))
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        self.assertIn('println', callees)

    def test_tracing_macro_classified_as_log_effect(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        root, get_text = self._parse(textwrap.dedent("""
        fn foo() {
            tracing::warn!("Attempt #{}, retrying after {}ms.", 1, 50);
            std::thread::sleep(std::time::Duration::from_millis(50));
        }
        """).lstrip('\n'))
        effects = collect_effects(root, 1, 999, get_text, language='rust')
        kinds = [(e['line'], e['kind']) for e in effects]
        self.assertIn((2, 'log'), kinds)
        self.assertIn((3, 'sleep'), kinds)

    def test_macro_invocation_in_call_node_types(self):
        from reveal.treesitter import CALL_NODE_TYPES
        self.assertIn('macro_invocation', CALL_NODE_TYPES)


class TestBack547KotlinDaoReceiverSuffix(unittest.TestCase):
    """Kotlin/Java's `xxxDao`/`XxxDao` naming convention (Data Access Object)
    is the dominant db-access receiver in Room/SQLDelight-backed repository
    layers, but the method vocabulary is open-ended (generated per-query
    names like `getShowWithIdOrThrow`, `entriesForShowIdWithSendPendingActions`)
    -- no fixed pattern list can enumerate it. Corpus (Tivi's data/ module,
    sideeffects-recall-oracle/kotlin, tenth language): 27 files, 100+ call
    sites, all unclassified before this fix. Fixed via a new suffix-match
    receiver mechanism (`_classify_by_receiver_suffix`), since the receiver is
    a whole identifier like `showdao`/`seasonsdao`, never the bare word `dao`
    alone (unlike the existing exact-match `_RECEIVER_TAXONOMY`)."""

    def test_dao_suffixed_receiver_classified_db(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('showDao.getShowWithIdOrThrow'), 'db')
        self.assertEqual(
            classify_call('episodeWatchEntryDao.entriesForShowIdWithSendPendingActions'),
            'db',
        )

    def test_bare_dao_receiver_also_classified(self):
        # A variable literally named `dao` (common: `private val dao: ShowDao`)
        # is itself a valid db receiver -- suffix match correctly includes the
        # zero-prefix case, same as the exact-match _RECEIVER_TAXONOMY would.
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertEqual(classify_call('dao.foo'), 'db')

    def test_non_dao_suffix_not_classified(self):
        from reveal.adapters.ast.nav_effects import classify_call
        self.assertIsNone(classify_call('showQueries.getShowWithId'))
        self.assertIsNone(classify_call('showDaoFactory.build'))


class TestScalaInstanceExpressionCalls(unittest.TestCase):
    """BACK-718/BACK-720: Scala's `new Foo(args)` parses to a DISTINCT
    tree-sitter node kind, 'instance_expression', not PHP/C#'s
    'object_creation_expression' -- entirely invisible to --calls/
    --sideeffects/--boundary before this loop despite the identical source
    shape. Fixed via a CALL_NODE_TYPES addition (treesitter.py) plus a
    paired callee-extraction case (nav_calls.py:
    _extract_scala_instance_callee), mirroring the existing PHP/C#
    "new <Name>" convention exactly."""

    def test_new_expression_visible_to_range_calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        tree, root, get_text, content_bytes = _parse_scala("""
        object T {
          def foo(): Unit = {
            val f = new File("x")
            val out = new FileOutputStream(f)
          }
        }
        """)
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        self.assertIn('new File', callees)
        self.assertIn('new FileOutputStream', callees)

    def test_new_expression_effects_classified(self):
        from reveal.adapters.ast.nav_effects import collect_effects
        tree, root, get_text, content_bytes = _parse_scala("""
        object T {
          def foo(): Unit = {
            val f = new File("x")
          }
        }
        """)
        effects = collect_effects(root, 1, 999, get_text, language='scala')
        kinds = {e['kind'] for e in effects}
        self.assertIn('file', kinds)


class TestSwiftConstructorExpressionCalls(unittest.TestCase):
    """BACK-730 (tenth calls:// language, pre-flight grammar dump): Swift's
    `<callee><TypeArgs>(args)` -- both a generic function call
    (`identity<Int>(5)`) AND a generic type initializer (`Array<Int>()`) --
    parses to a DISTINCT tree-sitter node kind, 'constructor_expression',
    not call_expression. Entirely invisible to --calls/--sideeffects/
    --boundary before this fix despite being a common shape in any Swift
    codebase using generics. Fixed via a CALL_NODE_TYPES addition
    (treesitter.py) plus a paired callee-extraction case (nav_calls.py:
    _extract_swift_constructor_callee), which emits the bare callee name
    (no "new " prefix, unlike Scala/PHP's object_creation/instance_expression)
    since this node isn't always semantically a construction."""

    def test_generic_function_call_visible_to_range_calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        tree, root, get_text, content_bytes = _parse_swift("""
        func run() {
            let x = identity<Int>(5)
        }
        """)
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        self.assertIn('identity', callees)

    def test_generic_type_initializer_visible_to_range_calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        tree, root, get_text, content_bytes = _parse_swift("""
        func run() {
            let a = Array<Int>()
            let d = Dictionary<String, Int>()
        }
        """)
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        self.assertIn('Array', callees)
        self.assertIn('Dictionary', callees)


class TestSwiftInitDeinitDeclaration(unittest.TestCase):
    """BACK-730 (tenth calls:// language, pre-flight grammar dump follow-up):
    Swift `init(...) { ... }` / `deinit { ... }` parse to their OWN distinct
    node kinds, `init_declaration`/`deinit_declaration`, not a variant of
    `function_declaration` (plain `func` methods) -- same class of gap as
    BACK-638 (Java/C# constructors) and BACK-724 (GDScript
    `constructor_definition`). Before this fix, every Swift
    initializer/deinitializer -- arguably the most common lifecycle method
    in any Swift OOP codebase -- was entirely absent from
    --outline/get_structure(), and every call made from inside one had no
    caller scope to attribute to at all (a total edge loss to calls://, not
    just a misattribution). Neither node has an identifier child (like
    GDScript's `_init`, the node KIND itself carries the fixed lifecycle
    name), so a new `_get_node_name` special case was needed alongside the
    FUNCTION_NODE_TYPES addition."""

    def test_init_visible_in_range_calls_via_call_node(self):
        # Sanity: attribute-call extraction inside init/deinit bodies works
        # independent of the node-name fix below (confirms the gap is
        # purely name/element-lookup, not call extraction itself).
        from reveal.adapters.ast.nav_calls import range_calls
        tree, root, get_text, content_bytes = _parse_swift("""
        class Foo {
            init() {
                setup()
            }
            deinit {
                cleanup()
            }
        }
        """)
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        self.assertIn('setup', callees)
        self.assertIn('cleanup', callees)

    def test_init_and_deinit_extracted_by_swift_analyzer_outline(self):
        import os
        import tempfile
        from reveal.analyzers.swift import SwiftAnalyzer

        code = textwrap.dedent("""\
            class Foo {
                init() {
                    setup()
                }
                deinit {
                    cleanup()
                }
                func greet() {
                    speak()
                }
            }
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name
        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()
            func_names = [fn['name'] for fn in structure.get('functions', [])]
            # Before the fix, 'init'/'deinit' were silently absent here --
            # only 'greet' showed up in --outline/get_structure().
            self.assertIn('init', func_names)
            self.assertIn('deinit', func_names)
            self.assertIn('greet', func_names)
            # Each caller's own calls list should attribute its call to
            # itself, not fall through to being unattributed/dropped.
            by_name = {fn['name']: fn for fn in structure['functions']}
            self.assertIn('setup', by_name['init'].get('calls', []))
            self.assertIn('cleanup', by_name['deinit'].get('calls', []))
        finally:
            os.unlink(temp_path)


class TestSwiftPrefixExpressionCallee(unittest.TestCase):
    """BACK-730 (tenth calls:// language, 8/bucket measurement): Swift
    `!isRunning(x)` (logical negation of a call's boolean result -- a
    common predicate-negation idiom) parses the whole `!isRunning` as one
    `prefix_expression(bang, simple_identifier)` callee node, not a plain
    identifier. Taking the whole node's raw text (old behavior) left the
    leading "!" in the callee string, and `_bare_callee_name` has no
    separator to act on a bare identifier, so the index key was literally
    "!isRunning", never matching a bare `?target=isRunning` lookup. Real
    corpus miss: SignalServiceKit's `BackupAttachmentCoordinator.swift`
    `kickOffNextOperation`, which calls `!isRunning(...)` four times. Fixed
    by recursing into `prefix_expression`'s last child (the operand) in
    `_callee_name_from_node`, which also covers Swift's `.foo(...)`
    implicit-member call shape (same node kind, different operator token)
    without changing its already-correct behavior."""

    def test_negated_call_strips_bang_from_callee(self):
        from reveal.analyzers.swift import SwiftAnalyzer
        import os
        import tempfile

        code = textwrap.dedent("""\
            func kickOffNextOperation() {
                if needsToRun(.thumbnail) && !isRunning(.thumbnail) {
                    runOperation(.thumbnail)
                }
            }
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name
        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()
            calls = structure['functions'][0]['calls']
            # Before the fix this was '!isRunning', not 'isRunning'.
            self.assertIn('isRunning', calls)
            self.assertNotIn('!isRunning', calls)
        finally:
            os.unlink(temp_path)

    def test_implicit_member_call_still_resolves_correctly(self):
        # Sanity: the same prefix_expression node shape covers `.foo(...)`
        # (implicit-member call, leading '.' not '!') -- confirm the fix
        # doesn't regress this already-working case.
        from reveal.analyzers.swift import SwiftAnalyzer
        import os
        import tempfile

        code = textwrap.dedent("""\
            func run() {
                let x: E = .foo(timestamp: 5)
            }
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name
        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()
            calls = structure['functions'][0]['calls']
            self.assertIn('foo', calls)
        finally:
            os.unlink(temp_path)


class TestSwiftOperatorOverloadName(unittest.TestCase):
    """BACK-730 (tenth calls:// language, 8/bucket measurement): Swift
    operator overloads (`static func -(left: CGSize, right: CGSize) ->
    CGSize`, `static func *(...)`) name themselves with a literal
    operator-symbol token whose tree-sitter KIND literally IS the operator
    text (e.g. kind '-'), not an identifier-family kind any `_name_via_*`
    strategy recognized -- and Swift's grammar has no wrapping
    parameter-list node kind at all, so `_name_via_param_adjacent` never
    even applies. Before this fix, every operator overload (CGPoint/CGSize
    arithmetic -- a common idiom in any Swift codebase with custom
    geometry/value types) was entirely absent from
    --outline/get_structure(), so calls made from inside one had no caller
    scope to attribute to at all. Real corpus example: SignalServiceKit's
    `Util/UIView+OWS.swift`, five operator overloads (`-`, `*`, `*=` twice
    more)."""

    def test_operator_overload_extracted_with_symbol_name(self):
        from reveal.analyzers.swift import SwiftAnalyzer
        import os
        import tempfile

        code = textwrap.dedent("""\
            struct CGSize {
                static func -(left: CGSize, right: CGSize) -> CGSize {
                    return subtract(left, right)
                }
                static func *(left: CGSize, right: CGFloat) -> CGSize {
                    return multiply(left, right)
                }
            }
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.swift', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name
        try:
            analyzer = SwiftAnalyzer(temp_path)
            structure = analyzer.get_structure()
            func_names = [fn['name'] for fn in structure.get('functions', [])]
            # Before the fix, both operator overloads were silently absent
            # from --outline/get_structure() entirely.
            self.assertIn('-', func_names)
            self.assertIn('*', func_names)
            by_name = {fn['name']: fn for fn in structure['functions']}
            self.assertIn('subtract', by_name['-'].get('calls', []))
            self.assertIn('multiply', by_name['*'].get('calls', []))
        finally:
            os.unlink(temp_path)


class TestBack724GdscriptConstructorDefinition(unittest.TestCase):
    """BACK-718/BACK-724 GDScript pre-flight structural check: `func _init(...)`
    parses to its own distinct node kind, `constructor_definition`, not a
    variant of `function_definition` -- the same class of gap as BACK-638
    (Java/C# constructors) and BACK-651 (C# operator_declaration), but more
    total: `_init` was entirely absent from --outline/get_structure() (no
    wrapping class_declaration for a top-level script to fall through to
    either) and a direct name lookup errored outright. Verified live on
    samples/gdscript_pixelorama/src/Classes/SteamManager.gd (a real corpus
    `env` oracle positive: `_init` sets OS.set_environment(...))."""

    def test_init_visible_in_range_calls_via_call_node(self):
        # Sanity: attribute-call extraction inside a constructor body works
        # independent of the node-name fix below (this part was never
        # broken -- confirms the gap is purely name/element-lookup, not call
        # extraction).
        from reveal.adapters.ast.nav_calls import range_calls
        tree, root, get_text, content_bytes = _parse_gdscript("""
        extends Node

        func _init():
            OS.set_environment("SteamAppID", "1")
        """)
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        self.assertIn('OS.set_environment', callees)

    def test_init_extracted_by_gdscript_analyzer_outline(self):
        import os
        import tempfile
        from reveal.analyzers.gdscript import GDScriptAnalyzer

        code = textwrap.dedent("""\
            extends Node

            func _init():
                OS.set_environment("SteamAppID", "1")

            func _ready():
                pass
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name
        try:
            analyzer = GDScriptAnalyzer(temp_path)
            structure = analyzer.get_structure()
            func_names = [fn['name'] for fn in structure.get('functions', [])]
            # Before the fix, '_init' was silently absent here -- only
            # '_ready' showed up in --outline/get_structure().
            self.assertIn('_init', func_names)
            self.assertIn('_ready', func_names)
        finally:
            os.unlink(temp_path)

    def test_init_direct_name_lookup_and_sideeffects(self):
        import os
        import tempfile
        from reveal.analyzers.gdscript import GDScriptAnalyzer

        code = textwrap.dedent("""\
            extends Node

            func _init():
                OS.set_environment("SteamAppID", "1")
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.gd', delete=False, encoding='utf-8') as f:
            f.write(code)
            temp_path = f.name
        try:
            from reveal.file_handler import _find_element_node

            analyzer = GDScriptAnalyzer(temp_path)
            # Before the fix this returned None: '_init' was not a
            # recognized FUNCTION_NODE_TYPES member, so bare-name element
            # lookup fell through entirely (unlike BACK-638's Java/C# gap,
            # which at least fell through to the enclosing class body).
            node = _find_element_node(analyzer, '_init')
            self.assertIsNotNone(node)
        finally:
            os.unlink(temp_path)


class TestBack726TsxHocWrappedComponent(unittest.TestCase):
    """BACK-718/BACK-726 (sideeffects-recall-oracle/tsx, eighteenth and final
    breadth-program language) pre-flight structural check: a named component
    wrapped in a higher-order call --
    `const Name = React.forwardRef((props, ref) => {...})` / `React.memo(...)`
    -- is the dominant "advanced" component-declaration shape in modern React/
    TSX (47 corpus occurrences of forwardRef/memo alone in
    samples/tsx/excalidraw). The variable_declarator's value child is a
    `call_expression` (the HOC call), never a bare `arrow_function`/
    `function_expression`/`generator_function` directly, so
    `_arrow_or_fn_value`'s direct-child-kind check never matched at all --
    entirely absent from --outline/get_structure() and erroring outright on a
    direct bare-name lookup. Verified live on real corpus files
    (QuickSearch.tsx, ToolButton.tsx, Island.tsx): fixed via
    `_call_wrapped_function_literal`, which looks one level into the call's
    own direct argument list for the sole function-literal argument."""

    def test_forwardref_wrapped_component_extracted_by_outline(self):
        import os
        import tempfile
        from reveal.registry import get_analyzer

        code = textwrap.dedent("""\
            import React from "react";

            export const Named = React.forwardRef<HTMLDivElement, {}>(
              (props, ref) => {
                console.log("mounted");
                return <div ref={ref} />;
              },
            );
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsx', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = f.name
        try:
            cls = get_analyzer(path)
            analyzer = cls(path)
            structure = analyzer.get_structure()
            names = {fn['name'] for fn in structure.get('functions', [])}
            # Before the fix, 'Named' was silently absent here.
            self.assertIn('Named', names)
        finally:
            os.unlink(path)

    def test_forwardref_wrapped_component_direct_lookup_and_sideeffects(self):
        import os
        import tempfile
        from reveal.file_handler import _find_element_node
        from reveal.registry import get_analyzer

        code = textwrap.dedent("""\
            import React from "react";

            export const Named = React.forwardRef<HTMLDivElement, {}>(
              (props, ref) => {
                console.log("mounted");
                return <div ref={ref} />;
              },
            );
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsx', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = f.name
        try:
            cls = get_analyzer(path)
            analyzer = cls(path)
            # Before the fix this errored: "could not find function or
            # method 'Named'" -- the HOC-wrapped arrow had no name-lookup
            # path at all.
            node = _find_element_node(analyzer, 'Named')
            self.assertIsNotNone(node)
        finally:
            os.unlink(path)

    def test_memo_wrapped_component_extracted_by_outline(self):
        """React.memo(...) shares the exact same call_expression-wrapping
        shape as forwardRef -- confirms the fix isn't forwardRef-specific."""
        import os
        import tempfile
        from reveal.registry import get_analyzer

        code = textwrap.dedent("""\
            import React from "react";

            export const Widget = React.memo(({ theme }: { theme: string }) => {
              return <div>{theme}</div>;
            });
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsx', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = f.name
        try:
            cls = get_analyzer(path)
            analyzer = cls(path)
            structure = analyzer.get_structure()
            names = {fn['name'] for fn in structure.get('functions', [])}
            self.assertIn('Widget', names)
        finally:
            os.unlink(path)

    def test_curried_hoc_without_function_literal_stays_unmatched(self):
        """A curried HOC call like `connect(mapStateToProps)(Component)` has
        no function-literal argument at the outer call level (Component is
        just an identifier reference) -- must NOT be mis-attributed; the
        fix only fires when there's exactly one function-literal argument to
        find."""
        from reveal.treesitter import TreeSitterAnalyzer
        import os
        import tempfile
        from reveal.registry import get_analyzer

        code = textwrap.dedent("""\
            import { connect } from "react-redux";

            function Component(props) {
              return null;
            }

            const Wrapped = connect(mapStateToProps)(Component);
            """)
        with tempfile.NamedTemporaryFile(mode='w', suffix='.tsx', delete=False, encoding='utf-8') as f:
            f.write(code)
            path = f.name
        try:
            cls = get_analyzer(path)
            analyzer = cls(path)
            structure = analyzer.get_structure()
            names = {fn['name'] for fn in structure.get('functions', [])}
            self.assertIn('Component', names)
            self.assertNotIn('Wrapped', names)
        finally:
            os.unlink(path)


class TestBack740PhpScopedCallInNavCalls(unittest.TestCase):
    """BACK-740: PHP `scoped_call_expression` (self::/parent::/static::/
    Class::method()) was already handled in treesitter.py's calls:// path
    (BACK-736) but missing from nav_calls.py's range-based --calls/
    --sideeffects/--boundary path -- every scoped call there fell through
    to the generic extractor and returned the bare receiver ('self'/
    'parent'/'Foo'), dropping the method name entirely. Fixed by mirroring
    treesitter.py's _extract_php_scoped_call_callee logic into nav_calls.py.
    No behavioral test landed with the original fix (7e257d4) -- this is
    that missing coverage."""

    def test_self_scoped_call_visible_to_range_calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        tree, root, get_text, content_bytes = _parse_php("""
        <?php
        class Foo {
            function bar() {
                self::baz();
            }
        }
        """)
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        # Regression: pre-fix this returned bare 'self', dropping '::baz'.
        self.assertIn('self::baz', callees)
        self.assertNotIn('self', callees)

    def test_parent_and_class_scoped_calls_visible_to_range_calls(self):
        from reveal.adapters.ast.nav_calls import range_calls
        tree, root, get_text, content_bytes = _parse_php("""
        <?php
        class Foo extends Base {
            function bar() {
                parent::init();
                static::hook();
                Base::helper();
            }
        }
        """)
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        self.assertIn('parent::init', callees)
        self.assertIn('static::hook', callees)
        self.assertIn('Base::helper', callees)


class TestBack741RustTurbofishAndParenCalleeInNavCalls(unittest.TestCase):
    """BACK-741: Rust turbofish generic calls (`size_of::<u32>()`) and
    parenthesized callees (`(f)(args)`) were already handled in
    treesitter.py's calls:// path (BACK-733) but missing from nav_calls.py's
    range-based --calls/--sideeffects/--boundary path -- turbofish calls
    kept the '::<T>' generic suffix in the callee name, and paren-wrapped
    callees never resolved past the literal '(f)' text. Fixed by mirroring
    treesitter.py's generic_function/parenthesized_expression unwrap loop
    into nav_calls.py. No behavioral test landed with the original fix
    (7e257d4) -- this is that missing coverage."""

    def _parse(self, src):
        parser = ts.get_parser('rust')
        content_bytes = src.encode('utf-8')
        tree = ts_parse(parser, src)
        root = tree_root(tree)

        def get_text(node):
            return content_bytes[
                _zero_arg(node, 'start_byte') : _zero_arg(node, 'end_byte')
            ].decode('utf-8')
        return root, get_text

    def test_turbofish_call_strips_generic_suffix(self):
        from reveal.adapters.ast.nav_calls import range_calls
        root, get_text = self._parse(textwrap.dedent("""
        fn foo() {
            let n = size_of::<u32>();
        }
        """).lstrip('\n'))
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        # Regression: pre-fix this returned 'size_of::<u32>' verbatim.
        self.assertIn('size_of', callees)
        self.assertNotIn('size_of::<u32>', callees)

    def test_parenthesized_callee_resolves_to_bare_name(self):
        from reveal.adapters.ast.nav_calls import range_calls
        root, get_text = self._parse(textwrap.dedent("""
        fn foo() {
            let f = get_handler();
            (f)(1, 2);
        }
        """).lstrip('\n'))
        calls = range_calls(root, 1, 999, get_text)
        callees = [c['callee'] for c in calls]
        # Regression: pre-fix this never resolved past the literal '(f)' text.
        self.assertIn('f', callees)


if __name__ == '__main__':
    unittest.main()

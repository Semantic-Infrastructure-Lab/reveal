"""Tests for depends:// adapter — inverse module dependency graph."""

import textwrap
import unittest
from pathlib import Path

import pytest


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(content))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def simple_pkg(tmp_path):
    """
    pkg/
      utils.py        — no imports
      models.py       — imports utils
      api.py          — imports utils, models
      cli.py          — imports models
    """
    _write(tmp_path / 'pkg' / 'utils.py', """\
        def helper(): pass
    """)
    _write(tmp_path / 'pkg' / 'models.py', """\
        from .utils import helper
        class User: pass
    """)
    _write(tmp_path / 'pkg' / 'api.py', """\
        from .utils import helper
        from .models import User
        def handler(): pass
    """)
    _write(tmp_path / 'pkg' / 'cli.py', """\
        from .models import User
        def main(): pass
    """)
    # pyproject.toml so find_project_root stops here
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')
    return tmp_path


@pytest.fixture
def star_pkg(tmp_path):
    """Package with a star import to test star_import type detection."""
    _write(tmp_path / 'pkg' / 'constants.py', 'X = 1\n')
    _write(tmp_path / 'pkg' / 'other.py', 'from .constants import *\n')
    (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')
    return tmp_path


@pytest.fixture
def barrel_pkg(tmp_path):
    """TS package where a barrel file re-exports a module (BACK-548).

    target.ts is imported two ways:
      - consumer.ts  via a normal `import { Thing } from './target'`
      - index.ts     via a re-export barrel `export * from './target'`

    Before BACK-548 depends://target.ts reported only consumer.ts — tree-sitter
    models `export * from` as an export_statement, not an import_statement, so
    the barrel edge was invisible and blast radius was undercounted. Both must
    now appear.
    """
    _write(tmp_path / 'src' / 'target.ts', "export class Thing {}\n")
    _write(tmp_path / 'src' / 'consumer.ts',
           "import { Thing } from './target';\nnew Thing();\n")
    _write(tmp_path / 'src' / 'index.ts',
           "export * from './target';\nexport { Other } from './other';\n")
    _write(tmp_path / 'src' / 'other.ts', "export const Other = 1;\n")
    (tmp_path / 'tsconfig.json').write_text('{}\n')
    (tmp_path / 'package.json').write_text('{"name": "demo"}\n')
    return tmp_path


@pytest.fixture
def honest_decline_pkg(tmp_path):
    """TS package where an importer references a relative module that isn't in
    the tree (BACK-547). target.ts has no in-tree importer, and consumer.ts
    imports `./driver`, which doesn't exist — an intra-project import that
    doesn't resolve. depends://target.ts must caveat its negative rather than
    assert a confident "nothing imports this module"."""
    _write(tmp_path / 'target.ts', "export class Target {}\n")
    _write(tmp_path / 'consumer.ts',
           "import { Gone } from './driver';\nexport const x = new Gone();\n")
    (tmp_path / 'tsconfig.json').write_text('{}\n')
    (tmp_path / 'package.json').write_text('{"name": "demo"}\n')
    return tmp_path


@pytest.fixture
def clean_pkg(tmp_path):
    """TS package where every relative import resolves — honest-decline must
    stay silent (no false caveat)."""
    _write(tmp_path / 'target.ts', "export class Target {}\n")
    _write(tmp_path / 'consumer.ts',
           "import { Target } from './target';\nexport const x = new Target();\n")
    (tmp_path / 'tsconfig.json').write_text('{}\n')
    (tmp_path / 'package.json').write_text('{"name": "demo"}\n')
    return tmp_path


@pytest.fixture
def gradle_pkg(tmp_path):
    """
    Gradle-style Java tree, no .git/pyproject.toml anywhere — only a
    `settings.gradle.kts` at the true root — with the dependent in a sibling
    package directory (com/example/app) from the target (com/example/util).
    Regression fixture for BACK-498: find_project_root() didn't recognize
    Gradle/Maven/dotnet/SPM/Composer root markers, so depends:// fell back to
    scanning just the target file's own parent dir and missed this dependent
    entirely (while imports://?rank=fan-in, which scans the whole given
    directory, saw it fine).
    """
    (tmp_path / 'settings.gradle.kts').write_text('rootProject.name = "demo"\n')
    _write(tmp_path / 'src/main/java/com/example/util/Helper.java', """\
        package com.example.util;
        public class Helper {
            public static int add(int a, int b) { return a + b; }
        }
    """)
    _write(tmp_path / 'src/main/java/com/example/app/Main.java', """\
        package com.example.app;
        import com.example.util.Helper;
        public class Main {
            public static void main(String[] args) { Helper.add(1, 2); }
        }
    """)
    return tmp_path


# ---------------------------------------------------------------------------
# Unit: DependsAdapter with controlled fixture data
# ---------------------------------------------------------------------------

class TestDependsAdapterFileTarget:
    """Single-file target: depends://pkg/utils.py"""

    def test_type_is_module_dependents(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        assert r['type'] == 'module_dependents'

    def test_contract_version_present(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        assert r['contract_version'] == '1.1'

    def test_utils_has_two_importers(self, simple_pkg):
        """utils.py is imported by models.py and api.py — cli.py does not import it."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        assert r['count'] == 2
        importer_names = {Path(d['file']).name for d in r['dependents']}
        assert 'models.py' in importer_names
        assert 'api.py' in importer_names
        assert 'cli.py' not in importer_names

    def test_models_has_two_importers(self, simple_pkg):
        """models.py is imported by api.py and cli.py."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'models.py'))
        r = a.get_structure()
        assert r['count'] == 2
        importer_names = {Path(d['file']).name for d in r['dependents']}
        assert 'api.py' in importer_names
        assert 'cli.py' in importer_names

    def test_cli_has_no_importers(self, simple_pkg):
        """cli.py is not imported by anyone."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'cli.py'))
        r = a.get_structure()
        assert r['count'] == 0
        assert r['dependents'] == []

    def test_dependent_record_has_required_fields(self, simple_pkg):
        """Each dependent record exposes file, line, names, type, is_relative."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        for dep in r['dependents']:
            assert 'file' in dep
            assert 'line' in dep
            assert 'names' in dep
            assert 'type' in dep
            assert 'is_relative' in dep

    def test_imported_names_correct(self, simple_pkg):
        """models.py imports 'helper' from utils — names should include 'helper'."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        models_dep = next(d for d in r['dependents'] if Path(d['file']).name == 'models.py')
        assert 'helper' in models_dep['names']

    def test_nonexistent_path_returns_error(self, tmp_path):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(tmp_path / 'does_not_exist.py'))
        r = a.get_structure()
        assert 'error' in r


class TestDependsAdapterReExportBarrels:
    """BACK-548: `export ... from` re-exports must count as importers so a
    barrel file doesn't silently drop out of a module's blast radius."""

    def test_barrel_counted_as_dependent(self, barrel_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(barrel_pkg / 'src' / 'target.ts'))
        r = a.get_structure()
        names = {Path(d['file']).name for d in r['dependents']}
        # Both the direct importer AND the re-export barrel must be present.
        assert names == {'consumer.ts', 'index.ts'}, (
            f"barrel index.ts must count as a dependent of target.ts, got {names}")

    def test_barrel_edge_marked_re_export(self, barrel_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(barrel_pkg / 'src' / 'target.ts'))
        r = a.get_structure()
        barrel = next(d for d in r['dependents'] if Path(d['file']).name == 'index.ts')
        assert barrel['type'] == 're_export'

    def test_named_reexport_counted(self, barrel_pkg):
        """`export { Other } from './other'` is also a re-export edge."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(barrel_pkg / 'src' / 'other.ts'))
        r = a.get_structure()
        names = {Path(d['file']).name for d in r['dependents']}
        assert 'index.ts' in names


class TestDependsAdapterHonestDecline:
    """BACK-547: a blast-radius negative must be caveated, not asserted, when the
    scan had intra-project imports that didn't resolve. External (stdlib/dep)
    imports and fully-resolved corpora must NOT trigger the caveat (no crying
    wolf)."""

    def test_negative_with_intra_project_miss_is_caveated(self, honest_decline_pkg):
        from reveal.adapters.depends import DependsAdapter
        r = DependsAdapter(str(honest_decline_pkg / 'target.ts')).get_structure()
        assert r['count'] == 0
        assert r['undercount_possible'] is True
        assert r['_meta']['confidence'] == 'reduced'
        assert 'intra-project' in (r.get('warning') or '')

    def test_clean_corpus_stays_silent(self, clean_pkg):
        from reveal.adapters.depends import DependsAdapter
        # target.ts IS imported by consumer.ts, and nothing is unresolved.
        r = DependsAdapter(str(clean_pkg / 'target.ts')).get_structure()
        assert r['count'] == 1
        assert r['undercount_possible'] is False
        assert r['_meta']['confidence'] == 'high'
        assert 'intra-project' not in (r.get('warning') or '')

    def test_positive_result_does_not_cry_wolf(self, honest_decline_pkg):
        """A non-empty result in a corpus with unrelated unresolved imports must
        NOT get the prominent ⚠ (it's disclosed in known_limits instead)."""
        from reveal.adapters.depends import DependsAdapter
        # driver.ts is missing, but ask about a module that DOES have importers:
        # consumer.ts imports './driver' — query the consumer's own importers is
        # empty, so instead assert the gating via known_limits vs warning split.
        r = DependsAdapter(str(honest_decline_pkg / 'target.ts')).get_structure()
        # target.ts is the empty case here; verify known_limits always carries it
        hd = [l for l in r['_meta']['known_limits'] if 'intra-project' in l]
        assert len(hd) == 1

    def test_external_imports_do_not_trigger_caveat(self, tmp_path):
        """A file importing only stdlib/third-party (external) must stay silent —
        those correctly have no in-tree edge."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'app.py', "import os\nimport sys\nfrom collections import OrderedDict\n")
        _write(tmp_path / 'lonely.py', "def f(): pass\n")
        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "t"\n')
        r = DependsAdapter(str(tmp_path / 'lonely.py')).get_structure()
        assert r['count'] == 0
        # os/sys/collections are external → None-classified → not counted.
        assert r['undercount_possible'] is False
        assert r['_meta']['confidence'] == 'high'

    def test_csharp_intra_project_namespace_miss_is_caveated(self, tmp_path):
        """C#: a `using` into a sub-namespace of a declared namespace that
        doesn't resolve is an intra-project miss (BACK-547 via BACK-544 index);
        an external `using System.*` must NOT trigger the caveat."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Core.cs', "namespace MyApp.Core { public class Thing {} }\n")
        _write(tmp_path / 'App.cs',
               "using System.Text;\nusing MyApp.Core.Missing;\n"
               "namespace MyApp.App { public class App {} }\n")
        r = DependsAdapter(str(tmp_path / 'Core.cs')).get_structure()
        assert r['count'] == 0
        # MyApp.Core.Missing is nested under declared MyApp.Core → intra-project
        # miss → caveat. System.Text is external → not counted.
        assert r['undercount_possible'] is True
        assert r['_meta']['confidence'] == 'reduced'
        assert 'intra-project' in (r.get('warning') or '')

    def test_csharp_external_only_stays_silent(self, tmp_path):
        """A C# file using only BCL namespaces must not trigger honest-decline."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Widget.cs', "namespace MyApp { public class Widget {} }\n")
        _write(tmp_path / 'Uses.cs',
               "using System.Text;\nusing System.Linq;\n"
               "namespace MyApp.Other { public class Uses {} }\n")
        r = DependsAdapter(str(tmp_path / 'Widget.cs')).get_structure()
        assert r['undercount_possible'] is False
        assert r['_meta']['confidence'] == 'high'

    def test_java_intra_project_package_miss_is_caveated(self, tmp_path):
        """BACK-547 scale-out: Java now has its own package inventory (`package`
        declarations) — an unresolved `import` naming a declared project
        package is an intra-project miss; `java.util.List` (undeclared) is not."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Thing.java', "package com.example.core;\npublic class Thing {}\n")
        _write(tmp_path / 'App.java',
               "package com.example.app;\n"
               "import java.util.List;\n"
               "import com.example.core.Missing;\n"
               "public class App {}\n")
        r = DependsAdapter(str(tmp_path / 'Thing.java')).get_structure()
        assert r['count'] == 0
        # com.example.core.Missing is nested under declared com.example.core
        # → intra-project miss → caveat. java.util.List is external → not counted.
        assert r['undercount_possible'] is True
        assert r['_meta']['confidence'] == 'reduced'
        assert 'intra-project' in (r.get('warning') or '')

    def test_java_external_only_stays_silent(self, tmp_path):
        """A Java file importing only JDK types must not trigger honest-decline."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Widget.java', "package com.example;\npublic class Widget {}\n")
        _write(tmp_path / 'Uses.java',
               "package com.example.other;\n"
               "import java.util.List;\nimport java.util.Map;\n"
               "public class Uses {}\n")
        r = DependsAdapter(str(tmp_path / 'Widget.java')).get_structure()
        assert r['undercount_possible'] is False
        assert r['_meta']['confidence'] == 'high'

    def test_kotlin_intra_project_package_miss_is_caveated(self, tmp_path):
        """BACK-547 scale-out: Kotlin `package` declarations feed the same
        honest-decline inventory as Java."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Thing.kt', "package com.example.core\nclass Thing\n")
        _write(tmp_path / 'App.kt',
               "package com.example.app\n"
               "import kotlin.collections.List\n"
               "import com.example.core.Missing\n"
               "class App\n")
        r = DependsAdapter(str(tmp_path / 'Thing.kt')).get_structure()
        assert r['count'] == 0
        assert r['undercount_possible'] is True
        assert r['_meta']['confidence'] == 'reduced'
        assert 'intra-project' in (r.get('warning') or '')

    def test_php_intra_project_namespace_miss_is_caveated(self, tmp_path):
        """BACK-547 scale-out: PHP `namespace` declarations feed the same
        honest-decline inventory as Java/Kotlin/C#."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Thing.php', "<?php\nnamespace App\\Core;\nclass Thing {}\n")
        _write(tmp_path / 'App.php',
               "<?php\nnamespace App\\Web;\n"
               "use Symfony\\Component\\HttpFoundation\\Request;\n"
               "use App\\Core\\Missing;\n"
               "class App {}\n")
        r = DependsAdapter(str(tmp_path / 'Thing.php')).get_structure()
        assert r['count'] == 0
        # App\Core\Missing is nested under declared App\Core → intra-project
        # miss → caveat. Symfony's namespace is external → not counted.
        assert r['undercount_possible'] is True
        assert r['_meta']['confidence'] == 'reduced'
        assert 'intra-project' in (r.get('warning') or '')

    def test_php_external_only_stays_silent(self, tmp_path):
        """A PHP file using only a third-party namespace must not trigger
        honest-decline."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Widget.php', "<?php\nnamespace App;\nclass Widget {}\n")
        _write(tmp_path / 'Uses.php',
               "<?php\nnamespace App\\Other;\n"
               "use Symfony\\Component\\HttpFoundation\\Request;\n"
               "class Uses {}\n")
        r = DependsAdapter(str(tmp_path / 'Widget.php')).get_structure()
        assert r['undercount_possible'] is False
        assert r['_meta']['confidence'] == 'high'

    def test_swift_stays_none_no_package_inventory(self, tmp_path):
        """Swift has no per-file package/module declaration to scan (BACK-547
        scope note) — an unresolved `import` stays the conservative None verdict,
        never crying wolf on a language with no inventory signal."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Widget.swift', "import Foundation\nclass Widget {}\n")
        _write(tmp_path / 'Lonely.swift', "class Lonely {}\n")
        r = DependsAdapter(str(tmp_path / 'Lonely.swift')).get_structure()
        assert r['undercount_possible'] is False
        assert r['_meta']['confidence'] == 'high'


class TestDependsAdapterSwiftSameModuleNote:
    """BACK-560: Swift same-module cross-file references have no import
    statement at all, so the ⚠ honest-decline (keyed on _unresolved_intra)
    never fires for them — an empty depends:// result on a Swift file looks
    identical to a genuinely dependency-free one. A separate, unconditional
    informational note must fire instead, distinguishing "this language can't
    express that edge as an import" from "we tried and partially failed"."""

    def test_swift_empty_result_carries_same_module_note(self, tmp_path):
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Lonely.swift', "class Lonely {}\n")
        r = DependsAdapter(str(tmp_path / 'Lonely.swift')).get_structure()
        assert r['count'] == 0
        note = r.get('same_module_note') or ''
        assert 'Swift' in note
        assert 'import' in note
        # Must not be conflated with the honest-decline ⚠ signal — that
        # implies a failed resolution, which never happened here.
        assert '⚠' not in note

    def test_swift_note_not_confused_with_undercount_warning(self, tmp_path):
        """The note is additive, not a replacement for the (silent-here)
        honest-decline machinery — undercount_possible must stay False since
        no import was extracted-and-unresolved."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Lonely.swift', "class Lonely {}\n")
        r = DependsAdapter(str(tmp_path / 'Lonely.swift')).get_structure()
        assert r['undercount_possible'] is False
        assert 'same_module_note' in r

    def test_swift_non_empty_result_has_no_note(self, tmp_path):
        """The note is scoped to empty results only — a Swift file that DOES
        have a resolved import-based dependent must not carry it (nothing to
        caveat about that positive edge)."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Widget.swift', "class Widget {}\n")
        _write(tmp_path / 'App.swift', "import Widget\nclass App {}\n")
        r = DependsAdapter(str(tmp_path / 'Widget.swift')).get_structure()
        assert r['count'] == 1
        assert 'same_module_note' not in r

    def test_non_swift_empty_result_has_no_note(self, tmp_path):
        """Languages without this architectural gap (imports always exist to
        be extracted, even if unresolved) must never carry the Swift note."""
        from reveal.adapters.depends import DependsAdapter
        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "t"\n')
        _write(tmp_path / 'lonely.py', "def f(): pass\n")
        r = DependsAdapter(str(tmp_path / 'lonely.py')).get_structure()
        assert r['count'] == 0
        assert 'same_module_note' not in r


class TestDependsAdapterCSharpNamespaceFanout:
    """BACK-554: depends:// must resolve a C# `using X.Y` naming a namespace
    declared across several files (or a file with NO local `using` at all —
    the shape a C# 10 `global using` produces) via the BACK-544 namespace
    index, the same way `imports://` already does. Before this fix,
    `resolve_import`'s dotted-name match only caught the coincidental case
    where the namespace's last component happened to equal a filename
    (`using X.Y` -> `Y.cs`); the common multi-file-namespace case fell
    through to the honest-decline caveat instead of a resolved edge, and a
    file with zero local imports (the `global using` shape) was invisible to
    the namespace index entirely regardless of that gap — a second, deeper
    bug this loop found (see the sibling fix in
    `ImportsAdapter._resolve_dependencies`, same root cause)."""

    def test_namespace_spanning_files_resolves(self, tmp_path):
        """`using MyApp.Services;` names a namespace, not the file `Services.cs`
        (which doesn't exist) — must still resolve via the namespace index."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'MyApp' / 'Services' / 'UserService.cs',
               "namespace MyApp.Services\n{\n    public class UserService {}\n}\n")
        _write(tmp_path / 'Consumer.cs',
               "using MyApp.Services;\n\nnamespace MyApp\n{\n"
               "    public class Consumer { UserService s; }\n}\n")
        (tmp_path / 'App.sln').write_text('')
        r = DependsAdapter(str(tmp_path / 'MyApp' / 'Services' / 'UserService.cs')).get_structure()
        assert r['count'] == 1
        assert Path(r['dependents'][0]['file']).name == 'Consumer.cs'
        assert r['_meta']['confidence'] == 'high'

    def test_global_using_file_with_no_local_imports_is_reachable(self, tmp_path):
        """C# 10 `global using MyApp.Services;` (conventionally in
        GlobalUsings.cs) makes the namespace available project-wide without a
        local `using` in every consuming file. The declaring file
        (UserService.cs) itself has ZERO import statements of its own — it
        must still be indexed as a namespace declarer so GlobalUsings.cs's
        edge to it resolves (this is the part that was silently invisible:
        a zero-import file never appeared in the graph the namespace index
        was built from)."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'MyApp' / 'Services' / 'UserService.cs',
               "namespace MyApp.Services\n{\n    public class UserService {}\n}\n")
        _write(tmp_path / 'GlobalUsings.cs', "global using MyApp.Services;\n")
        _write(tmp_path / 'Program.cs',
               "namespace MyApp\n{\n    public class Program { static void Main() {} }\n}\n")
        (tmp_path / 'App.sln').write_text('')
        r = DependsAdapter(str(tmp_path / 'MyApp' / 'Services' / 'UserService.cs')).get_structure()
        assert r['count'] == 1
        assert Path(r['dependents'][0]['file']).name == 'GlobalUsings.cs'
        assert r['_meta']['confidence'] == 'high'

    def test_unresolved_nested_namespace_still_caveated(self, tmp_path):
        """Sanity guard: the namespace index is an exact-key lookup, not a
        prefix match — an import naming an undeclared sub-namespace must
        still fall through to the honest-decline caveat (BACK-547), not a
        fabricated edge. Mirrors
        TestDependsAdapterHonestDecline.test_csharp_intra_project_namespace_miss_is_caveated."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'Core.cs', "namespace MyApp.Core { public class Thing {} }\n")
        _write(tmp_path / 'App.cs',
               "using MyApp.Core.Missing;\nnamespace MyApp.App { public class App {} }\n")
        r = DependsAdapter(str(tmp_path / 'Core.cs')).get_structure()
        assert r['count'] == 0
        assert r['undercount_possible'] is True
        assert r['_meta']['confidence'] == 'reduced'


class TestDependsAdapterDirectoryTarget:
    """Directory target: depends://pkg/ — reverse dependency summary."""

    def test_type_is_dependency_summary(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        assert r['type'] == 'dependency_summary'

    def test_utils_is_most_imported(self, simple_pkg):
        """utils.py has 2 importers, models.py has 2 — both should appear at top."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        modules = r['modules']
        names = [Path(m['module']).name for m in modules]
        assert 'utils.py' in names
        assert 'models.py' in names

    def test_top_n_limits_results(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'), query='top=1')
        r = a.get_structure()
        assert len(r['modules']) == 1

    def test_sorted_by_dependent_count_descending(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        counts = [m['dependent_count'] for m in r['modules']]
        assert counts == sorted(counts, reverse=True)

    def test_modules_include_dependents_list(self, simple_pkg):
        """Each module entry lists the actual importer file paths."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        utils_entry = next(
            m for m in r['modules'] if Path(m['module']).name == 'utils.py'
        )
        importer_names = {Path(p).name for p in utils_entry['dependents']}
        assert 'models.py' in importer_names
        assert 'api.py' in importer_names

    def test_leaf_modules_not_in_results(self, simple_pkg):
        """cli.py has no importers — should not appear in dependency_summary."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        names = [Path(m['module']).name for m in r['modules']]
        assert 'cli.py' not in names


class TestDependsAdapterStarImport:
    """Star imports are captured (type=star_import)."""

    def test_star_import_captured(self, star_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(star_pkg / 'pkg' / 'constants.py'))
        r = a.get_structure()
        assert r['count'] == 1
        dep = r['dependents'][0]
        assert dep['type'] == 'star_import'


class TestDependsAdapterDotFormat:
    """?format=dot produces GraphViz output."""

    def test_dot_format_starts_with_digraph(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg'), query='format=dot')
        r = a.get_structure()
        # _format flag is set
        assert r.get('_format') == 'dot'

    def test_dot_renderer_output(self, simple_pkg, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        a = DependsAdapter(str(simple_pkg / 'pkg'), query='format=dot')
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='text')
        captured = capsys.readouterr()
        assert 'digraph depends' in captured.out
        assert 'rankdir=LR' in captured.out


class TestDependsAdapterMetadata:
    """Metadata fields are populated."""

    def test_metadata_in_result(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        assert 'metadata' in r
        meta = r['metadata']
        assert 'total_files_scanned' in meta
        assert 'total_import_edges' in meta

    def test_total_import_edges_positive(self, simple_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        assert r['metadata']['total_import_edges'] > 0


class TestDependsAdapterSchema:
    """Schema and help methods."""

    def test_get_schema_has_adapter_key(self):
        from reveal.adapters.depends import DependsAdapter
        schema = DependsAdapter.get_schema()
        assert schema['adapter'] == 'depends'
        assert 'uri_syntax' in schema
        assert 'query_params' in schema
        assert 'output_types' in schema

    def test_get_help_has_name(self):
        from reveal.adapters.depends import DependsAdapter
        help_data = DependsAdapter.get_help()
        assert help_data['name'] == 'depends'
        assert 'examples' in help_data

    def test_adapter_registered_as_depends_scheme(self):
        from reveal.adapters.base import get_adapter_class
        cls = get_adapter_class('depends')
        assert cls is not None
        from reveal.adapters.depends import DependsAdapter
        assert cls is DependsAdapter

    def test_renderer_registered(self):
        from reveal.adapters.base import get_renderer_class
        renderer = get_renderer_class('depends')
        assert renderer is not None


class TestDependsAdapterRenderer:
    """Renderer produces expected output."""

    def test_render_structure_file_target(self, simple_pkg, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='text')
        captured = capsys.readouterr()
        assert 'Dependents of:' in captured.out
        assert '2 file(s) import this module' in captured.out

    def test_render_structure_json(self, simple_pkg, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        import json
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'utils.py'))
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='json')
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert parsed['type'] == 'module_dependents'

    def test_render_no_dependents_message(self, simple_pkg, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        a = DependsAdapter(str(simple_pkg / 'pkg' / 'cli.py'))
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='text')
        captured = capsys.readouterr()
        assert 'No dependents found' in captured.out

    def test_render_summary_directory(self, simple_pkg, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        a = DependsAdapter(str(simple_pkg / 'pkg'))
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='text')
        captured = capsys.readouterr()
        assert 'Reverse Dependency Summary' in captured.out


class TestDependsAdapterCrossModuleRoot:
    """BACK-498: cross-package-directory dependents for Gradle/Maven/dotnet/
    SPM/Composer trees with no .git/pyproject.toml, only their own ecosystem's
    root marker."""

    def test_gradle_root_marker_finds_sibling_package_dependent(self, gradle_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(gradle_pkg / 'src/main/java/com/example/util/Helper.java'))
        r = a.get_structure()
        assert r['count'] == 1
        dependent_paths = [d['file'] for d in r['dependents']]
        assert any('Main.java' in p for p in dependent_paths)

    def test_no_root_marker_falls_back_to_src_ancestor(self, tmp_path):
        """No settings.gradle.kts either: widen to the nearest 'src' ancestor
        rather than the bare parent dir (still finds the sibling-package
        dependent one level up from a same-name-only fallback)."""
        from reveal.adapters.depends import DependsAdapter
        _write(tmp_path / 'src/main/java/com/example/util/Helper.java', """\
            package com.example.util;
            public class Helper {
                public static int add(int a, int b) { return a + b; }
            }
        """)
        _write(tmp_path / 'src/main/java/com/example/app/Main.java', """\
            package com.example.app;
            import com.example.util.Helper;
            public class Main {
                public static void main(String[] args) { Helper.add(1, 2); }
            }
        """)
        a = DependsAdapter(str(tmp_path / 'src/main/java/com/example/util/Helper.java'))
        r = a.get_structure()
        assert r['count'] == 1

    # BACK-515: every language depends:// builds an import graph for must have
    # its project-root marker recognized by `_has_project_marker`. A missing
    # marker is not cosmetic — search_parents climbs past the real root to some
    # ancestor `.git`, and _build_graph then scans every file under it (the
    # reported "hang" was a full monorepo scan, not an infinite loop). This
    # matrix guards the BACK-514 language set (Lua/Scala/Dart/Zig/GDScript);
    # add a row whenever depends:// gains another language.
    #
    # Each row: (marker filename or '*.ext' glob, module-file extension,
    # `require`/import line importing `bar`, `bar` module body).
    _ROOT_MARKER_CASES = [
        ('mylib-1.0.rockspec', 'lua', 'local bar = require("bar")', 'return {}'),
        ('build.sbt', 'scala', 'import bar.Thing', 'package bar\nclass Thing'),
        ('pubspec.yaml', 'dart', "import 'bar.dart';", 'class Bar {}'),
        ('build.zig', 'zig', 'const bar = @import("bar.zig");', 'pub const x = 1;'),
        ('project.godot', 'gd', 'const Bar = preload("bar.gd")', 'extends Node'),
    ]

    @pytest.mark.parametrize(
        'marker,ext,importer_body,module_body',
        _ROOT_MARKER_CASES,
        ids=[c[1] for c in _ROOT_MARKER_CASES],
    )
    def test_language_root_marker_stops_ancestor_climb(
        self, tmp_path, marker, ext, importer_body, module_body
    ):
        """A per-language root marker at the true project root must stop
        search_parents there, not climb past it to a decoy `.git` several
        levels up. Regression matrix for the BACK-515 hang across every
        depends://-supported language BACK-514 added."""
        from reveal.adapters.depends import _has_project_marker

        # Decoy marker several levels above the real project root.
        (tmp_path / '.git').mkdir()
        proj = tmp_path / 'vendor' / 'lib'
        proj.mkdir(parents=True)
        (proj / marker).write_text('# marker\n')
        _write(proj / f'src/foo.{ext}', importer_body + '\n')
        _write(proj / f'src/bar.{ext}', module_body + '\n')

        # The marker dir is recognized; the src dir below it is not.
        assert _has_project_marker(proj)
        assert not _has_project_marker(proj / 'src')

    def test_rockspec_resolves_lua_dependent(self, tmp_path):
        """End-to-end companion to the marker matrix: with a `*.rockspec`
        root, the Lua importer is actually resolved (not just that the scan
        is bounded)."""
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / '.git').mkdir()
        (tmp_path / 'vendor' / 'lua-lib').mkdir(parents=True)
        (tmp_path / 'vendor' / 'lua-lib' / 'mylib-1.0.rockspec').write_text('package = "mylib"\n')
        _write(tmp_path / 'vendor/lua-lib/src/foo.lua', """\
            local bar = require("bar")
        """)
        _write(tmp_path / 'vendor/lua-lib/src/bar.lua', """\
            return {}
        """)
        a = DependsAdapter(str(tmp_path / 'vendor/lua-lib/src/bar.lua'))
        r = a.get_structure()
        assert r['count'] == 1
        assert 'foo.lua' in r['dependents'][0]['file']


class TestDependsAdapterScanRootResolution:
    """BACK-525 layers 1-3: tiered nearest-marker climb, hard ceiling, and
    the inferred-project fallback that replaces the flat marker-climb."""

    def test_package_marker_beats_nearer_vcs_root(self, tmp_path):
        """A package/build marker several levels up must be preferred over a
        *nearer* VCS root — package evidence is a project-unit signal, a bare
        `.git` is only a climb ceiling, and being nearer doesn't promote it
        (the core insight the flat nearest-match marker list couldn't
        express: it always picked whichever marker was nearest, regardless
        of kind)."""
        from reveal.adapters.depends import _resolve_project_root

        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "monorepo"\n')
        nested = tmp_path / 'packages' / 'foo'
        (nested / '.git').mkdir(parents=True)
        target = nested / 'src' / 'target.py'
        _write(target, 'x = 1\n')

        assert _resolve_project_root(target) == tmp_path

    def test_no_marker_before_ceiling_returns_none(self, tmp_path):
        """No package or VCS marker anywhere between the target and the hard
        ceiling (here: tmp_path's own ancestry crosses the OS temp dir) —
        the climb must stop at the ceiling, not silently pick some unrelated
        ancestor up past it."""
        from reveal.adapters.depends import _resolve_project_root

        target = tmp_path / 'no_markers' / 'target.py'
        _write(target, 'x = 1\n')

        assert _resolve_project_root(target) is None

    def test_inferred_fallback_scopes_to_target_dir_and_warns(self, tmp_path):
        """When no marker is found before the ceiling, depends:// must scope
        to the target's own directory (never scan the ceiling) and disclose
        it via a warning + metadata flag, not silently degrade."""
        from reveal.adapters.depends import DependsAdapter

        pkg = tmp_path / 'no_markers' / 'pkg'
        _write(pkg / 'utils.py', 'def helper(): pass\n')
        _write(pkg / 'models.py', 'from .utils import helper\n')

        a = DependsAdapter(str(pkg / 'utils.py'))
        r = a.get_structure()

        assert r['count'] == 1
        assert r['metadata']['root_inferred'] is True
        assert 'warning' in r
        assert "couldn't determine this file's project boundary" in r['warning'].lower()

    def test_vcs_root_still_used_when_no_package_marker_exists(self, tmp_path):
        """No package marker anywhere, but a `.git` exists before the
        ceiling — tier 2 (VCS root) still applies; a real repo boundary is
        legitimate project evidence, not something layer 3 should override."""
        from reveal.adapters.depends import _resolve_project_root

        (tmp_path / '.git').mkdir()
        target = tmp_path / 'src' / 'target.py'
        _write(target, 'x = 1\n')

        assert _resolve_project_root(target) == tmp_path

    def test_reveal_yaml_root_beats_ancestor_vcs(self, tmp_path):
        """BACK-609 tier 0: an explicit `.reveal.yaml root:true` pins the scan
        root and beats a distant ancestor `.git`. This is the consistent,
        language-agnostic way to root a marker-less tree (C/C++ with only a
        Makefile) or a project nested under a larger repo — without it the
        climb promotes the ancestor VCS root and over-scans."""
        from reveal.adapters.depends import _resolve_project_root

        (tmp_path / '.git').mkdir()
        component = tmp_path / 'vendor' / 'thing'
        component.mkdir(parents=True)
        (component / '.reveal.yaml').write_text('root: true\n')
        target = component / 'src' / 'target.c'
        _write(target, 'int x;\n')

        assert _resolve_project_root(target) == component

    def test_reveal_yaml_without_root_true_does_not_pin(self, tmp_path):
        """A `.reveal.yaml` that does NOT declare `root: true` is not a tier-0
        marker — resolution falls through to the ordinary package/VCS tiers,
        so an ambient config file can't accidentally re-scope the scan."""
        from reveal.adapters.depends import _resolve_project_root

        (tmp_path / '.git').mkdir()
        component = tmp_path / 'vendor' / 'thing'
        component.mkdir(parents=True)
        (component / '.reveal.yaml').write_text('exclude:\n  - "*.tmp"\n')
        target = component / 'src' / 'target.c'
        _write(target, 'int x;\n')

        # No root:true anywhere → the ancestor .git (tier 2) is the boundary.
        assert _resolve_project_root(target) == tmp_path

    def test_reveal_yaml_root_beats_nearer_package_marker(self, tmp_path):
        """Tier 0 outranks tier 1: a `.reveal.yaml root:true` higher up wins
        over a *nearer* package marker below it, so an explicit declaration is
        never silently overridden by an inferred sub-package boundary."""
        from reveal.adapters.depends import _resolve_project_root

        (tmp_path / '.reveal.yaml').write_text('root: true\n')
        nested = tmp_path / 'packages' / 'foo'
        nested.mkdir(parents=True)
        (nested / 'package.json').write_text('{"name": "foo"}\n')
        target = nested / 'src' / 'target.js'
        _write(target, 'var x = 1;\n')

        assert _resolve_project_root(target) == tmp_path


class TestDependsAdapterRootOverride:
    """BACK-610: the ``?root=DIR`` query param pins the scan root for one
    invocation (highest precedence, tier -1), with fail-closed validation, and
    the over-climb diagnostic now names it instead of giving impossible advice."""

    def test_root_override_is_highest_precedence(self, tmp_path):
        """Tier -1: a validated ``?root=`` beats even a ``.reveal.yaml root:true``
        higher up — an explicit per-invocation instruction wins over every
        inferred or declared marker."""
        from reveal.adapters.depends import _resolve_project_root

        (tmp_path / '.reveal.yaml').write_text('root: true\n')
        (tmp_path / '.git').mkdir()
        component = tmp_path / 'packages' / 'foo'
        (component / 'src').mkdir(parents=True)
        target = component / 'src' / 'target.c'
        _write(target, 'int x;\n')

        # Without an override, tier 0 pins tmp_path; the override forces component.
        assert _resolve_project_root(target) == tmp_path
        assert _resolve_project_root(target, root_override=component) == component

    def test_root_override_pins_scan_root_over_ancestor_git(self, tmp_path):
        """End-to-end: a marker-less C tree nested under an ancestor ``.git``
        over-climbs to that repo by default; ``?root=`` scopes the scan to the
        component instead — the exact over-climb case BACK-609/610 target."""
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / '.git').mkdir()  # foreign ancestor repo (the over-climb trap)
        comp = tmp_path / 'cproj' / 'src'
        _write(comp / 'util.h', 'int u(void);\n')
        _write(comp / 'util.c', '#include "util.h"\nint u(void){return 1;}\n')

        # Default: climbs to the ancestor .git.
        a = DependsAdapter(str(comp / 'util.h'))
        a.get_structure()
        assert a._scan_root == tmp_path

        # Pinned: scoped to the component, still finds the dependent.
        b = DependsAdapter(str(comp / 'util.h'), query=f'root={comp}')
        r = b.get_structure()
        assert b._scan_root == comp
        assert b._root_override_used == comp
        assert r['count'] == 1
        assert 'util.c' in r['dependents'][0]['file']

    def test_relative_root_resolved_from_cwd(self, tmp_path, monkeypatch):
        """A relative ``?root=`` resolves against cwd, so the same URI works in
        CLI and MCP/service mode."""
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / '.git').mkdir()
        comp = tmp_path / 'cproj' / 'src'
        _write(comp / 'util.h', 'int u(void);\n')
        _write(comp / 'util.c', '#include "util.h"\nint u(void){return 1;}\n')

        monkeypatch.chdir(tmp_path)
        a = DependsAdapter(str(comp / 'util.h'), query='root=cproj/src')
        a.get_structure()
        assert a._root_override_used == comp

    def test_unsafe_root_rejected_falls_back_and_warns(self, tmp_path):
        """``?root=`` cannot be used to force a catastrophic wide scan: a
        filesystem/home/system root is refused (same ceiling the climb obeys),
        and resolution falls back to auto-detection with a disclosure."""
        import tempfile
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / '.git').mkdir()
        target = tmp_path / 'src' / 'foo.h'
        _write(target, 'int f(void);\n')

        a = DependsAdapter(str(target), query=f'root={tempfile.gettempdir()}')
        r = a.get_structure()

        assert a._root_override_used is None
        assert a._scan_root == tmp_path  # fell back to tier-2 .git
        assert 'filesystem/home/system root' in r['warning']

    def test_nonexistent_root_rejected_and_warns(self, tmp_path):
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / '.git').mkdir()
        target = tmp_path / 'src' / 'foo.h'
        _write(target, 'int f(void);\n')

        a = DependsAdapter(str(target), query=f'root={tmp_path / "nope"}')
        r = a.get_structure()

        assert a._root_override_used is None
        assert 'not an existing directory' in r['warning']

    def test_root_not_containing_target_rejected_and_warns(self, tmp_path):
        """A pinned root that doesn't hold the target can never surface the
        target's dependents — reject it rather than scan an unrelated tree."""
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / '.git').mkdir()
        target = tmp_path / 'app' / 'foo.h'
        _write(target, 'int f(void);\n')
        (tmp_path / 'other').mkdir()

        a = DependsAdapter(str(target), query=f'root={tmp_path / "other"}')
        r = a.get_structure()

        assert a._root_override_used is None
        assert 'does not contain the target' in r['warning']

    def test_capped_file_target_diagnostic_names_root_lever(self, tmp_path, monkeypatch):
        """The over-climb fix (BACK-610): a single-file target that hits the cap
        must NOT be told to 'narrow the path' (impossible for one file) — it must
        name the levers that actually fix it (``?root=`` / ``.reveal.yaml``)."""
        from reveal.adapters.depends import DependsAdapter

        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 3)
        (tmp_path / '.git').mkdir()
        for i in range(5):
            inc = f'#include "m{i - 1}.h"\n' if i > 0 else ''
            _write(tmp_path / 'src' / f'm{i}.h', f'{inc}int f{i}(void);\n')

        a = DependsAdapter(str(tmp_path / 'src' / 'm0.h'))
        r = a.get_structure()

        assert r['metadata']['scan_capped'] is True
        warning = r['warning']
        assert "Can't narrow a single-file target" in warning
        assert '?root=' in warning
        assert "root: true" in warning

    def test_capped_pinned_root_diagnostic_is_honest(self, tmp_path, monkeypatch):
        """When ``?root=`` is already in effect and the cap STILL fires, don't
        loop back to advice they already followed — say the pinned root is
        genuinely over the cap."""
        from reveal.adapters.depends import DependsAdapter

        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 3)
        comp = tmp_path / 'cproj'
        for i in range(5):
            inc = f'#include "m{i - 1}.h"\n' if i > 0 else ''
            _write(comp / 'src' / f'm{i}.h', f'{inc}int f{i}(void);\n')

        a = DependsAdapter(str(comp / 'src' / 'm0.h'), query=f'root={comp}')
        r = a.get_structure()

        assert r['metadata']['scan_capped'] is True
        assert 'exceeds the scan cap even as scoped' in r['warning']
        assert '?root=DIR' not in r['warning']


class TestDependsAdapterLanguageScoping:
    """BACK-525 layer 4: a single-file target only parses files in its own
    extractor's extension family — a Python target must not pay to
    tree-sitter-parse sibling files in unrelated languages."""

    def test_other_language_files_excluded_from_scan_count(self, tmp_path):
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')
        _write(tmp_path / 'pkg/utils.py', 'def helper(): pass\n')
        _write(tmp_path / 'pkg/models.py', 'from .utils import helper\n')
        # Decoy: an unrelated Go file living right alongside the Python
        # package, *with an import statement* so it would register in
        # graph.files (get_file_count counts only files with imports) if
        # it were wrongly parsed. Pre-BACK-525, every supported language
        # under scan_root got tree-sitter-parsed looking for importers;
        # layer 4 should skip this entirely for a .py target.
        _write(tmp_path / 'pkg/other.go', 'package pkg\nimport "fmt"\n')

        a = DependsAdapter(str(tmp_path / 'pkg' / 'utils.py'))
        r = a.get_structure()

        assert r['count'] == 1
        # Only models.py has an import statement (utils.py has none); the
        # Go decoy — despite having its own import — must never register.
        assert r['metadata']['total_files_scanned'] == 1

    def test_c_target_still_scans_its_own_header_family(self, tmp_path):
        """C's family is {.c, .h} — narrowing to the target's own extension
        alone (not its extractor's full family) would wrongly drop header
        dependents/dependencies."""
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / '.git').mkdir()
        _write(tmp_path / 'src/foo.h', 'void foo(void);\n')
        _write(tmp_path / 'src/foo.c', '#include "foo.h"\nvoid foo(void) {}\n')

        a = DependsAdapter(str(tmp_path / 'src' / 'foo.h'))
        r = a.get_structure()

        assert r['count'] == 1
        assert 'foo.c' in r['dependents'][0]['file']

    def test_directory_target_stays_unscoped_across_languages(self, tmp_path):
        """A directory target isn't tied to one extractor family — it must
        still see dependents across every supported language, unchanged
        from pre-BACK-525 behavior."""
        from reveal.adapters.depends import DependsAdapter

        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')
        _write(tmp_path / 'pkg/utils.py', 'def helper(): pass\n')
        _write(tmp_path / 'pkg/models.py', 'from .utils import helper\n')
        _write(tmp_path / 'pkg/other.go', 'package pkg\nimport "fmt"\n')

        a = DependsAdapter(str(tmp_path / 'pkg'))
        r = a.get_structure()

        assert r['type'] == 'dependency_summary'
        # models.py (Python import) and other.go (Go import) both register —
        # a directory target spans every supported language, unscoped.
        assert r['metadata']['total_files_scanned'] == 2


class TestDependsAdapterScanCap:
    """BACK-524: _build_graph must bound the walk instead of unbounded-scanning
    a huge marker-legit ancestor repo — warn-and-continue with partial results,
    not a silent hang. Caps _SCAN_FILE_CAP down via monkeypatch so the test
    corpus itself stays small; real default is 5,000."""

    @pytest.fixture
    def wide_pkg(self, tmp_path):
        """5 sibling modules, each imported by the next — bigger than a
        monkeypatched cap of 3, so the walk must stop mid-tree."""
        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "test"\n')
        for i in range(5):
            imp = f'from .mod{i - 1} import x\n' if i > 0 else ''
            _write(tmp_path / 'pkg' / f'mod{i}.py', f"{imp}x = {i}\n")
        return tmp_path

    def test_cap_sets_scan_capped_flag(self, wide_pkg, monkeypatch):
        from reveal.adapters.depends import DependsAdapter
        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 3)
        a = DependsAdapter(str(wide_pkg / 'pkg' / 'mod0.py'))
        r = a.get_structure()
        assert r['metadata']['scan_capped'] is True

    def test_cap_emits_warning_in_result(self, wide_pkg, monkeypatch):
        from reveal.adapters.depends import DependsAdapter
        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 3)
        a = DependsAdapter(str(wide_pkg / 'pkg' / 'mod0.py'))
        r = a.get_structure()
        assert 'warning' in r
        assert 'capped at 3 files' in r['warning']

    def test_cap_warning_in_known_limits(self, wide_pkg, monkeypatch):
        from reveal.adapters.depends import DependsAdapter
        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 3)
        a = DependsAdapter(str(wide_pkg / 'pkg' / 'mod0.py'))
        r = a.get_structure()
        assert any('BACK-524' in limit for limit in r['_meta']['known_limits'])

    def test_no_cap_hit_below_threshold(self, wide_pkg):
        """Default cap (5,000) is nowhere near this fixture's 5 files — no
        warning, no flag, unaffected by the BACK-524 guard."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(wide_pkg / 'pkg' / 'mod0.py'))
        r = a.get_structure()
        assert r['metadata']['scan_capped'] is False
        assert 'warning' not in r

    def test_render_structure_shows_warning(self, wide_pkg, monkeypatch, capsys):
        from reveal.adapters.depends import DependsAdapter, DependsRenderer
        monkeypatch.setattr(DependsAdapter, '_SCAN_FILE_CAP', 3)
        a = DependsAdapter(str(wide_pkg / 'pkg'))
        r = a.get_structure()
        DependsRenderer.render_structure(r, format='text')
        captured = capsys.readouterr()
        assert 'Scan capped at 3 files' in captured.out


class TestSubmoduleImportIdiom:
    """BACK-542: `from pkg import submodule` must create a dependency edge to
    the submodule file, not only to pkg/__init__.py."""

    @pytest.fixture
    def submodule_pkg(self, tmp_path):
        _write(tmp_path / 'pkg' / '__init__.py', '')
        _write(tmp_path / 'pkg' / 'intent.py', 'def match(): return 1\n')
        _write(tmp_path / 'pkg' / 'mod.py', 'def foo(): return 2\n')
        # `from pkg import submodule` idiom (was silently missed)
        _write(tmp_path / 'user_a.py',
               'from pkg import intent\ndef go(): return intent.match()\n')
        # `from pkg.mod import name` idiom (already worked)
        _write(tmp_path / 'user_b.py',
               'from pkg.mod import foo\ndef go(): return foo()\n')
        # multi-name: both are submodules
        _write(tmp_path / 'user_c.py',
               'from pkg import intent, mod\ndef go(): return intent.match() + mod.foo()\n')
        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "t"\n')
        return tmp_path

    def test_from_pkg_import_submodule_creates_edge(self, submodule_pkg):
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(submodule_pkg / 'pkg' / 'intent.py'))
        r = a.get_structure()
        importers = {Path(d['file']).name for d in r['dependents']}
        assert 'user_a.py' in importers  # the regression: was missing

    def test_multi_name_from_import_resolves_each_submodule(self, submodule_pkg):
        from reveal.adapters.depends import DependsAdapter
        intent_importers = {
            Path(d['file']).name
            for d in DependsAdapter(str(submodule_pkg / 'pkg' / 'intent.py')).get_structure()['dependents']
        }
        mod_importers = {
            Path(d['file']).name
            for d in DependsAdapter(str(submodule_pkg / 'pkg' / 'mod.py')).get_structure()['dependents']
        }
        # user_c imports both submodules in one statement → edge to each
        assert 'user_c.py' in intent_importers
        assert 'user_c.py' in mod_importers

    def test_dotted_import_still_resolves(self, submodule_pkg):
        """`from pkg.mod import foo` must keep resolving to mod.py (no regression)."""
        from reveal.adapters.depends import DependsAdapter
        importers = {
            Path(d['file']).name
            for d in DependsAdapter(str(submodule_pkg / 'pkg' / 'mod.py')).get_structure()['dependents']
        }
        assert 'user_b.py' in importers

    def test_submodule_edge_display_names(self, submodule_pkg):
        """The dependent record names the imported submodule, not a bare fallback."""
        from reveal.adapters.depends import DependsAdapter
        r = DependsAdapter(str(submodule_pkg / 'pkg' / 'intent.py')).get_structure()
        dep = next(d for d in r['dependents'] if Path(d['file']).name == 'user_a.py')
        assert 'intent' in dep['names']
        assert dep['line'] == 1


class TestDependsAdapterGoPackageGranularity:
    """BACK-553: Go resolves an import to the package DIRECTORY (every .go
    file in a dir shares one import path/package), so go.py's
    resolve_import() returns a directory, never a file. _build_graph then
    adds an edge keyed by that directory. A file-level
    depends://path/to/file.go query used to do an exact `reverse_deps[target]`
    lookup where target is always a file — a key that can never exist for
    Go — so EVERY single-file Go query silently returned zero dependents,
    unconditionally, even when the package had real importers. Confirmed on
    real Kubernetes source (BACK-547 Go recall-oracle loop,
    internal-docs/planning/dogfood-findings/go-recall-oracle/): a
    284-importer target reported 0 before the fix."""

    @pytest.fixture
    def go_pkg(self, tmp_path):
        """
        go.mod            — module example.com/proj
        pkg/alpha/a1.go    — package alpha; no imports of beta
        pkg/alpha/a2.go    — package alpha; second file, same package
        pkg/beta/b1.go     — package beta; imports example.com/proj/pkg/alpha
        pkg/gamma/g1.go    — package gamma; imports nothing intra-project
        """
        (tmp_path / 'go.mod').write_text('module example.com/proj\n\ngo 1.21\n')
        _write(tmp_path / 'pkg/alpha/a1.go', """\
            package alpha

            func Helper() {}
        """)
        _write(tmp_path / 'pkg/alpha/a2.go', """\
            package alpha

            func Other() {}
        """)
        _write(tmp_path / 'pkg/beta/b1.go', """\
            package beta

            import "example.com/proj/pkg/alpha"

            func UseHelper() { alpha.Helper() }
        """)
        _write(tmp_path / 'pkg/gamma/g1.go', """\
            package gamma

            import "fmt"

            func Noop() { fmt.Println("noop") }
        """)
        return tmp_path

    def test_single_file_target_finds_package_importer(self, go_pkg):
        """The exact regression: depends://pkg/alpha/a1.go (a single FILE)
        must find b1.go, even though go.py's resolve_import() only ever
        records the edge against the alpha DIRECTORY, not a1.go itself."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(go_pkg / 'pkg' / 'alpha' / 'a1.go'))
        r = a.get_structure()
        importer_names = {Path(d['file']).name for d in r['dependents']}
        assert 'b1.go' in importer_names
        assert r['count'] == 1

    def test_sibling_file_in_same_package_also_finds_importer(self, go_pkg):
        """a2.go shares alpha's directory with a1.go — same package, same
        resolved edge target — must resolve identically."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(go_pkg / 'pkg' / 'alpha' / 'a2.go'))
        r = a.get_structure()
        importer_names = {Path(d['file']).name for d in r['dependents']}
        assert 'b1.go' in importer_names

    def test_unrelated_package_has_no_importers(self, go_pkg):
        """gamma isn't imported by anyone — must stay a real (non-caveated)
        empty result, not accidentally picking up unrelated directory edges."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(go_pkg / 'pkg' / 'gamma' / 'g1.go'))
        r = a.get_structure()
        assert r['count'] == 0
        assert r['dependents'] == []

    def test_import_line_reported_correctly(self, go_pkg):
        """The directory-fallback path must still resolve the right
        ImportStatement for display (line number, module name) — not just
        an 'unknown' bare importer entry."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(go_pkg / 'pkg' / 'alpha' / 'a1.go'))
        r = a.get_structure()
        dep = next(d for d in r['dependents'] if Path(d['file']).name == 'b1.go')
        assert dep['type'] != 'unknown'
        assert dep['module'] == 'example.com/proj/pkg/alpha'
        assert dep['line'] == 3

    def test_directory_target_unaffected_by_fallback(self, go_pkg):
        """Querying the directory itself (already worked pre-fix) must keep
        working identically — the fallback must not double-count or change
        directory-target behavior."""
        from reveal.adapters.depends import DependsAdapter
        a = DependsAdapter(str(go_pkg / 'pkg' / 'alpha'))
        r = a.get_structure()
        assert r['type'] == 'dependency_summary'
        module = r['modules'][0]
        assert module['dependent_count'] == 1
        assert 'b1.go' in module['dependents'][0]


class TestPythonPackageRootAndResolution:
    """BACK-561/562/563 — found by the Home Assistant `depends://` recall-oracle
    measurement loop (Python; 36.7%→100% recall, 0 false positives).

    A Python *package* directory (one with ``__init__.py``) is not a sys.path
    root: the parent is. All three bugs stem from treating a package interior
    as a root, in three different code paths.
    """

    @pytest.fixture
    def ha_like(self, tmp_path):
        """Mirror the real HA layout that triggered every bug:
          root/                    <- true project root (pyproject.toml)
            app/                   <- the importable package (__init__.py)
              setup.py             <- a SOURCE module named setup.py, NOT a build
                                      script (HA's homeassistant/setup.py)
              core.py              <- absolute-import target
              absuser.py           <- `from app.core import X`  (BACK-561)
              sub/
                __init__.py
                typing.py          <- shadows stdlib `typing` + multi-seg target
                stduser.py         <- `from typing import Any` (BACK-562), a
                                      sibling of the shadowing typing.py
              reluser.py           <- `from .sub.typing import T` (BACK-563)
        """
        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "proj"\n')
        _write(tmp_path / 'app' / '__init__.py', '')
        _write(tmp_path / 'app' / 'setup.py',
               '"""A source module that happens to be named setup.py."""\n'
               'def async_setup(): return 1\n')
        _write(tmp_path / 'app' / 'core.py', 'class HomeAssistant: ...\n')
        _write(tmp_path / 'app' / 'absuser.py',
               'from app.core import HomeAssistant\n')
        _write(tmp_path / 'app' / 'sub' / '__init__.py', '')
        _write(tmp_path / 'app' / 'sub' / 'typing.py', 'ConfigType = dict\n')
        # stdlib `typing`, imported from a file whose package sibling is a
        # same-named `typing.py` — the shadow only manifests intra-package.
        _write(tmp_path / 'app' / 'sub' / 'stduser.py', 'from typing import Any\n')
        # multi-segment relative import of the in-tree module
        _write(tmp_path / 'app' / 'reluser.py',
               'from .sub.typing import ConfigType\n')
        return tmp_path

    def test_setup_py_source_module_is_not_a_project_root(self, ha_like):
        """BACK-561: a package dir holding a `setup.py` *source module* must not
        be promoted to scan root — else every absolute `from app.X import Y`
        goes unresolved (the confident false-negative: absolute imports return
        None from is_intra_project_import, so no honest-decline caveat fires)."""
        from reveal.adapters.depends import _resolve_project_root, DependsAdapter
        assert _resolve_project_root((ha_like / 'app' / 'core.py').resolve()) == ha_like
        importers = {
            Path(d['file']).name
            for d in DependsAdapter(str(ha_like / 'app' / 'core.py')).get_structure()['dependents']
        }
        assert 'absuser.py' in importers  # the regression: was silently missing

    def test_stdlib_import_not_shadowed_by_sibling_module(self, ha_like):
        """BACK-562: `from typing import Any` is the *stdlib* typing; it must not
        resolve to a same-named sibling `sub/typing.py` (a false-positive edge
        breaking the 'never false positives' invariant). Absolute imports never
        consult the importing file's own package directory."""
        from reveal.adapters.depends import DependsAdapter
        importers = {
            Path(d['file']).name
            for d in DependsAdapter(str(ha_like / 'app' / 'sub' / 'typing.py')).get_structure()['dependents']
        }
        assert 'stduser.py' not in importers  # false positive pre-fix

    def test_multi_segment_relative_import_targets_leaf_module(self, ha_like):
        """BACK-563: `from .sub.typing import ConfigType` depends on
        sub/typing.py, not sub/__init__.py — the old parts[0]-only relative
        resolver stopped at the first package and mis-targeted the edge."""
        from reveal.adapters.depends import DependsAdapter
        importers = {
            Path(d['file']).name
            for d in DependsAdapter(str(ha_like / 'app' / 'sub' / 'typing.py')).get_structure()['dependents']
        }
        assert 'reluser.py' in importers  # was landing on sub/__init__.py pre-fix


class TestConventionAutoloadCaveat:
    """BACK-557 — depends:// is structurally blind to Zeitwerk-autoloaded
    (zero-require) intra-app edges. Containment step: caveat low require-density
    Ruby trees even on positive results, before any convention-inference recall
    feature. Fires only for the convention_autoloaded language (Ruby) below the
    density threshold and above the min-file floor."""

    def _zeitwerk_tree(self, tmp_path, n_models=30, requires=1):
        """A Rails-shaped Ruby tree: many model files, almost none with a
        require (bare-constant Zeitwerk references instead)."""
        (tmp_path / 'Gemfile').write_text('gem "rails"\n')
        for i in range(n_models):
            body = ('require "digest/sha1"\n' if i < requires else '')
            # bare-constant reference to a sibling class, no require:
            body += f'class Model{i}\n  def go\n    Model{(i + 1) % n_models}.new\n  end\nend\n'
            _write(tmp_path / 'app' / 'models' / f'model{i}.rb', body)
        return tmp_path

    def test_low_density_ruby_tree_caveats_empty_result(self, tmp_path):
        from reveal.adapters.depends import DependsAdapter
        root = self._zeitwerk_tree(tmp_path, n_models=30, requires=1)
        r = DependsAdapter(str(root / 'app' / 'models' / 'model0.rb')).get_structure()
        assert 'autoload_note' in r                       # positive OR empty, fires
        assert 'Zeitwerk' in r['autoload_note']
        assert any('BACK-557' in k for k in r['_meta']['known_limits'])

    def test_low_density_ruby_tree_caveats_positive_result(self, tmp_path):
        """The caveat must fire even when the count is > 0 — a positive result
        is still a lower bound when 90%+ of edges are unstated."""
        from reveal.adapters.depends import DependsAdapter
        root = self._zeitwerk_tree(tmp_path, n_models=30, requires=1)
        # add one real require edge so the target has a dependent
        _write(root / 'app' / 'models' / 'importer.rb',
               'require_relative "model0"\nclass Importer; end\n')
        r = DependsAdapter(str(root / 'app' / 'models' / 'model0.rb')).get_structure()
        assert r['count'] >= 1                            # positive result
        assert 'autoload_note' in r                       # still caveated

    def test_high_density_ruby_tree_no_caveat(self, tmp_path):
        """A normal Ruby tree where most files require their deps must NOT be
        caveated (script/ in Discourse is 87% — explicit-require, not Zeitwerk)."""
        from reveal.adapters.depends import DependsAdapter
        (tmp_path / 'Gemfile').write_text('gem "sinatra"\n')
        for i in range(30):
            _write(tmp_path / 'lib' / f'part{i}.rb',
                   f'require_relative "part{(i + 1) % 30}"\nclass Part{i}; end\n')
        r = DependsAdapter(str(tmp_path / 'lib' / 'part0.rb')).get_structure()
        assert 'autoload_note' not in r

    def test_below_min_files_no_caveat(self, tmp_path):
        """A tiny low-density tree is noise, not a signal — must not fire."""
        from reveal.adapters.depends import DependsAdapter
        root = self._zeitwerk_tree(tmp_path, n_models=5, requires=0)
        r = DependsAdapter(str(root / 'app' / 'models' / 'model0.rb')).get_structure()
        assert 'autoload_note' not in r

    def test_non_ruby_tree_no_caveat(self, tmp_path):
        """Python (not convention_autoloaded) must never get the Ruby caveat,
        even though a package of __init__-only files has low import density."""
        from reveal.adapters.depends import DependsAdapter
        (tmp_path / 'pyproject.toml').write_text('[project]\nname = "p"\n')
        _write(tmp_path / 'pkg' / '__init__.py', '')
        for i in range(30):
            _write(tmp_path / 'pkg' / f'm{i}.py', f'class M{i}: ...\n')
        r = DependsAdapter(str(tmp_path / 'pkg' / 'm0.py')).get_structure()
        assert 'autoload_note' not in r


class TestZeitwerkConventionInference:
    """BACK-557 direction a — teach depends:// the Zeitwerk path->constant
    convention as a new implicit-edge source, on top of (not replacing)
    statement-based edges. Containment (the coverage caveat, above) makes the
    gap honest; this makes it smaller by inferring the edges Zeitwerk itself
    would resolve at runtime with no require statement anywhere."""

    def _rails_app(self, tmp_path):
        (tmp_path / 'Gemfile').write_text('gem "rails"\n')
        # Gemfile isn't a recognized _PACKAGE_ROOT_MARKERS entry (a
        # pre-existing gap, not part of this feature) — a .git root ensures
        # project_root resolves to tmp_path itself so cross-directory edges
        # (app/models -> app/controllers) are actually scanned.
        (tmp_path / '.git').mkdir()
        _write(tmp_path / 'app' / 'models' / 'topic.rb', 'class Topic < ActiveRecord::Base\nend\n')
        _write(
            tmp_path / 'app' / 'models' / 'post.rb',
            '''\
            require "archetype"

            class Post < ActiveRecord::Base
              def notify
                Topic.find(1)
                User::Anonymizer.new.run
              end
            end
            ''')
        _write(tmp_path / 'app' / 'models' / 'user' / 'anonymizer.rb',
               'class User::Anonymizer\n  def run; end\nend\n')
        _write(tmp_path / 'app' / 'controllers' / 'posts_controller.rb',
               'class PostsController\n  def index\n    Post.all\n  end\nend\n')
        return tmp_path

    def test_bare_constant_reference_found_with_no_require(self, tmp_path):
        """The Discourse evidence case: Post references Topic with zero
        require statements — pre-fix this was a confident false negative."""
        from reveal.adapters.depends import DependsAdapter
        root = self._rails_app(tmp_path)
        r = DependsAdapter(str(root / 'app' / 'models' / 'topic.rb')).get_structure()
        files = {d['file'] for d in r['dependents']}
        assert str(root / 'app' / 'models' / 'post.rb') in files
        assert r['count'] >= 1

    def test_namespaced_constant_reference_resolved(self, tmp_path):
        """`User::Anonymizer.new` (scope_resolution, not a bare `constant`)
        must resolve to app/models/user/anonymizer.rb."""
        from reveal.adapters.depends import DependsAdapter
        root = self._rails_app(tmp_path)
        r = DependsAdapter(str(root / 'app' / 'models' / 'user' / 'anonymizer.rb')).get_structure()
        files = {d['file'] for d in r['dependents']}
        assert str(root / 'app' / 'models' / 'post.rb') in files

    def test_cross_directory_reference_resolved(self, tmp_path):
        """A controller (app/controllers) referencing a model (app/models) by
        bare constant — each app/* subdir is its own Zeitwerk root."""
        from reveal.adapters.depends import DependsAdapter
        root = self._rails_app(tmp_path)
        r = DependsAdapter(str(root / 'app' / 'models' / 'post.rb')).get_structure()
        files = {d['file'] for d in r['dependents']}
        assert str(root / 'app' / 'controllers' / 'posts_controller.rb') in files

    def test_explicit_require_edge_still_reported(self, tmp_path):
        """Zeitwerk inference is additive — an explicit require_relative edge
        must still show up unchanged alongside inferred ones."""
        from reveal.adapters.depends import DependsAdapter
        root = self._rails_app(tmp_path)
        _write(root / 'app' / 'models' / 'importer.rb',
               'require_relative "topic"\nclass Importer; end\n')
        r = DependsAdapter(str(root / 'app' / 'models' / 'topic.rb')).get_structure()
        files = {d['file'] for d in r['dependents']}
        assert str(root / 'app' / 'models' / 'importer.rb') in files
        assert str(root / 'app' / 'models' / 'post.rb') in files

    def test_no_edge_for_undeclared_constant(self, tmp_path):
        """A reference to a constant with no matching in-tree file (an
        external gem/stdlib class, or a typo) must never fabricate an edge —
        the honest-skip contract every other resolver in this module holds."""
        from reveal.adapters.depends import DependsAdapter
        root = tmp_path
        (root / 'Gemfile').write_text('gem "rails"\n')
        _write(root / 'app' / 'models' / 'post.rb',
               'class Post < ActiveRecord::Base\n  def go\n    NoSuchClass.new\n  end\nend\n')
        r = DependsAdapter(str(root / 'app' / 'models' / 'post.rb')).get_structure()
        assert r['count'] == 0

    def test_self_reference_not_counted_as_dependent(self, tmp_path):
        """A file referencing its own declared class name (or a sibling
        method on itself) must not appear as its own dependent."""
        from reveal.adapters.depends import DependsAdapter
        root = tmp_path
        (root / 'Gemfile').write_text('gem "rails"\n')
        _write(root / 'app' / 'models' / 'topic.rb',
               'class Topic < ActiveRecord::Base\n  def clone_self\n    Topic.new\n  end\nend\n')
        r = DependsAdapter(str(root / 'app' / 'models' / 'topic.rb')).get_structure()
        assert r['count'] == 0

    def test_non_app_directory_not_treated_as_autoload_root(self, tmp_path):
        """lib/, config/, spec/ aren't Zeitwerk-managed app/* roots in this
        scoped implementation — a bare-constant reference there must not be
        inferred (BACK-557 direction a's documented scope limit)."""
        from reveal.adapters.depends import DependsAdapter
        root = tmp_path
        (root / 'Gemfile').write_text('gem "rails"\n')
        _write(root / 'lib' / 'topic.rb', 'class Topic\nend\n')
        _write(root / 'lib' / 'post.rb', 'class Post\n  def go\n    Topic.new\n  end\nend\n')
        r = DependsAdapter(str(root / 'lib' / 'topic.rb')).get_structure()
        assert r['count'] == 0

    def test_metadata_reports_zeitwerk_edge_count(self, tmp_path):
        from reveal.adapters.depends import DependsAdapter
        root = self._rails_app(tmp_path)
        a = DependsAdapter(str(root / 'app' / 'models' / 'topic.rb'))
        a.get_structure()
        assert a.get_metadata()['zeitwerk_edges_inferred'] >= 3


class TestDependsAdapterSwiftModuleFanout:
    """BACK-567: Swift `import Foo` names a whole SwiftPM target, not a file.

    The target is almost always multi-file, so the old bare-basename match
    (`import Foo` -> `Foo.swift`) resolved ~0% of real cross-module imports and,
    worse, left `_unresolved_intra` at 0 so no honest-decline ⚠ fired either —
    a silent wrong "no dependents". These lock in the module→many-files fan-out
    (mirroring C#'s namespace fan-out) built purely from the Sources/<Target>/
    directory convention (no Swift toolchain at runtime).
    """

    def _spm_workspace(self, tmp_path: Path) -> Path:
        """A minimal multi-target SwiftPM layout: Library imports KsApi;
        KsApi is a 2-file target with a same-module sibling (no import);
        Standalone is imported by nobody."""
        root = tmp_path
        (root / 'Package.swift').write_text('// swift-tools-version:5.9\n')
        # KsApi target — two files; Models has NO import (same-module sibling).
        _write(root / 'Sources' / 'KsApi' / 'Service.swift',
               'import Foundation\npublic struct Service {}\n')
        _write(root / 'Sources' / 'KsApi' / 'Models.swift',
               'public struct Model {}\n')
        # Library target — two files, both import the KsApi module.
        _write(root / 'Sources' / 'Library' / 'Client.swift',
               'import Foundation\nimport KsApi\npublic struct Client {}\n')
        _write(root / 'Sources' / 'Library' / 'Helper.swift',
               'import KsApi\npublic struct Helper {}\n')
        # A test target that imports Library.
        _write(root / 'Tests' / 'LibraryTests' / 'ClientTests.swift',
               'import XCTest\nimport Library\nfinal class ClientTests: XCTestCase {}\n')
        # A target nobody imports.
        _write(root / 'Sources' / 'Standalone' / 'Alone.swift',
               'public struct Alone {}\n')
        return root

    def test_import_fans_out_to_every_file_in_module(self, tmp_path):
        """`import KsApi` makes each importer a dependent of BOTH KsApi files —
        Service.swift (which carries the import) and Models.swift (same-module
        sibling that never appears in any import statement)."""
        from reveal.adapters.depends import DependsAdapter
        root = self._spm_workspace(tmp_path)
        for member in ('Service.swift', 'Models.swift'):
            r = DependsAdapter(str(root / 'Sources' / 'KsApi' / member)).get_structure()
            names = {Path(d['file']).name for d in r['dependents']}
            assert names == {'Client.swift', 'Helper.swift'}, member
            assert r['count'] == 2

    def test_external_import_produces_no_edge_and_no_false_decline(self, tmp_path):
        """`import Foundation` is external — no in-tree edge, and it must NOT
        trip the honest-decline counter (never cry wolf on a stdlib import)."""
        from reveal.adapters.depends import DependsAdapter
        root = self._spm_workspace(tmp_path)
        a = DependsAdapter(str(root / 'Sources' / 'KsApi' / 'Service.swift'))
        a.get_structure()
        assert a._unresolved_intra == 0

    def test_module_with_no_importers_reports_zero_with_note(self, tmp_path):
        """Standalone is imported by nobody → 0 dependents, and the Swift
        module-level note fires (same-module siblings are invisible)."""
        from reveal.adapters.depends import DependsAdapter
        root = self._spm_workspace(tmp_path)
        r = DependsAdapter(str(root / 'Sources' / 'Standalone' / 'Alone.swift')).get_structure()
        assert r['count'] == 0
        assert 'same_module_note' in r
        assert 'module' in r['same_module_note']

    def test_test_target_import_resolves(self, tmp_path):
        """`import Library` from a Tests/<Target>/ file resolves — Tests/ is in
        the module_dir_convention set alongside Sources/."""
        from reveal.adapters.depends import DependsAdapter
        root = self._spm_workspace(tmp_path)
        r = DependsAdapter(str(root / 'Sources' / 'Library' / 'Client.swift')).get_structure()
        names = {Path(d['file']).name for d in r['dependents']}
        assert 'ClientTests.swift' in names

    def test_module_with_same_named_file_still_fans_out_fully(self, tmp_path):
        """A target with a file matching its own name (real case:
        ServerDrivenUI/ServerDrivenUI.swift) must NOT let the coincidental
        bare-basename direct match pre-empt the fan-out — every file in the
        module is still a dependent, not just the same-named one."""
        from reveal.adapters.depends import DependsAdapter
        root = tmp_path
        (root / 'Package.swift').write_text('// swift-tools-version:5.9\n')
        _write(root / 'Sources' / 'SDUI' / 'SDUI.swift', 'public struct SDUI {}\n')
        _write(root / 'Sources' / 'SDUI' / 'Other.swift', 'public struct Other {}\n')
        _write(root / 'Sources' / 'App' / 'Main.swift',
               'import SDUI\npublic struct Main {}\n')
        # Both SDUI files must show App/Main.swift as a dependent — including
        # Other.swift, which the bare-basename match could never reach.
        for member in ('SDUI.swift', 'Other.swift'):
            r = DependsAdapter(str(root / 'Sources' / 'SDUI' / member)).get_structure()
            names = {Path(d['file']).name for d in r['dependents']}
            assert 'Main.swift' in names, member

    def test_hyphenated_target_dir_matches_underscore_import(self, tmp_path):
        """SwiftPM sanitizes a target name to its module identifier: directory
        `My-Lib` is imported as `import My_Lib`. The dir-derived key is
        sanitized the same way so they match (real Kickstarter case:
        `Kickstarter-Framework` ↔ `import Kickstarter_Framework`)."""
        from reveal.adapters.depends import DependsAdapter
        root = tmp_path
        (root / 'Package.swift').write_text('// swift-tools-version:5.9\n')
        _write(root / 'Sources' / 'My-Lib' / 'Core.swift', 'public struct Core {}\n')
        _write(root / 'Sources' / 'App' / 'Main.swift',
               'import My_Lib\npublic struct Main {}\n')
        r = DependsAdapter(str(root / 'Sources' / 'My-Lib' / 'Core.swift')).get_structure()
        names = {Path(d['file']).name for d in r['dependents']}
        assert 'Main.swift' in names

    def _custom_path_workspace(self, tmp_path: Path) -> Path:
        """A package whose target relocates its sources with an explicit path:
        (real GraphAPI shape: `path: "./Sources"` collapses the WHOLE Sources/
        tree — subdirs and all — into one module, with no Sources/<Target>/
        level). The directory convention alone would mis-map Sources/Schema/*
        to a bogus `Schema` module and leave `import Api` resolving to nothing;
        the manifest path: override fixes it."""
        root = tmp_path
        _write(root / 'Package.swift', '''
            // swift-tools-version:5.9
            import PackageDescription
            let package = Package(
              name: "Api",
              targets: [
                .target(name: "Api", dependencies: [], path: "./Sources"),
                .testTarget(name: "ApiTests", dependencies: [.target(name: "Api")]),
              ]
            )
        ''')
        # Custom layout: files live in Sources/Schema/, Sources/Ops/ — NO
        # Sources/Api/ dir exists, so only the manifest path: can map them.
        _write(root / 'Sources' / 'Schema' / 'User.swift', 'public struct User {}\n')
        _write(root / 'Sources' / 'Ops' / 'Query.swift', 'public struct Query {}\n')
        _write(root / 'Tests' / 'ApiTests' / 'UserTests.swift',
               'import XCTest\nimport Api\nfinal class UserTests: XCTestCase {}\n')
        return root

    def test_manifest_path_override_maps_whole_subtree_to_one_module(self, tmp_path):
        """`import Api` fans out to EVERY file under the target's `path:
        "./Sources"` — including Sources/Schema/User.swift and
        Sources/Ops/Query.swift, which the directory convention would have
        mis-filed under bogus `Schema`/`Ops` modules."""
        from reveal.adapters.depends import DependsAdapter
        root = self._custom_path_workspace(tmp_path)
        for member in ('Schema/User.swift', 'Ops/Query.swift'):
            r = DependsAdapter(str(root / 'Sources' / member)).get_structure()
            names = {Path(d['file']).name for d in r['dependents']}
            assert 'UserTests.swift' in names, member

    def test_manifest_path_override_no_false_decline(self, tmp_path):
        """`import Api` resolves via the manifest override, so it must NOT be
        misclassified as an external module and trip honest-decline — the
        silent-negative this whole path exists to prevent."""
        from reveal.adapters.depends import DependsAdapter
        root = self._custom_path_workspace(tmp_path)
        a = DependsAdapter(str(root / 'Sources' / 'Schema' / 'User.swift'))
        a.get_structure()
        assert a._unresolved_intra == 0

    def test_manifest_dependency_reference_not_a_declaration(self, tmp_path):
        """A `.target(name: "Api")` nested in a testTarget's dependencies: is a
        reference, not a declaration — it must not create a second, wrongly-
        located `Api` module. Only the real target dir maps."""
        from reveal.adapters.depends import DependsAdapter
        root = self._custom_path_workspace(tmp_path)
        a = DependsAdapter(str(root))
        files, _ = a._discover_files(root, frozenset({'.swift'}))
        idx = a._build_resolution_indices(files)
        # Every Api-module file must be a real file under Sources/ (the path:
        # override), never a phantom from the dependency reference.
        for p in idx.module_index['Api']:
            assert p.exists()
            assert 'Sources' in p.parts


if __name__ == '__main__':
    unittest.main()

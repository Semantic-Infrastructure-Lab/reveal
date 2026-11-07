"""Go import extraction using tree-sitter.

Previous implementation: 172 lines with tree-sitter + 2 regex patterns
Current implementation: 178 lines using pure tree-sitter AST extraction

Benefits:
- Eliminates all regex patterns (package path, alias)
- Uses tree-sitter node types (package_identifier, dot, blank_identifier)
- More robust handling of Go import syntax variations
"""

import logging
import re
from pathlib import Path
from typing import Callable, Dict, List, Optional, Set, Tuple
from ...core import node_children as _children
from ...core.treesitter_compat import _zero_arg

# Go modules' semantic-import-versioning convention: a major version >= 2
# suffixes the import path (`k8s.io/klog/v2`), and the package's declared name
# is usually the segment BEFORE the suffix (`package klog`, BACK-431) -- but
# not always: `k8s.io/api/core/v1` declares `package v1` (BACK-1397). Both are
# offered as candidates; see _go_package_name_candidates().
_GO_MAJOR_VERSION_SUFFIX = re.compile(r'^v[0-9]+$')
# gopkg.in's `pkg.vN` form (`gopkg.in/yaml.v3` declares `package yaml`).
_GOPKG_IN_VERSION_SUFFIX = re.compile(r'\.v[0-9]+$')


def _go_package_name_candidates(package_path: str) -> List[str]:
    """Plausible local names for an unaliased import, most likely first.

    The name is whatever the target's `package` clause says, which the path only
    suggests: `k8s.io/klog/v2` is `klog` but `k8s.io/api/core/v1` is `v1`, and
    `github.com/mattn/go-sqlite3` is `sqlite3` (BACK-1397). A use of any of them
    counts, so a wrong guess can no longer flag a used import.
    """
    segments = package_path.split('/')
    last = segments[-1]
    if _GO_MAJOR_VERSION_SUFFIX.match(last) and len(segments) > 1:
        raw = [segments[-2], last]
    else:
        raw = [_GOPKG_IN_VERSION_SUFFIX.sub('', last)]
    names: List[str] = []
    for name in raw:
        for variant in (name, re.sub(r'^go-|[-.]go$', '', name)):
            if variant not in names:
                names.append(variant)
    return names

logger = logging.getLogger(__name__)


def _line_text(analyzer, line_number: int) -> str:
    """Full source line for a 1-indexed line number, or "" if out of range.

    BACK-432: I005/I001's noqa detection read ImportStatement.source_line,
    which every non-Python extractor left at its default "" — silently
    blind to duplicate-import detection and source-line-based suppression
    comments for Go/Rust/JS despite advertising support for them.
    """
    idx = line_number - 1
    if 0 <= idx < len(analyzer.lines):
        return analyzer.lines[idx].rstrip()
    return ""

from .types import ImportStatement
from .base import ImportsDiskCache, LanguageExtractor, nearest_marker_dir, register_extractor
from .packages import EMPTY_PACKAGES, PackageModel, PackageUnit

# Cross-invocation disk cache (BACK-626, extending BACK-625 to Go): same
# independent-reparse gap as PythonExtractor had -- extract_imports() does not
# share TreeSitterAnalyzer.get_structure()'s structure cache (BACK-535).
_IMPORTS_CACHE = ImportsDiskCache("go_imports")


@register_extractor
class GoExtractor(LanguageExtractor):
    """Go import extractor using pure tree-sitter parsing.

    Supports:
    - Single imports: import "fmt"
    - Grouped imports: import ( "fmt" "os" )
    - Aliased imports: import f "fmt"
    - Dot imports: import . "fmt"
    - Blank imports: import _ "database/sql/driver"
    """

    extensions = {'.go'}
    language_name = 'Go'
    package_manifests = ('go.mod', 'go.work')

    def extract_imports(self, file_path: Path) -> List[ImportStatement]:
        """Extract all import declarations from Go file using tree-sitter.

        Cached cross-invocation on disk (BACK-626), same pattern as
        PythonExtractor (BACK-625).

        Args:
            file_path: Path to .go file

        Returns:
            List of ImportStatement objects
        """
        return _IMPORTS_CACHE.get_or_compute(
            file_path, lambda: self._extract_imports_uncached(file_path),
            owner=self,
        )

    def _extract_imports_uncached(self, file_path: Path) -> List[ImportStatement]:
        analyzer = self._get_tree_analyzer(file_path)
        if not analyzer:
            return []

        imports = []

        # Find all import_spec nodes (works for both single and grouped imports)
        import_specs = analyzer._find_nodes_by_type('import_spec')
        for spec_node in import_specs:
            result = self._parse_import_spec(spec_node, file_path, analyzer)
            if result:
                imports.append(result)

        return imports

    def extract_symbols(self, file_path: Path) -> Set[str]:
        """Extract symbols used in Go file.

        Args:
            file_path: Path to source file

        Returns:
            Set of symbol names referenced in the file

        Used for detecting unused imports by comparing imported package names
        with actually-used symbols.
        """
        analyzer = self._get_tree_analyzer(file_path)
        if not analyzer:
            return set()

        symbols = set()

        # Find identifier nodes
        identifier_nodes = analyzer._find_nodes_by_type('identifier')

        for node in identifier_nodes:
            name = analyzer._get_node_text(node)

            # Filter out identifiers in definition contexts
            if self._is_usage_context(node):
                symbols.add(name)

            # Handle selector expressions (pkg.Function -> track 'pkg')
            if (
                _zero_arg(node, 'parent')
                and _zero_arg(_zero_arg(node, 'parent'), 'kind') == 'selector_expression'
            ):
                root = self._get_root_identifier(_zero_arg(node, 'parent'), analyzer)
                if root:
                    symbols.add(root)

        # Handle qualified types (pkg.Type in type position -> track 'pkg').
        # tree-sitter-go represents `sync.WaitGroup` as
        # qualified_type(package_identifier, type_identifier), NOT a
        # selector_expression, and the package part is a 'package_identifier'
        # node — so the identifier walk above never sees it and a package used
        # only for a type is falsely reported unused (BACK-420).
        for qt in analyzer._find_nodes_by_type('qualified_type'):
            if (
                _zero_arg(qt, 'child_count') > 0
                and _zero_arg(qt.child(0), 'kind') == 'package_identifier'
            ):
                symbols.add(analyzer._get_node_text(qt.child(0)))

        return symbols

    def _parse_import_spec(self, spec_node, file_path: Path, analyzer) -> ImportStatement | None:
        """Parse a Go import_spec node using tree-sitter AST.

        Tree-sitter provides structured nodes:
            "fmt"                           # interpreted_string_literal
            alias "github.com/user/pkg"     # package_identifier + interpreted_string_literal
            . "fmt"                         # dot + interpreted_string_literal
            _ "database/sql/driver"         # blank_identifier + interpreted_string_literal
        """
        line_number = _zero_arg(spec_node, 'start_position').row + 1

        # Extract components from AST
        package_path = None
        alias = None

        for child in _children(spec_node):
            if _zero_arg(child, 'kind') == 'interpreted_string_literal':
                # Extract package path (strip quotes)
                package_path = analyzer._get_node_text(child).strip('"')
            elif _zero_arg(child, 'kind') == 'package_identifier':
                # Aliased import: f "io"
                alias = analyzer._get_node_text(child)
            elif _zero_arg(child, 'kind') == 'dot':
                # Dot import: . "strings"
                alias = '.'
            elif _zero_arg(child, 'kind') == 'blank_identifier':
                # Blank import: _ "database/sql/driver"
                alias = '_'

        if not package_path:
            return None

        return self._create_import(
            file_path, line_number, package_path, alias,
            source_line=_line_text(analyzer, line_number),
        )

    @staticmethod
    def _create_import(
        file_path: Path,
        line_number: int,
        package_path: str,
        alias: Optional[str] = None,
        source_line: str = "",
    ) -> ImportStatement:
        """Create ImportStatement for a Go import.

        Args:
            file_path: Path to source file
            line_number: Line number of import
            package_path: Package path (e.g., "fmt", "github.com/user/pkg")
            alias: Optional alias (identifier, '.', or '_')

        Returns:
            ImportStatement object
        """
        # Determine import type based on alias
        if alias == '.':
            import_type = 'dot_import'  # Imports into current namespace
        elif alias == '_':
            import_type = 'blank_import'  # Side-effect only
        elif alias:
            import_type = 'aliased_import'
        else:
            import_type = 'go_import'

        # Go imports are never relative (no ./ syntax)
        # Internal packages start with module name, external from domain
        is_relative = False

        # Determine the local name the package is referenced by — this is what
        # I001 compares against the used-symbol set. For an aliased import
        # (`utilruntime "k8s.io/.../runtime"`) the code uses the *alias*, not the
        # path basename, so imported_names must be the alias or the import reads
        # as falsely unused (BACK-420). Blank imports ('_') bind no name; dot
        # imports ('.') pull names into scope directly (skipped by I001 anyway).
        alt_names: tuple = ()
        if alias == '_':
            imported_names = []
        elif alias and alias not in ('.', '_'):
            imported_names = [alias]
        else:
            candidates = _go_package_name_candidates(package_path)
            imported_names = [candidates[0]]
            alt_names = tuple(candidates[1:])

        return ImportStatement(
            file_path=file_path,
            line_number=line_number,
            module_name=package_path,
            imported_names=imported_names,
            is_relative=is_relative,
            import_type=import_type,
            alias=alias,
            source_line=source_line,
            alt_names=alt_names,
        )

    def _is_usage_context(self, node) -> bool:
        """Check if identifier is in a usage context (not definition).

        Filters out:
        - Function/method/type declarations
        - Parameter names
        - Field names in struct definitions
        - Variable declarations (left side of :=)
        - Import names
        """
        if not _zero_arg(node, 'parent'):
            return True

        # Walk up to check if inside import
        current = node
        while current:
            if _zero_arg(current, 'kind') in ('import_declaration', 'import_spec'):
                return False
            current = _zero_arg(current, 'parent')

        parent_type = _zero_arg(_zero_arg(node, 'parent'), 'kind')

        # Skip definition contexts
        if parent_type in ('function_declaration', 'method_declaration',
                          'type_declaration', 'type_spec',
                          'parameter_declaration', 'parameter_list',
                          'field_declaration', 'field_identifier'):
            return False

        # For short variable declarations (x := 5), check if left side
        if parent_type == 'short_var_declaration':
            # First child (or part of expression_list) is being declared
            _p = _zero_arg(node, 'parent')
            if (_p and _zero_arg(_p, 'child_count') > 0 and
                    _zero_arg(_p.child(0), 'start_byte') == _zero_arg(node, 'start_byte')):
                return False

        # For var declarations
        if parent_type == 'var_spec':
            # Name is first child
            _p = _zero_arg(node, 'parent')
            if (_p and _zero_arg(_p, 'child_count') > 0 and
                    _zero_arg(_p.child(0), 'start_byte') == _zero_arg(node, 'start_byte')):
                return False

        return True

    def _get_root_identifier(self, selector_node, analyzer):
        """Extract root identifier from selector expression chain.

        Examples:
            fmt.Println -> 'fmt'
            os.File.Read -> 'os'
        """
        # Walk up selector expression chain to find root
        current = selector_node
        while current and _zero_arg(current, 'kind') == 'selector_expression':
            if _children(current):
                current = current.child(0)  # Get operand (left side)
            else:
                break

        # Should now be an identifier
        if current and _zero_arg(current, 'kind') == 'identifier':
            return analyzer._get_node_text(current)

        return None

    def package_units(self, manifests: List[Path], files: List[Path],
                      on_error: Callable[[OSError], None]) -> List[PackageUnit]:
        """Each go.mod's module, linked to the in-tree modules it can import: its ``replace ... => ./path``
        targets and, when a go.work ``use``s it, every other module that go.work uses and its own local
        replaces (BACK-2557)."""
        return _go_units(manifests, on_error)

    def resolve_import_targets(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        packages: Optional[PackageModel] = None,
    ) -> List[Path]:
        primary = self.resolve_import(stmt, base_path, search_paths=search_paths, packages=packages)
        return [primary] if primary is not None else []

    def resolve_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        packages: Optional[PackageModel] = None,
    ) -> Optional[Path]:
        """Resolve a Go import path to its package directory, or None (stdlib, a dependency, or no module).

        Go has no relative imports: a path names a package of some module, and a package is a directory.
        ``packages`` is the scan's package model (BACK-2559). Where it read the file's go.mod, the path
        resolves in the in-tree module whose path contains it, the longest one winning: the file's own
        module, a ``replace`` target that is a local directory, or another module of a go.work that uses
        this one (BACK-2557). Without a model (calls://) only the nearest go.mod's own module counts.
        """
        package_path = stmt.module_name
        model = packages or EMPTY_PACKAGES
        directory = base_path.resolve()
        if model.owns(directory):
            return _resolve_in_units(package_path, model.local_units(directory))
        module_root = self._find_go_module_root(base_path)
        if module_root is None:
            return None
        module_name = self._get_module_name(module_root)
        if not module_name:
            return None
        return _resolve_in_units(package_path, ((module_name, PackageUnit(module_root / 'go.mod', module_name,
                                                                           module_root)),))

    def is_intra_project_import(
        self,
        stmt: ImportStatement,
        base_path: Path,
        search_paths: Optional[List[Path]] = None,
        project_namespaces: Optional[Set[str]] = None,
    ) -> Optional[bool]:
        """Go classification is precise: an import is intra-project iff its
        package path is inside the module named by go.mod (the test resolve_import
        applies to the file's own module). If there's no go.mod we can't tell (None).
        A go.work or replace sibling still classifies as external here: classification
        moves onto the package model in BACK-2550."""
        module_root = self._find_go_module_root(base_path)
        if not module_root:
            return None
        module_name = self._get_module_name(module_root)
        if not module_name:
            return None
        return module_contains(module_name, stmt.module_name)

    def _find_go_module_root(self, start_path: Path) -> Optional[Path]:
        """Find go.mod file by walking up directory tree.

        Args:
            start_path: Directory to start search from

        Returns:
            Directory containing go.mod, or None if not found
        """
        return nearest_marker_dir(start_path, 'go.mod')

    def _get_module_name(self, module_root: Path) -> Optional[str]:
        """Extract module name from go.mod file.

        Args:
            module_root: Directory containing go.mod

        Returns:
            Module name (e.g., 'github.com/user/repo'), or None if not found
        """
        go_mod = module_root / 'go.mod'
        if not go_mod.exists():
            return None

        try:
            content = go_mod.read_text(encoding='utf-8')
            # Parse "module name" from first line
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('module '):
                    return line.split()[1]
        except (OSError, UnicodeDecodeError) as e:
            # An unreadable or non-UTF-8 go.mod just means module-relative import
            # resolution degrades to best-effort -- not a parse failure of any Go source file.
            logger.debug("_get_module_name failed for %s: %s", module_root, e)
            return None

        return None


def module_contains(module_path: str, package_path: str) -> bool:
    """Whether ``package_path`` is a package of the module ``module_path``: equal, or below it on a ``/``
    boundary, so ``k8s.io/apimachinery/...`` is not inside ``k8s.io/api`` (BACK-2558)."""
    return package_path == module_path or package_path.startswith(module_path + '/')


def _resolve_in_units(package_path: str, units: Tuple[Tuple[str, PackageUnit], ...]) -> Optional[Path]:
    """The package directory ``package_path`` names in the longest-pathed module of ``units`` that contains it."""
    matches = [(name, unit) for name, unit in units if module_contains(name, package_path)]
    if not matches:
        return None
    name, unit = max(matches, key=lambda match: len(match[0]))
    package_dir = unit.manifest.parent / package_path[len(name):].lstrip('/')
    return package_dir.resolve() if package_dir.is_dir() else None


def _go_tokens(text: str) -> List[str]:
    return [token.strip('"`') for token in text.split()]


def go_directives(text: str) -> List[Tuple[str, List[str]]]:
    """(verb, arguments) for each directive of a go.mod or go.work, a block's entries each under its verb
    (``replace ( a => ./a )`` reads as ``('replace', ['a', '=>', './a'])``). Comments are dropped."""
    directives: List[Tuple[str, List[str]]] = []
    block: Optional[str] = None
    for raw in text.split('\n'):
        line = raw.split('//', 1)[0].strip()
        if not line:
            continue
        if block is not None:
            if line == ')':
                block = None
            else:
                directives.append((block, _go_tokens(line)))
            continue
        verb, _, rest = line.replace('\t', ' ').partition(' ')
        if rest.strip() == '(':
            block = verb
        else:
            directives.append((verb, _go_tokens(rest)))
    return directives


def _local_replace(arguments: List[str], manifest_dir: Path) -> Optional[Tuple[str, Path]]:
    """(module path importers spell, target directory) of a ``replace`` whose target is a directory (Go: a
    path beginning ./ or ../, or absolute); None for a module replacement or a malformed line."""
    if '=>' not in arguments:
        return None
    left, right = arguments[:arguments.index('=>')], arguments[arguments.index('=>') + 1:]
    if not left or not right:
        return None
    target = right[0]
    if not (target.startswith(('./', '../', '.\\', '..\\')) or Path(target).is_absolute()):
        return None
    return left[0], (manifest_dir / target).resolve()


def _read_go_manifest(manifest: Path, on_error: Callable[[OSError], None]) -> Optional[str]:
    """A go.mod/go.work's text; None when it cannot be read (reported) or is not UTF-8 (go rejects it too)."""
    try:
        return manifest.read_text(encoding='utf-8')
    except OSError as error:
        on_error(error)
    except UnicodeDecodeError:
        pass
    return None


_Replaces = List[Tuple[str, Path]]  # (module path importers spell, local target directory)


def _read_go_manifests(manifests: List[Path], on_error: Callable[[OSError], None]
                       ) -> Tuple[Dict[Path, Tuple[str, _Replaces]], List[Tuple[Set[Path], _Replaces]]]:
    """Every go.mod's (module path, local replaces) by directory, and every go.work's (used module
    directories, local replaces)."""
    modules: Dict[Path, Tuple[str, _Replaces]] = {}
    workspaces: List[Tuple[Set[Path], _Replaces]] = []
    for manifest in manifests:
        text = _read_go_manifest(manifest, on_error)
        if text is None:
            continue
        directives = go_directives(text)
        replaces = [r for verb, args in directives if verb == 'replace'
                    and (r := _local_replace(args, manifest.parent)) is not None]
        if manifest.name == 'go.work':
            used = {(manifest.parent / args[0]).resolve() for verb, args in directives if verb == 'use' and args}
            workspaces.append((used, replaces))
            continue
        module = next((args[0] for verb, args in directives if verb == 'module' and args), None)
        if module is not None:
            modules[manifest.parent] = (module, replaces)
    return modules, workspaces


def _go_links(directory: Path, replaces: _Replaces, modules: Dict[Path, Tuple[str, _Replaces]],
              workspaces: List[Tuple[Set[Path], _Replaces]]) -> Tuple[Tuple[str, Path], ...]:
    """The local dependencies of the module in ``directory``, as (module path, its go.mod): a go.work that uses
    it contributes its replaces (they override the module's own) and every other module it uses; then the
    module's own local replaces. The first link for a module path wins."""
    links: _Replaces = []
    for used, work_replaces in workspaces:
        if directory in used:
            links += work_replaces
            links += [(modules[d][0], d) for d in sorted(used) if d in modules and d != directory]
    links += replaces
    dependencies: Dict[str, Path] = {}
    for name, target in links:
        dependencies.setdefault(name, target / 'go.mod')
    return tuple(dependencies.items())


def _go_units(manifests: List[Path], on_error: Callable[[OSError], None]) -> List[PackageUnit]:
    modules, workspaces = _read_go_manifests(manifests, on_error)
    return [PackageUnit(directory / 'go.mod', module, directory, (directory,),
                        _go_links(directory, replaces, modules, workspaces))
            for directory, (module, replaces) in sorted(modules.items())]


# Backward compatibility: Keep old function-based API
def extract_go_imports(file_path: Path) -> List[ImportStatement]:
    """Extract all import declarations from Go file.

    DEPRECATED: Use GoExtractor().extract_imports() instead.
    Kept for backward compatibility with existing code.
    """
    extractor = GoExtractor()
    return extractor.extract_imports(file_path)


__all__ = [
    'GoExtractor',
    'extract_go_imports',  # deprecated
]

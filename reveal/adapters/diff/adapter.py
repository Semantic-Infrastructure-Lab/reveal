"""Core diff adapter for comparing two reveal resources."""

import os
from reveal.errors import ElementNotFoundError
from typing import Dict, Any, Optional, Tuple
from reveal.reveal_types import CONTRACT_VERSION
from reveal.utils.path_utils import failure_records

from .parsing import parse_diff_uris, split_trailing_element
from .resolution import (resolve_uri, extract_metadata, find_element, element_names,
                         read_element_source, read_source_text)
from .help import PARAM_SPECS, RESOURCE_SPEC, get_schema as _get_schema, get_help as _get_help
from ..base import ResourceAdapter, register_adapter, register_renderer
from .renderer import DiffRenderer
from ...utils.query_binding import bind_declared_params
from ...utils.query_parser import QueryParams
from ...utils.results import (AnalysisCompleteness, FailureCause, ResultBuilder,
                              result_execution_facts)


@register_adapter('diff')
@register_renderer(DiffRenderer)
class DiffAdapter(ResourceAdapter):
    """Compare two reveal-compatible resources.

    Usage:
        reveal diff LEFT RIGHT[/ELEMENT]          # or diff://LEFT:RIGHT[/ELEMENT]

    Examples:
        reveal diff app.py backup/app.py          # File comparison
        reveal diff app.py old.py/handle_request  # Element-specific diff

    Compares every element category the analyzer emits: functions, classes, imports,
    and interfaces, structs, enums, types... by name (BACK-1732). A pair of files that
    differ outside every compared element is disclosed in ``meta.warnings``, never called
    clean. A resource whose structure has no functions, classes or imports (env://,
    sqlite://, mysql://, JSON/YAML files) is declined as not applicable, so it is not a
    schema- or config-drift check (BACK-1642, BACK-1689).
    """
    HELP_CLUSTER = 'Code Analysis'

    resource: str
    left_uri: str
    right_uri: str
    left_structure: Optional[Dict[str, Any]]
    right_structure: Optional[Dict[str, Any]]
    embedded_element: Optional[str] = None  # from diff://a.py:b.py/element; read by the CLI router

    ELEMENT_RESULT_TYPE = 'diff_element'  # verdict lives in 'change' (BACK-1637)

    LEGACY_INIT = False
    CLI_QUERY_FLAGS = {'respect_gitignore': 'respect_gitignore=false'}  # directory diffs walk (BACK-1386)
    CANONICAL_EMPTY_RESOURCE = ''
    # The declaration `reveal diff` and diff:// are both generated from (D20, BACK-2214): the resource is the pair,
    # ``reveal diff LEFT RIGHT`` or diff://LEFT:RIGHT, each side a path or a URI, with an optional /ELEMENT after the
    # right side; diff takes no control. A directory pair walks (the walk policy and --exclude apply).
    # diff's one control is the walk's exclude: any other keyword, URI key or flag is an invalid request naming it.
    BOUND_QUERY_CALL = True
    PARAM_SPECS: tuple = PARAM_SPECS
    RESOURCE_SPEC = RESOURCE_SPEC
    RESULT_TYPE = 'diff_comparison'
    # The pair's request answers the element its resource names (diff://L:R/ELEMENT): the type follows the resource,
    # which the scope path (``resource_path``) no longer spells, so the comparison's request admits the element's type.
    RESULT_TYPE_VARIANTS = {RESULT_TYPE: (ELEMENT_RESULT_TYPE,)}
    DEFAULT_FAIL_ON = 'none'
    FINDINGS_POLICIES = ('none',)

    @classmethod
    def uri_execution_facts(cls, resource: str):
        """Every pair shares D6: a side that does not exist, or an element neither side has, is an invalid request
        (exit 2); a side that could not be read is a failed analysis (exit 3)."""
        return cls.execution_facts

    @classmethod
    def uri_result_type(cls, resource: str) -> str:
        """The element's diff when the resource names one after its right side, else the comparison."""
        try:
            _, right = parse_diff_uris(resource.partition('?')[0])
        except ValueError:
            return cls.RESULT_TYPE
        return cls.ELEMENT_RESULT_TYPE if split_trailing_element(right)[1] else cls.RESULT_TYPE

    @classmethod
    def resource_path(cls, resource: str) -> str:
        """The filesystem path the pair names, for the walk's scope (--exclude, REVEAL_IGNORE) and the project config:
        the directory both local sides sit under, or the left local file when every local side is a file (a file pair
        has nothing to prune). A URI side (git://) names no working-tree path; a pair with no local side names none."""
        try:
            left, right = parse_diff_uris(resource.partition('?')[0])
        except ValueError:
            return resource
        right = split_trailing_element(right)[0]
        local = [side.removeprefix('file://') for side in (left, right)]
        local = [os.path.expanduser(side) for side in local if '://' not in side]
        if not local:
            return ''
        if all(os.path.isfile(side) for side in local):
            return local[0]
        absolute = any(os.path.isabs(side) for side in local)
        try:
            return os.path.commonpath([os.path.abspath(side) if absolute else os.path.normpath(side)
                                       for side in local]) or '.'
        except ValueError:  # sides on two Windows drives share no directory: the walk has no one root
            return ''

    @staticmethod
    def execution_facts(result):
        """Missing targets are invalid requests; failed required reads are analysis loss."""
        errors = result.get('meta', {}).get('errors', []) if isinstance(result, dict) else []
        cause = (FailureCause.INVALID_REQUEST if any(e.get('code') == 'invalid_request' for e in errors)
                 else FailureCause.ANALYSIS)
        return result_execution_facts(result, completeness=AnalysisCompleteness.COMPLETE,
                                      failure_cause=cause)

    def __init__(self, resource: str = '', query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None):
        """Initialize from the pair diff://LEFT:RIGHT[/ELEMENT] (``reveal diff LEFT RIGHT[/ELEMENT]``) names.

        Args:
            resource: ``LEFT:RIGHT``, each side a path or a URI, with an optional ``/ELEMENT`` after the right side
            query: The URI query, bound through the declaration: diff takes no control, so any key is an invalid request
            params: Already-bound or typed controls, in place of *query*

        Raises:
            TypeError: When no pair is given (the generic handler's no-argument pattern, V019)
            ValueError: When the pair has no ``:`` between two sides, or a control is given
        """
        if params is not None:
            self.query_params = params if isinstance(params, QueryParams) else bind_declared_params(
                PARAM_SPECS, params, transport='typed')
        else:
            self.query_params = bind_declared_params(PARAM_SPECS, query or '', transport='uri')
        if not resource:
            raise TypeError("diff requires a pair: reveal diff LEFT RIGHT, or diff://LEFT:RIGHT")
        self.resource = resource
        # parse_diff_uris handles Windows drive letters and all URI schemes
        try:
            self.left_uri, self.right_uri = parse_diff_uris(resource)
            self.right_uri, self.embedded_element = split_trailing_element(self.right_uri)
        except ValueError:
            raise ValueError(
                "diff requires 'left:right' format (reveal diff LEFT RIGHT). "
                "Got: {!r}. Example: reveal diff app.py backup/app.py".format(resource)
            )
        self.left_structure = None
        self.right_structure = None

    @staticmethod
    def _parse_diff_uris(resource: str) -> Tuple[str, str]:
        """Parse left:right from diff resource string.

        Delegates to parsing.parse_diff_uris for backward compatibility.
        Tests may call this as DiffAdapter._parse_diff_uris().

        Args:
            resource: The resource string to parse

        Returns:
            Tuple of (left_uri, right_uri)

        Raises:
            ValueError: If parsing fails
        """
        return parse_diff_uris(resource)

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for diff:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return _get_schema()

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for diff:// adapter.

        Help data loaded from reveal/adapters/help_data/diff.yaml
        to reduce function complexity.
        """
        return _get_help()

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get diff summary between two resources.

        Returns:
            {
                'type': 'diff',
                'left': {'uri': ..., 'type': ...},
                'right': {'uri': ..., 'type': ...},
                'summary': {
                    'functions': {'added': 2, 'removed': 1, 'modified': 3},
                    'classes': {'added': 0, 'removed': 0, 'modified': 1},
                    'imports': {'added': 5, 'removed': 2},
                    'interfaces': {...},  # any other category either side has
                },
                'diff': {
                    'functions': [...],  # Detailed function diffs
                    'classes': [...],    # Detailed class diffs
                    'imports': [...],    # Import changes
                    'interfaces': [...], # added/removed/modified by name
                },
                'meta': {'warnings': [{'type': 'not_compared', ...}]},  # only when needed
            }
        """
        from ...diff import compute_structure_diff

        if self.embedded_element:
            # diff://a.py:b.py/element names one element: the structure call answers it, as the CLI router does through
            # get_element (BACK-2764; the API answered the whole comparison).
            element = self.get_element(self.embedded_element, **kwargs)
            if element is None:
                raise ElementNotFoundError(self.embedded_element)
            # The element envelope the generic URI route gave it (``_element_envelope``): reveal diff and diff:// answer
            # through the declared route, which requires a complete answer (BACK-2214).
            return {'contract_version': CONTRACT_VERSION, 'type': self.ELEMENT_RESULT_TYPE,
                    'source': f'diff://{self.resource}', 'source_type': 'runtime', **element}

        # Resolve both URIs using existing adapter infrastructure
        left_struct = resolve_uri(self.left_uri, **kwargs)
        right_struct = resolve_uri(self.right_uri, **kwargs)

        # Compute semantic diff
        diff_result = compute_structure_diff(left_struct, right_struct)

        return ResultBuilder.create(
            result_type='diff_comparison',
            source=f"{self.left_uri} vs {self.right_uri}",
            source_type='runtime',
            contract_version=CONTRACT_VERSION,
            warnings=(self._uncompared_warnings(diff_result)
                      + self._skipped_warnings(left_struct, right_struct)) or None,
            data={
                'left': extract_metadata(left_struct, self.left_uri),
                'right': extract_metadata(right_struct, self.right_uri),
                'summary': diff_result['summary'],
                'diff': diff_result['details'],
            }
        )

    def _uncompared_warnings(self, diff_result: Dict[str, Any]) -> list:
        """What the comparison could not see, so "no changes" is never a silent clean
        (BACK-1732): categories whose items have no name to match, and a pair of
        single files that differ although no compared element does (a Python
        module-level constant is in no category; a body edit can stay under the
        function thresholds)."""
        warnings = []
        if diff_result['not_compared']:
            warnings.append({
                'type': 'not_compared', 'field': 'categories',
                'message': (f"Categories not compared: {', '.join(diff_result['not_compared'])} "
                            "(their items have no name to match); they differ between the sides"),
            })
        if not any(any(counts.values()) for counts in diff_result['summary'].values()):
            left, right = read_source_text(self.left_uri), read_source_text(self.right_uri)
            if left is not None and right is not None and left != right:
                warnings.append({
                    'type': 'not_compared', 'field': 'source',
                    'message': (f"{self.left_uri} and {self.right_uri} differ, but in nothing "
                                f"diff:// compares ({', '.join(diff_result['summary'])}): the "
                                "change is outside every element (e.g. a module-level constant) "
                                "or inside a body below the change thresholds. Compare the text "
                                "to see it"),
                })
        return warnings

    def _skipped_warnings(self, left_struct: Dict[str, Any], right_struct: Dict[str, Any]) -> list:
        """Files a git directory side could not analyze: they are in neither side's element
        lists, so a file skipped on one side only reads as added or removed (BACK-1854)."""
        warnings = []
        for side, uri, struct in (('left', self.left_uri, left_struct),
                                  ('right', self.right_uri, right_struct)):
            skipped = struct.get('skipped_files') or {}
            if not skipped:
                continue
            names = sorted(skipped)
            shown = ', '.join(names[:5]) + (f" and {len(names) - 5} more" if len(names) > 5 else '')
            warnings.append({
                'type': 'analysis_failed', 'field': side, 'count': len(names), 'files': names[:5],
                'failures': failure_records(skipped.items()),
                'message': (f"{len(names)} file(s) in {uri} could not be analyzed "
                            f"({', '.join(sorted({c.split(':', 1)[0] for c in skipped.values()}))}) -- "
                            f"their elements are missing from the {side} side, so the diff may show "
                            f"them as added or removed: {shown}"),
            })
        return warnings

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get diff for a specific element (function, class, etc.).

        Args:
            element_name: Name of element to compare (e.g., 'handle_request')

        Returns:
            Detailed diff for that specific element, or None when neither side has it:
            the router fails the lookup (exit 1) and lists ``list_elements()``, as for any
            other element that does not exist (BACK-1639).
        """
        from ...diff import compute_element_diff

        left_struct = resolve_uri(self.left_uri, **kwargs)
        right_struct = resolve_uri(self.right_uri, **kwargs)

        left_elem = find_element(left_struct, element_name)
        right_elem = find_element(right_struct, element_name)
        if left_elem is None and right_elem is None:
            return None

        result = compute_element_diff(left_elem, right_elem, element_name)
        if left_elem is not None and right_elem is not None:
            self._compare_bodies(result, left_elem, right_elem)
        return result

    def list_elements(self) -> list:
        """Element names on either side, left first: what a not-found lookup offers instead."""
        left = element_names(resolve_uri(self.left_uri))
        right = element_names(resolve_uri(self.right_uri))
        return list(dict.fromkeys(left + right))

    def _compare_bodies(self, result: Dict[str, Any], left_elem: Dict[str, Any],
                        right_elem: Dict[str, Any]) -> None:
        """Fold a source-text comparison into a both-sides-present element diff.

        Structural fields (signature, line count, complexity) miss body-only
        edits such as ``return 1`` -> ``return 10``. When both sources are
        readable and differ, the element is MODIFIED with a ``body`` change;
        when either is unreadable an "unchanged" verdict says so instead of
        claiming the elements are identical.
        """
        old = read_element_source(self.left_uri, left_elem)
        new = read_element_source(self.right_uri, right_elem)
        if old is None or new is None:
            if result['change'] == 'unchanged':
                result['message'] = (f"Element '{result['name']}': signature and shape "
                                     "unchanged; body not compared (source unavailable)")
            return
        if old == new:
            return
        if result['change'] == 'unchanged':
            # A move is listed with the edit, as a modified element lists it (BACK-2281).
            result.update(change='modified', changes=result.pop('moved', {}), left=left_elem, right=right_elem)
            result.pop('message', None)
        result['changes']['body'] = {'old': old, 'new': new}

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the diff operation.

        Returns:
            Dict with diff metadata
        """
        return {
            'type': 'diff',
            'left_uri': self.left_uri,
            'right_uri': self.right_uri
        }

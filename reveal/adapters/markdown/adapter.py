"""Markdown query adapter (markdown://)."""

from pathlib import Path
import stat
from typing import Dict, Any, Optional, TypeGuard
from reveal.reveal_types import CONTRACT_VERSION

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...utils.query import parse_query_filters, parse_result_control, ResultControl
from ...utils.results import ResultBuilder
from ...utils.validation import require_directory
from ...utils.path_utils import as_spelled

from .renderer import MarkdownRenderer
from .help import get_schema, get_help
from . import query as query_module
from . import operations
from . import files
from . import filtering
from .results import BodySearchAnalysis
from ...utils.query_parser import note_query_parsed
from ...errors import RequestValidationError
from ...utils.results import AnalysisCompleteness, result_execution_facts


def _extract_backlinks(filter_query: str) -> tuple:
    """Extract backlinks=<path> param from filter query.

    Returns:
        (target_path_or_None, remaining_query_string)
    """
    target = None
    remaining_parts = []
    for part in filter_query.split('&'):
        stripped = part.strip()
        if stripped.startswith('backlinks='):
            note_query_parsed(stripped)
            value = stripped[len('backlinks='):]
            if value:
                target = value
        else:
            remaining_parts.append(part)
    return target, '&'.join(remaining_parts)


def _extract_aggregate(filter_query: str) -> tuple:
    """Extract aggregate=<field> param from filter query.

    Returns:
        (aggregate_field_or_None, remaining_query_string)
    """
    aggregate_field = None
    remaining_parts = []
    for part in filter_query.split('&'):
        stripped = part.strip()
        if stripped.startswith('aggregate='):
            note_query_parsed(stripped)
            field = stripped[len('aggregate='):]
            if field:
                aggregate_field = field
        else:
            remaining_parts.append(part)
    return aggregate_field, '&'.join(remaining_parts)


def _extract_explain(filter_query: str) -> tuple:
    """Extract bare ``explain`` flag from filter query.

    Returns:
        (explain_requested: bool, remaining_query_string)
    """
    explain = False
    remaining_parts = []
    for part in filter_query.split('&'):
        stripped = part.strip()
        if stripped == 'explain':
            note_query_parsed(stripped)
            explain = True
        else:
            remaining_parts.append(part)
    return explain, '&'.join(remaining_parts)


def _extract_link_graph(filter_query: str) -> tuple:
    """Extract bare ``link-graph`` flag from filter query.

    Returns:
        (link_graph_requested: bool, remaining_query_string)
    """
    link_graph = False
    remaining_parts = []
    for part in filter_query.split('&'):
        stripped = part.strip()
        if stripped in ('link-graph', 'link_graph'):
            note_query_parsed(stripped)
            link_graph = True
        else:
            remaining_parts.append(part)
    return link_graph, '&'.join(remaining_parts)


def _extract_lint(filter_query: str) -> tuple:
    """Extract bare ``lint`` flag from filter query.

    Returns:
        (lint_requested: bool, remaining_query_string)
    """
    lint = False
    remaining_parts = []
    for part in filter_query.split('&'):
        stripped = part.strip()
        if stripped == 'lint':
            note_query_parsed(stripped)
            lint = True
        else:
            remaining_parts.append(part)
    return lint, '&'.join(remaining_parts)


def _extract_lint_fields(filter_query: str) -> tuple:
    """Extract lint-fields=<f1,f2,...> param from filter query.

    Returns:
        (required_fields_list_or_None, remaining_query_string)
    """
    lint_fields = None
    remaining_parts = []
    for part in filter_query.split('&'):
        stripped = part.strip()
        if stripped.startswith('lint-fields='):
            note_query_parsed(stripped)
            value = stripped[len('lint-fields='):]
            if value:
                lint_fields = [f.strip() for f in value.split(',') if f.strip()]
        else:
            remaining_parts.append(part)
    return lint_fields, '&'.join(remaining_parts)


def _extract_fields(filter_query: str) -> tuple:
    """Extract fields=<f1,f2,...> param from filter query.

    Returns:
        (fields_list_or_None, remaining_query_string)
    """
    fields = None
    remaining_parts = []
    for part in filter_query.split('&'):
        stripped = part.strip()
        if stripped.startswith('fields='):
            note_query_parsed(stripped)
            value = stripped[len('fields='):]
            if value:
                fields = [f.strip() for f in value.split(',') if f.strip()]
        else:
            remaining_parts.append(part)
    return fields, '&'.join(remaining_parts)


def _extract_body_contains(filter_query: str) -> tuple:
    """Extract body-contains= params from filter query.

    Returns:
        (body_contains_terms, remaining_query_string)
    """
    body_contains = []
    remaining_parts = []
    for part in filter_query.split('&'):
        stripped = part.strip()
        if stripped.startswith('body-contains='):
            note_query_parsed(stripped)
            term = stripped[len('body-contains='):]
            if term:
                body_contains.append(term)
        else:
            remaining_parts.append(part)
    return body_contains, '&'.join(remaining_parts)


def _execution_query_type(query: str) -> Optional[str]:
    """Resolve qualified operations without consuming source files."""
    if not isinstance(query, str):
        raise TypeError('Markdown query must be a string')
    link_graph, query = _extract_link_graph(query)
    lint, query = _extract_lint(query)
    backlinks, query = _extract_backlinks(query)
    aggregate, query = _extract_aggregate(query)
    terms, _ = _extract_body_contains(query)
    if link_graph or lint or backlinks:
        return None
    if aggregate:
        return 'markdown_aggregate'
    return 'markdown_query' if terms else None


def _valid_body_analysis(proof: Any) -> TypeGuard[BodySearchAnalysis]:
    keys = ('candidate_files', 'analyzed_files', 'failed_files', 'discovery_failures')
    return (isinstance(proof, dict)
            and all(type(proof.get(key)) is int and proof[key] >= 0 for key in keys)
            and proof['candidate_files'] == proof['analyzed_files'] + proof['failed_files'])


def _valid_body_observations(result, proof: BodySearchAnalysis) -> bool:
    observations, matched = result.get('results'), result.get('matched_files')
    return (isinstance(observations, list) and all(_valid_body_row(row) for row in observations)
            and type(matched) is int and len(observations) <= matched <= proof['analyzed_files'])


def _valid_aggregate_observations(result, proof: BodySearchAnalysis) -> bool:
    rows, matched, missing = (result.get('aggregate'), result.get('matched_files'),
                              result.get('files_missing_field'))
    if not (isinstance(result.get('field'), str) and result['field']
            and type(matched) is int and type(missing) is int
            and 0 <= missing <= matched <= proof['analyzed_files']
            and isinstance(rows, list) and all(_valid_aggregate_row(row) for row in rows)):
        return False
    return len({row['value'] for row in rows}) == len(rows)


def _valid_aggregate_row(row) -> bool:
    return (isinstance(row, dict) and isinstance(row.get('value'), str)
            and type(row.get('count')) is int and row['count'] > 0)


def _valid_body_row(row) -> bool:
    return (isinstance(row, dict)
            and all(isinstance(row.get(key), str) and row[key] for key in ('path', 'relative_path'))
            and type(row.get('relevance_score')) is int and row['relevance_score'] >= 0
            and type(row.get('has_frontmatter')) is bool)


def _erased_source_loss(result, proof: BodySearchAnalysis, prior_facts) -> bool:
    return (prior_facts is not None
            and prior_facts.completeness in (AnalysisCompleteness.INCOMPLETE, AnalysisCompleteness.FAILED)
            and (result.get('applicable') is False or not (proof['failed_files'] or proof['discovery_failures'])))


def _directory_resource(resource: str, qualified: bool) -> tuple[Path, str]:
    clean_path = resource or '.'
    if '://' in clean_path:
        clean_path = clean_path.split('://', 1)[1]
    clean_path = clean_path.split('?', 1)[0].rstrip('/')
    try:
        resolved = Path(clean_path).resolve()
    except ValueError as exc:
        if qualified and '\x00' in clean_path:
            raise RequestValidationError(str(exc)) from exc
        raise
    mode = resolved.stat().st_mode if qualified else None
    if (stat.S_ISREG(mode) if mode is not None else resolved.is_file()):
        error = RequestValidationError if qualified else ValueError
        raise error(
            f"markdown:// queries a directory of markdown files, not a single file.\n"
            f"To read a single markdown file, use: reveal {clean_path}")
    if mode is not None and not stat.S_ISDIR(mode):
        raise RequestValidationError(f"markdown:// directory '{clean_path}' is not a directory: {resolved}")
    directory = resolved if mode is not None else require_directory(resolved, f"markdown:// directory '{clean_path}'")
    return directory, clean_path or '.'


def _request_result_control(query: str, qualified: bool):
    try:
        return parse_result_control(query)
    except ValueError as exc:
        if qualified:
            raise RequestValidationError(str(exc)) from exc
        raise


def _request_query_filters(query: str, qualified: bool):
    try:
        return parse_query_filters(query)
    except ValueError as exc:
        if qualified:
            raise RequestValidationError(str(exc)) from exc
        raise


@register_adapter('markdown')
@register_renderer(MarkdownRenderer)
class MarkdownQueryAdapter(ResourceAdapter):
    """Adapter for querying markdown files by frontmatter via markdown:// URIs.

    Enables finding markdown files based on frontmatter field values,
    missing fields, or wildcards. Works on local directory trees.
    """
    HELP_CLUSTER = 'Sessions & Docs'

    BUDGET_LIST_FIELD = 'results'
    LEGACY_INIT = False
    RESOURCE_IS_PATH = True
    RESULT_TYPE = 'markdown_query'
    DEFAULT_FAIL_ON = 'none'
    CLI_QUERY_FLAGS = {'respect_gitignore': 'respect_gitignore=false'}  # --no-gitignore (BACK-1386)

    @classmethod
    def uri_execution_facts(cls, resource):
        """Ordinary body searches and aggregates qualify required source decisions."""
        return cls.execution_facts if _execution_query_type(resource.partition('?')[2]) else None

    @staticmethod
    def uri_result_type(resource):
        return _execution_query_type(resource.partition('?')[2]) or 'markdown_query'

    @staticmethod
    def execution_facts(result):
        """Source decisions precede frontmatter/body selection and pagination."""
        state = AnalysisCompleteness.COMPLETE
        if not isinstance(result, dict):
            state = AnalysisCompleteness.FAILED
        elif not result.get('error') and result.get('applicable') is not False:
            proof = result.get('analysis')
            if not _valid_body_analysis(proof):
                state = AnalysisCompleteness.FAILED
            elif proof['failed_files'] or proof['discovery_failures']:
                state = (AnalysisCompleteness.INCOMPLETE if proof['analyzed_files']
                         else AnalysisCompleteness.FAILED)
        return result_execution_facts(result, completeness=state)

    @staticmethod
    def answer_requirement_error(result, expected_type, prior_facts=None):
        """Transformations must retain required source proof and observation counts."""
        if prior_facts is not None and any(
                error.get('code') == 'invalid_request' for error in result.get('meta', {}).get('errors', [])):
            return 'Markdown postprocessing cannot establish a request rejection from prior analysis'
        if prior_facts is None and (result.get('error') or result.get('applicable') is False):
            return None
        proof = result.get('analysis')
        if (not _valid_body_analysis(proof) or type(result.get('total_files')) is not int
                or result['total_files'] != proof['candidate_files']):
            return 'Markdown answer missing consistent nonnegative source analysis counts'
        if _erased_source_loss(result, proof, prior_facts):
            return 'Markdown postprocessing cannot erase established required source loss'
        valid_observations = (_valid_aggregate_observations(result, proof)
                              if expected_type == 'markdown_aggregate' else _valid_body_observations(result, proof))
        if not valid_observations:
            return 'Markdown answer missing consistent observations and match count'
        return None

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for markdown:// adapter.

        Returns JSON schema for AI agent integration.
        """
        return get_schema()

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for markdown:// adapter."""
        return get_help()

    def __init__(self, resource: str = '', query: Optional[str] = None, **kwargs: Any):
        """Initialize the markdown query adapter.

        Args:
            resource: Directory to search for markdown files ('' = current directory)
            query: Query string (e.g., 'topics=reveal', '!status', 'lines>100')
        """
        qualified = _execution_query_type(query or '') is not None
        self.base_path, self.spelling = _directory_resource(resource, qualified)
        self.query = query

        # Parse result control (sort, limit, offset) and get cleaned query
        if query:
            filter_query, self.result_control = _request_result_control(query, qualified)
        else:
            filter_query = ''
            self.result_control = ResultControl()

        # Extract link-graph flag before passing to filter parsers
        self.link_graph = False
        if filter_query:
            self.link_graph, filter_query = _extract_link_graph(filter_query)

        # Extract lint flag + optional required-fields list before filter parsers
        self.lint = False
        if filter_query:
            self.lint, filter_query = _extract_lint(filter_query)

        self.lint_fields = None
        if filter_query:
            self.lint_fields, filter_query = _extract_lint_fields(filter_query)

        # Extract backlinks= param before passing to filter parsers
        self.backlinks_target = None
        if filter_query:
            self.backlinks_target, filter_query = _extract_backlinks(filter_query)

        # Extract aggregate= param before passing to filter parsers
        self.aggregate_field = None
        if filter_query:
            self.aggregate_field, filter_query = _extract_aggregate(filter_query)

        # Extract body-contains= params before passing to filter parsers
        self.body_contains = []
        if filter_query:
            self.body_contains, filter_query = _extract_body_contains(filter_query)

        # Extract bare explain flag (score breakdown for body-contains ranking)
        self.explain = False
        if filter_query:
            self.explain, filter_query = _extract_explain(filter_query)

        # Extract fields= param (extra frontmatter columns to show in listing)
        self.extra_fields = None
        if filter_query:
            self.extra_fields, filter_query = _extract_fields(filter_query)

        # Parse query filters conditionally (only if new operators present)
        # This prevents legacy parameters from being misinterpreted
        self.query_filters = []
        has_new_operators = filter_query and any(op in filter_query for op in ['>', '<', '!=', '~=', '!~', '..', '=='])

        if has_new_operators:
            # No fallback to "no filters": that would answer an unfiltered query as if it
            # were the filtered one (BACK-1059). A ValueError here fails the query.
            self.query_filters = _request_query_filters(filter_query, qualified)

        # Keep legacy filter parsing for backward compatibility
        # Only use legacy parsing if there are no new operators
        self.filters = []
        if filter_query and not has_new_operators:
            self.filters = query_module.parse_query(filter_query)

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Query markdown files and return matching results.

        Returns:
            Dict containing matched files with frontmatter summary, or
            a frequency table when ?aggregate=<field> is specified, or
            a link graph when ?link-graph is specified, or a maintenance
            queue of frontmatter problems when ?lint is specified.
        """
        if self.link_graph:
            result = dict(operations.build_link_graph(self.base_path))
            return ResultBuilder.create(
                result_type='markdown_link_graph',
                source=str(self.base_path),
                source_type='directory',
                contract_version=CONTRACT_VERSION,
                warnings=self._unreadable_warnings(result, "their links are missing from the graph"),
                data=result,
            )

        if self.lint:
            result = operations.lint_frontmatter(self.base_path, self.lint_fields)
            return ResultBuilder.create(
                result_type='markdown_frontmatter_lint',
                source=self.base_path,
                source_type='directory',
                contract_version=CONTRACT_VERSION,
                data=result,
            )

        if self.backlinks_target:
            result = operations.get_backlinks(self.base_path, self.backlinks_target)
            return ResultBuilder.create(
                result_type='markdown_backlinks',
                source=self.base_path,
                contract_version=CONTRACT_VERSION,
                warnings=self._unreadable_warnings(result, "links from them are missing, so backlinks may be incomplete"),
                data=result,
            )

        if self.aggregate_field:
            result = operations.aggregate_field_values(
                self.base_path,
                self.aggregate_field,
                self.filters,
                self.query_filters,
                self.body_contains or None,
            )
            warnings = self._unreadable_warnings(result, "required document evidence is missing, so counts may be low")
            warnings.extend(result.pop('meta', {}).get('warnings', []))
            return ResultBuilder.create(
                result_type='markdown_aggregate',
                source=str(self.base_path),
                source_type='directory',
                contract_version=CONTRACT_VERSION,
                warnings=warnings,
                data=result,
            )

        result = operations.get_structure(
            self.base_path,
            self.query or '',
            self.filters,
            self.query_filters,
            self.result_control,
            self.body_contains or None,
            self.extra_fields,
            self.explain,
        )
        result.update(contract_version=CONTRACT_VERSION, source_type='directory')
        # Paths as the user named the directory, not its resolved location (BACK-1366).
        result['base_path'] = as_spelled(self.base_path, self.spelling)
        for item in result.get('results', []):
            item['path'] = as_spelled(item['path'], self.spelling)
        return result

    def _unreadable_warnings(self, result: Dict[str, Any], consequence: str) -> list:
        """The ``unreadable_files`` warning for the files in *result* that could not be read,
        consuming the carrier key so it is not also data (BACK-1854)."""
        warning = files.unreadable_warning(
            [tuple(item) for item in result.pop('unreadable_files', [])], consequence, self.base_path)
        return [warning] if warning else []

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get frontmatter from a specific file.

        Args:
            element_name: Filename or path to check

        Returns:
            Dict with file frontmatter details
        """
        return operations.get_element(self.base_path, element_name)

    def get_metadata(self) -> Dict[str, Any]:
        """Get metadata about the query scope.

        Returns:
            Dict with query metadata
        """
        return operations.get_metadata(self.base_path)

    # Backward compatibility methods for tests
    def _parse_query(self, query: str):
        """Parse query string (backward compatibility)."""
        return query_module.parse_query(query)

    def _compare(self, field_value, operator, target_value):
        """Compare values (backward compatibility)."""
        return query_module.compare(field_value, operator, target_value)

    def _find_markdown_files(self):
        """Find markdown files (backward compatibility)."""
        return files.find_markdown_files(self.base_path)

    def _extract_frontmatter(self, path):
        """Extract frontmatter (backward compatibility)."""
        return files.extract_frontmatter(path)

    def _matches_filter(self, frontmatter, field, operator, value):
        """Match filter (backward compatibility)."""
        return filtering.matches_filter(frontmatter, field, operator, value)

    def _matches_all_filters(self, frontmatter):
        """Match all filters (backward compatibility)."""
        return filtering.matches_all_filters(frontmatter, self.filters, self.query_filters)

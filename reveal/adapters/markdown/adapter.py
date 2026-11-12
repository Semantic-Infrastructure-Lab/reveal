"""Markdown query adapter (markdown://)."""

from pathlib import Path
import stat
import os
from typing import Dict, Any, Optional, TypeGuard
from reveal.reveal_types import CONTRACT_VERSION

from ..base import ResourceAdapter, register_adapter, register_renderer
from ...utils.results import ResultBuilder
from ...utils.validation import require_directory
from ...utils.path_utils import as_spelled

from .renderer import MarkdownRenderer
from .help import get_schema, get_help
from . import query as query_module
from . import operations
from . import files
from . import filtering
from .results import BodySearchAnalysis, valid_source_analysis
from ...utils.query_parser import QueryParams, ResourceSpec, param_schema, parse_query_params
from ...utils.query_binding import bind_declared_params
from .params import (PARAM_SPECS, MATCH, BACKLINKS, AGGREGATE, FIELD, LINT_FIELDS, FIELDS, EXPLAIN,
                     selected_view, result_type, result_control, filter_state, describe_request, validate_request)
from ...errors import RequestValidationError
from ...utils.results import AnalysisCompleteness, result_execution_facts


def _valid_body_analysis(proof: Any) -> TypeGuard[BodySearchAnalysis]:
    return valid_source_analysis(proof)


def _valid_body_observations(result, proof: BodySearchAnalysis, require_score: bool = True) -> bool:
    observations, matched = result.get('results'), result.get('matched_files')
    return (isinstance(observations, list) and all(_valid_listing_row(row, require_score) for row in observations)
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


def _valid_listing_row(row, require_score: bool) -> bool:
    if require_score:
        return _valid_body_row(row)
    return (isinstance(row, dict)
            and all(isinstance(row.get(key), str) and row[key] for key in ('path', 'relative_path'))
            and type(row.get('has_frontmatter')) is bool)


def _valid_lint_observations(result) -> bool:
    rows = result.get('issues')
    return (isinstance(rows, list) and type(result.get('issues_found')) is int
            and result['issues_found'] == len(rows)
            and all(isinstance(row, dict) and isinstance(row.get('file'), str)
                    and isinstance(row.get('issue'), str) for row in rows))


def _valid_graph_observations(result, proof) -> bool:
    nodes = result.get('nodes')
    if not (isinstance(nodes, list) and proof['analyzed_files'] <= len(nodes) <= proof['candidate_files']
            and all(isinstance(row, dict) and isinstance(row.get('file'), str)
                    and _strings(row.get('links_to')) and _strings(row.get('linked_by')) for row in nodes)):
        return False
    return (type(result.get('total_edges')) is int
            and result['total_edges'] == sum(len(row['links_to']) for row in nodes)
            and len({row['file'] for row in nodes}) == len(nodes))


def _valid_auxiliary_observations(result, proof, kind: str) -> bool:
    if kind == 'markdown_frontmatter_lint':
        return _valid_lint_observations(result)
    if kind == 'markdown_backlinks':
        return (type(result.get('found')) is bool and isinstance(result.get('target'), str)
                and _strings(result.get('linked_by')) and _strings(result.get('links_to')))
    return kind == 'markdown_link_graph' and _valid_graph_observations(result, proof)


def _strings(value) -> bool:
    return isinstance(value, list) and all(isinstance(item, str) for item in value)


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
    clean_path = os.path.expanduser(clean_path)
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
    FINDINGS_POLICIES = ('none',)
    BOUND_QUERY_CALL = True
    PARAM_SPECS = PARAM_SPECS
    RESOURCE_SPEC = ResourceSpec(kind='directory', uri_codec='existing-path-first')
    validate_request = staticmethod(validate_request)
    result_type_for = staticmethod(result_type)
    CLI_QUERY_FLAGS = {'respect_gitignore': 'respect_gitignore=false'}  # --no-gitignore (BACK-1386)

    @staticmethod
    def resource_path(resource):
        return os.path.expanduser(resource)

    @classmethod
    def uri_execution_facts(cls, resource):
        """Every directory-query view now records its required source decisions."""
        return cls.execution_facts

    @staticmethod
    def uri_result_type(resource):
        params = parse_query_params(resource.partition('?')[2])
        return result_type(params)

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

    def answer_requirement_error(self, result, expected_type, prior_facts=None):
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
        valid_observations = self._valid_observations(result, proof, expected_type)
        if not valid_observations:
            return 'Markdown answer missing consistent observations and match count'
        return None

    def _valid_observations(self, result, proof, expected_type):
        if expected_type == 'markdown_aggregate':
            return _valid_aggregate_observations(result, proof)
        if expected_type == 'markdown_query':
            return _valid_body_observations(result, proof, bool(self.body_contains))
        return _valid_auxiliary_observations(result, proof, expected_type)

    @staticmethod
    def get_schema() -> Dict[str, Any]:
        """Get machine-readable schema for markdown:// adapter.

        Returns JSON schema for AI agent integration.
        """
        schema = get_schema()
        return {**schema, 'query_params': param_schema(PARAM_SPECS),
                'resource': MarkdownQueryAdapter.RESOURCE_SPEC.schema()}

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for markdown:// adapter."""
        return get_help()

    def __init__(self, resource: str = '', query: Optional[str] = None, *,
                 params: Optional[Dict[str, Any]] = None, **kwargs: Any):
        if params is None:
            params = bind_declared_params(PARAM_SPECS, query or '', transport='uri')
        elif not isinstance(params, QueryParams):
            params = bind_declared_params(PARAM_SPECS, params, transport='typed')
        try:
            validate_request(params)
        except ValueError as exc:
            raise RequestValidationError(str(exc)) from exc
        self.query_params = params
        self.base_path, self.spelling = _directory_resource(resource, True)
        self.query = describe_request(params)
        self.result_control = result_control(params)
        _, self.filters, self.query_filters = filter_state(params)
        view = selected_view(params, apply=True)
        self.link_graph = view == 'links'
        self.lint = view == 'lint'
        self.backlinks_target = BACKLINKS.read(params) if view == 'backlinks' else None
        self.aggregate_field = (FIELD.read(params) or AGGREGATE.read(params)) if view == 'aggregate' else None
        self.body_contains = MATCH.read(params)
        self.lint_fields = LINT_FIELDS.read(params)
        self.extra_fields = FIELDS.read(params)
        self.explain = EXPLAIN.read(params)

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Query markdown files and return matching results.

        Returns:
            Dict containing matched files with frontmatter summary, or
            a frequency table when ?aggregate=<field> is specified, or
            a link graph when ?link-graph is specified, or a maintenance
            queue of frontmatter problems when ?lint is specified.
        """
        source = as_spelled(self.base_path, self.spelling)
        if self.link_graph:
            result = dict(operations.build_link_graph(self.base_path))
            return ResultBuilder.create(
                result_type='markdown_link_graph',
                source=source,
                source_type='directory',
                contract_version=CONTRACT_VERSION,
                warnings=self._source_warnings(result, "their links are missing from the graph"),
                data=result,
            )

        if self.lint:
            result = operations.lint_frontmatter(self.base_path, self.lint_fields)
            return ResultBuilder.create(
                result_type='markdown_frontmatter_lint',
                source=source,
                source_type='directory',
                contract_version=CONTRACT_VERSION,
                warnings=self._source_warnings(result, "required document evidence is missing from lint"),
                data=result,
            )

        if self.backlinks_target:
            result = operations.get_backlinks(self.base_path, self.backlinks_target)
            return ResultBuilder.create(
                result_type='markdown_backlinks',
                source=source,
                contract_version=CONTRACT_VERSION,
                warnings=self._source_warnings(result, "links from them are missing, so backlinks may be incomplete"),
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
            warnings = self._source_warnings(result, "required document evidence is missing, so counts may be low")
            return ResultBuilder.create(
                result_type='markdown_aggregate',
                source=source,
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
        result.update(contract_version=CONTRACT_VERSION, source_type='directory', source=source)
        # Paths as the user named the directory, not its resolved location (BACK-1366).
        result['base_path'] = as_spelled(self.base_path, self.spelling)
        for item in result.get('results', []):
            item['path'] = as_spelled(item['path'], self.spelling)
        return result

    def _source_warnings(self, result: Dict[str, Any], consequence: str) -> list:
        """Consume source diagnostics before the builder owns the result envelope."""
        warning = files.unreadable_warning(
            [tuple(item) for item in result.pop('unreadable_files', [])], consequence, self.base_path)
        warnings = [warning] if warning else []
        warnings.extend(result.pop('meta', {}).get('warnings', []))
        return warnings

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

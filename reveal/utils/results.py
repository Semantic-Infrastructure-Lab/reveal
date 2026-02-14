"""Result building utilities for Output Contract v1.x compliance.

This module provides utilities for building standardized result dictionaries
that comply with the reveal Output Contract specification versions 1.0 and 1.1.

The ResultBuilder class eliminates ~200 lines of duplicate result construction
code across 15+ adapters by centralizing the common patterns:
- contract_version field
- type field
- source/source_type fields
- meta dict (v1.1)
- error handling

Usage:
    # Basic result (v1.0)
    result = ResultBuilder.create(
        result_type='stats_summary',
        source=Path('/path/to/dir'),
        data={'summary': {...}, 'files': [...]}
    )

    # Result with metadata (v1.1)
    result = ResultBuilder.create(
        result_type='ast_query',
        source=Path('/path/to/file.py'),
        data={'functions': [...]},
        contract_version='1.1',
        parse_mode='tree_sitter_full',
        confidence=0.95
    )

    # Error result
    result = ResultBuilder.create_error(
        result_type='stats_summary',
        source=Path('/path/to/dir'),
        error='Directory not found'
    )
"""

from pathlib import Path
from typing import Dict, Any, Optional, List, Union


class ResultBuilder:
    """Build Output Contract v1.x compliant results."""

    @staticmethod
    def create(
        result_type: str,
        source: Union[str, Path],
        data: Optional[Dict[str, Any]] = None,
        contract_version: str = '1.0',
        parse_mode: Optional[str] = None,
        confidence: Optional[float] = None,
        warnings: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[Dict[str, Any]]] = None,
        **extra_fields
    ) -> Dict[str, Any]:
        """Build standard Output Contract v1.x result dictionary.

        Args:
            result_type: Type identifier (e.g., 'stats_summary', 'ast_query')
            source: Source path (file or directory)
            data: Adapter-specific data fields to include
            contract_version: Contract version ('1.0' or '1.1')
            parse_mode: Parse mode for v1.1 meta (tree_sitter_full, regex, etc.)
            confidence: Confidence score 0.0-1.0 for v1.1 meta
            warnings: Warning list for v1.1 meta
            errors: Error list for v1.1 meta
            **extra_fields: Additional fields to include in result

        Returns:
            Dict with contract_version, type, source, source_type, and data

        Example:
            >>> result = ResultBuilder.create(
            ...     result_type='stats_summary',
            ...     source=Path('/src'),
            ...     data={'summary': {'total_files': 10}, 'files': []},
            ...     contract_version='1.0'
            ... )
            >>> result['contract_version']
            '1.0'
            >>> result['type']
            'stats_summary'
        """
        source_path = Path(source) if isinstance(source, str) else source

        # Build base result
        result: Dict[str, Any] = {
            'contract_version': contract_version,
            'type': result_type,
            'source': str(source),
            'source_type': 'directory' if source_path.is_dir() else 'file',
        }

        # Add v1.1 meta if metadata provided
        if contract_version == '1.1' and any([parse_mode, confidence is not None, warnings, errors]):
            result['meta'] = ResultBuilder._create_meta(
                parse_mode=parse_mode,
                confidence=confidence,
                warnings=warnings,
                errors=errors
            )

        # Add adapter-specific data
        if data:
            result.update(data)

        # Add extra fields
        if extra_fields:
            result.update(extra_fields)

        return result

    @staticmethod
    def create_error(
        result_type: str,
        source: Union[str, Path],
        error: str,
        contract_version: str = '1.0',
        **extra_fields
    ) -> Dict[str, Any]:
        """Build error result dictionary.

        Args:
            result_type: Type identifier
            source: Source path
            error: Error message
            contract_version: Contract version
            **extra_fields: Additional fields

        Returns:
            Dict with error field

        Example:
            >>> result = ResultBuilder.create_error(
            ...     result_type='stats_summary',
            ...     source='/missing',
            ...     error='Directory not found'
            ... )
            >>> result['error']
            'Directory not found'
        """
        source_path = Path(source) if isinstance(source, str) else source

        result: Dict[str, Any] = {
            'contract_version': contract_version,
            'type': result_type,
            'source': str(source),
            'source_type': 'directory' if source_path.is_dir() else 'file',
            'error': error,
        }

        if extra_fields:
            result.update(extra_fields)

        return result

    @staticmethod
    def _create_meta(
        parse_mode: Optional[str] = None,
        confidence: Optional[float] = None,
        warnings: Optional[List[Dict[str, Any]]] = None,
        errors: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """Create Output Contract v1.1 meta dict with trust metadata.

        For adapters that use parsing (tree-sitter, regex, heuristics) to provide
        quality/confidence information to AI agents.

        Args:
            parse_mode: How parsing was performed
                - "tree_sitter_full" - Complete AST parsing (high confidence)
                - "tree_sitter_partial" - Partial AST parsing (some errors)
                - "fallback" - Tree-sitter failed, used fallback
                - "regex" - Regular expression extraction
                - "heuristic" - Pattern-based heuristics
            confidence: Overall confidence (0.0-1.0)
                - 1.0 = Perfect parse
                - 0.95-0.99 = High confidence
                - 0.80-0.94 = Good confidence
                - 0.50-0.79 = Partial results
                - < 0.50 = Low confidence
            warnings: Non-fatal issues
                [{'code': 'W001', 'message': '...', 'file': '...'}]
            errors: Fatal errors with fallback info
                [{'code': 'E002', 'message': '...', 'file': '...', 'fallback': '...'}]

        Returns:
            Meta dict for Output Contract v1.1
        """
        meta: Dict[str, Any] = {}

        if parse_mode is not None:
            meta['parse_mode'] = parse_mode

        if confidence is not None:
            # Clamp to [0.0, 1.0]
            meta['confidence'] = max(0.0, min(1.0, confidence))

        if warnings is not None:
            meta['warnings'] = warnings
        else:
            meta['warnings'] = []

        if errors is not None:
            meta['errors'] = errors
        else:
            meta['errors'] = []

        return meta if meta else {}

    @staticmethod
    def add_pagination_meta(
        result: Dict[str, Any],
        total: int,
        displayed: int,
        offset: Optional[int] = None,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Add pagination metadata to result.

        Args:
            result: Result dict to modify
            total: Total number of items available
            displayed: Number of items actually displayed
            offset: Starting offset (if applicable)
            limit: Limit applied (if applicable)

        Returns:
            Modified result dict

        Example:
            >>> result = {'type': 'query', 'results': [...]}
            >>> ResultBuilder.add_pagination_meta(result, total=100, displayed=25, limit=25)
            >>> result['pagination']
            {'total': 100, 'displayed': 25, 'offset': 0, 'limit': 25, 'truncated': True}
        """
        pagination: Dict[str, Any] = {
            'total': total,
            'displayed': displayed,
        }

        if offset is not None:
            pagination['offset'] = offset
        else:
            pagination['offset'] = 0

        if limit is not None:
            pagination['limit'] = limit

        pagination['truncated'] = displayed < total

        result['pagination'] = pagination
        return result

    @staticmethod
    def add_truncation_warning(
        result: Dict[str, Any],
        displayed: int,
        total: int,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """Add truncation warning if results were limited.

        Args:
            result: Result dict to modify
            displayed: Number of items displayed
            total: Total number of items available
            limit: Limit that was applied (if known)

        Returns:
            Modified result dict

        Example:
            >>> result = {'results': [...]}
            >>> ResultBuilder.add_truncation_warning(result, displayed=25, total=100)
            >>> result['warning']
            'Results truncated: showing 25 of 100 matches'
        """
        if displayed < total:
            result['warning'] = f'Results truncated: showing {displayed} of {total} matches'
            if limit:
                result['warning'] += f' (limit={limit})'

        return result


# Convenience functions for backward compatibility
def create_result(
    result_type: str,
    source: Union[str, Path],
    data: Optional[Dict[str, Any]] = None,
    **kwargs
) -> Dict[str, Any]:
    """Convenience function for ResultBuilder.create().

    See ResultBuilder.create() for full documentation.
    """
    return ResultBuilder.create(result_type, source, data, **kwargs)


def create_error_result(
    result_type: str,
    source: Union[str, Path],
    error: str,
    **kwargs
) -> Dict[str, Any]:
    """Convenience function for ResultBuilder.create_error().

    See ResultBuilder.create_error() for full documentation.
    """
    return ResultBuilder.create_error(result_type, source, error, **kwargs)


def create_meta(
    parse_mode: Optional[str] = None,
    confidence: Optional[float] = None,
    warnings: Optional[List[Dict[str, Any]]] = None,
    errors: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Convenience function for ResultBuilder._create_meta().

    See ResultBuilder._create_meta() for full documentation.
    """
    return ResultBuilder._create_meta(parse_mode, confidence, warnings, errors)

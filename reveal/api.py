"""Public Python API for Reveal.

Provides programmatic access to Reveal's analysis without subprocess overhead.

Usage::

    from reveal import analyze, element, query, check

    # Analyze a Python file — returns structured dict
    result = analyze("myfile.py")
    for fn in result.get("functions", []):
        print(fn["name"], fn["line"])

    # Extract a specific named element
    func = element("myfile.py", "my_function")
    if func:
        print(func["source"])

    # Query via URI scheme
    result = query("ast://myproject/?show=classes")

    # Check code quality — returns list of Detection objects
    findings = check("myfile.py", select=["C", "M"])
    for f in findings:
        print(f.rule_code, f.message)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def analyze(path: str, **kwargs: Any) -> Dict[str, Any]:
    """Get the structural overview of a file.

    Equivalent to ``reveal myfile.py`` at the CLI, but returns the raw data dict
    instead of rendering it to the terminal.

    Args:
        path: Path to the file to analyze.
        **kwargs: Additional keyword arguments forwarded to the analyzer's
            ``get_structure()`` method (e.g. ``head``, ``tail``).

    Returns:
        Dict with keys such as ``"functions"``, ``"classes"``, ``"imports"``,
        etc.  Exact keys depend on the file type and analyzer.

    Raises:
        FileNotFoundError: If *path* does not exist on disk.
        ValueError: If no analyzer is registered for this file type.

    Example::

        result = analyze("mymodule.py")
        for fn in result.get("functions", []):
            print(fn["name"], fn["line"])
    """
    from .registry import get_analyzer

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    analyzer_class = get_analyzer(str(file_path))
    if analyzer_class is None:
        raise ValueError(f"No analyzer available for: {path}")

    analyzer = analyzer_class(str(file_path))
    return analyzer.get_structure(**kwargs)


def element(
    path: str,
    name: str,
    element_type: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Extract a named element (function, class, section, …) from a file.

    Equivalent to ``reveal myfile.py my_function`` at the CLI.

    Args:
        path: Path to the file.
        name: Name of the element to extract.
        element_type: Optional type hint (``"function"``, ``"class"``,
            ``"section"``, etc.).  When ``None`` the structure is searched
            first to determine the correct type, then common types are tried.

    Returns:
        Dict with ``"source"``, ``"line_start"``, ``"line_end"``, etc.,
        or ``None`` if the element was not found.

    Raises:
        FileNotFoundError: If *path* does not exist on disk.
        ValueError: If no analyzer is registered for this file type.

    Example::

        func = element("mymodule.py", "load_config")
        if func:
            print(func["source"])
    """
    from .registry import get_analyzer

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    analyzer_class = get_analyzer(str(file_path))
    if analyzer_class is None:
        raise ValueError(f"No analyzer available for: {path}")

    analyzer = analyzer_class(str(file_path))

    # Fast path: caller provided the type.
    if element_type:
        return analyzer.extract_element(element_type, name)

    # Slower path: scan the structure to discover the element's type, then
    # use it for a precise extraction.  This avoids ambiguous matches.
    _SECTION_TO_TYPE: Dict[str, str] = {
        "functions": "function",
        "classes": "class",
        "methods": "method",
        "structs": "struct",
        "enums": "enum",
        "interfaces": "interface",
        "sections": "section",
        "variables": "variable",
    }
    try:
        struct = analyzer.get_structure()
        for section_key, elem_type in _SECTION_TO_TYPE.items():
            for item in struct.get(section_key, []):
                if isinstance(item, dict) and item.get("name") == name:
                    result = analyzer.extract_element(elem_type, name)
                    if result is not None:
                        return result
    except Exception as e:
        logger.debug("element() structure lookup failed for %s %r: %s", path, name, e)

    # Last resort: try common types in order.
    for elem_type in ("function", "class", "method", "struct", "enum",
                      "interface", "section", "variable"):
        result = analyzer.extract_element(elem_type, name)
        if result is not None:
            return result

    return None


def query(
    uri: str,
    element_name: Optional[str] = None,
    **kwargs: Any,
) -> Dict[str, Any]:
    """Query a resource via a reveal URI scheme.

    Equivalent to ``reveal ast://myproject/?show=classes`` at the CLI, but
    returns the structured dict instead of rendering it.

    Args:
        uri: Full URI of the form ``scheme://resource[?params]``.
            Examples: ``"ast://mydir/"``, ``"claude://sessions/"``,
            ``"nginx:///etc/nginx/nginx.conf"``.
        element_name: Optional element to extract from the resource.
        **kwargs: Additional keyword arguments forwarded to the adapter's
            ``get_structure()`` or ``get_element()`` method.

    Returns:
        Result dict from the adapter.

    Raises:
        ValueError: If the URI is malformed or the scheme is not supported.
        ImportError: If an optional dependency required by the adapter is missing.

    Example::

        sessions = query("claude://sessions/", element_name=None)
        nginx_result = query("nginx:///etc/nginx/nginx.conf")
    """
    from . import adapters as _adapters  # noqa: F401 — triggers adapter registrations
    from .adapters.base import _default_from_uri, get_adapter_class, list_supported_schemes

    if "://" not in uri:
        raise ValueError(
            f"Invalid URI (missing scheme): {uri!r}\n"
            "Expected format: scheme://resource  (e.g. ast://mydir/)"
        )

    scheme, resource = uri.split("://", 1)
    adapter_class = get_adapter_class(scheme)
    if adapter_class is None:
        supported = ", ".join(f"{s}://" for s in list_supported_schemes())
        raise ValueError(
            f"Unsupported URI scheme: {scheme}://\n"
            f"Supported schemes: {supported}"
        )

    if isinstance(adapter_class, type) and hasattr(adapter_class, "from_uri"):
        adapter = adapter_class.from_uri(scheme, resource, element_name)
    else:
        adapter = _default_from_uri(adapter_class, scheme, resource, element_name)

    if element_name:
        result = adapter.get_element(element_name, **kwargs)
        if result is None:
            raise ValueError(f"Element {element_name!r} not found in {uri}")
        return result

    return adapter.get_structure(**kwargs)


def check(
    path: str,
    select: Optional[List[str]] = None,
    ignore: Optional[List[str]] = None,
) -> List:
    """Run quality checks on a file.

    Equivalent to ``reveal check myfile.py`` at the CLI, but returns a list of
    :class:`~reveal.rules.base.Detection` objects instead of printing them.

    Args:
        path: Path to the file to check.
        select: Rule codes or prefixes to include (e.g. ``["C", "M101"]``).
            When ``None`` all applicable rules run.
        ignore: Rule codes or prefixes to exclude (e.g. ``["E501"]``).

    Returns:
        List of :class:`~reveal.rules.base.Detection` objects.  Each has
        ``.rule_code``, ``.message``, ``.line``, ``.column``, ``.severity``,
        and ``.suggestion`` attributes.  Call ``.to_dict()`` for JSON-safe output.

    Raises:
        FileNotFoundError: If *path* does not exist on disk.

    Example::

        findings = check("mymodule.py", ignore=["E501"])
        errors = [f for f in findings if f.severity.value == "high"]
    """
    from .registry import get_analyzer
    from .rules import RuleRegistry

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    path_str = str(file_path)
    content = file_path.read_text(encoding="utf-8", errors="replace")

    # Obtain structure if possible — rules use it for semantic analysis
    structure_data: Optional[Dict[str, Any]] = None
    analyzer_class = get_analyzer(path_str)
    if analyzer_class is not None:
        try:
            analyzer = analyzer_class(path_str)
            structure_data = analyzer.get_structure()
        except Exception as e:
            logger.debug("check() get_structure failed for %s: %s", path_str, e)

    return RuleRegistry.check_file(
        path_str, structure_data, content, select=select, ignore=ignore
    )

"""Filter matching logic for AST adapter."""

import re
from fnmatch import fnmatch
from typing import Dict, List, Any, Set, Tuple, cast
from ...conventions import decorator_attributes, decorator_name
from ...reveal_types import ASTElement
from ...utils.query import compare_values

# Filter keys `matches_filters` special-cases (mapped to a differently-named
# or derived element field, not a literal dict key) — always valid filter
# vocabulary regardless of what's present on any scanned element. Keep in
# sync with the elif chain in matches_filters() below (BACK-1111).
SPECIAL_FILTER_KEYS = {
    'type', 'lines', 'decorator', 'calls', 'callee_of',
    'param_type', 'return_type', 'has_annotations', 'callers',
}


def find_unknown_filter_keys(structures: List[Dict[str, Any]], query: Dict[str, Any]) -> List[str]:
    """Identify query filter keys that are neither special-cased nor present
    as a literal field on any scanned element — the typo-vs-genuine-zero
    disclosure for ast:// (BACK-1111).

    Only meaningful to call when a query produced zero results: a key that's
    never present anywhere is why nothing matched, distinguishing a typo'd
    filter key from a genuine "0 elements have this value" answer.

    Args:
        structures: File structures scanned by this query
        query: Query dict with filter conditions

    Returns:
        Sorted list of query keys never seen as a literal element field.
    """
    passthrough_keys = [k for k in query if k not in SPECIAL_FILTER_KEYS]
    if not passthrough_keys:
        return []

    seen: Set[str] = set()
    remaining = set(passthrough_keys)
    for structure in structures:
        for element in structure.get('elements', []):
            seen.update(element.keys())
            remaining -= seen
            if not remaining:
                return []

    return sorted(remaining)


def apply_filters(structures: List[Dict[str, Any]], query: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Apply query filters to collected structures.

    When a name= glob filter is used without an explicit type= filter, import
    declarations are excluded from results. Use type=import to find imports.

    Args:
        structures: List of file structures
        query: Query dict with filter conditions

    Returns:
        Filtered list of matching elements
    """
    # If name= glob is active but no type= filter, skip imports by default.
    # This avoids cluttering results with import declarations when the user
    # is searching for defs/calls (the common case).
    exclude_imports = (
        'name' in query
        and query['name'].get('op') == 'glob'
        and 'type' not in query
    )

    results = []

    for structure in structures:
        for element in structure.get('elements', []):
            if exclude_imports and element.get('category') == 'imports':
                continue
            if matches_filters(element, query):
                results.append(element)

    return results


# Sort keys an outline element already carries; any other (complexity, calls, ...) needs the metrics.
OUTLINE_SORT_FIELDS = (None, '', 'name', 'line', 'file')


def outline_plan(query: Dict[str, Any], sort_field: Any) -> Tuple[bool, Any]:
    """``(eligible, needle)``: can *query* pick its files from an outline (BACK-1867)?

    An outline (``get_outline()``) locates every function, class and method by name but omits
    metrics, calls and imports, so a query is eligible only when nothing it asks for lives in
    what is omitted: filter keys limited to ``name`` and ``type``, no import in play, and no
    sort on a metric. Import elements are named by their text, so an untyped exact ``name==X``
    could still match one; *needle* is then X and a file whose text lacks it cannot. An
    untyped glob drops imports itself (``apply_filters``). Anything else is not eligible and
    takes the full path, so the answer never differs from it.
    """
    if sort_field not in OUTLINE_SORT_FIELDS or 'name' not in query or set(query) - {'name', 'type'}:
        return False, None
    name = query['name']
    if 'type' in query:
        cond = normalize_type_condition(query['type'])
        if cond.get('op') == '==' and isinstance(cond.get('value'), str):
            kinds = [cond['value']]
        elif cond.get('op') == 'in' and isinstance(cond.get('value'), list):
            kinds = list(cond['value'])
        else:
            return False, None
        return ('imports' not in kinds), None
    if name.get('op') == 'glob':
        return True, None
    if name.get('op') == '==' and isinstance(name.get('value'), str):
        return True, name['value']
    return False, None


def matches_filters(element: ASTElement, query: Dict[str, Any]) -> bool:
    """Check if element matches all query filters.

    Args:
        element: Element dict
        query: Query dict with filter conditions

    Returns:
        True if element matches all filters
    """
    value: Any
    for key, condition in query.items():
        # Handle special key mappings
        if key == 'type':
            # Map 'type' to 'category'. Categories are plural (functions, classes) but
            # users may type singular.
            condition = normalize_type_condition(condition)
            value = _type_value(element, condition)
        elif key == 'lines':
            # Map 'lines' to 'line_count'
            value = element.get('line_count', 0)
        elif key == 'decorator':
            # Special handling: check if any decorator matches
            decorators = element.get('decorators', [])
            if not matches_decorator(decorators, condition):
                return False
            continue  # Already handled, skip normal comparison
        elif key == 'calls':
            # calls=<name>: find functions whose calls list contains <name>
            # Supports bare name match or attribute suffix: "validate_item" matches "self.validate_item"
            if not _matches_call_list(element.get('calls', []), condition):
                return False
            continue
        elif key == 'callee_of':
            # callee_of=<name>: find functions whose called_by list contains <name>
            if not _matches_call_list(element.get('called_by', []), condition):
                return False
            continue
        elif key == 'param_type':
            # param_type=dict: find functions where any param has this type annotation
            if not _matches_param_type(element.get('signature', ''), condition):
                return False
            continue
        elif key == 'return_type':
            # return_type=bool: find functions with this return annotation
            if not _matches_return_type(element.get('signature', ''), condition):
                return False
            continue
        elif key == 'has_annotations':
            # has_annotations=false: fully unannotated functions (no param or return hints)
            # has_annotations=true: at least one annotation present
            if not compare_value(_has_annotations(element.get('signature', '')), condition):
                return False
            continue
        elif key == 'callers':
            # callers>N: filter by number of inbound callers (length of called_by list)
            if not compare_value(len(element.get('called_by', [])), condition):
                return False
            continue
        else:
            value = cast(Dict[str, Any], element).get(key)  # arbitrary user-chosen key

        if value is None:
            return False

        if not compare_value(value, condition):
            return False

    return True


def matches_decorator(decorators: List[str], condition: Dict[str, Any]) -> bool:
    """Check if any decorator matches the condition (BACK-1777 contract).

    Each captured decorator holds one or more attributes (``@foo(...)`` one,
    ``[HttpGet, Authorize]`` and ``#[Route("/a"), Deprecated]`` one per top-level comma,
    ``conventions.decorator_attributes``). A query term matches an attribute by name:

    - ``decorator=HttpGet`` matches ``[HttpGet]`` and ``[HttpGet("{id}")]``; the term may be
      spelled as in source (``[HttpGet]``, ``#[Route]``, ``@Override``).
    - A qualified term matches when its segments end the attribute's name (``::`` and ``\\``
      read as ``.``): ``Obsolete`` and ``System.Obsolete`` match ``[System.Obsolete]``,
      ``route`` matches ``@app.route``; never a prefix (``Http`` does not match ``HttpGet``).
    - A term with arguments (``lru_cache(maxsize=100)``) also needs equal arguments, ignoring
      whitespace.
    - A comma list (op ``in``) matches if any term does.
    - A glob (``*cache*``, ``Http*``) matches the decorator's source text, an attribute's text,
      or its qualified or bare name. Rust ``#[derive(Debug)]`` is one attribute named
      ``derive``: ``decorator=Debug`` does not match it, ``decorator=*Debug*`` does.
    - ``!=`` keeps an element none of whose attributes match (an undecorated one too);
      ``~=`` is a regex search of the source text and each attribute's text and name.

    Args:
        decorators: Decorator source strings (e.g., ['@property', '[HttpGet, Authorize]'])
        condition: Condition dict with 'op' and 'value'

    Returns:
        True if any decorator matches
    """
    op = condition['op']
    value = condition['value']
    if op == '!=':
        positive = 'glob' if any(c in str(value) for c in '*?') else '=='
        return not matches_decorator(decorators, {'op': positive, 'value': value})
    if op == '~=':
        return any(compare_value(text, condition) for text in _decorator_texts(decorators))
    if not decorators or op not in ('==', 'in', 'glob'):
        return False
    raw = ','.join(str(v) for v in value) if isinstance(value, list) else str(value)
    terms = decorator_attributes(raw)
    return any(_decorator_matches_terms(dec, terms, op, raw) for dec in decorators)


def _decorator_texts(decorators: List[str]) -> List[str]:
    """Every text a ``decorator~=`` regex searches: each decorator's source, attributes and names."""
    texts: List[str] = []
    for dec in decorators:
        texts.append(dec)
        for attribute in decorator_attributes(dec):
            texts.extend((attribute, decorator_name(attribute)))
    return texts


def _decorator_matches_terms(dec: str, terms: List[str], op: str, raw: str) -> bool:
    """True when one captured decorator matches any query term (a glob term or a name term)."""
    attributes = decorator_attributes(dec)
    for term in terms:
        if op == 'glob' or (op == 'in' and ('*' in term or '?' in term)):
            if _decorator_glob_matches(dec, attributes, term, raw):
                return True
        elif any(_decorator_term_matches(term, attribute) for attribute in attributes):
            return True
    return False


def _decorator_args(attribute: str) -> str:
    """An attribute's argument text from its first ``(``, whitespace removed ('' when it has none)."""
    _, paren, args = attribute.partition('(')
    return ''.join((paren + args).split())


def _decorator_term_matches(term: str, attribute: str) -> bool:
    """True when *term*'s name segments end *attribute*'s name, and its arguments (if any) are equal."""
    wanted = decorator_name(term).split('.')
    have = decorator_name(attribute).split('.')
    if not wanted[-1] or len(wanted) > len(have) or have[-len(wanted):] != wanted:
        return False
    return '(' not in term or _decorator_args(term) == _decorator_args(attribute)


def _decorator_glob_matches(dec: str, attributes: List[str], pattern: str, raw: str) -> bool:
    """Glob over the source text (as before BACK-1777, ``*cache*`` / ``@lru*``) or any attribute's text or names."""
    if fnmatch(dec, raw) or fnmatch(dec, f'@{raw}'):
        return True
    for attribute in attributes:
        name = decorator_name(attribute)
        if any(fnmatch(text, pattern) for text in (attribute, name, name.rsplit('.', 1)[-1])):
            return True
    return False


def _type_value(element: ASTElement, condition: Dict[str, Any]) -> str:
    """The kind ``type=`` compares: the element's category, except that a function with an
    owner reads as ``methods`` when the condition names methods.

    No analyzer emits a ``methods`` category (a method is a ``functions`` element whose
    ``owner`` is its class), so ``type=method`` matched nothing; ``type=function`` still
    matches methods (BACK-2213).
    """
    category = str(element.get('category', ''))
    wanted = condition.get('value')
    names_methods = wanted == 'methods' or (isinstance(wanted, list) and 'methods' in wanted)
    if category == 'functions' and names_methods and cast(Dict[str, Any], element).get('owner'):
        return 'methods'
    return category


def normalize_type_condition(condition: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize type condition to handle singular/plural forms.

    Args:
        condition: Condition dict with 'op' and 'value'

    Returns:
        Normalized condition (singular -> plural)
    """
    # Map singular forms to plural (matching category values)
    singular_to_plural = {
        'function': 'functions',
        'class': 'classes',
        'method': 'methods',
        'struct': 'structs',
        'import': 'imports',
        'interface': 'interfaces',
        'trait': 'interfaces',  # Rust traits are stored as interfaces (BACK-1088)
        'module': 'modules',  # Rust mod (BACK-1636)
        'namespace': 'namespaces',  # PHP, C#, TypeScript
        'test': 'tests',
    }

    # Handle 'in' operator (OR logic) - normalize each type
    if condition.get('op') == 'in' and isinstance(condition.get('value'), list):
        normalized = [singular_to_plural.get(t.lower(), t.lower()) for t in condition['value']]
        return {'op': 'in', 'value': normalized}

    # Handle single type (type=X, type!=X)
    if condition.get('op') in ('==', '!=') and isinstance(condition.get('value'), str):
        value = condition['value'].lower()
        if value in singular_to_plural:
            return {'op': condition['op'], 'value': singular_to_plural[value]}

    return condition


def compare_value(value: Any, condition: Dict[str, Any]) -> bool:
    """Compare value against condition.

    Uses unified compare_values() from query.py to eliminate duplication.
    Adapts AST's condition dict format to the standard interface.

    Args:
        value: Actual value
        condition: Condition dict with 'op' and 'value'

    Returns:
        True if comparison passes
    """
    op = condition['op']
    target = condition['value']

    # Special case: 'glob' operator (AST-specific, not in unified parser)
    if op == 'glob':
        # Support single pattern or OR list: name=*run*|*process*
        if isinstance(target, list):
            return any(fnmatch(str(value), str(p)) for p in target)
        return fnmatch(str(value), str(target))

    # Special case: 'in' operator (list membership, AST-specific)
    elif op == 'in':
        # OR logic: check if value matches any in target list
        return str(value) in [str(t) for t in target]

    # All other operators: use unified comparison
    return compare_values(
        value,
        op,
        target,
        options={
            'allow_list_any': False,  # AST doesn't have list fields
            'case_sensitive': True,   # AST comparisons are case-sensitive
            'coerce_numeric': True,
            'none_matches_not_equal': False
        }
    )


def _matches_param_type(signature: str, condition: Dict[str, Any]) -> bool:
    """Check if any parameter in the signature has the given type annotation.

    Parses ': TYPE' patterns from the parameter section of a signature string
    like '(x: dict, y: str) -> bool'. Supports exact match and glob patterns.

    Examples:
        param_type=dict   matches (x: dict, y: str)
        param_type=Dict*  matches (x: Dict[str, Any])
    """
    param_str = signature.split(' -> ')[0] if ' -> ' in signature else signature
    # Extract bare type names after ': ' (handles generics like Dict[str, Any])
    types = re.findall(r':\s*([A-Za-z_][A-Za-z0-9_]*(?:\[[^\]]*\])*)', param_str)
    target = str(condition['value'])
    op = condition['op']
    for t in types:
        bare = t.split('[')[0]  # Dict[str, Any] → Dict for glob matching
        for candidate in {t, bare}:
            if op in ('==', '=') and candidate == target:
                return True
            elif op == 'glob' and fnmatch(candidate, target):
                return True
            elif op == '~=':
                if re.search(target, candidate):
                    return True
    return False


def _matches_return_type(signature: str, condition: Dict[str, Any]) -> bool:
    """Check if the return annotation matches the condition.

    Parses the ' -> TYPE' suffix of a signature string.
    Supports exact match and glob patterns.

    Examples:
        return_type=bool   matches (...) -> bool
        return_type=List*  matches (...) -> List[str]
        return_type=None   matches (...) -> None
    """
    if ' -> ' not in signature:
        return False
    return_part = signature.split(' -> ', 1)[1].strip().rstrip(':').strip()
    bare = return_part.split('[')[0]
    target = str(condition['value'])
    op = condition['op']
    for candidate in {return_part, bare}:
        if op in ('==', '=') and candidate == target:
            return True
        elif op == 'glob' and fnmatch(candidate, target):
            return True
        elif op == '~=':
            if re.search(target, candidate):
                return True
    return False


def _matches_call_list(call_list: List[str], condition: Dict[str, Any]) -> bool:
    """Check if any entry in a calls/called_by list satisfies the condition.

    Supports bare name match with attribute suffix stripping:
    - "validate_item" matches "validate_item" and "self.validate_item"
    - Glob patterns supported: "self.*" matches "self.bar"

    Args:
        call_list: List of callee/caller name strings
        condition: Condition dict with 'op' and 'value'

    Returns:
        True if any entry in call_list matches the condition
    """
    target = str(condition['value'])
    op = condition['op']

    for entry in call_list:
        # Also check the bare suffix (strips "self.", "obj.", etc.)
        local_name = entry.split('.')[-1]
        for candidate in {entry, local_name}:
            if op in ('==', '='):
                if candidate == target:
                    return True
            elif op == 'glob':
                if fnmatch(candidate, target):
                    return True
            elif op == '~=':
                if re.search(target, candidate):
                    return True
    return False


def _has_annotations(signature: str) -> bool:
    """Return True if the signature contains any type annotation.

    Checks for return annotation (->) or param annotations (: inside parens).
    """
    if not signature:
        return False
    if '->' in signature:
        return True
    paren_open = signature.find('(')
    paren_close = signature.rfind(')')
    if paren_open == -1 or paren_close == -1:
        return False
    params = signature[paren_open + 1:paren_close]
    return ':' in params

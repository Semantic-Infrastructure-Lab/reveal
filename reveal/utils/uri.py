"""URI parsing utilities for scheme-based adapters.

This module provides unified URI parsing for database, network, and connection
adapters (mysql, ssl, sqlite, domain, etc.).

Eliminates ~120 lines of duplicate URI parsing logic by centralizing common patterns:
- Scheme extraction
- Authentication parsing (user:password@)
- Host:port parsing
- Path/element extraction
- Query parameter parsing

Supported formats:
    scheme://host[:port][/path][?query]
    scheme://[user:pass@]host[:port][/element]
    scheme:///path (for file-based adapters)

Usage:
    # Parse mysql connection string
    uri = parse_resource_uri('mysql://user:pass@localhost:3306/mydb')
    # ParsedURI(scheme='mysql', user='user', password='pass',
    #           host='localhost', port=3306, element='mydb')

    # Parse SSL endpoint
    uri = parse_resource_uri('ssl://example.com:443', default_port=443)
    # ParsedURI(scheme='ssl', host='example.com', port=443)

    # Parse with query parameters
    uri = parse_resource_uri('http://api.example.com/v1/users?limit=10&format=json')
    # ParsedURI(scheme='http', host='api.example.com', path='/v1/users',
    #           query={'limit': '10', 'format': 'json'})
"""

from dataclasses import dataclass, field
from typing import Dict, Optional, List
from urllib.parse import parse_qs, urlparse, ParseResult


@dataclass
class ParsedURI:
    """Parsed URI components.

    Attributes:
        scheme: URI scheme (http, https, mysql, ssl, etc.)
        user: Username from user:pass@ auth (None if not provided)
        password: Password from user:pass@ auth (None if not provided)
        host: Hostname or IP address (None for file:// URIs)
        port: Port number (None if not specified, use default_port)
        path: Path component (e.g., /api/v1/users)
        element: Element/database name (alias for first path segment)
        query: Query parameters as dict
        fragment: URL fragment (rarely used)
        raw_uri: Original URI string
    """
    scheme: str
    user: Optional[str] = None
    password: Optional[str] = None
    host: Optional[str] = None
    port: Optional[int] = None
    path: Optional[str] = None
    element: Optional[str] = None
    query: Dict[str, str] = field(default_factory=dict)
    fragment: Optional[str] = None
    raw_uri: str = ""

    def __post_init__(self):
        """Extract element from path if not set."""
        if self.element is None and self.path:
            # Element is first segment of path (e.g., /dbname/table -> dbname)
            parts = self.path.lstrip('/').split('/', 1)
            if parts and parts[0]:
                self.element = parts[0]


def parse_resource_uri(
    uri: str,
    default_port: Optional[int] = None,
    allowed_schemes: Optional[List[str]] = None
) -> ParsedURI:
    """Parse resource URI into components.

    Handles various URI formats:
        scheme://host[:port][/path][?query]
        scheme://[user:pass@]host[:port][/element]
        scheme:///path (file-based)

    Args:
        uri: URI string to parse
        default_port: Default port if not specified in URI
        allowed_schemes: List of allowed schemes (raises ValueError if not in list)

    Returns:
        ParsedURI object with parsed components

    Raises:
        ValueError: If URI is invalid or scheme not allowed

    Examples:
        >>> uri = parse_resource_uri('mysql://user:pass@localhost:3306/mydb')
        >>> uri.scheme
        'mysql'
        >>> uri.user
        'user'
        >>> uri.host
        'localhost'
        >>> uri.port
        3306
        >>> uri.element
        'mydb'

        >>> uri = parse_resource_uri('ssl://example.com', default_port=443)
        >>> uri.host
        'example.com'
        >>> uri.port
        443
    """
    if not uri:
        raise ValueError("URI cannot be empty")

    # Use urllib.parse.urlparse for initial parsing
    parsed: ParseResult = urlparse(uri)

    if not parsed.scheme:
        raise ValueError(f"Invalid URI format (missing scheme): {uri}")

    # Validate scheme if allowed_schemes provided
    if allowed_schemes and parsed.scheme not in allowed_schemes:
        raise ValueError(
            f"Invalid scheme '{parsed.scheme}'. Allowed: {', '.join(allowed_schemes)}"
        )

    # Extract user and password from netloc (user:pass@host:port)
    user = parsed.username
    password = parsed.password
    host = parsed.hostname
    port = parsed.port or default_port

    # Extract path (may be empty for host-only URIs)
    path = parsed.path if parsed.path and parsed.path != '/' else None

    # Parse query string into dict
    query_dict: Dict[str, str] = {}
    if parsed.query:
        # parse_qs returns Dict[str, List[str]], we want Dict[str, str]
        parsed_qs = parse_qs(parsed.query)
        query_dict = {k: v[0] if v else '' for k, v in parsed_qs.items()}

    # Extract fragment
    fragment = parsed.fragment if parsed.fragment else None

    return ParsedURI(
        scheme=parsed.scheme,
        user=user,
        password=password,
        host=host,
        port=port,
        path=path,
        query=query_dict,
        fragment=fragment,
        raw_uri=uri
    )


def parse_connection_string(
    connection_string: str,
    scheme: str,
    default_port: Optional[int] = None
) -> ParsedURI:
    """Parse connection string for database/network adapters.

    Convenience wrapper around parse_resource_uri() that enforces a specific scheme.

    Args:
        connection_string: Connection string (mysql://..., ssl://..., etc.)
        scheme: Expected scheme (validates that URI starts with this)
        default_port: Default port for this connection type

    Returns:
        ParsedURI object

    Raises:
        ValueError: If connection string doesn't start with expected scheme

    Example:
        >>> uri = parse_connection_string('mysql://localhost/mydb', 'mysql', 3306)
        >>> uri.host
        'localhost'
        >>> uri.port
        3306
        >>> uri.element
        'mydb'
    """
    # Allow bare scheme:// to be valid (e.g., mysql:// for localhost defaults)
    if connection_string == f"{scheme}://":
        return ParsedURI(scheme=scheme, port=default_port, raw_uri=connection_string)

    if not connection_string.startswith(f"{scheme}://"):
        raise ValueError(
            f"Invalid {scheme} connection string. Must start with {scheme}://"
        )

    return parse_resource_uri(
        connection_string,
        default_port=default_port,
        allowed_schemes=[scheme]
    )


def parse_host_port(
    host_port_str: str,
    default_port: Optional[int] = None
) -> tuple[str, int]:
    """Parse host:port string into components.

    Args:
        host_port_str: String in format "host" or "host:port"
        default_port: Port to use if not specified

    Returns:
        Tuple of (host, port)

    Raises:
        ValueError: If port is not a valid integer

    Examples:
        >>> host, port = parse_host_port('localhost:3306')
        >>> host
        'localhost'
        >>> port
        3306

        >>> host, port = parse_host_port('example.com', default_port=443)
        >>> host
        'example.com'
        >>> port
        443
    """
    if ':' in host_port_str:
        host, port_str = host_port_str.rsplit(':', 1)
        try:
            port = int(port_str)
        except ValueError:
            raise ValueError(f"Invalid port number: {port_str}")
    else:
        host = host_port_str
        port = default_port

    if not host:
        raise ValueError("Host cannot be empty")

    return host, port


def build_connection_string(
    scheme: str,
    host: str,
    port: Optional[int] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
    element: Optional[str] = None,
    path: Optional[str] = None,
    query: Optional[Dict[str, str]] = None
) -> str:
    """Build connection string from components.

    Args:
        scheme: URI scheme (mysql, ssl, https, etc.)
        host: Hostname or IP
        port: Port number (omitted if None)
        user: Username for auth (omitted if None)
        password: Password for auth (omitted if None)
        element: Element/database name (appended as /element)
        path: Full path (alternative to element)
        query: Query parameters dict

    Returns:
        Formatted connection string

    Example:
        >>> build_connection_string('mysql', 'localhost', 3306, 'root', 'pass', 'mydb')
        'mysql://root:pass@localhost:3306/mydb'

        >>> build_connection_string('ssl', 'example.com', 443)
        'ssl://example.com:443'
    """
    uri = f"{scheme}://"

    # Add auth
    if user:
        uri += user
        if password:
            uri += f":{password}"
        uri += "@"

    # Add host:port
    uri += host
    if port:
        uri += f":{port}"

    # Add path or element
    if path:
        if not path.startswith('/'):
            path = '/' + path
        uri += path
    elif element:
        uri += f"/{element}"

    # Add query parameters
    if query:
        query_str = '&'.join(f"{k}={v}" for k, v in query.items())
        uri += f"?{query_str}"

    return uri


# Convenience functions for common schemes
def parse_mysql_uri(uri: str) -> ParsedURI:
    """Parse MySQL connection URI.

    Args:
        uri: mysql://[user:pass@]host[:port][/database]

    Returns:
        ParsedURI with mysql scheme
    """
    return parse_connection_string(uri, 'mysql', default_port=3306)


def parse_ssl_uri(uri: str) -> ParsedURI:
    """Parse SSL endpoint URI.

    Args:
        uri: ssl://host[:port][/element]

    Returns:
        ParsedURI with ssl scheme
    """
    return parse_connection_string(uri, 'ssl', default_port=443)


def parse_sqlite_uri(uri: str) -> ParsedURI:
    """Parse SQLite URI.

    Args:
        uri: sqlite:///path/to/db.sqlite or sqlite://path/to/db.sqlite

    Returns:
        ParsedURI with sqlite scheme
    """
    if uri == "sqlite://":
        raise ValueError("SQLite URI requires path: sqlite:///path/to/db.sqlite")

    parsed = parse_resource_uri(uri, allowed_schemes=['sqlite'])

    # For sqlite:///path, the path is in parsed.path
    # Make it accessible via .element for consistency
    if parsed.path and not parsed.element:
        parsed.element = parsed.path

    return parsed

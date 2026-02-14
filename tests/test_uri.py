"""Tests for reveal.utils.uri module."""
import pytest
from reveal.utils.uri import (
    ParsedURI,
    parse_resource_uri,
    parse_connection_string,
    parse_host_port,
    build_connection_string,
    parse_mysql_uri,
    parse_ssl_uri,
    parse_sqlite_uri,
)


class TestParsedURI:
    """Tests for ParsedURI dataclass."""

    def test_basic_initialization(self):
        """ParsedURI initializes with minimal fields."""
        uri = ParsedURI(scheme="http")
        assert uri.scheme == "http"
        assert uri.user is None
        assert uri.host is None

    def test_post_init_extracts_element_from_path(self):
        """__post_init__ extracts element from path."""
        uri = ParsedURI(scheme="mysql", path="/mydb/table")
        assert uri.element == "mydb"

    def test_post_init_no_element_from_empty_path(self):
        """__post_init__ doesn't extract element from empty path."""
        uri = ParsedURI(scheme="mysql", path="")
        assert uri.element is None

    def test_post_init_no_element_from_root_path(self):
        """__post_init__ doesn't extract element from root path."""
        uri = ParsedURI(scheme="mysql", path="/")
        assert uri.element is None

    def test_post_init_preserves_explicit_element(self):
        """__post_init__ preserves explicitly set element."""
        uri = ParsedURI(scheme="mysql", path="/mydb", element="explicit")
        assert uri.element == "explicit"

    def test_query_defaults_to_empty_dict(self):
        """Query parameter defaults to empty dict."""
        uri = ParsedURI(scheme="http")
        assert uri.query == {}
        assert isinstance(uri.query, dict)


class TestParseResourceURI:
    """Tests for parse_resource_uri() function."""

    def test_simple_http_uri(self):
        """Parse simple HTTP URI."""
        uri = parse_resource_uri("http://example.com")
        assert uri.scheme == "http"
        assert uri.host == "example.com"
        assert uri.port is None

    def test_https_with_port(self):
        """Parse HTTPS URI with explicit port."""
        uri = parse_resource_uri("https://example.com:8443")
        assert uri.scheme == "https"
        assert uri.host == "example.com"
        assert uri.port == 8443

    def test_with_default_port(self):
        """Parse URI and apply default port."""
        uri = parse_resource_uri("mysql://localhost", default_port=3306)
        assert uri.host == "localhost"
        assert uri.port == 3306

    def test_explicit_port_overrides_default(self):
        """Explicit port overrides default_port."""
        uri = parse_resource_uri("mysql://localhost:3307", default_port=3306)
        assert uri.port == 3307

    def test_with_user_and_password(self):
        """Parse URI with authentication."""
        uri = parse_resource_uri("mysql://user:password@localhost")
        assert uri.user == "user"
        assert uri.password == "password"
        assert uri.host == "localhost"

    def test_with_user_no_password(self):
        """Parse URI with username but no password."""
        uri = parse_resource_uri("mysql://user@localhost")
        assert uri.user == "user"
        assert uri.password is None
        assert uri.host == "localhost"

    def test_with_path(self):
        """Parse URI with path."""
        uri = parse_resource_uri("http://example.com/api/v1/users")
        assert uri.host == "example.com"
        assert uri.path == "/api/v1/users"

    def test_with_single_element_path(self):
        """Parse URI with single element path."""
        uri = parse_resource_uri("mysql://localhost/mydb")
        assert uri.path == "/mydb"
        assert uri.element == "mydb"

    def test_with_query_parameters(self):
        """Parse URI with query parameters."""
        uri = parse_resource_uri("http://api.example.com/search?q=test&limit=10")
        assert uri.host == "api.example.com"
        assert uri.path == "/search"
        assert uri.query == {"q": "test", "limit": "10"}

    def test_with_fragment(self):
        """Parse URI with fragment."""
        uri = parse_resource_uri("http://example.com/page#section1")
        assert uri.host == "example.com"
        assert uri.path == "/page"
        assert uri.fragment == "section1"

    def test_complete_uri(self):
        """Parse URI with all components."""
        uri = parse_resource_uri(
            "https://user:pass@api.example.com:8443/v1/data?format=json&limit=5#results"
        )
        assert uri.scheme == "https"
        assert uri.user == "user"
        assert uri.password == "pass"
        assert uri.host == "api.example.com"
        assert uri.port == 8443
        assert uri.path == "/v1/data"
        assert uri.query == {"format": "json", "limit": "5"}
        assert uri.fragment == "results"

    def test_raw_uri_preserved(self):
        """Original URI string is preserved."""
        original = "mysql://user:pass@localhost:3306/mydb"
        uri = parse_resource_uri(original)
        assert uri.raw_uri == original

    def test_empty_uri_raises(self):
        """Empty URI raises ValueError."""
        with pytest.raises(ValueError, match="URI cannot be empty"):
            parse_resource_uri("")

    def test_missing_scheme_parsed_as_scheme_path(self):
        """URI without // gets parsed as scheme:path by urllib.parse."""
        # This is actually valid URI format: scheme:path
        # "localhost:3306" becomes scheme="localhost", path="3306"
        uri = parse_resource_uri("localhost:3306")
        assert uri.scheme == "localhost"
        assert uri.path == "3306"

    def test_allowed_schemes_valid(self):
        """Allowed schemes list accepts valid scheme."""
        uri = parse_resource_uri("mysql://localhost", allowed_schemes=["mysql", "postgres"])
        assert uri.scheme == "mysql"

    def test_allowed_schemes_invalid(self):
        """Allowed schemes list rejects invalid scheme."""
        with pytest.raises(ValueError, match="Invalid scheme 'http'. Allowed: mysql, postgres"):
            parse_resource_uri("http://localhost", allowed_schemes=["mysql", "postgres"])

    def test_ipv4_address(self):
        """Parse URI with IPv4 address."""
        uri = parse_resource_uri("http://192.168.1.1:8080")
        assert uri.host == "192.168.1.1"
        assert uri.port == 8080

    def test_ipv6_address(self):
        """Parse URI with IPv6 address."""
        uri = parse_resource_uri("http://[2001:db8::1]:8080")
        assert uri.host == "2001:db8::1"
        assert uri.port == 8080

    def test_root_path_normalized_to_none(self):
        """Root path '/' is normalized to None."""
        uri = parse_resource_uri("http://example.com/")
        assert uri.path is None

    def test_query_with_empty_value(self):
        """Query parameter with empty value is ignored by parse_qs."""
        # parse_qs ignores empty values by default
        uri = parse_resource_uri("http://example.com?key=")
        assert uri.query == {}

    def test_query_with_multiple_values_takes_first(self):
        """Query parameter with multiple values takes first."""
        uri = parse_resource_uri("http://example.com?key=value1&key=value2")
        assert uri.query["key"] == "value1"

    def test_special_characters_in_password(self):
        """Parse URI with special characters in password."""
        uri = parse_resource_uri("mysql://user:p@ss:w0rd@localhost")
        assert uri.user == "user"
        assert uri.password == "p@ss:w0rd"

    def test_no_host_for_file_scheme(self):
        """File scheme URIs may not have host."""
        uri = parse_resource_uri("file:///path/to/file")
        assert uri.scheme == "file"
        assert uri.host is None
        assert uri.path == "/path/to/file"


class TestParseConnectionString:
    """Tests for parse_connection_string() function."""

    def test_valid_mysql_connection(self):
        """Parse valid MySQL connection string."""
        uri = parse_connection_string("mysql://localhost/mydb", "mysql", 3306)
        assert uri.scheme == "mysql"
        assert uri.host == "localhost"
        assert uri.port == 3306
        assert uri.element == "mydb"

    def test_applies_default_port(self):
        """Connection string applies default port."""
        uri = parse_connection_string("ssl://example.com", "ssl", 443)
        assert uri.port == 443

    def test_scheme_validation(self):
        """Connection string validates scheme."""
        with pytest.raises(ValueError, match="Invalid mysql connection string"):
            parse_connection_string("postgres://localhost", "mysql")

    def test_bare_scheme(self):
        """Bare scheme:// is valid."""
        uri = parse_connection_string("mysql://", "mysql", 3306)
        assert uri.scheme == "mysql"
        assert uri.port == 3306

    def test_with_all_components(self):
        """Connection string with all components."""
        uri = parse_connection_string(
            "mysql://user:pass@localhost:3307/mydb", "mysql", 3306
        )
        assert uri.user == "user"
        assert uri.password == "pass"
        assert uri.host == "localhost"
        assert uri.port == 3307
        assert uri.element == "mydb"

    def test_enforces_single_scheme(self):
        """Connection string enforces single allowed scheme."""
        with pytest.raises(ValueError, match="Invalid mysql connection string"):
            parse_connection_string("postgres://localhost", "mysql", 3306)


class TestParseHostPort:
    """Tests for parse_host_port() function."""

    def test_host_with_port(self):
        """Parse host:port string."""
        host, port = parse_host_port("localhost:3306")
        assert host == "localhost"
        assert port == 3306

    def test_host_only_with_default(self):
        """Parse host only, apply default port."""
        host, port = parse_host_port("example.com", default_port=443)
        assert host == "example.com"
        assert port == 443

    def test_host_only_no_default(self):
        """Parse host only, no default port."""
        host, port = parse_host_port("example.com")
        assert host == "example.com"
        assert port is None

    def test_ipv4_with_port(self):
        """Parse IPv4:port string."""
        host, port = parse_host_port("192.168.1.1:8080")
        assert host == "192.168.1.1"
        assert port == 8080

    def test_invalid_port_raises(self):
        """Invalid port number raises ValueError."""
        with pytest.raises(ValueError, match="Invalid port number: abc"):
            parse_host_port("localhost:abc")

    def test_empty_host_raises(self):
        """Empty host raises ValueError."""
        with pytest.raises(ValueError, match="Host cannot be empty"):
            parse_host_port(":3306")

    def test_multiple_colons_uses_last(self):
        """Multiple colons uses last as port separator."""
        host, port = parse_host_port("my:host:name:3306")
        assert host == "my:host:name"
        assert port == 3306

    def test_port_zero(self):
        """Port 0 is valid."""
        host, port = parse_host_port("localhost:0")
        assert host == "localhost"
        assert port == 0


class TestBuildConnectionString:
    """Tests for build_connection_string() function."""

    def test_simple_host(self):
        """Build simple connection string."""
        uri = build_connection_string("http", "example.com")
        assert uri == "http://example.com"

    def test_with_port(self):
        """Build connection string with port."""
        uri = build_connection_string("mysql", "localhost", port=3306)
        assert uri == "mysql://localhost:3306"

    def test_with_auth(self):
        """Build connection string with authentication."""
        uri = build_connection_string("mysql", "localhost", user="root", password="pass")
        assert uri == "mysql://root:pass@localhost"

    def test_with_user_no_password(self):
        """Build connection string with user but no password."""
        uri = build_connection_string("mysql", "localhost", user="root")
        assert uri == "mysql://root@localhost"

    def test_with_element(self):
        """Build connection string with element."""
        uri = build_connection_string("mysql", "localhost", element="mydb")
        assert uri == "mysql://localhost/mydb"

    def test_with_path(self):
        """Build connection string with path."""
        uri = build_connection_string("http", "example.com", path="/api/v1/users")
        assert uri == "http://example.com/api/v1/users"

    def test_path_without_leading_slash(self):
        """Build connection string adds leading slash to path."""
        uri = build_connection_string("http", "example.com", path="api/users")
        assert uri == "http://example.com/api/users"

    def test_with_query(self):
        """Build connection string with query parameters."""
        uri = build_connection_string("http", "example.com", query={"limit": "10", "format": "json"})
        assert "http://example.com?" in uri
        assert "limit=10" in uri
        assert "format=json" in uri

    def test_complete_uri(self):
        """Build complete connection string."""
        uri = build_connection_string(
            "mysql", "localhost", port=3306, user="root", password="pass", element="mydb"
        )
        assert uri == "mysql://root:pass@localhost:3306/mydb"

    def test_path_overrides_element(self):
        """Path takes precedence over element."""
        uri = build_connection_string("http", "example.com", path="/api", element="ignored")
        assert uri == "http://example.com/api"
        assert "ignored" not in uri


class TestParseMysqlURI:
    """Tests for parse_mysql_uri() convenience function."""

    def test_simple_mysql_uri(self):
        """Parse simple MySQL URI."""
        uri = parse_mysql_uri("mysql://localhost")
        assert uri.scheme == "mysql"
        assert uri.host == "localhost"
        assert uri.port == 3306

    def test_mysql_with_database(self):
        """Parse MySQL URI with database."""
        uri = parse_mysql_uri("mysql://localhost/mydb")
        assert uri.element == "mydb"

    def test_mysql_with_auth(self):
        """Parse MySQL URI with authentication."""
        uri = parse_mysql_uri("mysql://user:pass@localhost/mydb")
        assert uri.user == "user"
        assert uri.password == "pass"

    def test_mysql_custom_port(self):
        """Parse MySQL URI with custom port."""
        uri = parse_mysql_uri("mysql://localhost:3307/mydb")
        assert uri.port == 3307

    def test_mysql_invalid_scheme(self):
        """Parse MySQL URI rejects invalid scheme."""
        with pytest.raises(ValueError, match="Invalid mysql connection string"):
            parse_mysql_uri("postgres://localhost")


class TestParseSslURI:
    """Tests for parse_ssl_uri() convenience function."""

    def test_simple_ssl_uri(self):
        """Parse simple SSL URI."""
        uri = parse_ssl_uri("ssl://example.com")
        assert uri.scheme == "ssl"
        assert uri.host == "example.com"
        assert uri.port == 443

    def test_ssl_custom_port(self):
        """Parse SSL URI with custom port."""
        uri = parse_ssl_uri("ssl://example.com:8443")
        assert uri.port == 8443

    def test_ssl_with_path(self):
        """Parse SSL URI with path/element."""
        uri = parse_ssl_uri("ssl://example.com/cert")
        assert uri.element == "cert"

    def test_ssl_invalid_scheme(self):
        """Parse SSL URI rejects invalid scheme."""
        with pytest.raises(ValueError, match="Invalid ssl connection string"):
            parse_ssl_uri("http://example.com")


class TestParseSqliteURI:
    """Tests for parse_sqlite_uri() convenience function."""

    def test_sqlite_absolute_path(self):
        """Parse SQLite URI with absolute path."""
        uri = parse_sqlite_uri("sqlite:///path/to/database.db")
        assert uri.scheme == "sqlite"
        assert uri.path == "/path/to/database.db"
        # Element is first segment of path
        assert uri.element == "path"

    def test_sqlite_relative_path(self):
        """Parse SQLite URI with double-slash (interpreted as host)."""
        # sqlite://database.db is parsed as host, not path
        uri = parse_sqlite_uri("sqlite://database.db")
        assert uri.host == "database.db"
        assert uri.path is None

    def test_sqlite_empty_raises(self):
        """Empty SQLite URI raises ValueError."""
        with pytest.raises(ValueError, match="SQLite URI requires path"):
            parse_sqlite_uri("sqlite://")

    def test_sqlite_invalid_scheme(self):
        """Parse SQLite URI rejects invalid scheme."""
        with pytest.raises(ValueError, match="Invalid scheme"):
            parse_sqlite_uri("mysql:///path/to/db")


class TestRoundTrip:
    """Tests for parse -> build round-trip consistency."""

    def test_roundtrip_simple(self):
        """Round-trip simple URI."""
        original = "http://example.com"
        parsed = parse_resource_uri(original)
        rebuilt = build_connection_string(
            parsed.scheme, parsed.host, parsed.port, parsed.user,
            parsed.password, parsed.element, parsed.path, parsed.query
        )
        assert rebuilt == original

    def test_roundtrip_with_auth(self):
        """Round-trip URI with authentication."""
        original = "mysql://user:pass@localhost:3306/mydb"
        parsed = parse_resource_uri(original)
        rebuilt = build_connection_string(
            parsed.scheme, parsed.host, parsed.port, parsed.user,
            parsed.password, parsed.element
        )
        assert rebuilt == original

    def test_roundtrip_with_query(self):
        """Round-trip URI with query parameters."""
        original = "http://example.com"
        query = {"limit": "10", "format": "json"}
        parsed = parse_resource_uri(f"{original}?limit=10&format=json")
        rebuilt = build_connection_string(
            parsed.scheme, parsed.host, parsed.port,
            query=parsed.query
        )
        # Query parameter order may vary
        assert rebuilt.startswith(original + "?")
        assert "limit=10" in rebuilt
        assert "format=json" in rebuilt


class TestEdgeCases:
    """Tests for edge cases and unusual inputs."""

    def test_localhost_shorthand(self):
        """Localhost without domain works."""
        uri = parse_resource_uri("http://localhost")
        assert uri.host == "localhost"

    def test_underscore_in_hostname(self):
        """Underscores in hostname are accepted."""
        uri = parse_resource_uri("http://my_server.local")
        assert uri.host == "my_server.local"

    def test_very_long_path(self):
        """Very long path is handled."""
        long_path = "/api/" + "segment/" * 50 + "endpoint"
        uri = parse_resource_uri(f"http://example.com{long_path}")
        assert uri.path == long_path

    def test_port_65535(self):
        """Maximum port number works."""
        uri = parse_resource_uri("http://example.com:65535")
        assert uri.port == 65535

    def test_empty_password(self):
        """Empty password (user:@host) is handled."""
        uri = parse_resource_uri("mysql://user:@localhost")
        assert uri.user == "user"
        assert uri.password == ""

    def test_percent_encoded_characters(self):
        """Percent-encoded characters in password stay encoded."""
        # urllib.parse does NOT automatically decode percent-encoded characters
        uri = parse_resource_uri("mysql://user:p%40ss@localhost")
        assert uri.user == "user"
        assert uri.password == "p%40ss"

    def test_query_parameter_with_equals(self):
        """Query parameter value containing equals sign."""
        uri = parse_resource_uri("http://example.com?data=key=value")
        assert uri.query["data"] == "key=value"

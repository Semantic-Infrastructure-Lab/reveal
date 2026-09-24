"""`network` / `db` / `sdk` rule tables, import-shaped (BACK-1334 slices a-c: Go, Java, Kotlin, C#,
Rust, Swift, Ruby, C++).

Each row says "importing this module, or anything beneath it, is a network / database / vendor-SDK
surface". They replace the per-language `_*_TAXONOMY` tuples that `categorize_by_prefix` walked;
behavior is carried over site-for-site (entry `type: import`, `name` = the imported module; C++
keeps `type: include`, `name` = the header path).

One row is generated per module so every module has its own example and its own lookalike
counter-example (`<module>x` must not match: prefixes are segment-aligned). A file that imports a
module from two categories reports it under both; the tables keep their modules disjoint and a
test pins that, so first-match-wins across categories (the old behavior) cannot differ.

A module containing `*` is a glob for a name-prefix family with no shared segment (Rust
`aws_sdk_*`, Ruby `aws-sdk-*`); its example fills the `*` with `x` and its lookalike prefixes an `x`.
Ruby gems are matched as `gem`, `gem/...` and `gem-...` (the old scanner's rule), so each gem
generates a `gem` row and a `gem-*` row. C++ header roots are plain string prefixes, not segments
(`sqlite3` covers `sqlite3.h`, `mysql` covers `mysql.h` and `mysql/mysql.h`), so each C++ entry is
generated as the glob `<root>*`.

Socket-client Call/New rows for `network` live in `surface_rules_sockets.py` (BACK-1334 slice e).

Not yet rule-driven: PHP, Python, TypeScript/JavaScript (BACK-1334 slices c-d).
"""

from .surface_rules_model import Import, Rule
from .surface_rules_sockets import RULES as _SOCKET_RULES

# lang -> (example for module `{m}`, lookalike that must not match). The lookalike appends a
# letter to the last segment, so it shares the prefix text but not a segment boundary.
_SOURCES = {
    'go': ('package main\nimport "{m}"\nfunc main() {{}}\n',
           'package main\nimport "{m}x"\nfunc main() {{}}\n'),
    'java': ('import {m};\nclass A {{}}\n', 'import {m}x;\nclass A {{}}\n'),
    'kotlin': ('import {m}\nfun main() {{}}\n', 'import {m}x\nfun main() {{}}\n'),
    'csharp': ('using {m};\nclass A {{}}\n', 'using {m}x;\nclass A {{}}\n'),
    'rust': ('use {m};\nfn main() {{}}\n', 'use {m}x;\nfn main() {{}}\n'),
    'swift': ('import {m}\n', 'import {m}x\n'),
    'ruby': ("require '{m}'\n", "require '{m}x'\n"),
    'cpp': ('#include <{m}>\nint main() {{}}\n', '#include <{m}>\nint main() {{}}\n'),
}

# Ruby gem names are also matched with a `-` suffix (`aws-sdk` covers `aws-sdk-s3`), which is not
# a segment separator, so each gem gets a second, glob row.
_DASH_FAMILIES = frozenset({'ruby'})

# Languages whose entries are plain string prefixes of the module text (the old `startswith`).
_PREFIX_LANGS = frozenset({'cpp'})

# The entry `type` when it is not `import`.
_ENTRY_TYPES = {'cpp': 'include'}

_MODULES = {
    'network': {
        'go': ('net/http', 'net/rpc', 'google.golang.org/grpc', 'github.com/gorilla/websocket',
               'github.com/go-resty/resty'),
        'java': ('java.net.Socket', 'java.net.ServerSocket', 'java.net.DatagramSocket',
                 'java.net.URL', 'java.net.URLConnection', 'java.net.HttpURLConnection',
                 'java.net.http', 'okhttp3', 'retrofit2', 'org.apache.http', 'org.apache.hc'),
        'kotlin': ('java.net.Socket', 'java.net.ServerSocket', 'java.net.DatagramSocket',
                   'java.net.URL', 'java.net.URLConnection', 'java.net.HttpURLConnection',
                   'java.net.http', 'okhttp3', 'retrofit2', 'org.apache.http', 'io.ktor.client'),
        'csharp': ('System.Net.Http', 'RestSharp'),
        'rust': ('reqwest', 'hyper', 'isahc', 'ureq', 'tonic', 'tungstenite',
                 'tokio_tungstenite', 'awc'),
        'swift': ('Alamofire', 'Moya', 'AsyncHTTPClient', 'NIOHTTP1', 'NIOHTTP2'),
        'ruby': ('net/http', 'faraday', 'httparty', 'excon', 'typhoeus', 'rest-client'),
        # BSD/POSIX and Winsock socket headers too (BACK-1090): the library roots never matched.
        'cpp': ('curl/', 'cpr/', 'boost/asio', 'boost/beast', 'restclient', 'cpp-httplib',
                'httplib.h', 'sys/socket.h', 'netinet/', 'arpa/inet.h', 'netdb.h', 'winsock2.h',
                'ws2tcpip.h'),
    },
    'db': {
        'go': ('database/sql', 'gorm.io/gorm', 'github.com/jmoiron/sqlx',
               'go.mongodb.org/mongo-driver', 'github.com/redis/go-redis',
               'github.com/go-redis/redis', 'github.com/lib/pq',
               'github.com/go-sql-driver/mysql', 'github.com/jackc/pgx'),
        'java': ('java.sql', 'javax.persistence', 'jakarta.persistence', 'org.hibernate',
                 'org.springframework.data', 'com.mongodb', 'redis.clients.jedis'),
        'kotlin': ('java.sql', 'javax.persistence', 'jakarta.persistence', 'org.hibernate',
                   'org.springframework.data', 'com.mongodb', 'redis.clients.jedis',
                   'org.jetbrains.exposed'),
        'csharp': ('System.Data', 'Microsoft.EntityFrameworkCore', 'Dapper', 'Npgsql',
                   'MongoDB.Driver', 'StackExchange.Redis'),
        'rust': ('sqlx', 'diesel', 'tokio_postgres', 'postgres', 'mysql', 'mysql_async', 'redis',
                 'mongodb', 'rusqlite', 'sea_orm', 'deadpool_postgres'),
        'swift': ('GRDB', 'SQLite', 'RealmSwift', 'MongoKitten', 'Fluent', 'FluentKit',
                  'PostgresKit', 'MySQLKit', 'PostgresNIO'),
        'ruby': ('active_record', 'activerecord', 'sequel', 'mongo', 'mongoid', 'redis', 'pg',
                 'mysql2', 'sqlite3'),
        # The old list also had `mysqlx`, which the `mysql` prefix already covers.
        'cpp': ('pqxx/', 'sqlite3', 'mysql', 'mongocxx/', 'bsoncxx/', 'hiredis', 'sw/redis++',
                'soci/'),
    },
    'sdk': {
        'go': ('github.com/stripe/stripe-go', 'github.com/aws/aws-sdk-go',
               'github.com/aws/aws-sdk-go-v2', 'cloud.google.com/go',
               'github.com/twilio/twilio-go', 'github.com/slack-go/slack',
               'github.com/Azure/azure-sdk-for-go'),
        'java': ('com.amazonaws', 'software.amazon.awssdk', 'com.google.cloud', 'com.azure',
                 'com.microsoft.azure', 'com.stripe', 'com.twilio', 'com.slack.api'),
        'kotlin': ('com.amazonaws', 'software.amazon.awssdk', 'com.google.cloud', 'com.azure',
                   'com.stripe', 'com.twilio', 'com.slack.api'),
        'csharp': ('AWSSDK', 'Amazon', 'Azure', 'Google.Cloud', 'Stripe', 'Twilio'),
        # Old Rust taxonomy: exact crates plus the prefixes aws_sdk_ / aws_config / azure_ /
        # google_cloud_. `azure_core` and `google_cloud_storage` were exact entries under those
        # prefixes, so the globs cover them. `aws_config` is now exact (was a bare startswith).
        'rust': ('stripe', 'rusoto_core', 'rusoto_s3', 'twilio', 'octocrab', 'aws_sdk_*',
                 'aws_config', 'azure_*', 'google_cloud_*'),
        'swift': ('Stripe', 'StripeKit', 'Soto', 'AWSSDKSwift', 'FirebaseCore',
                  'FirebaseFirestore', 'FirebaseAuth', 'Sentry'),
        'ruby': ('aws-sdk', 'stripe', 'twilio-ruby', 'google/cloud', 'sendgrid-ruby',
                 'mailgun-ruby'),
        'cpp': ('aws/', 'google/cloud', 'stripe/'),
    },
}


def _forms(lang: str, module: str) -> tuple:
    """(pattern, module the example imports, module the lookalike imports)."""
    if '*' in module:
        concrete = module.replace('*', 'x')
        return module, concrete, 'x' + concrete
    return module, module, module + 'x'


def _patterns(lang: str, module: str) -> tuple:
    if lang in _PREFIX_LANGS:
        return (module + '*',)
    return (module, module + '-*') if lang in _DASH_FAMILIES else (module,)


def _rows(category: str) -> tuple:
    rows = []
    for lang, modules in _MODULES[category].items():
        example, lookalike = _SOURCES[lang]
        for m in modules:
            for pattern in _patterns(lang, m):
                pattern, hit, miss = _forms(lang, pattern)
                rows.append(Rule(category, lang, Import(module=pattern), '{module}',
                                 example=example.format(m=hit),
                                 counter_examples=(lookalike.format(m=miss),),
                                 entry_type=_ENTRY_TYPES.get(lang, 'import')))
    return tuple(rows)


# A category has one table: `network` also carries the socket-client Call/New rows.
_EXTRA = {'network': _SOCKET_RULES}

TABLES = {category: _rows(category) + _EXTRA.get(category, ()) for category in _MODULES}

"""`network` / `db` / `sdk` rule tables, import-shaped (BACK-1334 slice a: Go, Java, Kotlin, C#).

Each row says "importing this module, or anything beneath it, is a network / database / vendor-SDK
surface". They replace the per-language `_*_TAXONOMY` tuples that `categorize_by_prefix` walked;
behavior is carried over site-for-site (entry `type: import`, `name` = the imported module).

One row is generated per module so every module has its own example and its own lookalike
counter-example (`<module>x` must not match: prefixes are segment-aligned). A file that imports a
module from two categories reports it under both; the tables keep their modules disjoint and a
test pins that, so first-match-wins across categories (the old behavior) cannot differ.

Not yet rule-driven: Rust, Swift, Ruby, C++, PHP, Python, TypeScript/JavaScript (BACK-1334
slices b-d; several match by root name or plain string prefix, not by segment).
"""

from .surface_rules import Import, Rule, register_table

# lang -> (example for module `{m}`, lookalike that must not match). The lookalike appends a
# letter to the last segment, so it shares the prefix text but not a segment boundary.
_SOURCES = {
    'go': ('package main\nimport "{m}"\nfunc main() {{}}\n',
           'package main\nimport "{m}x"\nfunc main() {{}}\n'),
    'java': ('import {m};\nclass A {{}}\n', 'import {m}x;\nclass A {{}}\n'),
    'kotlin': ('import {m}\nfun main() {{}}\n', 'import {m}x\nfun main() {{}}\n'),
    'csharp': ('using {m};\nclass A {{}}\n', 'using {m}x;\nclass A {{}}\n'),
}

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
    },
}


def _rows(category: str) -> tuple:
    rows = []
    for lang, modules in _MODULES[category].items():
        example, lookalike = _SOURCES[lang]
        for m in modules:
            rows.append(Rule(category, lang, Import(module=m), '{module}',
                             example=example.format(m=m),
                             counter_examples=(lookalike.format(m=m),),
                             entry_type='import'))
    return tuple(rows)


for _category in _MODULES:
    register_table(_category, _rows(_category))

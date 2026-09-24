"""`network` / `db` rule rows for PHP's I/O builtins (BACK-1090, moved to rules in BACK-1334 c).

PHP I/O is mostly global functions and constructors, not `use` imports, so the import rows
(`surface_rules_imports.py`) cannot see it. These are curated exact names, as the scanner's
tables were: a bare call (`curl_init()`, `\\curl_init()`; not `$obj->curl_init()` or a namespaced
`Foo\\curl_init()`), or `new PDO(...)`. `fopen` / `file_get_contents` / `file` are network only
when their first string argument is a URL; `fopen`'s file-write form stays with the scanner's `fs`.

Entry shape carried over: `type: call`, `name` = the function, or `new <Class>`.
"""

from .surface_rules_model import Call, New, Rule

_NET_FUNCS = ('curl_init', 'curl_multi_init', 'fsockopen', 'pfsockopen', 'stream_socket_client',
              'stream_socket_server', 'socket_create')
_DB_FUNCS = ('mysqli_connect', 'mysqli_real_connect', 'mysql_connect', 'mysql_pconnect',
             'pg_connect', 'pg_pconnect', 'sqlsrv_connect', 'oci_connect', 'sqlite_open')
_URL_SCHEMES = ('http://', 'https://', 'ftp://')

RULES = (
    Rule('network', 'php', Call(receiver='', name=_NET_FUNCS), '{name}',
         example='<?php\n$h = curl_init();\n',
         counter_examples=('<?php\n$h = $client->curl_init();\n$g = Http\\curl_init();\n',),
         entry_type='call'),
    Rule('network', 'php',
         Call(receiver='', name=('fopen', 'file_get_contents', 'file'), string_arg=True,
              key_prefix=_URL_SCHEMES),
         '{name}',
         example="<?php\n$f = fopen('https://example.com/a', 'r');\n",
         counter_examples=("<?php\n$f = fopen('/tmp/a', 'w');\n$g = file_get_contents($url);\n",),
         entry_type='call'),
    Rule('db', 'php', Call(receiver='', name=_DB_FUNCS), '{name}',
         example="<?php\n$db = mysqli_connect('h', 'u', 'p');\n",
         counter_examples=("<?php\n$db = Foo::mysqli_connect('h');\n",),
         entry_type='call'),
    Rule('db', 'php', New(type=('PDO', 'mysqli', 'SQLite3')), 'new {type}',
         example="<?php\n$db = new PDO('sqlite::memory:');\n",
         counter_examples=("<?php\n$db = new PDOx('dsn');\n",),
         entry_type='call'),
)

"""`env` rule table (BACK-1333): call-shaped environment reads with a literal key.

Behavior carried over from the per-language scanners it replaces, so the corpus parity sweep
stays site-for-site. An entry is `{'type': 'env_var', 'name': <key>, 'expr': <callee>}`, and a
call whose key is not a string literal (`System.getenv()`, `getenv(name)`) is no entry.

Not yet rule-driven: Python, TypeScript/JavaScript, Ruby and PHP (subscript and property
forms such as `ENV['X']` and `process.env.X`, which have no fact yet), C++ and Swift.
"""

from .surface_rules_model import Call, Rule

_C = 'env'
_T = 'env_var'


def _row(lang, match, expr, example, counter_examples=()):
    return Rule(_C, lang, match, '{key}', example=example, counter_examples=counter_examples,
                entry_type=_T, entry_expr=expr)


RULES = (
    _row('go', Call(receiver='os', name=('Getenv', 'LookupEnv'), string_arg=True),
         '{receiver}.{name}',
         'package main\nimport "os"\nfunc f() { os.Getenv("HOME") }\n',
         ('package main\nimport "os"\nfunc f(k string) { os.Getenv(k); os.Setenv("A", "b") }\n',
          'package main\nfunc f(o x) { o.Getenv("A") }\n')),
    _row('java', Call(receiver='System', name='getenv', string_arg=True), 'System.getenv',
         'class A { void f() { System.getenv("HOME"); } }\n',
         ('class A { void f(String k) { System.getenv(); System.getenv(k); } }\n',)),
    _row('kotlin', Call(receiver='System', name='getenv', string_arg=True), 'System.getenv',
         'fun f() {\n  System.getenv("HOME")\n}\n',
         ('fun f(k: String) {\n  System.getenv(k)\n}\n',)),
    _row('csharp', Call(receiver='Environment', name='GetEnvironmentVariable', string_arg=True),
         'Environment.GetEnvironmentVariable',
         'class A { void F() { Environment.GetEnvironmentVariable("HOME"); } }\n',
         ('class A { void F(string k) { Environment.GetEnvironmentVariable(k); } }\n',)),
    _row('rust', Call(receiver_endswith='env', name=('var', 'var_os'), string_arg=True), '{path}',
         'fn f() { std::env::var("HOME").ok(); }\n',
         ('fn f(k: &str) { std::env::var(k).ok(); std::env::args(); }\n',)),
)

TABLES = {_C: RULES}

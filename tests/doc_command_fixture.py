"""A project tree whose paths and names are the ones AGENT_HELP.md and the guides use (BACK-1365).

The documentation's examples name concrete targets -- ``reveal src/processor.py process_batch
--varflow results``, ``reveal 'git://.?author=John'``, ``reveal doc.md Installation`` -- that
no placeholder map can stand in for: the element, heading, frontmatter field or commit has to
exist. This builds those targets under the names the docs use, so the executable-docs gate runs
each command literally as written instead of skipping it.

``FILES`` is the manifest (relative path -> content); ``named_paths()`` is what the gate checks
a command's target against, so a command only runs when every path it names exists here. The
tree is a git repository with the history the git:// and review examples filter on (authors,
messages, dates, tags, a ``main`` branch and a checked-out ``feature`` branch ahead of it).
"""

import json
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path, PurePosixPath


def _pad(prefix, count, indent='    '):
    """``count`` distinct, analyzable statements (a long body with real assignments)."""
    return ''.join(f'{indent}{prefix}_{i} = {prefix}_{i - 1} + {i}\n' if i else f'{indent}{prefix}_0 = 0\n'
                   for i in range(count))


def _branchy(name, branches, args='x'):
    """A function whose cyclomatic complexity is about ``branches``."""
    body = ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(branches))
    return f'def {name}({args}):\n{body}    return -1\n'


# process_batch spans lines 5-86 so the documented line ranges (7-12, 20-80) fall inside it.
_PROCESS_BATCH = (
    'def process_batch(items, config):\n'
    '    """Transform each item; skip the ones that fail."""\n'
    '    results = []\n'
    '    for value in items:\n'
    '        result = transform(value)\n'
    '        if result is None:\n'
    '            continue\n'
    '        results.append(result)\n'
    '    try:\n'
    '        limit = config["limit"]\n'
    '    except KeyError:\n'
    '        limit = len(results)\n'
    '    batch = results[:limit]\n'
    '    total = 0\n'
    + ''.join(f'    total += len(batch) * {i}\n' for i in range(62))
    + '    if total < 0:\n'
    '        raise ValueError("negative total")\n'
    '    results = [r for r in batch if r]\n'
    '    return results\n'
)

_APP_PY = (
    'import functools\n'
    'import os\n'
    'import requests\n'
    '\n'
    + _PROCESS_BATCH
    + '\n\n'
    'def transform(value):\n'
    '    return value * 2 if value else None\n'
    '\n\n'
    'def process_order(order, db):\n'
    '    if not order:\n'
    '        return None\n'
    '    db.save(order)\n'
    '    requests.post("https://example.invalid/orders", json=order)\n'
    '    print("order saved")\n'
    '    return order["id"]\n'
    '\n\n'
    'def process_request(request):\n'
    '    response = {"status": 200}\n'
    '    response["body"] = handle_request(request)\n'
    '    return response\n'
    '\n\n'
    'def handle_request(request):\n'
    '    data = process_data(request)\n'
    '    return process_order(data, None)\n'
    '\n\n'
    'def process_data(request):\n'
    '    return dict(request)\n'
    '\n\n'
    '@functools.lru_cache(maxsize=32)\n'
    'def cached_lookup(key):\n'
    '    return os.environ.get(key)\n'
    '\n\n'
    'def myfunc(path):\n'
    '    with open(path, "w", encoding="utf-8") as f:\n'
    '        f.write("x")\n'
    '\n\n'
    'def _private_function():\n'
    '    return 1\n'
    '\n\n'
    'def load_config(path):\n'
    '    with open(path, encoding="utf-8") as f:\n'
    '        return f.read()\n'
    '\n\n'
    'def handle_upload(request):\n'
    '    return request\n'
    '\n\n'
    'class DatabaseHandler:\n'
    '    def connect(self, url):\n'
    '        self.url = url\n'
    '        return url\n'
    '\n\n'
    'class MyClass:\n'
    '    def process(self, items):\n'
    '        result = []\n'
    '        for item in items:\n'
    '            if item:\n'
    '                result.append(item)\n'
    '        return result\n'
    '\n\n'
    'class Outer:\n'
    '    class Inner:\n'
    '        def method(self):\n'
    '            return 1\n'
    '\n\n'
    'def main():\n'
    '    return process_batch([1, 2, 3], {"limit": 2})\n'
)

# file.py: >340 lines; function_name starts near the top so `--calls 1-50` covers it.
_FILE_PY = (
    'import requests\n'
    '\n\n'
    'def function_name(x):\n'
    '    x = x + 1\n'
    '    data = requests.get("https://example.invalid", timeout=5)\n'
    '    x = x * 2\n'
    '    return x, data\n'
    '\n\n'
    'CONFIG = {"timeout": 5, "retries": 3}\n'
    'LIVE_SIGNALS = ["trade", "quote"]\n'
    '\n\n'
    'def normalize(config):\n'
    '    timeout = config["timeout"]\n'
    '    retries = config.get("retries")\n'
    '    return timeout, retries\n'
    '\n\n'
    'def process_batch(items):\n'
    '    out = []\n'
    '    for item in items:\n'
    '        out.append(normalize(item))\n'
    '        requests.post("https://example.invalid", json=item, timeout=5)\n'
    '    return out\n'
    '\n\n'
    'class Store:\n'
    '    def process_order(self, order):\n'
    '        self.last_order = order\n'
    '        self.count = getattr(self, "count", 0) + 1\n'
    '        return order\n'
    '\n\n'
    'def process_request(request):\n'
    '    return function_name(request)\n'
    '\n\n'
    'def get_repository(name):\n'
    '    return name\n'
    '\n\n'
    'def open_connection(url):\n'
    '    return url\n'
    '\n\n'
    'def upload_handler(request):\n'
    '    return escape(request)\n'
    '\n\n'
    'def escape(text):\n'
    '    return str(text).replace("<", "&lt;")\n'
    '\n\n'
    'def test_normalize():\n'
    '    assert normalize(CONFIG)\n'
    '\n\n'
    + _branchy('authenticate', 14, 'x')
    + '\n\n'
    + 'def authenticate_long(x):\n' + _pad('auth', 60)
    + ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(12)) + '    return auth_59\n'
    + '\n\n'
    + 'def long_function(x):\n' + _pad('step', 180) + '    return step_179\n'
)

_PROCESSOR_PY = (
    'from .validators import validate_item\n'
    '\n\n'
    '# process_batch spans the documented ranges 7-12 and 20-80.\n'
    + _PROCESS_BATCH.replace('result = transform(value)', 'result = validate_item(value)')
    + '\n\n'
    'def process_request(request):\n'
    '    return validate_item(request)\n'
    + '\n\n' + 'def long_simple(x):\n' + _pad('v', 110) + '    return v_109\n'
)

_AUTH_PY = (
    'from typing import List, Optional\n'
    '\n'
    'from .validators import validate_item\n'
    '\n\n'
    'def authenticate_user(user: str, password: str) -> bool:\n'
    '    """Check a password."""\n'
    '    validate_item(user)\n'
    '    return bool(password)\n'
    '\n\n'
    'def validate_token(token: str) -> Optional[str]:\n'
    '    validate_item(token)\n'
    '    if not token:\n'
    '        return None\n'
    '    return token\n'
    '\n\n'
    'def login(user: str, tokens: List[str]) -> bool:\n'
    '    return any(validate_token(t) for t in tokens)\n'
    '\n\n'
    'def process(item):\n'
    '    return validate_item(item)\n'
    '\n\n'
    'def send_email(to, body):\n'
    '    return (to, body)\n'
    '\n\n'
    'def notify(user):\n'
    '    return send_email(user, "hi")\n'
    '\n\n'
    + '# padding so MyClass.validate spans the documented range 45-70\n' * 4
    + 'class MyClass:\n'
    '    def validate(self, token):\n'
    + _pad('check', 30, '        ') + '        return validate_token(token)\n'
    + '\n\n'
    + 'def process_payment(amount: int) -> bool:\n' + _pad('fee', 60) + '    return amount > 0\n'
    + '\n\n'
    + 'def refresh(token):\n' + _pad('r', 40) + '    return validate_token(token)\n'
)

_SRC_APP_PY = (
    'from .auth import authenticate_user\n'
    'from .validators import validate_item\n'
    '\n\n'
    'def create_app(config):\n'
    '    validate_item(config)\n'
    '    return {"config": config}\n'
    '\n\n'
    'def handle_request(request):\n'
    '    if authenticate_user(request.get("user"), request.get("password")):\n'
    '        return process(request)\n'
    '    return None\n'
    '\n\n'
    'def process(request):\n'
    '    return validate_item(request)\n'
    '\n\n'
    'def main():\n'
    '    return handle_request({})\n'
    '\n\n'
    + 'def build_routes(app):\n' + _pad('route', 150) + '    return route_149\n'
)

_VALIDATORS_PY = (
    'def validate_item(item):\n'
    '    """Every caller funnels through here (callers>5)."""\n'
    '    if item is None:\n'
    '        raise ValueError("missing item")\n'
    '    return item\n'
    '\n\n'
    'def parse_config(text):\n'
    '    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)\n'
    '\n\n'
    'def match_pattern(pattern, text):\n'
    '    return pattern in text\n'
)

_HOTSPOT_PY = (
    'from .validators import validate_item\n'
    '\n\n'
    + _branchy('complex_function', 24)
    + '\n\n'
    + 'def huge_complex(x):\n' + _pad('h', 140)
    + ''.join(f'    if x == {i}:\n        return {i}\n' for i in range(32)) + '    return validate_item(h_139)\n'
)

_HANDLERS_PY = (
    'import logging\n'
    'from dataclasses import dataclass\n'
    'from abc import ABC, abstractmethod\n'
    '\n\n'
    'def error_handler(exc):\n'
    '    logging.error("failed: %s", exc)\n'
    '    return {"error": str(exc)}\n'
    '\n\n'
    'def exception_handler(exc):\n'
    '    return error_handler(exc)\n'
    '\n\n'
    '@dataclass\n'
    'class Event:\n'
    '    name: str\n'
    '\n\n'
    'class Handler(ABC):\n'
    '    @abstractmethod\n'
    '    def handle(self, event):\n'
    '        pass\n'
    '\n'
    '    @property\n'
    '    def name(self):\n'
    '        return type(self).__name__\n'
    '\n'
    '    @staticmethod\n'
    '    def create():\n'
    '        return None\n'
    '\n\n'
    'async def handle_async(event):\n'
    '    return event\n'
    '\n\n'
    'def read_settings(settings):\n'
    '    return settings["host"], settings["port"], settings.get("debug")\n'
)

_MAIN_PY = (
    'import json\n'
    '\n'
    'from .processor import process_batch\n'
    'from .validators import validate_item\n'
    '\n\n'
    'def load_config(path):\n'
    '    with open(path, encoding="utf-8") as f:\n'
    '        return json.load(f)\n'
    '\n\n'
    'def process_request(request):\n'
    '    validate_item(request)\n'
    '    if request:\n'
    '        return process_batch(request, {"limit": 1})\n'
    '    return None\n'
    '\n\n'
    'def process_order(order):\n'
    '    validate_item(order)\n'
    '    return process_request(order)\n'
    '\n\n'
    'def main():\n'
    '    return process_request(load_config("config.json"))\n'
)

_DOC_MD = '''---
title: Fixture document
type: guide
status: draft
related:
  - docs/guide.md
---
# Fixture document

Search terms: BACK-308, EX-12h, config, search-term, social_repost_log.

## Installation

Install with `pip install reveal-cli` and see [the guide](docs/guide.md).

```python
def install():
    return True
```

## Breaking Changes

Nothing broke; see [missing](docs/missing.md) and [example](https://example.com).

## Migration Guide

Run the migration.

## Open Issues

- Bug 11: social_repost_log grows without bound

## Action Items

- Rotate the config.
'''

_README_MD = '''---
title: Fixture readme
type: session
---
# Fixture project

See [the guide](docs/guide.md) and [example.com](https://example.com).

## Install

```python
import reveal
```

```bash
pip install reveal-cli
```
'''


def _doc(title, body, **meta):
    front = ''.join(f'{k}: {json.dumps(v)}\n' for k, v in meta.items())
    return f'---\ntitle: {json.dumps(title)}\n{front}---\n# {title}\n\n{body}\n'


_DOCS = {
    'docs/guide.md': _doc('API guide', 'Deploy nginx with ssl. See [auth](auth.md) and [setup](setup.md).\n'
                          'Uses an auth token for deployment.', type='guide', status='draft',
                          priority=7, tags=['python', 'api'], beth_topics=['deployment'],
                          created='2026-01-10', updated='2026-01-20', published=False),
    'docs/auth.md': _doc('Authentication', 'Authentication with oauth and a token. Retry on failure.',
                         type='procedure', status='complete', priority=3, tags=['api', 'python'],
                         topics=['authentication'], beth_topics=['authentication'],
                         created='2026-01-05', updated='2026-02-01', published=True),
    'docs/setup.md': _doc('Setup', 'Install, then read [the guide](guide.md) and [auth](auth.md).',
                          type='guide', status='archived', priority=1, tags=['setup'],
                          updated='2024-06-01'),
    'docs/page.md': _doc('Page', 'A page with nginx notes.', type='reference', status='draft'),
    'docs/api/reference.md': _doc('API reference', 'Endpoints. See [guide](../guide.md).',
                                  type='reference', status='complete'),
    'docs/guides/auth.md': _doc('Auth guide', 'Token auth. See [auth](../auth.md).', type='guide'),
}

_DATA_ROWS = [
    {'name': 'john', 'age': 34, 'role': 'admin', 'status': 'active', 'score': 88, 'count': 120,
     'type': 'user'},
    {'name': 'johnny', 'age': 29, 'role': 'user', 'status': 'draft', 'score': 91, 'count': 40,
     'type': 'user'},
    {'name': 'amy', 'age': 41, 'role': 'admin', 'status': 'active', 'score': 70, 'count': 300,
     'type': 'service'},
]

_JSON = {
    # A root array: the filter examples (?age>25, ?status=active) filter its rows.
    'data.json': _DATA_ROWS,
    'config.json': {'database': {'host': 'db.local', 'password': 'x'},
                    'services': {'api': {'url': 'https://example.invalid'}}},
    'users.json': [dict(r, last_login=f'2026-01-0{i}', id=i, email=f'{r["name"]}@example.com')
                   for i, r in enumerate(_DATA_ROWS, 1)],
    'package.json': {'name': 'fixture', 'scripts': {'test': 'pytest'},
                     'dependencies': {'left-pad': '1.0.0'}},
    'tsconfig.json': {'compilerOptions': {'strict': True}},
    'api-response.json': {'data': [{'id': 1}, {'id': 2}]},
    'logs.json': [{'level': 'error', 'message': 'boom'}, {'level': 'info', 'message': 'ok'}],
    'customers.json': [{'name': 'big', 'lifetime_value': 20000}, {'name': 'small', 'lifetime_value': 10}],
    'orders.json': [{'total': 150, 'date': '2026-02-01'}, {'total': 50, 'date': '2026-03-01'}],
    'large-config.json': {'api': {'key': 'k', 'secret_key': 's'}},
    'config.dev.json': {'debug': True, 'port': 8000},
    'config.prod.json': {'debug': False, 'port': 80},
}

_PHP_BLOCK = '''if ($row['id'] > {i}) {{
    $userId = $row['user_id'];
    $errormsg = "failed {i}";
    $result = mysql_query("SELECT * FROM t WHERE id = " . $userId);
    foreach ($rows as $row) {{
        $this->total += $row['amount'];
    }}
}} else {{
    return $errormsg;
}}
'''


def _php(lines):
    """Flat procedural PHP with at least ``lines`` lines (the docs' line ranges run to 3663)."""
    body, i = '<?php\n$rows = array();\n$row = array();\n', 0
    while body.count('\n') < lines:
        body += _PHP_BLOCK.format(i=i)
        i += 1
    return body + 'function handleRequest($req) {\n    return $req;\n}\n'


FILES = {
    'app.py': _APP_PY,
    'file.py': _FILE_PY + '\n'.join(f'# trailing line {i}' for i in range(60)) + '\n',
    'huge_file.py': 'def target_function(x):\n' + _pad('t', 80) + '    return t_79\n\n\n'
                    + 'def other(x):\n' + _pad('o', 80) + '    return o_79\n',
    'large_module.py': 'def a():\n    return 1\n\n\ndef b():\n    return 2\n',
    'models.py': 'class User:\n    name = "x"\n\n\nclass Order:\n    total = 0\n',
    'script.py': 'import sys\n\n\ndef main():\n    return sys.argv\n',
    'file1.py': 'def f():\n    return 1\n',
    'file2.py': 'def f():\n    return 2\n',
    'file_a.py': 'def f():\n    return 1\n',
    'file_b.py': 'def f():\n    return 2\n\n\ndef g():\n    return 3\n',
    'v1.py': 'def api():\n    return 1\n',
    'v2.py': 'def api():\n    return 2\n',
    'backup/app.py': _APP_PY.replace('return 1\n', 'return 0\n', 1),
    'src/__init__.py': '',
    'src/app.py': _SRC_APP_PY,
    'src/auth.py': _AUTH_PY,
    'src/auth/__init__.py': '',
    'src/auth/handler.py': 'from ..validators import validate_item\n\n\n'
                           'def authenticate_user(user):\n    return validate_item(user)\n',
    'src/auth/tokens.py': 'from .handler import authenticate_user\n\n\n'
                          'def issue(user):\n    return authenticate_user(user)\n',
    'src/processor.py': _PROCESSOR_PY,
    'src/main.py': _MAIN_PY,
    'src/module.py': 'from .validators import validate_item\n\n\n'
                     'def function_name(x):\n    print(x)\n    return validate_item(x)\n',
    'src/module_a.py': 'from . import module_b\n\n\ndef a():\n    return module_b.b()\n',
    'src/module_b.py': 'from . import module_a\n\n\ndef b():\n    return module_a\n',
    'src/hotspot.py': _HOTSPOT_PY,
    'src/handlers.py': _HANDLERS_PY,
    'src/validators.py': _VALIDATORS_PY,
    'src/changed_file.py': 'def changed_function(x):\n    return x\n',
    'src/insecure.py': 'import subprocess\n\n\ndef bad_function(cmd):\n'
                       '    return subprocess.call(cmd, shell=True)\n',
    'src/problematic_file.py': 'def broken(x):\n    return eval(x)\n',
    'src/utils.py': 'import os\nimport sys\n\n\ndef cwd():\n    return os.getcwd()\n',
    'src/file.py': 'from .validators import validate_item\n\n\ndef fn(x):\n    return validate_item(x)\n',
    'src/models/__init__.py': '',
    'src/models/user.py': 'from ..validators import validate_item\n\n\nclass User:\n'
                          '    def check(self):\n        return validate_item(self)\n',
    'src/services/__init__.py': '',
    'src/services/base.py': 'from abc import ABC, abstractmethod\n\n\nclass Service(ABC):\n'
                            '    @abstractmethod\n    def run(self):\n        pass\n',
    'src/jobs/__init__.py': '',
    'src/jobs/runner.py': 'from ..main import main\n\n\ndef run():\n    return main()\n',
    'tests/test_app.py': 'from src.app import create_app\n\n\ndef test_create_app():\n'
                         '    assert create_app({})\n\n\ndef test_handle():\n    assert True\n',
    'integration_tests/test_flow.py': 'def test_flow():\n    assert True\n',
    'deep_dir/a/b/c/target_module.py': 'def target_one():\n    return 1\n',
    'deep_dir/a/notes.md': '# Notes\n',
    'huge_dir/one.py': 'def one():\n    return 1\n',
    'huge_dir/two.py': 'def two():\n    return 2\n',
    'large_dir/one.py': 'def one():\n    return 1\n',
    'project/app.py': 'def run():\n    return 1\n',
    'project/README.md': '# Project\n',
    'doc.md': _DOC_MD,
    'README.md': _README_MD,
    'note.md': '---\ntitle: Note\ntags: [idea]\n---\n# Note\n\nAn obsidian note.\n',
    'post.md': '---\ntitle: Post\ndate: 2026-01-03\ndraft: false\n---\n# Post\n',
    '_posts/2026-01-03-my-post.md': '---\nlayout: post\ntitle: My post\n---\n# My post\n',
    'content/posts/article.md': '---\ntitle: Article\ndate: 2026-01-03\n---\n# Article\n',
    'vault/notes/project.md': '---\ntags: [project]\n---\n# Project\n',
    'sessions/demo-0101/README.md': '---\nsession_id: demo-0101\n---\n# Session\n',
    **_DOCS,
    **{name: json.dumps(value, indent=2) + '\n' for name, value in _JSON.items()},
    'config.yaml': 'server:\n  port: 8000\n  debug: true\n',
    'config_new.yaml': 'server:\n  port: 9000\n  debug: false\n',
    'pyproject.toml': '[project]\nname = "fixture"\n\n[tool.poetry]\nname = "fixture"\nversion = "0.1.0"\n',
    'setup.cfg': '[metadata]\nname = fixture\nversion = 0.1.0\n',
    'pom.xml': '<project>\n  <dependencies>\n    <dependency><artifactId>junit</artifactId></dependency>\n'
               '  </dependencies>\n</project>\n',
    'Dockerfile': 'FROM python:3.12\nRUN pip install reveal-cli\nCMD ["reveal"]\n',
    'main.go': 'package main\n\nfunc main() {\n}\n',
    'lib.rs': 'struct Foo;\n\nimpl Foo {\n    fn bar(&self) -> i32 {\n        1\n    }\n}\n',
    'Main.java': 'public class Main {\n    public static void main(String[] args) {\n    }\n}\n',
    'app.rb': 'class App\n  def run\n    1\n  end\nend\n',
    'script.lua': 'local function greet(name)\n  return "hi " .. name\nend\n',
    'io.cpp': 'class FileAccess {\npublic:\n    int get_bytes(char *buf, int len) {\n'
              '        return len;\n    }\n};\n',
    'main.tf': 'resource "aws_instance" "web" {\n  ami = "ami-123"\n}\n',
    'api.proto': 'syntax = "proto3";\n\nmessage User {\n  string name = 1;\n}\n',
    'file.ts': 'export function handler(payload: any) {\n  return payload.id + payload.name;\n}\n',
    'analysis.ipynb': json.dumps({'cells': [{'cell_type': 'code', 'source': ['import pandas\n'],
                                             'metadata': {}, 'outputs': [], 'execution_count': 1}],
                                  'metadata': {'language_info': {'name': 'python'}},
                                  'nbformat': 4, 'nbformat_minor': 5}),
    'conversation.jsonl': ''.join(json.dumps({'type': 'user', 'n': i, 'text': f'message {i}'}) + '\n'
                                  for i in range(60)),
    'log.jsonl': ''.join(json.dumps({'type': t, 'msg': 'x'}) + '\n' for t in ('user', 'assistant', 'user')),
    'service.log': 'INFO start\nERROR failed to connect\nINFO stop\n',
    'file.txt': 'all good\nerror: disk full\n',
    'file.php': _php(820),
    'flat_file.php': _php(3700),
    'rr_body.php': _php(2210),
    'legacy_handler.php': _php(2140),
    '.gitignore': 'home/\n',
}

# Commits after the initial one: (author, email, date, message, path, appended text). The
# authors, messages and dates are the ones the git:// examples filter on.
_HISTORY = (
    ('Alice', 'alice@company.com', '2026-01-12', 'feat: add token validation', 'src/auth.py',
     '\n\nCURLOPT_TIMEOUT = 30\n'),
    ('jane', 'jane@example.com', '2026-01-20', 'fix bug in parser', 'app.py',
     '\n\ndef parse_input(text):\n    return text.split()\n'),
    ('John', 'john@example.com', '2026-02-03', 'bug fix: empty batch', 'src/app.py',
     '\n\ndef empty_batch():\n    return []\n'),
    ('Jaydeep', 'jaydeep@company.com', '2026-02-10', 'feat: SmLogs logging', 'src/auth.py',
     '\n\nSmLogs = []\n'),
    ('Alice', 'alice@company.com', '2026-02-15', 'docs: update guide', 'docs/guide.md',
     '\nMore deployment notes.\n'),
    ('John', 'john@example.com', '2026-02-20', 'refactor processor', 'src/processor.py',
     '\n\ndef flush():\n    return None\n'),
    ('jane', 'jane@example.com', '2026-03-02', 'feat: config loader', 'src/main.py',
     '\n\ndef reload():\n    return None\n'),
    ('John', 'john@example.com', '2026-03-15', 'fix: hotspot bug', 'src/hotspot.py',
     '\n\ndef cool():\n    return None\n'),
    ('Alice', 'alice@company.com', '2026-04-10', 'feat: payment retries', 'src/auth.py',
     '\n\nRETRIES = 3\n'),
    ('John', 'john@example.com', '2026-04-20', 'docs: readme', 'docs/auth.md', '\nOAuth notes.\n'),
    ('John', 'john@example.com', '2026-04-25', 'bug fix: module', 'src/module.py',
     '\n\ndef module_fix():\n    return None\n'),
)
# Commits on the checked-out `feature` branch, ahead of `main`.
_FEATURE = (
    ('jane', 'jane@example.com', '2026-05-01', 'feat: faster hotspot', 'src/hotspot.py',
     '\n\ndef faster():\n    return None\n'),
    ('jane', 'jane@example.com', '2026-05-02', 'fix: auth edge case', 'src/auth.py',
     '\n\ndef edge(x):\n    if x:\n        return 1\n    return 0\n'),
)
TAGS = {'v0.63.0': 2, 'v1.2.0': 8}  # tag -> index into _HISTORY (after that commit)
BRANCHES = ('main', 'feature', 'feat', 'feature-branch')
GIT_COMMITS = 1 + len(_HISTORY) + len(_FEATURE)


def named_paths():
    """Every file and directory the tree has, as POSIX relative paths ('.' included)."""
    paths = {'.'}
    for name in FILES:
        path = PurePosixPath(name)
        paths.add(str(path))
        paths.update(str(p) for p in path.parents if str(p) != '.')
    return paths


def _write_binary_fixtures(root):
    for name in ('app.db', 'db.sqlite3', 'dev.db', 'prod.db'):
        conn = sqlite3.connect(str(root / name))
        conn.execute('CREATE TABLE users (id INTEGER PRIMARY KEY, name TEXT)')
        conn.execute('CREATE TABLE trades (id INTEGER PRIMARY KEY, symbol TEXT)')
        if name == 'prod.db':
            conn.execute('CREATE TABLE audit (id INTEGER PRIMARY KEY)')
        conn.commit()
        conn.close()
    try:
        import openpyxl
    except ImportError:
        return
    for name in ('model.xlsx', 'file.xlsx'):
        wb = openpyxl.Workbook()
        wb.active.title = 'Sales'
        wb.active.append(['region', 'revenue'])
        wb.active.append(['west', 100])
        budget = wb.create_sheet('Budget')
        budget.append(['item', 'cost', 'total'])
        budget.append(['x', 5, '=B2*2'])
        wb.create_sheet('Summary').append(['error', 'pattern'])
        wb.save(str(root / name))


def binary_paths():
    """The binary fixtures (written separately from FILES); xlsx only with openpyxl."""
    paths = {'app.db', 'db.sqlite3', 'dev.db', 'prod.db'}
    try:
        import openpyxl  # noqa: F401
        paths |= {'model.xlsx', 'file.xlsx'}
    except ImportError:
        pass
    return paths


# Recorded sessions under the names the docs use, beyond tests/claude_session_fixture.py's own.
CLAUDE_SESSIONS = ('my-session-name', 'my-session-0302')


def build_session_extras(home: Path) -> None:
    """The plan, Codex prompt history and Codex memory pipeline the docs' examples name."""
    (home / '.claude' / 'plans' / 'my-plan-name.md').write_text(
        '# My plan\n\nShip the token check.\n', encoding='utf-8')
    codex = home / '.codex'
    (codex / 'history.jsonl').write_text(''.join(
        json.dumps({'session_id': '019e5cc5', 'ts': 1774692000 + i, 'text': text}) + '\n'
        for i, text in enumerate(('refactor auth', 'run the tests'))), encoding='utf-8')
    conn = sqlite3.connect(str(codex / 'memories_1.sqlite'))
    conn.execute('CREATE TABLE stage1_outputs (thread_id TEXT, rollout_slug TEXT, generated_at TEXT, '
                 'selected_for_phase2 INTEGER, usage_count INTEGER, last_usage TEXT, '
                 'source_updated_at TEXT)')
    conn.execute("INSERT INTO stage1_outputs VALUES ('019e5cc5', 'auth-refactor', '2026-05-24', 1, 2, "
                 "'2026-05-25', '2026-05-24')")
    conn.commit()
    conn.close()


def _git(root, *cmd, author=('John', 'john@example.com'), date='2026-01-05'):
    name, email = author
    stamp = f'{date}T12:00:00'
    env = dict(os.environ, GIT_AUTHOR_NAME=name, GIT_AUTHOR_EMAIL=email, GIT_COMMITTER_NAME=name,
               GIT_COMMITTER_EMAIL=email, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
    subprocess.run(['git', '-C', str(root), *cmd], check=True, capture_output=True, env=env,
                   timeout=60)


def _commit(root, author, email, date, message, path, text):
    with open(root / path, 'a', encoding='utf-8') as f:
        f.write(text)
    _git(root, 'commit', '-q', '-am', message, author=(author, email), date=date)


def build_doc_command_tree(root: Path) -> Path:
    """Write ``FILES`` under ``root`` and, when git is installed, its history. Returns root."""
    for name, content in FILES.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding='utf-8')
    _write_binary_fixtures(root)
    if not shutil.which('git'):
        return root
    _git(root, 'init', '-q')
    _git(root, 'checkout', '-q', '-b', 'main')
    _git(root, 'add', '.')
    _git(root, 'commit', '-q', '-m', 'Initial commit')
    for index, (author, email, date, message, path, text) in enumerate(_HISTORY):
        _commit(root, author, email, date, message, path, text)
        for tag, at in TAGS.items():
            if at == index:
                _git(root, 'tag', tag)
    _git(root, 'checkout', '-q', '-b', 'feature')
    for author, email, date, message, path, text in _FEATURE:
        _commit(root, author, email, date, message, path, text)
    for branch in BRANCHES[2:]:
        _git(root, 'branch', branch)
    return root

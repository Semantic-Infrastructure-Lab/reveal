"""PHP function and class names are case-insensitive; surface name matching follows (BACK-1455).

`CURL_INIT()`, `Curl_Init()` and `new pdo()` are valid PHP. Case-sensitive languages must keep
matching exactly: a C++ macro `SYSTEM(..)` or a Go `exec.command(..)` is not the builtin.
"""

import pytest

from reveal.adapters.surface import _scan_surface

EXT = {'php': 'php', 'cpp': 'cpp', 'go': 'go'}


def _names(lang, code, category, tmp_path):
    path = tmp_path / f'sample.{EXT[lang]}'
    path.write_text(code, encoding='utf-8')
    return sorted(e['name'] for e in _scan_surface(path)['surfaces'][category])


@pytest.mark.parametrize('code, category, expected', [
    ('<?php\n$a = CURL_INIT();\n$b = Curl_Init();\n$c = \\Curl_Multi_Init();\n',
     'network', ['CURL_INIT', 'Curl_Init', 'Curl_Multi_Init']),
    ('<?php\n$a = Mysqli_Connect("h");\n$b = new pdo("dsn");\n$c = new \\SQLITE3("f");\n',
     'db', ['Mysqli_Connect', 'new SQLITE3', 'new pdo']),
    ('<?php\n$a = FOPEN("https://x/a", "r");\n$b = File_Get_Contents("http://x");\n',
     'network', ['File_Get_Contents', 'FOPEN']),
    ('<?php\n$a = SYSTEM("ls");\n$b = Shell_Exec("ls");\n', 'subprocess', ['SYSTEM', 'Shell_Exec']),
    ('<?php\nFile_Put_Contents("/tmp/x", "y");\n', 'fs', ['File_Put_Contents']),
], ids=['php-net-funcs', 'php-db', 'php-url-fopen', 'php-subprocess', 'php-fs-write'])
def test_php_builtins_match_in_any_case(code, category, expected, tmp_path):
    assert _names('php', code, category, tmp_path) == expected


def test_php_lookalike_names_still_do_not_match(tmp_path):
    code = '<?php\n$a = $c->CURL_INIT();\n$b = Http\\Curl_Init();\n$d = new PDOX("x");\n'
    assert _names('php', code, 'network', tmp_path) == []
    assert _names('php', code, 'db', tmp_path) == []


def test_case_sensitive_languages_keep_exact_matching(tmp_path):
    # C++ `system` / Go `exec.Command` differ from these only by case: a user symbol, not the API.
    assert _names('cpp', 'void f() { SYSTEM("ls"); System("ls"); }\n', 'subprocess', tmp_path) == []
    assert _names('cpp', 'void f() { system("ls"); }\n', 'subprocess', tmp_path) == ['system']
    go = 'package main\nimport "os/exec"\nfunc f() { exec.command("ls"); exec.COMMAND("ls") }\n'
    assert _names('go', go, 'subprocess', tmp_path) == []
    go_ok = 'package main\nimport "os/exec"\nfunc f() { exec.Command("ls") }\n'
    assert _names('go', go_ok, 'subprocess', tmp_path) == ['exec.Command']

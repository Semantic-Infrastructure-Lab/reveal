"""BACK-1090: surface:// I/O taxonomy for TypeScript, Kotlin, Java, C++ and PHP.

The scanners used to report nothing for network/filesystem/subprocess/database
I/O that these languages do through builtins, destructured imports or system
headers. Each test pins both what is found and what must NOT be (reads, non-IO
lookalikes), because over-matching is the failure mode of a name-based table.
"""

import pytest

from reveal.adapters.ast.nav_surface_cpp import scan_file_surface_cpp
from reveal.adapters.ast.nav_surface_java import scan_file_surface_java
from reveal.adapters.ast.nav_surface_kotlin import scan_file_surface_kotlin
from reveal.adapters.ast.nav_surface_php import scan_file_surface_php
from reveal.adapters.ast.nav_surface_ts import scan_file_surface_ts


def _scan(scanner, tmp_path, name, code):
    path = tmp_path / name
    path.write_text(code, encoding='utf-8')
    return scanner(str(path))


def _names(surfaces, category):
    return sorted(e['name'] for e in surfaces[category])


# ── TypeScript ──────────────────────────────────────────────────────────────

TS_CODE = '''import { writeFile as wf } from 'node:fs/promises';
import * as nfs from 'node:fs';
import cp, { spawn as sp } from 'child_process';
const { execSync } = require('child_process');
const fsx = require('fs');
export function run(re: RegExp) {
  wf('/tmp/a', 'x');
  nfs.promises.writeFile('/tmp/b', 'y');
  nfs.appendFileSync('/tmp/c', 'z');
  sp('ls'); cp.exec('ls'); execSync('ls');
  fsx.writeFileSync('/tmp/d', 'q');
  nfs.readFileSync('/tmp/r');
  re.exec('abc');
  other.writeFile('/tmp/n', 'not fs');
}
'''


def test_ts_destructured_aliased_and_promises_fs_writes(tmp_path):
    s = _scan(scan_file_surface_ts, tmp_path, 'a.ts', TS_CODE)
    assert _names(s, 'fs') == ['fs.appendFileSync', 'fs.writeFile', 'fs.writeFile', 'fs.writeFileSync']


def test_ts_child_process_through_bindings(tmp_path):
    s = _scan(scan_file_surface_ts, tmp_path, 'a.ts', TS_CODE)
    assert _names(s, 'subprocess') == ['child_process.exec', 'child_process.execSync', 'child_process.spawn']


def test_ts_unbound_lookalikes_are_ignored(tmp_path):
    # `re.exec` (RegExp) and `other.writeFile` are not built-in module calls.
    s = _scan(scan_file_surface_ts, tmp_path, 'a.ts',
              "export function f(re: RegExp) { re.exec('a'); other.writeFile('x', 'y'); spawn('ls'); }\n")
    assert s['fs'] == [] and s['subprocess'] == []


# ── Kotlin / Java ───────────────────────────────────────────────────────────

KOTLIN_CODE = '''import java.io.File
import java.net.URL
import java.net.URI
import java.nio.file.Files
fun run() {
    File("/tmp/a").writeText("x")
    File("/tmp/b").appendBytes(byteArrayOf())
    FileWriter("/tmp/c")
    Files.writeString(path, "x")
    val body = URL("https://api.example.com").readText()
    val text = File("/tmp/r").readText()
    list.write(1)
}
'''


def test_kotlin_jdk_network_imports(tmp_path):
    s = _scan(scan_file_surface_kotlin, tmp_path, 'a.kt', KOTLIN_CODE)
    assert _names(s, 'network') == ['java.net.URL']  # URI is not egress


def test_kotlin_fs_writes_not_reads(tmp_path):
    s = _scan(scan_file_surface_kotlin, tmp_path, 'a.kt', KOTLIN_CODE)
    assert _names(s, 'fs') == ['File.appendBytes', 'File.writeText', 'FileWriter()', 'Files.writeString']


def test_java_jdk_network_imports(tmp_path):
    s = _scan(scan_file_surface_java, tmp_path, 'A.java',
              'import java.net.URL;\nimport java.net.HttpURLConnection;\nimport java.net.URI;\nclass A {}\n')
    assert _names(s, 'network') == ['java.net.HttpURLConnection', 'java.net.URL']


# ── C++ ─────────────────────────────────────────────────────────────────────

def test_cpp_socket_headers_and_subprocess(tmp_path):
    s = _scan(scan_file_surface_cpp, tmp_path, 'a.cpp', '''#include <fstream>
#include <sys/socket.h>
#include <netinet/in.h>
#include <vector>
void run() { std::ofstream f("/tmp/a"); system("ls"); popen("ls", "r"); }
''')
    assert _names(s, 'network') == ['netinet/in.h', 'sys/socket.h']
    assert _names(s, 'subprocess') == ['popen', 'system']
    assert _names(s, 'fs') == ['std::ofstream']


# ── PHP ─────────────────────────────────────────────────────────────────────

PHP_CODE = '''<?php
function run() {
  $c = \\curl_init('https://api.example.com');
  file_put_contents('/tmp/a', 'x');
  $o = shell_exec('ls') . `date`;
  $pdo = new PDO('mysql:host=localhost');
  $f = fopen('/tmp/w', 'w');
  $r = fopen('/tmp/r', 'r');
  $out = fopen('php://output', 'w');
  $u = file_get_contents('https://x.io/api');
  $l = file_get_contents('/etc/hosts');
  $link = mysqli_connect('h', 'u', 'p');
  fwrite($f, 'x');
}
'''


def test_php_builtin_network_and_db(tmp_path):
    s = _scan(scan_file_surface_php, tmp_path, 'a.php', PHP_CODE)
    assert _names(s, 'network') == ['curl_init', 'file_get_contents']  # URL form only
    assert _names(s, 'db') == ['mysqli_connect', 'new PDO']


def test_php_builtin_fs_writes_exclude_reads_and_php_streams(tmp_path):
    s = _scan(scan_file_surface_php, tmp_path, 'a.php', PHP_CODE)
    assert _names(s, 'fs') == ['file_put_contents', 'fopen']
    assert [e['line'] for e in s['fs'] if e['name'] == 'fopen'] == [7]  # not the read, not php://output


def test_php_subprocess_functions_and_backticks(tmp_path):
    s = _scan(scan_file_surface_php, tmp_path, 'a.php', PHP_CODE)
    assert _names(s, 'subprocess') == ['`...`', 'shell_exec']


@pytest.mark.parametrize('code', ["<?php $x = $obj->exec('a'); $y = Foo::system('b'); file('/etc/passwd');"])
def test_php_methods_and_local_reads_are_not_io(tmp_path, code):
    s = _scan(scan_file_surface_php, tmp_path, 'b.php', code)
    assert all(s[k] == [] for k in ('network', 'db', 'fs', 'subprocess'))

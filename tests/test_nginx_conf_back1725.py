"""BACK-1725: the nginx grammar both readers share -- comments, quoted strings, blocks."""
from reveal.utils.nginx_conf import block_header, brace_delta, find_blocks, strip_comments

CONF = '''# server { not a server
server { listen 80; # listen 9999;
  location ~ "^/(a|b){2}$" { return 301 /x; }
  location /q { if ($a) { set $b "}"; } return 200; }
  add_header X "a # b";
}
'''


def test_strip_comments_keeps_lines_and_quoted_hash():
    out = strip_comments(CONF)
    assert out.count('\n') == CONF.count('\n')
    assert 'not a server' not in out and '9999' not in out
    assert '"a # b"' in out


def test_brace_delta_ignores_comments_and_quotes():
    assert brace_delta('location /q { if ($a) { set $b "}"; } return 200; }') == 0
    assert brace_delta('# server {') == 0
    assert brace_delta('server {') == 1


def test_block_header():
    assert block_header('# server {', 'server') is None
    assert block_header('server {', 'server') == ''
    assert block_header('location ~ "^/(a|b){2}$" { return 301 /x; }', 'location') == '~ "^/(a|b){2}$"'
    assert block_header('upstream_server {', 'server') is None


def test_find_blocks_nested_and_quoted():
    (_, body), = find_blocks(CONF, 'server')
    assert [h for h, _ in find_blocks(body, 'location')] == ['~ "^/(a|b){2}$"', '/q']
    assert len(find_blocks('server { a; } server { b; }', 'server')) == 2
    assert find_blocks('# server { a; }', 'server') == []

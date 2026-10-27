"""nginx_conf.line_statements / block_statements: directives by grammar, not by line start (BACK-2246)."""
from reveal.utils.nginx_conf import block_statements, line_statements


def test_line_statements_reads_inside_a_one_line_block():
    assert line_statements('location /x/ { root /srv/a; proxy_pass http://b; }') == [
        'root /srv/a', 'proxy_pass http://b']


def test_line_statements_plain_directive_and_controls():
    assert line_statements('    root /srv/a;') == ['root /srv/a']
    assert line_statements('location /x/ {') == []                 # a header is not a directive
    assert line_statements('    root /srv/a;  # root /srv/b;') == ['root /srv/a']
    assert line_statements('    return 200 "a;b";') == ['return 200 "a;b"']
    assert line_statements('    root /srv/a') == []                # not terminated on this line


def test_block_statements_one_line_block_stops_at_its_close():
    lines = ['location /a/ { root /srv/a; }', 'location /b/ { root /srv/b; }']
    assert list(block_statements(lines, 0)) == [(0, 1, 'root /srv/a')]


def test_block_statements_multi_line_with_depths():
    lines = ['server', '{', '  root /srv/s;', '  location /x/ { root /srv/x; }',
             '  if ($a) {', '    return 404;', '  }', '}', 'root /after;']
    assert list(block_statements(lines, 0)) == [
        (2, 1, 'root /srv/s'), (3, 2, 'root /srv/x'), (5, 2, 'return 404')]


def test_block_statements_empty_block_yields_nothing():
    assert list(block_statements(['location /x/ { }', 'root /srv/next;'], 0)) == []

"""nginx_conf.top_level_statements: the directives outside every block (BACK-2280)."""
from reveal.utils.nginx_conf import find_blocks, top_level_statements


def test_server_and_location_directives_are_not_top_level():
    body = find_blocks("""http {
    ssl_certificate_key /srv/k;
    server {
        ssl_certificate /srv/c;
        location / { root /srv/www; }
    }
    include ssl-common.conf;
}""", 'http')[0][1]
    assert top_level_statements(body) == ['ssl_certificate_key /srv/k', 'include ssl-common.conf']


def test_comments_and_quoted_braces_and_controls():
    assert top_level_statements('# server_tokens off;\nserver_tokens on;') == ['server_tokens on']
    assert top_level_statements('add_header X-Note "a } b";\nroot /srv/a;') == [
        'add_header X-Note "a } b"', 'root /srv/a']
    assert top_level_statements('map $a $b { default 1; }\nroot /srv/a;') == ['root /srv/a']
    assert top_level_statements('') == []
    assert top_level_statements('root /srv/a') == []     # not terminated

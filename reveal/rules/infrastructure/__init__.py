"""Infrastructure rules for nginx, terraform, etc.

Constants are defined here for shared use across rules.
"""

# Nginx configuration file patterns
# Used by N001, N002, N003 rules
NGINX_FILE_PATTERNS = ['.conf', '.nginx', 'nginx.conf']

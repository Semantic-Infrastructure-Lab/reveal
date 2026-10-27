"""SSL certificate adapter for reveal."""

# BACK-987: this module's name is also a top-level module's (stdlib or reveal itself). With cwd
# reveal/adapters on sys.path (python -m, or an empty PYTHONPATH entry) it is imported in that
# module's place, and its relative imports would fail with no hint of why.
if '.' not in __name__:
    raise ImportError(f"{__file__} was imported as the top-level module {__name__!r}: the current "
                      "directory is reveal/adapters and it is on sys.path (python -m, or an empty "
                      "PYTHONPATH entry); run reveal from another directory")

from .adapter import SSLAdapter, batch_check_from_nginx
from .certificate import SSLFetcher, CertificateInfo, check_ssl_health
from .renderer import SSLRenderer

__all__ = [
    'SSLAdapter',
    'SSLFetcher',
    'SSLRenderer',
    'CertificateInfo',
    'check_ssl_health',
    'batch_check_from_nginx',
]

"""Domain adapter for DNS, whois, and domain validation."""

from .adapter import DomainAdapter
from .renderer import DomainRenderer

__all__ = ['DomainAdapter', 'DomainRenderer']

"""Scaffolding commands for creating new adapters, analyzers, and rules."""

from .adapter import scaffold_adapter
from .analyzer import scaffold_analyzer
from .rule import scaffold_rule

__all__ = ['scaffold_adapter', 'scaffold_analyzer', 'scaffold_rule']

"""Reveal - Explore code semantically.

A clean, simple tool for progressive code exploration.
"""

# Import version from separate module to avoid circular dependencies
from .version import __version__

# Import base classes for external use
from .base import FileAnalyzer
from .registry import register, get_analyzer, get_all_analyzers
from .treesitter import TreeSitterAnalyzer

# Import all built-in analyzers to register them
from .analyzers import (  # noqa: F401
    PythonAnalyzer,
    RustAnalyzer,
    GoAnalyzer,
    CAnalyzer,
    CppAnalyzer,
    JavaAnalyzer,
    PhpAnalyzer,
    RubyAnalyzer,
    LuaAnalyzer,
    CSharpAnalyzer,
    ScalaAnalyzer,
    SQLAnalyzer,
    MarkdownAnalyzer,
    YamlAnalyzer,
    JsonAnalyzer,
    JsonlAnalyzer,
    GDScriptAnalyzer,
    JupyterAnalyzer,
    JavaScriptAnalyzer,
    TypeScriptAnalyzer,
    BashAnalyzer,
    NginxAnalyzer,
    TomlAnalyzer,
    DockerfileAnalyzer,
    HTMLAnalyzer,
    KotlinAnalyzer,
    SwiftAnalyzer,
    DartAnalyzer,
    HCLAnalyzer,
    GraphQLAnalyzer,
    ProtobufAnalyzer,
    ZigAnalyzer,
    CsvAnalyzer,
    IniAnalyzer,
    XmlAnalyzer,
    PowerShellAnalyzer,
    BatchAnalyzer,
    DocxAnalyzer,
    XlsxAnalyzer,
    PptxAnalyzer,
    OdtAnalyzer,
    OdsAnalyzer,
    OdpAnalyzer,
)

# Import type definitions to auto-register them in TypeRegistry
from .schemas import python  # noqa: F401

__all__ = [
    'FileAnalyzer',
    'TreeSitterAnalyzer',
    'register',
    'get_analyzer',
    'get_all_analyzers',
]

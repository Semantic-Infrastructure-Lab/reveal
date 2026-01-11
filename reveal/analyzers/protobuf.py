"""Protocol Buffers analyzer using tree-sitter."""
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.proto', name='Protocol Buffers', icon='📦')
class ProtobufAnalyzer(TreeSitterAnalyzer):
    """Protocol Buffers (protobuf) language analyzer.

    Supports Protocol Buffer definition files (.proto)
    used for gRPC and cross-language serialization.
    """
    language = 'proto'

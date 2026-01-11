"""C# analyzer using tree-sitter."""

from ..base import register
from ..treesitter import TreeSitterAnalyzer


@register('.cs', name='C#', icon='#️⃣')
class CSharpAnalyzer(TreeSitterAnalyzer):
    """Analyze C# source files.

    Extracts classes, interfaces, methods automatically using tree-sitter.
    """
    language = 'csharp'

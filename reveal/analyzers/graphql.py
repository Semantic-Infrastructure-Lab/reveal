"""GraphQL analyzer using tree-sitter."""
from ..registry import register
from ..treesitter import TreeSitterAnalyzer


@register('.graphql', '.gql', name='GraphQL', icon='🔷')
class GraphQLAnalyzer(TreeSitterAnalyzer):
    """GraphQL schema and query language analyzer.

    Supports GraphQL schema definitions (.graphql)
    and GraphQL query files (.gql).
    """
    language = 'graphql'

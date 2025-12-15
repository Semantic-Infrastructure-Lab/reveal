"""Python type definition for reveal.

Defines PythonType with containment rules for Python code elements:
- module contains classes, functions, imports
- class contains methods, attributes, nested classes
- function contains nested functions, variables

Auto-registers on import.
"""

from ..type_system import EntityDef, RevealType, TypeRegistry
from ..elements import PythonElement

# Python type definition
PythonType = RevealType(
    name="python",
    extensions=[".py", ".pyw", ".pyi"],
    scheme="py",
    entities={
        "module": EntityDef(
            contains=["class", "function", "import"],
            properties={"name": str, "line": int},
        ),
        "class": EntityDef(
            contains=["method", "function", "attribute", "class"],
            properties={"name": str, "line": int, "line_end": int, "bases": list, "decorators": list},
        ),
        "function": EntityDef(
            contains=["function", "variable"],
            properties={
                "name": str,
                "line": int,
                "line_end": int,
                "signature": str,
                "depth": int,
                "decorators": list,
            },
        ),
        "method": EntityDef(
            inherits="function",
            contains=["function", "variable"],
            properties={"decorators": list},
        ),
        "import": EntityDef(
            properties={"name": str, "line": int, "module": str},
        ),
        "attribute": EntityDef(
            properties={"name": str, "line": int, "value": str},
        ),
        "variable": EntityDef(
            properties={"name": str, "line": int},
        ),
    },
    adapters={
        "structure": "TreeSitterAnalyzer",
        "deep": "PythonDeepAdapter",
        "ast": "ASTQueryAdapter",
        "runtime": "PythonRuntimeAdapter",
    },
    element_class=PythonElement,
)

# Auto-register on import
TypeRegistry.register(PythonType)

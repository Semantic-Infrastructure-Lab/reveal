"""Help documentation for Python adapter."""

from typing import Dict, Any


def get_help() -> Dict[str, Any]:
    """Get help documentation for python:// adapter.

    Returns:
        Dict containing help information
    """
    return {
        "name": "python",
        "description": "Inspect Python runtime environment and debug common issues",
        "syntax": "python://[element]",
        "examples": [
            {"uri": "python://", "description": "Overview of Python environment"},
            {"uri": "python://version", "description": "Detailed Python version information"},
            {
                "uri": "python://env",
                "description": "Python's computed environment (sys.path, flags)",
            },
            {"uri": "python://venv", "description": "Virtual environment status and details"},
            {"uri": "python://packages", "description": "List all installed packages"},
            {
                "uri": "python://packages/reveal-cli",
                "description": "Details about a specific package",
            },
            {
                "uri": "python://imports",
                "description": "Currently loaded modules in sys.modules",
            },
            {
                "uri": "python://module/reveal",
                "description": "Analyze reveal module (pip vs import location)",
            },
            {
                "uri": "python://syspath",
                "description": "Analyze sys.path with conflict detection",
            },
            {"uri": "python://doctor", "description": "Run automated environment diagnostics"},
            {
                "uri": "python://debug/bytecode",
                "description": "Check for stale .pyc files and bytecode issues",
            },
            {"uri": "python:// --format=json", "description": "JSON output for scripting"},
        ],
        "elements": {
            "version": "Python version, implementation, and build details",
            "env": "Python environment configuration (sys.path, flags, encoding)",
            "venv": "Virtual environment detection and status",
            "packages": "List all installed packages (like pip list)",
            "packages/<name>": "Detailed information about a specific package",
            "module/<name>": "Module import analysis and conflict detection",
            "imports": "Currently loaded modules from sys.modules",
            "syspath": "sys.path analysis with CWD and conflict detection",
            "doctor": "Automated environment diagnostics and health check",
            "debug/bytecode": "Detect stale .pyc files and bytecode issues",
        },
        "features": [
            "Runtime environment inspection",
            "Virtual environment detection (venv, virtualenv, conda)",
            "Package listing and details",
            "Module conflict detection (CWD shadowing, pip vs import)",
            "sys.path analysis with priority classification",
            "Import tracking and analysis",
            "Automated environment diagnostics",
            "Bytecode debugging (stale .pyc detection)",
            "Editable install detection",
            "Cross-platform support (Linux, macOS, Windows)",
        ],
        "use_cases": [
            'Debug "my changes aren\'t working" (stale bytecode)',
            'Debug "wrong package version loading" (CWD shadowing)',
            "Verify virtual environment activation",
            "Check installed package versions",
            "Inspect sys.path and import configuration",
            "Find what modules are currently loaded",
            "Detect pip vs import location mismatches",
            "Pre-debug environment sanity check",
            "Automated health diagnostics",
        ],
        "separation_of_concerns": {
            "env://": "Raw environment variables (cross-language)",
            "ast://": "Static source code analysis (cross-language)",
            "python://": "Python runtime inspection (Python-specific)",
        },
        "try_now": [
            "reveal python://doctor",
            "reveal python://debug/bytecode",
            "reveal python://venv",
        ],
        "workflows": [
            {
                "name": "Debug 'My Changes Aren't Working'",
                "scenario": "You edited code but Python keeps running the old version",
                "steps": [
                    "reveal python://debug/bytecode     # Check for stale .pyc files",
                    "reveal python://module/mypackage   # Check import location",
                    "reveal python://syspath            # See import precedence",
                    "# If stale bytecode found:",
                    "find . -type d -name __pycache__ -exec rm -rf {} +",
                ],
            },
            {
                "name": "Debug 'Wrong Package Version'",
                "scenario": "pip shows v2.0 but code runs v1.0 behavior",
                "steps": [
                    "reveal python://module/package_name  # Compare pip vs import location",
                    "reveal python://syspath              # Check CWD shadowing",
                    "reveal python://venv                 # Verify venv is active",
                ],
            },
            {
                "name": "Environment Health Check",
                "scenario": "Setting up new machine or debugging weird behavior",
                "steps": [
                    "reveal python://doctor               # One-command diagnostics",
                    "reveal python://                     # Environment overview",
                    "reveal python://packages             # Installed packages",
                ],
            },
        ],
        "anti_patterns": [
            {
                "bad": "python -c \"import pkg; print(pkg.__file__)\"",
                "good": "reveal python://module/pkg",
                "why": "Structured output with conflict detection and recommendations",
            },
            {
                "bad": "pip show package && python -c \"import package; print(package.__version__)\"",
                "good": "reveal python://packages/package",
                "why": "Shows both pip metadata AND import location in one command",
            },
            {
                "bad": "echo $VIRTUAL_ENV && which python",
                "good": "reveal python://venv",
                "why": "Comprehensive venv detection including conda, poetry, etc.",
            },
        ],
        "notes": [
            "This adapter inspects the RUNTIME environment, not source code",
            "Use ast:// for static code analysis",
            "Use env:// for raw environment variables",
            "Bytecode checking requires filesystem access",
            "Package details require pkg_resources or importlib.metadata",
        ],
        "coming_soon": [
            "imports://src - Import dependency visualization (v0.27, separate adapter)",
            "imports://src?circular - Circular import detection (v0.27, separate adapter)",
        ],
        "see_also": [
            "reveal help://python-guide - Comprehensive guide with multi-shot examples",
            "reveal help://tricks - Power user workflows",
            "reveal ast:// - Static code analysis",
        ],
    }

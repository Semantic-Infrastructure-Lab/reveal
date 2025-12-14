"""Python runtime adapter (python://)."""

import sys
import platform
import os
from typing import Dict, Any, Optional

from ..base import ResourceAdapter, register_adapter
from .bytecode import check_bytecode, pyc_to_source
from .packages import get_packages, get_packages_list, get_package_details
from .modules import get_module_analysis, get_syspath_analysis
from .doctor import run_doctor
from .help import get_help


@register_adapter("python")
class PythonAdapter(ResourceAdapter):
    """Adapter for Python runtime inspection via python:// URIs."""

    def __init__(self):
        """Initialize with runtime introspection capabilities."""
        self._packages_cache = None
        self._imports_cache = None

    def get_structure(self, **kwargs) -> Dict[str, Any]:
        """Get overview of Python environment.

        Returns:
            Dict containing Python environment overview
        """
        venv_info = self._detect_venv()
        return {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "executable": sys.executable,
            "virtual_env": venv_info,
            "packages_count": len(list(get_packages())),
            "modules_loaded": len(sys.modules),
            "platform": sys.platform,
            "architecture": platform.machine(),
        }

    def get_element(self, element_name: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Get specific element within the Python runtime.

        Args:
            element_name: Element path (e.g., 'version', 'packages', 'debug/bytecode')

        Supported elements:
            - version: Python version details
            - env: Python environment configuration
            - venv: Virtual environment status
            - packages: All installed packages
            - packages/<name>: Specific package details
            - module/<name>: Module import location and conflicts
            - imports: Currently loaded modules
            - syspath: sys.path analysis with conflict detection
            - doctor: Auto-detect common environment issues
            - debug/bytecode: Bytecode issues
            - debug/syntax: Syntax errors (future)

        Returns:
            Dict containing element details, or None if not found
        """
        # Handle nested paths
        parts = element_name.split("/", 1)
        base = parts[0]

        # Route to handlers
        if base == "version":
            return self._get_version(**kwargs)
        elif base == "env":
            return self._get_env(**kwargs)
        elif base == "venv":
            return self._get_venv(**kwargs)
        elif base == "packages":
            if len(parts) > 1:
                return get_package_details(parts[1])
            return get_packages_list()
        elif base == "module":
            if len(parts) > 1:
                return get_module_analysis(parts[1])
            return {"error": "Specify module name: python://module/<name>"}
        elif base == "imports":
            if len(parts) > 1 and parts[1] == "graph":
                return {"error": "Import graph analysis coming in v0.18.0"}
            elif len(parts) > 1 and parts[1] == "circular":
                return {"error": "Circular import detection coming in v0.18.0"}
            return self._get_imports(**kwargs)
        elif base == "syspath":
            return get_syspath_analysis()
        elif base == "doctor":
            return run_doctor(self._detect_venv)
        elif base == "debug":
            if len(parts) > 1:
                return self._handle_debug(parts[1], **kwargs)
            return {"error": "Specify debug type: bytecode, syntax"}

        return None

    def _get_version(self, **kwargs) -> Dict[str, Any]:
        """Get detailed Python version information.

        Returns:
            Dict with version, implementation, build info, etc.
        """
        return {
            "version": platform.python_version(),
            "implementation": platform.python_implementation(),
            "compiler": platform.python_compiler(),
            "build_date": platform.python_build()[1],
            "build_number": platform.python_build()[0],
            "executable": sys.executable,
            "prefix": sys.prefix,
            "base_prefix": sys.base_prefix,
            "platform": sys.platform,
            "architecture": platform.machine(),
            "version_info": {
                "major": sys.version_info.major,
                "minor": sys.version_info.minor,
                "micro": sys.version_info.micro,
                "releaselevel": sys.version_info.releaselevel,
                "serial": sys.version_info.serial,
            },
        }

    def _detect_venv(self) -> Dict[str, Any]:
        """Detect if running in a virtual environment.

        Returns:
            Dict with virtual environment status and details
        """
        venv_path = os.getenv("VIRTUAL_ENV")
        if venv_path:
            return {"active": True, "path": venv_path, "type": "venv"}

        # Check if sys.prefix differs from sys.base_prefix
        if sys.prefix != sys.base_prefix:
            return {"active": True, "path": sys.prefix, "type": "venv"}

        # Check for conda
        conda_env = os.getenv("CONDA_DEFAULT_ENV")
        if conda_env:
            return {
                "active": True,
                "path": os.getenv("CONDA_PREFIX", ""),
                "type": "conda",
                "name": conda_env,
            }

        return {"active": False}

    def _get_venv(self, **kwargs) -> Dict[str, Any]:
        """Get detailed virtual environment information.

        Returns:
            Dict with virtual environment details
        """
        venv_info = self._detect_venv()

        if venv_info["active"]:
            venv_info.update(
                {
                    "python_version": platform.python_version(),
                    "prompt": os.path.basename(venv_info.get("path", "")),
                }
            )

        return venv_info

    def _get_env(self, **kwargs) -> Dict[str, Any]:
        """Get Python environment configuration.

        Returns:
            Dict with sys.path, flags, and environment details
        """
        return {
            "virtual_env": self._detect_venv(),
            "sys_path": list(sys.path),
            "sys_path_count": len(sys.path),
            "python_path": os.getenv("PYTHONPATH"),
            "flags": {
                "dont_write_bytecode": sys.dont_write_bytecode,
                "optimize": sys.flags.optimize,
                "verbose": sys.flags.verbose,
                "interactive": sys.flags.interactive,
                "debug": sys.flags.debug,
            },
            "encoding": {
                "filesystem": sys.getfilesystemencoding(),
                "default": sys.getdefaultencoding(),
            },
        }

    def _get_imports(self, **kwargs) -> Dict[str, Any]:
        """List currently loaded modules.

        Returns:
            Dict with loaded module information
        """
        modules = []

        for name, module in sys.modules.items():
            if module is None:
                continue

            module_info = {
                "name": name,
                "file": getattr(module, "__file__", None),
                "package": getattr(module, "__package__", None),
            }

            modules.append(module_info)

        return {"count": len(modules), "loaded": sorted(modules, key=lambda m: m["name"])}

    def _handle_debug(self, debug_type: str, **kwargs) -> Dict[str, Any]:
        """Handle debug/* endpoints.

        Args:
            debug_type: Type of debug check (bytecode, syntax, etc.)

        Returns:
            Dict with debug results
        """
        if debug_type == "bytecode":
            root_path = kwargs.get("root_path", ".")
            return check_bytecode(root_path)
        elif debug_type == "syntax":
            return {"error": "Syntax checking coming in v0.18.0"}

        return {"error": f"Unknown debug type: {debug_type}"}

    @staticmethod
    def _pyc_to_source(pyc_file):
        """Convert .pyc file path to corresponding .py file path.

        Backward compatibility wrapper for bytecode.pyc_to_source.
        """
        return pyc_to_source(pyc_file)

    @staticmethod
    def get_help() -> Dict[str, Any]:
        """Get help documentation for python:// adapter."""
        return get_help()

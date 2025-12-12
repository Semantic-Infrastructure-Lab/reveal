"""Python runtime adapter (python://)."""

import sys
import platform
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Iterator
from .base import ResourceAdapter, register_adapter


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
            "packages_count": len(list(self._get_packages())),
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
                return self._get_package_details(parts[1], **kwargs)
            return self._get_packages_list(**kwargs)
        elif base == "module":
            if len(parts) > 1:
                return self._get_module_analysis(parts[1], **kwargs)
            return {"error": "Specify module name: python://module/<name>"}
        elif base == "imports":
            if len(parts) > 1 and parts[1] == "graph":
                return {"error": "Import graph analysis coming in v0.18.0"}
            elif len(parts) > 1 and parts[1] == "circular":
                return {"error": "Circular import detection coming in v0.18.0"}
            return self._get_imports(**kwargs)
        elif base == "syspath":
            return self._get_syspath_analysis(**kwargs)
        elif base == "doctor":
            return self._run_doctor(**kwargs)
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

    def _get_packages(self) -> Iterator:
        """Generator for installed packages.

        Yields:
            Package distribution objects
        """
        try:
            # Try pkg_resources first (older but more compatible)
            import pkg_resources

            for dist in pkg_resources.working_set:
                yield dist
        except ImportError:
            # Fallback to importlib.metadata (Python 3.8+)
            try:
                import importlib.metadata

                for dist in importlib.metadata.distributions():
                    yield dist
            except ImportError:
                # No package metadata available
                pass

    def _get_packages_list(self, **kwargs) -> Dict[str, Any]:
        """List all installed packages.

        Returns:
            Dict with package count and list of packages
        """
        packages = []

        for dist in self._get_packages():
            try:
                # pkg_resources API
                packages.append(
                    {"name": dist.project_name, "version": dist.version, "location": dist.location}
                )
            except AttributeError:
                # importlib.metadata API
                try:
                    packages.append(
                        {
                            "name": dist.name,
                            "version": dist.version,
                            "location": str(dist._path.parent)
                            if hasattr(dist, "_path")
                            else "unknown",
                        }
                    )
                except Exception:
                    continue

        return {
            "count": len(packages),
            "packages": sorted(packages, key=lambda p: p["name"].lower()),
        }

    def _get_package_details(self, package_name: str, **kwargs) -> Dict[str, Any]:
        """Get detailed information about a specific package.

        Args:
            package_name: Name of the package

        Returns:
            Dict with package details or error
        """
        try:
            # Try pkg_resources first
            import pkg_resources

            dist = pkg_resources.get_distribution(package_name)

            details = {
                "name": dist.project_name,
                "version": dist.version,
                "location": dist.location,
                "requires_python": None,
                "dependencies": [],
            }

            # Get requirements
            try:
                details["dependencies"] = [str(req) for req in dist.requires()]
            except Exception:
                pass

            # Check if editable install
            try:
                details["editable"] = dist.has_metadata("direct_url.json")
            except Exception:
                details["editable"] = False

            return details

        except Exception:
            # Try importlib.metadata
            try:
                import importlib.metadata

                dist = importlib.metadata.distribution(package_name)

                metadata = dist.metadata

                return {
                    "name": metadata.get("Name"),
                    "version": metadata.get("Version"),
                    "summary": metadata.get("Summary"),
                    "author": metadata.get("Author"),
                    "license": metadata.get("License"),
                    "location": str(dist._path.parent) if hasattr(dist, "_path") else "unknown",
                    "requires_python": metadata.get("Requires-Python"),
                    "homepage": metadata.get("Home-page"),
                    "dependencies": dist.requires or [],
                }
            except Exception as e:
                return {"error": f"Package not found: {package_name}", "details": str(e)}

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
            return self._check_bytecode(root_path)
        elif debug_type == "syntax":
            return {"error": "Syntax checking coming in v0.18.0"}

        return {"error": f"Unknown debug type: {debug_type}"}

    # Directories to skip by default in bytecode checking
    # Note: Don't include __pycache__ here - that's where .pyc files live!
    BYTECODE_SKIP_DIRS = {
        '.cache', '.venv', 'venv', '.env', 'env',
        'node_modules', '.git',
        '.tox', '.nox', '.pytest_cache', '.mypy_cache',
        'site-packages', 'dist-packages',
        '.eggs', '*.egg-info',
    }

    def _check_bytecode(self, root_path: str = ".") -> Dict[str, Any]:
        """Check for bytecode issues (stale .pyc files, orphaned bytecode, etc.).

        Args:
            root_path: Root directory to scan

        Returns:
            Dict with issues found
        """
        issues = []
        root = Path(root_path)

        def should_skip(path: Path) -> bool:
            """Check if path should be skipped based on directory patterns."""
            parts = path.parts
            for part in parts:
                # Check exact matches
                if part in self.BYTECODE_SKIP_DIRS:
                    return True
                # Check wildcard patterns (e.g., *.egg-info)
                for pattern in self.BYTECODE_SKIP_DIRS:
                    if '*' in pattern:
                        from fnmatch import fnmatch
                        if fnmatch(part, pattern):
                            return True
            return False

        try:
            # Find all .pyc files
            for pyc_file in root.rglob("**/*.pyc"):
                # Skip directories that are typically not user code
                if should_skip(pyc_file):
                    continue

                # Skip if not in __pycache__ (old Python 2 style)
                if "__pycache__" not in pyc_file.parts:
                    issues.append(
                        {
                            "type": "old_style_pyc",
                            "severity": "info",
                            "file": str(pyc_file),
                            "problem": "Python 2 style .pyc file (should be in __pycache__)",
                            "fix": f"rm {pyc_file}",
                        }
                    )
                    continue

                # Get corresponding .py file
                py_file = self._pyc_to_source(pyc_file)

                if not py_file.exists():
                    issues.append(
                        {
                            "type": "orphaned_bytecode",
                            "severity": "info",
                            "pyc_file": str(pyc_file),
                            "problem": "No matching .py file found",
                            "fix": f"rm {pyc_file}",
                        }
                    )
                elif pyc_file.stat().st_mtime > py_file.stat().st_mtime:
                    issues.append(
                        {
                            "type": "stale_bytecode",
                            "severity": "warning",
                            "file": str(py_file),
                            "pyc_file": str(pyc_file),
                            "problem": ".pyc file is NEWER than source (stale bytecode)",
                            "source_mtime": py_file.stat().st_mtime,
                            "pyc_mtime": pyc_file.stat().st_mtime,
                            "fix": f"rm {pyc_file}",
                        }
                    )

        except Exception as e:
            return {"error": f"Failed to scan for bytecode issues: {str(e)}", "status": "error"}

        return {
            "status": "issues_found" if issues else "clean",
            "issues": issues,
            "summary": {
                "total": len(issues),
                "warnings": len([i for i in issues if i["severity"] == "warning"]),
                "info": len([i for i in issues if i["severity"] == "info"]),
                "errors": len([i for i in issues if i["severity"] == "error"]),
            },
        }

    @staticmethod
    def _pyc_to_source(pyc_file: Path) -> Path:
        """Convert .pyc file path to corresponding .py file path.

        Args:
            pyc_file: Path to .pyc file

        Returns:
            Path to corresponding .py file
        """
        # Example: __pycache__/module.cpython-310.pyc -> module.py
        if "__pycache__" in pyc_file.parts:
            parent = pyc_file.parent.parent
            # Remove cpython-XXX suffix and .pyc extension
            name = pyc_file.stem.split(".")[0]
            return parent / f"{name}.py"

        # Old style: module.pyc -> module.py
        return pyc_file.with_suffix(".py")

    def _get_module_analysis(self, module_name: str, **kwargs) -> Dict[str, Any]:
        """Analyze module import location and detect conflicts.

        Args:
            module_name: Name of the module/package to analyze

        Returns:
            Dict with module location, pip metadata, and conflict detection
        """
        import importlib.util

        result = {
            "module": module_name,
            "status": "unknown",
            "conflicts": [],
            "recommendations": [],
        }

        # Try to find the module's import location
        try:
            spec = importlib.util.find_spec(module_name)
            if spec and spec.origin:
                result["import_location"] = spec.origin
                result["import_path"] = (
                    str(Path(spec.origin).parent) if spec.origin != "built-in" else "built-in"
                )
                result["is_package"] = spec.submodule_search_locations is not None
                result["status"] = "importable"
            else:
                result["import_location"] = None
                result["status"] = "not_found"
        except (ImportError, ModuleNotFoundError, ValueError):
            result["import_location"] = None
            result["status"] = "not_found"
        except Exception as e:
            result["import_location"] = None
            result["status"] = "error"
            result["error"] = str(e)

        # Try to get pip package metadata
        try:
            import importlib.metadata

            dist = importlib.metadata.distribution(module_name)
            result["pip_package"] = {
                "name": dist.name,
                "version": dist.version,
                "location": str(dist._path.parent) if hasattr(dist, "_path") else "unknown",
            }

            # Check for editable install (default to normal)
            result["pip_package"]["install_type"] = "normal"
            try:
                direct_url_path = dist._path.parent / "direct_url.json"
                if direct_url_path.exists():
                    import json

                    with open(direct_url_path) as f:
                        direct_url = json.load(f)
                        result["pip_package"]["editable"] = direct_url.get("dir_info", {}).get(
                            "editable", False
                        )
                        result["pip_package"]["install_type"] = (
                            "editable" if result["pip_package"]["editable"] else "normal"
                        )
            except Exception:
                pass  # install_type already set to "normal" above

        except Exception:
            result["pip_package"] = None

        # Detect conflicts between pip and import locations
        if result["pip_package"] and result["import_location"]:
            pip_loc = Path(result["pip_package"]["location"])
            import_loc = Path(result["import_path"])

            if not import_loc.is_relative_to(pip_loc):
                result["conflicts"].append(
                    {
                        "type": "location_mismatch",
                        "severity": "warning",
                        "message": f"Import location differs from pip package location",
                        "pip_location": str(pip_loc),
                        "import_location": str(import_loc),
                    }
                )

        # Check if CWD is shadowing the module
        cwd = Path.cwd()
        if result.get("import_path") and (
            cwd in Path(result["import_path"]).parents or str(cwd) == result["import_path"]
        ):
            result["conflicts"].append(
                {
                    "type": "cwd_shadowing",
                    "severity": "warning",
                    "message": f"Current working directory is shadowing installed package",
                    "cwd": str(cwd),
                    "import_location": result["import_path"],
                }
            )
            result["recommendations"].append(
                {
                    "action": "change_directory",
                    "message": "Run from a different directory to use the installed package",
                    "command": "cd /tmp && python ...",
                }
            )

        # Check sys.path for the module
        if result.get("import_path"):
            for i, path in enumerate(sys.path):
                if result["import_path"].startswith(path if path else str(cwd)):
                    result["syspath_index"] = i
                    result["syspath_entry"] = path if path else f"(CWD: {cwd})"
                    break

        return result

    def _get_syspath_analysis(self, **kwargs) -> Dict[str, Any]:
        """Analyze sys.path for conflicts and issues.

        Returns:
            Dict with sys.path entries, CWD highlighting, and conflict detection
        """
        cwd = Path.cwd()
        paths = []

        for i, path in enumerate(sys.path):
            path_info = {
                "index": i,
                "path": path if path else f"(CWD: {cwd})",
                "is_cwd": path == "" or path == ".",
                "exists": Path(path).exists() if path else True,
                "type": "unknown",
            }

            # Classify path type
            if not path or path == ".":
                path_info["type"] = "cwd"
                path_info["priority"] = "highest"
            elif "site-packages" in path:
                path_info["type"] = "site-packages"
                path_info["priority"] = "normal"
            elif path == sys.prefix or path.startswith(sys.prefix):
                path_info["type"] = "python_stdlib"
                path_info["priority"] = "high"
            elif os.getenv("PYTHONPATH") and path in os.getenv("PYTHONPATH", "").split(":"):
                path_info["type"] = "pythonpath"
                path_info["priority"] = "high"
            else:
                path_info["type"] = "other"
                path_info["priority"] = "normal"

            paths.append(path_info)

        # Detect potential conflicts
        conflicts = []

        # Check for CWD shadowing site-packages
        if paths and paths[0]["is_cwd"]:
            site_packages = [p for p in paths if p["type"] == "site-packages"]
            if site_packages:
                conflicts.append(
                    {
                        "type": "cwd_precedence",
                        "severity": "info",
                        "message": "Current working directory takes precedence over site-packages",
                        "cwd": str(cwd),
                        "note": "Local modules will shadow installed packages",
                    }
                )

        return {
            "count": len(sys.path),
            "cwd": str(cwd),
            "paths": paths,
            "conflicts": conflicts,
            "pythonpath": os.getenv("PYTHONPATH"),
            "summary": {
                "cwd_entries": len([p for p in paths if p["is_cwd"]]),
                "site_packages": len([p for p in paths if p["type"] == "site-packages"]),
                "stdlib": len([p for p in paths if p["type"] == "python_stdlib"]),
                "pythonpath": len([p for p in paths if p["type"] == "pythonpath"]),
                "other": len([p for p in paths if p["type"] == "other"]),
            },
        }

    def _run_doctor(self, **kwargs) -> Dict[str, Any]:
        """Run automated diagnostics for common Python environment issues.

        Returns:
            Dict with detected issues, warnings, and recommendations
        """
        issues = []
        warnings = []
        info = []
        recommendations = []

        # Check 1: Virtual environment
        venv = self._detect_venv()
        if not venv["active"]:
            warnings.append(
                {
                    "category": "environment",
                    "message": "No virtual environment detected",
                    "impact": "Packages install globally, may cause conflicts",
                }
            )
            recommendations.append(
                {
                    "action": "create_venv",
                    "message": "Consider using a virtual environment",
                    "commands": [
                        "python3 -m venv venv",
                        "source venv/bin/activate",
                        "pip install -r requirements.txt",
                    ],
                }
            )

        # Check 2: CWD in sys.path[0]
        cwd = Path.cwd()
        if not sys.path[0] or sys.path[0] == ".":
            # Check if CWD contains Python modules that might shadow
            py_files = list(cwd.glob("*.py"))
            if py_files:
                warnings.append(
                    {
                        "category": "import_shadowing",
                        "message": f"CWD ({cwd}) is sys.path[0] and contains {len(py_files)} .py files",
                        "impact": "Local modules may shadow installed packages",
                        "files": [f.name for f in py_files[:5]],
                    }
                )
                recommendations.append(
                    {
                        "action": "verify_imports",
                        "message": "Verify imports are coming from expected locations",
                        "command": 'python -c "import module; print(module.__file__)"',
                    }
                )

        # Check 3: Stale .pyc files
        bytecode_check = self._check_bytecode(str(cwd))
        if bytecode_check.get("status") == "issues_found":
            stale = [i for i in bytecode_check["issues"] if i["type"] == "stale_bytecode"]
            if stale:
                issues.append(
                    {
                        "category": "bytecode",
                        "message": f"Found {len(stale)} stale .pyc files",
                        "impact": "Code changes may not take effect",
                        "severity": "high",
                    }
                )
                recommendations.append(
                    {
                        "action": "clean_bytecode",
                        "message": "Remove stale bytecode files",
                        "commands": [
                            "find . -type d -name __pycache__ -exec rm -rf {} +",
                            'find . -name "*.pyc" -delete',
                        ],
                    }
                )

        # Check 4: Python version
        version = sys.version_info
        if version.major < 3 or (version.major == 3 and version.minor < 8):
            warnings.append(
                {
                    "category": "version",
                    "message": f"Python {version.major}.{version.minor} is outdated",
                    "impact": "Many modern packages require Python 3.8+",
                    "severity": "medium",
                }
            )

        # Check 5: Editable installs
        try:
            import pkg_resources

            editable_count = 0
            for dist in pkg_resources.working_set:
                try:
                    if dist.has_metadata("direct_url.json"):
                        editable_count += 1
                except Exception:
                    pass

            if editable_count > 0:
                info.append(
                    {
                        "category": "development",
                        "message": f"Found {editable_count} editable package(s) installed",
                        "impact": "Editable installs are for development, not production",
                    }
                )
        except Exception:
            pass

        # Check 6: Duplicate/conflicting editable .pth files
        try:
            import site
            from collections import defaultdict

            site_packages_dirs = site.getsitepackages() + [site.getusersitepackages()]
            pth_by_package = defaultdict(list)

            for sp_dir in site_packages_dirs:
                sp_path = Path(sp_dir)
                if not sp_path.exists():
                    continue

                # Find all editable .pth files
                for pth_file in sp_path.glob("__editable__.*.pth"):
                    # Parse package name from __editable__.<pkg>-<version>.pth
                    name = pth_file.stem  # __editable__.<pkg>-<version>
                    parts = name.replace("__editable__.", "").rsplit("-", 1)
                    if len(parts) == 2:
                        pkg_name, version = parts
                        pth_by_package[pkg_name].append(
                            {"version": version, "path": str(pth_file)}
                        )

            # Check for packages with multiple .pth files
            for pkg_name, versions in pth_by_package.items():
                if len(versions) > 1:
                    issues.append(
                        {
                            "category": "editable_conflict",
                            "message": f"Multiple editable .pth files for '{pkg_name}'",
                            "impact": "Version conflicts - imports may load unexpected version",
                            "severity": "high",
                            "details": versions,
                        }
                    )
                    recommendations.append(
                        {
                            "action": "clean_editable",
                            "message": f"Remove stale editable .pth files for {pkg_name}",
                            "commands": [
                                f"rm ~/.local/lib/python*/site-packages/__editable__.*{pkg_name}*",
                                f"pip install {pkg_name} --force-reinstall",
                            ],
                        }
                    )

            # Check for editable installs shadowing PyPI dist-info
            for sp_dir in site_packages_dirs:
                sp_path = Path(sp_dir)
                if not sp_path.exists():
                    continue

                for pth_file in sp_path.glob("__editable__.*.pth"):
                    name = pth_file.stem.replace("__editable__.", "").rsplit("-", 1)[0]
                    # Look for non-editable dist-info for same package
                    dist_infos = list(sp_path.glob(f"{name}-*.dist-info"))
                    # Filter out the editable's own dist-info
                    non_editable = [
                        d
                        for d in dist_infos
                        if not (d / "direct_url.json").exists()
                    ]
                    if non_editable:
                        warnings.append(
                            {
                                "category": "editable_shadow",
                                "message": f"Editable '{name}' may shadow PyPI install",
                                "impact": "pip install from PyPI won't take effect",
                                "editable_pth": str(pth_file),
                                "pypi_dist_info": [str(d) for d in non_editable],
                            }
                        )
        except Exception:
            pass

        # Overall health score
        health_score = 100
        health_score -= len(issues) * 20
        health_score -= len(warnings) * 10
        health_score = max(0, health_score)

        status = "healthy"
        if health_score < 50:
            status = "critical"
        elif health_score < 70:
            status = "warning"
        elif health_score < 90:
            status = "caution"

        return {
            "status": status,
            "health_score": health_score,
            "issues": issues,
            "warnings": warnings,
            "info": info,
            "recommendations": recommendations,
            "summary": {
                "total_issues": len(issues),
                "total_warnings": len(warnings),
                "total_info": len(info),
                "total_recommendations": len(recommendations),
            },
            "checks_performed": [
                "virtual_environment",
                "cwd_shadowing",
                "stale_bytecode",
                "python_version",
                "editable_installs",
                "editable_conflicts",
            ],
        }

    @staticmethod
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
            # Executable examples for current directory
            "try_now": [
                "reveal python://doctor",
                "reveal python://debug/bytecode",
                "reveal python://venv",
            ],
            # Scenario-based workflow patterns
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
            # What NOT to do
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
                "python://imports/graph - Import dependency visualization (v0.18.0)",
                "python://imports/circular - Circular import detection (v0.18.0)",
                "python://debug/syntax - Syntax error detection (v0.18.0)",
                "python://project - Project type detection (v0.19.0)",
                "python://tests - Test discovery (v0.19.0)",
            ],
            "see_also": [
                "reveal help://python-guide - Comprehensive guide with multi-shot examples",
                "reveal help://tricks - Power user workflows",
                "reveal ast:// - Static code analysis",
            ],
        }

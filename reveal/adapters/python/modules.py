"""Module analysis utilities for Python adapter."""

import sys
import os
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple


def find_module_import_location(module_name: str) -> Dict[str, Any]:
    """Find the import location and metadata for a module."""
    import importlib.util

    try:
        spec = importlib.util.find_spec(module_name)
        if spec and spec.origin:
            return {
                "import_location": spec.origin,
                "import_path": (
                    str(Path(spec.origin).parent) if spec.origin != "built-in" else "built-in"
                ),
                "is_package": spec.submodule_search_locations is not None,
                "status": "importable",
            }
        else:
            return {"import_location": None, "status": "not_found"}
    except (ImportError, ModuleNotFoundError, ValueError):
        return {"import_location": None, "status": "not_found"}
    except Exception as e:
        return {"import_location": None, "status": "error", "error": str(e)}


def get_pip_package_metadata(module_name: str) -> Optional[Dict[str, Any]]:
    """Get pip package metadata including editable install detection."""
    try:
        import importlib.metadata

        dist = importlib.metadata.distribution(module_name)
        pip_package = {
            "name": dist.name,
            "version": dist.version,
            "location": str(dist._path.parent) if hasattr(dist, "_path") else "unknown",
            "install_type": "normal",
        }

        # Check for editable install
        try:
            direct_url_path = dist._path.parent / "direct_url.json"
            if direct_url_path.exists():
                import json

                with open(direct_url_path) as f:
                    direct_url = json.load(f)
                    editable = direct_url.get("dir_info", {}).get("editable", False)
                    pip_package["editable"] = editable
                    pip_package["install_type"] = "editable" if editable else "normal"
        except Exception:
            pass  # install_type already set to "normal"

        return pip_package
    except Exception:
        return None


def detect_pip_import_conflicts(
    pip_package: Optional[Dict[str, Any]], import_path: Optional[str]
) -> List[Dict[str, Any]]:
    """Detect conflicts between pip package location and import location."""
    if not pip_package or not import_path:
        return []

    pip_loc = Path(pip_package["location"])
    import_loc = Path(import_path)

    if not import_loc.is_relative_to(pip_loc):
        return [
            {
                "type": "location_mismatch",
                "severity": "warning",
                "message": "Import location differs from pip package location",
                "pip_location": str(pip_loc),
                "import_location": str(import_loc),
            }
        ]
    return []


def detect_cwd_shadowing(
    import_path: Optional[str]
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Detect if current working directory is shadowing the module."""
    conflicts = []
    recommendations = []

    if not import_path:
        return conflicts, recommendations

    cwd = Path.cwd()
    if cwd in Path(import_path).parents or str(cwd) == import_path:
        conflicts.append(
            {
                "type": "cwd_shadowing",
                "severity": "warning",
                "message": "Current working directory is shadowing installed package",
                "cwd": str(cwd),
                "import_location": import_path,
            }
        )
        recommendations.append(
            {
                "action": "change_directory",
                "message": "Run from a different directory to use the installed package",
                "command": "cd /tmp && python ...",
            }
        )

    return conflicts, recommendations


def find_module_syspath_index(import_path: Optional[str]) -> Dict[str, Any]:
    """Find the sys.path index where the module was found."""
    if not import_path:
        return {}

    cwd = Path.cwd()
    for i, path in enumerate(sys.path):
        if import_path.startswith(path if path else str(cwd)):
            return {
                "syspath_index": i,
                "syspath_entry": path if path else f"(CWD: {cwd})",
            }

    return {}


def get_module_analysis(module_name: str) -> Dict[str, Any]:
    """Analyze module import location and detect conflicts.

    Args:
        module_name: Name of the module/package to analyze

    Returns:
        Dict with module location, pip metadata, and conflict detection
    """
    result = {
        "module": module_name,
        "status": "unknown",
        "conflicts": [],
        "recommendations": [],
    }

    # Find module import location
    import_info = find_module_import_location(module_name)
    result.update(import_info)

    # Get pip package metadata
    result["pip_package"] = get_pip_package_metadata(module_name)

    # Detect conflicts
    pip_conflicts = detect_pip_import_conflicts(
        result["pip_package"], result.get("import_path")
    )
    result["conflicts"].extend(pip_conflicts)

    # Check CWD shadowing
    cwd_conflicts, cwd_recommendations = detect_cwd_shadowing(result.get("import_path"))
    result["conflicts"].extend(cwd_conflicts)
    result["recommendations"].extend(cwd_recommendations)

    # Find sys.path index
    syspath_info = find_module_syspath_index(result.get("import_path"))
    result.update(syspath_info)

    return result


def get_syspath_analysis() -> Dict[str, Any]:
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

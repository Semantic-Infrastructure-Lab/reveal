"""Environment diagnostics for Python adapter."""

import sys
from pathlib import Path
from typing import Dict, Any, List, Tuple

from .bytecode import check_bytecode


def check_venv(detect_venv_func) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Check virtual environment status."""
    warnings = []
    recommendations = []

    venv = detect_venv_func()
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

    return warnings, recommendations


def check_cwd_shadowing() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Check if CWD is shadowing installed packages."""
    warnings = []
    recommendations = []

    cwd = Path.cwd()
    if not sys.path[0] or sys.path[0] == ".":
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

    return warnings, recommendations


def check_stale_bytecode() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Check for stale .pyc files."""
    issues = []
    recommendations = []

    cwd = Path.cwd()
    bytecode_result = check_bytecode(str(cwd))
    if bytecode_result.get("status") == "issues_found":
        stale = [i for i in bytecode_result["issues"] if i["type"] == "stale_bytecode"]
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

    return issues, recommendations


def check_python_version() -> List[Dict[str, Any]]:
    """Check if Python version is outdated."""
    warnings = []

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

    return warnings


def check_editable_installs() -> List[Dict[str, Any]]:
    """Check for editable package installations."""
    info = []

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

    return info


def check_editable_conflicts() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Check for duplicate/conflicting editable .pth files."""
    issues = []
    warnings = []
    recommendations = []

    try:
        import site
        from collections import defaultdict

        site_packages_dirs = site.getsitepackages() + [site.getusersitepackages()]
        pth_by_package = defaultdict(list)

        # Find all editable .pth files
        for sp_dir in site_packages_dirs:
            sp_path = Path(sp_dir)
            if not sp_path.exists():
                continue

            for pth_file in sp_path.glob("__editable__.*.pth"):
                name = pth_file.stem
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
                dist_infos = list(sp_path.glob(f"{name}-*.dist-info"))
                non_editable = [
                    d for d in dist_infos if not (d / "direct_url.json").exists()
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

    return issues, warnings, recommendations


def calculate_health_score(
    issues: List[Dict[str, Any]], warnings: List[Dict[str, Any]]
) -> Tuple[int, str]:
    """Calculate health score and status from issues and warnings."""
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

    return health_score, status


def run_doctor(detect_venv_func) -> Dict[str, Any]:
    """Run automated diagnostics for common Python environment issues.

    Args:
        detect_venv_func: Function to detect virtual environment

    Returns:
        Dict with detected issues, warnings, and recommendations
    """
    issues = []
    warnings = []
    info = []
    recommendations = []

    # Run all diagnostic checks
    w, r = check_venv(detect_venv_func)
    warnings.extend(w)
    recommendations.extend(r)

    w, r = check_cwd_shadowing()
    warnings.extend(w)
    recommendations.extend(r)

    i, r = check_stale_bytecode()
    issues.extend(i)
    recommendations.extend(r)

    warnings.extend(check_python_version())
    info.extend(check_editable_installs())

    i, w, r = check_editable_conflicts()
    issues.extend(i)
    warnings.extend(w)
    recommendations.extend(r)

    # Calculate health score
    health_score, status = calculate_health_score(issues, warnings)

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

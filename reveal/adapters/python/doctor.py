"""Environment diagnostics for Python adapter."""

import re
import sys
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from .bytecode import check_bytecode

# Match a literal `__version__ = "1.2.3"` assignment (single or double quotes).
_VERSION_LITERAL = re.compile(
    r"""^__version__\s*[:=]\s*['"]([^'"]+)['"]""", re.MULTILINE
)


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


def _read_package_dir_version(pkg_dir: Path) -> Optional[str]:
    """Best-effort static read of a source package directory's declared version.

    Looks for a literal ``__version__ = "x.y.z"`` in the usual homes. Returns
    None when the version is computed dynamically (e.g. read from
    importlib.metadata at import time) — such packages can't be compared
    statically and are deliberately not flagged.
    """
    for candidate in ("__init__.py", "version.py", "_version.py"):
        f = pkg_dir / candidate
        if not f.is_file():
            continue
        try:
            text = f.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        m = _VERSION_LITERAL.search(text)
        if m:
            return m.group(1)
    return None


def check_package_dir_shadowing() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """BACK-419: detect a source package DIRECTORY on an earlier sys.path entry
    that shadows a separately-installed distribution of the same import name
    with a DIFFERENT version.

    This is the mechanism that silently contaminated reveal's own dogfood sweep:
    ``reveal --version`` returned 0.102.0 or 0.103.0 depending purely on cwd,
    because an unregistered dev checkout on sys.path shadowed a differently-
    versioned real install in site-packages. The existing ``check_cwd_shadowing``
    only globs *loose* ``.py`` files in cwd; it never looks at package
    *directories*, and ``check_editable_conflicts`` only sees PEP-660 editable
    registrations, not a manual checkout relying on sys.path's cwd-prepend.

    To keep false positives near zero this only fires on a confirmed version
    mismatch: the shadowing directory must (a) be an importable package
    (have ``__init__.py``), (b) map to an installed distribution, (c) sit on an
    earlier sys.path entry than that install, and (d) declare a *literal*
    ``__version__`` that differs from the installed distribution's version.
    Packages whose version is computed dynamically (no literal marker) are not
    flagged — including reveal itself, whose version is read from metadata.
    """
    issues: List[Dict[str, Any]] = []
    recommendations: List[Dict[str, Any]] = []

    try:
        import importlib.metadata as im

        pkg_to_dist = im.packages_distributions()

        # Ordered, resolved, existing sys.path directories.
        path_dirs: List[Path] = []
        for entry in sys.path:
            d = Path(entry or ".").resolve()
            if d.is_dir():
                path_dirs.append(d)

        def _install_dir(dist_name: str) -> Optional[Path]:
            try:
                return Path(str(im.distribution(dist_name).locate_file(""))).resolve()
            except Exception:  # noqa: BLE001 — best-effort metadata probe
                return None

        seen: set = set()
        for d_idx, d in enumerate(path_dirs):
            try:
                entries = list(d.iterdir())
            except OSError:
                continue
            for pkg in entries:
                if pkg.name in seen:
                    continue
                if not (pkg.is_dir() and (pkg / "__init__.py").is_file()):
                    continue
                dists = set(pkg_to_dist.get(pkg.name, []))
                if not dists:
                    continue
                local_ver = _read_package_dir_version(pkg)
                if not local_ver:
                    continue  # dynamic version — can't compare, don't guess
                for dist in dists:
                    inst = _install_dir(dist)
                    if inst is None or inst == pkg.parent:
                        continue  # not installed, or this dir IS the install (editable)
                    # Only shadowing if the install is later on sys.path.
                    try:
                        inst_idx = path_dirs.index(inst)
                    except ValueError:
                        inst_idx = None
                    if inst_idx is not None and d_idx >= inst_idx:
                        continue
                    try:
                        installed_ver = im.version(dist)
                    except Exception:  # noqa: BLE001
                        continue
                    if installed_ver and installed_ver != local_ver:
                        seen.add(pkg.name)
                        issues.append(
                            {
                                "category": "import_shadowing",
                                "message": (
                                    f"Package directory '{pkg}' (version {local_ver}) "
                                    f"shadows installed '{dist}' (version {installed_ver})"
                                ),
                                "impact": (
                                    f"'import {pkg.name}' resolves to the local checkout, not the "
                                    f"installed package — behavior changes with cwd/PYTHONPATH"
                                ),
                                "severity": "high",
                            }
                        )
                        recommendations.append(
                            {
                                "action": "resolve_package_shadowing",
                                "message": (
                                    f"Reconcile '{pkg.name}': `pip install -e {pkg.parent}` so the "
                                    f"checkout IS the install, or run from a directory that keeps "
                                    f"{pkg.parent} off sys.path"
                                ),
                                "command": f'python -c "import {pkg.name}; print({pkg.name}.__file__)"',
                            }
                        )
                        break
    except Exception:  # noqa: BLE001 — diagnostics must never crash the doctor
        pass

    return issues, recommendations


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
        import importlib.metadata

        def _is_editable(dist) -> bool:
            try:
                return bool(dist.read_text("direct_url.json"))
            except (FileNotFoundError, TypeError):
                return False

        editable_count = sum(1 for dist in importlib.metadata.distributions() if _is_editable(dist))

        if editable_count > 0:
            info.append(
                {
                    "category": "development",
                    "message": f"Found {editable_count} editable package(s) installed",
                    "impact": "Editable installs are for development, not production",
                }
            )
    except Exception:
        pass  # package introspection is best-effort; return whatever was collected

    return info


def _find_editable_packages(site_packages_dirs):
    """Return (pth_by_package dict, issues list, recommendations list) for editable conflicts."""
    from collections import defaultdict
    pth_by_package = defaultdict(list)
    issues = []
    recommendations = []

    for sp_dir in site_packages_dirs:
        sp_path = Path(sp_dir)
        if not sp_path.exists():
            continue
        for pth_file in sp_path.glob("__editable__.*.pth"):
            name = pth_file.stem
            parts = name.replace("__editable__.", "").rsplit("-", 1)
            if len(parts) == 2:
                pkg_name, version = parts
                pth_by_package[pkg_name].append({"version": version, "path": str(pth_file)})

    for pkg_name, versions in pth_by_package.items():
        if len(versions) > 1:
            issues.append({
                "category": "editable_conflict",
                "message": f"Multiple editable .pth files for '{pkg_name}'",
                "impact": "Version conflicts - imports may load unexpected version",
                "severity": "high",
                "details": versions,
            })
            recommendations.append({
                "action": "clean_editable",
                "message": f"Remove stale editable .pth files for {pkg_name}",
                "commands": [
                    f"rm ~/.local/lib/python*/site-packages/__editable__.*{pkg_name}*",
                    f"pip install {pkg_name} --force-reinstall",
                ],
            })

    return issues, recommendations


def _find_editable_shadows(site_packages_dirs):
    """Return warnings list for editable installs shadowing PyPI dist-info."""
    warnings = []
    for sp_dir in site_packages_dirs:
        sp_path = Path(sp_dir)
        if not sp_path.exists():
            continue
        for pth_file in sp_path.glob("__editable__.*.pth"):
            name = pth_file.stem.replace("__editable__.", "").rsplit("-", 1)[0]
            non_editable = [
                d for d in sp_path.glob(f"{name}-*.dist-info")
                if not (d / "direct_url.json").exists()
            ]
            if non_editable:
                warnings.append({
                    "category": "editable_shadow",
                    "message": f"Editable '{name}' may shadow PyPI install",
                    "impact": "pip install from PyPI won't take effect",
                    "editable_pth": str(pth_file),
                    "pypi_dist_info": [str(d) for d in non_editable],
                })
    return warnings


def check_editable_conflicts() -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Check for duplicate/conflicting editable .pth files."""
    try:
        import site
        site_packages_dirs = site.getsitepackages() + [site.getusersitepackages()]
        issues, recommendations = _find_editable_packages(site_packages_dirs)
        warnings = _find_editable_shadows(site_packages_dirs)
    except Exception:
        return [], [], []  # package introspection is best-effort

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

    i, r = check_package_dir_shadowing()
    issues.extend(i)
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
            "package_dir_shadowing",
            "stale_bytecode",
            "python_version",
            "editable_installs",
            "editable_conflicts",
        ],
    }

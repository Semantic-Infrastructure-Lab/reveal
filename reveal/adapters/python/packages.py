"""Package management utilities for Python adapter."""

from typing import Dict, Any, Iterator


def get_packages() -> Iterator[Any]:
    """Generator for installed packages.

    Yields:
        Package distribution objects
    """
    try:
        # Prefer importlib.metadata (modern, Python 3.8+)
        import importlib.metadata

        for dist in importlib.metadata.distributions():
            yield dist
    except ImportError:
        # Fallback to pkg_resources (deprecated but still works)
        try:
            import pkg_resources

            for dist in pkg_resources.working_set:  # type: ignore[assignment]
                yield dist
        except ImportError:
            # No package metadata available
            pass


def get_packages_list() -> Dict[str, Any]:
    """List all installed packages.

    Returns:
        Dict with package count and list of packages
    """
    packages = []

    for dist in get_packages():
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


def get_package_details(package_name: str) -> Dict[str, Any]:
    """Get detailed information about a specific package.

    Args:
        package_name: Name of the package

    Returns:
        Dict with package details or error
    """
    try:
        # Prefer importlib.metadata (modern, Python 3.8+)
        import importlib.metadata

        dist = importlib.metadata.distribution(package_name)
        metadata = dist.metadata

        return {
            "name": metadata.get("Name"),  # type: ignore[attr-defined]
            "version": metadata.get("Version"),  # type: ignore[attr-defined]
            "summary": metadata.get("Summary"),  # type: ignore[attr-defined]
            "author": metadata.get("Author"),  # type: ignore[attr-defined]
            "license": metadata.get("License"),  # type: ignore[attr-defined]
            "location": str(dist._path.parent) if hasattr(dist, "_path") else "unknown",
            "requires_python": metadata.get("Requires-Python"),  # type: ignore[attr-defined]
            "homepage": metadata.get("Home-page"),  # type: ignore[attr-defined]
            "dependencies": dist.requires or [],
        }
    except Exception:
        # Fallback to pkg_resources (deprecated but still works)
        try:
            import pkg_resources

            dist = pkg_resources.get_distribution(package_name)  # type: ignore[assignment]

            details = {
                "name": dist.project_name,  # type: ignore[attr-defined]
                "version": dist.version,
                "location": dist.location,  # type: ignore[attr-defined]
                "requires_python": None,
                "dependencies": [],
            }

            # Get requirements
            try:
                details["dependencies"] = [str(req) for req in dist.requires()]  # type: ignore[operator,misc]
            except Exception:
                pass

            # Check if editable install
            try:
                details["editable"] = dist.has_metadata("direct_url.json")  # type: ignore[attr-defined]
            except Exception:
                details["editable"] = False

            return details

        except Exception as e:
            return {"error": f"Package not found: {package_name}", "details": str(e)}

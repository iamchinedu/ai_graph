"""Packages: list what is installed, and check it is consistent (the same idea as `pip check`).

collect() -> [{"name", "version", "requires"}]      what this environment has installed
evaluate(packages, marker_env) -> (valid, reason)
packages: [{"name": "boto3", "version": "1.40.0", "requires": ["botocore<1.41,>=1.40", ...]}]
marker_env: environment markers from the project's machine (python_version, sys_platform, ...)
"""
import platform
from importlib import metadata

from packaging.markers import default_environment
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import InvalidVersion, Version


def collect():
    """Every installed distribution with its version and declared requirements."""
    seen = {}
    for dist in metadata.distributions():
        name = dist.metadata["Name"]
        if name:
            seen[canonicalize_name(name)] = {"name": name, "version": dist.version, "requires": list(dist.requires or [])}
    return list(seen.values())


def python_version():
    return platform.python_version()


def marker_env():
    return default_environment()


def evaluate(packages, marker_env=None, max_reasons=3):
    env = {**default_environment(), **(marker_env or {}), "extra": ""}
    installed = {canonicalize_name(p["name"]): p for p in packages}
    problems = []
    for pkg in packages:
        for raw in pkg.get("requires") or []:
            try:
                req = Requirement(raw)
            except Exception:
                continue
            if req.marker is not None:
                try:
                    if not req.marker.evaluate(env):
                        continue
                except Exception:
                    continue
            found = installed.get(canonicalize_name(req.name))
            label = f'{pkg["name"]} {pkg["version"]}'
            if found is None:
                problems.append(f"{label} requires {req.name}, which is not installed")
                continue
            try:
                ok = req.specifier.contains(Version(found["version"]), prereleases=True)
            except InvalidVersion:
                continue
            if not ok:
                problems.append(
                    f'{label} requires {req.name}{req.specifier}, found {found["version"]}'
                )
    if problems:
        return False, "; ".join(problems[:max_reasons]) + (
            f" (+{len(problems) - max_reasons} more)" if len(problems) > max_reasons else ""
        )
    return True, None

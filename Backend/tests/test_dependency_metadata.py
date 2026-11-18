"""Ensure the two supported backend install paths declare the same packages."""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def _package_name(spec: str) -> str:
    """Normalize distribution names, excluding extras and version constraints."""
    match = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)", spec)
    assert match is not None, f"Invalid dependency specification: {spec!r}"
    return re.sub(r"[-_.]+", "-", match.group(1)).lower()


def test_project_metadata_and_docker_requirements_declare_same_runtime_packages():
    package = tomllib.loads((BACKEND_DIR / "pyproject.toml").read_text(encoding="utf-8"))
    project_deps = package["project"]["dependencies"]

    requirement_lines = (BACKEND_DIR / "requirements.txt").read_text(encoding="utf-8").splitlines()
    install_deps = [line.strip() for line in requirement_lines
                    if line.strip() and not line.lstrip().startswith("#")]

    from_metadata = {_package_name(dep) for dep in project_deps}
    from_requirements = {_package_name(dep) for dep in install_deps}
    assert len(from_metadata) == len(project_deps), "Duplicate dependencies in pyproject.toml"
    assert len(from_requirements) == len(install_deps), "Duplicate dependencies in requirements.txt"
    assert from_metadata == from_requirements, (
        f"Missing from pyproject: {sorted(from_requirements - from_metadata)}; "
        f"missing from requirements: {sorted(from_metadata - from_requirements)}"
    )

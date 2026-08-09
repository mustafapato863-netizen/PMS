"""Deterministic dotenv loading where real process variables always win."""

from __future__ import annotations

import os

from dotenv import load_dotenv


def load_project_environment(backend_dir: str) -> None:
    """
    Load the shared defaults and local overrides without replacing variables
    injected by the process, container, or hosting platform.
    """
    backend_dir = os.path.abspath(backend_dir)
    project_root = os.path.abspath(os.path.join(backend_dir, ".."))
    env_path = os.path.join(project_root, "DevOps", ".env")
    backend_local_path = os.path.join(backend_dir, ".env.local")
    project_local_path = os.path.join(project_root, "DevOps", ".env.local")

    process_environment = dict(os.environ)
    load_dotenv(dotenv_path=env_path, override=False)
    if os.path.exists(backend_local_path):
        load_dotenv(dotenv_path=backend_local_path, override=True)
    if os.path.exists(project_local_path):
        load_dotenv(dotenv_path=project_local_path, override=True)

    # Restore values that existed before dotenv loading. This makes deployment
    # configuration authoritative while retaining local-over-shared file order.
    os.environ.update(process_environment)

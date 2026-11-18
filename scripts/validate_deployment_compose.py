#!/usr/bin/env python3
"""Enforce live Dokploy service startup and port exposure contracts.

Pass the JSON produced by "docker compose -f docker-compose.yml config --format json".
Only the live Dokploy backend/worker stack is covered; the alternative Caddy stack
has its own Compose file and checks.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


def validate_deployment_compose(config: dict[str, Any]) -> list[str]:
    """Return actionable violations without relying on a running Docker daemon."""
    violations: list[str] = []
    services = config.get("services")
    if not isinstance(services, dict):
        return ["Compose must contain a services mapping."]

    redis = services.get("redis")
    if not isinstance(redis, dict) or not redis.get("healthcheck"):
        violations.append("redis must have a healthcheck for dependent services.")

    migrate = services.get("migrate")
    if not isinstance(migrate, dict):
        violations.append("migrate service is required.")
    elif str(migrate.get("restart", "")).lower() not in {"no", "none"}:
        violations.append("migrate must remain a one-shot service (restart: no).")

    for name in ("backend", "worker"):
        service = services.get(name)
        if not isinstance(service, dict):
            violations.append(f"{name} service is required.")
            continue

        dependencies = service.get("depends_on")
        if not isinstance(dependencies, dict):
            violations.append(f"{name} must use conditional depends_on.")
        else:
            for dependency, condition in (
                ("redis", "service_healthy"),
                ("migrate", "service_completed_successfully"),
            ):
                value = dependencies.get(dependency)
                actual = value.get("condition") if isinstance(value, dict) else None
                if actual != condition:
                    violations.append(
                        f"{name} must require {dependency}: {condition} (got {actual!r})."
                    )

        for port in service.get("ports") or []:
            if not isinstance(port, dict):
                violations.append(f"{name} has an unrecognized published port: {port!r}.")
                continue
            host_ip = port.get("host_ip")
            if host_ip not in {"127.0.0.1", "::1"}:
                violations.append(
                    f"{name} publishes port {port.get('published', '?')} on "
                    f"{host_ip or 'all interfaces'}; restrict host access to loopback "
                    "or remove the published port. Traefik uses dokploy-network."
                )

    return violations


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(f"Usage: {argv[0]} <resolved-compose.json>", file=sys.stderr)
        return 2

    try:
        config = json.loads(Path(argv[1]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"Could not read resolved Compose JSON: {exc}", file=sys.stderr)
        return 2
    if not isinstance(config, dict):
        print("Resolved Compose JSON must be an object.", file=sys.stderr)
        return 2

    violations = validate_deployment_compose(config)
    if violations:
        for violation in violations:
            print(f"FAIL: {violation}", file=sys.stderr)
        return 1
    print("PASS: Dokploy migration, Redis, and published-port contracts validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

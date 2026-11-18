"""Unit tests for the production deployment contract checker."""

from __future__ import annotations

import copy
import unittest

from validate_deployment_compose import validate_deployment_compose


def valid_compose() -> dict:
    depends_on = {
        "redis": {"condition": "service_healthy"},
        "migrate": {"condition": "service_completed_successfully"},
    }
    return {
        "services": {
            "redis": {"healthcheck": {"test": ["CMD", "redis-cli", "ping"]}},
            "migrate": {"restart": "no"},
            "backend": {
                "depends_on": copy.deepcopy(depends_on),
                "ports": [{"host_ip": "127.0.0.1", "published": "7860"}],
            },
            "worker": {"depends_on": copy.deepcopy(depends_on)},
        }
    }


class DeploymentComposeContractTests(unittest.TestCase):
    def test_valid_dokploy_contract(self) -> None:
        self.assertEqual(validate_deployment_compose(valid_compose()), [])

    def test_migration_must_complete_before_backend_starts(self) -> None:
        compose = valid_compose()
        compose["services"]["backend"]["depends_on"]["migrate"] = {
            "condition": "service_started"
        }
        self.assertTrue(any("backend must require migrate" in error for error in validate_deployment_compose(compose)))

    def test_worker_must_wait_for_redis_health(self) -> None:
        compose = valid_compose()
        compose["services"]["worker"]["depends_on"]["redis"] = {
            "condition": "service_started"
        }
        self.assertTrue(any("worker must require redis" in error for error in validate_deployment_compose(compose)))

    def test_public_backend_port_fails(self) -> None:
        compose = valid_compose()
        compose["services"]["backend"]["ports"][0]["host_ip"] = "0.0.0.0"
        self.assertTrue(any("all interfaces" in error or "0.0.0.0" in error for error in validate_deployment_compose(compose)))

    def test_missing_redis_healthcheck_fails(self) -> None:
        compose = valid_compose()
        del compose["services"]["redis"]["healthcheck"]
        self.assertTrue(any("redis must have a healthcheck" in error for error in validate_deployment_compose(compose)))

    def test_migrate_is_one_shot(self) -> None:
        compose = valid_compose()
        compose["services"]["migrate"]["restart"] = "always"
        self.assertTrue(any("one-shot" in error for error in validate_deployment_compose(compose)))


if __name__ == "__main__":
    unittest.main()

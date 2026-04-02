"""Compose file checker — loads YAML and runs all lint rules."""

from __future__ import annotations

from pathlib import Path

import yaml

from sweat_review.compose_check.models import Issue, SEVERITY_ORDER
from sweat_review.compose_check.rules import (
    check_absolute_bind_mounts,
    check_build_context,
    check_compose_references,
    check_container_name,
    check_env_file,
    check_external_networks,
    check_external_volumes,
    check_hardcoded_ports,
    check_healthcheck_dependency,
    check_host_network,
    check_privileged,
    check_static_env_vars,
)


def check_compose_file(path: Path) -> list[Issue]:
    """Load a compose file and run all rules against it."""
    data = yaml.safe_load(path.read_text())

    if not isinstance(data, dict):
        return [Issue(
            code="E000",
            severity=__import__("sweat_review.compose_check.models", fromlist=["Severity"]).Severity.FAIL,
            service=None,
            message="invalid compose file — not a YAML mapping",
            explanation="The file must be a valid Docker Compose YAML file with a top-level mapping.",
        )]

    services = data.get("services", {}) or {}
    networks = data.get("networks", {}) or {}
    volumes = data.get("volumes", {}) or {}

    issues: list[Issue] = []

    # Per-service rules
    for name, config in services.items():
        if not isinstance(config, dict):
            continue
        issues.extend(check_hardcoded_ports(name, config))
        issues.extend(check_container_name(name, config))
        issues.extend(check_host_network(name, config))
        issues.extend(check_absolute_bind_mounts(name, config))
        issues.extend(check_static_env_vars(name, config))
        issues.extend(check_healthcheck_dependency(name, config, services))
        issues.extend(check_privileged(name, config))
        issues.extend(check_build_context(name, config))
        issues.extend(check_env_file(name, config))
        issues.extend(check_compose_references(name, config))

    # Top-level rules
    issues.extend(check_external_networks(networks))
    issues.extend(check_external_volumes(volumes))

    return sorted(issues, key=lambda i: (SEVERITY_ORDER[i.severity], i.code))

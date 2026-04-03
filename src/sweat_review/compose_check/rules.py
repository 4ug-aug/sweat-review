"""Lint rules for Docker Compose preview environment compatibility."""

from __future__ import annotations

from sweat_review.compose_check.models import Issue, Severity

# Env var names that typically need to vary per preview instance
_STATIC_ENV_VARS = {
    "VIRTUAL_HOST",
    "LETSENCRYPT_HOST",
    "DOMAIN",
    "BASE_URL",
    "SITE_URL",
    "APP_URL",
    "ALLOWED_HOSTS",
    "CORS_ORIGIN",
    "HOSTNAME",
}

_SENSITIVE_CAPS = {"SYS_ADMIN", "NET_ADMIN", "SYS_PTRACE", "ALL"}


# ---------------------------------------------------------------------------
# FAIL rules
# ---------------------------------------------------------------------------


def check_container_name(name: str, config: dict) -> list[Issue]:
    """F002: Flag explicit container_name."""
    if "container_name" in config:
        return [Issue(
            code="F002",
            severity=Severity.FAIL,
            service=name,
            message=f'explicit container_name "{config["container_name"]}"',
            explanation=(
                "Docker requires unique container names. This blocks parallel stacks.\n"
                "Remove container_name and let Compose generate it from the project name."
            ),
        )]
    return []


def check_host_network(name: str, config: dict) -> list[Issue]:
    """F003: Flag network_mode: host."""
    if config.get("network_mode") == "host":
        return [Issue(
            code="F003",
            severity=Severity.FAIL,
            service=name,
            message='host network mode',
            explanation=(
                "Host networking shares the host's network stack — no isolation between stacks.\n"
                "Switch to bridge networking (the default). Host mode is incompatible with "
                "running multiple isolated stacks."
            ),
        )]
    return []


def check_external_networks(networks: dict) -> list[Issue]:
    """F004: External networks that aren't traefik-public."""
    issues = []
    for net_name, net_config in networks.items():
        if not isinstance(net_config, dict):
            continue
        if net_config.get("external") is True and net_name != "traefik-public":
            issues.append(Issue(
                code="F004",
                severity=Severity.FAIL,
                service=None,
                message=f'external network "{net_name}"',
                explanation=(
                    "External networks are shared across all preview stacks. "
                    "Services on this network may clash.\n"
                    "Convert to a stack-internal network unless cross-stack "
                    "communication is intentional."
                ),
            ))
    return issues


# ---------------------------------------------------------------------------
# WARN rules
# ---------------------------------------------------------------------------


def check_external_volumes(volumes: dict) -> list[Issue]:
    """W001: Volumes declared as external."""
    issues = []
    for vol_name, vol_config in volumes.items():
        if not isinstance(vol_config, dict):
            continue
        if vol_config.get("external") is True:
            issues.append(Issue(
                code="W001",
                severity=Severity.WARN,
                service=None,
                message=f'named volume "{vol_name}" declared as external',
                explanation=(
                    "External volumes are shared across all preview stacks. "
                    "Each preview should have its own data.\n"
                    "Remove `external: true` to let each stack create its own volume."
                ),
            ))
    return issues


def check_absolute_bind_mounts(name: str, config: dict) -> list[Issue]:
    """W002: Absolute host paths in bind mounts."""
    issues = []
    for vol in config.get("volumes", []):
        if isinstance(vol, dict):
            source = vol.get("source", "")
        elif isinstance(vol, str) and ":" in vol:
            source = vol.split(":")[0]
        else:
            continue
        if isinstance(source, str) and source.startswith("/"):
            issues.append(Issue(
                code="W002",
                severity=Severity.WARN,
                service=name,
                message=f'absolute bind mount "{source}"',
                explanation=(
                    "Absolute bind mounts are shared across stacks. "
                    "Multiple stacks writing to the same host directory causes data races.\n"
                    "Consider using named volumes or relative paths within the clone directory."
                ),
            ))
    return issues


def check_static_env_vars(name: str, config: dict) -> list[Issue]:
    """W003: Environment variables that typically need to vary per instance."""
    issues = []
    env = config.get("environment", {})
    if isinstance(env, list):
        env_dict = {}
        for entry in env:
            if "=" in str(entry):
                key, _, val = str(entry).partition("=")
                env_dict[key] = val
        env = env_dict
    if not isinstance(env, dict):
        return []

    for key, value in env.items():
        if key.upper() in _STATIC_ENV_VARS and value:
            issues.append(Issue(
                code="W003",
                severity=Severity.WARN,
                service=name,
                message=f'static environment variable {key}="{value}"',
                explanation=(
                    "This environment variable likely needs to change per preview instance.\n"
                    "The preview agent can override it, but verify this is handled."
                ),
            ))
    return issues


def check_healthcheck_dependency(
    name: str, config: dict, all_services: dict
) -> list[Issue]:
    """W004: depends_on with service_healthy but no healthcheck on dependency."""
    issues = []
    depends = config.get("depends_on", {})
    if isinstance(depends, list):
        return []
    if not isinstance(depends, dict):
        return []

    for dep_name, dep_config in depends.items():
        if not isinstance(dep_config, dict):
            continue
        if dep_config.get("condition") == "service_healthy":
            dep_service = all_services.get(dep_name, {})
            if "healthcheck" not in dep_service:
                issues.append(Issue(
                    code="W004",
                    severity=Severity.WARN,
                    service=name,
                    message=f'depends on "{dep_name}" being healthy, but it has no healthcheck',
                    explanation=(
                        "This service depends on a health check that isn't defined. "
                        "The stack may fail to start.\n"
                        "Add a healthcheck to the dependency or remove the condition."
                    ),
                ))
    return issues


def check_privileged(name: str, config: dict) -> list[Issue]:
    """W005: Privileged mode or excessive capabilities."""
    issues = []
    if config.get("privileged") is True:
        issues.append(Issue(
            code="W005",
            severity=Severity.WARN,
            service=name,
            message="privileged mode enabled",
            explanation=(
                "Privileged containers in preview environments are a security risk, "
                "especially when deploying untrusted PR branches.\n"
                "Remove privileged mode unless absolutely required."
            ),
        ))
    caps = config.get("cap_add", [])
    flagged = [c for c in caps if str(c).upper() in _SENSITIVE_CAPS]
    if flagged:
        issues.append(Issue(
            code="W005",
            severity=Severity.WARN,
            service=name,
            message=f'sensitive capabilities: {", ".join(flagged)}',
            explanation=(
                "Elevated capabilities in preview environments are a security risk.\n"
                "Review whether these are necessary for preview deployments."
            ),
        ))
    return issues


# ---------------------------------------------------------------------------
# INFO rules
# ---------------------------------------------------------------------------


def check_build_context(name: str, config: dict) -> list[Issue]:
    """I001: Build context detected."""
    if "build" in config:
        return [Issue(
            code="I001",
            severity=Severity.INFO,
            service=name,
            message="builds from source",
            explanation=(
                "This service builds from source. Preview deploys will include "
                "a build step which may take a few minutes."
            ),
        )]
    return []


def check_env_file(name: str, config: dict) -> list[Issue]:
    """I002: env_file directive."""
    env_files = config.get("env_file", [])
    if isinstance(env_files, str):
        env_files = [env_files]
    if env_files:
        return [Issue(
            code="I002",
            severity=Severity.INFO,
            service=name,
            message=f'references env file: {", ".join(env_files)}',
            explanation=(
                "Make sure this env file is committed to the repo or the "
                "preview agent is configured to provide it via TARGET_ENV_FILE."
            ),
        )]
    return []


def check_compose_references(name: str, config: dict) -> list[Issue]:
    """I003: extends or include references."""
    if "extends" in config:
        return [Issue(
            code="I003",
            severity=Severity.INFO,
            service=name,
            message="uses extends to reference another service/file",
            explanation=(
                "This compose file references other files. "
                "Ensure all are present in the repo."
            ),
        )]
    return []

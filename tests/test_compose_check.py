"""Tests for the compose compatibility checker."""

from __future__ import annotations

from pathlib import Path

import pytest

from sweat_review.compose_check.checker import check_compose_file
from sweat_review.compose_check.models import Issue, Severity
from sweat_review.compose_check.output import format_json, format_text
from sweat_review.compose_check.rules import (
    check_absolute_bind_mounts,
    check_build_context,
    check_compose_references,
    check_container_name,
    check_env_file,
    check_external_networks,
    check_external_volumes,
    check_healthcheck_dependency,
    check_host_network,
    check_privileged,
    check_static_env_vars,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# F002 — Explicit container_name
# ---------------------------------------------------------------------------


def test_f002_present():
    issues = check_container_name("app", {"container_name": "my-app"})
    assert len(issues) == 1
    assert issues[0].code == "F002"


def test_f002_absent():
    issues = check_container_name("app", {"image": "nginx"})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# F003 — Host network mode
# ---------------------------------------------------------------------------


def test_f003_host():
    issues = check_host_network("app", {"network_mode": "host"})
    assert len(issues) == 1
    assert issues[0].code == "F003"


def test_f003_bridge():
    issues = check_host_network("app", {"network_mode": "bridge"})
    assert len(issues) == 0


def test_f003_absent():
    issues = check_host_network("app", {})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# F004 — External networks (not traefik-public)
# ---------------------------------------------------------------------------


def test_f004_external():
    issues = check_external_networks({"my-net": {"external": True}})
    assert len(issues) == 1
    assert issues[0].code == "F004"


def test_f004_traefik_public_ok():
    issues = check_external_networks({"traefik-public": {"external": True}})
    assert len(issues) == 0


def test_f004_not_external():
    issues = check_external_networks({"my-net": {"driver": "bridge"}})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# W001 — External volumes
# ---------------------------------------------------------------------------


def test_w001_external():
    issues = check_external_volumes({"data": {"external": True}})
    assert len(issues) == 1
    assert issues[0].code == "W001"
    assert issues[0].severity == Severity.WARN


def test_w001_not_external():
    issues = check_external_volumes({"data": {}})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# W002 — Absolute bind mounts
# ---------------------------------------------------------------------------


def test_w002_absolute_short():
    issues = check_absolute_bind_mounts("app", {"volumes": ["/var/data:/app/data"]})
    assert len(issues) == 1
    assert issues[0].code == "W002"


def test_w002_named_volume():
    issues = check_absolute_bind_mounts("app", {"volumes": ["pgdata:/var/lib/postgresql/data"]})
    assert len(issues) == 0


def test_w002_relative_path():
    issues = check_absolute_bind_mounts("app", {"volumes": ["./data:/app/data"]})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# W003 — Static env vars
# ---------------------------------------------------------------------------


def test_w003_virtual_host():
    issues = check_static_env_vars("app", {"environment": {"VIRTUAL_HOST": "example.com"}})
    assert len(issues) == 1
    assert issues[0].code == "W003"


def test_w003_list_format():
    issues = check_static_env_vars("app", {"environment": ["BASE_URL=https://example.com"]})
    assert len(issues) == 1
    assert issues[0].code == "W003"


def test_w003_safe_var():
    issues = check_static_env_vars("app", {"environment": {"DATABASE_URL": "postgres://db:5432"}})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# W004 — Healthcheck dependency
# ---------------------------------------------------------------------------


def test_w004_missing_healthcheck():
    services = {"db": {"image": "postgres"}}
    config = {"depends_on": {"db": {"condition": "service_healthy"}}}
    issues = check_healthcheck_dependency("app", config, services)
    assert len(issues) == 1
    assert issues[0].code == "W004"


def test_w004_healthcheck_present():
    services = {"db": {"image": "postgres", "healthcheck": {"test": "pg_isready"}}}
    config = {"depends_on": {"db": {"condition": "service_healthy"}}}
    issues = check_healthcheck_dependency("app", config, services)
    assert len(issues) == 0


def test_w004_simple_depends_on():
    config = {"depends_on": ["db"]}
    issues = check_healthcheck_dependency("app", config, {"db": {}})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# W005 — Privileged / capabilities
# ---------------------------------------------------------------------------


def test_w005_privileged():
    issues = check_privileged("app", {"privileged": True})
    assert len(issues) == 1
    assert issues[0].code == "W005"


def test_w005_cap_add():
    issues = check_privileged("app", {"cap_add": ["SYS_ADMIN"]})
    assert len(issues) == 1
    assert issues[0].code == "W005"


def test_w005_safe_cap():
    issues = check_privileged("app", {"cap_add": ["NET_BIND_SERVICE"]})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# I001 — Build context
# ---------------------------------------------------------------------------


def test_i001_build():
    issues = check_build_context("app", {"build": "./backend"})
    assert len(issues) == 1
    assert issues[0].code == "I001"
    assert issues[0].severity == Severity.INFO


def test_i001_no_build():
    issues = check_build_context("app", {"image": "nginx"})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# I002 — env_file
# ---------------------------------------------------------------------------


def test_i002_env_file():
    issues = check_env_file("app", {"env_file": ".env"})
    assert len(issues) == 1
    assert issues[0].code == "I002"


def test_i002_env_file_list():
    issues = check_env_file("app", {"env_file": [".env", ".env.local"]})
    assert len(issues) == 1
    assert issues[0].code == "I002"


def test_i002_no_env_file():
    issues = check_env_file("app", {})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# I003 — Compose references
# ---------------------------------------------------------------------------


def test_i003_extends():
    issues = check_compose_references("app", {"extends": {"file": "base.yml", "service": "web"}})
    assert len(issues) == 1
    assert issues[0].code == "I003"


def test_i003_no_extends():
    issues = check_compose_references("app", {"image": "nginx"})
    assert len(issues) == 0


# ---------------------------------------------------------------------------
# Integration tests with fixtures
# ---------------------------------------------------------------------------


def test_problematic_compose():
    issues = check_compose_file(FIXTURES / "problematic.yml")
    codes = {i.code for i in issues}
    assert "F002" in codes
    assert "F003" in codes
    assert "F004" in codes
    assert "W001" in codes
    assert "W002" in codes
    assert "W003" in codes
    assert "W004" in codes
    assert "W005" in codes
    assert "I001" in codes
    assert "I002" in codes

    fails = [i for i in issues if i.severity == Severity.FAIL]
    assert len(fails) >= 3


def test_clean_compose():
    issues = check_compose_file(FIXTURES / "clean.yml")
    fails = [i for i in issues if i.severity == Severity.FAIL]
    assert len(fails) == 0


def test_warnings_only():
    issues = check_compose_file(FIXTURES / "warnings-only.yml")
    fails = [i for i in issues if i.severity == Severity.FAIL]
    warns = [i for i in issues if i.severity == Severity.WARN]
    assert len(fails) == 0
    assert len(warns) >= 3


def test_issues_sorted_by_severity():
    issues = check_compose_file(FIXTURES / "problematic.yml")
    severities = [i.severity for i in issues]
    fail_idx = [j for j, s in enumerate(severities) if s == Severity.FAIL]
    warn_idx = [j for j, s in enumerate(severities) if s == Severity.WARN]
    info_idx = [j for j, s in enumerate(severities) if s == Severity.INFO]
    if fail_idx and warn_idx:
        assert max(fail_idx) < min(warn_idx)
    if warn_idx and info_idx:
        assert max(warn_idx) < min(info_idx)


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


def test_format_text_no_issues():
    output = format_text([], "docker-compose.yml")
    assert "No issues found" in output


def test_format_text_with_issues():
    issues = check_compose_file(FIXTURES / "problematic.yml")
    output = format_text(issues, "tests/fixtures/problematic.yml")
    assert "FAIL" in output
    assert "error" in output


def test_format_json_valid():
    import json
    issues = check_compose_file(FIXTURES / "problematic.yml")
    output = format_json(issues)
    parsed = json.loads(output)
    assert isinstance(parsed, list)
    assert len(parsed) > 0
    assert "code" in parsed[0]
    assert "severity" in parsed[0]

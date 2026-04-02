"""Output formatters for compose check results."""

from __future__ import annotations

import json

from sweat_review.compose_check.models import Issue, Severity

# ANSI color codes
_RED = "\033[31m"
_YELLOW = "\033[33m"
_BLUE = "\033[34m"
_GREEN = "\033[32m"
_BOLD = "\033[1m"
_DIM = "\033[2m"
_RESET = "\033[0m"

_SEVERITY_COLORS = {
    Severity.FAIL: _RED,
    Severity.WARN: _YELLOW,
    Severity.INFO: _BLUE,
}


def format_text(issues: list[Issue], file_path: str) -> str:
    """Format issues as colored terminal output."""
    lines: list[str] = []

    lines.append(f"\n  Checking {file_path} for preview environment compatibility...\n")

    if not issues:
        lines.append(f"  {_GREEN}PASS{_RESET}  No issues found. This compose file looks good!\n")
        return "\n".join(lines)

    for issue in issues:
        color = _SEVERITY_COLORS[issue.severity]
        label = f"{color}{_BOLD}{issue.severity.value}{_RESET}"
        service = f" {issue.service} —" if issue.service else ""
        lines.append(f"  {label}{service} {issue.message}")
        for explanation_line in issue.explanation.split("\n"):
            lines.append(f"        {_DIM}{explanation_line}{_RESET}")
        lines.append("")

    # Summary
    fails = sum(1 for i in issues if i.severity == Severity.FAIL)
    warns = sum(1 for i in issues if i.severity == Severity.WARN)
    infos = sum(1 for i in issues if i.severity == Severity.INFO)

    lines.append(f"  {'─' * 40}")
    parts = []
    if fails:
        parts.append(f"{_RED}{fails} error{'s' if fails != 1 else ''}{_RESET}")
    if warns:
        parts.append(f"{_YELLOW}{warns} warning{'s' if warns != 1 else ''}{_RESET}")
    if infos:
        parts.append(f"{_BLUE}{infos} info{_RESET}")
    lines.append(f"  {', '.join(parts)}")

    if fails:
        lines.append(f"\n  Fix the errors before using this compose file with sweat-review.\n")
    else:
        lines.append(f"\n  No errors found. Review the warnings above.\n")

    return "\n".join(lines)


def format_json(issues: list[Issue]) -> str:
    """Format issues as JSON."""
    return json.dumps(
        [
            {
                "code": issue.code,
                "severity": issue.severity.value,
                "service": issue.service,
                "message": issue.message,
                "explanation": issue.explanation,
            }
            for issue in issues
        ],
        indent=2,
    )

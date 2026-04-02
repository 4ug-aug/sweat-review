from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Severity(Enum):
    FAIL = "FAIL"
    WARN = "WARN"
    INFO = "INFO"


SEVERITY_ORDER = {Severity.FAIL: 0, Severity.WARN: 1, Severity.INFO: 2}


@dataclass
class Issue:
    code: str
    severity: Severity
    service: str | None
    message: str
    explanation: str

from __future__ import annotations

import logging
import platform
import shutil
from pathlib import Path

logger = logging.getLogger(__name__)

MIN_DISK_FREE_GB = 2.0
MIN_DISK_FREE_PERCENT = 10.0
MIN_MEM_FREE_MB = 256


class InsufficientResourcesError(Exception):
    pass


def check_disk_space(path: Path) -> None:
    usage = shutil.disk_usage(path)
    free_gb = usage.free / (1024**3)
    free_percent = (usage.free / usage.total) * 100

    if free_gb < MIN_DISK_FREE_GB or free_percent < MIN_DISK_FREE_PERCENT:
        raise InsufficientResourcesError(
            f"Low disk space: {free_gb:.1f} GB free ({free_percent:.1f}%). "
            f"Need at least {MIN_DISK_FREE_GB} GB or {MIN_DISK_FREE_PERCENT}%."
        )
    logger.debug("Disk check OK: %.1f GB free (%.1f%%)", free_gb, free_percent)


def check_memory() -> None:
    if platform.system() != "Linux":
        return

    try:
        meminfo = Path("/proc/meminfo").read_text()
        available_kb = None
        for line in meminfo.splitlines():
            if line.startswith("MemAvailable:"):
                parts = line.split()
                available_kb = int(parts[1])
                break
        if available_kb is None:
            logger.warning("Could not parse MemAvailable from /proc/meminfo")
            return
        available_mb = available_kb / 1024
        if available_mb < MIN_MEM_FREE_MB:
            raise InsufficientResourcesError(
                f"Low memory: {available_mb:.0f} MB available. "
                f"Need at least {MIN_MEM_FREE_MB} MB."
            )
        logger.debug("Memory check OK: %.0f MB available", available_mb)
    except InsufficientResourcesError:
        raise
    except FileNotFoundError:
        return
    except Exception:
        logger.warning("Memory check failed", exc_info=True)


def check_resources(clone_base_dir: Path) -> None:
    check_disk_space(clone_base_dir)
    check_memory()

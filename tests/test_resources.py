from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from sweat_review.resources import (
    InsufficientResourcesError,
    check_disk_space,
    check_memory,
    check_resources,
)


def _fake_disk_usage(free_gb: float, total_gb: float = 100.0):
    """Return a mock disk_usage result."""
    free = int(free_gb * 1024**3)
    total = int(total_gb * 1024**3)
    used = total - free

    class Usage:
        pass

    u = Usage()
    u.free = free
    u.total = total
    u.used = used
    return u


def test_check_disk_space_passes(tmp_path: Path) -> None:
    with patch("sweat_review.resources.shutil.disk_usage") as mock:
        mock.return_value = _fake_disk_usage(free_gb=50.0)
        check_disk_space(tmp_path)  # Should not raise


def test_check_disk_space_fails_low_gb(tmp_path: Path) -> None:
    with patch("sweat_review.resources.shutil.disk_usage") as mock:
        mock.return_value = _fake_disk_usage(free_gb=1.0, total_gb=100.0)
        with pytest.raises(InsufficientResourcesError, match="Low disk space"):
            check_disk_space(tmp_path)


def test_check_disk_space_fails_both_low(tmp_path: Path) -> None:
    with patch("sweat_review.resources.shutil.disk_usage") as mock:
        # 0.5 GB free out of 10 GB = 5% — both thresholds breached
        mock.return_value = _fake_disk_usage(free_gb=0.5, total_gb=10.0)
        with pytest.raises(InsufficientResourcesError, match="Low disk space"):
            check_disk_space(tmp_path)


def test_check_disk_space_passes_low_percent_high_gb(tmp_path: Path) -> None:
    with patch("sweat_review.resources.shutil.disk_usage") as mock:
        # 14.5 GB free out of 500 GB = 2.9% — low percent but plenty of GB
        mock.return_value = _fake_disk_usage(free_gb=14.5, total_gb=500.0)
        check_disk_space(tmp_path)  # Should not raise


def test_check_memory_skips_on_macos() -> None:
    with patch("sweat_review.resources.platform.system", return_value="Darwin"):
        check_memory()  # Should not raise


def test_check_memory_fails_on_linux() -> None:
    meminfo = "MemTotal:       8000000 kB\nMemAvailable:     100000 kB\n"
    with (
        patch("sweat_review.resources.platform.system", return_value="Linux"),
        patch("sweat_review.resources.Path.read_text", return_value=meminfo),
    ):
        with pytest.raises(InsufficientResourcesError, match="Low memory"):
            check_memory()


def test_check_memory_passes_on_linux() -> None:
    meminfo = "MemTotal:       8000000 kB\nMemAvailable:    4000000 kB\n"
    with (
        patch("sweat_review.resources.platform.system", return_value="Linux"),
        patch("sweat_review.resources.Path.read_text", return_value=meminfo),
    ):
        check_memory()  # Should not raise


def test_check_resources_runs_both(tmp_path: Path) -> None:
    with (
        patch("sweat_review.resources.shutil.disk_usage") as mock_disk,
        patch("sweat_review.resources.platform.system", return_value="Darwin"),
    ):
        mock_disk.return_value = _fake_disk_usage(free_gb=50.0)
        check_resources(tmp_path)  # Should not raise

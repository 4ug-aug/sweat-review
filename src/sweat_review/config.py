from __future__ import annotations

from importlib.resources import files as pkg_files
from pathlib import Path

from platformdirs import user_data_dir
from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_template_path() -> Path:
    """Return the path to the bundled Compose override template."""
    return Path(str(pkg_files("sweat_review").joinpath("data/docker-compose.override.yml.j2")))


def _default_data_dir() -> Path:
    """Return the platform-appropriate data directory for sweat-review."""
    return Path(user_data_dir("sweat-review"))


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    github_token: str = Field(description="GitHub PAT with repo scope")
    github_repo: str = Field(description="Target repo as owner/repo")
    vps_ip: str = "127.0.0.1"
    clone_base_dir: Path = Field(default_factory=lambda: _default_data_dir() / "repos")
    max_concurrent: int = Field(default=15, gt=0)
    stale_timeout_hours: int = Field(default=48, gt=0)
    poll_interval: int = Field(default=30, gt=0)
    db_path: Path = Field(default_factory=lambda: _default_data_dir() / "sweat-review.db")
    compose_file: str = "docker-compose.yml"
    target_env_file: Path | None = None
    template_path: Path = Field(default_factory=_default_template_path)

    @field_validator("github_repo")
    @classmethod
    def repo_must_have_slash(cls, v: str) -> str:
        if "/" not in v:
            raise ValueError("must be in 'owner/repo' format")
        return v

    @model_validator(mode="after")
    def resolve_paths(self) -> "Settings":
        object.__setattr__(self, "clone_base_dir", self.clone_base_dir.resolve())
        object.__setattr__(self, "db_path", self.db_path.resolve())
        object.__setattr__(self, "template_path", self.template_path.resolve())
        if not self.template_path.exists():
            raise ValueError(
                f"template_path does not exist: {self.template_path}"
            )
        if self.target_env_file is not None:
            resolved = self.target_env_file.resolve()
            object.__setattr__(self, "target_env_file", resolved)
            if not resolved.exists():
                raise ValueError(
                    f"target_env_file does not exist: {resolved}"
                )
        return self


def get_settings() -> Settings:
    return Settings()

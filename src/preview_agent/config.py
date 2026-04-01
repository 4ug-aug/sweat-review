from pathlib import Path

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    github_token: str = Field(description="GitHub PAT with repo scope")
    github_repo: str = Field(description="Target repo as owner/repo")
    vps_ip: str = "127.0.0.1"
    clone_base_dir: Path = Path("/tmp/preview-agent")
    max_concurrent: int = Field(default=15, gt=0)
    stale_timeout_hours: int = Field(default=48, gt=0)
    poll_interval: int = Field(default=30, gt=0)
    db_path: Path = Path("preview_agent.db")
    compose_file: str = "docker-compose.yml"
    template_path: Path = Path("templates/docker-compose.override.yml.j2")

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
        return self


def get_settings() -> Settings:
    return Settings()

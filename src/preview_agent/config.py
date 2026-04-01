import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    github_webhook_secret: str
    github_token: str
    github_repo: str
    vps_ip: str
    clone_base_dir: Path
    max_concurrent: int
    stale_timeout_hours: int
    db_path: Path
    compose_file: str
    template_path: Path


def get_settings() -> Settings:
    return Settings(
        github_webhook_secret=os.environ.get("GITHUB_WEBHOOK_SECRET", ""),
        github_token=os.environ.get("GITHUB_TOKEN", ""),
        github_repo=os.environ.get("GITHUB_REPO", ""),
        vps_ip=os.environ.get("VPS_IP", "127.0.0.1"),
        clone_base_dir=Path(os.environ.get("CLONE_BASE_DIR", "/tmp/preview-agent")),
        max_concurrent=int(os.environ.get("MAX_CONCURRENT", "15")),
        stale_timeout_hours=int(os.environ.get("STALE_TIMEOUT_HOURS", "48")),
        db_path=Path(os.environ.get("DB_PATH", "preview_agent.db")),
        compose_file=os.environ.get("COMPOSE_FILE", "docker-compose.yml"),
        template_path=Path(
            os.environ.get(
                "TEMPLATE_PATH", "templates/docker-compose.override.yml.j2"
            )
        ),
    )

from __future__ import annotations

import argparse
import getpass
import logging
import shutil
import subprocess
import sys
from contextlib import asynccontextmanager
from importlib.resources import files as pkg_files
from pathlib import Path

import uvicorn
from fastapi import FastAPI

from sweat_review.cleanup import CleanupService
from sweat_review.compose import ComposeRenderer
from sweat_review.config import get_settings
from sweat_review.github_client import GitHubClient
from sweat_review.health import router as health_router
from sweat_review.orchestrator import Orchestrator
from sweat_review.poller import PollerService
from sweat_review.state import StateStore

logger = logging.getLogger(__name__)


# ============================================================================
# FastAPI app
# ============================================================================


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()

    state_store = StateStore(settings.db_path)
    await state_store.initialize()

    github = GitHubClient(
        token=settings.github_token,
        repo=settings.github_repo,
    )
    compose = ComposeRenderer(settings.template_path)
    orchestrator = Orchestrator(settings, state_store, compose, github)

    settings.clone_base_dir.mkdir(parents=True, exist_ok=True)

    app.state.settings = settings
    app.state.state_store = state_store
    app.state.github = github
    app.state.compose = compose
    app.state.orchestrator = orchestrator

    cleanup = CleanupService(settings, state_store, orchestrator, github)
    await cleanup.start()
    app.state.cleanup = cleanup

    poller = PollerService(settings, state_store, orchestrator, github)
    await poller.start()
    app.state.poller = poller

    logger.info(
        "SWEAT Review started — repo: %s, vps: %s",
        settings.github_repo,
        settings.vps_ip,
    )

    yield

    await poller.stop()
    await cleanup.stop()
    await github.close()
    logger.info("SWEAT Review stopped")


def create_app() -> FastAPI:
    app = FastAPI(title="SWEAT Review", lifespan=lifespan)
    app.include_router(health_router)
    return app


# ============================================================================
# CLI: init
# ============================================================================


def run_init(target_dir: Path) -> None:
    target_dir = target_dir.resolve()
    print("\n  SWEAT Review — Setup\n")

    # Prompt for configuration
    token = getpass.getpass("  GitHub Token (ghp_...): ")
    if not token.strip():
        print("  Error: token is required.", file=sys.stderr)
        sys.exit(1)

    repo = input("  GitHub Repo (owner/repo): ").strip()
    if "/" not in repo:
        print("  Error: repo must be in 'owner/repo' format.", file=sys.stderr)
        sys.exit(1)

    vps_ip = input("  VPS IP [127.0.0.1]: ").strip() or "127.0.0.1"

    # Write .env
    env_path = target_dir / ".env"
    env_path.write_text(f"GITHUB_TOKEN={token}\nGITHUB_REPO={repo}\nVPS_IP={vps_ip}\n")
    print(f"  ✓ Created {env_path}")

    # Write traefik compose
    traefik_dir = target_dir / "traefik"
    traefik_dir.mkdir(parents=True, exist_ok=True)
    traefik_src = pkg_files("sweat_review").joinpath("data/traefik-compose.yml")
    traefik_dest = traefik_dir / "docker-compose.yml"
    shutil.copy2(str(traefik_src), str(traefik_dest))
    print(f"  ✓ Created {traefik_dest}")

    # Create Docker network (ignore if exists)
    subprocess.run(
        ["docker", "network", "create", "traefik-public"],
        capture_output=True,
    )
    print("  ✓ Docker network 'traefik-public' ready")

    # Start Traefik
    result = subprocess.run(
        ["docker", "compose", "-f", str(traefik_dest), "up", "-d"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        print("  ✓ Traefik started (dashboard: http://localhost:8080)")
    else:
        print(f"  ⚠ Traefik failed to start: {result.stderr.strip()}", file=sys.stderr)

    print("\n  Run 'sweat-review start' to begin watching for PRs.\n")


# ============================================================================
# CLI: start
# ============================================================================


def run_start(host: str, port: int) -> None:
    from pydantic import ValidationError

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    try:
        get_settings()
    except ValidationError as exc:
        print("Configuration error:\n", file=sys.stderr)
        for err in exc.errors():
            field = err["loc"][0]
            msg = err["msg"]
            print(f"  {field}: {msg}", file=sys.stderr)
        print(
            "\nRun 'sweat-review init' first, or check your .env file.", file=sys.stderr
        )
        sys.exit(1)

    app = create_app()
    uvicorn.run(app, host=host, port=port)


# ============================================================================
# CLI: check
# ============================================================================


def run_check(file: str, fmt: str) -> None:
    from sweat_review.compose_check.checker import check_compose_file
    from sweat_review.compose_check.models import Severity
    from sweat_review.compose_check.output import format_json, format_text

    path = Path(file)
    if not path.exists():
        print(f"  Error: {file} not found.", file=sys.stderr)
        sys.exit(1)

    issues = check_compose_file(path)

    if fmt == "json":
        print(format_json(issues))
    else:
        print(format_text(issues, file))

    if any(i.severity == Severity.FAIL for i in issues):
        sys.exit(1)


# ============================================================================
# CLI entry point
# ============================================================================


def cli() -> None:
    parser = argparse.ArgumentParser(
        prog="sweat-review",
        description="Self-hosted ephemeral preview environments for GitHub PRs",
    )
    sub = parser.add_subparsers(dest="command")

    init_p = sub.add_parser("init", help="Set up a new sweat-review project")
    init_p.add_argument(
        "--dir",
        type=Path,
        default=Path("."),
        help="Directory to initialize (default: current directory)",
    )

    start_p = sub.add_parser("start", help="Start the SWEAT Review server")
    start_p.add_argument(
        "--host", default="0.0.0.0", help="Bind host (default: 0.0.0.0)"
    )
    start_p.add_argument(
        "--port", type=int, default=8000, help="Bind port (default: 8000)"
    )

    check_p = sub.add_parser(
        "check", help="Check a compose file for preview compatibility"
    )
    check_p.add_argument(
        "-f", "--file", default="docker-compose.yml",
        help="Compose file to check (default: docker-compose.yml)",
    )
    check_p.add_argument(
        "--format", choices=["text", "json"], default="text",
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    if args.command == "init":
        run_init(args.dir)
    elif args.command == "start":
        run_start(args.host, args.port)
    elif args.command == "check":
        run_check(args.file, args.format)
    else:
        parser.print_help()

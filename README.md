# Preview Agent

Self-hosted ephemeral preview environments for GitHub pull requests.

Spins up an isolated Docker Compose stack per PR on a VPS, routes traffic via
subdomains using Traefik, and posts the preview URL as a GitHub PR comment.

## How it works

```
    GitHub PR event
         |
      webhook (POST /webhook)
         |
         v
  +---------------+
  | Preview Agent |  FastAPI server on port 8000
  +-------+-------+
          |
    +-----+------+
    |            |
 clone repo   post comment
 render override  on the PR
 docker compose
 up -d --build
    |
    v
  +--------+
  | Traefik |  Shared reverse proxy on port 80
  +----+----+  Routes by Host header
       |
  +----+----+----+
  |    |    |    |
 pr-1 pr-2 pr-3 ...   Isolated Compose stacks
```

Each PR gets its own fully isolated stack (frontend, backend, nginx, database,
workers — whatever your `docker-compose.yml` defines). Traffic is routed via
subdomain:

```
http://pr{N}.{VPS_IP}.nip.io
```

[nip.io](https://nip.io) provides wildcard DNS that maps any subdomain
containing an IP back to that IP — no domain registration or DNS config needed.

When a PR is opened or updated, the agent:

1. Clones the PR branch into an isolated directory
2. Renders a Compose override file that adds Traefik routing labels to your
   nginx service
3. Runs `docker compose -p pr-{N} up -d --build` to start the stack
4. Posts a comment on the PR with the preview URL

When the PR is closed, the agent tears down the stack, removes the clone
directory, and updates the PR comment.

## Prerequisites

- A VPS (or local machine) with **Docker** and **Docker Compose** installed
- **Python 3.12+**
- **[uv](https://docs.astral.sh/uv/)**
- A **GitHub personal access token** with `repo` scope (for cloning private
  repos and posting PR comments)

## Setup

### 1. Clone and install

```bash
git clone <this-repo>
cd preview-agent

# Install dependencies (creates .venv automatically)
uv sync --all-groups
```

### 2. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with your values:

```bash
GITHUB_WEBHOOK_SECRET=a-strong-random-secret   # You'll use this when creating the webhook
GITHUB_TOKEN=ghp_your_token_here               # GitHub PAT with repo scope
GITHUB_REPO=your-org/your-repo                 # The repo to monitor
VPS_IP=203.0.113.42                            # Your VPS public IP
```

Full list of settings:

| Variable | Description | Default |
|----------|-------------|---------|
| `GITHUB_WEBHOOK_SECRET` | Shared secret for webhook HMAC verification | (required) |
| `GITHUB_TOKEN` | GitHub PAT for PR comments and repo cloning | (required) |
| `GITHUB_REPO` | Target repository as `owner/repo` | (required) |
| `VPS_IP` | Public IP of the VPS | `127.0.0.1` |
| `CLONE_BASE_DIR` | Directory where PR repos are cloned | `/tmp/preview-agent` |
| `MAX_CONCURRENT` | Maximum simultaneous preview environments | `15` |
| `STALE_TIMEOUT_HOURS` | Hours before a deployment is considered stale | `48` |
| `DB_PATH` | Path to the SQLite state database | `preview_agent.db` |
| `COMPOSE_FILE` | Name of the Compose file in the target repo | `docker-compose.yml` |
| `TEMPLATE_PATH` | Path to the Jinja2 override template | `templates/docker-compose.override.yml.j2` |

### 3. Start Traefik

Traefik is the shared reverse proxy that routes subdomain traffic to the
correct preview stack.

```bash
# Create the shared Docker network (one-time)
docker network create traefik-public

# Start Traefik
docker compose -f traefik/docker-compose.yml up -d
```

Verify Traefik is running by visiting `http://localhost:8080` (the dashboard).

### 4. Configure the GitHub webhook

In your target repository, go to **Settings > Webhooks > Add webhook**:

| Field | Value |
|-------|-------|
| Payload URL | `http://{VPS_IP}:8000/webhook` |
| Content type | `application/json` |
| Secret | Same value as `GITHUB_WEBHOOK_SECRET` in your `.env` |
| Events | Select **Pull requests** only |

### 5. Start the agent

```bash
uv run preview-agent
```

The agent starts a FastAPI server on `0.0.0.0:8000`. It will:

- Listen for GitHub webhook events on `POST /webhook`
- Verify the HMAC signature on every request
- Deploy, update, or tear down preview stacks in the background
- Post/update comments on the PR with the preview URL or error details

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/webhook` | GitHub webhook receiver (signature-verified) |
| `GET` | `/health` | Health check — returns `{"status": "healthy"}` |
| `GET` | `/status` | List all tracked deployments |
| `GET` | `/status/{pr_number}` | Get a single deployment's status |

## Testing

### Run the test suite

```bash
uv sync --all-groups
uv run pytest -v
```

This runs 26 tests covering:

- **State store** — SQLite CRUD, upsert semantics, stale query
- **Compose renderer** — Template rendering, YAML validity, Traefik labels
- **Webhook signature** — HMAC-SHA256 verification
- **Orchestrator** — Deploy/teardown state transitions, command construction
- **Integration** — Full HTTP request flow through the FastAPI app

### Manual test with the sample app

A minimal multi-service app is included in `sample-app/` (Flask backend, static
frontend, nginx reverse proxy, Postgres, Celery stub). You can use it to verify
the Traefik routing without needing a real GitHub webhook.

```bash
# 1. Make sure Traefik is running (see Setup step 3 above)

# 2. Render an override for "PR 1"
uv run python -c "
from preview_agent.compose import ComposeRenderer
from pathlib import Path
r = ComposeRenderer(Path('templates/docker-compose.override.yml.j2'))
r.write_override(Path('sample-app'), pr_number=1, vps_ip='127.0.0.1')
"

# 3. Start the stack
docker compose -p pr-1 \
  -f sample-app/docker-compose.yml \
  -f sample-app/docker-compose.override.yml \
  up -d --build

# 4. Test it
curl -H "Host: pr1.127.0.0.1.nip.io" http://localhost/api/health
# Expected: {"status":"ok","service":"backend"}

curl -H "Host: pr1.127.0.0.1.nip.io" http://localhost/api/hello
# Expected: {"message":"Hello from the backend"}

# 5. Run a second stack to prove isolation
uv run python -c "
from preview_agent.compose import ComposeRenderer
from pathlib import Path
r = ComposeRenderer(Path('templates/docker-compose.override.yml.j2'))
r.write_override(Path('sample-app'), pr_number=2, vps_ip='127.0.0.1')
"

docker compose -p pr-2 \
  -f sample-app/docker-compose.yml \
  -f sample-app/docker-compose.override.yml \
  up -d --build

curl -H "Host: pr2.127.0.0.1.nip.io" http://localhost/api/health
# Both pr-1 and pr-2 respond independently

# 6. Tear down
docker compose -p pr-1 down -v --remove-orphans
docker compose -p pr-2 down -v --remove-orphans
```

### Simulate a webhook locally

With the agent running (`uv run preview-agent`), you can send a fake webhook to test
the full flow end-to-end:

```bash
# Generate the payload
PAYLOAD='{"action":"opened","number":99,"pull_request":{"head":{"ref":"main","sha":"abc123"}}}'

# Sign it
SIGNATURE=$(echo -n "$PAYLOAD" | openssl dgst -sha256 -hmac "$(grep GITHUB_WEBHOOK_SECRET .env | cut -d= -f2)" | awk '{print "sha256="$2}')

# Send it
curl -X POST http://localhost:8000/webhook \
  -H "Content-Type: application/json" \
  -H "X-GitHub-Event: pull_request" \
  -H "X-Hub-Signature-256: $SIGNATURE" \
  -d "$PAYLOAD"

# Check status
curl http://localhost:8000/status
curl http://localhost:8000/status/99
```

## Target repo requirements

The preview agent works with any project that has a `docker-compose.yml` with
an **nginx** service acting as the entry point. The override template attaches
Traefik labels to the nginx service so it can be reached via subdomain.

If your entry point service has a different name, edit
`templates/docker-compose.override.yml.j2` and replace `nginx` with your
service name.

## Project structure

```
├── pyproject.toml                          # Package config + CLI entry point
├── .env.example                            # Environment variable template
├── src/preview_agent/
│   ├── main.py                             # FastAPI app + CLI entry point
│   ├── config.py                           # Settings loaded from env vars
│   ├── webhook.py                          # POST /webhook — GitHub event handler
│   ├── orchestrator.py                     # Deploy / update / teardown logic
│   ├── compose.py                          # Jinja2 override template rendering
│   ├── github_client.py                    # Webhook signature + PR comments
│   ├── state.py                            # SQLite deployment state tracking
│   └── cleanup.py                          # Stale deployment garbage collection
├── templates/
│   └── docker-compose.override.yml.j2      # Per-PR Compose override with Traefik labels
├── traefik/
│   └── docker-compose.yml                  # Shared Traefik reverse proxy
├── sample-app/                             # Minimal multi-service app for testing
│   ├── docker-compose.yml
│   ├── backend/                            # Flask API
│   ├── frontend/                           # Static HTML
│   └── nginx/                              # Reverse proxy
└── tests/                                  # pytest suite (26 tests)
```

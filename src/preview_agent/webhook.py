from __future__ import annotations

import logging

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

logger = logging.getLogger(__name__)

router = APIRouter()


@router.post("/webhook")
async def handle_webhook(request: Request, background_tasks: BackgroundTasks) -> dict:
    body = await request.body()

    # Verify signature
    signature = request.headers.get("X-Hub-Signature-256", "")
    github = request.app.state.github
    if not github.verify_signature(body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")

    # Parse event
    event = request.headers.get("X-GitHub-Event", "")
    if event != "pull_request":
        return {"status": "ignored", "event": event}

    payload = await request.json()
    action = payload.get("action", "")
    pr = payload.get("pull_request", {})
    pr_number = payload.get("number", 0)
    branch = pr.get("head", {}).get("ref", "")
    commit_sha = pr.get("head", {}).get("sha", "")

    orchestrator = request.app.state.orchestrator

    if action in ("opened", "reopened"):
        logger.info("PR #%d %s — scheduling deploy", pr_number, action)
        background_tasks.add_task(orchestrator.deploy, pr_number, branch, commit_sha)
    elif action == "synchronize":
        logger.info("PR #%d synchronize — scheduling update", pr_number)
        background_tasks.add_task(orchestrator.update, pr_number, branch, commit_sha)
    elif action == "closed":
        logger.info("PR #%d closed — scheduling teardown", pr_number)
        background_tasks.add_task(orchestrator.teardown, pr_number)
    else:
        return {"status": "ignored", "action": action}

    return {"status": "accepted", "pr": pr_number, "action": action}

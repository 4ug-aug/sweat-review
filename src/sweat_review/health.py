from __future__ import annotations

import shutil

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request) -> dict:
    result: dict = {"status": "healthy"}

    try:
        state = request.app.state.state_store
        await state.get_all()
    except Exception:
        result["status"] = "degraded"

    try:
        settings = request.app.state.settings
        usage = shutil.disk_usage(settings.clone_base_dir)
        result["disk_free_gb"] = round(usage.free / (1024**3), 1)
    except Exception:
        pass

    return result


@router.get("/status")
async def all_status(request: Request) -> list[dict]:
    state = request.app.state.state_store
    deployments = await state.get_all()
    return [
        {
            "pr_number": d.pr_number,
            "branch": d.branch,
            "commit_sha": d.commit_sha,
            "status": d.status,
            "url": d.url,
            "created_at": d.created_at.isoformat(),
            "updated_at": d.updated_at.isoformat(),
            "error_message": d.error_message,
        }
        for d in deployments
    ]


@router.get("/status/{pr_number}")
async def pr_status(pr_number: int, request: Request) -> dict:
    state = request.app.state.state_store
    dep = await state.get(pr_number)
    if dep is None:
        raise HTTPException(status_code=404, detail="Deployment not found")
    return {
        "pr_number": dep.pr_number,
        "branch": dep.branch,
        "commit_sha": dep.commit_sha,
        "status": dep.status,
        "url": dep.url,
        "created_at": dep.created_at.isoformat(),
        "updated_at": dep.updated_at.isoformat(),
        "error_message": dep.error_message,
    }

from __future__ import annotations

from datetime import datetime, timezone
from html import escape

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from sweat_review.state import Deployment, DeploymentStatus

router = APIRouter()

STATUS_COLORS = {
    DeploymentStatus.RUNNING: "#22c55e",
    DeploymentStatus.BUILDING: "#eab308",
    DeploymentStatus.PENDING: "#eab308",
    DeploymentStatus.CLONING: "#eab308",
    DeploymentStatus.QUEUED: "#f97316",
    DeploymentStatus.FAILED: "#ef4444",
    DeploymentStatus.DESTROYING: "#94a3b8",
}


def relative_time(dt: datetime) -> str:
    now = datetime.now(timezone.utc)
    # Treat naive datetimes as UTC (SQLite stores without tz)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    delta = now - dt
    seconds = int(delta.total_seconds())
    if seconds < 0:
        return "just now"
    if seconds < 60:
        return f"{seconds}s ago"
    minutes = seconds // 60
    if minutes < 60:
        return f"{minutes}m ago"
    hours = minutes // 60
    if hours < 24:
        return f"{hours}h ago"
    days = hours // 24
    return f"{days}d ago"


def _render_row(dep: Deployment, repo: str) -> str:
    color = STATUS_COLORS.get(dep.status, "#94a3b8")
    status_label = dep.status.value.capitalize()

    if dep.url and dep.status == DeploymentStatus.RUNNING:
        url_cell = f'<a href="{escape(dep.url)}" target="_blank">{escape(dep.url)}</a>'
    else:
        url_cell = "&mdash;"

    pr_link = f"#{dep.pr_number}"
    if repo:
        pr_link = (
            f'<a href="https://github.com/{escape(repo)}/pull/{dep.pr_number}" '
            f'target="_blank">#{dep.pr_number}</a>'
        )

    error_attr = ""
    if dep.error_message:
        error_attr = f' title="{escape(dep.error_message)}"'

    return f"""<tr>
      <td>{pr_link}</td>
      <td><code>{escape(dep.branch or "")}</code></td>
      <td{error_attr}><span class="dot" style="background:{color}"></span> {status_label}</td>
      <td>{escape(dep.commit_sha[:7]) if dep.commit_sha else "&mdash;"}</td>
      <td>{url_cell}</td>
      <td>{relative_time(dep.updated_at)}</td>
    </tr>"""


def render_dashboard(deployments: list[Deployment], repo: str) -> str:
    if deployments:
        rows = "\n".join(_render_row(dep, repo) for dep in deployments)
    else:
        rows = '<tr><td colspan="6" class="empty">No preview environments</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="30">
  <title>SWEAT Review</title>
  <style>
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
           background: #0f172a; color: #e2e8f0; padding: 2rem; }}
    h1 {{ font-size: 1.25rem; font-weight: 600; margin-bottom: 1.5rem; color: #f8fafc; }}
    h1 span {{ color: #64748b; font-weight: 400; font-size: 0.875rem; margin-left: 0.5rem; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th {{ text-align: left; padding: 0.5rem 0.75rem; font-size: 0.75rem;
         text-transform: uppercase; letter-spacing: 0.05em; color: #64748b;
         border-bottom: 1px solid #1e293b; }}
    td {{ padding: 0.625rem 0.75rem; border-bottom: 1px solid #1e293b; font-size: 0.875rem; }}
    tr:hover {{ background: #1e293b; }}
    a {{ color: #38bdf8; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    code {{ background: #1e293b; padding: 0.125rem 0.375rem; border-radius: 0.25rem;
           font-size: 0.8125rem; }}
    .dot {{ display: inline-block; width: 8px; height: 8px; border-radius: 50%;
           margin-right: 0.375rem; vertical-align: middle; }}
    .empty {{ text-align: center; color: #64748b; padding: 2rem; }}
  </style>
</head>
<body>
  <h1>SWEAT Review <span>auto-refreshes every 30s</span></h1>
  <table>
    <thead>
      <tr>
        <th>PR</th>
        <th>Branch</th>
        <th>Status</th>
        <th>SHA</th>
        <th>Preview URL</th>
        <th>Updated</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> HTMLResponse:
    state = request.app.state.state_store
    settings = request.app.state.settings
    deployments = await state.get_all()
    html = render_dashboard(deployments, settings.github_repo)
    return HTMLResponse(content=html)

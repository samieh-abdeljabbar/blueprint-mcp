"""Detect stale nodes: old source files, lingering planned nodes, missing files."""

from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone, timedelta

from src.db import Database


async def find_stale(
    db: Database, days_threshold: int = 30, check_git: bool = True
) -> dict:
    """Scan all nodes for staleness indicators.

    Returns a dict with:
      - stale_files: nodes whose source_file hasn't been modified in > days_threshold days
      - stale_planned: nodes stuck in 'planned' status for > days_threshold days
      - missing_files: nodes whose source_file doesn't exist on disk
      - summary: human-readable one-liner
    """
    nodes = await db.get_all_nodes()
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=days_threshold)

    stale_files: list[dict] = []
    stale_planned: list[dict] = []
    missing_files: list[dict] = []

    for node in nodes:
        # --- Check source_file presence and freshness ---
        if node.source_file:
            if not os.path.exists(node.source_file):
                missing_files.append(
                    {
                        "node_id": node.id,
                        "node_name": node.name,
                        "expected_file": node.source_file,
                        "status": node.status.value
                        if hasattr(node.status, "value")
                        else str(node.status),
                    }
                )
            else:
                # Determine last modification time
                last_modified_dt = _get_last_modified(
                    node.source_file, check_git=check_git
                )
                if last_modified_dt is not None and last_modified_dt < cutoff:
                    days_ago = (now - last_modified_dt).days
                    stale_files.append(
                        {
                            "node_id": node.id,
                            "node_name": node.name,
                            "source_file": node.source_file,
                            "last_modified": last_modified_dt.isoformat(),
                            "days_ago": days_ago,
                        }
                    )

        # --- Check planned nodes that have been waiting too long ---
        status_val = (
            node.status.value
            if hasattr(node.status, "value")
            else str(node.status)
        )
        if status_val == "planned" and node.created_at:
            created_dt = _parse_datetime(node.created_at)
            if created_dt is not None and created_dt < cutoff:
                days_waiting = (now - created_dt).days
                stale_planned.append(
                    {
                        "node_id": node.id,
                        "node_name": node.name,
                        "planned_since": node.created_at,
                        "days_waiting": days_waiting,
                    }
                )

    return {
        "stale_files": stale_files,
        "stale_planned": stale_planned,
        "missing_files": missing_files,
        "summary": (
            f"{len(stale_files)} stale source files, "
            f"{len(stale_planned)} old planned nodes, "
            f"{len(missing_files)} missing files"
        ),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_last_modified(filepath: str, *, check_git: bool = True) -> datetime | None:
    """Return the last-modified time for *filepath*.

    If *check_git* is True, try ``git log`` first; fall back to
    ``os.path.getmtime`` on any failure.
    """
    if check_git:
        git_dt = _git_last_modified(filepath)
        if git_dt is not None:
            return git_dt

    # Fallback: filesystem mtime
    try:
        mtime = os.path.getmtime(filepath)
        return datetime.fromtimestamp(mtime, tz=timezone.utc)
    except OSError:
        return None


def _git_last_modified(filepath: str) -> datetime | None:
    """Ask git for the last commit date that touched *filepath*."""
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%ci", filepath],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0 or not result.stdout.strip():
            return None
        # git log --format=%ci produces e.g. "2024-06-01 14:30:00 +0000"
        raw = result.stdout.strip()
        # Replace the space before the timezone offset with nothing so
        # fromisoformat can handle it (Python 3.11+).
        # "2024-06-01 14:30:00 +0000" → "2024-06-01 14:30:00+00:00"
        parts = raw.rsplit(" ", 1)
        if len(parts) == 2:
            tz_str = parts[1]
            # Convert "+0000" → "+00:00"
            if len(tz_str) == 5 and (tz_str[0] in "+-"):
                tz_str = tz_str[:3] + ":" + tz_str[3:]
            iso_str = parts[0] + tz_str
        else:
            iso_str = raw
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def _parse_datetime(value: str) -> datetime | None:
    """Best-effort parse of an ISO 8601 datetime string."""
    try:
        dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError):
        return None

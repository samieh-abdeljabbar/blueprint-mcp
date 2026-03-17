"""Starlette HTTP server for the blueprint viewer."""

from __future__ import annotations

import argparse
import json
import os
import webbrowser

import uvicorn
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route, Mount
from starlette.staticfiles import StaticFiles

from src.db import Database, init_db

# Will be initialized on startup
_db: Database | None = None
_db_path: str = ".blueprint.db"


async def api_blueprint(request: Request) -> JSONResponse:
    status = request.query_params.get("status")
    type_ = request.query_params.get("type")
    root_only = request.query_params.get("root_only", "false").lower() == "true"
    data = await _db.get_blueprint(
        status_filter=status, type_filter=type_, root_only=root_only
    )
    return JSONResponse(data)


async def api_summary(request: Request) -> JSONResponse:
    data = await _db.get_blueprint_summary()
    return JSONResponse(data)


async def api_issues(request: Request) -> JSONResponse:
    try:
        from src.analyzer import analyze
        from src.models import IssueSeverity

        sev_str = request.query_params.get("severity")
        sev = IssueSeverity(sev_str) if sev_str else None
        issues = await analyze(_db, severity=sev)
        summary = {"critical": 0, "warning": 0, "info": 0}
        for i in issues:
            summary[i.severity.value] += 1
        return JSONResponse({
            "issues": [i.model_dump() for i in issues],
            "summary": summary,
        })
    except Exception as e:
        return JSONResponse({"error": str(e), "unavailable": True}, status_code=503)


async def on_startup():
    global _db
    _db = await init_db(_db_path)


async def on_shutdown():
    if _db:
        await _db.close()


def create_app(db_path: str = ".blueprint.db", dev: bool = False) -> Starlette:
    global _db_path
    _db_path = db_path

    routes = [
        Route("/api/blueprint", api_blueprint),
        Route("/api/summary", api_summary),
        Route("/api/issues", api_issues),
    ]

    # Serve static files from viewer/dist if built
    dist_dir = os.path.join(os.path.dirname(__file__), "..", "..", "viewer", "dist")
    dist_dir = os.path.abspath(dist_dir)
    if os.path.isdir(dist_dir):
        routes.append(
            Mount("/", app=StaticFiles(directory=dist_dir, html=True))
        )

    middleware = []
    if dev:
        middleware.append(
            Middleware(
                CORSMiddleware,
                allow_origins=["*"],
                allow_methods=["*"],
                allow_headers=["*"],
            )
        )

    return Starlette(
        routes=routes,
        on_startup=[on_startup],
        on_shutdown=[on_shutdown],
        middleware=middleware,
    )


def main():
    parser = argparse.ArgumentParser(description="Blueprint Viewer Server")
    parser.add_argument("--db-path", default=".blueprint.db", help="Path to blueprint DB")
    parser.add_argument("--port", type=int, default=3333, help="Port to listen on")
    parser.add_argument("--dev", action="store_true", help="Enable CORS for development")
    parser.add_argument("--open", action="store_true", help="Open browser on start")
    args = parser.parse_args()

    app = create_app(db_path=args.db_path, dev=args.dev)

    if args.open:
        import threading
        threading.Timer(1.0, lambda: webbrowser.open(f"http://localhost:{args.port}")).start()

    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="info")


if __name__ == "__main__":
    main()

"""CLI entry point for Blueprint MCP — init, sync, health, export."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys


async def _init_cmd(args: argparse.Namespace) -> None:
    db_path = os.path.join(os.getcwd(), ".blueprint.db")
    from src.db import init_db

    db = await init_db(db_path)
    await db.close()
    print(f"Initialized blueprint database at {db_path}")

    gitignore = os.path.join(os.getcwd(), ".gitignore")
    entry = ".blueprint.db"
    if os.path.exists(gitignore):
        with open(gitignore) as f:
            content = f.read()
        if entry not in content:
            with open(gitignore, "a") as f:
                f.write(f"\n{entry}\n")
            print("Added .blueprint.db to .gitignore")
    else:
        with open(gitignore, "w") as f:
            f.write(f"{entry}\n")
        print("Created .gitignore with .blueprint.db")


async def _install_hooks_cmd(args: argparse.Namespace) -> None:
    hooks_dir = os.path.join(os.getcwd(), ".git", "hooks")
    if not os.path.isdir(hooks_dir):
        print("Error: .git/hooks not found. Run from a git repository root.", file=sys.stderr)
        sys.exit(1)

    post_commit = os.path.join(hooks_dir, "post-commit")
    with open(post_commit, "w") as f:
        f.write("#!/bin/sh\nblueprint-mcp sync\n")
    os.chmod(post_commit, 0o755)

    pre_push = os.path.join(hooks_dir, "pre-push")
    with open(pre_push, "w") as f:
        f.write("#!/bin/sh\nblueprint-mcp health --fail-below 50\n")
    os.chmod(pre_push, 0o755)

    print("Installed post-commit and pre-push hooks.")


async def _sync_cmd(args: argparse.Namespace) -> None:
    from src.db import init_db
    from src.scanner import scan_project

    db = await init_db()
    try:
        result = await scan_project(".", db)
        print(json.dumps(result, indent=2, default=str))
    finally:
        await db.close()


async def _health_cmd(args: argparse.Namespace) -> None:
    from src.db import init_db
    from src.health import health_report

    db = await init_db()
    try:
        report = await health_report(db)
        print(json.dumps(report, indent=2, default=str))
        if args.fail_below is not None:
            score = report.get("overall_score", 0)
            if score < args.fail_below:
                sys.exit(1)
    finally:
        await db.close()


async def _export_cmd(args: argparse.Namespace) -> None:
    from src.db import init_db

    db = await init_db()
    try:
        fmt = args.format
        if fmt == "mermaid":
            from src.export import export_mermaid
            result = await export_mermaid(db)
        elif fmt == "json":
            from src.export import export_json
            result = await export_json(db)
        elif fmt == "csv":
            from src.export import export_csv
            result = await export_csv(db)
        elif fmt == "dot":
            from src.export import export_dot
            result = await export_dot(db)
        elif fmt == "markdown":
            from src.export import export_markdown
            result = await export_markdown(db)
        else:
            print(f"Unknown format: {fmt}", file=sys.stderr)
            sys.exit(1)
        print(result["content"])
    finally:
        await db.close()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="blueprint-mcp", description="Blueprint MCP CLI")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("init", help="Initialize blueprint database in current directory")
    sub.add_parser("install-hooks", help="Install git hooks for auto-sync")
    sub.add_parser("sync", help="Scan codebase and update blueprint")

    health_p = sub.add_parser("health", help="Print project health score")
    health_p.add_argument("--fail-below", type=int, default=None, help="Exit with code 1 if score is below N")

    export_p = sub.add_parser("export", help="Export blueprint to stdout")
    export_p.add_argument("--format", choices=["mermaid", "json", "csv", "dot", "markdown"], required=True)

    return parser


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    cmd_map = {
        "init": _init_cmd,
        "install-hooks": _install_hooks_cmd,
        "sync": _sync_cmd,
        "health": _health_cmd,
        "export": _export_cmd,
    }
    asyncio.run(cmd_map[args.command](args))


if __name__ == "__main__":
    main()

"""Command-line interface for Reddit Copilot."""

from __future__ import annotations

import argparse
import logging
import sys
import threading
from pathlib import Path

from rcopilot.config import load_config, write_example_config
from rcopilot.pipeline import (
    approve_draft,
    draft_pending,
    fetch_and_store,
    post_approved,
    reject_draft,
)
from rcopilot.store import Store

ENV_EXAMPLE = """REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_REFRESH_TOKEN=
LLM_API_KEY=
# OAuth stores REDDIT_REFRESH_TOKEN after Connect Reddit.
# Password grant is optional fallback: REDDIT_USERNAME / REDDIT_PASSWORD
"""


def _default_config_path() -> Path:
    return Path("config.yaml")


def _load_store(config_path: Path | None = None) -> tuple:
    path = config_path or _default_config_path()
    config = load_config(path)
    store = Store(config.db_path)
    return config, store


def cmd_init(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    env_example_path = Path(args.env_example)

    if config_path.exists():
        print(f"Config already exists: {config_path}")
    else:
        write_example_config(config_path)
        print(f"Created {config_path}")

    env_example_path.write_text(ENV_EXAMPLE, encoding="utf-8")
    print(f"Wrote {env_example_path}")

    print()
    print("Next steps:")
    print("  1. Create a Reddit web app with redirect URI:")
    print("     http://127.0.0.1:8000/api/oauth/callback")
    print("  2. rcopilot serve")
    print("  3. Open http://127.0.0.1:3000 and finish onboarding")
    return 0


def cmd_fetch(args: argparse.Namespace) -> int:
    config, store = _load_store(Path(args.config) if args.config else None)
    count = fetch_and_store(config, store, config_path=Path(args.config) if args.config else _default_config_path())
    print(f"Fetched and stored {count} post(s)")
    return 0


def cmd_draft(args: argparse.Namespace) -> int:
    config, store = _load_store(Path(args.config) if args.config else None)
    count = draft_pending(config, store, account_name=args.account)
    print(f"Generated {count} draft(s)")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    import uvicorn

    from rcopilot.api import create_app
    from rcopilot.ui_server import (
        ensure_web_deps,
        resolve_web_dir,
        start_ui,
        stop_ui,
    )
    from rcopilot.worker import run_forever

    config_path = str(args.config) if args.config else None
    stop_event = threading.Event()
    worker_thread: threading.Thread | None = None
    ui_proc = None

    if args.with_worker:
        config = load_config(config_path or "config.yaml")
        store = Store(config.db_path)
        store.ensure_schema()
        worker_thread = threading.Thread(
            target=run_forever,
            args=(config, store, stop_event, config_path or "config.yaml"),
            daemon=True,
            name="rcopilot-worker",
        )
        worker_thread.start()
        print("Worker thread started")

    if not args.api_only:
        web_dir = resolve_web_dir()
        if web_dir is None:
            print(
                "Warning: web/ not found — starting API only. "
                "Clone the full repo or use --api-only.",
                file=sys.stderr,
            )
        else:
            try:
                ensure_web_deps(web_dir, skip_install=args.no_install)
                ui_proc = start_ui(
                    web_dir,
                    api_host=args.host,
                    api_port=args.port,
                    ui_port=args.ui_port,
                )
            except Exception as exc:
                print(f"Error starting UI: {exc}", file=sys.stderr)
                return 1
            print(f"Open http://127.0.0.1:{args.ui_port} to use Reddit Copilot")

    app = create_app(config_path=config_path)
    try:
        uvicorn.run(app, host=args.host, port=args.port, log_level="info")
    finally:
        stop_ui(ui_proc)
        if worker_thread is not None:
            stop_event.set()
            worker_thread.join(timeout=5)
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    from rcopilot.worker import run_forever

    config, store = _load_store(Path(args.config) if args.config else None)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    print(f"Starting worker (interval={config.worker.interval_seconds}s)")
    run_forever(config, store, config_path=str(Path(args.config) if args.config else _default_config_path()))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    print("`rcopilot review` is deprecated.")
    print("Use: rcopilot serve")
    print("Or for API only: rcopilot serve --api-only")
    return 0


def cmd_post(args: argparse.Namespace) -> int:
    config, store = _load_store(Path(args.config) if args.config else None)
    results = post_approved(config, store, draft_id=args.id)
    posted = sum(1 for item in results if item.get("ok"))
    if args.id is not None:
        if posted:
            print(f"Posted draft {args.id}")
        else:
            detail = results[0].get("error") if results else "not approved or already posted"
            print(f"Draft {args.id} was not posted: {detail}")
    else:
        print(f"Posted {posted} approved draft(s)")
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    _, store = _load_store(Path(args.config) if args.config else None)
    approve_draft(store, args.id)
    print(f"Approved draft {args.id}")
    return 0


def cmd_reject(args: argparse.Namespace) -> int:
    _, store = _load_store(Path(args.config) if args.config else None)
    reject_draft(store, args.id)
    print(f"Rejected draft {args.id}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="rcopilot",
        description="Human-in-the-loop Reddit reply drafter",
    )
    parser.add_argument(
        "--config",
        "-c",
        default="config.yaml",
        help="Path to config.yaml (default: config.yaml)",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Create config.yaml and .env.example")
    init_parser.add_argument(
        "--env-example",
        default=".env.example",
        help="Path for .env.example (default: .env.example)",
    )
    init_parser.set_defaults(func=cmd_init)

    fetch_parser = subparsers.add_parser("fetch", help="Fetch posts and store them")
    fetch_parser.set_defaults(func=cmd_fetch)

    draft_parser = subparsers.add_parser("draft", help="Generate drafts for pending posts")
    draft_parser.add_argument(
        "--account",
        metavar="NAME",
        help="Account name from config (default: first account)",
    )
    draft_parser.set_defaults(func=cmd_draft)

    serve_parser = subparsers.add_parser(
        "serve",
        help="Start API + Next.js UI (use --api-only for the API alone)",
    )
    serve_parser.add_argument("--host", default="127.0.0.1", help="API bind host (default: 127.0.0.1)")
    serve_parser.add_argument("--port", type=int, default=8000, help="API bind port (default: 8000)")
    serve_parser.add_argument(
        "--ui-port",
        type=int,
        default=3000,
        help="Next.js UI port (default: 3000)",
    )
    serve_parser.add_argument(
        "--api-only",
        action="store_true",
        help="Start FastAPI only (for local frontend development)",
    )
    serve_parser.add_argument(
        "--no-install",
        action="store_true",
        help="Do not run npm install if web/node_modules is missing",
    )
    serve_parser.add_argument(
        "--with-worker",
        action="store_true",
        help="Run autonomous worker loop in a background thread",
    )
    serve_parser.set_defaults(func=cmd_serve)

    run_parser = subparsers.add_parser("run", help="Run worker loop (fetch, draft, post due schedules)")
    run_parser.set_defaults(func=cmd_run)

    review_parser = subparsers.add_parser("review", help="(deprecated) Use rcopilot serve")
    review_parser.set_defaults(func=cmd_review)

    post_parser = subparsers.add_parser("post", help="Post approved drafts to Reddit")
    post_parser.add_argument("--id", type=int, metavar="DRAFT_ID", help="Post a single draft by id")
    post_parser.set_defaults(func=cmd_post)

    approve_parser = subparsers.add_parser("approve", help="Approve a draft (CLI)")
    approve_parser.add_argument("--id", type=int, required=True, metavar="N", help="Draft id")
    approve_parser.set_defaults(func=cmd_approve)

    reject_parser = subparsers.add_parser("reject", help="Reject a draft (CLI)")
    reject_parser.add_argument("--id", type=int, required=True, metavar="N", help="Draft id")
    reject_parser.set_defaults(func=cmd_reject)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except NotImplementedError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

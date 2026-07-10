"""Command-line entry point.

Two subcommands keep the concerns separate:

    python main.py process [--source PATH] [--camera-id ID]
        Run the detection pipeline over a video / RTSP source.

    python main.py serve [--host H] [--port P]
        Start the FastAPI REST API + dashboard.

Both share the same configuration and database, so events written by
``process`` appear immediately in ``serve``.
"""

from __future__ import annotations

import argparse
import sys

from config import settings
from logging_utils import get_logger

logger = get_logger("main")


def _cmd_process(args: argparse.Namespace) -> int:
    """Run the detection pipeline."""
    # Imported lazily so `serve` need not load heavy CV/ML deps.
    from pipeline import Pipeline

    pipeline = Pipeline(source=args.source, camera_id=args.camera_id)
    count = pipeline.run()
    logger.info("Done. %d event(s) recorded.", count)
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    """Start the API server."""
    import uvicorn

    uvicorn.run(
        "api.routes:app",
        host=args.host,
        port=args.port,
        reload=False,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Smart Litter Detection System")
    sub = parser.add_subparsers(dest="command", required=True)

    p_process = sub.add_parser("process", help="Run detection over a video/RTSP source")
    p_process.add_argument(
        "--source", default=None, help="MP4 path or RTSP URL (default: from .env)"
    )
    p_process.add_argument(
        "--camera-id", default=None, help="Camera identifier (default: from .env)"
    )
    p_process.set_defaults(func=_cmd_process)

    p_serve = sub.add_parser("serve", help="Start the REST API + dashboard")
    p_serve.add_argument("--host", default=settings.api_host)
    p_serve.add_argument("--port", type=int, default=settings.api_port)
    p_serve.set_defaults(func=_cmd_serve)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

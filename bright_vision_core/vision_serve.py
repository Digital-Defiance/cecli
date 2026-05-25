"""HTTP API server for aider-vision-core."""

from __future__ import annotations

import argparse
import os
import sys


def run(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="aider-vision-core HTTP API server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8741)
    parser.add_argument("--reload", action="store_true", help="Reload on code changes")
    parser.add_argument(
        "--generate-token",
        action="store_true",
        help="Print a random token suitable for AIDER_VISION_TOKEN and exit",
    )
    args = parser.parse_args(argv)

    from bright_vision_core.http_auth import (
        configure_auth,
        generate_token,
        startup_message,
        validate_listen_address,
    )

    if args.generate_token:
        print(generate_token())
        return

    validate_listen_address(args.host)
    configure_auth(args.host)

    from bright_vision_core.vision_runtime import configure_vision_runtime

    if os.environ.get("BRIGHT_VISION_HEADLESS") == "1" or os.environ.get("AIDER_VISION_HEADLESS") == "1":
        configure_vision_runtime()
    else:
        print(startup_message(args.host))

    try:
        import uvicorn
    except ImportError:
        print("uvicorn is required: pip install uvicorn", file=sys.stderr)
        sys.exit(1)

    uvicorn.run(
        "bright_vision_core.http_api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        log_level="warning",
        access_log=not os.environ.get("AIDER_VISION_HEADLESS"),
    )

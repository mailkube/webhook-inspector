# SPDX-License-Identifier: Apache-2.0
"""Console entry point — ``webhook-inspector`` and ``python -m webhook-inspector``.

Reads configuration from the environment (``PORT``, ``USE_TUNNEL``, ``WEBHOOK_SECRET``);
CLI flags override the relevant env vars before the app is imported.
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    """Parse CLI flags, apply env overrides, and run the server with uvicorn."""
    parser = argparse.ArgumentParser(
        prog="webhook-inspector",
        description="Local receiver for testing mailkube webhooks (cloudflared tunnel).",
    )
    parser.add_argument("--host", default=None, help="Address to bind (default: $HOST or 127.0.0.1).")
    parser.add_argument("--port", type=int, default=None, help="Port to listen on (default: $PORT or 5000).")
    parser.add_argument("--no-tunnel", action="store_true", help="Serve locally only; do not open a tunnel.")
    parser.add_argument(
        "--tunnel-name",
        default=None,
        metavar="NAME",
        help=(
            "Use a Cloudflare named tunnel instead of an ephemeral quick tunnel. "
            "NAME is the tunnel name created with `cloudflared tunnel create`. "
            "Requires `cloudflared login` and a DNS route configured via "
            "`cloudflared tunnel route dns NAME your.hostname.com`. "
            "Override via $TUNNEL_NAME."
        ),
    )
    args = parser.parse_args()

    if args.host is not None:
        os.environ["HOST"] = args.host
    if args.port is not None:
        os.environ["PORT"] = str(args.port)
    if args.no_tunnel:
        os.environ["USE_TUNNEL"] = "false"
    if args.tunnel_name is not None:
        os.environ["TUNNEL_NAME"] = args.tunnel_name

    # Imported after env overrides so module-level config picks them up.
    import uvicorn

    from webhook_inspector.app import HOST, PORT, app

    uvicorn.run(app, host=HOST, port=PORT)


if __name__ == "__main__":
    main()

# SPDX-License-Identifier: Apache-2.0
"""In-process ngrok tunnel management via the official ``ngrok`` SDK.

The SDK embeds the tunnel in this process — there is no separate ngrok binary or CLI
subprocess. The top-level ``ngrok.forward`` / ``ngrok.disconnect`` calls are synchronous
(they drive ngrok's own runtime), so these helpers are plain sync functions called directly
from the app's async lifespan. ``ngrok`` is imported lazily so the package — and its tests —
load without the native dependency when tunnelling is disabled (``--no-tunnel`` /
``USE_NGROK=false``).
"""

from __future__ import annotations

from typing import Any


def open_tunnel(port: int) -> Any | None:
    """Open an ngrok tunnel to ``port`` and print the public URL.

    Returns the listener (so it can be torn down on shutdown), or ``None`` if the tunnel
    could not be established — in which case the server still runs locally.
    """
    import ngrok

    try:
        listener = ngrok.forward(addr=port, authtoken_from_env=True)
    except Exception as exc:  # noqa: BLE001 — surface setup issues without crashing the server
        print(f"\n⚠️  ngrok tunnel failed: {exc}")
        print("   Set NGROK_AUTHTOKEN (free: https://dashboard.ngrok.com/get-started/your-authtoken)")
        print("   or run with --no-tunnel / USE_NGROK=false to serve locally only.\n")
        return None
    _print_banner(listener.url())
    return listener


def close_tunnel(listener: Any | None) -> None:
    """Best-effort teardown of a tunnel opened by :func:`open_tunnel`."""
    if listener is None:
        return
    import ngrok

    try:
        ngrok.disconnect(listener.url())
    except Exception as exc:  # noqa: BLE001 — shutdown must never raise
        print(f"⚠️  ngrok disconnect failed (ignored): {exc}")


def _print_banner(url: str) -> None:
    print("\n" + "=" * 66)
    print(f"  Public URL : {url}")
    print("  Use it as your webhook endpoint_url (the https:// URL above).")
    print("  Inspector  : http://localhost:4040")
    print("=" * 66 + "\n")

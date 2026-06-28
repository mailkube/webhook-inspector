# SPDX-License-Identifier: Apache-2.0
"""Quick-tunnel management via the official ``cloudflared`` binary.

cloudflared has no first-party Python SDK, so the tunnel is an out-of-process subprocess:
``cloudflared tunnel --url http://localhost:<port>`` opens an account-less *quick tunnel* and
logs the assigned ``*.trycloudflare.com`` URL to stderr. These helpers spawn it, scrape that URL,
keep stderr drained (so cloudflared's continuous logging never blocks on a full pipe), and tear
the process down on shutdown. They are async coroutines awaited from the app's async lifespan.
"""

from __future__ import annotations

import asyncio
import re
import shutil
from dataclasses import dataclass

_URL_RE = re.compile(rb"https://[-a-z0-9]+\.trycloudflare\.com")
_URL_TIMEOUT = 30.0  # cloudflared takes a few seconds to provision the quick tunnel
_INSTALL_HINT = "https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"


@dataclass
class _Tunnel:
    """A running cloudflared quick tunnel and its public URL."""

    process: asyncio.subprocess.Process
    _url: str
    _drain: asyncio.Task[None]  # keeps stderr drained so cloudflared never blocks on a full pipe

    def url(self) -> str:
        """Return the public ``https://*.trycloudflare.com`` URL."""
        return self._url


async def open_tunnel(port: int, protocol: str = "http2") -> _Tunnel | None:
    """Open a cloudflared quick tunnel to ``port`` and print the public URL.

    ``protocol`` is cloudflared's edge transport. The default ``http2`` runs over outbound
    TCP 443; the cloudflared default (``quic``) needs outbound UDP 7844, which many networks
    block — leaving the tunnel registered but unreachable. Override via ``TUNNEL_PROTOCOL``.

    Returns the tunnel (so it can be torn down on shutdown), or ``None`` if it could not be
    established — in which case the server still runs locally.
    """
    if shutil.which("cloudflared") is None:
        print(
            "\n⚠️  cloudflared not found on PATH."
            f"\n   Install it ({_INSTALL_HINT}) — e.g. `brew install cloudflared`,"
            "\n   or run with --no-tunnel / USE_TUNNEL=false to serve locally only.\n",
            flush=True,
        )
        return None

    process = await asyncio.create_subprocess_exec(
        "cloudflared",
        "tunnel",
        "--protocol",
        protocol,
        "--url",
        # 127.0.0.1, not "localhost": the latter also resolves to IPv6 ::1, where the server
        # isn't listening (uvicorn binds IPv4) — and on macOS ::1:5000 is AirPlay's by default.
        f"http://127.0.0.1:{port}",
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stderr is not None  # stderr=PIPE guarantees a reader (narrows for mypy)

    try:
        url = await asyncio.wait_for(_read_url(process.stderr), _URL_TIMEOUT)
    except (TimeoutError, asyncio.TimeoutError):
        print(
            "\n⚠️  cloudflared tunnel timed out before reporting a URL."
            "\n   Serving locally only; retry or run with --no-tunnel.\n",
            flush=True,
        )
        await _terminate(process)
        return None

    if url is None:  # stderr closed without ever emitting a URL (cloudflared exited early)
        print(
            "\n⚠️  cloudflared exited before reporting a URL."
            "\n   Serving locally only; retry or run with --no-tunnel.\n",
            flush=True,
        )
        await _terminate(process)
        return None

    drain = asyncio.create_task(_drain(process.stderr))
    _print_banner(url)
    return _Tunnel(process, url, drain)


async def close_tunnel(tunnel: _Tunnel | None) -> None:
    """Best-effort teardown of a tunnel opened by :func:`open_tunnel`."""
    if tunnel is None:
        return
    tunnel._drain.cancel()
    await _terminate(tunnel.process)


async def _read_url(stream: asyncio.StreamReader) -> str | None:
    """Read stderr lines until the quick-tunnel URL appears; ``None`` if the stream ends first."""
    while True:
        line = await stream.readline()
        if not line:  # EOF — cloudflared closed stderr without emitting a URL
            return None
        match = _URL_RE.search(line)
        if match:
            return match.group(0).decode()


async def _drain(stream: asyncio.StreamReader) -> None:
    """Discard the rest of cloudflared's stderr so its pipe buffer never fills and deadlocks."""
    try:
        while await stream.readline():
            pass
    except asyncio.CancelledError:
        pass


async def _terminate(process: asyncio.subprocess.Process) -> None:
    """Terminate ``process``, escalating to kill if it does not exit promptly. Never raises."""
    if process.returncode is not None:
        return
    try:
        process.terminate()
        await asyncio.wait_for(process.wait(), timeout=5)
    except (TimeoutError, asyncio.TimeoutError):
        process.kill()
    except ProcessLookupError:
        pass


def _print_banner(url: str) -> None:
    print(
        "\n"
        + "=" * 66
        + f"\n  Public URL : {url}"
        + "\n  Use it as your webhook endpoint_url (the https:// URL above)."
        + "\n"
        + "=" * 66
        + "\n",
        flush=True,  # stdout is block-buffered when piped/redirected; flush so the URL shows now
    )

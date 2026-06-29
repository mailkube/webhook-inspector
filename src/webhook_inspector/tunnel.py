# SPDX-License-Identifier: Apache-2.0
"""Tunnel management via the official ``cloudflared`` binary.

Two modes are supported:

* **Quick tunnel** (default, no account required): ``cloudflared tunnel --url http://localhost:<port>``
  opens an account-less tunnel and logs an ephemeral ``*.trycloudflare.com`` URL to stderr.
  These helpers scrape that URL from stderr output.

* **Named tunnel** (fixed URL, Cloudflare account required): ``cloudflared tunnel run --url
  http://localhost:<port> <tunnel-name>`` uses a pre-created named tunnel whose DNS hostname was
  configured with ``cloudflared tunnel route dns``. The public URL is fixed and known in advance,
  so no URL scraping is needed.

In both modes the process is kept alive and torn down on shutdown. stderr is continuously drained
so cloudflared's logging never blocks on a full pipe.
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
    """A running cloudflared tunnel process."""

    process: asyncio.subprocess.Process
    _drain: asyncio.Task[None]  # keeps stderr drained so cloudflared never blocks on a full pipe


async def open_tunnel(port: int, protocol: str = "http2", tunnel_name: str | None = None) -> _Tunnel | None:
    """Open a cloudflared tunnel to ``port`` and print the public URL.

    When ``tunnel_name`` is ``None`` (default), opens an account-less quick tunnel and scrapes
    the assigned ``*.trycloudflare.com`` URL from stderr.

    When ``tunnel_name`` is provided, runs the named tunnel (``cloudflared tunnel run``) whose
    DNS hostname was pre-configured with ``cloudflared tunnel route dns``. The public URL is
    already fixed, so no scraping is needed — a reminder banner is printed instead.

    ``protocol`` is cloudflared's edge transport for quick tunnels. The default ``http2`` runs
    over outbound TCP 443; ``quic`` needs outbound UDP 7844, which many networks block.
    Override via ``TUNNEL_PROTOCOL``.

    Returns the tunnel on success, or ``None`` — in which case the server still runs locally.
    """
    if shutil.which("cloudflared") is None:
        print(
            "\n⚠️  cloudflared not found on PATH."
            f"\n   Install it ({_INSTALL_HINT}) — e.g. `brew install cloudflared`,"
            "\n   or run with --no-tunnel / USE_TUNNEL=false to serve locally only.\n",
            flush=True,
        )
        return None

    if tunnel_name is not None:
        return await _open_named_tunnel(port, tunnel_name)
    return await _open_quick_tunnel(port, protocol)


async def _open_quick_tunnel(port: int, protocol: str) -> _Tunnel | None:
    """Spawn a cloudflared quick tunnel and scrape its ephemeral URL from stderr."""
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
    _print_quick_banner(url)
    return _Tunnel(process, drain)


async def _open_named_tunnel(port: int, tunnel_name: str) -> _Tunnel | None:
    """Spawn a cloudflared named tunnel (fixed URL, requires ``cloudflared login``)."""
    process = await asyncio.create_subprocess_exec(
        "cloudflared",
        "tunnel",
        "run",
        "--url",
        f"http://127.0.0.1:{port}",
        tunnel_name,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.PIPE,
    )
    assert process.stderr is not None

    # Named tunnels don't emit a URL — they use the hostname configured via
    # ``cloudflared tunnel route dns``. Wait briefly to catch immediate startup failures
    # (bad tunnel name, not logged in, etc.) before declaring success.
    try:
        exited = await asyncio.wait_for(process.wait(), timeout=3.0)
    except (TimeoutError, asyncio.TimeoutError):
        exited = None  # still running — good

    if exited is not None:
        print(
            f"\n⚠️  cloudflared named tunnel '{tunnel_name}' exited immediately (code {exited})."
            "\n   Check that you are logged in (`cloudflared login`) and the tunnel name is correct."
            "\n   Serving locally only.\n",
            flush=True,
        )
        return None

    drain = asyncio.create_task(_drain(process.stderr))
    _print_named_banner(tunnel_name)
    return _Tunnel(process, drain)


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


def _print_quick_banner(url: str) -> None:
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


def _print_named_banner(tunnel_name: str) -> None:
    print(
        "\n"
        + "=" * 66
        + f"\n  Named tunnel : {tunnel_name}"
        + "\n  Use your configured DNS hostname as the webhook endpoint_url."
        + "\n"
        + "=" * 66
        + "\n",
        flush=True,
    )

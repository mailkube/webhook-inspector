# Project Rules

`webhook-inspector` is a small public (Apache-2.0) FastAPI tool for testing mailkube webhooks
locally over a cloudflared quick tunnel. Load the relevant rule file from `.rules/` based on
the task.

## Rule Index

| Rule File | Load When |
|---|---|
| `.rules/WEBHOOK_CONTRACT.md` | Touching the verification handshake or `X-Webhook-Sig` signature logic — it must stay byte-compatible with the mailkube API (the source of truth). |

## Key Conventions (always apply)

- **Tooling is `uv`** (not Poetry): `uv sync`, `uv run …`; deps in PEP 621 `[project]` +
  `[dependency-groups]`; `uv.lock` committed. Run paths are `uv run webhook-inspector` or Docker.
- **No packaging/releases** — this is a run-it-locally tool; never add publish/release workflows.
- **`src/` layout** — code lives in `src/webhook_inspector/`; tests in `tests/`.
- **Ruff** for lint **and** format; **line length ≤ 120**; **mypy strict** on `src`.
- **Type-annotate** every function; `from __future__ import annotations` at the top of modules.
- **SPDX header** (`# SPDX-License-Identifier: Apache-2.0`) on every source file.
- **Conventional Commits** for PR titles (squash-merged) — for readable history only; nothing is
  released.
- **No secrets in the repo** — `WEBHOOK_SECRET` lives in git-ignored `.env`
  (and is excluded from the Docker image via `.dockerignore`).
- **The tunnel is an external binary** — `tunnel.py` shells out to the `cloudflared` binary via
  `asyncio.subprocess` (stdlib only); there is no Python tunnel dependency to import.
- **Public-repo etiquette** — keep `README`, `CONTRIBUTING`, and `SECURITY` current with
  user-visible changes.

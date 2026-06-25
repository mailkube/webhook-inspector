# Contributing to webhook-inspector

Thanks for helping improve **webhook-inspector** — a small tool that helps developers test
[mailkube](https://mailkube.com) webhooks locally. Contributions of all kinds are welcome:
bug reports, fixes, docs, and features.

By contributing you agree that your contributions are licensed under the project's
[Apache License 2.0](LICENSE) (inbound = outbound). **No CLA and no sign-off are required.**
Please also read our [Code of Conduct](CODE_OF_CONDUCT.md).

## Development setup

Requires [uv](https://docs.astral.sh/uv/) (and Docker, optionally, to test the container path).

```bash
git clone https://github.com/mailkube/webhook-inspector
cd webhook-inspector

uv sync                                              # create the env + install everything
uv run pre-commit install                            # ruff + format hooks
uv run pre-commit install --hook-type commit-msg     # Conventional Commits hook
```

Run the tool locally:

```bash
uv run webhook-inspector --no-tunnel    # serve locally without a tunnel
uv run webhook-inspector                # open an ngrok tunnel (needs NGROK_AUTHTOKEN)
```

## Quality gates

Every change must pass the same checks CI runs:

```bash
uv run ruff check .            # lint
uv run ruff format --check .   # formatting
uv run mypy src                # types
uv run pytest                  # tests (coverage gate: 90%)
```

`uv run pre-commit run --all-files` runs the lint/format hooks in one shot.

## Commit & PR conventions

This project follows **[Conventional Commits](https://www.conventionalcommits.org/)** for a
readable history (a CI check enforces the PR title, and PRs are **squash-merged** using it).
This repo does **not** publish packages or cut releases — Conventional Commits are purely for
clarity, not version bumps.

Suggested scopes: `server`, `tunnel`, `docker`, `ci`, `deps`, `docs`.

```
feat(server): support a custom response status on deliveries
fix(tunnel): handle a missing NGROK_AUTHTOKEN gracefully
docs: clarify the verification handshake
```

## Reporting bugs / requesting features

Open an issue using the templates. For **security vulnerabilities**, do not open a public
issue — follow [SECURITY.md](SECURITY.md) instead.

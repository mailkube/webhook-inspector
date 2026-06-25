<!--
PR titles MUST follow Conventional Commits (e.g. `fix(tunnel): ...`) — it is CI-enforced and
becomes the squash-merge commit message. Only feat/fix/perf trigger a release.
-->

## What

<!-- Describe the change in 1–2 sentences. -->

## Why

<!-- The user-visible problem this solves, or the motivation. -->

## Checklist

- [ ] `ruff check .` and `ruff format --check .` pass
- [ ] `mypy src` passes
- [ ] `pytest` passes (added/updated tests where relevant)
- [ ] Docs updated (`README.md` / `CHANGELOG.md`) if user-visible
- [ ] PR title follows Conventional Commits

## Notes

<!-- Optional: screenshots, follow-ups, breaking-change details. -->

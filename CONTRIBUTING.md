# Contributing to MediaMind

Thanks for your interest in contributing! MediaMind is an early-stage
open-source project (v0.1) — help of all kinds is welcome, from bug reports
to code.

## Not a coder? You can still help

- **Report a bug or suggest a feature** by opening a
  [GitHub Issue](../../issues/new/choose) — pick the template that fits.
  You don't need to know why something broke, just what you did and what
  happened.
- Screenshots and steps to reproduce are the most useful thing you can
  include.

## Ways to contribute code

1. Check open [Issues](../../issues) — anything unassigned is fair game.
   For larger changes, open an issue first to discuss the approach before
   writing code.
2. Fork the repo and create a branch off `main`.
3. Follow the conventions in [`CLAUDE.md`](CLAUDE.md) (engineering rules,
   safety invariants, code style) — it's the project's own guidance doc and
   applies to human contributors too.
4. Make sure the checks in `.github/workflows/ci.yml` pass locally before
   opening a PR:
   ```bash
   cd backend && python -m pytest -m "not integration"
   cd app && npm run typecheck && npm run build
   ```
5. Open a pull request against `main` with a clear description of what
   changed and why.

## Project status

MediaMind is at v0.1. Duplicate Detection is the most tested feature;
Facial Recognition is functional but marked **Beta** in the UI — expect
rougher edges there. See [`docs/USER_GUIDE.md`](docs/USER_GUIDE.md) for the
current feature list and [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md)
for architecture.

## Safety rules

This app operates on real user files. Any change touching file operations
(move/copy/delete) must preserve the safety invariants in `CLAUDE.md`
(copy-then-delete, audit trail, dry-run support, review-before-commit).
These are non-negotiable — PRs that weaken them won't be merged.

## Code of conduct

Be respectful and constructive. Disagreements about code are fine;
personal attacks aren't.

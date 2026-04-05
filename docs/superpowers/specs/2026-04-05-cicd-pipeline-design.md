# CI/CD Pipeline for klaude — Design Spec

> Mirror nam-website's proven CI/CD patterns for klaude.

## Context

klaude is a Python CLI tool installed on a Hetzner VPS via `uv tool install` from GitHub. It runs on-demand — nam-website's Celery worker spawns `klaude` via subprocess per mission. There is no long-lived klaude service. Deploying a new version means upgrading the tool binary; the next Celery invocation picks up the new version automatically.

Currently klaude has zero CI/CD: no automated testing, no deploy pipeline, no branch protection.

## Components

### 1. CI Workflow — `.github/workflows/ci.yml`

**Triggers:** push to `main`, all pull requests.

Single job (Python-only, no frontend):

1. `actions/checkout@v4`
2. `actions/setup-python@v6` — Python 3.12
3. `astral-sh/setup-uv@v7` — uv with cache
4. `uv sync` — install dependencies
5. `ruff check` — lint
6. `ruff format --check` — format check
7. `uv run pytest tests/ -v` — run tests

### 2. Deploy Workflow — `.github/workflows/deploy.yml`

**Triggers:** `workflow_run` — runs only after CI succeeds on push to `main`.

**Gate:** `if: github.event.workflow_run.conclusion == 'success' && github.event.workflow_run.event == 'push'`

Steps:
1. SSH into Hetzner server using `appleboy/ssh-action@v1`
2. Run: `/home/klaude/.local/bin/uv tool upgrade klaude`

No restart needed — klaude is a CLI tool, not a service.

**Secrets:**
- `KLAUDE_DEPLOY_HOST` — server IP
- `KLAUDE_DEPLOY_SSH_KEY` — private SSH key (ed25519) for `klaude` user

**SSH user:** `klaude` directly (already sandboxed via iptables/restricted home). No sudo needed.

### 3. Dependabot — `.github/dependabot.yml`

Weekly checks for:
- `pip` — Python dependency updates
- `github-actions` — action version updates

### 4. Dependabot Auto-merge — `.github/workflows/dependabot-automerge.yml`

Automatically enables `--auto --squash` merge on dependabot PRs. Rebases open dependabot PRs when main updates.

### 5. Pre-commit Hooks — `.pre-commit-config.yaml`

Local quality gate:
- `ruff` — lint with `--fix`
- `ruff-format` — format check

Uses `https://github.com/astral-sh/ruff-pre-commit`.

### 6. Branch Protection (manual GitHub settings)

Applied to `main` branch:
- Require pull request before merging (no direct push)
- Require CI status checks to pass before merge
- Require branches to be up to date before merging
- Squash-merge only (no merge commits or rebase)
- Auto-delete head branches after merge

## One-time Server Setup

1. Generate SSH key pair on the server:
   ```bash
   sudo -u klaude ssh-keygen -t ed25519 -f /home/klaude/.ssh/github_deploy -N ""
   ```
2. Add public key to authorized_keys:
   ```bash
   sudo -u klaude bash -c 'cat /home/klaude/.ssh/github_deploy.pub >> /home/klaude/.ssh/authorized_keys'
   ```
3. Add repo secrets in GitHub (Settings > Secrets and variables > Actions):
   - `KLAUDE_DEPLOY_HOST` = server IP
   - `KLAUDE_DEPLOY_SSH_KEY` = contents of `/home/klaude/.ssh/github_deploy` (private key)

## What does NOT change

- `Makefile` — already has `test`, `lint`, `format` targets. Unchanged.
- `pyproject.toml` — already has ruff config and pytest. Unchanged.
- nam-website — no changes needed on that side.

## Scope exclusions

- Docker/containerization — not needed, klaude is a CLI tool
- Systemd service — klaude is on-demand, not a daemon
- Caddy/reverse proxy — klaude has no web interface
- Release versioning/PyPI publishing — not needed yet

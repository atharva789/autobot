---
description: How the app and docs are expected to be deployed, with current GitHub and GitBook notes.
---

# Deployment

## Product app

The product is split into:

- FastAPI backend in `apps/api/`,
- Next.js frontend in `apps/web/`,
- optional Electron desktop shell in `apps/web/electron/`.

The backend should be launched as:

```bash
uvicorn apps.api.app:app --host 127.0.0.1 --port 8000
```

The frontend should be built from `apps/web`:

```bash
npm run build
```

Deployment-specific hosting configuration should keep the same API contracts used locally.

## Documentation deployment

Robodex is GitBook source under:

```text
docs/
```

The repository root contains:

```text
.gitbook.yaml
```

which points GitBook to `docs/`.

If the GitBook project is connected to this GitHub repository through Git Sync, publishing the branch that GitBook tracks is enough for GitBook to ingest the docs.

## GitHub repository link

The repository README should link to the published docs URL once the docs are published or synced.

If GitBook returns a share URL or custom site URL, use that. If the GitBook project is still private or not connected, link to the local `docs/README.md` path temporarily and replace it after sync is configured.

## Deployment caveats

The installed `gitbook` CLI is integration-oriented. Its `publish` command publishes GitBook integrations, not a legacy static docs build. Do not assume `gitbook build` exists in this CLI version.


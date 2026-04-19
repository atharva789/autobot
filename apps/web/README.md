# Web App

This is the Next.js frontend for the IL Ideation workspace.

For the full project overview, setup, and architecture, start at the repo root:
- [../../README.md](../../README.md)

## Local run

```bash
cd apps/web
npm install
npm run dev
```

The frontend expects the FastAPI backend to be running and `NEXT_PUBLIC_API_URL` to point at it.

Default local URL:
- `http://localhost:3000`

## Notes

- The workspace defaults to backend-driven `engineering` mode.
- The viewer consumes `render_glb` and `ui_scene` from the backend.
- HITL setup, task events, checkpoints, and exports are all backend-backed.

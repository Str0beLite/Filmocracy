# Frontend

Empty until the stack is picked. Scaffold straight into this folder, for example:

```bash
npm create vite@latest . -- --template react-ts   # React + Vite
npx create-next-app@latest .                       # Next.js (can also cover the backend)
```

Once it runs, replace this README with: how to install, how to run, and the env vars it needs.

## SQLite backend integration

Use [the current backend guide](../docs/unified-backend.md). `session-client.js` accepts `{ apiUrl, getToken, storage }`, restores the TV session through REST using main's Google ID tokens, and stores only the session UUID. Use the exported `connectSession` WebSocket helper for live snapshots and heartbeats; the guide documents authentication, message formats, and reconnect handling. Run its checks from the repo root: `node --test frontend/session-client.test.mjs`.

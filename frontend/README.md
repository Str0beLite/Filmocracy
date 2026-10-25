# Frontend

Empty until the stack is picked. Scaffold straight into this folder, for example:

```bash
npm create vite@latest . -- --template react-ts   # React + Vite
npx create-next-app@latest .                       # Next.js (can also cover the backend)
```

Once it runs, replace this README with: how to install, how to run, and the env vars it needs.

## Supabase TV session integration

Use [the full frontend integration guide](../docs/frontend-integration.md) and
[OpenAPI specification](../docs/openapi.json) for the current endpoint and realtime contracts.

The frontend app remains the UI teammate's responsibility. `session-client.js`
is a framework-independent helper for preserving TV identity across refreshes.
Create a singleton Supabase client using only the project URL and publishable key:

```js
import { createClient } from '@supabase/supabase-js';
import { createTvSessionClient } from './session-client.js';

const supabase = createClient(url, publishableKey, {
  auth: { persistSession: true, autoRefreshToken: true, detectSessionInUrl: false },
});
const tv = createTvSessionClient(supabase);
const existing = await tv.restore();
const session = existing ?? await tv.create('TV');
```

Use the existing row's id, or create()'s session_id. Render an error/retry state if
restore fails; do not silently create a new host on network errors. On a restored
session call rotate_invite to show a fresh QR; the original raw token is not stored.
Auth must allow Anonymous Sign-Ins. localStorage is device/browser-specific;
clearing it loses guest identity. Do not sign out or create a user on every refresh.

Phones call heartbeat every 10 seconds while connected. Subscribe to Postgres
Changes on the six session tables documented in ../docs/backend-plan.md, filtered
by session_id (id for group_sessions). Subscribe first, fetch session state, and
refetch after reconnect. All clients use their own user JWTs; RLS limits reads.
The server handles completion; do not advance based on client-side vote counts.

Verify the helper: `node --test frontend/session-client.test.mjs`.
There is no rendered UI or frontend build command yet.

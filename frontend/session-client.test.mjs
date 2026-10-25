import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

// Import as ESM without imposing a package type on the teammate's future app.
const source = await readFile(new URL("./session-client.js", import.meta.url), "utf8");
const { createTvSessionClient } = await import(`data:text/javascript,${encodeURIComponent(source)}`);

test("refresh restores host identity and session without creating either again", async () => {
  const values = new Map([["tandem.tv.session", "session-1"]]);
  const storage = { getItem: (k) => values.get(k), removeItem: (k) => values.delete(k) };
  let signIns = 0;
  const supabase = {
    auth: {
      getSession: async () => ({ data: { session: { user: { id: "host-1" } } } }),
      signInAnonymously: async () => { signIns++; throw new Error("Unexpected sign-in"); },
    },
    from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({
      data: { id: "session-1", host_user_id: "host-1", status: "active",
        expires_at: new Date(Date.now() + 60000).toISOString() },
    }) }) }) }),
    rpc: async () => { throw new Error("Unexpected create"); },
  };
  const beforeRefresh = createTvSessionClient(supabase, storage);
  assert.equal((await beforeRefresh.restore()).id, "session-1");
  const afterRefresh = createTvSessionClient(supabase, storage);
  assert.deepEqual(await afterRefresh.create(), { session_id: "session-1" });
  assert.equal(signIns, 0);
});

test("concurrent identity requests create only one anonymous identity", async () => {
  let signIns = 0;
  const client = createTvSessionClient({ auth: {
    getSession: async () => ({ data: { session: null } }),
    signInAnonymously: async () => {
      signIns++;
      return { data: { session: { user: { id: "guest" } } } };
    },
  } }, {});
  await Promise.all([client.identity(), client.identity()]);
  assert.equal(signIns, 1);
});

test("a restored session owned by someone else is discarded", async () => {
  let removed = false;
  const client = createTvSessionClient({
    auth: { getSession: async () => ({ data: { session: { user: { id: "new-host" } } } }) },
    from: () => ({ select: () => ({ eq: () => ({ maybeSingle: async () => ({
      data: { id: "old", host_user_id: "old-host", status: "active" },
    }) }) }) }),
  }, { getItem: () => "old", removeItem: () => { removed = true; } });
  assert.equal(await client.restore(), null);
  assert.equal(removed, true);
});

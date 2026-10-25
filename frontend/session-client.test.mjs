import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";
const source = await readFile(new URL("./session-client.js", import.meta.url), "utf8");
const { createTvSessionClient } = await import(`data:text/javascript,${encodeURIComponent(source)}`);

function fixture({ owner = "host", status = 200 } = {}) {
  const values = new Map([["tandem.tv.session", "session-1"]]);
  const storage = { getItem: k => values.get(k), setItem: (k,v) => values.set(k,v), removeItem: k => values.delete(k) };
  const calls = [];
  const fetchImpl = async (path, options) => {
    calls.push({ path, options });
    if (path === "/me") return { ok: true, json: async () => ({ user: "host" }) };
    return { ok: status === 200, status, json: async () => ({ session: { id: "session-1",
      host_user_id: owner, status: "active", expires_at: new Date(Date.now()+60000).toISOString() } }) };
  };
  return { values, calls, options: { getToken: async () => "google-token", fetchImpl, storage } };
}

test("refresh restores the same TV and session without creating another", async () => {
  const f = fixture();
  assert.equal((await createTvSessionClient(f.options).restore()).id, "session-1");
  assert.deepEqual(await createTvSessionClient(f.options).create(), { session_id: "session-1" });
  assert.ok(f.calls.every(c => c.options.method === "GET"));
  assert.ok(f.calls.every(c => c.options.headers.Authorization === "Bearer google-token"));
});

test("a session belonging to a different Google account is discarded", async () => {
  const f = fixture({ owner: "other" });
  assert.equal(await createTvSessionClient(f.options).restore(), null);
  assert.equal(f.values.size, 0);
});

test("network and authentication failures preserve session identity for retry", async () => {
  for (const status of [401, 503]) {
    const f = fixture({ status });
    await assert.rejects(createTvSessionClient(f.options).create());
    assert.equal(f.values.get("tandem.tv.session"), "session-1");
    assert.ok(f.calls.every(c => c.options.method === "GET"));
  }
});

test("WebSocket authenticates without a URL token and applies fresh snapshots", async () => {
  const { connectSession } = await import(`data:text/javascript,${encodeURIComponent(source)}`);
  class Socket {
    constructor(url) { this.url = url; this.sent = []; this.readyState = 1; }
    send(data) { this.sent.push(JSON.parse(data)); }
  }
  const states = [];
  const ws = await connectSession({ apiUrl: "https://api.example", sessionId: "session-1",
    getToken: async () => "private-token", onState: state => states.push(state),
    WebSocketImpl: Socket });
  assert.equal(ws.url, "wss://api.example/sessions/session-1/ws");
  ws.onopen();
  try {
    assert.deepEqual(ws.sent, [{ type: "auth", token: "private-token" }]);
    for (const revision of [2, 1, 2, 3]) ws.onmessage({ data: JSON.stringify({
      type: "state", revision, state: { revision },
    }) });
    assert.deepEqual(states, [{ revision: 2 }, { revision: 3 }]);
  } finally { ws.onclose({ code: 1000 }); }
});

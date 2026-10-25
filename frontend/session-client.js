// The UI supplies a fresh Google ID token from its sign-in flow. Tokens are never stored here.
const sessionKey = "tandem.tv.session";

export function createTvSessionClient({ apiUrl = "", getToken, fetchImpl = globalThis.fetch,
  storage = globalThis.localStorage }) {
  async function call(path, body) {
    const token = await getToken();
    if (!token) throw new Error("Google sign-in required");
    const response = await fetchImpl(`${apiUrl}${path}`, {
      method: body ? "POST" : "GET",
      headers: { Authorization: `Bearer ${token}`, ...(body ? { "Content-Type": "application/json" } : {}) },
      ...(body ? { body: JSON.stringify(body) } : {}),
    });
    if (!response.ok) {
      const error = new Error(`Backend request failed (${response.status})`);
      error.status = response.status;
      throw error;
    }
    return response.json();
  }
  return {
    identity: () => call("/me"),
    async restore() {
      const id = storage.getItem(sessionKey);
      if (!id) return null;
      const auth = await this.identity();
      let state;
      try { state = await call(`/sessions/${id}`); }
      catch (error) {
        if (error.status !== 404) throw error;
        storage.removeItem(sessionKey);
        return null;
      }
      const session = state.session;
      if (session.host_user_id !== auth.user || session.status === "ended"
          || Date.parse(session.expires_at) <= Date.now()) {
        storage.removeItem(sessionKey);
        return null;
      }
      return session;
    },
    async create(displayName = "TV") {
      const previous = await this.restore();
      if (previous) return { session_id: previous.id };
      const result = await call("/sessions", { display_name: displayName });
      storage.setItem(sessionKey, result.session_id);
      return result;
    },
  };
}

// Shared by phones and the TV. Reconnect by calling again with a fresh Google token.
export async function connectSession({ apiUrl, sessionId, getToken, onState, onClose,
  WebSocketImpl = globalThis.WebSocket }) {
  const token = await getToken();
  if (!token) throw new Error("Google sign-in required");
  const url = new URL(`${apiUrl.replace(/\/$/, "")}/sessions/${encodeURIComponent(sessionId)}/ws`,
    globalThis.location?.href);
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
  const socket = new WebSocketImpl(url.href);
  let revision = -1;
  let heartbeat;
  socket.onopen = () => {
    socket.send(JSON.stringify({ type: "auth", token }));
    heartbeat = setInterval(() => {
      if (socket.readyState === 1) socket.send(JSON.stringify({ type: "heartbeat" }));
    }, 10000);
  };
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.type === "state" && message.revision > revision) {
      revision = message.revision;
      onState(message.state);
    }
  };
  socket.onclose = event => {
    clearInterval(heartbeat);
    onClose?.(event);
  };
  return socket;
}

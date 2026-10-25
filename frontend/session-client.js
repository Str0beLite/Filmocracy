// Pass a singleton Supabase client configured with auth.persistSession:true and
// auth.autoRefreshToken:true. This module has no dependency on the TV UI framework.
const sessionKey = "tandem.tv.session";

export function createTvSessionClient(supabase, storage = globalThis.localStorage) {
  let restoring;

  async function identity() {
    if (!restoring) {
      restoring = (async () => {
        const { data, error } = await supabase.auth.getSession();
        if (error) throw error;
        if (data.session) return data.session;
        const result = await supabase.auth.signInAnonymously();
        if (result.error) throw result.error;
        return result.data.session;
      })().catch((error) => {
        restoring = undefined;
        throw error;
      });
    }
    return restoring;
  }

  return {
    identity,
    async restore() {
      const auth = await identity();
      const id = storage.getItem(sessionKey);
      if (!id) return null;
      const { data, error } = await supabase.from("group_sessions")
        .select("*").eq("id", id).maybeSingle();
      if (error) throw error;
      if (!data || data.host_user_id !== auth.user.id || data.status === "ended"
          || Date.parse(data.expires_at) <= Date.now()) {
        storage.removeItem(sessionKey);
        return null;
      }
      return data;
    },
    async create(displayName = "TV") {
      await identity();
      // Reuse a session after refresh; rotate its invitation separately to show QR again.
      const previous = await this.restore();
      if (previous) return { session_id: previous.id };
      const { data, error } = await supabase.rpc("create_session", { p_name: displayName });
      if (error) throw error;
      storage.setItem(sessionKey, data.session_id);
      return data;
    },
  };
}

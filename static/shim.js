// Connects the page to the Flask backend. It provides the same small interface the
// page uses inside Claude (db, user, sample), backed by /api/docs and /api/claude.
(function () {
  async function call(method, url, body) {
    const r = await fetch(url, {
      method,
      headers: body ? { "Content-Type": "application/json" } : {},
      body: body ? JSON.stringify(body) : undefined,
      credentials: "same-origin",
    });
    if (r.status === 401) { location.href = "/login"; throw { code: "revoked", message: "Signed out" }; }
    let data = null;
    try { data = await r.json(); } catch (e) {}
    if (!r.ok) throw { code: (data && data.code) || "unavailable", message: (data && data.message) || ("HTTP " + r.status) };
    return data;
  }

  const snap = (id, data) => ({ id, exists: data !== undefined, data: () => data, metadata: { fromCache: false, hasPendingWrites: false } });
  const docRef = (id) => ({
    id,
    set: (data) => call("PUT", "/api/docs/" + encodeURIComponent(id), data).then(() => {}),
    delete: () => call("DELETE", "/api/docs/" + encodeURIComponent(id)).then(() => {}),
  });
  const db = {
    collection: () => ({
      get: async () => {
        const list = await call("GET", "/api/docs");
        const docs = list.map((d) => snap(d.id, d.data));
        return { docs, size: docs.length, empty: !docs.length };
      },
      doc: (id) => docRef(id),
    }),
  };

  const user = { id: async () => "me", isOwner: () => true, canEdit: () => true, can: () => true };

  async function sample(prompt, opts) {
    opts = opts || {};
    const r = await call("POST", "/api/claude", { prompt, tier: opts.modelTier || "default" });
    return { text: r.text || "", truncated: !!r.truncated };
  }
  sample.json = async (prompt, opts) => {
    const r = await sample(prompt + "\n\nRespond with JSON only.", opts);
    const m = r.text.match(/\{[\s\S]*\}/);
    return JSON.parse(m ? m[0] : r.text);
  };

  const caps = { db, user, sample };
  window.claude = { use: async (name) => caps[name] || null };
})();

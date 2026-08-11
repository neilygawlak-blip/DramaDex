// Cloudflare Pages worker for the DramaDex deploy. Serves the static
// site untouched and adds the Voice Booth's upload path into the VOICES
// KV store. The whole hostname sits behind Cloudflare Access, so every
// request that reaches this code is already cast-only; the inbox pages
// are further restricted to the admin emails below, read off the header
// Access stamps onto each authenticated request.

const ADMINS = new Set(["chris@nexustechfl.com"]);

const EXT = {
  "audio/webm": "webm",
  "audio/mp4": "m4a",
  "audio/ogg": "ogg",
  "audio/mpeg": "mp3",
  "audio/wav": "wav",
};

const json = (obj, status) =>
  new Response(JSON.stringify(obj), {
    status: status || 200,
    headers: { "content-type": "application/json" },
  });

const isAdmin = (req) =>
  ADMINS.has(
    (req.headers.get("cf-access-authenticated-user-email") || "").toLowerCase()
  );

async function upload(req, env, url) {
  const who = (url.searchParams.get("who") || "").toUpperCase();
  const card = url.searchParams.get("card") || "";
  if (!/^[A-Z][A-Z .]{1,24}$/.test(who) || !/^[1-9]$/.test(card))
    return json({ error: "bad who/card" }, 400);
  const len = +(req.headers.get("content-length") || 0);
  if (!len || len > 25e6) return json({ error: "bad size" }, 400);
  const ct = (req.headers.get("content-type") || "").split(";")[0];
  const stamp = new Date().toISOString().replace(/[:.]/g, "-");
  const key =
    "inbox/" + who.replace(/ /g, "_") + "/" + stamp +
    "_card" + card + "." + (EXT[ct] || "bin");
  await env.VOICES.put(key, req.body, {
    metadata: { ct: ct || "application/octet-stream", size: len,
                uploaded: Date.now() },
  });
  return json({ ok: true, key });
}

// A plain HTML listing of everything in the inbox, newest first, with
// download links. This is how recordings come off the site: open it in
// the browser (already Access-authenticated), click, save.
async function inbox(req, env) {
  if (!isAdmin(req)) return json({ error: "not for you" }, 403);
  const list = await env.VOICES.list({ prefix: "inbox/", limit: 500 });
  const rows = list.keys
    .sort((a, b) => (a.name < b.name ? 1 : -1))
    .map((k) => {
      const m = k.metadata || {};
      return (
        '<li><a href="/api/voice-clip/' + encodeURIComponent(k.name) +
        '">' + k.name + "</a> <small>" +
        Math.round((m.size || 0) / 1024) + " KB · " +
        (m.uploaded ? new Date(m.uploaded).toLocaleString() : "?") +
        "</small></li>"
      );
    })
    .join("\n");
  const html =
    "<!doctype html><meta charset=utf-8><title>Neil's Lab inbox</title>" +
    "<body style='font-family:system-ui;background:#0a0f1e;color:#e8e6df;" +
    "max-width:720px;margin:2rem auto;line-height:1.7'>" +
    "<h1 style='color:#ffd75e'>Voice Booth inbox</h1>" +
    (rows ? "<ul>" + rows + "</ul>" : "<p>Empty. Nobody has recorded yet.</p>") +
    "</body>";
  return new Response(html, { headers: { "content-type": "text/html" } });
}

async function clip(req, env, url) {
  if (!isAdmin(req)) return json({ error: "not for you" }, 403);
  const key = decodeURIComponent(url.pathname.slice("/api/voice-clip/".length));
  if (!key.startsWith("inbox/")) return json({ error: "bad key" }, 400);
  const got = await env.VOICES.getWithMetadata(key, { type: "stream" });
  if (!got.value) return json({ error: "gone" }, 404);
  return new Response(got.value, {
    headers: {
      "content-type": got.metadata?.ct || "application/octet-stream",
      "content-disposition":
        'attachment; filename="' + key.split("/").slice(1).join("_") + '"',
    },
  });
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/api/voice-upload" && req.method === "POST")
      return upload(req, env, url);
    if (url.pathname === "/api/voice-inbox") return inbox(req, env);
    if (url.pathname.startsWith("/api/voice-clip/")) return clip(req, env, url);
    return env.ASSETS.fetch(req);
  },
};

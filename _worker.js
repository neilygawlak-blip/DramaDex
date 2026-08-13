// Cloudflare Pages worker for the DramaDex deploy. Serves the static
// site untouched and adds the Voice Booth's upload path into the VOICES
// KV store. The whole hostname sits behind Cloudflare Access, so every
// request that reaches this code is already cast-only; the inbox pages
// are further restricted to the admin emails below, read off the header
// Access stamps onto each authenticated request.

const ADMINS = new Set(["chris@nexustechfl.com"]);

// The Pineapple Playhouse Discord, for the "who's in voice" strip on the
// cast list. Paste the numeric server id here: Discord -> Settings ->
// Advanced -> Developer Mode, then right-click the server icon -> Copy
// Server ID. Server Settings -> Widget -> Enable Server Widget must also
// be on, or Discord answers 403 and the strip simply stays hidden.
const GUILD_ID = "PASTE_DISCORD_SERVER_ID";

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

// Who is sitting in a Discord voice channel right now. Read from the
// public guild widget, so there is no bot to host and nothing to keep
// running. Proxied rather than fetched by each browser for three
// reasons: the widget is rate-limited and this collapses every viewer
// into one call per cache window, the roster stays behind the Access
// gate, and a Discord outage degrades to an empty strip instead of a
// console full of errors. Presence is therefore up to ~15s stale, which
// is the right resolution for "is anyone around", not for who is
// talking this second.
let widgetCache = { at: 0, body: null };

async function presence() {
  if (!/^\d{17,20}$/.test(GUILD_ID)) return json({ off: true, inVoice: [] });
  const now = Date.now();
  if (widgetCache.body && now - widgetCache.at < 15000)
    return json(widgetCache.body);
  const body = { inVoice: [], invite: null };
  try {
    const r = await fetch(
      "https://discord.com/api/guilds/" + GUILD_ID + "/widget.json"
    );
    if (r.ok) {
      const w = await r.json();
      const rooms = new Map((w.channels || []).map((c) => [c.id, c.name]));
      body.invite = w.instant_invite || null;
      // Only members with a channel_id are connected to voice; the rest
      // of the list is everyone merely online, which nobody needs here.
      body.inVoice = (w.members || [])
        .filter((m) => m.channel_id)
        .map((m) => ({
          name: m.nick || m.username || "someone",
          room: rooms.get(m.channel_id) || "voice",
          muted: !!(m.mute || m.self_mute),
        }));
    } else {
      body.off = true;
    }
  } catch (_) {
    body.off = true;
  }
  widgetCache = { at: now, body };
  return json(body);
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/api/voice-upload" && req.method === "POST")
      return upload(req, env, url);
    if (url.pathname === "/api/voice-presence") return presence();
    if (url.pathname === "/api/voice-inbox") return inbox(req, env);
    if (url.pathname.startsWith("/api/voice-clip/")) return clip(req, env, url);
    return env.ASSETS.fetch(req);
  },
};

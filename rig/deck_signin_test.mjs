// Every sign-in and sync flow of DramaDeck's worker (private/deck/_worker.js),
// against stand-ins for the store, Stripe and the email service. Nothing
// real is called and nothing is sent.
//     python build_deck.py --signin
//     node rig/deck_signin_test.mjs
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const ROOT = path.join(path.dirname(fileURLToPath(import.meta.url)), "..");
// The built worker, copied where Node will read it as a module.
fs.mkdirSync(path.join(ROOT, ".rig"), { recursive: true });
const copy = path.join(ROOT, ".rig", "deck_worker.mjs");
fs.copyFileSync(path.join(ROOT, "deck_site", "_worker.js"), copy);
const w = (await import(pathToFileURL(copy).href + "?t=" + Date.now())).default;
// The paid page's folder is the buyer's link: read, never written here.
const PAID = "/" + fs.readFileSync(path.join(ROOT, "private", "deck_app_name.txt"), "utf8").trim().split("/")[0] + "/";
const kv = new Map();
const mkEnv = (over) => Object.assign({
  DECK: { get: async (k) => (kv.has(k) ? kv.get(k) : null), put: async (k, v) => { kv.set(k, v); }, delete: async (k) => { kv.delete(k); } },
  ASSETS: { fetch: async (r) => new Response(new URL(r.url).pathname === "/signin" ? "SIGNIN" : "APP",
    { headers: { "content-type": "text/html", "cache-control": "public, max-age=0" } }) },
  SESSION_KEY: "k".repeat(48), STRIPE_KEY: "rk_test_x", RESEND_KEY: "re_x", MAIL_FROM: "DramaDeck <signin@dramadeck.app>",
}, over || {});
let env = mkEnv();

// ---- stand-in Stripe and email ----
const now = Math.floor(Date.now() / 1000);
const sessions = {
  cs_test_paidfresh0001: { status: "complete", payment_status: "paid", created: now - 60, payment_link: "plink_deck", customer_details: { email: "Buyer@Example.com" } },
  cs_test_unpaid0000001: { status: "open", payment_status: "unpaid", created: now - 60, payment_link: "plink_deck", customer_details: { email: "nopay@example.com" } },
  cs_test_paidold000001: { status: "complete", payment_status: "paid", created: now - 3 * 86400, payment_link: "plink_deck", customer_details: { email: "old@example.com" } },
  cs_test_otherthing001: { status: "complete", payment_status: "paid", created: now - 60, payment_link: "plink_other", customer_details: { email: "other@example.com" } },
};
const mails = [];
let stripeCalls = 0;
globalThis.fetch = async (url, opt) => {
  url = String(url);
  if (url.startsWith("https://api.stripe.com/v1/checkout/sessions/")) {
    stripeCalls++;
    const s = sessions[url.split("/").pop()];
    return s ? new Response(JSON.stringify(s)) : new Response("{}", { status: 404 });
  }
  if (url.startsWith("https://api.stripe.com/v1/checkout/sessions?")) {
    stripeCalls++;
    const email = new URL(url).searchParams.get("customer_details[email]");
    return new Response(JSON.stringify({ data: Object.values(sessions).filter((s) => s.customer_details.email.toLowerCase() === email) }));
  }
  if (url === "https://api.resend.com/emails") {
    const b = JSON.parse(opt.body);
    mails.push({ to: b.to[0], code: /code is (\d{6})/.exec(b.text)[1], link: /https?:\/\/\S+/.exec(b.text)[0], from: b.from });
    return new Response("{}");
  }
  throw new Error("unexpected fetch " + url);
};

let pass = 0, fail = 0;
const ok = (name, cond, extra) => { cond ? pass++ : fail++; console.log((cond ? "ok   " : "FAIL ") + name + (extra && !cond ? "  -> " + extra : "")); };
const call = async (path, opt) => {
  opt = opt || {};
  const h = Object.assign({ "cf-connecting-ip": opt.ip || "1.2.3.4" }, opt.cookie ? { cookie: opt.cookie } : {});
  const r = await w.fetch(new Request("https://dramadeck.app" + path, { method: opt.method || "GET", headers: h,
    body: opt.body ? JSON.stringify(opt.body) : undefined, redirect: "manual" }), env);
  const set = r.headers.get("set-cookie") || "";
  const text = await r.text();
  let j = null; try { j = JSON.parse(text); } catch (_) { /* not json */ }
  return { status: r.status, text, j, cookie: set.split(";")[0], set, loc: r.headers.get("location"), cc: r.headers.get("cache-control") };
};

// 1. the gate
let r = await call(PAID);
ok("no cookie: the paid page shows the sign-in page", r.text === "SIGNIN" && r.status === 200 && r.cc === "no-store");
r = await call("/demo");
ok("the demo is open to anyone", r.text === "APP");
r = await call(PAID + "vendor/pdf.min.js");
ok("the paid page's libraries stay open", r.text === "APP");

// 2. a new buyer arrives from Stripe
r = await call("/welcome?session_id=cs_test_paidfresh0001");
const buyer = r.cookie;
ok("fresh paid purchase: signed in and sent to the app", r.status === 302 && r.loc === PAID && /^dd_s=[0-9a-f]{40}\.\d+\.[0-9a-f]{64}$/.test(buyer), r.set);
ok("cookie is HttpOnly, Secure, 400 days", /HttpOnly/.test(r.set) && /Secure/.test(r.set) && /Max-Age=34560000/.test(r.set));
r = await call(PAID, { cookie: buyer });
ok("with the cookie the paid page is the app, never cached", r.text === "APP" && /no-store/.test(r.cc));
r = await call("/api/me", { cookie: buyer });
ok("/api/me says signed in", r.j.in === true);

// 3. what must NOT sign anyone in
for (const [id, why] of [["cs_test_unpaid0000001", "unpaid"], ["cs_test_paidold000001", "three days old"], ["cs_test_nosuchsession1", "unknown"], ["../../etc", "junk"]]) {
  r = await call("/welcome?session_id=" + encodeURIComponent(id));
  ok("welcome refuses a session that is " + why, r.status === 302 && !r.set);
}
env = mkEnv({ STRIPE_PAYMENT_LINK: "plink_deck" });
r = await call("/welcome?session_id=cs_test_otherthing001");
ok("with the payment link set, a purchase of something else is refused", !r.set);
r = await call("/welcome?session_id=cs_test_paidfresh0001");
ok("and DramaDeck's own purchase still works", !!r.set);
env = mkEnv();
r = await call(PAID, { cookie: buyer.replace(/.$/, (c) => (c === "0" ? "1" : "0")) });
ok("a tampered cookie is not signed in", r.text === "SIGNIN");
const acct = buyer.slice(5, 45);
r = await call(PAID, { cookie: "dd_s=" + acct + ".1000000000." + "0".repeat(64) });
ok("an expired cookie is not signed in", r.text === "SIGNIN");

// 4. signing in by email
r = await call("/api/signin", { method: "POST", body: { email: "stranger@example.com" } });
ok("an email with no purchase: told so, no email sent", r.status === 404 && r.j.why === "none" && mails.length === 0);
r = await call("/api/signin", { method: "POST", body: { email: "not an email" } });
ok("a bad address is refused", r.status === 400 && r.j.why === "email");
r = await call("/api/signin", { method: "POST", body: { email: "  BUYER@example.COM " } });
ok("the buyer's email, any capitals: code sent", r.j.ok === true && mails.length === 1 && mails[0].to === "buyer@example.com");
const m1 = mails[0];
r = await call("/api/code", { method: "POST", body: { email: "buyer@example.com", code: "000000" === m1.code ? "111111" : "000000" } });
ok("a wrong code is refused", r.status === 403 && !r.set);
r = await call("/api/code", { method: "POST", body: { email: "buyer@example.com", code: m1.code } });
ok("the right code signs in, same account as the purchase", r.j.ok && r.j.to === PAID && r.cookie.slice(5, 45) === acct);
r = await call(new URL(m1.link).pathname + new URL(m1.link).search);
ok("the emailed link signs in too (and the code is not used up by it)", r.status === 302 && r.loc === PAID && r.cookie.slice(5, 45) === acct);

// someone who bought before sign-in existed: found through Stripe by email
stripeCalls = 0;
r = await call("/api/signin", { method: "POST", body: { email: "old@example.com" }, ip: "5.5.5.5" });
ok("an earlier buyer is found through Stripe and sent a code", r.j.ok === true && stripeCalls === 1 && mails.length === 2);
r = await call("/api/code", { method: "POST", body: { email: "old@example.com", code: mails[1].code } });
const older = r.cookie;
ok("and signs in as a different account", r.j.ok && older.slice(5, 45) !== acct);

// six wrong tries spend a code
r = await call("/api/signin", { method: "POST", body: { email: "old@example.com" }, ip: "5.5.5.6" });
const c3 = mails[2].code, wrong = c3 === "123456" ? "654321" : "123456";
for (let i = 0; i < 6; i++) await call("/api/code", { method: "POST", body: { email: "old@example.com", code: wrong } });
r = await call("/api/code", { method: "POST", body: { email: "old@example.com", code: c3 } });
ok("after six wrong tries even the right code is refused", r.status === 403);

// a few an hour
let last;
for (let i = 0; i < 6; i++) last = await call("/api/signin", { method: "POST", body: { email: "buyer@example.com" }, ip: "9.9.9." + i });
ok("more than five codes an hour for one email: told to wait", last.status === 429 && last.j.why === "wait");

// 5. scores follow the account
const S = "run:0|scene|15", page = "/api/sync?page=" + encodeURIComponent("HALE — Trifles");
r = await call(page);
ok("sync without signing in: 401, nothing kept", r.status === 401 && r.j.off === true);
r = await call(page, { cookie: buyer });
ok("signed in, nothing yet", r.status === 200 && Object.keys(r.j.sets).length === 0);
r = await call(page, { cookie: buyer, method: "POST", body: { set: S, pct: 80, mine: 70, clean: 0, of: 15, secs: 190, skips: 2, asks: 1 } });
r = await call(page, { cookie: buyer, method: "POST", body: { set: S, pct: 75, mine: 40, clean: 0, of: 15, secs: 150, skips: 0, asks: 0 } });
r = await call(page, { cookie: buyer, method: "POST", body: { set: S, pct: 80, mine: 61, clean: 0, of: 15 } });
ok("best score kept, fastest time AT that score, runs counted", r.j.sets[S].pct === 80 && r.j.sets[S].mine === 61 && r.j.sets[S].runs === 3, JSON.stringify(r.j.sets[S]));
r = await call(page, { cookie: older });
ok("another buyer sees none of it", Object.keys(r.j.sets).length === 0);
r = await call(page, { cookie: buyer, method: "POST", body: { set: S, pct: 101, mine: 1, clean: 0, of: 15 } });
ok("a nonsense run is refused", r.status === 400);
const dataKey = [...kv.keys()].find((k) => k.startsWith("data/" + acct));
const rec = JSON.parse(kv.get(dataKey));
ok("a log of the three runs is kept with their details", rec.runs.length === 3 && rec.runs[0].secs === 190 && rec.runs[0].skips === 2 && rec.runs[2].secs === 0);
rec.seen = Date.now() - 91 * 86400000; kv.set(dataKey, JSON.stringify(rec));
r = await call(page, { cookie: buyer });
ok("a part not run for 91 days starts over", Object.keys(r.j.sets).length === 0);

// 6. the way out, and a refund
r = await call("/api/signout", { method: "POST", cookie: buyer });
ok("sign out clears the cookie", /dd_s=;/.test(r.set) && /Max-Age=0/.test(r.set));
kv.delete("acct/" + acct);
r = await call(PAID, { cookie: buyer });
ok("a deleted account (a refund) is signed out everywhere", r.text === "SIGNIN");

// 7. nothing set up: fail closed
env = mkEnv({ SESSION_KEY: undefined });
r = await call(PAID, { cookie: older });
ok("no session key: nobody is signed in", r.text === "SIGNIN");
r = await call("/api/signin", { method: "POST", body: { email: "old@example.com" } });
ok("no session key: sign-in says it is off", r.status === 503);
env = mkEnv({ RESEND_KEY: undefined });
r = await call("/api/signin", { method: "POST", body: { email: "old@example.com" }, ip: "7.7.7.7" });
ok("no email key: says the email could not be sent", r.status === 502 && r.j.why === "mail");

// 8. what the store holds
const all = [...kv.entries()].map(([k, v]) => k + " " + v).join("\n");
ok("no email address anywhere in the store", !/example\.com/i.test(all) && !/@/.test(all));
ok("sender is the configured address", mails.every((m) => m.from === "DramaDeck <signin@dramadeck.app>"));
console.log("store keys:", [...new Set([...kv.keys()].map((k) => k.split("/")[0]))].join(", "));
console.log(fail ? "RESULT: " + fail + " FAILED, " + pass + " passed" : "RESULT: all " + pass + " passed");
process.exit(fail ? 1 : 0);

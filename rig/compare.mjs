// Old build (.rig/base) against new build (private/deploy), asked with what
// the recognizer really wrote for every line (both sweeps) and with the
// script itself read perfectly. No speech; the pages' own gate answers.
// Run from the DramaDex folder. Writes .rig/compare.json.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

const ROOT = process.cwd(), WORK = path.join(ROOT, ".rig");
const DIRS = { base: path.join(WORK, "base"), new: path.join(ROOT, "private", "deploy") };
const PORT = 8793, CDP = 9351;
const CHROME = ["C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"].find(p => fs.existsSync(p));
const sleep = ms => new Promise(r => setTimeout(r, ms));
const A = JSON.parse(fs.readFileSync(path.join(WORK, "sweep_david.json"), "utf8"));
const B = JSON.parse(fs.readFileSync(path.join(WORK, "sweep_zira.json"), "utf8"));

const srv = http.createServer((req, rsp) => {
  const u = decodeURIComponent(req.url.split("?")[0]).split("/").filter(Boolean);
  if (u[0] === "api") { req.resume(); rsp.writeHead(200); rsp.end("{}"); return; }
  const file = DIRS[u[0]] && path.join(DIRS[u[0]], path.basename(u[1] || ""));
  if (!file || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { rsp.writeHead(404); rsp.end("no"); return; }
  rsp.writeHead(200, { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" });
  fs.createReadStream(file).pipe(rsp);
});
await new Promise(r => srv.listen(PORT, "127.0.0.1", r));
const proc = spawn(CHROME, ["--headless=new", `--user-data-dir=${path.join(WORK, "gate_profile")}`, `--remote-debugging-port=${CDP}`,
  "--remote-allow-origins=*", "--no-first-run", "about:blank"], { stdio: "ignore" });
let list;
for (let i = 0; i < 80; i++) { try { list = await (await fetch(`http://127.0.0.1:${CDP}/json`)).json(); if (list.some(t => t.type === "page")) break; } catch { /* not up */ } await sleep(250); }
const ws = new WebSocket(list.find(t => t.type === "page").webSocketDebuggerUrl);
await new Promise(r => { ws.onopen = r; });
let id = 0; const wait = new Map();
ws.onmessage = m => { const d = JSON.parse(m.data); const w = d.id && wait.get(d.id); if (w) { wait.delete(d.id); w(d); } };
const send = (method, params = {}) => new Promise(res => { const i = ++id; wait.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async expression => { const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
  if (r.result.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description || "page error"); return r.result.result.value; };

const byPage = {};
for (const k of Object.keys(A)) { const [p, i] = k.split(":"); (byPage[p] ||= []).push(+i); }
const out = { base: {}, new: {} };
await send("Page.enable");
for (const which of ["base", "new"]) for (const [page, is] of Object.entries(byPage)) {
  await send("Page.navigate", { url: `http://127.0.0.1:${PORT}/${which}/${page}.html?v=${Date.now()}#nochime-notrack-nohold` });
  let ok = false;
  for (let t = 0; t < 150; t++) { try { if (await ev(`typeof DATA!=="undefined"&&typeof doneEnough==="function"&&document.readyState==="complete"`)) { ok = true; break; } } catch { /* loading */ } await sleep(100); }
  if (!ok) { console.log(which, page, "did not load"); continue; }
  const jobs = is.map(i => ({ i, a: A[`${page}:${i}`].text || "", b: (B[`${page}:${i}`] || {}).text ?? null }));
  const res = await ev(`(()=>{const J=${JSON.stringify(jobs)};const R={};
   const st=(l,t)=>{heard=t;greenWait=false;const p=doneEnough(l);return p?2:greenWait?1:0;};
   const fp=(l,t)=>{const W=t.split(" ").filter(Boolean);for(let k=1;k<=W.length;k++)if(st(l,W.slice(0,k).join(" "))===2)return k;return 0;};
   const one=(l,t)=>t===null?null:[st(l,t),grade(l.say,t).marks.filter(m=>!m.ok).map(m=>m.w),fp(l,t),t.split(" ").filter(Boolean).length];
   for(const j of J){const l=DATA.lines.find(l=>l.i===j.i);if(!l)continue;const s=norm(l.say);
    R[j.i]={a:one(l,j.a),b:one(l,j.b),s:[fp(l,s),s.split(" ").filter(Boolean).length,st(l,s)]};}
   heard="";return JSON.stringify(R);})()`).then(JSON.parse);
  for (const [i, r] of Object.entries(res)) out[which][`${page}:${i}`] = r;
}
fs.writeFileSync(path.join(WORK, "compare.json"), JSON.stringify(out));
console.log("lines:", Object.keys(out.base).length, Object.keys(out.new).length);
ws.close(); try { proc.kill(); } catch { /* gone */ } srv.close();
process.exit(0);

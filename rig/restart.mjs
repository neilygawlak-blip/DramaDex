// Restart check: does the page's cue voice still speak after a run is
// halted from the scene menu and started again? (Chris, 2026-11-16: "only
// sound cues worked and voices were hung".) Real Chrome, the page's own
// voices, Chrome muted. No recognition is needed: the mic is a fake one.
//
//   node rig/restart.mjs [PAGE] [scope]     e.g. CD_HAROLD run:4
//
// Prints every utterance the page hands the browser, the voice it chose,
// and whether it started and ended, for the first run and the restarted one.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = path.join(ROOT, "private", "deploy"), WORK = path.join(ROOT, ".rig");
const PAGE = process.argv[2] || "CD_HAROLD", SCOPE = process.argv[3] || "run:4";
const HOW = process.argv[4] || "menu";          // menu = pick another scene and back; same = Start again only
const SECS = +(process.env.RIG_SECS || 25);
const PORT = 8794, CDP = 9352;
const CHROME = ["C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"].find(p => fs.existsSync(p));
const sleep = ms => new Promise(r => setTimeout(r, ms));

const srv = http.createServer((req, rsp) => {
  const u = decodeURIComponent(req.url.split("?")[0]);
  if (u.startsWith("/api/")) { req.resume(); rsp.writeHead(200); rsp.end("{}"); return; }
  const file = path.join(SITE, u);
  if (!file.startsWith(SITE) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { rsp.writeHead(404); rsp.end("no"); return; }
  const type = file.endsWith(".html") ? "text/html; charset=utf-8" : file.endsWith(".mp3") ? "audio/mpeg" : "application/octet-stream";
  rsp.writeHead(200, { "content-type": type, "cache-control": "no-store" });
  fs.createReadStream(file).pipe(rsp);
});
await new Promise(r => srv.listen(PORT, "127.0.0.1", r));
const proc = spawn(CHROME, [`--user-data-dir=${path.join(WORK, "restart_profile")}`, `--remote-debugging-port=${CDP}`,
  "--remote-allow-origins=*", "--no-first-run", "--no-default-browser-check", "--mute-audio",
  "--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream",
  // RIG_BLOCK=1: this Chrome cannot reach Google, the way a bad connection
  // or a filter leaves it. Its online voices and its recognizer both need it.
  ...(process.env.RIG_BLOCK === "1" ? ["--host-resolver-rules=MAP *.google.com ~NOTFOUND, MAP google.com ~NOTFOUND, MAP *.googleapis.com ~NOTFOUND"] : []),
  "--window-size=520,760", "about:blank"], { stdio: "ignore" });
let list;
for (let i = 0; i < 80; i++) { try { list = await (await fetch(`http://127.0.0.1:${CDP}/json`)).json(); if (list.some(t => t.type === "page")) break; } catch { /* not up */ } await sleep(250); }
const ws = new WebSocket(list.find(t => t.type === "page").webSocketDebuggerUrl);
await new Promise(r => { ws.onopen = r; });
let id = 0; const wait = new Map();
ws.onmessage = m => { const d = JSON.parse(m.data); const w = d.id && wait.get(d.id); if (w) { wait.delete(d.id); w(d); } };
const send = (method, params = {}) => new Promise(res => { const i = ++id; wait.set(i, res); ws.send(JSON.stringify({ id: i, method, params })); });
const ev = async (expression, gesture) => { const r = await send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true, userGesture: !!gesture });
  if (r.result.exceptionDetails) throw new Error(r.result.exceptionDetails.exception?.description || "page error"); return r.result.result.value; };

// Every speak() and cancel() the page makes, with what became of it.
const SHIM = `(()=>{const L=window.__tts=[];const t0=performance.now();const at=()=>Math.round(performance.now()-t0);
 const S=speechSynthesis,sp=S.speak.bind(S),ca=S.cancel.bind(S);
 S.speak=u=>{const e={at:at(),n:(u.text||"").split(" ").length,vol:u.volume,voice:u.voice?u.voice.name:"(default)",
   local:u.voice?u.voice.localService:null,busy:S.speaking,pend:S.pending,start:null,end:null,err:null};L.push(e);
  u.addEventListener("start",()=>e.start=at());u.addEventListener("end",()=>e.end=at());
  u.addEventListener("error",x=>e.err=x.error||"error");return sp(u);};
 S.cancel=()=>{L.push({at:at(),cancel:true,busy:S.speaking,pend:S.pending});return ca();};})();`;
await send("Page.enable");
await send("Page.addScriptToEvaluateOnNewDocument", { source: SHIM });
await send("Page.navigate", { url: `http://127.0.0.1:${PORT}/${PAGE}.html?v=${Date.now()}#nochime-notrack` });
for (let t = 0; t < 150; t++) { try { if (await ev(`typeof DATA!=="undefined"&&typeof start==="function"&&document.readyState==="complete"`)) break; } catch { /* loading */ } await sleep(100); }
await sleep(1500);
console.log("voices:", await ev(`JSON.stringify(speechSynthesis.getVoices().filter(v=>v.lang.startsWith("en")).map(v=>v.name+(v.localService?"":" [online]")))`));
console.log("scopes:", await ev(`JSON.stringify([...scope.options].map(o=>o.value))`), "mode:", await ev(`mode.value`));

const dump = async label => {
  const L = JSON.parse(await ev(`JSON.stringify(window.__tts.splice(0))`));
  console.log(`--- ${label}: ${L.filter(e => !e.cancel).length} utterances`);
  for (const e of L) console.log(e.cancel ? `  ${e.at} ms  CANCEL (speaking=${e.busy}, pending=${e.pend})`
    : `  ${e.at} ms  ${e.voice}${e.local === false ? " [online]" : ""}, ${e.n} words, vol ${e.vol}, queued while speaking=${e.busy} pending=${e.pend} -> `
      + (e.err ? "ERROR " + e.err : e.start === null ? "NEVER STARTED" : e.end === null ? `started ${e.start}, no end yet` : `started ${e.start}, ended ${e.end}`));
  console.log("  state now:", await ev(`"speaking="+speechSynthesis.speaking+" pending="+speechSynthesis.pending+" running="+running+" pos="+pos`));
  return L;
};
const press = sel => ev(`document.querySelector(${JSON.stringify(sel)}).click()`, true);
const pick = v => ev(`(()=>{scope.value=${JSON.stringify(v)};scope.dispatchEvent(new Event("change",{bubbles:true}));return scope.value})()`, true);

await pick(SCOPE);
await press("#startbtn");
await sleep(SECS * 1000);
// Restart while a voice is in the middle of a sentence: RIG_MID=online
// waits for one of Chrome's online voices, RIG_MID=local for a built-in one.
const MID = process.env.RIG_MID || "";
if (MID) for (let t = 0; t < 600; t++) {
  if (await ev(`(()=>{const e=window.__tts.filter(e=>!e.cancel).pop();return !!e&&e.vol!==0&&e.start!==null&&e.end===null&&e.local===${MID === "local"}&&e.n>6})()`)) break;
  await sleep(50);
}
if (MID) await sleep(700);
await dump("first run");
if (HOW === "menu") {
  const other = await ev(`[...scope.options].map(o=>o.value).find(v=>v.startsWith("run:")&&v!==${JSON.stringify(SCOPE)})`);
  await pick(other); await sleep(600); await pick(SCOPE); await sleep(1200);
  if (await ev(`running`)) console.log("(still running after the menu pick)"); else await press("#startbtn");
} else { await press("#startbtn"); }
await sleep(SECS * 1000);
const L2 = await dump("restarted run");
const said = L2.filter(e => !e.cancel && e.vol !== 0), lost = said.filter(e => e.start === null && !e.err);
console.log(`RESULT: restarted run handed over ${said.length} lines to say, ${lost.length} never started`);
ws.close(); try { proc.kill(); } catch { /* gone */ } srv.close();
process.exit(0);

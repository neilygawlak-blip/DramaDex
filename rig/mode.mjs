// Mode check: start a run in any way of practising and print what the page
// really does: every sentence it hands the browser and the voice that said
// it, every sound cue, every time it opens the mic, and what the screen
// showed. Real Chrome, Chrome muted, a fake mic.
//
//   node rig/mode.mjs [PAGE] [scope] [mode]    e.g. CD_HAROLD run:0 mine
//   RIG_SECS=45 how long to watch; RIG_PAUSE=1 also pauses and resumes.
//
// Built for My Lines Only (2026-11-16): wanted there, a name, then any
// sound, then the actor's line, and no mic at all.
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


const SHIM = `(()=>{const L=window.__log=[];const t0=performance.now();const at=()=>Math.round(performance.now()-t0);
 const S=speechSynthesis,sp=S.speak.bind(S);
 S.speak=u=>{if(u.volume===0)return sp(u);const e={at:at(),say:(u.text||"").slice(0,46),voice:u.voice?u.voice.name.replace("Microsoft ","").replace(" - English (United States)",""):"(default)",start:null,end:null};L.push(e);
  u.addEventListener("start",()=>e.start=at());u.addEventListener("end",()=>e.end=at());return sp(u);};
 const gum=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
 navigator.mediaDevices.getUserMedia=c=>{L.push({at:at(),mic:"getUserMedia"});return gum(c);};
 const R=window.webkitSpeechRecognition;if(R){const st=R.prototype.start;R.prototype.start=function(){L.push({at:at(),mic:"recognizer started"});return st.apply(this,arguments);};}
 addEventListener("load",()=>{const o=window.playSfx;window.playSfx=function(n){if(n)L.push({at:at(),sfx:n});return o.apply(this,arguments);};});})();`;
await send("Page.enable");
await send("Page.addScriptToEvaluateOnNewDocument", { source: SHIM });
await send("Page.navigate", { url: `http://127.0.0.1:${PORT}/${PAGE}.html?v=${Date.now()}#nochime-notrack` });
for (let t = 0; t < 150; t++) { try { if (await ev(`typeof DATA!=="undefined"&&typeof start==="function"&&document.readyState==="complete"`)) break; } catch { /* loading */ } await sleep(100); }
await sleep(1500);
console.log("modes:", await ev(`JSON.stringify([...mode.options].map(o=>o.value+"="+o.textContent))`));
await ev(`(()=>{scope.value=${JSON.stringify(SCOPE)};scope.dispatchEvent(new Event("change",{bubbles:true}));mode.value=${JSON.stringify(HOW)};mode.dispatchEvent(new Event("change",{bubbles:true}));})()`, true);
await ev(`document.querySelector("#startbtn").click()`, true);
const shots=[];
for (let i=0;i<SECS*2;i++){ await sleep(500); const s=await ev(`stage.innerText.replace(/\s+/g," ").slice(0,70)+" | "+whereEl.textContent`); if(shots[shots.length-1]!==s)shots.push(s); }
if (process.env.RIG_PAUSE==="1"){ await ev(`pausebtn.click()`,true); await sleep(1500); await ev(`pausebtn.click()`,true); await sleep(6000); shots.push("(paused and resumed)"); }
const L = JSON.parse(await ev(`JSON.stringify(window.__log)`));
for (const e of L) console.log(e.sfx ? `  ${e.at} ms  SOUND ${e.sfx}` : e.mic ? `  ${e.at} ms  MIC ${e.mic}` : `  ${e.at} ms  [${e.voice}] "${e.say}" ` + (e.start===null?"NEVER STARTED":e.end===null?"speaking":`${e.end-e.start} ms`));
console.log("screen:"); for (const s of shots) console.log("  "+s);
console.log("state:", await ev(`"running="+running+" pos="+pos+" of "+queue.length+" rec="+(typeof rec!=="undefined"&&!!rec)`));
ws.close(); try { proc.kill(); } catch { /* gone */ } srv.close();
process.exit(0);

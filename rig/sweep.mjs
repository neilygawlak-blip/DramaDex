// The sweep: every line of every character through Chrome's real speech
// recognition, to find words the recognizer never writes the way the
// script has them (Chris, 2026-11-12, after "head porter's" came back as
// "headquarters": "go through everyones lines and find any similarities").
//
//   node rig/sweep.mjs david                 every page, voice David
//   node rig/sweep.mjs zira --flagged david  only the lines David's sweep
//                                            left a word unlit on
//   node rig/sweep.mjs david CD_WOMAN,MAN    only those pages
//   RIG_WORKERS=4 (default 3) Chrome windows side by side
//
// Unlike rig.mjs this does not run the page's practice flow. It opens each
// character page for its own matching code (grade, norm, the aliases),
// gives each line a fresh listen of its own, plays the line's recording
// into it, waits for the recognizer to settle, and keeps what it wrote and
// which words of the line that leaves unlit. Results go to
// .rig/sweep_<voice>.json as it goes, so a stopped sweep picks up where it
// left off. Recordings are deleted page by page.
//
// It finds candidates, not truths: a computer voice is not an actor. A
// word two different voices both lose the same way is worth a look.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = path.join(ROOT, "private", "deploy");
const WORK = path.join(ROOT, ".rig");
const PORT = 8791;
const WORKERS = +(process.env.RIG_WORKERS || 3);
const CHROME = ["C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"].find(p => fs.existsSync(p));
const sleep = ms => new Promise(r => setTimeout(r, ms));

const args = process.argv.slice(2);
const VOICE = (args[0] || "david").toLowerCase();
const SAPI = { david: "Microsoft David Desktop", zira: "Microsoft Zira Desktop" }[VOICE];
if (!SAPI) { console.log("voice must be david or zira"); process.exit(2); }
const flagIdx = args.indexOf("--flagged");
const FLAGGED = flagIdx >= 0 ? args[flagIdx + 1] : null;
const ONLY = args[1] && !args[1].startsWith("--") ? args[1].split(",") : null;
const WAVS = path.join(WORK, "sweepwav_" + VOICE);
const OUT = path.join(WORK, `sweep_${VOICE}.json`);

const wavName = t => crypto.createHash("sha1").update(t).digest("hex").slice(0, 16) + ".wav";
function record(texts) {
  fs.mkdirSync(WAVS, { recursive: true });
  const need = [...new Set(texts)].filter(t => !fs.existsSync(path.join(WAVS, wavName(t))));
  if (!need.length) return;
  const job = path.join(WORK, `sweepjob_${VOICE}_${process.pid}_${Math.random().toString(36).slice(2, 7)}.json`);
  fs.writeFileSync(job, JSON.stringify(need.map(t => ({ text: t, file: path.join(WAVS, wavName(t)) }))));
  const ps = `Add-Type -AssemblyName System.Speech;
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono);
$jobs = Get-Content -Raw -Encoding UTF8 '${job}' | ConvertFrom-Json;
foreach ($j in $jobs) { $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SelectVoice('${SAPI}'); $s.SetOutputToWaveFile($j.file, $fmt); $s.Speak($j.text); $s.Dispose() }`;
  const r = spawnSync("powershell", ["-NoProfile", "-Command", ps], { encoding: "utf8", maxBuffer: 1 << 26 });
  fs.rmSync(job, { force: true });
  if (r.status) throw new Error("recording failed: " + r.stderr);
}

const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".json": "application/json",
  ".mp3": "audio/mpeg", ".wav": "audio/wav", ".css": "text/css" };
function serve() {
  return new Promise(res => {
    const srv = http.createServer((req, rsp) => {
      const u = decodeURIComponent(req.url.split("?")[0]);
      if (u === "/__rig") { rsp.writeHead(200, { "content-type": TYPES[".html"] });
        rsp.end("<title>DramaDex sweep</title><body style='font:16px sans-serif;background:#0a0f1e;color:#e8e6df;padding:2rem'>DramaDex sweep: an automated check of every line. Closes by itself."); return; }
      if (u.startsWith("/api/")) { req.resume(); rsp.writeHead(200, { "content-type": "application/json" }); rsp.end('{"ok":true}'); return; }
      const wav = u.startsWith("/__wav/");
      const file = wav ? path.join(WAVS, path.basename(u)) : path.join(SITE, u === "/" ? "index.html" : u);
      if (!file.startsWith(wav ? WAVS : SITE) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { rsp.writeHead(404); rsp.end("not found"); return; }
      rsp.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream", "cache-control": "no-store" });
      fs.createReadStream(file).pipe(rsp);
    });
    srv.listen(PORT, "127.0.0.1", () => res(srv));
  });
}

class Tab {
  constructor(ws) { this.ws = ws; this.id = 0; this.wait = new Map();
    ws.onmessage = m => { const d = JSON.parse(m.data); const w = d.id && this.wait.get(d.id);
      if (w) { this.wait.delete(d.id); d.error ? w.rej(new Error(d.error.message)) : w.res(d.result); } };
    ws.onclose = () => { for (const w of this.wait.values()) w.rej(new Error("Chrome window closed")); this.wait.clear(); }; }
  send(method, params = {}) { const id = ++this.id;
    return new Promise((res, rej) => { this.wait.set(id, { res, rej }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expression) {
    const r = await this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error("page: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    return r.result.value; }
  async until(expression, ms = 10000) { const t0 = Date.now();
    for (;;) { if (await this.ev(`!!(${expression})`)) return true; if (Date.now() - t0 > ms) return false; await sleep(80); } }
}
const open = url => new Promise((res, rej) => { const ws = new WebSocket(url); ws.onopen = () => res(ws); ws.onerror = () => rej(new Error("no connection to Chrome")); });
async function chrome(w) {
  const cdp = 9340 + w;
  const proc = spawn(CHROME, [`--user-data-dir=${path.join(WORK, "sweep_profile_" + w)}`, `--remote-debugging-port=${cdp}`,
    "--remote-allow-origins=*", "--autoplay-policy=no-user-gesture-required", "--use-fake-ui-for-media-stream",
    "--mute-audio", "--no-first-run", "--no-default-browser-check", "--disable-default-apps",
    "--disable-background-timer-throttling", "--disable-renderer-backgrounding", "--disable-backgrounding-occluded-windows",
    "--window-size=420,260", `--window-position=${20 + w * 36},${20 + w * 36}`, `http://127.0.0.1:${PORT}/__rig`], { stdio: "ignore" });
  let list;
  for (let i = 0; i < 80; i++) { try { list = await (await fetch(`http://127.0.0.1:${cdp}/json`)).json(); if (list.some(t => t.type === "page")) break; } catch { /* not up yet */ } await sleep(250); }
  if (!list) throw new Error("Chrome did not start");
  const ver = await (await fetch(`http://127.0.0.1:${cdp}/json/version`)).json();
  const tab = new Tab(await open(list.find(t => t.type === "page").webSocketDebuggerUrl));
  const close = async () => { try { const b = new Tab(await open(ver.webSocketDebuggerUrl)); await Promise.race([b.send("Browser.close"), sleep(1500)]); } catch { /* gone */ } try { proc.kill(); } catch { /* gone */ } };
  return { tab, close };
}

// The rig's track in place of the microphone, and one listen per line.
const SHIM = `(()=>{
 const ac=new AudioContext(),dest=ac.createMediaStreamDestination(),track=dest.stream.getAudioTracks()[0];
 // A real microphone never stops sending: silence is still sound frames.
 // With nothing connected the track sends none, and the recognizer then
 // neither starts nor times out the way it does on a mic. So silence is
 // fed all the time, and the recordings play over it.
 const hush=ac.createConstantSource();hush.offset.value=0;hush.connect(dest);hush.start();
 const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
 const start=SR.prototype.start;SR.prototype.start=function(){return start.call(this,track);};
 if(navigator.mediaDevices)navigator.mediaDevices.getUserMedia=async()=>dest.stream.clone();
 speechSynthesis.speak=()=>{};
 const nap=ms=>new Promise(r=>setTimeout(r,ms));
 window.__tx=async url=>{
  if(ac.state!=="running"){try{await Promise.race([ac.resume(),nap(1500)]);}catch(_){}}
  const buf=await ac.decodeAudioData(await (await fetch(url)).arrayBuffer());
  const r=new SR();r.continuous=true;r.interimResults=true;r.lang="en-US";
  let text="",lastAt=0,err="";
  r.onresult=e=>{let t="";for(let i=0;i<e.results.length;i++)t+=e.results[i][0].transcript+" ";text=t;lastAt=performance.now();};
  r.onerror=e=>{if(e.error!=="aborted")err=e.error;};
  const seen=[];for(const e of ["start","audiostart","soundstart","speechstart","audioend","end"])r.addEventListener(e,()=>seen.push(e));
  const up=new Promise(res=>{r.addEventListener("audiostart",()=>res(true));r.addEventListener("start",()=>res(true));setTimeout(()=>res(false),5000);});
  try{r.start();}catch(x){return {text:"",err:"start "+x.name};}
  if(!await up){try{r.abort();}catch(_){}return {text:"",err:"no start "+err+" (audio "+ac.state+"; events "+seen.join(",")+"; track "+track.readyState+(track.muted?" muted":"")+"; visible "+document.visibilityState+")"};}
  await nap(250);
  const s=ac.createBufferSource();s.buffer=buf;s.connect(dest);s.start();
  await new Promise(res=>{s.onended=res;});
  const tEnd=performance.now();
  while(performance.now()-tEnd<5000){if(performance.now()-Math.max(lastAt,tEnd)>1200)break;await nap(100);}
  try{r.abort();}catch(_){}
  await nap(200);
  return {text:text.trim(),err,secs:Math.round(buf.duration*10)/10};};
})();`;

// ---------- the work ----------
const done = fs.existsSync(OUT) ? JSON.parse(fs.readFileSync(OUT, "utf8")) : {};
const save = () => fs.writeFileSync(OUT, JSON.stringify(done));
let flagged = null;
if (FLAGGED) {
  const f = JSON.parse(fs.readFileSync(path.join(WORK, `sweep_${FLAGGED}.json`), "utf8"));
  flagged = new Set(Object.entries(f).filter(([, r]) => r.unlit && r.unlit.length).map(([k]) => k));
}
const pages = fs.readdirSync(SITE).filter(f => f.endsWith(".html") && fs.readFileSync(path.join(SITE, f), "utf8").includes("function doneEnough"))
  .map(f => f.replace(".html", "")).filter(p => !ONLY || ONLY.includes(p));

const srv = await serve();
const queue = [...pages];
let total = 0, flaggedNow = 0, errors = 0;
const t0 = Date.now();
async function worker(w) {
  let browser;
  try {
    browser = await chrome(w);
    const tab = browser.tab;
    await tab.send("Page.enable");
    await tab.send("Page.addScriptToEvaluateOnNewDocument", { source: SHIM });
    for (;;) {
      const page = queue.shift();
      if (!page) break;
      await tab.send("Page.navigate", { url: `http://127.0.0.1:${PORT}/${page}.html#nochime-notrack-nohold` });
      if (!await tab.until(`typeof DATA!=="undefined"&&document.readyState==="complete"&&window.__tx`, 20000)) { console.log(`${page}: did not load`); errors++; continue; }
      for (const type of ["mousePressed", "mouseReleased"])
        await tab.send("Input.dispatchMouseEvent", { type, x: 5, y: 5, button: "left", clickCount: 1 });
      const lines = await tab.ev(`JSON.stringify(DATA.lines.map((l,k)=>({k,i:l.i,say:l.say})))`).then(JSON.parse);
      const todo = lines.filter(l => !done[`${page}:${l.i}`] && (!flagged || flagged.has(`${page}:${l.i}`)));
      if (!todo.length) { console.log(`${page}: nothing to do`); continue; }
      record(todo.map(l => l.say));
      let n = 0;
      for (const l of todo) {
        let r;
        for (let attempt = 0; attempt < 2; attempt++) {
          r = await tab.ev(`__tx(${JSON.stringify("/__wav/" + wavName(l.say))})`);
          if (!r.err) break;
          await sleep(1500);                 // a blip: one more go
        }
        const g = r.err ? null : await tab.ev(`(()=>{const g=grade(DATA.lines[${l.k}].say,${JSON.stringify(r.text)});return JSON.stringify({unlit:g.marks.filter(m=>!m.ok).map(m=>m.w),words:g.marks.length});})()`).then(JSON.parse);
        done[`${page}:${l.i}`] = r.err ? { err: r.err } : { text: r.text, unlit: g.unlit, words: g.words };
        if (r.err) { errors++; delete done[`${page}:${l.i}`]; if (errors <= 5) console.log(`   ${page}:${l.i} error: ${r.err}`); } else { total++; if (g.unlit.length) flaggedNow++; }
        if (++n % 20 === 0) save();
      }
      save();
      for (const l of todo) fs.rmSync(path.join(WAVS, wavName(l.say)), { force: true });
      console.log(`${page}: ${todo.length} lines done  [${total} so far, ${flaggedNow} with an unlit word, ${errors} errors, ${Math.round((Date.now() - t0) / 60000)} min]`);
    }
  } catch (e) {
    console.log(`worker ${w} stopped: ${e.message}`);
    errors++;
  } finally {
    save();
    if (browser) await browser.close();
  }
}
await Promise.all(Array.from({ length: Math.min(WORKERS, pages.length) }, (_, w) => worker(w)));
srv.close();
save();
console.log(`SWEEP ${VOICE} finished: ${total} lines this run, ${flaggedNow} with an unlit word, ${errors} errors, ${Math.round((Date.now() - t0) / 60000)} min. ${Object.keys(done).length} lines on file.`);
process.exitCode = errors ? 1 : 0;

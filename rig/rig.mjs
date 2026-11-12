// The voice rig: runs the practice page through Chrome's REAL speech
// recognition with no person and no microphone.
//
//   node rig/rig.mjs                     smoke run on CD_HAROLD
//   node rig/rig.mjs CD_RUELLA           smoke run on another page
//   node rig/rig.mjs CD_HAROLD 911,915   those lines (script positions)
//   node rig/rig.mjs CD_HAROLD 911,915 whole   ...each taken that way
//       (whole, nextword, readmine, nextline, slow; a list is used in turn)
//   slow = the way he works a monologue: eight words, a four-second
//   pause, eight more. It reports the moment the line lets go, and every
//   word the recognizer ever showed as the newest one (its guesses change
//   as it listens, and a passing guess can open the gate).
//   longpause = most of the line, twenty-five seconds of silence, the rest.
//   (Found 2026-11-12: silence alone does NOT end a listen here.)
//   restart = most of the line, then the listen is ended the way a network
//   blip ends one, then the rest: the line must keep its credit.
//
// How (proven 2026-11-12, Chrome 157): the recognizer accepts an audio
// track in place of the microphone, recognition.start(track). The rig
// opens the built page from private/deploy in a throwaway Chrome profile,
// makes every recognizer on the page listen to its own track, and plays
// computer-voice recordings of the lines into that track when the page is
// listening. The words go to the same recognition service a real voice
// would, so the partial results, the timing and the restarts are real.
// Chrome is muted and the page's own voice is turned to zero, so it runs
// silent. The real microphone is never opened.
//
// What it cannot show: Bluetooth, the iPhone, a room's echo, a human's
// pauses and stumbles. Those stay with a person (tests.json).
//
// Needs: Windows, Chrome installed, Node 24+, the site built (deploy.cmd
// or build_character_pages.py + prep_deploy.py). Recordings and the Chrome
// profile live in .rig/ (ignored by git: the recordings are play text).
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { spawn, spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const SITE = path.join(ROOT, "private", "deploy");
const WORK = path.join(ROOT, ".rig");
const WAVS = path.join(WORK, "wav");
const PORT = 8790, CDP = 9334;
const CHROME = ["C:/Program Files/Google/Chrome/Application/chrome.exe",
  "C:/Program Files (x86)/Google/Chrome/Application/chrome.exe"].find(p => fs.existsSync(p));
const sleep = ms => new Promise(r => setTimeout(r, ms));

// ---------- the recordings ----------
const wavName = t => crypto.createHash("sha1").update(t).digest("hex").slice(0, 16) + ".wav";
function record(texts) {
  fs.mkdirSync(WAVS, { recursive: true });
  const need = [...new Set(texts)].filter(t => !fs.existsSync(path.join(WAVS, wavName(t))));
  if (!need.length) return;
  const job = path.join(WORK, "job.json");
  fs.writeFileSync(job, JSON.stringify(need.map(t => ({ text: t, file: path.join(WAVS, wavName(t)) }))));
  const ps = `Add-Type -AssemblyName System.Speech;
$fmt = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(48000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono);
$jobs = Get-Content -Raw -Encoding UTF8 '${job}' | ConvertFrom-Json;
foreach ($j in $jobs) { $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; $s.SetOutputToWaveFile($j.file, $fmt); $s.Speak($j.text); $s.Dispose() }`;
  const r = spawnSync("powershell", ["-NoProfile", "-Command", ps], { encoding: "utf8" });
  if (r.status) throw new Error("recording failed: " + r.stderr);
}

// ---------- the site, served from the build folder ----------
const TYPES = { ".html": "text/html; charset=utf-8", ".js": "text/javascript", ".json": "application/json",
  ".mp3": "audio/mpeg", ".wav": "audio/wav", ".css": "text/css" };
function serve() {
  return new Promise(res => {
    const srv = http.createServer((req, rsp) => {
      const u = decodeURIComponent(req.url.split("?")[0]);
      if (u === "/__rig") { rsp.writeHead(200, { "content-type": TYPES[".html"] });
        rsp.end("<title>DramaDex voice rig</title><body style='font:16px sans-serif;background:#0a0f1e;color:#e8e6df;padding:2rem'>DramaDex voice rig: an automated test. This window closes by itself."); return; }
      if (u.startsWith("/api/")) { req.resume(); rsp.writeHead(200, { "content-type": "application/json" }); rsp.end('{"ok":true}'); return; }
      const file = u.startsWith("/__wav/") ? path.join(WAVS, path.basename(u)) : path.join(SITE, u === "/" ? "index.html" : u);
      if (!file.startsWith(u.startsWith("/__wav/") ? WAVS : SITE) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        rsp.writeHead(404); rsp.end("not found"); return; }
      rsp.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream", "cache-control": "no-store" });
      fs.createReadStream(file).pipe(rsp);
    });
    srv.listen(PORT, "127.0.0.1", () => res(srv));
  });
}

// ---------- Chrome ----------
class Tab {
  constructor(ws) { this.ws = ws; this.id = 0; this.wait = new Map();
    ws.onmessage = m => { const d = JSON.parse(m.data); const w = d.id && this.wait.get(d.id);
      if (w) { this.wait.delete(d.id); d.error ? w.rej(new Error(d.error.message)) : w.res(d.result); } }; }
  send(method, params = {}) { const id = ++this.id;
    return new Promise((res, rej) => { this.wait.set(id, { res, rej }); this.ws.send(JSON.stringify({ id, method, params })); }); }
  async ev(expression) {
    const r = await this.send("Runtime.evaluate", { expression, awaitPromise: true, returnByValue: true });
    if (r.exceptionDetails) throw new Error("page: " + (r.exceptionDetails.exception?.description || r.exceptionDetails.text));
    return r.result.value; }
  async until(expression, ms = 10000) { const t0 = Date.now();
    for (;;) { if (await this.ev(`!!(${expression})`)) return true; if (Date.now() - t0 > ms) return false; await sleep(60); } }
  async click(selector) {
    const b = await this.ev(`(()=>{const r=document.querySelector(${JSON.stringify(selector)}).getBoundingClientRect();return [r.x+r.width/2,r.y+r.height/2];})()`);
    for (const type of ["mousePressed", "mouseReleased"])
      await this.send("Input.dispatchMouseEvent", { type, x: b[0], y: b[1], button: "left", clickCount: 1 }); }
}
const open = url => new Promise((res, rej) => { const ws = new WebSocket(url); ws.onopen = () => res(ws); ws.onerror = () => rej(new Error("no connection to Chrome")); });
async function chrome() {
  if (!CHROME) throw new Error("Chrome is not installed where expected");
  const proc = spawn(CHROME, [`--user-data-dir=${path.join(WORK, "profile")}`, `--remote-debugging-port=${CDP}`,
    "--remote-allow-origins=*", "--autoplay-policy=no-user-gesture-required", "--use-fake-ui-for-media-stream",
    "--mute-audio", "--no-first-run", "--no-default-browser-check", "--disable-default-apps",
    "--window-size=560,820", "--window-position=30,30", `http://127.0.0.1:${PORT}/__rig`], { detached: false, stdio: "ignore" });
  let list;
  for (let i = 0; i < 60; i++) { try { list = await (await fetch(`http://127.0.0.1:${CDP}/json`)).json(); if (list.some(t => t.type === "page")) break; } catch { /* not up yet */ } await sleep(250); }
  if (!list) throw new Error("Chrome did not start");
  const ver = await (await fetch(`http://127.0.0.1:${CDP}/json/version`)).json();
  const tab = new Tab(await open(list.find(t => t.type === "page").webSocketDebuggerUrl));
  const close = async () => { try { const b = new Tab(await open(ver.webSocketDebuggerUrl)); await Promise.race([b.send("Browser.close"), sleep(1500)]); } catch { /* gone */ } try { proc.kill(); } catch { /* gone */ } };
  return { tab, close };
}

// What every page gets before its own scripts run: the rig's track in
// place of the microphone, the page's voices turned to nothing, and a
// record of what the page said and what the recognizer reported.
const SHIM = `(()=>{
 const ac=new AudioContext(),dest=ac.createMediaStreamDestination(),track=dest.stream.getAudioTracks()[0];
 const R=window.__rig={ac,said:[],ears:[],bufs:{},playing:0,moved:{},spokeEnd:0,tips:[]};
 const now=()=>Math.round(performance.now());
 setInterval(()=>{try{if(typeof pos!=="undefined"&&R.moved[pos]===undefined)R.moved[pos]=now();}catch(_){}},15);
 const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(SR){const start=SR.prototype.start,abort=SR.prototype.abort;
  SR.prototype.start=function(){
   if(!this.__rig){this.__rig=1;
    for(const e of ["start","end","speechstart"])this.addEventListener(e,()=>R.ears.push([now(),e]));
    this.addEventListener("error",x=>R.ears.push([now(),"error:"+x.error]));
    this.addEventListener("result",x=>{R.results=(R.results||0)+1;R.lastResult=now();
     let t="";for(let i=0;i<x.results.length;i++)t+=x.results[i][0].transcript+" ";
     const w=t.trim().toLowerCase().split(" ").filter(x=>x);const tip=w[w.length-1];
     if(tip&&R.tips[R.tips.length-1]!==tip)R.tips.push(tip);});}
   return start.call(this,track);};
  SR.prototype.abort=function(){R.ears.push([now(),"abort()"]);return abort.call(this);};}
 if(navigator.mediaDevices)navigator.mediaDevices.getUserMedia=async()=>dest.stream.clone();
 const speak=speechSynthesis.speak.bind(speechSynthesis);
 speechSynthesis.speak=u=>{u.volume=0;const rec={t:u.text,at:now(),end:0};
  if(u.text.trim())R.said.push(rec);
  u.addEventListener("end",()=>{rec.end=now();});u.addEventListener("error",e=>{rec.end=now();rec.err=e.error;});
  speak(u);};
 const play=HTMLMediaElement.prototype.play;
 HTMLMediaElement.prototype.play=function(){this.muted=true;return play.call(this);};
 R.load=async url=>R.bufs[url]||(R.bufs[url]=await ac.decodeAudioData(await (await fetch(url)).arrayBuffer()));
 R.say=async url=>{const b=await R.load(url);const s=ac.createBufferSource();s.buffer=b;s.connect(dest);
  R.playing++;s.start();await new Promise(r=>{s.onended=r;});R.playing--;R.spokeEnd=now();return Math.round(b.duration*1000);};
})();`;

// ---------- a run ----------
const args = process.argv.slice(2);
const PAGE = args[0] || "CD_HAROLD";
const WANT = args[1] ? args[1].split(",").map(Number) : null;
const out = [];
const say = s => { console.log(s); out.push(s); };

const srv = await serve();
let browser;
let failed = 0;
try {
  if (!fs.existsSync(path.join(SITE, PAGE + ".html"))) throw new Error("no built page " + PAGE + ".html in private/deploy");
  browser = await chrome();
  const tab = browser.tab;
  await tab.send("Page.enable");
  await tab.send("Page.addScriptToEvaluateOnNewDocument", { source: SHIM });
  await tab.send("Page.navigate", { url: `http://127.0.0.1:${PORT}/${PAGE}.html#nochime-notrack-nohold-rig` });
  if (!await tab.until(`typeof DATA!=="undefined"&&document.readyState==="complete"&&window.__rig`, 15000)) throw new Error("the page did not load");

  // The lines: the ones asked for, else a short, a medium and a long one.
  const lines = await tab.ev(`JSON.stringify(DATA.lines.map((l,k)=>({k,i:l.i,say:l.say,n:norm(l.say).split(" ").filter(w=>w).length,words:norm(l.say).split(" ").filter(w=>w)})))`).then(JSON.parse);
  let pick;
  if (WANT) pick = WANT.map(i => lines.find(l => l.i === i)).filter(Boolean);
  else {
    const by = (lo, hi) => lines.filter(l => l.n >= lo && l.n <= hi);
    pick = [by(4, 7)[0], by(10, 16)[0], by(20, 30)[0], by(10, 16)[1], by(10, 16)[2]].filter(Boolean);
  }
  const P = { whole: l => l.say, head: l => l.words.slice(0, 3).join(" "), rest: l => l.words.slice(3).join(" ") };
  const texts = ["next word", "read my line", "next line"];
  for (const l of pick) texts.push(P.whole(l), P.head(l), P.rest(l));
  const chunks = l => { const c = []; for (let a = 0; a < l.words.length; a += 8) c.push(l.words.slice(a, a + 8).join(" ")); return c; };
  if ((args[2] || "").includes("slow")) for (const l of pick) texts.push(...chunks(l));
  const cut = l => Math.floor(l.n * .7);
  if (/longpause|restart/.test(args[2] || "")) for (const l of pick) texts.push(l.words.slice(0, cut(l)).join(" "), l.words.slice(cut(l)).join(" "));
  say(`rig: ${PAGE}, ${pick.length} lines, recording what is new...`);
  record(texts);
  const url = t => "/__wav/" + wavName(t);
  const speakIn = async t => tab.ev(`__rig.say(${JSON.stringify(url(t))})`);

  await tab.ev(`(()=>{const idx=${JSON.stringify(pick.map(l => l.k))};currentSet=()=>idx;mode.value="drill";})()`);
  await tab.click("#startbtn");
  const ua = await tab.ev("navigator.userAgent");
  say("chrome: " + (/Chrome\/[\d.]+/.exec(ua) || [""])[0] + ", real recognition, audio fed as a track");

  // Each line is taken a different way, in turn.
  const WAYS = args[2] ? args[2].split(",") : ["whole", "nextword", "whole", "readmine", "nextline"];
  for (let k = 0; k < pick.length; k++) {
    const l = pick[k], way = WAYS[k % WAYS.length];
    const head = `line ${k + 1} (i=${l.i}, ${l.n} words, ${way})`;
    if (!await tab.until(`running&&pos===${k}&&judging`, 20000)) { say(`FAIL ${head}: the page never started listening`); failed++; break; }
    const t0 = Date.now();
    const passed = ms => tab.until(`pos>${k}||!running`, ms);
    let note = "";
    if (way === "whole") {
      await speakIn(P.whole(l));
    } else if (way === "nextword") {
      await speakIn(P.head(l));
      await sleep(500);
      const saidBefore = await tab.ev("__rig.said.length");
      await speakIn("next word");
      const spoke = await tab.until(`__rig.said.length>${saidBefore}`, 5000);
      const word = spoke ? await tab.ev(`__rig.said[__rig.said.length-1].t`) : "";
      const lag = spoke ? await tab.ev(`__rig.said[__rig.said.length-1].at-__rig.spokeEnd`) : 0;
      note = spoke ? `page gave "${word}" ${lag >= 0 ? lag + " ms after" : -lag + " ms before"} the command ended` : "PAGE DID NOT GIVE A WORD";
      if (!spoke) failed++;
      await sleep(700);                       // a person hears the word, then goes on
      await speakIn(P.rest(l));
    } else if (way === "readmine") {
      const saidBefore = await tab.ev("__rig.said.length");
      await speakIn("read my line");
      const spoke = await tab.until(`__rig.said.length>${saidBefore}`, 5000);
      note = spoke ? "page read the line" : "PAGE DID NOT READ THE LINE";
      if (!spoke) failed++;
      await tab.until(`__rig.said.length>${saidBefore}&&__rig.said[__rig.said.length-1].end&&judging`, 30000);
      await sleep(400);
      await speakIn(P.whole(l));
    } else if (way === "slow") {
      const cs = chunks(l);
      await tab.ev("__rig.tips=[]");
      const e0 = await tab.ev("__rig.ears.length");
      let saidWords = 0, early = "";
      for (let c = 0; c < cs.length; c++) {
        await speakIn(cs[c]); saidWords += cs[c].split(" ").length;
        const last = c === cs.length - 1;
        if (!last) await sleep(4000);
        const st = await tab.ev(`JSON.stringify({pos,heard:norm(heard).split(" ").filter(w=>w).length,lit:stage.querySelectorAll("#diff .lit").length})`).then(JSON.parse);
        if (!last && st.pos > k) { early = `LET GO EARLY after ${saidWords} of ${l.n} words (chunk ${c + 1} of ${cs.length})`; break; }
        if (!last) say(`     ...after ${saidWords} words and a pause: still on the line, ears hold ${st.heard} words, ${st.lit} lit`);
      }
      const ev = await tab.ev(`JSON.stringify(__rig.ears.slice(${e0}).map(e=>e[1]))`).then(JSON.parse);
      const restarts = ev.filter(e => e === "end").length;
      const tips = await tab.ev("JSON.stringify(__rig.tips)").then(JSON.parse);
      const odd = tips.filter(w => !l.words.includes(w.replace(/[^a-z0-9']/g, "")));
      note = `${restarts} listen(s) ended during it (${[...new Set(ev.filter(e => e.startsWith("error")))].join(", ") || "no errors"}); guesses not in the line: ${[...new Set(odd)].slice(0, 12).join(", ") || "none"}`;
      if (early) { failed++; say(`FAIL ${head}: ${early}; ${note}`); continue; }
    } else if (way === "restart") {
      const e0 = await tab.ev("__rig.ears.length");
      await speakIn(l.words.slice(0, cut(l)).join(" "));
      await sleep(1500);
      await tab.ev("rec.stop()");           // the listen ends without the page asking
      await sleep(2500);
      const mid = await tab.ev(`JSON.stringify({pos,kept:norm(kept).split(" ").filter(w=>w).length,lit:stage.querySelectorAll("#diff .lit").length})`).then(JSON.parse);
      const ev = await tab.ev(`JSON.stringify(__rig.ears.slice(${e0}).map(e=>e[1]))`).then(JSON.parse);
      note = `listen ended and restarted (${ev.filter(e => e === "end").length} end, ${ev.filter(e => e === "start").length} start); credit carried: ${mid.kept} words of the ${cut(l)} said, ${mid.lit} lit`;
      if (mid.pos > k) { failed++; say(`FAIL ${head}: LET GO at the restart; ${note}`); continue; }
      if (!mid.kept) { failed++; note += "; NOTHING CARRIED"; }
      await speakIn(l.words.slice(cut(l)).join(" "));
    } else if (way === "longpause") {
      const e0 = await tab.ev("__rig.ears.length");
      await speakIn(l.words.slice(0, cut(l)).join(" "));
      await sleep(25000);
      const mid = await tab.ev(`JSON.stringify({pos,heard:norm(heard).split(" ").filter(w=>w).length,kept:norm(kept).split(" ").filter(w=>w).length})`).then(JSON.parse);
      const ev = await tab.ev(`JSON.stringify(__rig.ears.slice(${e0}).map(e=>e[1]))`).then(JSON.parse);
      note = `during the silence ${ev.filter(e => e === "end").length} listen(s) ended (${[...new Set(ev.filter(e => e.startsWith("error")))].join(", ") || "no errors"}); credit carried: ${mid.kept} words`;
      if (mid.pos > k) { failed++; say(`FAIL ${head}: LET GO during the silence; ${note}`); continue; }
      await speakIn(l.words.slice(cut(l)).join(" "));
    } else if (way === "nextline") {
      await speakIn(P.head(l));
      await sleep(400);
      await speakIn("next line");
    }
    const ok = await passed(8000);
    // On the page's own clock: when the run moved on, against when the last
    // recording ended. Negative means it let go before the words were out.
    const gap = await tab.ev(`(__rig.moved[${k + 1}]||0)-__rig.spokeEnd`);
    const state = await tab.ev(`JSON.stringify({heard:norm(heard).split(" ").filter(w=>w).length,lit:stage.querySelectorAll("#diff .lit").length,results:__rig.results||0})`).then(JSON.parse);
    if (ok) say(`ok   ${head}: passed ${gap >= 0 ? gap + " ms after" : -gap + " ms BEFORE"} the recording ended, ${((Date.now() - t0) / 1000).toFixed(1)} s on the line${note ? "; " + note : ""}`);
    else {
      failed++;
      say(`FAIL ${head}: did not pass within 8 s of the last word; ears held ${state.heard} words, ${state.lit} of ${l.n} lit${note ? "; " + note : ""}`);
      await tab.ev(`document.getElementById("gotbtn")&&document.getElementById("gotbtn").click()`);
    }
  }
  const ears = await tab.ev(`JSON.stringify(__rig.ears)`).then(JSON.parse);
  const count = e => ears.filter(x => x[1] === e).length;
  const errs = ears.filter(x => x[1].startsWith("error:") && x[1] !== "error:aborted").map(x => x[1]);
  say(`ears: ${count("start")} listens started, ${count("abort()")} cut by the page, errors: ${errs.length ? [...new Set(errs)].join(", ") : "none"}`);
  const lost = await tab.ev(`__rig.said.filter(s=>!s.end).length`);
  say(`page voice: ${await tab.ev("__rig.said.length")} things said, ${lost} never reported an end`);
  say(failed ? `RESULT: ${failed} problem(s)` : "RESULT: all passed");
} catch (e) {
  failed++;
  say("RIG ERROR: " + e.message);
} finally {
  if (browser) await browser.close();
  srv.close();
  fs.mkdirSync(WORK, { recursive: true });
  fs.writeFileSync(path.join(WORK, "last_report.txt"), out.join("\n") + "\n");
}
process.exitCode = failed ? 1 : 0;

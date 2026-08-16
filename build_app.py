"""Build the sellable single-user app: app/index.html.

The product is scan-your-own-in rehearsal: import a script (photos ->
on-device OCR, or pasted text), confirm the cast, fix the stragglers,
pick your part, practice. It ships ONLY what the cast sees on the
DramaDex site -- the practice runtime and the read-through -- lifted
VERBATIM from build_character_pages so there is one source of truth.
None of the internal work ships: no voice cloning, no golden keys, no
workbench knobs, no French scenes, no Neil's Lab.

Everything runs on the user's device: rule-based parsing, Tesseract.js
OCR (CDN here; bundled when this wraps for the app stores), Web Speech
for the mic and the voices, localStorage for the shelf. No LLM, no
server, no account.

Usage: python build_app.py     -> app/index.html
"""

import json
import os
import re

from build_character_pages import READ_TEMPLATE, TEMPLATE


def strip_product(t, kind):
    """Remove the parts of the cast-site runtime that are ours, not the
    product's. Every surgery asserts, so a template edit that moves the
    furniture fails the build instead of silently shipping lab gear."""
    def cut(s, frag, repl=""):
        assert frag in s, "missing fragment: %.60r" % frag
        return s.replace(frag, repl)

    # Real-voices machinery: the product has no rendered clips.
    t = re.sub(r"// ---- real cast voices.*?voxchk\.onchange=[^\n]*\n",
               "let VOX=new Set();const voxchk={checked:false};\n",
               t, count=1, flags=re.S)
    assert "voices/manifest.json" not in t
    t = re.sub(r'\s*<label id="voxwrap".*?</label>', "", t, count=1,
               flags=re.S)
    if kind == "practice":
        # The bug-report button mails Neil; the product has no Neil.
        t = re.sub(r'\s*<a id="reportbtn".*?</a>', "", t, count=1, flags=re.S)
        t = re.sub(r"// ---- error capture.*?What happened / what needs "
                   r"fixing:\\n\"\);};\n", "", t, count=1, flags=re.S)
        t = re.sub(r"\s*#reportbtn\{[^}]*\}", "", t)
        t = re.sub(r"\s*#reportbtn:hover\{[^}]*\}", "", t)
        assert "reportbtn" not in t and "Tell Neil" not in t
    # Build stamp: meaningless for an imported play.
    t = re.sub(r'\s*<div id="build">[^<]*</div>', "", t, count=1)
    # The back button walks the app's own router instead of a URL.
    t = cut(t, '<a id="backbtn" href="__HOME__">',
            '<a id="backbtn" href="#" '
            'onclick="parent.appBack();return false">')
    return t


APP = r"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>DramaDex — rehearse your part</title>
<style>
 body{font-family:"Segoe UI Variable Display","Segoe UI",system-ui,"Helvetica Neue",Arial,sans-serif;
      font-weight:500;letter-spacing:.012em;max-width:640px;margin:0 auto;
      padding:1.4rem 1rem 4rem;background:#0a0f1e;color:#e8e6df;line-height:1.55}
 h1{font-size:1.35rem;font-weight:800;letter-spacing:.03em;color:#ffd75e;margin:.2rem 0}
 h2{font-size:1rem;color:#ffd75e;margin:1.2rem 0 .4rem}
 .muted{color:#7d87a3;font-size:.88rem;font-weight:400}
 button,select,input[type=text]{font-size:1rem;padding:.5rem .85rem;margin:.25rem .3rem .25rem 0;
      border:1px solid #2b3a5e;border-radius:8px;background:#111a30;color:#e8e6df;cursor:pointer}
 input[type=text]{cursor:text;width:100%;box-sizing:border-box}
 button.primary{background:#0d1526;color:#ffd75e;border:1px solid #ffd75e;
      text-shadow:0 0 6px #ffb347,0 0 14px #ff9d1c;
      box-shadow:0 0 8px rgba(255,183,71,.45),inset 0 0 8px rgba(255,183,71,.15)}
 button:disabled{opacity:.4;cursor:default}
 textarea{width:100%;box-sizing:border-box;min-height:11rem;background:#111a30;
      color:#e8e6df;border:1px solid #2b3a5e;border-radius:8px;padding:.6rem;font-size:.9rem}
 .rowlink{display:block;padding:.7rem 1rem;margin:.4rem 0;border:1px solid #2b3a5e;
      border-radius:10px;color:#e8e6df;text-decoration:none;background:#111a30;cursor:pointer}
 .rowlink:hover{border-color:#ffd75e;box-shadow:0 0 10px rgba(255,183,71,.35)}
 .rowlink small{color:#7d87a3;display:block;margin-top:.1rem}
 .card{margin:.8rem 0;padding:.9rem 1rem;border:1px solid #2b3a5e;border-radius:12px;
      background:linear-gradient(160deg,#111a30,#0d1526)}
 .card .ptext{font-family:Georgia,serif;font-size:.92rem;color:#c9d2ea;margin:.3rem 0 .6rem}
 .card .neighbor{font-size:.78rem;color:#55618a}
 .castrow{display:flex;gap:.5rem;align-items:center;margin:.3rem 0}
 .castrow input[type=text]{width:5.5rem;flex:none;text-align:center}
 .castrow b{flex:1;letter-spacing:.04em}
 .castrow small{color:#55618a}
 .pill{display:inline-block;font-size:.75rem;border:1px solid #3a4a75;border-radius:999px;
      padding:.1rem .6rem;color:#9aa4c0;margin-left:.4rem}
 #ocrlog{font-size:.8rem;color:#7d87a3;white-space:pre-line;max-height:9rem;overflow:auto}
 .danger{color:#ff9d9d;border-color:#5e2b2b}
 #stagewrap{position:fixed;inset:0;background:#0a0f1e;display:none;z-index:20}
 #stage{width:100%;height:100%;border:0}
 .step{display:none}
 .bar{height:6px;border-radius:3px;background:#111a30;border:1px solid #2b3a5e;overflow:hidden;margin:.4rem 0}
 .bar div{height:100%;width:0;background:linear-gradient(90deg,#7fe0a7,#ffd75e)}
 .footnote{margin-top:2.5rem;font-size:.72rem;color:#39415e;text-align:center}
</style></head><body>

<div id="home">
 <h1>&#127917; DramaDex</h1>
 <div class="muted">Your script, your device. Scan it in, pick your
 part, and rehearse hands-free. Nothing leaves this device.</div>
 <h2>Your plays</h2>
 <div id="shelf"></div>
 <button class="primary" id="newbtn">&#10133; New Play</button>
 <div class="footnote">All parsing, reading and listening happens on
 this device. No account, no upload, no tracking.</div>
</div>

<div id="wizard" style="display:none">
 <h1>&#127917; New Play</h1>

 <div class="step" id="step-title">
  <h2>What's it called?</h2>
  <input type="text" id="wtitle" placeholder="Play title">
  <input type="text" id="wauthor" placeholder="Author (optional)" style="margin-top:.4rem">
  <p class="muted">Use your own lawfully owned script. This app never
  copies, stores or sends the text anywhere off this device.</p>
  <button class="primary" id="titlenext">Next</button>
  <button id="wcancel1">Cancel</button>
 </div>

 <div class="step" id="step-source">
  <h2>Bring in the script</h2>
  <div class="card"><b>&#128196; PDF</b>
   <p class="muted">Typed or scanned — both work. A scanned PDF is
   read page by page right here on the device (this takes a minute).
   Tip: any scanner or phone scan app can save straight to PDF.</p>
   <input type="file" id="wpdf" accept=".pdf,application/pdf">
   <div class="bar" id="ocrbar" style="display:none"><div></div></div>
  </div>
  <div class="card"><b>&#128203; Text</b>
   <p class="muted">Paste the whole script, or pick a .txt file.</p>
   <input type="file" id="wtxt" accept=".txt,text/plain">
   <textarea id="wpaste" placeholder="LILI: Did you see him? ..."></textarea>
  </div>
  <div id="ocrlog"></div>
  <button class="primary" id="srcnext" disabled>Next</button>
  <button id="wcancel2">Cancel</button>
 </div>

 <div class="step" id="step-cast">
  <h2>Are these all the characters?</h2>
  <p class="muted">Found in your script. Untick anything that isn't a
  character; add anyone missing. The emoji is your call.</p>
  <div id="castlist"></div>
  <input type="text" id="addcast" placeholder="Add a missing character name (optional)">
  <button id="addcastbtn">Add</button>
  <div><button class="primary" id="castnext">Yes, that's everyone</button>
  <button id="wcancel3">Cancel</button></div>
 </div>

 <div class="step" id="step-triage">
  <h2>A few stragglers</h2>
  <p class="muted" id="triagecount"></p>
  <div id="triagecard"></div>
 </div>

 <div class="step" id="step-done">
  <h2>&#127881; Ready to rehearse</h2>
  <p class="muted" id="donesummary"></p>
  <button class="primary" id="donebtn">Open the play</button>
 </div>
</div>

<div id="playview" style="display:none">
 <h1 id="pvtitle"></h1>
 <div class="muted" id="pvauthor"></div>
 <h2>Pick your character</h2>
 <div id="pvcast"></div>
 <div style="margin-top:1.2rem">
  <button id="pvback">&#8592; Your plays</button>
  <button class="danger" id="pvdelete">Delete this play</button>
 </div>
</div>

<div id="stagewrap"><iframe id="stage" allow="microphone; autoplay"></iframe></div>

<script>
"use strict";
const PRACTICE_T=__PRACTICE_T__;
const READ_T=__READ_T__;
// ~10k most common English words. A script word not on this list gets
// a small bounded fuzzy allowance in grading (names, foreign words).
const COMMON=new Set(__COMMON__);
function looseWords(speeches){
 const out=new Set();
 speeches.forEach(s=>{
  if(!s.say)return;
  const t=s.say.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g,"");
  (t.match(/[a-z]+/g)||[]).forEach(w=>{
   if(w.length>=4&&!COMMON.has(w))out.add(w);});
 });
 return [...out].sort();
}

// ---------- storage ----------
const DB="dramadex_plays";
const store={
 all(){try{return JSON.parse(localStorage.getItem(DB))||[]}catch(_){return[]}},
 save(p){const a=store.all().filter(x=>x.id!==p.id);a.push(p);
  localStorage.setItem(DB,JSON.stringify(a));},
 del(id){localStorage.setItem(DB,JSON.stringify(store.all().filter(x=>x.id!==id)));},
 get(id){return store.all().find(x=>x.id===id);}
};

// ---------- script analysis (the same rules the cast site uses) ----------
const HEAD_RE=/^(ACT|SCENE|TIME|SETTING|AT RISE|CURTAIN|QUICK CURTAIN|THE CURTAIN|WARN|END OF|PROPS|COSTUMES|CHARACTERS)\b/;
const ACT_RE=/^ACT\s+(ONE|TWO|THREE|FOUR|1|2|3|4|IV|III|II|I)\b/;
const ACT_NAMES={ONE:"Act I",TWO:"Act II",THREE:"Act III",FOUR:"Act IV",
 "1":"Act I","2":"Act II","3":"Act III","4":"Act IV",
 I:"Act I",II:"Act II",III:"Act III",IV:"Act IV"};
const TOGETHER_RE=/\(together\b/i;
const PACE_FAST=/hurried|quickly|rapid|briskly|rushing|excited|wildly|frantic|shout|scream|yell/i;
const PACE_SLOW=/slowly|ponderous|heavily|drawl|dazed|vaguely|murmur|sleepy|solemn/i;
// Generic effect cues, matched only against text in (directions).
const SFX_LIST=[["doorbell",/DOORBELL|DOOR-?BELL/i],["phone",/PHONE RINGS|TELEPHONE RINGS|phone rings|phone buzzes/],
 ["bump",/KNOCK AT (THE )?DOOR|KNOCKING|loud HAMMERING/],["crash",/CRASH/],
 ["slam",/slams the door|door[- ]slam/i],["bell",/\bBELL rings\b/]];

// PDF text and OCR text arrive with a newline per PRINTED line and few
// blank lines, so blank-line splitting alone would glue whole pages
// into one paragraph. When that shape is detected, paragraphs restart
// at every speaker-looking line, direction, or heading instead.
const LINE_SPEAKER=/^\s*(?:OS\s+)?[A-Z][A-Z .'&/-]{1,24}?\s*(?:\([^)]*\))?\s*[:.]\s/;
function paragraphs(text){
 const blank=text.split(/\n\s*\n/).map(p=>p.replace(/\s+/g," ").trim()).filter(Boolean);
 const lines=text.split("\n").map(l=>l.trim()).filter(Boolean);
 const speakerLines=lines.filter(l=>LINE_SPEAKER.test(l)).length;
 if(blank.length>=speakerLines*0.8||speakerLines<4)return blank;
 const out=[];let cur="";
 const push=()=>{if(cur.trim())out.push(cur.replace(/\s+/g," ").trim());cur="";};
 lines.forEach(l=>{
  if(/^\d{1,4}$/.test(l))return;              // stray page numbers
  if(LINE_SPEAKER.test(l)||l.startsWith("(")||ACT_RE.test(l)||HEAD_RE.test(l)){push();}
  cur+=" "+l;
 });
 push();
 return out;
}
// "OS ARNOLD:" / "VOICE OF ARNOLD:" mean Arnold, offstage. Fold the
// prefix into a direction so the same character never splits in two.
const OS_RE=/^((?:OS|O\.S\.|OFFSTAGE|VOICE OF)\s+)([A-Z][A-Z .'&-]{1,24}?\s*[:.])/;
function normalizeOffstage(paras){
 return paras.map(p=>{
  const m=p.match(OS_RE);
  if(!m)return p;
  return p.replace(OS_RE,(a,pre,name)=>name.replace(/\s*([:.])$/," (off)$1"));
 });
}
// Generic stage vocabulary that LOOKS like a speaker but usually
// isn't a practicable character: suggested unticked, user's call.
const GENERIC=new Set(["VOICE","VOICES","ALL","BOTH","EVERYONE","OMNES",
 "CROWD","OFFSTAGE","OS","TOGETHER"]);
function detectCast(paras){
 const counts={};
 paras.forEach(p=>{
  const m=p.match(/^([A-Z][A-Z .'&-]{1,24}?)\s*(\([^)]*\))?\s*[:.]/);
  if(!m)return;
  const n=m[1].trim().replace(/\s+/g," ");
  if(HEAD_RE.test(n)||n.length<2)return;
  counts[n]=(counts[n]||0)+1;
 });
 return Object.entries(counts).filter(([n,c])=>c>=2)
  .sort((a,b)=>b[1]-a[1]).map(([n,c])=>({name:n,count:c}));
}
function speechRe(cast){
 const esc=s=>s.replace(/[.*+?^${}()|[\]\\]/g,"\\$&");
 return new RegExp("^("+cast.slice().sort((a,b)=>b.length-a.length).map(esc).join("|")+")\\b");
}
function spoken(text,speaker){
 let t=text;
 if(t.toUpperCase().startsWith(speaker.toUpperCase()))t=t.slice(speaker.length);
 t=t.replace(/\([^)]*\)/g," ");
 t=t.replace(/^\s*and\s+[A-Z][A-Z ]+?\s*[.:]/,"");
 t=t.replace(/^[ .:]+/,"");
 return t.replace(/\s+/g," ").trim();
}
function paceOf(text){
 const d=(text.match(/\(([^)]*)\)/g)||[]).join(" ");
 if(PACE_FAST.test(d))return 1.6;
 if(PACE_SLOW.test(d))return 1.0;
 return 1.3;
}
function sfxOf(p){
 const dirs=(p.match(/\(([^)]*)\)/g)||[]).join(" ")+(p.startsWith("(")?p:"");
 for(const[n,rx]of SFX_LIST)if(rx.test(dirs))return n;
 return null;
}
// Classify every paragraph; only genuine mid-play ambiguity reaches
// triage. Front matter (title page, rights notice, the character list
// with its descriptions) and back matter (THE END, prop and costume
// plots) are recognized and skipped for the user: the play runs from
// its first act heading (or first scene heading, or first line of
// dialogue) to its end marker.
const END_RE=/^(THE END\b|END OF (THE )?PLAY|Blackout End of Play|PROPS\b|COSTUMES\b|FURNITURE PLOT|PROPERTY PLOT|EFFECTS PLOT|CURTAIN CALL)/i;
function classify(paras,cast){
 const re=speechRe(cast);
 let start=paras.findIndex(p=>ACT_RE.test(p));
 if(start<0)start=paras.findIndex(p=>/^(AT RISE|SCENE|SETTING)\b/.test(p));
 if(start<0)start=paras.findIndex(p=>re.test(p));
 if(start<0)start=0;
 let end=paras.findIndex((p,i)=>i>start&&END_RE.test(p));
 if(end<0)end=paras.length;
 const out=[];
 paras.forEach((p,idx)=>{
  if(idx<start||idx>=end){out.push({k:"front",p});return;}
  if(ACT_RE.test(p)){out.push({k:"act",p});return;}
  if(HEAD_RE.test(p)){out.push({k:"head",p});return;}
  if(re.test(p)){out.push({k:"sp",p});return;}
  if(p.startsWith("(")){out.push({k:"dir",p});return;}
  const prev=out.length&&out[out.length-1];
  if(prev&&prev.k==="sp"&&/[a-z]/.test(p)){out.push({k:"stitch",p});return;}
  out.push({k:"orphan",p});
 });
 return out;
}
// Build the parsed speech list from classified paragraphs.
function buildSpeeches(classified,cast){
 const re=speechRe(cast);
 let act="Front matter";const speeches=[];
 classified.forEach(c=>{
  if(c.k==="drop"||c.k==="front")return;
  if(c.k==="act"){const m=c.p.match(ACT_RE);act=ACT_NAMES[m[1]]||"Act I";return;}
  if(c.k==="head")return;
  const p=c.k==="dirform"?"("+c.p+")":c.p;
  if(act==="Front matter"&&re.test(p))act="Act I";
  const m=re.exec(p);
  const sfx=sfxOf(p);
  if(c.k==="stitch"&&speeches.length&&speeches[speeches.length-1].speaker){
   const prev=speeches[speeches.length-1];
   prev.text+=" "+p;prev.say=spoken(prev.text,prev.speaker);
   prev.sfx=prev.sfx||sfx;return;
  }
  speeches.push({act,speaker:m?m[1]:null,text:p,
   say:m?spoken(p,m[1]):"",sfx});
 });
 // together groups, same rule as the cast site
 let gid=0,i=0;
 while(i<speeches.length){
  let j=i;
  while(speeches[j].speaker&&TOGETHER_RE.test(speeches[j].text)
   &&j+1<speeches.length&&speeches[j+1].speaker
   &&TOGETHER_RE.test(speeches[j+1].text))j++;
  if(j>i){gid++;for(let k=i;k<=j;k++)speeches[k].gid=gid;}
  i=j+1;
 }
 return speeches;
}
function cueFor(sp,i){
 for(let j=i-1;j>=0;j--){
  const s=sp[j];
  if(sp[i].gid&&s.gid===sp[i].gid)continue;
  if(s.speaker&&s.say){
   let tail=s.say;
   if(tail.length>160)tail="… "+tail.slice(-160);
   return{speaker:s.speaker,say:tail,l:"",sfx:sp[i-1].sfx||s.sfx,
    mood:"\u{1F642}",pace:paceOf(s.text)};
  }
  if(s.sfx)return{speaker:"",say:"",sfx:s.sfx,mood:"\u{1F642}"};
 }
 return{speaker:"",say:"(top of the play)",sfx:null,mood:"\u{1F642}"};
}
function runsFor(sp,name){
 const GAP=15,MIN=4;
 const runs=[];let cur=[],last=null;
 sp.forEach((s,i)=>{
  if(s.speaker!==name||!s.say)return;
  if(cur.length&&(i-last>GAP||s.act!==sp[cur[0]].act)){runs.push(cur);cur=[];}
  cur.push(i);last=i;
 });
 if(cur.length)runs.push(cur);
 const merged=[];
 runs.forEach(r=>{
  const same=merged.length&&sp[merged[merged.length-1][0]].act===sp[r[0]].act;
  if(same&&(r.length<MIN||merged[merged.length-1].length<MIN))
   merged[merged.length-1].push(...r);
  else merged.push(r);
 });
 const out=[],counts={};
 merged.forEach(r=>{
  const a=sp[r[0]].act;counts[a]=(counts[a]||0)+1;
  out.push({label:a+" — run "+counts[a],lines:r});
 });
 return out;
}
function dataFor(play,name){
 const sp=play.speeches;
 const voices={},avatars={};
 play.cast.forEach(c=>{voices[c.name]={g:"?",style:"casual",mult:1};
  avatars[c.name]=c.emoji||"";});
 const lines=[];let prev=-1;
 sp.forEach((s,i)=>{
  if(s.speaker!==name||!s.say)return;
  const gap=[];
  for(let j=prev+1;j<i;j++){const g=sp[j];
   if(s.gid&&g.gid===s.gid)continue;
   if(g.speaker&&g.say)gap.push({s:g.speaker,t:g.say,l:"",m:"\u{1F642}",
    p:paceOf(g.text),x:g.sfx});
   else if(g.sfx)gap.push({s:"",t:"",m:"\u{1F642}",p:1.3,x:g.sfx});}
  const rec={i,act:s.act,say:s.say,l:"",page:0,cue:cueFor(sp,i),gap};
  if(s.gid)rec.sim=sp.filter(g=>g.gid===s.gid&&g!==s)
   .map(g=>({s:g.speaker,t:g.say,l:"",m:"\u{1F642}"}));
  lines.push(rec);prev=i;
 });
 return{lines,runs:runsFor(sp,name),voices,avatars,loose:play.loose||[]};
}
function readData(play){
 const items=[];const sp=play.speeches;
 const voices={},avatars={};
 play.cast.forEach(c=>{voices[c.name]={g:"?",style:"casual",mult:1};
  avatars[c.name]=c.emoji||"";});
 for(let i=0;i<sp.length;i++){const s=sp[i];
  if(s.speaker&&s.say){
   const ent={s:s.speaker,t:s.say,l:"",p:paceOf(s.text),x:s.sfx,act:s.act};
   if(s.gid&&items.length&&items[items.length-1].gid===s.gid){
    items[items.length-1].sim.push(ent);continue;}
   if(s.gid){ent.gid=s.gid;ent.sim=[];}
   items.push(ent);
  }else if(s.sfx)items.push({s:"",t:"",x:s.sfx,act:s.act});
 }
 return{items,voices,avatars};
}

// ---------- views ----------
const $=id=>document.getElementById(id);
function show(view){["home","wizard","playview"].forEach(v=>$(v).style.display=v===view?"":"none");
 $("stagewrap").style.display="none";window.scrollTo(0,0);}
function step(s){document.querySelectorAll(".step").forEach(e=>e.style.display="none");
 $("step-"+s).style.display="block";}
function esc(s){return String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));}

function renderShelf(){
 const plays=store.all().sort((a,b)=>b.created-a.created);
 $("shelf").innerHTML=plays.length?"":'<p class="muted">Nothing yet. Scan in your first script.</p>';
 plays.forEach(p=>{
  const d=document.createElement("div");d.className="rowlink";
  d.innerHTML="<b>"+esc(p.title)+"</b><small>"+
   (p.author?"by "+esc(p.author)+" · ":"")+
   p.cast.length+" characters · "+
   p.speeches.filter(s=>s.speaker).length+" lines</small>";
  d.onclick=()=>openPlay(p.id);
  $("shelf").appendChild(d);
 });
}

// ---------- wizard ----------
let wiz=null;
$("newbtn").onclick=()=>{wiz={id:String(Date.now()),text:""};
 $("wtitle").value="";$("wauthor").value="";$("wpaste").value="";
 $("wpdf").value="";$("wtxt").value="";
 $("ocrlog").textContent="";$("srcnext").disabled=true;
 show("wizard");step("title");};
["wcancel1","wcancel2","wcancel3"].forEach(id=>$(id).onclick=()=>{show("home");renderShelf();});
$("titlenext").onclick=()=>{
 const t=$("wtitle").value.trim();
 if(!t){$("wtitle").focus();return;}
 wiz.title=t;wiz.author=$("wauthor").value.trim();step("source");};

$("wpaste").oninput=()=>{$("srcnext").disabled=!$("wpaste").value.trim()&&!wiz.text;};

// OCR path: Tesseract.js, loaded only when needed. CDN for now;
// bundled with the app when it wraps for the stores.
let tessReady=null;
function loadTesseract(){
 if(tessReady)return tessReady;
 tessReady=new Promise((res,rej)=>{
  const s=document.createElement("script");
  s.src="https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/tesseract.min.js";
  s.onload=res;s.onerror=()=>rej(new Error("Could not load the OCR engine (offline?)"));
  document.head.appendChild(s);
 });
 return tessReady;
}
$("wtxt").onchange=async()=>{
 const f=$("wtxt").files[0];if(!f)return;
 wiz.text=await f.text();
 $("ocrlog").textContent="Loaded "+f.name+" ("+wiz.text.split(/\s+/).length+" words).";
 $("srcnext").disabled=false;
};
// PDF path: pdf.js reads the text layer on-device. CDN for now,
// bundled when this wraps for the stores.
let pdfReady=null;
function loadPdfjs(){
 if(pdfReady)return pdfReady;
 pdfReady=new Promise((res,rej)=>{
  const s=document.createElement("script");
  s.src="https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.min.js";
  s.onload=()=>{pdfjsLib.GlobalWorkerOptions.workerSrc=
   "https://cdn.jsdelivr.net/npm/pdfjs-dist@3.11.174/build/pdf.worker.min.js";res();};
  s.onerror=()=>rej(new Error("Could not load the PDF engine (offline?)"));
  document.head.appendChild(s);
 });
 return pdfReady;
}
$("wpdf").onchange=async()=>{
 const f=$("wpdf").files[0];if(!f)return;
 const log=$("ocrlog");
 const bar=$("ocrbar"),fill=bar.firstElementChild;
 try{
  await loadPdfjs();
  const doc=await pdfjsLib.getDocument({data:await f.arrayBuffer()}).promise;
  const all=[];
  for(let i=1;i<=doc.numPages;i++){
   const tc=await(await doc.getPage(i)).getTextContent();
   // Spacing is reconstructed from GEOMETRY, the way real extractors
   // do it: fragments touching on the page join ("th"+"r"+"ee" ->
   // three), fragments with a real horizontal gap get a space, and a
   // vertical jump is a new line. Trusting the PDF's own space
   // fragments shattered words in both directions.
   let page="",last=null;
   for(const it of tc.items){
    if(!it.str){last=it.width?it:last;continue;}
    if(last){
     const dy=Math.abs(it.transform[5]-last.transform[5]);
     if(dy>2)page+="\n";
     else{
      const gap=it.transform[4]-(last.transform[4]+last.width);
      if(gap>(it.height||10)*0.12)page+=" ";
     }
    }
    page+=it.str;
    last=it;
   }
   all.push(page);
   log.textContent="Reading page "+i+" of "+doc.numPages+"…";
  }
  let text=all.join("\n\n");
  if(text.replace(/\s/g,"").length<80){
   // No text layer: a scanned PDF. Render each page and read it
   // right here — slower, but nothing ever leaves the device.
   log.textContent="This PDF is a scan — reading it page by page…";
   await loadTesseract();
   const worker=await Tesseract.createWorker("eng");
   bar.style.display="";
   const pages=[];
   for(let i=1;i<=doc.numPages;i++){
    const pg=await doc.getPage(i);
    // Render around 2000px wide: enough detail for OCR, without
    // building a monster canvas from a high-res phone scan.
    const vp1=pg.getViewport({scale:1});
    const vp=pg.getViewport({scale:Math.min(2,2000/vp1.width)});
    const cv=document.createElement("canvas");
    cv.width=vp.width;cv.height=vp.height;
    // intent:"print" renders without waiting on animation frames, so
    // the OCR keeps working when the tab is backgrounded mid-import.
    await pg.render({canvasContext:cv.getContext("2d"),viewport:vp,
     intent:"print"}).promise;
    const{data}=await worker.recognize(cv);
    pages.push(data.text);
    fill.style.width=Math.round(i/doc.numPages*100)+"%";
    log.textContent="Read page "+i+" of "+doc.numPages+"…";
   }
   await worker.terminate();
   text=pages.join("\n\n");
  }
  wiz.text=text;
  log.textContent="Read "+doc.numPages+" pages, "+
   text.split(/\s+/).length+" words.";
  $("srcnext").disabled=false;
 }catch(e){log.textContent="⚠ "+e.message;}
};
$("srcnext").onclick=()=>{
 const pasted=$("wpaste").value.trim();
 const text=pasted||wiz.text;
 if(!text)return;
 wiz.paras=normalizeOffstage(paragraphs(text));
 wiz.castGuess=detectCast(wiz.paras);
 // OCR sometimes spaces a name out ("KRIST I N"): a candidate whose
 // letters match a stronger candidate's letters is the same person.
 // Fold it — rewrite its paragraphs and merge the counts.
 const compact=n=>n.replace(/[^A-Z]/g,"");
 const keep=[];
 wiz.castGuess.forEach(c=>{
  const twin=keep.find(b=>compact(b.name)===compact(c.name));
  if(twin){
   const rx=new RegExp("^"+c.name.replace(/[.*+?^${}()|[\]\\]/g,"\\$&"));
   wiz.paras=wiz.paras.map(p=>rx.test(p)?p.replace(rx,twin.name):p);
   twin.count+=c.count;
  }else keep.push(c);
 });
 wiz.castGuess=keep;
 renderCast();step("cast");
};
function renderCast(){
 const el=$("castlist");el.innerHTML="";
 wiz.castGuess.forEach((c,i)=>{
  const row=document.createElement("div");row.className="castrow";
  const on=GENERIC.has(c.name)?"":" checked";
  row.innerHTML='<input type="checkbox"'+on+' data-i="'+i+'">'+
   '<b>'+esc(c.name)+'</b><small>'+c.count+' lines'+
   (on?"":" · probably not a character")+'</small>'+
   '<input type="text" maxlength="4" placeholder="emoji" data-e="'+i+'">';
  el.appendChild(row);
 });
}
$("addcastbtn").onclick=()=>{
 const n=$("addcast").value.trim().toUpperCase();
 if(!n)return;
 wiz.castGuess.push({name:n,count:0});
 $("addcast").value="";renderCast();
};
$("castnext").onclick=()=>{
 const cast=[];
 document.querySelectorAll("#castlist input[type=checkbox]").forEach(cb=>{
  if(!cb.checked)return;
  const i=+cb.dataset.i;
  const emoji=document.querySelector('#castlist input[data-e="'+i+'"]').value.trim();
  cast.push({name:wiz.castGuess[i].name,emoji});
 });
 if(!cast.length)return;
 wiz.cast=cast;
 wiz.classified=classify(wiz.paras,cast.map(c=>c.name));
 // No questions (Chris's call): stragglers are auto-filed with the
 // best-guess rule — reads like the tail of the previous speech, it's
 // stitched on; otherwise it's a stage direction. The done screen says
 // how many were filed.
 wiz.autoFiled=0;
 wiz.classified.forEach((c,i)=>{
  if(c.k!=="orphan")return;
  const prev=wiz.classified[i-1];
  c.k=(prev&&prev.k==="sp"&&/^[a-z]/.test(c.p))?"stitch":"dirform";
  wiz.autoFiled++;
 });
 finishImport();
};
function nextTriage(){
 if(!wiz.queue.length){finishImport();return;}
 step("triage");
 const c=wiz.queue[0];
 const idx=wiz.classified.indexOf(c);
 const before=wiz.classified[idx-1];
 $("triagecount").textContent=wiz.queue.length+" paragraph"+
  (wiz.queue.length>1?"s":"")+" need"+(wiz.queue.length>1?"":"s")+
  " a decision. Everything else parsed itself.";
 const opts=wiz.cast.map(x=>'<option>'+esc(x.name)+'</option>').join("");
 $("triagecard").innerHTML='<div class="card">'+
  (before?'<div class="neighbor">… '+esc(before.p.slice(-90))+'</div>':"")+
  '<div class="ptext">'+esc(c.p.slice(0,400))+'</div>'+
  '<div><select id="twho">'+opts+'</select>'+
  '<button class="primary" id="tspk">This is a line by ↑</button></div>'+
  '<div><button id="tstitch">Part of the previous line</button>'+
  '<button id="tdir">Stage direction</button>'+
  '<button id="tdrop">Junk, drop it</button></div>'+
  '<div style="margin-top:.5rem"><button id="talldir" class="muted">Treat ALL remaining as directions</button></div></div>';
 const done=k=>{c.k=k;wiz.queue.shift();nextTriage();};
 $("tspk").onclick=()=>{c.p=$("twho").value+". "+c.p;c.k="sp";wiz.queue.shift();nextTriage();};
 $("tstitch").onclick=()=>done("stitch");
 $("tdir").onclick=()=>done("dirform");
 $("tdrop").onclick=()=>done("drop");
 $("talldir").onclick=()=>{wiz.queue.forEach(q=>q.k="dirform");wiz.queue=[];nextTriage();};
}
function finishImport(){
 const speeches=buildSpeeches(wiz.classified,wiz.cast.map(c=>c.name));
 const play={id:wiz.id,title:wiz.title,author:wiz.author,created:Date.now(),
  cast:wiz.cast,speeches,loose:looseWords(speeches)};
 store.save(play);
 const n=speeches.filter(s=>s.speaker&&s.say).length;
 const skipped=wiz.classified.filter(c=>c.k==="front").length;
 $("donesummary").textContent=wiz.title+": "+wiz.cast.length+
  " characters, "+n+" spoken lines, "+
  [...new Set(speeches.map(s=>s.act))].filter(a=>a!=="Front matter").length+" act(s)."+
  (skipped?" "+skipped+" front/back-matter paragraphs skipped.":"")+
  (wiz.autoFiled?" "+wiz.autoFiled+" odd paragraph"+
   (wiz.autoFiled>1?"s":"")+" auto-filed.":"");
 step("done");
 $("donebtn").onclick=()=>openPlay(play.id);
}

// ---------- play view + the lifted runtimes ----------
let current=null;
function openPlay(id){
 current=store.get(id);if(!current){show("home");renderShelf();return;}
 // Plays imported before the loose-word feature self-heal here.
 if(!current.loose){current.loose=looseWords(current.speeches);
  store.save(current);}
 $("pvtitle").textContent="\u{1F3AD} "+current.title;
 $("pvauthor").textContent=current.author?"by "+current.author:"";
 const el=$("pvcast");el.innerHTML="";
 const rt=document.createElement("div");rt.className="rowlink";
 rt.innerHTML="<b>\u{1F3A7} Full Read Through</b><small>the whole play, read aloud</small>";
 rt.onclick=()=>openRead();
 el.appendChild(rt);
 current.cast.forEach(c=>{
  const n=current.speeches.filter(s=>s.speaker===c.name&&s.say).length;
  if(!n)return;
  const d=document.createElement("div");d.className="rowlink";
  d.innerHTML="<b>"+esc(c.emoji?c.emoji+" ":"")+esc(c.name)+"</b><small>"+n+" lines</small>";
  d.onclick=()=>openPractice(c.name,c.emoji||"");
  el.appendChild(d);
 });
 show("playview");
}
$("pvback").onclick=()=>{show("home");renderShelf();};
$("pvdelete").onclick=()=>{
 store.del(current.id);show("home");renderShelf();
};
function mount(html){
 $("stagewrap").style.display="block";
 $("stage").srcdoc=html;
}
window.appBack=()=>{ $("stagewrap").style.display="none";$("stage").srcdoc="";};
function openPractice(name,avatar){
 const data=dataFor(current,name);
 mount(PRACTICE_T
  .replace(/__NAME__/g,name)
  .replace(/__AVATAR__/g,avatar)
  .replace(/__PLAY__/g,esc(current.title))
  .replace(/__COUNT__/g,String(data.lines.length))
  .replace(/__BUILD__/g,"")
  .replace("__DATA__",JSON.stringify(data)));
}
function openRead(){
 mount(READ_T
  .replace(/__PLAY__/g,esc(current.title))
  .replace(/__BUILD__/g,"")
  .replace("__DATA__",JSON.stringify(readData(current))));
}

renderShelf();
</script></body></html>
"""


def main():
    practice = strip_product(TEMPLATE, "practice")
    read = strip_product(READ_TEMPLATE, "read")
    # "</" must not appear raw inside the host <script>: a literal
    # "</script>" inside the embedded template strings would terminate
    # the app's own script tag mid-string.
    js_str = lambda s: json.dumps(s).replace("</", "<\\/")
    common = [w.strip() for w in open("english10k.txt", encoding="utf-8")
              if w.strip()]
    out = (APP
           .replace("__PRACTICE_T__", js_str(practice))
           .replace("__READ_T__", js_str(read))
           .replace("__COMMON__", json.dumps(common)))
    os.makedirs("app", exist_ok=True)
    with open(os.path.join("app", "index.html"), "w",
              encoding="utf-8") as fh:
        fh.write(out)
    print("app/index.html: %d KB (practice runtime lifted verbatim "
          "from the cast site)" % (len(out) // 1024))


if __name__ == "__main__":
    main()

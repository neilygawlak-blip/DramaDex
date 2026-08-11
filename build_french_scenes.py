"""Build the French-scene labeler: a director-only module.

One self-contained HTML file showing the whole script in a readable book
style (or one printed page at a time), with a gutter down the left where
French scenes are assigned. Entrances and exits are detected and offered
as suggested boundaries; the director keeps, kills, or adds boundaries
with one click.

Everything computational happens silently behind clicks (spec per Chris,
Aug 2026: "all that coding done in the background, minimal buttons"):
  - Rehearsal groups appear as cards, not a text report.
  - The plan is built by clicking a group ("Make this a call") or typing
    nothing more technical than scene numbers. Actors are chips: gold is
    called, dim is released; click to flip.
  - Coverage problems (scenes in no call, needed-but-released actors)
    appear as plain sentences on the cards, automatically.
  - The trivial-part rule is a preset formula (a character with 4 or
    fewer lines in a scene is optional there), not a knob.
  - Two output buttons: Save (a PDF) and Email. State persists in the
    browser on every click; there is nothing to export or import.

This never ships to the cast list, only behind the same gate.

Usage:
    python build_french_scenes.py private/see_how_they_run_fixed.txt \
        private/cast_see_how_they_run.txt private/french_scenes.html
"""

import json
import re
import sys

from build_character_pages import parse

ENTER_EXIT = re.compile(
    r"\b(enters?|enter(ed)?|exits?|exit|re-enters?|goes off|dashes (in|off|out)|"
    r"rushes (in|off|out)|runs off|appears|comes in|she is gone|they exit|"
    r"exeunt|leaps over .* and (exits|runs off)|stamps off)\b", re.I)

# A character with this many lines or fewer in a scene is optional there:
# they can skip that call. Preset, not a knob (keep the surface simple).
TRIVIAL_LINES = 4

TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>French scenes</title>
<style>
 body{font-family:"Segoe UI Variable Display","Segoe UI",system-ui,sans-serif;
      margin:0;background:#0a0f1e;color:#e8e6df}
 #top{position:sticky;top:0;background:#0d1526;border-bottom:1px solid #2b3a5e;
      padding:.6rem 1rem;display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;z-index:5}
 h1{font-size:1rem;color:#ffd75e;margin:0 1rem 0 0}
 button,select,input[type=text]{font-size:.9rem;padding:.35rem .7rem;border:1px solid #2b3a5e;
      border-radius:8px;background:#111a30;color:#e8e6df;cursor:pointer}
 input[type=text]{cursor:text}
 button.primary{color:#ffd75e;border-color:#ffd75e}
 button:hover{border-color:#8d97b8}
 #wrap{display:flex;max-width:1200px;margin:0 auto}
 #script{flex:3;padding:1rem}
 #panel{flex:1;min-width:300px;padding:1rem;border-left:1px solid #2b3a5e;
      position:sticky;top:3.2rem;align-self:flex-start;max-height:90vh;overflow:auto}
 .row{display:flex;gap:.8rem;padding:.22rem 0;border-bottom:1px solid #131d38}
 .gut{width:5.2rem;flex:none;text-align:right}
 .gut button{font-size:.72rem;padding:.1rem .45rem;border-radius:999px;color:#55618a}
 .gut button.on{color:#0a0f1e;background:#ffd75e;border-color:#ffd75e;font-weight:700}
 .gut button.sug{border-style:dashed;color:#8d97b8}
 .meta{width:3.4rem;flex:none;color:#3f4a6e;font-size:.72rem;padding-top:.2rem}
 .txt{flex:1;font-family:Georgia,serif;font-size:.95rem;line-height:1.45}
 .txt .nm{font-variant:small-caps;font-weight:700;color:#c9d2ea}
 .dir{color:#7d87a3;font-style:italic}
 .scenehead{background:#131d38;color:#ffd75e;font-weight:700;padding:.3rem .8rem;
      border-radius:8px;margin:.6rem 0 .2rem}
 .hint{color:#55618a;font-size:.78rem}
 .card{background:#111a30;border:1px solid #2b3a5e;border-radius:10px;
      padding:.6rem .8rem;margin:.5rem 0;font-size:.85rem}
 .card b{color:#ffd75e}
 .card .who{color:#c9d2ea}
 .card button{font-size:.75rem;padding:.15rem .55rem;margin-top:.35rem}
 .chip{display:inline-block;font-size:.75rem;padding:.1rem .55rem;margin:.12rem .15rem;
      border:1px solid #3a4a75;border-radius:999px;cursor:pointer;user-select:none}
 .chip.on{background:#ffd75e;color:#0a0f1e;border-color:#ffd75e;font-weight:600}
 .chip.off{color:#55618a;text-decoration:line-through}
 .warn{color:#e0b34a;font-size:.78rem;margin-top:.3rem}
 .callx{float:right;border:none;background:none;color:#55618a;cursor:pointer;font-size:.9rem}
 h2{font-size:.95rem;color:#ffd75e;margin:1.1rem 0 .3rem}
 #footer{display:flex;gap:.6rem;margin-top:1rem;position:sticky;bottom:0;
      background:#0a0f1e;padding:.6rem 0}
 #footer button{flex:1;font-size:1rem;padding:.55rem}
</style></head><body>
<div id="top">
 <h1>&#127821; French scenes</h1>
 <select id="view"><option value="book">Whole script</option><option value="page">One page at a time</option></select>
 <span id="pagenav" style="display:none"><button id="pgprev">&#9664;</button>
  <span id="pgno"></span> <button id="pgnext">&#9654;</button></span>
 <button id="reset">Reset to suggestions</button>
 <span class="hint">Gold = a scene starts here. The script pre-marks every
 entrance and exit; click any gold pill to remove it, any blank dot to add
 your own. Saves by itself.</span>
</div>
<div id="wrap">
 <div id="script"></div>
 <div id="panel">
  <div id="count" style="font-size:1.4rem;font-weight:700;color:#ffd75e"></div>
  <div class="hint">French scenes marked</div>

  <h2>The plan</h2>
  <div class="hint">One click groups the scenes by who they need and
  turns them into calls. Click an actor to release them from a call;
  anyone with """ + str(TRIVIAL_LINES) + """ lines or fewer in a scene is optional anyway.</div>
  <button class="primary" id="build" style="margin-top:.4rem">Build the plan for me</button>
  <div style="display:flex;gap:.4rem;margin:.4rem 0">
   <input type="text" id="callin" placeholder="or type one: Tuesday: 3-7, 12" style="flex:1">
   <button id="addcall">Add</button>
  </div>
  <div id="plancards"></div>
  <div id="coverage"></div>

  <div id="footer">
   <button class="primary" id="saveemail">&#128190; Save &amp; Email</button>
  </div>
 </div>
</div>
<script>
const P=__DATA__;
const KEY="dd_french_scenes";
const TRIVIAL=""" + str(TRIVIAL_LINES) + """;
let bounds=new Set(JSON.parse(localStorage.getItem(KEY)||"null")||P.suggested);
let calls=JSON.parse(localStorage.getItem(KEY+"_calls")||"[]");
const scriptEl=document.getElementById("script");
const view=document.getElementById("view");
let page=P.minpage;

function save(){localStorage.setItem(KEY,JSON.stringify([...bounds]));
 localStorage.setItem(KEY+"_calls",JSON.stringify(calls));}
function sceneNumbers(){
 const map={};let n=0;
 P.paras.forEach((p,i)=>{if(bounds.has(i))n++;map[i]=n;});
 return map;
}
const esc=s=>s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));

function render(){
 const nums=sceneNumbers();
 scriptEl.innerHTML="";
 const frag=document.createDocumentFragment();
 P.paras.forEach((p,i)=>{
  if(view.value==="page"&&p.page!==page)return;
  if(bounds.has(i)){
   const h=document.createElement("div");h.className="scenehead";
   h.textContent=p.act+" \\u00b7 French scene "+nums[i];frag.appendChild(h);
  }
  const row=document.createElement("div");row.className="row";
  const g=document.createElement("div");g.className="gut";
  const b=document.createElement("button");
  if(bounds.has(i)){b.textContent="scene "+nums[i];b.className="on";}
  else if(P.suggested.includes(i)){b.textContent="scene?";b.className="sug";}
  else{b.textContent="\\u00b7";}
  b.onclick=()=>{bounds.has(i)?bounds.delete(i):bounds.add(i);save();refresh();};
  g.appendChild(b);
  const m=document.createElement("div");m.className="meta";
  m.textContent="p."+p.page;
  const t=document.createElement("div");t.className="txt";
  if(p.speaker){t.innerHTML='<span class="nm">'+p.speaker+'.</span> '+esc(p.text.slice(p.speaker.length+1))}
  else{t.innerHTML='<span class="dir">'+esc(p.text)+'</span>'}
  row.append(g,m,t);frag.appendChild(row);
 });
 scriptEl.appendChild(frag);
 document.getElementById("pgno").textContent="p. "+page;
 document.getElementById("count").textContent=[...bounds].length;
}

// ---- the quiet math: scenes, casts, groups ----
function sceneData(){
 const nums=sceneNumbers(),scenes={};
 P.paras.forEach((p,i)=>{
  const s=nums[i];if(!s)return;
  scenes[s]=scenes[s]||{n:s,act:p.act,cast:{},firstPage:p.page,lines:0};
  if(p.speaker){scenes[s].cast[p.speaker]=(scenes[s].cast[p.speaker]||0)+1;scenes[s].lines++;}
 });
 Object.values(scenes).forEach(s=>{
  s.needed=Object.keys(s.cast).filter(c=>s.cast[c]>TRIVIAL).sort();
  s.optional=Object.keys(s.cast).filter(c=>s.cast[c]<=TRIVIAL).sort();
 });
 return scenes;
}
function makeGroups(){
 const scenes=Object.values(sceneData());
 const groups={};
 scenes.forEach(s=>{
  const sig=s.needed.join(", ")||"small bits";
  groups[sig]=groups[sig]||{sig,ids:[],lines:0,opt:new Set()};
  groups[sig].ids.push(s.n);groups[sig].lines+=s.lines;
  s.optional.forEach(c=>groups[sig].opt.add(c));
 });
 return Object.values(groups).sort((a,b)=>b.lines-a.lines);
}
// One button: group every scene not yet in a call by who it needs, and
// make those groups calls. Works from empty (full plan) or partial
// (fills the gaps).
document.getElementById("build").onclick=()=>{
 const scenes=sceneData();
 const covered=new Set();calls.forEach(c=>c.ids.forEach(id=>covered.add(id)));
 const groups={};
 Object.values(scenes).forEach(s=>{
  if(covered.has(s.n))return;
  const sig=s.needed.join(", ")||"small bits";
  groups[sig]=groups[sig]||[];groups[sig].push(s.n);
 });
 Object.values(groups).sort((a,b)=>b.length-a.length).forEach(ids=>
  calls.push({label:"Call "+(calls.length+1),ids,off:[]}));
 save();renderPlan();
};

// ---- the plan: cards and chips, no syntax ----
function callRoster(call,scenes){
 const inScenes=new Set();
 call.ids.forEach(id=>{const s=scenes[id];if(s)Object.keys(s.cast).forEach(c=>inScenes.add(c));});
 return [...inScenes].sort();
}
function renderPlan(){
 const scenes=sceneData();
 const el=document.getElementById("plancards");el.innerHTML="";
 calls.forEach((call,k)=>{
  const d=document.createElement("div");d.className="card";
  const x=document.createElement("button");x.className="callx";x.textContent="\\u2715";
  x.title="remove this call";
  x.onclick=()=>{calls.splice(k,1);save();renderPlan();};
  d.appendChild(x);
  const title=document.createElement("b");title.textContent=call.label;
  title.style.cursor="pointer";title.title="click to rename";
  title.onclick=()=>{const nl=prompt("Name this call (a day, a time, anything):",call.label);
   if(nl){call.label=nl;save();renderPlan();}};
  d.appendChild(title);
  const sc=document.createElement("div");sc.className="who";
  sc.textContent="scenes "+call.ids.join(", ");d.appendChild(sc);
  // actor chips: gold = called, struck = released. Click flips.
  const needed=new Set();
  call.ids.forEach(id=>{const s=scenes[id];if(s)s.needed.forEach(n=>needed.add(n));});
  callRoster(call,scenes).forEach(c=>{
   const ch=document.createElement("span");
   const off=call.off.includes(c);
   ch.className="chip "+(off?"off":"on");
   ch.textContent=c;
   ch.title=off?"released \\u2014 click to call":"called \\u2014 click to release";
   ch.onclick=()=>{call.off=off?call.off.filter(o=>o!==c):[...call.off,c];
    save();renderPlan();};
   d.appendChild(ch);
  });
  // plain-sentence warnings, computed silently
  const missing=[...needed].filter(n=>call.off.includes(n));
  if(missing.length){const w=document.createElement("div");w.className="warn";
   w.textContent="\\u26A0 "+missing.join(", ")+" carries real lines in these scenes but is released.";
   d.appendChild(w);}
  el.appendChild(d);
 });
 // coverage, always visible, always current
 const covered=new Set();calls.forEach(c=>c.ids.forEach(id=>covered.add(id)));
 const all=Object.keys(scenes).map(Number);
 const un=all.filter(id=>!covered.has(id));
 const cov=document.getElementById("coverage");
 if(!all.length||!calls.length){cov.innerHTML="";}
 else if(un.length){
  cov.innerHTML='<div class="warn">\\u26A0 Scenes in no call yet: '+un.join(", ")
   +' \\u2014 "Build the plan for me" adds them.</div>';
 }else{cov.innerHTML='<div class="hint">Every scene is in a call.</div>';}
}
document.getElementById("addcall").onclick=()=>{
 const raw=document.getElementById("callin").value.trim();if(!raw)return;
 const di=raw.search(/\\d/);
 const label=(di>0?raw.slice(0,di).replace(/[:,\\u2014-]+\\s*$/,"").trim():"")||("Call "+(calls.length+1));
 const ids=new Set();
 (di<0?"":raw.slice(di)).split(/[ ,]+/).forEach(tok=>{
  const r=tok.match(/^(\\d+)\\s*[-\\u2013]\\s*(\\d+)$/);
  if(r){for(let k=+r[1];k<=+r[2];k++)ids.add(k);}
  else if(/^\\d+$/.test(tok))ids.add(+tok);});
 if(!ids.size)return;
 calls.push({label,ids:[...ids].sort((a,b)=>a-b),off:[]});
 document.getElementById("callin").value="";
 save();renderPlan();
};

function refresh(){render();renderPlan();}

view.onchange=()=>{document.getElementById("pagenav").style.display=view.value==="page"?"":"none";render();};
document.getElementById("pgprev").onclick=()=>{page=Math.max(P.minpage,page-1);render();};
document.getElementById("pgnext").onclick=()=>{page=Math.min(P.maxpage,page+1);render();};
document.getElementById("reset").onclick=()=>{
 if(confirm("Reset? Scene boundaries go back to the script's suggestions and the plan is cleared."))
 {bounds=new Set(P.suggested);calls=[];save();refresh();}};

// ---- Save and Email: the one readable version of everything ----
function shareText(){
 const scenes=sceneData();
 const ordered=[...bounds].sort((a,b)=>a-b);
 let out="FRENCH SCENES \\u2014 See How They Run\\n";
 out+="-".repeat(38)+"\\n";
 ordered.forEach((i,k)=>{
  const p=P.paras[i],prev=P.paras[i-1];
  let after="the top";
  if(prev){const t=prev.text.replace(/\\s+/g," ").trim();
   after=(prev.speaker?prev.speaker+": ":"")+"..."+t.slice(-55);}
  const opens=(p.speaker?p.speaker+": ":"")+p.text.replace(/\\s+/g," ").slice(p.speaker?p.speaker.length+1:0,90).trim();
  out+="\\nSCENE "+(k+1)+" \\u2014 "+p.act+", p."+p.page+", "+(p.loc||"")+" the page\\n";
  out+="  starts after  "+after+"\\n";
  out+="  opens with    "+opens+"...\\n";
 });
 if(calls.length){
  out+="\\n\\nTHE PLAN\\n"+"-".repeat(38)+"\\n";
  calls.forEach(c=>{
   const roster=callRoster(c,scenes).filter(n=>!c.off.includes(n));
   out+="\\n"+c.label+" \\u2014 scenes "+c.ids.join(", ")+"\\n";
   out+="  call: "+(roster.join(", ")||"(nobody)")+"\\n";
  });
 }
 return out;
}
function dl(name,blob){const a=document.createElement("a");
 a.href=URL.createObjectURL(blob);a.download=name;a.click();}
function pdfSafe(s){return s.replace(/\\u2014/g,"--").replace(/\\u2026/g,"...")
 .replace(/\\u26A0/g,"!").replace(/\\u00b7/g,".").replace(/[^\\x20-\\x7E\\n]/g,"?");}
function pdf(text){
 const lines=pdfSafe(text).split("\\n");
 const perPage=52,chunks=[];
 for(let i=0;i<lines.length;i+=perPage)chunks.push(lines.slice(i,i+perPage));
 const e2=s=>s.replace(/\\\\/g,"\\\\\\\\").replace(/\\(/g,"\\\\(").replace(/\\)/g,"\\\\)");
 const objs=[];const add=s=>{objs.push(s);return objs.length;};
 const fontId=add("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>");
 const pageIds=[],contentIds=[];
 chunks.forEach(ch=>{
  let st="BT /F1 11 Tf 13 TL 50 742 Td\\n";
  ch.forEach(l=>{st+="("+e2(l)+") Tj T*\\n";});
  st+="ET";
  contentIds.push(add("<< /Length "+st.length+" >>\\nstream\\n"+st+"\\nendstream"));
 });
 const pagesId=objs.length+chunks.length+1;
 chunks.forEach((_,k)=>{
  pageIds.push(add("<< /Type /Page /Parent "+pagesId+" 0 R /MediaBox [0 0 612 792]"+
   " /Resources << /Font << /F1 "+fontId+" 0 R >> >> /Contents "+contentIds[k]+" 0 R >>"));
 });
 add("<< /Type /Pages /Kids ["+pageIds.map(i=>i+" 0 R").join(" ")+"] /Count "+pageIds.length+" >>");
 const catId=add("<< /Type /Catalog /Pages "+pagesId+" 0 R >>");
 let out="%PDF-1.4\\n";const offs=[0];
 objs.forEach((o,i)=>{offs.push(out.length);out+=(i+1)+" 0 obj\\n"+o+"\\nendobj\\n";});
 const xref=out.length;
 out+="xref\\n0 "+(objs.length+1)+"\\n0000000000 65535 f \\n";
 for(let i=1;i<=objs.length;i++)out+=String(offs[i]).padStart(10,"0")+" 00000 n \\n";
 out+="trailer\\n<< /Size "+(objs.length+1)+" /Root "+catId+" 0 R >>\\nstartxref\\n"+xref+"\\n%%EOF";
 return new Blob([out],{type:"application/pdf"});
}
function png(text,title){
 const lines=text.split("\\n");
 const cv=document.createElement("canvas");
 const lh=26,pad=40;cv.width=1050;cv.height=pad*2+lines.length*lh;
 const g=cv.getContext("2d");
 g.fillStyle="#0a0f1e";g.fillRect(0,0,cv.width,cv.height);
 lines.forEach((l,i)=>{
  g.font=(i===0?"bold 22px":"16px")+" Consolas,monospace";
  g.fillStyle=i===0?"#ffd75e":l.startsWith("SCENE")||l.startsWith("THE PLAN")?"#ffd75e":"#c9d2ea";
  g.fillText(l,pad,pad+i*lh+18);});
 return new Promise(res=>cv.toBlob(res,"image/png"));
}
// One button. Title it, it saves the PDF and PNG under that title, then
// opens the email with the same title as the subject. (Browsers cannot
// attach files to an email by themselves; the body says which two files
// to drag in.)
document.getElementById("saveemail").onclick=async()=>{
 const title=prompt("Title this (it becomes the file names and the email subject):",
  "French scenes \\u2014 See How They Run");
 if(!title)return;
 const safe=title.replace(/[^\\w \\u2014-]+/g,"").trim().replace(/\\s+/g,"_")||"french_scenes";
 const text=title+"\\n"+shareText().split("\\n").slice(1).join("\\n");
 dl(safe+".pdf",pdf(text));
 dl(safe+".png",await png(text,title));
 setTimeout(()=>{
  location.href="mailto:?subject="+encodeURIComponent(title)+
   "&body="+encodeURIComponent("The plan is in the two files that just saved \\u2014 attach "
    +safe+".pdf and "+safe+".png (check your Downloads folder).\\n\\n");
 },600);
};
render();renderPlan();
</script></body></html>
"""


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    rawfile, castfile, outfile = sys.argv[1:4]
    cast = [l.strip() for l in open(castfile, encoding="utf-8-sig") if l.strip()]
    speeches = parse(rawfile, cast)
    # Front matter (title page, copyright, story-of-the-play) has no place
    # in the director's view and is where every "p.?" came from.
    speeches = [s for s in speeches if s["act"] != "Front matter"]
    paras, suggested = [], []
    for s in speeches:
        i = len(paras)
        paras.append({"speaker": s["speaker"], "text": s["text"],
                      "act": s["act"], "page": s.get("page", 0)})
        # An entrance or exit anywhere in the paragraph suggests a boundary
        # at the NEXT paragraph, which is where the new grouping begins.
        if ENTER_EXIT.search(s["text"]):
            suggested.append(i + 1)
    # Any paragraph the page interpolation missed inherits its neighbour's
    # page: the director always gets a real page number.
    for i, p in enumerate(paras):
        if not p["page"]:
            p["page"] = next((q["page"] for q in paras[i:] if q["page"]),
                             next((q["page"] for q in reversed(paras[:i])
                                   if q["page"]), 1))
    # Where on its printed page each paragraph sits, in the words a person
    # flipping the book actually uses.
    by_page = {}
    for i, p in enumerate(paras):
        by_page.setdefault(p["page"], []).append(i)
    for page, idxs in by_page.items():
        for j, i in enumerate(idxs):
            f = j / max(1, len(idxs) - 1) if len(idxs) > 1 else 0
            paras[i]["loc"] = ("top of" if f < .2 else
                               "a quarter down" if f < .45 else
                               "halfway down" if f < .7 else
                               "three quarters down" if f < .9 else
                               "bottom of")
    suggested = sorted({j for j in suggested if j < len(paras)})
    pages = [p["page"] for p in paras]
    data = {"paras": paras, "suggested": suggested,
            "minpage": min(pages), "maxpage": max(pages)}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    with open(outfile, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("%d paragraphs, %d suggested boundaries -> %s"
          % (len(paras), len(suggested), outfile))


if __name__ == "__main__":
    main()

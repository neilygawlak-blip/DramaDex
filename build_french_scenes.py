"""Build the French-scene workbench: a local, director-only module.

One self-contained HTML file showing the whole script in a readable book
style (or one printed page at a time), with a gutter down the left where
French scenes are assigned. Entrances and exits in the stage directions
are detected and offered as suggested boundaries, since a French scene by
definition starts wherever somebody steps on or off; the director keeps,
kills, or adds boundaries with one click.

From the assigned scenes it derives rehearsal groups: which set of actors
each stretch actually needs, with a knob for ignoring trivial parts (a
character with two easy lines in an act does not need to attend that
call — the MAN can live in the Act III group). Assignments persist in the
browser and export to a JSON file worth committing to the private repo.

The Plan panel meets the director wherever he already is. He can type in
a plan he made himself (a call is a label plus scene numbers, with actors
derived automatically and adjustable by hand), and the checker bridges
the logical gaps: scenes nobody is rehearsing, actors a call needs but
does not name, actors named who have nothing to do in it. Fill gaps
generates calls only for whatever the plan leaves uncovered.

This never ships to the cast site: prep_deploy only copies handouts.

Usage:
    python build_french_scenes.py private/see_how_they_run_raw.txt \
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


TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>French scenes — director's workbench</title>
<style>
 body{font-family:"Segoe UI Variable Display","Segoe UI",system-ui,sans-serif;
      margin:0;background:#0a0f1e;color:#e8e6df}
 #top{position:sticky;top:0;background:#0d1526;border-bottom:1px solid #2b3a5e;
      padding:.6rem 1rem;display:flex;gap:.6rem;align-items:center;flex-wrap:wrap;z-index:5}
 h1{font-size:1rem;color:#ffd75e;margin:0 1rem 0 0}
 button,select,input[type=number]{font-size:.9rem;padding:.35rem .7rem;border:1px solid #2b3a5e;
      border-radius:8px;background:#111a30;color:#e8e6df;cursor:pointer}
 button.primary{color:#ffd75e;border-color:#ffd75e}
 #wrap{display:flex;max-width:1200px;margin:0 auto}
 #script{flex:3;padding:1rem}
 #panel{flex:1;min-width:260px;padding:1rem;border-left:1px solid #2b3a5e;
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
 #report{white-space:pre-wrap;font-size:.82rem;color:#c9d2ea;font-family:Consolas,monospace}
 .hint{color:#55618a;font-size:.78rem}
</style></head><body>
<div id="top">
 <h1>&#127821; French scenes</h1>
 <select id="view"><option value="book">Whole script</option><option value="page">One page at a time</option></select>
 <span id="pagenav" style="display:none"><button id="pgprev">&#9664;</button>
  <span id="pgno"></span> <button id="pgnext">&#9654;</button></span>
 <button id="accept">Accept all suggestions</button>
 <button id="clear">Clear all</button>
 <label class="hint">trivial part &le; <input id="minlines" type="number" value="4" min="0" style="width:3.2rem"> lines</label>
 <button class="primary" id="groups">Suggest groups</button>
 <button class="primary" id="ship">Ship PDF + PNG</button>
 <button class="primary" id="email">Email it</button>
 <button id="word">Word</button>
 <button id="export">JSON</button>
 <label class="hint">import <input id="importfile" type="file" accept=".json" style="width:11rem"></label>
</div>
<div id="wrap">
 <div id="script"></div>
 <div id="panel">
  <div class="hint">Click a dashed suggestion to confirm it, or the blank
  gutter of any paragraph to start a scene there. Confirmed boundaries are
  gold. Everything saves in this browser; Export for the repo.</div>
  <h2 style="font-size:.95rem;color:#ffd75e;margin:1rem 0 .3rem">The plan</h2>
  <div class="hint">One call per line:<br>
  <code>Tue &mdash; 3-7, 12 + IDA - CLIVE</code><br>
  label, scene numbers/ranges, then optional
  <code>+ NAME</code> to call someone extra and <code>- NAME</code> to
  release someone. Actors are otherwise derived from the scenes.</div>
  <textarea id="plan" rows="8" style="width:100%;background:#111a30;color:#e8e6df;
   border:1px solid #2b3a5e;border-radius:8px;font-family:Consolas,monospace;
   font-size:.82rem;margin:.3rem 0"></textarea>
  <button class="primary" id="check">Check plan</button>
  <button id="fill">Fill gaps</button>
  <div id="report"></div>
 </div>
</div>
<script>
const P=__DATA__;
const KEY="dd_french_scenes";
let bounds=new Set(JSON.parse(localStorage.getItem(KEY)||"null")||P.suggested);
const scriptEl=document.getElementById("script");
const view=document.getElementById("view");
let page=P.paras.find(p=>p.page)?.page||5;

function save(){localStorage.setItem(KEY,JSON.stringify([...bounds]));}
function sceneNumbers(){
 const map={};let n=0;
 P.paras.forEach((p,i)=>{if(bounds.has(i))n++;map[i]=n;});
 return map;
}
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
  b.onclick=()=>{bounds.has(i)?bounds.delete(i):bounds.add(i);save();render();};
  g.appendChild(b);
  const m=document.createElement("div");m.className="meta";
  m.textContent="p."+(p.page||"?");
  const t=document.createElement("div");t.className="txt";
  if(p.speaker){t.innerHTML='<span class="nm">'+p.speaker+'.</span> '+esc(p.text.slice(p.speaker.length+1))}
  else{t.innerHTML='<span class="dir">'+esc(p.text)+'</span>'}
  row.append(g,m,t);frag.appendChild(row);
 });
 scriptEl.appendChild(frag);
 document.getElementById("pgno").textContent="p. "+page;
}
const esc=s=>s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));
view.onchange=()=>{document.getElementById("pagenav").style.display=view.value==="page"?"":"none";render();};
document.getElementById("pgprev").onclick=()=>{page=Math.max(P.minpage,page-1);render();};
document.getElementById("pgnext").onclick=()=>{page=Math.min(P.maxpage,page+1);render();};
document.getElementById("accept").onclick=()=>{P.suggested.forEach(i=>bounds.add(i));save();render();};
document.getElementById("clear").onclick=()=>{if(confirm("Clear every boundary?")){bounds.clear();save();render();}};

// ---- rehearsal groups from the assigned scenes ----
function analyse(){
 const min=+document.getElementById("minlines").value||0;
 const nums=sceneNumbers();
 const scenes={};
 P.paras.forEach((p,i)=>{
  const s=nums[i];if(!s)return;
  scenes[s]=scenes[s]||{n:s,act:p.act,cast:{},firstPage:p.page,lines:0};
  if(p.speaker){scenes[s].cast[p.speaker]=(scenes[s].cast[p.speaker]||0)+1;scenes[s].lines++;}
 });
 const list=Object.values(scenes);
 list.forEach(s=>{
  s.needed=Object.keys(s.cast).filter(c=>s.cast[c]>min).sort();
  s.optional=Object.keys(s.cast).filter(c=>s.cast[c]<=min).sort();
 });
 // group scenes that need the same people
 const groups={};
 list.forEach(s=>{
  const sig=s.needed.join(" + ")||"(nobody above threshold)";
  groups[sig]=groups[sig]||{sig,scenes:[],lines:0,opt:{}};
  groups[sig].scenes.push(s);groups[sig].lines+=s.lines;
  s.optional.forEach(c=>groups[sig].opt[c]=(groups[sig].opt[c]||0)+s.cast[c]);
 });
 let out="REHEARSAL GROUPS  (trivial \\u2264 "+min+" lines per scene)\\n";
 out+="=".repeat(46)+"\\n";
 Object.values(groups).sort((a,b)=>b.lines-a.lines).forEach(g=>{
  out+="\\nCALL: "+g.sig+"\\n";
  out+="  scenes "+g.scenes.map(s=>s.n+" ("+s.act.replace("Act ","")+", p."+s.firstPage+")").join(", ")+"\\n";
  out+="  "+g.lines+" speeches total\\n";
  const opt=Object.entries(g.opt);
  if(opt.length)out+="  optional: "+opt.map(([c,n])=>c+" ("+n+" lines \\u2014 could fold elsewhere)").join(", ")+"\\n";
 });
 out+="\\nPER-ACTOR CALLS\\n"+"-".repeat(46)+"\\n";
 const actors={};
 list.forEach(s=>Object.keys(s.cast).forEach(c=>{
  actors[c]=actors[c]||{lines:0,scenes:[]};
  actors[c].lines+=s.cast[c];actors[c].scenes.push(s.n);}));
 Object.entries(actors).sort((a,b)=>b[1].lines-a[1].lines).forEach(([c,a])=>{
  out+=c.padEnd(14)+String(a.lines).padStart(4)+" lines in scenes "+a.scenes.join(",")+"\\n";});
 document.getElementById("report").textContent=out;
}
document.getElementById("groups").onclick=analyse;

// ---- the director's plan: check it, bridge its gaps ----
const planEl=document.getElementById("plan");
planEl.value=localStorage.getItem(KEY+"_plan")||"";
planEl.oninput=()=>localStorage.setItem(KEY+"_plan",planEl.value);
function sceneData(){
 const min=+document.getElementById("minlines").value||0;
 const nums=sceneNumbers(),scenes={};
 P.paras.forEach((p,i)=>{
  const s=nums[i];if(!s)return;
  scenes[s]=scenes[s]||{n:s,act:p.act,cast:{},firstPage:p.page,lines:0};
  if(p.speaker){scenes[s].cast[p.speaker]=(scenes[s].cast[p.speaker]||0)+1;scenes[s].lines++;}
 });
 Object.values(scenes).forEach(s=>{
  s.needed=Object.keys(s.cast).filter(c=>s.cast[c]>min).sort();});
 return scenes;
}
function parseCall(line){
 // label = text before the first digit; the rest holds scenes and +/- names
 const di=line.search(/\\d/);if(di<0)return null;
 const label=line.slice(0,di).replace(/[\\u2014:,-]+\\s*$/,"").trim()||"Call";
 let rest=line.slice(di);
 const extra=[],released=[];
 rest=rest.replace(/([+-])\\s*([A-Z][A-Z ]*[A-Z]|[A-Z]+)/g,(_,sign,name)=>{
  (sign==="+"?extra:released).push(name.trim());return "";});
 const ids=new Set();
 rest.split(/[ ,]+/).forEach(tok=>{
  const r=tok.match(/^(\\d+)\\s*[-\\u2013]\\s*(\\d+)$/);
  if(r){for(let k=+r[1];k<=+r[2];k++)ids.add(k);}
  else if(/^\\d+$/.test(tok))ids.add(+tok);});
 return {label,ids:[...ids].sort((a,b)=>a-b),extra,released};
}
function checkPlan(){
 const scenes=sceneData();
 const calls=planEl.value.split("\\n").map(l=>l.trim()).filter(Boolean).map(parseCall).filter(Boolean);
 let out="PLAN CHECK\\n"+"=".repeat(46)+"\\n";
 const covered=new Set();
 calls.forEach(c=>{
  const present=new Set(c.extra);
  const needed=new Set();
  c.ids.forEach(id=>{const s=scenes[id];if(!s)return;covered.add(id);
   s.needed.forEach(n=>needed.add(n));Object.keys(s.cast).forEach(n=>{if(!c.released.includes(n))present.add(n);});});
  c.released.forEach(n=>present.delete(n));
  out+="\\n"+c.label+"  (scenes "+c.ids.join(",")+")\\n";
  out+="  call: "+([...present].sort().join(", ")||"(nobody)")+"\\n";
  const missing=[...needed].filter(n=>!present.has(n));
  if(missing.length)out+="  \\u26A0 needed but released: "+missing.join(", ")+"\\n";
  const idle=[...present].filter(n=>!c.ids.some(id=>scenes[id]&&scenes[id].cast[n]));
  if(idle.length)out+="  \\u26A0 called but has no lines here: "+idle.join(", ")+"\\n";
  const light=[...present].filter(n=>!idle.includes(n)&&!needed.has(n));
  if(light.length)out+="  could release (trivial here): "+light.join(", ")+"\\n";
 });
 const all=Object.keys(scenes).map(Number);
 const un=all.filter(id=>!covered.has(id));
 out+="\\n"+"-".repeat(46)+"\\n";
 out+=un.length?("\\u26A0 scenes in no call: "+un.join(", ")+"\\n"):"every scene is covered.\\n";
 const bad=calls.flatMap(c=>c.ids.filter(id=>!scenes[id]));
 if(bad.length)out+="\\u26A0 plan names scenes that do not exist: "+[...new Set(bad)].join(", ")+"\\n";
 document.getElementById("report").textContent=out;
 return un;
}
document.getElementById("check").onclick=checkPlan;
document.getElementById("fill").onclick=()=>{
 const un=checkPlan();if(!un.length)return;
 const scenes=sceneData();
 const groups={};
 un.forEach(id=>{const sig=scenes[id].needed.join(" + ")||"(bits)";
  groups[sig]=groups[sig]||[];groups[sig].push(id);});
 let add="";
 Object.entries(groups).forEach(([sig,ids])=>{
  add+="\\nNew call ("+sig+") \\u2014 "+ids.join(", ");});
 planEl.value=(planEl.value.trim()+add).trim();
 planEl.oninput();checkPlan();
};
// ---- shipping: the finished, human-readable version ----
function shareText(){
 const ordered=[...bounds].sort((a,b)=>a-b);
 let out="FRENCH SCENES \\u2014 See How They Run\\n";
 out+="\\u2500".repeat(38)+"\\n";
 ordered.forEach((i,k)=>{
  const p=P.paras[i];
  const prev=P.paras[i-1];
  let after="the top";
  if(prev){
   const t=prev.text.replace(/\\s+/g," ").trim();
   after=(prev.speaker?prev.speaker+": ":"")+"\\u2026"+t.slice(-55);
  }
  const opens=(p.speaker?p.speaker+": ":"")+p.text.replace(/\\s+/g," ").slice(p.speaker?p.speaker.length+1:0,90).trim();
  out+="\\nSCENE "+(k+1)+" \\u2014 "+p.act+", p."+p.page+", "+(p.loc||"")+" the page\\n";
  out+="  starts after  "+after+"\\n";
  out+="  opens with    "+opens+"\\u2026\\n";
 });
 const plan=planEl.value.trim();
 if(plan)out+="\\n\\nTHE PLAN\\n"+"\\u2500".repeat(38)+"\\n"+plan+"\\n";
 return out;
}
function dl(name,blob){const a=document.createElement("a");
 a.href=URL.createObjectURL(blob);a.download=name;a.click();}
// ---- a real modern .docx: a stored zip of three small XML files ----
const CRCT=(()=>{const t=[];for(let n=0;n<256;n++){let c=n;
 for(let k=0;k<8;k++)c=c&1?0xEDB88320^(c>>>1):c>>>1;t[n]=c>>>0;}return t;})();
function crc32(b){let c=0xFFFFFFFF;
 for(let i=0;i<b.length;i++)c=CRCT[(c^b[i])&0xFF]^(c>>>8);
 return (c^0xFFFFFFFF)>>>0;}
function zip(files){
 const enc=new TextEncoder();const parts=[];const cdir=[];let off=0;
 const u16=v=>[v&255,v>>8&255];const u32=v=>[v&255,v>>8&255,v>>16&255,v>>>24&255];
 files.forEach(([name,txt])=>{
  const nb=enc.encode(name),db=enc.encode(txt),crc=crc32(db);
  const head=[80,75,3,4,...u16(20),...u16(0),...u16(0),...u16(0),...u16(0),
   ...u32(crc),...u32(db.length),...u32(db.length),...u16(nb.length),...u16(0)];
  parts.push(new Uint8Array(head),nb,db);
  cdir.push({nb,crc,len:db.length,off});
  off+=head.length+nb.length+db.length;});
 let cstart=off,clen=0;
 cdir.forEach(e=>{
  const h=[80,75,1,2,...u16(20),...u16(20),...u16(0),...u16(0),...u16(0),...u16(0),
   ...u32(e.crc),...u32(e.len),...u32(e.len),...u16(e.nb.length),...u16(0),...u16(0),
   ...u16(0),...u16(0),...u32(0),...u32(e.off)];
  parts.push(new Uint8Array(h),e.nb);clen+=h.length+e.nb.length;});
 parts.push(new Uint8Array([80,75,5,6,...u16(0),...u16(0),...u16(cdir.length),
  ...u16(cdir.length),...u32(clen),...u32(cstart),...u16(0)]));
 return new Blob(parts,{type:"application/vnd.openxmlformats-officedocument.wordprocessingml.document"});
}
function docx(text){
 const xesc=s=>s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
 const body=text.split("\\n").map(l=>
  '<w:p><w:r><w:rPr><w:rFonts w:ascii="Consolas" w:hAnsi="Consolas"/></w:rPr>'+
  '<w:t xml:space="preserve">'+xesc(l)+"</w:t></w:r></w:p>").join("");
 return zip([
  ["[Content_Types].xml",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
   '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'+
   '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'+
   '<Default Extension="xml" ContentType="application/xml"/>'+
   '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'],
  ["_rels/.rels",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
   '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'+
   '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'],
  ["word/document.xml",'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'+
   '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'+
   "<w:body>"+body+"</w:body></w:document>"],
 ]);
}
// ---- a real PDF, built by hand: the format every device opens ----
function pdfSafe(s){return s.replace(/\\u2500/g,"-").replace(/\\u2014/g,"--")
 .replace(/\\u2026/g,"...").replace(/\\u26A0/g,"!").replace(/\\u00b7/g,".")
 .replace(/[^\\x20-\\x7E\\n]/g,"?");}
function pdf(text){
 const lines=pdfSafe(text).split("\\n");
 const perPage=52,chunks=[];
 for(let i=0;i<lines.length;i+=perPage)chunks.push(lines.slice(i,i+perPage));
 const esc=s=>s.replace(/\\\\/g,"\\\\\\\\").replace(/\\(/g,"\\\\(").replace(/\\)/g,"\\\\)");
 const objs=[];const add=s=>{objs.push(s);return objs.length;};
 const fontId=add("<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>");
 const pageIds=[],contentIds=[];
 chunks.forEach(ch=>{
  let st="BT /F1 11 Tf 13 TL 50 742 Td\\n";
  ch.forEach(l=>{st+="("+esc(l)+") Tj T*\\n";});
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
document.getElementById("word").onclick=()=>dl("french_scenes.docx",docx(shareText()));
document.getElementById("ship").onclick=()=>{
 const text=shareText();
 dl("french_scenes.pdf",pdf(text));
 // The PNG: same content drawn in house colours, phone-shareable.
 const lines=text.split("\\n");
 const cv=document.createElement("canvas");
 const lh=26,pad=40;cv.width=1050;cv.height=pad*2+lines.length*lh;
 const g=cv.getContext("2d");
 g.fillStyle="#0a0f1e";g.fillRect(0,0,cv.width,cv.height);
 lines.forEach((l,i)=>{
  g.font=(i===0?"bold 22px":"16px")+" Consolas,monospace";
  g.fillStyle=i===0?"#ffd75e":l.startsWith("SCENE")||l.startsWith("THE PLAN")?"#ffd75e":"#c9d2ea";
  g.fillText(l,pad,pad+i*lh+18);});
 cv.toBlob(b=>dl("french_scenes.png",b),"image/png");
};
document.getElementById("email").onclick=()=>{
 let text=shareText();
 const MAX=1700;
 if(text.length>MAX)text=text.slice(0,MAX)+"\\n\\u2026(full version in the attached Word/PNG files \\u2014 use the Word + PNG button, then drag them in)";
 location.href="mailto:?subject="+encodeURIComponent("French scenes \\u2014 See How They Run")+
  "&body="+encodeURIComponent(text);
};
document.getElementById("importfile").onchange=e=>{
 const f=e.target.files[0];if(!f)return;
 f.text().then(t=>{const d=JSON.parse(t);
  if(d.boundaries){bounds=new Set(d.boundaries);save();}
  if(typeof d.plan==="string"){planEl.value=d.plan;planEl.oninput();}
  render();});
};
document.getElementById("export").onclick=()=>{
 const nums=sceneNumbers();
 const data={boundaries:[...bounds].sort((a,b)=>a-b),
  plan:planEl.value,
  scenes:P.paras.filter((p,i)=>bounds.has(i)).map((p,k)=>({scene:k+1,para:[...bounds].sort((a,b)=>a-b)[k],act:p.act,page:p.page}))};
 const blob=new Blob([JSON.stringify(data,null,1)],{type:"application/json"});
 const a=document.createElement("a");a.href=URL.createObjectURL(blob);
 a.download="french_scenes.json";a.click();
};
render();
</script></body></html>
"""


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    rawfile, castfile, outfile = sys.argv[1:4]
    cast = [l.strip() for l in open(castfile, encoding="utf-8") if l.strip()]
    speeches = parse(rawfile, cast)
    paras, suggested = [], []
    for s in speeches:
        i = len(paras)
        paras.append({"speaker": s["speaker"], "text": s["text"],
                      "act": s["act"], "page": s.get("page", 0)})
        # An entrance or exit anywhere in the paragraph suggests a boundary
        # at the NEXT paragraph, which is where the new grouping begins.
        if ENTER_EXIT.search(s["text"]):
            suggested.append(i + 1)
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
    pages = [p["page"] for p in paras if p["page"]]
    data = {"paras": paras, "suggested": suggested,
            "minpage": min(pages), "maxpage": max(pages)}
    html = TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False))
    with open(outfile, "w", encoding="utf-8") as fh:
        fh.write(html)
    print("%d paragraphs, %d suggested boundaries -> %s"
          % (len(paras), len(suggested), outfile))


if __name__ == "__main__":
    main()

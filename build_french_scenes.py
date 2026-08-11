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
 <button id="export">Export JSON</button>
</div>
<div id="wrap">
 <div id="script"></div>
 <div id="panel">
  <div class="hint">Click a dashed suggestion to confirm it, or the blank
  gutter of any paragraph to start a scene there. Confirmed boundaries are
  gold. Everything saves in this browser; Export for the repo.</div>
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
document.getElementById("export").onclick=()=>{
 const nums=sceneNumbers();
 const data={boundaries:[...bounds].sort((a,b)=>a-b),
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

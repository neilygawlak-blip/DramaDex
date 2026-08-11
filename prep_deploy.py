"""Assemble the folder that gets uploaded to Cloudflare Pages.

Collects the freshly built character pages, adds a landing page for the
cast, the Voice Booth (records samples for Neil's Lab), the upload
worker, any rendered real-voice clips, and the headers that keep a
licensed script out of search engines. The whole folder is what gets
deployed. Nothing here is the deployment itself: the account, the upload
and the email gate stay in your hands, per DEPLOY.md alongside.

Usage:
    python prep_deploy.py private/handouts private/deploy
"""

import json
import os
import shutil
import sys

from build_character_pages import AVATARS

INDEX = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Pineapple Playhouse — line practice</title>
<style>
 body{font-family:Georgia,serif;max-width:640px;margin:3rem auto;padding:0 1rem;
      background:#0a0f1e;color:#e8e6df;line-height:1.6}
 h1{color:#ffd75e;font-size:1.4rem;text-shadow:0 0 10px rgba(255,183,71,.5)}
 a{display:block;padding:.7rem 1rem;margin:.4rem 0;border:1px solid #2b3a5e;
   border-radius:10px;color:#e8e6df;text-decoration:none;background:#111a30}
 a:hover{border-color:#ffd75e;box-shadow:0 0 10px rgba(255,183,71,.35)}
 .muted{color:#7d87a3;font-size:.9rem}
 .intro{margin:1rem 0 1.6rem}
 .intro p{color:#9aa4c0;font-size:.92rem;margin:.55rem 0;line-height:1.55}
 .intro b{color:#c9d2ea;font-weight:600}
 #cols{display:flex;gap:2rem;align-items:flex-start}
 #cast{flex:1}
 aside{flex:none;width:240px;position:sticky;top:2rem}
 a.door-btn{display:flex;align-items:center;gap:.8rem;text-decoration:none;
   padding:.8rem 1rem .8rem .8rem;border-radius:14px;cursor:pointer;
   background:linear-gradient(160deg,#111a30,#0d1526);border:1px solid #2b3a5e;
   box-shadow:0 8px 20px rgba(0,0,0,.55),0 0 10px rgba(255,183,71,.08);
   transition:transform .18s ease,box-shadow .18s ease}
 a.door-btn:hover{transform:translateY(-3px);border-color:#3a4a75;
   box-shadow:0 14px 28px rgba(0,0,0,.65),0 0 22px rgba(255,183,71,.35)}
 .doorway{width:44px;height:66px;flex:none;position:relative;perspective:180px;
   border-radius:5px 5px 0 0;background:linear-gradient(180deg,#ffe9a8,#ffb347);
   box-shadow:0 0 12px rgba(255,183,71,.45)}
 .doorway .frame{position:absolute;inset:-3px -4px 0;border:2px solid #ffd75e;
   border-bottom:none;border-radius:7px 7px 0 0;
   filter:drop-shadow(0 0 4px rgba(255,215,94,.7))}
 .doorway .panel{position:absolute;inset:0;transform-origin:left center;
   transform:rotateY(-30deg);transition:transform .28s ease;
   background:linear-gradient(100deg,#182446,#101a36 60%,#0c1428);
   border-radius:3px 3px 0 0;border:1px solid #3a4a75;
   box-shadow:5px 0 9px rgba(0,0,0,.5)}
 .doorway .panel::after{content:"";position:absolute;right:5px;top:46%;
   width:4px;height:4px;border-radius:50%;background:#ffd75e;
   box-shadow:0 0 5px #ffb347}
 a.door-btn:hover .panel{transform:rotateY(-56deg)}
 .dlabel b{display:block;font-size:.92rem;color:#ffd75e;
   text-shadow:0 0 8px rgba(255,183,71,.45)}
 .dlabel span{display:block;font-size:.86rem;font-weight:600;color:#dfe6f7}
 .dlabel small{display:block;margin-top:.2rem;color:#55618a;font-size:.66rem;
   text-transform:uppercase;letter-spacing:.09em}
 .micbox{width:44px;height:66px;flex:none;display:flex;align-items:center;
   justify-content:center;border-radius:10px;
   background:linear-gradient(180deg,#182446,#0c1428);border:1px solid #3a4a75;
   box-shadow:0 8px 18px rgba(0,0,0,.6),0 0 12px rgba(255,183,71,.22)}
 .micbox svg{width:24px;height:38px;
   filter:drop-shadow(0 3px 5px rgba(0,0,0,.75)) drop-shadow(0 0 6px rgba(255,183,71,.5))}
 @media (max-width:720px){#cols{flex-direction:column}aside{width:100%;position:static;margin-top:1.2rem}}
</style></head><body>
<h1>&#127821; See How They Run — pick your character</h1>
<div class="intro">
<p style="color:#ffd75e">I built this for repetition and line-learning.
Always ask your cast mates to run lines first if you can. It's always
funner with friends.</p>
<p>Pick a scene, press the pineapple. Speak your line when the cue
finishes; it moves on when you land your last word.</p>
<p>Call for <b>one word</b>, or <b>full line</b>, just like calling for
line in rehearsal. Arrow keys skip around.</p>
<p>Practice with <b>just Cue Lines</b>, or <b>Full scene</b> plays
everyone else and waits for you; or <b>Listen through</b> the whole
thing in your car.</p>
</div>
<div id="cols">
<div id="cast">
__LINKS__
</div>
<aside>
<a class="door-btn" href="french_scenes.html">
 <span class="doorway"><span class="panel"></span><span class="frame"></span></span>
 <span class="dlabel"><b>French Scene Labeler</b><span>Assign Groups</span>
 <small>director's door &#8250;</small></span>
</a>
<a class="door-btn" href="voice_booth.html" style="margin-top:.8rem">
 <span class="micbox"><svg viewBox="0 0 24 34" fill="none">
  <rect x="8" y="2" width="8" height="14" rx="4" fill="#ffd75e"/>
  <path d="M4.5 13a7.5 7.5 0 0 0 15 0" stroke="#ffd75e" stroke-width="2" stroke-linecap="round"/>
  <line x1="12" y1="21" x2="12" y2="27" stroke="#ffd75e" stroke-width="2" stroke-linecap="round"/>
  <line x1="7.5" y1="28.5" x2="16.5" y2="28.5" stroke="#ffd75e" stroke-width="2" stroke-linecap="round"/>
 </svg></span>
 <span class="dlabel"><b>Voice Booth</b><span>Record your voice so
 others can use it</span>
 <small>neil's lab &#8250;</small></span>
</a>
</aside>
</div>
</body></html>
"""

BOOTH = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Voice Booth — Neil's Lab</title>
<style>
 body{font-family:"Segoe UI Variable Display","Segoe UI",system-ui,"Helvetica Neue",Arial,sans-serif;
      font-weight:500;letter-spacing:.012em;max-width:640px;margin:2rem auto;
      padding:0 1rem 5rem;background:#0a0f1e;color:#e8e6df;line-height:1.55}
 h1{font-size:1.45rem;font-weight:800;letter-spacing:.03em;margin-bottom:.2rem;color:#ffd75e}
 .muted{color:#7d87a3;font-size:.9rem;font-weight:400}
 select,button{font-size:1rem;padding:.45rem .8rem;margin:.2rem .3rem .2rem 0;
      border:1px solid #2b3a5e;border-radius:8px;background:#111a30;color:#e8e6df;cursor:pointer}
 button:disabled{opacity:.4;cursor:default}
 button.primary{background:#0d1526;color:#ffd75e;border:1px solid #ffd75e;
      text-shadow:0 0 6px #ffb347,0 0 14px #ff9d1c;
      box-shadow:0 0 8px rgba(255,183,71,.45),inset 0 0 8px rgba(255,183,71,.15)}
 .card{margin:1.1rem 0;padding:1rem 1.1rem;border:1px solid #2b3a5e;border-radius:14px;
      background:linear-gradient(160deg,#111a30,#0d1526);
      box-shadow:0 8px 20px rgba(0,0,0,.5)}
 .card h2{font-size:.95rem;color:#ffd75e;margin:0 0 .5rem;letter-spacing:.03em}
 .card .prompt{font-size:1.05rem;color:#f2f0e9;margin:.4rem 0 .8rem}
 .card .prompt i{color:#9aa4c0}
 .recbtn{border-radius:999px}
 .recbtn.on{border-color:#ff6b6b;color:#ff9d9d;box-shadow:0 0 10px rgba(255,80,80,.5)}
 .state{font-size:.85rem;color:#7d87a3;min-height:1.2rem;margin-top:.3rem}
 .state.good{color:#7fe0a7}
 .state.warn{color:#ffb347}
 #meter{height:6px;border-radius:3px;background:#111a30;border:1px solid #2b3a5e;
      overflow:hidden;margin:.5rem 0 0;display:none}
 #meter div{height:100%;width:0;background:linear-gradient(90deg,#7fe0a7,#ffd75e,#ff6b6b)}
 #sendwrap{margin-top:1.6rem;text-align:center}
 #sendmsg{margin-top:.6rem;font-size:.9rem;color:#9aa4c0;min-height:1.3rem}
 .consent{margin-top:2rem;font-size:.78rem;color:#55618a;line-height:1.5}
 #backbtn{position:fixed;bottom:1.2rem;left:1.2rem;font-size:.75rem;
      color:#7d87a3;background:#0d1526;border:1px solid #2b3a5e;
      border-radius:999px;padding:.35rem .8rem;text-decoration:none;
      box-shadow:0 2px 8px rgba(0,0,0,.5)}
 #backbtn:hover{border-color:#ffd75e;color:#e8e6df}
</style></head><body>
<h1>&#127908; Voice Booth <span class="muted">— Neil's Lab</span></h1>
<div class="muted">Record your voice so others can use it. Three short
takes, about two minutes all told. Use your <b>regular speaking
voice</b> on the first two — the conversion copies your natural voice
best, even if it flattens the theatrics. The third take is where the
character comes out. None of it has to be perfect — this is a farce,
funny will be funny.</div>
<div style="margin:1.2rem 0 .2rem">Who are you?
 <select id="who"><option value="">— pick your character —</option></select>
</div>
<div id="cards"></div>
<div id="meter"><div></div></div>
<div id="sendwrap">
 <button class="primary" id="sendbtn" disabled>&#127821; Send to Neil's Lab</button>
 <div id="sendmsg"></div>
</div>
<div class="consent">Your takes go only to Neil's Lab. They're used to
build a practice voice that reads your lines inside this cast's pages —
nothing else, nowhere else — and it's deleted if you ask.</div>
<a id="backbtn" href="index.html">&#8592; Back to Cast List</a>
<script>
const CAST=__CAST__;
// The cloner only keeps ~12 seconds of reference, so card 1 is sized to
// fit that at an easy pace, and every card stops the recording itself at
// its cap: nobody should feel a clock and rush.
const CARDS=[
 {title:"1 · The paragraph (your everyday voice)",min:6,max:16,free:false,
  text:"Right, here goes: my ordinary speaking voice. The old church "+
   "clock struck nine, thick fog rolled over the green, and somebody's "+
   "bicycle bell jangled twice."},
 {title:"2 · A question, then an order (mean both)",min:3,max:10,free:false,
  text:"Who on earth put a penguin in the pantry? Well, don't just "+
   "stand there -- go and fetch it out!"},
 {title:"3 · A line of your own",min:2,max:15,free:true,
  text:"One line of your character, from memory -- your favorite "+
   "delivery, played the way you'd play it on stage."},
];
const whoSel=document.getElementById("who");
CAST.forEach(c=>{const o=document.createElement("option");o.value=c;o.textContent=c;whoSel.appendChild(o);});

const takes=CARDS.map(()=>null);   // {blob,type,dur,peak,clip}
let stream=null,ac=null,an=null,mr=null,chunks=[],recIdx=-1,t0=0,peak=0,clipN=0,frameN=0,raf=0,maxT=0;
const MT=["audio/webm;codecs=opus","audio/webm","audio/mp4"].find(t=>window.MediaRecorder&&MediaRecorder.isTypeSupported(t))||"";
const meter=document.getElementById("meter"),bar=meter.firstElementChild;

const cardsEl=document.getElementById("cards");
CARDS.forEach((c,i)=>{
 const d=document.createElement("div");d.className="card";
 d.innerHTML='<h2>'+c.title+'</h2><div class="prompt">'+
  (c.free?'<i>'+c.text+'</i>':'&ldquo;'+c.text+'&rdquo;')+'</div>'+
  '<button class="recbtn" data-i="'+i+'">&#9210; Record</button>'+
  '<button class="playbtn" data-i="'+i+'" disabled>&#9654; Play</button>'+
  '<div class="state" id="state'+i+'"></div>';
 cardsEl.appendChild(d);
});
const state=(i,msg,cls)=>{const s=document.getElementById("state"+i);
 s.textContent=msg;s.className="state"+(cls?" "+cls:"");};

// Recording wants the actor's actual sound: turn the phone's own
// processing off where the browser lets us.
async function mic(){
 if(stream)return stream;
 stream=await navigator.mediaDevices.getUserMedia({audio:{
  echoCancellation:false,noiseSuppression:false,autoGainControl:false}});
 ac=new (window.AudioContext||window.webkitAudioContext)();
 an=ac.createAnalyser();an.fftSize=2048;
 ac.createMediaStreamSource(stream).connect(an);
 return stream;
}
function watch(){
 const buf=new Float32Array(an.fftSize);
 const tick=()=>{
  an.getFloatTimeDomainData(buf);
  let p=0;for(let i=0;i<buf.length;i++){const v=Math.abs(buf[i]);if(v>p)p=v;}
  peak=Math.max(peak,p);frameN++;if(p>.97)clipN++;
  bar.style.width=Math.min(100,p*130)+"%";
  raf=requestAnimationFrame(tick);
 };tick();
}
async function startRec(i,btn){
 try{await mic();}catch(_){state(i,"Mic blocked -- allow the microphone for this site and try again.","warn");return;}
 if(ac.state==="suspended")ac.resume();
 chunks=[];recIdx=i;t0=Date.now();peak=0;clipN=0;frameN=0;
 mr=new MediaRecorder(stream,MT?{mimeType:MT}:undefined);
 mr.ondataavailable=e=>{if(e.data.size)chunks.push(e.data);};
 mr.onstop=()=>finishRec(i,btn);
 mr.start();
 btn.textContent="\\u23F9 Stop";btn.classList.add("on");
 meter.style.display="block";watch();
 state(i,"Recording\\u2026 easy pace; it stops itself at "+CARDS[i].max+"s.");
 maxT=setTimeout(()=>{if(mr&&mr.state==="recording"&&recIdx===i)mr.stop();},CARDS[i].max*1000);
}
function finishRec(i,btn){
 clearTimeout(maxT);
 cancelAnimationFrame(raf);meter.style.display="none";
 btn.textContent="\\u23FA Record";btn.classList.remove("on");
 const dur=(Date.now()-t0)/1000;
 const blob=new Blob(chunks,{type:mr.mimeType||MT||"audio/webm"});
 // The booth-side judgment: catch the takes no adjustment can save
 // before they're ever sent. Everything softer than these gets fixed
 // in Neil's Lab, not re-recorded.
 if(dur<CARDS[i].min){state(i,"Too short -- have another go, no rush.","warn");return;}
 if(peak<.06){state(i,"Barely heard you -- a bit closer to the phone, once more.","warn");return;}
 takes[i]={blob,type:blob.type,dur:Math.round(dur)};
 const rough=clipN/Math.max(1,frameN)>.05;
 state(i,"\\u2713 Got it ("+Math.round(dur)+"s)."+(rough?" A touch loud/crackly -- fine to keep, or redo a step further back.":""),
  rough?"warn":"good");
 document.querySelector('.playbtn[data-i="'+i+'"]').disabled=false;
 maybeArm();
}
document.addEventListener("click",e=>{
 const b=e.target.closest("button");if(!b)return;
 const i=+b.dataset.i;
 if(b.classList.contains("recbtn")){
  if(mr&&mr.state==="recording"){if(recIdx===i)mr.stop();return;}
  startRec(i,b);
 }
 if(b.classList.contains("playbtn")&&takes[i]){
  new Audio(URL.createObjectURL(takes[i].blob)).play();
 }
});
const sendbtn=document.getElementById("sendbtn"),sendmsg=document.getElementById("sendmsg");
function maybeArm(){sendbtn.disabled=!(whoSel.value&&takes.every(t=>t));}
whoSel.onchange=maybeArm;
sendbtn.onclick=async()=>{
 sendbtn.disabled=true;
 for(let i=0;i<takes.length;i++){
  sendmsg.textContent="Sending take "+(i+1)+" of "+takes.length+"\\u2026";
  try{
   const r=await fetch("/api/voice-upload?who="+encodeURIComponent(whoSel.value)+"&card="+(i+1),
    {method:"POST",headers:{"content-type":takes[i].type},body:takes[i].blob});
   if(!r.ok)throw new Error(r.status);
  }catch(_){
   sendmsg.textContent="Take "+(i+1)+" didn't go through -- check the connection and press Send again.";
   sendbtn.disabled=false;return;
  }
 }
 sendmsg.innerHTML="&#127821; Sent to Neil's Lab. You're done -- thank you!";
};
</script></body></html>
"""

# Keep the pages out of search indexes; this play is licensed material and
# the cast list gate is what makes hosting it defensible.
HEADERS = """/*
  X-Robots-Tag: noindex, nofollow
"""

ROBOTS = "User-agent: *\nDisallow: /\n"

DEPLOY_MD = """# Putting the practice pages online (once, ~10 minutes)

The pages must be served over HTTPS for the microphone to work, and they
must NOT be public: this is a licensed Samuel French play, and an email
gate limited to the cast is what keeps hosting it inside normal
production use. Cloudflare does both on its free plan.

1. Create a free account at dash.cloudflare.com (this step is yours; it
   asks for an email and password).
2. Workers & Pages -> Create -> Pages -> "Upload assets". Name the
   project something bland (not the play's title). Drag the whole
   `private/deploy` folder in. You get a `<name>.pages.dev` URL.
3. BEFORE sharing the URL, gate it: Zero Trust -> Access -> Applications
   -> Add an application -> Self-hosted. Application domain: your
   `<name>.pages.dev`. Policy: Allow -> Include -> Emails -> paste the
   cast's addresses. (The free Zero Trust plan covers a small team;
   check the seat limit on the plan page when you set it up.)
4. Cast members visit the URL, get a one-time PIN by email, and land on
   the character list. Voice mode works because the site is HTTPS.
5. After any script fix: rebuild pages, rerun prep_deploy.py, and drag
   the folder into the same Pages project again (it redeploys in place).

Send each actor either the site URL (they pick their name) or the direct
link to their page, e.g. `https://<name>.pages.dev/PENELOPE.html`.
"""


def main():
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    src, dst = sys.argv[1:3]
    os.makedirs(dst, exist_ok=True)
    # A page removed from the build must not linger from an old copy.
    for f in os.listdir(dst):
        if f.endswith(".html") and not os.path.exists(os.path.join(src, f)):
            os.remove(os.path.join(dst, f))
    links = []
    for f in sorted(os.listdir(src)):
        if not f.endswith(".html"):
            continue
        shutil.copy2(os.path.join(src, f), os.path.join(dst, f))
        key = f[:-5].replace("_", " ")
        nice = key.title()
        badge = AVATARS.get(key, "")
        links.append('<a href="%s">%s %s</a>' % (f, badge, nice))
    with open(os.path.join(dst, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(INDEX.replace("__LINKS__", "\n".join(links)))
    # The director's workbench ships behind the same gate as the cast.
    fs = os.path.join(os.path.dirname(src), "french_scenes.html")
    if os.path.exists(fs):
        shutil.copy2(fs, os.path.join(dst, "french_scenes.html"))
    # The Voice Booth, its upload worker, and any voices already rendered
    # by Neil's Lab. Cast list comes from AVATARS so even the CHOIRBOY
    # (no practice page, but his lines cue people) can leave a voice.
    with open(os.path.join(dst, "voice_booth.html"), "w",
              encoding="utf-8") as fh:
        fh.write(BOOTH.replace("__CAST__", json.dumps(sorted(AVATARS))))
    here = os.path.dirname(os.path.abspath(__file__))
    shutil.copy2(os.path.join(here, "_worker.js"),
                 os.path.join(dst, "_worker.js"))
    voices = os.path.join(os.path.dirname(src), "voices")
    if os.path.isdir(voices):
        shutil.copytree(voices, os.path.join(dst, "voices"),
                        dirs_exist_ok=True)
        n = sum(len(fs) for _, _, fs in os.walk(voices))
        print("real-voice clips: %d files" % n)
    with open(os.path.join(dst, "_headers"), "w", encoding="utf-8") as fh:
        fh.write(HEADERS)
    with open(os.path.join(dst, "robots.txt"), "w", encoding="utf-8") as fh:
        fh.write(ROBOTS)
    with open(os.path.join(dst, "DEPLOY.md"), "w", encoding="utf-8") as fh:
        fh.write(DEPLOY_MD)
    print("%d pages + index + headers -> %s" % (len(links), dst))
    print("read %s/DEPLOY.md for the upload steps" % dst)


if __name__ == "__main__":
    main()

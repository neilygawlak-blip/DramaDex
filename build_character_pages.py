"""Build one self-contained practice page per character from the cleaned script.

Each page is a single HTML file a cast member can be sent individually. It
holds their whole part: every line they speak, with the cue that comes
before it. No server, no install, nothing leaves the file.

How a page runs, per the prototype spec (Aug 2026):
  - Hands-free. The mic listens continuously; the page only *judges* while
    it is the actor's turn, and the moment it hears the final word of their
    line it stops judging and moves on. Pause button instead of any
    push-to-talk. Untimed throughout.
  - The actor picks the run before starting: the whole play, one act, one
    of their scene-runs (contiguous stretches where their character is in
    the thick of it), or a folder they made themselves — the star on any
    line files it into a named folder, which is how the hard ones get
    collected.
  - Cues are read aloud by the browser's own voice. Cues that carry a
    sound effect (doorbell, telephone, crash, church bells) fire a small
    synthesized effect first — WebAudio tones, no audio files, nothing to
    license.
  - While a cue is read aloud, an emoji shows its tone, taken from the
    stage direction when the script gives one (angrily, laughing,
    nervously, hurriedly...). A plain line gets the neutral smile: when we
    don't really know, we don't pretend to.
  - Feedback is three emoji tiers, scored forgivingly on a word diff:
    nailed it / close / not yet. Type-to-answer is the fallback when the
    browser refuses the mic (file:// pages cannot use it; localhost can).

Usage:
    python build_character_pages.py private/see_how_they_run_raw.txt \
        private/cast_see_how_they_run.txt private/handouts
"""

import datetime
import json
import os
import re
import sys

ACT_RE = re.compile(r"^ACT (ONE|TWO|THREE)\b")
ACTS = {"ONE": "Act I", "TWO": "Act II", "THREE": "Act III"}
# A stretch this many speeches long without the character means their
# scene-run has ended and the next line of theirs starts a fresh one.
RUN_GAP = 15
# A run smaller than this is clutter in the menu, not a scene: it gets
# folded into the run before it.
RUN_MIN = 4

BACK_MATTER = ("FURNITURE PLOT", "PROPERTY PLOT", "EFFECTS PLOT", "COSTUMES")

# Printed page range of each act in the Samuel French edition. A speech's
# page is interpolated inside its act; the type is dense and even enough
# that this lands within a page of the real book.
ACT_PAGES = {"Act I": (5, 32), "Act II": (33, 61), "Act III": (62, 101)}

# Speakers who exist in the script (their lines still cue other people and
# get voiced in Full Scene) but are not roles anyone practises: no page.
NO_PAGE = {"CHOIRBOY"}

# Tone of a cue, read off its stage direction. Order matters: the first
# family with a hit wins, and no hit means the honest neutral smile.
MOODS = [
    ("\U0001F620", r"angr|furious|fierce|roar|rag[ei]|sharply|severely|"
                   r"acidly|wither|testily|snapp|indignan|sternly"),
    ("\U0001F631", r"scream|shriek|yell|horror|horrified|terrif|panic"),
    ("\U0001F606", r"laugh|giggl|chuckl|gaily|happily|merrily|brightly|"
                   r"delighted|joyful"),
    ("\U0001F622", r"\bsad|dolefully|miserabl|weep|sob|mournful|gloomil|"
                   r"tearful|wail"),
    ("\U0001F630", r"nervous|anxious|frighten|alarm|uneasi|desperat|"
                   r"flustered|tremulous|wretchedly|frantic"),
    ("\U0001F3C3", r"hurried|quickly|rushing|rapid|briskly"),
    ("\U0001F632", r"surpris|startl|amaz|astonish|aghast|stunned|gasp"),
    ("\U0001F915", r"dazed|bewilder|blankly|vaguely|baffled|confus|"
                   r"mystified|helpless"),
    ("\U0001F910", r"quietly|murmur|whisper|low voice|undertone"),
    ("\U0001F97A", r"implor|plead|beg of|appeal"),
]
MOODS = [(e, re.compile(rx, re.I)) for e, rx in MOODS]
NEUTRAL = "\U0001F642"


def mood_of(text):
    """The tone emoji for a speech, from its parenthetical directions."""
    directions = " ".join(re.findall(r"\(([^)]*)\)", text))
    for emoji, rx in MOODS:
        if rx.search(directions):
            return emoji
    return NEUTRAL


# Farce runs fast. The reader's base rate is brisk, a cue marked hurried
# goes faster still, and only an explicitly slow direction gets to dawdle.
PACE_FAST = re.compile(r"hurried|quickly|rapid|briskly|rushing|excited|"
                       r"wildly|frantic|shout|scream|yell", re.I)
PACE_SLOW = re.compile(r"slowly|ponderous|heavily|drawl|dazed|vaguely|"
                       r"murmur|sleepy|solemn", re.I)


def pace_of(text):
    directions = " ".join(re.findall(r"\(([^)]*)\)", text))
    if PACE_FAST.search(directions):
        return 1.6
    if PACE_SLOW.search(directions):
        return 1.0
    return 1.3


# Emoji-art badges: each character in the costume the audience mostly sees
# them in, per the printed costume plot. Two emoji, distinguishable at a
# glance, nothing to render or license.
AVATARS = {
    "IDA":          "\U0001F9F9\U0001F375",   # broom and the tea she carries
    "MISS SKILLON": "\U0001F452\U0001F6B2",   # felt hat, the famous bicycle
    "PENELOPE":     "\U0001F3AD\U0001F456",   # actress in the scandalous slacks
    "LIONEL":       "✝\U0001FA73",       # the vicar, reduced to his shorts
    "CLIVE":        "\U0001FA96✝",       # airman in a borrowed dog collar
    "BISHOP":       "✝\U0001F458",       # bishop in pyjamas and robe
    "HUMPHREY":     "✝\U0001F9E3",       # the mild one with the muffler
    "MAN":          "\U0001F17F️\U0001F52B",  # dungarees marked P, revolver
    "SERGEANT":     "\U0001F46E\U0001F4D3",   # copper with his notebook
    "CHOIRBOY":     "\U0001F466\U0001F3B6",   # Willie, heard singing off
}

# Who sounds like what, per Chris's casting. "proper" prefers a British
# voice when the machine has one, "casual" an American; "faster" bumps the
# rate on top of the farce pace. The browser picks the nearest voice it
# actually has, so this degrades gracefully on any machine.
VOICE_PROFILES = {
    "IDA":          {"g": "f", "style": "casual", "mult": 1.15},
    "MISS SKILLON": {"g": "f", "style": "casual", "mult": 1.0},
    "PENELOPE":     {"g": "f", "style": "casual", "mult": 1.15},
    "LIONEL":       {"g": "m", "style": "proper", "mult": 1.0},
    "CLIVE":        {"g": "m", "style": "casual", "mult": 1.0},
    "BISHOP":       {"g": "m", "style": "proper", "mult": 1.0},
    "HUMPHREY":     {"g": "m", "style": "proper", "mult": 1.0},
    "MAN":          {"g": "m", "style": "casual", "mult": 1.0},
    "SERGEANT":     {"g": "m", "style": "casual", "mult": 1.0},
    "CHOIRBOY":     {"g": "m", "style": "casual", "mult": 1.0},
}

SFX_RE = [
    ("doorbell", re.compile(r"DOORBELL|DOOR-BELL|front door bell", re.I)),
    ("phone", re.compile(r"TELEPHONE rings|'phone rings|PHONE-BELL", re.I)),
    ("crash", re.compile(r"CRASH", re.I)),
    ("church", re.compile(r"church BELLS|BELLS tops|clanging of church", re.I)),
    ("slam", re.compile(r"slams the door|door[- ]slam", re.I)),
    ("bump", re.compile(r"bumping noise|bumps in|loud HAMMERING|KNOCK from",
                        re.I)),
    ("bell", re.compile(r"\bBELL rings\b|rings servant bell", re.I)),
]


def spoken(text, speaker):
    """What the actor actually says: no name, no stage directions."""
    t = text
    if t.upper().startswith(speaker.upper()):
        t = t[len(speaker):]
    t = re.sub(r"\([^)]*\)", " ", t)
    # "CLIVE and HUMPHREY (together)." lines: the second name is part of
    # the heading, not something anyone says aloud.
    t = re.sub(r"^\s*and\s+[A-Z][A-Z ]+?\s*[.:]", "", t)
    t = t.lstrip(" .:")
    return re.sub(r"\s+", " ", t).strip()


def parse(rawfile, cast):
    speech_re = re.compile(
        r"^(%s)\b" % "|".join(re.escape(c) for c in
                              sorted(cast, key=len, reverse=True)))
    text = open(rawfile, encoding="utf-8").read()
    act, speeches = "Front matter", []
    for p in (q.strip() for q in text.split("\n\n") if q.strip()):
        m = ACT_RE.match(p)
        if m:
            act = ACTS[m.group(1)]
            continue
        # The Act One heading rode inside a front-matter paragraph, so the
        # first spoken line is what actually opens the act.
        if act == "Front matter" and speech_re.match(p):
            act = "Act I"
        if any(p.startswith(b) for b in BACK_MATTER):
            break
        m = speech_re.match(p)
        sfx = next((n for n, rx in SFX_RE if rx.search(p)), None)
        # A paragraph with no name that is not a direction or a heading is
        # a splinter of the speech before it: OCR broke the paragraph, and
        # unstitched it would simply vanish from every page.
        if (not m and speeches and speeches[-1]["speaker"]
                and not p.startswith("(")
                and not re.match(r"(SCENE|TIME|CURTAIN|QUICK CURTAIN|"
                                 r"THE CURTAIN|WARN)\b", p)
                and any(c.islower() for c in p)):
            prev = speeches[-1]
            prev["text"] += " " + p
            # Recompute the say from the JOINED text: a direction split
            # across the seam has unbalanced halves, and stripping the
            # fragments separately leaked both halves into the spoken line.
            prev["say"] = spoken(prev["text"], prev["speaker"])
            prev["sfx"] = prev["sfx"] or sfx
            continue
        speeches.append({
            "act": act,
            "speaker": m.group(1) if m else None,
            "text": p,
            "say": spoken(p, m.group(1)) if m else "",
            "sfx": sfx,
        })
    number_pages(speeches)
    return speeches


def number_pages(speeches):
    """Give every speech its printed page, interpolated within its act."""
    by_act = {}
    for i, s in enumerate(speeches):
        by_act.setdefault(s["act"], []).append(i)
    for act, idxs in by_act.items():
        lo, hi = ACT_PAGES.get(act, (0, 0))
        for j, i in enumerate(idxs):
            speeches[i]["page"] = (lo + j * (hi - lo + 1) // len(idxs)
                                   if lo else 0)


def runs_for(speeches, name):
    """The character's scene-runs: [{label, lines:[indexes]}].

    A run never crosses an act boundary, and small runs are folded into
    their neighbour only within the same act. Before that rule, the MAN's
    two-line Act II entrance was welded onto his first Act III scene and
    the lot was labelled Act II, which read as fifteen Act II lines he
    does not have.
    """
    runs, current, last_i = [], [], None
    for i, s in enumerate(speeches):
        if s["speaker"] != name or not s["say"]:
            continue
        if current and (i - last_i > RUN_GAP
                        or s["act"] != speeches[current[0]]["act"]):
            runs.append(current)
            current = []
        current.append(i)
        last_i = i
    if current:
        runs.append(current)
    merged = []
    for r in runs:
        same_act = (merged and
                    speeches[merged[-1][0]]["act"] == speeches[r[0]]["act"])
        if same_act and (len(r) < RUN_MIN or len(merged[-1]) < RUN_MIN):
            merged[-1].extend(r)
        else:
            merged.append(r)
    labelled, counts = [], {}
    for r in merged:
        act = speeches[r[0]]["act"]
        counts[act] = counts.get(act, 0) + 1
        labelled.append({"label": "%s — run %d" % (act, counts[act]),
                         "lines": r})
    return labelled


def cue_for(speeches, i):
    """The line before theirs: who says it and its tail end."""
    for j in range(i - 1, -1, -1):
        s = speeches[j]
        if s["speaker"] and s["say"]:
            tail = s["say"]
            if len(tail) > 160:
                tail = "\u2026 " + tail[-160:]
            return {"speaker": s["speaker"], "say": tail,
                    "sfx": speeches[i - 1]["sfx"] or s["sfx"],
                    "mood": mood_of(s["text"]),
                    "pace": pace_of(s["text"])}
        if s["sfx"]:
            return {"speaker": "", "say": "", "sfx": s["sfx"],
                    "mood": NEUTRAL}
    return {"speaker": "", "say": "(top of the play)", "sfx": None,
            "mood": NEUTRAL}


TEMPLATE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__NAME__ — See How They Run</title>
<style>
 body{font-family:"Segoe UI Variable Display","Segoe UI",system-ui,"Helvetica Neue",Arial,sans-serif;
      font-weight:500;letter-spacing:.012em;max-width:640px;margin:2rem auto;
      padding:0 1rem;background:#0a0f1e;color:#e8e6df;line-height:1.55}
 h1{font-size:1.45rem;font-weight:800;letter-spacing:.03em;margin-bottom:.2rem;color:#ffd75e}
 .muted{color:#7d87a3;font-size:.9rem;font-weight:400}
 select,button{font-size:1rem;padding:.45rem .8rem;margin:.2rem .3rem .2rem 0;
      border:1px solid #2b3a5e;border-radius:8px;background:#111a30;color:#e8e6df;cursor:pointer}
 button.primary{background:#0d1526;color:#ffd75e;border:1px solid #ffd75e;
      text-shadow:0 0 6px #ffb347,0 0 14px #ff9d1c;
      box-shadow:0 0 8px rgba(255,183,71,.45),inset 0 0 8px rgba(255,183,71,.15);
      animation:hum 2.6s ease-in-out infinite}
 @keyframes hum{50%{box-shadow:0 0 16px rgba(255,183,71,.75),inset 0 0 10px rgba(255,183,71,.25)}}
 #stage{margin-top:1.4rem;min-height:10rem}
 .cue{color:#9aa4c0;font-style:italic;margin-bottom:1rem}
 .mine{font-size:1.18rem;font-weight:600;color:#f2f0e9}
 .cuename{font-style:normal;font-weight:700;font-variant:small-caps;
      letter-spacing:.04em;color:#dfe6f7;display:inline-block;
      padding:.06rem .55rem;border:1px solid #3a4a75;border-radius:999px;
      background:#131d38;box-shadow:0 2px 8px rgba(0,0,0,.55),
      0 0 6px rgba(255,183,71,.12)}
 #verdict{font-size:2.2rem;margin:.5rem 0}
 #diff span.ok{color:#7fe0a7}
 #diff span.pending{color:transparent;border-bottom:1px dotted #3a4a75}
 #diff span.pending.lit{color:#7fe0a7;border-bottom:none}
 #diff span.pending.show{color:#8d97b8}
 #hints{margin-top:.6rem}
 #hints button{font-size:.85rem;padding:.3rem .7rem;color:#9aa4c0}
 #ctxbtn{position:fixed;bottom:1.7rem;right:5.1rem;font-size:.75rem;
      padding:.3rem .7rem;color:#7d87a3;border-radius:999px;
      background:#0d1526;box-shadow:0 2px 8px rgba(0,0,0,.5)}
 #ctx{display:none;position:fixed;inset:7% 5%;overflow-y:auto;z-index:9;
      background:#0d1526;border:1px solid #3a4a75;border-radius:12px;
      padding:1rem 1.2rem;font-size:.9rem;color:#c7cee2;
      box-shadow:0 8px 40px rgba(0,0,0,.8)}
 #ctx .fsline{margin:.4rem 0}
 #ctx .fsmine{color:#ffd75e}
 #ctx .fsnow{outline:1px solid #ffd75e;border-radius:6px;padding:.15rem .35rem;display:inline-block}
 #where{margin-top:1.6rem;font-size:.78rem;letter-spacing:.06em;
      color:#55618a;text-transform:uppercase}
 #pausebtn{position:fixed;bottom:1.2rem;right:1.2rem;width:3.1rem;height:3.1rem;
      border-radius:50%;font-size:1.15rem;line-height:1;padding:0;
      background:#0d1526;border:1px solid #3a4a75;color:#ffd75e;
      box-shadow:0 2px 10px rgba(0,0,0,.6),0 0 8px rgba(255,183,71,.2)}
 .star{cursor:pointer;border:none;background:none;font-size:1.1rem}
 #mystate{font-size:.85rem;color:#7d87a3}
 .listening{color:#7fe0a7;font-weight:bold}
 #againbtn{border:none;background:none;cursor:pointer;color:#ffd75e;
      font-size:.8rem;display:inline-flex;align-items:center;gap:.35rem;
      margin-left:.6rem;vertical-align:middle;padding:0}
 #againbtn svg{width:1.5rem;height:1.5rem;transform:rotate(-90deg)}
 #againbtn .rbg{fill:none;stroke:#2b3a5e;stroke-width:3}
 #againbtn .rfg{fill:none;stroke:#ffd75e;stroke-width:3;
      stroke-dasharray:63;stroke-dashoffset:0;animation:ring 1s linear forwards}
 @keyframes ring{to{stroke-dashoffset:63}}
 #backbtn{position:fixed;bottom:1.2rem;left:1.2rem;font-size:.75rem;
      color:#7d87a3;background:#0d1526;border:1px solid #2b3a5e;
      border-radius:999px;padding:.35rem .8rem;text-decoration:none;
      box-shadow:0 2px 8px rgba(0,0,0,.5)}
 #backbtn:hover{border-color:#ffd75e;color:#e8e6df}
 #reportbtn{position:fixed;bottom:3.6rem;left:1.2rem;font-size:.72rem;
      color:#55618a;background:#0d1526;border:1px solid #2b3a5e;
      border-radius:999px;padding:.3rem .7rem;text-decoration:none;
      box-shadow:0 2px 8px rgba(0,0,0,.5)}
 #reportbtn:hover{border-color:#ffd75e;color:#e8e6df}
 #build{margin-top:2.2rem;font-size:.68rem;color:#39415e;text-align:center}
</style></head><body>
<h1>__AVATAR__ __NAME__ <span class="muted">— See How They Run</span></h1>
<div class="muted">__COUNT__ lines. Pick a scene, press the pineapple, and
just speak when it's your turn.</div>
<div id="controls">
 <select id="scope"></select>
 <select id="mode">
  <option value="drill">Just cue lines</option>
  <option value="scene">Full scene (waits for you)</option>
  <option value="listen">Listen through</option>
 </select>
 <button class="primary" id="startbtn">&#127821; Start</button>
 <button id="prevbtn" style="display:none" title="previous line (left arrow)">&#9664;</button>
 <button id="nextbtn" style="display:none" title="next line (right arrow)">&#9654;</button>
 <button id="pausebtn" style="display:none" title="pause">&#9208;</button>
</div>
<div id="mystate"></div>
<div id="stage"></div>
<div id="where"></div>
<a id="backbtn" href="index.html">&#8592; Back to Character List</a>
<a id="reportbtn" href="#">&#9888; Tell Neil it broke</a>
<div id="build">build __BUILD__</div>
<script>
const DATA=__DATA__;
const NAME="__NAME__";
// ---- scope menu: whole play, acts, scene-runs ----
const scope=document.getElementById("scope");
function buildScope(){
 scope.innerHTML="";
 const add=(v,t)=>{const o=document.createElement("option");o.value=v;o.textContent=t;scope.appendChild(o);};
 add("all","From the top ("+DATA.lines.length+" lines)");
 [...new Set(DATA.lines.map(l=>l.act))].forEach(a=>{
  const n=DATA.lines.filter(l=>l.act===a).length;
  add("act:"+a,a+" ("+n+" lines)");});
 DATA.runs.forEach((r,i)=>add("run:"+i,r.label+" ("+r.lines.length+" lines)"));
}
buildScope();
// Nobody drills one line, and few start with the whole play: the first
// scene-run is the natural default bite.
if(DATA.runs.length)scope.value="run:0";

function currentSet(){
 const v=scope.value;
 if(v==="all")return DATA.lines.map((_,i)=>i);
 if(v.startsWith("act:"))return DATA.lines.map((l,i)=>[l,i]).filter(x=>x[0].act===v.slice(4)).map(x=>x[1]);
 if(v.startsWith("run:"))return DATA.runs[+v.slice(4)].lines.map(g=>DATA.lines.findIndex(l=>l.i===g)).filter(i=>i>=0);
 return [];
}

// ---- tiny synthesized sound effects (no files, nothing to license) ----
let AC=null;
function tone(f,t0,d,type,gain){const o=AC.createOscillator(),g=AC.createGain();
 o.type=type||"sine";o.frequency.value=f;g.gain.setValueAtTime(gain||.25,AC.currentTime+t0);
 g.gain.exponentialRampToValueAtTime(.001,AC.currentTime+t0+d);
 o.connect(g).connect(AC.destination);o.start(AC.currentTime+t0);o.stop(AC.currentTime+t0+d);}
function noise(t0,d){const b=AC.createBuffer(1,AC.sampleRate*d,AC.sampleRate),ch=b.getChannelData(0);
 for(let i=0;i<ch.length;i++)ch[i]=(Math.random()*2-1)*Math.pow(1-i/ch.length,2);
 const s=AC.createBufferSource(),g=AC.createGain();g.gain.value=.4;s.buffer=b;
 s.connect(g).connect(AC.destination);s.start(AC.currentTime+t0);}
const SFX={
 doorbell(){tone(659,0,.4,"sine");tone(523,.35,.6,"sine");},
 bell(){for(let i=0;i<4;i++)tone(880,i*.15,.12,"square",.12);},
 phone(){for(let r=0;r<2;r++)for(let i=0;i<10;i++)tone(1000+(i%2)*180,r*1.1+i*.05,.05,"square",.1);},
 crash(){noise(0,.7);tone(180,0,.4,"sawtooth",.15);},
 church(){[392,330,294,262].forEach((f,i)=>tone(f,i*.7,1.6,"sine",.3));},
 slam(){noise(0,.18);tone(70,0,.25,"sine",.5);},
 bump(){[0,.4,.8].forEach(t=>{noise(t,.1);tone(90,t,.15,"sine",.4);});},
};
function playSfx(n){if(!n)return 0;if(!AC)AC=new (window.AudioContext||window.webkitAudioContext)();SFX[n]();
 return n==="church"?3000:n==="phone"?2300:n==="slam"?500:n==="bump"?1300:1200;}

// ---- forgiving word diff, the workbench tiers ----
const norm=s=>s.toLowerCase().replace(/[^a-z0-9' ]+/g," ").replace(/\\s+/g," ").trim();
const FILLERS=new Set(["er","um","uh","erm","like","well"]);
// Phonetic key (metaphone-style consonant skeleton). The recognizer
// mishears an accented or mumbled word as a *soundalike* real word:
// this/these, wish/which, knot/not, four/for. Two words with the same
// key count as the same word. A paraphrase still fails, because
// different words make different sounds: forgives the accent, never
// the wording.
function pkey(w){
 w=w.toLowerCase().replace(/[^a-z]/g,"");
 if(!w)return"";
 w=w.replace(/^kn|^gn/,"n").replace(/^wr/,"r").replace(/^ps/,"s").replace(/^wh/,"w");
 w=w.replace(/mb$/,"m").replace(/tion|sion/g,"xn");
 w=w.replace(/sch/g,"sk").replace(/ch|sh/g,"x").replace(/th/g,"t");
 w=w.replace(/ph/g,"f").replace(/gh$/,"f").replace(/gh/g,"");
 w=w.replace(/ck/g,"k").replace(/c(?=[iey])/g,"s").replace(/c/g,"k").replace(/q/g,"k").replace(/x/g,"ks");
 w=w.replace(/dg/g,"j").replace(/g(?=[iey])/g,"j");
 w=w.replace(/z/g,"s").replace(/v/g,"f").replace(/d/g,"t").replace(/b/g,"p").replace(/(.)h/g,"$1");
 if(w.length>3)w=w.replace(/s$/,"");
 const first=w[0]||"";
 w=(first+w.slice(1).replace(/[aeiouy]/g,"")).replace(/(.)\\1+/g,"$1");
 return w;
}
// True homophones the skeleton cannot merge (two/too) fold to one
// spelling before any comparison.
const HC={two:"to",too:"to",their:"there",your:"youre",hear:"here",
 know:"no",won:"one",wear:"where",whose:"whos",knew:"new",ate:"eight"};
// Dialect equivalence: the page DISPLAYS the line as printed ('aven't,
// goin', wot) but the recognizer transcribes standard English, so both
// sides of every comparison fold to the proper word. Ida speaks cockney;
// her actor should not be punished for saying it right.
const DMAP={wot:"what",orl:"all",fur:"for",praps:"perhaps",oo:"who",
 salright:"alright",gawd:"god",lor:"lord",arf:"half",nuffink:"nothing",
 yer:"your",ome:"home",ot:"hot",eaven:"heaven",ell:"hell"};
function canon(w){
 const bare0=w.replace(/'/g,"");
 if(w.endsWith("'m")&&w.length>2)w=w.slice(0,-2);   // yes'm -> yes
 if(w.endsWith("in'"))w=w.slice(0,-1)+"g";          // goin' -> going
 if(w.startsWith("'")&&w.length>1)w="h"+w.slice(1); // 'aven't -> haven't
 let b=w.replace(/'/g,"");
 if(DMAP[bare0]!==undefined)b=DMAP[bare0];
 return HC[b]||b;
}
// A heard word matches a script word by spelling OR by sound. Sound
// matches only count for words of 3+ letters: tiny words collapse to
// near-nothing phonetically and would match anything.
function soundSets(H){
 H=H.map(canon);
 return {hset:new Set(H),pset:new Set(H.map(pkey).filter(k=>k.length>1))};
}
const wordOk=(w,S)=>{w=canon(w);
 return S.hset.has(w)||(w.length>2&&S.pset.has(pkey(w)));};
function grade(expected,heard){
 const E=norm(expected).split(" ").filter(w=>w),H=norm(heard).split(" ").filter(w=>!FILLERS.has(w));
 const S=soundSets(H);let hit=0;const marks=E.map(w=>{const ok=wordOk(w,S);if(ok)hit++;return {w,ok};});
 const r=E.length?hit/E.length:1;
 return {tier:r>=.9?"\\u{1F3AF} Nailed it":r>=.65?"\\u{1F642} Close":"\\u{1F501} Not yet",marks,r};
}

// ---- the run loop ----
const stage=document.getElementById("stage"),my=document.getElementById("mystate");
const startbtn=document.getElementById("startbtn"),pausebtn=document.getElementById("pausebtn");
const prevbtn=document.getElementById("prevbtn"),nextbtn=document.getElementById("nextbtn");
let queue=[],pos=0,running=false,paused=false,judging=false,heard="",rec=null,revealed=false;

// ---- pick a system voice per character: gender, then accent preference ----
const FEM=/female|zira|hazel|susan|heather|catherine|linda|samantha|karen|serena|kate|fiona|moira|tessa|libby|sonia|aria|jenny|michelle/i;
const MASC=/male|david|mark|george|richard|james|ryan|daniel|alex|fred|oliver|thomas|guy|william|sean/i;
const rank=v=>/natural|neural/i.test(v.name)?0:/google/i.test(v.name)?1:2;
function pickVoice(p,who){
 const vs=speechSynthesis.getVoices().filter(v=>v.lang&&v.lang.startsWith("en"));
 if(!vs.length)return null;
 const gender=v=>FEM.test(v.name)?"f":MASC.test(v.name)?"m":"?";
 let pool=vs.filter(v=>gender(v)===p.g);
 if(!pool.length)pool=vs;
 const wantGB=p.style==="proper";
 const accent=pool.filter(v=>wantGB?v.lang.includes("GB"):v.lang.includes("US"));
 pool=accent.length?accent:pool;
 // Edge ships neural voices through this same API and they are in a
 // different league to the old local ones; always take that tier when
 // present, then spread the cast across it so no two characters need to
 // share a voice while others sit unused.
 pool.sort((a,b)=>rank(a)-rank(b));
 const best=pool.filter(v=>rank(v)===rank(pool[0]));
 let h=0;for(const ch of (who||""))h=(h*31+ch.charCodeAt(0))>>>0;
 return best[h%best.length];
}
// iOS reads the same rate number far faster than desktop does, so rates
// are squeezed toward normal there: quick stays quicker, nobody gabbles.
const IOS=/iPad|iPhone|iPod/.test(navigator.userAgent)
 ||(navigator.platform==="MacIntel"&&navigator.maxTouchPoints>1);
function speak(t,pace,who,done){if(!t){done();return;}const u=new SpeechSynthesisUtterance(t);
 const p=(DATA.voices&&DATA.voices[who])||{g:"m",style:"casual",mult:1};
 const v=pickVoice(p,who);if(v)u.voice=v;
 let r=(pace||1.3)*(p.mult||1);
 if(IOS)r=1+(r-1)*.3;
 u.rate=r;
 // The pitch shove tells the old robotic voices apart, but a neural
 // voice already sounds like a person: bending it just adds artifacts.
 u.pitch=(v&&rank(v)===0)?1:(p.g==="f"?1.1:.85);
 // Chrome swallows utterances queued right after a cancel and sometimes
 // never fires onend at all. Whatever happens to the audio, the run must
 // move: done() is guaranteed, once, by whichever signal arrives first.
 let fin=false;const fin1=()=>{if(!fin){fin=true;clearTimeout(guard);done();}};
 u.onend=fin1;u.onerror=fin1;
 const est=1200+t.split(" ").length*430/u.rate;
 const guard=setTimeout(fin1,est+2500);
 speechSynthesis.speak(u);}

function show(l,auto){
 const c=l.cue;
 const av=c.speaker&&DATA.avatars&&DATA.avatars[c.speaker]||"";
 const myAv=(DATA.avatars&&DATA.avatars[NAME])||"";
 const words=norm(l.say).split(" ").filter(w=>w);
 const mine=auto?esc(l.say)
  :words.map(w=>'<span class="pending">'+esc(w)+'</span>').join(" ");
 stage.innerHTML='<div class="cue"><span style="font-size:1.6rem">'+(c.mood||"\\u{1F642}")+'</span> '+
  (c.sfx?"\\u{1F514} ":"")+
  (c.speaker?'<span class="cuename">'+av+" "+c.speaker+'.</span> ':"")+esc(c.say)+
  '<button id="ctxbtn">Full Script</button></div>'+
  '<div id="ctx"></div>'+
  '<div id="verdict"></div>'+
  '<div class="mine"><span class="cuename">'+myAv+" "+NAME+'.</span> <span id="diff">'+mine+'</span></div>'+
  (auto?"":'<div id="hints"><button id="wordbtn">Next Word</button> <button id="linebtn">Line</button> <button id="gotbtn">\\u2713 Got it</button></div>');
 const cb=document.getElementById("ctxbtn");
 // Full Script: the whole selected run, everyone's lines in order, with
 // the actor's lines gold and the current line boxed. Rebuilt from the
 // gaps, so nothing new ships in the file.
 if(cb)cb.onclick=()=>{const x=document.getElementById("ctx");
  if(x.style.display==="block"){x.style.display="none";return;}
  let h='<div style="text-align:right;position:sticky;top:0"><button id="fsclose">Close</button></div>';
  queue.forEach((qi,k)=>{const L=DATA.lines[qi];
   (L.gap||[]).forEach(g=>{h+='<div class="fsline">'+
    (g.t?'<b>'+esc(g.s)+'.</b> '+esc(g.t):"\\u{1F514} (sound)")+"</div>";});
   h+='<div class="fsline fsmine'+(k===pos?" fsnow":"")+'"><b>'+esc(NAME)+'.</b> '+esc(L.say)+'</div>';});
  x.innerHTML=h;x.style.display="block";
  document.getElementById("fsclose").onclick=()=>{x.style.display="none";};
  const now=x.querySelector(".fsnow");if(now)now.scrollIntoView({block:"center"});};
 const wb=document.getElementById("wordbtn"),lb=document.getElementById("linebtn");
 if(wb)wb.onclick=()=>{const nxt=stage.querySelector("#diff .pending:not(.lit):not(.show)");
  if(nxt)nxt.classList.add("show");};
 if(lb)lb.onclick=()=>stage.querySelectorAll("#diff .pending").forEach(s=>s.classList.add("show"));
 // The mic will not catch everything (Russian, mumbles, loud rooms):
 // Got it is the actor vouching for themselves, and the run moves on.
 const gb=document.getElementById("gotbtn");
 if(gb)gb.onclick=()=>{if(!running)return;judging=false;
  speechSynthesis.cancel();token++;pos++;setTimeout(step,150);};
}
function lightUp(text){
 const S=soundSets(norm(text).split(" "));
 stage.querySelectorAll("#diff .pending").forEach(s=>{
  if(wordOk(s.textContent,S))s.classList.add("lit");});
}
const esc=s=>s.replace(/[&<>]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;"}[c]));


const mode=document.getElementById("mode");
const whereEl=document.getElementById("where");
function setWhere(l){
 const v=scope.value;
 const label=v.startsWith("run:")?DATA.runs[+v.slice(4)].label:l.act;
 whereEl.textContent=(l.page?"p. "+l.page+" \\u00b7 ":"")+label
  +" \\u00b7 line "+(pos+1)+" of "+queue.length;
}
let token=0;
function myTurn(l,t,auto){
 if(t!==token||!running)return;
 show(l,auto);
 if(auto){speak(l.say,1.3,NAME,()=>{if(t===token&&running&&!paused)
   setTimeout(()=>{if(t===token&&running&&!paused){pos++;step();}},500);});}
 else{judging=true;
  my.textContent=rec?"":"No mic here: say it out loud anyway, then \\u25B6";}
}
function showGap(g){
 const av=g.s&&DATA.avatars&&DATA.avatars[g.s]||"";
 stage.innerHTML='<div class="cue"><span style="font-size:1.6rem">'+(g.m||"\\u{1F642}")+'</span> '+
  (g.x?"\\u{1F514} ":"")+
  (g.s?'<span class="cuename">'+av+" "+g.s+'.</span> ':"")+esc(g.t)+'</div>';
}
function playGap(l,k,t,auto){
 if(t!==token||!running||paused)return;
 const gap=l.gap||[];
 if(k>=gap.length){myTurn(l,t,auto);return;}
 const g=gap[k];
 showGap(g);
 const wait=playSfx(g.x);
 setTimeout(()=>{if(t!==token||!running||paused)return;
  speak(g.t,g.p,g.s,()=>playGap(l,k+1,t,auto));},wait);
}
function step(){
 if(!running||paused)return;
 if(pos>=queue.length){
  const v=scope.value;
  const what=v.startsWith("act:")?v.slice(4)+" complete!"
   :v.startsWith("run:")?"Scene complete!":"That's the whole play!";
  stage.innerHTML='<div id="verdict">\\u{1F389}</div><div class="mine">'+what+'</div>';
  whereEl.textContent="";my.textContent="";stop();return;}
 const t=++token;
 const l=DATA.lines[queue[pos]];heard="";
 setWhere(l);
 if(mode.value==="drill"){
  show(l,false);
  const wait=playSfx(l.cue.sfx);
  setTimeout(()=>{if(t!==token||!running||paused)return;
   speak(l.cue.say,l.cue.pace,l.cue.speaker,()=>{if(t!==token||!running||paused)return;
    judging=true;
    my.textContent=rec?"":"No mic here: say it out loud anyway, then \\u25B6";});},wait);
 }else{
  // Never perform more than the last stretch before their line: a
  // character who enters late would otherwise sit through half the play.
  playGap(l,Math.max(0,(l.gap||[]).length-8),t,mode.value==="listen");
 }
}

function judged(l,text){
 judging=false;const g=grade(l.say,text);
 const v=document.getElementById("verdict");
 v.textContent=g.tier;
 // Only the words they landed light up. A missed word stays a blank
 // slot rather than a red spoiler: hints are given when asked for,
 // never as a punishment.
 lightUp(text);
 my.textContent="";
 const t=token;
 // After any completion: a one-second ring, then straight on. Tapping
 // the ring ("Again") replays this line instead.
 const b=document.createElement("button");b.id="againbtn";
 b.innerHTML='<svg viewBox="0 0 24 24"><circle class="rbg" cx="12" cy="12" r="10"/>'+
  '<circle class="rfg" cx="12" cy="12" r="10"/></svg>Again';
 v.appendChild(b);
 const go=setTimeout(()=>{if(t===token&&running&&!paused){pos++;step();}},1000);
 b.onclick=()=>{clearTimeout(go);
  if(t===token&&running&&!paused){token++;setTimeout(step,100);}};
}

function lev(a,b){if(a===b)return 0;let p=[...Array(b.length+1).keys()];
 for(let i=1;i<=a.length;i++){const c=[i];
  for(let j=1;j<=b.length;j++)c.push(Math.min(p[j]+1,c[j-1]+1,p[j-1]+(a[i-1]!==b[j-1])));
  p=c;}return p[b.length];}
function doneEnough(l){
 // Advance only when the word JUST spoken is the line's final word
 // (off-by-a-letter allowed on longer words). Matching anywhere in the
 // transcript let a mid-line stall advance the run the moment an
 // earlier word resembled the ending. Nothing else auto-advances;
 // Got it and the arrow are the way onward when recognition loses it.
 const E=norm(l.say).split(" ").filter(w=>w);
 if(!E.length)return true;
 const H=norm(heard).split(" ").filter(w=>w);
 if(!H.length)return false;
 const last=canon(E[E.length-1]);
 const tol=last.length>=5?1:0;
 const endsRight=H.slice(-2).map(canon).some(h=>h===last||(tol&&lev(h,last)<=tol)
  ||(last.length>2&&pkey(h)===pkey(last)));
 if(!endsRight)return false;
 // A repeated word must not end the line early: "WE will get it ...
 // what is it?" says "it" at word four. The ending only counts once
 // most of the line is behind them. Three words or fewer are exempt.
 if(E.length<=3)return true;
 const S=soundSets(H);
 const hit=E.filter(w=>wordOk(w,S)).length;
 return hit/E.length>=.55;
}

function start(q){
 queue=q||currentSet();if(!queue.length){my.textContent="Nothing in that run.";return;}
 pos=0;running=true;paused=false;
 pausebtn.textContent="\\u23F8";pausebtn.title="pause";
 startbtn.style.display="none";pausebtn.style.display="";
 prevbtn.style.display="";nextbtn.style.display="";
 // Phones only let audio begin inside a real tap: wake the effects
 // engine and the speech engine here, while this IS a real tap.
 if(!AC)AC=new (window.AudioContext||window.webkitAudioContext)();
 if(AC.state==="suspended")AC.resume();
 try{const u=new SpeechSynthesisUtterance(" ");u.volume=0;speechSynthesis.speak(u);}catch(_){/**/}
 lockWake();initMic();step();
}
function stop(){running=false;unlockWake();startbtn.style.display="";pausebtn.style.display="none";
 prevbtn.style.display="none";nextbtn.style.display="none";
 if(rec){rec.onend=null;rec.stop();rec=null;}}
function jump(d){if(!running)return;speechSynthesis.cancel();judging=false;
 // Stepping forward off the last line is how a run ends, not a wall.
 pos=Math.max(0,Math.min(queue.length,pos+d));
 if(paused){paused=false;if(rec)try{rec.start();}catch(_){/**/}}
 pausebtn.textContent="\\u23F8";pausebtn.title="pause";my.textContent="";
 // A breath between cancel and the next speak, or Chrome eats the speak.
 token++;setTimeout(step,150);}
prevbtn.onclick=()=>jump(-1);nextbtn.onclick=()=>jump(1);
document.addEventListener("keydown",e=>{
 if(/INPUT|SELECT/.test(document.activeElement.tagName))return;
 if(e.key==="ArrowLeft")jump(-1);
 if(e.key==="ArrowRight")jump(1);});
// A hidden window keeps its mic and voice unless told otherwise, and two
// copies of the page then fight over both. Going invisible means pause.
let autoPaused=false;
document.addEventListener("visibilitychange",()=>{
 if(document.hidden&&running&&!paused){pause();autoPaused=true;}
 else if(!document.hidden&&running){
  // The OS drops the wake lock whenever the tab hides; take it back.
  lockWake();
  if(paused&&autoPaused){autoPaused=false;resume();}}});
startbtn.onclick=()=>start(currentSet());
// Changing the scene or mode mid-run: the queue was built at Start, so
// the old run would keep playing ("stuck on whatever the line is").
// Halt cleanly and hand back the pineapple, aimed at the new pick.
function halt(){token++;speechSynthesis.cancel();judging=false;paused=false;
 stop();stage.innerHTML="";whereEl.textContent="";
 my.textContent="\\u{1F34D} Press Start to run this selection.";}
scope.onchange=()=>{if(running)halt();};
mode.onchange=()=>{if(running)halt();};
// Pause must actually kill the run in flight: bump the token so every
// pending timer and speech callback goes stale, silence the voice, and
// release the mic. Without the token bump, cancelling the speech fires
// its done-callback, which flips judging back on — the page kept
// listening and reacting while "paused".
function pause(){if(paused)return;paused=true;token++;judging=false;
 pausebtn.textContent="\\u25B6";pausebtn.title="resume";
 speechSynthesis.cancel();
 if(rec)try{rec.abort();}catch(_){/**/}
 my.textContent="Paused.";}
function resume(){if(!paused)return;paused=false;autoPaused=false;
 pausebtn.textContent="\\u23F8";pausebtn.title="pause";
 my.textContent="";
 if(rec)try{rec.start();}catch(_){/**/}
 step();}
pausebtn.onclick=()=>{paused?resume():pause();};

// ---- keep the screen awake while a run is on (hands-free means nobody
// touches the phone, and a dimming screen would auto-pause the play) ----
let wake=null;
async function lockWake(){try{
 if("wakeLock" in navigator&&!wake){wake=await navigator.wakeLock.request("screen");
  wake.addEventListener("release",()=>{wake=null;});}}catch(_){/**/}}
function unlockWake(){if(wake){wake.release().catch(()=>{});wake=null;}}

// ---- error capture + one-tap bug report ----
let lastErr="";
window.addEventListener("error",e=>{lastErr=(e.message||"?")+" @"
 +String(e.filename||"").split("/").pop()+":"+e.lineno;});
window.addEventListener("unhandledrejection",e=>{lastErr=String(e.reason).slice(0,140);});
document.getElementById("reportbtn").onclick=ev=>{ev.preventDefault();
 const info="DramaDex "+NAME+" \\u00b7 build __BUILD__"
  +"\\n"+location.href
  +"\\n"+navigator.userAgent
  +"\\nscope "+scope.value+" \\u00b7 mode "+mode.value
  +(running?" \\u00b7 line "+(pos+1)+" of "+queue.length:"")
  +"\\nlast error: "+(lastErr||"none caught");
 try{navigator.clipboard.writeText(info);}catch(_){/**/}
 my.textContent="Report copied \\u2014 opening email\\u2026";
 location.href="mailto:Chris@nexustechfl.com?subject="
  +encodeURIComponent("DramaDex bug \\u2014 "+NAME)
  +"&body="+encodeURIComponent(info+"\\n\\nWhat happened / what needs fixing:\\n");};

function initMic(){
 const SR=window.SpeechRecognition||window.webkitSpeechRecognition;
 if(!SR||location.protocol==="file:"){rec=null;return;}
 rec=new SR();rec.continuous=true;rec.interimResults=true;rec.lang="en-US";
 rec.onresult=e=>{
  if(!judging)return;
  heard="";for(let i=0;i<e.results.length;i++)heard+=e.results[i][0].transcript+" ";
  lightUp(heard);
  const l=DATA.lines[queue[pos]];
  if(doneEnough(l)){try{rec.abort();}catch(_){/**/}judged(l,heard);setTimeout(()=>{try{if(rec)rec.start();}catch(_){/**/}},300);}
 };
 rec.onerror=e=>{if(e.error==="not-allowed"||e.error==="service-not-allowed"||e.error==="audio-capture"){
  if(rec){rec.onend=null;try{rec.abort();}catch(_){/**/}}rec=null;
  if(judging)my.textContent="No mic here: say it out loud anyway, then \\u25B6";}};
 rec.onend=()=>{if(running&&!paused&&rec)try{rec.start();}catch(_){/**/}};
 try{rec.start();}catch(_){rec=null;}
}
</script></body></html>
"""


def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    rawfile, castfile, outdir = sys.argv[1:4]
    # utf-8-sig: Windows editors and PowerShell love to prepend a BOM, and
    # an invisible byte glued to the first name silently drops that
    # character's every line.
    cast = [l.strip() for l in open(castfile, encoding="utf-8-sig")
            if l.strip()]
    speeches = parse(rawfile, cast)
    os.makedirs(outdir, exist_ok=True)

    for name in cast:
        if name in NO_PAGE:
            continue
        lines, prev = [], -1
        for i, s in enumerate(speeches):
            if s["speaker"] == name and s["say"]:
                # Everything between their last line and this one: the talk
                # and the noises they stand through on stage. Structured so
                # Full Scene mode can perform it, voice by voice.
                gap = []
                for g in speeches[prev + 1:i]:
                    if g["speaker"] and g["say"]:
                        gap.append({"s": g["speaker"], "t": g["say"],
                                    "m": mood_of(g["text"]),
                                    "p": pace_of(g["text"]),
                                    "x": g["sfx"]})
                    elif g["sfx"]:
                        gap.append({"s": "", "t": "", "m": NEUTRAL,
                                    "p": 1.3, "x": g["sfx"]})
                lines.append({"i": i, "act": s["act"], "say": s["say"],
                              "page": s.get("page", 0),
                              "cue": cue_for(speeches, i), "gap": gap})
                prev = i
        if not lines:
            continue
        runs = runs_for(speeches, name)
        data = {"lines": lines, "runs": runs, "voices": VOICE_PROFILES,
                "avatars": AVATARS}
        build = datetime.datetime.now().strftime("%b %d, %I:%M %p")
        html = (TEMPLATE
                .replace("__AVATAR__", AVATARS.get(name, ""))
                .replace("__NAME__", name)
                .replace("__COUNT__", str(len(lines)))
                .replace("__BUILD__", build)
                .replace("__DATA__", json.dumps(data, ensure_ascii=False)))
        path = os.path.join(outdir, name.replace(" ", "_") + ".html")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(html)
        print("%-14s %4d lines, %2d scene-runs -> %s"
              % (name, len(lines), len(runs), path))


if __name__ == "__main__":
    main()

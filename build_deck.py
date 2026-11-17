"""Build the public app's site, DramaDeck (dramadeck.app): deck_site/.

    python build_deck.py

The product is scan-your-own-in rehearsal for one person: import a script,
pick a part, practise. Its practice page and read-through are the cast
site's own (build_character_pages.TEMPLATE / READ_TEMPLATE), lifted at build
time so there is one source of truth, with everything that belongs to the
cast site alone taken off and the product's few own patches put on
(product(), below). Every surgery asserts: a template edit that moves the
furniture fails this build instead of quietly shipping lab gear.

private/deck/ holds the site's own sources (in the private repo: the shell is
the paid product, and this repo is public):
  shell.html       the app around the practice page: shelf, import, cast
  demo_plays.json  what the free demo is seeded with (Trifles, public domain)
  landing.html, privacy.html, terms.html
  vendor/          the import's libraries: pdf.js, Tesseract, its English data
These were RECOVERED from the live site on 2026-11-17: the folder they were
written in was never committed and is not on this PC. shell.html is the
live demo page with its two embedded practice pages, word list and demo
plays swapped for placeholders; Cloudflare's additions (bot trap, email
scrambling, challenge script) were taken off. They are the source now.
build_app.py and app/ are the August ancestor and are no longer what ships.

Out, in deck_site/ (not committed):
  index.html   the landing page
  demo.html    the shell with the demo plays; lines fill themselves, no mic
  <paid>/index.html  the shell with nothing seeded: the product, with its
               vendor/ beside it. The folder's name is the buyer's link, so
               it is not written here: it is read from
               private/deck_app_name.txt.
  privacy.html, terms.html

PUBLISHING. `wrangler pages deploy` replaces the WHOLE site: whatever is not
in deck_site/ is gone, the page buyers use included. The live site was 18
files on 2026-11-17 (the five pages and the 13 in vendor/) and this build
writes the same 18 at the same addresses. Publish from a copy outside this
folder (wrangler.toml here belongs to the cast site). A preview first:
    npx wrangler@4.120.1 pages deploy . --project-name dramadeck --branch preview
and the live site, on Chris's word only:
    npx wrangler@4.120.1 pages deploy . --project-name dramadeck --branch main
"""
import json
import os
import re
import shutil
import sys

from build_character_pages import READ_TEMPLATE, TEMPLATE, chime_b64

HERE = os.path.dirname(os.path.abspath(__file__))
DECK = os.path.join(HERE, "private", "deck")
OUT = os.path.join(HERE, "deck_site")

# Apple's novelty voices SING the line to a tune; the product alone met them
# (every imported character has no known gender, and the leftovers of the
# name lists on an iPhone were the singers). Carried over from the live
# product, where this fix was made.
NOVELTY = ('// iOS/macOS ship novelty voices through this same API, and several of\n'
           '// them SING the line to a tune. They are struck out first.\n'
           'const NOVELTY=/bad news|good news|bells|boing|bubbles|cellos|deranged|hysterical|jester|'
           'organ|pipe|superstar|trinoids|whisper|wobble|zarvox|bahh|albert|junior|kathy|ralph|princess/i;\n')

# The demo is a showcase, not a test (Chris, 2026-11-17: "a more marketing
# based demo ... just a demonstration of how when words are spoken they show
# up in green and it keeps going ... we know it works, they cant test it
# themselves so we show them what it looks like when its successful"). A
# voice says the visitor's line for them, the way "read my line" does, and
# each word turns green the moment it is spoken; then the line passes, the
# chime sounds and the play moves on. No mic is asked for. It is scored as a
# line said in full, so the run report at the end has something to show.
# Before this the line filled in silence at a fixed pace.
DEMOSAY = r'''function demoSay(l){
 my.textContent="In this demo a voice says your lines for you. In the real version they turn green as you say them, and you can call for one word at a time, or the full line.";
 const t=token,slots=[...stage.querySelectorAll("#diff .pending")];
 const live=()=>t===token&&running&&!paused&&judging;
 let lit=0,timer=0,told=false;
 const light=n=>{while(lit<Math.min(n,slots.length))slots[lit++].classList.add("lit");};
 const done=()=>{clearInterval(timer);if(!live())return;light(slots.length);
  setTimeout(()=>{if(live()){heard=l.say;if(RUN)RUN.mic=true;noteDone(l,"v");judged(l,l.say);}},220);};
 setTimeout(()=>{if(!live())return;
  ttsSpeak(l.say,1.15,NAME,done);
  const u=ttsKeep;
  const pace=()=>{if(timer)return;
   timer=setInterval(()=>{if(!live()){clearInterval(timer);return;}if(!told)light(lit+1);},
    340/((u&&u.rate)||1.15));};
  if(u){
   u.addEventListener("boundary",e=>{if(!live()||e.name==="sentence")return;told=true;
    light(norm(l.say.slice(0,e.charIndex)).split(" ").filter(w=>w).length+1);});
   u.addEventListener("start",pace);}
  setTimeout(()=>{if(live())pace();},1200);
 },300);
}
'''


# Sign-in build only: a quiet way out, for a shared computer. Goes into the
# paid page's shell just before it draws the shelf.
SIGNOUT = """fetch("/api/me").then(r=>r.json()).then(j=>{if(!j.in)return;
 const a=document.createElement("a");a.href="#";a.className="muted";
 a.style.cssText="display:block;margin-top:1.6rem;font-size:.8rem";
 a.textContent="Sign out of DramaDeck on this device";
 a.onclick=e=>{e.preventDefault();fetch("/api/signout",{method:"POST"}).then(()=>location.reload());};
 $("home").appendChild(a);}).catch(()=>{});
"""


def product(t, kind, demo=False, sync=False):
    """The cast site's page made into the product's: kind is "practice" or
    "read"; demo=True is the practice page of the free demo; sync=True is
    the sign-in build's, whose bests also go to the buyer's account."""
    def cut(frag, repl="", n=1):
        nonlocal t
        assert t.count(frag) == n, "expected %d of %.70r, found %d" % (n, frag, t.count(frag))
        t = t.replace(frag, repl)

    def sub(pattern, repl, flags=0):
        nonlocal t
        t, n = re.subn(pattern, lambda _m: repl, t, count=1, flags=flags)
        assert n == 1, "no match for %.70r" % pattern

    # ---- the cast site's own gear comes off ----
    # Real cast voices: the product has no rendered clips.
    sub(r"// ---- real cast voices.*?voxchk\.onchange=[^\n]*\n",
        "let VOX=new Set();const voxchk={checked:false};\n", re.S)
    sub(r'\s*<label id="voxwrap".*?</label>', "", re.S)
    if kind == "practice":
        # The bug-report button mails the cast site's owner.
        sub(r'\s*<a id="reportbtn".*?</a>', "", re.S)
        sub(r"// ---- error capture.*?What happened / what needs fixing:\\n\"\);};\n", "", re.S)
        t = re.sub(r"\s*#reportbtn(:hover)?\{[^}]*\}", "", t)
        # Session notes, mic logs and personal bests go to the cast site's
        # own server. The product has none and promises nothing leaves the
        # device: with this off no request is made, and the bests live in
        # the browser alone.
        cut('const TRACK=!/notrack/.test(location.hash)&&location.protocol!=="file:";',
            "const TRACK=false;")
        # The page lives in a frame with no address of its own, so what its
        # scores are filed under comes from its title (part and play).
        cut('const PAGEKEY=(location.pathname.split("/").pop()||"").split(".")[0]||NAME;',
            "const PAGEKEY=document.title;")
        cut('const key="rep:"+NAME+":"+scope.value+":"+mode.value;',
            'const key="rep:"+PAGEKEY+":"+scope.value+":"+mode.value;')
        if sync:
            # Signed in, the bests (and a log of finished runs) follow the
            # buyer: private/deck/_worker.js keeps them. Not signed in, the
            # store answers no and the browser's own copy carries on.
            cut('const BESTS_URL=TRACK?"/api/bests?page="+PAGEKEY:"";',
                'const BESTS_URL="/api/sync?page="+encodeURIComponent(PAGEKEY);')
        # No test links, and no separate copy of the script to fetch: Full
        # Script is rebuilt from the lines the page already holds.
        cut("const TESTS=__TESTS__;", "const TESTS={};")
        cut('const SCRIPT_URL="__SCRIPT__";', 'const SCRIPT_URL="data:,";')
        cut('const CHIME_MP3="__CHIME__"', 'const CHIME_MP3="%s"' % chime_b64())
    # Build stamp: meaningless for an imported play.
    sub(r'\s*<div id="build">[^<]*</div>', "")
    # The back button walks the app's own router instead of a URL.
    cut('<a id="backbtn" href="__HOME__">',
        '<a id="backbtn" href="#" onclick="parent.appBack();return false">')
    # The production's year note is a cast-site thing.
    cut("__YEARTAG__", "")

    # ---- the product's own patches go on ----
    cut("function pickVoice(p,who){\n"
        ' let vs=speechSynthesis.getVoices().filter(v=>v.lang&&v.lang.startsWith("en"));\n'
        " if(!vs.length)return null;\n",
        NOVELTY +
        "function pickVoice(p,who){\n"
        ' let vs=speechSynthesis.getVoices().filter(v=>v.lang&&v.lang.startsWith("en"));\n'
        " if(!vs.length)return null;\n"
        " {const sane=vs.filter(v=>!NOVELTY.test(v.name));if(sane.length)vs=sane;}\n")
    # A character with no known gender (every imported play) takes the
    # whole shelf of voices.
    cut(" let pool=vs.filter(v=>gender(v)===p.g);",
        ' let pool=p.g==="?"?vs:vs.filter(v=>gender(v)===p.g);')
    if demo:
        assert kind == "practice"
        # (the page writes the play arrow as a JS escape: backslash, u25B6)
        cut('my.textContent=rec?"":"No mic here: say it out loud anyway, then '
            + chr(92) + 'u25B6";', "demoSay(l);", n=2)
        cut("function initMic(){\n", DEMOSAY + "function initMic(){\n rec=null;return;\n")

    # ---- working notes stay home ----
    # The scripts carry our running commentary (who asked for what, when,
    # and why). Whole-line // comments are dropped from the product; code
    # with a trailing comment is left exactly as it is.
    def strip_notes(m):
        kept = [ln for ln in m.group(2).split("\n") if not ln.lstrip().startswith("//")]
        # A multi-line template literal could hold a line that only LOOKS
        # like a comment; there are none today, and this says so if one comes.
        assert "`" not in "\n".join(kept), "a template literal: check the comment stripper"
        return m.group(1) + "\n".join(kept) + m.group(3)
    t = re.sub(r"(<script>)(.*?)(</script>)", strip_notes, t, flags=re.S)

    for bad in ("voices/manifest.json", "reportbtn", "Tell Neil", "mailto:", "nexustechfl",
                "__HOME__", "__TESTS__", "__SCRIPT__", "__CHIME__", "__YEARTAG__", "Chris,"):
        assert bad not in t, "left in the %s page: %s" % (kind, bad)
    return t


def read(name):
    with open(os.path.join(DECK, name), encoding="utf-8") as fh:
        return fh.read()


def main():
    # --signin builds the version with sign-in by purchase and synced
    # scores (the worker, the sign-in page, the changed Privacy and Terms).
    # Without it the build is the site as it is live: files only.
    signin = "--signin" in sys.argv[1:]
    practice = product(TEMPLATE, "practice", sync=signin)
    practice_demo = product(TEMPLATE, "practice", demo=True)
    readthru = product(READ_TEMPLATE, "read")
    # "</" must not appear raw inside the host <script>: a literal
    # "</script>" inside an embedded page would end the app's own script.
    js_str = lambda s: json.dumps(s).replace("</", "<\\/")
    common = [w.strip() for w in open(os.path.join(HERE, "english10k.txt"), encoding="utf-8")
              if w.strip()]
    shell = read("shell.html")
    demo_plays = json.dumps(json.loads(read("demo_plays.json")), ensure_ascii=False).replace("</", "<\\/")

    def fill(page, demo, last=""):
        out = shell
        if last:
            nl = chr(10)
            tail = "renderShelf();" + nl + "</script></body></html>"
            assert out.rstrip().endswith(tail), "the shell no longer ends where it did"
            out = out.rstrip()[:-len(tail)] + last + tail + nl
        for ph, val in (("__PRACTICE_T__", js_str(page)), ("__READ_T__", js_str(readthru)),
                        ("__COMMON__", json.dumps(common)), ("__DEMO__", demo)):
            assert out.count(ph) == 1, ph
            out = out.replace(ph, val)
        return out

    name_file = os.path.join(HERE, "private", "deck_app_name.txt")
    paid = "app/index.html"
    if os.path.exists(name_file):
        paid = open(name_file, encoding="utf-8").read().strip() or paid
    # A folder of its own: the page finds its libraries in vendor/ beside it
    # (shell.html: new URL("vendor/", location.href)).
    assert re.fullmatch(r"[A-Za-z0-9_-]+/index\.html", paid), paid

    if os.path.isdir(OUT):
        shutil.rmtree(OUT)
    os.makedirs(os.path.join(OUT, os.path.dirname(paid)))
    # The import's libraries (pdf.js, Tesseract and its English data), kept
    # in the site itself so nothing is fetched from anyone else: 13 files,
    # recovered from the live site with the rest.
    vendor = os.path.join(DECK, "vendor")
    n = sum(len(fs) for _, _, fs in os.walk(vendor))
    assert n == 13, "private/deck/vendor should hold 13 files, found %d" % n
    shutil.copytree(vendor, os.path.join(OUT, os.path.dirname(paid), "vendor"))
    print("deck_site/<the paid page's folder>/vendor: %d files, %d MB" % (n, sum(
        os.path.getsize(os.path.join(d, f)) for d, _, fs in os.walk(vendor) for f in fs) // 2**20))
    pages = {
        "index.html": read("landing.html"),
        "privacy.html": read("privacy_signin.html" if signin else "privacy.html"),
        "terms.html": read("terms_signin.html" if signin else "terms.html"),
        "demo.html": fill(practice_demo, demo_plays),
        paid: fill(practice, "null", SIGNOUT if signin else ""),
    }
    if signin:
        pages["signin.html"] = read("signin.html")
        worker = read("_worker.js")
        assert worker.count('"/__PAID__/"') == 1
        pages["_worker.js"] = worker.replace("__PAID__", os.path.dirname(paid))
    for name, html in pages.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(html)
        shown = "<the paid page>" if name == paid else name
        print("deck_site/%-16s %4d KB" % (shown, len(html.encode("utf-8")) // 1024))
    print("practice page lifted from the cast site: %d KB (%d KB with our notes)"
          % (len(practice) // 1024, len(TEMPLATE) // 1024))
    print("SIGN-IN BUILD: needs the DECK store and its secrets, see private/deck/_worker.js"
          if signin else "plain build: the site as it is live")


if __name__ == "__main__":
    main()

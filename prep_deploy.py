"""Assemble the folder that gets uploaded to Cloudflare Pages.

Collects the freshly built character pages, adds a landing page for the
cast, and adds the headers that keep a licensed script out of search
engines. The whole folder is what you drag into Cloudflare's direct
upload. Nothing here is the deployment itself: the account, the upload
and the email gate stay in your hands, per DEPLOY.md alongside.

Usage:
    python prep_deploy.py private/handouts private/deploy
"""

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
 @media (max-width:720px){#cols{flex-direction:column}aside{width:100%;position:static;margin-top:1.2rem}}
</style></head><body>
<h1>&#127821; See How They Run — pick your character</h1>
<div class="intro">
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
</aside>
</div>
</body></html>
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

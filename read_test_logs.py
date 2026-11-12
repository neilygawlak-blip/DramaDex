"""Read what a test link sent back.

A test link (tests.json, <page>.html#test=<name>) logs what the ears did
and sends it to the site's store when Chris taps a result. This lists
those logs or prints one.

    python read_test_logs.py            list every test log, newest last
    python read_test_logs.py NAME       print the newest log of that test
    python read_test_logs.py NAME all   print every log of that test

Needs the same wrangler login as deploy.cmd.
"""
import json
import re
import subprocess
import sys

WRANGLER = "npx wrangler@4.120.1"


def namespace():
    with open("wrangler.toml", encoding="utf-8") as fh:
        return re.search(r'id\s*=\s*"([0-9a-f]+)"', fh.read()).group(1)


def run(args):
    out = subprocess.run("%s %s" % (WRANGLER, args), shell=True,
                         capture_output=True, text=True, encoding="utf-8")
    if out.returncode:
        sys.exit(out.stderr or out.stdout)
    return out.stdout


def main():
    ns = namespace()
    name = sys.argv[1] if len(sys.argv) > 1 else ""
    listing = run('kv key list --namespace-id %s --prefix "miclog/t-%s" --remote'
                  % (ns, name + "-" if name else ""))
    keys = sorted(k["name"] for k in json.loads(listing[listing.index("["):]))
    if not name:
        print("\n".join(keys) or "no test logs")
        return
    if not keys:
        print("no log for %r yet" % name)
        return
    for key in (keys if sys.argv[2:] == ["all"] else keys[-1:]):
        print("=====", key)
        print(run('kv key get "%s" --namespace-id %s --remote' % (key, ns)))


if __name__ == "__main__":
    main()

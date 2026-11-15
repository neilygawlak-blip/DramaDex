// Reads the two sweeps and lists the places where the recognizer wrote
// something else for a script word, the same way with both voices.
// Run from the DramaDex folder: node <this file> [min lines]
import fs from "node:fs";
import path from "node:path";

const ROOT = process.cwd();
const SITE = path.join(ROOT, "private", "deploy");
const load = f => { try { return JSON.parse(fs.readFileSync(path.join(ROOT, ".rig", f), "utf8")); } catch { return {}; } };
const A = load("sweep_david.json"), B = load("sweep_zira.json");

const norm = s => s.toLowerCase().replace(/[’‘]/g, "'").normalize("NFD").replace(/[̀-ͯ]/g, "")
  .replace(/[^a-z0-9' ]+/g, " ").replace(/\s+/g, " ").trim();
const bare = w => w.replace(/'/g, "");
const toks = s => norm(s || "").split(" ").filter(Boolean);

// the script's lines
const SAY = {};
for (const f of fs.readdirSync(SITE).filter(f => f.endsWith(".html"))) {
  const h = fs.readFileSync(path.join(SITE, f), "utf8");
  if (!h.includes("function doneEnough")) continue;
  const m = /const DATA=(\{.*?\});\s*\n/s.exec(h);
  if (!m) continue;
  const D = JSON.parse(m[1]), page = f.replace(".html", "");
  for (const l of D.lines) SAY[`${page}:${l.i}`] = l.say;
}

// align script words with heard words; give back each stretch of script
// words that has no equal in what was heard, with what stood in its place
function runs(E, H) {
  const n = E.length, m = H.length, eq = (a, b) => bare(a) === bare(b);
  const d = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = 0; i <= n; i++) d[i][0] = i;
  for (let j = 0; j <= m; j++) d[0][j] = j;
  for (let i = 1; i <= n; i++) for (let j = 1; j <= m; j++)
    d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (eq(E[i - 1], H[j - 1]) ? 0 : 1));
  const pair = new Array(n).fill(-1);          // script word -> heard word it equals
  let i = n, j = m;
  while (i > 0 && j > 0) {
    if (eq(E[i - 1], H[j - 1]) && d[i][j] === d[i - 1][j - 1]) { pair[i - 1] = j - 1; i--; j--; }
    else if (d[i][j] === d[i - 1][j - 1] + 1) { i--; j--; }
    else if (d[i][j] === d[i - 1][j] + 1) i--;
    else j--;
  }
  const out = [];
  for (let a = 0; a < n;) {
    if (pair[a] >= 0) { a++; continue; }
    let b = a; while (b < n && pair[b] < 0) b++;
    const left = a > 0 ? pair[a - 1] : -1;
    let right = m; for (let k = b; k < n; k++) if (pair[k] >= 0) { right = pair[k]; break; }
    out.push({ at: a, e: E.slice(a, b), h: H.slice(left + 1, right) });
    a = b;
  }
  return out;
}

const found = [];            // one per stretch both voices lost
let both = 0, onlyA = 0, emptyA = 0, emptyB = 0;
for (const [k, ra] of Object.entries(A)) {
  if (!ra.unlit || !ra.unlit.length) continue;
  if (!ra.text) { emptyA++; }
  const rb = B[k];
  if (!rb) continue;
  if (!rb.unlit.length) { onlyA++; continue; }
  if (!rb.text) emptyB++;
  both++;
  const say = SAY[k]; if (!say) continue;
  const E = toks(say);
  const ua = new Set(ra.unlit.map(w => bare(norm(w)))), ub = new Set(rb.unlit.map(w => bare(norm(w))));
  const Ra = runs(E, toks(ra.text)), Rb = runs(E, toks(rb.text));
  for (const x of Ra) {
    const y = Rb.find(y => y.at < x.at + x.e.length && x.at < y.at + y.e.length);
    if (!y) continue;
    // the script words in this stretch that the page left unlit with BOTH voices
    const lost = x.e.filter(w => ua.has(bare(w)) && ub.has(bare(w)) && y.e.includes(w));
    if (!lost.length) continue;
    found.push({ k, lost, e: x.e, ha: x.h, hb: y.h, same: x.h.join(" ") === y.h.join(" "), nothing: !ra.text || !rb.text, n: E.length });
  }
}

const MIN = +(process.argv[2] || 1);
const out = [];
out.push(`david: ${Object.keys(A).length} lines, zira: ${Object.keys(B).length} lines`);
out.push(`flagged by david: ${Object.values(A).filter(r => r.unlit && r.unlit.length).length}; zira also left a word unlit: ${both}; zira fine: ${onlyA}`);
out.push(`david wrote nothing: ${emptyA}; zira wrote nothing: ${emptyB}`);
out.push(`stretches both voices lost: ${found.length}; written the same by both: ${found.filter(f => f.same && f.ha.length).length}`);

// by the script stretch -> what was written
const group = (list, keyOf) => { const g = new Map(); for (const f of list) { const key = keyOf(f); if (!g.has(key)) g.set(key, []); g.get(key).push(f); } return [...g.entries()].sort((a, b) => b[1].length - a[1].length); };
const heard = f => f.same ? (f.ha.join(" ") || "(nothing)") : `${f.ha.join(" ") || "(nothing)"} | ${f.hb.join(" ") || "(nothing)"}`;
const real = found.filter(f => !f.nothing);

out.push("", "== A. several script words written as fewer words, the same by both voices (the head porter's kind) ==");
for (const [key, L] of group(real.filter(f => f.same && f.ha.length && f.e.length > f.ha.length && f.e.length >= 2), f => f.e.join(" ") + "  ->  " + f.ha.join(" ")))
  if (L.length >= MIN) out.push(`${String(L.length).padStart(3)}  ${key}    [${[...new Set(L.map(f => f.k))].slice(0, 6).join(", ")}]`);

out.push("", "== B. one script word written as something else, the same by both voices ==");
for (const [key, L] of group(real.filter(f => f.same && f.ha.length && !(f.e.length > f.ha.length && f.e.length >= 2)), f => f.e.join(" ") + "  ->  " + f.ha.join(" ")))
  if (L.length >= MIN) out.push(`${String(L.length).padStart(3)}  ${key}    [${[...new Set(L.map(f => f.k))].slice(0, 6).join(", ")}]`);

out.push("", "== C. lost by both voices but written differently (by lost word) ==");
for (const [key, L] of group(real.filter(f => !f.same || !f.ha.length).flatMap(f => f.lost.map(w => ({ ...f, w }))), f => f.w))
  if (L.length >= Math.max(2, MIN)) out.push(`${String(L.length).padStart(3)}  ${key}    e.g. ${[...new Set(L.map(heard))].slice(0, 4).join("  ;  ")}    [${[...new Set(L.map(f => f.k))].slice(0, 5).join(", ")}]`);

out.push("", "== D. every lost word, how many lines, both voices ==");
for (const [key, L] of group(real.flatMap(f => f.lost.map(w => ({ ...f, w }))), f => f.w))
  if (L.length >= 3) out.push(`${String(L.length).padStart(3)}  ${key}   pages ${[...new Set(L.map(f => f.k.split(":")[0]))].length}`);

fs.writeFileSync(path.join(ROOT, ".rig", "sweep_report.txt"), out.join("\n"));
fs.writeFileSync(path.join(ROOT, ".rig", "sweep_found.json"), JSON.stringify(found));
console.log(out.slice(0, 4).join("\n"));

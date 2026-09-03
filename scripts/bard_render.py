#!/usr/bin/env python3
"""bard_render.py — MEGA Crew saga renderer.
Drawn scene if art/out/issue-NNN/<id>.png|jpg|webp exists; else portraits.
Balloons sit UNDER the picture (artwell). Accepts jpg from generate_saga_scenes.py.
"""
import os, sys, json, html
from pathlib import Path

DISCORD_URL = "https://discord.gg/BTZZrG4MtV"
SITE = "https://mega.shanebrain.cloud"
SOCIAL_OG = "/art/out/social/social-og.png"
_ART_BASE = SITE.rstrip("/") + "/cards/portraits/"
CREW_ART = {
    "arc": "arc_Gemini_Generated.png", "blaze": "blaze_Gemini_Generated.png",
    "bolt": "bolt_Gemini_Generated.png", "crank": "crank_Gemini_Generated.png",
    "flux": "flux_Gemini_Generated.png", "forge": "forge_Gemini_Generate.png",
    "gemini_strategist": "gemini_Gemini_Generated.png", "glitch": "glitch_Gemini_Generated.png",
    "grind": "grind_Gemini_Generated.png", "neon": "neon_Gemini_Generated.png",
    "nukkels": "nukkels_Gemini_Generated.png", "rivet": "rivet_Gemini_Generated.png",
    "sparky": "sparky_Gemini_Generated.png", "spike": "spike_Gemini_Generated.png",
    "stomp": "stomp_Gemini_Generated.png", "torch": "torch_Gemini_Generated.png",
    "volt": "volt_Gemini_Generated.png", "weld": "weld_Gemini_Generated.png",
}
B_SIDE = {"shane", "claude"}
HOUSE_STYLE = ("detailed COMIC BOOK panel art, heavy bold black ink outlines, "
               "cinematic amber and cool blue lighting, wholesome all-ages, "
               "no text, no letters, no speech bubbles drawn, no watermark")
COVER_STYLE = HOUSE_STYLE.replace("panel art", "COVER art")

def _esc(s):
    return html.escape(s or "")

def _letter(s, n=18):
    words = (s or "").split()
    if len(words) <= n:
        return s or ""
    return " ".join(words[:n]).rstrip(",;:—-") + "."

def iter_pages(issue):
    g = 0
    for a in issue.get("acts", []) or []:
        for p in a.get("pages", []) or []:
            g += 1
            yield g, a, p

def art_id(issue_num, gpage, k):
    return f"i{issue_num:03d}-p{gpage:02d}-k{k}"

def panel_speakers(panel):
    out, seen = [], set()
    for d in panel.get("dialogue", []) or []:
        w = (d.get("who") or "").strip().lower()
        if w in CREW_ART and w not in seen:
            seen.add(w); out.append(w)
    return out

def _cover_img_url(issue_num, art_dir):
    if not art_dir:
        return None
    p = Path(art_dir).parent / "covers" / f"i{issue_num:03d}-cover.png"
    return f"/art/out/covers/i{issue_num:03d}-cover.png" if p.exists() else None

def _balloons_cell(pan, is_bottom=False):
    out = []
    for idx, d in enumerate(pan.get("dialogue", []) or []):
        who = (d.get("who") or "").strip()
        name = who.replace("gemini_strategist", "gemini").upper()
        side = "r" if idx % 2 else "l"
        out.append(f"<div class='cb {side}'><span class='nm'>{_esc(name)}</span>{_esc(_letter(d.get('line','')))}</div>")
        if len(out) >= 2:
            break
    cls = "balloons bottom" if is_bottom else "balloons"
    return f"<div class='{cls}'>{''.join(out)}</div>" if out else ""

def _find_art(art_dir, pid, art_url):
    if not art_dir:
        return None
    for ext in (".png", ".jpg", ".webp"):
        if os.path.exists(os.path.join(art_dir, pid + ext)):
            return f"{art_url}/{pid}{ext}"
    return None

def _cell(pan, gpage, k, issue_num, art_dir, art_url, prompts_map=None):
    pid = art_id(issue_num, gpage, k)
    landed = _find_art(art_dir, pid, art_url)
    if landed:
        img = f"<img class='cellimg' loading='lazy' src='{landed}' alt=''>"
    else:
        sp = panel_speakers(pan)
        if sp:
            img = f"<img class='cellimg' loading='lazy' src='{_ART_BASE}{CREW_ART[sp[0]]}' alt=''>"
        else:
            whos = []
            for d in pan.get("dialogue") or []:
                w = (d.get("who") or "").strip().lower()
                if w and w not in whos:
                    whos.append(w)
            chips = "".join(f"<span class='av chip {_esc(w)}'>{_esc((w[:1] or '?').upper())}</span>" for w in (whos[:2] or ["?"]))
            hint = _esc((pan.get("art") or "no art yet")[:80])
            img = f"<div class='cellimg noimg bside'>{chips}<i>{hint}</i></div>"
    cap = f"<div class='capbox'>{_esc(pan['caption'])}</div>" if pan.get("caption") else ""
    return f"<div class='cell'><div class='artwell'>{img}</div>{_balloons_cell(pan)}{cap}</div>"

_CSS = """
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:#070809;color:#e8e6e1;font-family:Georgia,serif;overflow:hidden}
#stage{position:fixed;inset:0;display:flex;align-items:center;justify-content:center;perspective:2000px}
.leaf{position:absolute;inset:0;display:flex;flex-direction:column;overflow-y:auto;padding:52px 22px 96px;max-width:900px;margin:0 auto;left:0;right:0;opacity:0;visibility:hidden;pointer-events:none}
.leaf.on{opacity:1;visibility:visible;pointer-events:auto}
.kicker{color:#7fb0d6;letter-spacing:.22em;text-transform:uppercase;font-size:12px;font-family:Menlo,monospace}
.cover{justify-content:center;text-align:center}
.cover h1{font-size:46px;color:#f4c87a;line-height:1.06}
.cover .tagline{color:#b9b4aa;font-style:italic;font-size:20px}
.cover .logline{color:#cfcabf;max-width:560px;margin:22px auto 0}
.cover .hint{color:#5f656c;font-family:Menlo,monospace;font-size:12px;margin-top:42px}
.act-leaf{justify-content:center;text-align:center}
.act-leaf h2{color:#f4c87a;font-size:38px}
.leaf.comicpage{justify-content:flex-start;align-items:stretch;padding:8px 10px 70px;overflow-y:auto}
.narrbar{max-width:720px;width:100%;margin:0 auto 8px;background:#1c160a;border:1px solid #4a3c18;color:#f0d9a8;font-style:italic;font-size:13px;padding:6px 10px;border-radius:6px;text-align:center}
.sheet{display:flex;flex-direction:column;gap:14px;margin:0 auto;width:100%;max-width:720px}
.cell{overflow:visible;background:#0d1115;border:3px solid #1c232c;border-radius:8px;display:flex;flex-direction:column}
.artwell{width:100%;aspect-ratio:4/3;background:#07090c;overflow:hidden}
.cellimg{width:100%;height:100%;object-fit:contain;object-position:center bottom;display:block}
.cellimg.noimg.bside{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:10px;padding:16px;color:#9aa6b2;text-align:center;height:100%}
.balloons{display:flex;flex-direction:column;gap:6px;padding:8px 10px 10px}
.cb{align-self:flex-start;max-width:92%;background:#fffdf8;color:#10131a;border:2px solid #0a0c10;border-radius:14px;padding:7px 10px;font-family:'Comic Neue','Trebuchet MS',sans-serif;font-size:16px;line-height:1.25;box-shadow:2px 3px 0 #0008}
.cb.r{align-self:flex-end}
.cb .nm{display:block;font-weight:700;font-size:.75em;letter-spacing:.04em;color:#b4690a;text-transform:uppercase}
.capbox{background:#1c160a;border-top:1px solid #4a3c18;color:#f0d9a8;font-size:12px;padding:6px 10px}
.pagebadge{align-self:flex-end;color:#cfcabf;background:#000a;font-family:Menlo,monospace;font-size:11px;padding:2px 8px;border-radius:7px}
.endcard{justify-content:center;text-align:center}
.endcard .box{padding:22px;border-radius:12px;margin:12px auto;max-width:600px}
.lesson{background:#0d1510;border:1px solid #1f3a27;color:#bfe6c8}
.prelude{background:#15110a;border:1px solid #3a2f17;color:#f0d9a8}
.tobe{color:#f4c87a;font-size:26px;margin:18px 0}
.discord{display:inline-block;margin-top:10px;background:#5865F2;color:#fff;text-decoration:none;font-family:Menlo,monospace;font-size:14px;padding:13px 20px;border-radius:11px}
#nav{position:fixed;left:0;right:0;bottom:0;height:54px;display:flex;align-items:center;justify-content:center;gap:18px;background:#0b0d10ee;border-top:1px solid #1d232a;font-family:Menlo,monospace;font-size:13px;z-index:10}
#nav button{background:#161b21;color:#e8e6e1;border:1px solid #2a3138;border-radius:8px;padding:8px 16px}
.zone{position:fixed;top:0;bottom:54px;width:22%;z-index:5}
.zone.l{left:0}.zone.r{right:0}
.av.chip{display:flex;align-items:center;justify-content:center;width:58px;height:58px;border-radius:50%;border:2px solid #2f3742}
.av.chip.shane{background:#1a1206;border-color:#5a4318;color:#f4c87a}
.av.chip.claude{background:#0a1018;border-color:#25435e;color:#9fd0f0}
"""

_JS = """
const leaves=[...document.querySelectorAll('.leaf')];let i=0;
function show(n){i=Math.max(0,Math.min(leaves.length-1,n));
 leaves.forEach((l,k)=>{l.classList.toggle('on',k===i);});
 document.getElementById('counter').textContent=(i+1)+' / '+leaves.length;
 document.getElementById('prev').disabled=i===0;
 document.getElementById('next').disabled=i===leaves.length-1;
 leaves[i].scrollTop=0;}
document.getElementById('next').onclick=()=>show(i+1);
document.getElementById('prev').onclick=()=>show(i-1);
document.querySelector('.zone.r').onclick=()=>show(i+1);
document.querySelector('.zone.l').onclick=()=>show(i-1);
addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key===' ')show(i+1);if(e.key==='ArrowLeft')show(i-1);});
show(0);
"""

def render_html(issue, issue_num, art_dir=None, art_url="", prompts_map=None):
    cover_img = _cover_img_url(issue_num, art_dir)
    cover_leaf = (
        f"<section class='leaf cover'><div class='kicker'>MEGA Crew · The Saga · Issue #{issue_num:03d}</div>"
        f"<h1>{_esc(issue.get('issue_title',''))}</h1>"
        f"<div class='tagline'>{_esc(issue.get('tagline',''))}</div>"
        f"<div class='logline'>{_esc(issue.get('logline',''))}</div>"
        f"<div class='hint'>→ / space / tap right to turn the page</div></section>")
    leaves = [cover_leaf]
    last_act = None
    for g, a, p in iter_pages(issue):
        if a is not last_act:
            last_act = a
            leaves.append(f"<section class='leaf act-leaf'><div class='kicker'>{_esc(a.get('act',''))}</div><h2>{_esc(a.get('title',''))}</h2></section>")
        cells = "".join(_cell(pan, g, k, issue_num, art_dir, art_url, prompts_map) for k, pan in enumerate(p.get("panels") or [], 1))
        narr = f"<div class='narrbar'>{_esc(_letter(p['narration'], 22))}</div>" if p.get("narration") else ""
        leaves.append(f"<section class='leaf comicpage'>{narr}<div class='sheet'>{cells}<div class='pagebadge'>PAGE {p.get('page','')}</div></div></section>")
    if issue.get("lesson"):
        leaves.append(f"<section class='leaf endcard'><div class='box lesson'><b>What this issue is really about</b><br><br>{_esc(issue['lesson'])}</div></section>")
    leaves.append(f"<section class='leaf endcard'><div class='box prelude'><b>Next issue —</b><br><br>{_esc(issue.get('prelude',''))}</div><div class='tobe'>… to be continued.</div></section>")
    og = SITE + (cover_img or SOCIAL_OG)
    return ("<!doctype html><html lang='en'><head><meta charset='utf-8'>"
            "<meta name='viewport' content='width=device-width,initial-scale=1'>"
            "<link rel='stylesheet' href='https://fonts.googleapis.com/css2?family=Comic+Neue:wght@700&display=swap'>"
            f"<title>MEGA Crew — Issue #{issue_num}: {_esc(issue.get('issue_title',''))}</title>"
            f"<meta property='og:image' content='{og}'><style>{_CSS}</style></head><body>"
            "<div class='zone l'></div><div class='zone r'></div>"
            f"<div id='stage'>{''.join(leaves)}</div>"
            "<div id='nav'><button id='prev'>‹ Prev</button><span id='counter'></span><button id='next'>Next ›</button></div>"
            f"<script>{_JS}</script></body></html>")

def main():
    if len(sys.argv) < 2:
        print("usage: bard_render.py <issue.json> [out.html]"); sys.exit(1)
    src = Path(sys.argv[1])
    issue = json.loads(src.read_text(encoding="utf-8"))
    num = 1
    for part in src.stem.replace("issue", " ").replace("-", " ").split():
        if part.isdigit():
            num = int(part); break
    repo = src.parent.parent
    art_dir = repo / "art" / "out" / f"issue-{num:03d}"
    art_url = f"/art/out/issue-{num:03d}"
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".html")
    out.write_text(render_html(issue, num, str(art_dir), art_url), encoding="utf-8")
    n = sum(1 for _ in art_dir.glob("*.*")) if art_dir.exists() else 0
    print(f"rendered -> {out} ({num}) | frames: {n}")

if __name__ == "__main__":
    main()

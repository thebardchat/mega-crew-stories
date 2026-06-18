#!/usr/bin/env python3
"""
bard_render.py — page-TURNING comic renderer for The Bard / MEGA Crew saga.

LANE A art + speech bubbles: every line of dialogue is a comic SPEECH BALLOON
spoken by that bot's REAL canonical face (from cards/portraits/, served live).
The crew always looks like themselves and images never fail to load (static
PNGs). Shane/Claude speak as styled chips. Scene description is kept above the
bubbles so it reads like a story.

The "to be continued" end card carries a Discord call-to-action when DISCORD_URL
is set.

Usage:
  python3 scripts/bard_render.py saga/issue-002.json            # -> saga/issue-002.html
  python3 scripts/bard_render.py saga/issue-002.json out.html
"""
import sys
import json
import html
from datetime import datetime, timezone
from pathlib import Path

# Set this to the server's Discord invite to light up the end-card CTA.
DISCORD_URL = "https://discord.gg/BTZZrG4MtV"

_ART_BASE = "/cards/portraits/"
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


def _esc(s):
    return html.escape(s or "")


def _avatar(who: str) -> str:
    w = (who or "").strip().lower()
    name = w.replace("gemini_strategist", "gemini").upper()
    if w in CREW_ART:
        return f"<img class='av' loading='lazy' src='{_ART_BASE}{CREW_ART[w]}' alt='{_esc(name)}'>"
    if w in B_SIDE:
        return f"<span class='av chip {w}'>{_esc(name[:1])}</span>"
    return f"<span class='av chip other'>{_esc(name[:1] or '?')}</span>"


def _panels_html(panels):
    out = []
    for pan in panels or []:
        out.append("<div class='panel'>")
        if pan.get("art"):  # scene description, reads like story
            out.append(f"<div class='art'>{_esc(pan['art'])}</div>")
        if pan.get("caption"):
            out.append(f"<div class='cap'>{_esc(pan['caption'])}</div>")
        for d in pan.get("dialogue", []) or []:
            who = (d.get("who") or "").strip()
            name = who.replace("gemini_strategist", "gemini").upper()
            side = "right" if who.strip().lower() in B_SIDE else "left"
            out.append(
                f"<div class='bubble {side}'>{_avatar(who)}"
                f"<div class='balloon'><span class='nm'>{_esc(name)}</span>"
                f"{_esc(d.get('line',''))}</div></div>")
        out.append("</div>")
    return "".join(out)


_CSS = """
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:#070809;color:#e8e6e1;font-family:Georgia,'Times New Roman',serif;line-height:1.6;overflow:hidden}
#stage{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}
.leaf{position:absolute;inset:0;display:none;flex-direction:column;overflow-y:auto;padding:52px 22px 96px;max-width:900px;margin:0 auto;left:0;right:0;animation:turn .32s ease}
.leaf.on{display:flex}
@keyframes turn{from{opacity:0;transform:translateX(26px) rotateY(6deg)}to{opacity:1;transform:none}}
.kicker{color:#7fb0d6;letter-spacing:.22em;text-transform:uppercase;font-size:12px;font-family:Menlo,monospace}
.cover{justify-content:center;text-align:center}
.cover h1{font-size:46px;color:#f4c87a;line-height:1.06;margin:.2em 0}
.cover .tagline{color:#b9b4aa;font-style:italic;font-size:20px}
.cover .logline{color:#cfcabf;max-width:560px;margin:22px auto 0}
.cover .hint{color:#5f656c;font-family:Menlo,monospace;font-size:12px;margin-top:42px}
.act-leaf{justify-content:center;text-align:center}
.act-leaf .act-kind{color:#7fb0d6;letter-spacing:.2em;text-transform:uppercase;font-family:Menlo,monospace;font-size:13px}
.act-leaf h2{color:#f4c87a;font-size:38px;margin:.25em 0}
.page-no{color:#6b7178;font-family:Menlo,monospace;font-size:11px;letter-spacing:.12em}
.setting{color:#9fb6c6;font-style:italic;font-size:13px;margin-top:4px}
.narr{color:#dcd8cf;margin:12px 0 6px;font-size:17px}
.panel{background:#11151a;border:1px solid #222831;border-radius:9px;padding:13px 15px;margin:11px 0}
.art{color:#9fb6c6;font-style:italic;font-size:14px;margin-bottom:8px}
.cap{color:#d7d3ca;margin-bottom:8px}
.bubble{display:flex;gap:11px;align-items:flex-start;margin:9px 0;max-width:680px}
.bubble.right{flex-direction:row-reverse;margin-left:auto}
.av{width:58px;height:58px;border-radius:50%;object-fit:cover;border:2px solid #2f3742;background:#0d1115;flex:none}
.av.chip{display:flex;align-items:center;justify-content:center;font-family:Menlo,monospace;font-weight:bold;font-size:18px}
.av.chip.shane{background:#1a1206;border-color:#5a4318;color:#f4c87a}
.av.chip.claude{background:#0a1018;border-color:#25435e;color:#9fd0f0}
.av.chip.other{background:#15191f;border-color:#2f3742;color:#9aa6b2}
.balloon{position:relative;background:#f4f0e7;color:#15171a;border-radius:15px;padding:9px 14px;font-family:'Trebuchet MS','Segoe UI',sans-serif;font-size:15px;line-height:1.45;box-shadow:0 1px 0 #0006}
.balloon .nm{display:block;font-size:11px;font-weight:bold;color:#9a6a12;text-transform:uppercase;letter-spacing:.05em;margin-bottom:2px}
.bubble.left .balloon:before{content:'';position:absolute;left:-8px;top:18px;border:7px solid transparent;border-right-color:#f4f0e7}
.bubble.right .balloon:before{content:'';position:absolute;right:-8px;top:18px;border:7px solid transparent;border-left-color:#f4f0e7}
.endcard{justify-content:center;text-align:center}
.endcard .box{padding:22px;border-radius:12px;margin:12px auto;max-width:600px}
.lesson{background:#0d1510;border:1px solid #1f3a27;color:#bfe6c8}
.prelude{background:#15110a;border:1px solid #3a2f17;color:#f0d9a8}
.tobe{color:#f4c87a;font-size:26px;margin:18px 0}
.discord{display:inline-block;margin-top:10px;background:#5865F2;color:#fff;text-decoration:none;font-family:Menlo,monospace;font-size:14px;padding:13px 20px;border-radius:11px}
.discord:hover{background:#4752c4}
.discord small{display:block;opacity:.85;font-size:11px;margin-top:3px}
#nav{position:fixed;left:0;right:0;bottom:0;height:54px;display:flex;align-items:center;justify-content:center;gap:18px;background:#0b0d10ee;border-top:1px solid #1d232a;font-family:Menlo,monospace;font-size:13px;z-index:10}
#nav button{background:#161b21;color:#e8e6e1;border:1px solid #2a3138;border-radius:8px;padding:8px 16px;cursor:pointer;font-family:inherit;font-size:13px}
#nav button:hover{background:#1e252d;color:#f4c87a}
#nav button:disabled{opacity:.3;cursor:default}
#counter{color:#8b9198;min-width:96px;text-align:center}
.zone{position:fixed;top:0;bottom:54px;width:22%;z-index:5;cursor:pointer}
.zone.l{left:0}.zone.r{right:0}
"""

_JS = """
const leaves=[...document.querySelectorAll('.leaf')];let i=0;
function show(n){i=Math.max(0,Math.min(leaves.length-1,n));
 leaves.forEach((l,k)=>l.classList.toggle('on',k===i));
 const t=leaves[i];t.style.animation='none';t.offsetHeight;t.style.animation='';
 document.getElementById('counter').textContent=(i+1)+' / '+leaves.length;
 document.getElementById('prev').disabled=i===0;
 document.getElementById('next').disabled=i===leaves.length-1;
 t.scrollTop=0;}
document.getElementById('next').onclick=()=>show(i+1);
document.getElementById('prev').onclick=()=>show(i-1);
document.querySelector('.zone.r').onclick=()=>show(i+1);
document.querySelector('.zone.l').onclick=()=>show(i-1);
addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key===' ')show(i+1);if(e.key==='ArrowLeft')show(i-1);});
show(0);
"""


def render_html(issue: dict, issue_num: int) -> str:
    leaves = [
        f"<section class='leaf cover'><div class='kicker'>MEGA Crew · The Saga · "
        f"Issue #{issue_num:03d}</div><h1>{_esc(issue.get('issue_title',''))}</h1>"
        f"<div class='tagline'>{_esc(issue.get('tagline',''))}</div>"
        f"<div class='logline'>{_esc(issue.get('logline',''))}</div>"
        f"<div class='hint'>→ / space / tap right to turn the page</div></section>"
    ]
    act_labels = {"Cold Open / Hook": "ACT ONE", "Core": "ACT TWO",
                  "Climax / Resolution": "ACT THREE", "Prelude": "ACT FOUR"}
    for a in issue.get("acts", []) or []:
        label = act_labels.get(a.get("act", ""), a.get("act", ""))
        leaves.append(
            f"<section class='leaf act-leaf'><div class='act-kind'>{label} · "
            f"{_esc(a.get('act',''))}</div><h2>{_esc(a.get('title',''))}</h2></section>")
        for p in a.get("pages", []) or []:
            body = [f"<div class='page-no'>{label} · PAGE {p.get('page','')}</div>"]
            if p.get("setting"):
                body.append(f"<div class='setting'>{_esc(p['setting'])}</div>")
            if p.get("narration"):
                body.append(f"<div class='narr'>{_esc(p['narration'])}</div>")
            body.append(_panels_html(p.get("panels", [])))
            leaves.append(f"<section class='leaf'>{''.join(body)}</section>")
    if issue.get("lesson"):
        leaves.append(
            f"<section class='leaf endcard'><div class='box lesson'>"
            f"<b>What this issue is really about</b><br><br>{_esc(issue['lesson'])}</div></section>")
    cta = (f"<a class='discord' href='{_esc(DISCORD_URL)}' target='_blank' rel='noopener'>"
           f"Come help guide the MEGA bots → "
           f"<small>jump in our Discord and talk with them — your words shape the crew</small></a>"
           ) if DISCORD_URL else ""
    leaves.append(
        f"<section class='leaf endcard'><div class='box prelude'><b>Next issue —</b><br><br>"
        f"{_esc(issue.get('prelude',''))}</div><div class='tobe'>… to be continued.</div>{cta}</section>")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>MEGA Crew — Issue #{issue_num}: {_esc(issue.get('issue_title',''))}</title>"
        f"<style>{_CSS}</style></head><body>"
        "<div class='zone l'></div><div class='zone r'></div>"
        f"<div id='stage'>{''.join(leaves)}</div>"
        "<div id='nav'><button id='prev'>‹ Prev</button>"
        "<span id='counter'></span><button id='next'>Next ›</button></div>"
        f"<!-- The Bard · generated {stamp} -->"
        f"<script>{_JS}</script></body></html>")


def main():
    if len(sys.argv) < 2:
        print("usage: bard_render.py <issue.json> [out.html]")
        sys.exit(1)
    src = Path(sys.argv[1])
    issue = json.loads(src.read_text(encoding="utf-8"))
    num = 1
    for part in src.stem.replace("issue", " ").replace("-", " ").split():
        if part.isdigit():
            num = int(part)
            break
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".html")
    out.write_text(render_html(issue, num), encoding="utf-8")
    print(f"rendered -> {out} ({num})")


if __name__ == "__main__":
    main()

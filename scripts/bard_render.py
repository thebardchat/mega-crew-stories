#!/usr/bin/env python3
"""
bard_render.py — page-TURNING comic renderer for The Bard / MEGA Crew saga.

Two art modes, chosen PER PANEL automatically:
  • DRAWN  — if art/out/issue-NNN/<panel-id>.png exists (rendered by Antigravity /
             Nano Banana Pro on pulsar), show that drawn scene with the dialogue
             as comic speech bubbles overlaid in the scene.
  • LANE A — otherwise, fall back to the speaking bots' real canonical portraits
             (cards/portraits/) + speech bubbles. Always available, never breaks.
So an issue publishes instantly (portraits) and self-upgrades to drawn art the
moment the images land — it can never end up blank.

Also exposes build_art_queue(issue, n, colors) -> the per-panel work orders the
render farm consumes (art/queue/issue-NNN.jsonl). The panel-ID scheme lives here
so the queue builder and the renderer agree by construction.

Usage:
  python3 scripts/bard_render.py saga/issue-002.json            # render (auto art lookup)
  python3 scripts/bard_render.py saga/issue-002.json out.html
"""
import os
import sys
import json
import html
from datetime import datetime, timezone
from pathlib import Path

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

# Locked house style appended to every render-farm prompt — DETAILED COMIC-MECHA
# (the look of the Bolt panel). Same string every panel = one cohesive book.
HOUSE_STYLE = ("detailed COMIC BOOK panel art, gritty semi-realistic robot/mecha rendering, "
               "heavy bold black ink outlines, dramatic cross-hatching and halftone shading, "
               "cinematic moody industrial lighting with warm amber and cool blue accents, "
               "dynamic camera angle, strong sense of motion and depth, wholesome all-ages, "
               "consistent house art style across every panel, "
               "keep the main characters and faces in the lower two-thirds of the frame, "
               "leave a clean uncluttered band across the TOP for speech balloons, "
               "no text, no letters, no speech bubbles drawn, no watermark")

# Cover style — same DNA as HOUSE_STYLE but an epic full composition (no bubble
# gutter); the issue title is overlaid as HTML, so still NO drawn text.
COVER_STYLE = ("detailed COMIC BOOK COVER art, gritty semi-realistic robot/mecha rendering, "
               "heavy bold black ink outlines, dramatic cross-hatching and halftone shading, "
               "cinematic moody industrial lighting with warm amber and cool blue accents, "
               "epic heroic dynamic composition, strong sense of depth and scale, wholesome "
               "all-ages, consistent with the interior house art style, leave clean empty "
               "space at the very top for a title logo, "
               "no text, no letters, no title drawn, no watermark")


def _esc(s):
    return html.escape(s or "")


# ── Panel addressing (shared by queue-builder and renderer) ─────────────────────
def iter_pages(issue):
    """Yield (global_page_number, act, page) across all acts, in order."""
    g = 0
    for a in issue.get("acts", []) or []:
        for p in a.get("pages", []) or []:
            g += 1
            yield g, a, p


def art_id(issue_num, gpage, k):
    return f"i{issue_num:03d}-p{gpage:02d}-k{k}"


def panel_speakers(panel):
    """Ordered unique crew bots speaking in this panel (in CREW_ART)."""
    out, seen = [], set()
    for d in panel.get("dialogue", []) or []:
        w = (d.get("who") or "").strip().lower()
        if w in CREW_ART and w not in seen:
            seen.add(w)
            out.append(w)
    return out


# ── Render-farm work orders ─────────────────────────────────────────────────────
def build_art_queue(issue, issue_num, colors=None):
    """Return a list of per-panel work orders for the Antigravity render farm."""
    colors = colors or {}
    rel_base = _ART_BASE.strip("/")  # "cards/portraits"
    orders = []
    for g, a, p in iter_pages(issue):
        for k, pan in enumerate(p.get("panels", []) or [], 1):
            bots = panel_speakers(pan)[:3]  # Nano Banana Pro takes up to 3 reference images
            # Trust the portrait for identity (colors/design); force the house style for the look.
            recipe = "  ".join(
                f"{r.replace('gemini_strategist','gemini').upper()} — match the supplied "
                f"reference image of {r} for its EXACT colors, markings and design, "
                f"but rendered in the detailed comic-book house style below."
                for r in bots)
            scene = (pan.get("art") or "").strip()
            prompt = f"{scene} {recipe} {HOUSE_STYLE}".strip()
            orders.append({
                "id": art_id(issue_num, g, k),
                "prompt": prompt,
                "refs": [f"{rel_base}/{CREW_ART[r]}" for r in bots],  # repo-relative portrait paths
                "w": 1248, "h": 832,
            })
    return orders


def build_cover_order(issue, issue_num, colors=None):
    """One hero-cover work order for the covers lane (art/queue/covers.jsonl ->
    art/out/covers/iNNN-cover.png). refs = the issue's 3 most-present crew bots."""
    counts = {}
    for g, a, p in iter_pages(issue):
        for pan in p.get("panels", []) or []:
            for b in panel_speakers(pan):
                counts[b] = counts.get(b, 0) + 1
    bots = sorted(counts, key=lambda b: -counts[b])[:3] or ["arc", "sparky", "glitch"]
    rel_base = _ART_BASE.strip("/")
    names = ", ".join(b.replace("gemini_strategist", "gemini").upper() for b in bots)
    title = (issue.get("issue_title") or issue.get("title") or "").strip()
    logline = (issue.get("logline") or issue.get("tagline") or "").strip()
    scene = (f"Comic book COVER illustration for MEGA Crew Issue #{issue_num:03d} "
             f"\"{title}\". A dramatic heroic full-cover composition of the MEGA crew of "
             f"robots assembled together as a team, featuring {names} in the foreground. "
             f"{logline} ")
    recipe = "  ".join(
        f"{b.replace('gemini_strategist','gemini').upper()} — match the supplied reference "
        f"image of {b} for its EXACT colors, markings and design." for b in bots)
    return {
        "id": f"i{issue_num:03d}-cover",
        "prompt": f"{scene}{recipe} {COVER_STYLE}".strip(),
        "refs": [f"{rel_base}/{CREW_ART[b]}" for b in bots],
        "w": 832, "h": 1248,
    }


def _cover_img_url(issue_num, art_dir):
    """Public URL of the drawn cover if it has landed, else None (text cover)."""
    if not art_dir:
        return None
    p = Path(art_dir).parent / "covers" / f"i{issue_num:03d}-cover.png"
    return f"/art/out/covers/i{issue_num:03d}-cover.png" if p.exists() else None


# ── Social / brand lane (art/queue/social.jsonl -> art/out/social/<id>.png) ──────
SOCIAL_STYLE = ("detailed comic-mecha brand KEY ART, gritty semi-realistic robot/mecha "
                "rendering, heavy bold black ink outlines, dramatic cross-hatching and "
                "halftone shading, cinematic warm-amber and cool-blue lighting, bold graphic "
                "poster/banner composition, strong depth, wholesome all-ages, consistent with "
                "the comic house style, leave clean negative space for a logo wordmark, "
                "no text, no letters, no watermark")
EMOTE_STYLE = ("bold punchy CHAT-EMOTE style: a single character bust centered on a clean flat "
               "vignette background, thick clean outlines, saturated and instantly readable at "
               "small size, semi-realistic robot/mecha rendering consistent with the comic "
               "house style, no text, no letters, no watermark")

# Static brand-asset set (not per-issue). Re-runnable: idempotent by id.
SOCIAL_ASSETS = [
    {"id": "social-og", "kind": "banner", "bots": ["arc", "sparky", "glitch"], "w": 1280, "h": 640,
     "scene": "Wide brand key-art banner for 'MEGA Crew' — a heroic ensemble of friendly "
              "robots assembled as a team in a cinematic group hero shot, the warm glow of a "
              "home server workshop behind them."},
    {"id": "social-twitch-banner", "kind": "banner", "bots": ["arc", "weld", "volt"], "w": 1200, "h": 480,
     "scene": "Ultra-wide Twitch channel banner for the MEGA Crew — robots side by side facing "
              "the viewer, dynamic and bold, room left on one side for a channel logo."},
    {"id": "social-discord-banner", "kind": "banner", "bots": ["glitch", "sparky", "nukkels"], "w": 960, "h": 540,
     "scene": "Discord community welcome banner for the MEGA Crew — an inviting, fun group shot "
              "of the robots gathered around with warm 'come join us' energy."},
    {"id": "social-emote-arc", "kind": "emote", "bots": ["arc"], "w": 512, "h": 512,
     "scene": "Chat-emote bust of ARC the gatekeeper robot, friendly confident expression, "
              "centered, simple readable silhouette."},
    {"id": "social-emote-glitch", "kind": "emote", "bots": ["glitch"], "w": 512, "h": 512,
     "scene": "Chat-emote bust of GLITCH the mischievous robot, sly grin and wink, centered, "
              "punchy readable silhouette."},
    {"id": "social-emote-sparky", "kind": "emote", "bots": ["sparky"], "w": 512, "h": 512,
     "scene": "Chat-emote bust of SPARKY the quality-judge robot, bright approving thumbs-up "
              "energy, centered, punchy readable silhouette."},
]


def build_social_orders(colors=None):
    """Return the brand/social work orders for the social lane."""
    rel_base = _ART_BASE.strip("/")
    orders = []
    for a in SOCIAL_ASSETS:
        bots = [b for b in a["bots"] if b in CREW_ART][:3]
        recipe = "  ".join(
            f"{b.replace('gemini_strategist','gemini').upper()} — match the supplied reference "
            f"image of {b} for its EXACT colors, markings and design." for b in bots)
        style = EMOTE_STYLE if a["kind"] == "emote" else SOCIAL_STYLE
        orders.append({
            "id": a["id"],
            "prompt": f"{a['scene']} {recipe} {style}".strip(),
            "refs": [f"{rel_base}/{CREW_ART[b]}" for b in bots],
            "w": a["w"], "h": a["h"],
        })
    return orders


# ── Per-panel HTML ───────────────────────────────────────────────────────────────
def _avatar(who):
    w = (who or "").strip().lower()
    name = w.replace("gemini_strategist", "gemini").upper()
    if w in CREW_ART:
        return f"<img class='av' loading='lazy' src='{_ART_BASE}{CREW_ART[w]}' alt='{_esc(name)}'>"
    if w in B_SIDE:
        return f"<span class='av chip {w}'>{_esc(name[:1])}</span>"
    return f"<span class='av chip other'>{_esc(name[:1] or '?')}</span>"


def _bubbles_inline(panel):
    out = []
    for d in panel.get("dialogue", []) or []:
        who = (d.get("who") or "").strip()
        name = who.replace("gemini_strategist", "gemini").upper()
        side = "right" if who.lower() in B_SIDE else "left"
        out.append(f"<div class='bubble {side}'>{_avatar(who)}<div class='balloon'>"
                   f"<span class='nm'>{_esc(name)}</span>{_esc(d.get('line',''))}</div></div>")
    return "".join(out)


def _panel_drawn(img_url, panel):
    """Drawn scene with dialogue overlaid as in-scene comic bubbles."""
    obs = []
    for i, d in enumerate(panel.get("dialogue", []) or []):
        name = (d.get("who") or "").replace("gemini_strategist", "gemini").upper()
        side = "r" if i % 2 else "l"
        obs.append(f"<div class='ob {side}'><span class='nm'>{_esc(name)}</span>"
                   f"{_esc(d.get('line',''))}</div>")
    cap = f"<div class='cap'>{_esc(panel['caption'])}</div>" if panel.get("caption") else ""
    return (f"<div class='panel drawn'><div class='scene'>"
            f"<img class='sceneimg' loading='lazy' src='{img_url}' alt=''>"
            f"<div class='obwrap'>{''.join(obs)}</div></div>{cap}</div>")


def _panel_laneA(panel):
    parts = ["<div class='panel'>"]
    if panel.get("art"):
        parts.append(f"<div class='art'>{_esc(panel['art'])}</div>")
    if panel.get("caption"):
        parts.append(f"<div class='cap'>{_esc(panel['caption'])}</div>")
    parts.append(_bubbles_inline(panel))
    parts.append("</div>")
    return "".join(parts)


def _panel_at(pan, gpage, k, issue_num, art_dir, art_url):
    """Render ONE panel (drawn if its art has landed, else lane-A portraits)."""
    pid = art_id(issue_num, gpage, k)
    if art_dir and os.path.exists(os.path.join(art_dir, pid + ".png")):
        return _panel_drawn(f"{art_url}/{pid}.png", pan)
    return _panel_laneA(pan)


def _panels_html(panels, gpage, issue_num, art_dir, art_url):
    return "".join(_panel_at(pan, gpage, k, issue_num, art_dir, art_url)
                   for k, pan in enumerate(panels or [], 1))


# ── Comic-page cells (multi-panel grid, top speech balloons) ─────────────────────
BOTTOM_PANELS = {
    "i001-p07-k4",
    "i001-p11-k1",
    "i001-p15-k4",
    "i001-p18-k3",
}


def _balloons_cell(pan, is_bottom=False):
    """Dialogue as comic speech balloons at the top (or bottom) of a panel cell."""
    out = []
    for idx, d in enumerate(pan.get("dialogue", []) or []):
        who = (d.get("who") or "").strip()
        name = who.replace("gemini_strategist", "gemini").upper()
        side = "r" if idx % 2 else "l"
        out.append(f"<div class='cb {side}'><span class='nm'>{_esc(name)}</span>"
                   f"{_esc(d.get('line', ''))}</div>")
    cls = "balloons bottom" if is_bottom else "balloons"
    return f"<div class='{cls}'>{''.join(out)}</div>" if out else ""


def _cell(pan, gpage, k, issue_num, art_dir, art_url, prompts_map=None):
    """One panel as a comic-grid cell: drawn art (or speaker portrait fallback)
    with speech balloons on top (or bottom) and an optional caption box."""
    pid = art_id(issue_num, gpage, k)
    if art_dir and os.path.exists(os.path.join(art_dir, pid + ".png")):
        img = f"<img class='cellimg' loading='lazy' src='{art_url}/{pid}.png' alt=''>"
    else:
        sp = panel_speakers(pan)
        if sp:
            img = f"<img class='cellimg' loading='lazy' src='{_ART_BASE}{CREW_ART[sp[0]]}' alt=''>"
        else:
            img = "<div class='cellimg noimg'></div>"
    
    prompt = prompts_map.get(pid, "") if prompts_map else ""
    is_bottom = pid in BOTTOM_PANELS or any(kw in prompt.lower() for kw in ["bottom", "lower third", "bottom third"])
    
    cap = f"<div class='capbox'>{_esc(pan['caption'])}</div>" if pan.get("caption") else ""
    return f"<div class='cell'>{img}{_balloons_cell(pan, is_bottom)}{cap}</div>"


_CSS = """
*{box-sizing:border-box}
html,body{margin:0;height:100%;background:#070809;color:#e8e6e1;font-family:Georgia,'Times New Roman',serif;line-height:1.6;overflow:hidden}
#stage{position:fixed;inset:0;display:flex;align-items:center;justify-content:center}
.leaf{position:absolute;inset:0;display:flex;flex-direction:column;overflow-y:auto;padding:52px 22px 96px;max-width:900px;margin:0 auto;left:0;right:0;opacity:0;visibility:hidden;pointer-events:none;transform-origin:left center;backface-visibility:hidden;transform-style:preserve-3d;transition:transform .75s cubic-bezier(0.2,0.8,0.2,1),opacity .75s ease,visibility .75s}
.leaf.on{opacity:1;visibility:visible;pointer-events:auto}
.kicker{color:#7fb0d6;letter-spacing:.22em;text-transform:uppercase;font-size:12px;font-family:Menlo,monospace}
.cover{justify-content:center;text-align:center}
.cover h1{font-size:46px;color:#f4c87a;line-height:1.06;margin:.2em 0}
.cover .tagline{color:#b9b4aa;font-style:italic;font-size:20px}
.cover .logline{color:#cfcabf;max-width:560px;margin:22px auto 0}
.cover .hint{color:#5f656c;font-family:Menlo,monospace;font-size:12px;margin-top:42px}
.cover.hero{position:relative;padding:0;justify-content:flex-end;text-align:center;overflow:hidden}
.cover.hero::before{content:'';position:absolute;inset:0;background:var(--cv) center/cover no-repeat;z-index:0}
.cover.hero .heroveil{position:absolute;inset:0;background:linear-gradient(to bottom,rgba(7,9,12,.12) 28%,rgba(7,9,12,.93) 100%);z-index:1}
.cover.hero .herotext{position:relative;z-index:2;padding:0 26px 58px}
.cover.hero h1{font-size:46px;color:#f4c87a;line-height:1.06;margin:.2em 0;text-shadow:0 2px 16px #000}
.cover.hero .tagline{color:#ece7dd;font-style:italic;font-size:20px;text-shadow:0 2px 12px #000}
.cover.hero .hint{color:#cfcabf;margin-top:30px}
.act-leaf{justify-content:center;text-align:center}
.act-leaf .act-kind{color:#7fb0d6;letter-spacing:.2em;text-transform:uppercase;font-family:Menlo,monospace;font-size:13px}
.act-leaf h2{color:#f4c87a;font-size:38px;margin:.25em 0}
.page-no{color:#6b7178;font-family:Menlo,monospace;font-size:11px;letter-spacing:.12em}
.setting{color:#9fb6c6;font-style:italic;font-size:13px;margin-top:4px}
.narr{color:#dcd8cf;margin:12px 0 6px;font-size:17px}
.panel{background:#11151a;border:1px solid #222831;border-radius:9px;padding:13px 15px;margin:11px 0}
.panel.drawn{padding:0;overflow:hidden;background:#0d1115}
.leaf.panelpage{justify-content:flex-start;padding:22px 20px 66px;overflow:hidden}
.panelpage .page-no,.panelpage .setting,.panelpage .narr{text-align:center;flex:0 0 auto}
.panelpage .narr{max-width:640px;margin:8px auto 0;font-size:15px}
.panelpage .panel{margin:10px auto 0;width:100%;max-width:760px}
.panelpage .panel.drawn{flex:1 1 auto;min-height:0;max-width:760px;border-radius:11px;display:flex;flex-direction:column}
.panelpage .scene{flex:1 1 auto;min-height:0;width:100%;position:relative}
.panelpage .sceneimg{width:100%;height:100%;object-fit:contain;object-position:center bottom}
.art{color:#9fb6c6;font-style:italic;font-size:14px;margin-bottom:8px}
.cap{color:#d7d3ca;padding:8px 14px}
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
.scene{position:relative;width:100%}
.sceneimg{width:100%;display:block}
.obwrap{position:absolute;left:0;right:0;bottom:0;top:auto;display:flex;flex-direction:column;
justify-content:flex-end;gap:6px;padding:14% 5% 4%;pointer-events:none;
background:linear-gradient(to top,rgba(8,9,12,.84) 0%,rgba(8,9,12,.8) 24%,rgba(8,9,12,.4) 42%,rgba(8,9,12,0) 60%)}
.ob{background:#fdfbf5;color:#15171a;border:2px solid #15171a;border-radius:14px;padding:6px 12px;font-family:'Trebuchet MS','Segoe UI',sans-serif;font-size:14px;line-height:1.3;max-width:78%;box-shadow:0 2px 6px #000a;align-self:flex-start}
.ob.r{align-self:flex-end}
.ob .nm{display:block;font-weight:bold;font-size:10px;color:#9a6a12;text-transform:uppercase;letter-spacing:.04em}
.endcard{justify-content:center;text-align:center}
.endcard .box{padding:22px;border-radius:12px;margin:12px auto;max-width:600px}
.lesson{background:#0d1510;border:1px solid #1f3a27;color:#bfe6c8}
.prelude{background:#15110a;border:1px solid #3a2f17;color:#f0d9a8}
.tobe{color:#f4c87a;font-size:26px;margin:18px 0}
.discord{display:inline-block;margin-top:10px;background:#5865F2;color:#fff;text-decoration:none;font-family:Menlo,monospace;font-size:14px;padding:13px 20px;border-radius:11px}
.discord:hover{background:#4752c4}
.discord small{display:block;opacity:.85;font-size:11px;margin-top:3px}
.credits{color:#8b9198;font-size:13px;line-height:1.7;max-width:560px;margin:0 auto;font-family:Menlo,monospace}
.credits b{color:#cdb98a}
#nav{position:fixed;left:0;right:0;bottom:0;height:54px;display:flex;align-items:center;justify-content:center;gap:18px;background:#0b0d10ee;border-top:1px solid #1d232a;font-family:Menlo,monospace;font-size:13px;z-index:10}
#nav button{background:#161b21;color:#e8e6e1;border:1px solid #2a3138;border-radius:8px;padding:8px 16px;cursor:pointer;font-family:inherit;font-size:13px}
#nav button:hover{background:#1e252d;color:#f4c87a}
#nav button:disabled{opacity:.3;cursor:default}
#counter{color:#8b9198;min-width:96px;text-align:center}
.zone{position:fixed;top:0;bottom:54px;width:22%;z-index:5;cursor:pointer}
.zone.l{left:0}.zone.r{right:0}
/* ── page-turn flip ── */
#stage{perspective:2000px;transform-style:preserve-3d}
.leaf.past{transform:rotateY(-120deg);opacity:0;visibility:hidden}
.leaf.on{transform:rotateY(0deg);opacity:1;visibility:visible;pointer-events:auto}
.leaf.future{transform:rotateY(120deg);opacity:0;visibility:hidden}
.leaf::after{content:'';position:absolute;inset:0;background:linear-gradient(to right,rgba(0,0,0,0.2) 0%,rgba(0,0,0,0) 12%);opacity:0;transition:opacity .75s ease;pointer-events:none;z-index:10}
.leaf.past::after{opacity:1}
/* ── full-bleed cover (blurred fill + whole cover sharp) ── */
.cover.hero::before{background:var(--cv) center/cover no-repeat;filter:blur(26px) brightness(.45);transform:scale(1.15)}
.cover.hero .heroart{position:absolute;inset:0;background:var(--cv) center/contain no-repeat;z-index:1}
.cover.hero .heroveil{background:linear-gradient(to bottom,rgba(7,9,12,0) 55%,rgba(7,9,12,.92) 100%)}
.cover.hero h1{font-size:clamp(30px,5vw,48px)}
.cover.hero .tagline{font-size:clamp(15px,2.4vw,21px)}
/* ── comic pages: multi-panel grid ── */
.leaf.comicpage{justify-content:center;align-items:center;padding:12px 12px 62px;overflow:hidden}
.narrbar{flex:0 0 auto;max-width:720px;margin:0 auto 8px;background:#1c160a;border:1px solid #4a3c18;color:#f0d9a8;font-style:italic;font-size:14px;line-height:1.35;padding:7px 13px;border-radius:6px;text-align:center}
.sheet{position:relative;display:grid;gap:7px;background:#05060a;padding:7px;border:1px solid #232a33;border-radius:8px;box-shadow:0 12px 46px #000b;margin:auto;width:auto;max-width:min(720px,95vw);max-height:calc(100vh - 84px);aspect-ratio:var(--ar,1)}
.cell{position:relative;overflow:hidden;background:#0d1115;border-radius:3px}
.cellimg{width:100%;height:100%;object-fit:cover;display:block}
.cellimg.noimg{background:repeating-linear-gradient(45deg,#11151a,#11151a 10px,#0d1115 10px,#0d1115 20px)}
.balloons{position:absolute;top:3.5%;left:4.5%;right:4.5%;display:flex;flex-direction:column;gap:5px;z-index:3;pointer-events:none}
.balloons.bottom{top:auto;bottom:3.5%}
.cb{position:relative;align-self:flex-start;max-width:84%;background:#fff;color:#10131a;border:2px solid #0a0c10;border-radius:13px;padding:3px 9px 4px;font-family:'Comic Neue','Trebuchet MS','Segoe UI',sans-serif;font-size:clamp(9px,1.5vmin,14px);line-height:1.16;box-shadow:1.5px 2.5px 0 rgba(0,0,0,.5)}
.cb.r{align-self:flex-end}
.cb .nm{display:block;font-weight:700;font-size:.72em;letter-spacing:.03em;color:#b4690a;text-transform:uppercase;margin-bottom:1px}
.cb:after{content:'';position:absolute;bottom:-8px;left:18px;width:0;height:0;border:7px solid transparent;border-top-color:#fff}
.cb.r:after{left:auto;right:18px}
.balloons.bottom .cb:after{bottom:auto;top:-8px;border-top-color:transparent;border-bottom-color:#fff}
.pagebadge{position:absolute;right:7px;bottom:5px;z-index:4;color:#cfcabf;background:#000a;font-family:Menlo,monospace;font-size:11px;padding:1px 7px;border-radius:7px}
.capbox{position:absolute;left:0;bottom:0;z-index:3;max-width:72%;background:#1c160a;border-top:2px solid #4a3c18;border-right:2px solid #4a3c18;color:#f0d9a8;font-size:clamp(8px,1.25vmin,12px);line-height:1.2;padding:3px 8px;border-radius:0 7px 0 3px}
"""

_JS = """
const leaves=[...document.querySelectorAll('.leaf')];let i=0;
function show(n,immediate=false){const tgt=Math.max(0,Math.min(leaves.length-1,n));
 if(tgt===i&&!immediate)return;
 const direction=tgt>=i?1:-1;const prevActive=i;i=tgt;
 leaves.forEach((l,k)=>{
  l.classList.toggle('past',k<i);
  l.classList.toggle('on',k===i);
  l.classList.toggle('future',k>i);
  if(immediate){l.style.transition='none'}else{l.style.transition=''}
  if(direction>0){
   if(k===prevActive)l.style.zIndex=5;
   else if(k===i)l.style.zIndex=4;
   else l.style.zIndex=1;
  }else{
   if(k===i)l.style.zIndex=5;
   else if(k===prevActive)l.style.zIndex=4;
   else l.style.zIndex=1;
  }
 });
 document.getElementById('counter').textContent=(i+1)+' / '+leaves.length;
 document.getElementById('prev').disabled=i===0;
 document.getElementById('next').disabled=i===leaves.length-1;
 leaves[i].scrollTop=0;}
document.getElementById('next').onclick=()=>show(i+1);
document.getElementById('prev').onclick=()=>show(i-1);
document.querySelector('.zone.r').onclick=()=>show(i+1);
document.querySelector('.zone.l').onclick=()=>show(i-1);
addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key===' ')show(i+1);if(e.key==='ArrowLeft')show(i-1);});
show(0,true);
"""

CREDITS_HTML = (
    "<b>CREDITS</b><br><br>"
    "Written by <b>Claude</b> (Anthropic).<br>"
    "Character &amp; panel art by Google <b>Nano Banana Pro</b> (Gemini 3 Pro Image) via Antigravity, "
    "from the MEGA Crew's own designs.<br>"
    "AI-assisted imagery — Google <b>SynthID</b> watermark retained.<br>"
    "The MEGA Crew lives on the <b>ShaneBrain</b> cluster — a Raspberry Pi 5 and a mesh of machines.<br><br>"
    "Built with Claude · Runs on a Raspberry Pi 5"
)


def render_html(issue, issue_num, art_dir=None, art_url="", prompts_map=None):
    cover_img = _cover_img_url(issue_num, art_dir)
    if cover_img:
        cover_leaf = (
            f"<section class='leaf cover hero' style=\"--cv:url('{cover_img}')\">"
            f"<div class='heroart'></div><div class='heroveil'></div><div class='herotext'>"
            f"<div class='kicker'>MEGA Crew · The Saga · Issue #{issue_num:03d}</div>"
            f"<h1>{_esc(issue.get('issue_title',''))}</h1>"
            f"<div class='tagline'>{_esc(issue.get('tagline',''))}</div>"
            f"<div class='hint'>→ / space / tap right to turn the page</div></div></section>")
    else:
        cover_leaf = (
            f"<section class='leaf cover'><div class='kicker'>MEGA Crew · The Saga · "
            f"Issue #{issue_num:03d}</div><h1>{_esc(issue.get('issue_title',''))}</h1>"
            f"<div class='tagline'>{_esc(issue.get('tagline',''))}</div>"
            f"<div class='logline'>{_esc(issue.get('logline',''))}</div>"
            f"<div class='hint'>→ / space / tap right to turn the page</div></section>")
    leaves = [cover_leaf]
    act_labels = {"Cold Open / Hook": "ACT ONE", "Core": "ACT TWO",
                  "Climax / Resolution": "ACT THREE", "Prelude": "ACT FOUR"}
    last_act = None
    for g, a, p in iter_pages(issue):
        if a is not last_act:
            last_act = a
            label = act_labels.get(a.get("act", ""), a.get("act", ""))
            leaves.append(
                f"<section class='leaf act-leaf'><div class='act-kind'>{label} · "
                f"{_esc(a.get('act',''))}</div><h2>{_esc(a.get('title',''))}</h2></section>")
        panels = p.get("panels", []) or []
        n = len(panels)
        cols = 1 if n <= 1 else (3 if n > 4 else 2)
        rows = (-(-n // cols)) or 1
        ar = round(cols / rows, 3)
        cells = "".join(_cell(pan, g, k, issue_num, art_dir, art_url, prompts_map)
                        for k, pan in enumerate(panels, 1))
        narr = (f"<div class='narrbar'>{_esc(p['narration'])}</div>"
                if p.get("narration") else "")
        sheet = (f"<div class='sheet' style='--ar:{ar};"
                 f"grid-template-columns:repeat({cols},1fr)'>{cells}"
                 f"<div class='pagebadge'>PAGE {p.get('page','')}</div></div>")
        leaves.append(f"<section class='leaf comicpage'>{narr}{sheet}</section>")
    if issue.get("lesson"):
        leaves.append(
            f"<section class='leaf endcard'><div class='box lesson'>"
            f"<b>What this issue is really about</b><br><br>{_esc(issue['lesson'])}</div></section>")
    cta = (f"<a class='discord' href='{_esc(DISCORD_URL)}' target='_blank' rel='noopener'>"
           f"Come help guide the MEGA bots → <small>jump in our Discord and talk with them — "
           f"your words shape the crew</small></a>") if DISCORD_URL else ""
    leaves.append(
        f"<section class='leaf endcard'><div class='box prelude'><b>Next issue —</b><br><br>"
        f"{_esc(issue.get('prelude',''))}</div><div class='tobe'>… to be continued.</div>{cta}</section>")
    leaves.append(f"<section class='leaf endcard'><div class='credits'>{CREDITS_HTML}</div></section>")

    return (
        "<!doctype html><html lang='en'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width,initial-scale=1'>"
        f"<title>MEGA Crew — Issue #{issue_num}: {_esc(issue.get('issue_title',''))}</title>"
        f"<style>{_CSS}</style></head><body>"
        "<div class='zone l'></div><div class='zone r'></div>"
        f"<div id='stage'>{''.join(leaves)}</div>"
        "<div id='nav'><button id='prev'>‹ Prev</button>"
        "<span id='counter'></span><button id='next'>Next ›</button></div>"
        "<!-- The Bard · MEGA Crew -->"
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
    repo = src.parent.parent  # saga/issue.json -> repo root
    art_dir = repo / "art" / "out" / f"issue-{num:03d}"
    art_url = f"/art/out/issue-{num:03d}"
    
    # Load prompts mapping from queue file
    prompts_map = {}
    queue_file = repo / "art" / "queue" / f"issue-{num:03d}.jsonl"
    if queue_file.exists():
        try:
            with open(queue_file, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip():
                        item = json.loads(line)
                        if "id" in item and "prompt" in item:
                            prompts_map[item["id"]] = item["prompt"]
        except Exception as e:
            print(f"Warning: could not parse queue file {queue_file}: {e}")

    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_suffix(".html")
    out.write_text(render_html(issue, num, str(art_dir), art_url, prompts_map), encoding="utf-8")
    drawn = sum(1 for f in art_dir.glob("*.png")) if art_dir.exists() else 0
    print(f"rendered -> {out} ({num}) | drawn panels available: {drawn}")


if __name__ == "__main__":
    main()

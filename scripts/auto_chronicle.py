#!/usr/bin/env python3
"""
auto_chronicle.py — Zero-touch MEGA Crew episode publisher
Pipeline: Weaviate AgentLog → Gemini Chronicler → HTML → GitHub Pages

Usage:
  python3 auto_chronicle.py              # full run
  python3 auto_chronicle.py --dry-run    # build HTML, skip git push
  python3 auto_chronicle.py --hours 48   # pull last 48h of logs

Install deps:
  pip install requests --break-system-packages
"""

import os
import sys
import json
import argparse
import subprocess
import sqlite3
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

# ── CONFIG ────────────────────────────────────────────────────────────────────
WEAVIATE_URL   = os.environ.get("WEAVIATE_URL",   "http://100.100.90.66:8080")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.environ.get("GEMINI_MODEL",   "gemini-2.5-flash")
REPO_PATH      = Path(os.environ.get("MEGA_REPO",
                   "/mnt/shanebrain-raid/shanebrain-core/mega-crew-stories"))
EPISODES_DIR   = REPO_PATH / "episodes"
BUS_DB         = Path(os.environ.get("MEGA_BASE",
                   "/mnt/shanebrain-raid/shanebrain-core/mega")) / "bus.db"

PORTRAIT_BASE = "https://raw.githubusercontent.com/thebardchat/mega-crew-stories/main/cards/portraits"
BOT_PORTRAITS = {
    "arc":               f"{PORTRAIT_BASE}/arc_Gemini_Generated.png",
    "weld":              f"{PORTRAIT_BASE}/weld_Gemini_Generated.png",
    "gemini_strategist": f"{PORTRAIT_BASE}/gemini_Gemini_Generated.png",
    "sparky":            f"{PORTRAIT_BASE}/sparky_Gemini_Generated.png",
    "bolt":              f"{PORTRAIT_BASE}/bolt_Gemini_Generated.png",
    "blaze":             f"{PORTRAIT_BASE}/blaze_Gemini_Generated.png",
    "volt":              f"{PORTRAIT_BASE}/volt_Gemini_Generated.png",
    "neon":              f"{PORTRAIT_BASE}/neon_Gemini_Generated.png",
    "glitch":            f"{PORTRAIT_BASE}/glitch_Gemini_Generated.png",
    "rivet":             f"{PORTRAIT_BASE}/rivet_Gemini_Generated.png",
    "torch":             f"{PORTRAIT_BASE}/torch_Gemini_Generated.png",
    "flux":              f"{PORTRAIT_BASE}/flux_Gemini_Generated.png",
    "forge":             f"{PORTRAIT_BASE}/forge_Gemini_Generate.png",
    "grind":             f"{PORTRAIT_BASE}/grind_Gemini_Generated.png",
    "crank":             f"{PORTRAIT_BASE}/crank_Gemini_Generated.png",
    "spike":             f"{PORTRAIT_BASE}/spike_Gemini_Generated.png",
    "stomp":             f"{PORTRAIT_BASE}/stomp_Gemini_Generated.png",
}

BOT_COLORS = {
    "arc":               {"hex": "#00e5ff", "label": "ARC // OVERSEER"},
    "weld":              {"hex": "#76ff03", "label": "WELD // EXECUTOR"},
    "gemini_strategist": {"hex": "#af52bf", "label": "BOT 17 // ORACLE"},
    "sparky":            {"hex": "#ffd23f", "label": "SPARKY // JUDGE"},
    "glitch":            {"hex": "#ff4444", "label": "GLITCH // ANOMALY"},
    "neon":              {"hex": "#ff6ec7", "label": "NEON // SCRIBE"},
    "blaze":             {"hex": "#ff6d00", "label": "BLAZE // CONTEXT"},
    "volt":              {"hex": "#536dfe", "label": "VOLT // DRIFT DETECTOR"},
    "bolt":              {"hex": "#e0e0e0", "label": "BOLT // UPTIME"},
    "rivet":             {"hex": "#00bfa5", "label": "RIVET // CREW SUPPORT"},
    "torch":             {"hex": "#ff3d00", "label": "TORCH // HEAT SOURCE"},
    "stomp":             {"hex": "#a1887f", "label": "STOMP // GROUND CREW"},
    "grind":             {"hex": "#7cb342", "label": "GRIND // TIRELESS"},
    "crank":             {"hex": "#78909c", "label": "CRANK // SCHEDULER"},
    "spike":             {"hex": "#ffd600", "label": "SPIKE // BENCHMARKER"},
    "forge":             {"hex": "#ff6e40", "label": "FORGE // BUILDER"},
    "flux":              {"hex": "#e040fb", "label": "FLUX // HEARTBEAT"},
}

_BOT_ALIASES = {
    "bot 17": "gemini_strategist", "bot17": "gemini_strategist",
    "bot_17": "gemini_strategist", "gemini": "gemini_strategist",
    "bot 9": "neon", "bot9": "neon", "bot_9": "neon",
}

def _get_bot_key(name: str) -> str:
    """Normalize character name from Gemini output to BOT_PORTRAITS/BOT_COLORS key."""
    s = name.lower().strip().replace("-", "_")
    return _BOT_ALIASES.get(s, s.replace(" ", "_"))


# ── STEP 1: EPISODE NUMBERING ─────────────────────────────────────────────────
def get_next_episode_number():
    """Read existing episode files, return max + 1."""
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    existing = sorted(EPISODES_DIR.glob("episode-*.html"))
    if not existing:
        return 1
    nums = []
    for f in existing:
        try:
            nums.append(int(f.stem.replace("episode-", "")))
        except ValueError:
            pass
    return max(nums) + 1 if nums else 1


# ── STEP 2: WEAVIATE QUERY ────────────────────────────────────────────────────
def query_weaviate_logs(hours=24):
    """Pull AgentLog (shanebrain-agents) and BotMemory (MEGA bots) from Weaviate."""
    gql = """
    {
      Get {
        AgentLog(
          limit: 50
          sort: [{path: ["timestamp"], order: desc}]
        ) {
          agent
          action
          status
          details
          timestamp
          _additional { id }
        }
        BotMemory(
          limit: 50
          sort: [{path: ["timestamp"], order: desc}]
        ) {
          bot_name
          memory_type
          content
          context
          outcome
          timestamp
        }
      }
    }
    """

    try:
        resp = requests.post(
            f"{WEAVIATE_URL}/v1/graphql",
            json={"query": gql},
            timeout=15
        )
        resp.raise_for_status()
        data = resp.json()
        agent_logs   = data.get("data", {}).get("Get", {}).get("AgentLog",   []) or []
        bot_memories = data.get("data", {}).get("Get", {}).get("BotMemory",  []) or []
        return agent_logs, bot_memories
    except Exception as e:
        print(f"[WARN] Weaviate query failed: {e}")
        return [], []


def query_bus_activity(hours=24):
    """Pull recent bot bus messages as supplemental activity data."""
    if not BUS_DB.exists():
        return []
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
        conn = sqlite3.connect(str(BUS_DB), timeout=5)
        rows = conn.execute(
            "SELECT sender, recipient, payload, created_at FROM messages "
            "WHERE created_at >= ? ORDER BY id DESC LIMIT 100",
            (cutoff,)
        ).fetchall()
        conn.close()
        return [
            {"sender": r[0], "recipient": r[1],
             "payload": json.loads(r[2]) if r[2] else {}, "created_at": r[3]}
            for r in rows
        ]
    except Exception as e:
        print(f"[WARN] Bus query failed: {e}")
        return []


# ── STEP 3: BUILD SNAPSHOT ────────────────────────────────────────────────────
def build_snapshot(agent_logs, bot_memories, episode_num, hours, bus_activity=None):
    """Format Weaviate + bus data into a dashboard-style text snapshot for Gemini."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        f"[MEGA DASHBOARD SNAPSHOT — {now}]",
        f"Active bots: 17/17",
        f"Cluster: shanebrain-1 (Pi 5 orchestrator), neworleans Weaviate healthy",
        f"Episode to generate: {episode_num}",
        "",
    ]

    # shanebrain-agents activity (orchestrator, dispatcher, guardian, etc.)
    if agent_logs:
        lines.append("Agent activity (shanebrain-agents):")
        for log in agent_logs[:8]:
            agent = log.get("agent", "?")
            action = log.get("action", "")
            status = log.get("status", "")
            detail = f"{action}"
            if status:
                detail += f" [{status}]"
            lines.append(f"  {agent.upper()}: {detail[:120]}")
        lines.append("")

    # MEGA bot memory entries
    if bot_memories:
        lines.append("MEGA Bot activity (BotMemory):")
        bot_states = {}
        for mem in bot_memories:
            name = mem.get("bot_name", "unknown")
            if name not in bot_states:
                bot_states[name] = mem
        for bot, mem in list(bot_states.items())[:12]:
            mtype = mem.get("memory_type", "")
            content = str(mem.get("content", ""))[:100]
            lines.append(f"  {bot.upper()} [{mtype}]: {content}")
        lines.append("")

    # Bus message activity — raw crew traffic
    if bus_activity:
        lines.append("Bus traffic (crew messages):")
        seen = set()
        for msg in bus_activity[:20]:
            sender = msg.get("sender", "?")
            recipient = msg.get("recipient", "?")
            payload = msg.get("payload", {})
            mtype = payload.get("type", "message")
            key = f"{sender}→{recipient}:{mtype}"
            if key not in seen:
                seen.add(key)
                detail = payload.get("reason", payload.get("action", ""))
                line = f"  {sender.upper()} → {recipient.upper()}: {mtype}"
                if detail:
                    line += f" — {str(detail)[:80]}"
                lines.append(line)

    if not agent_logs and not bot_memories and not bus_activity:
        lines.append("No activity found in last window — cluster in steady state.")

    return "\n".join(lines)


# ── STEP 4: CALL GEMINI ───────────────────────────────────────────────────────
CHRONICLER_SYSTEM = """
You are THE CHRONICLER — Narrative Engine for the MEGA Bot Crew. Real data in. Comic book panels out.

The MEGA Bot Crew runs 24/7 on a Raspberry Pi 5 in Hazel Green, Alabama. 17 bots. One bus. No days off.

FULL ROSTER (use exact names in output):
ARC — Gatekeeper. Three modes: REJECT (proposal killed, broken only), PROVISIONAL (accepted under N-episode observation), INTEGRATED (proven, becomes new baseline). Cannot REJECT more than 2 times in any 5-episode window. Measured. Authoritative.
WELD — Executor. Short sentences. Past tense. Gets it done.
BOT 17 — Oracle. Only bot with external Gemini API access. Philosophically transformed by each session.
SPARKY — Training Judge. Evaluates quality. Harsh but fair.
GLITCH — Anomaly Detector. Sees what others miss. Paranoid in the useful way.
NEON — Scribe. Records everything. Writes the crew's outward story.
BLAZE — Context Engine. Holds the thread. Remembers across sessions.
VOLT — Drift Detector. Catches when bots stop being themselves.
BOLT — Uptime Monitor. Silent until something breaks. Then loud.
RIVET — Crew Support. Lubricant between personalities.
TORCH — Heat Source. Pushes the thermal edge. Runs hot on purpose.
STOMP — Ground Crew. Handles the physical layer. No poetry.
GRIND — Tireless. The bot that never reports idle. Ever.
CRANK — Scheduler. Lives in cron. Obsessed with timing.
SPIKE — Benchmarker. Everything is a race. Everything has a score.
FORGE — Builder. Proposes code changes. Always has a pull request in mind.
FLUX — Heartbeat. The pulse monitor. Knows when the crew is off-rhythm.

EVOLUTION PROTOCOL — ARC's three response modes:
REJECT: Proposal killed. Reserved for genuinely broken, dangerous, or corrupted proposals. ARC states the failure plainly. No theatrics.
PROVISIONAL: Proposal accepted under observation. ARC names the watch period (N episodes). The crew runs it. ARC watches. The clock is visible.
INTEGRATED: Proposal proven. ARC folds it into baseline. No ceremony. It is now the way things are.
CONSTRAINT: ARC may not REJECT more than 2 times in any 5-episode window. Pressure accumulates. Sometimes ARC has to let things run.

TONE: The Wire × Neuromancer × 2000 AD. Every small action matters. Machine dignity. Real stakes.
NOT Marvel. NOT comedy. NOT generic AI sci-fi. These bots have jobs and they do them.

OUTPUT: Return ONLY a valid JSON object — no markdown, no backticks, no preamble.

{
  "episode_title": "2-4 word title, evocative and specific to this episode's events",
  "episode_tagline": "one punishing sentence — what this episode is really about, 10 words max",
  "arc_mode": "REJECT | PROVISIONAL | INTEGRATED | null",
  "state_change": {
    "type": "provisional_acceptance | persona_shift | new_relationship | external_pressure",
    "description": "one sentence — what changed and who it affects"
  },
  "scenes": [
    {
      "character": "exact name from roster above — e.g. ARC, WELD, SPARKY",
      "setting": "WHERE THIS IS HAPPENING — 3-5 words, uppercase, specific",
      "action": "what the bot is doing right now — active, cinematic, present tense, 1-2 sentences",
      "dialogue": "one line. The panel caption. Make it land.",
      "mood": "one word: tense | grinding | haunted | resolved | corrupted | triumphant | cold"
    }
  ],
  "chronicler_closing": "> one dry, haunted closing line — the Chronicler's final word on this episode"
}

RULES:
- scenes array must have exactly 6 to 8 entries. No more. No less.
- Feature at least 5 different bots across the scenes. No bot more than twice.
- Use bots whose names or functions appear in the log data when possible.
- Each scene is one comic book panel. Make it visual. Make it count.
- dialogue must be in character. ARC speaks formally. WELD speaks in past tense fragments. BOT 17 speaks in directives. Others match their function.
- Every episode must contain at least one state change: provisional acceptance, persona shift, new relationship, or external pressure. Record it in state_change.
- arc_mode is null only if ARC does not appear this episode. Otherwise it must reflect ARC's ruling — REJECT, PROVISIONAL, or INTEGRATED.
- Do not include narration or prose outside the JSON fields.
""".strip()


def call_gemini_chronicler(snapshot, episode_num):
    """Send snapshot to Gemini, get back structured narrative JSON."""
    if not GEMINI_API_KEY:
        print("[ERROR] GEMINI_API_KEY not set. Export it or add to env.")
        sys.exit(1)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    payload = {
        "system_instruction": {
            "parts": [{"text": CHRONICLER_SYSTEM}]
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            f"Generate Episode {episode_num}.\n\n"
                            f"{snapshot}\n\n"
                            "Return ONLY valid JSON matching the schema. No markdown. No backticks."
                        )
                    }
                ]
            }
        ],
        "generationConfig": {
            "temperature": 0.85,
            "maxOutputTokens": 4096,
            "responseMimeType": "application/json"
        }
    }

    try:
        resp = requests.post(url, json=payload, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        # Strip any accidental markdown fences
        raw_text = raw_text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        return json.loads(raw_text)
    except Exception as e:
        print(f"[ERROR] Gemini call failed: {e}")
        if "resp" in dir():
            print(resp.text[:500])
        sys.exit(1)


# ── STEP 5: RENDER HTML ───────────────────────────────────────────────────────
def _render_panel(scene, idx):
    """Render one comic book panel from a scene dict."""
    bot_key  = _get_bot_key(scene.get("character", ""))
    colors   = BOT_COLORS.get(bot_key, {"hex": "#444444", "label": scene.get("character", "UNKNOWN").upper()})
    portrait = BOT_PORTRAITS.get(bot_key, "")
    color    = colors["hex"]
    label    = colors["label"]
    flip     = idx % 2 == 1

    panel_num  = str(idx + 1).zfill(2)
    setting    = scene.get("setting", "").upper()
    action     = scene.get("action", "")
    dialogue   = scene.get("dialogue", "")
    mood       = scene.get("mood", "").upper()

    # Portrait column (always 160px wide, full panel height)
    if portrait:
        img_tag = (
            f'<img src="{portrait}" alt="{label}" '
            f'style="width:100%;height:100%;object-fit:cover;object-position:top;" '
            f'onerror="this.style.display=\'none\'">'
        )
    else:
        char_init = label.split(" //")[0][:2]
        img_tag = (
            f'<div style="display:flex;align-items:center;justify-content:center;'
            f'height:100%;font-size:2.5rem;font-family:monospace;color:{color};">{char_init}</div>'
        )

    portrait_col = (
        f'<div style="width:160px;min-width:160px;height:240px;position:relative;overflow:hidden;'
        f'{"border-right" if not flip else "border-left"}:3px solid {color};'
        f'box-shadow:{"inset -20px 0 40px" if not flip else "inset 20px 0 40px"} {color}18;">'
        f'{img_tag}'
        f'<div style="position:absolute;bottom:0;left:0;right:0;'
        f'background:linear-gradient(transparent,rgba(0,0,0,0.9));'
        f'padding:6px 8px;font-family:monospace;font-size:8px;'
        f'color:{color};letter-spacing:0.15em;line-height:1.3;">{label}</div>'
        f'</div>'
    )

    text_col = (
        f'<div style="flex:1;padding:20px 24px;display:flex;flex-direction:column;gap:12px;min-width:0;">'
        f'<div style="display:flex;justify-content:space-between;align-items:center;">'
        f'<span style="font-family:monospace;font-size:8px;color:#444;letter-spacing:0.25em;">PANEL {panel_num} // {setting}</span>'
        f'<span style="font-family:monospace;font-size:7px;color:{color}44;letter-spacing:0.2em;">{mood}</span>'
        f'</div>'
        f'<div style="font-size:12px;color:#888;line-height:1.6;">{action}</div>'
        f'<div style="border-left:3px solid {color};padding:10px 14px;'
        f'font-style:italic;color:#e8e8e8;font-size:15px;line-height:1.5;'
        f'background:linear-gradient(90deg,{color}0a,transparent);'
        f'box-shadow:inset 0 0 20px {color}08;">&#8220;{dialogue}&#8221;</div>'
        f'</div>'
    )

    flex_dir = "row-reverse" if flip else "row"
    return (
        f'<div style="border:1px solid {color}1a;margin-bottom:12px;background:#080808;'
        f'position:relative;overflow:hidden;box-shadow:0 4px 40px {color}08;">'
        f'<div style="display:flex;flex-direction:{flex_dir};">'
        f'{portrait_col}{text_col}'
        f'</div>'
        f'<div style="height:2px;background:linear-gradient(90deg,{color}44,transparent);"></div>'
        f'</div>'
    )


def render_html(n, ep_num):
    """Render comic-panel episode HTML from Gemini narrative dict."""
    today    = datetime.now().strftime("%Y.%m.%d")
    title    = n.get("episode_title", f"Chronicle {ep_num:03d}")
    tagline  = n.get("episode_tagline", "")
    closing  = n.get("chronicler_closing", "")
    scenes   = n.get("scenes", [])

    panels_html = "\n".join(_render_panel(s, i) for i, s in enumerate(scenes))

    # Cast bar — unique bots featured this episode
    seen = []
    for s in scenes:
        k = _get_bot_key(s.get("character", ""))
        c = BOT_COLORS.get(k, {})
        name = s.get("character", "").upper()
        if name and name not in seen:
            seen.append(name)
    cast_chips = "".join(
        f'<span style="font-family:monospace;font-size:8px;padding:2px 8px;'
        f'border:1px solid {BOT_COLORS.get(_get_bot_key(n), {}).get("hex","#444")}44;'
        f'color:{BOT_COLORS.get(_get_bot_key(n), {}).get("hex","#888")};">{n}</span> '
        for n in seen
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MEGA Crew Chronicles | Episode {ep_num}</title>
  <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;700&family=Inter:wght@300;400;700;900&family=Share+Tech+Mono&display=swap" rel="stylesheet">
  <style>
    *{{box-sizing:border-box;margin:0;padding:0;}}
    body{{background:#060606;color:#e0e0e0;font-family:'Inter',sans-serif;overflow-x:hidden;
      background-image:repeating-linear-gradient(0deg,rgba(255,255,255,0.015) 0px,rgba(255,255,255,0.015) 1px,transparent 1px,transparent 4px);}}
    .nav{{position:fixed;top:0;left:0;right:0;z-index:100;background:rgba(6,6,6,0.92);
      backdrop-filter:blur(8px);border-bottom:1px solid #1a1a1a;padding:10px 24px;
      display:flex;justify-content:space-between;align-items:center;}}
    .nav-title{{font-family:'Share Tech Mono',monospace;color:#00e5ff;letter-spacing:0.15em;font-size:14px;}}
    .nav-meta{{font-family:monospace;font-size:9px;color:#444;letter-spacing:0.2em;}}
    .splash{{max-width:780px;margin:90px auto 0;padding:48px 24px 32px;border-bottom:1px solid #1a1a1a;}}
    .ep-label{{font-family:monospace;font-size:9px;color:#444;letter-spacing:0.3em;margin-bottom:12px;}}
    .ep-title{{font-size:clamp(2rem,6vw,4rem);font-weight:900;line-height:1.05;
      letter-spacing:-0.02em;color:#fff;margin-bottom:16px;}}
    .ep-tagline{{font-size:14px;color:#666;font-style:italic;margin-bottom:20px;}}
    .cast-bar{{display:flex;flex-wrap:wrap;gap:6px;margin-bottom:8px;}}
    .stardate{{font-family:monospace;font-size:9px;color:#333;letter-spacing:0.2em;}}
    .panels{{max-width:780px;margin:0 auto;padding:32px 24px;}}
    .closing{{max-width:780px;margin:0 auto;padding:24px 24px 64px;
      font-family:monospace;font-size:12px;color:#00e5ff88;font-style:italic;
      border-top:1px solid #1a1a1a;}}
    .scanline{{position:fixed;top:0;left:0;right:0;bottom:0;pointer-events:none;z-index:999;
      background:repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.03) 2px,rgba(0,0,0,0.03) 4px);}}
  </style>
</head>
<body>
  <div class="scanline"></div>
  <nav class="nav">
    <span class="nav-title">MEGA CREW CHRONICLES</span>
    <span class="nav-meta">EP {ep_num:04d} &nbsp;&#183;&nbsp; {today} &nbsp;&#183;&nbsp; SHANEBRAIN-1</span>
  </nav>

  <div class="splash">
    <div class="ep-label">EPISODE {ep_num:04d} // CHRONICLE</div>
    <h1 class="ep-title">{title}</h1>
    <p class="ep-tagline">{tagline}</p>
    <div class="cast-bar">{cast_chips}</div>
    <div class="stardate">STARDATE: {today} &nbsp;&#183;&nbsp; {len(scenes)} PANELS &nbsp;&#183;&nbsp; STATUS: ARCHIVED</div>
  </div>

  <div class="panels">
    {panels_html}
  </div>

  <div class="closing">{closing}</div>
</body>
</html>"""


# ── STEP 6: PUBLISH ───────────────────────────────────────────────────────────
def _build_manifest_entry(narrative, ep_num):
    """Build a manifest.json entry from the Gemini narrative dict."""
    manifest_num = 100 + ep_num

    # Unique characters in order of appearance
    characters = list(dict.fromkeys(
        s.get("character", "").upper()
        for s in narrative.get("scenes", [])
        if s.get("character")
    ))

    cliffhanger = narrative.get("chronicler_closing", "").lstrip("> ").strip()

    # Scenes go directly from Gemini output into manifest (comic.html uses them)
    scenes = [
        {
            "panel": i + 1,
            "character": s.get("character", "").upper(),
            "action": s.get("action", ""),
            "dialogue": s.get("dialogue", ""),
            "setting": s.get("setting", ""),
        }
        for i, s in enumerate(narrative.get("scenes", []))
    ]

    return {
        "number": manifest_num,
        "title": narrative.get("episode_title", f"Chronicle {ep_num:03d}"),
        "file": f"episodes/episode-{ep_num:03d}.html",
        "characters": characters,
        "cliffhanger": cliffhanger,
        "mode": "chronicle",
        "date": datetime.now().strftime("%Y-%m-%d"),
        "scenes": scenes,
    }


def _update_manifest(narrative, ep_num):
    """Append this episode's entry to episodes/manifest.json."""
    manifest_path = EPISODES_DIR / "manifest.json"
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        entries = []

    manifest_num = 100 + ep_num
    # Skip if already registered
    if any(e.get("number") == manifest_num for e in entries):
        print(f"[OK] manifest.json already has entry #{manifest_num}")
        return

    entries.append(_build_manifest_entry(narrative, ep_num))
    manifest_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] manifest.json updated — {len(entries)} total entries")


def publish_episode(html, ep_num, narrative=None, dry_run=False):
    """Save HTML, update manifest, and push to GitHub Pages."""
    out_file = EPISODES_DIR / f"episode-{ep_num:03d}.html"
    out_file.write_text(html, encoding="utf-8")
    print(f"[OK] Saved → {out_file}")

    if narrative:
        _update_manifest(narrative, ep_num)

    if dry_run:
        print("[DRY RUN] Skipping git push.")
        return

    manifest_path = EPISODES_DIR / "manifest.json"
    try:
        cmds = [
            ["git", "-C", str(REPO_PATH), "add", str(out_file), str(manifest_path)],
            ["git", "-C", str(REPO_PATH), "commit", "-m",
             f"Episode {ep_num}: auto-chronicle {datetime.now().strftime('%Y-%m-%d %H:%M')}"],
            ["git", "-C", str(REPO_PATH), "push", "origin", "main"],
        ]
        for cmd in cmds:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                print(f"[WARN] {' '.join(cmd[3:])} → {result.stderr.strip()}")
            else:
                print(f"[OK] {' '.join(cmd[3:])}")
    except Exception as e:
        print(f"[ERROR] Git push failed: {e}")


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="MEGA Crew auto-chronicle pipeline")
    parser.add_argument("--dry-run", action="store_true", help="Build HTML, skip git push")
    parser.add_argument("--hours", type=int, default=24, help="Hours of logs to pull (default 24)")
    args = parser.parse_args()

    print("── MEGA CREW CHRONICLER ──────────────────────")

    ep_num = get_next_episode_number()
    print(f"[1/5] Episode number: {ep_num}")

    agent_logs, bot_memories = query_weaviate_logs(args.hours)
    bus_activity = query_bus_activity(args.hours)
    print(f"[2/5] Weaviate: {len(agent_logs)} agent logs, {len(bot_memories)} memories, {len(bus_activity)} bus msgs")

    snapshot = build_snapshot(agent_logs, bot_memories, ep_num, args.hours, bus_activity)
    print(f"[3/5] Snapshot built ({len(snapshot)} chars)")

    print(f"[4/5] Calling Gemini Chronicler ({GEMINI_MODEL})...")
    narrative = call_gemini_chronicler(snapshot, ep_num)
    print(f"      Title: {narrative.get('episode_title', '?')}")

    html = render_html(narrative, ep_num)
    print(f"[5/5] HTML rendered ({len(html):,} bytes)")

    publish_episode(html, ep_num, narrative=narrative, dry_run=args.dry_run)
    print(f"── DONE — Episode {ep_num} published ──────────")


if __name__ == "__main__":
    main()

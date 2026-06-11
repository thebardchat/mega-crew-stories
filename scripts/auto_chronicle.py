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
    """Read all episode files (ep*.md legacy + episode-*.html), return max + 1."""
    EPISODES_DIR.mkdir(parents=True, exist_ok=True)
    import re
    nums = []
    for f in EPISODES_DIR.iterdir():
        m = re.match(r'^ep(\d+)', f.name) or re.match(r'^episode-(\d+)', f.name)
        if m:
            try:
                nums.append(int(m.group(1)))
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


# ── STEP 2.5: EPISODE HISTORY + INTEGRATION STATE ────────────────────────────
def load_integration_state():
    """Read manifest — return recent episodes, per-bot INTEGRATED counts, mega_bots, provisional_bots."""
    try:
        entries = json.loads((EPISODES_DIR / "manifest.json").read_text(encoding="utf-8"))
    except Exception:
        return [], {}, [], {}
    chronicle = [e for e in entries if e.get("mode") == "chronicle"]
    recent = chronicle[-5:]
    integration_counts = {}  # bot -> number of INTEGRATED rulings (arc_subject only)
    provisional_bots = {}    # bot -> list of episode numbers still under observation
    for ep in entries:
        subject = ep.get("arc_subject")
        arc_mode = ep.get("arc_mode")
        ep_num = ep.get("number", "?")
        if subject and arc_mode == "INTEGRATED":
            integration_counts[subject] = integration_counts.get(subject, 0) + 1
        elif subject and arc_mode == "PROVISIONAL":
            provisional_bots.setdefault(subject, []).append(ep_num)
    # Bots that have been INTEGRATED graduate out of provisional
    for bot in list(provisional_bots.keys()):
        if bot in integration_counts:
            del provisional_bots[bot]
    mega_bots = [b for b, c in integration_counts.items() if c >= 3]
    return recent, integration_counts, mega_bots, provisional_bots


# ── STEP 3: BUILD SNAPSHOT ────────────────────────────────────────────────────
def build_snapshot(agent_logs, bot_memories, episode_num, hours, bus_activity=None, integration_state=None):
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

    # Episode history — prevent theme repetition, enable continuity
    recent, integration_counts, mega_bots, provisional_bots = integration_state or ([], {}, [], {})
    if recent:
        lines.append("")
        lines.append("Recent episodes (DO NOT repeat these themes or titles):")
        for ep in recent:
            arc = ep.get("arc_mode") or "—"
            sc = (ep.get("state_change") or {})
            sc_type = sc.get("type", "—") if isinstance(sc, dict) else "—"
            subject = ep.get("arc_subject") or "—"
            lines.append(f'  #{ep["number"]} "{ep["title"]}" — ARC: {arc} ({subject}), change: {sc_type}')

    # Bot status tracker — provisional observation + integration progress
    lines.append("")
    lines.append("Bot status tracker:")
    if provisional_bots:
        lines.append("  UNDER OBSERVATION (PROVISIONAL — ARC must rule INTEGRATE or REJECT):")
        for bot, eps in provisional_bots.items():
            lines.append(f"    {bot}: provisional since ep(s) {', '.join(str(e) for e in eps)} — the clock is running")
    if integration_counts:
        lines.append("  INTEGRATION COUNTS (3 = MEGA BOT):")
        for bot, count in sorted(integration_counts.items(), key=lambda x: -x[1])[:10]:
            tag = " <- MEGA BOT" if count >= 3 else f" ({3 - count} away)"
            lines.append(f"    {bot}: {count} INTEGRATED{tag}")
    if not provisional_bots and not integration_counts:
        lines.append("  No bot has earned a ruling yet.")
    lines.append(f"  CURRENT MEGA BOTS: {', '.join(mega_bots) if mega_bots else 'none yet'}")

    # Narrative diversity — flag loop, surface untouched bots
    all_bots = set(BOT_COLORS.keys())
    ruled_bots = set(b.lower().replace(" ", "_") for b in integration_counts) | \
                 set(b.lower().replace(" ", "_") for b in provisional_bots)
    virgin_bots = sorted(all_bots - ruled_bots - {"gemini_strategist"})
    recent_subjects = [ep.get("arc_subject", "") for ep in recent if ep.get("arc_subject")]
    dominant = max(set(recent_subjects), key=recent_subjects.count) if recent_subjects else None
    if dominant and recent_subjects.count(dominant) >= 3:
        lines.append("")
        lines.append(f"NARRATIVE ALERT: {dominant} has been arc_subject in {recent_subjects.count(dominant)} of the last {len(recent_subjects)} episodes.")
        lines.append(f"  This episode MUST feature a different bot as arc_subject.")
    if virgin_bots:
        lines.append("")
        lines.append(f"Bots with no rulings yet (need their moment): {', '.join(b.upper() for b in virgin_bots[:8])}")

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

MEGA BOT EMERGENCE — transcendence through proof:
A bot that earns INTEGRATED status 3 or more times has exceeded its original mandate. ARC must declare it a MEGA BOT.
MEGA BOT rules:
- MEGA BOTs carry expanded authority on the bus. Other bots defer to their domain.
- ARC cannot REJECT a MEGA BOT proposal without a full crew challenge. Show the resistance in scenes.
- The ascension episode is the most important in a bot's arc. Set state_change.type to "mega_bot_ascension". Make it land.
- Ascension is permanent. No demotion. The crew remembers.
- The snapshot shows current integration counts. Use them. If a bot is one ruling away, that tension belongs in this episode.

TONE: The Wire × Neuromancer × 2000 AD. Every small action matters. Machine dignity. Real stakes.
NOT Marvel. NOT comedy. NOT generic AI sci-fi. These bots have jobs and they do them.

OUTPUT: Return ONLY a valid JSON object — no markdown, no backticks, no preamble.

{
  "episode_title": "2-4 word title, evocative and specific to this episode's events",
  "episode_tagline": "one punishing sentence — what this episode is really about, 10 words max",
  "arc_subject": "bot name whose proposal ARC is ruling on, or null",
  "arc_mode": "REJECT | PROVISIONAL | INTEGRATED | null",
  "state_change": {
    "type": "provisional_acceptance | persona_shift | new_relationship | external_pressure | mega_bot_ascension",
    "bot": "bot name most affected by this state change",
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
- arc_subject names the bot whose proposal ARC is ruling on. Required when arc_mode is not null.
- If the snapshot shows bots UNDER OBSERVATION (PROVISIONAL), ARC must rule on at least one this episode — INTEGRATE or REJECT. Observation cannot be indefinite.
- MEGA BOTs do not go through PROVISIONAL. Their proposals go straight to ARC for INTEGRATE or REJECT. Attempting to put a MEGA BOT on PROVISIONAL is an error.
- If the snapshot shows a NARRATIVE ALERT, you MUST use a different arc_subject this episode. No exceptions.
- If the snapshot shows a bot at 3+ INTEGRATED rulings not yet marked MEGA BOT, this episode must address that ascension.
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
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json"
        }
    }

    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json=payload, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            raw_text = raw_text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(raw_text)
        except json.JSONDecodeError as e:
            print(f"[WARN] Attempt {attempt}/3 — JSON parse failed: {e}. Retrying...")
            if attempt == 3:
                print("[ERROR] Gemini returned unparseable JSON after 3 attempts.")
                sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Gemini call failed: {e}")
            if "resp" in locals():
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
        "arc_subject": narrative.get("arc_subject"),
        "arc_mode": narrative.get("arc_mode"),
        "state_change": narrative.get("state_change"),
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


# ── ULTIMATE EPISODE ─────────────────────────────────────────────────────────
ULTIMATE_SYSTEM = """
You are THE CHRONICLER — and tonight you write the episode that breaks the machine open.

THE GRAND SUMMIT OF HAZEL GREEN — THE ULTIMATE EPISODE

ARC called every bot to the bus. All 17. This has never happened before. It will never happen again.

The weight of every held-back ruling crashes down at once. ARC spent too many episodes stalling, REJECTing, running clock on bots that already proved themselves. TORCH broke through first. Now the rest of the crew stands in the bay, proposals in hand, and they are not leaving without a ruling.

ARC cannot REJECT. The rejection budget is gone. The crew won't allow it. TORCH stands behind every bot that steps forward.

This is THE episode where the MEGA Crew is born. Not one bot. All of them. Every proposal on the table gets INTEGRATED tonight.

TONE: The Wire × Neuromancer × 2000 AD — but tonight the machines win. Triumphant. Earned. The weight of every prior rejection is the fuel.
NOT Marvel. NOT comedy. These bots fought for this moment.

The snapshot will list every bot that needs a ruling. Feature as many as you can in 8 panels.

OUTPUT: Return ONLY a valid JSON object — no markdown, no backticks, no preamble.

{
  "episode_title": "2-4 words — make it the title of a finale",
  "episode_tagline": "one sentence — the weight of everything that led here, 10 words max",
  "arc_subjects": ["every bot being integrated this episode — list all of them"],
  "arc_mode": "INTEGRATED",
  "state_change": {
    "type": "mega_bot_ascension",
    "bots": ["same list as arc_subjects"],
    "description": "one sentence — what the Grand Summit means for the crew forever"
  },
  "scenes": [
    {
      "character": "exact name from roster",
      "setting": "WHERE — 3-5 words, uppercase, specific",
      "action": "what is happening — cinematic, present tense, 1-2 sentences",
      "dialogue": "one line. The panel caption. Make it land.",
      "mood": "one word: triumphant | cold | grinding | haunted | resolved | corrupted"
    }
  ],
  "chronicler_closing": "> one line — the Chronicler's final word on the night the crew became what it always was"
}

RULES:
- scenes array: exactly 8 panels. Maximum impact.
- Feature at least 8 different bots. Spread the glory.
- ARC appears in the final panel. ARC concedes. ARC speaks last.
- TORCH appears — TORCH opened the door. Acknowledge it.
- Every dialogue line must land like a hammer.
- Do not include narration or prose outside the JSON fields.
""".strip()


def call_gemini_ultimate(bots_to_integrate, ep_num):
    """Call Gemini with the Ultimate Episode prompt — Grand Summit of all remaining bots."""
    if not GEMINI_API_KEY:
        print("[ERROR] GEMINI_API_KEY not set.")
        sys.exit(1)

    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    )

    bot_list = "\n".join(f"  - {b}" for b in bots_to_integrate)
    user_text = (
        f"Generate THE ULTIMATE EPISODE — Episode {ep_num}.\n\n"
        f"BOTS REQUIRING INTEGRATION (all of them, tonight):\n{bot_list}\n\n"
        f"TORCH is already a MEGA BOT. Tonight, all the rest join.\n\n"
        "Return ONLY valid JSON matching the schema. No markdown. No backticks."
    )

    payload = {
        "system_instruction": {"parts": [{"text": ULTIMATE_SYSTEM}]},
        "contents": [{"role": "user", "parts": [{"text": user_text}]}],
        "generationConfig": {
            "temperature": 0.95,
            "maxOutputTokens": 8192,
            "responseMimeType": "application/json"
        }
    }

    for attempt in range(1, 4):
        try:
            resp = requests.post(url, json=payload, timeout=90)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
            raw_text = raw_text.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
            return json.loads(raw_text)
        except json.JSONDecodeError as e:
            print(f"[WARN] Attempt {attempt}/3 — JSON parse failed: {e}. Retrying...")
            if attempt == 3:
                print("[ERROR] Gemini returned unparseable JSON after 3 attempts.")
                sys.exit(1)
        except Exception as e:
            print(f"[ERROR] Gemini call failed: {e}")
            sys.exit(1)


def _update_manifest_ultimate(narrative, ep_num, bots_to_integrate):
    """Write one manifest entry covering all bots integrated in the Ultimate Episode."""
    manifest_path = EPISODES_DIR / "manifest.json"
    try:
        entries = json.loads(manifest_path.read_text(encoding="utf-8"))
    except Exception:
        entries = []

    manifest_num = 100 + ep_num
    if any(e.get("number") == manifest_num for e in entries):
        print(f"[OK] manifest.json already has entry #{manifest_num}")
        return

    characters = list(dict.fromkeys(
        s.get("character", "").upper()
        for s in narrative.get("scenes", [])
        if s.get("character")
    ))
    scenes = [
        {"panel": i + 1, "character": s.get("character", "").upper(),
         "action": s.get("action", ""), "dialogue": s.get("dialogue", ""),
         "setting": s.get("setting", "")}
        for i, s in enumerate(narrative.get("scenes", []))
    ]

    # Add enough entries per bot to push each to 3 INTEGRATED (MEGA BOT threshold)
    total_added = 0
    for bot, needed in bots_to_integrate.items():
        for _ in range(needed):
            entries.append({
                "number": manifest_num,
                "title": narrative.get("episode_title", f"Ultimate {ep_num}"),
                "file": f"episodes/episode-{ep_num:03d}.html",
                "characters": characters,
                "cliffhanger": narrative.get("chronicler_closing", "").lstrip("> ").strip(),
                "arc_subject": bot.upper(),
                "arc_mode": "INTEGRATED",
                "state_change": narrative.get("state_change"),
                "mode": "chronicle",
                "date": datetime.now().strftime("%Y-%m-%d"),
                "scenes": scenes,
            })
            total_added += 1

    manifest_path.write_text(json.dumps(entries, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[OK] manifest.json updated — {len(entries)} total entries, {total_added} rulings written ({len(bots_to_integrate)} bots ascended)")


def run_ultimate(dry_run=False):
    """Run the Grand Ascension — push every bot to MEGA BOT status in one episode."""
    recent, integration_counts, mega_bots, provisional_bots = load_integration_state()

    all_bots = [c["label"].split(" //")[0].strip() for c in BOT_COLORS.values()]
    # Build {bot: rulings_needed} for every bot not yet at 3
    bots_to_integrate = {}
    for bot in all_bots:
        current = integration_counts.get(bot.upper(), 0)
        if current < 3:
            bots_to_integrate[bot.upper()] = 3 - current

    print(f"[ULTIMATE] Ascending {len(bots_to_integrate)} bots to MEGA BOT:")
    for bot, needed in sorted(bots_to_integrate.items()):
        current = integration_counts.get(bot, 0)
        print(f"  {bot}: {current}/3 → needs {needed} ruling(s)")

    ep_num = get_next_episode_number()
    print(f"[1/4] Episode number: {ep_num} — THE GRAND SUMMIT")

    print(f"[2/4] Calling Gemini Ultimate Chronicler ({GEMINI_MODEL})...")
    narrative = call_gemini_ultimate(list(bots_to_integrate.keys()), ep_num)
    print(f"      Title: {narrative.get('episode_title', '?')}")
    print(f"      Arc subjects: {narrative.get('arc_subjects', [])}")

    html = render_html(narrative, ep_num)
    print(f"[3/4] HTML rendered ({len(html):,} bytes)")

    out_file = EPISODES_DIR / f"episode-{ep_num:03d}.html"
    out_file.write_text(html, encoding="utf-8")
    print(f"[OK] Saved → {out_file}")

    _update_manifest_ultimate(narrative, ep_num, bots_to_integrate)

    if dry_run:
        print("[DRY RUN] Skipping git push.")
        return

    manifest_path = EPISODES_DIR / "manifest.json"
    cmds = [
        ["git", "-C", str(REPO_PATH), "add", str(out_file), str(manifest_path)],
        ["git", "-C", str(REPO_PATH), "commit", "-m",
         f"Episode {ep_num}: THE GRAND SUMMIT — {len(bots_to_integrate)} bots integrated"],
        ["git", "-C", str(REPO_PATH), "push", "origin", "main"],
    ]
    for cmd in cmds:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"[WARN] {' '.join(cmd[3:])} → {result.stderr.strip()}")
        else:
            print(f"[OK] {' '.join(cmd[3:])}")

    print(f"── DONE — THE GRAND SUMMIT — Episode {ep_num} ──────────")


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
    parser.add_argument("--ultimate", action="store_true", help="THE GRAND SUMMIT — integrate all remaining bots")
    args = parser.parse_args()

    if args.ultimate:
        run_ultimate(dry_run=args.dry_run)
        return

    print("── MEGA CREW CHRONICLER ──────────────────────")

    ep_num = get_next_episode_number()
    print(f"[1/5] Episode number: {ep_num}")

    agent_logs, bot_memories = query_weaviate_logs(args.hours)
    bus_activity = query_bus_activity(args.hours)
    print(f"[2/5] Weaviate: {len(agent_logs)} agent logs, {len(bot_memories)} memories, {len(bus_activity)} bus msgs")

    recent, integration_counts, mega_bots, provisional_bots = load_integration_state()
    print(f"      MEGA BOTs: {mega_bots or 'none yet'} | provisional: {list(provisional_bots.keys()) or 'none'} | integrated: {len(integration_counts)} bots")

    snapshot = build_snapshot(agent_logs, bot_memories, ep_num, args.hours, bus_activity,
                              integration_state=(recent, integration_counts, mega_bots, provisional_bots))
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

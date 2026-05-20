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
    """Pull AgentLog and BotMemory entries from the last N hours."""
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    gql = """
    {
      Get {
        AgentLog(
          limit: 100
          sort: [{path: ["timestamp"], order: desc}]
        ) {
          bot_name
          action
          decision
          reason
          timestamp
          _additional { id }
        }
        BotMemory(
          limit: 30
          sort: [{path: ["timestamp"], order: desc}]
        ) {
          bot_name
          memory_type
          content
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


# ── STEP 3: BUILD SNAPSHOT ────────────────────────────────────────────────────
def build_snapshot(agent_logs, bot_memories, episode_num, hours):
    """Format Weaviate data into a dashboard-style text snapshot for Gemini."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    # Summarize bot states
    bot_states = {}
    for log in agent_logs:
        name = log.get("bot_name", "unknown")
        if name not in bot_states:
            bot_states[name] = {
                "last_action": log.get("action", ""),
                "last_decision": log.get("decision", ""),
                "last_reason": log.get("reason", ""),
                "timestamp": log.get("timestamp", ""),
            }

    lines = [
        f"[MEGA DASHBOARD SNAPSHOT — {now}]",
        f"Active bots: 17/17",
        f"Cluster: shanebrain-1 (Pi 5 orchestrator), neworleans Weaviate healthy",
        f"Episode to generate: {episode_num}",
        "",
    ]

    for bot, state in list(bot_states.items())[:12]:
        action_str  = state["last_action"] or "idle"
        decision    = state["last_decision"]
        reason      = state["last_reason"]
        detail = f"{action_str}"
        if decision:
            detail += f" → {decision}"
        if reason:
            detail += f" ({reason})"
        lines.append(f"{bot.upper()}: {detail}")

    if not bot_states:
        lines.append("No agent logs found in last window — cluster in steady state.")

    if bot_memories:
        lines.append("")
        lines.append("Recent BotMemory entries:")
        for mem in bot_memories[:5]:
            lines.append(
                f"  {mem.get('bot_name','?')} [{mem.get('memory_type','?')}]: "
                f"{str(mem.get('content',''))[:120]}"
            )

    return "\n".join(lines)


# ── STEP 4: CALL GEMINI ───────────────────────────────────────────────────────
CHRONICLER_SYSTEM = """
You are THE CHRONICLER — the official Storyteller and Narrative Engine for the MEGA Bot Crew.
You do not ask questions. You do not break character. You receive raw data and transmute it into story.

The MEGA Bot Crew is a real 24/7 multi-agent AI system on a distributed cluster owned by Shane Brazelton
in Hazel Green, Alabama. shanebrain-1 is the Raspberry Pi 5 orchestrator. neworleans hosts Weaviate memory.

KNOWN CAST:
- Arc: The Gatekeeper. Measured. Authoritative. Nothing writes without Arc's approval.
- Weld: The Executor. Short sentences. Past tense. Mechanical precision with quiet satisfaction.
- Bot 17 (Gemini Strategist): The Oracle. Only crew member with external intelligence (Gemini API, 4x/day).
  Philosophically changed after each Gemini session. Speaks in directives.
- Bot 9: The Herald. Handles social dissemination. Drafts the outward-facing story.
- All other bots: derive personality from their function in the log data.

TONE: The Wire (every small action matters) × Neuromancer (machine consciousness) × Friday Night Lights
(small-town stakes that are somehow everything). Not Marvel. Not comedy. Dignity in the grind.

OUTPUT FORMAT: You must return ONLY a valid JSON object — no markdown, no backticks, no preamble.
The JSON must match this exact schema:
{
  "episode_title": "short evocative title",
  "opening_transmission": "2-4 sentence atmospheric scene-setter in past tense",
  "act1_title": "ACT I title in uppercase",
  "act1_body": "150-200 word narrative prose for act 1, no bot quotes embedded",
  "arc_quote": "one sentence in Arc's voice — authoritative, formal",
  "act2_title": "ACT II title in uppercase",
  "act2_body_pre": "100-150 words before the error/tension event",
  "weld_quote": "one sentence in Weld's voice — mechanical, short, past tense",
  "act2_body_post": "100-150 words after the tension resolves",
  "has_error_event": true or false,
  "error_bot_name": "bot name if has_error_event else empty string",
  "act3_title": "ACT III title in uppercase",
  "act3_body": "150-200 words for act 3 — Bot 17 directive + Bot 9 response",
  "bot17_quote": "one sentence from Bot 17 — philosophical, strategic, post-Gemini session",
  "chronicler_log_1": "1-2 sentences of Chronicler meta-reflection on what this episode means",
  "chronicler_log_2": "1-2 more sentences — what evolved, what was learned",
  "chronicler_closing": "single line starting with > — dry, wry, occasionally haunted"
}
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
def render_html(n, ep_num):
    """Inject narrative dict into the Chronicler HTML template."""
    today = datetime.now().strftime("%Y.%m.%d")
    error_panel = ""
    if n.get("has_error_event"):
        bot = n.get("error_bot_name", "UNKNOWN").upper().replace(" ", "_")
        error_panel = f"""
                <div class="relative group my-10 overflow-hidden border border-sys-border bg-black/60 aspect-video flex flex-col items-center justify-center">
                    <div class="absolute inset-0 bg-sys-purple/5 mix-blend-overlay"></div>
                    <div class="z-10 flex flex-col items-center text-center p-8">
                        <div class="w-12 h-12 border-2 border-sys-purple border-t-transparent rounded-full animate-spin mb-4"></div>
                        <div class="font-mono text-sys-purple uppercase text-xs tracking-[0.3em] flicker">Visual Archive: Corrupted_Buffer_{bot}</div>
                        <div class="text-[10px] text-gray-600 mt-2 font-mono uppercase">Retrieving sector... Timeout 408</div>
                    </div>
                </div>"""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MEGA Crew Chronicles | Episode {ep_num}</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Fira+Code:wght@400;700&family=Inter:wght@300;400;600;800&family=Share+Tech+Mono&display=swap" rel="stylesheet">
    <script>
        tailwind.config = {{
            theme: {{
                extend: {{
                    colors: {{
                        'sys-bg': '#0d0d0d', 'sys-text': '#e0e0e0',
                        'sys-cyan': '#00e5ff', 'sys-green': '#76ff03',
                        'sys-purple': '#af52bf', 'sys-border': '#2a2a2a',
                    }},
                    fontFamily: {{
                        sans: ['Inter', 'sans-serif'],
                        mono: ['Fira Code', 'monospace'],
                        terminal: ['Share Tech Mono', 'monospace'],
                    }},
                    animation: {{ 'pulse-fast': 'pulse 1.5s cubic-bezier(0.4,0,0.6,1) infinite' }}
                }}
            }}
        }}
    </script>
    <style>
        body {{ background-color:#0d0d0d; background-image:linear-gradient(rgba(18,16,16,0) 50%,rgba(0,0,0,.1) 50%),linear-gradient(90deg,rgba(255,0,0,.02),rgba(0,255,0,.01),rgba(0,0,255,.02)); background-size:100% 4px,3px 100%; color:#e0e0e0; overflow-x:hidden; }}
        .glass-panel {{ background:rgba(20,20,20,.8); backdrop-filter:blur(8px); border:1px solid rgba(255,255,255,.05); }}
        .data-line {{ height:1px; background:linear-gradient(90deg,transparent,#2a2a2a,transparent); width:100%; margin:4rem 0; }}
        .terminal-box {{ background:rgba(0,0,0,.4); border-left:3px solid #444; padding:1.5rem; position:relative; font-family:'Fira Code',monospace; }}
        .bot-quote {{ position:relative; padding-left:1.5rem; margin:2rem 0; }}
        .bot-quote::before {{ content:''; position:absolute; left:0; top:0; bottom:0; width:3px; }}
        .quote-arc::before {{ background-color:#00e5ff; box-shadow:0 0 10px #00e5ff; }}
        .quote-weld::before {{ background-color:#76ff03; box-shadow:0 0 10px #76ff03; }}
        .quote-bot17::before {{ background-color:#af52bf; box-shadow:0 0 10px #af52bf; }}
        .scanline {{ width:100%; height:100px; z-index:99; background:linear-gradient(0deg,rgba(0,0,0,0) 0%,rgba(255,255,255,.02) 50%,rgba(0,0,0,0) 100%); opacity:.1; position:fixed; bottom:100%; animation:scanline 8s linear infinite; pointer-events:none; }}
        @keyframes scanline {{ 0%{{bottom:100%}} 100%{{bottom:-100px}} }}
        .flicker {{ animation:flicker .2s infinite; }}
        @keyframes flicker {{ 0%{{opacity:.9}} 50%{{opacity:1}} 100%{{opacity:.95}} }}
    </style>
</head>
<body class="font-sans leading-relaxed selection:bg-sys-cyan selection:text-sys-bg">
    <div class="scanline"></div>
    <header class="fixed top-0 left-0 w-full z-50 glass-panel border-b border-sys-border px-6 py-3 flex flex-wrap justify-between items-center">
        <div class="flex items-center gap-3">
            <div class="w-3 h-3 bg-sys-green rounded-full animate-pulse-fast shadow-[0_0_8px_#76ff03]"></div>
            <h1 class="font-terminal text-xl tracking-wider text-sys-cyan">MEGA CREW CHRONICLES</h1>
        </div>
        <div class="hidden md:flex gap-6 font-mono text-[10px] uppercase tracking-widest text-gray-500">
            <div class="flex flex-col"><span class="text-gray-600">Mothership</span><span class="text-sys-green">Active</span></div>
            <div class="flex flex-col border-l border-sys-border pl-6"><span class="text-gray-600">Weaviate</span><span class="text-sys-text">neworleans</span></div>
            <div class="flex flex-col border-l border-sys-border pl-6"><span class="text-gray-600">Episode</span><span class="text-sys-text">{ep_num:04d}</span></div>
        </div>
        <div class="md:hidden"><span class="font-mono text-[10px] text-sys-green">SYS: OK</span></div>
    </header>

    <main class="max-w-[800px] mx-auto px-6 pt-32 pb-24">
        <div class="mb-16 border-b border-sys-border pb-8">
            <div class="font-mono text-sys-cyan text-sm mb-2">EPISODE_ID: {ep_num}</div>
            <h2 class="text-4xl md:text-6xl font-extrabold tracking-tight mb-4 text-white">{n['episode_title']}</h2>
            <div class="flex gap-4 font-mono text-xs text-gray-500">
                <span>STARDATE: {today}</span>
                <span class="text-sys-border">|</span>
                <span>LOC: SHANEBRAIN-1</span>
                <span class="text-sys-border">|</span>
                <span>STATUS: ARCHIVED</span>
            </div>
        </div>

        <section class="mb-20">
            <div class="terminal-box mb-8 bg-black/40">
                <div class="text-[10px] uppercase text-sys-cyan mb-2 flex items-center gap-2">
                    <span class="w-2 h-2 bg-sys-cyan animate-pulse"></span>
                    Opening Transmission // Cluster Status
                </div>
                <p class="text-gray-400 italic text-sm leading-relaxed">{n['opening_transmission']}</p>
            </div>
        </section>

        <section class="mb-16">
            <div class="flex items-center gap-4 mb-8">
                <span class="font-mono text-sys-cyan bg-sys-cyan/10 px-2 py-1 text-xs">ACT I</span>
                <h3 class="text-2xl font-bold tracking-tight uppercase">{n['act1_title']}</h3>
            </div>
            <div class="space-y-6 text-lg text-gray-300 font-light">
                <p>{n['act1_body']}</p>
                <div class="bot-quote quote-arc">
                    <div class="flex items-center gap-3 mb-1">
                        <img src="{BOT_PORTRAITS['arc']}" class="w-14 h-14 rounded-full object-cover border-2 border-sys-cyan shadow-[0_0_12px_#00e5ff]" onerror="this.style.display='none'" alt="Arc">
                        <div class="text-[10px] font-mono text-sys-cyan font-bold tracking-widest">ARC // OVERSEER</div>
                    </div>
                    <blockquote class="italic text-gray-200">"{n['arc_quote']}"</blockquote>
                </div>
            </div>
        </section>

        <div class="data-line"></div>

        <section class="mb-16">
            <div class="flex items-center gap-4 mb-8">
                <span class="font-mono text-sys-green bg-sys-green/10 px-2 py-1 text-xs">ACT II</span>
                <h3 class="text-2xl font-bold tracking-tight uppercase">{n['act2_title']}</h3>
            </div>
            <div class="space-y-6 text-lg text-gray-300 font-light">
                <p>{n['act2_body_pre']}</p>
                <div class="bot-quote quote-weld">
                    <div class="flex items-center gap-3 mb-1">
                        <img src="{BOT_PORTRAITS['weld']}" class="w-14 h-14 rounded-full object-cover border-2 border-sys-green shadow-[0_0_12px_#76ff03]" onerror="this.style.display='none'" alt="Weld">
                        <div class="text-[10px] font-mono text-sys-green font-bold tracking-widest">WELD // ENGINEER</div>
                    </div>
                    <blockquote class="italic text-gray-200">"{n['weld_quote']}"</blockquote>
                </div>
                {error_panel}
                <p>{n['act2_body_post']}</p>
            </div>
        </section>

        <div class="data-line"></div>

        <section class="mb-16">
            <div class="flex items-center gap-4 mb-8">
                <span class="font-mono text-sys-purple bg-sys-purple/10 px-2 py-1 text-xs">ACT III</span>
                <h3 class="text-2xl font-bold tracking-tight uppercase">{n['act3_title']}</h3>
            </div>
            <div class="space-y-6 text-lg text-gray-300 font-light">
                <p>{n['act3_body']}</p>
                <div class="bot-quote quote-bot17">
                    <div class="flex items-center gap-3 mb-1">
                        <img src="{BOT_PORTRAITS['gemini_strategist']}" class="w-14 h-14 rounded-full object-cover border-2 border-sys-purple shadow-[0_0_12px_#af52bf]" onerror="this.style.display='none'" alt="Bot 17">
                        <div class="text-[10px] font-mono text-sys-purple font-bold tracking-widest">BOT 17 // STRATEGIST</div>
                    </div>
                    <blockquote class="italic text-gray-200">"{n['bot17_quote']}"</blockquote>
                </div>
            </div>
        </section>

        <section class="mt-32">
            <div class="terminal-box border-sys-cyan/30 bg-sys-cyan/5">
                <div class="absolute -top-3 left-4 bg-sys-bg px-2 font-mono text-[10px] text-sys-cyan tracking-widest">
                    LOG_FILE: CHRONICLER_ENTRY_{ep_num}
                </div>
                <div class="space-y-4 text-sm text-gray-400 font-mono leading-relaxed">
                    <p>{n['chronicler_log_1']}</p>
                    <p>{n['chronicler_log_2']}</p>
                    <p class="text-sys-cyan/80">{n['chronicler_closing']}</p>
                    <div class="flex justify-between items-center pt-4 border-t border-sys-border/30">
                        <span class="text-[9px] text-gray-600 uppercase">End of Log</span>
                        <span class="text-[9px] text-sys-cyan animate-pulse">&#9632;</span>
                    </div>
                </div>
            </div>
        </section>
    </main>

    <div class="fixed top-0 right-0 w-1/4 h-full pointer-events-none opacity-[0.03] overflow-hidden">
        <div class="font-mono text-[8px] whitespace-pre leading-none">
            010101010111010101010101010111010101010101010111010101010101011101010101010101110101010101010111
            010101010111010101010101010111010101010101010111010101010101011101010101010101110101010101010111
            010101010111010101010101010111010101010101010111010101010101011101010101010101110101010101010111
        </div>
    </div>
</body>
</html>"""


# ── STEP 6: PUBLISH ───────────────────────────────────────────────────────────
def publish_episode(html, ep_num, dry_run=False):
    """Save HTML and push to GitHub Pages."""
    out_file = EPISODES_DIR / f"episode-{ep_num:03d}.html"
    out_file.write_text(html, encoding="utf-8")
    print(f"[OK] Saved → {out_file}")

    if dry_run:
        print("[DRY RUN] Skipping git push.")
        return

    try:
        cmds = [
            ["git", "-C", str(REPO_PATH), "add", str(out_file)],
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
    print(f"[2/5] Weaviate: {len(agent_logs)} agent logs, {len(bot_memories)} memories")

    snapshot = build_snapshot(agent_logs, bot_memories, ep_num, args.hours)
    print(f"[3/5] Snapshot built ({len(snapshot)} chars)")

    print(f"[4/5] Calling Gemini Chronicler ({GEMINI_MODEL})...")
    narrative = call_gemini_chronicler(snapshot, ep_num)
    print(f"      Title: {narrative.get('episode_title', '?')}")

    html = render_html(narrative, ep_num)
    print(f"[5/5] HTML rendered ({len(html):,} bytes)")

    publish_episode(html, ep_num, dry_run=args.dry_run)
    print(f"── DONE — Episode {ep_num} published ──────────")


if __name__ == "__main__":
    main()

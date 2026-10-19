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
    "nukkels":           f"{PORTRAIT_BASE}/nukkels_Gemini_Generated.png",
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
    "nukkels":           {"hex": "#ff1744", "label": "NUKKELS // POWER GRID"},
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
    """Pull AgentLog (shanebrain-agents) and BotMemory (MEGA bots) from Weaviate.

    Honors the hours window via a GreaterThan timestamp filter. Falls back to an
    unfiltered query if the where clause is rejected by the schema.
    """
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    where_clause = f'where: {{path: ["timestamp"], operator: GreaterThan, valueString: "{cutoff}"}}'

    def _build(use_where):
        w = f"\n          {where_clause}" if use_where else ""
        return f"""
    {{
      Get {{
        AgentLog(
          limit: 50{w}
          sort: [{path: ["timestamp"], order: desc}]
        ) {{}}
          agent
          action
          status
          details
          timestamp
          _additional {{ id }}
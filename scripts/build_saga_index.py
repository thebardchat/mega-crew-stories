#!/usr/bin/env python3
"""
build_saga_index.py — Pi side. Generates saga/index.html: a library landing page
that lists every published issue (newest first) with its hero cover thumbnail,
title, tagline, date and a Read button. This is the front door at
https://thebardchat.github.io/mega-crew-stories/saga/

Auto-generated from saga/manifest.json, so future issues appear with no edits.
Idempotent: only commits/pushes when the rendered HTML actually changes.
Paths are relative to saga/ so it works on any host (GitHub Pages, Cloudflare).

Usage:
  build_saga_index.py               # Pi: rebuild, commit and push
  build_saga_index.py --no-push     # just write saga/index.html (used by CI)
  SAGA_REPO=/path/to/mega-crew-stories build_saga_index.py --no-push

The same file lives in mega-crew-stories/scripts/ where a GitHub Action runs it
after every new issue, so the Pi no longer has to.
"""
import json
import os
import subprocess
import sys
from html import escape
from pathlib import Path

SITE = "https://thebardchat.github.io/mega-crew-stories"
PI_REPO = Path("/mnt/shanebrain-raid/shanebrain-core/mega-crew-stories")


def _find_repo():
    if os.environ.get("SAGA_REPO"):
        return Path(os.environ["SAGA_REPO"])
    if PI_REPO.exists():
        return PI_REPO
    here = Path(__file__).resolve().parents[1]
    for cand in (here, here / "mega-crew-stories"):
        if (cand / "saga" / "manifest.json").exists():
            return cand
    sys.exit("can't find mega-crew-stories; set SAGA_REPO")


REPO = _find_repo()
MANIFEST = REPO / "saga" / "manifest.json"
OUT = REPO / "saga" / "index.html"
DISCORD = "https://discord.gg/BTZZrG4MtV"


def _git(*a):
    return subprocess.run(["git", "-C", str(REPO), *a], capture_output=True, text=True)


def card(entry):
    n = entry.get("issue", 0)
    title = escape(entry.get("title", "").strip())
    tag = escape(entry.get("tagline", "").strip())
    date = escape(str(entry.get("date", "")).strip())
    href = escape(Path(entry.get("file", "")).name)  # relative to saga/
    cov = REPO / "art" / "out" / "covers" / f"i{n:03d}-cover.png"
    if cov.exists():
        thumb = (f"<div class='thumb' style=\"background-image:url('../art/out/"
                 f"covers/i{n:03d}-cover.png')\"></div>")
    else:
        thumb = f"<div class='thumb noart'><span>#{n:03d}</span></div>"
    return (f"<a class='issue' href='{href}'>{thumb}"
            f"<div class='meta'><div class='num'>ISSUE #{n:03d}"
            f"{' · ' + date if date else ''}</div>"
            f"<h2>{title}</h2><p>{tag}</p>"
            f"<span class='read'>Read →</span></div></a>")


def render(entries):
    cards = "".join(card(e) for e in sorted(
        entries, key=lambda x: x.get("issue", 0), reverse=True))
    return f"""<!doctype html><html lang='en'><head><meta charset='utf-8'>
<meta name='viewport' content='width=device-width,initial-scale=1'>
<title>The MEGA Crew Saga — All Issues</title>
<meta name='description' content='The self-writing comic book of the MEGA Crew. New issues Wed & Sun, 5 AM Central.'>
<meta property='og:type' content='website'>
<meta property='og:title' content='The MEGA Crew Saga'>
<meta property='og:description' content='The comic book the bots write themselves. New issues Wed & Sun, 5 AM Central.'>
<meta property='og:image' content='{SITE}/art/out/social/social-og.png'>
<meta name='twitter:card' content='summary_large_image'>
<meta name='twitter:image' content='{SITE}/art/out/social/social-og.png'>
<style>
*{{box-sizing:border-box}}
body{{margin:0;background:#07090c;color:#e9e5dc;font-family:-apple-system,Segoe UI,Roboto,sans-serif}}
.wrap{{max-width:980px;margin:0 auto;padding:42px 20px 80px}}
.kicker{{color:#7fb0d6;letter-spacing:.22em;text-transform:uppercase;font-size:12px;font-family:Menlo,monospace}}
h1{{font-size:40px;color:#f4c87a;margin:.15em 0 .1em}}
.sub{{color:#b9b4aa;font-style:italic;margin-bottom:8px}}
.cadence{{color:#6b7178;font-family:Menlo,monospace;font-size:12px;margin-bottom:30px}}
.hero{{width:100%;max-height:340px;object-fit:cover;border-radius:10px;border:1px solid #232a33;margin-bottom:22px;display:block}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(280px,1fr));gap:20px}}
.issue{{display:flex;flex-direction:column;text-decoration:none;color:inherit;background:#11151a;
border:1px solid #222831;border-radius:12px;overflow:hidden;transition:transform .12s,border-color .12s}}
.issue:hover{{transform:translateY(-3px);border-color:#3a4756}}
.thumb{{aspect-ratio:16/10;background:#0d1115 center/cover no-repeat}}
.thumb.noart{{display:flex;align-items:center;justify-content:center}}
.thumb.noart span{{color:#3a4350;font-family:Menlo,monospace;font-size:30px}}
.meta{{padding:14px 16px 18px}}
.num{{color:#7fb0d6;font-family:Menlo,monospace;font-size:11px;letter-spacing:.12em}}
.meta h2{{font-size:21px;color:#f4c87a;margin:.3em 0 .25em;line-height:1.12}}
.meta p{{color:#cfcabf;font-size:14px;margin:0 0 12px}}
.read{{color:#7fb0d6;font-weight:700;font-size:14px}}
.foot{{margin-top:42px;text-align:center}}
.dc{{display:inline-block;background:#5865F2;color:#fff;text-decoration:none;padding:12px 22px;
border-radius:10px;font-weight:700}}
.foot .home{{display:block;margin-top:18px;color:#5f656c;font-size:13px;text-decoration:none}}
</style></head><body><div class='wrap'>
<div class='kicker'>MEGA Crew · The Saga</div>
<h1>The MEGA Crew Saga</h1>
<div class='sub'>The comic book the bots write themselves.</div>
<div class='cadence'>NEW ISSUES — WEDNESDAY &amp; SUNDAY · 5 AM CENTRAL</div>
<img class='hero' src='../art/out/social/social-og.png' alt='The MEGA Crew'>
<div class='grid'>{cards}</div>
<div class='foot'>
<a class='dc' href='{DISCORD}' target='_blank' rel='noopener'>Come help guide the MEGA bots → join our Discord</a>
<a class='home' href='../index.html'>← back to thebardchat</a>
</div></div></body></html>"""


def main():
    push = "--no-push" not in sys.argv
    if push:
        _git("pull", "--ff-only", "origin", "main")
    entries = json.loads(MANIFEST.read_text(encoding="utf-8"))
    html = render(entries)
    if OUT.exists() and OUT.read_text(encoding="utf-8") == html:
        print("saga index already current")
        return
    OUT.write_text(html, encoding="utf-8")
    print(f"wrote {OUT} ({len(entries)} issues)")
    if not push:
        return
    _git("add", "saga/index.html")
    _git("commit", "-m", "saga: rebuild library index")
    r = _git("push", "origin", "main")
    print("pushed" if r.returncode == 0 else "push failed: " + r.stderr[:200])


if __name__ == "__main__":
    main()

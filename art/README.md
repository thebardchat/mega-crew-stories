# MEGA Crew — Art Render Farm Contract

This folder is the conveyor belt between the comic pipeline and the **Antigravity /
Nano Banana Pro** render farm running on **pulsar00100**.

```
art/queue/issue-NNN.jsonl     ← work orders IN  (the Pi writes these)
art/out/issue-NNN/<id>.png    ← finished art OUT (Antigravity writes these)
```

## Work-order format (`art/queue/issue-NNN.jsonl`, one JSON per line)
```json
{ "id": "i001-p07-k1",
  "prompt": "<scene + per-bot recipe + locked comic-book house style>",
  "refs": ["cards/portraits/spike_Gemini_Generated.png",
           "cards/portraits/stomp_Gemini_Generated.png"],
  "w": 1248, "h": 832 }
```
- **`id`** — the panel's address (issue·page·panel). The output filename MUST be `<id>.png`.
- **`refs`** — **repo-relative** portrait paths (0–3). Prepend your local clone path to get
  absolute `ImagePaths` for `generate_image` so the bots come out on-model.
- **`prompt`** — full prompt; already includes the house style and "leave space for speech
  bubbles, no text" (bubbles are added by the renderer, so **do not draw text**).

## What the scheduled task does each run (suggested cron `*/30 * * * *`)
1. `git pull` the `thebardchat/mega-crew-stories` clone on pulsar.
2. For each `art/queue/issue-NNN.jsonl`, for each line:
   - If `art/out/issue-NNN/<id>.png` **already exists → skip** (idempotent; don't redo).
   - Else `generate_image(prompt, ImagePaths=[<clone>/<ref> ...], width=w, height=h)`
     and save to `art/out/issue-NNN/<id>.png`.
3. If any new images were written: `git add art/out && git commit -m "art: issue NNN" && git push`.

That's it. The Pi watcher (`art_rerender.py`) sees the pushed images and republishes the
issue's page-turner with the drawn panels + speech bubbles automatically.

## Notes
- **On-model is the whole point** — always pass the `refs` as reference images.
- Images carry Google **SynthID** (invisible) — keep it; the comic credits the AI art properly.
- Safe to re-run anytime; existing panels are skipped, so it only ever fills gaps.

## Generalized lanes (2026-06-19)

The farm now consumes **every** `art/queue/*.jsonl` (not just `issue-*`). Each
queue file's stem is its output folder, so new asset streams need NO farm change:

| Queue file              | Output folder          | What it is                         |
|-------------------------|------------------------|------------------------------------|
| `issue-NNN.jsonl`       | `art/out/issue-NNN/`   | comic panels (per issue)           |
| `covers.jsonl`          | `art/out/covers/`      | hero covers, `iNNN-cover.png`      |
| `portraits-v2.jsonl`    | `art/out/portraits-v2/`| upgraded character portraits (planned) |
| `social.jsonl`          | `art/out/social/`      | banners / og:image / emotes (**LIVE**) |

Same per-line format (`id`, `prompt`, `refs`, `w`, `h`), same idempotent
skip-existing rule, same `git add art/out && push`. Covers use a portrait
canvas (832×1248); the renderer shows the drawn cover behind the title the moment
it lands, falling back to the text cover until then.

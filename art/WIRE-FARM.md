# Wire the farm — saga scenes, not portraits

Two lanes. Do not smash them.

| Lane | Script | Reads | Writes |
|---|---|---|---|
| Short episodes | `shanebrain-core/scripts/generate_scene_images.py` | `episodes/manifest.json` | `episodes/scenes/epNNN_*.webp` + R2 |
| **Saga book** | **NEW** `shanebrain-core/scripts/generate_saga_scenes.py` | `saga/issue-NNN-*.json` `panel.art` | `art/out/issue-NNN/iNNN-pPP-kK.jpg` + rerun `bard_render.py` |

013 look = saga lane. Episode farm stays hero-shots for shorts.

## On the Pi

1. `scripts/generate_saga_scenes.py` is on `shanebrain-core` main.
2. Patched `bard_render.py` (jpg + artwell + balloons under) is this repo.
3. Cron:

```
*/15 * * * * flock -n /tmp/generate_saga_scenes.lock python3 /mnt/shanebrain-raid/shanebrain-core/scripts/generate_saga_scenes.py
```

4. Smoke:

```
python3 scripts/generate_saga_scenes.py --issue 13 --dry-run
python3 scripts/generate_saga_scenes.py --issue 13 --no-git --cap 4
```

## Budget

`mega/status/hf_image_budget.json`
- `saga_today` max 20
- `images_today` max 40 (episodes + saga combined)

Backfill 001–012 at 20/day ≈ a month. `--issue N` first.

## Law

- Camera = `panel.art` (the beat). Not a bust.
- No text in the drawing.
- Balloons live in HTML under the frame.
- Cron on the Pi is the last switch.

# Repair Pass 6 — Continuous kinetic layers (motion graphics)

## Why this pass exists
The user confirmed that the latest video renders, but its visual language is still too static: one central illustration appears with a simple pop and remains almost unchanged for several seconds. This is a renderer-level problem, not a transcript-specific issue.

## Changes
- `v2_renderer.py`
  - Added `_draw_kinetic_motion_overlays()` to the common scene-rendering path so every scene receives restrained animated accents: rotating arc segments, three orbiting nodes/trails, moving side streaks, and a travelling locator cue.
  - Motion placement is adapted to the selected template's focal region (`concept_icon`, `big_number`, `phone_reel_mockup`, `before_after`, etc.) to reduce collisions with the main headline.
  - The semantic icon and its speech-derived labels remain the scene's primary content; the new motion layers are accents, not replacements for semantic visuals.
  - Kept the pre-render rate at 6 fps deliberately to avoid doubling the already high memory footprint of cached 960x940 RGB scene frames. The final output is still rendered at 30 fps; the moving layers update at 6 fps and the stage/camera transform remains smooth.
- `tests/test_repair_regressions.py`
  - Added a regression test proving the common renderer produces substantially different frames at different animation times even when no external SVG asset is available.

## Verification
- Python syntax compilation: all `.py` files passed.
- Regression suite: 26/26 passed.
- Motion-frame pixel-difference test: passed at t=0.0, 0.5, and 1.5 seconds.
- Full end-to-end render in the hosted app: not available from this environment; user must run a new sample to assess visual result and memory/performance in the deployment runtime.

## Limitations / next pass
This pass improves continuous movement in the common renderer, but it does not yet create fully distinct, scene-specific multi-object choreography or guarantee social-media reach. Next, inspect the new hosted render and its scene plan; then prioritize per-template animated elements (e.g. waveform reveal for audio, animated chart for social metrics, staged checkmarks for steps) and visual variety while keeping speech/visual alignment and safe zones validated.

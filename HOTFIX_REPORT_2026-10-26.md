# Hotfix report — 2026-10-26

## Root cause addressed
- `v2_director.generate_scene_plan` had a special branch that substituted a fixed storyboard for one known marketing script and also when transcription returned no words. This could make unrelated uploads inherit the same scenes.
- `build_stage1_kinetic_only_plan` contained a hard-coded script and timings.
- Unknown topics fell back to `hourglass_deadline`, making the clock visual appear even when the topic was unrelated.
- `vector_lottie_engine.classify_scene_stage_architecture` defaulted unknown speech to the clock/time scene and hard-coded marketing copy.
- `v2_renderer` assigned reference families scene-by-scene and selected the visual archetype from template alone, ignoring the semantic visual query.

## Changes made
- Scene plans now derive from the words transcribed from the current upload; no fixed sample script is substituted.
- If transcription returns no words, the pipeline stops with a clear error instead of rendering unrelated fallback visuals.
- Unknown topics use text-derived semantic hints and a neutral semantic-concept stage rather than an automatic clock.
- Generic supporting cards are derived from the actual scene text instead of invented percentages/claims.
- The v2 renderer keeps one reference design family per video and prefers the scene's semantic visual query when choosing a hero visual.
- Added regression tests for fixed-script removal, unknown-topic fallback, and hourglass fallback.

## Validation performed
- `python -m py_compile *.py`: passed.
- `python -m unittest test_suite_all -v`: 9 tests passed.

## Important limitation
These checks validate code behavior and basic rendering integration; they do not prove that every possible topic will receive a perfect, photorealistic semantic visual. A fresh end-to-end render using an unrelated test audio/video is still required before calling the output production-ready.

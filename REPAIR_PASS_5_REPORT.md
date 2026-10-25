# Repair Pass 5 — Root-cause fixes

## Input audited
- User output: `7584.mp4`
- Duration: 31.766667 seconds.
- FFmpeg `silencedetect=noise=-38dB:d=0.8`: no detected interval longer than 0.8 seconds.
- Visual review of a contact sheet showed repeated phone compositions, semantically fragmented scenes, generic/mismatched headlines, CTA text bleeding from the previous feature, and headline overflow.

## Code changes
- `v2_director.py`: Arabic orthography/clitic normalization; context-based scene segmentation; explicit CTA boundaries; contiguous speech-grounded headlines; scene-specific grounded headline selection; reduced repeated phone compositions; optional Gemini semantic director with hard validation.
- `v2_validator.py`: rejects ungrounded headlines and rebuilds them from spoken words instead of generic fallback copy.
- `v2_renderer.py`: measured two-line wrapping for long Arabic headlines; distinct, grounded labels for silence-removal before/after scenes.
- `v2_run.py`: passes ASR provider keys/model/dialect through to transcription and Gemini key to semantic planning.
- `app.py`: passes existing UI keys and transcription settings into the v2 pipeline.
- `tests/test_repair_regressions.py`: added regression tests for Arabic clitics, scene boundaries, CTA isolation, Gemini output guards, headline bounds, and key propagation.

## Verification
- Python compile: 27/27 passed.
- Regression/integration tests: 25/25 passed.
- Latest uploaded video silence check: no interval >=0.8s at -38dB.
- Mocked Gemini invalid-output test: passed.
- Full end-to-end video render: not run in this sandbox because `faster_whisper` is not installed here. The new ZIP still requires a fresh render in the platform runtime before visual quality can be certified.

## Next
Deploy this exact pass-5 ZIP, render a new unrelated sample (not only the prior topic), then inspect the generated `scene_plan.json`, audio guard report, and contact sheet. Keep prior tests green before the next repair.

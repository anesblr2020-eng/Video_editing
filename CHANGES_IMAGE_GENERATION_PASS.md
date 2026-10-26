# Change Log — Semantic Image Generation Pass

1. Added `scene_image_generator.py` for optional Gemini image generation per semantic scene.
2. Added prompt-hash cache, 9:16 image normalization, incremental JSON persistence, graceful failure and generation report.
3. Wired image generation into `v2_run.py` after scene planning and attached successful image paths to scene records.
4. Wired generated image backgrounds into the render loop with restrained motion/opacity while preserving existing foreground motion graphics.
5. Added Arabic setup and limitation notes in `NEXT_STEP_IMAGE_GENERATION_AR.md`.
6. Validation: all Python modules compile; local no-key smoke test passes. Real provider generation/video integration remains unverified without a valid API key.

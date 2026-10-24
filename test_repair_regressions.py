# -*- coding: utf-8 -*-
"""Regression tests for the staged repair pass 1."""
import ast
import sys
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import v2_director
import v2_transcribe


class RepairPass1Tests(unittest.TestCase):
    def test_reference_like_transcript_is_not_replaced_by_hardcoded_script(self):
        words = [
            {"word": "مشكل", "start": 0.0, "end": 0.3},
            {"word": "الوقت", "start": 0.31, "end": 0.65},
            {"word": "إيديتينغ", "start": 0.66, "end": 1.0},
            {"word": "الصوت", "start": 1.01, "end": 1.35},
            {"word": "بسهولة", "start": 1.36, "end": 1.8},
        ]
        result = v2_director.generate_scene_plan(words, duration=2.0)
        speech = " ".join(scene["speech"] for scene in result["scenes"])
        self.assertIn("إيديتينغ", speech)
        self.assertIn("الصوت", speech)
        self.assertNotIn("السلام عليكم", speech)
        self.assertNotIn("رابط التسجيل في أسفل الفيديو", speech)

    def test_empty_transcript_does_not_invent_scenes(self):
        result = v2_director.generate_scene_plan([], duration=5.0)
        self.assertEqual(result["scenes"], [])
        self.assertTrue(any("No transcript words" in item for item in result["validator_audit_log"]))

    def test_no_dead_duplicate_style_three_branch(self):
        source = (BASE / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(
            node for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == "run_selected_pipeline"
        )
        self.assertNotIn("elif style_name == STYLE_OPTIONS[3]", ast.get_source_segment(source, function))
        self.assertIn("style_name in (STYLE_OPTIONS[0], STYLE_OPTIONS[3])", ast.get_source_segment(source, function))

    def test_product_ad_uses_existing_gemini_key_parameter(self):
        source = (BASE / "app.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        function = next(node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef) and node.name == "run_selected_pipeline")
        segment = ast.get_source_segment(source, function)
        product_branch = segment.split("elif style_name == STYLE_OPTIONS[1]:", 1)[1].split("elif style_name == STYLE_OPTIONS[2]:", 1)[0]
        self.assertIn("gemini_api_key=gemini_key", product_branch)
        self.assertNotIn("gemini_api_key=gemini_api_key", product_branch)


    def test_stage1_plan_uses_uploaded_transcript_not_reference_copy(self):
        words = [
            {"word": "جرب", "start": 0.0, "end": 0.4},
            {"word": "تطبيق", "start": 0.4, "end": 0.8},
            {"word": "التصميم", "start": 0.8, "end": 1.2},
            {"word": "الجديد", "start": 1.2, "end": 1.6},
        ]
        scenes = v2_director.build_stage1_kinetic_only_plan(words, duration=2.0)
        text = " ".join(scene["speech"] for scene in scenes)
        self.assertIn("تطبيق", text)
        self.assertIn("التصميم", text)
        self.assertNotIn("السلام عليكم", text)
        self.assertNotIn("رابط التسجيل في أسفل الفيديو", text)

    def test_failed_asr_does_not_fabricate_reference_transcript(self):
        with tempfile.NamedTemporaryFile(suffix=".wav") as audio:
            audio.write(b"placeholder audio bytes")
            audio.flush()
            with patch("transcriber.transcribe_audio", return_value=[]):
                words, alerts = v2_transcribe.transcribe_any_audio_or_video(audio.name, duration=3.0)
        self.assertEqual(words, [])
        self.assertEqual(alerts, [])

    def test_long_silence_filter_reduces_synthetic_pause(self):
        import shutil
        import subprocess
        import v2_run
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not installed")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "source.wav"
            cleaned = Path(tmp) / "cleaned.wav"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=2",
                "-f", "lavfi", "-i", "sine=frequency=660:duration=1",
                "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[out]",
                "-map", "[out]", "-ac", "1", "-ar", "44100", str(source)
            ], check=True)
            report = v2_run._trim_long_silence_ffmpeg(str(source), str(cleaned))
            self.assertEqual(report["status"], "trimmed")
            self.assertGreater(report["removed_seconds"], 1.0)
            self.assertLess(report["cleaned_duration_seconds"], report["original_duration_seconds"])


    def test_semantic_svg_motion_changes_between_animation_frames(self):
        import json
        import numpy as np
        import v2_renderer
        if v2_renderer.search_and_fetch_web_vectors is None or v2_renderer.render_recolored_svg_motion_canvas is None:
            self.skipTest("vector engine unavailable")
        with (BASE / "themes.json").open(encoding="utf-8") as handle:
            theme = json.load(handle)["themes"]["obsidian_gold"]
        scene = {
            "template": "concept_icon", "speech": "وتنحي الصمت من الفيديو",
            "keywords": ["تنحي الصمت", "من الفيديو"],
            "visual_query": "scissors waveform silence", "start": 0.0, "end": 2.0,
        }
        svgs = v2_renderer.search_and_fetch_web_vectors(
            scene_text_ar=scene["speech"], fallback_topic=scene["visual_query"],
            max_assets=1, allow_network=False,
        )
        self.assertTrue(svgs)
        frame_a, _ = v2_renderer.render_scene_card_and_measure_dom(scene, theme, animation_t=0.0, motion_svg=svgs[0])
        frame_b, _ = v2_renderer.render_scene_card_and_measure_dom(scene, theme, animation_t=0.5, motion_svg=svgs[0])
        self.assertGreater(int(np.abs(frame_a.astype("int16") - frame_b.astype("int16")).sum()), 1000)


    def test_non_cta_final_scene_does_not_invent_call_to_action(self):
        words = [
            {"word": "المنصة", "start": 0.0, "end": 0.4},
            {"word": "تعالج", "start": 0.4, "end": 0.8},
            {"word": "الصوت", "start": 0.8, "end": 1.2},
            {"word": "وتحذف", "start": 1.2, "end": 1.6},
            {"word": "الصمت", "start": 1.6, "end": 2.0},
        ]
        result = v2_director.generate_scene_plan(words, duration=2.2)
        self.assertTrue(result["scenes"])
        self.assertFalse(any(scene["template"] == "cta_end" for scene in result["scenes"]))
        all_keywords = " ".join(" ".join(scene.get("keywords", [])) for scene in result["scenes"])
        self.assertNotIn("الرابط في الأسفل", all_keywords)
        self.assertNotIn("ابدأ الآن", all_keywords)

    def test_big_number_template_has_no_hardcoded_zero_dinar_claim(self):
        source = (BASE / "v2_renderer.py").read_text(encoding="utf-8")
        self.assertNotIn("صفر دينار مجاناً", source)
        self.assertIn("supporting labels must also come from the scene", source)

    def test_theme_rotation_is_persisted_after_successful_pipeline(self):
        source = (BASE / "app.py").read_text(encoding="utf-8")
        self.assertIn('mem_st["style_rotation_counter"] = rot_c + 1', source)
        self.assertIn("save_evolution_memory(mem_st)", source)

    def test_scene_headlines_are_semantic_and_not_generic_media_fragment(self):
        words = [
            {"word": "راك", "start": 0.0, "end": 0.25},
            {"word": "تعاني", "start": 0.25, "end": 0.55},
            {"word": "من", "start": 0.55, "end": 0.7},
            {"word": "مشكل", "start": 0.7, "end": 1.0},
            {"word": "الوقت", "start": 1.0, "end": 1.3},
            {"word": "والسوشيال", "start": 1.4, "end": 1.7},
            {"word": "ميديا", "start": 1.7, "end": 2.0},
            {"word": "عموما", "start": 2.0, "end": 2.3},
            {"word": "يموتوا", "start": 2.3, "end": 2.6},
        ]
        result = v2_director.generate_scene_plan(words, duration=3.0)
        headlines = [k for scene in result["scenes"] for k in scene.get("keywords", [])]
        self.assertNotIn("ميديا عموما", headlines)
        self.assertGreaterEqual(len(set(headlines)), min(2, len(headlines)))

    def test_free_offer_does_not_force_big_number_template(self):
        words = [
            {"word": "الخدمة", "start": 0.0, "end": 0.3},
            {"word": "مجانية", "start": 0.3, "end": 0.6},
            {"word": "بالذكاء", "start": 0.6, "end": 0.9},
            {"word": "الاصطناعي", "start": 0.9, "end": 1.2},
        ]
        result = v2_director.generate_scene_plan(words, duration=1.5)
        self.assertFalse(any(s["template"] == "big_number" and not s.get("numbers") for s in result["scenes"]))

    def test_free_word_is_not_misclassified_as_a_spoken_number(self):
        from v2_validator import extract_spoken_numbers
        self.assertEqual(extract_spoken_numbers("الخدمة مجانية بالذكاء الاصطناعي"), [])

    def test_platform_scene_uses_self_contained_visual_without_storyboard(self):
        words = [
            {"word": "كاين", "start": 0.0, "end": 0.2},
            {"word": "منصة", "start": 0.2, "end": 0.5},
            {"word": "اسمها", "start": 0.5, "end": 0.8},
            {"word": "إيديتينغ", "start": 0.8, "end": 1.2},
        ]
        result = v2_director.generate_scene_plan(words, duration=1.5)
        self.assertTrue(result["scenes"])
        self.assertFalse(any(s["template"] == "fullscreen_image" and not s.get("image_path") for s in result["scenes"]))

    def test_ai_mention_alone_does_not_create_steps_flow(self):
        words = [
            {"word": "تنحي", "start": 0.0, "end": 0.2},
            {"word": "الصمت", "start": 0.2, "end": 0.5},
            {"word": "بالذكاء", "start": 0.5, "end": 0.8},
            {"word": "الاصطناعي", "start": 0.8, "end": 1.2},
        ]
        result = v2_director.generate_scene_plan(words, duration=1.5)
        self.assertFalse(any(s["template"] == "steps_flow" for s in result["scenes"]))

    def test_renderer_strips_unsupported_graphic_symbols(self):
        import v2_renderer
        safe = v2_renderer._safe_graphic_text("فيديو تاع قاع 🧨□□ إيديتينغ")
        self.assertNotIn("🧨", safe)
        self.assertNotIn("□", safe)
        self.assertIn("فيديو", safe)

    def test_long_silence_detector_catches_trailing_silence(self):
        import shutil
        import subprocess
        import v2_run
        if not shutil.which("ffmpeg"):
            self.skipTest("ffmpeg not installed")
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "tone_then_silence.wav"
            subprocess.run([
                "ffmpeg", "-y", "-v", "error",
                "-f", "lavfi", "-i", "sine=frequency=440:duration=0.8",
                "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono:d=1.2",
                "-filter_complex", "[0:a][1:a]concat=n=2:v=0:a=1[out]",
                "-map", "[out]", "-ac", "1", "-ar", "44100", str(source)
            ], check=True)
            intervals = v2_run._detect_long_silence(str(source), threshold_db=-35, min_seconds=0.8)
            self.assertTrue(intervals)
            self.assertGreaterEqual(intervals[-1]["duration"], 0.8)
            self.assertGreaterEqual(intervals[-1]["start"], 0.7)

    def test_post_render_guard_caps_duration_and_checks_silence(self):
        import v2_run
        source = (BASE / "v2_run.py").read_text(encoding="utf-8")
        self.assertIn("_ensure_render_matches_clean_audio", source)
        self.assertIn("long_silences_after_render", source)
        self.assertIn("فشل فحص الصوت النهائي", source)


if __name__ == "__main__":
    unittest.main()

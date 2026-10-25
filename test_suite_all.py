# -*- coding: utf-8 -*-
"""
test_suite_all.py — حزمة الاختبارات الشاملة في الجذر مباشرة (Zero Subfolders for GitHub Upload)
"""
import os
import sys
import shutil
import unittest
import numpy as np

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)


class TestReferenceDirectingIntegration(unittest.TestCase):
    def test_01_no_v2_hijack_in_motion_text(self):
        with open(os.path.join(BASE_DIR, "motion_text.py"), "r", encoding="utf-8") as f:
            src = f.read()
        fn_body = src.split("def create_kinetic_typography_video(")[1]
        self.assertNotIn("run_v2_pipeline_programmatic", fn_body[:600], "create_kinetic_typography_video must not hijack to flat v2_renderer!")

    def test_02_light_and_editorial_backgrounds_enabled(self):
        from style_evolution_brain import PRO_STUDIO_STYLE_FAMILIES
        for fam_id in ("honeyy_highkey_3d_ui", "divyansh_kinetic_contrast", "morningstar_editorial_25d"):
            self.assertIn(fam_id, PRO_STUDIO_STYLE_FAMILIES)
            pal = PRO_STUDIO_STYLE_FAMILIES[fam_id]["unified_palette"]
            self.assertTrue(pal.get("is_light_bg"), f"{fam_id} must have is_light_bg=True")

    def test_03_two_clause_semantic_decomposition(self):
        from smart_analyzer import decompose_scene_clauses_and_verb
        res = decompose_scene_clauses_and_verb(
            "المجهر الرقمي يرصد الخلايا بدقة تتفوق على الفحص اليدوي",
            scene_index=2,
            total_scenes=5,
        )
        self.assertTrue(res["clause_a"])
        self.assertTrue(res["clause_b"])
        self.assertEqual(res["visual_verb"], "dual_viewport_reveal")
        self.assertTrue(0.35 <= res["pivot_u"] <= 0.66)

    def test_04_multi_state_frame_progression(self):
        from motion_text import render_single_scene_canvas
        from style_evolution_brain import PRO_STUDIO_STYLE_FAMILIES

        sc_meta = {
            "index": 0,
            "step_number": 1,
            "total_scenes_count": 5,
            "start": 0.0,
            "end": 3.0,
            "text": "سجل المريض الطبي يتحول فوراً عبر وكيل التشخيص الذكي",
            "clause_a": "سجل المريض الطبي",
            "clause_b": "وكيل التشخيص الذكي",
            "pivot_u": 0.46,
            "visual_verb": "anchor_and_displace",
            "archetype": "hero_smartphone_reels",
            "visual_subject": "artificial-intelligence",
            "concept_title": "سجل المريض الطبي",
            "kpi_value": "99.4% دقة",
            "sub_items": ["تحليل المؤشرات الحيوية", "فحص التاريخ الوراثي", "إنذار مبكر ذكي"],
            "scene_style_spec": {
                "style_family_id": "honeyy_highkey_3d_ui",
                "design_family": "honeyy_highkey_3d_ui",
                "has_giant_bg_numbers": True,
                "header_style": "none_clean",
                "headline_style": "editorial_contrast_serif",
                "palette": dict(PRO_STUDIO_STYLE_FAMILIES["honeyy_highkey_3d_ui"]["unified_palette"]),
            },
        }
        img_state_a = render_single_scene_canvas(
            scene_meta=sc_meta,
            active_word="سجل",
            scene_words=["سجل", "المريض", "الطبي"],
            active_word_idx=0,
            word_local_progress=0.5,
            scene_progress=0.20,
            global_t=0.6,
            total_duration=15.0,
            audio_level=0.8,
            width=540,
            height=960,
            bg_cache={},
        )
        img_state_b = render_single_scene_canvas(
            scene_meta=sc_meta,
            active_word="الذكي",
            scene_words=["وكيل", "التشخيص", "الذكي"],
            active_word_idx=2,
            word_local_progress=0.5,
            scene_progress=0.82,
            global_t=2.4,
            total_duration=15.0,
            audio_level=0.8,
            width=540,
            height=960,
            bg_cache={},
        )
        arr_a = np.array(img_state_a.convert("RGB"), dtype=np.float32)
        arr_b = np.array(img_state_b.convert("RGB"), dtype=np.float32)
        mad = float(np.mean(np.abs(arr_a - arr_b)))
        self.assertGreater(mad, 8.0, f"State A -> State B must evolve significantly within scene (got MAD={mad:.2f})")
        mean_luma = float(np.mean(arr_a))
        self.assertGreater(mean_luma, 180.0, f"High-key studio canvas must be bright (got luma={mean_luma:.1f})")

    def test_05_auto_sfx_generation_without_assets_folder(self):
        from sound_designer import ensure_builtin_sfx_pack
        tmp_sfx = "/tmp/_test_auto_sfx_pack"
        if os.path.exists(tmp_sfx):
            shutil.rmtree(tmp_sfx)
        ensure_builtin_sfx_pack(tmp_sfx, sr=24000)
        self.assertTrue(os.path.isdir(os.path.join(tmp_sfx, "1_click")))
        self.assertTrue(os.path.isdir(os.path.join(tmp_sfx, "6_whooch")))


    def test_06_arabic_darija_semantic_clause_splitting(self):
        from transcriber import (
            split_words_into_micro_scenes,
            FORBIDDEN_SCENE_END_WORDS,
            FORBIDDEN_SCENE_START_WORDS,
        )
        sample_text = (
            "السلام عليكم على بالي بلي راك تعاني من مشكل تاع الوقت "
            "وما عندكش الوقت باش تمونتي لي فيديو وتطلعهم في السوشيال "
            "ومخلي الحساب تاعك في انستغرام والسوشيال ميديا عموما يموتوا "
            "وانت ما على بالكش بلي كاين منصة اسمها فيديو ايديتينغ "
            "تقدر تمونتي لك لي فيديو تاعك بالموشن جرافيك "
            "وبالمونتاج العادي وتنقي الصوت "
            "وتمونتي الصمت من الفيديو وهذا بشكل مجاني وبالاي أي "
            "التسجيل في أسفل الفيديو"
        )
        words = []
        t = 0.0
        for tok in sample_text.split():
            words.append({"word": tok, "start": round(t, 3), "end": round(t + 0.40, 3), "probability": 0.95})
            t += 0.43

        scenes = split_words_into_micro_scenes(words, max_words_per_scene=6, max_duration_per_scene=2.8)
        self.assertGreaterEqual(len(scenes), 5)
        # الجملة الافتتاحية يجب أن تبقى جملة دلالية متكاملة ولا تنقطع عند "على" أو "تاع"
        self.assertIn("على بالي بلي راك تعاني من مشكل تاع الوقت", scenes[0]["text"])
        for sc in scenes:
            w_list = sc.get("words", [])
            self.assertTrue(len(w_list) >= 2, f"Scene too short: {sc['text']}")
            first_w = w_list[0]["word"].strip("،,.!؟?")
            last_w = w_list[-1]["word"].strip("،,.!؟?")
            if not (last_w in {"أي", "اي"} and len(w_list) >= 2 and w_list[-2]["word"] in {"وبالاي", "بالاي"}):
                self.assertNotIn(last_w, FORBIDDEN_SCENE_END_WORDS, f"Forbidden end word '{last_w}' in scene: {sc['text']}")
            self.assertNotIn(first_w, FORBIDDEN_SCENE_START_WORDS, f"Forbidden start word '{first_w}' in scene: {sc['text']}")


if __name__ == "__main__":
    unittest.main()

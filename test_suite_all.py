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

    def test_00_no_hardcoded_reference_script_fallback(self):
        import inspect
        import v2_director
        src = inspect.getsource(v2_director.generate_scene_plan)
        self.assertNotIn("is_reference_script", src)
        self.assertIn("build_dynamic_scene_plan_for_any_words", src)
        self.assertIn("if not words", src)

    def test_00b_unknown_topic_does_not_default_to_clock(self):
        from vector_lottie_engine import classify_scene_stage_architecture
        result = classify_scene_stage_architecture("المجهر يقيس حركة الجزيئات داخل العينة", 0, 4)
        self.assertEqual(result["stage_type"], "semantic_concept")
        self.assertIn("المجهر", result["clause_a"] + result["clause_b"])

    def test_00c_unknown_topic_does_not_get_hourglass_query(self):
        from v2_director import _pick_unique_visual_query
        q = _pick_unique_visual_query("المجهر يقيس حركة الجزيئات داخل العينة", [], 0)
        self.assertTrue(q.startswith("semantic_concept"), q)
        self.assertNotEqual(q, "hourglass_deadline")

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



    def test_07_v5_interactions_api_routing_and_image_extraction(self):
        import io
        import json
        import base64
        import tempfile
        from PIL import Image
        import scene_image_generator as sig
        from visual_scene_pipeline import write_visual_plan

        # إنشاء صورة اختبار حقيقية 512x512 وتحويلها إلى بايتات PNG
        im = Image.new("RGB", (512, 768), (24, 140, 190))
        buf = io.BytesIO()
        im.save(buf, format="PNG")
        valid_png_bytes = buf.getvalue()
        valid_b64 = base64.b64encode(valid_png_bytes).decode("ascii")

        # 1. التحقق من أن Nano Banana 2.1 يصنف كنموذج Interactions API ويُمنع إرساله إلى generateContent
        self.assertTrue(sig.is_interactions_api_model("models/gemini-nano-banana-2.1"))
        self.assertFalse(sig.is_interactions_api_model("gemini-2.5-flash-image"))
        with self.assertRaises(ValueError):
            sig.invoke_generate_content_image_api(
                prompt="test",
                api_key="dummy_key",
                model_name="models/gemini-nano-banana-2.1"
            )

        # 2. محاكاة كائن SDK مع client.interactions.create والتحقق من استدعائه بالمعاملات المطلوبة
        calls_recorded = []

        class DummyInteractions:
            def create(self, **kwargs):
                calls_recorded.append(kwargs)
                return {
                    "outputs": [
                        {
                            "type": "image",
                            "inline_data": {
                                "mime_type": "image/png",
                                "data": valid_b64,
                            }
                        }
                    ]
                }

        class DummyClient:
            def __init__(self):
                self.interactions = DummyInteractions()

        with tempfile.TemporaryDirectory() as tmpdir:
            scenes = [
                {"start": 0.0, "end": 3.0, "speech": "شخص ينتظر وصول طلب التوصيل أمام منزله", "keywords": ["انتظار طلب", "توصيل"], "intent": "hook"},
                {"start": 3.0, "end": 6.0, "speech": "منصة ذكية تختصر ساعات المونتاج", "keywords": ["منصة مونتاج", "ذكاء اصطناعي"], "intent": "solution"},
            ]
            paths = write_visual_plan(tmpdir, "obsidian_gold", {"colors": {"primary": "#10B981"}}, scenes)
            rep1 = sig.generate_scene_images(
                out_dir=tmpdir,
                prompts_path=paths["scene_image_prompts"],
                api_key="test_key_do_not_persist",
                sdk_client=DummyClient(),
            )
            self.assertEqual(rep1["generated"], 2)
            self.assertEqual(rep1["cached"], 0)
            self.assertEqual(rep1["failed"], 0)
            self.assertEqual(len(calls_recorded), 2)
            self.assertEqual(calls_recorded[0]["model"], "models/gemini-nano-banana-2.1")
            self.assertEqual(calls_recorded[0]["generation_config"], {"image_config": {"image_size": "1K"}})
            self.assertEqual(calls_recorded[0]["response_modalities"], ["image", "text"])
            self.assertIn("ينتظر", calls_recorded[0]["input"])

            # 3. اختبار الكاش: إعادة التشغيل على نفس المجلد يجب أن تسترجع الصورتين من الكاش (0 طلبات جديدة)
            calls_recorded.clear()
            rep2 = sig.generate_scene_images(
                out_dir=tmpdir,
                prompts_path=paths["scene_image_prompts"],
                api_key="test_key_do_not_persist",
                sdk_client=DummyClient(),
            )
            self.assertEqual(rep2["generated"], 0)
            self.assertEqual(rep2["cached"], 2)
            self.assertEqual(rep2["failed"], 0)
            self.assertEqual(len(calls_recorded), 0, "Cached images must not trigger redundant API requests!")

    def test_08_text_only_response_and_429_handling_never_fakes_success(self):
        import json
        import tempfile
        import scene_image_generator as sig
        from visual_scene_pipeline import write_visual_plan

        # 1. استجابة نصية فقط بدون صورة يجب أن تفشل ولا تسجل كصورة ناجحة
        img_b, txt_s, note = sig.extract_image_bytes_from_response({
            "candidates": [{"content": {"parts": [{"text": "I cannot generate an image right now."}]}}]
        })
        self.assertIsNone(img_b)
        self.assertIn("text_only_response_no_image", note)

        # 2. اختبار تصنيف خطأ 429 ومنع استهلاك محاولات متكررة لنفس النموذج المستنفد عبر المشاهد
        attempt_log = []

        class QuotaExhaustedInteractions:
            def create(self, **kwargs):
                attempt_log.append(("interactions", kwargs["model"]))
                raise RuntimeError("HTTP 429 RESOURCE_EXHAUSTED: Quota exceeded for quota metric 'GenerateRequests' and limit: 0 for project gen-lang-client-0998760040")

        class QuotaExhaustedClient:
            def __init__(self):
                self.interactions = QuotaExhaustedInteractions()

        class QuotaExhaustedSession:
            def post(self, url, **kwargs):
                attempt_log.append(("rest", url))
                class FakeResp:
                    status_code = 429
                    text = '{"error": {"code": 429, "message": "Quota exceeded for quota metric and limit: 0", "status": "RESOURCE_EXHAUSTED"}}'
                return FakeResp()

        with tempfile.TemporaryDirectory() as tmpdir:
            scenes = [
                {"start": 0.0, "end": 3.0, "speech": "المشهد الأول للاختبار", "keywords": ["اختبار 1"], "intent": "hook"},
                {"start": 3.0, "end": 6.0, "speech": "المشهد الثاني للاختبار", "keywords": ["اختبار 2"], "intent": "body"},
                {"start": 6.0, "end": 9.0, "speech": "المشهد الثالث للاختبار", "keywords": ["اختبار 3"], "intent": "outro"},
            ]
            paths = write_visual_plan(tmpdir, "obsidian_gold", {"colors": {"primary": "#10B981"}}, scenes)
            rep = sig.generate_scene_images(
                out_dir=tmpdir,
                prompts_path=paths["scene_image_prompts"],
                api_key="test_key_429",
                sdk_client=QuotaExhaustedClient(),
                session=QuotaExhaustedSession(),
            )
            self.assertEqual(rep["generated"], 0)
            self.assertEqual(rep["cached"], 0)
            self.assertEqual(rep["failed"], 3)
            # كل نموذج في السلسلة يجب أن يُجرَّب مرة واحدة فقط في المشهد الأول ثم يُعزل في المشهدين الثاني والثالث!
            self.assertEqual(len(attempt_log), len(rep["model_chain"]), "Exhausted 429 models must not be retried on subsequent scenes!")
            with open(paths["scene_image_prompts"], "r", encoding="utf-8") as pf:
                saved_prompts = json.load(pf)
            for sc_item in saved_prompts["scenes"]:
                self.assertIsNone(sc_item["image_path"])
                self.assertEqual(sc_item["generation_status"], "failed")


if __name__ == "__main__":
    unittest.main()

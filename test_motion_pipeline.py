# -*- coding: utf-8 -*-
"""
اختبارات تضمن عدم رجوع أخطاء الموشن جرافيك. التشغيل:  python -m unittest discover -s tests -v
كل اختبار يقابل خطأً حقيقياً ظهر في فيديو studio_output_1792242246.mp4.
"""
import os, sys, subprocess, tempfile, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from darija_lexicon import extract_spoken_numbers, build_whisper_prompt, norm_ar
from context_engine import (
    build_storyboard, qa_report, is_grounded, echoes_caption, validate_card,
    apply_text_fix, speech_coverage, merge_words_by_time, detect_role, detect_topics, CAPTION_HOLD_SEC,
)


def mk_scene(text, start):
    ws = text.split()
    words = [{"word": w, "start": round(start + i * 0.35, 3), "end": round(start + i * 0.35 + 0.33, 3)} for i, w in enumerate(ws)]
    return {"text": text, "start": start, "end": words[-1]["end"], "words": words}


def scenes_from(sentences):
    out, t = [], 0.0
    for s in sentences:
        sc = mk_scene(s, t)
        out.append(sc)
        t = sc["end"] + 0.1
    return out, t


# مجموعة جمل متنوعة بالدارجة الجزائرية (ليست من فيديو واحد)
CORPUS = [
    "السلام عليكم كاين بزاف ناس يعانيوا مشكل تاع الكونت انستقرام ولا كونت تيك توك",
    "واش راكم خاوتي اليوم نحكيلكم على كيفاش تربحو دراهم من الفيديوهات",
    "اصبر اصبر هذا الكابل فيه سيبور تيليفون ومغلف بالقماش ما يتقطعش",
    "التوصيل متوفر ل 58 ولاية والدفع عند الاستلام اكموندي من الرابط",
    "راني نخدم باترون في شركة ومكانش وقت نقرا الكورس",
    "الطبخ بالدارجة وصفة الكسكسي بالخضرة بزاف سهلة",
    "علاش المشكل هذا يطرا ديجا مرتين في الأسبوع",
    "ندير مونتاج للفيديوهات والريلز بالذكاء الاصطناعي",
]
FABRICATED = ["17", "عاماً", "مؤسس", "المؤسس", "4K", "60FPS", "+300%", "300", "100%", "10x"]


class TestNoFabrication(unittest.TestCase):
    def test_no_invented_claims_any_sentence(self):
        """الخطأ: ظهور «17 عاماً / المؤسس الشاب» لمجرد جملة سلام."""
        for sent in CORPUS:
            sc, dur = scenes_from([sent])
            sb = build_storyboard(sc, sent, total_duration=dur)
            blob = " ".join(str(sb[0].get(k, "")) for k in ("badge_label", "concept_title", "kpi_value", "kpi_label"))
            for bad in FABRICATED:
                if bad.lower() in sent.lower():
                    continue
                self.assertNotIn(bad.lower(), blob.lower(), f"اختلاق «{bad}» في: {sent} -> {blob}")
            self.assertEqual(qa_report(sb, sent), [])

    def test_llm_hallucination_is_rejected(self):
        """LLM يعطي معلومات مختلقة -> يجب أن تُستبدل تلقائياً."""
        sent = "السلام عليكم كاين بزاف ناس يعانيوا مشكل تاع الكونت انستقرام"
        sc, dur = scenes_from([sent])

        def bad_llm(prompt, system_prompt, max_tokens=0):
            return '[{"i":0,"role":"hook","topic":"مؤسس شاب","badge":"تعريف بالمؤسس 17 سنة","concept":"المؤسس الشاب","kpi_value":"17 عاماً","kpi_label":"انطلاقة ريادية","scene_type":"creator_profile"}]'

        sb = build_storyboard(sc, sent, llm_fn=bad_llm, total_duration=dur)
        blob = " ".join(str(sb[0][k]) for k in ("badge_label", "concept_title", "kpi_value", "kpi_label"))
        for bad in ("17", "مؤسس", "المؤسس", "عاماً"):
            self.assertNotIn(bad, blob)
        self.assertEqual(qa_report(sb, sent), [])

    def test_llm_good_output_is_used(self):
        sent = "نوريكم كيفاش تحمي الكونت تاعك من الهاكرز"
        sc, dur = scenes_from([sent])

        def good_llm(prompt, system_prompt, max_tokens=0):
            return '```json\n[{"i":0,"role":"solution","topic":"حماية الحساب","badge":"حماية حسابك","concept":"أمان الحساب","kpi_value":"","kpi_label":"خطوات بسيطة","scene_type":"solution_check"}]\n```'

        sb = build_storyboard(sc, sent, llm_fn=good_llm, total_duration=dur)
        self.assertEqual(sb[0]["scene_type"], "solution_check")
        self.assertEqual(sb[0]["concept_title"], "أمان الحساب")

    def test_echo_of_caption_rejected(self):
        sent = "كاين بزاف ناس يعانيوا مشكل تاع الكونت"
        self.assertTrue(echoes_caption("كاين بزاف ناس يعانيوا", sent))
        self.assertFalse(echoes_caption("حساب إنستغرام", sent))

    def test_spoken_numbers_are_kept(self):
        sc, dur = scenes_from(["التوصيل متوفر ل 58 ولاية"])
        sb = build_storyboard(sc, "التوصيل متوفر ل 58 ولاية", total_duration=dur)
        self.assertIn("58", sb[0]["kpi_value"])
        n = extract_spoken_numbers("عمري سبعتاش سنة")
        self.assertEqual((n[0]["value"], n[0]["unit"]), (17, "سنة"))
        self.assertFalse(is_grounded("17 عاماً", "السلام عليكم"))
        self.assertTrue(is_grounded("17 سنة", "عمري سبعتاش سنة"))


class TestDarijaUnderstanding(unittest.TestCase):
    def test_roles(self):
        self.assertEqual(detect_role("كاين بزاف ناس يعانيوا مشكل", 1, 5), "problem")
        self.assertEqual(detect_role("اكموندي من الرابط تحت", 4, 5), "cta")
        self.assertEqual(detect_role("نوريلكم الحل ساهل", 2, 5), "solution")

    def test_topics_darija_and_french_loanwords(self):
        self.assertEqual(detect_topics("الكونت تاعي تهكر")[0][0], "social_account")
        self.assertEqual(detect_topics("ليفريزون لباب الدار")[0][0], "delivery")
        self.assertEqual(detect_topics("نمنتج الفيديوهات")[0][0], "video_editing")

    def test_account_instagram_context(self):
        sent = "كاين بزاف ناس يعانيوا مشكل تاع الكونت انستقرام"
        sc, dur = scenes_from([sent])
        sb = build_storyboard(sc, sent, total_duration=dur)[0]
        self.assertIn("حساب", sb["concept_title"])
        self.assertIn("إنستغرام", sb["concept_title"])
        self.assertEqual(sb["role"], "problem")

    def test_neighbor_context_for_short_connectors(self):
        sents = ["كاين بزاف ناس يعانيوا مشكل", "تاع الكونت انستقرام"]
        sc, dur = scenes_from(sents)
        sb = build_storyboard(sc, " ".join(sents), total_duration=dur)
        self.assertIn("إنستغرام", sb[0]["concept_title"] + sb[0]["kpi_label"])

    def test_whisper_prompt_is_neutral(self):
        pr = build_whisper_prompt()
        self.assertFalse(any(ch.isdigit() for ch in pr), "الموجّه يجب ألا يحتوي أرقاماً")
        for name in ("أنس", "17", "58", "سيبور", "اكموندي"):
            self.assertNotIn(name, pr)


class TestCaptionTiming(unittest.TestCase):
    def test_caption_never_stuck(self):
        """الخطأ: الكابشن «فيديو وطلع» تجمد ~16 ثانية بينما المتحدث يتكلم."""
        s1 = mk_scene("ندير فيديو وطلع", 0.0)
        s2 = mk_scene("وبعدها نكمل", 20.0)  # فجوة 19 ثانية بلا تفريغ
        sb = build_storyboard([s1, s2], "ندير فيديو وطلع وبعدها نكمل", total_duration=22.0)
        self.assertLessEqual(sb[0]["caption_until"] - sb[0]["speech_end"], CAPTION_HOLD_SEC + 1e-6)
        self.assertGreaterEqual(sb[0]["visual_end"], 20.0)  # الرسمة تبقى، الكابشن يختفي
        self.assertEqual([i for i in qa_report(sb, "ندير فيديو وطلع وبعدها نكمل") if "stuck" in i], [])


class TestCoverageGuard(unittest.TestCase):
    def test_detects_lost_speech(self):
        words = [{"word": "a", "start": i * 0.4, "end": i * 0.4 + 0.35} for i in range(10)]  # 4 ثواني فقط
        rep = speech_coverage(words, [(0.0, 27.0)])
        self.assertLess(rep["coverage"], 0.3)
        self.assertTrue(rep["gaps"] and rep["gaps"][0][0] < 5 and rep["gaps"][0][1] > 26)

    def test_full_coverage_ok(self):
        words = [{"word": "a", "start": i * 0.5, "end": i * 0.5 + 0.45} for i in range(20)]
        self.assertGreater(speech_coverage(words, [(0.0, 10.0)])["coverage"], 0.95)

    def test_merge_no_duplicates(self):
        base = [{"word": "a", "start": 0.0, "end": 1.0}]
        extra = [{"word": "a2", "start": 0.1, "end": 0.9}, {"word": "b", "start": 2.0, "end": 2.5}]
        self.assertEqual([w["word"] for w in merge_words_by_time(base, extra)], ["a", "b"])

    def test_refill_with_mock_engine(self):
        import transcriber as T
        wav = os.path.join(tempfile.gettempdir(), "tone_test.wav")
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=300:duration=20", "-ar", "16000", "-ac", "1", wav], check=True)
        orig_chunk, orig_dev = T._transcribe_chunk_words, T.get_optimal_device_settings
        T._transcribe_chunk_words = lambda *a, **k: [{"word": f"x{i}", "start": i * 0.9, "end": i * 0.9 + 0.8} for i in range(10)]
        T.get_optimal_device_settings = lambda: ("cpu", "int8")
        try:
            words = [{"word": "a", "start": i * 0.4, "end": i * 0.4 + 0.35} for i in range(8)]
            out = T._ensure_coverage(wav, words, "test")
            self.assertGreater(T.get_last_coverage_report()["coverage"], 0.85)
            self.assertGreater(len(out), len(words))
        finally:
            T._transcribe_chunk_words, T.get_optimal_device_settings = orig_chunk, orig_dev


class TestTextFixAndFit(unittest.TestCase):
    def test_text_fix_keeps_timing(self):
        words = [{"word": "المو", "start": 1.0, "end": 1.4}, {"word": "تاعنا", "start": 1.4, "end": 1.9}]
        new, ch = apply_text_fix(words, "المونتاج تاعنا")
        self.assertTrue(ch)
        self.assertEqual((new[0]["start"], new[0]["end"]), (1.0, 1.4))

    def test_text_fix_rejects_new_numbers_or_length_change(self):
        words = [{"word": "عمري", "start": 0, "end": 1}, {"word": "كبير", "start": 1, "end": 2}]
        self.assertFalse(apply_text_fix(words, "عمري 17")[1])
        self.assertFalse(apply_text_fix(words, "عمري كبير جدا")[1])

    def test_text_fits_inside_card(self):
        from PIL import Image, ImageDraw
        import motion_text as M
        d = ImageDraw.Draw(Image.new("RGBA", (10, 10)))
        for txt in ["المؤسس الشاب المؤسس الشاب المؤسس", "بنية تقنية حديثة ومتكاملة للغاية جداً"]:
            fitted, f = M.fit_text_to_width(d, txt, 150, 40, 14)
            self.assertLessEqual(M.measure_arabic_text(d, fitted, f)[0], 150)


class TestRenderSmoke(unittest.TestCase):
    def test_all_scene_types_render_and_caption_hides(self):
        import motion_text as M
        from context_engine import RENDERABLE_SCENE_TYPES
        sc, dur = scenes_from(["كاين بزاف ناس يعانيوا مشكل تاع الكونت انستقرام"])
        base = build_storyboard(sc, sc[0]["text"], total_duration=dur)[0]
        for st in sorted(RENDERABLE_SCENE_TYPES):
            meta = dict(base, scene_type=st)
            im = M.render_single_scene_canvas(meta, "كاين", base["word_strings"], 0, .5, .5, 1.0, dur, .8, 540, 960, {})
            self.assertEqual(im.size, (540, 960), st)


if __name__ == "__main__":
    unittest.main(verbosity=2)

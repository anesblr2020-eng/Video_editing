# -*- coding: utf-8 -*-
"""Regression tests for the staged repair pass 1."""
import ast
import sys
import unittest
from pathlib import Path

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))

import v2_director


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

    def test_theme_rotation_is_persisted_after_successful_pipeline(self):
        source = (BASE / "app.py").read_text(encoding="utf-8")
        self.assertIn('mem_st["style_rotation_counter"] = rot_c + 1', source)
        self.assertIn("save_evolution_memory(mem_st)", source)


if __name__ == "__main__":
    unittest.main()

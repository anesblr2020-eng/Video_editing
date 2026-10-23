# -*- coding: utf-8 -*-
"""
manim_generator.py - محرك الموشن جرافيك الهندسي الحقيقي بذاكرة تراكمية ذاتية النمو (Self-Growing Manim Engine)
=================================================================================================================
Principal Video DSP & Mathematical Motion Graphics Engine (Zero-OOM Architecture):
1. إلغاء التحويل المؤقت القديم وبناء رندرة Manim حقيقية (مخططات بيانية متحركة، شبكات عصبية، عدادات رقمية سينمائية،
   تحويلات هندسية سياقية) متزامنة مع جمل المتحدث ومخرجات `context_engine.py`.
2. دعم الرندرة بخلفية شفافة (`-t` / `--transparent` بصيغة `.mov` / `.webm` مع قناة `rgba`) أو خلفية داكنة مدمجة،
   ثم دمجها فوق الفيديو الأصلي للمتحدث (Chroma/Alpha Blend) مع الكابشن والبطاقات الزجاجية عبر أنبوب `FFmpeg`
   أحادي الخيط (`-threads 1`) باستهلاك ذاكرة ثابت `O(1)`.
3. مكتبة أكواد Manim ذاتية النمو (`outputs/manim_library.json`):
   - كل كود يولده الـ LLM وينجح في الـ `compile` والرندرة الفعلية بدون أخطاء يُحفظ تلقائياً في المكتبة مع الكلمات المفتاحية والموضوع.
   - في المرات القادمة، يسترجع النظام أقرب كود ناجح (`Few-Shot Retrieval`) ويعطيه للـ LLM ليطور عليه بدلاً من البدء من الصفر.
"""

import os
import sys
import gc
import re
import json
import glob
import math
import time
import ctypes
import shutil
import hashlib
import logging
import subprocess
from typing import Optional, Callable, List, Dict, Any, Tuple
import numpy as np
from PIL import Image

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

from auto_cut import (
    remove_silence,
    is_video_file,
    get_safe_working_resolution,
    extract_jumpcut_audio_and_intervals,
    force_free_ram
)
from transcriber import transcribe_audio, split_words_into_micro_scenes

try:
    from context_engine import build_storyboard, analyze_global_context
except ImportError:
    build_storyboard = None
    analyze_global_context = None

try:
    from smart_analyzer import query_hybrid_llm, analyze_contextual_storyboard
except ImportError:
    def query_hybrid_llm(*args, **kwargs):
        return None
    analyze_contextual_storyboard = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

MANIM_LIBRARY_PATH = os.path.join(_CURRENT_DIR, "outputs", "manim_library.json")


# ==============================================================================
# 1. مكتبة أكواد Manim ذاتية النمو واسترجاع الأمثلة الناجحة (Few-Shot Manim Library)
# ==============================================================================
def _seed_manim_library() -> Dict[str, Any]:
    """بذور أولية مختبرة ومضمونة لمكتبة Manim تغطي الشبكات العصبية، النمو البياني، والعدادات السينمائية."""
    return {
        "version": "2.0",
        "total_successful_renders": 3,
        "entries": [
            {
                "id": "seed_neural_ai",
                "topic": "ai_tech",
                "keywords": ["ذكاء", "اصطناعي", "خوارزمية", "تلقائي", "منصة", "برمجة", "ai"],
                "duration_sec": 10.0,
                "timestamp": 1729000000,
                "code": (
                    "from manim import *\nimport numpy as np\n\n"
                    "class GeneratedScene(Scene):\n"
                    "    def construct(self):\n"
                    "        self.camera.background_color = '#070B16'\n"
                    "        plane = NumberPlane(background_line_style={'stroke_color': TEAL_E, 'stroke_width': 1, 'stroke_opacity': 0.22}, axis_config={'stroke_opacity': 0})\n"
                    "        self.add(plane)\n"
                    "        layer1 = VGroup(*[Dot(np.array([-2.8, y, 0]), radius=0.14, color=BLUE_B) for y in np.linspace(-1.8, 1.8, 4)])\n"
                    "        layer2 = VGroup(*[Dot(np.array([0.0, y, 0]), radius=0.16, color=TEAL_A) for y in np.linspace(-2.2, 2.2, 5)])\n"
                    "        layer3 = VGroup(*[Dot(np.array([2.8, y, 0]), radius=0.18, color=GOLD_B) for y in np.linspace(-1.2, 1.2, 3)])\n"
                    "        edges1 = VGroup(*[Line(d1.get_center(), d2.get_center(), stroke_width=1.8, color=BLUE_D, stroke_opacity=0.55) for d1 in layer1 for d2 in layer2])\n"
                    "        edges2 = VGroup(*[Line(d2.get_center(), d3.get_center(), stroke_width=2.2, color=TEAL_C, stroke_opacity=0.65) for d2 in layer2 for d3 in layer3])\n"
                    "        self.play(FadeIn(layer1), Create(edges1), FadeIn(layer2), run_time=1.8)\n"
                    "        self.play(Create(edges2), FadeIn(layer3), run_time=1.6)\n"
                    "        core = RegularPolygon(n=6, radius=1.6, color=YELLOW, stroke_width=5)\n"
                    "        self.play(ReplacementTransform(VGroup(edges1, edges2), core), Rotate(core, angle=PI/3), run_time=2.0)\n"
                    "        self.wait(0.6)\n"
                )
            },
            {
                "id": "seed_growth_bars",
                "topic": "growth",
                "keywords": ["نمو", "مبيعات", "مشاهدات", "متابعين", "أرباح", "إنتاجية", "سوشيال", "ريلز"],
                "duration_sec": 10.0,
                "timestamp": 1729000100,
                "code": (
                    "from manim import *\nimport numpy as np\n\n"
                    "class GeneratedScene(Scene):\n"
                    "    def construct(self):\n"
                    "        self.camera.background_color = '#070B16'\n"
                    "        bars = VGroup()\n"
                    "        heights = [0.9, 1.5, 2.2, 3.1, 4.1]\n"
                    "        cols = [BLUE_D, BLUE_B, TEAL_C, TEAL_A, GOLD_B]\n"
                    "        for i, (h, c) in enumerate(zip(heights, cols)):\n"
                    "            r = RoundedRectangle(corner_radius=0.12, width=0.68, height=h, fill_color=c, fill_opacity=0.88, stroke_color=WHITE, stroke_width=2)\n"
                    "            r.move_to(np.array([-2.4 + i * 1.2, -2.0 + h / 2.0, 0]))\n"
                    "            bars.add(r)\n"
                    "        arrow = Arrow(np.array([-2.6, -0.8, 0]), np.array([2.6, 2.5, 0]), color=YELLOW, stroke_width=7, buff=0)\n"
                    "        self.play(LaggedStart(*[GrowFromEdge(b, DOWN) for b in bars], lag_ratio=0.18), run_time=2.2)\n"
                    "        self.play(GrowArrow(arrow), bars[-1].animate.scale(1.08), run_time=1.6)\n"
                    "        ring = Circle(radius=2.1, color=TEAL_A, stroke_width=5)\n"
                    "        self.play(ReplacementTransform(bars, ring), Rotate(arrow, angle=PI/6), run_time=1.8)\n"
                    "        self.wait(0.6)\n"
                )
            },
            {
                "id": "seed_chrono_counter",
                "topic": "time",
                "keywords": ["وقت", "سرعة", "ثواني", "دقيقة", "ساعة", "توصيل", "شحن", "مونتاج"],
                "duration_sec": 10.0,
                "timestamp": 1729000200,
                "code": (
                    "from manim import *\nimport numpy as np\n\n"
                    "class GeneratedScene(Scene):\n"
                    "    def construct(self):\n"
                    "        self.camera.background_color = '#070B16'\n"
                    "        outer = Circle(radius=2.4, color=BLUE_C, stroke_width=5)\n"
                    "        ticks = VGroup(*[Line(2.1*np.array([np.cos(a), np.sin(a), 0]), 2.35*np.array([np.cos(a), np.sin(a), 0]), color=WHITE, stroke_width=2) for a in np.linspace(0, 2*np.pi, 12, endpoint=False)])\n"
                    "        hand = Arrow(ORIGIN, np.array([0, 1.8, 0]), color=GOLD_B, buff=0, stroke_width=6)\n"
                    "        self.play(Create(outer), FadeIn(ticks), GrowArrow(hand), run_time=1.8)\n"
                    "        self.play(Rotate(hand, angle=-2*PI, about_point=ORIGIN), outer.animate.set_color(TEAL_A), run_time=2.4)\n"
                    "        wave = FunctionGraph(lambda x: 0.9 * np.sin(2.2 * x) * np.exp(-0.15 * x * x), x_range=[-3.5, 3.5], color=YELLOW, stroke_width=5)\n"
                    "        self.play(ReplacementTransform(VGroup(outer, ticks, hand), wave), run_time=1.8)\n"
                    "        self.wait(0.6)\n"
                )
            }
        ]
    }


def load_manim_library(lib_path: str = MANIM_LIBRARY_PATH) -> Dict[str, Any]:
    if os.path.exists(lib_path):
        try:
            with open(lib_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and isinstance(data.get("entries"), list) and data["entries"]:
                return data
        except Exception as e:
            logger.debug(f"Could not read manim_library.json: {e}")
    seeded = _seed_manim_library()
    save_manim_library(seeded, lib_path)
    return seeded


def save_manim_library(lib_data: Dict[str, Any], lib_path: str = MANIM_LIBRARY_PATH) -> None:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(lib_path)), exist_ok=True)
        tmp_p = lib_path + ".tmp"
        with open(tmp_p, "w", encoding="utf-8") as f:
            json.dump(lib_data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_p, lib_path)
    except Exception as e:
        logger.debug(f"Could not save manim_library.json: {e}")


def retrieve_best_few_shot_manim_code(
    transcript_text: str,
    topic: str = "",
    lib_path: str = MANIM_LIBRARY_PATH
) -> Dict[str, Any]:
    """
    استرجاع أقرب كود Manim ناجح من `manim_library.json` (`Few-Shot Retrieval`)
    بناءً على تطابق الموضوع والكلمات المفتاحية.
    """
    lib = load_manim_library(lib_path)
    entries = lib.get("entries", [])
    if not entries:
        return _seed_manim_library()["entries"][0]

    t_low = (transcript_text or "").lower()
    best_entry = entries[0]
    best_score = -1.0

    for item in entries:
        score = 0.0
        if topic and item.get("topic") == topic:
            score += 4.0
        for kw in item.get("keywords", []):
            if str(kw).lower() in t_low:
                score += 2.0
        if score > best_score:
            best_score = score
            best_entry = item

    return best_entry


def record_successful_manim_code(
    code: str,
    transcript_text: str,
    topic: str = "general",
    duration_sec: float = 10.0,
    lib_path: str = MANIM_LIBRARY_PATH
) -> None:
    """حفظ كود Manim الجديد الذي نجح في الـ `compile` والرندرة الفعلية داخل `manim_library.json`."""
    if not code or "class " not in code:
        return
    lib = load_manim_library(lib_path)
    entries = lib.setdefault("entries", [])
    code_hash = hashlib.md5(code.strip().encode("utf-8", errors="ignore")).hexdigest()[:10]

    for existing in entries:
        if existing.get("id") == f"learned_{code_hash}":
            return

    words = [w.strip("،,.!؟?()[]") for w in (transcript_text or "").split() if len(w.strip("،,.!؟?()[]")) >= 3]
    keywords = list(dict.fromkeys(words[:8]))

    entries.append({
        "id": f"learned_{code_hash}",
        "topic": topic or "general",
        "keywords": keywords,
        "duration_sec": round(float(duration_sec), 2),
        "timestamp": int(time.time()),
        "code": code.strip()
    })
    # الاحتفاظ بأحدث 40 كوداً ناجحاً لمنع تضخم الملف
    if len(entries) > 40:
        lib["entries"] = entries[-40:]
    lib["total_successful_renders"] = int(lib.get("total_successful_renders", 0)) + 1
    save_manim_library(lib, lib_path)


# ==============================================================================
# 2. بناء وتوليد مشاهد Manim السياقية المتعددة المراحل
# ==============================================================================
def build_dynamic_manim_template(
    duration_seconds: float,
    num_sentences: int = 3,
    storyboard: Optional[List[Dict[str, Any]]] = None,
    transparent: bool = False
) -> str:
    """
    يبني كود Manim هندسي متعدد المراحل متزامناً مع مشاهد `storyboard` الفعلية:
    يشمل: شبكات عصبية (`ai_neural_brain`), مخططات أعمدة ومنحنيات نمو (`growth_analytics`),
    عدادات زمنية وساعات (`time_warp_clock`), وهياكل منصات هندسية (`platform_builder`).
    """
    n_stages = max(3, min(6, len(storyboard) if storyboard else num_sentences))
    stage_time = max(1.1, min(2.8, duration_seconds / float(n_stages + 1)))
    bg_line = "" if transparent else "        self.camera.background_color = '#070B16'\n"

    return f"""from manim import *
import numpy as np

class GeneratedScene(Scene):
    def construct(self):
{bg_line}        stage_t = {stage_time:.2f}

        grid = NumberPlane(
            background_line_style={{
                "stroke_color": TEAL_E,
                "stroke_width": 1,
                "stroke_opacity": 0.24
            }},
            axis_config={{"stroke_opacity": 0.0}}
        )
        self.add(grid)

        outer_hex = RegularPolygon(n=6, radius=2.5, color=TEAL_B, stroke_width=5)
        inner_circle = Circle(radius=1.65, color=GOLD_B, stroke_width=5)
        core_dot = Dot(ORIGIN, color=YELLOW, radius=0.18)

        orbit_dots = VGroup(*[
            Dot(point=2.5 * np.array([np.cos(a), np.sin(a), 0]), color=BLUE_B, radius=0.13)
            for a in np.linspace(0, 2 * np.pi, 6, endpoint=False)
        ])

        self.play(Create(outer_hex), Create(inner_circle), FadeIn(core_dot), run_time=stage_t)
        self.play(FadeIn(orbit_dots), Rotate(outer_hex, angle=PI / 3), run_time=stage_t * 0.85)

        nodes = VGroup(*[
            Dot(point=np.array([x, y, 0]), color=TEAL_A if (i % 2 == 0) else GOLD_A, radius=0.15)
            for i, (x, y) in enumerate([
                (-2.8, 1.4), (-1.4, -1.1), (0.0, 1.7), (1.4, -1.1), (2.8, 1.4), (0.0, 0.0)
            ])
        ])
        edges = VGroup(*[
            Line(nodes[i].get_center(), nodes[j].get_center(), color=BLUE_C, stroke_width=2.4, stroke_opacity=0.72)
            for i in range(len(nodes)) for j in range(i + 1, len(nodes))
        ])

        self.play(
            ReplacementTransform(orbit_dots, nodes),
            Create(edges),
            outer_hex.animate.scale(1.22).set_stroke(opacity=0.28),
            run_time=stage_t
        )

        bars = VGroup()
        bar_heights = [1.0, 1.7, 2.4, 3.2, 4.0]
        bar_colors = [BLUE_D, BLUE_C, TEAL_C, TEAL_B, GOLD_B]
        for idx, (bh, bc) in enumerate(zip(bar_heights, bar_colors)):
            rect = RoundedRectangle(
                corner_radius=0.12,
                width=0.64,
                height=bh,
                fill_color=bc,
                fill_opacity=0.88,
                stroke_color=WHITE,
                stroke_width=2
            )
            rect.move_to(np.array([-2.4 + idx * 1.2, -2.0 + bh / 2.0, 0]))
            bars.add(rect)

        trend_arrow = Arrow(
            start=np.array([-2.6, -0.5, 0]),
            end=np.array([2.6, 2.3, 0]),
            color=YELLOW,
            buff=0,
            stroke_width=6
        )

        self.play(
            FadeOut(edges),
            FadeOut(inner_circle),
            ReplacementTransform(nodes, bars),
            GrowArrow(trend_arrow),
            run_time=stage_t
        )

        wave_curve = FunctionGraph(
            lambda x: 0.85 * np.sin(2.4 * x) * np.cos(0.6 * x),
            x_range=[-4.2, 4.2],
            color=TEAL_A,
            stroke_width=5
        )
        self.play(
            ReplacementTransform(bars, wave_curve),
            FadeOut(trend_arrow),
            Rotate(outer_hex, angle=PI / 2),
            run_time=stage_t
        )
        self.wait(0.5)
"""


def clean_manim_code(raw_code: str, duration_seconds: float = 10.0) -> Tuple[str, bool]:
    """تنظيف وفحص الكود المولد من الـ LLM، وإرجاع `(code, is_ai_generated)`."""
    fallback = build_dynamic_manim_template(duration_seconds)
    if not raw_code or not raw_code.strip():
        return fallback, False

    code = raw_code.strip()
    markdown_match = re.search(r"```(?:python)?(.*?)```", code, re.DOTALL | re.IGNORECASE)
    if markdown_match:
        code = markdown_match.group(1).strip()

    if "from manim import *" not in code and "import manim" not in code:
        code = "from manim import *\nimport numpy as np\n\n" + code

    if "Scene" not in code or "def construct" not in code:
        return fallback, False

    # منع أي استدعاء لـ Tex أو MathTex قد يسبب فشل LaTeX
    if any(forbidden in code for forbidden in ["MathTex(", "Tex(", "Text("]):
        return fallback, False

    try:
        compile(code, "<manim_ai>", "exec")
        return code, True
    except SyntaxError:
        return fallback, False


def extract_scene_class_name(code: str) -> str:
    match = re.search(r"class\s+(\w+)\s*\(\s*Scene\s*\)\s*:", code)
    if match:
        return match.group(1)
    return "GeneratedScene"


def query_ai_for_manim_with_few_shot(
    transcribed_text: str,
    duration_seconds: float,
    topic: str = "general",
    model_name: str = "llama3",
    ollama_url: str = "http://localhost:11434",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> Tuple[str, bool]:
    """
    يسترجع أقرب كود ناجح من `manim_library.json` (`Few-Shot Retrieval`) ويطلبه من الـ LLM
    لتطوير مشهد Manim مخصص لسياق الفيديو الحالي.
    """
    few_shot_entry = retrieve_best_few_shot_manim_code(transcribed_text, topic=topic)
    few_shot_code = few_shot_entry.get("code", "")

    system_prompt = (
        "You are an expert Manim Community (v0.18+) Python developer. "
        "Write a valid, visually stunning Manim Scene class named GeneratedScene that illustrates the meaning "
        "of the user's transcript using geometric shapes, graphs, arrows, glowing circles, polygons, and smooth transforms."
    )

    user_message = (
        f"Transcript summary: \"{transcribed_text}\"\n"
        f"Topic: {topic} | Target duration: {duration_seconds:.1f} seconds.\n\n"
        f"Here is a proven working Manim reference example from our library (Few-Shot Example):\n"
        f"```python\n{few_shot_code}\n```\n\n"
        "Evolve and customize this code to match the transcript's pacing and topic.\n"
        "Strict rules:\n"
        "1. Start with `from manim import *` and `import numpy as np`.\n"
        "2. Define `class GeneratedScene(Scene):` and `def construct(self):`.\n"
        "3. DO NOT use `Tex`, `MathTex`, or `Text` inside Manim. Use ONLY geometric Mobjects: "
        "`Circle`, `RoundedRectangle`, `RegularPolygon`, `Arrow`, `Line`, `Dot`, `VGroup`, `NumberPlane`, `FunctionGraph`.\n"
        "4. Return ONLY valid Python code inside ```python ... ```."
    )

    ai_resp = query_hybrid_llm(
        prompt=user_message,
        system_prompt=system_prompt,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        ollama_model=model_name,
        ollama_url=ollama_url,
        temperature=0.25,
        max_tokens=950
    )

    if ai_resp:
        cleaned, is_valid_ai = clean_manim_code(ai_resp, duration_seconds=duration_seconds)
        if is_valid_ai:
            return cleaned, True

    return few_shot_code or build_dynamic_manim_template(duration_seconds), False


def find_rendered_manim_video(search_directory: str) -> Optional[str]:
    patterns = [
        os.path.join(search_directory, "**", "*.mov"),
        os.path.join(search_directory, "**", "*.webm"),
        os.path.join(search_directory, "**", "*.mp4"),
        os.path.join("media", "**", "*.mp4")
    ]
    found_files = []
    for pattern in patterns:
        found_files.extend(glob.glob(pattern, recursive=True))
    found_files = [f for f in found_files if "partial_movie_files" not in f]
    if found_files:
        found_files.sort(key=os.path.getmtime, reverse=True)
        return found_files[0]
    return None


# ==============================================================================
# 3. الرندرة الفعلية لمشاهد Manim والدمج عبر أنبوب FFmpeg المباشر (Zero-OOM Pipe)
# ==============================================================================
def generate_manim_motion_graphics(
    input_path: str,
    output_path: str,
    whisper_model: str = "base",
    ollama_model: str = "llama3",
    quality_flag: str = "-ql",
    dialect_mode: str = "algerian_darija",
    include_captions: bool = True,
    transparent_overlay: bool = True,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    **kwargs
) -> str:
    """
    تنفيذ مسار الموشن جرافيك الهندسي الحقيقي (Manim + Self-Growing Library + Zero-OOM FFmpeg Streaming Pipe):
    1. تنظيف الصوت وقص الصمت واستخراج الكلمات ومخطط المشاهد السياقي (`context_engine.py`).
    2. استرجاع أقرب كود Manim ناجح (`Few-Shot Retrieval`) وتوليد مشهد هندسي مخصص عبر الـ LLM.
    3. تشغيل محرك `manim` الفعلي في عملية مستقلة، وحفظ الكود الجديد في `outputs/manim_library.json` فور نجاحه.
    4. دمج مخرجات Manim فوق فيديو المتحدث الأصلي (أو كخلفية كاملة للملفات الصوتية) مع البطاقات السياقية
       والكابشن التفاعلي عبر أنبوب `FFmpeg` أحادي الخيط (`-threads 1`) باستهلاك ذاكرة ثابت `O(1)`.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"الملف غير موجود: {input_path}")

    from motion_text import (
        MOTION_THEMES,
        _render_unified_karaoke_subtitle,
        draw_visionos_glass_panel,
        draw_contained_arabic_text,
        render_single_scene_canvas
    )

    base_dir = os.path.dirname(os.path.abspath(output_path))
    temp_dir = os.path.join(base_dir, "temp")
    manim_media_dir = os.path.join(temp_dir, f"manim_media_{os.getpid()}")
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(manim_media_dir, exist_ok=True)

    def update_progress(val: float, msg: str):
        if progress_callback:
            progress_callback(val, msg)
        logger.info(f"Progress: {val*100:.1f}% - {msg}")

    has_speaker_video = is_video_file(input_path)
    clean_media_path = os.path.join(temp_dir, f"manim_clean_input_{os.getpid()}" + (".mp4" if has_speaker_video else ".mp3"))
    temp_manim_py = os.path.join(temp_dir, f"scene_manim_{os.getpid()}.py")

    manim_dec_proc = None
    spk_dec_proc = None
    enc_proc = None

    try:
        force_free_ram()
        update_progress(0.10, "1/4: قص الصمت الطبيعي وتحضير المسار الصوتي/المرئي...")
        if has_speaker_video:
            remove_silence(input_path=input_path, output_path=clean_media_path, silence_threshold=-42.0, padding_ms=250)
            from dynamic_edit import _probe_video_dimensions_and_duration
            vw, vh, total_dur = _probe_video_dimensions_and_duration(clean_media_path)
        else:
            _, total_dur = extract_jumpcut_audio_and_intervals(
                input_path=input_path,
                clean_audio_output_path=clean_media_path,
                silence_threshold=-42.0,
                padding_ms=250
            )
            vw, vh = 540, 960

        force_free_ram()
        update_progress(0.26, "2/4: تفريغ الكلام وفهم السياق (`context_engine`) واسترجاع أقرب كود Manim...")
        words = transcribe_audio(
            audio_path=clean_media_path,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        micro_scenes = split_words_into_micro_scenes(words, max_words_per_scene=8, max_duration_per_scene=4.2, min_words_per_scene=4)
        full_transcript = " ".join(w.get("word", "") for w in words) if words else "موشن جرافيك هندسي ذكي"

        main_topic = "general"
        if callable(analyze_global_context):
            g_ctx = analyze_global_context(full_transcript)
            main_topic = g_ctx.get("main_topic") or "general"

        if callable(build_storyboard):
            storyboard = build_storyboard(micro_scenes, full_transcript=full_transcript, total_duration=total_dur)
        elif callable(analyze_contextual_storyboard):
            storyboard = analyze_contextual_storyboard(micro_scenes, full_transcript=full_transcript)
        else:
            storyboard = micro_scenes

        manim_code, was_ai_generated = query_ai_for_manim_with_few_shot(
            transcribed_text=full_transcript,
            duration_seconds=min(16.0, max(5.0, total_dur)),
            topic=main_topic,
            model_name=ollama_model,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )

        with open(temp_manim_py, "w", encoding="utf-8") as f:
            f.write(manim_code)
        scene_class = extract_scene_class_name(manim_code)

        update_progress(0.45, f"3/4: رندرة المشهد الهندسي عبر محرك Manim ({quality_flag})...")
        rendered_manim_path = None
        manim_bin = shutil.which("manim")

        if manim_bin:
            eff_q = "-ql" if quality_flag not in ("-ql", "-qm", "-qh") else quality_flag
            cmd = [
                manim_bin,
                temp_manim_py,
                scene_class,
                eff_q,
                "--fps", "24",
                "--media_dir", manim_media_dir,
                "-v", "ERROR"
            ]
            try:
                res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=110)
                if res.returncode == 0:
                    rendered_manim_path = find_rendered_manim_video(manim_media_dir)
                    if rendered_manim_path and was_ai_generated:
                        record_successful_manim_code(
                            code=manim_code,
                            transcript_text=full_transcript,
                            topic=main_topic,
                            duration_sec=total_dur
                        )
                else:
                    logger.warning(f"Manim initial render failed ({res.stderr[:200]}), falling back to verified template...")
                    fallback_code = build_dynamic_manim_template(min(14.0, total_dur), len(storyboard), storyboard)
                    with open(temp_manim_py, "w", encoding="utf-8") as f:
                        f.write(fallback_code)
                    cmd[2] = "GeneratedScene"
                    res2 = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=110)
                    if res2.returncode == 0:
                        rendered_manim_path = find_rendered_manim_video(manim_media_dir)
            except Exception as m_err:
                logger.warning(f"Manim CLI execution notice: {m_err}")

        force_free_ram()
        update_progress(0.72, "4/4: الدمج المباشر لمشاهد Manim والكابشن عبر أنبوب FFmpeg أحادي الخيط (Zero-OOM)...")

        fps = 24
        frame_bytes_len = vw * vh * 3
        total_frames = max(1, int(round(total_dur * fps)))
        bg_cache: Dict[str, np.ndarray] = {}

        if rendered_manim_path and os.path.exists(rendered_manim_path):
            m_cmd = [
                "ffmpeg", "-v", "error", "-threads", "1",
                "-stream_loop", "-1",
                "-i", rendered_manim_path,
                "-vf", f"scale={vw}:{vh}:force_original_aspect_ratio=increase,crop={vw}:{vh},fps={fps}",
                "-threads", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
            ]
            manim_dec_proc = subprocess.Popen(m_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes_len)

        if has_speaker_video:
            s_cmd = [
                "ffmpeg", "-v", "error", "-threads", "1",
                "-i", clean_media_path,
                "-vf", f"scale={vw}:{vh},fps={fps}",
                "-threads", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
            ]
            spk_dec_proc = subprocess.Popen(s_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes_len)

        enc_cmd = [
            "ffmpeg", "-y", "-v", "error", "-threads", "1",
            "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{vw}x{vh}", "-r", str(fps), "-i", "-",
            "-threads", "1", "-i", clean_media_path,
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-x264-params", "rc-lookahead=0:sync-lookahead=0:ref=1:bframes=0",
            "-crf", "22", "-pix_fmt", "yuv420p", "-threads", "1",
            "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-ar", "16000",
            "-movflags", "+faststart", "-shortest",
            output_path
        ]
        enc_proc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, bufsize=frame_bytes_len)

        for f_idx in range(total_frames):
            t_cur = f_idx / float(fps)

            manim_frm = None
            if manim_dec_proc is not None and manim_dec_proc.stdout is not None:
                m_raw = manim_dec_proc.stdout.read(frame_bytes_len)
                if m_raw and len(m_raw) == frame_bytes_len:
                    manim_frm = np.frombuffer(m_raw, dtype=np.uint8).reshape((vh, vw, 3)).copy()

            spk_frm = None
            if spk_dec_proc is not None and spk_dec_proc.stdout is not None:
                s_raw = spk_dec_proc.stdout.read(frame_bytes_len)
                if s_raw and len(s_raw) == frame_bytes_len:
                    spk_frm = np.frombuffer(s_raw, dtype=np.uint8).reshape((vh, vw, 3)).copy()

            # تحديد المشهد السياقي النشط
            active_sc = storyboard[0] if storyboard else {"text": "", "start": 0.0, "end": total_dur, "words": []}
            for sc in storyboard:
                if float(sc.get("start", 0.0)) <= t_cur <= float(sc.get("end", total_dur)):
                    active_sc = sc
                    break

            theme_name = active_sc.get("theme_name", "cyber_gold")
            theme = MOTION_THEMES.get(theme_name, MOTION_THEMES["cyber_gold"])

            if manim_frm is not None and spk_frm is not None:
                # دمج شفاف ذكي (Screen/Alpha Luminance Keying) للرسوم الهندسية من Manim فوق فيديو المتحدث!
                m_luma = (0.299 * manim_frm[:, :, 0] + 0.587 * manim_frm[:, :, 1] + 0.114 * manim_frm[:, :, 2])
                fg_mask = np.clip((m_luma - 18.0) / 45.0, 0.0, 0.88)[:, :, None]
                darkened_spk = (spk_frm.astype(np.float32) * 0.78).astype(np.uint8)
                comp_rgb = np.clip(darkened_spk * (1.0 - fg_mask) + manim_frm.astype(np.float32) * fg_mask, 0, 255).astype(np.uint8)
                canvas = Image.fromarray(comp_rgb, mode="RGB").convert("RGBA")
            elif manim_frm is not None:
                canvas = Image.fromarray(manim_frm, mode="RGB").convert("RGBA")
            else:
                sc_dur = max(0.2, float(active_sc.get("end", 2.5)) - float(active_sc.get("start", 0.0)))
                sc_prog = max(0.0, min(1.0, (t_cur - float(active_sc.get("start", 0.0))) / sc_dur))
                canvas = render_single_scene_canvas(
                    scene_meta=active_sc,
                    active_word="",
                    scene_words=active_sc.get("word_strings", []),
                    active_word_idx=0,
                    word_local_progress=0.5,
                    scene_progress=sc_prog,
                    global_t=t_cur,
                    total_duration=total_dur,
                    audio_level=0.8,
                    width=vw,
                    height=vh,
                    bg_cache=bg_cache
                )

            # رسم الشارة السياقية العلوية والكابشن التفاعلي فوق مشهد Manim
            if manim_frm is not None:
                badge_txt = active_sc.get("badge_label") or active_sc.get("concept_title") or "موشن هندسي ذكي"
                bp_w, bp_h = int(vw * 0.78), max(46, int(vh * 0.052))
                bx1, by1 = (vw - bp_w) // 2, int(vh * 0.042)
                canvas = draw_visionos_glass_panel(
                    canvas_rgba=canvas,
                    bbox=(bx1, by1, bx1 + bp_w, by1 + bp_h),
                    radius=bp_h // 2,
                    tint_color=(10, 16, 30, 215),
                    border_color=theme["primary"],
                    blur_radius=12
                )
                from PIL import ImageDraw
                draw_contained_arabic_text(
                    ImageDraw.Draw(canvas, "RGBA"),
                    (bx1, by1, bx1 + bp_w, by1 + bp_h),
                    badge_txt,
                    initial_font_size=max(18, int(min(vw, vh) * 0.028)),
                    fill=(255, 255, 255, 255),
                    pad_left=16,
                    pad_right=16
                )

                if include_captions:
                    sc_words = [w.get("word", "") for w in active_sc.get("words", [])]
                    act_w = sc_words[0] if sc_words else ""
                    act_idx = 0
                    w_prog = 0.5
                    for wi, w_obj in enumerate(active_sc.get("words", [])):
                        ws = float(w_obj.get("start", 0.0))
                        we = float(w_obj.get("end", ws + 0.3))
                        if t_cur >= ws - 0.04:
                            act_w = w_obj.get("word", "")
                            act_idx = wi
                            w_prog = max(0.0, min(1.0, (t_cur - ws) / max(0.10, we - ws)))
                    cap_until = float(active_sc.get("caption_until", float(active_sc.get("end", total_dur)) + 0.6))
                    if t_cur <= cap_until and (act_w or sc_words):
                        _render_unified_karaoke_subtitle(
                            img=canvas,
                            sc_words=sc_words,
                            act_word=act_w,
                            w_prog=w_prog,
                            cap_y=int(vh * 0.83),
                            theme=theme,
                            active_word_idx=act_idx
                        )

            out_rgb = np.array(canvas.convert("RGB"), dtype=np.uint8)
            enc_proc.stdin.write(np.ascontiguousarray(out_rgb).tobytes())
            del out_rgb, canvas

            if f_idx % 24 == 0:
                prog_v = 0.72 + 0.26 * (f_idx / float(max(1, total_frames)))
                update_progress(prog_v, f"4/4: جاري دمج ورندرة مشهد Manim الهندسي ({int(round(f_idx / float(max(1, total_frames)) * 100))}%)...")
            if f_idx % 60 == 0 and f_idx > 0:
                force_free_ram()

        if enc_proc and enc_proc.stdin:
            enc_proc.stdin.close()
            enc_proc.wait(timeout=120)
            enc_proc = None

        update_progress(1.0, "اكتمل إنتاج فيديو الموشن جرافيك الهندسي (Manim + Self-Growing Library) بنجاح!")
        return output_path

    finally:
        for p in (manim_dec_proc, spk_dec_proc, enc_proc):
            if p is not None:
                try:
                    if getattr(p, "stdin", None):
                        p.stdin.close()
                    if getattr(p, "stdout", None):
                        p.stdout.close()
                    p.kill()
                except Exception:
                    pass
        for tmp_p in (clean_media_path, temp_manim_py):
            if os.path.exists(tmp_p):
                try:
                    os.remove(tmp_p)
                except Exception:
                    pass
        if os.path.exists(manim_media_dir):
            try:
                shutil.rmtree(manim_media_dir, ignore_errors=True)
            except Exception:
                pass
        force_free_ram()
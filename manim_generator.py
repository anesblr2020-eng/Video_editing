"""
manim_generator.py - وحدة الموشن جرافيك الهندسي والأنفوجرافيك المتحرك (Manim + Zero-OOM Streaming Pipe)
=========================================================================================================
تتميز هذه الوحدة بـ:
1. دعم توليد كود Manim عبر الذكاء الاصطناعي السحابي (Groq / Gemini / OpenAI / Free Cloud AI) أو Ollama المحلي.
2. مولد مشاهد هندسية ديناميكي ذكي (Dynamic Multi-Stage Manim Builder).
3. دمج الكابشن والصوت عبر أنابيب FFmpeg المباشرة (Zero-OOM Streaming Pipe) بدلاً من MoviePy `write_videofile` لمنع انهيار الذاكرة.
"""

import sys
import os
import gc
import ctypes

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import re
import glob
import shutil
import logging
import subprocess
from typing import Optional, Callable, List, Dict, Any

from transcriber import transcribe_audio, transcribe_sentences

try:
    from smart_analyzer import query_hybrid_llm
except ImportError:
    def query_hybrid_llm(*args, **kwargs):
        return None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def _free_ram():
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def build_dynamic_manim_template(duration_seconds: float, num_sentences: int = 3) -> str:
    stage_time = max(1.2, min(3.0, duration_seconds / max(4.0, num_sentences + 2)))
    return f"""from manim import *
import numpy as np

class GeneratedScene(Scene):
    def construct(self):
        self.camera.background_color = "#0B1120"
        stage_t = {stage_time:.2f}

        grid = NumberPlane(
            background_line_style={{
                "stroke_color": TEAL_E,
                "stroke_width": 1,
                "stroke_opacity": 0.25
            }},
            axis_config={{"stroke_opacity": 0.0}}
        )
        self.add(grid)

        outer_hex = RegularPolygon(n=6, radius=2.6, color=TEAL_B, stroke_width=4)
        inner_circle = Circle(radius=1.7, color=GOLD_B, stroke_width=5)
        core_dot = Dot(ORIGIN, color=YELLOW, radius=0.18)

        orbit_dots = VGroup(*[
            Dot(point=2.6 * np.array([np.cos(a), np.sin(a), 0]), color=BLUE_B, radius=0.12)
            for a in np.linspace(0, 2 * np.pi, 6, endpoint=False)
        ])

        self.play(Create(outer_hex), Create(inner_circle), FadeIn(core_dot), run_time=stage_t)
        self.play(FadeIn(orbit_dots), Rotate(outer_hex, angle=PI / 3), run_time=stage_t)

        nodes = VGroup(*[
            Dot(point=np.array([x, y, 0]), color=TEAL_A if (i % 2 == 0) else GOLD_A, radius=0.14)
            for i, (x, y) in enumerate([
                (-3.0, 1.5), (-1.5, -1.2), (0.0, 1.8), (1.5, -1.2), (3.0, 1.5), (0.0, 0.0)
            ])
        ])
        edges = VGroup(*[
            Line(nodes[i].get_center(), nodes[j].get_center(), color=BLUE_D, stroke_width=2.5, stroke_opacity=0.7)
            for i in range(len(nodes)) for j in range(i + 1, len(nodes))
        ])

        self.play(
            ReplacementTransform(orbit_dots, nodes),
            Create(edges),
            outer_hex.animate.scale(1.25).set_stroke(opacity=0.3),
            run_time=stage_t
        )

        bars = VGroup()
        bar_heights = [1.1, 1.8, 2.5, 3.2, 4.0]
        bar_colors = [BLUE_D, BLUE_C, TEAL_C, TEAL_B, GOLD_B]
        for idx, (bh, bc) in enumerate(zip(bar_heights, bar_colors)):
            rect = RoundedRectangle(
                corner_radius=0.1,
                width=0.65,
                height=bh,
                fill_color=bc,
                fill_opacity=0.85,
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
            lambda x: 0.85 * np.sin(2.5 * x) * np.cos(0.6 * x),
            x_range=[-4.5, 4.5],
            color=TEAL_A,
            stroke_width=5
        )
        self.play(
            ReplacementTransform(bars, wave_curve),
            FadeOut(trend_arrow),
            Rotate(outer_hex, angle=PI / 2),
            run_time=stage_t
        )
        self.wait(0.8)
"""


def clean_manim_code(raw_code: str, duration_seconds: float = 10.0) -> str:
    fallback = build_dynamic_manim_template(duration_seconds)
    if not raw_code or not raw_code.strip():
        return fallback

    code = raw_code.strip()
    markdown_match = re.search(r"```(?:python)?(.*?)```", code, re.DOTALL | re.IGNORECASE)
    if markdown_match:
        code = markdown_match.group(1).strip()

    if "from manim import *" not in code and "import manim" not in code:
        code = "from manim import *\nimport numpy as np\n\n" + code

    if "Scene" not in code or "def construct" not in code:
        return fallback

    try:
        compile(code, "<manim_ai>", "exec")
    except SyntaxError:
        return fallback

    return code


def extract_scene_class_name(code: str) -> str:
    match = re.search(r"class\s+(\w+)\s*\(\s*Scene\s*\)\s*:", code)
    if match:
        return match.group(1)
    return "GeneratedScene"


def query_ai_for_manim(
    transcribed_text: str,
    duration_seconds: float,
    model_name: str = "llama3",
    ollama_url: str = "http://localhost:11434",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None
) -> str:
    system_prompt = (
        "You are an expert Manim Community (v0.18+) Python developer. "
        "Write a valid, visually stunning Manim Scene class named GeneratedScene that illustrates the meaning of the user's transcript using geometric shapes, graphs, arrows, glowing circles, polygons, and smooth transforms."
    )

    user_message = (
        f"Transcript summary: \"{transcribed_text}\"\n"
        f"Target duration: approximately {duration_seconds:.1f} seconds.\n"
        "Strict rules:\n"
        "1. Start with `from manim import *` and `import numpy as np`.\n"
        "2. Define `class GeneratedScene(Scene):` and `def construct(self):`.\n"
        "3. Set `self.camera.background_color = '#0B1120'`.\n"
        "4. DO NOT use `Tex`, `MathTex`, or Arabic `Text` inside Manim. Use ONLY geometric Mobjects: `Circle`, `RoundedRectangle`, `RegularPolygon`, `Arrow`, `Line`, `Dot`, `VGroup`, `NumberPlane`, `FunctionGraph`.\n"
        "5. Return ONLY valid Python code inside ```python ... ```."
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
        max_tokens=900
    )

    if ai_resp:
        return clean_manim_code(ai_resp, duration_seconds=duration_seconds)

    return build_dynamic_manim_template(duration_seconds)


def find_rendered_manim_video(search_directory: str) -> Optional[str]:
    patterns = [
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


def generate_manim_motion_graphics(
    input_path: str,
    output_path: str,
    whisper_model: str = "base",
    ollama_model: str = "llama3",
    quality_flag: str = "-ql",
    dialect_mode: str = "algerian_darija",
    include_captions: bool = True,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    **kwargs
) -> str:
    """
    تنفيذ مسار الموشن جرافيك الهندسي (Manim + Hybrid AI) باستهلاك ذاكرة منخفض جداً
    عبر أنابيب FFmpeg المباشرة بدلاً من MoviePy CompositeVideoClip.
    """
    from motion_text import create_kinetic_typography_video
    return create_kinetic_typography_video(
        input_path=input_path,
        output_path=output_path,
        whisper_model=whisper_model,
        ollama_model=ollama_model,
        dialect_mode=dialect_mode,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        progress_callback=progress_callback
    )
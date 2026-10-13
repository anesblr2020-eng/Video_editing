"""
manim_generator.py - وحدة الموشن جرافيك الهندسي والأنفوجرافيك المتحرك (Manim + Hybrid Cloud/Local AI)
=====================================================================================================
تتميز هذه الوحدة بـ:
1. دعم توليد كود Manim عبر الذكاء الاصطناعي السحابي (Groq / Gemini / OpenAI / Free Cloud AI) أو Ollama المحلي.
2. مولد مشاهد هندسية ديناميكي ذكي (Dynamic Multi-Stage Manim Builder) يبني رسوماً متحركة ومخططات بيانية
   وموجات طاقة متزامنة مع عدد جمل المستخدم ومدتها الفعلية.
3. دمج اختياري لكابشن الكلمات العربية والدارجة الجزائرية فوق فيديو Manim الهندسي لجمع المتعة البصرية مع وضوح النص.
"""

import sys
import os

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


def build_dynamic_manim_template(duration_seconds: float, num_sentences: int = 3) -> str:
    """
    بناء كود Manim هندسي غني ومتعدد المراحل يتناسب تلقائياً مع المدة الزمنية للصوت،
    يتضمن: شبكة محاور، حلقات طاقة نابضة، مخطط بياني متحرك، وشبكة عقد ذكية (Neural Nodes).
    """
    stage_time = max(1.2, min(3.0, duration_seconds / max(4.0, num_sentences + 2)))
    return f"""from manim import *
import numpy as np

class GeneratedScene(Scene):
    def construct(self):
        self.camera.background_color = "#0B1120"
        stage_t = {stage_time:.2f}

        # المرحلة 1: شبكة خلفية ناعمة ومدار هندسي مركزي نابض
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

        # المرحلة 2: التحول إلى شبكة عقد ذكية مترابطة (Neural Graph)
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

        # المرحلة 3: مخطط أعمدة صاعد ومؤشر نمو ديناميكي
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

        # المرحلة 4: موجة صوتية هندسية متناغمة في الختام
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
    """استخراج كود بايثون الصافي من رد الذكاء الاصطناعي والتحقق من سلامته."""
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
        logger.warning("الكود المولد لا يحتوي على Scene صالحة. سيتم استخدام المشهد الهندسي الديناميكي.")
        return fallback

    # التحقق من صحة قواعد بايثون (Syntax Check) قبل الحفظ
    try:
        compile(code, "<manim_ai>", "exec")
    except SyntaxError as e:
        logger.warning(f"تم اكتشاف خطأ صياغة في كود Manim المولد ({e})، سيتم استخدام القالب الديناميكي المضمون.")
        return fallback

    return code


def extract_scene_class_name(code: str) -> str:
    """استخراج اسم كلاس المشهد لاستدعائه في سطر أوامر Manim."""
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
    """
    توليد كود Manim احترافي عبر الذكاء الاصطناعي السحابي أو المحلي.
    يتجنب استخدام Text/Tex التي قد تفشل مع الحروف العربية في بعض بيئات Manim ويركز على الأشكال الهندسية والمخططات،
    ثم ندمج النصوص العربية والدارجة الجزائرية بدقة عالية فوق الفيديو في مرحلة التركيب!
    """
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
        "4. DO NOT use `Tex`, `MathTex`, or Arabic `Text` inside Manim (to avoid LaTeX/Pango missing font crashes). Use ONLY geometric Mobjects: `Circle`, `RoundedRectangle`, `RegularPolygon`, `Arrow`, `Line`, `Dot`, `VGroup`, `NumberPlane`, `FunctionGraph`.\n"
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
    """البحث عن ملف الفيديو المصدّر بواسطة Manim."""
    patterns = [
        os.path.join(search_directory, "**", "*.mp4"),
        os.path.join("media", "**", "*.mp4")
    ]
    found_files = []
    for pattern in patterns:
        found_files.extend(glob.glob(pattern, recursive=True))
    # استبعاد ملفات partial_movie_files الجزئية
    found_files = [f for f in found_files if "partial_movie_files" not in f]
    if found_files:
        found_files.sort(key=os.path.getmtime, reverse=True)
        return found_files[0]
    return None


def generate_manim_motion_graphics(
    input_path: str,
    output_path: str,
    whisper_model: str = "small",
    ollama_model: str = "llama3",
    quality_flag: str = "-qh",
    dialect_mode: str = "algerian_darija",
    include_captions: bool = True,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    تنفيذ مسار الموشن جرافيك الهندسي (Manim + Hybrid AI) مع تراكب الكابشن العربي/الدارجة:
    1. تفريغ الصوت لحساب المدة واستخراج النص والكلمات.
    2. توليد كود Manim عبر الذكاء الاصطناعي السحابي أو المحلي.
    3. رندرة المشهد الهندسي عبر Manim (مع تراجع ذكي في حال عدم توفر أداة manim CLI).
    4. دمج الكابشن التفاعلي والصوت الأصلي مع المشهد الهندسي.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"الملف غير موجود: {input_path}")

    base_dir = os.path.dirname(os.path.abspath(output_path))
    temp_dir = os.path.join(base_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    def update_progress(val: float, msg: str):
        if progress_callback:
            progress_callback(val, msg)
        logger.info(f"Progress: {val*100:.1f}% - {msg}")

    from moviepy.editor import AudioFileClip, VideoFileClip, ImageClip, CompositeVideoClip, vfx
    from dynamic_edit import generate_caption_image

    audio_clip = None
    manim_video_clip = None
    final_video_clip = None
    caption_clips = []

    try:
        update_progress(0.1, "1/4: تحليل الملف الصوتي وتفريغ الكلمات بالدارجة/العربية...")
        audio_clip = AudioFileClip(input_path)
        audio_duration = audio_clip.duration

        words = transcribe_audio(
            input_path,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        sentences = transcribe_sentences(
            input_path,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        full_transcript = " ".join([w["word"] for w in words]) if words else "موشن جرافيك هندسي تعليمي"

        update_progress(0.3, "2/4: توليد كود المشهد الهندسي عبر الذكاء الاصطناعي...")
        manim_code = query_ai_for_manim(
            transcribed_text=full_transcript,
            duration_seconds=audio_duration,
            model_name=ollama_model,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )

        temp_manim_file = os.path.join(temp_dir, "temp_manim.py")
        with open(temp_manim_file, "w", encoding="utf-8") as f:
            f.write(manim_code)

        scene_name = extract_scene_class_name(manim_code)

        update_progress(0.5, f"3/4: رندرة المشهد الهندسي عبر Manim ({quality_flag})...")
        manim_media_dir = os.path.join(temp_dir, "manim_media")
        os.makedirs(manim_media_dir, exist_ok=True)

        cmd = [
            "manim",
            temp_manim_file,
            scene_name,
            quality_flag,
            "--media_dir",
            manim_media_dir,
            "-v", "WARNING"
        ]

        render_result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if render_result.returncode != 0:
            logger.warning(f"فشلت رندرة الكود الأولي ({render_result.stderr}). جاري الرندرة بالقالب الهندسي الديناميكي...")
            fallback_code = build_dynamic_manim_template(audio_duration, num_sentences=max(2, len(sentences)))
            with open(temp_manim_file, "w", encoding="utf-8") as f:
                f.write(fallback_code)
            cmd[1] = temp_manim_file
            cmd[2] = "GeneratedScene"
            subprocess.run(cmd, check=True)

        rendered_video_path = find_rendered_manim_video(manim_media_dir)
        if not rendered_video_path or not os.path.exists(rendered_video_path):
            raise FileNotFoundError("تعذر العثور على ملف الفيديو الناتج من تصيير Manim.")

        update_progress(0.75, "4/4: مزامنة المشهد الهندسي مع الصوت والكابشن العربي...")
        manim_video_clip = VideoFileClip(rendered_video_path)
        vw, vh = manim_video_clip.size

        # تكرار أو ضبط مدة المشهد الهندسي ليغطي كامل مدة الصوت بسلاسة
        if manim_video_clip.duration < audio_duration:
            manim_video_clip = manim_video_clip.fx(vfx.loop, duration=audio_duration)
        elif manim_video_clip.duration > audio_duration:
            manim_video_clip = manim_video_clip.subclip(0, audio_duration)

        # إضافة الكلمات المفرغة أسفل المشهد الهندسي ليكون الفيديو مفهوماً وجذاباً
        if include_captions and words:
            for item in words:
                w_txt = item["word"]
                w_start = item["start"]
                w_end = min(item["end"], audio_duration)
                if w_end <= w_start or w_start >= audio_duration:
                    continue
                dur = max(0.14, w_end - w_start)
                cap_arr = generate_caption_image(
                    word_text=w_txt,
                    video_width=vw,
                    video_height=vh
                )
                c_clip = (
                    ImageClip(cap_arr, ismask=False, transparent=True)
                    .set_start(w_start)
                    .set_duration(dur)
                    .set_position(("center", int(vh * 0.78)))
                )
                caption_clips.append(c_clip)

        if caption_clips:
            final_video_clip = CompositeVideoClip([manim_video_clip, *caption_clips], size=(vw, vh)).set_audio(audio_clip)
        else:
            final_video_clip = manim_video_clip.set_audio(audio_clip)

        update_progress(0.9, "جاري تصدير الفيديو الهندسي النهائي...")
        temp_audio_export = os.path.join(temp_dir, "temp_manim_audio.m4a")

        final_video_clip.write_videofile(
            output_path,
            fps=30,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=temp_audio_export,
            remove_temp=True,
            preset="medium",
            threads=4,
            logger=None
        )

        update_progress(1.0, "تم إنتاج فيديو الموشن جرافيك الهندسي (Manim) بنجاح!")
        return output_path

    except Exception as err:
        logger.error(f"خطأ أثناء توليد موشن جرافيك Manim: {str(err)}", exc_info=True)
        raise err

    finally:
        for cc in caption_clips:
            try:
                cc.close()
            except Exception:
                pass
        if audio_clip is not None:
            try:
                audio_clip.close()
            except Exception:
                pass
        if manim_video_clip is not None:
            try:
                manim_video_clip.close()
            except Exception:
                pass
        if final_video_clip is not None:
            try:
                final_video_clip.close()
            except Exception:
                pass

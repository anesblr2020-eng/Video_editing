"""
manim_generator.py - وحدة الموشن جرافيك الهندسي التعليمي (Manim + Ollama)
==========================================================================
المرحلة 6: إنتاج موشن جرافيك هندسي ورياضي تلقائي بالكامل:
1. تفريغ الصوت واستخراج النص الكامل للمتحدث عبر faster-whisper.
2. إرسال النص إلى نموذج الذكاء الاصطناعي المحلي (Llama 3 عبر Ollama) لصياغة كود Manim Class متكامل.
3. حفظ كود بايثون كملف temp_manim.py وتصحيحه تلقائياً.
4. تنفيذ رندرة الفيديو بجودة عالية باستخدام manim CLI (-qh).
5. دمج فيديو Manim الناتج مع الصوت الأصلي للمستخدم وتصدير النسخة النهائية.
"""

import sys
import os

# إضافة مسار المجلد الحالي إلى أولويات البحث لضمان تعرف كل ملف على الملفات المجاورة في الاستضافة
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)


import os
import re
import glob
import shutil
import logging
import subprocess
from typing import Optional, Callable
import requests

# استيراد وحدة التفريغ
from transcriber import transcribe_audio

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ==============================================================================
# كود هندسي بديل فخم في حال عدم توفر خادم Ollama أو حدوث خطأ في الكود المولد
# ==============================================================================
DEFAULT_MANIM_TEMPLATE = """from manim import *

class GeneratedScene(Scene):
    def construct(self):
        # إعداد خلفية هندسية أنيقة
        self.camera.background_color = "#0F172A"
        
        # دائرة مركزية مع شبكة هندسية نابضة
        center_circle = Circle(radius=1.8, color=TEAL, stroke_width=4)
        inner_dot = Dot(color=YELLOW, radius=0.15)
        pulse_ring = Circle(radius=2.6, color=BLUE_D, stroke_width=2)
        
        # محاور وأشكال محيطة
        square = Square(side_length=2.5, color=PURPLE_B, stroke_width=3)
        triangle = Triangle(color=GOLD, stroke_width=3).scale(1.4)
        
        # حركات هندسية متتالية
        self.play(Create(center_circle), FadeIn(inner_dot), run_time=1.5)
        self.play(Create(pulse_ring), run_time=1.2)
        self.play(Transform(center_circle, square), Rotate(pulse_ring, PI/2), run_time=2.0)
        self.play(Transform(center_circle, triangle), run_time=2.0)
        
        # خطوط إشعاعية متصلة
        lines = VGroup(*[
            Line(ORIGIN, 3.5 * np.array([np.cos(theta), np.sin(theta), 0]), color=BLUE_C, stroke_width=2)
            for theta in np.linspace(0, 2*PI, 8, endpoint=False)
        ])
        
        self.play(Create(lines), run_time=2.0)
        self.play(Rotate(lines, PI/4), FadeOut(lines), run_time=2.0)
        self.play(FadeOut(center_circle), FadeOut(inner_dot), FadeOut(pulse_ring), run_time=1.5)
        self.wait(1.0)
"""


def clean_manim_code(raw_code: str) -> str:
    """
    استخراج كود بايثون الصافي من رد Ollama وإزالة وسوم Markdown والتعليقات الزائدة.
    """
    if not raw_code or not raw_code.strip():
        return DEFAULT_MANIM_TEMPLATE

    code = raw_code.strip()

    # إزالة أقواس Markdown ```python ... ``` إذا وجدت
    markdown_match = re.search(r"```(?:python)?(.*?)```", code, re.DOTALL | re.IGNORECASE)
    if markdown_match:
        code = markdown_match.group(1).strip()

    # التأكد من استيراد مكتبة Manim
    if "from manim import *" not in code and "import manim" not in code:
        code = "from manim import *\n\n" + code

    # التحقق من وجود كلاس يرث من Scene
    if "Scene" not in code or "def construct" not in code:
        logger.warning("الرد المولد لا يحتوي على Scene Class صالح. سيتم استخدام القالب الهندسي البديل.")
        return DEFAULT_MANIM_TEMPLATE

    return code


def extract_scene_class_name(code: str) -> str:
    """استخراج اسم كلاس المشهد لاستدعائه في سطر أوامر Manim."""
    match = re.search(r"class\s+(\w+)\s*\(\s*Scene\s*\)\s*:", code)
    if match:
        return match.group(1)
    return "GeneratedScene"


def query_ollama_for_manim(
    transcribed_text: str,
    duration_seconds: float,
    model_name: str = "llama3",
    ollama_url: str = "http://localhost:11434"
) -> str:
    """
    إرسال النص المفرغ إلى Ollama للحصول على كود Manim هندسي يعبر عن المعنى.
    """
    system_prompt = (
        "أنت خبير في مكتبة Manim. بناءً على هذا النص المفرغ، اكتب كود Python باستخدام Manim Class "
        "لرسم أشكال هندسية بسيطة تعبر عن المعنى. أرجع كود بايثون فقط"
    )

    user_message = (
        f"{system_prompt}\n\n"
        f"النص المفرغ من صوت المستخدم:\n\"{transcribed_text}\"\n\n"
        f"ملاحظات تقنية صارمة:\n"
        f"1. يجب أن تكون مدة الحركات الكلية قريبة من {duration_seconds:.1f} ثانية.\n"
        f"2. استخدم أشكالاً هندسية مثل Circle, Square, Lines, Dots, Arrows مع حركات Create, Transform, FadeIn, FadeOut.\n"
        f"3. أرجع كود Python فقط داخل بلوك برمجي دون أي نصوص تمهيدية أو شروحات."
    )

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model_name,
                "prompt": user_message,
                "stream": False,
                "options": {
                    "temperature": 0.3
                }
            },
            timeout=25
        )

        if response.status_code == 200:
            raw_response = response.json().get("response", "")
            return clean_manim_code(raw_response)

    except Exception as e:
        logger.warning(f"تعذر الاتصال بـ Ollama لتوليد كود Manim ({str(e)}). سيتم استخدام القالب الهندسي المتوافق.")

    return DEFAULT_MANIM_TEMPLATE


def find_rendered_manim_video(search_directory: str) -> Optional[str]:
    """البحث عن ملف الفيديو المصدّر بواسطة Manim في مجلدات الإخراج المؤقتة."""
    # يبحث Manim افتراضياً في media/videos/ أو المجلد المحدد
    patterns = [
        os.path.join(search_directory, "**", "*.mp4"),
        os.path.join("media", "**", "*.mp4")
    ]

    found_files = []
    for pattern in patterns:
        found_files.extend(glob.glob(pattern, recursive=True))

    if found_files:
        # اختيار أحدث ملف تم إنشاؤه
        found_files.sort(key=os.path.getmtime, reverse=True)
        return found_files[0]

    return None


def generate_manim_motion_graphics(
    input_path: str,
    output_path: str,
    whisper_model: str = "small",
    ollama_model: str = "llama3",
    quality_flag: str = "-qh",  # -qh (1080p), -qm (720p), -ql (480p)
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    تنفيذ مسار الموشن جرافيك الهندسي الكامل:
    1. تفريغ الصوت لحساب المدة واستخراج النص.
    2. استدعاء Ollama وتوليد كود temp_manim.py.
    3. عمل رندر عبر manim CLI.
    4. دمج الصوت مع فيديو Manim الناتج وتصديره.
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

    from moviepy.editor import AudioFileClip, VideoFileClip, vfx

    audio_clip = None
    manim_video_clip = None
    final_video_clip = None

    try:
        # 1. قراءة وتفريغ الصوت
        update_progress(0.1, "1/4: تحليل الملف الصوتي وحساب المدة وتفريغ الكلمات...")
        audio_clip = AudioFileClip(input_path)
        audio_duration = audio_clip.duration

        words = transcribe_audio(input_path, model_size=whisper_model, language="ar")
        full_transcript = " ".join([w["word"] for w in words]) if words else "موشن جرافيك هندسي تعليمي"

        # 2. توليد كود Manim عبر Ollama وحفظه في temp_manim.py
        update_progress(0.3, f"2/4: توليد كود الأشكال الهندسية عبر Ollama ({ollama_model})...")
        manim_code = query_ollama_for_manim(
            transcribed_text=full_transcript,
            duration_seconds=audio_duration,
            model_name=ollama_model
        )

        temp_manim_file = os.path.join(temp_dir, "temp_manim.py")
        with open(temp_manim_file, "w", encoding="utf-8") as f:
            f.write(manim_code)

        scene_name = extract_scene_class_name(manim_code)
        logger.info(f"تم حفظ كود Manim في {temp_manim_file}. اسم المشهد: {scene_name}")

        # 3. تشغيل أمر Manim للرندرة
        update_progress(0.5, f"3/4: جاري رندرة فيديو Manim بجودة عالية ({quality_flag})...")
        
        # تنفيذ الرندرة بواسطة manim CLI
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

        logger.info(f"تنفيذ الأمر: {' '.join(cmd)}")
        render_result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

        if render_result.returncode != 0:
            logger.warning(f"فشلت رندرة الكود المولد: {render_result.stderr}. جاري الرندرة بالقالب البديل المضمون...")
            with open(temp_manim_file, "w", encoding="utf-8") as f:
                f.write(DEFAULT_MANIM_TEMPLATE)
            cmd[1] = temp_manim_file
            cmd[2] = "GeneratedScene"
            subprocess.run(cmd, check=True)

        # العثور على الفيديو الناتج من Manim
        rendered_video_path = find_rendered_manim_video(manim_media_dir)
        if not rendered_video_path or not os.path.exists(rendered_video_path):
            raise FileNotFoundError("تعذر العثور على ملف الفيديو الناتج من تصيير Manim.")

        # 4. دمج فيديو Manim مع صوت المستخدم
        update_progress(0.75, "4/4: دمج فيديو Manim الهندسي مع الصوت الأصلي وتصدير العمل...")
        manim_video_clip = VideoFileClip(rendered_video_path)

        # مزامنة المدة: إذا كانت مدة فيديو Manim أقصر أو أطول من الصوت
        if manim_video_clip.duration < audio_duration:
            freeze_time = audio_duration - manim_video_clip.duration
            manim_video_clip = manim_video_clip.fx(
                vfx.freeze,
                t=manim_video_clip.duration - 0.05,
                freeze_duration=freeze_time
            )
        elif manim_video_clip.duration > audio_duration:
            manim_video_clip = manim_video_clip.subclip(0, audio_duration)

        final_video_clip = manim_video_clip.set_audio(audio_clip)

        update_progress(0.9, "جاري تصدير الفيديو النهائي...")
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

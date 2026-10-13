"""
motion_text.py - وحدة الموشن جرافيك النصي المتحرك (Kinetic Typography)
======================================================================
المرحلة 5: صناعة فيديو موشن جرافيك نصي ديناميكي بالكامل:
1. توليد خلفية سينمائية متدرجة الألوان (Gradient Background).
2. استخراج الكلمات المفتاحية عبر نموذج الذكاء الاصطناعي المحلي (Llama 3 عبر Ollama API).
3. البحث عن أيقونات مطابقة داخل مجلد assets/icons/ وتراكبها.
4. تحريك النصوص بأسلوب Kinetic Typography Pop-up متزامن تماماً مع تواقيت faster-whisper
   (الكلمة الحالية تظهر كبيرة وبارزة بالمنتصف، والكلمة السابقة تصغر وترتفع للأعلى).
"""

import sys
import os

# إضافة مسار المجلد الحالي إلى أولويات البحث لضمان تعرف كل ملف على الملفات المجاورة في الاستضافة
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)


import os
import re
import shutil
import logging
from typing import List, Dict, Any, Optional, Tuple, Callable
import numpy as np
import requests
from PIL import Image, ImageDraw, ImageFont

# استيراد وحدات النظام السابقة
from auto_cut import remove_silence
from transcriber import transcribe_audio, transcribe_sentences

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ==============================================================================
# 1. دوال الخطوط وتوليد الخلفيات المتدرجة
# ==============================================================================
def get_arabic_font(font_size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    """البحث عن خط عربي مناسب متوفر في النظام."""
    candidate_fonts = [
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf" if bold else "/usr/share/fonts/truetype/noto/NotoKufiArabic-Regular.ttf",
        "/usr/share/fonts/truetype/noto/NotoKufiArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
        "/System/Library/Fonts/GeezaPro.ttc",
        "arial.ttf"
    ]

    for path in candidate_fonts:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, font_size)
            except Exception:
                continue

    try:
        return ImageFont.load_default()
    except Exception:
        raise RuntimeError("تعذر العثور على خط نظام صالح.")


def create_vertical_gradient(
    width: int,
    height: int,
    top_color: Tuple[int, int, int] = (24, 18, 48),      # أرجواني ليلي عميق
    bottom_color: Tuple[int, int, int] = (10, 12, 28)    # كحلي داكن فخم
) -> np.ndarray:
    """
    إنشاء خلفية متدرجة عمودياً باستخدام معالجة المصفوفات الرياضية السريعة.
    """
    gradient = np.zeros((height, width, 3), dtype=np.uint8)
    for y in range(height):
        ratio = y / max(1, height - 1)
        r = int(top_color[0] * (1 - ratio) + bottom_color[0] * ratio)
        g = int(top_color[1] * (1 - ratio) + bottom_color[1] * ratio)
        b = int(top_color[2] * (1 - ratio) + bottom_color[2] * ratio)
        gradient[y, :] = [r, g, b]
    return gradient


# ==============================================================================
# 2. وحدة الذكاء الاصطناعي المحلي (Ollama API - Llama 3)
# ==============================================================================
def extract_keyword_ollama(
    sentence: str,
    model_name: str = "llama3",
    ollama_url: str = "http://localhost:11434"
) -> str:
    """
    الاتصال بخادم Ollama المحلي لإرسال الجملة واستخراج الكلمة المفتاحية الأكثر تعبيراً.
    مزودة بنظام Fallback ذكي يعمل في حال كان Ollama غير مشغل.
    """
    if not sentence or not sentence.strip():
        return ""

    prompt = (
        f"أنت خبير في تلخيص وتحليل النصوص. بناءً على هذه الجملة: '{sentence}'، "
        "استخرج كلمة مفتاحية رئيسية واحدة فقط تمثل المفهوم الأهم (مثال: ذكاء، مال، وقت، نجاح، تسويق). "
        "أرجع الكلمة المفتاحية فقط دون أي شرح أو مقدمات أو علامات ترقيم."
    )

    try:
        response = requests.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model_name,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.2,
                    "num_predict": 10
                }
            },
            timeout=8
        )

        if response.status_code == 200:
            raw_text = response.json().get("response", "").strip()
            # تنظيف النتيجة لاستخراج أول كلمة صالحة فقط
            words = re.findall(r"[\w\u0621-\u064A]+", raw_text)
            if words:
                keyword = words[0]
                logger.info(f"Ollama ({model_name}) استخرج الكلمة المفتاحية: [{keyword}] للجملة: '{sentence[:30]}...'")
                return keyword

    except Exception as e:
        logger.warning(f"تعذر الاتصال بـ Ollama ({str(e)}). جاري تفعيل نظام الاستخراج البديل المدمج.")

    # نظام بديل (Heuristic Fallback): استخراج أطول كلمة ذات دلالة وتجاوز حروف الجر
    stop_words = {"في", "من", "على", "إلى", "عن", "مع", "هذا", "هذه", "التي", "الذي", "أن", "إن", "ما", "لا", "كان", "هو", "هي"}
    words = [w for w in re.findall(r"[\w\u0621-\u064A]+", sentence) if w not in stop_words and len(w) > 2]
    if words:
        words.sort(key=len, reverse=True)
        return words[0]

    return ""


def find_matching_icon(keyword: str, icons_dir: str = "assets/icons") -> Optional[str]:
    """البحث عن أيقونة تطابق الكلمة المفتاحية في مجلد assets/icons/."""
    if not keyword or not os.path.exists(icons_dir):
        return None

    kw = keyword.strip().lower()
    valid_exts = {".png", ".jpg", ".jpeg", ".webp"}

    for fname in os.listdir(icons_dir):
        base, ext = os.path.splitext(fname.lower())
        if ext in valid_exts:
            if base == kw or kw in base or base in kw:
                return os.path.join(icons_dir, fname)

    return None


# ==============================================================================
# 3. محرك تصيير الكلمات والتحريك (Pop-up & Rise Kinetic Typography)
# ==============================================================================
def render_kinetic_frame(
    current_word: str,
    prev_word: Optional[str],
    video_width: int,
    video_height: int,
    icon_path: Optional[str] = None
) -> np.ndarray:
    """
    تصيير إطار شفاف يحتوي على:
    - الكلمة الحالية: تظهر كبيرة في المنتصف باللون الأصفر (#FFE600).
    - الكلمة السابقة: تصغر وترتفع للأعلى بلون رمادي/شفاف (#90A4AE).
    - الأيقونة المفتاحية: تظهر في الأعلى عند توفرها.
    """
    canvas = Image.new("RGBA", (video_width, video_height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    center_x = video_width // 2
    center_y = video_height // 2

    # أبعاد الخطوط المتجاوبة
    current_font_size = max(48, int(video_height * 0.075))
    prev_font_size = max(28, int(current_font_size * 0.58))

    current_font = get_arabic_font(current_font_size, bold=True)
    prev_font = get_arabic_font(prev_font_size, bold=False)

    # 1. رسم الأيقونة (إن وجدت) أعلى الكلمة السابقة
    if icon_path and os.path.exists(icon_path):
        try:
            icon_img = Image.open(icon_path).convert("RGBA")
            icon_size = max(64, int(video_height * 0.12))
            icon_img = icon_img.resize((icon_size, icon_size), Image.Resampling.LANCZOS)
            icon_x = center_x - (icon_size // 2)
            icon_y = center_y - int(current_font_size * 2.3)
            canvas.paste(icon_img, (icon_x, icon_y), icon_img)
        except Exception as e:
            logger.warning(f"تعذر تحميل الأيقونة: {e}")

    # 2. رسم الكلمة السابقة (تصغر وترتفع للأعلى)
    if prev_word:
        prev_y = center_y - int(current_font_size * 1.05)
        # رسم خلفية خفيفة جداً للكلمة السابقة
        try:
            bbox_prev = draw.textbbox((0, 0), prev_word, font=prev_font, direction="rtl")
        except Exception:
            bbox_prev = draw.textbbox((0, 0), prev_word, font=prev_font)

        pw = bbox_prev[2] - bbox_prev[0]
        ph = bbox_prev[3] - bbox_prev[1]
        draw.rounded_rectangle(
            [(center_x - (pw//2) - 18, prev_y - (ph//2) - 8),
             (center_x + (pw//2) + 18, prev_y + (ph//2) + 8)],
            radius=12,
            fill=(20, 20, 35, 130)
        )

        try:
            draw.text(
                (center_x, prev_y),
                prev_word,
                font=prev_font,
                fill=(176, 190, 197, 210),  # رمادي فاتح شفاف
                anchor="mm",
                direction="rtl"
            )
        except Exception:
            draw.text(
                (center_x, prev_y),
                prev_word,
                font=prev_font,
                fill=(176, 190, 197, 210),
                anchor="mm"
            )

    # 3. رسم الكلمة الحالية (كبيرة في المنتصف مع Pop-up card)
    curr_y = center_y + int(current_font_size * 0.15)
    try:
        bbox_curr = draw.textbbox((0, 0), current_word, font=current_font, direction="rtl")
    except Exception:
        bbox_curr = draw.textbbox((0, 0), current_word, font=current_font)

    cw = bbox_curr[2] - bbox_curr[0]
    ch = bbox_curr[3] - bbox_curr[1]
    pad_x = int(current_font_size * 0.5)
    pad_y = int(current_font_size * 0.3)

    # بطاقة داكنة شبه شفافة محيطة بالكلمة الحالية
    draw.rounded_rectangle(
        [(center_x - (cw//2) - pad_x, curr_y - (ch//2) - pad_y),
         (center_x + (cw//2) + pad_x, curr_y + (ch//2) + pad_y)],
        radius=18,
        fill=(0, 0, 0, 190),
        outline=(255, 230, 0, 120),  # إطار أصفر خفيف
        width=2
    )

    try:
        draw.text(
            (center_x, curr_y),
            current_word,
            font=current_font,
            fill=(255, 230, 0, 255),  # أصفر تيك توك ساطع
            anchor="mm",
            direction="rtl"
        )
    except Exception:
        draw.text(
            (center_x, curr_y),
            current_word,
            font=current_font,
            fill=(255, 230, 0, 255),
            anchor="mm"
        )

    return np.array(canvas)


# ==============================================================================
# 4. مسار المعالجة والتصدير الرئيسي
# ==============================================================================
def create_kinetic_typography_video(
    input_path: str,
    output_path: str,
    video_resolution: Tuple[int, int] = (1080, 1920),  # 9:16 عمودي لوسائل التواصل
    whisper_model: str = "small",
    ollama_model: str = "llama3",
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    إنشاء فيديو موشن جرافيك نصي متكامل بدون استخدام فيديو المستخدم الأصلي:
    1. استخراج الصوت وتفريغه عبر faster-whisper.
    2. استخراج الكلمات المفتاحية عبر Ollama والربط بالأيقونات.
    3. إنشاء خلفية تدرج لوني سينمائية.
    4. تراكب الكلمات المتحركة المتزامنة (Pop-up + Rise).
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"الملف المدخل غير موجود: {input_path}")

    base_dir = os.path.dirname(os.path.abspath(output_path))
    temp_dir = os.path.join(base_dir, "temp")
    icons_dir = os.path.join(base_dir, "assets", "icons")
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(icons_dir, exist_ok=True)

    def update_progress(val: float, msg: str):
        if progress_callback:
            progress_callback(val, msg)
        logger.info(f"Progress: {val*100:.1f}% - {msg}")

    from moviepy.editor import (
        AudioFileClip,
        ImageClip,
        CompositeVideoClip
    )

    audio_clip = None
    bg_clip = None
    final_video = None
    frame_clips = []

    try:
        update_progress(0.1, "1/4: قراءة وتفريغ الملف الصوتي بدقة الكلمة عبر faster-whisper...")
        audio_clip = AudioFileClip(input_path)
        total_duration = audio_clip.duration

        if total_duration <= 0.2:
            raise ValueError("الملف الصوتي قصير جداً وغير صالح للمعالجة.")

        # استخراج الكلمات والجمل
        words_data = transcribe_audio(input_path, model_size=whisper_model, language="ar")
        sentences_data = transcribe_sentences(input_path, model_size=whisper_model, language="ar")

        if not words_data:
            raise ValueError("لم يتم استخراج أي كلمات من الملف الصوتي.")

        # الخطوة 2: استخراج الكلمات المفتاحية لكل جملة والبحث عن الأيقونات
        update_progress(0.3, f"2/4: استخراج الكلمات المفتاحية عبر الذكاء الاصطناعي المحلي ({ollama_model})...")
        sentence_icon_map = {}
        for sent in sentences_data:
            sent_text = sent["text"]
            keyword = extract_keyword_ollama(sent_text, model_name=ollama_model)
            matched_icon = find_matching_icon(keyword, icons_dir=icons_dir)
            sentence_icon_map[sent["start"]] = (keyword, matched_icon)

        # الخطوة 3: إنشاء خلفية التدرج اللوني السينمائية
        update_progress(0.5, "3/4: توليد خلفية التدرج اللوني (Gradient Canvas)...")
        w, h = video_resolution
        gradient_arr = create_vertical_gradient(width=w, height=h)
        bg_clip = ImageClip(gradient_arr).set_duration(total_duration)

        # الخطوة 4: بناء إطارات Kinetic Typography المتزامنة
        update_progress(0.7, "4/4: إنشاء الكروت النصية المتزامنة (Pop-up & Rise Animation)...")
        for i, item in enumerate(words_data):
            curr_w = item["word"]
            prev_w = words_data[i - 1]["word"] if i > 0 else None
            w_start = item["start"]
            w_end = item["end"]

            if w_start >= total_duration:
                continue

            # مدة بقاء الكلمة الحالية: حتى بداية الكلمة التالية أو انتهاء الكلمة
            if i + 1 < len(words_data):
                next_start = words_data[i + 1]["start"]
                duration = max(0.12, next_start - w_start)
            else:
                duration = max(0.15, min(w_end - w_start, total_duration - w_start))

            # البحث عن أيقونة الجملة التي تنتمي إليها هذه الكلمة
            current_icon = None
            for s_start, (kw, icon_p) in sentence_icon_map.items():
                if w_start >= s_start:
                    current_icon = icon_p

            frame_arr = render_kinetic_frame(
                current_word=curr_w,
                prev_word=prev_w,
                video_width=w,
                video_height=h,
                icon_path=current_icon
            )

            txt_clip = (
                ImageClip(frame_arr, ismask=False, transparent=True)
                .set_start(w_start)
                .set_duration(duration)
                .set_position(("center", "center"))
            )
            frame_clips.append(txt_clip)

        # دمج الخلفية المتدرجة مع الصوت وطبقات الكلمات المتحركة
        composite_layers = [bg_clip, *frame_clips]
        final_video = CompositeVideoClip(composite_layers, size=(w, h)).set_audio(audio_clip)

        update_progress(0.85, "جاري رندرة وتصدير فيديو الموشن جرافيك النصي...")
        temp_audio_file = os.path.join(temp_dir, "temp_motion_audio.m4a")

        final_video.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=temp_audio_file,
            remove_temp=True,
            preset="medium",
            threads=4,
            logger=None
        )

        update_progress(1.0, "تم إنتاج فيديو Kinetic Typography بنجاح!")
        return output_path

    except Exception as err:
        logger.error(f"خطأ أثناء تصدير الموشن جرافيك النصي: {str(err)}", exc_info=True)
        raise err

    finally:
        for fc in frame_clips:
            try:
                fc.close()
            except Exception:
                pass

        if bg_clip is not None:
            try:
                bg_clip.close()
            except Exception:
                pass

        if audio_clip is not None:
            try:
                audio_clip.close()
            except Exception:
                pass

        if final_video is not None:
            try:
                final_video.close()
            except Exception:
                pass

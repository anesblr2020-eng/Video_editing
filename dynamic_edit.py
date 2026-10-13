"""
dynamic_edit.py - وحدة المونتاج الديناميكي (Auto-Zoom + Jump-cuts + TikTok Captions)
===================================================================================
المرحلة 4: تنفيذ مونتاج ديناميكي تفاعلي يتضمن:
1. تطبيق Jump-cuts لحذف الصمت بالاعتماد على وحدة auto_cut.
2. تفريغ الصوت واستخراج تواقيت الكلمات والجمل بالاعتماد على وحدة transcriber.
3. التكبير السينمائي (Auto-Zoom بنسبة 15%) بالتناوب مع كل جملة جديدة لكسر الرتابة.
4. طباعة الكلمات الحالية بنمط تيك توك الشهير (خط عريض أصفر مع خلفية سوداء شفافة بمنتصف الشاشة).
"""

import sys
import os

# إضافة مسار المجلد الحالي إلى أولويات البحث لضمان تعرف كل ملف على الملفات المجاورة في الاستضافة
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)


import os
import shutil
import logging
from typing import List, Dict, Any, Tuple, Optional, Callable
import numpy as np
from PIL import Image, ImageDraw, ImageFont

# استيراد الوحدات السابقة
from auto_cut import remove_silence, is_video_file
from transcriber import transcribe_audio, transcribe_sentences

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_arabic_bold_font(font_size: int) -> ImageFont.FreeTypeFont:
    """
    البحث عن خط عريض يدعم اللغة العربية من مسارات النظام الشائعة (Linux, Windows, macOS)
    مع التراجع التلقائي لخط بديل في حال عدم توفره.
    """
    candidate_fonts = [
        # مسارات أنظمة لينكس / أوبونتو
        "/usr/share/fonts/truetype/noto/NotoNaskhArabic-Bold.ttf",
        "/usr/share/fonts/truetype/noto/NotoKufiArabic-Regular.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        # مسارات أنظمة ويندوز
        "C:\\Windows\\Fonts\\arialbd.ttf",
        "C:\\Windows\\Fonts\\tahoma.ttf",
        "C:\\Windows\\Fonts\\segoeui.ttf",
        # مسارات نظام ماك
        "/System/Library/Fonts/GeezaPro.ttc",
        "/Library/Fonts/Arial Bold.ttf",
        # أسماء الخطوط العامة
        "arialbd.ttf",
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
        raise RuntimeError("تعذر تحميل أي خط صالح للنظام.")


def generate_caption_image(
    word_text: str,
    video_width: int,
    video_height: int,
    font_size: Optional[int] = None
) -> np.ndarray:
    """
    إنشاء صورة RGBA شفافة تحتوي على الكلمة باللون الأصفر داخل مستطيل أسود شبه شفاف،
    بأسلوب كابشن التيك توك (TikTok Style).

    :param word_text: الكلمة المراد طباعتها
    :param video_width: عرض شاشة الفيديو
    :param video_height: ارتفاع شاشة الفيديو
    :param font_size: حجم الخط (إذا كان None يحسب تناسبياً مع أبعاد الفيديو)
    :return: مصفوفة Numpy لصورة RGBA
    """
    if font_size is None:
        # حجم خط متناسب مع الفيديو (مثالي لشاشات الهواتف والفيديو العرضي)
        font_size = max(36, int(video_height * 0.055))

    font = get_arabic_bold_font(font_size)

    # صورة مؤقتة لقياس أبعاد النص بدقة
    dummy_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    dummy_draw = ImageDraw.Draw(dummy_img)

    try:
        bbox = dummy_draw.textbbox((0, 0), word_text, font=font, direction="rtl")
    except Exception:
        bbox = dummy_draw.textbbox((0, 0), word_text, font=font)

    text_w = max(10, bbox[2] - bbox[0])
    text_h = max(10, bbox[3] - bbox[1])

    # إضافة هوامش أمان للمستطيل الأسود
    pad_x = int(font_size * 0.6)
    pad_y = int(font_size * 0.35)

    box_w = text_w + (pad_x * 2)
    box_h = text_h + (pad_y * 2)

    # إنشاء كانفاس شفاف بالكامل بحجم الصندوق فقط لتقليل استهلاك الذاكرة
    canvas = Image.new("RGBA", (box_w, box_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # رسم مستطيل أسود ذو حواف دائرية وبشفافية 75% (alpha = 190)
    corner_radius = max(8, int(box_h * 0.25))
    draw.rounded_rectangle(
        [(0, 0), (box_w, box_h)],
        radius=corner_radius,
        fill=(0, 0, 0, 190)
    )

    # طباعة الكلمة باللون الأصفر التفاعلي (#FFE600 -> 255, 230, 0)
    text_x = box_w // 2
    text_y = box_h // 2

    try:
        draw.text(
            (text_x, text_y),
            word_text,
            font=font,
            fill=(255, 230, 0, 255),
            anchor="mm",
            direction="rtl"
        )
    except Exception:
        draw.text(
            (text_x, text_y),
            word_text,
            font=font,
            fill=(255, 230, 0, 255),
            anchor="mm"
        )

    return np.array(canvas)


def apply_zoom_in_crop(clip, zoom_factor: float = 1.15):
    """
    اقتصاص وتكبير المقطع بنسبة 15% من المنتصف (Center Crop & Resize)
    """
    w, h = clip.size
    crop_w = int(w / zoom_factor)
    crop_h = int(h / zoom_factor)
    x1 = (w - crop_w) // 2
    y1 = (h - crop_h) // 2

    # قص وتكبير المقطع ليعود لأبعاده الأصلية بنعومة
    zoomed = clip.crop(x1=x1, y1=y1, width=crop_w, height=crop_h).resize((w, h))
    return zoomed


def apply_dynamic_edit(
    input_path: str,
    output_path: str,
    silence_threshold: float = -40.0,
    chunk_size: int = 10,
    padding_ms: int = 100,
    zoom_factor: float = 1.15,
    whisper_model: str = "small",
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    تنفيذ مسار المونتاج الديناميكي بالكامل:
    1. قص الصمت (Jump-cuts) لإنتاج فيديو أساسي مركز.
    2. تفريغ الصوت لاستخراج الجمل وتواقيت الكلمات.
    3. تطبيق Auto-Zoom بنسبة 15% بالتناوب على الجمل.
    4. طباعة الكلمات الصفراء بنمط تيك توك في منتصف الشاشة.

    :param input_path: مسار الفيديو الأصلي
    :param output_path: مسار حفظ الفيديو النهائي
    :param silence_threshold: عتبة الصمت
    :param chunk_size: دقة فحص الصمت
    :param padding_ms: هامش حماية أطراف الكلمات
    :param zoom_factor: نسبة التكبير (افتراضياً 1.15 أي 15%)
    :param whisper_model: نموذج faster-whisper المستخدم
    :param progress_callback: تحديث واجهة المستخدم
    :return: مسار الفيديو النهائي المصدّر
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"الملف غير موجود: {input_path}")

    if not is_video_file(input_path):
        raise ValueError("يتطلب المونتاج الديناميكي ملف فيديو (MP4, MOV, etc.) وليس ملف صوت فقط.")

    # مسارات الملفات المؤقتة
    base_dir = os.path.dirname(os.path.abspath(output_path))
    temp_dir = os.path.join(base_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    jumpcut_temp_video = os.path.join(temp_dir, "temp_jumpcut_base.mp4")

    def update_progress(val: float, msg: str):
        if progress_callback:
            progress_callback(val, msg)
        logger.info(f"Progress: {val*100:.1f}% - {msg}")

    # استيراد MoviePy عند الحاجة
    from moviepy.editor import (
        VideoFileClip,
        ImageClip,
        CompositeVideoClip,
        concatenate_videoclips
    )

    base_clip = None
    final_video = None
    sentence_clips = []
    caption_clips = []

    try:
        # الخطوة 1: قص الصمت لإنتاج فيديو أساسي متدفق
        update_progress(0.1, "1/4: تنفيذ قص الصمت التلقائي (Jump-cuts)...")
        remove_silence(
            input_path=input_path,
            output_path=jumpcut_temp_video,
            silence_threshold=silence_threshold,
            chunk_size=chunk_size,
            padding_ms=padding_ms
        )

        # الخطوة 2: تفريغ الفيديو الأساسي بعد قص الصمت
        update_progress(0.3, "2/4: استخراج التفريغ الزمني وتحديد الجمل عبر faster-whisper...")
        sentence_data = transcribe_sentences(
            audio_path=jumpcut_temp_video,
            model_size=whisper_model,
            language="ar"
        )
        word_data = transcribe_audio(
            audio_path=jumpcut_temp_video,
            model_size=whisper_model,
            language="ar"
        )

        # الخطوة 3: فتح الفيديو المقصوص وتطبيق Auto-Zoom بالتناوب على الجمل
        update_progress(0.5, "3/4: تطبيق التكبير السينمائي (Auto-Zoom 15%) بالتناوب بين الجمل...")
        base_clip = VideoFileClip(jumpcut_temp_video)
        video_w, video_h = base_clip.size
        video_duration = base_clip.duration

        # تقسيم الفيديو إلى كتل وفق فترات الجمل لتطبيق الزوم
        current_time = 0.0
        for i, sent in enumerate(sentence_data):
            sent_start = max(0.0, sent["start"])
            sent_end = min(video_duration, sent["end"])

            # إذا كان هناك فاصل زمني بسيط قبل بداية الجملة، نضيفه كوضع عادي
            if sent_start > current_time + 0.05:
                gap_clip = base_clip.subclip(current_time, sent_start)
                sentence_clips.append(gap_clip)

            if sent_end > sent_start + 0.05:
                chunk = base_clip.subclip(sent_start, sent_end)
                # نطبق التكبير 15% في الجمل الفردية (i % 2 == 1) ونبقي الزوجية عادية
                if i % 2 == 1:
                    zoomed_chunk = apply_zoom_in_crop(chunk, zoom_factor=zoom_factor)
                    sentence_clips.append(zoomed_chunk)
                else:
                    sentence_clips.append(chunk)

                current_time = sent_end

        # إضافة أي وقت متبقي في نهاية الفيديو
        if current_time < video_duration - 0.05:
            remaining_clip = base_clip.subclip(current_time, video_duration)
            sentence_clips.append(remaining_clip)

        if not sentence_clips:
            # إذا لم يتم تقسيم جمل واضحة، نستخدم الفيديو الأساسي كما هو
            zoomed_base = base_clip
        else:
            zoomed_base = concatenate_videoclips(sentence_clips, method="compose")

        # الخطوة 4: توليد نصوص التيك توك التفاعلية الصفراء المتزامنة
        update_progress(0.7, "4/4: إنشاء كابشن التيك توك الأصفر التفاعلي وتراكب الطبقات...")
        for item in word_data:
            word = item["word"]
            w_start = item["start"]
            w_end = item["end"]

            # التأكد من التوقيت المنطقي
            if w_end <= w_start or w_start >= zoomed_base.duration:
                continue

            w_end = min(w_end, zoomed_base.duration)
            duration = w_end - w_start
            if duration < 0.08:
                duration = 0.15  # ضمان ظهور بصري مريح للعين

            # توليد صورة الكلمة
            word_img_np = generate_caption_image(
                word_text=word,
                video_width=video_w,
                video_height=video_h
            )

            # تحويل مصفوفة الصورة إلى ImageClip في MoviePy
            txt_clip = (
                ImageClip(word_img_np, ismask=False, transparent=True)
                .set_start(w_start)
                .set_duration(duration)
                .set_position(("center", "center"))
            )
            caption_clips.append(txt_clip)

        # دمج الفيديو بعد الزوم مع طبقات النصوص
        final_video = CompositeVideoClip(
            [zoomed_base, *caption_clips],
            size=zoomed_base.size
        )

        update_progress(0.85, "جاري الرندرة النهائية وتصدير الفيديو الديناميكي...")
        temp_audio = os.path.join(temp_dir, "temp_dyn_audio.m4a")

        final_video.write_videofile(
            output_path,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=temp_audio,
            remove_temp=True,
            preset="medium",
            threads=4,
            logger=None
        )

        update_progress(1.0, "تم إنجاز المونتاج الديناميكي وتصدير الفيديو بنجاح!")
        return output_path

    except Exception as err:
        logger.error(f"خطأ في مسار المونتاج الديناميكي: {str(err)}", exc_info=True)
        raise err

    finally:
        # تنظيف وإغلاق كافة الكليبات في الذاكرة
        for c in sentence_clips:
            try:
                c.close()
            except Exception:
                pass

        for cap in caption_clips:
            try:
                cap.close()
            except Exception:
                pass

        if base_clip is not None:
            try:
                base_clip.close()
            except Exception:
                pass

        if final_video is not None:
            try:
                final_video.close()
            except Exception:
                pass

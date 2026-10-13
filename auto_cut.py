"""
auto_cut.py - وحدة قص الصمت التلقائي والمونتاج المعتمد على Jump-cuts
====================================================================
تعتمد هذه الوحدة على:
1. Pydub لتحليل مستوى الصوت واكتشاف فترات الصمت والكلام بدقة ملي-ثانية.
2. MoviePy لتقطيع مقاطع الفيديو وإعادة دمجها بسلاسة بناءً على الفواصل الزمنية المكتشفة.
3. معالجة شاملة للأخطاء وتنظيف الملفات المؤقتة تلقائياً.
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
from typing import List, Tuple, Callable, Optional
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

# إعداد التسجيل للمتابعة وتصحيح الأخطاء
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def apply_padding_and_merge(
    chunks: List[List[int]],
    total_duration_ms: int,
    padding_ms: int = 100
) -> List[Tuple[int, int]]:
    """
    إضافة هوامش أمان (Padding) قبل وبعد كل مقطع صوتي لمنع بتر بدايات ونهايات الكلمات،
    مع دمج الفترات المتداخلة بعد إضافة الهوامش.
    
    :param chunks: قائمة بفترات الكلام [[start_ms, end_ms], ...]
    :param total_duration_ms: المدة الكلية للملف بالملي ثانية
    :param padding_ms: هامش الأمان بالملي ثانية (افتراضياً 100 ملي ثانية)
    :return: قائمة بفترات الكلام المدمجة [(start_ms, end_ms), ...]
    """
    if not chunks:
        return []

    merged = []
    for start, end in chunks:
        start_padded = max(0, start - padding_ms)
        end_padded = min(total_duration_ms, end + padding_ms)

        if not merged:
            merged.append([start_padded, end_padded])
        else:
            last_start, last_end = merged[-1]
            # إذا تداخل المقطع الحالي مع السابق، ندمجهما
            if start_padded <= last_end:
                merged[-1][1] = max(last_end, end_padded)
            else:
                merged.append([start_padded, end_padded])

    return [(start, end) for start, end in merged]


def is_video_file(file_path: str) -> bool:
    """التحقق مما إذا كان الملف فيديو بناءً على الامتداد."""
    video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
    _, ext = os.path.splitext(file_path.lower())
    return ext in video_extensions


def remove_silence(
    input_path: str,
    output_path: str,
    silence_threshold: float = -40.0,
    chunk_size: int = 10,
    min_silence_len: int = 500,
    padding_ms: int = 100,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    قص فترات الصمت من ملف الفيديو أو الصوت وإنتاج مقطع سريع (Jump-cuts).
    
    :param input_path: مسار الملف المدخل (فيديو أو صوت)
    :param output_path: مسار حفظ الملف بعد المعالجة
    :param silence_threshold: عتبة الصمت بوحدة dBFS (أي صوت أقل من هذه القيمة يعتبر صمتاً)
    :param chunk_size: دقة خطوة الفحص بالملي ثانية (seek_step في Pydub)
    :param min_silence_len: الحد الأدنى لطول فترة الصمت حتى يتم اعتبارها صمتاً (بالملي ثانية)
    :param padding_ms: هامش أمان لتفادي قطع مخارج الحروف بالملي ثانية
    :param progress_callback: دالة رد اتصال لتحديث شريط التقدم في Streamlit
    :return: المسار النهائي للملف المصدّر
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"الملف المدخل غير موجود: {input_path}")

    # ضمان وجود المجلد الهدف
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    temp_dir = os.path.join(os.path.dirname(os.path.abspath(output_path)), "temp")
    os.makedirs(temp_dir, exist_ok=True)

    def update_progress(val: float, text: str):
        if progress_callback:
            progress_callback(val, text)
        logger.info(f"Progress: {val*100:.1f}% - {text}")

    video_clip = None
    final_clip = None
    subclips = []

    try:
        update_progress(0.1, "جاري قراءة وتحليل الإشارة الصوتية...")
        
        # استخراج وتحليل الصوت باستخدام Pydub
        audio = AudioSegment.from_file(input_path)
        total_duration_ms = len(audio)

        if total_duration_ms == 0:
            raise ValueError("الملف المدخل فارغ أو لا يحتوي على مدة زمنية صالحة.")

        update_progress(0.3, f"جاري فحص فترات الكلام فوق عتبة {silence_threshold} dBFS...")
        
        # الكشف عن أجزاء الصوت غير الصامتة (الكلام)
        raw_nonsilent = detect_nonsilent(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=silence_threshold,
            seek_step=chunk_size
        )

        # التحقق من وجود كلام مكتشف
        if not raw_nonsilent:
            raise ValueError(
                f"لم يتم اكتشاف أي فترات صوتية تتجاوز {silence_threshold} dBFS. "
                "يرجى خفض عتبة الصمت (مثلاً إلى -50 dBFS) أو التأكد من سلامة ميكروفون التسجيل."
            )

        # إضافة هوامش الأمان ودمج الفترات المتقاربة
        speech_intervals = apply_padding_and_merge(
            raw_nonsilent,
            total_duration_ms=total_duration_ms,
            padding_ms=padding_ms
        )

        total_kept_duration_ms = sum(end - start for start, end in speech_intervals)
        cut_duration_sec = (total_duration_ms - total_kept_duration_ms) / 1000.0
        logger.info(
            f"تم تحديد {len(speech_intervals)} مقطع كلام. "
            f"تم اختصار {cut_duration_sec:.2f} ثانية من الصمت غير المرغوب فيه."
        )

        update_progress(0.5, "جاري قص المقاطع وإعادة تجميعها (Jump-cuts)...")

        # معالجة ملف الفيديو عبر MoviePy
        if is_video_file(input_path):
            from moviepy.editor import VideoFileClip, concatenate_videoclips

            video_clip = VideoFileClip(input_path)
            video_duration_sec = video_clip.duration

            for start_ms, end_ms in speech_intervals:
                start_sec = max(0.0, start_ms / 1000.0)
                end_sec = min(video_duration_sec, end_ms / 1000.0)
                if end_sec > start_sec + 0.05:  # تجاهل المقاطع المتناهية الصغر
                    subclips.append(video_clip.subclip(start_sec, end_sec))

            if not subclips:
                raise ValueError("فشلت عملية إنشاء المقاطع الجزئية للفيديو.")

            final_clip = concatenate_videoclips(subclips, method="compose")

            update_progress(0.7, "جاري رندرة وتصدير الفيديو النهائي...")
            
            temp_audio_path = os.path.join(temp_dir, "temp_render_audio.m4a")
            final_clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=temp_audio_path,
                remove_temp=True,
                preset="medium",
                threads=4,
                logger=None  # إيقاف نصوص MoviePy التكرارية في الكونسول
            )

        # معالجة ملف الصوت فقط (MP3, WAV, etc.)
        else:
            update_progress(0.7, "جاري تجميع وحفظ الملف الصوتي النهائي...")
            combined_audio = AudioSegment.empty()
            for start_ms, end_ms in speech_intervals:
                combined_audio += audio[start_ms:end_ms]

            _, ext = os.path.splitext(output_path.lower())
            export_format = ext.replace(".", "") if ext else "mp3"
            combined_audio.export(output_path, format=export_format)

        update_progress(1.0, "اكتملت المعالجة بنجاح!")
        return output_path

    except Exception as e:
        logger.error(f"حدث خطأ أثناء معالجة قص الصمت: {str(e)}", exc_info=True)
        raise e

    finally:
        # إغلاق كافة الكليبات لتحرير الذاكرة وتفادي قفل الملفات
        for sub in subclips:
            try:
                sub.close()
            except Exception:
                pass

        if video_clip is not None:
            try:
                video_clip.close()
            except Exception:
                pass

        if final_clip is not None:
            try:
                final_clip.close()
            except Exception:
                pass


def get_speech_timestamps(
    input_path: str,
    silence_threshold: float = -40.0,
    chunk_size: int = 10,
    min_silence_len: int = 500,
    padding_ms: int = 100
) -> List[Tuple[float, float]]:
    """
    دالة مساعدة لإرجاع التواقيت الزمنية لفترات الكلام بوحدة الثواني،
    لاستخدامها في المراحل اللاحقة (المونتاج الديناميكي وتحديد الجمل).
    
    :return: قائمة من الأزواج [(start_sec, end_sec), ...]
    """
    audio = AudioSegment.from_file(input_path)
    raw_nonsilent = detect_nonsilent(
        audio,
        min_silence_len=min_silence_len,
        silence_thresh=silence_threshold,
        seek_step=chunk_size
    )
    merged = apply_padding_and_merge(raw_nonsilent, len(audio), padding_ms=padding_ms)
    return [(s / 1000.0, e / 1000.0) for s, e in merged]

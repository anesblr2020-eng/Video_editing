"""
transcriber.py - وحدة التفريغ الصوتي الزمني بدقة الكلمة (Word-Level Timestamps)
================================================================================
المرحلة 3: تعتمد هذه الوحدة على faster-whisper لتوفير تفريغ زمني دقيق وخفيف
يعمل محلياً بالكامل على المعالج (CPU) أو كرت الشاشة (CUDA) مع دعم كامل للغة العربية.
"""

import sys
import os

# إضافة مسار المجلد الحالي إلى أولويات البحث لضمان تعرف كل ملف على الملفات المجاورة في الاستضافة
_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)


import os
import logging
from typing import List, Dict, Any, Optional

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_optimal_device_settings():
    """
    تحديد الإعدادات المثلى للعتاد المحلي تلقائياً (GPU/CUDA مقابل CPU)
    لتجنب أي انهيار في التطبيق عند تشغيله على أجهزة مختلفة.
    """
    try:
        import torch
        if torch.cuda.is_available():
            logger.info("تم العثور على كرت شاشة يدعم CUDA. سيتم استخدام نمط GPU مع float16.")
            return "cuda", "float16"
    except ImportError:
        pass

    logger.info("سيتم استخدام المعالج المحلي (CPU) مع نمط الحسابات السريع int8.")
    return "cpu", "int8"


def transcribe_audio(
    audio_path: str,
    model_size: str = "small",
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
    language: Optional[str] = None,
    vad_filter: bool = True
) -> List[Dict[str, Any]]:
    """
    تفريغ الملف الصوتي أو الفيديو واستخراج التواقيت الزمنية الدقيقة لكل كلمة.

    :param audio_path: مسار ملف الصوت أو الفيديو (MP3, MP4, WAV, etc.)
    :param model_size: حجم نموذج Whisper المحلي (tiny, base, small, medium, large-v3)
    :param device: 'cpu' أو 'cuda' (إذا تُركت None فسيتم اكتشاف الأفضل تلقائياً)
    :param compute_type: نمط دقة الحسابات (int8, float16, float32)
    :param language: رمز اللغة (افتراضياً None للكشف التلقائي مع دعم كامل للعربية 'ar')
    :param vad_filter: استخدام مرشح اكتشاف الصوت البشري (Voice Activity Detection) لزيادة الدقة
    :return: قائمة من القواميس بالشكل: [{'word': 'كلمة', 'start': 1.2, 'end': 1.5, 'probability': 0.98}, ...]
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"الملف المطلوب تفريغه غير موجود: {audio_path}")

    # استيراد المكتبة محلياً مع معالجة أي خطأ في التثبيت
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise ImportError(
            "حزمة faster-whisper غير مثبتة. يرجى تثبيتها عبر: pip install faster-whisper"
        ) from e

    # تحديد نوع الجهاز ونمط الحساب المناسب
    detected_device, detected_compute = get_optimal_device_settings()
    final_device = device if device is not None else detected_device
    final_compute = compute_type if compute_type is not None else detected_compute

    logger.info(
        f"جاري تحميل نموذج Whisper ({model_size}) على {final_device} بنمط {final_compute}..."
    )

    try:
        # تحميل النموذج محلياً
        model = WhisperModel(
            model_size_or_path=model_size,
            device=final_device,
            compute_type=final_compute
        )

        logger.info(f"جاري تفريغ الصوت للملف: {audio_path}")

        # ضبط اللغة: دعم صريح للعربية أو كشف تلقائي ذكي
        target_language = language if language else None

        # تشغيل التفريغ مع تفعيل word_timestamps
        segments, info = model.transcribe(
            audio_path,
            word_timestamps=True,
            language=target_language,
            vad_filter=vad_filter,
            vad_parameters=dict(min_silence_duration_ms=400)
        )

        logger.info(f"تم اكتشاف اللغة: {info.language} بنسبة ثقة: {info.language_probability:.2f}")

        word_timestamps: List[Dict[str, Any]] = []

        # استخراج الكلمات والتواقيت بدقة الملي ثانية
        for segment in segments:
            if segment.words:
                for word_obj in segment.words:
                    cleaned_word = word_obj.word.strip()
                    if cleaned_word:
                        word_timestamps.append({
                            "word": cleaned_word,
                            "start": round(word_obj.start, 3),
                            "end": round(word_obj.end, 3),
                            "probability": round(word_obj.probability, 3)
                        })

        logger.info(f"اكتمل التفريغ الصوتي بنجاح. إجمالي الكلمات المستخرجة: {len(word_timestamps)} كلمة.")
        return word_timestamps

    except Exception as err:
        logger.error(f"حدث خطأ أثناء التفريغ الصوتي عبر faster-whisper: {str(err)}", exc_info=True)
        raise err


def transcribe_sentences(
    audio_path: str,
    model_size: str = "small",
    device: Optional[str] = None,
    compute_type: Optional[str] = None,
    language: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    دالة مساعدة لإرجاع الجمل الكاملة مع كلماتها وتواقيتها،
    وهي مخصصة للاستخدام في المرحلة 4 (المونتاج الديناميكي والـ Auto-Zoom على مستوى الجملة).
    
    :return: قائمة من القواميس تمثل الجمل:
             [{'text': 'جملة كاملة', 'start': 0.5, 'end': 3.2, 'words': [...]}, ...]
    """
    if not os.path.exists(audio_path):
        raise FileNotFoundError(f"الملف غير موجود: {audio_path}")

    from faster_whisper import WhisperModel

    detected_device, detected_compute = get_optimal_device_settings()
    final_device = device if device is not None else detected_device
    final_compute = compute_type if compute_type is not None else detected_compute

    model = WhisperModel(
        model_size_or_path=model_size,
        device=final_device,
        compute_type=final_compute
    )

    segments, info = model.transcribe(
        audio_path,
        word_timestamps=True,
        language=language,
        vad_filter=True
    )

    sentence_list = []
    for seg in segments:
        words = []
        if seg.words:
            for w in seg.words:
                cleaned_word = w.word.strip()
                if cleaned_word:
                    words.append({
                        "word": cleaned_word,
                        "start": round(w.start, 3),
                        "end": round(w.end, 3),
                        "probability": round(w.probability, 3)
                    })

        sentence_list.append({
            "text": seg.text.strip(),
            "start": round(seg.start, 3),
            "end": round(seg.end, 3),
            "words": words
        })

    return sentence_list

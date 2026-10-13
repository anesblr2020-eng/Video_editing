"""
auto_cut.py - وحدة قص الصمت الذكي وتحضير الملفات الصوتية والفيديوهات
=====================================================================
تتميز هذه الوحدة بـ:
1. دعم كامل لجميع صيغ الصوت والتسجيلات الصوتية من الهواتف والمتصفحات (mp3, wav, m4a, ogg, opus, aac, amr, webm, 3gp, flac, wma) مع التحويل التلقائي الذكي.
2. فحص فعلي لمسار الفيديو (وليس بالامتداد فقط) لمنع انهيار MoviePy إذا كان الملف صوتياً بامتداد mp4 أو webm.
3. معايرة تلقائية ذكية لعتبة الصمت (Auto Adaptive Silence Threshold) إذا كانت العتبة اليدوية لا تناسب مستوى تسجيل المايكروفون.
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import shutil
import subprocess
import logging
from typing import List, Tuple, Callable, Optional
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def is_video_file(file_path: str) -> bool:
    """
    التحقق مما إذا كان الملف يحتوي فعلياً على مسار فيديو صالح للعرض،
    وليس مجرد التحقق من الامتداد فقط (لأن بعض التسجيلات الصوتية تكون بامتداد webm أو mp4 أو 3gp).
    """
    if not file_path or not os.path.exists(file_path):
        return False

    video_extensions = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".3gp", ".ts", ".wmv", ".flv"}
    _, ext = os.path.splitext(file_path.lower())
    if ext not in video_extensions:
        return False

    try:
        from moviepy.editor import VideoFileClip
        clip = VideoFileClip(file_path)
        has_vid = bool(clip.w and clip.h and clip.duration and clip.duration > 0.05)
        if has_vid:
            frame = clip.get_frame(0)
            has_vid = frame is not None and frame.size > 0
        clip.close()
        return has_vid
    except Exception:
        return False


def ensure_playable_audio_or_video(input_path: str, working_dir: str) -> Tuple[str, bool]:
    """
    تحضير وتطبيع الملف المرفوع (خاصة التسجيلات الصوتية بصيغ الهواتف مثل ogg, opus, m4a, aac, amr, webm, 3gp):
    - إذا كان فيديو صالحاً: يرجع مساره و True.
    - إذا كان ملفاً صوتياً (أو تسجيل صوتي من الهاتف/المتصفح): يحوله تلقائياً عبر ffmpeg/pydub
      إلى ملف WAV/MP3 قياسي نظيف لضمان عمل المعاينة والتفريغ والموشن جرافيك بنسبة 100% دون أي فشل.
    """
    os.makedirs(working_dir, exist_ok=True)
    has_video = is_video_file(input_path)
    if has_video:
        return input_path, True

    # الملف صوتي: نقوم بتطبيعه إلى ملف WAV أو MP3 قياسي متوافق مع كل المتصفحات والمكتبات
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    normalized_wav = os.path.join(working_dir, f"normalized_{base_name}.wav")

    if os.path.exists(normalized_wav) and os.path.getsize(normalized_wav) > 1024:
        return normalized_wav, False

    try:
        # المحاولة الأولى عبر FFmpeg مباشرة لدعم كافة حاويات التسجيلات الصوتية في الهواتف
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            normalized_wav
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(normalized_wav) and os.path.getsize(normalized_wav) > 512:
            logger.info(f"تم تحويل وتطبيع الملف الصوتي بنجاح إلى: {normalized_wav}")
            return normalized_wav, False
    except Exception as e:
        logger.warning(f"تحويل FFmpeg المباشر تعذر ({e})، جاري الاستخدام عبر Pydub...")

    try:
        audio = AudioSegment.from_file(input_path)
        audio.export(normalized_wav, format="wav")
        return normalized_wav, False
    except Exception as e:
        logger.warning(f"تعذر تطبيع الملف الصوتي، سيتم استخدام المسار الأصلي: {e}")
        return input_path, False


def apply_padding_and_merge(
    chunks: List[List[int]],
    total_duration_ms: int,
    padding_ms: int = 100
) -> List[Tuple[int, int]]:
    """
    إضافة هوامش أمان (Padding) قبل وبعد كل مقطع صوتي لمنع بتر بدايات ونهايات الكلمات،
    مع دمج الفترات المتداخلة بعد إضافة الهوامش.
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
            if start_padded <= last_end:
                merged[-1][1] = max(last_end, end_padded)
            else:
                merged.append([start_padded, end_padded])

    return [(start, end) for start, end in merged]


def compute_adaptive_threshold(audio: AudioSegment, requested_threshold: float) -> float:
    """
    حساب عتبة صمت ذكية في حال كان الصوت منخفضاً جداً أو كانت العتبة اليدوية تحذف الكلام.
    """
    if len(audio) == 0 or audio.dBFS == -float("inf"):
        return requested_threshold

    mean_db = float(audio.dBFS)
    # إذا كانت العتبة المطلوبة أعلى من متوسط الصوت، نخفضها تلقائياً لحماية الكلام
    if requested_threshold >= mean_db - 2.0:
        adapted = max(-55.0, round(mean_db - 7.5, 1))
        logger.info(f"تم تعديل عتبة الصمت تلقائياً من {requested_threshold} إلى {adapted} dBFS لتناسب مستوى التسجيل.")
        return adapted
    return requested_threshold


def remove_silence(
    input_path: str,
    output_path: str,
    silence_threshold: float = -40.0,
    chunk_size: int = 10,
    min_silence_len: int = 450,
    padding_ms: int = 110,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    قص فترات الصمت من ملف الفيديو أو الصوت وإنتاج مقطع سريع ونظيف (Jump-cuts).
    يدعم المعايرة التلقائية الذكية في حال كان التسجيل الصوتي منخفضاً.
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"الملف المدخل غير موجود: {input_path}")

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

        audio = AudioSegment.from_file(input_path)
        total_duration_ms = len(audio)

        if total_duration_ms == 0:
            raise ValueError("الملف المدخل فارغ أو لا يحتوي على مدة زمنية صالحة.")

        effective_threshold = compute_adaptive_threshold(audio, silence_threshold)
        update_progress(0.3, f"جاري فحص فترات الكلام فوق عتبة {effective_threshold} dBFS...")

        raw_nonsilent = detect_nonsilent(
            audio,
            min_silence_len=min_silence_len,
            silence_thresh=effective_threshold,
            seek_step=chunk_size
        )

        # إذا لم يكتشف كلاماً، نخفض العتبة تدريجياً بدلاً من إيقاف العملية بخطأ
        if not raw_nonsilent:
            fallback_thresh = max(-60.0, float(audio.dBFS) - 10.0) if audio.dBFS != -float("inf") else -52.0
            logger.warning(f"إعادة الفحص بعتبة تكيّفية منخفضة ({fallback_thresh:.1f} dBFS)...")
            raw_nonsilent = detect_nonsilent(
                audio,
                min_silence_len=min_silence_len,
                silence_thresh=fallback_thresh,
                seek_step=chunk_size
            )

        # إذا بقي فارغاً، نحتفظ بكامل المقطع لضمان عدم فشل المعالجة أبداً
        if not raw_nonsilent:
            raw_nonsilent = [[0, total_duration_ms]]

        speech_intervals = apply_padding_and_merge(
            raw_nonsilent,
            total_duration_ms=total_duration_ms,
            padding_ms=padding_ms
        )

        total_kept_duration_ms = sum(end - start for start, end in speech_intervals)
        cut_duration_sec = max(0.0, (total_duration_ms - total_kept_duration_ms) / 1000.0)
        logger.info(
            f"تم تحديد {len(speech_intervals)} مقطع كلام. "
            f"تم اختصار {cut_duration_sec:.2f} ثانية من الصمت."
        )

        update_progress(0.5, "جاري قص المقاطع وإعادة تجميعها بسلاسة...")

        if is_video_file(input_path):
            from moviepy.editor import VideoFileClip, concatenate_videoclips

            video_clip = VideoFileClip(input_path)
            video_duration_sec = video_clip.duration

            for start_ms, end_ms in speech_intervals:
                start_sec = max(0.0, start_ms / 1000.0)
                end_sec = min(video_duration_sec, end_ms / 1000.0)
                if end_sec > start_sec + 0.05:
                    subclips.append(video_clip.subclip(start_sec, end_sec))

            if not subclips:
                subclips.append(video_clip)

            final_clip = concatenate_videoclips(subclips, method="compose")

            update_progress(0.75, "جاري رندرة وتصدير الفيديو النهائي...")
            temp_audio_path = os.path.join(temp_dir, "temp_render_audio.m4a")
            final_clip.write_videofile(
                output_path,
                codec="libx264",
                audio_codec="aac",
                temp_audiofile=temp_audio_path,
                remove_temp=True,
                preset="medium",
                threads=4,
                logger=None
            )
        else:
            update_progress(0.75, "جاري تجميع وتنقية الملف الصوتي النهائي...")
            combined_audio = AudioSegment.empty()
            for start_ms, end_ms in speech_intervals:
                combined_audio += audio[start_ms:end_ms]

            # تحسين توازن الصوت (Normalize) ليكون واضحاً ونقياً
            try:
                from pydub.effects import normalize
                combined_audio = normalize(combined_audio)
            except Exception:
                pass

            _, ext = os.path.splitext(output_path.lower())
            export_format = ext.replace(".", "") if ext else "mp3"
            if export_format in {"m4a", "aac", "mp4"}:
                export_format = "mp3"
                output_path = os.path.splitext(output_path)[0] + ".mp3"
            combined_audio.export(output_path, format=export_format)

        update_progress(1.0, f"اكتملت المعالجة بنجاح! (تم اختصار {cut_duration_sec:.1f} ثانية من الصمت)")
        return output_path

    except Exception as e:
        logger.error(f"حدث خطأ أثناء معالجة قص الصمت: {str(e)}", exc_info=True)
        raise e

    finally:
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
    min_silence_len: int = 450,
    padding_ms: int = 110
) -> List[Tuple[float, float]]:
    """إرجاع التواقيت الزمنية لفترات الكلام بوحدة الثواني."""
    audio = AudioSegment.from_file(input_path)
    effective_threshold = compute_adaptive_threshold(audio, silence_threshold)
    raw_nonsilent = detect_nonsilent(
        audio,
        min_silence_len=min_silence_len,
        silence_thresh=effective_threshold,
        seek_step=chunk_size
    )
    if not raw_nonsilent:
        return [(0.0, len(audio) / 1000.0)]
    merged = apply_padding_and_merge(raw_nonsilent, len(audio), padding_ms=padding_ms)
    return [(s / 1000.0, e / 1000.0) for s, e in merged]

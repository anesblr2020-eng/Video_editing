"""
auto_cut.py - وحدة قص الصمت الذكي الطبيعي (Natural Human Speech Cadence) وتحضير الوسائط
======================================================================================
تتميز هذه الوحدة بـ:
1. قص الصمت بأسلوب بشري طبيعي 100% (Natural Human Speech Cadence):
   - حماية مخارج الحروف الضعيفة والهمس وأواخر الكلمات عبر هوامش غير متماثلة (Pre-padding 220ms + Post-padding 280ms).
   - عدم قص التوقفات التنفسية الطبيعية القصيرة (فقط الصمت الفعلي الأطول من 700 ملي ثانية).
   - دمج الفجوات القصيرة (Gap Bridging < 420ms) لمنع التقطيع المزعج أو ظهور الكلام وكأنه "ملصق في بعضه".
2. معايرة ذكية لعتبة الصوت تقترب من أرضية الضجيج (Noise Floor) ولا تقترب أبداً من الكلام المنخفض.
3. دعم كامل لجميع صيغ الصوت والتسجيلات الصوتية والفيديو.
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import shutil
import subprocess
import logging
from typing import List, Tuple, Callable, Optional
import numpy as np
from pydub import AudioSegment
from pydub.silence import detect_nonsilent

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def is_video_file(file_path: str) -> bool:
    """التحقق مما إذا كان الملف يحتوي فعلياً على مسار فيديو صالح للعرض."""
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
    """تحضير وتطبيع الملف المرفوع لضمان عمل المعاينة والمعالجة بنسبة 100%."""
    os.makedirs(working_dir, exist_ok=True)
    has_video = is_video_file(input_path)
    if has_video:
        return input_path, True

    base_name = os.path.splitext(os.path.basename(input_path))[0]
    normalized_wav = os.path.join(working_dir, f"normalized_{base_name}.wav")

    if os.path.exists(normalized_wav) and os.path.getsize(normalized_wav) > 1024:
        return normalized_wav, False

    try:
        cmd = [
            "ffmpeg", "-y", "-i", input_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "2",
            normalized_wav
        ]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode == 0 and os.path.exists(normalized_wav) and os.path.getsize(normalized_wav) > 512:
            return normalized_wav, False
    except Exception:
        pass

    try:
        audio = AudioSegment.from_file(input_path)
        audio.export(normalized_wav, format="wav")
        return normalized_wav, False
    except Exception:
        return input_path, False


def apply_padding_and_merge(
    chunks: List[List[int]],
    total_duration_ms: int,
    padding_ms: int = 250,
    min_bridge_gap_ms: int = 420
) -> List[Tuple[int, int]]:
    """
    حماية طبيعية الكلام البشري (Natural Breath & Syllable Protection):
    1. إضافة هامش حماية قبل بداية الكلمة (Pre-padding) وهامش أطول قليلاً بعد نهايتها (Post-padding)
       لحماية مخارج الحروف الضعيفة والمدود في آخر الجمل حتى لا يُبتر أي حرف منطوق.
    2. دمج المقاطع المتقاربة التي تقل الفجوة بينها عن min_bridge_gap_ms (420 ملي ثانية)
       بحيث تبقى وقفات التنفس الطبيعية بين الكلمات سليمة ولا يبدو الكلام "ملصقاً في بعضه".
    """
    if not chunks:
        return []

    pre_pad = max(180, int(padding_ms * 0.90))
    post_pad = max(240, int(padding_ms * 1.15))

    merged = []
    for start, end in chunks:
        start_padded = max(0, start - pre_pad)
        end_padded = min(total_duration_ms, end + post_pad)

        if not merged:
            merged.append([start_padded, end_padded])
        else:
            last_start, last_end = merged[-1]
            # إذا كانت الفجوة بين المقطع السابق والحالي أقل من 420ms ندمجهما معاً ليبقى الكلام متصلاً بطبيعية
            if start_padded - last_end <= min_bridge_gap_ms:
                merged[-1][1] = max(last_end, end_padded)
            else:
                merged.append([start_padded, end_padded])

    return [(start, end) for start, end in merged]


def compute_adaptive_threshold(audio: AudioSegment, requested_threshold: float) -> float:
    """
    معايرة عتبة الصمت بذكاء لتكون قريبة من أرضية الضجيج (Noise Floor) وبعيدة عن الكلام المنخفض،
    مما يضمن عدم قص أي لحظة يتحدث فيها الإنسان بصوت هادئ.
    """
    if len(audio) == 0 or audio.dBFS == -float("inf"):
        return requested_threshold

    mean_db = float(audio.dBFS)
    try:
        chunk_levels = [
            c.dBFS for c in audio[::100]
            if c.dBFS != -float("inf") and c.dBFS > -85.0
        ]
        if chunk_levels:
            p15 = float(np.percentile(chunk_levels, 15))
            p85 = float(np.percentile(chunk_levels, 85))
            # نضع العتبة فوق أرضية الضجيج بقليل (18% فقط من المدى الديناميكي) لحماية كل الحروف المنطوقة
            safe_speech_thresh = p15 + 0.18 * (p85 - p15)
            max_allowed = min(-32.0, mean_db - 10.5)
            optimal = max(-55.0, min(max_allowed, safe_speech_thresh))
            # إذا كانت العتبة المطلوبة أعلى من الحد الآمن للكلام الهامس، نخفضها تلقائياً
            if requested_threshold > optimal + 2.0:
                logger.info(f"معايرة عتبة الصمت لحماية الكلام الطبيعي: {optimal:.1f} dBFS بدلاً من {requested_threshold} dBFS")
                return round(optimal, 1)
    except Exception:
        pass

    if requested_threshold >= mean_db - 8.0:
        return max(-55.0, round(mean_db - 11.0, 1))
    return requested_threshold


def remove_silence(
    input_path: str,
    output_path: str,
    silence_threshold: float = -42.0,
    chunk_size: int = 10,
    min_silence_len: int = 700,
    padding_ms: int = 250,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    قص فترات السكوت الطويلة فقط مع الحفاظ التام على طبيعية الكلام البشري ونفَس المتحدث.
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
        update_progress(0.1, "جاري تحليل الإشارة الصوتية وتحديد وقفات الكلام الطبيعية...")

        audio = AudioSegment.from_file(input_path)
        total_duration_ms = len(audio)

        if total_duration_ms == 0:
            raise ValueError("الملف المدخل فارغ أو لا يحتوي على مدة زمنية صالحة.")

        effective_threshold = compute_adaptive_threshold(audio, silence_threshold)
        effective_min_silence = max(600, int(min_silence_len))
        effective_padding = max(220, int(padding_ms))

        update_progress(0.3, f"فحص فترات السكوت الطويلة (> {effective_min_silence}ms) تحت عتبة {effective_threshold} dBFS...")

        raw_nonsilent = detect_nonsilent(
            audio,
            min_silence_len=effective_min_silence,
            silence_thresh=effective_threshold,
            seek_step=chunk_size
        )

        if not raw_nonsilent:
            fallback_thresh = max(-60.0, float(audio.dBFS) - 14.0) if audio.dBFS != -float("inf") else -54.0
            raw_nonsilent = detect_nonsilent(
                audio,
                min_silence_len=effective_min_silence,
                silence_thresh=fallback_thresh,
                seek_step=chunk_size
            )

        if not raw_nonsilent:
            raw_nonsilent = [[0, total_duration_ms]]

        speech_intervals = apply_padding_and_merge(
            raw_nonsilent,
            total_duration_ms=total_duration_ms,
            padding_ms=effective_padding,
            min_bridge_gap_ms=420
        )

        total_kept_duration_ms = sum(end - start for start, end in speech_intervals)
        cut_duration_sec = max(0.0, (total_duration_ms - total_kept_duration_ms) / 1000.0)
        logger.info(
            f"تم تحديد {len(speech_intervals)} مقطع متصل بطبيعية. "
            f"تم إزالة {cut_duration_sec:.2f} ثانية من السكوت الطويل فقط."
        )

        update_progress(0.5, "جاري تجميع المقاطع بانسيابية طبيعية...")

        if is_video_file(input_path):
            from moviepy.editor import VideoFileClip, concatenate_videoclips

            video_clip = VideoFileClip(input_path)
            video_duration_sec = video_clip.duration

            for start_ms, end_ms in speech_intervals:
                start_sec = max(0.0, start_ms / 1000.0)
                end_sec = min(video_duration_sec, end_ms / 1000.0)
                if end_sec > start_sec + 0.08:
                    subclips.append(video_clip.subclip(start_sec, end_sec))

            if not subclips:
                subclips.append(video_clip)

            final_clip = concatenate_videoclips(subclips, method="compose")

            update_progress(0.75, "جاري رندرة وتصدير الفيديو...")
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
            update_progress(0.75, "جاري دمج وتنقية الملف الصوتي بنعومة (Crossfade)...")
            combined_audio = AudioSegment.empty()
            for idx, (start_ms, end_ms) in enumerate(speech_intervals):
                segment_chunk = audio[start_ms:end_ms]
                if idx == 0 or len(combined_audio) < 30 or len(segment_chunk) < 30:
                    combined_audio += segment_chunk
                else:
                    # دمج متدرج ناعم (15ms Crossfade) لمنع أي طقة أو التصاق حاد بين الجمل
                    combined_audio = combined_audio.append(segment_chunk, crossfade=15)

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

        update_progress(1.0, f"اكتملت المعالجة بنجاح! (تم إزالة {cut_duration_sec:.1f} ثانية من السكوت الطويل)")
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
    silence_threshold: float = -42.0,
    chunk_size: int = 10,
    min_silence_len: int = 700,
    padding_ms: int = 250
) -> List[Tuple[float, float]]:
    """إرجاع التواقيت الزمنية لفترات الكلام بوحدة الثواني."""
    audio = AudioSegment.from_file(input_path)
    effective_threshold = compute_adaptive_threshold(audio, silence_threshold)
    raw_nonsilent = detect_nonsilent(
        audio,
        min_silence_len=max(600, min_silence_len),
        silence_thresh=effective_threshold,
        seek_step=chunk_size
    )
    if not raw_nonsilent:
        return [(0.0, len(audio) / 1000.0)]
    merged = apply_padding_and_merge(raw_nonsilent, len(audio), padding_ms=max(220, padding_ms))
    return [(s / 1000.0, e / 1000.0) for s, e in merged]

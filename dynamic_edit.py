"""
dynamic_edit.py - وحدة المونتاج الديناميكي، دمج الموشن جرافيك بالفيديو الأصلي، والمخرج الذكي الشامل (All-in-One)
=================================================================================================================
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

# معالجة فورية لتوافق Pillow 10+ مع MoviePy لمنع خطأ 'PIL.Image' has no attribute 'ANTIALIAS'
import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import logging
from typing import List, Dict, Any, Tuple, Optional, Callable
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from auto_cut import remove_silence, is_video_file
from transcriber import transcribe_audio, transcribe_sentences
from motion_text import (
    get_arabic_font,
    draw_arabic_text,
    measure_arabic_text,
    analyze_sentence_visual_metadata,
    create_studio_background,
    render_video_motion_overlay_card,
    create_kinetic_typography_video,
    MOTION_THEMES
)

try:
    from smart_analyzer import analyze_media_file, plan_smart_director_segments
except ImportError:
    analyze_media_file = None
    plan_smart_director_segments = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_arabic_bold_font(font_size: int) -> ImageFont.FreeTypeFont:
    """جلب خط عربي عريض متوافق مع تشكيل الحروف."""
    return get_arabic_font(font_size, bold=True)


def generate_caption_image(
    word_text: str,
    video_width: int,
    video_height: int,
    font_size: Optional[int] = None,
    highlight_color: Tuple[int, int, int] = (255, 230, 0),
    phrase_context: Optional[str] = None
) -> np.ndarray:
    """
    إنشاء صورة RGBA شفافة للكلمة المنطوقة (مع سياق اختياري) بأسلوب تيك توك وريلز الاحترافي،
    مع ضمان اتصال الحروف العربية والدارجة الجزائرية بشكل سليم.
    """
    if font_size is None:
        font_size = max(38, int(min(video_width, video_height) * 0.062))

    font = get_arabic_bold_font(font_size)
    dummy_img = Image.new("RGBA", (1, 1), (0, 0, 0, 0))
    dummy_draw = ImageDraw.Draw(dummy_img)

    text_w, text_h = measure_arabic_text(dummy_draw, word_text, font)

    pad_x = int(font_size * 0.65)
    pad_y = int(font_size * 0.38)

    box_w = text_w + (pad_x * 2)
    box_h = text_h + (pad_y * 2)

    canvas = Image.new("RGBA", (box_w + 8, box_h + 8), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    corner_radius = max(12, int(box_h * 0.28))
    draw.rounded_rectangle(
        [(0, 0), (box_w + 6, box_h + 6)],
        radius=corner_radius + 2,
        fill=(0, 0, 0, 95)
    )
    draw.rounded_rectangle(
        [(3, 3), (box_w + 3, box_h + 3)],
        radius=corner_radius,
        fill=(12, 16, 28, 215),
        outline=(*highlight_color, 210),
        width=3
    )

    text_x = (box_w + 6) // 2
    text_y = (box_h + 6) // 2

    draw_arabic_text(
        draw,
        (text_x, text_y),
        word_text,
        font=font,
        fill=(*highlight_color, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 230)
    )

    return np.array(canvas)


def apply_zoom_in_crop(clip, zoom_factor: float = 1.15):
    """اقتصاص وتكبير المقطع من المنتصف (Center Crop & Resize) بسلاسة."""
    if zoom_factor <= 1.01:
        return clip
    w, h = clip.size
    crop_w = int(w / zoom_factor)
    crop_h = int(h / zoom_factor)
    x1 = (w - crop_w) // 2
    y1 = (h - crop_h) // 2
    return clip.crop(x1=x1, y1=y1, width=crop_w, height=crop_h).resize((w, h))


def _build_base_video_from_audio_or_video(
    media_path: str,
    temp_dir: str,
    silence_threshold: float,
    chunk_size: int,
    padding_ms: int
) -> Tuple[Any, bool]:
    """
    تجهيز مقطع الفيديو الأساسي بعد قص الصمت.
    """
    from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip

    has_vid = is_video_file(media_path)
    if has_vid:
        jumpcut_temp_video = os.path.join(temp_dir, "temp_jumpcut_base.mp4")
        remove_silence(
            input_path=media_path,
            output_path=jumpcut_temp_video,
            silence_threshold=silence_threshold,
            chunk_size=chunk_size,
            padding_ms=padding_ms
        )
        return VideoFileClip(jumpcut_temp_video), True
    else:
        jumpcut_temp_audio = os.path.join(temp_dir, "temp_jumpcut_base.mp3")
        remove_silence(
            input_path=media_path,
            output_path=jumpcut_temp_audio,
            silence_threshold=silence_threshold,
            chunk_size=chunk_size,
            padding_ms=padding_ms
        )
        aud_clip = AudioFileClip(jumpcut_temp_audio)
        bg_arr = create_studio_background(1080, 1920, theme_name="cyber_gold")
        vid_clip = ImageClip(bg_arr).set_duration(aud_clip.duration).set_audio(aud_clip)
        vid_clip.filename = jumpcut_temp_audio
        return vid_clip, False


# ==============================================================================
# 1. النمط الثاني: المونتاج الديناميكي (Auto-Zoom + Jump-cuts + TikTok Captions)
# ==============================================================================
def apply_dynamic_edit(
    input_path: str,
    output_path: str,
    silence_threshold: float = -40.0,
    chunk_size: int = 10,
    padding_ms: int = 100,
    zoom_factor: float = 1.15,
    whisper_model: str = "small",
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    تنفيذ مسار المونتاج الديناميكي (يدعم كلاً من ملفات الفيديو والملفات الصوتية).
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

    from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips

    base_clip = None
    final_video = None
    sentence_clips = []
    caption_clips = []

    try:
        update_progress(0.1, "1/4: تنفيذ قص الصمت التلقائي وتجهيز المسار...")
        base_clip, has_vid = _build_base_video_from_audio_or_video(
            media_path=input_path,
            temp_dir=temp_dir,
            silence_threshold=silence_threshold,
            chunk_size=chunk_size,
            padding_ms=padding_ms
        )
        transcribe_source = getattr(base_clip, "filename", input_path) or input_path

        update_progress(0.3, "2/4: تفريغ الكلام وتحديد الجمل (مع دعم الدارجة الجزائرية)...")
        sentence_data = transcribe_sentences(
            audio_path=transcribe_source,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        word_data = transcribe_audio(
            audio_path=transcribe_source,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )

        update_progress(0.5, "3/4: تطبيق التكبير السينمائي (Auto-Zoom 15%) بالتناوب بين الجمل...")
        video_w, video_h = base_clip.size
        video_duration = base_clip.duration

        current_time = 0.0
        for i, sent in enumerate(sentence_data):
            sent_start = max(0.0, sent["start"])
            sent_end = min(video_duration, sent["end"])

            if sent_start > current_time + 0.05:
                sentence_clips.append(base_clip.subclip(current_time, sent_start))

            if sent_end > sent_start + 0.05:
                chunk = base_clip.subclip(sent_start, sent_end)
                if i % 2 == 1:
                    sentence_clips.append(apply_zoom_in_crop(chunk, zoom_factor=zoom_factor))
                else:
                    sentence_clips.append(chunk)
                current_time = sent_end

        if current_time < video_duration - 0.05:
            sentence_clips.append(base_clip.subclip(current_time, video_duration))

        zoomed_base = concatenate_videoclips(sentence_clips, method="compose") if sentence_clips else base_clip

        update_progress(0.7, "4/4: إنشاء كابشن التيك توك التفاعلي وتراكب الطبقات...")
        caption_pos = ("center", int(video_h * 0.74)) if has_vid else ("center", "center")

        for item in word_data:
            word = item["word"]
            w_start = item["start"]
            w_end = min(item["end"], zoomed_base.duration)
            if w_end <= w_start or w_start >= zoomed_base.duration:
                continue

            duration = max(0.14, w_end - w_start)
            word_img_np = generate_caption_image(
                word_text=word,
                video_width=video_w,
                video_height=video_h
            )

            txt_clip = (
                ImageClip(word_img_np, ismask=False, transparent=True)
                .set_start(w_start)
                .set_duration(duration)
                .set_position(caption_pos)
            )
            caption_clips.append(txt_clip)

        final_video = CompositeVideoClip([zoomed_base, *caption_clips], size=zoomed_base.size)

        update_progress(0.85, "جاري الرندرة النهائية وتصدير الفيديو الديناميكي...")
        temp_audio = os.path.join(temp_dir, "temp_dyn_audio.m4a")

        final_video.write_videofile(
            output_path,
            fps=24 if not has_vid else None,
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


# ==============================================================================
# 2. النمط الخامس: دمج الموشن جرافيك بالفيديو الأصلي
# ==============================================================================
def apply_motion_overlay_on_video(
    input_path: str,
    output_path: str,
    silence_threshold: float = -40.0,
    chunk_size: int = 10,
    padding_ms: int = 100,
    whisper_model: str = "small",
    ollama_model: str = "llama3",
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    """
    نمط دمج الموشن جرافيك بالفيديو الأصلي.
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

    from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips

    base_clip = None
    final_video = None
    sentence_clips = []
    overlay_clips = []

    try:
        update_progress(0.1, "1/5: تنظيف الصمت وتجهيز الفيديو الأصلي...")
        base_clip, has_vid = _build_base_video_from_audio_or_video(
            media_path=input_path,
            temp_dir=temp_dir,
            silence_threshold=silence_threshold,
            chunk_size=chunk_size,
            padding_ms=padding_ms
        )
        transcribe_source = getattr(base_clip, "filename", input_path) or input_path

        update_progress(0.28, "2/5: تفريغ الكلام بدقة الكلمة والجملة (دعم الدارجة الجزائرية)...")
        sentence_data = transcribe_sentences(
            audio_path=transcribe_source,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        word_data = transcribe_audio(
            audio_path=transcribe_source,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )

        video_w, video_h = base_clip.size
        video_duration = base_clip.duration
        theme_keys = list(MOTION_THEMES.keys())

        update_progress(0.48, "3/5: تصميم بطاقات الموشن جرافيك والأيقونات الفيكتور لكل جملة...")
        current_time = 0.0
        for idx, sent in enumerate(sentence_data):
            s_start = max(0.0, sent["start"])
            s_end = min(video_duration, sent["end"])

            if s_start > current_time + 0.05:
                sentence_clips.append(base_clip.subclip(current_time, s_start))

            if s_end > s_start + 0.05:
                chunk = base_clip.subclip(s_start, s_end)
                if idx % 2 == 1:
                    chunk = apply_zoom_in_crop(chunk, zoom_factor=1.12)
                sentence_clips.append(chunk)
                current_time = s_end

                meta = analyze_sentence_visual_metadata(
                    sent["text"],
                    model_name=ollama_model,
                    groq_api_key=groq_api_key,
                    gemini_api_key=gemini_api_key,
                    openai_api_key=openai_api_key
                )
                overlay_mode = "graphic_burst" if (idx == 0 or idx % 3 == 0) else "corner_card"
                theme_name = theme_keys[idx % len(theme_keys)]
                card_arr = render_video_motion_overlay_card(
                    keyword_title=meta["keyword"],
                    icon_type=meta["icon_type"],
                    video_width=video_w,
                    video_height=video_h,
                    mode=overlay_mode,
                    theme_name=theme_name
                )
                card_clip = (
                    ImageClip(card_arr, ismask=False, transparent=True)
                    .set_start(s_start)
                    .set_duration(max(0.2, s_end - s_start))
                    .set_position(("center", "center"))
                )
                overlay_clips.append(card_clip)

        if current_time < video_duration - 0.05:
            sentence_clips.append(base_clip.subclip(current_time, video_duration))

        zoomed_base = concatenate_videoclips(sentence_clips, method="compose") if sentence_clips else base_clip

        update_progress(0.68, "4/5: إضافة الكابشن التفاعلي في الثلث السفلي من الفيديو...")
        lower_third_y = int(video_h * 0.78)
        for item in word_data:
            w_txt = item["word"]
            w_start = item["start"]
            w_end = min(item["end"], zoomed_base.duration)
            if w_end <= w_start or w_start >= zoomed_base.duration:
                continue
            dur = max(0.14, w_end - w_start)
            cap_arr = generate_caption_image(
                word_text=w_txt,
                video_width=video_w,
                video_height=video_h,
                highlight_color=(255, 230, 0)
            )
            c_clip = (
                ImageClip(cap_arr, ismask=False, transparent=True)
                .set_start(w_start)
                .set_duration(dur)
                .set_position(("center", lower_third_y))
            )
            overlay_clips.append(c_clip)

        final_video = CompositeVideoClip([zoomed_base, *overlay_clips], size=zoomed_base.size)

        update_progress(0.85, "5/5: رندرة وتصدير الفيديو المدمج بالموشن جرافيك...")
        temp_audio = os.path.join(temp_dir, "temp_overlay_audio.m4a")
        final_video.write_videofile(
            output_path,
            fps=24 if not has_vid else None,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=temp_audio,
            remove_temp=True,
            preset="medium",
            threads=4,
            logger=None
        )

        update_progress(1.0, "تم دمج الموشن جرافيك مع الفيديو الأصلي بنجاح!")
        return output_path

    except Exception as err:
        logger.error(f"خطأ في دمج الموشن جرافيك بالفيديو الأصلي: {str(err)}", exc_info=True)
        raise err

    finally:
        for c in sentence_clips:
            try:
                c.close()
            except Exception:
                pass
        for ov in overlay_clips:
            try:
                ov.close()
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


# ==============================================================================
# 3. النمط السادس: المخرج الذكي الشامل (Smart Auto All-in-One)
# ==============================================================================
def apply_smart_director_all_in_one(
    input_path: str,
    output_path: str,
    media_analysis: Optional[Dict[str, Any]] = None,
    whisper_model: Optional[str] = None,
    ollama_model: str = "llama3",
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    المخرج التلقائي الذكي (Smart Auto Director & All-in-One).
    """
    if not os.path.exists(input_path):
        raise FileNotFoundError(f"الملف غير موجود: {input_path}")

    def update_progress(val: float, msg: str):
        if progress_callback:
            progress_callback(val, msg)
        logger.info(f"Progress: {val*100:.1f}% - {msg}")

    update_progress(0.05, "1/5: تشغيل المحلل الذكي لفحص الصوت والفيديو واختيار أفضل الإعدادات والموديلات...")
    if media_analysis is None and analyze_media_file is not None:
        media_analysis = analyze_media_file(
            input_path,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
    elif media_analysis is None:
        media_analysis = {
            "has_video": is_video_file(input_path),
            "optimal_silence_threshold": -38.0,
            "optimal_padding_ms": 110,
            "optimal_chunk_size": 10,
            "optimal_whisper_model": whisper_model or "small",
            "visual_motion_score": 8.0,
            "criteria_reasons": ["تم ضبط الإعدادات التلقائية الذكية."],
        }

    chosen_silence_thresh = float(media_analysis.get("optimal_silence_threshold", -38.0))
    chosen_padding_ms = int(media_analysis.get("optimal_padding_ms", 110))
    chosen_chunk_size = int(media_analysis.get("optimal_chunk_size", 10))
    chosen_whisper = whisper_model or str(media_analysis.get("optimal_whisper_model", "small"))
    has_vid = bool(media_analysis.get("has_video", is_video_file(input_path)))
    motion_score = float(media_analysis.get("visual_motion_score", 8.0))

    base_dir = os.path.dirname(os.path.abspath(output_path))
    temp_dir = os.path.join(base_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    if not has_vid:
        update_progress(0.18, f"2/5: تنظيف الصمت تلقائياً بعتبة ذكية ({chosen_silence_thresh} dBFS)...")
        clean_audio_path = os.path.join(temp_dir, "temp_smart_clean_audio.mp3")
        remove_silence(
            input_path=input_path,
            output_path=clean_audio_path,
            silence_threshold=chosen_silence_thresh,
            chunk_size=chosen_chunk_size,
            padding_ms=chosen_padding_ms
        )
        out_path = create_kinetic_typography_video(
            input_path=clean_audio_path,
            output_path=output_path,
            whisper_model=chosen_whisper,
            ollama_model=ollama_model,
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key,
            progress_callback=progress_callback
        )
        return out_path, media_analysis

    from moviepy.editor import ImageClip, CompositeVideoClip, concatenate_videoclips

    base_clip = None
    final_video = None
    sentence_clips = []
    overlay_clips = []

    try:
        update_progress(0.18, f"2/5: قص الصمت الذكي بعتبة مُعايرة تلقائياً ({chosen_silence_thresh} dBFS)...")
        base_clip, _ = _build_base_video_from_audio_or_video(
            media_path=input_path,
            temp_dir=temp_dir,
            silence_threshold=chosen_silence_thresh,
            chunk_size=chosen_chunk_size,
            padding_ms=chosen_padding_ms
        )
        transcribe_source = getattr(base_clip, "filename", input_path) or input_path

        update_progress(0.35, f"3/5: تفريغ الكلام عبر ({chosen_whisper}) مع معالج الدارجة الجزائرية...")
        sentence_data = transcribe_sentences(
            audio_path=transcribe_source,
            model_size=chosen_whisper,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        word_data = transcribe_audio(
            audio_path=transcribe_source,
            model_size=chosen_whisper,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )

        if plan_smart_director_segments is not None:
            planned_sentences = plan_smart_director_segments(
                sentences=sentence_data,
                has_video=True,
                visual_motion_score=motion_score
            )
        else:
            planned_sentences = sentence_data

        media_analysis["directed_segments_count"] = len(planned_sentences)

        update_progress(0.55, "4/5: توزيع الأدوار البصرية ودمج الموشن جرافيك والزوم مع الفيديو الأصلي...")
        video_w, video_h = base_clip.size
        video_duration = base_clip.duration
        theme_keys = list(MOTION_THEMES.keys())

        current_time = 0.0
        for idx, sent in enumerate(planned_sentences):
            s_start = max(0.0, sent["start"])
            s_end = min(video_duration, sent["end"])
            role = sent.get("director_role", "motion_card_overlay")
            z_factor = float(sent.get("zoom_factor", 1.12))

            if s_start > current_time + 0.05:
                sentence_clips.append(base_clip.subclip(current_time, s_start))

            if s_end > s_start + 0.05:
                chunk = base_clip.subclip(s_start, s_end)
                if z_factor > 1.01:
                    chunk = apply_zoom_in_crop(chunk, zoom_factor=z_factor)
                sentence_clips.append(chunk)
                current_time = s_end

                if role in {"hook_motion_overlay", "graphic_burst_overlay", "motion_card_overlay"}:
                    meta = analyze_sentence_visual_metadata(
                        sent["text"],
                        model_name=ollama_model,
                        groq_api_key=groq_api_key,
                        gemini_api_key=gemini_api_key,
                        openai_api_key=openai_api_key
                    )
                    ov_mode = "graphic_burst" if role in {"hook_motion_overlay", "graphic_burst_overlay"} else "corner_card"
                    theme_name = theme_keys[idx % len(theme_keys)]
                    card_arr = render_video_motion_overlay_card(
                        keyword_title=meta["keyword"],
                        icon_type=meta["icon_type"],
                        video_width=video_w,
                        video_height=video_h,
                        mode=ov_mode,
                        theme_name=theme_name
                    )
                    c_clip = (
                        ImageClip(card_arr, ismask=False, transparent=True)
                        .set_start(s_start)
                        .set_duration(max(0.2, s_end - s_start))
                        .set_position(("center", "center"))
                    )
                    overlay_clips.append(c_clip)

        if current_time < video_duration - 0.05:
            sentence_clips.append(base_clip.subclip(current_time, video_duration))

        zoomed_base = concatenate_videoclips(sentence_clips, method="compose") if sentence_clips else base_clip

        lower_third_y = int(video_h * 0.78)
        for i, item in enumerate(word_data):
            w_txt = item["word"]
            w_start = item["start"]
            w_end = min(item["end"], zoomed_base.duration)
            if w_end <= w_start or w_start >= zoomed_base.duration:
                continue
            dur = max(0.14, w_end - w_start)
            hl_color = (255, 230, 0) if (i % 4 != 3) else (0, 245, 212)
            cap_arr = generate_caption_image(
                word_text=w_txt,
                video_width=video_w,
                video_height=video_h,
                highlight_color=hl_color
            )
            w_clip = (
                ImageClip(cap_arr, ismask=False, transparent=True)
                .set_start(w_start)
                .set_duration(dur)
                .set_position(("center", lower_third_y))
            )
            overlay_clips.append(w_clip)

        final_video = CompositeVideoClip([zoomed_base, *overlay_clips], size=zoomed_base.size)

        update_progress(0.85, "5/5: رندرة وتصدير الفيديو النهائي بالنمط التلقائي الشامل...")
        temp_audio = os.path.join(temp_dir, "temp_smart_director_audio.m4a")
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

        update_progress(1.0, "اكتمل إخراج الفيديو بالنمط التلقائي الشامل (All-in-One) بنجاح!")
        return output_path, media_analysis

    except Exception as err:
        logger.error(f"خطأ في مسار المخرج الذكي الشامل: {str(err)}", exc_info=True)
        raise err

    finally:
        for c in sentence_clips:
            try:
                c.close()
            except Exception:
                pass
        for ov in overlay_clips:
            try:
                ov.close()
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

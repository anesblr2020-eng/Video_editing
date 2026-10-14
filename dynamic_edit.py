"""
dynamic_edit.py - وحدة المونتاج الديناميكي ودمج الموشن جرافيك المتحرك إطاراً بإطار فوق الفيديو الأصلي
====================================================================================================
يعالج هذا الملف مشكلة بقاء بطاقة واحدة ثابتة أو تقطع الكابشن في الفيديوهات (مثل 6314.mp4) عبر:
1. استخدام المحرك اللحظي `render_live_video_motion_frame` الذي يرسم ويحرك الموشن جرافيك والكابشن إطاراً بإطار (`VideoClip.fl`) فوق الفيديو الأصلي!
2. توليد مشهد رسومي وبطاقة متحركة جديدة كل 1.4 - 1.9 ثانية (`Micro-Scenes`) تنزلق بفيزياء زنبركية وتتغير مع كل فكرة في الكلام.
3. شريط كابشن كاريوكي متصل يعرض العبارة كاملة ويضيء الكلمة المنطوقة لحظياً ليمشي "سوا سوا" مع الصوت بدون أي اختفاء.
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

# معالجة فورية لتوافق Pillow 10+ مع MoviePy
import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import logging
from typing import List, Dict, Any, Tuple, Optional, Callable
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from auto_cut import remove_silence, is_video_file
from transcriber import transcribe_audio, transcribe_sentences, split_words_into_micro_scenes
from motion_text import (
    get_arabic_font,
    draw_arabic_text,
    measure_arabic_text,
    classify_micro_scene_blueprint,
    create_studio_background,
    render_live_video_motion_frame,
    create_kinetic_typography_video,
    MOTION_THEMES
)

try:
    from smart_analyzer import (
        analyze_media_file,
        plan_smart_director_segments,
        plan_product_ad_segments
    )
except ImportError:
    analyze_media_file = None
    plan_smart_director_segments = None
    plan_product_ad_segments = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def get_arabic_bold_font(font_size: int) -> ImageFont.FreeTypeFont:
    return get_arabic_font(font_size, bold=True)


def generate_caption_image(
    word_text: str,
    video_width: int,
    video_height: int,
    font_size: Optional[int] = None,
    highlight_color: Tuple[int, int, int] = (255, 230, 0),
    phrase_context: Optional[str] = None
) -> np.ndarray:
    """إنشاء صورة RGBA لكابشن التيك توك وريلز الاحترافي."""
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
    draw.rounded_rectangle([(0, 0), (box_w + 6, box_h + 6)], radius=corner_radius + 2, fill=(0, 0, 0, 95))
    draw.rounded_rectangle(
        [(3, 3), (box_w + 3, box_h + 3)],
        radius=corner_radius,
        fill=(12, 16, 28, 215),
        outline=(*highlight_color, 210),
        width=3
    )

    draw_arabic_text(
        draw,
        ((box_w + 6) // 2, (box_h + 6) // 2),
        word_text,
        font=font,
        fill=(*highlight_color, 255),
        stroke_width=2,
        stroke_fill=(0, 0, 0, 230)
    )
    return np.array(canvas)


def apply_zoom_in_crop(clip, zoom_factor: float = 1.14):
    """اقتصاص وتكبير المقطع من المنتصف بسلاسة."""
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
    """تجهيز مقطع الفيديو الأساسي بعد قص الصمت الطبيعي."""
    from moviepy.editor import VideoFileClip, AudioFileClip, ImageClip

    has_vid = is_video_file(media_path)
    if has_vid:
        jumpcut_temp_video = os.path.join(temp_dir, "temp_jumpcut_base.mp4")
        remove_silence(
            input_path=media_path,
            output_path=jumpcut_temp_video,
            silence_threshold=silence_threshold,
            chunk_size=chunk_size,
            padding_ms=max(220, padding_ms)
        )
        return VideoFileClip(jumpcut_temp_video), True
    else:
        jumpcut_temp_audio = os.path.join(temp_dir, "temp_jumpcut_base.mp3")
        remove_silence(
            input_path=media_path,
            output_path=jumpcut_temp_audio,
            silence_threshold=silence_threshold,
            chunk_size=chunk_size,
            padding_ms=max(220, padding_ms)
        )
        aud_clip = AudioFileClip(jumpcut_temp_audio)
        bg_arr = create_studio_background(1080, 1920, theme_name="crimson_energy")
        vid_clip = ImageClip(bg_arr).set_duration(aud_clip.duration).set_audio(aud_clip)
        vid_clip.filename = jumpcut_temp_audio
        return vid_clip, False


def _build_storyboard_for_video(
    words_data: List[Dict[str, Any]],
    total_duration: float,
    product_name_override: Optional[str] = None,
    cta_override: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    بناء جدول المشاهد المتجددة (كل 1.4 إلى 1.9 ثانية) للفيديو بحيث يحصل كل مشهد على:
    - رسمة موشن جرافيك متحركة خاصة به (`scene_type`)
    - عنوان تسويقي واضح (`badge_label`)
    - ثيم لوني متجدد (`theme_name`)
    - نسبة تكبير كاميرا ديناميكية (`zoom_factor`).
    """
    micro_scenes = split_words_into_micro_scenes(words_data, max_words_per_scene=4, max_duration_per_scene=1.9)
    storyboard: List[Dict[str, Any]] = []
    prev_s_type = None

    for idx, sc in enumerate(micro_scenes):
        bp = classify_micro_scene_blueprint(
            scene_text=sc["text"],
            scene_index=idx,
            total_scenes=len(micro_scenes),
            prev_scene_type=prev_s_type
        )
        prev_s_type = bp["scene_type"]

        if idx == 0 and product_name_override:
            bp["badge_label"] = product_name_override
        elif idx == len(micro_scenes) - 1 and cta_override:
            bp["badge_label"] = cta_override

        s_start = float(sc["start"])
        s_end = float(micro_scenes[idx + 1]["start"]) if (idx + 1 < len(micro_scenes)) else total_duration

        zoom = 1.15 if idx == 0 else (1.12 if idx % 2 == 1 else 1.0)
        storyboard.append({
            "index": idx,
            "start": s_start,
            "end": max(s_start + 0.18, s_end),
            "text": sc["text"],
            "words": sc["words"],
            "word_strings": [w["word"] for w in sc["words"]],
            "zoom_factor": zoom,
            **bp
        })

    return storyboard


# ==============================================================================
# 1. محرك الرندرة الموحد للفيديو مع الموشن جرافيك المتحرك إطاراً بإطار
# ==============================================================================
def _render_video_with_live_motion_graphics(
    input_path: str,
    output_path: str,
    silence_threshold: float = -42.0,
    chunk_size: int = 10,
    padding_ms: int = 240,
    whisper_model: str = "small",
    dialect_mode: str = "algerian_darija",
    product_name_override: Optional[str] = None,
    cta_override: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Tuple[str, Dict[str, Any]]:
    """
    يركب الموشن جرافيك المتحرك والكابشن الكاريوكي المتزامن إطاراً بإطار (`fl`) فوق الفيديو الأصلي،
    مما يضمن تغير الرسومات والبطاقات كل 1.5 ثانية وتحركها الفعلي ومزامنتها التامة مع الدارجة الجزائرية!
    """
    base_dir = os.path.dirname(os.path.abspath(output_path))
    temp_dir = os.path.join(base_dir, "temp")
    os.makedirs(temp_dir, exist_ok=True)

    def update_progress(val: float, msg: str):
        if progress_callback:
            progress_callback(val, msg)
        logger.info(f"Progress: {val*100:.1f}% - {msg}")

    if not is_video_file(input_path):
        clean_audio = os.path.join(temp_dir, "temp_clean_audio.mp3")
        remove_silence(input_path, clean_audio, silence_threshold=silence_threshold, padding_ms=padding_ms)
        out = create_kinetic_typography_video(
            input_path=clean_audio,
            output_path=output_path,
            whisper_model=whisper_model,
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key,
            progress_callback=progress_callback
        )
        return out, {"scenes_count": 12}

    from moviepy.editor import concatenate_videoclips

    base_clip = None
    zoomed_base = None
    final_video = None
    sentence_clips = []

    try:
        update_progress(0.12, "1/4: إزالة السكوت الطويل بانسيابية طبيعية وتجهيز الفيديو...")
        base_clip, _ = _build_base_video_from_audio_or_video(
            media_path=input_path,
            temp_dir=temp_dir,
            silence_threshold=silence_threshold,
            chunk_size=chunk_size,
            padding_ms=padding_ms
        )
        transcribe_source = getattr(base_clip, "filename", input_path) or input_path

        update_progress(0.32, "2/4: تفريغ الدارجة الجزائرية عبر المحرك الثلاثي (ar-DZ + Whisper)...")
        word_data = transcribe_audio(
            audio_path=transcribe_source,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )

        video_duration = float(base_clip.duration)
        storyboard = _build_storyboard_for_video(
            words_data=word_data,
            total_duration=video_duration,
            product_name_override=product_name_override,
            cta_override=cta_override
        )

        update_progress(0.55, f"3/4: تطبيق التكبير السينمائي وتجهيز {len(storyboard)} مشهد موشن جرافيك متحرك...")
        current_time = 0.0
        for sc in storyboard:
            s_start = max(0.0, float(sc["start"]))
            s_end = min(video_duration, float(sc["end"]))
            z_factor = float(sc.get("zoom_factor", 1.12))

            if s_start > current_time + 0.04:
                sentence_clips.append(base_clip.subclip(current_time, s_start))

            if s_end > s_start + 0.04:
                chunk = base_clip.subclip(s_start, s_end)
                if z_factor > 1.01:
                    chunk = apply_zoom_in_crop(chunk, zoom_factor=z_factor)
                sentence_clips.append(chunk)
                current_time = s_end

        if current_time < video_duration - 0.04:
            sentence_clips.append(base_clip.subclip(current_time, video_duration))

        zoomed_base = concatenate_videoclips(sentence_clips, method="compose") if sentence_clips else base_clip

        # تطبيق دالة الرسم المتحرك إطاراً بإطار فوق الفيديو
        def _frame_filter(get_frame, t: float) -> np.ndarray:
            raw_frame = get_frame(t)
            return render_live_video_motion_frame(
                base_frame_rgb=raw_frame,
                t=t,
                total_duration=video_duration,
                storyboard=storyboard,
                words_data=word_data
            )

        final_video = zoomed_base.fl(_frame_filter)

        update_progress(0.82, "4/4: رندرة وتصدير الفيديو النهائي مع الموشن جرافيك المتحرك...")
        temp_audio = os.path.join(temp_dir, "temp_live_motion_audio.m4a")
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

        update_progress(1.0, f"اكتمل إنتاج الفيديو بنجاح ({len(storyboard)} مشهد موشن جرافيك متحرك ومتزامن)!")
        return output_path, {"scenes_count": len(storyboard), "duration": video_duration}

    except Exception as err:
        logger.error(f"خطأ أثناء رندرة الموشن جرافيك على الفيديو: {str(err)}", exc_info=True)
        raise err

    finally:
        for c in sentence_clips:
            try:
                c.close()
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
# 2. الدوال القياسية المستدعاة من الواجهة (app.py)
# ==============================================================================
def apply_product_ad_mode(
    input_path: str,
    output_path: str,
    product_name_override: Optional[str] = None,
    cta_override: Optional[str] = None,
    silence_threshold: float = -42.0,
    padding_ms: int = 240,
    whisper_model: str = "small",
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> Tuple[str, Dict[str, Any]]:
    return _render_video_with_live_motion_graphics(
        input_path=input_path,
        output_path=output_path,
        silence_threshold=silence_threshold,
        padding_ms=padding_ms,
        whisper_model=whisper_model,
        dialect_mode=dialect_mode,
        product_name_override=product_name_override,
        cta_override=cta_override,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        progress_callback=progress_callback
    )


def apply_motion_overlay_on_video(
    input_path: str,
    output_path: str,
    silence_threshold: float = -42.0,
    chunk_size: int = 10,
    padding_ms: int = 250,
    whisper_model: str = "small",
    ollama_model: str = "llama3",
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    out_path, _ = _render_video_with_live_motion_graphics(
        input_path=input_path,
        output_path=output_path,
        silence_threshold=silence_threshold,
        chunk_size=chunk_size,
        padding_ms=padding_ms,
        whisper_model=whisper_model,
        dialect_mode=dialect_mode,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        progress_callback=progress_callback
    )
    return out_path


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
            "optimal_silence_threshold": -42.0,
            "optimal_padding_ms": 250,
            "optimal_chunk_size": 10,
            "optimal_whisper_model": whisper_model or "small",
        }

    out_path, info = _render_video_with_live_motion_graphics(
        input_path=input_path,
        output_path=output_path,
        silence_threshold=float(media_analysis.get("optimal_silence_threshold", -42.0)),
        chunk_size=int(media_analysis.get("optimal_chunk_size", 10)),
        padding_ms=int(media_analysis.get("optimal_padding_ms", 250)),
        whisper_model=whisper_model or str(media_analysis.get("optimal_whisper_model", "small")),
        dialect_mode=dialect_mode,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        progress_callback=progress_callback
    )
    media_analysis.update(info)
    return out_path, media_analysis


def apply_dynamic_edit(
    input_path: str,
    output_path: str,
    silence_threshold: float = -42.0,
    chunk_size: int = 10,
    padding_ms: int = 250,
    zoom_factor: float = 1.15,
    whisper_model: str = "small",
    dialect_mode: str = "algerian_darija",
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None
) -> str:
    out_path, _ = _render_video_with_live_motion_graphics(
        input_path=input_path,
        output_path=output_path,
        silence_threshold=silence_threshold,
        chunk_size=chunk_size,
        padding_ms=padding_ms,
        whisper_model=whisper_model,
        dialect_mode=dialect_mode,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        progress_callback=progress_callback
    )
    return out_path

"""
dynamic_edit.py - وحدة المونتاج الديناميكي، دمج المشاهد الرسومية، مشاهد B-Roll، والمخرج الذكي الشامل
=======================================================================================================
تنفذ هذه الوحدة أوامر "مخطط المخرج الشامل (Master Director Plan)" الصادرة من المحلل الذكي:
- تستورد 3 إلى 4 مشاهد B-Roll حقيقية خالية من حقوق الملكية في اللحظات المناسبة لدعم المحتوى.
- تتنقل بين أنماط التراكب بذكاء: الشاشة الكاملة للموشن جرافيك، مقاطع B-Roll الواقعية، البطاقات العلوية، واللقطات الصافية.
- تدمج الكابشن الكاريوكي المتزامن وشارات الموشن جرافيك فوق مشاهد الـ B-Roll مع استمرار صوت المتحدث.
"""

import sys
import os

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import PIL.ImageDraw
_orig_rounded_rect = PIL.ImageDraw.ImageDraw.rounded_rectangle

def _safe_rounded_rectangle(self, xy, radius=0, fill=None, outline=None, width=1, *, corners=None):
    try:
        if isinstance(xy[0], (list, tuple)):
            (x0, y0), (x1, y1) = xy
        else:
            x0, y0, x1, y1 = xy
        x_min, x_max = min(x0, x1), max(x0, x1)
        y_min, y_max = min(y0, y1), max(y0, y1)
        if x_max - x_min < 1:
            x_max = x_min + 1
        if y_max - y_min < 1:
            y_max = y_min + 1
        safe_r = max(0, min(int(radius), int((x_max - x_min) // 2), int((y_max - y_min) // 2)))
        return _orig_rounded_rect(self, [(x_min, y_min), (x_max, y_max)], radius=safe_r, fill=fill, outline=outline, width=width, corners=corners)
    except Exception:
        pass

PIL.ImageDraw.ImageDraw.rounded_rectangle = _safe_rounded_rectangle

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
    render_single_scene_canvas,
    render_master_directed_video_frame,
    create_kinetic_typography_video,
    MOTION_THEMES
)
import inspect
import hashlib
import requests

def _safe_call(func, **kwargs):
    try:
        sig = inspect.signature(func)
        has_var_kw = any(p.kind == inspect.Parameter.VAR_KEYWORD for p in sig.parameters.values())
        if has_var_kw:
            return func(**kwargs)
        filtered = {k: v for k, v in kwargs.items() if k in sig.parameters}
        return func(**filtered)
    except Exception:
        return func(**kwargs)

try:
    from stock_video_finder import get_stock_broll_clip, process_broll_clip_for_timeline
except ImportError:
    import importlib.util
    _cur = os.path.dirname(os.path.abspath(__file__))
    if _cur not in sys.path:
        sys.path.insert(0, _cur)
    _stock_path = os.path.join(_cur, "stock_video_finder.py")
    if os.path.exists(_stock_path):
        _spec = importlib.util.spec_from_file_location("stock_video_finder", _stock_path)
        _mod = importlib.util.module_from_spec(_spec)
        sys.modules["stock_video_finder"] = _mod
        _spec.loader.exec_module(_mod)
        get_stock_broll_clip = getattr(_mod, "get_stock_broll_clip")
        process_broll_clip_for_timeline = getattr(_mod, "process_broll_clip_for_timeline")
    else:
        _DIRECT_VIDEOS = {
            'video_editor': ['https://assets.mixkit.co/videos/preview/mixkit-hands-of-a-man-working-on-a-computer-43407-large.mp4'],
            'ai_technology': ['https://assets.mixkit.co/videos/preview/mixkit-digital-animation-of-screens-with-data-41526-large.mp4'],
            'busy_no_time': ['https://assets.mixkit.co/videos/preview/mixkit-sand-flowing-through-an-hourglass-42861-large.mp4'],
            'smartphone_reels': ['https://assets.mixkit.co/videos/preview/mixkit-young-man-using-a-smartphone-in-the-city-43180-large.mp4'],
            'developer_coding': ['https://assets.mixkit.co/videos/preview/mixkit-hands-of-a-man-typing-on-a-laptop-keyboard-41315-large.mp4'],
            'creator_studio': ['https://assets.mixkit.co/videos/preview/mixkit-man-working-with-headphones-on-in-an-office-43411-large.mp4']
        }
        def get_stock_broll_clip(category: str, target_duration: float, cache_dir: str, width: int = 1080, height: int = 1920, pexels_api_key: Optional[str] = None, **kw) -> Optional[str]:
            os.makedirs(cache_dir, exist_ok=True)
            urls = _DIRECT_VIDEOS.get(category.lower(), _DIRECT_VIDEOS['video_editor'])
            for u in urls:
                uh = hashlib.md5(u.encode()).hexdigest()[:10]
                dest = os.path.join(cache_dir, f"stock_{category}_{uh}.mp4")
                if os.path.exists(dest) and os.path.getsize(dest) > 50000:
                    return dest
                try:
                    r = requests.get(u, headers={'User-Agent': 'Mozilla/5.0'}, stream=True, timeout=12)
                    if r.status_code == 200:
                        with open(dest, 'wb') as f:
                            for ch in r.iter_content(131072):
                                if ch:
                                    f.write(ch)
                        if os.path.exists(dest) and os.path.getsize(dest) > 50000:
                            return dest
                except Exception:
                    pass
            return None

        def process_broll_clip_for_timeline(raw_video_path: str, target_duration: float, width: int, height: int, **kw):
            from moviepy.editor import VideoFileClip, vfx
            clip = VideoFileClip(raw_video_path).without_audio()
            ow, oh = clip.size
            sc = max(width / float(ow), height / float(oh))
            nw, nh = int(ow * sc), int(oh * sc)
            res = clip.resize((nw, nh))
            cropped = res.crop(x1=max(0, (nw - width) // 2), y1=max(0, (nh - height) // 2), width=width, height=height)
            if cropped.duration < target_duration:
                return cropped.fx(vfx.loop, duration=target_duration)
            return cropped.subclip(0, target_duration)

try:
    from smart_analyzer import (
        analyze_media_file,
        generate_master_director_plan,
        plan_smart_director_segments,
        plan_product_ad_segments
    )
except ImportError:
    analyze_media_file = None
    generate_master_director_plan = None
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
    draw.rounded_rectangle([(3, 3), (box_w + 3, box_h + 3)], radius=corner_radius, fill=(12, 16, 28, 215), outline=(*highlight_color, 210), width=3)

    text_x = (box_w + 6) // 2
    text_y = (box_h + 6) // 2
    draw_arabic_text(draw, (text_x, text_y), word_text, font=font, fill=(*highlight_color, 255), stroke_width=2, stroke_fill=(0, 0, 0, 230))
    return np.array(canvas)


def apply_zoom_in_crop(clip, zoom_factor: float = 1.15):
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


# ==============================================================================
# المحرك التنفيذي الموحد لأوامر مخطط المخرج الشامل مع دمج مشاهد B-Roll
# ==============================================================================
def _execute_master_director_pipeline(
    input_path: str,
    output_path: str,
    silence_threshold: float = -42.0,
    chunk_size: int = 10,
    padding_ms: int = 240,
    whisper_model: str = "small",
    dialect_mode: str = "algerian_darija",
    product_name_override: Optional[str] = None,
    cta_override: Optional[str] = None,
    enable_stock_broll: bool = True,
    pexels_api_key: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    caption_mode: str = "bottom_modern",
    **kwargs
) -> Tuple[str, Dict[str, Any]]:
    """
    تنفيذ أوامر مخطط المخرج الشامل الصادرة من المحلل الذكي:
    - قص الصمت الطبيعي.
    - استخراج الكلمات وتوليد مخطط المخرج الشامل.
    - جلب ودمج 3-4 مشاهد B-Roll حقيقية خالية من حقوق الملكية في اللحظات المناسبة.
    - رندرة الإطارات إطاراً بإطار مع الكابشن الكاريوكي وشارات الموشن جرافيك.
    """
    base_dir = os.path.dirname(os.path.abspath(output_path))
    temp_dir = os.path.join(base_dir, "temp")
    stock_dir = os.path.join(temp_dir, "stock_videos")
    os.makedirs(temp_dir, exist_ok=True)
    os.makedirs(stock_dir, exist_ok=True)

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
        return out, {"director_plan_scenes": 12}

    from moviepy.editor import concatenate_videoclips

    base_clip = None
    zoomed_base = None
    final_video = None
    sentence_clips = []
    broll_clips_to_close = []

    try:
        update_progress(0.10, "1/5: تحليل الإشارة الصوتية وإزالة السكوت الطويل بانسيابية طبيعية...")
        base_clip, _ = _build_base_video_from_audio_or_video(
            media_path=input_path,
            temp_dir=temp_dir,
            silence_threshold=silence_threshold,
            chunk_size=chunk_size,
            padding_ms=padding_ms
        )
        transcribe_source = getattr(base_clip, "filename", input_path) or input_path

        update_progress(0.25, "2/5: تفريغ الكلام بدقة وتوليد مخطط المخرج متعدد الأنماط المكانية...")
        word_data = transcribe_audio(
            audio_path=transcribe_source,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        micro_scenes = split_words_into_micro_scenes(word_data, max_words_per_scene=4, max_duration_per_scene=2.0)
        video_duration = float(base_clip.duration)
        video_w, video_h = base_clip.size

        if generate_master_director_plan is not None:
            master_plan = _safe_call(
                generate_master_director_plan,
                sentences_or_micro_scenes=micro_scenes,
                total_duration=video_duration,
                has_video=True,
                visual_motion_score=8.0,
                enable_stock_broll=enable_stock_broll,
                product_name_override=product_name_override,
                cta_override=cta_override,
                groq_api_key=groq_api_key,
                gemini_api_key=gemini_api_key,
                openai_api_key=openai_api_key
            )
        else:
            master_plan = micro_scenes

        # استيراد وتجهيز مشاهد الـ B-Roll المختارة تلقائياً (3 إلى 4 مشاهد)
        broll_scenes_count = sum(1 for sc in master_plan if sc.get("layout_mode") == "stock_broll")
        update_progress(0.42, f"3/5: جلب {broll_scenes_count} مشاهد B-Roll حقيقية خالية من حقوق الملكية من الإنترنت...")

        current_time = 0.0
        for sc in master_plan:
            s_start = max(0.0, float(sc.get("start", 0.0)))
            s_end = min(video_duration, float(sc.get("end", s_start + 1.8)))
            dur = max(0.2, s_end - s_start)
            z_factor = float(sc.get("zoom_factor", 1.12))
            layout_mode = sc.get("layout_mode", "top_overlay")

            # إذا كانت هناك فجوة قبل المشهد نملؤها بالمقطع الأصلي
            if s_start > current_time + 0.04:
                sentence_clips.append(base_clip.subclip(current_time, s_start))

            if s_end > s_start + 0.04:
                orig_sub = base_clip.subclip(s_start, s_end)
                used_broll = False
                if layout_mode == "stock_broll" and enable_stock_broll and callable(get_stock_broll_clip) and callable(process_broll_clip_for_timeline):
                    try:
                        cat = sc.get("stock_category", "video_editor")
                        raw_broll = get_stock_broll_clip(
                            category=cat,
                            target_duration=dur,
                            cache_dir=stock_dir,
                            width=video_w,
                            height=video_h,
                            pexels_api_key=pexels_api_key
                        )
                        if raw_broll and os.path.exists(raw_broll):
                            broll_processed = process_broll_clip_for_timeline(
                                raw_video_path=raw_broll,
                                target_duration=dur,
                                width=video_w,
                                height=video_h
                            )
                            if orig_sub.audio is not None:
                                broll_processed = broll_processed.set_audio(orig_sub.audio)
                            broll_clips_to_close.append(broll_processed)
                            sentence_clips.append(broll_processed)
                            used_broll = True
                    except Exception as b_err:
                        logger.warning(f"تعذر إدراج مشهد B-Roll، سيتم استخدام الكاميرا الأصلية: {b_err}")

                if not used_broll:
                    chunk = orig_sub
                    if z_factor > 1.01:
                        chunk = apply_zoom_in_crop(chunk, zoom_factor=z_factor)
                    sentence_clips.append(chunk)

                current_time = s_end

        if current_time < video_duration - 0.04:
            sentence_clips.append(base_clip.subclip(current_time, video_duration))

        zoomed_base = concatenate_videoclips(sentence_clips, method="compose") if sentence_clips else base_clip
        if base_clip.audio is not None and zoomed_base is not base_clip:
            try:
                zoomed_base = zoomed_base.set_audio(base_clip.audio.subclip(0, min(base_clip.audio.duration, zoomed_base.duration)))
            except Exception:
                pass

        bg_cache = {
            t_name: create_studio_background(video_w, video_h, theme_name=t_name)
            for t_name in MOTION_THEMES.keys()
        }

        update_progress(0.65, f"4/5: تصيير الموشن جرافيك والكابشن فوق المشاهد (شاشة كاملة، B-Roll، وبطاقات)...")

        def _master_frame_filter(get_frame, t: float) -> np.ndarray:
            raw_frame = get_frame(t)
            return _safe_call(
                render_master_directed_video_frame,
                base_frame_rgb=raw_frame,
                t=t,
                total_duration=video_duration,
                master_plan=master_plan,
                words_data=word_data,
                bg_cache=bg_cache,
                audio_level=0.75,
                caption_mode=caption_mode
            )

        final_video = zoomed_base.fl(_master_frame_filter)

        update_progress(0.85, "5/5: الرندرة النهائية وتصدير الفيديو المخرج بالكامل...")
        temp_audio = os.path.join(temp_dir, "temp_master_audio.m4a")
        final_video.write_videofile(
            output_path,
            fps=24,
            codec="libx264",
            audio_codec="aac",
            temp_audiofile=temp_audio,
            remove_temp=True,
            preset="medium",
            threads=4,
            logger=None
        )

        update_progress(1.0, f"اكتمل إخراج الفيديو بنجاح ({len(master_plan)} لقطة مخرجة و {broll_scenes_count} مشاهد B-Roll)! ")
        return output_path, {
            "director_scenes": len(master_plan),
            "broll_scenes_count": broll_scenes_count,
            "duration": video_duration
        }

    except Exception as err:
        logger.error(f"خطأ أثناء تنفيذ الإخراج الشامل: {str(err)}", exc_info=True)
        raise err

    finally:
        for c in sentence_clips:
            try:
                c.close()
            except Exception:
                pass
        for bc in broll_clips_to_close:
            try:
                bc.close()
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
# الدوال القياسية المربوطة بالواجهة (app.py)
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
    pexels_api_key: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    caption_mode: str = "bottom_modern",
    **kwargs
) -> Tuple[str, Dict[str, Any]]:
    return _execute_master_director_pipeline(
        input_path=input_path,
        output_path=output_path,
        silence_threshold=silence_threshold,
        padding_ms=padding_ms,
        whisper_model=whisper_model,
        dialect_mode=dialect_mode,
        product_name_override=product_name_override,
        cta_override=cta_override,
        enable_stock_broll=True,
        pexels_api_key=pexels_api_key,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        progress_callback=progress_callback,
        caption_mode=caption_mode
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
    pexels_api_key: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    caption_mode: str = "bottom_modern",
    **kwargs
) -> str:
    out, _ = _execute_master_director_pipeline(
        input_path=input_path,
        output_path=output_path,
        silence_threshold=silence_threshold,
        chunk_size=chunk_size,
        padding_ms=padding_ms,
        whisper_model=whisper_model,
        dialect_mode=dialect_mode,
        enable_stock_broll=True,
        pexels_api_key=pexels_api_key,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        progress_callback=progress_callback,
        caption_mode=caption_mode
    )
    return out


def apply_smart_director_all_in_one(
    input_path: str,
    output_path: str,
    media_analysis: Optional[Dict[str, Any]] = None,
    whisper_model: Optional[str] = None,
    ollama_model: str = "llama3",
    dialect_mode: str = "algerian_darija",
    pexels_api_key: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    caption_mode: str = "bottom_modern",
    **kwargs
) -> Tuple[str, Dict[str, Any]]:
    return _execute_master_director_pipeline(
        input_path=input_path,
        output_path=output_path,
        silence_threshold=-42.0,
        padding_ms=250,
        whisper_model=whisper_model or "small",
        dialect_mode=dialect_mode,
        enable_stock_broll=True,
        pexels_api_key=pexels_api_key,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        progress_callback=progress_callback,
        caption_mode=caption_mode
    )


def apply_dynamic_edit(
    input_path: str,
    output_path: str,
    silence_threshold: float = -42.0,
    chunk_size: int = 10,
    padding_ms: int = 250,
    zoom_factor: float = 1.15,
    whisper_model: str = "small",
    dialect_mode: str = "algerian_darija",
    pexels_api_key: Optional[str] = None,
    groq_api_key: Optional[str] = None,
    gemini_api_key: Optional[str] = None,
    openai_api_key: Optional[str] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    caption_mode: str = "bottom_modern",
    **kwargs
) -> str:
    out, _ = _execute_master_director_pipeline(
        input_path=input_path,
        output_path=output_path,
        silence_threshold=silence_threshold,
        chunk_size=chunk_size,
        padding_ms=padding_ms,
        whisper_model=whisper_model,
        dialect_mode=dialect_mode,
        enable_stock_broll=False,
        pexels_api_key=pexels_api_key,
        groq_api_key=groq_api_key,
        gemini_api_key=gemini_api_key,
        openai_api_key=openai_api_key,
        progress_callback=progress_callback,
        caption_mode=caption_mode
    )
    return out

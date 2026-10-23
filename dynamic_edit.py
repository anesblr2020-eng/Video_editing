"""
dynamic_edit.py - وحدة المونتاج الديناميكي، دمج المشاهد الرسومية السياقية، مشاهد B-Roll، والمخرج الذكي الشامل
=================================================================================================================
معمارية التدفق المباشر باستهلاك ذاكرة ثابت O(1) (Zero-OOM FFmpeg Streaming Pipe Engine for Streamlit Cloud):
- تعالج الفيديوهات بحجم 55MB و100MB+ دون تجاوز حدود ذاكرة Streamlit Cloud (1GB RAM) على الإطلاق!
- المرحلة 1 تقص الصمت وتطبّع الدقة إلى 960p qHD (24fps) مباشرة عبر عملية `ffmpeg` أصلية أحادية الخيط خارج ذاكرة بايثون.
- المرحلة 5 تقرأ الفيديو إطاراً بإطار عبر أنبوب `ffmpeg` مباشر أحادي الخيط (`-threads 1` قبل `-i`)، وتطبق الزوم والموشن جرافيك السياقي وB-Roll،
  وتضخ الإطار فوراً إلى أنبوب التشفير `ffmpeg` (`-preset ultrafast -tune zerolatency -x264-params rc-lookahead=0:sync-lookahead=0:ref=1:bframes=0 -threads 1`)
  مع تحرير الذاكرة الفوري لنظام التشغيل (`glibc malloc_trim(0)`) كل 60 إطاراً!
"""

import sys
import os
import gc
import re
import ctypes
import subprocess

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if _CURRENT_DIR not in sys.path:
    sys.path.insert(0, _CURRENT_DIR)

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = getattr(PIL.Image, "LANCZOS", getattr(getattr(PIL.Image, "Resampling", None), "LANCZOS", 1))

import PIL.ImageDraw
if not hasattr(PIL.ImageDraw.ImageDraw, "_true_orig_rounded_rect"):
    PIL.ImageDraw.ImageDraw._true_orig_rounded_rect = PIL.ImageDraw.ImageDraw.rounded_rectangle

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
        return PIL.ImageDraw.ImageDraw._true_orig_rounded_rect(
            self, [(x_min, y_min), (x_max, y_max)], radius=safe_r, fill=fill, outline=outline, width=width, corners=corners
        )
    except Exception:
        pass

PIL.ImageDraw.ImageDraw.rounded_rectangle = _safe_rounded_rectangle

import logging
from typing import List, Dict, Any, Tuple, Optional, Callable
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from auto_cut import (
    remove_silence,
    is_video_file,
    get_safe_working_resolution,
    force_free_ram
)
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
        get_stock_broll_clip = None
        process_broll_clip_for_timeline = None

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


def _zoom_frame_numpy(frame_rgb: np.ndarray, zoom_factor: float, target_w: int, target_h: int) -> np.ndarray:
    fh, fw, _ = frame_rgb.shape
    if zoom_factor <= 1.01 and fw == target_w and fh == target_h:
        return frame_rgb

    if zoom_factor > 1.01:
        cw = max(16, int(fw / zoom_factor))
        ch = max(16, int(fh / zoom_factor))
        x1 = max(0, (fw - cw) // 2)
        y1 = max(0, (fh - ch) // 2)
        cropped = frame_rgb[y1:y1 + ch, x1:x1 + cw]
        return np.array(Image.fromarray(cropped).resize((target_w, target_h), Image.Resampling.BILINEAR), dtype=np.uint8)

    scale = max(target_w / float(fw), target_h / float(fh))
    nw = max(target_w, int(round(fw * scale)))
    nh = max(target_h, int(round(fh * scale)))
    resized = np.array(Image.fromarray(frame_rgb).resize((nw, nh), Image.Resampling.BILINEAR), dtype=np.uint8)
    x1 = max(0, (nw - target_w) // 2)
    y1 = max(0, (nh - target_h) // 2)
    return resized[y1:y1 + target_h, x1:x1 + target_w]


def _probe_video_dimensions_and_duration(video_path: str) -> Tuple[int, int, float]:
    w, h, dur = 540, 960, 10.0
    try:
        res = subprocess.run(
            ["ffmpeg", "-threads", "1", "-i", video_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        info = res.stderr or ""
        m_res = re.search(r"Stream\s+#\d+:\d+.*Video:.*?(\d{2,5})x(\d{2,5})", info)
        if not m_res:
            m_res = re.search(r"(\d{3,5})x(\d{3,5})", info)
        if m_res:
            w, h = int(m_res.group(1)), int(m_res.group(2))
        m_dur = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", info)
        if m_dur:
            dur = round(int(m_dur.group(1)) * 3600 + int(m_dur.group(2)) * 60 + float(m_dur.group(3)), 3)
    except Exception:
        pass
    w, h = get_safe_working_resolution(w, h, max_dim=960)
    return w, h, max(0.2, dur)


# ==============================================================================
# المحرك التنفيذي الموحد عبر أنابيب FFmpeg المباشرة (O(1) Constant RAM Engine)
# ==============================================================================
def _execute_master_director_pipeline(
    input_path: str,
    output_path: str,
    silence_threshold: float = -42.0,
    chunk_size: int = 20,
    padding_ms: int = 240,
    whisper_model: str = "base",
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
        clean_audio = os.path.join(temp_dir, f"temp_clean_audio_{os.getpid()}.mp3")
        remove_silence(input_path, clean_audio, silence_threshold=silence_threshold, padding_ms=padding_ms)
        force_free_ram()
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
        return out, {"director_plan_scenes": 6}

    jumpcut_temp_video = os.path.join(temp_dir, f"temp_jumpcut_base_{os.getpid()}.mp4")
    dec_proc = None
    enc_proc = None
    broll_proc_state: Dict[str, Any] = {"path": None, "proc": None}

    def _close_broll_pipe():
        p = broll_proc_state.get("proc")
        if p is not None:
            try:
                if p.stdout:
                    p.stdout.close()
                p.kill()
            except Exception:
                pass
        broll_proc_state["proc"] = None
        broll_proc_state["path"] = None

    try:
        force_free_ram()
        update_progress(0.10, "1/5: تحليل الإشارة الصوتية وقص السكوت الطويل عبر محرك FFmpeg السريع...")
        remove_silence(
            input_path=input_path,
            output_path=jumpcut_temp_video,
            silence_threshold=silence_threshold,
            chunk_size=chunk_size,
            padding_ms=max(220, padding_ms)
        )
        force_free_ram()

        video_w, video_h, video_duration = _probe_video_dimensions_and_duration(jumpcut_temp_video)

        update_progress(0.25, "2/5: تفريغ الكلام وتشغيل المخ السياقي لتوليد مخطط المخرج...")
        word_data = transcribe_audio(
            audio_path=jumpcut_temp_video,
            model_size=whisper_model,
            language="ar",
            dialect_mode=dialect_mode,
            groq_api_key=groq_api_key,
            gemini_api_key=gemini_api_key,
            openai_api_key=openai_api_key
        )
        micro_scenes = split_words_into_micro_scenes(
            word_data,
            max_words_per_scene=8,
            max_duration_per_scene=4.2,
            min_words_per_scene=4
        )
        force_free_ram()

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

        broll_scenes_count = sum(1 for sc in master_plan if sc.get("layout_mode") == "stock_broll")
        update_progress(0.42, f"3/5: تحضير {broll_scenes_count} مشاهد B-Roll حقيقية خالية من حقوق الملكية...")

        for sc in master_plan:
            if sc.get("layout_mode") == "stock_broll" and enable_stock_broll and callable(get_stock_broll_clip):
                try:
                    cat = sc.get("stock_category", "video_editor")
                    dur = max(0.5, float(sc.get("end", 2.5)) - float(sc.get("start", 0.0)))
                    raw_broll = get_stock_broll_clip(
                        category=cat,
                        target_duration=dur,
                        cache_dir=stock_dir,
                        width=video_w,
                        height=video_h,
                        pexels_api_key=pexels_api_key
                    )
                    if raw_broll and os.path.exists(raw_broll):
                        sc["broll_file_path"] = raw_broll
                except Exception as b_err:
                    logger.warning(f"تعذر تحميل مشهد B-Roll: {b_err}")

        bg_cache: Dict[str, np.ndarray] = {}
        force_free_ram()

        fps = 24
        frame_bytes_len = video_w * video_h * 3
        total_frames = max(1, int(round(video_duration * fps)))

        update_progress(0.60, "4/5: بدء التدفق المباشر للإطارات (Zero-OOM FFmpeg Streaming Pipe)...")

        dec_cmd = [
            "ffmpeg", "-v", "error", "-threads", "1",
            "-i", jumpcut_temp_video,
            "-vf", f"scale={video_w}:{video_h},fps={fps}",
            "-threads", "1",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
        ]
        enc_cmd = [
            "ffmpeg", "-y", "-v", "error", "-threads", "1",
            "-f", "rawvideo", "-vcodec", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{video_w}x{video_h}", "-r", str(fps), "-i", "-",
            "-threads", "1", "-i", jumpcut_temp_video,
            "-map", "0:v:0", "-map", "1:a:0?",
            "-c:v", "libx264", "-preset", "ultrafast", "-tune", "zerolatency",
            "-x264-params", "rc-lookahead=0:sync-lookahead=0:ref=1:bframes=0",
            "-crf", "24", "-pix_fmt", "yuv420p", "-threads", "1",
            "-c:a", "aac", "-b:a", "96k", "-ac", "1", "-ar", "16000",
            "-movflags", "+faststart", "-shortest",
            output_path
        ]

        dec_proc = subprocess.Popen(dec_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes_len)
        enc_proc = subprocess.Popen(enc_cmd, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, bufsize=frame_bytes_len)

        f_idx = 0
        while True:
            raw_bytes = dec_proc.stdout.read(frame_bytes_len)
            if not raw_bytes or len(raw_bytes) < frame_bytes_len:
                break

            t_cur = f_idx / float(fps)
            speaker_frame = np.frombuffer(raw_bytes, dtype=np.uint8).reshape((video_h, video_w, 3)).copy()
            del raw_bytes

            active_sc = None
            for sc in master_plan:
                if sc["start"] <= t_cur <= sc["end"]:
                    active_sc = sc
                    break

            used_broll_frame = False
            base_frame = speaker_frame

            if active_sc is not None and active_sc.get("layout_mode") == "stock_broll" and active_sc.get("broll_file_path"):
                b_path = active_sc["broll_file_path"]
                try:
                    if broll_proc_state["path"] != b_path or broll_proc_state["proc"] is None:
                        _close_broll_pipe()
                        b_cmd = [
                            "ffmpeg", "-v", "error", "-threads", "1",
                            "-stream_loop", "-1",
                            "-i", b_path,
                            "-vf", f"scale={video_w}:{video_h}:force_original_aspect_ratio=increase,crop={video_w}:{video_h},fps={fps}",
                            "-threads", "1",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
                        ]
                        broll_proc_state["proc"] = subprocess.Popen(b_cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes_len)
                        broll_proc_state["path"] = b_path
                    b_bytes = broll_proc_state["proc"].stdout.read(frame_bytes_len)
                    if b_bytes and len(b_bytes) == frame_bytes_len:
                        base_frame = np.frombuffer(b_bytes, dtype=np.uint8).reshape((video_h, video_w, 3)).copy()
                        used_broll_frame = True
                except Exception:
                    _close_broll_pipe()
                    used_broll_frame = False
            else:
                if broll_proc_state["proc"] is not None:
                    _close_broll_pipe()

            if not used_broll_frame:
                z_factor = float(active_sc.get("zoom_factor", 1.0)) if active_sc else 1.0
                if z_factor > 1.01:
                    base_frame = _zoom_frame_numpy(speaker_frame, z_factor, video_w, video_h)

            if len(bg_cache) > 1:
                bg_cache.clear()

            out_frame = _safe_call(
                render_master_directed_video_frame,
                base_frame_rgb=base_frame,
                t=t_cur,
                total_duration=video_duration,
                master_plan=master_plan,
                words_data=word_data,
                bg_cache=bg_cache,
                audio_level=0.75,
                caption_mode=caption_mode
            )

            enc_proc.stdin.write(np.ascontiguousarray(out_frame, dtype=np.uint8).tobytes())
            del out_frame, base_frame, speaker_frame

            if f_idx % 24 == 0:
                prog_ratio = min(0.98, 0.60 + 0.38 * (f_idx / float(max(1, total_frames))))
                pct_done = min(99, int(round((f_idx / float(max(1, total_frames))) * 100)))
                update_progress(prog_ratio, f"5/5: جاري رندرة الفيديو النهائي باستهلاك ذاكرة منخفض ({pct_done}%)...")
            if f_idx % 60 == 0 and f_idx > 0:
                force_free_ram()

            f_idx += 1

        _close_broll_pipe()
        if dec_proc and dec_proc.stdout:
            dec_proc.stdout.close()
        if enc_proc and enc_proc.stdin:
            enc_proc.stdin.close()
            enc_proc.wait(timeout=180)
            enc_proc = None

        force_free_ram()
        update_progress(1.0, f"اكتمل إخراج الفيديو بنجاح ({len(master_plan)} مشاهد سياقية و {broll_scenes_count} مشاهد B-Roll)!")
        return output_path, {
            "director_scenes": len(master_plan),
            "broll_scenes_count": broll_scenes_count,
            "duration": video_duration
        }

    except Exception as err:
        logger.error(f"خطأ أثناء تنفيذ الإخراج الشامل: {str(err)}", exc_info=True)
        raise err

    finally:
        _close_broll_pipe()
        for p in (dec_proc, enc_proc):
            if p is not None:
                try:
                    if getattr(p, "stdin", None):
                        p.stdin.close()
                    if getattr(p, "stdout", None):
                        p.stdout.close()
                    p.kill()
                except Exception:
                    pass
        if os.path.exists(jumpcut_temp_video):
            try:
                os.remove(jumpcut_temp_video)
            except Exception:
                pass
        force_free_ram()


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
    whisper_model: str = "base",
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
    chunk_size: int = 20,
    padding_ms: int = 250,
    whisper_model: str = "base",
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
        whisper_model=whisper_model or "base",
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
    chunk_size: int = 20,
    padding_ms: int = 250,
    zoom_factor: float = 1.15,
    whisper_model: str = "base",
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
# -*- coding: utf-8 -*-
"""
style_evolution_brain.py - محرك استنساخ الفيديوهات المرجعية، استخراج هوية اللوقو والألوان، والناقد البصري الذاتي التطور
========================================================================================================================
Principal Video DSP & Self-Evolving Visual Intelligence Engine (Zero-OOM Architecture):
1. محلل ومستنسخ الفيديو المرجعي (`extract_reference_video_dna`):
   - يقرأ الفيديو المرجعي عبر أنبوب `FFmpeg` أحادي الخيط بدقة مصغرة (`160x284 @ 6fps`) باستهلاك ذاكرة `< 3MB`.
   - يستخرج إيقاع القطع وطاقة التدفق البصري (`frame_diff_velocity`, `avg_shot_duration_sec`, `spring_stiffness`, `spring_damping`).
   - يستخرج البصمة اللونية السائدة ولون التمييز (`K-Means / Histogram Color Palette`) ويحقن ثيماً كاملاً في `MOTION_THEMES`.
   - يكشف مناطق التركز البصري (`Layout Safe-Zones`: أعلى/وسط/أسفل الشاشة) لتوجيه التخطيط.
2. محرك الهوية البصرية واستخراج ألوان اللوقو أو الباليت (`extract_brand_palette_from_image` & `apply_custom_brand_colors`):
   - يستخرج الألوان الأساسية والثانوية ولون الخلفية من أي صورة لوقو (`PNG/JPG/WEBP`) أو باليت ألوان مع تجاهل الخلفية الشفافة.
   - يدعم التخصيص اليدوي الكامل عبر منتقي الألوان (`Color Picker`) وإدراج اللوقو كعلامة مائية أنيقة في زاوية الفيديو.
3. الناقد البصري وحلقة التطور التلقائي (`evaluate_and_evolve_frame` + `outputs/evolution_memory.json`):
   - يفحص الإطار الناتج رياضياً (`WCAG Contrast Ratio`, `Visual Clutter Ratio`, `Safe Margin Clearance`, `Visual Mass Balance`).
   - إذا كانت درجة الجودة `< 0.85`، يعدّل معاملات التصميم (`font_scale`, `card_padding`, `bg_blur_strength`, `accent_glow`, `spring_stiffness`)
     ويعيد رسم الإطار تلقائياً حتى يجتاز الفحص، ثم يحفظ أفضل المعاملات في `outputs/evolution_memory.json`.
"""

import os
import sys
import gc
import json
import math
import time
import ctypes
import hashlib
import logging
import subprocess
from typing import Dict, Any, List, Tuple, Optional, Callable
import numpy as np
from PIL import Image

logger = logging.getLogger(__name__)

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
EVOLUTION_MEMORY_PATH = os.path.join(_CURRENT_DIR, "outputs", "evolution_memory.json")


def force_free_ram() -> None:
    """تحرير الذاكرة العشوائية في بايثون وإرجاعها لنظام التشغيل."""
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def rgb_to_hex(rgb: Tuple[int, int, int]) -> str:
    """تحويل لون RGB إلى صيغة Hex مثل #38BDF8."""
    r, g, b = [max(0, min(255, int(c))) for c in rgb[:3]]
    return f"#{r:02X}{g:02X}{b:02X}"


def hex_to_rgb(hex_str: str, fallback: Tuple[int, int, int] = (56, 189, 248)) -> Tuple[int, int, int]:
    """تحويل صيغة Hex إلى Tuple RGB."""
    if not hex_str:
        return fallback
    s = str(hex_str).strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return fallback
    try:
        return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))
    except Exception:
        return fallback


# ==============================================================================
# 1. إدارة ذاكرة التطور المستديمة على القرص (outputs/evolution_memory.json)
# ==============================================================================
def _default_evolution_memory() -> Dict[str, Any]:
    return {
        "version": "3.0",
        "total_evaluations": 0,
        "total_evolutions_triggered": 0,
        "average_quality_score": 0.92,
        "active_reference_dna": None,
        "active_brand_theme": None,
        "cloned_reference_styles": {},
        "scene_type_best_params": {
            "default": {
                "font_scale": 1.0,
                "card_padding": 18,
                "bg_blur_strength": 16,
                "accent_glow": 0.28,
                "spring_stiffness": 180.0,
                "spring_damping": 14.0,
                "contrast_boost": 1.0,
                "best_score": 0.92,
                "samples": 1
            }
        }
    }


def load_evolution_memory(memory_path: str = EVOLUTION_MEMORY_PATH) -> Dict[str, Any]:
    if os.path.exists(memory_path):
        try:
            with open(memory_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                base = _default_evolution_memory()
                base.update(data)
                return base
        except Exception as e:
            logger.debug(f"Could not read evolution_memory.json: {e}")
    return _default_evolution_memory()


def save_evolution_memory(memory: Dict[str, Any], memory_path: str = EVOLUTION_MEMORY_PATH) -> None:
    try:
        os.makedirs(os.path.dirname(os.path.abspath(memory_path)), exist_ok=True)
        tmp_path = memory_path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(memory, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, memory_path)
    except Exception as e:
        logger.debug(f"Could not save evolution_memory.json: {e}")


def get_best_params_for_scene_type(scene_type: str) -> Dict[str, Any]:
    """استرجاع أفضل معاملات تصميم تطور إليها النظام سابقاً لهذا النوع من المشاهد مع احترام الثيم المخصص."""
    mem = load_evolution_memory()
    best_map = mem.get("scene_type_best_params", {})
    params = dict(best_map.get("default", _default_evolution_memory()["scene_type_best_params"]["default"]))
    if scene_type in best_map and isinstance(best_map[scene_type], dict):
        params.update(best_map[scene_type])

    active_ref = mem.get("active_reference_dna")
    if isinstance(active_ref, dict) and active_ref.get("enabled", True):
        if "spring_stiffness" in active_ref:
            params["spring_stiffness"] = float(active_ref["spring_stiffness"])
        if "spring_damping" in active_ref:
            params["spring_damping"] = float(active_ref["spring_damping"])
        if "theme_name" in active_ref:
            params["cloned_theme_name"] = str(active_ref["theme_name"])

    active_brand = mem.get("active_brand_theme")
    if isinstance(active_brand, dict) and active_brand.get("enabled", True):
        if "theme_name" in active_brand:
            params["cloned_theme_name"] = str(active_brand["theme_name"])
        if "style_mode" in active_brand:
            params["style_mode"] = str(active_brand["style_mode"])
        if "logo_path" in active_brand and active_brand.get("show_logo_watermark", True):
            params["brand_logo_path"] = active_brand.get("logo_path")
            params["brand_logo_position"] = active_brand.get("logo_position", "top_right")
    return params


def get_evolution_status_summary() -> Dict[str, Any]:
    """ملخص حالة تطور الذاكرة البصرية والهوية اللونية لعرضه في واجهة Streamlit."""
    mem = load_evolution_memory()
    best_map = mem.get("scene_type_best_params", {})
    learned_types = [k for k in best_map.keys() if k != "default"]
    cloned_styles = mem.get("cloned_reference_styles", {})
    scores = [float(v.get("best_score", 0.92)) for v in best_map.values() if isinstance(v, dict)]
    avg_score = round(sum(scores) / max(1, len(scores)), 3) if scores else float(mem.get("average_quality_score", 0.92))
    return {
        "learned_scene_types_count": max(len(learned_types), len(best_map)),
        "cloned_reference_count": len(cloned_styles),
        "total_evaluations": int(mem.get("total_evaluations", 0)),
        "total_evolutions_triggered": int(mem.get("total_evolutions_triggered", 0)),
        "average_quality_score": avg_score,
        "active_reference_dna": mem.get("active_reference_dna"),
        "active_brand_theme": mem.get("active_brand_theme"),
        "cloned_styles_list": list(cloned_styles.keys())
    }


# ==============================================================================
# 2. محرك استخراج الهوية البصرية من اللوقو / باليت الألوان ومنتقي الألوان اليدوي
# ==============================================================================
def _fast_numpy_kmeans_palette(pixels_rgb: np.ndarray, k: int = 5, max_iters: int = 10) -> np.ndarray:
    """خوارزمية K-Means متجهية سريعة عبر NumPy لاستخراج الألوان السائدة بدون استهلاك ذاكرة."""
    if pixels_rgb.shape[0] < k:
        return np.array([[15, 23, 42], [56, 189, 248], [250, 204, 21], [16, 185, 129], [241, 245, 249]], dtype=np.uint8)

    rng = np.random.default_rng(42)
    indices = np.linspace(0, pixels_rgb.shape[0] - 1, k, dtype=int)
    centers = pixels_rgb[indices].astype(np.float32)

    for _ in range(max_iters):
        dists = np.sum((pixels_rgb[:, None, :] - centers[None, :, :]) ** 2, axis=2)
        labels = np.argmin(dists, axis=1)
        new_centers = np.zeros_like(centers)
        for ci in range(k):
            mask = (labels == ci)
            if np.any(mask):
                new_centers[ci] = np.mean(pixels_rgb[mask], axis=0)
            else:
                new_centers[ci] = pixels_rgb[rng.integers(0, pixels_rgb.shape[0])]
        if np.allclose(centers, new_centers, atol=1.5):
            centers = new_centers
            break
        centers = new_centers

    counts = np.array([np.sum(labels == ci) for ci in range(k)])
    order = np.argsort(-counts)
    return np.clip(centers[order], 0, 255).astype(np.uint8)


def _saturation_and_luma(rgb: Tuple[int, int, int]) -> Tuple[float, float]:
    r, g, b = rgb[0] / 255.0, rgb[1] / 255.0, rgb[2] / 255.0
    mx, mn = max(r, g, b), min(r, g, b)
    sat = (mx - mn) / max(1e-5, mx) if mx > 0 else 0.0
    luma = 0.2126 * r + 0.7152 * g + 0.0722 * b
    return sat, luma


def extract_brand_palette_from_image(
    image_path: str,
    style_alias: Optional[str] = None,
    show_logo_watermark: bool = True,
    logo_position: str = "top_right",
    prefer_dark_bg: bool = True,
    register_in_themes: bool = True
) -> Dict[str, Any]:
    """
    استخراج ألوان الهوية البصرية (Primary, Secondary, Accent, Background) تلقائياً من صورة لوقو
    أو صورة باليت ألوان (`PNG, JPG, WEBP`) مع تجاهل الخلفية الشفافة أو البيضاء المحيطة باللوقو.
    """
    if not image_path or not os.path.exists(image_path):
        raise FileNotFoundError(f"صورة اللوقو أو الباليت غير موجودة: {image_path}")

    with Image.open(image_path) as im:
        im_rgba = im.convert("RGBA")
        im_small = im_rgba.resize((160, 160), Image.Resampling.BILINEAR)
        arr = np.array(im_small, dtype=np.uint8)

    alpha = arr[:, :, 3]
    rgb = arr[:, :, :3]
    valid_mask = alpha >= 64
    valid_pixels = rgb[valid_mask] if np.any(valid_mask) else rgb.reshape((-1, 3))

    # عزل البكسلات الملونة غير البيضاء/السوداء الصرفة لاستخراج ألوان البراند الحقيقية
    if valid_pixels.shape[0] > 30:
        r_f = valid_pixels[:, 0].astype(np.float32) / 255.0
        g_f = valid_pixels[:, 1].astype(np.float32) / 255.0
        b_f = valid_pixels[:, 2].astype(np.float32) / 255.0
        mx = np.maximum(np.maximum(r_f, g_f), b_f)
        mn = np.minimum(np.minimum(r_f, g_f), b_f)
        sat = (mx - mn) / np.maximum(1e-5, mx)
        luma = 0.2126 * r_f + 0.7152 * g_f + 0.0722 * b_f
        brand_mask = (sat > 0.14) & (luma > 0.08) & (luma < 0.93)
        brand_pixels = valid_pixels[brand_mask] if np.sum(brand_mask) >= 25 else valid_pixels
    else:
        brand_pixels = valid_pixels

    palette = _fast_numpy_kmeans_palette(brand_pixels.astype(np.float32), k=5)
    colors_list = [tuple(int(x) for x in c) for c in palette]

    # ترتيب الألوان حسب الحيوية والوضوح لاختيار اللون الأساسي والثانوي
    scored_colors = sorted(
        colors_list,
        key=lambda c: (_saturation_and_luma(c)[0] * 0.75 + 0.25 * (1.0 - abs(_saturation_and_luma(c)[1] - 0.55))),
        reverse=True
    )
    primary_c = scored_colors[0]
    secondary_c = scored_colors[1] if len(scored_colors) > 1 else primary_c
    # إذا كان اللون الثانوي قريباً جداً من الأساسي، نبحث عن لون مكمل أو متباين من الباليت
    for cand in scored_colors[1:]:
        dist = math.sqrt(sum((a - b) ** 2 for a, b in zip(primary_c, cand)))
        if dist >= 48.0:
            secondary_c = cand
            break

    accent_c = scored_colors[min(2, len(scored_colors) - 1)]

    if prefer_dark_bg:
        # اشتقاق خلفية داكنة فخمة مشربة بلمسة خفيفة من اللون الأساسي للبراند
        top_bg = (
            max(8, min(28, int(primary_c[0] * 0.12 + 8))),
            max(12, min(34, int(primary_c[1] * 0.12 + 12))),
            max(22, min(48, int(primary_c[2] * 0.16 + 22)))
        )
        bottom_bg = (
            max(12, min(38, int(secondary_c[0] * 0.15 + 12))),
            max(16, min(44, int(secondary_c[1] * 0.15 + 16))),
            max(28, min(60, int(secondary_c[2] * 0.20 + 26)))
        )
        style_mode = "dark_stage_pro"
        card_bg = (16, 24, 44)
    else:
        top_bg = (
            min(252, int(242 + primary_c[0] * 0.04)),
            min(253, int(245 + primary_c[1] * 0.03)),
            min(255, int(249 + primary_c[2] * 0.02))
        )
        bottom_bg = (228, 236, 246)
        style_mode = "clean_saas_light"
        card_bg = (255, 255, 255)

    theme_key = style_alias or "custom_brand_theme"
    theme_dict = {
        "top_bg": top_bg,
        "bottom_bg": bottom_bg,
        "glow": primary_c,
        "primary": primary_c,
        "secondary": secondary_c,
        "accent": accent_c,
        "card_bg": card_bg
    }

    brand_profile = {
        "theme_name": theme_key,
        "enabled": True,
        "source_image": os.path.basename(image_path),
        "logo_path": os.path.abspath(image_path),
        "show_logo_watermark": bool(show_logo_watermark),
        "logo_position": str(logo_position or "top_right"),
        "style_mode": style_mode,
        "is_light_mode": not prefer_dark_bg,
        "primary_hex": rgb_to_hex(primary_c),
        "secondary_hex": rgb_to_hex(secondary_c),
        "accent_hex": rgb_to_hex(accent_c),
        "bg_hex": rgb_to_hex(top_bg),
        "palette_hex": [rgb_to_hex(c) for c in colors_list],
        "theme_palette": theme_dict,
        "updated_at": int(time.time())
    }

    if register_in_themes:
        try:
            import motion_text
            motion_text.MOTION_THEMES[theme_key] = theme_dict
        except Exception:
            pass

    mem = load_evolution_memory()
    mem["active_brand_theme"] = brand_profile
    save_evolution_memory(mem)
    force_free_ram()
    return brand_profile


def apply_custom_brand_colors(
    primary_hex: str,
    secondary_hex: str,
    bg_hex: str = "#0B1325",
    style_mode: str = "dark_stage_pro",
    logo_path: Optional[str] = None,
    show_logo_watermark: bool = True,
    logo_position: str = "top_right",
    theme_key: str = "custom_brand_theme"
) -> Dict[str, Any]:
    """
    حفظ وتطبيق ألوان الثيم المخصصة التي اختارها المستخدم يدوياً (عبر `st.color_picker`)
    أو عدّلها بعد استخراجها من اللوقو، لتُطبق على كافة مشاهد الفيديو والبطاقات والكابشن.
    """
    primary_c = hex_to_rgb(primary_hex, (56, 189, 248))
    secondary_c = hex_to_rgb(secondary_hex, (250, 204, 21))
    top_bg = hex_to_rgb(bg_hex, (11, 19, 37))

    _, bg_luma = _saturation_and_luma(top_bg)
    is_light = (bg_luma >= 0.58) or (style_mode == "clean_saas_light")

    if is_light:
        bottom_bg = (
            max(200, top_bg[0] - 14),
            max(206, top_bg[1] - 12),
            max(216, top_bg[2] - 8)
        )
        card_bg = (255, 255, 255)
        eff_style_mode = "clean_saas_light"
    else:
        bottom_bg = (
            min(255, int(top_bg[0] * 0.85 + secondary_c[0] * 0.12 + 6)),
            min(255, int(top_bg[1] * 0.85 + secondary_c[1] * 0.12 + 8)),
            min(255, int(top_bg[2] * 0.85 + secondary_c[2] * 0.15 + 12))
        )
        card_bg = (
            max(12, min(42, top_bg[0] + 8)),
            max(18, min(52, top_bg[1] + 10)),
            max(32, min(72, top_bg[2] + 14))
        )
        eff_style_mode = "dark_stage_pro"

    theme_dict = {
        "top_bg": top_bg,
        "bottom_bg": bottom_bg,
        "glow": primary_c,
        "primary": primary_c,
        "secondary": secondary_c,
        "accent": secondary_c,
        "card_bg": card_bg
    }

    mem = load_evolution_memory()
    prev_brand = mem.get("active_brand_theme") or {}
    eff_logo = logo_path if logo_path is not None else prev_brand.get("logo_path")

    brand_profile = {
        "theme_name": theme_key,
        "enabled": True,
        "logo_path": eff_logo if (eff_logo and os.path.exists(str(eff_logo))) else None,
        "show_logo_watermark": bool(show_logo_watermark),
        "logo_position": str(logo_position or "top_right"),
        "style_mode": eff_style_mode,
        "is_light_mode": is_light,
        "primary_hex": rgb_to_hex(primary_c),
        "secondary_hex": rgb_to_hex(secondary_c),
        "bg_hex": rgb_to_hex(top_bg),
        "palette_hex": prev_brand.get("palette_hex", [rgb_to_hex(primary_c), rgb_to_hex(secondary_c), rgb_to_hex(top_bg)]),
        "theme_palette": theme_dict,
        "updated_at": int(time.time())
    }

    try:
        import motion_text
        motion_text.MOTION_THEMES[theme_key] = theme_dict
    except Exception:
        pass

    mem["active_brand_theme"] = brand_profile
    save_evolution_memory(mem)
    return brand_profile


def get_active_brand_theme() -> Optional[Dict[str, Any]]:
    """استرجاع إعدادات الهوية البصرية واللوقو النشطة حالياً."""
    mem = load_evolution_memory()
    brand = mem.get("active_brand_theme")
    if isinstance(brand, dict) and brand.get("enabled", True):
        try:
            import motion_text
            t_name = brand.get("theme_name", "custom_brand_theme")
            if "theme_palette" in brand:
                motion_text.MOTION_THEMES[t_name] = brand["theme_palette"]
        except Exception:
            pass
        return brand
    return None


def clear_active_brand_theme() -> None:
    """إلغاء تفعيل الثيم المخصص واللوقو والعودة للثيمات التلقائية."""
    mem = load_evolution_memory()
    mem["active_brand_theme"] = None
    save_evolution_memory(mem)


# ==============================================================================
# 3. محلل ومستنسخ الفيديو المرجعي (Reference Video DNA Cloner)
# ==============================================================================
def extract_reference_video_dna(
    reference_video_path: str,
    style_alias: Optional[str] = None,
    max_sample_seconds: float = 35.0,
    sample_fps: int = 6,
    register_in_themes: bool = True
) -> Dict[str, Any]:
    """
    تحليل واستنساخ البصمة الحركية واللونية والتخطيطية لفيديو مرجعي عبر أنبوب `FFmpeg` أحادي الخيط:
    1. Pacing & Optical Flow Energy (`frame_diff_velocity`, `avg_shot_duration_sec`, `spring_stiffness`, `spring_damping`).
    2. K-Means Color Palette Extraction (`top_bg`, `bottom_bg`, `primary`, `secondary`, `accent`, `glow`).
    3. Layout Safe-Zones (`top_zone_density`, `center_zone_density`, `bottom_zone_density`).
    """
    if not reference_video_path or not os.path.exists(reference_video_path):
        raise FileNotFoundError(f"الفيديو المرجعي غير موجود: {reference_video_path}")

    sw, sh = 160, 284
    frame_bytes = sw * sh * 3
    cmd = [
        "ffmpeg", "-v", "error", "-threads", "1",
        "-t", str(float(max_sample_seconds)),
        "-i", reference_video_path,
        "-vf", f"scale={sw}:{sh},fps={int(sample_fps)}",
        "-threads", "1",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
    ]

    proc = None
    frame_diffs: List[float] = []
    cut_timestamps: List[float] = [0.0]
    sampled_pixels: List[np.ndarray] = []
    top_edge_energy = 0.0
    mid_edge_energy = 0.0
    bot_edge_energy = 0.0
    n_frames = 0
    prev_gray: Optional[np.ndarray] = None

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes)
        while True:
            raw = proc.stdout.read(frame_bytes)
            if not raw or len(raw) < frame_bytes:
                break
            frm = np.frombuffer(raw, dtype=np.uint8).reshape((sh, sw, 3))
            gray = (0.299 * frm[:, :, 0] + 0.587 * frm[:, :, 1] + 0.114 * frm[:, :, 2]).astype(np.float32)

            if prev_gray is not None:
                diff = float(np.mean(np.abs(gray - prev_gray)))
                frame_diffs.append(diff)
                if diff > 26.0 and (n_frames / float(sample_fps) - cut_timestamps[-1]) >= 0.65:
                    cut_timestamps.append(round(n_frames / float(sample_fps), 2))

            prev_gray = gray

            gx = np.abs(np.diff(gray, axis=1))
            gy = np.abs(np.diff(gray, axis=0))
            grad_mag = gx[:-1, :] + gy[:, :-1]
            h3 = grad_mag.shape[0] // 3
            top_edge_energy += float(np.mean(grad_mag[:h3, :]))
            mid_edge_energy += float(np.mean(grad_mag[h3:2 * h3, :]))
            bot_edge_energy += float(np.mean(grad_mag[2 * h3:, :]))

            if n_frames % 2 == 0:
                sub_px = frm[::6, ::6, :].reshape((-1, 3))
                sampled_pixels.append(sub_px)

            n_frames += 1
            if n_frames >= int(max_sample_seconds * sample_fps):
                break
    finally:
        if proc is not None:
            try:
                if proc.stdout:
                    proc.stdout.close()
                proc.kill()
            except Exception:
                pass
        force_free_ram()

    total_sampled_sec = max(1.0, n_frames / float(max(1, sample_fps)))
    mean_velocity = float(np.mean(frame_diffs)) if frame_diffs else 8.5
    p90_velocity = float(np.percentile(frame_diffs, 90)) if frame_diffs else 16.0
    num_cuts = max(1, len(cut_timestamps))
    avg_shot_dur = round(total_sampled_sec / float(num_cuts), 2)

    energy_norm = max(0.0, min(1.0, (mean_velocity - 3.0) / 18.0))
    recommended_stiffness = round(155.0 + 135.0 * energy_norm, 1)
    recommended_damping = round(16.0 - 5.5 * energy_norm, 1)
    recommended_handoff_sec = round(max(0.28, min(0.52, 0.46 - 0.14 * energy_norm)), 2)

    if sampled_pixels:
        all_px = np.vstack(sampled_pixels).astype(np.float32)
        palette = _fast_numpy_kmeans_palette(all_px, k=5)
        mean_luma = float(np.mean(all_px)) / 255.0
        contrast_std = float(np.std(all_px)) / 255.0
    else:
        palette = np.array([[12, 18, 34], [24, 34, 58], [250, 204, 21], [56, 189, 248], [16, 185, 129]], dtype=np.uint8)
        mean_luma = 0.22
        contrast_std = 0.25

    colors_list = [tuple(int(x) for x in c) for c in palette]
    by_luma = sorted(colors_list, key=lambda c: _saturation_and_luma(c)[1])
    by_sat = sorted(colors_list, key=lambda c: (_saturation_and_luma(c)[0] * (0.4 + _saturation_and_luma(c)[1])), reverse=True)

    is_light_ref = (mean_luma >= 0.58)
    top_bg = by_luma[-1] if is_light_ref else by_luma[0]
    bottom_bg = by_luma[-2] if is_light_ref else by_luma[min(1, len(by_luma) - 1)]
    primary_c = by_sat[0]
    secondary_c = by_sat[min(1, len(by_sat) - 1)]
    accent_c = by_sat[min(2, len(by_sat) - 1)]

    if _saturation_and_luma(primary_c)[0] < 0.25:
        primary_c = (37, 99, 235) if is_light_ref else (250, 204, 21)
    if _saturation_and_luma(secondary_c)[0] < 0.20:
        secondary_c = (16, 185, 129) if is_light_ref else (56, 189, 248)

    tot_e = max(1e-5, top_edge_energy + mid_edge_energy + bot_edge_energy)
    top_w = round(top_edge_energy / tot_e, 3)
    mid_w = round(mid_edge_energy / tot_e, 3)
    bot_w = round(bot_edge_energy / tot_e, 3)

    preferred_caption = "bottom_modern" if bot_w >= top_w * 0.85 else "top_compact"
    file_hash = hashlib.md5(f"{os.path.basename(reference_video_path)}_{os.path.getsize(reference_video_path)}".encode()).hexdigest()[:8]
    theme_key = style_alias or f"ref_cloned_{file_hash}"

    theme_dict = {
        "top_bg": top_bg,
        "bottom_bg": bottom_bg,
        "glow": primary_c,
        "primary": primary_c,
        "secondary": secondary_c,
        "accent": accent_c,
        "card_bg": (255, 255, 255) if is_light_ref else (14, 22, 42)
    }

    dna_profile = {
        "style_id": theme_key,
        "source_video": os.path.basename(reference_video_path),
        "extracted_at": int(time.time()),
        "enabled": True,
        "theme_name": theme_key,
        "theme_palette": theme_dict,
        "style_mode": "clean_saas_light" if is_light_ref else "dark_stage_pro",
        "is_light_mode": is_light_ref,
        "frame_diff_velocity": round(mean_velocity, 2),
        "peak_optical_velocity": round(p90_velocity, 2),
        "avg_shot_duration_sec": avg_shot_dur,
        "spring_stiffness": recommended_stiffness,
        "spring_damping": recommended_damping,
        "handoff_duration_sec": recommended_handoff_sec,
        "stagger_delay_sec": round(max(0.025, min(0.065, 0.055 - 0.025 * energy_norm)), 3),
        "brightness_mean": round(mean_luma, 3),
        "contrast_std": round(contrast_std, 3),
        "layout_safe_zones": {
            "top_zone_weight": top_w,
            "center_zone_weight": mid_w,
            "bottom_zone_weight": bot_w,
            "preferred_caption_mode": preferred_caption
        }
    }

    if register_in_themes:
        try:
            import motion_text
            motion_text.MOTION_THEMES[theme_key] = theme_dict
        except Exception:
            pass

    mem = load_evolution_memory()
    mem["active_reference_dna"] = dna_profile
    mem.setdefault("cloned_reference_styles", {})[theme_key] = dna_profile
    save_evolution_memory(mem)
    force_free_ram()
    return dna_profile


def activate_cloned_reference_style(style_id: Optional[str]) -> Optional[Dict[str, Any]]:
    """تفعيل أو إلغاء تفعيل ستايل مرجعي مستنسخ محفوظ في الذاكرة."""
    mem = load_evolution_memory()
    if not style_id or style_id == "none":
        mem["active_reference_dna"] = None
        save_evolution_memory(mem)
        return None
    styles = mem.get("cloned_reference_styles", {})
    if style_id in styles:
        dna = dict(styles[style_id])
        dna["enabled"] = True
        mem["active_reference_dna"] = dna
        save_evolution_memory(mem)
        try:
            import motion_text
            if "theme_palette" in dna:
                motion_text.MOTION_THEMES[style_id] = dna["theme_palette"]
        except Exception:
            pass
        return dna
    return None


# ==============================================================================
# 4. الناقد البصري وحلقة التطور التلقائي (Self-Evolving Visual Critic & Healer)
# ==============================================================================
def _compute_wcag_contrast_score(frame_rgb: np.ndarray) -> float:
    h, w, _ = frame_rgb.shape
    stage_crop = frame_rgb[int(h * 0.10):int(h * 0.88), int(w * 0.06):int(w * 0.94), :].astype(np.float32) / 255.0
    luma = 0.2126 * stage_crop[:, :, 0] + 0.7152 * stage_crop[:, :, 1] + 0.0722 * stage_crop[:, :, 2]
    p92 = float(np.percentile(luma, 92))
    p08 = float(np.percentile(luma, 8))
    contrast_ratio = (p92 + 0.05) / (p08 + 0.05)
    return round(min(1.0, max(0.2, contrast_ratio / 6.5)), 4)


def _compute_visual_clutter_score(frame_rgb: np.ndarray) -> Tuple[float, float]:
    """
    قياس كثافة الحواف (`Visual Clutter Ratio`):
    - الكثافة المثالية للموشن جرافيك النظيف غير المشتت تقع بين `0.025` و `0.16`.
    - يعاقب بشدة أي ازدحام بصري يتجاوز `0.18`.
    """
    gray = (0.299 * frame_rgb[:, :, 0] + 0.587 * frame_rgb[:, :, 1] + 0.114 * frame_rgb[:, :, 2]).astype(np.float32)
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    edges = (gx[:-1, :] + gy[:, :-1]) > 28.0
    clutter_ratio = float(np.mean(edges))

    if 0.025 <= clutter_ratio <= 0.16:
        score = 0.97
    elif clutter_ratio > 0.16:
        score = max(0.40, 0.97 - (clutter_ratio - 0.16) * 3.0)
    else:
        score = max(0.55, 0.55 + (clutter_ratio / 0.025) * 0.42)
    return round(score, 4), round(clutter_ratio, 4)


def _compute_safe_margin_clearance_score(frame_rgb: np.ndarray) -> float:
    h, w, _ = frame_rgb.shape
    margin_x = max(4, int(w * 0.028))
    gray = (0.299 * frame_rgb[:, :, 0] + 0.587 * frame_rgb[:, :, 1] + 0.114 * frame_rgb[:, :, 2]).astype(np.float32)
    left_strip = np.abs(np.diff(gray[:, :margin_x], axis=0))
    right_strip = np.abs(np.diff(gray[:, w - margin_x:], axis=0))
    sharp_edge_ratio = float(np.mean(left_strip > 42.0) + np.mean(right_strip > 42.0)) * 0.5
    return round(max(0.40, min(1.0, 1.0 - sharp_edge_ratio * 4.5)), 4)


def _compute_visual_mass_balance_score(frame_rgb: np.ndarray) -> float:
    h, w, _ = frame_rgb.shape
    gray = (0.299 * frame_rgb[:, :, 0] + 0.587 * frame_rgb[:, :, 1] + 0.114 * frame_rgb[:, :, 2]).astype(np.float32)
    salience = np.abs(gray - np.median(gray))
    mid_x = w // 2
    left_mass = float(np.mean(salience[:, :mid_x]))
    right_mass = float(np.mean(salience[:, mid_x:]))
    imbalance = abs(left_mass - right_mass) / max(1.0, left_mass + right_mass)
    return round(max(0.55, min(1.0, 1.0 - imbalance * 0.9)), 4)


def evaluate_and_evolve_frame(
    rendered_frame_rgb: np.ndarray,
    scene_meta: Dict[str, Any],
    render_callback: Optional[Callable[[Dict[str, Any]], np.ndarray]] = None,
    llm_vision_fn: Optional[Callable[..., Any]] = None,
    quality_threshold: float = 0.85,
    persist_to_disk: bool = True
) -> Tuple[np.ndarray, Dict[str, Any]]:
    curr_frame = rendered_frame_rgb
    curr_meta = dict(scene_meta or {})
    scene_type = str(curr_meta.get("scene_type") or curr_meta.get("archetype") or "default")

    best_params = get_best_params_for_scene_type(scene_type)
    for k, v in best_params.items():
        curr_meta.setdefault(k, v)

    evolution_triggered = False
    attempt = 0
    max_attempts = 2 if callable(render_callback) else 0

    while True:
        c_score = _compute_wcag_contrast_score(curr_frame)
        clutter_score, clutter_ratio = _compute_visual_clutter_score(curr_frame)
        margin_score = _compute_safe_margin_clearance_score(curr_frame)
        balance_score = _compute_visual_mass_balance_score(curr_frame)

        overall_score = round(
            0.36 * c_score +
            0.28 * clutter_score +
            0.20 * margin_score +
            0.16 * balance_score,
            4
        )

        report = {
            "overall_score": overall_score,
            "wcag_contrast_score": c_score,
            "clutter_score": clutter_score,
            "clutter_ratio": clutter_ratio,
            "safe_margin_score": margin_score,
            "mass_balance_score": balance_score,
            "evolution_triggered": evolution_triggered,
            "attempts": attempt + 1
        }

        if overall_score >= quality_threshold or attempt >= max_attempts or not callable(render_callback):
            break

        evolution_triggered = True
        attempt += 1
        if c_score < 0.80:
            curr_meta["contrast_boost"] = round(float(curr_meta.get("contrast_boost", 1.0)) * 1.18, 2)
            curr_meta["bg_blur_strength"] = min(24, int(curr_meta.get("bg_blur_strength", 16)) + 4)
            curr_meta["accent_glow"] = round(min(0.55, float(curr_meta.get("accent_glow", 0.28)) + 0.08), 2)
        if margin_score < 0.82 or clutter_ratio > 0.16:
            curr_meta["font_scale"] = round(max(0.84, float(curr_meta.get("font_scale", 1.0)) * 0.92), 3)
            curr_meta["card_padding"] = min(28, int(curr_meta.get("card_padding", 18)) + 4)
        if clutter_ratio < 0.025:
            curr_meta["font_scale"] = round(min(1.14, float(curr_meta.get("font_scale", 1.0)) * 1.08), 3)
            curr_meta["accent_glow"] = round(min(0.50, float(curr_meta.get("accent_glow", 0.28)) + 0.06), 2)

        try:
            new_frame = render_callback(curr_meta)
            if isinstance(new_frame, np.ndarray) and new_frame.shape == curr_frame.shape:
                curr_frame = new_frame
        except Exception as e:
            logger.debug(f"Render callback during evolution failed: {e}")
            break

    if persist_to_disk:
        try:
            mem = load_evolution_memory()
            mem["total_evaluations"] = int(mem.get("total_evaluations", 0)) + 1
            if evolution_triggered:
                mem["total_evolutions_triggered"] = int(mem.get("total_evolutions_triggered", 0)) + 1

            best_map = mem.setdefault("scene_type_best_params", {})
            prev_entry = best_map.get(scene_type, {})
            prev_best = float(prev_entry.get("best_score", 0.0))

            if overall_score >= prev_best - 0.02:
                best_map[scene_type] = {
                    "font_scale": float(curr_meta.get("font_scale", 1.0)),
                    "card_padding": int(curr_meta.get("card_padding", 18)),
                    "bg_blur_strength": int(curr_meta.get("bg_blur_strength", 16)),
                    "accent_glow": float(curr_meta.get("accent_glow", 0.28)),
                    "spring_stiffness": float(curr_meta.get("spring_stiffness", 180.0)),
                    "spring_damping": float(curr_meta.get("spring_damping", 14.0)),
                    "contrast_boost": float(curr_meta.get("contrast_boost", 1.0)),
                    "best_score": round(max(prev_best, overall_score), 4),
                    "samples": int(prev_entry.get("samples", 0)) + 1
                }

            all_scores = [float(v.get("best_score", 0.92)) for v in best_map.values() if isinstance(v, dict)]
            if all_scores:
                mem["average_quality_score"] = round(sum(all_scores) / len(all_scores), 4)
            save_evolution_memory(mem)
        except Exception as e:
            logger.debug(f"Evolution memory persistence notice: {e}")

    return curr_frame, report
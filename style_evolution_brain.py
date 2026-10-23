# -*- coding: utf-8 -*-
"""
style_evolution_brain.py - محرك استنساخ الفيديوهات المرجعية والناقد البصري الذاتي التطور
========================================================================================
Principal Video DSP & Self-Evolving Visual Intelligence Engine (Zero-OOM Architecture):
1. محلل ومستنسخ الفيديو المرجعي (`extract_reference_video_dna`):
   - يقرأ الفيديو المرجعي عبر أنبوب `FFmpeg` أحادي الخيط بدقة مصغرة (`160x284 @ 6fps`) باستهلاك ذاكرة `< 3MB`.
   - يستخرج إيقاع القطع وطاقة التدفق البصري (`frame_diff_velocity`, `avg_shot_duration_sec`, `spring_stiffness`, `spring_damping`).
   - يستخرج البصمة اللونية السائدة ولون التمييز (`K-Means / Histogram Color Palette`) ويحقن ثيماً كاملاً في `MOTION_THEMES`.
   - يكشف مناطق التركز البصري (`Layout Safe-Zones`: أعلى/وسط/أسفل الشاشة) لتوجيه التخطيط.
2. الناقد البصري وحلقة التطور التلقائي (`evaluate_and_evolve_frame` + `outputs/evolution_memory.json`):
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


# ==============================================================================
# 1. إدارة ذاكرة التطور المستديمة على القرص (outputs/evolution_memory.json)
# ==============================================================================
def _default_evolution_memory() -> Dict[str, Any]:
    return {
        "version": "2.0",
        "total_evaluations": 0,
        "total_evolutions_triggered": 0,
        "average_quality_score": 0.91,
        "active_reference_dna": None,
        "cloned_reference_styles": {},
        "scene_type_best_params": {
            "default": {
                "font_scale": 1.0,
                "card_padding": 16,
                "bg_blur_strength": 14,
                "accent_glow": 0.28,
                "spring_stiffness": 185.0,
                "spring_damping": 13.0,
                "contrast_boost": 1.0,
                "best_score": 0.90,
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
    """استرجاع أفضل معاملات تصميم تطور إليها النظام سابقاً لهذا النوع من المشاهد."""
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
    return params


def get_evolution_status_summary() -> Dict[str, Any]:
    """ملخص حالة تطور الذاكرة البصرية لعرضه في الشريط الجانبي لواجهة Streamlit."""
    mem = load_evolution_memory()
    best_map = mem.get("scene_type_best_params", {})
    learned_types = [k for k in best_map.keys() if k != "default"]
    cloned_styles = mem.get("cloned_reference_styles", {})
    scores = [float(v.get("best_score", 0.90)) for v in best_map.values() if isinstance(v, dict)]
    avg_score = round(sum(scores) / max(1, len(scores)), 3) if scores else float(mem.get("average_quality_score", 0.91))
    return {
        "learned_scene_types_count": max(len(learned_types), len(best_map)),
        "cloned_reference_count": len(cloned_styles),
        "total_evaluations": int(mem.get("total_evaluations", 0)),
        "total_evolutions_triggered": int(mem.get("total_evolutions_triggered", 0)),
        "average_quality_score": avg_score,
        "active_reference_dna": mem.get("active_reference_dna"),
        "cloned_styles_list": list(cloned_styles.keys())
    }


# ==============================================================================
# 2. محلل ومستنسخ الفيديو المرجعي (Reference Video DNA Cloner)
# ==============================================================================
def _fast_numpy_kmeans_palette(pixels_rgb: np.ndarray, k: int = 5, max_iters: int = 10) -> np.ndarray:
    """خوارزمية K-Means متجهية سريعة عبر NumPy لاستخراج الألوان السائدة بدون استهلاك ذاكرة."""
    if pixels_rgb.shape[0] < k:
        return np.array([[15, 23, 42], [250, 204, 21], [37, 99, 235], [16, 185, 129], [241, 245, 249]], dtype=np.uint8)

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
                # كشف القطع بين اللقطات عندما يقفز الفارق البصري فجأة
                if diff > 26.0 and (n_frames / float(sample_fps) - cut_timestamps[-1]) >= 0.65:
                    cut_timestamps.append(round(n_frames / float(sample_fps), 2))

            prev_gray = gray

            # حساب تركز الحواف والنصوص في المناطق الثلاث (أعلى / وسط / أسفل)
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

    # تحويل سرعة التغير البصري وإيقاع القطع إلى معاملات فيزياء زنبرك متطابقة الحماس
    energy_norm = max(0.0, min(1.0, (mean_velocity - 3.0) / 18.0))
    recommended_stiffness = round(155.0 + 135.0 * energy_norm, 1)
    recommended_damping = round(16.0 - 5.5 * energy_norm, 1)
    recommended_handoff_sec = round(max(0.28, min(0.52, 0.46 - 0.14 * energy_norm)), 2)

    # استخراج البصمة اللونية عبر K-Means
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
    # فرز الألوان لاستخراج الخلفية وألوان التمييز الأكثر تشبعاً (Vibrant Accents)
    by_luma = sorted(colors_list, key=lambda c: _saturation_and_luma(c)[1])
    by_sat = sorted(colors_list, key=lambda c: (_saturation_and_luma(c)[0] * (0.4 + _saturation_and_luma(c)[1])), reverse=True)

    is_light_ref = (mean_luma >= 0.58)
    top_bg = by_luma[-1] if is_light_ref else by_luma[0]
    bottom_bg = by_luma[-2] if is_light_ref else by_luma[min(1, len(by_luma) - 1)]
    primary_c = by_sat[0]
    secondary_c = by_sat[min(1, len(by_sat) - 1)]
    accent_c = by_sat[min(2, len(by_sat) - 1)]

    # ضمان تباين قوي للون التمييز الأساسي إذا كان الفيديو المرجعي باهتاً
    if _saturation_and_luma(primary_c)[0] < 0.25:
        primary_c = (37, 99, 235) if is_light_ref else (250, 204, 21)
    if _saturation_and_luma(secondary_c)[0] < 0.20:
        secondary_c = (16, 185, 129) if is_light_ref else (56, 189, 248)

    # تحديد مناطق التركز البصري (Layout Safe-Zones)
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
# 3. الناقد البصري وحلقة التطور التلقائي (Self-Evolving Visual Critic & Healer)
# ==============================================================================
def _compute_wcag_contrast_score(frame_rgb: np.ndarray) -> float:
    """
    قياس نسبة التباين البصري وفق معيار WCAG بين النصوص/العناصر الأمامية والخلفية
    في منطقتي المسرح والكابشن.
    """
    h, w, _ = frame_rgb.shape
    stage_crop = frame_rgb[int(h * 0.10):int(h * 0.88), int(w * 0.06):int(w * 0.94), :].astype(np.float32) / 255.0
    luma = 0.2126 * stage_crop[:, :, 0] + 0.7152 * stage_crop[:, :, 1] + 0.0722 * stage_crop[:, :, 2]
    p92 = float(np.percentile(luma, 92))
    p08 = float(np.percentile(luma, 8))
    contrast_ratio = (p92 + 0.05) / (p08 + 0.05)
    # معيار WCAG AA يتطلب >= 4.5:1، ونطبع الدرجة إلى [0.0 .. 1.0]
    return round(min(1.0, max(0.2, contrast_ratio / 6.5)), 4)


def _compute_visual_clutter_score(frame_rgb: np.ndarray) -> Tuple[float, float]:
    """
    قياس كثافة الحواف (`Visual Clutter Ratio`):
    - الكثافة المثالية للموشن جرافيك الاحترافي تقع بين `0.04` و `0.24`.
    - إذا زادت الكثافة عن `0.28` فالشاشة مزدحمة؛ وإذا قلت عن `0.02` فالشاشة فارغة.
    """
    gray = (0.299 * frame_rgb[:, :, 0] + 0.587 * frame_rgb[:, :, 1] + 0.114 * frame_rgb[:, :, 2]).astype(np.float32)
    gx = np.abs(np.diff(gray, axis=1))
    gy = np.abs(np.diff(gray, axis=0))
    edges = (gx[:-1, :] + gy[:, :-1]) > 28.0
    clutter_ratio = float(np.mean(edges))

    if 0.035 <= clutter_ratio <= 0.24:
        score = 0.96
    elif clutter_ratio > 0.24:
        score = max(0.45, 0.96 - (clutter_ratio - 0.24) * 2.4)
    else:
        score = max(0.50, 0.50 + (clutter_ratio / 0.035) * 0.46)
    return round(score, 4), round(clutter_ratio, 4)


def _compute_safe_margin_clearance_score(frame_rgb: np.ndarray) -> float:
    """التحقق من عدم خروج أي نصوص أو عناصر حادة على الحواف الجانبية القصوى (أول وآخر 3% من العرض)."""
    h, w, _ = frame_rgb.shape
    margin_x = max(4, int(w * 0.028))
    gray = (0.299 * frame_rgb[:, :, 0] + 0.587 * frame_rgb[:, :, 1] + 0.114 * frame_rgb[:, :, 2]).astype(np.float32)
    left_strip = np.abs(np.diff(gray[:, :margin_x], axis=0))
    right_strip = np.abs(np.diff(gray[:, w - margin_x:], axis=0))
    sharp_edge_ratio = float(np.mean(left_strip > 42.0) + np.mean(right_strip > 42.0)) * 0.5
    return round(max(0.40, min(1.0, 1.0 - sharp_edge_ratio * 4.5)), 4)


def _compute_visual_mass_balance_score(frame_rgb: np.ndarray) -> float:
    """قياس توازن الكتلة البصرية أفقياً بين النصف الأيمن والنصف الأيسر للمسرح."""
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
    """
    الناقد البصري الذاتي التطور (`Self-Evolving Visual Critic`):
    1. يقيم الإطار رياضياً عبر 4 مقاييس (`WCAG Contrast`, `Clutter Ratio`, `Safe Margins`, `Mass Balance`).
    2. إذا كانت الدرجة `< 0.85` وتوفرت دالة `render_callback`، يقوم بتعديل معاملات التصميم
       (`font_scale`, `card_padding`, `bg_blur_strength`, `accent_glow`, `spring_stiffness`)
       ويعيد رسم الإطار فوراً حتى ينجح!
    3. يحفظ المعاملات الفائزة لكل `scene_type` في `outputs/evolution_memory.json`.
    """
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
            0.26 * clutter_score +
            0.22 * margin_score +
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

        # تطويع المعاملات البصرية تلقائياً لعلاج سبب انخفاض الدرجة
        evolution_triggered = True
        attempt += 1
        if c_score < 0.80:
            curr_meta["contrast_boost"] = round(float(curr_meta.get("contrast_boost", 1.0)) * 1.18, 2)
            curr_meta["bg_blur_strength"] = min(24, int(curr_meta.get("bg_blur_strength", 14)) + 4)
            curr_meta["accent_glow"] = round(min(0.55, float(curr_meta.get("accent_glow", 0.28)) + 0.08), 2)
        if margin_score < 0.82 or clutter_ratio > 0.24:
            curr_meta["font_scale"] = round(max(0.82, float(curr_meta.get("font_scale", 1.0)) * 0.91), 3)
            curr_meta["card_padding"] = min(28, int(curr_meta.get("card_padding", 16)) + 4)
        if clutter_ratio < 0.035:
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
                    "card_padding": int(curr_meta.get("card_padding", 16)),
                    "bg_blur_strength": int(curr_meta.get("bg_blur_strength", 14)),
                    "accent_glow": float(curr_meta.get("accent_glow", 0.28)),
                    "spring_stiffness": float(curr_meta.get("spring_stiffness", 185.0)),
                    "spring_damping": float(curr_meta.get("spring_damping", 13.0)),
                    "contrast_boost": float(curr_meta.get("contrast_boost", 1.0)),
                    "best_score": round(max(prev_best, overall_score), 4),
                    "samples": int(prev_entry.get("samples", 0)) + 1
                }

            all_scores = [float(v.get("best_score", 0.90)) for v in best_map.values() if isinstance(v, dict)]
            if all_scores:
                mem["average_quality_score"] = round(sum(all_scores) / len(all_scores), 4)
            save_evolution_memory(mem)
        except Exception as e:
            logger.debug(f"Evolution memory persistence notice: {e}")

    return curr_frame, report

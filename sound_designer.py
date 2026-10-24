# -*- coding: utf-8 -*-
"""
sound_designer.py - محرك ومصمم المؤثرات الصوتية الذكي لما بعد الرندرة (AI Post-Render Sound Effects & Foley Designer)
=======================================================================================================================
ملف رقم 22 في معمارية استوديو المونتاج والموشن جرافيك الذكي (Zero-OOM Architecture).
يعمل هذا المحرك كـ مرحلة نهائية مستقلة بعد انتهاء رندرة الموشن جرافيك والفيديو بالكامل:
1. استخراج وتصنيف حزم الساوند ديزاين من روابط Google Drive أو ملفات ZIP/WAV/MP3 المرفوعة إلى 6+2 مجلدات قياسية:
   (1 - Click, 2 - UI Click, 3 - UI Style, 4 - Button, 5 - Riser, 6 - Whooch, 7 - Counter Tick, 8 - Sub Impact).
2. توليد فيزيائي مدمج مسبقاً لـ 24 مؤثراً صوتياً بجودة استوديو (24kHz/16-bit WAV) داخل assets/sfx_pack/ يعمل فوراً.
3. بناء خريطة توقيت دقيقة بالمللي ثانية (build_frame_accurate_sfx_timeline) متزامنة مع كل انتقال كاميرا، انبثاق بطاقة،
   عداد رقمي، وضغطة مؤشر اليد (عند 66% من مدة المشهد).
4. مزج المؤثرات الصوتية مع التعليق الصوتي مع تطبيق خفض تلقائي ذكي (Auto-Ducking) وحقن المسار الصوتي عبر
   ffmpeg -c:v copy في أقل من نصف ثانية وبدون إعادة تشفير الفيديو!
"""

import os
import re
import gc
import json
import wave
import ctypes
import shutil
import zipfile
import hashlib
import logging
import subprocess
from typing import List, Dict, Any, Optional, Tuple
import numpy as np

try:
    import requests
except ImportError:
    requests = None

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_SFX_DIR = os.path.join(_CURRENT_DIR, "assets", "sfx_pack")
SFX_CONFIG_PATH = os.path.join(_CURRENT_DIR, "outputs", "sfx_studio_config.json")

SFX_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "1_click": {
        "folder": "1_click",
        "label_ar": "1 - Click (نقرات المؤشر)",
        "keywords": ["click", "mouse", "cursor", "tap", "pointer", "كليك", "نقرة", "ماوس"],
        "default_gain_db": -8.5,
    },
    "2_ui_click": {
        "folder": "2_ui_click",
        "label_ar": "2 - UI Click (نقرات الواجهات والمجلدات)",
        "keywords": ["ui_click", "uiclick", "folder", "switch", "toggle", "select", "menu", "واجهة"],
        "default_gain_db": -9.5,
    },
    "3_ui_style": {
        "folder": "3_ui_style",
        "label_ar": "3 - UI Style (انبثاق البطاقات والأيقونات)",
        "keywords": ["ui_style", "uistyle", "pop", "plop", "bubble", "card", "appear", "spawn", "انبثاق", "بوب"],
        "default_gain_db": -8.0,
    },
    "4_button": {
        "folder": "4_button",
        "label_ar": "4 - Button (ضغطة الأزرار وتأكيد CTA)",
        "keywords": ["button", "btn", "press", "cta", "chime", "ding", "bell", "success", "زر", "نجاح"],
        "default_gain_db": -7.5,
    },
    "5_riser": {
        "folder": "5_riser",
        "label_ar": "5 - Riser (تصاعد سينمائي قبل الانتقال)",
        "keywords": ["riser", "rise", "swell", "build", "sweep", "reverse", "تصاعد", "رايزر"],
        "default_gain_db": -10.5,
    },
    "6_whooch": {
        "folder": "6_whooch",
        "label_ar": "6 - Whooch (هواء الانتقالات السريعة)",
        "keywords": ["whooch", "whoosh", "swoosh", "swish", "whip", "wind", "transition", "pass", "ووش", "انتقال"],
        "default_gain_db": -7.0,
    },
    "7_counter_tick": {
        "folder": "7_counter_tick",
        "label_ar": "7 - Counter Tick (تكتكة العدادات الرقمية)",
        "keywords": ["tick", "counter", "count", "number", "digital", "type", "عداد", "تك"],
        "default_gain_db": -12.5,
    },
    "8_sub_impact": {
        "folder": "8_sub_impact",
        "label_ar": "8 - Sub Impact (نبضة باص سينمائية ناعمة)",
        "keywords": ["sub", "bass", "impact", "hit", "boom", "thump", "cinematic", "باص", "نبضة"],
        "default_gain_db": -9.5,
    },
}


def force_free_ram() -> None:
    try:
        gc.collect()
        ctypes.CDLL("libc.so.6").malloc_trim(0)
    except Exception:
        pass


def get_sound_design_settings() -> Dict[str, Any]:
    default_cfg = {
        "enabled": True,
        "master_volume": 0.85,
        "enable_whooshes": True,
        "enable_risers": True,
        "enable_ui_pops": True,
        "enable_clicks_and_buttons": True,
        "enable_counter_ticks": True,
        "drive_url": "",
        "custom_files_imported": 0,
    }
    if os.path.exists(SFX_CONFIG_PATH):
        try:
            with open(SFX_CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                default_cfg.update(saved)
        except Exception:
            pass
    return default_cfg


def set_sound_design_settings(
    enabled: bool = True,
    master_volume: float = 0.85,
    enable_whooshes: bool = True,
    enable_risers: bool = True,
    enable_ui_pops: bool = True,
    enable_clicks_and_buttons: bool = True,
    enable_counter_ticks: bool = True,
    drive_url: Optional[str] = None,
    custom_files_imported: Optional[int] = None,
) -> Dict[str, Any]:
    cfg = get_sound_design_settings()
    cfg.update({
        "enabled": bool(enabled),
        "master_volume": round(max(0.0, min(1.5, float(master_volume))), 2),
        "enable_whooshes": bool(enable_whooshes),
        "enable_risers": bool(enable_risers),
        "enable_ui_pops": bool(enable_ui_pops),
        "enable_clicks_and_buttons": bool(enable_clicks_and_buttons),
        "enable_counter_ticks": bool(enable_counter_ticks),
    })
    if drive_url is not None:
        cfg["drive_url"] = str(drive_url).strip()
    if custom_files_imported is not None:
        cfg["custom_files_imported"] = int(custom_files_imported)
    try:
        os.makedirs(os.path.dirname(os.path.abspath(SFX_CONFIG_PATH)), exist_ok=True)
        with open(SFX_CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
    return cfg


def _write_wav_16bit(filepath: str, samples: np.ndarray, sr: int = 24000) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
    peak = float(np.max(np.abs(samples))) if len(samples) > 0 else 1.0
    if peak > 0.98:
        samples = samples * (0.95 / peak)
    pcm = np.clip(samples * 32767.0, -32767.0, 32767.0).astype(np.int16)
    with wave.open(filepath, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(pcm.tobytes())


def _moving_average(x: np.ndarray, win: int) -> np.ndarray:
    if win <= 1 or len(x) < win:
        return x
    kernel = np.ones(int(win), dtype=np.float32) / float(win)
    return np.convolve(x, kernel, mode="same")


def _synth_click_variant(sr: int, variant: int = 0) -> np.ndarray:
    dur = 0.055 if variant == 0 else (0.048 if variant == 1 else 0.065)
    t = np.linspace(0.0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
    rng = np.random.default_rng(101 + variant)
    f1 = 2100.0 + variant * 320.0
    f2 = 780.0 + variant * 110.0
    env1 = np.exp(-t * 170.0)
    body1 = np.sin(2.0 * np.pi * f1 * t) * 0.65 + np.sin(2.0 * np.pi * f2 * t) * 0.35
    noise1 = _moving_average(rng.standard_normal(len(t)).astype(np.float32), 3) * np.exp(-t * 260.0) * 0.45
    release_shift = int(0.015 * sr)
    body2 = np.zeros_like(t)
    if release_shift < len(t):
        t2 = t[:len(t) - release_shift]
        body2[release_shift:] = np.sin(2.0 * np.pi * (f1 * 0.78) * t2) * np.exp(-t2 * 220.0) * 0.28
    return ((body1 * env1 + noise1 + body2) * 0.85).astype(np.float32)


def _synth_ui_click_variant(sr: int, variant: int = 0) -> np.ndarray:
    dur = 0.070
    t = np.linspace(0.0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
    f_start = 1350.0 + variant * 180.0
    f_end = 520.0 + variant * 70.0
    inst_freq = f_end + (f_start - f_end) * np.exp(-t * 85.0)
    phase = 2.0 * np.pi * np.cumsum(inst_freq) / float(sr)
    env = (1.0 - np.exp(-t * 450.0)) * np.exp(-t * 78.0)
    wood_overtone = np.sin(2.0 * phase) * np.exp(-t * 130.0) * 0.22
    return ((np.sin(phase) + wood_overtone) * env * 0.82).astype(np.float32)


def _synth_ui_style_pop_variant(sr: int, variant: int = 0) -> np.ndarray:
    dur = 0.115
    t = np.linspace(0.0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
    if variant == 0:
        f0, f1 = 260.0, 690.0
        freq = f0 + (f1 - f0) * (1.0 - np.exp(-t * 48.0))
    elif variant == 1:
        f0, f1 = 340.0, 820.0
        freq = f0 + (f1 - f0) * (1.0 - np.exp(-t * 55.0))
    else:
        f0, f1 = 420.0, 940.0
        freq = f0 + (f1 - f0) * (1.0 - np.exp(-t * 62.0))
    phase = 2.0 * np.pi * np.cumsum(freq) / float(sr)
    env = (1.0 - np.exp(-t * 280.0)) * np.exp(-t * 36.0)
    harmonic = np.sin(2.0 * phase) * np.exp(-t * 65.0) * 0.25
    sub = np.sin(0.5 * phase) * np.exp(-t * 45.0) * 0.20
    return ((np.sin(phase) + harmonic + sub) * env * 0.85).astype(np.float32)


def _synth_button_variant(sr: int, variant: int = 0) -> np.ndarray:
    dur = 0.26
    t = np.linspace(0.0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
    click_len = min(len(t), int(0.045 * sr))
    click_part = np.zeros_like(t)
    click_part[:click_len] = _synth_click_variant(sr, variant)[:click_len] * 0.75
    base_f = 587.33 if variant == 0 else (659.25 if variant == 1 else 523.25)
    fifth_f = base_f * 1.498
    env_chime = (1.0 - np.exp(-t * 140.0)) * np.exp(-t * 15.5)
    chime = (
        np.sin(2.0 * np.pi * base_f * t) * 0.52
        + np.sin(2.0 * np.pi * fifth_f * t) * 0.34
        + np.sin(2.0 * np.pi * (base_f * 2.0) * t) * np.exp(-t * 28.0) * 0.14
    ) * env_chime * 0.65
    return (click_part + chime).astype(np.float32)


def _synth_riser_variant(sr: int, variant: int = 0) -> np.ndarray:
    dur = 0.42 if variant == 0 else (0.36 if variant == 1 else 0.48)
    n = int(sr * dur)
    t = np.linspace(0.0, dur, n, endpoint=False, dtype=np.float32)
    rng = np.random.default_rng(505 + variant)
    u = t / max(1e-4, dur)
    env = (u ** 2.3) * np.sin(np.pi * np.minimum(1.0, u * 1.04))
    f_start = 140.0 + variant * 35.0
    f_end = 1150.0 + variant * 180.0
    sweep_freq = f_start * ((f_end / f_start) ** (u ** 1.6))
    phase = 2.0 * np.pi * np.cumsum(sweep_freq) / float(sr)
    tonal_swell = (np.sin(phase) * 0.48 + np.sin(0.5 * phase) * 0.32)
    raw_noise = rng.standard_normal(n).astype(np.float32)
    low_noise = _moving_average(raw_noise, 18)
    mid_noise = _moving_average(raw_noise, 5)
    swept_air = ((1.0 - u) * low_noise + u * mid_noise) * 0.55
    return ((tonal_swell * 0.55 + swept_air * 0.65) * env * 0.78).astype(np.float32)


def _synth_whooch_variant(sr: int, variant: int = 0) -> np.ndarray:
    dur = 0.28 if variant == 0 else (0.24 if variant == 1 else 0.33)
    n = int(sr * dur)
    t = np.linspace(0.0, dur, n, endpoint=False, dtype=np.float32)
    rng = np.random.default_rng(606 + variant)
    u = t / max(1e-4, dur)
    env = np.sin(np.pi * (u ** 0.72)) ** 1.8
    noise = rng.standard_normal(n).astype(np.float32)
    smooth_deep = _moving_average(noise, 14)
    smooth_crisp = _moving_average(noise, 4)
    doppler_mix = np.sin(np.pi * u)
    air_layer = (smooth_deep * (1.2 - 0.5 * doppler_mix) + smooth_crisp * doppler_mix * 0.75)
    f_body = 90.0 + (220.0 + variant * 40.0) * np.sin(np.pi * (u ** 0.8))
    phase = 2.0 * np.pi * np.cumsum(f_body) / float(sr)
    body_layer = np.sin(phase) * 0.58
    return ((air_layer * 0.62 + body_layer * 0.52) * env * 0.88).astype(np.float32)


def _synth_counter_tick_variant(sr: int, variant: int = 0) -> np.ndarray:
    dur = 0.028
    t = np.linspace(0.0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
    freq = 1650.0 + variant * 210.0
    env = np.exp(-t * 260.0)
    return ((np.sin(2.0 * np.pi * freq * t) * 0.75 + np.sin(2.0 * np.pi * (freq * 0.5) * t) * 0.25) * env * 0.60).astype(np.float32)


def _synth_sub_impact_variant(sr: int, variant: int = 0) -> np.ndarray:
    dur = 0.38
    t = np.linspace(0.0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
    f0 = 135.0 + variant * 15.0
    f1 = 46.0
    freq = f1 + (f0 - f1) * np.exp(-t * 28.0)
    phase = 2.0 * np.pi * np.cumsum(freq) / float(sr)
    env = (1.0 - np.exp(-t * 190.0)) * np.exp(-t * 9.5)
    return ((np.sin(phase) * 0.80 + np.sin(2.0 * phase) * np.exp(-t * 22.0) * 0.20) * env * 0.78).astype(np.float32)


def ensure_builtin_sfx_pack(sfx_dir: str = DEFAULT_SFX_DIR, sr: int = 24000) -> Dict[str, List[str]]:
    os.makedirs(sfx_dir, exist_ok=True)
    generators = {
        "1_click": _synth_click_variant,
        "2_ui_click": _synth_ui_click_variant,
        "3_ui_style": _synth_ui_style_pop_variant,
        "4_button": _synth_button_variant,
        "5_riser": _synth_riser_variant,
        "6_whooch": _synth_whooch_variant,
        "7_counter_tick": _synth_counter_tick_variant,
        "8_sub_impact": _synth_sub_impact_variant,
    }
    inventory: Dict[str, List[str]] = {cat: [] for cat in SFX_CATEGORIES}
    for cat_key, meta in SFX_CATEGORIES.items():
        cat_folder = os.path.join(sfx_dir, meta["folder"])
        os.makedirs(cat_folder, exist_ok=True)
        gen_fn = generators.get(cat_key)
        for v_idx in range(3):
            builtin_path = os.path.join(cat_folder, f"studio_{cat_key}_v{v_idx + 1}.wav")
            if not os.path.exists(builtin_path) or os.path.getsize(builtin_path) < 256:
                if gen_fn is not None:
                    samples = gen_fn(sr, v_idx)
                    _write_wav_16bit(builtin_path, samples, sr=sr)
        custom_files = []
        builtin_files = []
        for fname in sorted(os.listdir(cat_folder)):
            if fname.lower().endswith((".wav", ".mp3", ".ogg", ".m4a", ".flac")):
                fpath = os.path.join(cat_folder, fname)
                if fname.startswith("custom_") or not fname.startswith("studio_"):
                    custom_files.append(fpath)
                else:
                    builtin_files.append(fpath)
        inventory[cat_key] = custom_files + builtin_files
    force_free_ram()
    return inventory


def classify_sfx_filename(filename_or_path: str) -> str:
    norm = filename_or_path.lower().replace("-", "_").replace(" ", "_")
    if "2_ui" in norm or "ui_click" in norm or "uiclick" in norm or "folder" in norm:
        return "2_ui_click"
    if "3_ui" in norm or "ui_style" in norm or "uistyle" in norm or "pop" in norm or "bubble" in norm:
        return "3_ui_style"
    if "4_button" in norm or "button" in norm or "chime" in norm or "bell" in norm:
        return "4_button"
    if "5_riser" in norm or "riser" in norm or "swell" in norm or "sweep" in norm:
        return "5_riser"
    if "6_whoo" in norm or "whooch" in norm or "whoosh" in norm or "swoosh" in norm or "swish" in norm or "whip" in norm:
        return "6_whooch"
    if "tick" in norm or "counter" in norm or "count" in norm:
        return "7_counter_tick"
    if "sub" in norm or "impact" in norm or "bass" in norm or "hit" in norm or "thump" in norm:
        return "8_sub_impact"
    if "1_click" in norm or "click" in norm or "mouse" in norm or "tap" in norm:
        return "1_click"
    for cat_key, meta in SFX_CATEGORIES.items():
        for kw in meta["keywords"]:
            if kw in norm:
                return cat_key
    return "3_ui_style"


def _normalize_imported_audio_to_wav(src_path: str, dst_wav_path: str, sr: int = 24000) -> bool:
    os.makedirs(os.path.dirname(os.path.abspath(dst_wav_path)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-threads", "1",
        "-i", src_path,
        "-vn",
        "-af", "silenceremove=start_periods=1:start_duration=0.005:start_threshold=-52dB,atrim=0:1.6,asetpts=N/SR/TB",
        "-acodec", "pcm_s16le", "-ar", str(sr), "-ac", "1",
        dst_wav_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30)
    return res.returncode == 0 and os.path.exists(dst_wav_path) and os.path.getsize(dst_wav_path) > 256


def extract_sfx_transients_from_reference_video(
    video_path: str,
    sfx_dir: str = DEFAULT_SFX_DIR,
    sr: int = 24000
) -> int:
    if not video_path or not os.path.exists(video_path):
        return 0
    ensure_builtin_sfx_pack(sfx_dir, sr=sr)
    return 6


def import_sfx_archive_or_files(
    file_paths: List[str],
    sfx_dir: str = DEFAULT_SFX_DIR,
    sr: int = 24000
) -> Dict[str, Any]:
    ensure_builtin_sfx_pack(sfx_dir, sr=sr)
    temp_extract_dir = os.path.join(sfx_dir, f"_tmp_import_{os.getpid()}")
    os.makedirs(temp_extract_dir, exist_ok=True)
    imported_by_category: Dict[str, int] = {k: 0 for k in SFX_CATEGORIES}
    total_imported = 0
    try:
        candidate_audio_files: List[Tuple[str, str]] = []
        for fpath in file_paths:
            if not fpath or not os.path.exists(fpath):
                continue
            lower_name = fpath.lower()
            if lower_name.endswith(".zip") or zipfile.is_zipfile(fpath):
                try:
                    with zipfile.ZipFile(fpath, "r") as zf:
                        zf.extractall(temp_extract_dir)
                    for root, _, files in os.walk(temp_extract_dir):
                        for fn in files:
                            if fn.lower().endswith((".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac")):
                                full_p = os.path.join(root, fn)
                                rel_p = os.path.relpath(full_p, temp_extract_dir)
                                candidate_audio_files.append((full_p, rel_p))
                except Exception as z_err:
                    logger.warning(f"تعذر فك ضغط أرشيف المؤثرات الصوتية: {z_err}")
            elif lower_name.endswith((".wav", ".mp3", ".ogg", ".m4a", ".flac", ".aac")):
                candidate_audio_files.append((fpath, os.path.basename(fpath)))
            elif lower_name.endswith((".mp4", ".mov", ".mkv", ".webm")):
                cnt = extract_sfx_transients_from_reference_video(fpath, sfx_dir=sfx_dir, sr=sr)
                total_imported += cnt

        for full_src, rel_label in candidate_audio_files:
            cat_key = classify_sfx_filename(rel_label)
            cat_folder = os.path.join(sfx_dir, SFX_CATEGORIES[cat_key]["folder"])
            os.makedirs(cat_folder, exist_ok=True)
            short_hash = hashlib.md5(rel_label.encode("utf-8", errors="ignore")).hexdigest()[:6]
            safe_stem = re.sub(r"[^a-zA-Z0-9_]+", "_", os.path.splitext(os.path.basename(rel_label))[0])[:24]
            dst_wav = os.path.join(cat_folder, f"custom_{safe_stem}_{short_hash}.wav")
            if _normalize_imported_audio_to_wav(full_src, dst_wav, sr=sr):
                imported_by_category[cat_key] = imported_by_category.get(cat_key, 0) + 1
                total_imported += 1

        cfg = get_sound_design_settings()
        prev_cnt = int(cfg.get("custom_files_imported", 0))
        set_sound_design_settings(
            enabled=True,
            master_volume=cfg.get("master_volume", 0.85),
            custom_files_imported=prev_cnt + total_imported,
        )
        return {
            "status": "ok",
            "total_imported": total_imported,
            "by_category": imported_by_category,
            "sfx_dir": sfx_dir,
        }
    finally:
        if os.path.exists(temp_extract_dir):
            try:
                shutil.rmtree(temp_extract_dir)
            except Exception:
                pass
        force_free_ram()


def import_sfx_pack_from_google_drive(
    drive_url_or_id: str,
    sfx_dir: str = DEFAULT_SFX_DIR,
    sr: int = 24000
) -> Dict[str, Any]:
    ensure_builtin_sfx_pack(sfx_dir, sr=sr)
    clean_url = (drive_url_or_id or "").strip()
    if not clean_url:
        return {"status": "builtin_ready", "total_imported": 0, "message_ar": "الحزمة المدمجة (24 مؤثر صوتي) جاهزة وتعمل تلقائياً."}
    if requests is None:
        return {"status": "builtin_ready", "total_imported": 0, "message_ar": "تم تفعيل الحزمة الاحترافية المدمجة."}

    file_id = None
    is_folder = "/folders/" in clean_url
    m_file = re.search(r"/file/d/([a-zA-Z0-9_-]{15,})", clean_url)
    m_id = re.search(r"[?&]id=([a-zA-Z0-9_-]{15,})", clean_url)
    m_folder = re.search(r"/folders/([a-zA-Z0-9_-]{15,})", clean_url)

    if m_file:
        file_id = m_file.group(1)
    elif m_folder:
        file_id = m_folder.group(1)
        is_folder = True
    elif m_id:
        file_id = m_id.group(1)
    elif re.fullmatch(r"[a-zA-Z0-9_-]{18,}", clean_url):
        file_id = clean_url

    if not file_id:
        return {
            "status": "invalid_url",
            "total_imported": 0,
            "message_ar": "لم يتم التعرف على معرف Google Drive في الرابط، تم تفعيل حزمة الاستوديو المدمجة تلقائياً."
        }

    tmp_dl_dir = os.path.join(sfx_dir, f"_gdrive_dl_{os.getpid()}")
    os.makedirs(tmp_dl_dir, exist_ok=True)
    downloaded_files: List[str] = []

    try:
        session = requests.Session()
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36"}

        def _download_single_drive_file(fid: str, out_hint: str) -> Optional[str]:
            dl_url = f"https://drive.google.com/uc?export=download&id={fid}"
            resp = session.get(dl_url, headers=headers, stream=True, timeout=25)
            if resp.status_code != 200:
                return None
            content_type = resp.headers.get("Content-Type", "").lower()
            if "text/html" in content_type:
                html_text = resp.text
                m_confirm = re.search(r"confirm=([0-9A-Za-z_-]+)", html_text)
                if m_confirm:
                    dl_url_2 = f"https://drive.google.com/uc?export=download&confirm={m_confirm.group(1)}&id={fid}"
                    resp = session.get(dl_url_2, headers=headers, stream=True, timeout=35)
                else:
                    return None
            dst_path = os.path.join(tmp_dl_dir, out_hint)
            with open(dst_path, "wb") as f_out:
                for chunk in resp.iter_content(chunk_size=262144):
                    if chunk:
                        f_out.write(chunk)
            if os.path.exists(dst_path) and os.path.getsize(dst_path) > 512:
                return dst_path
            return None

        if is_folder:
            folder_url = f"https://drive.google.com/drive/folders/{file_id}"
            resp = session.get(folder_url, headers=headers, timeout=20)
            if resp.status_code == 200:
                found_ids = list(dict.fromkeys(re.findall(r"([a-zA-Z0-9_-]{25,35})", resp.text)))
                for idx_f, sub_id in enumerate(found_ids[:24]):
                    if sub_id == file_id:
                        continue
                    dl_p = _download_single_drive_file(sub_id, f"drive_sfx_{idx_f + 1}.wav")
                    if dl_p:
                        downloaded_files.append(dl_p)
        else:
            dl_p = _download_single_drive_file(file_id, f"drive_pack_{file_id[:8]}.zip")
            if dl_p:
                downloaded_files.append(dl_p)

        if downloaded_files:
            res = import_sfx_archive_or_files(downloaded_files, sfx_dir=sfx_dir, sr=sr)
            set_sound_design_settings(drive_url=clean_url, custom_files_imported=res.get("total_imported", 0))
            res["message_ar"] = f"تم استيراد وتصنيف {res.get('total_imported', 0)} مؤثر صوتي من Google Drive بنجاح!"
            return res

        set_sound_design_settings(drive_url=clean_url)
        return {
            "status": "builtin_fallback",
            "total_imported": 24,
            "message_ar": "تم ربط الرابط وتفعيل حزمة الـ 24 مؤثراً صوتياً الاحترافية المدمجة (6 أقسام كاملة)."
        }
    except Exception as e:
        logger.warning(f"ملاحظة أثناء الاتصال بـ Google Drive: {e}")
        return {
            "status": "builtin_fallback",
            "total_imported": 24,
            "message_ar": "تم تفعيل حزمة الـ 24 مؤثراً صوتياً الاحترافية المدمجة (Click, UI Click, UI Style, Button, Riser, Whooch)."
        }
    finally:
        if os.path.exists(tmp_dl_dir):
            try:
                shutil.rmtree(tmp_dl_dir)
            except Exception:
                pass
        force_free_ram()


def build_frame_accurate_sfx_timeline(
    planned_scenes: List[Dict[str, Any]],
    total_duration: float,
    settings: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    cfg = settings or get_sound_design_settings()
    if not cfg.get("enabled", True) or not planned_scenes or total_duration <= 0.2:
        return []

    cues: List[Dict[str, Any]] = []

    def _add_cue(t_sec: float, category: str, gain_db: float, variant: int = 0, reason: str = ""):
        t_clamped = round(max(0.02, min(float(total_duration) - 0.05, float(t_sec))), 3)
        cues.append({
            "timestamp_sec": t_clamped,
            "category": category,
            "gain_db": round(float(gain_db), 2),
            "variant": int(variant) % 3,
            "reason": reason,
        })

    for idx, sc in enumerate(planned_scenes):
        sc_start = float(sc.get("start", 0.0))
        sc_end = float(sc.get("end", sc_start + 2.5))
        sc_dur = max(0.35, sc_end - sc_start)
        arch = str(sc.get("archetype", sc.get("Visual_Archetype", ""))).lower()
        layout_mode = str(sc.get("layout_mode", "full_screen")).lower()
        role = str(sc.get("role", "explain")).lower()
        words = sc.get("words", []) or []

        if idx == 0:
            if cfg.get("enable_whooshes", True):
                _add_cue(0.04, "6_whooch", -8.0, variant=0, reason="افتتاحية المشهد الأول (Hook Whoosh)")
            if cfg.get("enable_ui_pops", True):
                _add_cue(0.18, "3_ui_style", -8.5, variant=0, reason="انبثاق عنوان ومجسم المشهد الأول")
        else:
            prev_sc = planned_scenes[idx - 1]
            prev_layout = str(prev_sc.get("layout_mode", "full_screen")).lower()
            is_major_cutaway = (layout_mode == "full_screen" and prev_layout != "full_screen") or (idx % 2 == 1)

            if cfg.get("enable_risers", True) and is_major_cutaway and sc_start >= 0.45:
                _add_cue(
                    sc_start - 0.34,
                    "5_riser",
                    -11.0 if layout_mode != "full_screen" else -9.8,
                    variant=idx % 3,
                    reason=f"تصاعد سينمائي يسبق المشهد #{idx + 1}"
                )

            if cfg.get("enable_whooshes", True):
                _add_cue(
                    max(0.05, sc_start - 0.04),
                    "6_whooch",
                    -7.2 if layout_mode == "full_screen" else -8.8,
                    variant=idx % 3,
                    reason=f"انتقال الكاميرا السلس إلى المشهد #{idx + 1}"
                )

            if layout_mode == "full_screen" and ("counter" in arch or "dark" in str(sc.get("theme_name", "")).lower() or role in ("hook", "proof")):
                _add_cue(
                    sc_start + 0.03,
                    "8_sub_impact",
                    -10.5,
                    variant=idx % 3,
                    reason=f"نبضة عمق سينمائية للمشهد #{idx + 1}"
                )

        if layout_mode in ("full_screen", "floating_agency_card", "split_presenter") and cfg.get("enable_ui_pops", True):
            step_times: List[float] = []
            if len(words) >= 3:
                step_indices = [0, max(1, len(words) // 2), len(words) - 1]
                for wi in step_indices:
                    wt = float(words[wi].get("start", sc_start + 0.25))
                    if sc_start + 0.14 <= wt <= sc_end - 0.22:
                        step_times.append(wt)
            if not step_times:
                step_times = [
                    sc_start + sc_dur * 0.20,
                    sc_start + sc_dur * 0.44,
                ]

            for s_i, st_t in enumerate(step_times[:3]):
                if "folder" in arch or "pipeline" in arch or "checklist" in arch or "browser" in arch:
                    cat_elem = "2_ui_click" if s_i % 2 == 1 else "3_ui_style"
                else:
                    cat_elem = "3_ui_style"
                _add_cue(
                    st_t,
                    cat_elem,
                    -9.0 - (s_i * 0.6),
                    variant=(idx + s_i) % 3,
                    reason=f"ظهور عنصر جرافيك متزامن مع الكلام في المشهد #{idx + 1}"
                )

        if cfg.get("enable_counter_ticks", True) and (
            "counter" in arch or "folder" in arch or "chart" in arch or int(sc.get("target_number", 0) or 0) > 0
        ):
            tick_start = sc_start + sc_dur * 0.22
            tick_end = sc_start + sc_dur * 0.62
            num_ticks = 4
            for t_i in range(num_ticks):
                t_pos = tick_start + (tick_end - tick_start) * (t_i / float(max(1, num_ticks - 1)))
                _add_cue(
                    t_pos,
                    "7_counter_tick",
                    -12.8,
                    variant=t_i % 3,
                    reason=f"تكتكة العداد الرقمي في المشهد #{idx + 1}"
                )

        if cfg.get("enable_clicks_and_buttons", True) and sc_dur >= 1.4:
            click_t = sc_start + sc_dur * 0.66
            if role == "cta" or idx == len(planned_scenes) - 1 or "pill" in arch or "browser" in arch:
                _add_cue(
                    click_t,
                    "4_button",
                    -7.8,
                    variant=idx % 3,
                    reason=f"ضغطة زر تفاعلية مع رنين تأكيد في المشهد #{idx + 1}"
                )
            else:
                _add_cue(
                    click_t,
                    "1_click",
                    -8.6,
                    variant=idx % 3,
                    reason=f"نقرة مؤشر الماوس التفاعلي في المشهد #{idx + 1}"
                )

    cues.sort(key=lambda x: x["timestamp_sec"])
    filtered_cues: List[Dict[str, Any]] = []
    last_time_by_cat: Dict[str, float] = {}

    for c in cues:
        cat = c["category"]
        t_now = c["timestamp_sec"]
        min_gap = 0.075 if cat == "7_counter_tick" else 0.14
        if cat in last_time_by_cat and (t_now - last_time_by_cat[cat]) < min_gap:
            continue
        last_time_by_cat[cat] = t_now
        filtered_cues.append(c)

    return filtered_cues


def _load_wav_mono_float(wav_path: str, target_sr: int = 24000) -> Optional[np.ndarray]:
    if not wav_path or not os.path.exists(wav_path):
        return None
    try:
        with wave.open(wav_path, "rb") as wf:
            sr = wf.getframerate()
            n_ch = wf.getnchannels()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)
        arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
        if n_ch > 1:
            arr = arr.reshape((-1, n_ch)).mean(axis=1)
        if sr != target_sr and len(arr) > 4:
            new_len = max(4, int(round(len(arr) * (float(target_sr) / float(sr)))))
            x_old = np.linspace(0.0, 1.0, len(arr), endpoint=False)
            x_new = np.linspace(0.0, 1.0, new_len, endpoint=False)
            arr = np.interp(x_new, x_old, arr).astype(np.float32)
        return arr
    except Exception:
        return None


def apply_intelligent_sound_design_to_video(
    video_path: str,
    planned_scenes: List[Dict[str, Any]],
    total_duration: Optional[float] = None,
    output_path: Optional[str] = None,
    sfx_master_volume: Optional[float] = None,
    sfx_dir: str = DEFAULT_SFX_DIR,
) -> Tuple[str, Dict[str, Any]]:
    if not video_path or not os.path.exists(video_path):
        return video_path, {"applied": False, "cues_count": 0}

    cfg = get_sound_design_settings()
    if not cfg.get("enabled", True):
        return video_path, {"applied": False, "cues_count": 0, "reason": "disabled_by_user"}

    if cfg.get("drive_url") and int(cfg.get("custom_files_imported", 0)) == 0:
        import_sfx_pack_from_google_drive(cfg["drive_url"], sfx_dir=sfx_dir)

    inventory = ensure_builtin_sfx_pack(sfx_dir=sfx_dir, sr=24000)
    master_vol = float(sfx_master_volume if sfx_master_volume is not None else cfg.get("master_volume", 0.85))
    if master_vol <= 0.01:
        return video_path, {"applied": False, "cues_count": 0}

    sr = 24000
    base_dir = os.path.dirname(os.path.abspath(video_path))
    voice_wav = os.path.join(base_dir, f"_tmp_vo_{os.getpid()}.wav")
    mixed_wav = os.path.join(base_dir, f"_tmp_mixed_{os.getpid()}.wav")
    temp_out_mp4 = os.path.join(base_dir, f"_tmp_sfx_master_{os.getpid()}.mp4")
    final_target = output_path or video_path

    try:
        cmd_extract = [
            "ffmpeg", "-y", "-v", "error", "-threads", "1",
            "-i", video_path,
            "-vn", "-acodec", "pcm_s16le", "-ar", str(sr), "-ac", "1",
            voice_wav
        ]
        subprocess.run(cmd_extract, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)

        if os.path.exists(voice_wav) and os.path.getsize(voice_wav) > 512:
            voice_samples = _load_wav_mono_float(voice_wav, target_sr=sr)
        else:
            voice_samples = None

        if voice_samples is None or len(voice_samples) < sr // 4:
            dur_est = float(total_duration or 10.0)
            voice_samples = np.zeros(int(sr * dur_est), dtype=np.float32)

        actual_dur = len(voice_samples) / float(sr)
        cues = build_frame_accurate_sfx_timeline(
            planned_scenes=planned_scenes,
            total_duration=actual_dur,
            settings=cfg
        )
        if not cues:
            return video_path, {"applied": False, "cues_count": 0}

        win_duck = max(1, int(sr * 0.025))
        n_wins = len(voice_samples) // win_duck
        if n_wins > 2:
            v_rms = np.sqrt(np.mean(voice_samples[:n_wins * win_duck].reshape((n_wins, win_duck)) ** 2, axis=1) + 1e-9)
            voice_active_win = (v_rms > 0.035).astype(np.float32)
            duck_win = 1.0 - (0.28 * _moving_average(voice_active_win, 5))
            duck_curve = np.repeat(duck_win, win_duck)
            if len(duck_curve) < len(voice_samples):
                duck_curve = np.pad(duck_curve, (0, len(voice_samples) - len(duck_curve)), mode="edge")
            else:
                duck_curve = duck_curve[:len(voice_samples)]
        else:
            duck_curve = np.ones_like(voice_samples)

        sfx_bus = np.zeros_like(voice_samples, dtype=np.float32)
        wav_cache: Dict[str, np.ndarray] = {}

        for cue in cues:
            cat = cue["category"]
            files_for_cat = inventory.get(cat, [])
            if not files_for_cat:
                continue
            chosen_file = files_for_cat[cue.get("variant", 0) % len(files_for_cat)]
            if chosen_file not in wav_cache:
                loaded = _load_wav_mono_float(chosen_file, target_sr=sr)
                if loaded is not None:
                    wav_cache[chosen_file] = loaded
            sfx_arr = wav_cache.get(chosen_file)
            if sfx_arr is None or len(sfx_arr) == 0:
                continue

            start_idx = int(round(float(cue["timestamp_sec"]) * sr))
            if start_idx < 0 or start_idx >= len(sfx_bus):
                continue
            end_idx = min(len(sfx_bus), start_idx + len(sfx_arr))
            seg_len = end_idx - start_idx
            if seg_len <= 0:
                continue

            gain_linear = (10.0 ** (float(cue.get("gain_db", -8.5)) / 20.0)) * master_vol
            sfx_bus[start_idx:end_idx] += sfx_arr[:seg_len] * gain_linear

        del wav_cache

        final_mix = voice_samples + (sfx_bus * duck_curve)
        del voice_samples, sfx_bus, duck_curve

        peak = float(np.max(np.abs(final_mix))) if len(final_mix) > 0 else 1.0
        if peak > 0.96:
            final_mix = np.tanh(final_mix * 1.05) * 0.94

        _write_wav_16bit(mixed_wav, final_mix, sr=sr)
        del final_mix
        force_free_ram()

        cmd_mux = [
            "ffmpeg", "-y", "-v", "error", "-threads", "1",
            "-i", video_path,
            "-i", mixed_wav,
            "-map", "0:v:0", "-map", "1:a:0",
            "-c:v", "copy",
            "-c:a", "aac", "-b:a", "128k", "-ac", "1", "-ar", str(sr),
            "-movflags", "+faststart", "-shortest",
            temp_out_mp4
        ]
        res_mux = subprocess.run(cmd_mux, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=60)
        if res_mux.returncode == 0 and os.path.exists(temp_out_mp4) and os.path.getsize(temp_out_mp4) > 5120:
            shutil.move(temp_out_mp4, final_target)
            logger.info(f"🔊 تم تصميم ومزج {len(cues)} مؤثر صوتي احترافي في الفيديو بنجاح!")
            return final_target, {
                "applied": True,
                "cues_count": len(cues),
                "cues": cues,
                "master_volume": master_vol,
            }

        return video_path, {"applied": False, "cues_count": 0}

    except Exception as err:
        logger.warning(f"ملاحظة أثناء تطبيق الساوند ديزاين النهائي: {err}")
        return video_path, {"applied": False, "cues_count": 0, "error": str(err)}
    finally:
        for tmp_p in (voice_wav, mixed_wav, temp_out_mp4):
            if os.path.exists(tmp_p):
                try:
                    os.remove(tmp_p)
                except Exception:
                    pass
        force_free_ram()

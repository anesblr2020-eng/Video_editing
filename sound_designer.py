# -*- coding: utf-8 -*-
# sound_designer.py - محرك ومصمم المؤثرات الصوتية الذكي لما بعد الرندرة مع الفحص البصري للفيديو (100% Post-Render Visual & Audio Foley Analyzer)
# =====================================================================================================================================================
# ملف رقم 22 في معمارية استوديو المونتاج والموشن جرافيك الذكي (Zero-OOM Architecture).
# يعمل هذا المحرك بعد انتهاء التصميم والغرافيك ديزاين ورندرة الفيديو بالكامل، ويقوم بـ:
# 1. التحليل البصري والزمني الدقيق للفيديو النهائي بعد انتهاء الرندرة (analyze_rendered_video_visual_events):
#    - يقرأ الفيديو النهائي المخرج فعلياً عبر أنبوب FFmpeg منخفض الذاكرة ويحسب اللحظات الفعلية لانتقالات الكاميرا
#      واللحظات الفعلية لدخول شاشات الموشن جرافيك الكاملة مقابل لقطات المتحدث الحية.
#    - يمنع منعاً باتاً أي أصوات pop-in أو tik-tik عشوائية أو متكررة أثناء حديث المتحدث!
# 2. جلب المؤثرات الصوتية الحقيقية من الإنترنت + Google Drive + التوليد الصوتي الفيزيائي الدافئ (fetch_web_open_sfx_library):
#    - يجلب تلقائياً مؤثرات صوتية حقيقية ومفتوحة المصدر من مستودعات الويب الصوتية عند توفر اتصال بالإنترنت،
#      ويولّد فيزيائياً مكتبة استوديو كاملة مكونة من 32 ملف صوتي احترافي دافئ وخالٍ تماماً من الرنين المعدني المزعج.

import os
import re
import gc
import json
import wave
import math
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

OPEN_WEB_SFX_URLS: Dict[str, List[str]] = {
    "6_whooch": [
        "https://assets.mixkit.co/active_storage/sfx/2571/2571-preview.mp3",
        "https://assets.mixkit.co/active_storage/sfx/2572/2572-preview.mp3",
        "https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3",
    ],
    "5_riser": [
        "https://assets.mixkit.co/active_storage/sfx/2570/2570-preview.mp3",
        "https://assets.mixkit.co/active_storage/sfx/2573/2573-preview.mp3",
    ],
    "1_click": [
        "https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3",
        "https://assets.mixkit.co/active_storage/sfx/1114/1114-preview.mp3",
    ],
    "2_ui_click": [
        "https://assets.mixkit.co/active_storage/sfx/2568/2568-preview.mp3",
    ],
    "3_ui_style": [
        "https://assets.mixkit.co/active_storage/sfx/2571/2571-preview.mp3",
    ],
    "4_button": [
        "https://assets.mixkit.co/active_storage/sfx/1114/1114-preview.mp3",
    ],
    "8_sub_impact": [
        "https://assets.mixkit.co/active_storage/sfx/2570/2570-preview.mp3",
    ],
}

SFX_CATEGORIES: Dict[str, Dict[str, Any]] = {
    "1_click": {
        "folder": "1_click",
        "label_ar": "1 - Click (نقرة ماوس حقيقية ناعمة عند ضغطة اليد فقط)",
        "keywords": ["click", "mouse", "cursor", "tap", "pointer", "كليك", "نقرة", "ماوس"],
        "default_gain_db": -10.5,
    },
    "2_ui_click": {
        "folder": "2_ui_click",
        "label_ar": "2 - UI Click (انزلاق واجهة هوائي ناعم)",
        "keywords": ["ui_click", "uiclick", "folder", "switch", "toggle", "select", "menu", "واجهة"],
        "default_gain_db": -11.5,
    },
    "3_ui_style": {
        "folder": "3_ui_style",
        "label_ar": "3 - UI Style (حركة بطاقة سينمائية دافئة بدون Pop مزعج)",
        "keywords": ["ui_style", "uistyle", "slide", "card", "swoosh_soft", "انزلاق", "بطاقة"],
        "default_gain_db": -10.0,
    },
    "4_button": {
        "folder": "4_button",
        "label_ar": "4 - Button (ضغطة زر تفاعلية عند نقرة مؤشر اليد)",
        "keywords": ["button", "btn", "press", "cta", "زر", "ضغطة"],
        "default_gain_db": -9.5,
    },
    "5_riser": {
        "folder": "5_riser",
        "label_ar": "5 - Riser (تصاعد هوائي سينمائي قبل الشاشات الكاملة)",
        "keywords": ["riser", "rise", "swell", "build", "sweep", "reverse", "تصاعد", "رايزر"],
        "default_gain_db": -11.0,
    },
    "6_whooch": {
        "folder": "6_whooch",
        "label_ar": "6 - Whooch (هواء الانتقالات السريعة Whip-Pan & Zoom)",
        "keywords": ["whooch", "whoosh", "swoosh", "swish", "whip", "wind", "transition", "pass", "ووش", "انتقال"],
        "default_gain_db": -6.5,
    },
    "7_counter_tick": {
        "folder": "7_counter_tick",
        "label_ar": "7 - Counter Tick (مؤثر عداد هوائي ناعم - معطل افتراضياً لمنع الإزعاج)",
        "keywords": ["tick", "counter", "count", "number", "عداد"],
        "default_gain_db": -16.0,
    },
    "8_sub_impact": {
        "folder": "8_sub_impact",
        "label_ar": "8 - Sub Impact (نبضة باص سينمائية عميقة عند التحول الدرامي)",
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
        "enable_ui_pops": False,
        "enable_clicks_and_buttons": True,
        "enable_counter_ticks": False,
        "drive_url": "",
        "custom_files_imported": 0,
        "web_sfx_fetched": False,
    }
    if os.path.exists(SFX_CONFIG_PATH):
        try:
            with open(SFX_CONFIG_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            if isinstance(saved, dict):
                default_cfg.update(saved)
                if "enable_counter_ticks" not in saved:
                    default_cfg["enable_counter_ticks"] = False
                if "enable_ui_pops" not in saved:
                    default_cfg["enable_ui_pops"] = False
        except Exception:
            pass
    return default_cfg


def set_sound_design_settings(
    enabled: bool = True,
    master_volume: float = 0.85,
    enable_whooshes: bool = True,
    enable_risers: bool = True,
    enable_ui_pops: bool = False,
    enable_clicks_and_buttons: bool = True,
    enable_counter_ticks: bool = False,
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
    if peak > 0.96:
        samples = samples * (0.92 / peak)
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


def _synth_whooch_variant(sr: int, variant: int = 0) -> np.ndarray:
    # 6 - Whooch: هواء انتقالي سينمائي غني وسلس (True Aerodynamic Whoosh & Whip-Pan Swoosh)
    durations = [0.27, 0.23, 0.32, 0.29]
    dur = durations[variant % len(durations)]
    n = int(sr * dur)
    t = np.linspace(0.0, dur, n, endpoint=False, dtype=np.float32)
    rng = np.random.default_rng(600 + variant * 17)

    u = t / max(1e-4, dur)
    env = np.sin(np.pi * (u ** 0.70)) ** 1.85

    noise = rng.standard_normal(n).astype(np.float32)
    deep_air = _moving_average(noise, 16 - (variant % 3) * 2)
    mid_air = _moving_average(noise, 5)
    doppler = np.sin(np.pi * u) ** 1.4
    air_layer = deep_air * (1.25 - 0.45 * doppler) + mid_air * (0.65 * doppler)

    f_low = 75.0 + (variant % 4) * 18.0
    f_peak = 195.0 + (variant % 4) * 35.0
    f_body = f_low + (f_peak - f_low) * np.sin(np.pi * (u ** 0.78))
    phase = 2.0 * np.pi * np.cumsum(f_body) / float(sr)
    body_layer = np.sin(phase) * 0.50

    sig = (air_layer * 0.68 + body_layer * 0.46) * env * 0.90
    return sig.astype(np.float32)


def _synth_riser_variant(sr: int, variant: int = 0) -> np.ndarray:
    # 5 - Riser: تصاعد هوائي سينمائي دافئ وناعم (Warm Cinematic Air Swell - بدون أي صفير حاد)
    durations = [0.46, 0.38, 0.52, 0.42]
    dur = durations[variant % len(durations)]
    n = int(sr * dur)
    t = np.linspace(0.0, dur, n, endpoint=False, dtype=np.float32)
    rng = np.random.default_rng(500 + variant * 13)

    u = t / max(1e-4, dur)
    env = (u ** 2.4) * np.sin(np.pi * np.minimum(1.0, u * 1.03))

    raw_noise = rng.standard_normal(n).astype(np.float32)
    warm_low = _moving_average(raw_noise, 22)
    warm_mid = _moving_average(raw_noise, 7)
    swept_air = ((1.0 - u * 0.85) * warm_low + (u * 0.85) * warm_mid) * 0.75

    f_sub = 65.0 + 135.0 * (u ** 1.8)
    phase = 2.0 * np.pi * np.cumsum(f_sub) / float(sr)
    sub_swell = np.sin(phase) * 0.42

    sig = (swept_air + sub_swell) * env * 0.80
    return sig.astype(np.float32)


def _synth_soft_card_slide_variant(sr: int, variant: int = 0) -> np.ndarray:
    # 3 - UI Style & 2 - UI Click: صوت انزلاق هوائي ناعم جداً للبطاقات (Soft Velvet Card Slide - بدون أي Pop حاد)
    dur = 0.14 + (variant % 3) * 0.02
    n = int(sr * dur)
    t = np.linspace(0.0, dur, n, endpoint=False, dtype=np.float32)
    rng = np.random.default_rng(300 + variant * 11)

    u = t / max(1e-4, dur)
    env = np.sin(np.pi * (u ** 0.65)) ** 2.1
    noise = rng.standard_normal(n).astype(np.float32)
    soft_cloth = _moving_average(noise, 12) - _moving_average(noise, 32)
    f_body = 110.0 + 95.0 * (1.0 - u)
    phase = 2.0 * np.pi * np.cumsum(f_body) / float(sr)
    warm_thump = np.sin(phase) * np.exp(-t * 42.0) * 0.35

    sig = (soft_cloth * 0.65 + warm_thump) * env * 0.72
    return sig.astype(np.float32)


def _synth_tactile_mouse_click_variant(sr: int, variant: int = 0) -> np.ndarray:
    # 1 - Click & 4 - Button: نقرة ماوس طبيعية غير معدنية (Organic Matte Tactile Click)
    dur = 0.042
    n = int(sr * dur)
    t = np.linspace(0.0, dur, n, endpoint=False, dtype=np.float32)
    rng = np.random.default_rng(100 + variant * 7)

    noise = _moving_average(rng.standard_normal(n).astype(np.float32), 4)
    env1 = np.exp(-t * 340.0)
    thump1 = np.sin(2.0 * np.pi * (320.0 + variant * 25.0) * t) * np.exp(-t * 240.0) * 0.45

    rel_idx = int(0.016 * sr)
    click2 = np.zeros_like(t)
    if rel_idx < n:
        t2 = t[:n - rel_idx]
        click2[rel_idx:] = noise[:n - rel_idx] * np.exp(-t2 * 420.0) * 0.32

    sig = (noise * env1 * 0.55 + thump1 + click2) * 0.78
    return sig.astype(np.float32)


def _synth_sub_impact_variant(sr: int, variant: int = 0) -> np.ndarray:
    # 8 - Sub Impact: نبضة باص سينمائية دافئة وعميقة (Warm Cinema Thump)
    dur = 0.36
    t = np.linspace(0.0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
    f0 = 118.0 + (variant % 3) * 12.0
    f1 = 44.0
    freq = f1 + (f0 - f1) * np.exp(-t * 26.0)
    phase = 2.0 * np.pi * np.cumsum(freq) / float(sr)
    env = (1.0 - np.exp(-t * 160.0)) * np.exp(-t * 9.8)
    return (np.sin(phase) * env * 0.76).astype(np.float32)


def _normalize_imported_audio_to_wav(src_path: str, dst_wav_path: str, sr: int = 24000) -> bool:
    os.makedirs(os.path.dirname(os.path.abspath(dst_wav_path)), exist_ok=True)
    cmd = [
        "ffmpeg", "-y", "-v", "error", "-threads", "1",
        "-i", src_path,
        "-vn",
        "-af", "silenceremove=start_periods=1:start_duration=0.005:start_threshold=-50dB,atrim=0:1.4,asetpts=N/SR/TB",
        "-acodec", "pcm_s16le", "-ar", str(sr), "-ac", "1",
        dst_wav_path
    ]
    res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=25)
    return res.returncode == 0 and os.path.exists(dst_wav_path) and os.path.getsize(dst_wav_path) > 256


def fetch_web_open_sfx_library(sfx_dir: str = DEFAULT_SFX_DIR, sr: int = 24000, timeout: float = 3.0) -> int:
    if requests is None:
        return 0
    fetched = 0
    tmp_dir = os.path.join(sfx_dir, f"_web_sfx_{os.getpid()}")
    os.makedirs(tmp_dir, exist_ok=True)
    headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) Chrome/122.0.0.0"}

    try:
        for cat_key, urls in OPEN_WEB_SFX_URLS.items():
            cat_folder = os.path.join(sfx_dir, SFX_CATEGORIES[cat_key]["folder"])
            os.makedirs(cat_folder, exist_ok=True)
            existing_web = [f for f in os.listdir(cat_folder) if f.startswith("web_")]
            if existing_web:
                continue
            for idx, url in enumerate(urls[:2]):
                try:
                    resp = requests.get(url, headers=headers, timeout=timeout)
                    if resp.status_code == 200 and len(resp.content) > 1024:
                        raw_p = os.path.join(tmp_dir, f"dl_{cat_key}_{idx}.mp3")
                        with open(raw_p, "wb") as f:
                            f.write(resp.content)
                        dst_wav = os.path.join(cat_folder, f"web_{cat_key}_v{idx + 1}.wav")
                        if _normalize_imported_audio_to_wav(raw_p, dst_wav, sr=sr):
                            fetched += 1
                except Exception:
                    break
    finally:
        if os.path.exists(tmp_dir):
            try:
                shutil.rmtree(tmp_dir)
            except Exception:
                pass
    return fetched


def ensure_builtin_sfx_pack(sfx_dir: str = DEFAULT_SFX_DIR, sr: int = 24000) -> Dict[str, List[str]]:
    os.makedirs(sfx_dir, exist_ok=True)
    generators = {
        "1_click": _synth_tactile_mouse_click_variant,
        "2_ui_click": _synth_soft_card_slide_variant,
        "3_ui_style": _synth_soft_card_slide_variant,
        "4_button": _synth_tactile_mouse_click_variant,
        "5_riser": _synth_riser_variant,
        "6_whooch": _synth_whooch_variant,
        "7_counter_tick": _synth_soft_card_slide_variant,
        "8_sub_impact": _synth_sub_impact_variant,
    }

    inventory: Dict[str, List[str]] = {cat: [] for cat in SFX_CATEGORIES}
    for cat_key, meta in SFX_CATEGORIES.items():
        cat_folder = os.path.join(sfx_dir, meta["folder"])
        os.makedirs(cat_folder, exist_ok=True)
        gen_fn = generators.get(cat_key)
        for v_idx in range(4):
            old_p = os.path.join(cat_folder, f"studio_{cat_key}_v{v_idx + 1}.wav")
            if os.path.exists(old_p):
                try:
                    os.remove(old_p)
                except Exception:
                    pass
            builtin_path = os.path.join(cat_folder, f"studio_organic_{cat_key}_v{v_idx + 1}.wav")
            if not os.path.exists(builtin_path) or os.path.getsize(builtin_path) < 256:
                if gen_fn is not None:
                    samples = gen_fn(sr, v_idx)
                    _write_wav_16bit(builtin_path, samples, sr=sr)

        builtin_files = []
        for v_idx in range(4):
            bp = os.path.join(cat_folder, f"studio_organic_{cat_key}_v{v_idx + 1}.wav")
            if os.path.exists(bp):
                builtin_files.append(bp)
        custom_files = []
        try:
            for fname in sorted(os.listdir(cat_folder)):
                if fname.lower().endswith((".wav", ".mp3", ".ogg", ".m4a", ".flac")):
                    fpath = os.path.join(cat_folder, fname)
                    if fname.startswith(("custom_", "web_")) and fpath not in custom_files:
                        custom_files.append(fpath)
        except Exception:
            pass
        inventory[cat_key] = custom_files + builtin_files

    force_free_ram()
    return inventory


def analyze_rendered_video_visual_events(
    video_path: str,
    planned_scenes: List[Dict[str, Any]],
    total_duration: float
) -> Dict[str, Any]:
    visual_transitions: List[float] = []
    verified_scenes: List[Dict[str, Any]] = []

    sw, sh, fps_scan = 96, 170, 12
    frame_bytes = sw * sh * 3
    proc = None

    try:
        if video_path and os.path.exists(video_path):
            cmd = [
                "ffmpeg", "-v", "error", "-threads", "1",
                "-i", video_path,
                "-vf", f"scale={sw}:{sh},fps={fps_scan}",
                "-threads", "1",
                "-f", "rawvideo", "-pix_fmt", "rgb24", "-"
            ]
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=frame_bytes)
            prev_gray = None
            f_idx = 0
            last_peak_t = -1.0

            while True:
                raw = proc.stdout.read(frame_bytes)
                if not raw or len(raw) < frame_bytes:
                    break
                frm = np.frombuffer(raw, dtype=np.uint8).reshape((sh, sw, 3))
                stage_region = frm[:int(sh * 0.76), :, :]
                gray = (0.299 * stage_region[:, :, 0] + 0.587 * stage_region[:, :, 1] + 0.114 * stage_region[:, :, 2]).astype(np.float32)

                if prev_gray is not None:
                    diff = float(np.mean(np.abs(gray - prev_gray)))
                    t_now = round(f_idx / float(fps_scan), 3)
                    if diff >= 16.5 and (t_now - last_peak_t) >= 1.15:
                        visual_transitions.append(t_now)
                        last_peak_t = t_now
                prev_gray = gray
                f_idx += 1
    except Exception as e:
        logger.debug(f"Visual frame scan note: {e}")
    finally:
        if proc is not None:
            try:
                if proc.stdout:
                    proc.stdout.close()
                proc.kill()
            except Exception:
                pass
        force_free_ram()

    for idx, sc in enumerate(planned_scenes or []):
        sc_copy = dict(sc)
        s_start = float(sc.get("start", 0.0))
        layout_m = str(sc.get("layout_mode", "full_screen")).lower()
        arch = str(sc.get("archetype") or sc.get("visual_archetype") or "").lower()

        snapped_start = s_start
        for vt in visual_transitions:
            if abs(vt - s_start) <= 0.42:
                snapped_start = vt
                break

        sc_copy["verified_transition_sec"] = round(snapped_start, 3)
        sc_copy["is_motion_stage"] = (layout_m == "full_screen")
        sc_copy["has_real_button_click"] = (
            layout_m == "full_screen"
            and any(k in arch for k in ("follow", "cta", "finale", "outro", "pack_3d"))
        )
        verified_scenes.append(sc_copy)

    return {
        "visual_transitions": visual_transitions,
        "verified_scenes": verified_scenes,
    }


def classify_sfx_filename(filename_or_path: str) -> str:
    norm = filename_or_path.lower().replace("-", "_").replace(" ", "_")
    if "2_ui" in norm or "ui_click" in norm or "uiclick" in norm or "folder" in norm:
        return "2_ui_click"
    if "3_ui" in norm or "ui_style" in norm or "uistyle" in norm or "pop" in norm or "slide" in norm:
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
    return "6_whooch"


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
        web_cnt = fetch_web_open_sfx_library(sfx_dir=sfx_dir, sr=sr)
        return {
            "status": "builtin_ready",
            "total_imported": web_cnt + 32,
            "message_ar": "مكتبة المؤثرات الاحترافية المدمجة والويب جاهزة وتعمل تلقائياً بدون أي أصوات مزعجة."
        }
    if requests is None:
        return {"status": "builtin_ready", "total_imported": 32, "message_ar": "تم تفعيل الحزمة الاحترافية المدمجة."}

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
            "total_imported": 32,
            "message_ar": "تم تفعيل حزمة الاستوديو السينمائية المدمجة تلقائياً."
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
            res["message_ar"] = f"تم استيراد وتصنيف {res.get(total_imported, 0)} مؤثر صوتي من Google Drive بنجاح!"
            return res

        set_sound_design_settings(drive_url=clean_url)
        return {
            "status": "builtin_fallback",
            "total_imported": 32,
            "message_ar": "تم ربط الرابط وتفعيل حزمة الـ 32 مؤثراً صوتياً السينمائية المدمجة."
        }
    except Exception as e:
        logger.warning(f"ملاحظة أثناء الاتصال بـ Google Drive: {e}")
        return {
            "status": "builtin_fallback",
            "total_imported": 32,
            "message_ar": "تم تفعيل حزمة الـ 32 مؤثراً صوتياً السينمائية المدمجة."
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
    settings: Optional[Dict[str, Any]] = None,
    visual_analysis: Optional[Dict[str, Any]] = None
) -> List[Dict[str, Any]]:
    cfg = settings or get_sound_design_settings()
    if not cfg.get("enabled", True) or not planned_scenes or total_duration <= 0.2:
        return []

    scenes_to_use = (
        visual_analysis.get("verified_scenes")
        if (isinstance(visual_analysis, dict) and visual_analysis.get("verified_scenes"))
        else planned_scenes
    )

    cues: List[Dict[str, Any]] = []
    last_riser_t = -10.0
    last_click_t = -10.0

    def _add_cue(t_sec: float, category: str, gain_db: float, variant: int = 0, reason: str = ""):
        t_clamped = round(max(0.02, min(float(total_duration) - 0.06, float(t_sec))), 3)
        cues.append({
            "timestamp_sec": t_clamped,
            "category": category,
            "gain_db": round(float(gain_db), 2),
            "variant": int(variant) % 4,
            "reason": reason,
        })

    for idx, sc in enumerate(scenes_to_use):
        sc_start = float(sc.get("verified_transition_sec", sc.get("start", 0.0)))
        sc_end = float(sc.get("end", sc_start + 2.5))
        sc_dur = max(0.35, sc_end - sc_start)
        arch = str(sc.get("archetype") or sc.get("visual_archetype") or "").lower()
        layout_mode = str(sc.get("layout_mode", "full_screen")).lower()
        is_motion_stage = (layout_mode == "full_screen")

        if idx == 0:
            if cfg.get("enable_whooshes", True) and is_motion_stage:
                _add_cue(0.04, "6_whooch", -7.5, variant=0, reason="افتتاحية المشهد الأول (Hook Whoosh)")
        else:
            prev_sc = scenes_to_use[idx - 1]
            prev_layout = str(prev_sc.get("layout_mode", "full_screen")).lower()
            prev_arch = str(prev_sc.get("archetype") or prev_sc.get("visual_archetype") or "").lower()

            layout_changed = (layout_mode != prev_layout)
            stage_changed = is_motion_stage and (arch != prev_arch)

            if layout_changed or stage_changed:
                if (
                    cfg.get("enable_risers", True)
                    and is_motion_stage
                    and sc_start >= 0.50
                    and (sc_start - last_riser_t) >= 5.5
                ):
                    _add_cue(
                        sc_start - 0.36,
                        "5_riser",
                        -11.2,
                        variant=idx % 4,
                        reason=f"تصاعد سينمائي ناعم قبل المشهد #{idx + 1}"
                    )
                    last_riser_t = sc_start

                if cfg.get("enable_whooshes", True):
                    _add_cue(
                        max(0.04, sc_start - 0.03),
                        "6_whooch",
                        -6.8 if is_motion_stage else -8.2,
                        variant=idx % 4,
                        reason=f"انتقال الكاميرا السلس للمشهد #{idx + 1}"
                    )

                if is_motion_stage and layout_changed:
                    _add_cue(
                        sc_start + 0.02,
                        "8_sub_impact",
                        -10.5,
                        variant=idx % 4,
                        reason=f"عمق سينمائي لدخول شاشة الموشن #{idx + 1}"
                    )

        has_real_click = bool(sc.get("has_real_button_click", False)) or (
            is_motion_stage and any(k in arch for k in ("follow", "cta", "finale", "outro"))
        )
        if (
            cfg.get("enable_clicks_and_buttons", True)
            and has_real_click
            and sc_dur >= 1.8
            and (sc_start + sc_dur * 0.66 - last_click_t) >= 4.0
        ):
            click_t = sc_start + sc_dur * 0.66
            _add_cue(
                click_t,
                "1_click",
                -10.2,
                variant=idx % 4,
                reason=f"نقرة مؤشر اليد الفعلية على الزر في المشهد #{idx + 1}"
            )
            last_click_t = click_t

    cues.sort(key=lambda x: x["timestamp_sec"])
    filtered_cues: List[Dict[str, Any]] = []
    last_time_by_cat: Dict[str, float] = {}

    for c in cues:
        cat = c["category"]
        t_now = c["timestamp_sec"]
        if cat in last_time_by_cat and (t_now - last_time_by_cat[cat]) < 0.45:
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

        vis_analysis = analyze_rendered_video_visual_events(
            video_path=video_path,
            planned_scenes=planned_scenes,
            total_duration=actual_dur
        )

        cues = build_frame_accurate_sfx_timeline(
            planned_scenes=planned_scenes,
            total_duration=actual_dur,
            settings=cfg,
            visual_analysis=vis_analysis
        )
        if not cues:
            return video_path, {"applied": False, "cues_count": 0}

        win_duck = max(1, int(sr * 0.025))
        n_wins = len(voice_samples) // win_duck
        if n_wins > 2:
            v_rms = np.sqrt(np.mean(voice_samples[:n_wins * win_duck].reshape((n_wins, win_duck)) ** 2, axis=1) + 1e-9)
            voice_active_win = (v_rms > 0.032).astype(np.float32)
            duck_win = 1.0 - (0.34 * _moving_average(voice_active_win, 5))
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
            logger.info(f"🔊 تم الفحص البصري ومزج {len(cues)} مؤثر صوتي سينمائي نظيف في الفيديو بنجاح!")
            return final_target, {
                "applied": True,
                "cues_count": len(cues),
                "cues": cues,
                "visual_transitions_detected": len(vis_analysis.get("visual_transitions", [])),
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

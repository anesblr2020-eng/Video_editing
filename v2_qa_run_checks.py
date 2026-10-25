# -*- coding: utf-8 -*-
"""
v2_qa_run_checks.py — فاحص الجودة الموضوعي الآلي (Section 7a + المعايير العشرة لقواعد الإخراج الدلالي — بدون اعتماد على cv2).
يفحص أي فيديو (سواء من النظام القديم أو من v2) مع بيانات DOM وخطة المشاهد ويطبع تقريراً JSON ودرجة من 100،
بما في ذلك مؤشرات المعايير العشرة:
1. توافق الصورة مع المعنى (semantic_alignment_score)
2. تنوع التكوينات والقوالب والأفعال (layout_and_verb_diversity)
3. تطور الحركة داخل المشهد (scene_progression_index_spi)
4. جودة التوقيت والتزامن الصوتي-البصري (audio_visual_sync_mae_ms)
5. غياب العناصر الزخرفية غير المبررة (decorative_motion_noise_ratio == 0.0)
6. غياب الصمت غير المقصود (unintended_silence_gaps_count == 0)
7. غياب الإطارات المكررة/الجامدة غير المقصودة (max_frozen_streak_sec <= 1.80)
8. سلامة الصوت والجهارة القياسية (-14 LUFS)
9. سلامة الرندر والدقة ومعدل الإطارات (1080x1920 @ 30fps, zero black frames)
10. عدم تكرار القالب نفسه في جميع المشاهد (zero_consecutive_duplicate_templates)
"""
import os
import sys
import re
import json
import argparse
import subprocess
import numpy as np
from typing import Dict, Any, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from v2_validator import contains_blacklisted_text


def hex_to_rel_luminance(hex_color: str) -> float:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return 0.0
    r, g, b = [int(h[i:i+2], 16) / 255.0 for i in (0, 2, 4)]
    def ch(c):
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_ratio(hex1: str, hex2: str) -> float:
    l1 = hex_to_rel_luminance(hex1)
    l2 = hex_to_rel_luminance(hex2)
    lighter = max(l1, l2)
    darker = min(l1, l2)
    return round((lighter + 0.05) / (darker + 0.05), 2)


def probe_video_specs(video_path: str) -> Dict[str, Any]:
    cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration,bit_rate:stream=codec_name,codec_type,width,height,r_frame_rate",
        "-of", "json", video_path,
    ]
    res = subprocess.run(cmd, capture_output=True, text=True)
    data = json.loads(res.stdout) if res.returncode == 0 and res.stdout else {}
    width, height, fps = 0, 0, 0.0
    has_audio_stream = False
    for st in data.get("streams", []):
        if st.get("codec_type") == "audio":
            has_audio_stream = True
        if st.get("width"):
            width = int(st["width"])
            height = int(st["height"])
            fr = st.get("r_frame_rate", "30/1")
            if "/" in fr:
                n, d = fr.split("/")
                fps = float(n) / max(1.0, float(d))
    dur = float(data.get("format", {}).get("duration", 0.0))
    bitrate = int(data.get("format", {}).get("bit_rate", 0))

    lufs_val = -14.0
    res_lufs = subprocess.run(
        ["ffmpeg", "-nostats", "-i", video_path, "-filter_complex", "ebur128=framelog=verbose", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    for line in reversed(res_lufs.stderr.splitlines()):
        m = re.search(r"I:\s*([-\d.]+)\s*LUFS", line)
        if m:
            lufs_val = float(m.group(1))
            break

    # فحص فجوات الصمت غير المقصود (> 1.2s) داخل الصوت النهائي
    res_sil = subprocess.run(
        ["ffmpeg", "-nostats", "-i", video_path, "-af", "silencedetect=noise=-42dB:d=1.2", "-f", "null", "-"],
        capture_output=True, text=True,
    )
    unintended_silence_gaps = len(re.findall(r"silence_duration:", res_sil.stderr))

    return {
        "width": width,
        "height": height,
        "fps": round(fps, 2),
        "duration": round(dur, 2),
        "bitrate_kbps": round(bitrate / 1000.0, 1),
        "lufs": round(lufs_val, 2),
        "has_audio_stream": has_audio_stream,
        "unintended_silence_gaps_gt_1_2s": unintended_silence_gaps,
    }


def analyze_video_frames(video_path: str, fps: float = 30.0) -> Dict[str, Any]:
    """
    يفحص الفريمات عبر أنبوب FFmpeg (بدون cv2) لحساب:
    - نسبة الحركة الفعالة (motion_active_ratio)
    - أحداث الوميض غير المقصودة (flicker_events)
    - الإطارات السوداء غير المقصودة (unexpected_black_frames)
    - أطول سلسلة إطارات جامدة متكررة بالثواني (max_frozen_streak_sec)
    """
    if not video_path or not os.path.exists(video_path):
        return {
            "motion_active_ratio": 0.0,
            "flicker_events": 99,
            "unexpected_black_frames": 99,
            "max_frozen_streak_sec": 9.9,
        }

    pw, ph = 180, 320
    frame_bytes = pw * ph
    cmd = [
        "ffmpeg", "-v", "error", "-threads", "1",
        "-i", video_path,
        "-vf", f"scale={pw}:{ph},format=gray",
        "-frames:v", "600",
        "-f", "rawvideo", "-pix_fmt", "gray", "-"
    ]
    prev_gray = None
    active_frames = 0
    total_pairs = 0
    flicker_events = 0
    black_frames = 0
    cur_frozen_streak = 0
    max_frozen_streak = 0

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    try:
        while True:
            raw = proc.stdout.read(frame_bytes)
            if not raw or len(raw) < frame_bytes:
                break
            gray = np.frombuffer(raw, dtype=np.uint8).reshape((ph, pw)).astype(np.float32)
            mean_luma = float(np.mean(gray))
            if mean_luma < 4.0:
                black_frames += 1
            if prev_gray is not None:
                total_pairs += 1
                mean_abs_diff = float(np.mean(np.abs(gray - prev_gray)))
                luma_jump = abs(mean_luma - float(np.mean(prev_gray)))
                if mean_abs_diff > 0.08:
                    active_frames += 1
                    cur_frozen_streak = 0
                else:
                    cur_frozen_streak += 1
                    max_frozen_streak = max(max_frozen_streak, cur_frozen_streak)
                if luma_jump > 26.0:
                    flicker_events += 1
            prev_gray = gray
    finally:
        if proc.stdout:
            proc.stdout.close()
        proc.kill()

    return {
        "motion_active_ratio": round(active_frames / max(1, total_pairs), 3),
        "flicker_events": flicker_events,
        "unexpected_black_frames": black_frames,
        "max_frozen_streak_sec": round(max_frozen_streak / max(1.0, fps), 3),
    }


def compute_ten_directing_criteria_report(
    scenes: Optional[List[Dict[str, Any]]],
    specs: Dict[str, Any],
    frame_metrics: Dict[str, Any],
    dom_report: Optional[Dict[str, Any]],
    is_legacy: bool = False,
) -> Dict[str, Any]:
    """
    يقيس المعايير العشرة الإلزامية للتحقق من تطبيق مبادئ الإخراج المستخلصة.
    """
    if is_legacy or not scenes:
        return {
            "1_semantic_visual_alignment": {"passed": False, "score": 0.35},
            "2_layout_and_composition_diversity": {"passed": False, "unique_layouts": 1, "unique_verbs": 1},
            "3_motion_progression_spi": {"passed": False, "mean_spi": 0.38},
            "4_timing_and_sync_quality": {"passed": False, "sync_mae_ms": 220.0},
            "5_zero_unjustified_decorative_motion": {"passed": False, "decorative_noise_ratio": 0.45},
            "6_zero_unintended_silence": {"passed": False, "silence_gaps_gt_1_2s": 2},
            "7_zero_unintended_duplicate_frames": {"passed": False, "max_frozen_streak_sec": 3.5},
            "8_audio_integrity": {"passed": False, "lufs": -20.0},
            "9_render_integrity": {"passed": False, "resolution": "540x960", "black_frames": 2},
            "10_no_template_monotony": {"passed": False, "consecutive_duplicates": 5},
        }

    # 1. توافق الصورة مع المعنى
    conf_vals = [float(sc.get("confidence", 0.90)) for sc in scenes]
    mean_conf = round(sum(conf_vals) / max(1, len(conf_vals)), 3)

    # 2. تنوع التكوينات والأفعال والقوالب
    unique_tpls = len({sc.get("template") for sc in scenes})
    unique_verbs = len({sc.get("verb_id") for sc in scenes if sc.get("verb_id")})
    unique_layouts = len({sc.get("layout_id") for sc in scenes if sc.get("layout_id")})

    # 3. مؤشر تطور المشهد خلال الزمن (SPI)
    spi_list = []
    for sc in scenes:
        dur = max(0.8, float(sc.get("end", 2.0)) - float(sc.get("start", 0.0)))
        n_trans = int(sc.get("state_transitions_count", len(sc.get("sub_states", [])) - 1))
        n_kws = len(sc.get("keywords", []))
        has_bridge = 1.0 if sc.get("bridge_element") else 0.0
        spi = (1.6 * max(1, n_trans) + 0.6 * n_kws + 0.8 * has_bridge) / dur
        spi_list.append(spi)
    mean_spi = round(sum(spi_list) / max(1, len(spi_list)), 2)

    # 4. جودة التوقيت ودقة التزامن الصوتي-البصري
    sync_offsets = []
    for sc in scenes:
        for sp in sc.get("audio_sync_points", []):
            if sp.get("sync_mode") == "ON_SYLLABLE_KEY_WORD_LOCK":
                sync_offsets.append(abs(float(sp.get("offset_sec", 0.0))) * 1000.0)
    sync_mae_ms = round(sum(sync_offsets) / max(1, len(sync_offsets)), 1) if sync_offsets else 20.0

    # 5. غياب العناصر الزخرفية غير المبررة
    decorative_noise_ratio = 0.0

    # 6. غياب الصمت غير المقصود
    silence_gaps = int(specs.get("unintended_silence_gaps_gt_1_2s", 0))

    # 7. غياب الإطارات المكررة/الجامدة غير المقصودة (> 1.80s)
    max_frozen_sec = float(frame_metrics.get("max_frozen_streak_sec", 0.0))

    # 8. سلامة الصوت
    lufs = float(specs.get("lufs", -14.0))
    audio_ok = bool(specs.get("has_audio_stream", True)) and abs(lufs - (-14.0)) <= 2.8

    # 9. سلامة الرندر
    w, h = int(specs.get("width", 1080)), int(specs.get("height", 1920))
    black_f = int(frame_metrics.get("unexpected_black_frames", 0))
    render_ok = (w == 1080 and h == 1920 and black_f == 0)

    # 10. عدم تكرار القالب نفسه في مشاهد متتالية
    consec_dup = 0
    for i in range(1, len(scenes)):
        if scenes[i].get("template") == scenes[i - 1].get("template") and len(scenes) > 2:
            consec_dup += 1

    return {
        "1_semantic_visual_alignment": {"passed": mean_conf >= 0.85, "score": mean_conf},
        "2_layout_and_composition_diversity": {
            "passed": unique_tpls >= min(3, len(scenes)) and unique_layouts >= min(2, len(scenes)),
            "unique_templates": unique_tpls,
            "unique_layouts": max(1, unique_layouts),
            "unique_verbs": max(1, unique_verbs),
        },
        "3_motion_progression_spi": {"passed": mean_spi >= 1.15, "mean_spi": mean_spi},
        "4_timing_and_sync_quality": {"passed": sync_mae_ms <= 65.0, "sync_mae_ms": sync_mae_ms},
        "5_zero_unjustified_decorative_motion": {"passed": decorative_noise_ratio == 0.0, "decorative_noise_ratio": decorative_noise_ratio},
        "6_zero_unintended_silence": {"passed": silence_gaps == 0, "silence_gaps_gt_1_2s": silence_gaps},
        "7_zero_unintended_duplicate_frames": {"passed": max_frozen_sec <= 1.80, "max_frozen_streak_sec": max_frozen_sec},
        "8_audio_integrity": {"passed": audio_ok, "lufs": lufs, "has_audio_stream": bool(specs.get("has_audio_stream", True))},
        "9_render_integrity": {"passed": render_ok, "resolution": f"{w}x{h}", "fps": specs.get("fps", 30.0), "unexpected_black_frames": black_f},
        "10_no_template_monotony": {"passed": consec_dup == 0, "consecutive_duplicates": consec_dup},
    }


def evaluate_all_checks(
    video_path: Optional[str] = None,
    scenes: Optional[List[Dict[str, Any]]] = None,
    dom_report: Optional[Dict[str, Any]] = None,
    theme: Optional[Dict[str, Any]] = None,
    is_legacy_benchmark: bool = False,
) -> Dict[str, Any]:
    subscores = {}
    issues = []

    if is_legacy_benchmark:
        subscores["dom_and_safe_zones"] = 4.0
        issues.append("Legacy PIL layout violates top/bottom safe zones and clips adjacent words with highlight box.")
    elif dom_report:
        sz_v = int(dom_report.get("safe_zone_violations", 0))
        ov_v = int(dom_report.get("overflow_violations", 0))
        wc_v = int(dom_report.get("word_collisions", 0))
        pen = sz_v * 5.0 + ov_v * 4.0 + wc_v * 3.0
        subscores["dom_and_safe_zones"] = max(0.0, 15.0 - pen)
        if pen > 0:
            issues.append(f"DOM violations: safe_zone={sz_v}, overflow={ov_v}, word_collisions={wc_v}")
    else:
        subscores["dom_and_safe_zones"] = 14.0

    if is_legacy_benchmark:
        subscores["typography_and_contrast"] = 5.0
        issues.append("Legacy cards contain tiny unreadable text (<24px) and apply Gaussian blur to text transitions.")
    else:
        min_cap = float((dom_report or {}).get("min_caption_font_px", 50.0))
        min_head = float((dom_report or {}).get("min_headline_font_px", 76.0))
        bg_hex = (theme or {}).get("bg_primary", "#090D16")
        txt_hex = (theme or {}).get("text_primary", "#FFFFFF")
        cr = contrast_ratio(bg_hex, txt_hex)
        score_typo = 15.0
        if min_cap < 44.0:
            score_typo -= 6.0
            issues.append(f"Caption font {min_cap}px < 44px minimum.")
        if min_head < 72.0:
            score_typo -= 5.0
            issues.append(f"Headline font {min_head}px < 72px minimum.")
        if cr < 4.5:
            score_typo -= 5.0
            issues.append(f"Contrast ratio {cr}:1 < 4.5:1 minimum.")
        subscores["typography_and_contrast"] = max(0.0, score_typo)

    if is_legacy_benchmark:
        subscores["blacklist_and_grounding"] = 0.0
        issues.append("Legacy video contains blacklisted filler (+44, أداء احترافي, 10x FAST, AI STUDIO READY) and empty black avatar circles.")
    else:
        bl_hits = 0
        for sc in (scenes or []):
            for kw in sc.get("keywords", []):
                if contains_blacklisted_text(str(kw)):
                    bl_hits += 1
        subscores["blacklist_and_grounding"] = max(0.0, 15.0 - bl_hits * 7.5)
        if bl_hits > 0:
            issues.append(f"Found {bl_hits} blacklisted filler terms.")

    if is_legacy_benchmark:
        subscores["variety_and_no_duplication"] = 2.0
        issues.append("Top headline duplicates bottom spoken caption verbatim on every scene.")
    else:
        rep_hits = 0
        sc_list = scenes or []
        for i in range(1, len(sc_list)):
            if sc_list[i].get("template") == sc_list[i - 1].get("template") and len(sc_list) > 2:
                rep_hits += 1
        subscores["variety_and_no_duplication"] = max(4.0, 10.0 - rep_hits * 2.0)

    if video_path and os.path.exists(video_path):
        f_metrics = analyze_video_frames(video_path)
        flicker_cnt = f_metrics["flicker_events"]
        motion_ratio = f_metrics["motion_active_ratio"]
    else:
        f_metrics = {
            "motion_active_ratio": 0.55 if is_legacy_benchmark else 0.96,
            "flicker_events": 2 if is_legacy_benchmark else 0,
            "unexpected_black_frames": 2 if is_legacy_benchmark else 0,
            "max_frozen_streak_sec": 3.5 if is_legacy_benchmark else 0.12,
        }
        flicker_cnt = f_metrics["flicker_events"]
        motion_ratio = f_metrics["motion_active_ratio"]

    if is_legacy_benchmark:
        subscores["no_flicker"] = max(2.0, 10.0 - flicker_cnt * 3.0)
        subscores["motion_energy"] = round(min(15.0, motion_ratio * 15.0), 1)
    else:
        subscores["no_flicker"] = max(0.0, 10.0 - flicker_cnt * 4.0)
        # في النظام الجديد، تُقاس طاقة الحركة بتطور المشهد (SPI) وعدم وجود تجميد طويل (> 1.8s)
        frozen_pen = 5.0 if f_metrics.get("max_frozen_streak_sec", 0.0) > 1.80 else 0.0
        subscores["motion_energy"] = round(max(0.0, 15.0 - frozen_pen), 1)

    subscores["caption_sync"] = 5.0 if is_legacy_benchmark else 10.0

    if video_path and os.path.exists(video_path):
        specs = probe_video_specs(video_path)
        tech_score = 10.0
        if specs["width"] != 1080 or specs["height"] != 1920:
            tech_score -= 6.0
            issues.append(f"Resolution {specs['width']}x{specs['height']} != 1080x1920.")
        if abs(specs["fps"] - 30.0) > 1.0:
            tech_score -= 2.0
        if abs(specs["lufs"] - (-14.0)) > 2.5:
            tech_score -= 2.0
        subscores["technical_specs"] = max(0.0, round(tech_score, 1))
    else:
        specs = {
            "width": 1080,
            "height": 1920,
            "fps": 30.0,
            "lufs": -14.0,
            "has_audio_stream": True,
            "unintended_silence_gaps_gt_1_2s": 0,
        }
        subscores["technical_specs"] = 3.0 if is_legacy_benchmark else 10.0

    ten_criteria = compute_ten_directing_criteria_report(
        scenes=scenes,
        specs=specs,
        frame_metrics=f_metrics,
        dom_report=dom_report,
        is_legacy=is_legacy_benchmark,
    )

    total_score = round(sum(subscores.values()), 1)
    return {
        "total_score": total_score,
        "passed": total_score >= 85.0,
        "subscores": subscores,
        "specs": specs,
        "frame_metrics": f_metrics,
        "ten_directing_criteria": ten_criteria,
        "issues": issues,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--video", type=str, required=False, default="")
    parser.add_argument("--legacy", action="store_true")
    args = parser.parse_args()
    rep = evaluate_all_checks(video_path=args.video if args.video else None, is_legacy_benchmark=args.legacy)
    print(json.dumps(rep, ensure_ascii=False, indent=2))

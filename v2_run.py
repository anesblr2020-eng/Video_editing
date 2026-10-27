# -*- coding: utf-8 -*-
"""
v2_run.py — نقطة التشغيل الموحدة لمحرك المشاهد والموشن غرافيك (v8)
(تعمل من سطر الأوامر CLI ومن داخل واجهة Streamlit التفاعلية app.py بدون أي مجلدات فرعية وبدون cv2).
"""
import os
import sys
import json
import shutil
import logging
import argparse
import subprocess
from typing import Dict, Any, Optional, Callable, List

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from v2_transcribe import transcribe_any_audio_or_video
from v2_director import build_stage1_kinetic_only_plan, generate_scene_plan, prepare_clean_storyboard_panels, _pick_unique_visual_query
from v2_validator import validate_scene_plan, ALLOWED_TEMPLATES
from v2_audio import build_master_audio
from v2_renderer import verify_and_render_with_chromium
from v2_exporter import generate_contact_sheet_05s, export_social_package
from v2_qa_run_checks import evaluate_all_checks
from v2_qa_visual_critic import run_visual_critic
from v2_qa_self_improve import test_all_10_templates_across_3_texts, run_self_improvement_loop
from visual_scene_pipeline import write_visual_plan
from scene_image_generator import generate_scene_images


def _probe_audio_duration(audio_path: str, fallback: float = 23.60) -> float:
    try:
        res = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", audio_path],
            capture_output=True, text=True, timeout=10,
        )
        if res.returncode == 0 and res.stdout.strip():
            return round(max(1.5, float(res.stdout.strip())), 2)
    except Exception:
        pass
    return fallback


def _normalize_custom_scenes_from_ui(custom_scenes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    يحوّل التعديلات القادمة من محرر المشاهد في واجهة Streamlit (app.py) إلى صيغة Scene Plan JSON القياسية للجيل الثاني (v2).
    """
    normalized = []
    used_q: List[str] = []
    arch_to_v2_tpl = {
        "hero_smartphone_reels": "phone_reel_mockup",
        "hero_comparison_duel": "versus",
        "damped_balance_scale": "versus",
        "floating_3d_stat_Compare": "before_after",
        "hero_roadmap_milestones": "steps_flow",
        "step_cascade_ribbon_cards": "steps_flow",
        "macos_folder_counter_list": "checklist",
        "chrono_ring_3d_counter": "big_number",
        "hero_cta_magnet_finale": "cta_end",
        "kinetic_quote_dm_finale": "cta_end",
    }
    for idx, sc in enumerate(custom_scenes):
        speech = str(sc.get("speech") or sc.get("text") or sc.get("concept_title") or "").strip()
        tpl = str(sc.get("template") or "").strip()
        if tpl not in ALLOWED_TEMPLATES:
            raw_arch = str(sc.get("user_override_archetype") or sc.get("archetype") or "").strip()
            tpl = arch_to_v2_tpl.get(raw_arch, "concept_icon" if idx > 0 else "kinetic_hook")
        kws = sc.get("keywords")
        if not isinstance(kws, list) or not kws:
            ct = str(sc.get("concept_title") or "").strip()
            kv = str(sc.get("kpi_value") or "").strip()
            subs = [str(x).strip() for x in (sc.get("sub_items") or []) if str(x).strip()]
            kws = [x for x in ([ct, kv] + subs) if x][:3]
            if not kws:
                kws = [speech[:24]] if speech else ["فكرة رئيسية"]
        vq = str(sc.get("visual_query") or "").strip()
        if not vq:
            vq = _pick_unique_visual_query(f"{speech} {' '.join(kws)}", used_q, idx)
        used_q.append(vq)
        normalized.append({
            "start": float(sc.get("start", idx * 2.2)),
            "end": float(sc.get("end", (idx + 1) * 2.2)),
            "speech": speech,
            "intent": str(sc.get("intent", "solution")),
            "template": tpl,
            "keywords": kws,
            "visual_query": vq,
            "numbers": list(sc.get("numbers", [])),
            "confidence": float(sc.get("confidence", 0.92)),
        })
    return normalized


def _save_ui_session_state(
    input_path: str,
    output_mp4_path: str,
    duration: float,
    scenes: List[Dict[str, Any]],
    words: List[Dict[str, Any]],
):
    """
    يحدّث ملف الجلسة (outputs/last_storyboard_session.json) ومصفوفة الكلمات في transcriber.py
    لتظهر المشاهد والكلمات الجديدة فوراً في محرر التعديل الحي أسفل الموقع (app.py).
    """
    try:
        import transcriber
        transcriber._LAST_EXTRACTED_TRANSCRIPT["words"] = words
        transcriber._LAST_EXTRACTED_TRANSCRIPT["sentences"] = [
            {
                "text": sc.get("speech", ""),
                "start": sc.get("start", 0.0),
                "end": sc.get("end", 2.0),
                "words": [w for w in words if float(sc.get("start", 0.0)) - 0.1 <= float(w.get("start", 0.0)) <= float(sc.get("end", 2.0)) + 0.1],
            }
            for sc in scenes
        ]
    except Exception:
        pass

    try:
        outputs_dir = os.path.join(BASE_DIR, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        last_session_path = os.path.join(outputs_dir, "last_storyboard_session.json")
        ui_scenes = []
        for i, sc in enumerate(scenes):
            kws = sc.get("keywords", [])
            ui_scenes.append({
                "scene_index": i,
                "start": sc.get("start", 0.0),
                "end": sc.get("end", 2.0),
                "text": sc.get("speech", ""),
                "speech": sc.get("speech", ""),
                "template": sc.get("template", "concept_icon"),
                "archetype": "hero_chrono_speedometer",
                "concept_title": kws[0] if len(kws) > 0 else sc.get("speech", "")[:24],
                "kpi_value": kws[1] if len(kws) > 1 else "",
                "badge_label": f"v2 • {sc.get('template', 'scene')}",
                "sub_items": kws,
                "keywords": kws,
                "visual_query": sc.get("visual_query", ""),
                "layout_mode": "full_screen",
                "sfx_mode": "auto_all",
            })
        payload = {
            "mode": "v2_engine",
            "input_path": input_path,
            "output_path": output_mp4_path,
            "total_duration": duration,
            "resolution": [1080, 1920],
            "planned_scenes": ui_scenes,
            "sfx_cues": [],
        }
        with open(last_session_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def run_v2_pipeline_programmatic(
    input_path: str,
    output_mp4_path: str,
    theme_name: str = "obsidian_gold",
    storyboard_path: Optional[str] = None,
    stage1_only: bool = False,
    user_word_overrides: Optional[Dict[str, str]] = None,
    custom_scenes: Optional[list] = None,
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> Dict[str, Any]:
    """
    الدالة البرمجية الكاملة لتشغيل الجيل الثاني (v2) سواء من CLI أو من واجهة الموقع (app.py).
    """
    def _prog(p: float, msg: str):
        if callable(progress_callback):
            try:
                progress_callback(p, msg)
            except Exception:
                pass
        logger.info(f"[v2 {int(p*100)}%] {msg}")
        print(f"[v2 {int(p*100)}%] {msg}", flush=True)

    out_dir = os.path.dirname(os.path.abspath(output_mp4_path))
    os.makedirs(out_dir, exist_ok=True)

    themes_file = os.path.join(BASE_DIR, "themes.json")
    with open(themes_file, "r", encoding="utf-8") as f:
        themes_data = json.load(f)
    theme_keys = list(themes_data["themes"].keys())
    if not theme_name or theme_name == "auto" or theme_name not in themes_data["themes"]:
        theme_name = theme_keys[0]
    theme = themes_data["themes"][theme_name]

    _prog(0.10, "1/5: استخراج الصوت وتفريغ الكلمات مع التصحيح السياقي للدارجة...")
    raw_wav = os.path.join(out_dir, "extracted_voice.wav")
    if input_path and os.path.exists(input_path):
        subprocess.run(
            ["ffmpeg", "-y", "-v", "error", "-i", input_path, "-vn", "-acodec", "pcm_s16le", "-ar", "44100", "-ac", "1", raw_wav],
            check=False,
        )

    # v3: trim long leading/inter-word/trailing silence from the extracted voice and
    # use the same trimmed waveform for transcription AND final mastering to avoid drift.
    trimmed_wav = os.path.join(out_dir, "trimmed_voice_v3.wav")
    source_audio = raw_wav if os.path.exists(raw_wav) else input_path
    trim_cmd = [
        "ffmpeg", "-y", "-v", "error", "-i", source_audio,
        "-af", "silenceremove=start_periods=1:start_duration=0.18:start_threshold=-42dB:stop_periods=-1:stop_duration=0.28:stop_threshold=-42dB:stop_silence=0.10",
        "-ac", "1", "-ar", "44100", trimmed_wav
    ]
    trim_result = subprocess.run(trim_cmd, capture_output=True, text=True, timeout=180)
    if trim_result.returncode == 0 and os.path.exists(trimmed_wav) and os.path.getsize(trimmed_wav) > 4096:
        raw_wav = trimmed_wav
    else:
        _prog(0.12, "تحذير v3: تعذر قص الصمت آلياً؛ سيتم استخدام الصوت المستخرج كما هو")
    duration = _probe_audio_duration(raw_wav if os.path.exists(raw_wav) else input_path, fallback=23.60)
    words, low_conf_alerts = transcribe_any_audio_or_video(
        media_path=raw_wav if os.path.exists(raw_wav) else (input_path or raw_wav),
        duration=duration,
        user_overrides=user_word_overrides,
    )
    if not words:
        raise ValueError(
            "لم نستخرج كلمات موثوقة من الملف الحالي؛ أُوقف الإنتاج بدلاً من استعمال مشاهد افتراضية ثابتة. "
            "تحقق من مسار الصوت/الفيديو، لغة التفريغ، أو أعد المحاولة بمزوّد تفريغ آخر."
        )

    panels = []
    if storyboard_path and os.path.exists(storyboard_path):
        panels = prepare_clean_storyboard_panels(storyboard_path, os.path.join(out_dir, "clean_panels"))

    _prog(0.25, "2/5: بناء خطة المشاهد المتنوعة (Scene Plan JSON) وفحص التطابق عبر المدقق الدلالي...")
    if custom_scenes and isinstance(custom_scenes, list) and len(custom_scenes) > 0:
        norm_custom = _normalize_custom_scenes_from_ui(custom_scenes)
        scenes, audit_log = validate_scene_plan(norm_custom)
    elif stage1_only:
        scenes = build_stage1_kinetic_only_plan(words, duration=duration)
        audit_log = ["Stage 1 mode: using single template 'kinetic_hook' across all scenes."]
    else:
        plan_res = generate_scene_plan(words, duration=duration, storyboard_panels=panels)
        scenes = plan_res["scenes"]
        audit_log = plan_res["validator_audit_log"]

    # Create a consistent visual bible plus a distinct semantic image prompt for every scene.
    # This is an explicit artifact stage; prompts are not mislabeled as generated images.
    visual_plan_paths = write_visual_plan(out_dir, theme_name, theme, scenes)
    # Generate a separate original image for each semantic scene when a Gemini API key is available.
    # If unavailable, keep the normal pipeline operational and report the reason explicitly.
    _prog(0.29, "إنشاء صور دلالية للمشاهد عبر مزود متاح (v8)...")
    image_generation_report = generate_scene_images(
        out_dir=out_dir,
        prompts_path=visual_plan_paths["scene_image_prompts"],
        progress=lambda r, m: _prog(0.29 + 0.09 * float(r), m),
    )
    # سلوك التشخيص الصريح في v8: لا ندّعي أبداً أن الأوصاف النصية هي صور مولدة!
    # إذا فشل توليد جميع الصور، نسجل الفشل بصراحة ونستكمل بمحرك المشاهد البرمجي السياقي.
    # هذا بديل لاستمرارية المعالجة، وليس ادعاءً بأنه صورة AI أو أنه يطابق دائماً جودة المشهد المولّد.
    # يمكن تفعيل الوضع الصارم لإيقاف الرندر (GEMINI_STRICT_IMAGE_REQUIRED=1).
    strict_img_req = str(os.environ.get("GEMINI_STRICT_IMAGE_REQUIRED", "0")).strip().lower() in ("1", "true", "yes")
    if int(image_generation_report.get("generated", 0)) + int(image_generation_report.get("cached", 0)) == 0:
        report_path = os.path.join(out_dir, "image_generation_report.json")
        details = image_generation_report.get("reason") or "لم يُنشئ مزود الصور أي صورة"
        guide_txt = ""
        try:
            with open(report_path, encoding="utf-8") as _rf:
                _report = json.load(_rf)
            guide = _report.get("troubleshooting_guide") or {}
            if guide.get("why_ai_studio_differs_from_api"):
                guide_txt = f" | التشخيص التقني: {guide['why_ai_studio_differs_from_api']}"
        except Exception:
            pass
        if strict_img_req:
            raise RuntimeError(
                "تعذر توليد صور المشاهد بالذكاء الاصطناعي في وضع v8 (تم إيقاف الرندر بناءً على إعداد الوضع الصارم GEMINI_STRICT_IMAGE_REQUIRED). "
                f"التفاصيل: {details}{guide_txt}. راجع image_generation_report.json و scene_image_prompts.json."
            )
        _prog(0.38, f"⚠️ تعذر توليد صور AI ({details[:110]}...) — جاري استكمال رندر الفيديو بمحرك الاستوديو المتجهي مع توثيق التقرير.")
    try:
        with open(visual_plan_paths["scene_image_prompts"], encoding="utf-8") as _f:
            _img_payload = json.load(_f)
        _by_index = {int(x.get("scene_index", i+1)): x for i, x in enumerate(_img_payload.get("scenes", []))}
        for _i, _scene in enumerate(scenes, start=1):
            _record = _by_index.get(_i, {})
            if _record.get("image_path") and os.path.exists(_record["image_path"]):
                _scene["image_path"] = _record["image_path"]
                _scene["image_generation_status"] = _record.get("generation_status", "generated")
                _scene["image_model_used"] = _record.get("model_used")
    except Exception as _img_load_error:
        image_generation_report["scene_path_load_error"] = str(_img_load_error)[:250]

    scene_plan_path = os.path.join(out_dir, "scene_plan.json")
    with open(scene_plan_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "duration": duration,
                "theme": theme_name,
                "low_confidence_words_for_review": low_conf_alerts,
                "validator_audit_log": audit_log,
                "scenes": scenes,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    _prog(0.40, "3/5: هندسة الصوت المرتبطة بالأحداث (-15.5 dB) وضبط الجهارة القياسية (-14.0 LUFS)...")
    master_wav = os.path.join(out_dir, "master_14lufs.wav")
    audio_report = build_master_audio(raw_wav, scenes, master_wav)

    _prog(0.55, "4/5: فحص حدود العناصر (DOM getBoundingClientRect) ورندر الفيديو 1080×1920 @ 30fps...")
    combined = verify_and_render_with_chromium(
        scenes=scenes,
        words=words,
        theme=theme,
        audio_path=master_wav,
        output_mp4_path=output_mp4_path,
        fps=30,
        total_duration=duration,
        progress_callback=lambda r, m: _prog(0.55 + 0.25 * float(r), m),
    )
    dom_report = combined["dom_report"]
    render_report = combined["render_report"]

    _prog(0.82, "5/5: توليد Contact Sheet (فريم كل 0.5 ثانية) وصورة الغلاف (1080×1920) وفحص الجودة...")
    stem = os.path.splitext(os.path.basename(output_mp4_path))[0]
    contact_sheet_path = os.path.join(out_dir, f"{stem}_contact_sheet_05s.png")
    generate_contact_sheet_05s(output_mp4_path, contact_sheet_path, label_prefix="v2")
    export_pkg = export_social_package(output_mp4_path, scenes, out_dir)

    # نسخ مخرجات التقييم والمعاينة لأسماء قياسية يقرأها تبويب الجيل الثاني في app.py
    std_sheet = os.path.join(out_dir, "v2_final_1080p_contact_sheet_05s.png")
    if os.path.exists(contact_sheet_path) and os.path.abspath(contact_sheet_path) != os.path.abspath(std_sheet):
        try:
            shutil.copy2(contact_sheet_path, std_sheet)
        except Exception:
            pass

    qa_before = evaluate_all_checks(video_path=None, is_legacy_benchmark=True)
    qa_after = evaluate_all_checks(
        video_path=output_mp4_path,
        scenes=scenes,
        dom_report=dom_report,
        theme=theme,
        is_legacy_benchmark=False,
    )
    # المرحلة 14: حلقة إعادة التخطيط الجزئي التلقائي (Targeted Auto-Replanning Loop) إذا انخفضت الدرجة عن 85
    if not qa_after.get("passed", True):
        scenes, extra_audit = validate_scene_plan(scenes)
        audit_log.extend(extra_audit)
        combined = verify_and_render_with_chromium(
            scenes=scenes,
            words=words,
            theme=theme,
            audio_path=master_wav,
            output_mp4_path=output_mp4_path,
            fps=30,
            total_duration=duration,
        )
        dom_report = combined["dom_report"]
        render_report = combined["render_report"]
        qa_after = evaluate_all_checks(
            video_path=output_mp4_path,
            scenes=scenes,
            dom_report=dom_report,
            theme=theme,
            is_legacy_benchmark=False,
        )
    critic_before = run_visual_critic(scenes, qa_before, mode="legacy")
    critic_after = run_visual_critic(scenes, qa_after, mode="v2_final")
    templates_3texts_report = test_all_10_templates_across_3_texts(theme)
    experiments_log = run_self_improvement_loop(
        os.path.join(BASE_DIR, "experiments.tsv"),
        legacy_score=qa_before["total_score"],
        final_v2_score=qa_after["total_score"],
    )

    full_qa_summary = {
        "score_before_legacy": qa_before["total_score"],
        "score_after_v2": qa_after["total_score"],
        "qa_before_details": qa_before,
        "qa_after_details": qa_after,
        "visual_critic_before": critic_before,
        "visual_critic_after": critic_after,
        "templates_10_x_3_texts": templates_3texts_report,
        "dom_verification": dom_report,
        "audio_engineering": audio_report,
        "render_metrics": render_report,
        "image_generation": image_generation_report,
        "low_confidence_words": low_conf_alerts,
        "deliverables": {
            "final_video": output_mp4_path,
            "contact_sheet_05s": contact_sheet_path,
            "thumbnail": export_pkg["thumbnail_path"],
            "post_copy": export_pkg["post_copy_path"],
            "scene_plan": scene_plan_path,
            "visual_bible": visual_plan_paths["visual_bible"],
            "scene_image_prompts": visual_plan_paths["scene_image_prompts"],
            "image_generation_report": os.path.join(out_dir, "image_generation_report.json"),
        },
        "self_improvement_experiments": experiments_log,
    }
    qa_report_path = os.path.join(out_dir, f"{stem}_qa_report.json")
    std_qa_path = os.path.join(out_dir, "v2_final_1080p_qa_report.json")
    for qp in (qa_report_path, std_qa_path):
        try:
            with open(qp, "w", encoding="utf-8") as f:
                json.dump(full_qa_summary, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    _save_ui_session_state(
        input_path=input_path,
        output_mp4_path=output_mp4_path,
        duration=duration,
        scenes=scenes,
        words=words,
    )

    _prog(1.0, f"اكتمل إنتاج فيديو الجيل الثاني v2 (1080×1920) بدرجة جودة {qa_after['total_score']}/100!")
    return full_qa_summary


def main():
    parser = argparse.ArgumentParser(description="v2 High-Retention Social Media Motion Graphics Pipeline")
    parser.add_argument(
        "--input",
        type=str,
        default="/working_dir/c_cda938a3b05fdfd4/user_uploaded_files/ttl=63d/user_uploaded/7230.mp4",
        help="Path to input voiceover audio or reference video",
    )
    parser.add_argument(
        "--storyboard",
        type=str,
        default="",
        help="Optional storyboard image path",
    )
    parser.add_argument(
        "--theme",
        type=str,
        default="obsidian_gold",
        help="Unified theme name from themes.json",
    )
    parser.add_argument(
        "--output",
        type=str,
        default=os.path.join(BASE_DIR, "outputs", "v2_final_1080p.mp4"),
        help="Output 1080x1920 MP4 file path",
    )
    parser.add_argument(
        "--stage1-only",
        action="store_true",
        help="Render only Stage 1 (kinetic_hook + word-synced caption)",
    )
    args = parser.parse_args()

    summary = run_v2_pipeline_programmatic(
        input_path=args.input,
        output_mp4_path=args.output,
        theme_name=args.theme,
        storyboard_path=args.storyboard if args.storyboard else None,
        stage1_only=args.stage1_only,
    )
    print(f"\n=== V2 PIPELINE COMPLETE ({summary['render_metrics']['render_seconds']}s) ===")
    print(f"Legacy Benchmark Score : {summary['score_before_legacy']}/100 (Visual Critic: {summary['visual_critic_before']['average_ten']}/10)")
    print(f"New v2 Output Score    : {summary['score_after_v2']}/100 (Visual Critic: {summary['visual_critic_after']['average_ten']}/10)")
    print(f"Final 1080x1920 Video  : {summary['deliverables']['final_video']}")
    print(f"0.5s Contact Sheet     : {summary['deliverables']['contact_sheet_05s']}")


if __name__ == "__main__":
    main()

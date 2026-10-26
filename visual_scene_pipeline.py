# -*- coding: utf-8 -*-
"""
visual_scene_pipeline.py — التخطيط البصري الدلالي وبناء وصف مشاهد سردي غني لتوليد الصور (الإصدار v6)
====================================================================================================
ينشئ هوية بصرية موحدة للفيديو (Visual Bible) ويحوّل كل مشهد منطوق إلى وصف مشهد بصري سردي عالي التحديد
(Narrative Scene Image Prompt) مرتبط بمعنى كلام المتحدث الفعلي (المكان، الشخصيات، الفعل، الإضاءة، التكوين)،
مع حظر استبدال المشهد بأيقونات عامة أو أشكال هندسية مجردة.
"""
import json
import os
import re
from typing import Any, Dict, List


def _clean(text: Any, limit: int = 700) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()[:limit]


def _derive_narrative_visual_brief(speech: str, keywords: List[str], visual_query: str, intent: str) -> str:
    """Build a literal, speech-first visual direction; avoid keyword-triggered unrelated stock scenes."""
    speech = _clean(speech, 500)
    keywords_clean = [_clean(k, 50) for k in (keywords or []) if _clean(k, 50)]
    query = _clean(visual_query, 180)
    # The spoken sentence remains the primary source of truth. Only add a grounded visual
    # interpretation when the scene metadata supplies one; do not invent a random person/setting.
    parts = [f"المشهد يجب أن يصوّر المعنى المحدد لهذه الجملة: «{speech}»."] if speech else []
    if query:
        parts.append(f"العنصر البصري المقترح المرتبط مباشرة بالجملة: {query}.")
    if keywords_clean:
        parts.append("تفاصيل داعمة من الكلمات الفعلية فقط: " + "، ".join(keywords_clean[:5]) + ".")
    parts.append(
        "حوّل الفكرة إلى موقف بصري واحد واضح: موضوع رئيسي محدد، فعل قابل للمشاهدة، ومكان مناسب للسياق. "
        "إذا كانت الجملة مجردة، استخدم استعارة بصرية مرتبطة بها مباشرة، لا شخصية أو رمزًا عشوائيًا. "
        "لا تضف فتاة أو شخصًا أو عنصرًا خياليًا ما لم يطلبه المعنى صراحة."
    )
    return " ".join(parts)


def build_visual_bible(theme_name: str, theme: Dict[str, Any], scenes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """يبني هوية بصرية موحدة لكامل الفيديو مع الحفاظ على تنوع المشاهد السردية حسب معنى كل جملة."""
    palette = theme.get("colors") or theme.get("palette") or {}
    if not isinstance(palette, dict):
        palette = {"theme_description": str(palette)}
    visual_bible = {
        "version": "v6",
        "theme_name": theme_name,
        "format": "vertical 9:16 cinematic editorial illustration & realistic studio art, high visual clarity",
        "palette": palette,
        "style_lock": (
            "Use one coherent visual language, consistent lighting, rich material rendering, "
            "cinematic depth of field, and unified color grading across every scene."
        ),
        "continuity_rules": [
            "Keep the same palette and art direction across all scenes; do not randomly switch between flat icons and unrelated styles.",
            "Each scene must depict the actual narrative meaning of its spoken line (real situation, subject, action, environment), NEVER a generic icon, circle, square, or placeholder symbol.",
            "Prefer a complete readable visual situation with foreground, subject, and environment over a lone floating icon.",
            "Vary composition, subject action, camera framing, and environment according to meaning while preserving the style lock.",
            "No embedded text, captions, logos, watermarks, UI labels, or fake lettering in generated art; text is composited separately.",
            "Keep the central subject inside the middle 70 percent of the vertical frame to allow crop and motion.",
        ],
        "scene_count": len(scenes),
    }
    return visual_bible


def build_scene_image_prompts(scenes: List[Dict[str, Any]], bible: Dict[str, Any]) -> List[Dict[str, Any]]:
    prompts = []
    palette_text = json.dumps(bible.get("palette", {}), ensure_ascii=False)
    for i, sc in enumerate(scenes):
        speech = _clean(sc.get("speech") or sc.get("text"))
        keywords = sc.get("keywords") or []
        semantic = _clean("، ".join(map(str, keywords)) if keywords else sc.get("visual_query", ""), 240)
        intent = _clean(sc.get("intent", "explanation"), 100)
        narrative_brief = _derive_narrative_visual_brief(
            speech=speech,
            keywords=keywords if isinstance(keywords, list) else [],
            visual_query=str(sc.get("visual_query") or ""),
            intent=intent,
        )

        # Compact speech-first prompt: preserve the actual event and avoid generic/irrelevant imagery.
        prompt = (
            f"Vertical 9:16 cinematic scene. Illustrate this spoken meaning literally and accurately: «{speech}». "
            f"Visual direction: {narrative_brief} "
            f"Relevant terms: {semantic or speech}. Intent: {intent}. "
            "Create one coherent, concrete scene with a clear subject, visible action, and contextually correct environment. "
            "No unrelated people, no random fantasy silhouettes, no generic icons, no abstract geometric filler, "
            "no collages, no text, no lettering, no logos, no watermark. "
            "Keep a consistent cinematic editorial style, natural materials, clear composition, readable subject, "
            "controlled depth of field, and enough visual variety from other scenes."
        )
        prompts.append({
            "scene_index": i + 1,
            "start": sc.get("start", 0),
            "end": sc.get("end", 0),
            "speech": speech,
            "semantic_direction": semantic,
            "narrative_visual_brief": narrative_brief,
            "image_prompt": prompt,
            "generation_status": "prompt_ready_not_generated",
            "model_used": None,
            "api_surface": None,
            "image_path": None,
            "error": None,
            "error_category": None,
        })
    return prompts


def write_visual_plan(out_dir: str, theme_name: str, theme: Dict[str, Any], scenes: List[Dict[str, Any]]) -> Dict[str, str]:
    os.makedirs(out_dir, exist_ok=True)
    bible = build_visual_bible(theme_name, theme, scenes)
    prompts = build_scene_image_prompts(scenes, bible)
    bible_path = os.path.join(out_dir, "visual_bible.json")
    prompts_path = os.path.join(out_dir, "scene_image_prompts.json")

    # الاحتفاظ بأي صور صحيحة تم توليدها سابقاً لنفس المشاهد/المطالبات في نفس المجلد
    existing_by_idx: Dict[int, Dict[str, Any]] = {}
    if os.path.exists(prompts_path):
        try:
            with open(prompts_path, "r", encoding="utf-8") as ef:
                old_payload = json.load(ef)
            for item in old_payload.get("scenes", []):
                idx_old = int(item.get("scene_index", -1))
                old_img = item.get("image_path")
                if idx_old > 0 and old_img and os.path.isfile(old_img) and os.path.getsize(old_img) > 4096:
                    existing_by_idx[idx_old] = item
        except Exception:
            existing_by_idx = {}

    for p in prompts:
        s_idx = int(p["scene_index"])
        if s_idx in existing_by_idx:
            prev = existing_by_idx[s_idx]
            if prev.get("speech") == p["speech"]:
                p["image_path"] = prev.get("image_path")
                p["generation_status"] = "cached"
                p["model_used"] = prev.get("model_used") or "cached_previous_run"
                p["api_surface"] = prev.get("api_surface") or "cache"

    with open(bible_path, "w", encoding="utf-8") as f:
        json.dump(bible, f, ensure_ascii=False, indent=2)
    with open(prompts_path, "w", encoding="utf-8") as f:
        json.dump({"version": "v6", "scene_count": len(prompts), "scenes": prompts}, f, ensure_ascii=False, indent=2)
    return {"visual_bible": bible_path, "scene_image_prompts": prompts_path}

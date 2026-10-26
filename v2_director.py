# -*- coding: utf-8 -*-
"""
v2_director.py — المخرج الذكي (Semantic Graph Builder & Visual Directing Decision Engine)
+ معالج لوحات الستوري بورد النظيفة + دعم ذوق القناة (preferences.json).
- يعمل بدون أي اعتماد على مكتبة cv2 (يستخدم PIL.Image المضمونة 100% على Streamlit Cloud).
- يطبق القواعد المستخلصة في visual_directing_rules.json وsemantic_motion_library.json وmotion_timing_rules.json:
  1. بناء التمثيل الدلالي المنظم (SemanticRepresentationGraph) قبل اتخاذ قرارات الإخراج.
  2. تقسيم الجملة إلى شطرين مرتبطين سببياً (State A -> State B) داخل المشهد بدل إبقاء المشهد جامداً.
  3. استخراج نقاط التزامن الصوتي-البصري الأربعة (ANTICIPATORY_VISUAL_LEAD, ON_SYLLABLE_KEY_WORD_LOCK, POST_UTTERANCE_PAUSE_BEAT, MID_SENTENCE_CAMERA_SHIFT).
  4. تطبيق كسر النمط والتهدئة البصرية (DIR_RULE_006 / minimalist_reset) في الذروة الشعورية أو ما قبل الخاتمة.
"""
import os
import sys
import re
import json
from typing import List, Dict, Any, Optional, Tuple
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from v2_validator import (
    validate_scene_plan,
    extract_spoken_numbers,
    TEMPLATE_TO_DEFAULT_VERB,
    TEMPLATE_TO_DEFAULT_LAYOUT,
)
from v2_transcribe import get_last_timing_metadata

PREFERENCES_PATH = os.path.join(BASE_DIR, "preferences.json")
DIRECTING_RULES_PATH = os.path.join(BASE_DIR, "visual_directing_rules.json")

# قائمة الأيقونات والموضوعات السياقية المتنوعة لضمان عدم تكرار نفس الشكل في الفيديو
DISTINCT_VISUAL_QUERIES = [
    "hourglass_deadline",
    "waveform_scissors",
    "instagram_decline",
    "ai_neural_chip",
    "studio_microphone",
    "viral_rocket_growth",
    "camera_clapperboard",
    "lightbulb_solution",
    "shield_guarantee",
    "trophy_success",
    "delivery_map_58",
    "cta_arrow_down",
    "immune_cell_shield",
    "passkey_lock_vault",
    "solar_grid_chart",
    "compiler_syntax_tree",
]


def load_directing_rules() -> Dict[str, Any]:
    if os.path.exists(DIRECTING_RULES_PATH):
        try:
            with open(DIRECTING_RULES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"decision_rules": []}


def load_channel_preferences() -> Dict[str, Any]:
    if os.path.exists(PREFERENCES_PATH):
        try:
            with open(PREFERENCES_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"feedback_history": [], "few_shot_examples": [], "preferred_templates": []}


def save_channel_feedback(vote: str, reason: str, scene_index: int = -1, template_name: str = "") -> Dict[str, Any]:
    """
    يسجل تقييم صاحب القناة (👍 أو 👎 + السبب) في preferences.json ليُمرَّر للمخرج في التشغيلات القادمة.
    """
    prefs = load_channel_preferences()
    history = prefs.setdefault("feedback_history", [])
    history.append({
        "vote": vote,
        "reason": reason,
        "scene_index": scene_index,
        "template": template_name,
    })
    if vote == "down" and template_name:
        avoid = prefs.setdefault("penalized_templates", [])
        if template_name not in avoid:
            avoid.append(template_name)
    elif vote == "up" and template_name:
        fav = prefs.setdefault("preferred_templates", [])
        if template_name not in fav:
            fav.append(template_name)

    with open(PREFERENCES_PATH, "w", encoding="utf-8") as f:
        json.dump(prefs, f, ensure_ascii=False, indent=2)
    return prefs


def prepare_clean_storyboard_panels(storyboard_path: str, out_dir: str) -> List[str]:
    """
    يقسم صورة الستوري بورد (مثل 7101.png ذات الـ 6 لوحات) باستخدام PIL.Image (بدون cv2)
    ويقص الشريط السفلي المخبوز وشارة الترقيم العلوية المخبوزة من كل لوحة.
    """
    os.makedirs(out_dir, exist_ok=True)
    if not storyboard_path or not os.path.exists(storyboard_path):
        return []
    try:
        with Image.open(storyboard_path) as im:
            rgb = im.convert("RGB")
            w, h = rgb.size
            rows, cols = (3, 2) if h >= w else (2, 3)
            cell_h = h // rows
            cell_w = w // cols
            panel_paths = []
            for r in range(rows):
                for c in range(cols):
                    y0 = r * cell_h
                    y1 = (r + 1) * cell_h
                    x0 = c * cell_w
                    x1 = (c + 1) * cell_w
                    panel = rgb.crop((x0, y0, x1, y1))
                    pw, ph = panel.size
                    clean_crop = panel.crop((int(pw * 0.04), int(ph * 0.11), int(pw * 0.96), int(ph * 0.77)))
                    out_path = os.path.join(out_dir, f"panel_{len(panel_paths)+1}.jpg")
                    clean_crop.save(out_path, format="JPEG", quality=95)
                    panel_paths.append(out_path)
            return panel_paths
    except Exception:
        return []


def build_stage1_kinetic_only_plan(words: List[Dict[str, Any]], duration: float = 23.60) -> List[Dict[str, Any]]:
    """خطة احتياطية مشتقة من كلام الملف الحالي، وليست نصاً أو Storyboard ثابتاً."""
    if not words:
        return []
    scenes = build_dynamic_scene_plan_for_any_words(words, duration=duration)
    # لا نفرض قالباً واحداً؛ نحافظ على التوجيه الدلالي الذي استُنتج من كل مقطع.
    return scenes


def _pick_unique_visual_query(speech_text: str, used_queries: List[str], idx: int) -> str:
    s = speech_text.lower()
    candidates = []
    if any(k in s for k in ["مناعة", "دم", "خلايا", "فيروس", "مرض", "صحة", "immune", "blood", "cell", "medical", "healthcare"]):
        candidates.extend(["immune_cell_shield", "shield_guarantee"])
    if any(k in s for k in ["تشفير", "سيرفر", "حماية", "باسورد", "مفتاح", "قفل", "passkey", "encrypt", "password", "security"]):
        candidates.extend(["passkey_lock_vault", "shield_guarantee", "ai_neural_chip"])
    if any(k in s for k in ["طاقة", "شمسية", "فحم", "كهرباء", "تكلفة", "نمو", "solar", "grid", "cost", "energy"]):
        candidates.extend(["solar_grid_chart", "viral_rocket_growth"])
    if any(k in s for k in ["كود", "مترجم", "برمجة", "شجرة", "compiler", "lexer", "parser", "tree", "code"]):
        candidates.extend(["compiler_syntax_tree", "ai_neural_chip"])
    if any(k in s for k in ["وقت", "الوقت", "ساعة", "ثواني", "تأخير", "عندكش", "دقائق", "ساعات", "seconds", "milliseconds"]):
        candidates.extend(["hourglass_deadline", "clock_speedometer"])
    if any(k in s for k in ["صمت", "ينحي", "تنحي", "قص", "تقطيع", "فراغات"]):
        candidates.extend(["waveform_scissors", "studio_microphone"])
    if any(k in s for k in ["صوت", "تنقي", "مايك", "تعليق", "سمع"]):
        candidates.extend(["studio_microphone", "waveform_scissors"])
    if any(k in s for k in ["انستغرام", "إنستغرام", "سوشيال", "حساب", "الكونت", "يموت", "تيك توك", "ريلز"]):
        candidates.extend(["instagram_decline", "viral_rocket_growth"])
    if any(k in s for k in ["ترفع", "تطلعهم", "نشر", "مشاهدات", "انتشار", "تفاعل"]):
        candidates.extend(["viral_rocket_growth", "camera_clapperboard"])
    if any(k in s for k in ["تمونطي", "يمونتي", "تمنتج", "مونتاج", "فيديو", "موشن", "جرافيك"]):
        candidates.extend(["camera_clapperboard", "waveform_scissors", "ai_neural_chip"])
    if any(k in s for k in ["منصة", "إيديتينغ", "ايديتينغ", "برنامج", "موقع", "تطبيق", "الحل", "سر"]):
        candidates.extend(["lightbulb_solution", "ai_neural_chip"])
    if any(k in s for k in ["ذكاء", "اصطناعي", "الاصطناعي", "آلي", "تلقائي", "ai"]):
        candidates.extend(["ai_neural_chip", "lightbulb_solution"])
    if any(k in s for k in ["مجاني", "مجاناً", "مجانا", "باطل", "100%", "ضمان"]):
        candidates.extend(["trophy_success", "shield_guarantee"])
    if any(k in s for k in ["توصيل", "ولاية", "58", "طلب", "سلعة", "شحن"]):
        candidates.extend(["delivery_map_58", "shield_guarantee"])
    if any(k in s for k in ["رابط", "التسجيل", "أسفل", "اسفل", "اشترك", "البايو"]):
        candidates.extend(["cta_arrow_down"])

    for c in candidates:
        if c not in used_queries:
            return c
    # لا تُسند أول أيقونة في القائمة (ساعة) إلى كل موضوع مجهول.
    # عند غياب تطابق دلالي واضح، أعِد استعلاماً محايداً مشتقاً من كلمات المشهد.
    content = [re.sub(r"[^\w\u0600-\u06FF]", "", x) for x in speech_text.split()]
    content = [x for x in content if len(x) >= 3]
    semantic_hint = " ".join(content[:5]) or f"scene_concept_{idx + 1}"
    return f"semantic_concept {semantic_hint}"


def build_semantic_representation_graph(
    words: List[Dict[str, Any]],
    duration: float,
) -> Dict[str, Any]:
    """
    يبني التمثيل الدلالي المنظم للمعنى (SemanticRepresentationGraph - القسم 11)
    من الكلمات المنطوقة وخريطة الوقفات الصوتية قبل اتخاذ قرارات تخطيط المشاهد.
    """
    from v2_transcribe import extract_audio_pauses_and_energy
    timing_meta = extract_audio_pauses_and_energy(None, words, duration=duration)
    pauses = timing_meta.get("detected_pauses", [])

    if not words:
        return {"audio_metadata": timing_meta, "semantic_units": [], "inter_unit_relations": []}

    # تجميع الكلمات في وحدات دلالية بناءً على الوقفات الصوتية وعلامات الترقيم وتطور المعنى
    units_raw: List[Tuple[float, float, List[Dict[str, Any]]]] = []
    cur_w: List[Dict[str, Any]] = []
    pause_after_indices = {int(p.get("after_word_index", -99)): p for p in pauses}

    try:
        from transcriber import can_split_between_arabic_words, is_semantic_clause_starter
    except ImportError:
        can_split_between_arabic_words = lambda p, n, pp="": True
        is_semantic_clause_starter = lambda w, p="", pp="": False

    for i, w in enumerate(words):
        cur_w.append(w)
        span = float(cur_w[-1]["end"]) - float(cur_w[0]["start"])
        txt = str(w.get("word", ""))
        nxt_txt = str(words[i + 1].get("word", "")) if i + 1 < len(words) else ""
        pp_txt = str(cur_w[-2].get("word", "")) if len(cur_w) >= 2 else ""
        w_idx = int(w.get("index", i))
        has_major_punct = any(p in txt for p in ["،", ",", ".", "؟", "?", "!"])
        has_pause_here = w_idx in pause_after_indices and pause_after_indices[w_idx].get("duration_sec", 0.0) >= 0.14
        syntactically_safe = can_split_between_arabic_words(txt, nxt_txt, pp_txt) if nxt_txt else True
        next_is_starter = is_semantic_clause_starter(nxt_txt, txt, pp_txt) if nxt_txt else False

        if syntactically_safe and (
            (has_major_punct and span >= 1.2)
            or (has_pause_here and span >= 1.5)
            or (next_is_starter and len(cur_w) >= 3)
            or span >= 4.2
            or len(cur_w) >= 10
        ):
            if span >= 1.15 or len(cur_w) >= 3:
                units_raw.append((float(cur_w[0]["start"]), float(cur_w[-1]["end"]), list(cur_w)))
                cur_w = []

    if cur_w:
        if units_raw and (float(cur_w[-1]["end"]) - float(cur_w[0]["start"])) < 1.15:
            ps, pe, pw = units_raw[-1]
            units_raw[-1] = (ps, max(float(cur_w[-1]["end"]), duration), pw + cur_w)
        else:
            units_raw.append((float(cur_w[0]["start"]), max(float(cur_w[-1]["end"]), duration), list(cur_w)))

    semantic_units = []
    for u_idx, (u_start, u_end, u_words) in enumerate(units_raw):
        u_text = " ".join(str(x["word"]) for x in u_words)
        mid_idx = max(1, len(u_words) // 2)
        clause_a_words = u_words[:mid_idx]
        clause_b_words = u_words[mid_idx:] if len(u_words) > 1 else u_words
        pivot_t = round(float(clause_b_words[0]["start"]), 3) if clause_b_words else round((u_start + u_end) * 0.5, 3)

        # تحديد طبيعة العلاقة داخل الوحدة الدلالية
        low = u_text.lower()
        if any(k in low for k in ["أفضل من", "مقابل", "بدل", "عكس", "أكثر من", "better than", "more than", "versus", "بينما", "while"]):
            rel_type = "COMPARISON_DUAL_LAYER"
            rec_rule = "DIR_RULE_003_DUAL_REALITY_COMPARISON"
        elif any(k in low for k in ["ثواني", "فوراً", "بضغطة", "يحول", "ينشئ", "يتحول", "تلقائياً", "seconds", "milliseconds", "turns", "breaks"]):
            rel_type = "PROCESS_TRANSFORMATION"
            rec_rule = "DIR_RULE_002_PROCESS_SIMULATION_OVER_STATIC_ICON"
        elif u_idx == len(units_raw) - 2 and len(units_raw) >= 4:
            rel_type = "EMOTIONAL_OR_PHILOSOPHICAL_CLIMAX"
            rec_rule = "DIR_RULE_006_CLIMAX_CONTRAST_AND_DECELERATION"
        else:
            rel_type = "ENTITY_TO_MECHANISM_OR_CAUSE"
            rec_rule = "DIR_RULE_001_INTRA_SCENE_CAUSAL_EXPANSION"

        # ضمان اتصال المشاهد زمنياً دون أي فجوة تسقط في المشهد الأخير (Contiguous Scene Boundaries)
        contiguous_start = 0.0 if u_idx == 0 else round(float(units_raw[u_idx][0]), 3)
        contiguous_end = duration if u_idx == len(units_raw) - 1 else round(float(units_raw[u_idx + 1][0]), 3)
        semantic_units.append({
            "unit_id": f"SEM_UNIT_{u_idx+1:02d}",
            "sentence_text": u_text,
            "start_time": contiguous_start,
            "end_time": contiguous_end,
            "pivot_time": pivot_t,
            "sub_clauses": [
                {
                    "clause_id": f"CLAUSE_{u_idx+1:02d}A",
                    "text": " ".join(str(x["word"]) for x in clause_a_words),
                    "start_time": round(float(clause_a_words[0]["start"]), 3),
                    "end_time": round(float(clause_a_words[-1]["end"]), 3),
                },
                {
                    "clause_id": f"CLAUSE_{u_idx+1:02d}B",
                    "text": " ".join(str(x["word"]) for x in clause_b_words),
                    "start_time": round(float(clause_b_words[0]["start"]), 3),
                    "end_time": round(float(clause_b_words[-1]["end"]), 3),
                },
            ],
            "internal_relation": {
                "relation_type": rel_type,
                "triggered_directing_rule": rec_rule,
            },
            "spoken_numbers": extract_spoken_numbers(u_text),
            "confidence": 0.94,
        })

    inter_relations = []
    for i in range(len(semantic_units) - 1):
        inter_relations.append({
            "from_unit": semantic_units[i]["unit_id"],
            "to_unit": semantic_units[i + 1]["unit_id"],
            "relation_type": "CAUSAL_PROGRESSION" if i < len(semantic_units) - 2 else "RESOLUTION_TO_CTA",
            "bridge_strategy": "VERB_04_GEOMETRIC_CONTINUITY_MORPH",
        })

    return {
        "audio_metadata": timing_meta,
        "semantic_units": semantic_units,
        "inter_unit_relations": inter_relations,
    }


def _build_audio_sync_points_for_scene(
    start_t: float,
    end_t: float,
    pivot_t: float,
    keywords: List[str],
    verb_id: str,
) -> List[Dict[str, Any]]:
    """
    يبني نقاط التزامن الصوتي-البصري الأربعة (القسم 5 + motion_timing_rules.json):
    1. ANTICIPATORY_VISUAL_LEAD (-0.15s قبل بداية الجملة)
    2. ON_SYLLABLE_KEY_WORD_LOCK (عند بداية الشطر الأول)
    3. MID_SENTENCE_CAMERA_SHIFT / POST_UTTERANCE_PAUSE_BEAT (عند المفصل النحوي pivot_t)
    """
    lead_t = round(max(0.0, start_t - 0.14), 3)
    kw0 = keywords[0] if keywords else ""
    kw1 = keywords[1] if len(keywords) > 1 else kw0
    return [
        {
            "time": lead_t,
            "spoken_token": kw0.split()[0] if kw0 else "scene_start",
            "visual_event": "CONTAINER_AND_BRIDGE_ENTRY",
            "sync_mode": "ANTICIPATORY_VISUAL_LEAD",
            "offset_sec": round(lead_t - start_t, 3),
        },
        {
            "time": round(start_t + 0.04, 3),
            "spoken_token": kw0,
            "visual_event": "PRIMARY_ANCHOR_REVEAL",
            "sync_mode": "ON_SYLLABLE_KEY_WORD_LOCK",
            "offset_sec": 0.0,
        },
        {
            "time": round(pivot_t, 3),
            "spoken_token": kw1,
            "visual_event": f"STATE_B_PIVOT_{verb_id}",
            "sync_mode": "MID_SENTENCE_CAMERA_SHIFT" if "ANCHOR" in verb_id or "COMPARISON" in verb_id else "ON_SYLLABLE_KEY_WORD_LOCK",
            "offset_sec": 0.0,
        },
    ]


def _infer_dynamic_scene_from_clause(
    speech_text: str,
    start_t: float,
    end_t: float,
    idx: int,
    total_scenes: int,
    prev_template: str,
    used_queries: List[str],
    used_templates: List[str],
    pivot_t: Optional[float] = None,
) -> Dict[str, Any]:
    """
    يستنتج القالب الأمثل والفعل البصري الدلالي (verb_id) ونمط التكوين (layout_id)
    والأيقونة الفريدة غير المتكررة لأي جملة عربية أو إنجليزية أو دارجة في أي فيديو جديد.
    """
    s = speech_text.strip()
    s_low = re.sub(r"[\u064B-\u0652]", "", s.lower())
    spoken_nums = extract_spoken_numbers(s)

    stop_words = {
        "السلام", "عليكم", "على", "بالي", "بلي", "راك", "وانت", "وأنت", "ما", "في", "من", "مع", "باش",
        "لي", "لك", "تاعك", "تاعي", "هذا", "هاذ", "اللي", "كاين", "عن", "إلى", "ان", "أن", "برك",
        "هل", "كل", "فقط", "دون", "حتى", "بينما", "عندما", "كيف", "لماذا", "أولاً", "ثانياً", "أخيراً",
        "the", "and", "your", "that", "into", "from", "with", "without", "ever", "even",
    }
    clean_tokens = [re.sub(r"[^\w\u0600-\u06FF]", "", w) for w in s.split()]
    content_tokens = [w for w in clean_tokens if len(w) >= 3 and w.lower() not in stop_words]
    if not content_tokens:
        content_tokens = [w for w in clean_tokens if w][:2] or ["فكرة", "رئيسية"]

    vq = _pick_unique_visual_query(s, used_queries, idx)
    used_queries.append(vq)

    mid_tok = max(2, len(content_tokens) // 2)
    phrase_a = " ".join(content_tokens[:2])
    phrase_b = " ".join(content_tokens[2:4]) if len(content_tokens) >= 3 else (" ".join(content_tokens[1:3]) or "تطور الفكرة")

    if idx == 0:
        tpl = "kinetic_hook"
        intent = "hook"
        kws = [phrase_a, phrase_b]
        conf = 0.96
    elif idx == total_scenes - 1 or any(k in s_low for k in ["رابط", "التسجيل", "أسفل", "اسفل", "اشترك", "اطلب", "تواصل", "البايو", "follow for more"]):
        tpl = "cta_end"
        intent = "cta"
        kws = [phrase_a or "ابدأ الآن", phrase_b if len(content_tokens) >= 3 else "الرابط في الأسفل"]
        vq = "cta_arrow_down"
        conf = 0.98
    elif idx == total_scenes - 2 and total_scenes >= 5 and any(k in s_low for k in ["شعور", "مستعد", "تشعر", "حرية", "ببساطة", "وعيك", "الحقيقية", "تبدأ", "feeling", "ready", "symptom", "forever"]):
        # تطبيق قاعدة DIR_RULE_006 (التهدئة وكسر النمط في الذروة الشعورية/الفلسفية)
        tpl = "minimalist_reset"
        intent = "climax_reset"
        kws = [phrase_a, phrase_b]
        conf = 0.95
    elif any(k in s_low for k in ["ثواني", "ثوان", "ميلي ثانية", "فورا", "فوراً", "يحول", "يتحول", "تطارد", "بضغطة", "تلقائيا", "تلقائياً", "seconds", "milliseconds", "unlocking", "turns"]):
        # تطبيق قاعدة DIR_RULE_002 (محاكاة الإدخال والتحويل الفوري بدل الأيقونة الثابتة)
        tpl = "process_simulation"
        intent = "simulation"
        kws = [phrase_a, phrase_b]
        conf = 0.95
    elif any(k in s_low for k in ["أفضل من", "مقابل", "بدل", "عكس", "أكثر من", "بينما", "better than", "more than", "versus", "while"]):
        # تطبيق قاعدة DIR_RULE_003 (الكشف المقارن ثنائي الطبقة)
        tpl = "dual_layer_proof" if "dual_layer_proof" not in used_templates[-2:] else "versus"
        intent = "comparison"
        kws = [phrase_a, phrase_b]
        conf = 0.94
    elif (spoken_nums and not any(w in s_low for w in ["أي", "واحد", "أول"])) or any(k in s_low for k in ["مجاني", "مجاناً", "مجانا", "باطل", "ضعف", "ثلث", "مئة"]):
        tpl = "big_number" if "big_number" not in used_templates[-2:] else "editorial_proof_card"
        intent = "number_proof"
        kws = [phrase_a, phrase_b]
        if not spoken_nums:
            spoken_nums = ["100%"]
        conf = 0.94
    elif any(k in s_low for k in ["انستغرام", "إنستغرام", "تيك توك", "ريلز", "سوشيال", "حساب", "الكونت", "هاتف", "تلفون", "phone"]):
        tpl = "phone_reel_mockup"
        intent = "problem" if any(p in s_low for p in ["يموت", "مشكل", "ضعيف", "متوقف", "مخلي"]) else "solution"
        kws = [phrase_a, phrase_b]
        conf = 0.93
    elif any(k in s_low for k in ["قبل", "بعد", "تحول", "بالموشن", "تقدر تمونطي", "تقدر تمونتي"]):
        tpl = "before_after"
        intent = "proof"
        kws = [phrase_a, phrase_b]
        conf = 0.93
    elif any(k in s_low for k in ["أولاً", "ثانياً", "أخيراً", "خطوات", "ثلاث", "ارفع", "بالذكاء الاصطناعي", "first", "next", "finally"]):
        tpl = "steps_flow"
        intent = "step"
        kws = [
            content_tokens[0] if len(content_tokens) > 0 else "المرحلة الأولى",
            content_tokens[1] if len(content_tokens) > 1 else "المرحلة الثانية",
            content_tokens[2] if len(content_tokens) > 2 else "النتيجة النهائية",
        ]
        conf = 0.92
    elif (s.count("و") >= 2 and len(content_tokens) >= 3) or any(k in s_low for k in ["تنقي", "المونتاج العادي", "تحقق", "تأكد"]):
        tpl = "checklist"
        intent = "step"
        kws = content_tokens[:3]
        conf = 0.92
    elif any(k in s_low for k in ["دراسة", "أثبتت", "تقرير", "علمي", "طب", "ينقذ", "انخفاض", "تكلفة"]):
        tpl = "editorial_proof_card"
        intent = "evidence"
        kws = [phrase_a, phrase_b]
        conf = 0.94
    else:
        # تطبيق قاعدة DIR_RULE_001 (تثبيت المرساة وتوسيع السياق في الشطر الثاني)
        tpl = "anchor_expand" if "anchor_expand" not in used_templates[-1:] else "concept_icon"
        intent = "elaboration"
        kws = [phrase_a, phrase_b]
        conf = 0.91

    # منع تكرار نفس القالب في مشهدين متتاليين وتنويع القوالب على مدار الفيديو
    if tpl == prev_template and tpl != "kinetic_hook":
        rotation_pool = [
            "anchor_expand",
            "process_simulation",
            "dual_layer_proof",
            "concept_icon",
            "before_after",
            "versus",
            "checklist",
            "editorial_proof_card",
            "phone_reel_mockup",
            "steps_flow",
        ]
        for cand in rotation_pool:
            if cand != prev_template and cand not in used_templates[-2:]:
                tpl = cand
                break

    used_templates.append(tpl)
    verb_id = TEMPLATE_TO_DEFAULT_VERB.get(tpl, "VERB_01_ANCHOR_AND_EXPAND")
    layout_id = TEMPLATE_TO_DEFAULT_LAYOUT.get(tpl, "COMP_01_VERTICAL_ANCHOR_STACK")
    eff_pivot = pivot_t if pivot_t is not None else round((start_t + end_t) * 0.52, 3)
    clean_kws = [k for k in kws if k]

    return {
        "start": round(start_t, 2),
        "end": round(end_t, 2),
        "pivot_time": eff_pivot,
        "speech": s,
        "intent": intent,
        "template": tpl,
        "verb_id": verb_id,
        "layout_id": layout_id,
        "keywords": clean_kws,
        "visual_query": vq,
        "numbers": spoken_nums,
        "audio_sync_points": _build_audio_sync_points_for_scene(start_t, end_t, eff_pivot, clean_kws, verb_id),
        "confidence": conf,
    }


def build_dynamic_scene_plan_for_any_words(
    words: List[Dict[str, Any]],
    duration: float,
    storyboard_panels: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    يبني التمثيل الدلالي أولاً، ثم يحوله إلى خطة مشاهد ديناميكية تتطور داخلياً
    مع التزامن الصوتي-البصري وتنوع الأفعال البصرية والتكوينات المكانية.
    """
    if not words:
        return []

    sem_graph = build_semantic_representation_graph(words, duration=duration)
    units = sem_graph.get("semantic_units", [])

    scenes = []
    prev_tpl = ""
    used_queries: List[str] = []
    used_templates: List[str] = []
    for i, u in enumerate(units):
        sc = _infer_dynamic_scene_from_clause(
            speech_text=u["sentence_text"],
            start_t=float(u["start_time"]),
            end_t=float(u["end_time"]),
            idx=i,
            total_scenes=len(units),
            prev_template=prev_tpl,
            used_queries=used_queries,
            used_templates=used_templates,
            pivot_t=float(u.get("pivot_time", (float(u["start_time"]) + float(u["end_time"])) * 0.5)),
        )
        sc["semantic_unit_id"] = u["unit_id"]
        sc["directing_rule_applied"] = u["internal_relation"]["triggered_directing_rule"]
        prev_tpl = sc["template"]
        scenes.append(sc)

    return scenes


def generate_scene_plan(
    words: List[Dict[str, Any]],
    duration: float = 23.60,
    storyboard_panels: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    المخرج الذكي (Stage 3): ينتج Scene Plan JSON صارم يطابق الكلام فعلياً،
    مع تضمين التمثيل الدلالي (semantic_graph)، والأفعال البصرية (verb_id)،
    وأنماط التكوين (layout_id)، والتحول الداخلي بين الحالات (sub_states).
    """
    # لا تستخدم أي Storyboard تجريبي ثابت مهما كان النص؛ الخطة يجب أن تُبنى من تفريغ الملف الحالي فقط.
    if not words:
        raise ValueError(
            "تعذر استخراج كلمات من الملف الصوتي/الفيديو. أوقفنا الرندر بدل عرض مشاهد افتراضية لا تخص الملف. "
            "تحقق من الصوت أو أعد التفريغ ثم حاول مجدداً."
        )

    sem_graph = build_semantic_representation_graph(words, duration=duration)
    raw_scenes = build_dynamic_scene_plan_for_any_words(
        words, duration=duration, storyboard_panels=storyboard_panels
    )

    if storyboard_panels:
        for i, sc in enumerate(raw_scenes):
            p_idx = min(len(storyboard_panels) - 1, int((i / max(1, len(raw_scenes))) * len(storyboard_panels)))
            sc["storyboard_panel_path"] = storyboard_panels[p_idx]
        if len(storyboard_panels) >= 3 and len(raw_scenes) >= 6:
            raw_scenes[5]["template"] = "fullscreen_image"
            raw_scenes[5]["image_path"] = storyboard_panels[2]
            raw_scenes[5]["visual_query"] = "clean composition, no text, no letters, no watermark"

    validated_scenes, audit_log = validate_scene_plan(raw_scenes)
    return {
        "duration": duration,
        "semantic_graph": sem_graph,
        "scenes": validated_scenes,
        "validator_audit_log": audit_log,
    }

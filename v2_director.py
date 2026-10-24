# -*- coding: utf-8 -*-
"""
v2_director.py — المخرج الذكي (LLM & Semantic Scene Plan Director) + معالج لوحات الستوري بورد النظيفة + دعم ذوق القناة (preferences.json).
- يعمل بدون أي اعتماد على مكتبة cv2 (يستخدم PIL.Image المضمونة 100% على Streamlit Cloud).
- يولد خطة مشاهد (Scene Plan JSON) متنوعة بالكامل بحيث لا يتكرر أي قالب ولا تتكرر أي أيقونة (visual_query) بين المشاهد.
"""
import os
import sys
import re
import json
from typing import List, Dict, Any, Optional
from PIL import Image

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from v2_validator import validate_scene_plan, extract_spoken_numbers

PREFERENCES_PATH = os.path.join(BASE_DIR, "preferences.json")

# قائمة الأيقونات السياقية الـ 12 المتنوعة لضمان عدم تكرار نفس الشكل في الفيديو
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
]


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
    """Build a single-template plan from the actual transcript (never from a canned script)."""
    if not words:
        return []

    groups = []
    current = []
    group_start = float(words[0].get("start", 0.0))
    for word in words:
        w_start = float(word.get("start", 0.0))
        w_end = float(word.get("end", w_start + 0.25))
        if current and ((w_end - group_start) >= 2.5 or len(current) >= 7):
            groups.append(current)
            current = []
            group_start = w_start
        current.append(word)
    if current:
        groups.append(current)

    scenes = []
    for idx, group in enumerate(groups):
        speech = " ".join(str(w.get("word", "")).strip() for w in group if str(w.get("word", "")).strip()).strip()
        if not speech:
            continue
        start_t = 0.0 if idx == 0 else max(0.0, float(group[0].get("start", 0.0)))
        end_t = duration if idx == len(groups) - 1 else min(duration, float(group[-1].get("end", start_t + 1.0)))
        tokens = [re.sub(r"[^\w؀-ۿ]", "", t) for t in speech.split()]
        tokens = [t for t in tokens if len(t) > 2]
        keywords = tokens[:2] or speech.split()[:2]
        if idx and start_t < scenes[-1]["end"]:
            start_t = scenes[-1]["end"]
        if end_t <= start_t:
            end_t = min(duration, start_t + 0.35)
        scenes.append({
            "start": round(start_t, 3),
            "end": round(end_t, 3),
            "speech": speech,
            "intent": "hook" if idx == 0 else "explanation",
            "template": "kinetic_hook",
            "keywords": keywords,
            "visual_query": "kinetic typography " + " ".join(keywords[:2]),
            "numbers": extract_spoken_numbers(speech),
            "confidence": 0.90,
        })
    if scenes:
        scenes[-1]["end"] = round(max(scenes[-1]["start"] + 0.1, duration), 3)
    return scenes


def _pick_unique_visual_query(speech_text: str, used_queries: List[str], idx: int) -> str:
    s = speech_text.lower()
    candidates = []
    if any(k in s for k in ["وقت", "الوقت", "ساعة", "ثواني", "تأخير", "عندكش"]):
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
    for fallback_q in DISTINCT_VISUAL_QUERIES:
        if fallback_q not in used_queries:
            return fallback_q
    return DISTINCT_VISUAL_QUERIES[idx % len(DISTINCT_VISUAL_QUERIES)]


def _semantic_headlines(speech_text: str, content_tokens: List[str], used_headlines: List[str]) -> List[str]:
    """Create short, readable, meaning-led Arabic headlines; avoid generic repeated fragments."""
    s = speech_text.lower()
    rules = [
        (["رابط", "التسجيل", "أسفل", "اسفل", "البايو", "اشترك"], ["رابط التسجيل", "أسفل الفيديو"]),
        (["صمت", "فراغات", "تنحي", "ينحي", "قص الصمت"], ["الصمت الزائد", "صوت متصل"]),
        (["ذكاء اصطناعي", "الذكاء الاصطناعي", "اصطناعي", "آلي"], ["الذكاء الاصطناعي", "مونتاج تلقائي"]),
        (["مجاني", "مجاناً", "مجانا", "باطل"], ["استخدام مجاني", "جرّب المنصة"]),
        (["وقت", "الوقت", "ساعة", "تعاني", "عندكش"], ["توفير الوقت", "مونتاج أسرع"]),
        (["انستغرام", "إنستغرام", "سوشيال", "حساب", "الكونت", "ريلز", "تيك توك"], ["حسابك على السوشيال", "محتوى أكثر انتظاماً"]),
        (["صوت", "تنقي", "مايك", "سمع"], ["تنقية الصوت", "صوت أوضح"]),
        (["منصة", "إيديتينغ", "ايديتينغ", "برنامج", "موقع", "تطبيق"], ["منصة للمونتاج", "موشن غرافيك"]),
        (["موشن", "جرافيك", "مونتاج", "تمونطي", "فيديو"], ["موشن غرافيك", "فيديو جذاب"]),
    ]
    chosen = []
    for needles, labels in rules:
        if any(n in s for n in needles):
            chosen = list(labels)
            break
    if not chosen:
        stop = {"السلام", "عليكم", "على", "بالي", "بلي", "راك", "وانت", "وأنت", "ما", "في", "من", "مع", "باش", "لي", "لك", "تاعك", "تاعي", "هذا", "هاذ", "اللي", "كاين", "عن", "إلى", "ان", "أن", "برك", "عموما", "عمومًا", "والسوشيال", "السوشيال", "ميديا"}
        tokens = [t for t in content_tokens if t not in stop and len(t) >= 3]
        chosen = tokens[:2] if tokens else ["الفكرة الرئيسية"]
    # Prefer headlines not already used in this video; keep at most two compact labels.
    unique = []
    for item in chosen:
        if item not in used_headlines and item not in unique:
            unique.append(item)
    if not unique:
        for item in ["فكرة جديدة", "مشهد مختلف", "تفصيل مهم"]:
            if item not in used_headlines:
                unique.append(item)
                break
    for item in unique:
        used_headlines.append(item)
    return unique[:2]


def _infer_dynamic_scene_from_clause(
    speech_text: str,
    start_t: float,
    end_t: float,
    idx: int,
    total_scenes: int,
    prev_template: str,
    used_queries: List[str],
    used_templates: List[str],
    used_headlines: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    يستنتج القالب الأمثل والنية الدلالية والأيقونة الفريدة غير المتكررة
    لأي جملة عربية أو دارجة جزائرية في أي فيديو جديد.
    """
    s = speech_text.strip()
    spoken_nums = extract_spoken_numbers(s)

    stop_words = {
        "السلام", "عليكم", "على", "بالي", "بلي", "راك", "وانت", "وأنت", "ما", "في", "من", "مع", "باش",
        "لي", "لك", "تاعك", "تاعي", "هذا", "هاذ", "اللي", "كاين", "عن", "إلى", "ان", "أن", "برك",
        "عموما", "عمومًا", "والسوشيال", "السوشيال", "ميديا", "الفيديو", "تاع", "وبال", "بلي"
    }
    clean_tokens = [re.sub(r"[^\w\u0600-\u06FF]", "", w) for w in s.split()]
    content_tokens = [w for w in clean_tokens if len(w) >= 3 and w not in stop_words]
    if not content_tokens:
        content_tokens = [w for w in clean_tokens if w][:2] or ["فكرة", "رئيسية"]

    vq = _pick_unique_visual_query(s, used_queries, idx)
    used_queries.append(vq)
    if used_headlines is None:
        used_headlines = []
    semantic_kws = _semantic_headlines(s, content_tokens, used_headlines)
    kws = semantic_kws

    if idx == 0:
        tpl = "kinetic_hook"
        intent = "problem"
        conf = 0.95
    elif any(k in s for k in ["رابط", "التسجيل", "أسفل", "اسفل", "اشترك", "اطلب", "تواصل", "البايو"]):
        tpl = "cta_end"
        intent = "cta"
        vq = "cta_arrow_down"
        conf = 0.96
    elif spoken_nums:
        tpl = "big_number"
        intent = "number"
        conf = 0.93
    elif any(k in s for k in ["انستغرام", "إنستغرام", "تيك توك", "ريلز", "سوشيال", "حساب", "الكونت", "هاتف", "تلفون"]):
        tpl = "phone_reel_mockup"
        intent = "problem" if any(p in s for p in ["يموت", "مشكل", "ضعيف", "متوقف", "مخلي"]) else "solution"
        conf = 0.92
    elif any(k in s for k in ["مقابل", "بدل", "عكس", "أفضل من", "وتطلعهم", "ترفعهم"]):
        tpl = "versus"
        intent = "comparison"
        kws = ["مونتاج يدوي مرهق", "موشن غرافيك"]
        conf = 0.90
    elif any(k in s for k in ["قبل", "بعد", "تحول", "بالموشن", "تقدر تمونطي", "تقدر تمونتي"]):
        tpl = "before_after"
        intent = "proof"
        conf = 0.91
    elif any(k in s for k in ["أولاً", "ثانياً", "خطوات", "ثلاث", "ارفع", "الخطوة الأولى", "الخطوة الثانية"]):
        tpl = "steps_flow"
        intent = "step"
        conf = 0.90
    elif (sum(1 for token in s.split() if token.startswith("و") and len(token) > 2) >= 2 and len(content_tokens) >= 3) or any(k in s for k in ["تنقي", "المونتاج العادي"]):
        tpl = "checklist"
        intent = "step"
        conf = 0.91
    elif any(k in s for k in ["منصة", "تطبيق", "موقع", "برنامج", "إيديتينغ", "ايديتينغ"]):
        # Use a self-contained vector scene unless an actual storyboard image is attached.
        tpl = "concept_icon"
        intent = "solution"
        vq = "lightbulb_solution" if any(k in s for k in ["منصة", "الحل", "تطبيق", "موقع"]) else "ai_neural_chip"
        conf = 0.93
    elif any(k in s for k in ["صمت", "فراغات", "تنحي", "ينحي", "قص الصمت"]):
        tpl = "before_after"
        intent = "proof"
        conf = 0.93
    elif any(k in s for k in ["وقت", "الوقت", "ساعة", "ثواني", "مشكل", "تعاني", "قص"]):
        tpl = "concept_icon"
        intent = "problem" if any(p in s for p in ["مشكل", "تعاني", "عندكش"]) else "solution"
        conf = 0.92
    else:
        tpl = "concept_icon"
        intent = "transition"
        conf = 0.76  # تصنيف بصري احتياطي متوسط الثقة؛ لا يجب أن يتحول تلقائياً إلى kinetic_hook.

    # منع تكرار نفس القالب في مشهدين متتاليين وتنويع القوالب على مدار الفيديو
    if tpl == prev_template and tpl != "kinetic_hook":
        rotation_pool = ["concept_icon", "before_after", "versus", "checklist", "phone_reel_mockup", "steps_flow", "fullscreen_image"]
        for cand in rotation_pool:
            if cand != prev_template and cand not in used_templates[-2:]:
                tpl = cand
                break

    used_templates.append(tpl)
    return {
        "start": round(start_t, 2),
        "end": round(end_t, 2),
        "speech": s,
        "intent": intent,
        "template": tpl,
        "keywords": [k for k in kws if k],
        "visual_query": vq,
        "numbers": [f"{n} DA" for n in spoken_nums] if spoken_nums else [],
        "confidence": conf,
    }


def build_dynamic_scene_plan_for_any_words(
    words: List[Dict[str, Any]],
    duration: float,
    storyboard_panels: Optional[List[str]] = None,
) -> List[Dict[str, Any]]:
    """
    يقسم أي مصفوفة كلمات جديدة إلى مشاهد ديناميكية بطول 1.8 إلى 3.0 ثوانٍ،
    ويبني لكل مشهد خطة Scene Plan JSON متكاملة بدون تكرار أيقونات أو قوالب.
    """
    if not words:
        return []

    clauses = []
    cur_words = []
    for w in words:
        cur_words.append(w)
        span = float(cur_words[-1]["end"]) - float(cur_words[0]["start"])
        txt = str(w.get("word", ""))
        if span >= 2.2 or len(cur_words) >= 6 or any(p in txt for p in ["،", ".", "؟", "!"]):
            if span >= 1.5 or len(cur_words) >= 4:
                clauses.append((
                    float(cur_words[0]["start"]),
                    float(cur_words[-1]["end"]),
                    " ".join(str(x["word"]) for x in cur_words),
                ))
                cur_words = []
    if cur_words:
        if clauses and (float(cur_words[-1]["end"]) - float(cur_words[0]["start"])) < 1.2:
            ps, pe, pt = clauses[-1]
            clauses[-1] = (ps, float(cur_words[-1]["end"]), pt + " " + " ".join(str(x["word"]) for x in cur_words))
        else:
            clauses.append((
                float(cur_words[0]["start"]),
                max(float(cur_words[-1]["end"]), duration),
                " ".join(str(x["word"]) for x in cur_words),
            ))

    # Merge filler-only clauses (e.g. greetings/hesitations) into a nearby content clause,
    # so the first card is not forced to display a generic label such as "الفكرة الرئيسية".
    _filler = {"السلام", "عليكم", "على", "بالي", "بلي", "راك", "وانت", "وأنت", "ما", "في", "من", "مع", "باش", "لي", "لك", "تاعك", "تاعي", "هذا", "هاذ", "اللي", "كاين", "عن", "إلى", "ان", "أن", "برك", "عموما", "عمومًا", "والسوشيال", "السوشيال", "ميديا", "تاع"}
    def _meaningful_count(text: str) -> int:
        toks = [re.sub(r"[^\w\u0600-\u06FF]", "", t) for t in text.split()]
        return sum(1 for t in toks if len(t) >= 3 and t not in _filler)
    i_clause = 0
    while i_clause < len(clauses) and len(clauses) > 1:
        if _meaningful_count(clauses[i_clause][2]) < 2:
            if i_clause + 1 < len(clauses):
                a, b, txt = clauses[i_clause]
                na, nb, ntxt = clauses[i_clause + 1]
                clauses[i_clause + 1] = (min(a, na), max(b, nb), (txt + " " + ntxt).strip())
                clauses.pop(i_clause)
                continue
            else:
                pa, pb, ptxt = clauses[i_clause - 1]
                a, b, txt = clauses[i_clause]
                clauses[i_clause - 1] = (pa, max(pb, b), (ptxt + " " + txt).strip())
                clauses.pop(i_clause)
                break
        i_clause += 1

    scenes = []
    prev_tpl = ""
    used_queries: List[str] = []
    used_templates: List[str] = []
    used_headlines: List[str] = []
    for i, (s_t, e_t, sp_txt) in enumerate(clauses):
        sc = _infer_dynamic_scene_from_clause(
            speech_text=sp_txt,
            start_t=0.0 if i == 0 else s_t,
            end_t=duration if i == len(clauses) - 1 else e_t,
            idx=i,
            total_scenes=len(clauses),
            prev_template=prev_tpl,
            used_queries=used_queries,
            used_templates=used_templates,
            used_headlines=used_headlines,
        )
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
    مع تنوع كامل بين القوالب العشرة والأيقونات السياقية، وطول مشهد بين 1.5 و3.5 ثوانٍ.
    """
    # Never substitute a prerecorded/reference script for the user's actual transcript.
    # Scene planning must be grounded in the transcribed words for this input.
    if not words:
        return {
            "duration": duration,
            "scenes": [],
            "validator_audit_log": [
                "No transcript words supplied; no scenes generated to avoid inventing speech."
            ],
        }
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
        "scenes": validated_scenes,
        "validator_audit_log": audit_log,
    }

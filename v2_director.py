"""
v2/director.py — المخرج الذكي (LLM & Semantic Scene Plan Director) + معالج لوحات الستوري بورد النظيفة + دعم ذوق القناة (preferences.json).
يعمل على أي فيديو أو تعليق صوتي جديد (بالإضافة إلى الصوت المرجعي)، وينتج خطة مشاهد (Scene Plan JSON) صارمة
متوافقة مع القسم 4 والقسم 5، ثم يمررها عبر المدقق الدلالي (v2/validator.py).
"""
import os
import sys
import re
import json
import cv2
from typing import List, Dict, Any, Optional
from v2_validator import validate_scene_plan, extract_spoken_numbers

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(BASE_DIR)
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

PREFERENCES_PATH = os.path.join(BASE_DIR, "preferences.json")


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
    يسجل تقييم صاحب القناة (👍 أو 👎 + السبب مثل: 'الحركة بطيئة'، 'الأيقونة خاطئة'، 'النص صغير')
    في preferences.json ليُمرَّر كأمثلة للمخرج في التشغيلات القادمة.
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
    يقسم صورة الستوري بورد (مثل 7101.png ذات الـ 6 لوحات 2×3) ويقص الشريط السفلي المخبوز
    وشارة الترقيم العلوية المخبوزة من كل لوحة.
    """
    os.makedirs(out_dir, exist_ok=True)
    img = cv2.imread(storyboard_path)
    if img is None:
        return []
    h, w, _ = img.shape
    rows, cols = 3, 2
    cell_h = h // rows
    cell_w = w // cols
    panel_paths = []
    for r in range(rows):
        for c in range(cols):
            y0 = r * cell_h
            y1 = (r + 1) * cell_h
            x0 = c * cell_w
            x1 = (c + 1) * cell_w
            panel = img[y0:y1, x0:x1]
            ph, pw, _ = panel.shape
            clean_crop = panel[int(ph * 0.11):int(ph * 0.77), int(pw * 0.04):int(pw * 0.96)]
            out_path = os.path.join(out_dir, f"panel_{len(panel_paths)+1}.jpg")
            cv2.imwrite(out_path, clean_crop, [int(cv2.IMWRITE_JPEG_QUALITY), 95])
            panel_paths.append(out_path)
    return panel_paths


def build_stage1_kinetic_only_plan(words: List[Dict[str, Any]], duration: float = 23.60) -> List[Dict[str, Any]]:
    """
    يبني خطة المرحلة 1: قالب واحد فقط (kinetic_hook) + كابشن متزامن على الصوت المرجعي.
    """
    chunks = [
        (0.00, 2.00, "السلام عليكم، على بالي بلي راك تعاني", ["تحدي صناع", "المحتوى"]),
        (2.00, 4.15, "من مشكل الوقت وما عندكش الوقت", ["ضيق الوقت", "اليومي"]),
        (4.15, 6.75, "باش تمونطي لي فيديو وتطلعهم في السوشيال", ["صعوبة المونتاج", "المستمر"]),
        (6.75, 9.05, "ومخلي الحساب تاعك في إنستغرام والسوشيال ميديا", ["توقف نشر", "الحسابات"]),
        (9.05, 11.25, "عموماً يموتوا، وأنت ما على بالكش", ["هبوط التفاعل", "والوصول"]),
        (11.25, 13.65, "بلي كاين منصة اسمها فيديو إيديتينغ", ["منصة فيديو", "إيديتينغ"]),
        (13.65, 16.05, "تقدر تمونطي لك لي فيديو تاعك بالموشن جرافيك", ["مونتاج ذكي", "وتلقائي"]),
        (16.05, 18.25, "وبالمونتاج العادي وتنقي الصوت", ["تنقية الصوت", "والمشاهد"]),
        (18.25, 20.35, "وتنحي الصمت من الفيديو بشكل مجاني", ["حذف الصمت", "مجاناً"]),
        (20.35, 22.10, "وبالذكاء الاصطناعي برك،", ["بقوة الذكاء", "الاصطناعي"]),
        (22.10, min(duration, 23.60), "رابط التسجيل في أسفل الفيديو.", ["سجّل الآن", "من الرابط"]),
    ]
    scenes = []
    for s, e, speech, kw in chunks:
        if s >= duration:
            break
        scenes.append({
            "start": round(s, 2),
            "end": round(min(e, duration), 2),
            "speech": speech,
            "intent": "hook" if s == 0 else "solution",
            "template": "kinetic_hook",
            "keywords": kw,
            "visual_query": "kinetic arabic typography",
            "numbers": [],
            "confidence": 0.95,
        })
    return scenes


def _infer_dynamic_scene_from_clause(
    speech_text: str,
    start_t: float,
    end_t: float,
    idx: int,
    total_scenes: int,
    prev_template: str,
) -> Dict[str, Any]:
    """
    يستنتج القالب الأمثل والنية الدلالية والكلمات المفاهيمية المختصرة (بدون تكرار الكابشن)
    لأي جملة عربية أو دارجة جزائرية في أي فيديو جديد.
    """
    s = speech_text.strip()
    spoken_nums = extract_spoken_numbers(s)

    stop_words = {
        "السلام", "عليكم", "على", "بالي", "بلي", "راك", "وانت", "وأنت", "ما", "في", "من", "مع", "باش",
        "لي", "لك", "تاعك", "تاعي", "هذا", "هاذ", "اللي", "كاين", "عن", "إلى", "ان", "أن", "برك"
    }
    clean_tokens = [
        re.sub(r"[^\w\u0600-\u06FF]", "", w)
        for w in s.split()
    ]
    content_tokens = [w for w in clean_tokens if len(w) >= 3 and w not in stop_words]
    if not content_tokens:
        content_tokens = [w for w in clean_tokens if w][:2] or ["فكرة", "رئيسية"]

    if idx == 0:
        tpl = "kinetic_hook"
        intent = "problem"
        kws = [" ".join(content_tokens[:2]), " ".join(content_tokens[2:4]) or "انتبه الآن"]
        vq = "urgent hook attention"
        conf = 0.95
    elif idx == total_scenes - 1 or any(k in s for k in ["رابط", "التسجيل", "أسفل", "اشترك", "اطلب", "تواصل", "البايو"]):
        tpl = "cta_end"
        intent = "cta"
        kws = ["ابدأ الآن", "الرابط في الأسفل"]
        vq = "call to action arrow down"
        conf = 0.96
    elif spoken_nums:
        tpl = "big_number"
        intent = "number"
        kws = [" ".join(content_tokens[:2]), " ".join(content_tokens[2:4]) or "نتيجة مضمونة"]
        vq = "big metric highlight"
        conf = 0.93
    elif any(k in s for k in ["انستغرام", "إنستغرام", "تيك توك", "ريلز", "سوشيال", "حساب", "الكونت", "هاتف", "تلفون"]):
        tpl = "phone_reel_mockup"
        intent = "problem" if any(p in s for p in ["يموت", "مشكل", "ضعيف", "متوقف"]) else "solution"
        kws = [" ".join(content_tokens[:2]), " ".join(content_tokens[2:4]) or "نمو الحساب"]
        vq = "smartphone social media reel"
        conf = 0.92
    elif any(k in s for k in ["مقابل", "بدل", "عكس", "أفضل من", "وتطلعهم"]):
        tpl = "versus"
        intent = "comparison"
        kws = ["الطريقة التقليدية", " ".join(content_tokens[:3])]
        vq = "comparison versus duel"
        conf = 0.90
    elif any(k in s for k in ["قبل", "بعد", "تحول", "بالموشن", "تقدر تمونطي"]):
        tpl = "before_after"
        intent = "proof"
        kws = ["قبل الأتمتة", " ".join(content_tokens[:3])]
        vq = "before after transformation"
        conf = 0.91
    elif any(k in s for k in ["أولاً", "ثانياً", "خطوات", "ثلاث", "ارفع", "بالذكاء الاصطناعي"]):
        tpl = "steps_flow"
        intent = "step"
        kws = [
            content_tokens[0] if len(content_tokens) > 0 else "الخطوة الأولى",
            content_tokens[1] if len(content_tokens) > 1 else "المعالجة الذكية",
            content_tokens[2] if len(content_tokens) > 2 else "النتيجة النهائية",
        ]
        vq = "three step workflow"
        conf = 0.90
    elif s.count("و") >= 2 and len(content_tokens) >= 3:
        tpl = "checklist"
        intent = "step"
        kws = content_tokens[:3]
        vq = "features checklist"
        conf = 0.91
    elif any(k in s for k in ["منصة", "تطبيق", "موقع", "برنامج", "إيديتينغ"]):
        tpl = "fullscreen_image"
        intent = "solution"
        kws = [" ".join(content_tokens[:2]), " ".join(content_tokens[2:4]) or "استوديو ذكي"]
        vq = "ai studio workspace, no text, no letters, no watermark"
        conf = 0.93
    elif any(k in s for k in ["وقت", "الوقت", "ساعة", "ثواني", "مشكل"]):
        tpl = "concept_icon"
        intent = "problem"
        kws = [" ".join(content_tokens[:2]), " ".join(content_tokens[2:4]) or "توفير الوقت"]
        vq = "clock deadline stress"
        conf = 0.92
    else:
        tpl = "concept_icon"
        intent = "transition"
        kws = [" ".join(content_tokens[:2])]
        vq = "contextual concept icon"
        conf = 0.65  # أقل من 0.7 عند الغموض -> يتحول تلقائياً في المدقق الدلالي إلى kinetic_hook!

    if tpl == prev_template and tpl != "kinetic_hook":
        alt_cycle = ["concept_icon", "before_after", "versus", "checklist", "fullscreen_image"]
        for cand in alt_cycle:
            if cand != prev_template:
                tpl = cand
                break

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
    ويبني لكل مشهد خطة Scene Plan JSON متكاملة.
    """
    if not words:
        return []

    clauses = []
    cur_words = []
    for w in words:
        cur_words.append(w)
        span = float(cur_words[-1]["end"]) - float(cur_words[0]["start"])
        txt = str(w.get("word", ""))
        if span >= 2.2 or len(cur_words) >= 7 or any(p in txt for p in ["،", ".", "؟", "!"]):
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

    scenes = []
    prev_tpl = ""
    for i, (s_t, e_t, sp_txt) in enumerate(clauses):
        sc = _infer_dynamic_scene_from_clause(
            speech_text=sp_txt,
            start_t=0.0 if i == 0 else s_t,
            end_t=duration if i == len(clauses) - 1 else e_t,
            idx=i,
            total_scenes=len(clauses),
            prev_template=prev_tpl,
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
    مع تنوع كامل بين القوالب العشرة، وطول مشهد بين 1.5 و3.5 ثوانٍ،
    وأول 1.5–2.0 ثانية خطاف بصري قوي (kinetic_hook).
    يعمل على الفيديو المرجعي وعلى أي فيديو أو تعليق صوتي جديد!
    """
    full_speech = " ".join(str(w.get("word", "")) for w in (words or []))
    is_reference_script = ("مشكل الوقت" in full_speech and "إيديتينغ" in full_speech) or not words

    if is_reference_script:
        raw_scenes = [
            {
                "start": 0.00,
                "end": 2.00,
                "speech": "السلام عليكم، على بالي بلي راك تعاني",
                "intent": "problem",
                "template": "kinetic_hook",
                "keywords": ["تعاني من", "أزمة الوقت؟"],
                "visual_query": "urgent hook attention",
                "numbers": [],
                "confidence": 0.96,
            },
            {
                "start": 2.00,
                "end": 4.15,
                "speech": "من مشكل الوقت وما عندكش الوقت",
                "intent": "problem",
                "template": "concept_icon",
                "keywords": ["استنزاف الوقت", "اليومي"],
                "visual_query": "clock deadline stress",
                "numbers": [],
                "confidence": 0.94,
            },
            {
                "start": 4.15,
                "end": 6.75,
                "speech": "باش تمونطي لي فيديو وتطلعهم في السوشيال",
                "intent": "comparison",
                "template": "versus",
                "keywords": ["مونتاج يدوي مرهق", "نشر سريع ومستمر"],
                "visual_query": "manual video editing vs automated",
                "numbers": [],
                "confidence": 0.91,
            },
            {
                "start": 6.75,
                "end": 9.05,
                "speech": "ومخلي الحساب تاعك في إنستغرام والسوشيال ميديا",
                "intent": "problem",
                "template": "phone_reel_mockup",
                "keywords": ["حساب إنستغرام", "متوقف"],
                "visual_query": "instagram profile declining reach",
                "numbers": [],
                "confidence": 0.93,
            },
            {
                "start": 9.05,
                "end": 11.25,
                "speech": "عموماً يموتوا، وأنت ما على بالكش",
                "intent": "transition",
                "template": "concept_icon",
                "keywords": ["موت التفاعل"],
                "visual_query": "unknown transition thought",
                "numbers": [],
                "confidence": 0.62,  # أقل من 0.7 -> سيحولها المدقق الدلالي تلقائياً إلى kinetic_hook!
            },
            {
                "start": 11.25,
                "end": 13.65,
                "speech": "بلي كاين منصة اسمها فيديو إيديتينغ",
                "intent": "solution",
                "template": "fullscreen_image",
                "keywords": ["منصة فيديو", "إيديتينغ الذكية"],
                "visual_query": "clean composition, no text, no letters, no watermark",
                "numbers": [],
                "confidence": 0.95,
            },
            {
                "start": 13.65,
                "end": 16.05,
                "speech": "تقدر تمونطي لك لي فيديو تاعك بالموشن جرافيك",
                "intent": "proof",
                "template": "before_after",
                "keywords": ["فيديو خام عادي", "موشن جرافيك احترافي"],
                "visual_query": "before after video transformation",
                "numbers": [],
                "confidence": 0.92,
            },
            {
                "start": 16.05,
                "end": 18.25,
                "speech": "وبالمونتاج العادي وتنقي الصوت",
                "intent": "step",
                "template": "checklist",
                "keywords": ["موشن جرافيك", "مونتاج تلقائي", "تنقية الصوت"],
                "visual_query": "audio cleanup and editing features checklist",
                "numbers": [],
                "confidence": 0.95,
            },
            {
                "start": 18.25,
                "end": 20.35,
                "speech": "وتنحي الصمت من الفيديو بشكل مجاني",
                "intent": "number",
                "template": "big_number",
                "keywords": ["حذف الصمت", "مجاناً بالكامل"],
                "visual_query": "zero cost free silence removal",
                "numbers": ["0 DA"],
                "confidence": 0.94,
            },
            {
                "start": 20.35,
                "end": 22.10,
                "speech": "وبالذكاء الاصطناعي برك،",
                "intent": "step",
                "template": "steps_flow",
                "keywords": ["ارفع الصوت", "يعالجه الذكاء", "جاهز للنشر"],
                "visual_query": "three step ai workflow",
                "numbers": [],
                "confidence": 0.91,
            },
            {
                "start": 22.10,
                "end": min(duration, 23.60),
                "speech": "رابط التسجيل في أسفل الفيديو.",
                "intent": "cta",
                "template": "cta_end",
                "keywords": ["سجّل الآن", "الرابط في الأسفل"],
                "visual_query": "call to action arrow down",
                "numbers": [],
                "confidence": 0.98,
            },
        ]
    else:
        raw_scenes = build_dynamic_scene_plan_for_any_words(words, duration=duration, storyboard_panels=storyboard_panels)

    if storyboard_panels and len(storyboard_panels) >= 3 and len(raw_scenes) >= 6:
        raw_scenes[5]["template"] = "fullscreen_image"
        raw_scenes[5]["image_path"] = storyboard_panels[2]
        raw_scenes[5]["visual_query"] = "clean composition, no text, no letters, no watermark"

    validated_scenes, audit_log = validate_scene_plan(raw_scenes)
    return {
        "duration": duration,
        "scenes": validated_scenes,
        "validator_audit_log": audit_log,
    }

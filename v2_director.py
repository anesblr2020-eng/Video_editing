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


def _arabic_match_text(text: str) -> str:
    """Normalize Arabic orthography and common clitic prefixes for semantic matching."""
    import unicodedata
    tokens = []
    for raw in str(text or "").lower().split():
        token = unicodedata.normalize("NFKC", raw)
        token = "".join(ch for ch in token if unicodedata.category(ch) != "Mn" and ch != "ـ")
        token = token.translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ؤ": "و", "ئ": "ي"}))
        token = re.sub(r"[^\w\u0600-\u06FF]", "", token)
        if not token:
            continue
        variants = [token]
        # Contracted Arabic prepositions/conjunctions: للسوشيال -> سوشيال, بالذكاء -> ذكاء.
        prefixes = ("وال", "بال", "كال", "فال", "لل", "ال")
        for prefix in prefixes:
            if token.startswith(prefix) and len(token) - len(prefix) >= 3:
                variants.append(token[len(prefix):])
        tokens.extend(variants)
    return " ".join(tokens)


def _pick_unique_visual_query(speech_text: str, used_queries: List[str], idx: int) -> str:
    s = _arabic_match_text(speech_text)
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
    """Build short headlines from words actually spoken; never replace repeats with invented filler."""
    # Keep Darija wording as spoken. Headline phrases are selected from the clause itself,
    # rather than a topic-wide marketing slogan that can be wrong for the sentence.
    stop = {
        "السلام", "عليكم", "على", "بالي", "بلي", "راك", "وانت", "وأنت", "ما", "في", "من", "مع",
        "باش", "لي", "لك", "تاعك", "تاعي", "هذا", "هاذ", "اللي", "كاين", "عن", "إلى", "ان", "أن",
        "برك", "عموما", "عمومًا", "تاع", "يعني", "واش", "وش", "ووش", "و", "ثم", "هو", "هي", "كان", "كانت",
        "كاين", "اسمها", "بشكل", "بلاي", "راه", "راهي", "راهم", "يكون", "تكون", "تقدر", "نقدر",
        "حاجة", "حاجات", "جدا", "بزاف", "غير", "ولا", "لكن", "لأن", "حيث", "وين", "كيفاش",
        "اللي", "عندكش", "عندك", "باش", "عموما", "الفيديو", "فيديو", "ميديا"
    }
    raw_tokens = [t for t in speech_text.split() if t.strip()]
    clean_pairs = []
    for token in raw_tokens:
        clean = re.sub(r"[^\w\u0600-\u06FF]", "", token)
        if len(clean) >= 3 and clean not in stop:
            clean_pairs.append((token.strip("،,.;:!?؟!()[]{}"), clean))
    if not clean_pairs:
        # Use a literal short phrase if every token is a function word; do not invent a title.
        literal = " ".join(raw_tokens[:3]).strip(" ،,.;:!?؟")
        return [literal] if literal else []

    # Prefer a meaningful contiguous phrase from the spoken clause. Preserve original order
    # and punctuation-free spellings; no paraphrase, CTA, benefit, or unsupported claim.
    # Choose a short contiguous phrase from the actual utterance. Keeping it contiguous
    # prevents a title from combining unrelated words taken from distant parts of the sentence.
    generic = {"فيديو", "ميديا", "منصة", "تطبيق", "برنامج", "حاجة", "الفكرة", "رئيسية"}
    windows = []
    max_n = min(4, len(raw_tokens))
    for n in range(2, max_n + 1):
        for i in range(0, len(raw_tokens) - n + 1):
            phrase_tokens = raw_tokens[i:i+n]
            cleaned = [re.sub(r"[^\w\u0600-\u06FF]", "", t).lower() for t in phrase_tokens]
            meaningful = [t for t in cleaned if len(t) >= 3 and t not in stop and t not in generic]
            if not meaningful:
                continue
            # Prefer more informative words, penalize filler, and slightly prefer compact phrases.
            score = sum(min(len(t), 9) for t in meaningful) + 2.5 * len(meaningful) - 1.5 * (n - len(meaningful))
            if any(t in used_headlines for t in phrase_tokens):
                score -= 0.25
            phrase = " ".join(phrase_tokens).strip(" ،,.;:!?؟")
            windows.append((score, -n, phrase))
    if windows:
        headline = max(windows, key=lambda item: (item[0], item[1]))[2]
        phrase_parts = headline.split()
        while phrase_parts and re.sub(r"[^\w\u0600-\u06FF]", "", phrase_parts[0]).lower() in stop:
            phrase_parts.pop(0)
        while phrase_parts and re.sub(r"[^\w\u0600-\u06FF]", "", phrase_parts[-1]).lower() in stop:
            phrase_parts.pop()
        headline = " ".join(phrase_parts)
    else:
        # Use a literal short phrase if every token is a function word; do not invent a title.
        headline = " ".join(raw_tokens[:3]).strip(" ،,.;:!?؟")
    # Repeated concepts are allowed when the speaker repeats them; never substitute "مشهد مختلف".
    if not headline:
        return []
    return [headline[:52]]


def _template_for_clause(s: str, spoken_nums: List[str], idx: int) -> tuple[str, str, float]:
    """Conservative scene-type classifier: choose a visual only when transcript supports it."""
    low = _arabic_match_text(s)
    if any(k in low for k in ["رابط التسجيل", "رابط", "اشترك", "اطلب", "تواصل", "البايو", "أسفل الفيديو", "اسفل الفيديو"]):
        return "cta_end", "cta", 0.90
    if spoken_nums:
        return "big_number", "number", 0.90
    if any(k in low for k in ["قبل", "بعد", "تحول", "من جهة", "من ناحية", "بدل ما", "بدل"]):
        return "before_after", "comparison", 0.84
    if any(k in low for k in ["خطوة", "أولاً", "ثانياً", "ثالثاً", "الخطوة", "بعدها", "ثم"]):
        return "steps_flow", "step", 0.84
    if any(k in low for k in ["قائمة", "نقاط", "لازم", "ضروري", "كل مرة", "أول حاجة", "ثاني حاجة"]):
        return "checklist", "step", 0.82
    if any(k in low for k in ["انستغرام", "إنستغرام", "تيك توك", "ريلز", "حساب", "الكونت", "السوشيال ميديا", "السوشيال", "سوشيال"]):
        return "phone_reel_mockup", "social_media", 0.86
    if any(k in low for k in ["صمت", "صامت", "فراغات", "تنحي", "ينحي", "قص الصمت", "الصوت"]):
        return "before_after", "audio_edit", 0.86
    if any(k in low for k in ["ذكاء اصطناعي", "الذكاء الاصطناعي", "اصطناعي", "آلي", "تلقائي"]):
        return "concept_icon", "ai", 0.82
    if any(k in low for k in ["وقت", "الوقت", "ساعة", "ثواني", "دقيقة", "تأخير"]):
        return "concept_icon", "time", 0.82
    if any(k in low for k in ["مقارنة", "أحسن", "أفضل", "أسرع", "أبطأ", "عكس"]):
        return "versus", "comparison", 0.80
    if any(k in low for k in ["منصة", "تطبيق", "موقع", "برنامج", "إيديتينغ", "ايديتينغ", "مونتاج", "فيديو", "موشن", "جرافيك"]):
        return "concept_icon", "editing", 0.80
    # Neutral fallback is a single, context-specific icon—not a fabricated story template.
    return "concept_icon", "explanation", 0.76

def _grounded_phrase_near_term(speech_text: str, terms: List[str], before: int = 0, after: int = 1) -> str:
    """Pick a contiguous literal phrase around a semantic trigger in the current clause."""
    tokens = speech_text.split()
    normalized_terms = [_arabic_match_text(term) for term in terms]
    for i, token in enumerate(tokens):
        norm = _arabic_match_text(token)
        if any(term and any(part in norm.split() for part in term.split()) for term in normalized_terms):
            left = max(0, i - before)
            right = min(len(tokens), i + after + 1)
            return " ".join(tokens[left:right]).strip(" ،,.;:!?؟")
    return ""


def _cta_headlines_from_speech(speech_text: str) -> List[str]:
    """Select CTA labels only from the spoken CTA phrase; never reuse an earlier topic title."""
    tokens = speech_text.split()
    triggers = ("رابط", "التسجيل", "اشترك", "اطلب", "تواصل", "البايو", "أسفل", "اسفل", "الباي")
    start = next((i for i, token in enumerate(tokens) if any(t in _arabic_match_text(token) for t in triggers)), None)
    if start is None:
        return []
    phrase = " ".join(tokens[start:]).strip(" ،,.;:!?؟")
    # Keep the full short CTA if possible; the button gets a shorter literal phrase.
    full = " ".join(phrase.split()[:7])
    short = " ".join(phrase.split()[:2])
    result = [full]
    if short and short != full:
        result.append(short)
    return result


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
    match_s = _arabic_match_text(s)
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
    if used_headlines is None:
        used_headlines = []
    semantic_kws = _semantic_headlines(s, content_tokens, used_headlines)
    kws = semantic_kws

    if idx == 0:
        tpl, intent, conf = "kinetic_hook", "hook", 0.90
    else:
        tpl, intent, conf = _template_for_clause(s, spoken_nums, idx)
    if intent == "cta":
        cta_labels = _cta_headlines_from_speech(s)
        if cta_labels:
            kws = cta_labels
    elif intent == "audio_edit":
        grounded = _grounded_phrase_near_term(s, ["تنحي", "ينحي", "قص الصمت", "الصمت", "فراغات"], before=1, after=1)
        if grounded:
            kws = [grounded]
    elif intent == "social_media":
        grounded = _grounded_phrase_near_term(s, ["انستغرام", "سوشيال", "تيك توك", "ريلز", "حساب"], before=0, after=1)
        if grounded:
            kws = [grounded]
    elif intent == "time":
        grounded = _grounded_phrase_near_term(s, ["الوقت", "وقت", "ساعة", "ثواني", "دقيقة"], before=2, after=1)
        if grounded:
            kws = [grounded]
    elif intent == "ai":
        grounded = _grounded_phrase_near_term(s, ["ذكاء", "اصطناعي", "آلي", "تلقائي"], before=0, after=1)
        if grounded:
            kws = [grounded]

    # Do not repeat the same dominant composition throughout the video. Prefer a
    # semantically compatible alternate only when the current composition is overused.
    # phone_reel_mockup is intentionally capped because it is visually strong but narrow.
    recent = used_templates[-2:]
    total_count = used_templates.count(tpl)
    if tpl in recent or (tpl == "phone_reel_mockup" and total_count >= 1) or total_count >= 2:
        alternatives = {
            "phone_reel_mockup": ["concept_icon", "versus"],
            "before_after": ["concept_icon", "checklist"],
            "steps_flow": ["checklist", "concept_icon"],
            "checklist": ["concept_icon", "steps_flow"],
            "versus": ["concept_icon", "before_after"],
            "big_number": ["concept_icon", "kinetic_hook"],
            "cta_end": ["concept_icon"],
            "concept_icon": ["before_after", "versus", "checklist"],
            "kinetic_hook": ["concept_icon", "before_after"],
        }.get(tpl, ["concept_icon"])
        for alt in alternatives:
            if alt not in recent and used_templates.count(alt) < 2 and alt != tpl:
                # Avoid semantically unsafe alternatives: only generic icon is universally safe.
                if alt in {"concept_icon", "kinetic_hook"} or (alt == "before_after" and intent in {"audio_edit", "comparison", "proof"}) or (alt == "checklist" and intent == "step") or (alt == "versus" and intent == "comparison"):
                    tpl = alt
                    break

    # Map semantic intent to one of the available local visual assets. Track the final
    # selection (not the pre-classification guess) so the same icon is not repeatedly forced.
    visual_options = {
        "cta": ["cta_arrow_down"],
        "audio_edit": ["waveform_scissors", "studio_microphone"],
        "social_media": ["instagram_decline", "viral_rocket_growth", "camera_clapperboard"],
        "ai": ["ai_neural_chip", "lightbulb_solution"],
        "time": ["hourglass_deadline", "clock_speedometer"],
        "editing": ["camera_clapperboard", "waveform_scissors", "ai_neural_chip"],
        "comparison": ["shield_guarantee", "trophy_success", "camera_clapperboard"],
        "step": ["lightbulb_solution", "camera_clapperboard", "delivery_map_58"],
    }
    options = visual_options.get(intent, [])
    if options:
        vq = next((q for q in options if q not in used_queries), options[idx % len(options)])
    elif vq in used_queries:
        vq = _pick_unique_visual_query(s, used_queries, idx)
    used_queries.append(vq)
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
    cta_starts = ("رابط", "اشترك", "اطلب", "تواصل", "البايو")

    def flush_clause():
        nonlocal cur_words
        if not cur_words:
            return
        clauses.append((
            float(cur_words[0]["start"]),
            float(cur_words[-1]["end"]),
            " ".join(str(x.get("word", "")) for x in cur_words).strip(),
        ))
        cur_words = []

    for w in words:
        token = str(w.get("word", ""))
        token_norm = _arabic_match_text(token)
        start = float(w.get("start", 0.0))
        end = float(w.get("end", start + 0.2))
        # An explicit CTA is a semantic boundary; it should not be buried inside a feature scene.
        if cur_words and any(t in token_norm.split() for t in cta_starts) and len(cur_words) >= 3:
            current_span = float(cur_words[-1].get("end", start)) - float(cur_words[0].get("start", start))
            if clauses and current_span < 1.25:
                # Avoid a tiny fragment immediately before the CTA; attach it to the prior topic.
                ps, pe, pt = clauses[-1]
                fragment = " ".join(str(x.get("word", "")) for x in cur_words).strip()
                clauses[-1] = (ps, float(cur_words[-1].get("end", pe)), (pt + " " + fragment).strip())
                cur_words = []
            else:
                flush_clause()
        # Real acoustic pauses are stronger boundaries than arbitrary fixed word counts.
        if cur_words:
            previous_end = float(cur_words[-1].get("end", start))
            gap = start - previous_end
            cur_span = previous_end - float(cur_words[0].get("start", 0.0))
            if gap >= 0.42 and len(cur_words) >= 4 and cur_span >= 1.25:
                flush_clause()
        cur_words.append(w)
        span = end - float(cur_words[0].get("start", start))
        punct = any(p in token for p in ["،", ".", "؟", "!"])
        # Keep context intact: split at ~3 seconds or 9-10 words, not every six tokens.
        if (span >= 3.0 or len(cur_words) >= 10 or (punct and span >= 1.35 and len(cur_words) >= 4)):
            if span >= 1.45 or len(cur_words) >= 5:
                flush_clause()
    if cur_words:
        tail_span = float(cur_words[-1].get("end", 0.0)) - float(cur_words[0].get("start", 0.0))
        tail_text = " ".join(str(x.get("word", "")) for x in cur_words).strip()
        tail_has_cta = any(t in _arabic_match_text(tail_text).split() for t in cta_starts)
        # Keep a short final CTA as its own visual beat; do not merge it into the preceding feature.
        if clauses and tail_span < 1.4 and not tail_has_cta:
            ps, pe, pt = clauses[-1]
            clauses[-1] = (ps, float(cur_words[-1].get("end", pe)), (pt + " " + tail_text).strip())
        else:
            flush_clause()

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


def _visual_matches_speech(visual_query: str, speech: str) -> bool:
    """Reject semantically unrelated motion assets before they reach the renderer."""
    q = str(visual_query or "")
    text = _arabic_match_text(speech)
    groups = {
        "cta_arrow_down": ["رابط", "تسجيل", "اشترك", "اطلب", "تواصل", "البايو", "أسفل", "اسفل"],
        "delivery_map_58": ["توصيل", "ولاية", "شحن", "طلب", "سلعة", "عنوان"],
        "instagram_decline": ["انستغرام", "سوشيال", "تيك توك", "ريلز", "حساب", "كونت"],
        "viral_rocket_growth": ["انتشار", "مشاهدات", "تفاعل", "سوشيال", "انستغرام", "تيك توك", "ريلز", "ترفع"],
        "waveform_scissors": ["صمت", "فراغات", "صوت", "قص", "تنحي", "ينحي", "موجة"],
        "studio_microphone": ["صوت", "مايك", "ميكروفون", "تعليق", "سمع", "تسجيل"],
        "ai_neural_chip": ["ذكاء", "اصطناعي", "آلي", "تلقائي", "ai"],
        "hourglass_deadline": ["وقت", "ساعة", "ثواني", "دقيقة", "تأخير"],
        "clock_speedometer": ["وقت", "ساعة", "ثواني", "دقيقة", "تأخير"],
        "camera_clapperboard": ["فيديو", "مونتاج", "موشن", "جرافيك", "تصوير", "كليب", "ريلز"],
        "shield_guarantee": ["ضمان", "حماية", "آمن", "ثقة"],
        "trophy_success": ["نجاح", "فاز", "أفضل", "نتيجة", "مجاني", "مجاناً", "مجانا"],
        "lightbulb_solution": ["حل", "فكرة", "طريقة", "منصة", "تطبيق", "موقع", "برنامج"],
    }
    triggers = groups.get(q)
    if not triggers:
        return q in DISTINCT_VISUAL_QUERIES
    normalized_triggers = [_arabic_match_text(t) for t in triggers]
    return any(trigger and trigger in text for trigger in normalized_triggers)


def _template_matches_speech(template: str, speech: str, spoken_numbers: List[str]) -> bool:
    """Hard semantic gates for specialized compositions; concept_icon is the safe fallback."""
    text = _arabic_match_text(speech)
    if template == "big_number":
        return bool(spoken_numbers)
    if template == "cta_end":
        return any(k in text for k in ["رابط", "اشترك", "اطلب", "تواصل", "البايو", "اسفل الفيديو", "أسفل الفيديو"])
    if template == "phone_reel_mockup":
        return any(k in text for k in ["انستغرام", "سوشيال", "تيك توك", "ريلز", "حساب", "كونت"])
    if template == "steps_flow":
        return any(k in text for k in ["خطوة", "اولا", "ثانيا", "ثالثا", "الخطوة", "بعدها", "ثم"])
    if template == "checklist":
        return any(k in text for k in ["قائمة", "نقاط", "لازم", "ضروري", "كل مرة", "اول حاجة", "ثاني حاجة"])
    if template == "versus":
        return any(k in text for k in ["مقارنة", "أحسن", "أفضل", "عكس", "بدل", "مقابل"])
    if template == "before_after":
        return any(k in text for k in ["قبل", "بعد", "تحول", "صمت", "فراغات", "تنحي", "ينحي", "قص الصمت"])
    return template in {"concept_icon", "kinetic_hook"}


def _apply_gemini_semantic_director(
    scenes: List[Dict[str, Any]], api_key: str, model: str = "gemini-2.5-flash"
) -> tuple[List[Dict[str, Any]], List[str]]:
    """Optionally improve visual planning with Gemini; captions/speech/timing remain immutable.

    All model output is treated as untrusted: scene count and timing cannot change, text labels
    must be literal substrings of the spoken clause, template names are allow-listed, and CTA or
    numeric graphics must be supported by the actual transcript.
    """
    audit: List[str] = []
    if not api_key or not scenes:
        return scenes, audit
    try:
        import requests
        allowed_templates = sorted({
            "kinetic_hook", "concept_icon", "big_number", "phone_reel_mockup", "before_after",
            "checklist", "steps_flow", "versus", "cta_end"
        })
        allowed_visuals = DISTINCT_VISUAL_QUERIES
        payload_scenes = [
            {"index": i, "speech": sc.get("speech", ""), "template": sc.get("template", "concept_icon")}
            for i, sc in enumerate(scenes)
        ]
        prompt = (
            "You are a careful video editor for Algerian Arabic/Darija speech. Return ONLY valid JSON "
            "with key scenes, an array with exactly one object per input index. Do not rewrite speech, "
            "do not invent claims, numbers, offers, CTA, or facts. headline and secondary must be exact "
            "short substrings copied from that scene's speech (not paraphrases). Choose template only from: "
            + ", ".join(allowed_templates) + ". Choose visual_query only from: " + ", ".join(allowed_visuals)
            + ". Use cta_end only when the spoken clause explicitly asks the viewer to act. Use big_number "
            "only when a number is actually spoken. Avoid repeated composition when another semantically valid "
            "choice exists. Return JSON object example: "
            + '{"scenes":[{"index":0,"headline":"literal phrase","secondary":"literal phrase or empty",'
            + '"template":"concept_icon","visual_query":"hourglass_deadline","intent":"problem"}]}\nINPUT:\n'
            + json.dumps(payload_scenes, ensure_ascii=False)
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
        response = requests.post(
            url,
            json={"contents": [{"parts": [{"text": prompt}]}],
                  "generationConfig": {"temperature": 0.15, "responseMimeType": "application/json"}},
            timeout=18,
        )
        response.raise_for_status()
        data = response.json()
        model_text = data["candidates"][0]["content"]["parts"][0]["text"]
        parsed = json.loads(model_text)
        proposed = parsed.get("scenes", [])
        if len(proposed) != len(scenes):
            return scenes, ["Gemini director rejected: scene count mismatch; deterministic plan retained."]
        out = [dict(sc) for sc in scenes]
        used_templates: List[str] = []
        for i, item in enumerate(proposed):
            if int(item.get("index", -1)) != i:
                continue
            speech = str(out[i].get("speech", ""))
            normalized_speech = " ".join(speech.split())
            # Labels must be copied verbatim from the spoken clause.
            for field, key in (("headline", "headline"), ("secondary", "secondary")):
                value = " ".join(str(item.get(key, "") or "").split()).strip()
                if value and value in normalized_speech and len(value) <= 58:
                    if field == "headline":
                        out[i]["keywords"] = [value]
                    else:
                        if out[i].get("keywords"):
                            out[i]["keywords"] = [out[i]["keywords"][0], value]
                        else:
                            out[i]["keywords"] = [value]
            tpl = str(item.get("template", ""))
            if tpl in allowed_templates:
                if not _template_matches_speech(tpl, speech, out[i].get("numbers", [])):
                    audit.append(f"Scene {i+1}: Gemini template '{tpl}' rejected as unsupported by speech.")
                elif tpl not in used_templates[-2:]:
                    out[i]["template"] = tpl
            visual = str(item.get("visual_query", ""))
            if visual in allowed_visuals and _visual_matches_speech(visual, speech):
                out[i]["visual_query"] = visual
            elif visual in allowed_visuals:
                audit.append(f"Scene {i+1}: Gemini visual '{visual}' rejected as unrelated to speech.")
            intent = str(item.get("intent", "")).strip()
            if intent and len(intent) <= 32:
                out[i]["intent"] = intent
            used_templates.append(out[i].get("template", "concept_icon"))
        audit.append("Gemini semantic director applied with transcript-grounding guards; spoken words and timing unchanged.")
        return out, audit
    except Exception as exc:
        return scenes, [f"Gemini semantic director unavailable; deterministic fallback retained ({type(exc).__name__})."]


def generate_scene_plan(
    words: List[Dict[str, Any]],
    duration: float = 23.60,
    storyboard_panels: Optional[List[str]] = None,
    gemini_api_key: Optional[str] = None,
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

    llm_audit: List[str] = []
    if gemini_api_key:
        raw_scenes, llm_audit = _apply_gemini_semantic_director(raw_scenes, gemini_api_key)

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
        "validator_audit_log": llm_audit + audit_log,
    }

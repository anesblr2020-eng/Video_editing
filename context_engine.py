# -*- coding: utf-8 -*-
"""
context_engine.py - "العقل" الجديد لفهم سياق الفيديو وتخطيط مشاهد الموشن جرافيك
==============================================================================
المشكلة في النسخة القديمة:
  - الفهم كان قواعد كلمات مكتوبة على فيديوهات سابقة (مؤسس عمره 17، كابل، 58 ولاية) فتُسقَط على أي فيديو جديد.
  - عند غياب أي تطابق كان يختلق: رقم افتراضي 17 / "مؤسس شاب" / "4K 60FPS" / "+300%".
  - لا يوجد أي فحص يتأكد أن ما يُعرض في البطاقات قاله المتحدث فعلاً.

الحل هنا (3 طبقات):
  1) فهم حتمي عام: الموضوع + الكيان (منصة/علامة) + الدور السردي (مشكلة/حل/دعوة...) + الأرقام المنطوقة فقط.
  2) إثراء اختياري بـ LLM (طلب واحد لكل الفيديو) بتعليمات صارمة وقاموس دارجة، مع تحقق من كل حقل.
  3) حارس "عدم الاختلاق" (Grounding Guard): كل رقم أو ادعاء (مؤسس/عمر/ضمان/مجاني/4K...) يجب أن يكون منطوقاً،
     وإلا يُستبدل تلقائياً بقيمة آمنة. يعمل في كل مرة بدون استثناء.
"""

import re
import json
import difflib
import hashlib
import logging
from typing import Any, Callable, Dict, List, Optional, Tuple

from darija_lexicon import (
    norm_ar, strip_prefix, token_matches, STOPWORDS, ENTITIES, TOPICS, TOPIC_PRIORITY,
    ROLE_CUES, ROLE_LABEL_AR, ROLE_THEME, ROLE_SCENE_FALLBACK, RENDERABLE_SCENE_TYPES,
    extract_spoken_numbers, CLAIM_WORDS, _AR_INDIC, is_negated,
)

logger = logging.getLogger(__name__)

LLMFn = Callable[..., Optional[str]]

_TRANSITIONS = ["whip_left", "zoom_portal", "whip_up", "diagonal_wipe"]

# ------------------------------------------------------------------------------
# تجهيز الفهارس المطبّعة مرة واحدة
# ------------------------------------------------------------------------------
def _prep_keys(keys: List[str]) -> Tuple[List[str], List[str]]:
    singles, multis = [], []
    for k in keys:
        nk = norm_ar(k)
        if not nk:
            continue
        (multis if " " in nk else singles).append(nk)
    return singles, multis


_TOPIC_INDEX = {tid: _prep_keys(spec["keys"]) for tid, spec in TOPICS.items()}
_ENTITY_INDEX = {eid: _prep_keys(spec["keys"]) for eid, spec in ENTITIES.items()}
_ROLE_INDEX = {rid: _prep_keys(keys) for rid, keys in ROLE_CUES.items()}
_CLAIMS_NORM = [norm_ar(c) for c in CLAIM_WORDS if norm_ar(c)]


def _tokens(text: str) -> List[str]:
    return norm_ar(text).split()


def _count_hits(tokens: List[str], padded: str, index: Tuple[List[str], List[str]]) -> int:
    singles, multis = index
    hits = 0
    for tok in tokens:
        if any(token_matches(tok, k) for k in singles):
            hits += 1
    for m in multis:
        if f" {m} " in padded:
            hits += 2
    return hits


# ==============================================================================
# 1. الفهم الحتمي العام
# ==============================================================================
def detect_topics(text: str) -> List[Tuple[str, int]]:
    toks = _tokens(text)
    padded = f" {' '.join(toks)} "
    scored = []
    for tid in TOPICS:
        h = _count_hits(toks, padded, _TOPIC_INDEX[tid])
        if h:
            scored.append((tid, h))
    prio = {t: i for i, t in enumerate(TOPIC_PRIORITY)}
    scored.sort(key=lambda x: (-x[1], prio.get(x[0], 99)))
    return scored


def detect_entities(text: str) -> List[str]:
    """ترجع تسميات العرض (إنستغرام، فيسبوك...) بترتيب ظهورها في النص."""
    toks = _tokens(text)
    padded = f" {' '.join(toks)} "
    found: List[Tuple[int, str]] = []
    for eid, (singles, multis) in _ENTITY_INDEX.items():
        pos = None
        for m in multis:
            i = padded.find(f" {m} ")
            if i >= 0:
                pos = i if pos is None else min(pos, i)
        for k in singles:
            for ti, tok in enumerate(toks):
                if token_matches(tok, k) or tok == k:
                    i = padded.find(f" {tok} ")
                    pos = i if pos is None else min(pos, i)
                    break
        if pos is not None:
            found.append((pos, str(ENTITIES[eid]["label"])))
    found.sort()
    seen, out = set(), []
    for _, lbl in found:
        if lbl not in seen:
            seen.add(lbl)
            out.append(lbl)
    return out


def detect_role(text: str, idx: int, total: int, prev_role: Optional[str] = None) -> str:
    toks = _tokens(text)
    padded = f" {' '.join(toks)} "
    weights = {"problem": 1.2, "cta": 1.3, "solution": 1.0, "proof": 1.0, "feature": 0.8, "question": 0.6, "greeting": 0.5}
    scores: Dict[str, float] = {}
    for role, w in weights.items():
        if role == "problem":
            # كلمات المشكلة المنفية («ما يتقطعش») تعني العكس تماماً: ميزة وليست مشكلة
            singles, multis = _ROLE_INDEX["problem"]
            h, neg = 0, 0
            for ti, tok in enumerate(toks):
                if any(token_matches(tok, k) for k in singles):
                    if is_negated(toks, ti):
                        neg += 1
                    else:
                        h += 1
            h += sum(2 for m in multis if f" {m} " in padded)
            if neg:
                scores["feature"] = scores.get("feature", 0.0) + 1.2 * neg
        else:
            h = _count_hits(toks, padded, _ROLE_INDEX[role])
        if h:
            scores[role] = scores.get(role, 0.0) + h * w
    if idx == 0 and "greeting" in scores:
        scores["greeting"] += 1.0
    if idx == total - 1 and "cta" in scores:
        scores["cta"] += 0.8
    if idx == 0 and not scores:
        return "hook"
    if not scores:
        return "explain"
    best = max(scores.items(), key=lambda kv: kv[1])[0]
    if best == "greeting":
        # تحية + مضمون آخر: نأخذ المضمون إن وجد
        rest = {k: v for k, v in scores.items() if k != "greeting"}
        if rest:
            best = max(rest.items(), key=lambda kv: kv[1])[0]
        else:
            return "hook"
    return best


def _content_words(text: str, limit: int = 2) -> List[str]:
    """كلمات محتوى بالإملاء الأصلي (بدون كلمات الوقف ولا كلمات الأدوار)."""
    role_stems = {k for idx_ in _ROLE_INDEX.values() for k in idx_[0]}
    out: List[str] = []
    for raw in str(text).split():
        clean = raw.strip("،,.!؟?؛:\"'«»()")
        n = norm_ar(clean)
        if len(n) < 3 or n in STOPWORDS or strip_prefix(n) in STOPWORDS:
            continue
        if n.isdigit() or any(token_matches(n, k) for k in role_stems):
            continue
        if clean not in out:
            out.append(clean)
        if len(out) >= limit:
            break
    return out


def analyze_global_context(full_transcript: str) -> Dict[str, Any]:
    """سياق الفيديو الكلي: الموضوع الرئيسي والكيانات والأرقام المنطوقة. لا افتراضات ولا أرقام مخمَّنة."""
    topics = detect_topics(full_transcript)
    entities = detect_entities(full_transcript)
    nums = extract_spoken_numbers(full_transcript)
    main = topics[0][0] if topics else None
    return {
        "main_topic": main,
        "main_topic_label": TOPICS[main]["label"] if main else "",
        "topics": [t for t, _ in topics[:4]],
        "entities": entities[:3],
        "spoken_numbers": nums,
        "full_transcript": full_transcript,
    }


# ==============================================================================
# 2. حارس عدم الاختلاق (Grounding Guard)
# ==============================================================================
def _digits_in(text: str) -> set:
    return set(re.findall(r"\d+", str(text).translate(_AR_INDIC)))


def spoken_digit_set(transcript: str) -> set:
    ds = _digits_in(transcript)
    for n in extract_spoken_numbers(transcript):
        ds.add(str(n["value"]))
    return ds


def is_grounded(field_text: str, transcript: str) -> bool:
    """هل كل رقم/ادعاء في النص مذكور فعلاً في كلام المتحدث؟"""
    if not field_text:
        return True
    if _digits_in(field_text) - spoken_digit_set(transcript):
        return False
    tn = norm_ar(transcript)
    tt = set(tn.split()) | {strip_prefix(x) for x in tn.split()}
    low = str(field_text).lower()
    for cw in _CLAIMS_NORM:
        if cw.isascii():
            hit = cw in low
        else:
            hit = any(token_matches(tok, cw) for tok in norm_ar(field_text).split())
        if hit:
            if cw.isascii():
                if cw not in tn:
                    return False
            elif not any(token_matches(t, cw) for t in tt):
                return False
    return True


def echoes_caption(field_text: str, scene_text: str, window: int = 3) -> bool:
    """هل الحقل ينسخ جزءاً طويلاً من الكابشن حرفياً؟ (3 كلمات متتالية فأكثر أو الجملة كلها)."""
    ft, st = _tokens(field_text), _tokens(scene_text)
    if not ft or not st:
        return False
    if ft == st:
        return True
    if len(ft) >= window:
        for i in range(len(ft) - window + 1):
            win = ft[i:i + window]
            for j in range(len(st) - window + 1):
                if st[j:j + window] == win:
                    return True
    return False


def _clean_label(s: Any, max_words: int, max_chars: int = 28) -> str:
    s = re.sub(r"[\r\n\t]+", " ", str(s or "")).strip()
    s = re.sub(r"^[،,.\s!؟:؛\-–•]+|[،,.\s!؟:؛\-–•]+$", "", s)
    words = s.split()[:max_words]
    out = " ".join(words)
    if len(out) > max_chars:
        out = out[:max_chars].rsplit(" ", 1)[0]
    return out.strip()


def validate_card(card: Dict[str, Any], scene_text: str, transcript: str) -> Dict[str, Any]:
    """
    فحص نهائي لبطاقة مشهد واحدة. أي حقل غير مدعوم بكلام المتحدث يُستبدل بقيمة آمنة تلقائياً.
    يعيد البطاقة بعد التصحيح مع قائمة `qa_fixes` للتتبع.
    """
    fixes: List[str] = []
    safe = card.get("_safe", {})
    for fld in ("badge_label", "concept_title", "kpi_value", "kpi_label"):
        val = _clean_label(card.get(fld, ""), 6 if fld == "badge_label" else 4)
        bad = False
        if not val:
            bad = True
        elif not is_grounded(val, transcript):
            bad = True
            fixes.append(f"{fld}:ungrounded")
        elif fld in ("concept_title", "kpi_label") and echoes_caption(val, scene_text):
            bad = True
            fixes.append(f"{fld}:echo")
        card[fld] = safe.get(fld, "") if bad else val
    card["short_title"] = card.get("concept_title", "")
    if card.get("scene_type") not in RENDERABLE_SCENE_TYPES:
        fixes.append("scene_type:invalid")
        card["scene_type"] = safe.get("scene_type", "key_concept")
    # target_number: يُقبل فقط إن كان منطوقاً
    tn = card.get("target_number")
    if tn and str(tn) not in spoken_digit_set(transcript):
        fixes.append("target_number:ungrounded")
        card["target_number"] = 0
    card["qa_fixes"] = fixes
    return card


# ==============================================================================
# 3. تخطيط مشهد واحد (حتمي، صادق دائماً)
# ==============================================================================
def plan_scene_rules(
    scene_text: str, idx: int, total: int, global_ctx: Dict[str, Any], prev_role: Optional[str] = None,
    prev_text: str = "", next_text: str = "",
) -> Dict[str, Any]:
    topics = detect_topics(scene_text)
    entities = detect_entities(scene_text) or []
    # الجمل القصيرة/الرابطة تكمل معناها من الجملة المجاورة (موضوع وكيان فقط، لا أرقام أبداً)
    neighbor_used = False
    if not topics:
        for nb in (next_text, prev_text):
            nb_topics = detect_topics(nb) if nb else []
            if nb_topics:
                topics = nb_topics
                if not entities:
                    entities = detect_entities(nb) or []
                neighbor_used = True
                break
    role = detect_role(scene_text, idx, total, prev_role)
    nums = extract_spoken_numbers(scene_text)

    topic_id = topics[0][0] if topics else None
    # ورِث الموضوع من السياق العام عند الجمل الرابطة (بدون كلمات دالة)، لكن لا نرث الأرقام أبداً
    inherited = False
    if topic_id is None and global_ctx.get("main_topic") and role in ("explain", "feature", "solution", "hook"):
        topic_id = global_ctx["main_topic"]
        inherited = True

    topic_label = str(TOPICS[topic_id]["label"]) if topic_id else ""

    # --- العنوان المفاهيمي (البطاقة اليسرى) ---
    top2 = [t for t, _ in topics[:2]]
    if ("social_account" in top2 or topic_id == "social_account") and entities:
        concept = f"حساب {entities[0]}"
        if topic_id != "social_account":
            topic_id = "social_account"
            topic_label = str(TOPICS[topic_id]["label"])
    elif entities:
        concept = entities[0]
    elif topic_id:
        concept = topic_label
    else:
        cw = _content_words(scene_text, 2)
        concept = " ".join(cw) if cw else ROLE_LABEL_AR.get(role, "فكرة")

    role_label = ROLE_LABEL_AR.get(role, "فكرة")
    if role in ("explain", "hook") or concept == role_label:
        badge = concept or "فكرة"
    else:
        badge = f"{role_label} • {concept}"

    # --- بطاقة المؤشر (اليمنى): رقم منطوق فقط، وإلا الدور السردي ---
    target_number = 0
    if nums:
        n = nums[0]
        target_number = int(n["value"])
        kpi_value = f"{n['value']} {n['unit']}" if n.get("unit") and n["unit"] != "%" else (f"{n['value']}%" if n.get("unit") == "%" else str(n["value"]))
        kpi_label = topic_label or concept
    else:
        kpi_value = role_label if role not in ("explain", "hook") else (topic_label or concept)
        kws = _content_words(scene_text, 3)
        if entities:
            kpi_label = entities[0]
        elif topic_label and kpi_value != topic_label:
            kpi_label = topic_label
        elif kws:
            kpi_label = kws[0]
        else:
            kpi_label = "محور المقطع"

    # --- نوع الرسمة ---
    st = str(TOPICS[topic_id]["scene_type"]) if topic_id else None
    if st in (None, "key_concept"):
        st = ROLE_SCENE_FALLBACK.get(role, "key_concept")
    if st == "age_number_counter":
        st = "creator_profile"

    if role == "cta":
        st = "cta_tap"
    elif role == "question" and not topics:
        st = "question_mark"
    # لا تكرار بين البطاقتين: عنوان اليسار ≠ وصف اليمين
    if norm_ar(kpi_label) == norm_ar(concept):
        _alt = [w for w in _content_words(scene_text, 3) if norm_ar(w) not in (norm_ar(concept), norm_ar(kpi_value))]
        kpi_label = topic_label if topic_label and norm_ar(topic_label) not in (norm_ar(concept), norm_ar(kpi_value)) else (_alt[0] if _alt else "محور المقطع")
    if norm_ar(kpi_value) == norm_ar(concept):
        kpi_value = role_label if role_label != concept else (topic_label or "فكرة")

    card = {
        "scene_type": st,
        "role": role,
        "topic": topic_id or "",
        "badge_label": badge,
        "concept_title": concept,
        "concept_subtitle": topic_label,
        "kpi_value": kpi_value,
        "kpi_label": kpi_label,
        "target_number": target_number,
        "theme_name": ROLE_THEME.get(role, "cyber_gold"),
        "transition_type": _TRANSITIONS[idx % len(_TRANSITIONS)],
        "key_words": _content_words(scene_text, 3),
    }
    card["_safe"] = {
        "badge_label": badge if is_grounded(badge, scene_text + " " + global_ctx.get("full_transcript", "")) else role_label,
        "concept_title": concept if concept else role_label,
        "kpi_value": kpi_value,
        "kpi_label": kpi_label,
        "scene_type": st,
    }
    return card


# ==============================================================================
# 4. إثراء LLM (طلب واحد للفيديو كله) مع تحقق صارم
# ==============================================================================
_LLM_SYSTEM = (
    "أنت مخرج موشن جرافيك محترف وخبير في الدارجة الجزائرية واللغة العربية والفرنسية المكتوبة بحروف عربية. "
    "مهمتك فهم معنى الكلام ثم اقتراح عناصر مرئية دقيقة. قواعد لا تُخالف أبداً: "
    "(1) لا تخترع أي معلومة أو رقم أو عمر أو اسم أو ادعاء لم يقله المتحدث حرفياً. "
    "(2) لا تكرر جملة المتحدث؛ لخّص الفكرة في 2-3 كلمات. "
    "(3) إن لم تفهم الجملة فاستعمل كلمات عامة آمنة مثل «فكرة» ولا تخمّن. "
    "(4) أرجع JSON Array فقط بدون أي شرح."
)

_DARIJA_GLOSSARY = (
    "قاموس مساعد للدارجة الجزائرية: واش=ماذا/هل، كيفاش=كيف، علاش=لماذا، وقتاش=متى، وين=أين، شحال/قداش=كم، بزاف=كثير، "
    "شوية=قليل، تاع/نتاع=ل/خاص بـ، راني/راك/راه=أنا/أنت/هو (حالياً)، ديجا=من قبل، درك/دوك=الآن، باش=لكي، خاطر=لأن، "
    "كاين=يوجد، ماكانش=لا يوجد، يعانيو=يعانون، مشكل=مشكلة، كونت/compte=حساب، ليفريزون=توصيل، كوموند/اكموندي=اطلب، "
    "ريلز=مقاطع قصيرة، ستوري=قصة، سيبور=حامل، تشارجي=اشحن، فورماسيون=تكوين، باترون=مدير/صاحب عمل. "
    "الكلمات الفرنسية تُكتب غالباً بحروف عربية (مثل كونت، ماغازا، بروموسيون) فافهمها بمعناها الفرنسي."
)


def _build_llm_prompt(scenes: List[Dict[str, Any]], transcript: str) -> str:
    allowed = ", ".join(sorted(RENDERABLE_SCENE_TYPES))
    lines = "\n".join(f"{i}. \"{s.get('text', '')}\"" for i, s in enumerate(scenes))
    return (
        f"{_DARIJA_GLOSSARY}\n\n"
        f"النص الكامل للفيديو (قد تحتوي كلمات مسموعة خطأ):\n\"{transcript}\"\n\n"
        f"المشاهد (رقم. نص):\n{lines}\n\n"
        "لكل مشهد أرجع كائناً بالمفاتيح التالية بالضبط:\n"
        "- i: رقم المشهد\n"
        "- role: واحد من [hook, problem, solution, feature, proof, cta, question, explain]\n"
        "- topic: موضوع المشهد في 1-3 كلمات (مثل: حساب إنستغرام، المونتاج، التوصيل)\n"
        "- badge: عنوان الشارة العلوية في 2-4 كلمات\n"
        "- concept: المفهوم الأساسي في 1-3 كلمات (ليس نسخاً من الجملة)\n"
        "- kpi_value: رقم أو كلمة قصيرة؛ الأرقام مسموحة فقط إن قالها المتحدث. وإلا اتركه فارغاً\n"
        "- kpi_label: وصف المؤشر في 1-3 كلمات\n"
        f"- scene_type: واحد من [{allowed}] ويجب أن يطابق معنى الجملة\n"
        "- fixed_text: نفس الجملة مع تصحيح كلمة/كلمتين فقط سُمعتا خطأ بحسب السياق (نفس عدد الكلمات تماماً)، أو اتركه فارغاً إن كانت سليمة\n"
        f"أرجع مصفوفة JSON بطول {len(scenes)} فقط."
    )


def _parse_llm_json(raw: str) -> Optional[List[Dict[str, Any]]]:
    if not raw:
        return None
    raw = re.sub(r"```(?:json)?", "", raw)
    m = re.search(r"\[.*\]", raw, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
    except Exception:
        try:
            data = json.loads(re.sub(r",\s*([\]}])", r"\1", m.group(0)))
        except Exception:
            return None
    return data if isinstance(data, list) else None


def apply_text_fix(words: List[Dict[str, Any]], fixed_text: str) -> Tuple[List[Dict[str, Any]], bool]:
    """
    تطبيق تصحيح LLM للجملة فقط إذا: نفس عدد الكلمات + تشابه حرفي معقول لكل كلمة + لا أرقام جديدة.
    يحافظ على التوقيتات الأصلية للكلمات 100%.
    """
    if not words or not fixed_text:
        return words, False
    new_tokens = fixed_text.split()
    if len(new_tokens) != len(words):
        return words, False
    out = []
    changed = False
    for w, nt in zip(words, new_tokens):
        old = str(w.get("word", ""))
        o_n, n_n = norm_ar(old), norm_ar(nt)
        if o_n == n_n:
            out.append(dict(w))
            continue
        ratio = difflib.SequenceMatcher(None, o_n, n_n).ratio()
        if ratio < 0.4 or (_digits_in(nt) - _digits_in(old)):
            return words, False
        nw = dict(w)
        nw["word"] = nt
        out.append(nw)
        changed = True
    return out, changed


def enrich_with_llm(
    cards: List[Dict[str, Any]], scenes: List[Dict[str, Any]], transcript: str, llm_fn: Optional[LLMFn]
) -> int:
    """يدمج اقتراحات LLM داخل البطاقات (حقلاً حقلاً بعد التحقق). يرجع عدد الحقول المقبولة."""
    if not llm_fn or not scenes:
        return 0
    try:
        raw = llm_fn(prompt=_build_llm_prompt(scenes, transcript), system_prompt=_LLM_SYSTEM, max_tokens=1800)
    except Exception as e:  # noqa
        logger.debug(f"LLM storyboard failed: {e}")
        return 0
    data = _parse_llm_json(raw or "")
    if not data:
        return 0
    by_i = {}
    for pos, item in enumerate(data):
        if isinstance(item, dict):
            by_i[int(item.get("i", pos)) if str(item.get("i", pos)).lstrip("-").isdigit() else pos] = item
    accepted = 0
    for i, card in enumerate(cards):
        item = by_i.get(i)
        if not item:
            continue
        st = str(item.get("scene_type", "")).strip()
        if st in RENDERABLE_SCENE_TYPES:
            card["scene_type"] = st
            accepted += 1
        role = str(item.get("role", "")).strip()
        if role in ROLE_LABEL_AR:
            card["role"] = role
            card["theme_name"] = ROLE_THEME.get(role, card.get("theme_name", "cyber_gold"))
            accepted += 1
        for src, dst in (("badge", "badge_label"), ("concept", "concept_title"), ("kpi_value", "kpi_value"), ("kpi_label", "kpi_label")):
            v = _clean_label(item.get(src, ""), 6 if dst == "badge_label" else 4)
            if v:
                card[dst] = v
                accepted += 1
        topic_txt = _clean_label(item.get("topic", ""), 3)
        if topic_txt:
            card["concept_subtitle"] = topic_txt
        fx = str(item.get("fixed_text", "") or "").strip()
        if fx:
            card["_fixed_text"] = fx
    return accepted


# ==============================================================================
# 5. الواجهة الرئيسية: بناء الستوري بورد الكامل
# ==============================================================================
def build_storyboard(
    scenes: List[Dict[str, Any]],
    full_transcript: str = "",
    llm_fn: Optional[LLMFn] = None,
    total_duration: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """
    scenes: [{"text","start","end","words":[...]}] -> نفس المشاهد + حقول الموشن (نوع الرسمة، البطاقات، الثيم، الانتقال...).
    يعمل دائماً (حتى بدون LLM/إنترنت) ولا يختلق أي معلومة.
    """
    if not scenes:
        return []
    transcript = full_transcript or " ".join(str(s.get("text", "")) for s in scenes)
    gctx = analyze_global_context(transcript)
    total = len(scenes)

    cards: List[Dict[str, Any]] = []
    prev_role = None
    for i, sc in enumerate(scenes):
        c = plan_scene_rules(
            str(sc.get("text", "")), i, total, gctx, prev_role,
            prev_text=str(scenes[i - 1].get("text", "")) if i > 0 else "",
            next_text=str(scenes[i + 1].get("text", "")) if i + 1 < total else "",
        )
        prev_role = c["role"]
        cards.append(c)

    n_acc = enrich_with_llm(cards, scenes, transcript, llm_fn)

    out: List[Dict[str, Any]] = []
    prev_types: List[str] = []
    for i, (sc, c) in enumerate(zip(scenes, cards)):
        entry = dict(sc)
        # تصحيح النص بـ LLM (بحذر) مع حفظ التوقيت
        fx = c.pop("_fixed_text", None)
        if fx and sc.get("words"):
            new_words, changed = apply_text_fix(sc["words"], fx)
            if changed:
                entry["words"] = new_words
                entry["text"] = " ".join(w["word"] for w in new_words)
                entry["text_fixed_by_llm"] = True
        validate_card(c, entry["text"], transcript)
        c.pop("_safe", None)

        # تنوع بصري: لا نكرر نفس الرسمة 3 مرات متتالية
        if len(prev_types) >= 2 and prev_types[-1] == prev_types[-2] == c["scene_type"]:
            alt = ROLE_SCENE_FALLBACK.get(c["role"], "key_concept")
            c["scene_type"] = alt if alt != c["scene_type"] else "key_concept"
        prev_types.append(c["scene_type"])

        entry.update(c)
        entry["transition"] = entry["transition_type"]
        entry["word_strings"] = [w.get("word", "") for w in entry.get("words", [])]
        entry["global_domain"] = gctx.get("main_topic") or "general"
        entry["storyboard_source"] = "llm+rules" if n_acc else "rules"
        out.append(entry)

    finalize_scene_timing(out, total_duration)
    return out


# ==============================================================================
# 6. توقيت المشاهد والكابشن (يمنع تجمد الكابشن)
# ==============================================================================
CAPTION_HOLD_SEC = 0.6   # أقصى مدة يبقى فيها آخر كابشن بعد آخر كلمة منطوقة


def finalize_scene_timing(scenes: List[Dict[str, Any]], total_duration: Optional[float] = None) -> None:
    """
    - المشهد البصري يمتد حتى بداية التالي (لا شاشة فارغة).
    - الكابشن لا يبقى بعد آخر كلمة منطوقة بأكثر من CAPTION_HOLD_SEC (كان يتجمد 16 ثانية سابقاً).
    """
    if not scenes:
        return
    scenes.sort(key=lambda s: float(s.get("start", 0.0)))
    scenes[0]["visual_start"] = 0.0
    for i, s in enumerate(scenes):
        words = s.get("words") or []
        sp_start = float(words[0]["start"]) if words else float(s.get("start", 0.0))
        sp_end = float(words[-1]["end"]) if words else float(s.get("end", sp_start + 1.0))
        nxt_start = float(scenes[i + 1]["start"]) if i + 1 < len(scenes) else (float(total_duration) if total_duration else sp_end + CAPTION_HOLD_SEC)
        s.setdefault("visual_start", sp_start if i else 0.0)
        s["visual_end"] = max(sp_end, nxt_start)
        s["speech_start"] = sp_start
        s["speech_end"] = sp_end
        s["caption_until"] = min(s["visual_end"], sp_end + CAPTION_HOLD_SEC)
        if i > 0:
            s["visual_start"] = scenes[i - 1]["visual_end"]


# ==============================================================================
# 7. قياس تغطية التفريغ للكلام الفعلي (يكتشف فقدان الكلام)
# ==============================================================================
def speech_coverage(
    words: List[Dict[str, Any]],
    voiced: List[Tuple[float, float]],
    min_gap: float = 1.2,
    tolerance: float = 0.35,
) -> Dict[str, Any]:
    """
    voiced: فترات يوجد فيها صوت كلام فعلي (من تحليل الطاقة الصوتية).
    ترجع: coverage (0..1) + gaps: فترات فيها كلام لكن بلا أي كلمات مفرَّغة.
    """
    voiced = [(float(a), float(b)) for a, b in voiced if b > a]
    total_v = sum(b - a for a, b in voiced)
    if total_v <= 0:
        return {"coverage": 1.0, "gaps": [], "voiced_sec": 0.0}
    covered_iv = sorted((max(0.0, float(w["start"]) - tolerance), float(w["end"]) + tolerance) for w in words)
    merged: List[List[float]] = []
    for a, b in covered_iv:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    gaps: List[Tuple[float, float]] = []
    covered_sec = 0.0
    for va, vb in voiced:
        cursor = va
        for ca, cb in merged:
            if cb <= cursor:
                continue
            if ca >= vb:
                break
            if ca > cursor:
                gaps.append((cursor, min(ca, vb)))
            covered_sec += max(0.0, min(cb, vb) - max(ca, cursor))
            cursor = max(cursor, min(cb, vb))
            if cursor >= vb:
                break
        if cursor < vb:
            gaps.append((cursor, vb))
    # دمج الفجوات المتقاربة وإبقاء الطويلة فقط
    gaps.sort()
    mg: List[List[float]] = []
    for a, b in gaps:
        if mg and a - mg[-1][1] <= 0.5:
            mg[-1][1] = b
        else:
            mg.append([a, b])
    big = [(round(a, 3), round(b, 3)) for a, b in mg if b - a >= min_gap]
    return {"coverage": round(min(1.0, covered_sec / total_v), 3), "gaps": big, "voiced_sec": round(total_v, 3)}


def merge_words_by_time(base: List[Dict[str, Any]], extra: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """إضافة كلمات extra إلى base دون تكرار (تُسقَط الكلمات المتداخلة زمنياً مع كلمات base)."""
    out = [dict(w) for w in base]
    for w in extra:
        ws, we = float(w["start"]), float(w["end"])
        dur = max(0.05, we - ws)
        overlap = False
        for b in base:
            ov = min(we, float(b["end"])) - max(ws, float(b["start"]))
            if ov > 0.5 * dur:
                overlap = True
                break
        if not overlap:
            out.append(dict(w))
    out.sort(key=lambda x: (float(x["start"]), float(x["end"])))
    return out


# ==============================================================================
# 8. فحص جودة شامل قبل الرندر (يُسجَّل ويُصحَّح تلقائياً)
# ==============================================================================
def qa_report(scenes: List[Dict[str, Any]], transcript: str) -> List[str]:
    """قائمة مشاكل متبقية (يجب أن تكون فارغة). تُستخدم في الاختبارات وفي سجل التشغيل."""
    issues: List[str] = []
    for i, s in enumerate(scenes):
        for fld in ("badge_label", "concept_title", "kpi_value", "kpi_label"):
            v = str(s.get(fld, ""))
            if not v:
                issues.append(f"scene{i}:{fld}:empty")
            elif not is_grounded(v, transcript):
                issues.append(f"scene{i}:{fld}:ungrounded:{v}")
            elif fld in ("concept_title",) and echoes_caption(v, s.get("text", "")):
                issues.append(f"scene{i}:{fld}:echo")
        if s.get("scene_type") not in RENDERABLE_SCENE_TYPES:
            issues.append(f"scene{i}:bad_scene_type:{s.get('scene_type')}")
        if s.get("caption_until", 0) - s.get("speech_end", 0) > CAPTION_HOLD_SEC + 1e-6:
            issues.append(f"scene{i}:caption_stuck")
    return issues


def storyboard_cache_key(scenes: List[Dict[str, Any]]) -> str:
    return hashlib.md5("|".join(str(s.get("text", "")) for s in scenes).encode("utf-8")).hexdigest()


# ==============================================================================
# 5. التحكم البصري السريع وتغيير المشهد كل 2.5 - 3 ثوانٍ (Hormozi Fast Visual Pacing & Pexels Query Builder)
# ==============================================================================
import math

def enforce_fast_hormozi_scene_pacing(
    planned_scenes: List[Dict[str, Any]],
    min_scene_sec: float = 1.6,
    max_scene_sec: float = 2.85
) -> List[Dict[str, Any]]:
    """
    يضمن تغيير المشهد أو الزاوية البصرية كل `2.5` إلى `3.0` ثوانٍ كحد أقصى لكسر الملل والاحتفاظ بانتباه المشاهد (High Retention):
    إذا كان أي مشهد أطول من `max_scene_sec` (~2.85s)، يتم تقسيمه تلقائياً إلى لقطتين بصريتين متتاليتين
    مع تبديل زاوية الكاميرا/وضع العرض (`full_screen` <-> `stock_broll` / `split_screen_stage`) وتنويع الرسم التعبيري.
    """
    if not planned_scenes:
        return []

    paced_scenes: List[Dict[str, Any]] = []
    layout_cycle = ["full_screen", "stock_broll", "split_screen_stage"]
    archetype_fallbacks = [
        "video_montage_studio", "time_warp_clock", "ai_neural_brain",
        "growth_analytics", "platform_builder", "reels_smartphone"
    ]

    for idx, sc in enumerate(planned_scenes):
        s_start = float(sc.get("start", 0.0))
        s_end = float(sc.get("end", s_start + 2.5))
        dur = s_end - s_start

        if dur <= max_scene_sec or dur < (min_scene_sec * 1.75):
            sc_copy = dict(sc)
            sc_copy["scene_index"] = len(paced_scenes)
            paced_scenes.append(sc_copy)
            continue

        # تقسيم المشهد الطويل إلى لقطات سريعة كل 2.5 - 2.8 ثانية
        num_parts = max(2, int(math.ceil(dur / 2.65)))
        part_dur = dur / float(num_parts)
        words_list = list(sc.get("words") or [])
        text_tokens = str(sc.get("text", "")).split()

        for p_i in range(num_parts):
            p_start = round(s_start + p_i * part_dur, 3)
            p_end = round(s_end if p_i == num_parts - 1 else (s_start + (p_i + 1) * part_dur), 3)
            sub_sc = dict(sc)
            sub_sc["start"] = p_start
            sub_sc["end"] = p_end
            sub_sc["duration"] = round(p_end - p_start, 3)
            sub_sc["scene_index"] = len(paced_scenes)

            if words_list:
                sub_words = [w for w in words_list if float(w.get("start", 0.0)) >= p_start - 0.08 and float(w.get("start", 0.0)) < p_end + 0.05]
                if sub_words:
                    sub_sc["words"] = sub_words
                    sub_sc["text"] = " ".join(str(w.get("word", "")).strip() for w in sub_words if str(w.get("word", "")).strip())
            elif text_tokens:
                chunk_sz = max(1, int(math.ceil(len(text_tokens) / float(num_parts))))
                tok_slice = text_tokens[p_i * chunk_sz:(p_i + 1) * chunk_sz]
                if tok_slice:
                    sub_sc["text"] = " ".join(tok_slice)

            if p_i > 0 and not sc.get("user_override_archetype"):
                cur_layout = str(sc.get("layout_mode", "full_screen"))
                next_layout = layout_cycle[(layout_cycle.index(cur_layout) + p_i) % len(layout_cycle)] if cur_layout in layout_cycle else "stock_broll"
                sub_sc["layout_mode"] = next_layout
                sub_sc["zoom_factor"] = 1.14 if (p_i % 2 == 1) else 1.06
                if next_layout != "stock_broll":
                    alt_arch = archetype_fallbacks[(idx + p_i) % len(archetype_fallbacks)]
                    sub_sc["archetype"] = alt_arch
                    sub_sc["visual_subject"] = alt_arch

            paced_scenes.append(sub_sc)

    return paced_scenes
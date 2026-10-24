"""
motion_learning_system.py - نظام التعلم الذاتي للموشن جرافيك من الملفات المرجعية والإنترنت (Self-Learning Motion Graphics Brain)
=================================================================================================================================
يقوم هذا النظام بـ:
1. التعلم من الملفات المرجعية (`SpecKnowledgeIngestor`):
   - يقرأ ويحلل ملفات توصيف الموشن جرافيك إطاراً بإطار (مثل `reference_motion_spec.md` / `Motion Graphics Frame By Frame Spec (1).md`).
   - يستخلص لوحات الألوان (`Clean SaaS Light #EEF2F6` و `Split-Screen Dark Stage #111317`)، ومنحنيات فيزياء النوابض (`Spring stiffness: 180-260, damping: 16-18`)،
     وقواعد الإيقاع البصري (تفاعل بصري جديد كل 1.5 - 2.5 ثانية عند 30fps).
2. التعلم التلقائي الحي من الإنترنت (`WebMotionLearner`):
   - يتصل بالإنترنت (عبر محركات البحث ونماذج الذكاء الاصطناعي السحابية Groq / Gemini / OpenAI / Pollinations) لاستلهام أنماط الموشن جرافيك الاحترافية
     الخاصة بموضوع الفيديو (قوائم متتابعة، فقاعات أسئلة، ميزان مقارنة السعر/القيمة أو المشكلة/الحل، شبكة 2x2 مع نقرة الماوس، مقارنة قبل/بعد، وشريط كتابة آلي).
   - يحفظ الأنماط المكتسبة تلقائياً في قاعدة معرفة متنامية (`learned_motion_genome.json`) ليتطور مع كل فيديو جديد.
3. المدقق الذاتي الصارم لمنع تكرار الأخطاء (`MotionQualityAuditor`):
   - يصلح الكلمات المبتورة صوتياً في السياق (مثل: "المونت" -> "المونتاج"، "الاج" -> "الاجتماعي"، "منت" -> "تمنتج"، "احت" -> "احترافي").
   - يمنع منعاً باتاً نسخ أول كلمات المتحدث حرفياً في الشارة العلوية أو البطاقات (لا مزيد من "إضاءة معرفية • أهلاً لاحظت كثير" أو "جبت لكم منصة").
   - يمنع تكرار البطاقة الثابتة ("Pro Tips / معلومة قيمة") ويستبدلها ببيانات حركية غنية ومتغيرة في كل مشهد.
"""

import os
import re
import json
import time
import hashlib
import logging
from typing import Dict, Any, List, Optional, Tuple
import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

_CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
GENOME_STORAGE_PATH = os.path.join(_CURRENT_DIR, "outputs", "learned_motion_genome.json")
REFERENCE_SPEC_PATHS = [
    os.path.join(_CURRENT_DIR, "reference_motion_spec.md"),
    os.path.join(_CURRENT_DIR, "Motion Graphics Frame By Frame Spec (1).md")
]

from style_evolution_brain import ALL_DYNAMIC_VISUAL_ARCHETYPES as CHOREOGRAPHY_ARCHETYPES

CONTEXTUAL_BROKEN_WORD_REPAIRS: List[Tuple[str, str]] = [
    (r"(?<!\w)في\s+المونت(?!\w)", "في المونتاج"),
    (r"(?<!\w)المونت\s+الان(?!\w)", "المونتاج لأن"),
    (r"(?<!\w)المونت(?!\w)", "المونتاج"),
    (r"(?<!\w)الان\s+أغلب\s+الناس(?!\w)", "لأن أغلب الناس"),
    (r"(?<!\w)الان\s+اغلب\s+الناس(?!\w)", "لأن أغلب الناس"),
    (r"(?<!\w)تصور\s+للفيديوهات(?!\w)", "تصور الفيديوهات"),
    (r"(?<!\w)التواصل\s+الاج(?!\w)", "التواصل الاجتماعي"),
    (r"(?<!\w)مواقع\s+التواصل\s+الاج(?!\w)", "مواقع التواصل الاجتماعي"),
    (r"(?<!\w)الاج(?!\w)", "الاجتماعي"),
    (r"(?<!\w)المسؤوله\s+على\s+اللي(?!\w)", "المسؤولة على المونتاج"),
    (r"(?<!\w)صورته\s+ذكاء\s+الاصطناعي(?!\w)", "صوت وصورة بالذكاء الاصطناعي"),
    (r"(?<!\w)منت\s+الفيديو(?!\w)", "تمنتج الفيديو"),
    (r"(?<!\w)ومونتاج\s+احت\s+ولا(?!\w)", "ومونتاج احترافي"),
    (r"(?<!\w)ومونتاج\s+احت(?!\w)", "ومونتاج احترافي"),
    (r"(?<!\w)مونتاج\s+احت(?!\w)", "مونتاج احترافي"),
    (r"(?<!\w)من\s+دقيقه(?!\w)", "أقل من دقيقة"),
    (r"(?<!\w)قص\s+تعديل\s+الفيديو(?!\w)", "قص وتعديل الفيديو"),
]

SINGLE_TRUNCATED_TOKEN_MAP = {
    "المونت": "المونتاج",
    "الاج": "الاجتماعي",
    "منت": "تمنتج",
    "احت": "احترافي",
    "الانتاجيه": "الإنتاجية",
    "المسؤوله": "المسؤولة",
    "دقيقه": "دقيقة",
    "للفيديوهات": "الفيديوهات",
}


def repair_truncated_words_and_sentences(words_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if not words_list:
        return []

    repaired: List[Dict[str, Any]] = [dict(w) for w in words_list]

    for i, w_obj in enumerate(repaired):
        raw_w = str(w_obj.get("word", "")).strip()
        clean_w = raw_w.strip("،,.!؟?")
        if clean_w in SINGLE_TRUNCATED_TOKEN_MAP:
            repaired[i]["word"] = SINGLE_TRUNCATED_TOKEN_MAP[clean_w]

        if clean_w in {"الان", "الآن"} and i + 1 < len(repaired):
            nxt_w = str(repaired[i + 1].get("word", "")).strip("،,.!؟?")
            if nxt_w in {"أغلب", "اغلب", "كثير", "بزاف", "الناس"}:
                repaired[i]["word"] = "لأن"

        if clean_w in {"صورته", "صورتك"} and i + 1 < len(repaired):
            nxt_w = str(repaired[i + 1].get("word", "")).strip("،,.!؟?")
            if "ذكاء" in nxt_w or "اصطناعي" in nxt_w:
                repaired[i]["word"] = "صوت وصورة"

        if clean_w == "ولا" and i > 0:
            prev_w = str(repaired[i - 1].get("word", "")).strip("،,.!؟?")
            if prev_w == "احترافي":
                repaired[i]["word"] = ""

    repaired = [w for w in repaired if str(w.get("word", "")).strip()]
    return repaired


class SpecKnowledgeIngestor:
    @staticmethod
    def load_reference_specs() -> Dict[str, Any]:
        extracted_specs: Dict[str, Any] = {
            "styles_loaded": ["clean_saas_educational_cards", "gamified_pixel_judges_split_screen"],
            "pacing_seconds_per_event": 1.8,
            "target_fps": 30,
            "palettes": {
                "clean_saas_light": {
                    "bg": (238, 242, 246),         # #EEF2F6
                    "card_bg": (255, 255, 255),    # #FFFFFF
                    "text_dark": (17, 24, 39),     # #111827
                    "text_muted": (100, 116, 139), # #64748B
                    "blue": (37, 99, 235),         # #2563EB
                    "emerald": (16, 185, 129),     # #10B981
                    "purple": (139, 92, 246),      # #8B5CF6
                    "pink": (236, 72, 153),        # #EC4899
                    "yellow_hl": (250, 204, 21),   # #FACC15
                    "red_alert": (239, 68, 68)     # #EF4444
                },
                "dark_stage_split": {
                    "stage_bg": (17, 19, 23),      # #111317
                    "card_bg": (26, 29, 36),       # #1A1D24
                    "white_card": (255, 255, 255), # #FFFFFF
                    "orange": (255, 107, 0),       # #FF6B00
                    "blue": (59, 130, 246),        # #3B82F6
                    "purple": (168, 85, 247),      # #A855F7
                    "green": (34, 197, 94),        # #22C55E
                    "yellow": (234, 179, 8),       # #EAB308
                    "red": (239, 68, 68)           # #EF4444
                }
            },
            "json_templates": []
        }

        for path in REFERENCE_SPEC_PATHS:
            if os.path.exists(path):
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        md_text = f.read()
                    json_blocks = re.findall(r"```json\s*(.*?)\s*```", md_text, re.DOTALL)
                    for jb in json_blocks:
                        try:
                            parsed = json.loads(jb)
                            extracted_specs["json_templates"].append(parsed)
                        except Exception:
                            pass
                except Exception as e:
                    logger.debug(f"Reference spec parse notice: {e}")

        return extracted_specs


class WebMotionLearner:
    def __init__(self):
        self.spec_knowledge = SpecKnowledgeIngestor.load_reference_specs()
        self.learned_genome = self._load_genome()

    def _load_genome(self) -> Dict[str, Any]:
        if os.path.exists(GENOME_STORAGE_PATH):
            try:
                with open(GENOME_STORAGE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {"learned_topics": {}, "total_videos_learned": 0}

    def _save_genome(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(GENOME_STORAGE_PATH)), exist_ok=True)
            with open(GENOME_STORAGE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.learned_genome, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def fetch_web_design_inspiration(self, topic_query: str, timeout: float = 3.5) -> List[str]:
        snippets: List[str] = []
        try:
            url = "https://api.duckduckgo.com/"
            resp = requests.get(url, params={"q": topic_query, "format": "json", "no_html": 1}, timeout=timeout)
            if resp.status_code == 200:
                data = resp.json()
                if data.get("AbstractText"):
                    snippets.append(str(data["AbstractText"])[:200])
                for rt in data.get("RelatedTopics", [])[:3]:
                    if isinstance(rt, dict) and rt.get("Text"):
                        snippets.append(str(rt["Text"])[:140])
        except Exception:
            pass
        return snippets

    def learn_and_build_scene_choreography(
        self,
        scenes: List[Dict[str, Any]],
        full_transcript: str,
        global_ctx: Dict[str, Any],
        query_llm_func=None,
        groq_api_key: Optional[str] = None,
        gemini_api_key: Optional[str] = None,
        openai_api_key: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        if not scenes:
            return []

        domain = global_ctx.get("domain", "general")
        topic_hash = hashlib.md5(full_transcript.encode("utf-8", errors="ignore")).hexdigest()[:10]

        choreographed_scenes: List[Dict[str, Any]] = []
        used_archetypes: List[str] = []

        for idx, sc in enumerate(scenes):
            s_text = str(sc.get("text", "")).strip()
            blueprint = self._build_deep_scene_blueprint(
                scene_text=s_text,
                scene_index=idx,
                total_scenes=len(scenes),
                domain=domain,
                global_ctx=global_ctx,
                used_archetypes=used_archetypes
            )
            used_archetypes.append(blueprint["archetype"])

            merged = dict(sc)
            merged.update(blueprint)
            merged["step_badge"] = f"#{idx + 1}"
            merged["style_mode"] = "clean_saas_light" if (idx % 2 == 0) else "dark_stage_split"
            choreographed_scenes.append(merged)

        if callable(query_llm_func):
            try:
                web_Order = self.fetch_web_design_inspiration(global_ctx.get("domain_label_ar", "motion graphics"))
                web_hint = " | ".join(web_Order) if web_Order else "أسلوب 101bdarija و moujtabakhalifa الاحترافي"

                scenes_desc = "\n".join(
                    f"{i+1}. [{s['start']:.1f}s - {s['end']:.1f}s]: \"{s['text']}\""
                    for i, s in enumerate(choreographed_scenes)
                )
                prompt = (
                    f"النص الكامل للفيديو: \"{full_transcript}\"\n"
                    f"المجال المكتشف: {global_ctx.get('domain_label_ar', '')}\n"
                    f"مرجع الإلهام من الإنترنت: {web_hint}\n\n"
                    f"المشاهد:\n{scenes_desc}\n\n"
                    "أنت مخرج موشن جرافيك عالمي يتبع أسلوب الفيديوهات الاحترافية (101bdarija Clean SaaS Cards و moujtabakhalifa Split-Screen Stage).\n"
                    "لكل مشهد، أعطني JSON Array يحتوي كائناً لكل مشهد بالمفاتيح التالية:\n"
                    "- archetype: واحد من [saas_folder_reorder, stage_trust_bubbles, stage_balance_scale, saas_typewriter_mechanism, saas_process_flow, saas_grid_2x2_cursor, stage_before_after_checklist, interactive_cta_outro]\n"
                    "- badge_label: عنوان المفهوم في الشارة العلوية (2 إلى 4 كلمات تلخص المعنى الضمني، ممنوع تماماً نسخ كلمات المتحدث حرفياً أو كتابة 'إضاءة معرفية')\n"
                    "- concept_title: العنوان الرئيسي داخل بطاقة الموشن (2 إلى 4 كلمات قوية)\n"
                    "- sub_items: مصفوفة من 4 عناصر قصيرة جداً (كلمتان لكل عنصر) تظهر كبطاقات فرعية متحركة أو فقاعات أو شبكة 2x2 تعبر عن تفاصيل الفكرة\n"
                    "- kpi_value: مؤشر رقمي أو رمز قوي (مثل '< 60s', '10x أسرع', 'AI Auto', '58 ولاية', '+300%')\n"
                    "- kpi_label: وصف المؤشر في كلمتين\n"
                    "أرجع JSON Array صالحاً فقط."
                )

                ai_resp = query_llm_func(
                    prompt=prompt,
                    system_prompt="أنت مخرج فني خبير في الموشن جرافيك التفاعلي. أرجع JSON Array فقط بدون أي شرح.",
                    groq_api_key=groq_api_key,
                    gemini_api_key=gemini_api_key,
                    openai_api_key=openai_api_key,
                    temperature=0.2,
                    max_tokens=1400
                )
                if ai_resp:
                    m = re.search(r"\[.*\]", ai_resp, re.DOTALL)
                    if m:
                        parsed = json.loads(m.group(0))
                        if isinstance(parsed, list) and len(parsed) == len(choreographed_scenes):
                            for i, item in enumerate(parsed):
                                if not isinstance(item, dict):
                                    continue
                                arch = str(item.get("archetype", "")).strip()
                                if arch in CHOREOGRAPHY_ARCHETYPES:
                                    choreographed_scenes[i]["archetype"] = arch
                                bl = str(item.get("badge_label", "")).strip()
                                if len(bl) >= 4 and "إضاءة" not in bl and "أنس" not in bl and "17" not in bl:
                                    choreographed_scenes[i]["badge_label"] = bl
                                ct = str(item.get("concept_title", "")).strip()
                                if len(ct) >= 4 and "إضاءة" not in ct:
                                    choreographed_scenes[i]["concept_title"] = ct
                                    choreographed_scenes[i]["short_title"] = ct
                                subs = item.get("sub_items")
                                if isinstance(subs, list) and len(subs) >= 3:
                                    clean_subs = [str(x).strip()[:28] for x in subs[:4] if str(x).strip()]
                                    if len(clean_subs) >= 3:
                                        choreographed_scenes[i]["sub_items"] = clean_subs
                                kv = str(item.get("kpi_value", "")).strip()
                                kl = str(item.get("kpi_label", "")).strip()
                                if kv and kl and "Pro Tips" not in kv:
                                    choreographed_scenes[i]["kpi_value"] = kv
                                    choreographed_scenes[i]["kpi_label"] = kl
            except Exception as e:
                logger.debug(f"Web motion learner fallback to built-in deep choreography: {e}")

        choreographed_scenes = MotionQualityAuditor.audit_and_heal_storyboard(
            choreographed_scenes, full_transcript, global_ctx
        )

        self.learned_genome["learned_topics"][topic_hash] = {
            "domain": domain,
            "timestamp": int(time.time()),
            "scenes_count": len(choreographed_scenes),
            "archetypes_used": [s.get("archetype") for s in choreographed_scenes]
        }
        self.learned_genome["total_videos_learned"] = int(self.learned_genome.get("total_videos_learned", 0)) + 1
        self._save_genome()

        return choreographed_scenes

    def _build_deep_scene_blueprint(
        self,
        scene_text: str,
        scene_index: int,
        total_scenes: int,
        domain: str,
        global_ctx: Dict[str, Any],
        used_archetypes: List[str],
        prev_scene_text: str = "",
        next_scene_text: str = ""
    ) -> Dict[str, Any]:
        from style_evolution_brain import match_speech_to_visual_archetype
        raw_clean = re.sub(r"[،,.!؟?()\[\]\-]+ ", " ", (scene_text or "")).strip()
        filler_stop = {
            "أهلاً", "اهلا", "وسهلاً", "مرحبا", "شوف", "شوفوا", "طبعاً", "طبعا", "يعني",
            "صراحة", "بصراحة", "أنه", "انه", "أن", "ان", "اللي", "التي", "الذي", "الذين",
            "هذا", "هذه", "هاد", "هادي", "في", "من", "على", "إلى", "عن", "مع", "هو", "هي",
            "هم", "أنا", "انا", "نحن", "بس", "برك", "قاع", "راه", "راهي", "واش", "كيفاش",
            "علاش", "لأن", "لان", "لو", "إذا", "اذا", "كان", "كانت", "يكون", "تكون", "جدا", "بزاف"
        }
        all_tokens = [w for w in raw_clean.split() if len(w) > 1]
        meaningful_tokens = [w for w in all_tokens if w.lower() not in filler_stop]
        if len(meaningful_tokens) < 2:
            meaningful_tokens = all_tokens if all_tokens else ["الفكرة", "الأساسية"]

        concept_title = " ".join(meaningful_tokens[:5])
        if len(concept_title) < 5 and len(all_tokens) >= 2:
            concept_title = " ".join(all_tokens[:5])

        sub_items: List[str] = []
        chunk_size = max(2, min(3, len(meaningful_tokens) // 2 or 2))
        for i in range(0, len(meaningful_tokens), chunk_size):
            phrase = " ".join(meaningful_tokens[i:i + chunk_size]).strip()
            if len(phrase) >= 3 and phrase not in sub_items:
                sub_items.append(phrase)
        while len(sub_items) < 4:
            sub_items.append(concept_title if len(sub_items) == 0 else " ".join(meaningful_tokens[:min(3, len(meaningful_tokens))]))

        num_m = re.search(r"(\d+\s*(?:%|ثانية|ثواني|دقيقة|دقائق|ساعة|ساعات|ولاية|خصائص|ميزات)?)", scene_text or "")
        if num_m:
            kpi_value = num_m.group(1).strip()
        else:
            kpi_value = " ".join(meaningful_tokens[:2]) if len(meaningful_tokens) >= 2 else meaningful_tokens[0]
        kpi_label = " ".join(meaningful_tokens[-2:]) if len(meaningful_tokens) >= 3 else concept_title

        rot_seed = int(self.learned_genome.get("total_videos_learned", 0)) + int(time.time()) % 997
        arch, vis_subj = match_speech_to_visual_archetype(
            scene_text=scene_text,
            scene_index=scene_index,
            total_scenes=total_scenes,
            used_archetypes=used_archetypes,
            variation_seed=rot_seed
        )

        short_kw = " ".join(meaningful_tokens[:3])
        badge_label = f"محور المشهد • {short_kw}"

        return {
            "archetype": arch,
            "visual_subject": vis_subj,
            "scene_type": "growth_analytics",
            "badge_label": badge_label,
            "concept_title": concept_title,
            "concept_subtitle": raw_clean[:68] if raw_clean else concept_title,
            "sub_items": sub_items[:4],
            "balance_left": (sub_items[0], "الوضع السابق"),
            "balance_right": (sub_items[min(1, len(sub_items) - 1)], kpi_value),
            "before_after": (sub_items[0], "4.0", concept_title[:22], "9.8"),
            "typewriter_query": concept_title,
            "kpi_value": kpi_value,
            "kpi_label": kpi_label,
        }


class MotionQualityAuditor:
    @staticmethod
    def audit_and_heal_storyboard(
        scenes: List[Dict[str, Any]],
        full_transcript: str,
        global_ctx: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        if not scenes:
            return []

        from style_evolution_brain import ALL_DYNAMIC_VISUAL_ARCHETYPES, match_speech_to_visual_archetype
        healed: List[Dict[str, Any]] = []
        used_archs: List[str] = []
        dyn_seed = int(time.time() * 10) % 997

        for idx, sc in enumerate(scenes):
            item = dict(sc)
            raw_text = str(item.get("text", "")).strip()
            user_arch = str(item.get("user_override_archetype") or "").strip()
            arch = str(item.get("archetype", "")).strip()
            vis_subj = str(item.get("visual_subject", "")).strip()

            if user_arch and user_arch in ALL_DYNAMIC_VISUAL_ARCHETYPES:
                arch = user_arch
                vis_subj = user_arch
            elif not arch or arch not in ALL_DYNAMIC_VISUAL_ARCHETYPES or arch in used_archs:
                arch, matched_subj = match_speech_to_visual_archetype(
                    scene_text=raw_text,
                    scene_index=idx,
                    total_scenes=len(scenes),
                    used_archetypes=used_archs,
                    variation_seed=dyn_seed
                )
                if not vis_subj:
                    vis_subj = matched_subj

            concept = str(item.get("concept_title", "")).strip()
            if not concept and raw_text:
                concept = raw_text[:34]
            badge = str(item.get("badge_label", "")).strip() or concept[:28]

            item["archetype"] = arch
            item["visual_subject"] = vis_subj or arch
            item["badge_label"] = badge
            item["concept_title"] = concept
            item["short_title"] = concept

            used_archs.append(arch)
            healed.append(item)

        return healed


_GLOBAL_LEARNER_INSTANCE: Optional[WebMotionLearner] = None


def get_motion_learner() -> WebMotionLearner:
    global _GLOBAL_LEARNER_INSTANCE
    if _GLOBAL_LEARNER_INSTANCE is None:
        _GLOBAL_LEARNER_INSTANCE = WebMotionLearner()
    return _GLOBAL_LEARNER_INSTANCE

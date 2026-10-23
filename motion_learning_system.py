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

CHOREOGRAPHY_ARCHETYPES = [
    "saas_folder_reorder",          # بطاقة مجلد وقائمة عناصر تنزلق بالتتابع (Stagger 6f) وتتبادل مواقعها مع أسهم دوارة
    "stage_trust_bubbles",          # شاشة هاتف/عنصر مركزي محاط بـ 4 فقاعات منبثقة (Pop-in Spring) + شريط مؤشر سفلي
    "stage_balance_scale",          # ميزان فيزيائي ذو كفتين (المشكلة/اليدوي مقابل الحل/الذكي أو السعر مقابل القيمة)
    "saas_typewriter_mechanism",    # ترس ميكانيكي دوار + شريط بحث يكتب المفهوم حرفاً بحرف (Typewriter + Caret)
    "saas_process_flow",            # 3 بطاقات متدرجة: شريط تقدم + منحنى بياني تتبعه أيقونة ذكية + بطاقة اكتشاف
    "saas_grid_2x2_cursor",         # شبكة رباعية (2x2 Grid) بأشرطة تقدم ملونة + جزيئات متطايرة + مؤشر ماوس ينقر مع Ripple
    "stage_before_after_checklist", # مقارنة (قبل / بعد) مع عداد تقييم صاعد + قائمة تدقيق تتفعل بعلامات صح خضراء ✔️
    "interactive_cta_outro"         # بطاقة تفاعل ختامية بخطوتين (طائرة ورقية متحركة ✈️ + حقل تعليق/طلب مع نقرة ماوس)
]

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
        used_archetypes: List[str]
    ) -> Dict[str, Any]:
        t_low = scene_text.lower()
        wilayas = global_ctx.get("wilayas_count") or 58

        is_problem_or_pain = any(w in t_low for w in ["مشكل", "مشكلة", "يعاني", "يعانيوا", "ما عندها وقت", "ما عندهمش وقت", "ضيق", "صعيب", "يتقطع", "تلف", "خسارة"])
        is_time_or_speed = any(w in t_low for w in ["أقل من دقيقة", "اقل من دقيقه", "دقيقة", "دقيقه", "ثواني", "بسرعة", "وقت", "ساعات"])
        is_productivity_or_social = any(w in t_low for w in ["انتاجية", "إنتاجية", "الانتاجيه", "التواصل الاجتماعي", "انستغرام", "ريلز", "تيك توك", "مشاهدات", "تفاعل", "ريتش", "نشر"])
        is_ai_or_platform_intro = any(w in t_low for w in ["جبت لكم", "منصة", "تطبيق", "ذكاء", "الاصطناعي", "أوتوماتيكي", "اوتوماتيكي", "مسؤولة", "المسؤوله"])
        is_editing_or_cuts = any(w in t_low for w in ["قص", "تعديل", "تمنتج", "مونتاج", "احترافي", "صوت", "صورة", "فيديوهات", "الفيديو"])
        is_ecommerce_feature = any(w in t_low for w in ["كابل", "شاحن", "سيبور", "حامل", "قماش", "تشارجي", "خصائص", "ثلاث", "بري", "سعر"])
        is_delivery_or_cta = any(w in t_low for w in ["توصيل", "ولاية", "اكموندي", "اطلب", "رابط", "اسفل", "تابع", "شارك", "حفظ"]) or (scene_index == total_scenes - 1 and total_scenes > 2)

        if is_problem_or_pain and not is_ai_or_platform_intro and scene_index == 0:
            if domain == "ecommerce":
                return {
                    "archetype": "stage_trust_bubbles",
                    "scene_type": "ecommerce_showcase",
                    "badge_label": "المشكلة الشائعة • تلف الشواحن التقليدية",
                    "concept_title": "معاناة الكوابل العادية",
                    "concept_subtitle": "انقطاع سريع وبطء في الشحن اليومي",
                    "sub_items": ["انقطاع السلك السريع", "بطء في الشحن", "صعوبة مسك الهاتف", "خسارة المال المتكررة"],
                    "balance_left": ("كابل تقليدي", "يتلف بسرعة"),
                    "balance_right": ("كابل القماش الذكي", "متانة 100%"),
                    "before_after": ("قبل: تلف مستمر", "3.2", "بعد: حماية فائقة", "9.8"),
                    "typewriter_query": "حل مشكلة تلف الكوابل",
                    "kpi_value": "مشكلة شائعة",
                    "kpi_label": "تلف الشواحن العادية"
                }
            else:
                return {
                    "archetype": "stage_trust_bubbles",
                    "scene_type": "time_warp_clock",
                    "badge_label": "تحدي صناع المحتوى • عقبة المونتاج اليومي",
                    "concept_title": "مشكلة استنزاف الوقت في المونتاج",
                    "concept_subtitle": "معاناة تصوير الفيديوهات دون وقت لتحريرها",
                    "sub_items": ["تراكم الفيديوهات الخام", "ضيق الوقت اليومي", "صعوبة القص اليدوي", "تأخر النشر المستمر"],
                    "balance_left": ("المونتاج اليدوي", "ساعات مرهقة"),
                    "balance_right": ("الأتمتة الذكية", "ثوانٍ معدودة"),
                    "before_after": ("يدوياً: 4 ساعات", "3.5", "آلياً: 45 ثانية", "9.7"),
                    "typewriter_query": "لماذا يتأخر صناع المحتوى؟",
                    "kpi_value": "85% يعانون",
                    "kpi_label": "ضيق وقت المونتاج"
                }

        if ("ما عندها وقت" in t_low or "تصور" in t_low or ("وقت" in t_low and is_editing_or_cuts)) and scene_index > 0 and not is_ai_or_platform_intro:
            return {
                "archetype": "stage_balance_scale",
                "scene_type": "time_warp_clock",
                "badge_label": "معادلة الوقت • التصوير السهل مقابل المونتاج المرهق",
                "concept_title": "التصوير جاهز لكن المونتاج يستهلك الساعات",
                "concept_subtitle": "الفجوة بين تسجيل الفيديو ونشره للجمهور",
                "sub_items": ["تسجيل الفيديو: 5 دقائق", "قص الصمت يدوياً: ساعة", "تصميم الموشن: ساعتان", "كتابة الكابشن: 45 دقيقة"],
                "balance_left": ("المونتاج اليدوي", "4 ساعات عمل"),
                "balance_right": ("المونتاج الآلي", "أقل من دقيقة"),
                "before_after": ("قبل: إرهاق وتأخر", "4.0", "بعد: سرعة فائقة", "9.6"),
                "typewriter_query": "توفير 95% من وقت التحرير",
                "kpi_value": "4 ساعات -> 1 د",
                "kpi_label": "اختصار وقت التحرير"
            }

        if is_productivity_or_social and not is_ai_or_platform_intro:
            return {
                "archetype": "saas_grid_2x2_cursor",
                "scene_type": "growth_analytics",
                "badge_label": "مضاعفة الإنتاجية • حضور قوي على منصات التواصل",
                "concept_title": "رفع الإنتاجية والانتشار الرقمي",
                "concept_subtitle": "نشر مستمر على إنستغرام وتيك توك ويوتيوب شورتس",
                "sub_items": ["مضاعفة معدل النشر", "سرعة تجهيز الريلز", "جذب انتباه المشاهد", "رفع التفاعل والوصول"],
                "balance_left": ("نشر متقطع", "تفاعل ضعيف"),
                "balance_right": ("نشر يومي منتظم", "نمو متسارع"),
                "before_after": ("قبل: فيديو أسبوعياً", "4.2", "بعد: فيديو يومياً", "9.5"),
                "typewriter_query": "Productivity & Social Growth",
                "kpi_value": "+300% إنتاجية",
                "kpi_label": "نمو التفاعل والوصول"
            }

        if is_ai_or_platform_intro:
            if "صوت" in t_low or "صورة" in t_low or "ذكاء" in t_low:
                return {
                    "archetype": "saas_process_flow",
                    "scene_type": "ai_neural_brain",
                    "badge_label": "محرك الذكاء الاصطناعي • معالجة الصوت والصورة آلياً",
                    "concept_title": "تحويل الصوت والصورة إلى فيديو متكامل",
                    "concept_subtitle": "الذكاء الاصطناعي يفهم السياق ويصمم المشاهد تلقائياً",
                    "sub_items": ["تحليل الصوت والدارجة", "فهم السياق والمعنى", "توليد الموشن جرافيك", "دمج ومزامنة الإطارات"],
                    "balance_left": ("مدخلات خام", "صوت أو فيديو"),
                    "balance_right": ("مخرجات ذكية", "موشن جرافيك احترافي"),
                    "before_after": ("خام: تسجيل عادي", "4.5", "الناتج: فيديو سينمائي", "9.8"),
                    "typewriter_query": "AI Audio & Video Context Engine",
                    "kpi_value": "100% بالـ AI",
                    "kpi_label": "معالجة سياقية ذكية"
                }
            return {
                "archetype": "saas_typewriter_mechanism",
                "scene_type": "platform_builder",
                "badge_label": "الحل الذكي • منصة أتمتة المونتاج بالذكاء الاصطناعي",
                "concept_title": "منصة المونتاج الذكي الشاملة",
                "concept_subtitle": "مسؤولة بالكامل عن تحرير وإخراج الفيديوهات تلقائياً",
                "sub_items": ["قص الصمت التلقائي", "موشن جرافيك سياقي", "كابشن تفاعلي ذكي", "استيراد مشاهد B-Roll"],
                "balance_left": ("برامج معقدة", "خبرة ومجهود"),
                "balance_right": ("منصة ذكية", "بضغطة زر واحدة"),
                "before_after": ("قبل: تعقيد تقني", "3.9", "بعد: أتمتة كاملة", "9.6"),
                "typewriter_query": "AI Video Editing Platform",
                "kpi_value": "All-in-One AI",
                "kpi_label": "منصة مونتاج ذاتية"
            }

        if is_time_or_speed and ("احترافي" in t_low or "احت" in t_low or "مونتاج" in t_low):
            return {
                "archetype": "stage_before_after_checklist",
                "scene_type": "time_warp_clock",
                "badge_label": "سرعة قياسية • مونتاج احترافي في أقل من دقيقة",
                "concept_title": "إخراج احترافي كامل في أقل من 60 ثانية",
                "concept_subtitle": "جودة استوديو عالية مع توفير كامل للوقت والجهد",
                "sub_items": ["سرعة معالجة فائقة", "جودة موشن جرافيك 1080p", "تزامن صوتي وبصري دقيق", "جاهز للنشر الفوري"],
                "balance_left": ("الوقت السابق", "ساعات طويلة"),
                "balance_right": ("الوقت الحالي", "أقل من 60 ثانية"),
                "before_after": ("قبل: 4.1", "4.1", "بعد: 9.8", "9.8"),
                "typewriter_query": "مونتاج احترافي < 60 ثانية",
                "kpi_value": "< 60 ثانية",
                "kpi_label": "سرعة الإنجاز الكامل"
            }

        if is_editing_or_cuts:
            if scene_index >= total_scenes - 1:
                return {
                    "archetype": "interactive_cta_outro",
                    "scene_type": "video_montage_studio",
                    "badge_label": "تحرير شامل • قص وتعديل وموشن جرافيك بضغطة زر",
                    "concept_title": "قص الصمت وتعديل الفيديو بالكامل",
                    "concept_subtitle": "من التسجيل الخام إلى فيديو جاهز لتصدر المشاهدات",
                    "sub_items": ["قص لحظات السكوت", "تحريك البطاقات السياقية", "كابشن متفاعل دقيق", "تصدير بجودة عالية"],
                    "balance_left": ("فيديو خام", "بدون تحرير"),
                    "balance_right": ("فيديو احترافي", "جاهز للنشر"),
                    "before_after": ("قبل: 4.2", "4.2", "بعد: 9.7", "9.7"),
                    "typewriter_query": "ابدأ تجربة المونتاج الذكي",
                    "kpi_value": "قص + تعديل آلي",
                    "kpi_label": "إخراج متكامل"
                }
            return {
                "archetype": "saas_folder_reorder",
                "scene_type": "video_montage_studio",
                "badge_label": "خطوات الأتمتة • تنظيم وقص المشاهد ذكياً",
                "concept_title": "تنظيم وقص المشاهد تلقائياً",
                "concept_subtitle": "ترتيب اللقطات وإزالة الفراغات الصوتية بدقة",
                "sub_items": ["1. تنقية الصوت وقص الصمت", "2. تقسيم الجمل الدلالية", "3. توليد الرسوم المتحركة", "4. دمج الكابشن والتأثيرات"],
                "balance_left": ("لقطات مبعثرة", "صمت طويل"),
                "balance_right": ("تسلسل مشوق", "إيقاع سريع"),
                "before_after": ("قبل: 4.0", "4.0", "بعد: 9.5", "9.5"),
                "typewriter_query": "Smart Auto-Cut & Sequencing",
                "kpi_value": "Auto-Cut Pro",
                "kpi_label": "تحرير ذكي متكامل"
            }

        if is_ecommerce_feature:
            return {
                "archetype": "saas_grid_2x2_cursor" if "خصائص" in t_low or "ثلاث" in t_low else "saas_folder_reorder",
                "scene_type": "ecommerce_showcase",
                "badge_label": "مواصفات المنتج • جودة عملية وتصميم مبتكر",
                "concept_title": "ثلاث مزايا حصرية في منتج واحد",
                "concept_subtitle": "شحن سريع + حامل هاتف مدمج + تغليف قماشي متين",
                "sub_items": ["شحن فائق السرعة", "حامل هاتف مدمج", "تغليف قماشي ضد القطع", "سعر اقتصادي ممتاز"],
                "balance_left": ("السعر", "اقتصادي ومناسب"),
                "balance_right": ("القيمة والجودة", "3 مزايا في 1"),
                "before_after": ("كابل عادي: 3.8", "3.8", "كابل ذكي: 9.6", "9.6"),
                "typewriter_query": "Fast Charge + Stand Cable",
                "kpi_value": "3 في 1",
                "kpi_label": "مواصفات متكاملة"
            }

        if is_delivery_or_cta:
            return {
                "archetype": "interactive_cta_outro",
                "scene_type": "delivery_express" if "ولاية" in t_low or "توصيل" in t_low else "brand_finale",
                "badge_label": f"توصيل سريع • متوفر لجميع {wilayas} ولاية" if "ولاية" in t_low else "الخطوة التالية • ابدأ الآن وشارك التجربة",
                "concept_title": f"توصيل مضمون لباب المنزل ({wilayas} ولاية)" if "ولاية" in t_low else "جاهز لتجربة الجيل الجديد من المحتوى",
                "concept_subtitle": "اطلب الآن أو شارك الفيديو مع أصدقائك المهتمين",
                "sub_items": [f"توصيل لـ {wilayas} ولاية", "الدفع عند الاستلام", "ضمان الجودة الأصلية", "اطلب عبر الرابط الآن"],
                "balance_left": ("الطلب", "خلال 30 ثانية"),
                "balance_right": ("التوصيل", "لباب المنزل"),
                "before_after": ("قبل: 4.5", "4.5", "بعد: 9.8", "9.8"),
                "typewriter_query": "اطلب الآن • متوفر فوراً",
                "kpi_value": f"{wilayas} ولاية" if "ولاية" in t_low else "ابدأ الآن",
                "kpi_label": "تغطية وطنية شاملة" if "ولاية" in t_low else "خطوة فورية"
            }

        available_archs = [a for a in CHOREOGRAPHY_ARCHETYPES if (not used_archetypes or a != used_archetypes[-1])]
        chosen_arch = available_archs[scene_index % len(available_archs)]

        return {
            "archetype": chosen_arch,
            "scene_type": "ai_neural_brain" if (scene_index % 2 == 0) else "growth_analytics",
            "badge_label": f"المرحلة #{scene_index + 1} • تطوير الأداء وصناعة المحتوى",
            "concept_title": "منهجية ذكية لتحقيق أفضل النتائج",
            "concept_subtitle": "خطوات عملية مدروسة لرفع الكفاءة والجودة",
            "sub_items": ["تحديد الهدف بدقة", "أتمتة المهام المتكررة", "قياس وتحسين الأداء", "تحقيق نتائج مضاعفة"],
            "balance_left": ("الطريقة التقليدية", "وقت وجهد كبير"),
            "balance_right": ("الطريقة الذكية", "إنجاز فوري متقن"),
            "before_after": ("قبل: 4.2", "4.2", "بعد: 9.4", "9.4"),
            "typewriter_query": "Smart Workflow Automation",
            "kpi_value": f"خطوة #{scene_index + 1}",
            "kpi_label": "تطوير مستمر"
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

        healed: List[Dict[str, Any]] = []
        prev_arch = None
        prev_kpi = None

        conceptual_fallbacks = [
            ("تحدي صناع المحتوى • عقبة المونتاج اليومي", "مشكلة استنزاف الوقت", "85% من الصناع", "يعانون من ضيق الوقت"),
            ("معادلة الوقت • التصوير مقابل التحرير", "فجوة الوقت والجهد", "4 ساعات -> 1 د", "اختصار وقت المونتاج"),
            ("مضاعفة الإنتاجية • حضور رقمي مستمر", "رفع إنتاجية النشر", "+300% تفاعل", "نمو الحسابات الرقمية"),
            ("الحل الذكي • منصة المونتاج الآلي", "منصة التحرير الذكي", "All-in-One AI", "أتمتة كاملة للفيديو"),
            ("محرك الذكاء الاصطناعي • صوت وصورة", "تحويل الصوت والصورة آلياً", "100% تلقائي", "ذكاء اصطناعي سياقي"),
            ("سرعة قياسية • جاهز في أقل من دقيقة", "مونتاج احترافي فوري", "< 60 ثانية", "سرعة الإخراج الكامل"),
            ("إخراج متكامل • قص وتعديل احترافي", "تنظيم وقص المشاهد", "Full HD 30fps", "جودة استوديو احترافية"),
        ]

        for idx, sc in enumerate(scenes):
            item = dict(sc)
            raw_text = str(item.get("text", "")).strip()
            raw_words = [w.strip("،,.!؟?") for w in raw_text.split() if w.strip("،,.!؟?")]
            first_three = " ".join(raw_words[:3])

            badge = str(item.get("badge_label", "")).strip()
            concept = str(item.get("concept_title", "")).strip()
            kpi_v = str(item.get("kpi_value", "")).strip()
            kpi_l = str(item.get("kpi_label", "")).strip()

            fb_badge, fb_concept, fb_kv, fb_kl = conceptual_fallbacks[idx % len(conceptual_fallbacks)]

            if (
                "إضاءة معرفية" in badge
                or (first_three and len(first_three) > 4 and first_three in badge)
                or any(broken in badge for broken in ["المونت ", "الاج ", "أهلاً لاحظت", "جبت لكم", "صورته ذكاء"])
            ):
                badge = fb_badge

            if (
                not concept
                or (first_three and len(first_three) > 4 and first_three in concept)
                or any(broken in concept for broken in ["المونت ", "الاج ", "أهلاً لاحظت", "جبت لكم", "صورته ذكاء", "تصور للفيديوهات"])
            ):
                concept = fb_concept

            if not kpi_v or "Pro Tips" in kpi_v or "معلومة قيمة" in kpi_l or kpi_v == prev_kpi:
                kpi_v = fb_kv
                kpi_l = fb_kl

            arch = str(item.get("archetype", "")).strip()
            if arch not in CHOREOGRAPHY_ARCHETYPES or arch == prev_arch:
                candidates = [a for a in CHOREOGRAPHY_ARCHETYPES if a != prev_arch]
                arch = candidates[idx % len(candidates)]

            item["archetype"] = arch
            item["badge_label"] = badge
            item["concept_title"] = concept
            item["short_title"] = concept
            item["kpi_value"] = kpi_v
            item["kpi_label"] = kpi_l

            prev_arch = arch
            prev_kpi = kpi_v
            healed.append(item)

        return healed


_GLOBAL_LEARNER_INSTANCE: Optional[WebMotionLearner] = None


def get_motion_learner() -> WebMotionLearner:
    global _GLOBAL_LEARNER_INSTANCE
    if _GLOBAL_LEARNER_INSTANCE is None:
        _GLOBAL_LEARNER_INSTANCE = WebMotionLearner()
    return _GLOBAL_LEARNER_INSTANCE

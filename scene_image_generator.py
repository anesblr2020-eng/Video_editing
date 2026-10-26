# -*- coding: utf-8 -*-
"""
scene_image_generator.py — محرك توليد صور المشاهد السردية بالذكاء الاصطناعي (الإصدار v5)
=========================================================================================
الميزات الهندسية في الإصدار v5:
1. دمج `models/gemini-nano-banana-2.1` عبر `google.genai` (`client.interactions.create`) مع تمرير
   وصف المشهد الحقيقي الناتج من نظام تحليل الصوت/الفيديو، وإعدادات `image_config: {"image_size": "1K"}`
   و`response_modalities=["image", "text"]`.
2. الفصل الصارم بين مسار `Interactions API` (الخاص بنماذج Nano Banana) ومسار `generateContent`
   الخاص بالنماذج البديلة (`gemini-2.5-flash-image` وغيرها) مع منع إرسال طلبات `Nano Banana` إلى
   عنوان REST الخاص بـ `generateContent`.
3. استخراج متعدد الطبقات لبيانات الصورة من استجابات `Interactions API` أو `generateContent` مع التحقق
   الفعلي من أن البيانات المستخرجة تمثل صورة صالحة قابلة للفتح عبر `PIL.Image`، ورفض الاستجابات النصية فقط.
4. تشخيص وتصنيف ذكي لأخطاء `HTTP 429` وأخطاء المزود الأخرى:
   - التمييز بين نفاد الحصة الكلية/المجانية (`quota_exhausted` / `limit: 0`)، وحدود معدل الطلبات المؤقتة
     (`rate_limit_temporary`)، ومشكلات الفوترة أو الصلاحيات (`billing_or_permission`)، وعدم دعم النموذج
     أو الواجهة (`model_or_endpoint_unsupported`).
   - إيقاف المحاولات المتكررة غير المجدية فور اكتشاف نفاد الحصة (`limit: 0` أو `quota_exhausted`)
     لتجنب استهلاك الطلبات بلا فائدة، مع الانتقال المنطقي للنموذج البديل المهيأ فقط عند الحاجة.
5. نظام تخزين مؤقت (Cache) يحافظ على الصور الصحيحة المنشأة سابقاً ولا يعيد توليدها، ويسجل تقريراً شاملاً
   في `image_generation_report.json` وتفاصيل كل مشهد في `scene_image_prompts.json`.
"""
import os
import re
import json
import time
import base64
import hashlib
from io import BytesIO
from typing import Dict, Any, List, Optional, Tuple, Callable

import logging
import requests
from PIL import Image

logger = logging.getLogger(__name__)

try:
    from google import genai as google_genai_sdk
    _HAS_GOOGLE_GENAI_SDK = True
except Exception:
    google_genai_sdk = None
    _HAS_GOOGLE_GENAI_SDK = False

DEFAULT_PRIMARY_MODEL = "models/gemini-nano-banana-2.1"
DEFAULT_FALLBACK_MODELS = [
    "gemini-2.5-flash-image",
    "gemini-2.0-flash-preview-image-generation",
]
DEFAULT_IMAGE_SIZE = "1K"

GENERATE_CONTENT_REST_BASE = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
INTERACTIONS_REST_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"


# ==============================================================================
# 1. قراءة الإعدادات ومفتاح API من البيئة أو Streamlit Secrets بأمان
# ==============================================================================
def _get_secret_or_env(key: str, default: str = "") -> str:
    val = os.environ.get(key, "").strip()
    if val:
        return val
    try:
        import streamlit as st
        if hasattr(st, "secrets") and key in st.secrets:
            return str(st.secrets.get(key, "")).strip()
    except Exception:
        pass
    return default


def resolve_image_generation_config(api_key: str = "") -> Dict[str, Any]:
    """يقرأ مفتاح GEMINI_API_KEY وإعدادات النماذج وحجم الصورة من البيئة أو Streamlit Secrets."""
    resolved_key = (api_key or _get_secret_or_env("GEMINI_API_KEY", "")).strip()
    primary_model = _get_secret_or_env("GEMINI_IMAGE_MODEL", DEFAULT_PRIMARY_MODEL).strip() or DEFAULT_PRIMARY_MODEL
    image_size = _get_secret_or_env("GEMINI_IMAGE_SIZE", DEFAULT_IMAGE_SIZE).strip() or DEFAULT_IMAGE_SIZE
    cloud_project_id = _get_secret_or_env("GOOGLE_CLOUD_PROJECT", "gen-lang-client-0998760040").strip()

    raw_fallbacks = _get_secret_or_env("GEMINI_FALLBACK_IMAGE_MODELS", "")
    if raw_fallbacks:
        fallbacks = [m.strip() for m in raw_fallbacks.split(",") if m.strip()]
    else:
        fallbacks = list(DEFAULT_FALLBACK_MODELS)

    # بناء سلسلة النماذج بدون تكرار مع ضمان وجود Nano Banana 2.1 في المقدمة ما لم يحدد المستخدم غير ذلك
    model_chain: List[str] = []
    for m in [primary_model] + fallbacks:
        if m and m not in model_chain:
            model_chain.append(m)

    hf_token = (_get_secret_or_env("HF_TOKEN", "") or _get_secret_or_env("HUGGINGFACE_API_KEY", "")).strip()
    enable_free_fallback = _get_secret_or_env("ENABLE_FREE_IMAGE_FALLBACK", "1").strip().lower() not in ("0", "false", "no")

    max_attempts_per_model = max(1, min(2, int(_get_secret_or_env("GEMINI_MAX_ATTEMPTS_PER_MODEL", "1") or "1")))
    return {
        "api_key": resolved_key,
        "hf_token": hf_token,
        "enable_free_fallback": enable_free_fallback,
        "primary_model": primary_model,
        "fallback_models": [m for m in model_chain if m != primary_model],
        "model_chain": model_chain,
        "image_size": image_size,
        "cloud_project_id": cloud_project_id,
        "max_attempts_per_model": max_attempts_per_model,
    }


def is_interactions_api_model(model_name: str) -> bool:
    """
    يحدد ما إذا كان النموذج يتطلب واجهة Interactions API (مثل Nano Banana 2.1)
    بحيث يُمنع إرساله إلى عنوان REST الخاص بـ generateContent.
    """
    m_low = str(model_name or "").strip().lower()
    return ("nano-banana" in m_low) or ("interactions:" in m_low)


def normalize_model_identifier(model_name: str, for_interactions: bool = False) -> str:
    m = str(model_name or "").strip()
    if m.startswith("interactions:"):
        m = m.split("interactions:", 1)[1].strip()
    if for_interactions:
        if not m.startswith("models/"):
            return f"models/{m}"
        return m
    # في generateContent REST URI يوضع اسم النموذج بدون بادئة models/ المزدوجة
    if m.startswith("models/"):
        return m[len("models/"):]
    return m


# ==============================================================================
# 2. التحقق من صلاحية الصورة وحفظها وتطبيع أبعادها (9:16)
# ==============================================================================
def validate_and_save_scene_image(data: bytes, path: str, min_dim: int = 128) -> Tuple[bool, str]:
    """
    يتحقق من أن البايتات المستخرجة تمثل صورة حقيقية قابلة للفتح عبر PIL،
    ويطبّعها إلى أبعاد عمودية (9:16) ويحفظها في مجلد المشهد المناسب.
    """
    if not data or not isinstance(data, (bytes, bytearray)) or len(data) < 64:
        return False, "empty_or_too_small_image_bytes"
    try:
        bio_verify = BytesIO(data)
        with Image.open(bio_verify) as im_verify:
            im_verify.verify()

        bio_load = BytesIO(data)
        with Image.open(bio_load) as im_raw:
            im = im_raw.convert("RGB")
            w, h = im.size
            if w < min_dim or h < min_dim:
                return False, f"image_dimensions_too_small_{w}x{h}"

            target_ratio = 9.0 / 16.0
            if (w / float(h)) > target_ratio:
                nw = max(1, int(round(h * target_ratio)))
                left = (w - nw) // 2
                im = im.crop((left, 0, left + nw, h))
            else:
                nh = max(1, int(round(w / target_ratio)))
                top = (h - nh) // 2
                im = im.crop((0, top, w, top + nh))

            im = im.resize((768, 1365), Image.Resampling.LANCZOS)
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
            im.save(path, "JPEG", quality=92, optimize=True)

        if not os.path.isfile(path) or os.path.getsize(path) < 1024:
            return False, "saved_file_missing_or_empty"
        return True, "ok"
    except Exception as exc:
        return False, f"invalid_image_data: {str(exc)[:180]}"


def is_existing_valid_image_file(path: Optional[str]) -> bool:
    """يتحقق مما إذا كانت الصورة المخزنة سابقاً موجودة وصالحة للفتح حتى لا نعيد توليدها."""
    if not path or not os.path.isfile(path):
        return False
    try:
        if os.path.getsize(path) < 1024:
            return False
        with Image.open(path) as im:
            im.verify()
        return True
    except Exception:
        return False


# ==============================================================================
# 3. استخراج الصورة الفعلية من استجابات Interactions API و generateContent
# ==============================================================================
def _decode_candidate_bytes(raw_val: Any) -> Optional[bytes]:
    if raw_val is None:
        return None
    if isinstance(raw_val, bytes):
        return raw_val if len(raw_val) >= 64 else None
    if isinstance(raw_val, bytearray):
        return bytes(raw_val) if len(raw_val) >= 64 else None
    if isinstance(raw_val, str):
        s = raw_val.strip()
        if not s:
            return None
        if s.startswith("data:image/") and "," in s:
            s = s.split(",", 1)[1].strip()
        try:
            decoded = base64.b64decode(s, validate=False)
            if decoded and len(decoded) >= 64:
                return decoded
        except Exception:
            return None
    return None


def extract_image_bytes_from_response(resp_obj: Any) -> Tuple[Optional[bytes], Optional[str], str]:
    """
    يستخرج بايتات الصورة الفعلية من استجابة Google GenAI (سواء كانت كائن SDK من Interactions API،
    أو generate_content، أو قاموس JSON من REST API).
    يُرجع: (image_bytes, text_only_snippet, extraction_note).
    إذا أعادت الواجهة استجابة نصية فقط، يعيد image_bytes=None مع النص المستخرج لتسجيل ذلك كفشل واضح.
    """
    if resp_obj is None:
        return None, None, "null_response_object"

    collected_texts: List[str] = []

    def _walk(node: Any, depth: int = 0) -> Optional[bytes]:
        if depth > 12 or node is None:
            return None

        # 1. إذا كان الكائن يحتوي على دالة تحويل إلى قاموس في SDK (`model_dump` أو `to_dict`)
        if not isinstance(node, (dict, list, tuple, str, bytes, bytearray, int, float, bool)):
            for attr_img in ("image_bytes", "data", "bytes", "raw_bytes"):
                if hasattr(node, attr_img):
                    cand_b = _decode_candidate_bytes(getattr(node, attr_img))
                    if cand_b:
                        return cand_b
            for attr_inline in ("inline_data", "inlineData", "image", "blob", "media"):
                if hasattr(node, attr_inline):
                    res_b = _walk(getattr(node, attr_inline), depth + 1)
                    if res_b:
                        return res_b
            if hasattr(node, "text") and isinstance(getattr(node, "text"), str) and getattr(node, "text").strip():
                collected_texts.append(getattr(node, "text").strip())
            for container_attr in ("outputs", "output", "candidates", "parts", "content", "contents", "items", "messages", "result", "response", "generated_images"):
                if hasattr(node, container_attr):
                    res_b = _walk(getattr(node, container_attr), depth + 1)
                    if res_b:
                        return res_b
            if hasattr(node, "model_dump") and callable(node.model_dump):
                try:
                    return _walk(node.model_dump(), depth + 1)
                except Exception:
                    pass
            if hasattr(node, "to_dict") and callable(node.to_dict):
                try:
                    return _walk(node.to_dict(), depth + 1)
                except Exception:
                    pass
            if hasattr(node, "__dict__"):
                try:
                    return _walk(vars(node), depth + 1)
                except Exception:
                    pass
            return None

        # 2. إذا كان قاموساً (Dict)
        if isinstance(node, dict):
            # نلتقط أي نص أعيد في الاستجابة لتشخيص حالة "نص فقط بدون صورة"
            if isinstance(node.get("text"), str) and node["text"].strip():
                collected_texts.append(node["text"].strip())

            # فحص الحقول المباشرة لبيانات الصورة (inlineData / inline_data / image / b64_json / data)
            for k_inline in ("inlineData", "inline_data", "image", "blob", "image_data", "media"):
                if k_inline in node and node[k_inline] is not None:
                    sub = node[k_inline]
                    if isinstance(sub, dict):
                        for k_d in ("data", "image_bytes", "bytes", "b64_json", "base64"):
                            if k_d in sub:
                                cand_b = _decode_candidate_bytes(sub[k_d])
                                if cand_b:
                                    return cand_b
                    else:
                        res_b = _walk(sub, depth + 1)
                        if res_b:
                            return res_b

            # إذا كان العقد نفسه يمثل مخرج صورة في Interactions API (مثلاً {"type": "image", "data": ...} أو {"mime_type": "image/...", "data": ...})
            mime_val = str(node.get("mime_type") or node.get("mimeType") or node.get("type") or "").lower()
            if "image" in mime_val or "data" in node or "image_bytes" in node or "b64_json" in node:
                for k_d in ("data", "image_bytes", "bytes", "b64_json", "base64"):
                    if k_d in node:
                        cand_b = _decode_candidate_bytes(node[k_d])
                        if cand_b:
                            return cand_b

            # البحث في الحاويات المتفرعة بالترتيب
            for k_child in ("outputs", "output", "candidates", "content", "contents", "parts", "generated_images", "items", "result", "response", "messages"):
                if k_child in node:
                    res_b = _walk(node[k_child], depth + 1)
                    if res_b:
                        return res_b

            for k, v in node.items():
                if k not in ("text", "prompt", "input", "model"):
                    res_b = _walk(v, depth + 1)
                    if res_b:
                        return res_b
            return None

        # 3. إذا كان قائمة أو Tuple
        if isinstance(node, (list, tuple)):
            for item in node:
                res_b = _walk(item, depth + 1)
                if res_b:
                    return res_b
            return None

        return None

    img_bytes = _walk(resp_obj, 0)
    text_summary = " | ".join(dict.fromkeys(collected_texts))[:300] if collected_texts else None
    if img_bytes:
        return img_bytes, text_summary, "image_bytes_extracted"
    if text_summary:
        return None, text_summary, f"text_only_response_no_image: {text_summary[:160]}"
    return None, None, "no_image_or_text_found_in_response_structure"


# ==============================================================================
# 4. تشخيص وتصنيف أخطاء HTTP 429 وأخطاء المزود بدقة
# ==============================================================================
def classify_provider_error(raw_error: Any, status_code: Optional[int] = None) -> Dict[str, Any]:
    """
    يحلل رسالة الخطأ الأصلية التي يعيدها مزود Google GenAI ويميز بين:
    1. `quota_exhausted_zero_limit`: الحصة = 0 أو نفاد الحصة اليومية/المجانية تماماً للمشروع/النموذج.
    2. `rate_limit_temporary`: تجاوز معدل الطلبات في الدقيقة (RPM/TPM) مع إمكانية المحاولة بعد فترة قصيرة.
    3. `billing_or_permission_denied`: مشكلة في تفعيل الفوترة (Billing) أو صلاحيات مفتاح API أو المشروع.
    4. `model_or_endpoint_unsupported`: النموذج غير مدعوم على هذه الواجهة أو غير متاح في المنطقة/الحساب.
    5. `network_or_timeout`: خطأ اتصال بالشبكة أو انتهاء المهلة.
    """
    msg = str(raw_error or "").strip()
    msg_low = msg.lower()

    detected_code = status_code
    if detected_code is None:
        m_code = re.search(r"\b(400|401|403|404|429|500|502|503|504)\b", msg)
        if m_code:
            detected_code = int(m_code.group(1))

    retry_after_sec: Optional[float] = None
    m_retry = re.search(r"retry\s*(?:in|after|delay)[^\d]*(\d+(?:\.\d+)?)\s*s", msg_low)
    if not m_retry:
        m_retry = re.search(r'"retrydelay"\s*:\s*"(\d+(?:\.\d+)?)s"', msg_low)
    if m_retry:
        try:
            retry_after_sec = float(m_retry.group(1))
        except Exception:
            retry_after_sec = None

    # 1. فحص HTTP 429 / RESOURCE_EXHAUSTED / Quota exceeded
    if detected_code == 429 or "429" in msg_low or "resource_exhausted" in msg_low or "quota" in msg_low:
        is_hard_zero_quota = any(
            pat in msg_low
            for pat in [
                "limit: 0",
                "limit:0",
                "quota_value: 0",
                "free_tier",
                "check your plan and billing",
                "billing details",
                "daily limit",
                "per day",
                "quota exceeded for quota metric",
            ]
        )
        if is_hard_zero_quota and retry_after_sec is None:
            return {
                "status_code": 429,
                "category": "quota_exhausted_or_billing_tier",
                "should_retry_same_model": False,
                "should_try_fallback_model": True,
                "retry_after_sec": None,
                "original_error": msg[:500],
                "diagnosis_ar": (
                    "خطأ HTTP 429 (نفاد الحصة أو الحصة المخصصة للمشروع تساوي 0 لهذا النموذج على واجهة API). "
                    "نجاح التوليد داخل واجهة Google AI Studio التفاعلية يستخدم حصة الواجهة المستقلة ولا يعني "
                    "أن مفتاح API المرتبط بالمشروع لديه نفس الحصة المجانية لتوليد الصور عبر الكود."
                ),
            }
        return {
            "status_code": 429,
            "category": "rate_limit_or_quota_429",
            "should_retry_same_model": bool(retry_after_sec and retry_after_sec <= 5.0),
            "should_try_fallback_model": True,
            "retry_after_sec": retry_after_sec,
            "original_error": msg[:500],
            "diagnosis_ar": (
                "خطأ HTTP 429 (تجاوز حد الطلبات أو نفاد الحصة المتاحة للنموذج). "
                "لن يعيد النظام إغراق نفس النموذج بطلبات متكررة، وسينتقل للنموذج البديل المهيأ مرة واحدة فقط."
            ),
        }

    # 2. فحص الصلاحيات والفوترة (401 / 403)
    if detected_code in (401, 403) or any(k in msg_low for k in ["permission_denied", "api_key_invalid", "invalid api key", "billing", "forbidden", "unauthenticated"]):
        return {
            "status_code": detected_code or 403,
            "category": "billing_or_permission_denied",
            "should_retry_same_model": False,
            "should_try_fallback_model": False,
            "retry_after_sec": None,
            "original_error": msg[:500],
            "diagnosis_ar": (
                "رفض الصلاحية أو الفوترة (HTTP 401/403): مفتاح GEMINI_API_KEY غير صالح أو أن مشروع Google Cloud "
                "غير مفعل به حساب فوترة (Billing) أو صلاحية Generative Language API."
            ),
        }

    # 3. فحص عدم دعم النموذج أو نقطة النهاية (404 / 400)
    if detected_code in (400, 404) or any(k in msg_low for k in ["not found", "not supported", "invalid_argument", "unsupported", "unknown model"]):
        return {
            "status_code": detected_code or 404,
            "category": "model_or_endpoint_unsupported",
            "should_retry_same_model": False,
            "should_try_fallback_model": True,
            "retry_after_sec": None,
            "original_error": msg[:500],
            "diagnosis_ar": (
                "النموذج أو أسلوب الاستدعاء غير مدعوم على هذا الحساب/الإصدار (HTTP 400/404). "
                "سيتم الانتقال تلقائياً إلى النموذج البديل."
            ),
        }

    # 4. استجابة نصية فقط بدون صورة
    if "text_only_response_no_image" in msg_low:
        return {
            "status_code": 200,
            "category": "text_only_response_no_image",
            "should_retry_same_model": False,
            "should_try_fallback_model": True,
            "retry_after_sec": None,
            "original_error": msg[:500],
            "diagnosis_ar": "أعادت الواجهة استجابة نصية فقط بدون بيانات صورة؛ لا تُحتسب هذه العملية كنجاح.",
        }

    return {
        "status_code": detected_code,
        "category": "provider_or_network_error",
        "should_retry_same_model": False,
        "should_try_fallback_model": True,
        "retry_after_sec": None,
        "original_error": msg[:500],
        "diagnosis_ar": f"خطأ أثناء الاتصال بمزود الصور: {msg[:220]}",
    }


# ==============================================================================
# 5. مسارات الاتصال الفعلية: Interactions API (Nano Banana 2.1) و generateContent
# ==============================================================================
def invoke_nano_banana_interactions_api(
    prompt: str,
    api_key: str,
    model_name: str = DEFAULT_PRIMARY_MODEL,
    image_size: str = DEFAULT_IMAGE_SIZE,
    sdk_client: Any = None,
    session: Optional[requests.Session] = None,
) -> Tuple[Optional[bytes], Dict[str, Any]]:
    """
    ينفذ طلب توليد الصورة لنموذج `models/gemini-nano-banana-2.1` عبر `Interactions API` حصرياً:
    1. إذا تم تمرير `sdk_client` صريح (أو فُعّل `GEMINI_USE_SDK_TRANSPORT=1`)، يستخدم `client.interactions.create(...)`.
    2. في التشغيل السحابي المباشر، يستخدم نقطة نهاية `Interactions REST API` (`/v1beta/interactions`) مباشرة عبر `requests`
       لتجنب حلقة `tenacity` الداخلية في `google-genai` التي تعلّق التنفيذ لعدة دقائق عند حدوث `HTTP 429`!
    """
    norm_model = normalize_model_identifier(model_name, for_interactions=True)
    meta = {
        "model": norm_model,
        "api_surface": "interactions_api",
        "image_size": image_size,
        "sdk_available": _HAS_GOOGLE_GENAI_SDK,
    }

    use_sdk = sdk_client is not None or str(os.environ.get("GEMINI_USE_SDK_TRANSPORT", "0")).strip() in ("1", "true")
    if use_sdk:
        client = sdk_client
        if client is None and _HAS_GOOGLE_GENAI_SDK and google_genai_sdk is not None:
            try:
                client = google_genai_sdk.Client(api_key=api_key, http_options={"timeout": 25000})
            except Exception:
                try:
                    client = google_genai_sdk.Client(api_key=api_key)
                except Exception:
                    client = None

        if client is not None and hasattr(client, "interactions") and hasattr(client.interactions, "create"):
            meta["transport"] = "google_genai_sdk_interactions"
            interaction = client.interactions.create(
                model=norm_model,
                input=prompt,
                generation_config={
                    "image_config": {
                        "image_size": image_size
                    }
                },
                response_modalities=["image", "text"],
            )
            img_bytes, txt_only, note = extract_image_bytes_from_response(interaction)
            meta["extraction_note"] = note
            if txt_only:
                meta["text_response"] = txt_only
            if not img_bytes:
                raise RuntimeError(f"Interactions SDK returned no valid image ({note})")
            return img_bytes, meta

    # المسار المباشر المضمون ضد التعليق (Zero-Retry Hang): Interactions REST API (/v1beta/interactions)
    meta["transport"] = "interactions_rest_v1beta"
    sess = session or requests.Session()
    payload = {
        "model": norm_model,
        "input": prompt,
        "generation_config": {
            "image_config": {
                "image_size": image_size
            }
        },
        "response_modalities": ["image", "text"],
    }
    resp = sess.post(
        INTERACTIONS_REST_URL,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=payload,
        timeout=(8, 25),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} (Interactions API - {norm_model}): {resp.text[:450]}")

    data_json = resp.json()
    img_bytes, txt_only, note = extract_image_bytes_from_response(data_json)
    meta["extraction_note"] = note
    if txt_only:
        meta["text_response"] = txt_only
    if not img_bytes:
        raise RuntimeError(f"Interactions REST returned no valid image ({note})")
    return img_bytes, meta


def invoke_generate_content_image_api(
    prompt: str,
    api_key: str,
    model_name: str,
    image_size: str = DEFAULT_IMAGE_SIZE,
    sdk_client: Any = None,
    session: Optional[requests.Session] = None,
) -> Tuple[Optional[bytes], Dict[str, Any]]:
    """
    ينفذ طلب توليد الصورة للنماذج البديلة التي تستخدم `generateContent`
    (مثل `gemini-2.5-flash-image` و `gemini-2.0-flash-preview-image-generation`).
    """
    if is_interactions_api_model(model_name):
        raise ValueError(f"Security/Routing Guard: Model '{model_name}' requires Interactions API and must NEVER be sent to generateContent!")

    clean_model = normalize_model_identifier(model_name, for_interactions=False)
    meta = {
        "model": clean_model,
        "api_surface": "generateContent",
        "image_size": image_size,
    }

    # محاولة عبر SDK models.generate_content إذا تم تمرير عميل SDK جاهز يدعمها، أو عبر REST القياسي الموثوق
    if sdk_client is not None and hasattr(sdk_client, "models") and hasattr(sdk_client.models, "generate_content"):
        try:
            meta["transport"] = "google_genai_sdk_generate_content"
            sdk_resp = sdk_client.models.generate_content(
                model=clean_model,
                contents=prompt,
                config={"response_modalities": ["TEXT", "IMAGE"]},
            )
            img_bytes, txt_only, note = extract_image_bytes_from_response(sdk_resp)
            meta["extraction_note"] = note
            if txt_only:
                meta["text_response"] = txt_only
            if img_bytes:
                return img_bytes, meta
        except Exception as sdk_err:
            # إذا كان الخطأ من المزود (مثل 429 أو 403 أو 404) نعيد رفعه ليُصنّف فوراً دون تكرار الطلب عبر REST!
            err_str = str(sdk_err)
            if any(code in err_str for code in ("429", "401", "403", "404", "RESOURCE_EXHAUSTED", "Quota", "quota")):
                raise RuntimeError(f"SDK generateContent ({clean_model}): {err_str[:450]}") from sdk_err

    meta["transport"] = "generate_content_rest_v1beta"
    sess = session or requests.Session()
    url = GENERATE_CONTENT_REST_BASE.format(model=clean_model)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
    }
    resp = sess.post(
        url,
        headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
        json=body,
        timeout=(10, 35),
    )
    if resp.status_code >= 400:
        raise RuntimeError(f"HTTP {resp.status_code} (generateContent - {clean_model}): {resp.text[:450]}")

    result = resp.json()
    img_bytes, txt_only, note = extract_image_bytes_from_response(result)
    meta["extraction_note"] = note
    if txt_only:
        meta["text_response"] = txt_only
    if not img_bytes:
        raise RuntimeError(f"generateContent returned no valid image ({note})")
    return img_bytes, meta




def invoke_free_cloud_image_fallback(
    prompt: str,
    scene_idx: int = 1,
    hf_token: str = "",
    session: Optional[requests.Session] = None,
) -> Tuple[Optional[bytes], Dict[str, Any]]:
    """
    مزود مجاني 100% بدون بطاقة بنكية وبدون حساب فوترة Google Cloud (لمستخدمي الجزائر والمناطق غير المدعومة في Free Tier):
    1. إذا وُفر `HF_TOKEN` مجاني من Hugging Face، يستخدم `FLUX.1-schnell` عبر Hugging Face Inference API.
    2. يعمل تلقائياً بدون أي مفتاح عبر محرك `Pollinations Flux` السحابي (`image.pollinations.ai`) بتوليد صورة عمودية 9:16 (768x1344) حقيقية لكل مشهد!
    """
    import urllib.parse
    sess = session or requests.Session()
    seed = int(hashlib.md5(f"{scene_idx}_{prompt}".encode("utf-8")).hexdigest()[:8], 16) % 999999

    # 1. المحاولة عبر Hugging Face Free Inference API (إن وضع المستخدم HF_TOKEN مجاني)
    if hf_token:
        hf_models = [
            "black-forest-labs/FLUX.1-schnell",
            "stabilityai/stable-diffusion-xl-base-1.0",
        ]
        for hfm in hf_models:
            try:
                hf_url = f"https://router.huggingface.co/hf-inference/models/{hfm}"
                r_hf = sess.post(
                    hf_url,
                    headers={"Authorization": f"Bearer {hf_token}", "Accept": "image/jpeg"},
                    json={"inputs": prompt},
                    timeout=(8, 28),
                )
                if r_hf.status_code == 200 and r_hf.content and len(r_hf.content) > 2048:
                    return r_hf.content, {
                        "model": f"hf/{hfm}",
                        "api_surface": "huggingface_free_inference",
                        "image_size": "768x1344",
                    }
            except Exception as hf_e:
                logger.debug(f"HF fallback notice ({hfm}): {hf_e}")

    # 2. المحاولة المجانية بدون مفتاح نهائياً عبر Pollinations Flux (9:16 Portrait)
    clean_p = " ".join(prompt.split())[:420]
    encoded_p = urllib.parse.quote(clean_p)
    for model_slug in ("flux", "turbo"):
        pol_url = (
            f"https://image.pollinations.ai/prompt/{encoded_p}"
            f"?width=768&height=1344&seed={seed}&model={model_slug}&nologo=true"
        )
        try:
            r_pol = sess.get(
                pol_url,
                headers={"User-Agent": "Mozilla/5.0 (compatible; StudioV5/1.0)"},
                timeout=(8, 28),
            )
            if r_pol.status_code == 200 and r_pol.content and len(r_pol.content) > 2048:
                return r_pol.content, {
                    "model": f"pollinations/{model_slug}-free",
                    "api_surface": "pollinations_free_api",
                    "image_size": "768x1344",
                }
        except Exception as pol_e:
            logger.debug(f"Pollinations fallback notice ({model_slug}): {pol_e}")

    raise RuntimeError("تعذر جلب الصورة من المزودات المجانية البديلة (Pollinations / HuggingFace)")


# ==============================================================================
# 6. الدالة الرئيسية لتوليد صور المشاهد مع إدارة الكاش والحصص والتقارير
# ==============================================================================
def build_quota_and_cloud_checklist(project_id: str = "gen-lang-client-0998760040") -> Dict[str, Any]:
    """يرجع قائمة فحص تقنية واضحة للمستخدم عند حدوث أخطاء HTTP 429 أو مشاكل الفوترة والحصص."""
    return {
        "google_cloud_project_id": project_id,
        "why_ai_studio_differs_from_api": (
            "توليد الصور داخل واجهة الويب في Google AI Studio يستهلك من حصة الواجهة التفاعلية لحسابك، "
            "بينما الطلبات البرمجية عبر GEMINI_API_KEY من المنصة تستهلك من حصة الـ API الخاصة بالمشروع "
            f"({project_id}). في طبقة Free Tier للـ API، تكون حصة توليد الصور لعدد من النماذج مضبوطة على 0 (limit: 0) "
            "إلا بعد ربط حساب فوترة (Billing Account) وتفعيل Tier 1."
        ),
        "steps_to_verify": [
            f"1. التأكد في Google AI Studio (قسم API Keys) من أن المفتاح المستخدم في GEMINI_API_KEY تابع للمشروع '{project_id}' تحديداً.",
            f"2. الدخول إلى Google Cloud Console للمشروع '{project_id}' -> Billing، والتأكد من ربط حساب فوترة نشط (Pay-as-you-go / Tier 1) لأن طبقة Free Tier تمنح limit: 0 لتوليد الصور عبر الـ API في معظم المناطق.",
            "3. فتح صفحة IAM & Admin -> Quotas & System Limits في Google Cloud، وتصفية الخدمة على 'Generative Language API' للتحقق من أن حصة الطلبات في الدقيقة/اليوم لنموذج الصور أكبر من 0.",
            "4. التأكد في Streamlit Cloud -> App Settings -> Secrets من كتابة GEMINI_API_KEY بشكل صحيح دون مسافات إضافية، وتمرير GEMINI_IMAGE_MODEL و GEMINI_IMAGE_SIZE عند الرغبة.",
        ],
    }


def generate_scene_images(
    out_dir: str,
    prompts_path: str,
    api_key: str = "",
    progress: Optional[Callable[[float, str], None]] = None,
    sdk_client: Any = None,
    session: Optional[requests.Session] = None,
) -> Dict[str, Any]:
    """
    ينشئ صور المشاهد اعتماداً على وصف كل مشهد في `scene_image_prompts.json`،
    مع البدء بـ `models/gemini-nano-banana-2.1` عبر `Interactions API` ثم الانتقال المدروس
    إلى النماذج البديلة عبر `generateContent`، مع حماية الكاش وعدم تكرار الطلبات الفاشلة عند نفاد الحصة.
    """
    cfg = resolve_image_generation_config(api_key=api_key)
    resolved_key = cfg["api_key"]
    model_chain: List[str] = cfg["model_chain"]
    image_size = cfg["image_size"]
    project_id = cfg["cloud_project_id"]

    report: Dict[str, Any] = {
        "version": "v5",
        "enabled": bool(resolved_key),
        "project_id": project_id,
        "primary_model": cfg["primary_model"],
        "fallback_models": cfg["fallback_models"],
        "model_chain": model_chain,
        "image_size": image_size,
        "total_scenes": 0,
        "generated": 0,
        "cached": 0,
        "failed": 0,
        "models_succeeded": {},
        "models_failed": {},
        "scene_results": [],
        "errors": [],
        "reason": None,
        "troubleshooting_guide": None,
    }

    os.makedirs(out_dir, exist_ok=True)
    report_path = os.path.join(out_dir, "image_generation_report.json")

    if not os.path.exists(prompts_path):
        report["reason"] = "scene prompts file not found"
        with open(report_path, "w", encoding="utf-8") as rf:
            json.dump(report, rf, ensure_ascii=False, indent=2)
        return report

    with open(prompts_path, "r", encoding="utf-8") as f:
        payload = json.load(f)

    scenes: List[Dict[str, Any]] = payload.get("scenes", [])
    report["total_scenes"] = len(scenes)
    image_dir = os.path.join(out_dir, "scene_images")
    os.makedirs(image_dir, exist_ok=True)
    report["image_dir"] = image_dir

    # فحص الصور المخزنة مسبقاً أولاً حتى تعمل المنصة بالكاش المتاح حتى لو لم يتوفر مفتاح جديد
    uncached_indices: List[int] = []
    for i, scene in enumerate(scenes):
        scene_idx = int(scene.get("scene_index", i + 1))
        prompt = str(scene.get("image_prompt") or "").strip()
        if not prompt:
            scene["image_path"] = None
            scene["generation_status"] = "failed"
            scene["error"] = "empty_scene_image_prompt"
            scene["error_category"] = "invalid_prompt"
            report["failed"] += 1
            report["scene_results"].append({
                "scene_index": scene_idx,
                "status": "failed",
                "model_used": None,
                "error": "empty_scene_image_prompt",
            })
            continue

        # 1. هل للمشهد مسار صورة صالح محفوظ مسبقاً؟
        existing_path = scene.get("image_path")
        if is_existing_valid_image_file(existing_path):
            scene["generation_status"] = "cached"
            scene["model_used"] = scene.get("model_used") or "cached_existing"
            scene["error"] = None
            report["cached"] += 1
            report["scene_results"].append({
                "scene_index": scene_idx,
                "status": "cached",
                "model_used": scene["model_used"],
                "image_path": existing_path,
            })
            continue

        # 2. هل توجد صورة مطابقة لهاش المطالبة في مجلد scene_images من تشغيل سابق؟
        prompt_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:20]
        canonical_cache_path = os.path.join(image_dir, f"scene_{scene_idx:03d}_{prompt_digest}.jpg")
        # دعم التوافق مع الكاش القديم الذي كان يدخل اسم النموذج في الهاش
        legacy_found_path = None
        if is_existing_valid_image_file(canonical_cache_path):
            legacy_found_path = canonical_cache_path
        else:
            for m_cand in model_chain:
                leg_digest = hashlib.sha256((m_cand + prompt).encode("utf-8")).hexdigest()[:20]
                leg_path = os.path.join(image_dir, f"scene_{scene_idx:03d}_{leg_digest}.jpg")
                if is_existing_valid_image_file(leg_path):
                    legacy_found_path = leg_path
                    break

        if legacy_found_path:
            scene["image_path"] = legacy_found_path
            scene["generation_status"] = "cached"
            scene["model_used"] = scene.get("model_used") or "cached_by_hash"
            scene["error"] = None
            report["cached"] += 1
            report["scene_results"].append({
                "scene_index": scene_idx,
                "status": "cached",
                "model_used": scene["model_used"],
                "image_path": legacy_found_path,
            })
            continue

        uncached_indices.append(i)

    # إذا كانت كل المشاهد مسترجعة من الكاش بنجاح، لا نرسل أي طلب خارجي!
    if not uncached_indices:
        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        with open(report_path, "w", encoding="utf-8") as rf:
            json.dump(report, rf, ensure_ascii=False, indent=2)
        return report

    hf_token = cfg.get("hf_token", "")
    # لا نسمح بالمزود المجاني بدون مفتاح إلا في التشغيل السحابي الحقيقي (عندما لا يكون في وضع اختبار معزول بـ session/sdk_client وهمي)
    allow_free_fallback = bool(
        cfg.get("enable_free_fallback", True)
        and sdk_client is None
        and session is None
    )

    if not resolved_key and not allow_free_fallback:
        for i in uncached_indices:
            sc = scenes[i]
            sc["image_path"] = None
            sc["generation_status"] = "failed"
            sc["error"] = "GEMINI_API_KEY not configured"
            sc["error_category"] = "missing_api_key"
            report["failed"] += 1
            report["scene_results"].append({
                "scene_index": int(sc.get("scene_index", i + 1)),
                "status": "failed",
                "model_used": None,
                "error": "GEMINI_API_KEY not configured",
            })
        report["reason"] = "GEMINI_API_KEY not configured"
        report["troubleshooting_guide"] = build_quota_and_cloud_checklist(project_id)
        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        with open(report_path, "w", encoding="utf-8") as rf:
            json.dump(report, rf, ensure_ascii=False, indent=2)
        return report

    # تهيئة جلسة HTTP وعميل google.genai مرة واحدة
    http_session = session or requests.Session()
    # لا نمرر عميل google-genai التلقائي إلا إذا طُلب صراحة لتفادي تعليق tenacity الداخلي عند أخطاء 429
    active_sdk_client = sdk_client

    # قائمة النماذج التي ثبت نفاد حصتها أو عدم صلاحيتها في هذه الجلسة لمنع تكرار استدعائها في المشاهد التالية!
    exhausted_or_blocked_models: Dict[str, Dict[str, Any]] = {}
    global_auth_abort: Optional[Dict[str, Any]] = None

    for pos, i in enumerate(uncached_indices):
        scene = scenes[i]
        scene_idx = int(scene.get("scene_index", i + 1))
        prompt = str(scene.get("image_prompt") or "").strip()
        prompt_digest = hashlib.sha256(prompt.encode("utf-8")).hexdigest()[:20]
        target_path = os.path.join(image_dir, f"scene_{scene_idx:03d}_{prompt_digest}.jpg")

        if global_auth_abort is not None:
            scene["image_path"] = None
            scene["generation_status"] = "failed"
            scene["error"] = global_auth_abort["original_error"]
            scene["error_category"] = global_auth_abort["category"]
            report["failed"] += 1
            report["scene_results"].append({
                "scene_index": scene_idx,
                "status": "failed",
                "model_used": None,
                "error_category": global_auth_abort["category"],
                "error": global_auth_abort["original_error"],
            })
            continue

        scene_succeeded = False
        scene_attempt_errors: List[Dict[str, Any]] = []

        for model_name in (model_chain if resolved_key else []):
            if model_name in exhausted_or_blocked_models:
                # لا نعيد ضرب نموذج ثبت أن حصته مستنفدة (429) أو غير مدعوم في المشهد السابق!
                prev_err_info = exhausted_or_blocked_models[model_name]
                scene_attempt_errors.append({
                    "model": model_name,
                    "skipped_due_to_previous_exhaustion": True,
                    "category": prev_err_info["category"],
                    "error": prev_err_info["original_error"],
                })
                continue

            use_interactions = is_interactions_api_model(model_name)
            surface_label = "interactions_api" if use_interactions else "generateContent"
            logger.info(f"[v5 ImageGen] المشهد #{scene_idx}: محاولة النموذج {model_name} عبر {surface_label}...")

            try:
                if use_interactions:
                    img_bytes, call_meta = invoke_nano_banana_interactions_api(
                        prompt=prompt,
                        api_key=resolved_key,
                        model_name=model_name,
                        image_size=image_size,
                        sdk_client=active_sdk_client,
                        session=http_session,
                    )
                else:
                    img_bytes, call_meta = invoke_generate_content_image_api(
                        prompt=prompt,
                        api_key=resolved_key,
                        model_name=model_name,
                        image_size=image_size,
                        sdk_client=active_sdk_client,
                        session=http_session,
                    )

                ok_img, save_note = validate_and_save_scene_image(img_bytes, target_path)
                if not ok_img:
                    raise RuntimeError(f"Image validation failed for {model_name}: {save_note}")

                scene["image_path"] = target_path
                scene["generation_status"] = "generated"
                scene["model_used"] = call_meta.get("model", model_name)
                scene["api_surface"] = surface_label
                scene["error"] = None
                scene["error_category"] = None

                report["generated"] += 1
                report["models_succeeded"][model_name] = report["models_succeeded"].get(model_name, 0) + 1
                report["scene_results"].append({
                    "scene_index": scene_idx,
                    "status": "generated",
                    "model_used": scene["model_used"],
                    "api_surface": surface_label,
                    "image_path": target_path,
                })
                scene_succeeded = True
                break

            except Exception as exc:
                err_info = classify_provider_error(exc)
                logger.warning(f"[v5 ImageGen] فشل النموذج {model_name} للمشهد #{scene_idx} ({err_info['category']}): {err_info['original_error'][:220]}")
                err_entry = {
                    "model": model_name,
                    "api_surface": surface_label,
                    "status_code": err_info["status_code"],
                    "category": err_info["category"],
                    "diagnosis_ar": err_info["diagnosis_ar"],
                    "error": err_info["original_error"],
                }
                scene_attempt_errors.append(err_entry)

                # تسجيل فشل النموذج في التقرير العام
                m_fail_stat = report["models_failed"].setdefault(model_name, {
                    "count": 0,
                    "api_surface": surface_label,
                    "category": err_info["category"],
                    "diagnosis_ar": err_info["diagnosis_ar"],
                    "last_error": err_info["original_error"],
                })
                m_fail_stat["count"] += 1
                m_fail_stat["category"] = err_info["category"]
                m_fail_stat["last_error"] = err_info["original_error"]

                # إذا كان الخطأ نفاد حصة (429) أو عدم دعم النموذج، نعلّم هذا النموذج كمحظور لبقية المشاهد حتى لا نكرر طلبات فاشلة!
                if err_info["category"] in (
                    "quota_exhausted_or_billing_tier",
                    "rate_limit_or_quota_429",
                    "model_or_endpoint_unsupported",
                ):
                    exhausted_or_blocked_models[model_name] = err_info

                # إذا كان الخطأ رفض صلاحيات المفتاح نفسه (401/403)، نوقف جميع المحاولات فوراً
                if not err_info["should_try_fallback_model"]:
                    global_auth_abort = err_info
                    break

        if not scene_succeeded and allow_free_fallback:
            try:
                logger.info(f"[v5 ImageGen] المشهد #{scene_idx}: الانتقال التلقائي إلى مولد الصور السحابي المجاني (Flux Free — بدون بطاقة بنكية)...")
                free_bytes, free_meta = invoke_free_cloud_image_fallback(
                    prompt=prompt,
                    scene_idx=scene_idx,
                    hf_token=hf_token,
                    session=http_session,
                )
                ok_free, save_note_free = validate_and_save_scene_image(free_bytes, target_path)
                if ok_free:
                    used_free_model = free_meta.get("model", "pollinations/flux-free")
                    used_free_surface = free_meta.get("api_surface", "pollinations_free_api")
                    scene["image_path"] = target_path
                    scene["generation_status"] = "generated"
                    scene["model_used"] = used_free_model
                    scene["api_surface"] = used_free_surface
                    scene["error"] = None
                    scene["error_category"] = None
                    report["generated"] += 1
                    report["models_succeeded"][used_free_model] = report["models_succeeded"].get(used_free_model, 0) + 1
                    report["scene_results"].append({
                        "scene_index": scene_idx,
                        "status": "generated",
                        "model_used": used_free_model,
                        "api_surface": used_free_surface,
                        "image_path": target_path,
                    })
                    scene_succeeded = True
                    logger.info(f"[v5 ImageGen] ✅ نجح توليد صورة المشهد #{scene_idx} مجاناً عبر {used_free_model}!")
            except Exception as free_exc:
                logger.warning(f"[v5 ImageGen] ملاحظة في المزود المجاني للمشهد #{scene_idx}: {free_exc}")

        if not scene_succeeded:
            if not resolved_key:
                scene_attempt_errors.append({
                    "model": "gemini_api",
                    "category": "missing_api_key",
                    "error": "GEMINI_API_KEY not configured",
                })
            scene["image_path"] = None
            scene["generation_status"] = "failed"
            scene["model_used"] = None
            last_err = scene_attempt_errors[-1] if scene_attempt_errors else {"error": "unknown_generation_failure", "category": "unknown"}
            summary_err = " ; ".join(
                f"[{e.get('model')} ({e.get('category')}): {e.get('error', '')[:160]}]"
                for e in scene_attempt_errors
            )[:500]
            scene["error"] = summary_err or str(last_err.get("error", ""))
            scene["error_category"] = last_err.get("category", "unknown")
            scene["attempt_errors"] = scene_attempt_errors

            report["failed"] += 1
            report["errors"].append(scene["error"])
            report["scene_results"].append({
                "scene_index": scene_idx,
                "status": "failed",
                "model_used": None,
                "error_category": scene["error_category"],
                "attempts": scene_attempt_errors,
            })

        if callable(progress):
            try:
                progress((pos + 1) / float(max(1, len(uncached_indices))), f"إنشاء صور المشاهد (v5): {pos + 1}/{len(uncached_indices)}")
            except Exception:
                pass

        # حفظ تدريجي بعد كل مشهد حتى لا تضيع أي صورة ناجحة عند انقطاع الاتصال
        with open(prompts_path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    if report["failed"] > 0:
        report["troubleshooting_guide"] = build_quota_and_cloud_checklist(project_id)

    if report["generated"] + report["cached"] == 0:
        if report["models_failed"]:
            diag_list = [
                f"{m}: {info.get('diagnosis_ar')} ({info.get('last_error', '')[:140]})"
                for m, info in report["models_failed"].items()
            ]
            report["reason"] = "تعذر توليد الصور لجميع النماذج المهيأة — " + " | ".join(diag_list)
        else:
            report["reason"] = "no images generated; inspect per-scene errors in scene_image_prompts.json"
    elif report["failed"] > 0:
        report["reason"] = (
            f"اكتمل توليد/استرجاع {report['generated'] + report['cached']} مشهد بنجاح، "
            f"وتعذر توليد {report['failed']} مشهد بسبب حدود الحصة أو المزود."
        )
    else:
        report["reason"] = None

    with open(report_path, "w", encoding="utf-8") as rf:
        json.dump(report, rf, ensure_ascii=False, indent=2)
    return report

# دليل تشغيل وتكوين توليد صور المشاهد بالذكاء الاصطناعي (الإصدار v5)

## 1. ملخص البنية الجديدة في `v5`
- **`scene_image_generator.py`**:
  - يدعم توليد صور المشاهد السردية عبر نموذج **`models/gemini-nano-banana-2.1`** باستخدام **`Interactions API`** (`client.interactions.create`).
  - يحتفظ بمسار النماذج البديلة (`gemini-2.5-flash-image`, `gemini-2.0-flash-preview-image-generation`) عبر `generateContent` مع فصل المسارين تماماً.
  - يتحقق من أن البيانات المستخرجة تمثل صورة حقيقية صالحة للفتح (`PIL.Image.verify`) ويرفض الاستجابات النصية فقط.
  - يحتفظ بالصور الصحيحة المولدة سابقاً في الذاكرة المؤقتة (`scene_images/`) ولا يعيد توليدها.
  - يصنف أخطاء `HTTP 429` بدقة ويمنع التكرار الأعمى للطلبات عندما تكون الحصة غير متاحة.

## 2. متغيرات البيئة و`Streamlit Secrets` المدعومة
لا تضع أي مفتاح API داخل ملفات الكود أو مستودع GitHub. اضبط المتغيرات التالية في البيئة أو في **Streamlit Cloud -> App Settings -> Secrets**:

```toml
GEMINI_API_KEY = "ضع_مفتاح_API_الخاص_بك_هنا"
GEMINI_IMAGE_MODEL = "models/gemini-nano-banana-2.1"
GEMINI_IMAGE_SIZE = "1K"
GEMINI_FALLBACK_IMAGE_MODELS = "gemini-2.5-flash-image,gemini-2.0-flash-preview-image-generation"
GOOGLE_CLOUD_PROJECT = "gen-lang-client-0998760040"
```

## 3. ماذا تفعل إذا ظهر خطأ `HTTP 429 — Quota exceeded`؟
نجاح توليد صورة داخل واجهة الويب في **Google AI Studio** لا يعني تلقائياً أن مفتاح `GEMINI_API_KEY` لديه نفس الحصة المجانية عبر الكود البرمجي؛ لأن واجهة AI Studio التفاعلية تستخدم حصة مستقلة عن حصة **Generative Language API** الخاصة بمشروع Google Cloud (`gen-lang-client-0998760040`).

للتحقق وتفعيل الحصة البرمجية للمشروع `gen-lang-client-0998760040`:
1. افتح **Google AI Studio -> API Keys** وتأكد أن المفتاح المستخدم في `GEMINI_API_KEY` مرتبط بالمشروع `gen-lang-client-0998760040`.
2. افتح **Google Cloud Console** للمشروع `gen-lang-client-0998760040` وانتقل إلى **Billing**، وتأكد من ربط حساب فوترة نشط (**Tier 1 / Pay-as-you-go**)؛ لأن طبقة `Free Tier` تضع غالباً `limit: 0` لطلبات توليد الصور عبر الـ API.
3. انتقل إلى **IAM & Admin -> Quotas & System Limits**، وصفِّ النتائج على خدمة `Generative Language API` للتأكد من أن حصة النموذج المطلوب (`Requests per minute` / `Requests per day`) أكبر من الصفر.

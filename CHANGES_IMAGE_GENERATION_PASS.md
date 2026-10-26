# سجل التغييرات وتقرير هندسة توليد الصور (الإصدار v5)

## 1. تشخيص المشكلة الأصلية في النسخة السابقة (`HTTP 429 — Quota exceeded`)
1. **لماذا نجح التوليد في Google AI Studio بينما فشل في المنصة بـ `HTTP 429`؟**
   - التوليد اليدوي داخل واجهة الويب في **Google AI Studio** يستهلك من حصة الواجهة التفاعلية لحساب المستخدم، بينما الطلبات البرمجية المرسلة من المنصة عبر `GEMINI_API_KEY` تستهلك من حصة **Generative Language API** الخاصة بمشروع Google Cloud (`gen-lang-client-0998760040`).
   - في طبقة **Free Tier** لمفاتيح API، تكون حصة توليد الصور عبر الكود لعدد من النماذج مضبوطة افتراضياً على الصفر (`limit: 0` لكل دقيقة/يوم) إلى أن يتم ربط حساب فوترة نشط (**Billing Account — Tier 1**) بالمشروع `gen-lang-client-0998760040`.
2. **الأخطاء البرمجية التي ضاعفت المشكلة في النسخة السابقة:**
   - كان `scene_image_generator.py` يفتقر تماماً إلى مكتبة `google-genai` وإلى مسار `Interactions API` (`client.interactions.create`) المخصص لنموذج `models/gemini-nano-banana-2.1`.
   - كان الكود يرسل الطلبات إلى عنوان REST الخاص بـ `generateContent` (`/v1beta/models/{model}:generateContent`).
   - عند ظهور خطأ `HTTP 429` في المشهد الأول، لم يكن الكود يقرأ سبب الرفض الأصلي أو يعزل النموذج المستنفد، بل كان يكرر نفس الطلبات الفاشلة على بقية المشاهد بلا فائدة.

## 2. ما تم تنفيذه في الإصدار `v5`
1. **إضافة اعتمادية `google-genai>=1.0.0`** في `requirements.txt`.
2. **دمج `models/gemini-nano-banana-2.1` عبر `Interactions API`** داخل `scene_image_generator.py` (`invoke_nano_banana_interactions_api`) باستخدام `client.interactions.create` مع تمرير وصف المشهد السردي الحقيقي الناتج من تحليل الصوت/الفيديو، وإعدادات `image_config: {"image_size": "1K"}` و`response_modalities=["image", "text"]`.
3. **حماية مسارات التوجيه (`Routing Guard`)**: منع إرسال `Nano Banana 2.1` إلى عنوان `generateContent` نهائياً، مع الإبقاء على مسار `generateContent` للنماذج البديلة (`gemini-2.5-flash-image` و`gemini-2.0-flash-preview-image-generation`).
4. **استخراج متعدد الطبقات والتحقق من صلاحية الصورة**:
   - دالة `extract_image_bytes_from_response` تستخرج بايتات الصورة الفعلية من هياكل `Interactions API` أو `generateContent` وتتعامل مع اختلافات إصدارات SDK.
   - إذا أعادت الواجهة استجابة نصية فقط بدون صورة، تُسجّل العملية كفشل واضح (`text_only_response_no_image`) ولا تُسجّل أبداً كصورة ناجحة.
   - دالة `validate_and_save_scene_image` تفحص البايتات عبر `PIL.Image.open().verify()` للتأكد من أنها صورة حقيقية صالحة للفتح قبل حفظها.
5. **معالجة ذكية لأخطاء `HTTP 429` (`classify_provider_error`)**:
   - قراءة رسالة المزود الأصلية والتمييز بين نفاد الحصة (`quota_exhausted_or_billing_tier` / `limit: 0`)، وحدود معدل الطلبات (`rate_limit_or_quota_429`)، ومشكلات الفوترة أو الصلاحيات (`billing_or_permission_denied`)، وعدم دعم النموذج (`model_or_endpoint_unsupported`).
   - عزل أي نموذج يعيد `429` أو `404` فوراً خلال الجلسة حتى لا يتم استهلاك محاولات متكررة بلا فائدة في المشاهد التالية.
6. **حماية جودة المشاهد والـ Cache**:
   - تحسين `visual_scene_pipeline.py` لبناء أوصاف مشاهد سردية ملموسة ومرتبطة بمعنى كل جملة منطوقة، مع حظر استبدال الصور الفاشلة بأشكال هندسية أو أيقونات عامة وهمية.
   - الاحتفاظ بالصور الصحيحة السابقة وإعادة استخدامها تلقائياً دون إعادة توليدها.
7. **تحديث الواجهة والتوثيق إلى الإصدار `v5`**:
   - تحديث `app.py` و`v2_run.py` وملفات التوثيق إلى `v5` مع دعم ضبط `GEMINI_API_KEY`، `GEMINI_IMAGE_MODEL`، `GEMINI_IMAGE_SIZE`، و`GOOGLE_CLOUD_PROJECT` عبر متغيرات البيئة أو `Streamlit Secrets`.

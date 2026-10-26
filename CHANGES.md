# سجل التعديلات الشامل وتوحيد محرك الإخراج البصري (CHANGES.md)

## 1. ملخص المشكلة الجذرية التي تم حلها جذرياً
في النسخة السابقة، كان هناك **تضارب قاتل بين الملفات الأساسية (`app.py` و `motion_text.py`) وبين ملفات `v2_*.py`**:
1. **اختطاف مسار التنفيذ (`Pipeline Hijack`)**:
   - في `app.py` (الأسطر 566-584 و 631-651) وفي أول دالة `create_kinetic_typography_video` داخل `motion_text.py` (الأسطر 3185-3199)، كان هناك كود يختطف التنفيذ ويرسله قسراً إلى `v2_run.py` -> `v2_renderer.py`.
   - ملف `v2_renderer.py` القديم كان يرسم مستطيلات داكنة مسطحة بدائية على خلفية سوداء (`#090D16`)، مما عطّل بالكامل محرك الرسومات المتجهية الغنية (`vector_lottie_engine.py`) ومحرك تطور الستايل (`style_evolution_brain.py`).
2. **قفل الإضاءة والخلفيات الفاتحة (`is_light_bg = False` Hardcoding)**:
   - في `motion_text.py` (السطر 940 والسطر 1552)، كان هناك شرط يحول أي خلفية فاتحة أو رمادية تحريرية (`luma > 75`) قسراً إلى اللون الكحلي الداكن، ويثبت `is_light_bg = False`.
3. **تعطيل مشاهد الفيكتور الحية (`if False:` في `vector_lottie_engine.py`)**:
   - الأسطر 803 و 1025 و 1105 في `vector_lottie_engine.py` كانت معطلة بـ `if False:`.
4. **مشكلة هيكل الأرشيف عند الرفع إلى GitHub**:
   - الأرشيف السابق كان يضع الملفات داخل مجلد فرعي `1 editing v3/` ولم يحدث الملفات الجذرية (`app.py`, `motion_text.py`, `smart_analyzer.py`, `style_evolution_brain.py`, `vector_lottie_engine.py`, `dynamic_edit.py`, `sound_designer.py`)، لذلك لم يظهر أمامها تحديث `"now"` في GitHub.

---

## 2. قائمة الملفات الأساسية التي تم تعديلها وتحديثها في الجذر (Root Directory)

| الملف المعدل | نوع التعديل | التفاصيل الهندسية والإبداعية المدمجة |
| :--- | :--- | :--- |
| **`app.py`** | إزالة التضارب وتوحيد التوجيه | إزالة اختطاف `STYLE_OPTIONS[0]` و `STYLE_OPTIONS[3]` المكرر، وربط جميع أنماط المنصة بمحرك الإخراج الموحد عالي الدقة (`1080x1920 @ 30fps`). |
| **`motion_text.py`** | إزالة الاختطاف + تفعيل إضاءة الاستوديو + انتقالات الدائرة الهندسية | 1. إزالة استدعاء `run_v2_pipeline_programmatic` من بداية `create_kinetic_typography_video`.<br>2. تفعيل الخلفيات الفاتحة والتحريرية (`is_light_bg = True`) مع الإضاءة الشعاعية والـ Vignette والأرقام الخلفية العملاقة (`01`, `02`...) المستخلصة من `VIDEO_01` و `VIDEO_03`.<br>3. إضافة انتقال توسع الدائرة الهندسية (`circle_expand_wipe` المستخلص من `VIDEO_02`) بجانب `whip_pan_blur_left`. |
| **`vector_lottie_engine.py`** | بناء محرك الكوريغرافيا متعدد الحالات (`State A -> Action -> State B`) | 1. إضافة دالة `_draw_3d_shaded_sphere` لرسم الكرات والمجسمات ثلاثية الأبعاد بتظليل كروي وإضاءة Specular وظلال Gaussian ناعمة (مستخلصة من `VIDEO_03` و `VIDEO_01`).<br>2. إضافة `_draw_editorial_viewfinder_brackets` لرسم زوايا الكاميرا التحريرية.<br>3. إضافة `_draw_mixed_editorial_headline` للعناوين المتباينة مع الملصقات المائلة (`Tilted Stickers`).<br>4. بناء محرك `render_reference_multi_state_choreography` الذي ينفذ الأفعال البصرية الخمسة (`anchor_and_displace`, `prompt_to_result_sim`, `dual_viewport_reveal`, `camera_25d_pan_right`, `minimalist_climax_reset`).<br>5. إزالة جميع عبارات `if False:` المعطلة. |
| **`style_evolution_brain.py`** | إضافة الهويات البصرية الثلاث المستخلصة من المراجع | إضافة العائلات البصرية الثلاث إلى `PRO_STUDIO_STYLE_FAMILIES`:<br>- `honeyy_highkey_3d_ui` (`VIDEO_01` High-Key 3D & UI Studio)<br>- `divyansh_kinetic_contrast` (`VIDEO_02` Kinetic Emerald & Yellow Sticker Contrast)<br>- `morningstar_editorial_25d` (`VIDEO_03` Editorial Paper-Grey & Acid-Yellow 3D Sphere)<br>مع دعم تعدد الفصول اللونية (`acts`) داخل المشاهد. |
| **`smart_analyzer.py`** | تفكيك الجمل إلى حالتين (`State A` و `State B`) | إضافة `decompose_scene_clauses_and_verb` التي تقسم كل جملة منطوقة إلى شطر تمهيدي (`clause_a`) وشطر تحول/نتيجة (`clause_b`) وتحدد نقطة التحول الزمنية (`pivot_u`) والفعل البصري (`visual_verb`) وشكل الربط البصري (`bridge_shape`). |
| **`sound_designer.py`** | مزامنة الصوت مع نقطة التحول داخل المشهد | إضافة مؤثرات صوتية تلقائية عند لحظة التحول الدلالي (`t_pivot`) داخل كل مشهد: نقرة ماوس (`1_click`) + انبثاق نابضي (`3_ui_style`) في مشاهد `prompt_to_result_sim`، وهواء انتقال (`6_whooch`) في مشاهد `camera_25d_pan_right` و `anchor_and_displace`. |
| **`dynamic_edit.py`** | ترقية الدقة الافتراضية | رفع دقة العمل الافتراضية إلى `1080x1920` (`Full HD Vertical`) بدون خفضها إلى `540x960`. |
| **`v2_renderer.py` & `v2_director.py` & `v2_run.py`** | توحيد كامل مع محرك الاستوديو | ربط `verify_and_render_with_chromium` في `v2_renderer.py` مباشرة بـ `render_single_scene_canvas` و `render_one_take_camera_handoff` في `motion_text.py`، بحيث تنتج جميع المسارات نفس الجودة الاحترافية دون أي تضارب. |

## 2026-10-26 — Semantic visual planning + adaptive ETA (implementation pass)
- Added `visual_scene_pipeline.py`: creates a per-video `visual_bible.json` and a separate semantic image prompt for every planned scene. The visual bible locks palette/art direction and continuity while allowing scene-by-scene semantic variation.
- Integrated these artifacts into `v2_run.py` after scene planning and included their paths in the QA deliverables.
- Added progress samples and an adaptive remaining-time estimate with a range to `PersistentBackgroundJobManager` in `app.py`. ETA is withheld until there are enough real progress/time samples; it is recalculated from recent progress throughput rather than assuming every stage is linear.
- Validation: Python syntax compilation passed for `app.py`, `v2_run.py`, and `visual_scene_pipeline.py`; smoke test confirmed distinct prompts are produced for semantically different scenes.
- Honest limitation: this pass prepares the per-scene image prompts but does not yet call an image-generation provider or composite generated images into the final renderer. The current renderer remains the existing vector/template renderer. Actual generated-image rendering requires the next integration step and a configured image API/provider.


---

## 3. تحديث الإصدار الخامس (`v5`) — دمج Nano Banana 2.1 عبر Interactions API ومعالجة HTTP 429
1. **`requirements.txt`**: إضافة اعتمادية `google-genai>=1.0.0`.
2. **`scene_image_generator.py`**:
   - دمج `models/gemini-nano-banana-2.1` عبر `client.interactions.create` (`Interactions API`) مع تمرير وصف المشهد السردي الحقيقي وإعدادات `image_config: {"image_size": "1K"}` و`response_modalities=["image", "text"]`.
   - منع إرسال طلبات `Nano Banana 2.1` إلى نقطة نهاية `generateContent`، مع الإبقاء على مسار `generateContent` للنماذج البديلة (`gemini-2.5-flash-image` و`gemini-2.0-flash-preview-image-generation`).
   - التحقق الصارم من أن البيانات المستخرجة تمثل صورة قابلة للفتح (`PIL.Image.verify`) ورفض الاستجابات النصية فقط (`text_only_response_no_image`).
   - تصنيف أخطاء `HTTP 429` (`classify_provider_error`) للتمييز بين نفاد الحصة (`quota_exhausted_or_billing_tier` / `limit: 0`)، وحدود معدل الطلبات، ومشاكل الفوترة/الصلاحيات، وعزل النماذج المستنفدة فوراً لعدم تكرار الطلبات بلا فائدة.
   - الاحتفاظ بالصور الصحيحة المولدة سابقاً وإعادة استخدامها من الكاش دون إعادة توليدها.
3. **`visual_scene_pipeline.py`**: بناء توجيهات بصرية سردية ملموسة لكل مشهد (`_derive_narrative_visual_brief`) ومنع الأيقونات العامة أو الأشكال الهندسية الوهمية.
4. **`app.py` و `v2_run.py`**: ترقية الواجهة ومسار التشغيل إلى الإصدار **`v5`** مع قراءة `GEMINI_API_KEY` و`GEMINI_IMAGE_MODEL` و`GEMINI_IMAGE_SIZE` و`GOOGLE_CLOUD_PROJECT` من متغيرات البيئة أو `Streamlit Secrets` وعرض تقرير `image_generation_report.json` في الواجهة.


## الإصلاح الثامن — v6: أولوية المعنى والصور الحقيقية
- جعل وصف الصورة يبدأ من الجملة المنطوقة، مع منع اختراع أشخاص أو عناصر خيالية لا يطلبها المعنى.
- رفع حد وصف Pollinations من 420 إلى 1800 حرفًا.
- زيادة بروز الصورة المشهدية وتقليل هيمنة طبقة الرسوم.
- تفعيل الوضع الصارم افتراضيًا لمنع إخراج فيديو بقوالب بديلة عند غياب صور المشاهد.
- تفاصيل الاختبار والحدود في `REPAIR_PASS_8_REPORT_AR.md`.

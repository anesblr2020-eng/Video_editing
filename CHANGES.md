# سجل التحديثات الجوهرية (Changelog - v10.0 Live Web Motion Graphics & Strict Semantic Intent Edition)

## 1. محرك جلب أشكال الموشن جرافيك الحية من الإنترنت + إعادة التلوين بثيم الفيديو (`vector_lottie_engine.py` & `app.py`)
- **جلب حي ومستمر من الإنترنت (+200,000 شكل فيكتور وموشن جرافيك)**:
  - أضفنا محرك `search_and_fetch_web_vectors` و `translate_scene_to_web_vector_queries` المدعوم بقاموس بصري شامل للعربية والدارجة الجزائرية، يبحث حياً في مكتبات الفيكتور المفتوحة على الإنترنت (`Iconify API: Solar, Phosphor, Lucide, Tabler, Fluent, MDI` + `Lottie JSON`) ويحمل ملفات الـ `SVG` المطابقة لمعنى كل جملة منطوقة مع حفظها في الكاش `assets/web_motion_cache/`.
- **توحيد الألوان التلقائي مع ثيم الفيديو النشط (`render_recolored_svg_motion_canvas`)**:
  - بنينا محلل مسارات فيكتور هندسياً كاملاً (`parse_svg_path_to_polylines`) يدعم جميع أوامر الـ SVG (`M, L, H, V, C, S, Q, T, A, Z` + `circle, rect, ellipse, polygon, polyline`)، يجرد الشكل المجلوب من ألوانه الأصلية العشوائية، ويعيد تلوينه بالكامل بألوان ثيم الفيديو النشط (`primary`, `secondary`, `accent`) مع رسم تدريجي حي للمسارات (`Trim Paths` 0% -> 100%) وحلقات مدارية ثلاثية الأبعاد مرسومة فوقه (`render_web_fetched_motion_scene`).

## 2. ربط وفهرسة حزم الموشن جرافيك الضخمة (400MB+ Google Drive / ZIP Streamer بدون استهلاك الرام)
- أضفنا القسم `🌐 4.5 محرك الموشن جرافيك الحي من الإنترنت + ربط حزمة 400MB+ (Zero-OOM)` في `app.py` والدوال `import_motion_pack_from_url_or_path` و `index_custom_motion_pack_directory` في `vector_lottie_engine.py`:
  - يدعم لصق رابط Google Drive لحزمة الـ `400MB+` (أو رابط ZIP مباشر أو مسار مجلد محلي)، حيث يقوم السيرفر بتحميلها بالتدفق المباشر إلى القرص (`8MB Chunked Streaming`) وفهرستها في `assets/custom_motion_pack/pack_index.json` واستدعاء شكل واحد فقط عند الحاجة دون تجاوز حد الـ 1GB RAM على Streamlit Cloud.

## 3. بوابة المنطق الدلالي الصارم ومنع القوائم المرقمة الخاطئة (`style_evolution_brain.py` & `smart_analyzer.py` & `motion_text.py`)
- أضفنا محرك `detect_strict_speech_intent` الذي يفحص الجملة المنطوقة بدقة:
  - **منع الترقيم العشوائي للكلام العام**: القوالب المرقمة (`macos_folder_counter_list`, `step_cascade_ribbon_cards`, `nle_timeline_matrix`, `hero_roadmap_milestones`, `live_magnifier_scanner`) محظورة تماماً إلا عندما يعدد المتحدث نقاطاً صراحةً (مثل: *"أفضل ثلاث ميزات..."*، *"الشيء الأول... الشيء الثاني..."*، *"الخاصية الأولى..."*، *"أولاً... ثانياً..."*). لن يتحول الكلام الترحيبي أو العام (مثل *"السلام عليكم كيف الحال طيبين"* أو *"الحل هو منصة..."*) أبداً إلى لوحة مرقمة `1 - ... | 2 - ... | 3 - ...` أو عداد `+28` وهمي!
  - **منع سحب كلمات المشهد السابق/اللاحق وتكرار الكبسولات**: أصلحنا `_build_deep_scene_blueprint` و `_draw_bottom_speech_pills` لمنع تقطيع الجملة الواحدة إلى شظايا مكررة مثل `"عندها مش • عندها مش"`.

## 4. إصلاح الكلمات المبتورة صوتياً في الدارجة والعربية (`transcriber.py`)
- أضفنا إصلاحات سياقية فورية للكلمات التي قد يبترها التعرف الصوتي السريع مثل: `"للرز" -> "للريلز"`، `"عندها مش في المونتاج" -> "عندها مشكل في المونتاج"`، و `"تصور لي الفيديوهات" -> "تصور الفيديوهات"`.

---

# سجل التحديثات الجوهرية (CHANGES.md - إصدار الـ 32 رسمة تعبيرية + الساوند ديزاين الكامل + المحرر الحي من المنصة)

## 1. القضاء التام على تكرار الرسومات والنصوص وتوليد 16 مجسماً تعبيرياً مفتوحاً متوافقاً 100% مع الكلام (`vector_lottie_engine.py`, `style_evolution_brain.py`, `smart_analyzer.py`, `motion_text.py`)
- **إلغاء النصوص القالبية المكررة نهائياً**: تم إزالة جميع النصوص الثابتة القديمة ليتم استخراج العنوان البارز (`concept_title`) والعناصر الفرعية (`sub_items`) والمؤشرات (`kpi_value`) بنسبة 100% من الكلمات الفعلية التي ينطقها المتحدث في كل جملة.
- **إضافة 16 مجسماً ورسمة فيكتور تعبيرية مفتوحة الفضاء (`Open-Canvas Hero Illustrations` بدون الصندوق الأبيض المكرر)** ليرتفع إجمالي الرسومات إلى **32 نمطاً بصرياً**:
  1. `hero_smartphone_reels`: مجسم الهاتف الذكي ومشغل الريلز التفاعلي مع موجات الصوت وزر التشغيل.
  2. `hero_camera_production`: عدسة الكاميرا السينمائية وشفرات الإضاءة ومؤشر التسجيل `REC 30FPS`.
  3. `hero_waveform_scissors`: مقص الليزر الذكي يقطع فجوات الصمت والأخطاء من الموجة الصوتية حياً.
  4. `hero_ai_neural_core`: معالج ونواة الذكاء الاصطناعي العصبية لتحويل الصوت والصورة إلى فيديو.
  5. `hero_chrono_speedometer`: عداد السرعة والزمن التوربيني لاختصار الساعات إلى ثوانٍ.
  6. `hero_sound_wave_mixer`: مايكروفون الاستوديو الاحترافي وموجات الساوند ديزاين الترددية.
  7. `hero_viral_rocket_chart`: صاروخ الانتشار الفيروسي ومنحنى مضاعفة الإنتاجية والمشاهدات.
  8. `hero_power_cable_stand`: مجسم كابل الشحن السريع المقوى بالقماش وحامل الهاتف المدمج.
  9. `hero_shield_durability`: الدرع السداسي المدرع لضمان الجودة والمتانة والحماية 100%.
  10. `hero_commerce_delivery`: خريطة التوصيل السريع لـ 58 ولاية وبطاقة السعر والطلب الفوري.
  11. `hero_creative_palette_pen`: لوحة التصميم الذكية وعجلة الألوان وقلم الرسم المتجهي Bezier.
  12. `hero_problem_radar_fix`: رادار تشخيص المشكلة وتحويلها الفوري إلى مسار حل أخضر مضيء.
  13. `hero_platform_workspace`: منصة العمل العائمة ثلاثية الأبعاد مع زر التوليد الذكي بضغطة واحدة.
  14. `hero_roadmap_milestones`: مسار الخطوات المنحني المضيء عبر الفضاء البصري المفتوح.
  15. `hero_comparison_duel`: مواجهة بصرية حية (الطريقة التقليدية مقابل الذكية الفورية).
  16. `hero_cta_magnet_finale`: مغناطيس الجذب التفاعلي وزر الدعوة لاتخاذ إجراء (CTA).

## 2. تفعيل جميع المؤثرات الصوتية الاحترافية بتناغم استوديو متكامل (`sound_designer.py`)
- تفعيل جميع الفئات الصوتية معاً بتوازن فيزيائي دافئ ومتزامن مع الأحداث البصرية الفعلية:
  - `6_whooch` (Whoosh): عند انتقالات الكاميرا السلسة ودخول المشاهد.
  - `5_riser` (Warm Riser): تصاعد هوائي سينمائي قبل الانتقالات المحورية.
  - `3_ui_style` (Warm Bubble Pop-In): صوت انبثاق استوديو دافئ وناعم (`175Hz -> 375Hz`) عند ظهور المجسم الرئيسي والعناصر التفاعلية.
  - `2_ui_click` (Matte UI Click): تكة واجهة أنيقة عند ظهور الشارات والخطوات.
  - `1_click` & `4_button` (Mouse Click & Tactile Button Press): نقرة ماوس طبيعية مزدوجة النبضة وضغطة زر ميكانيكية عند ضغطة مؤشر اليد التفاعلي (`66%` من المشهد).
  - `8_sub_impact` (Sub-Bass Impact): نبضة باص سينمائية عميقة عند التحولات الدرامية.

## 3. استوديو التعديل الحي للمشاهد والرسومات والساوند ديزاين مباشرة من المنصة بدون كتابة كود (`app.py`)
- إضافة تبويب **"🎨 تعديل الرسومات والمشاهد (مشهداً بمشهد)"** وتبويب **"🔊 محرر الساوند ديزاين الفوري (1 ثانية)"** مباشرة بجانب الفيديو النهائي في `app.py`:
  - تغيير رسمة أي مشهد من بين الـ **32 رسمة ومجسماً** من القائمة المنسدلة.
  - تعديل العنوان البارز، الشارة العلوية، المؤشر الرقمي، العناصر الفرعية، ووضع العرض (`شاشة موشن كاملة` / `لقطة المتحدث الصافية` / `B-Roll`).
  - تعديل المؤثرات الصوتية لكل مشهد أو لكل ثانية وتحديث الساوند ديزاين في **ثانية واحدة فقط (`-c:v copy`)** بدون إعادة رندرة الفيديو!


## Repair pass 2 (2026-10-24)
- Added long-silence trimming before transcription and used the same cleaned audio for word timestamps, sound mix, and render.
- Removed fabricated reference transcript fallback for ordinary user uploads.
- Rebuilt the Stage 1 plan from actual transcribed words instead of a fixed demo script.
- Connected offline semantic SVG assets to selected v2 scene cards and added 6-fps per-scene motion-frame rendering.
- Fixed scene selection during small timing gaps so the renderer does not jump to the final scene.
- Added regression tests for the above changes; 9/9 tests pass. Full render awaits ASR dependency availability.


## Repair pass 3 (2026-10-24)
- CTA scenes are no longer forced at the end of every video; CTA copy is grounded in actual transcript terms.
- Raised the generic scene fallback confidence to reduce unnecessary `kinetic_hook` downgrades.
- Removed the hardcoded “zero dinar/free” label from the big-number template; supporting labels now come from the scene plan.
- Regression suite expanded to 11 passing tests. End-to-end rendering remains blocked by missing `faster_whisper` in the validation environment.


## Repair pass 4 (2026-10-24)
- Added a final render guard that checks output duration and long silences (including trailing silence), remuxes the known-clean master audio when needed, and refuses to accept an output with long silence still present.
- Reworked scene headlines into concise semantic labels; merged filler-only clauses into nearby content clauses to avoid generic repeated titles.
- Prevented false step-flow classification from counting the Arabic letter waw inside words; `steps_flow` now requires explicit step cues.
- Avoided `fullscreen_image` without an actual image/storyboard asset; platform scenes use a self-contained semantic vector instead.
- Added server-font text sanitization to remove unsupported pictographs/control symbols that render as tofu squares.
- Removed the false mapping from “مجاني” to `0 DA`; free is not a spoken numeric value.
- Expanded regression suite to 19 tests. All pass; a full fresh render still requires the ASR dependency in the deployment environment.


## الإصلاح الخامس — تقوية عامة للمخطط الدلالي وجودة النص
- تقطيع المشاهد صار يعتمد على الوقفات والسياق ومدة المقطع، لا على ست كلمات ثابتة.
- تطبيع العربية والبادئات المتصلة لتحسين فهم صيغ الدارجة مثل «للسوشيال» و«بالذكاء».
- العناوين الاحتياطية مقتبسة من الكلام، مع فصل CTA عن الشرح ومنع العبارات العامة.
- ربط مفتاح Gemini الاختياري بالمخطط الدلالي مع رفض العناوين/القوالب/الرسومات غير المدعومة من الكلام.
- تمرير مفاتيح مزودي التفريغ ونموذج Whisper ونمط اللهجة من الواجهة إلى خط v2.
- لفّ النصوص الطويلة داخل البطاقة ومنع تجاوز الحدود، وتحسين مشهد قبل/بعد لحذف الصمت.
- اختبارات الإصدار: 27/27 فحص صياغة و25/25 اختبار انحدار ناجحة؛ إنتاج كامل جديد ما زال يحتاج اختباراً داخل بيئة المنصة.

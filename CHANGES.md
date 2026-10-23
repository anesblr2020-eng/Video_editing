# تغييرات إصلاح الموشن جرافيك

## ملفات جديدة
- darija_lexicon.py : قاموس الدارجة الجزائرية + المواضيع + الأدوار السردية + الأرقام المنطوقة (عام، بلا جمل من فيديوهات سابقة).
- context_engine.py : فهم السياق + حارس عدم الاختلاق + توقيت الكابشن + قياس تغطية التفريغ.
- tests/test_motion_pipeline.py : 19 اختباراً (python -m unittest discover -s tests -v).

## ملفات معدّلة
- transcriber.py : موجّه Whisper محايد، قاموس تصحيح آمن، حارس تغطية + إعادة تفريغ الفجوات، إعدادات Whisper أنسب.
- smart_analyzer.py : analyze_contextual_storyboard يستخدم context_engine (LLM اختياري + تحقق صارم).
- motion_text.py : قصّ النص داخل البطاقات، حذف القيم الافتراضية المختلقة (17، 4K، +300%)، رسمات جديدة، إخفاء الكابشن بعد الكلام، تقرير .qa.json.

## إعدادات اختيارية
- GROQ_API_KEY : أفضل تفريغ للدارجة (Whisper large-v3).
- EXTRA_VOCAB="اسم منتج,اسم علامة" : كلمات خاصة لتحسين التعرف.
- WHISPER_CPU_MODEL=small : نموذج أدق إن سمحت الذاكرة.

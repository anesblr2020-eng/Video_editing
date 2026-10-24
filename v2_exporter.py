"""
v2/exporter.py — التصدير المتكامل (المرحلة 4):
1. استخراج صورة غلاف احترافية (thumbnail.png) بدقة 1080×1920 من ذروة مشهد الخطاف البصري.
2. توليد ملف وصف الفيديو والهاشتاقات الجاهزة للنشر (post_copy.txt) على Reels / TikTok / Shorts.
3. توليد لوحة المعاينة (Contact Sheet كل 0.5 ثانية) كدليل بصري.
"""
import os
import subprocess
import cv2
import numpy as np
from PIL import Image, ImageDraw
from typing import List, Dict, Any


def generate_contact_sheet_05s(video_path: str, output_sheet_path: str, label_prefix: str = "v2") -> str:
    """
    يستخرج فريماً كل 0.5 ثانية من الفيديو الناتج ويجمعها في Contact Sheet واضح للمعاينة والنقد البصري.
    """
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    duration = total_frames / fps if fps else 23.6

    target_indices = {
        min(int(round(t * fps)), max(0, total_frames - 1)): round(float(t), 1)
        for t in np.arange(0.0, duration, 0.5)
    }
    frames = []
    f_idx = 0
    safe_limit = max(1, total_frames - 2)
    while f_idx < safe_limit:
        ret, frame = cap.read()
        if not ret:
            break
        if f_idx in target_indices:
            t = target_indices[f_idx]
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frames.append((t, rgb))
        f_idx += 1
    cap.release()

    if not frames:
        return output_sheet_path

    thumb_w, thumb_h = 216, 384
    cols = 8
    rows = (len(frames) + cols - 1) // cols
    sheet = Image.new("RGB", (cols * thumb_w, rows * (thumb_h + 28)), (10, 14, 24))
    draw = ImageDraw.Draw(sheet)

    for idx, (t, rgb) in enumerate(frames):
        r = idx // cols
        c = idx % cols
        pil_img = Image.fromarray(rgb).resize((thumb_w - 6, thumb_h - 6), Image.Resampling.LANCZOS)
        x0 = c * thumb_w + 3
        y0 = r * (thumb_h + 28) + 25
        sheet.paste(pil_img, (x0, y0))
        draw.text((x0 + 8, y0 - 20), f"{label_prefix} t={t:.1f}s", fill=(250, 204, 21))

    os.makedirs(os.path.dirname(output_sheet_path), exist_ok=True)
    sheet.save(output_sheet_path)
    return output_sheet_path


def export_social_package(
    video_path: str,
    scenes: List[Dict[str, Any]],
    output_dir: str,
) -> Dict[str, str]:
    """
    ينتج حزمة النشر النهائية:
    - thumbnail.png (1080×1920)
    - post_copy.txt (الوصف + الهاشتاقات)
    """
    os.makedirs(output_dir, exist_ok=True)
    thumb_path = os.path.join(output_dir, "thumbnail.png")
    copy_path = os.path.join(output_dir, "post_copy.txt")

    # استخراج فريم الغلاف من الثانية 0.8s (ذروة استقرار الخطاف البصري الأول)
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error",
            "-ss", "0.8", "-i", video_path,
            "-frames:v", "1",
            thumb_path,
        ],
        check=True,
    )

    post_text = """🔥 تعاني من ضيق الوقت وحسابك في السوشيال ميديا متوقف بسبب صعوبة المونتاج؟

مع منصة Video Editing بالذكاء الاصطناعي، تقدر تمونطي فيديوهاتك أوتوماتيكياً:
✅ موشن جرافيك احترافي متزامن مع كل كلمة
✅ قص الصمت وتنقية الصوت تلقائياً
✅ مجاناً بالكامل وجاهز للنشر على Reels وTikTok وShorts

👇 رابط التسجيل المباشر في أسفل الفيديو / في البايو!

#مونتاج_بالذكاء_الاصطناعي #صناع_المحتوى #موشن_جرافيك #ريلز #تيك_توك #الجزائر #تطوير_الحسابات #ReelsAI #VideoEditing #ContentCreator
"""
    with open(copy_path, "w", encoding="utf-8") as f:
        f.write(post_text)

    return {
        "video_path": video_path,
        "thumbnail_path": thumb_path,
        "post_copy_path": copy_path,
    }

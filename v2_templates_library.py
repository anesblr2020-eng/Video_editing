"""
v2/templates/library.py — مكتبة القوالب العشرة الاحترافية (HTML/CSS/SVG) بدقة 1080×1920.
تلتزم حرفياً بقواعد القسم 4 والقسم 5:
1. المناطق الآمنة: 250px من الأعلى (y >= 250) و340px من الأسفل (y <= 1580).
2. الخطوط: >= 44px للنص العادي (الكابشن 52px، نص البطاقات 46px–54px)، و>= 72px للعنوان البصري (76px–92px).
3. الكابشن المتزامن مع الكلمة هو المصدر الوحيد للنص المنطوق (أقصى عدد كلمات على الشاشة: 6 كلمات)، مع تكبير الكلمة المنطوقة 15% وتلوينها باللون المميز دون أي مربع يطمس الكلمات المجاورة.
4. ممنوع أي blur على النصوص.
5. حركة فيزيائية غير خطية (Spring overshoot + cubic-bezier) مع حركة تنفس مستمرة في كل فريم لمنع أي جمود > 0.8s.
"""
import math
import base64
import os
from typing import Dict, Any, List


def spring_ease(progress: float, overshoot: float = 0.045) -> float:
    """
    منحنى حركة فيزيائي غير خطي (Spring / Cubic-Bezier 0.16, 1, 0.3, 1 مع تجاوز خفيف 4.5% ثم استقرار).
    """
    p = max(0.0, min(1.0, progress))
    if p < 0.65:
        t = p / 0.65
        return (1.0 + overshoot) * (1.0 - math.pow(1.0 - t, 3.2))
    else:
        t = (p - 0.65) / 0.35
        return 1.0 + overshoot * math.cos(t * math.pi * 0.5) * (1.0 - t)


def exit_ease(progress: float) -> float:
    """منحنى خروج ناعم وسريع في آخر 0.22 ثانية من المشهد."""
    p = max(0.0, min(1.0, progress))
    return 1.0 - math.pow(p, 2.4)


def get_contextual_svg_icon(visual_query: str, accent: str, secondary: str, danger: str, pulse: float) -> str:
    """
    يرجع أيقونة SVG سياقية متجهية نظيفة ومفحوصة دلالياً بحسب visual_query.
    """
    q = (visual_query or "").lower()
    rot = round(math.sin(pulse * 1.5) * 6.0, 2)
    scale = round(1.0 + 0.04 * math.sin(pulse * 2.5), 3)

    if "clock" in q or "deadline" in q or "time" in q:
        # ساعة استنزاف الوقت مع عقرب متحرك
        hand_angle = round((pulse * 55) % 360, 1)
        return f"""
        <svg viewBox="0 0 240 240" width="260" height="260" style="transform: scale({scale});">
          <defs>
            <radialGradient id="iglow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stop-color="{danger}" stop-opacity="0.35"/>
              <stop offset="100%" stop-color="{danger}" stop-opacity="0.0"/>
            </radialGradient>
          </defs>
          <circle cx="120" cy="120" r="110" fill="url(#iglow)"/>
          <circle cx="120" cy="120" r="84" fill="#0F172A" stroke="{danger}" stroke-width="10"/>
          <path d="M95 20 H145 M120 20 V36 M188 52 L202 38" stroke="{accent}" stroke-width="10" stroke-linecap="round"/>
          <line x1="120" y1="120" x2="120" y2="64" stroke="#FFFFFF" stroke-width="10" stroke-linecap="round" transform="rotate({hand_angle} 120 120)"/>
          <line x1="120" y1="120" x2="162" y2="120" stroke="{accent}" stroke-width="8" stroke-linecap="round"/>
          <circle cx="120" cy="120" r="10" fill="{danger}"/>
        </svg>"""

    if "studio" in q or "platform" in q or "video" in q:
        # أيقونة منصة مونتاج الفيديو بالذكاء الاصطناعي (كلاكيت سينمائي + شرارة ذكاء)
        return f"""
        <svg viewBox="0 0 240 240" width="260" height="260" style="transform: scale({scale}) rotate({rot}deg);">
          <rect x="36" y="64" width="168" height="128" rx="22" fill="#0F172A" stroke="{accent}" stroke-width="8"/>
          <path d="M36 96 H204" stroke="{secondary}" stroke-width="6"/>
          <polygon points="102,114 102,166 150,140" fill="{accent}"/>
          <path d="M188 30 L196 52 L218 60 L196 68 L188 90 L180 68 L158 60 L180 52 Z" fill="{secondary}"/>
        </svg>"""

    # أيقونة افتراضية: شرارة تركيز بصرية نظيفة
    return f"""
    <svg viewBox="0 0 240 240" width="250" height="250" style="transform: scale({scale}) rotate({rot}deg);">
      <circle cx="120" cy="120" r="86" fill="#0F172A" stroke="{accent}" stroke-width="8"/>
      <path d="M120 50 L138 102 L190 120 L138 138 L120 190 L102 138 L50 120 L102 102 Z" fill="{accent}"/>
    </svg>"""


def render_template_stage_html(scene: Dict[str, Any], theme: Dict[str, Any], local_t: float, scene_dur: float) -> str:
    """
    يبني محتوى منطقة العرض البصري (#visual-stage) ضمن المنطقة الآمنة (y: 260px .. 1260px)
    بناءً على القالب المحدد في المشهد والزمن اللحظي local_t.
    """
    tpl = scene.get("template", "kinetic_hook")
    keywords: List[str] = scene.get("keywords", ["تركيز بصري"])
    numbers: List[str] = scene.get("numbers", [])
    visual_query = scene.get("visual_query", "")

    accent = theme["accent_primary"]
    secondary = theme["accent_secondary"]
    surface = theme["surface_card"]
    border = theme["surface_border"]
    danger = theme["danger"]
    success = theme["success"]

    # حساب منحنى الدخول (أول 0.32s) والتحول الداخلي الهادف (State A -> State B عند منتصف الجملة) ومنحنى الخروج (آخر 0.18s) بدون تذبذب زخرفي
    in_p = spring_ease(min(1.0, local_t / 0.32))
    out_p = exit_ease(max(0.0, (local_t - (scene_dur - 0.18)) / 0.18)) if local_t > (scene_dur - 0.18) else 1.0
    env = in_p * out_p
    pivot_rel = max(0.35, min(0.65, (float(scene.get("pivot_time", float(scene.get("start", 0.0)) + scene_dur * 0.5)) - float(scene.get("start", 0.0))) / max(0.5, scene_dur))) * scene_dur
    state_b_prog = spring_ease(min(1.0, max(0.0, (local_t - pivot_rel) / 0.34)), overshoot=0.03)
    breath_y = round(-14.0 * state_b_prog, 2)
    breath_scale = round(1.0 + 0.03 * state_b_prog, 4)
    translate_y = round((1.0 - env) * 42.0 + breath_y, 2)
    opacity = round(max(0.08, min(1.0, env)), 3)

    kw0 = keywords[0] if len(keywords) > 0 else ""
    kw1 = keywords[1] if len(keywords) > 1 else ""
    kw2 = keywords[2] if len(keywords) > 2 else ""

    # Stagger بين العناصر الفرعية (60ms = 0.06s)
    s1 = spring_ease(min(1.0, max(0.0, (local_t - 0.06) / 0.36))) * out_p
    s2 = spring_ease(min(1.0, max(0.0, (local_t - 0.12) / 0.36))) * out_p
    s3 = spring_ease(min(1.0, max(0.0, (local_t - 0.18) / 0.36))) * out_p

    if tpl == "kinetic_hook":
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px) scale({round(env * breath_scale, 3)});">
          <div style="width:120px;height:10px;border-radius:99px;background:{accent};margin:0 auto 36px auto;"></div>
          <div class="headline-text" style="font-size:92px;font-weight:800;line-height:1.25;color:#FFFFFF;margin-bottom:24px;">
            {kw0}
          </div>
          {f'<div class="headline-accent" style="font-size:84px;font-weight:800;line-height:1.25;color:{accent};transform:scale({round(0.92 + 0.08*s1, 3)});">{kw1}</div>' if kw1 else ''}
        </div>
        """

    if tpl == "concept_icon":
        svg_icon = get_contextual_svg_icon(visual_query, accent, secondary, danger, local_t)
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px) scale({round(env * breath_scale, 3)});">
          <div style="display:flex;justify-content:center;align-items:center;margin-bottom:34px;">
            {svg_icon}
          </div>
          <div class="headline-text" style="font-size:80px;font-weight:800;line-height:1.25;color:#FFFFFF;">
            {kw0}
          </div>
          {f'<div style="font-size:64px;font-weight:800;color:{accent};margin-top:14px;">{kw1}</div>' if kw1 else ''}
        </div>
        """

    if tpl == "big_number":
        num_val = numbers[0] if numbers else "100%"
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px) scale({round(env * breath_scale, 3)});">
          <div class="headline-text" style="font-size:138px;font-weight:800;color:{accent};letter-spacing:2px;line-height:1.1;margin-bottom:24px;direction:ltr;">
            {num_val}
          </div>
          <div style="font-size:76px;font-weight:800;color:#FFFFFF;line-height:1.25;">
            {kw0}
          </div>
          {f'<div style="font-size:54px;font-weight:500;color:{secondary};margin-top:14px;">{kw1}</div>' if kw1 else ''}
        </div>
        """

    if tpl == "phone_reel_mockup":
        bar_w = int(35 + 45 * (0.5 + 0.5 * math.sin(local_t * 3.0)))
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px) scale({round(env * breath_scale, 3)});">
          <div style="width:440px;height:620px;margin:0 auto 28px auto;background:#0B1120;border:6px solid {border};border-radius:48px;padding:28px;display:flex;flex-direction:column;justify-content:space-between;box-shadow:0 24px 60px rgba(0,0,0,0.55);">
            <div style="width:110px;height:12px;background:{border};border-radius:99px;margin:0 auto;"></div>
            <div style="flex:1;margin:24px 0;border-radius:28px;background:linear-gradient(145deg,#1E293B,#0F172A);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:20px;border:2px solid {danger};">
              <svg width="110" height="110" viewBox="0 0 100 100">
                <polyline points="12,30 40,52 62,44 88,78" fill="none" stroke="{danger}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
                <polyline points="68,78 88,78 88,58" fill="none" stroke="{danger}" stroke-width="8" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <div style="font-size:46px;font-weight:800;color:#FFFFFF;margin-top:16px;">{kw0}</div>
            </div>
            <div style="height:16px;background:#1E293B;border-radius:99px;overflow:hidden;">
              <div style="width:{bar_w}%;height:100%;background:{danger};border-radius:99px;"></div>
            </div>
          </div>
          {f'<div class="headline-text" style="font-size:74px;font-weight:800;color:{accent};">{kw1}</div>' if kw1 else ''}
        </div>
        """

    if tpl == "before_after":
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px);">
          <div style="display:flex;flex-direction:column;gap:28px;width:880px;margin:0 auto;">
            <div style="background:rgba(244,63,94,0.14);border:4px solid {danger};border-radius:32px;padding:34px 40px;transform:translateX({round((1-s1)*60,1)}px);opacity:{round(max(0.1,s1),2)};">
              <div style="font-size:46px;font-weight:800;color:{danger};margin-bottom:10px;">قبل</div>
              <div class="headline-text" style="font-size:72px;font-weight:800;color:#FFFFFF;">{kw0}</div>
            </div>
            <div style="background:rgba(16,185,129,0.16);border:4px solid {success};border-radius:32px;padding:34px 40px;transform:translateX({round((1-s2)*-60,1)}px) scale({breath_scale});opacity:{round(max(0.1,s2),2)};">
              <div style="font-size:46px;font-weight:800;color:{success};margin-bottom:10px;">بعد</div>
              <div class="headline-text" style="font-size:72px;font-weight:800;color:{accent};">{kw1 or kw0}</div>
            </div>
          </div>
        </div>
        """

    if tpl == "checklist":
        items = [k for k in [kw0, kw1, kw2] if k]
        staggers = [s1, s2, s3]
        rows_html = ""
        for idx, item in enumerate(items):
            st = staggers[min(idx, 2)]
            rows_html += f"""
            <div style="display:flex;align-items:center;gap:24px;background:{surface};border:3px solid {border};border-radius:28px;padding:28px 36px;transform:translateY({round((1-st)*35,1)}px);opacity:{round(max(0.1,st),2)};">
              <div style="width:64px;height:64px;border-radius:50%;background:{success};display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                <svg width="38" height="38" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7" fill="none" stroke="#090D16" stroke-width="3.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
              </div>
              <div style="font-size:64px;font-weight:800;color:#FFFFFF;">{item}</div>
            </div>
            """
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px); width:880px; margin:0 auto;">
          <div style="display:flex;flex-direction:column;gap:22px;">
            {rows_html}
          </div>
        </div>
        """

    if tpl == "steps_flow":
        items = [k for k in [kw0, kw1, kw2] if k]
        staggers = [s1, s2, s3]
        steps_html = ""
        for idx, item in enumerate(items):
            st = staggers[min(idx, 2)]
            steps_html += f"""
            <div style="display:flex;align-items:center;gap:24px;background:{surface};border:3px solid {accent if idx==len(items)-1 else border};border-radius:28px;padding:26px 36px;transform:scale({round(0.9 + 0.1*st,3)});opacity:{round(max(0.1,st),2)};">
              <div style="width:66px;height:66px;border-radius:20px;background:{accent};color:#090D16;font-size:48px;font-weight:800;display:flex;align-items:center;justify-content:center;flex-shrink:0;">
                {idx+1}
              </div>
              <div style="font-size:62px;font-weight:800;color:#FFFFFF;">{item}</div>
            </div>
            """
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px); width:880px; margin:0 auto;">
          <div style="display:flex;flex-direction:column;gap:20px;">
            {steps_html}
          </div>
        </div>
        """

    if tpl == "versus":
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px); width:880px; margin:0 auto;">
          <div style="background:{surface};border:3px solid {danger};border-radius:30px;padding:32px;margin-bottom:20px;opacity:{round(max(0.1,s1),2)};">
            <div style="font-size:68px;font-weight:800;color:#FCA5A5;">{kw0}</div>
          </div>
          <div style="width:96px;height:96px;border-radius:50%;background:{accent};color:#090D16;font-size:46px;font-weight:800;display:flex;align-items:center;justify-content:center;margin:-10px auto 10px auto;transform:scale({breath_scale});">
            VS
          </div>
          <div style="background:{surface};border:4px solid {accent};border-radius:30px;padding:32px;opacity:{round(max(0.1,s2),2)};">
            <div class="headline-text" style="font-size:74px;font-weight:800;color:{accent};">{kw1 or kw0}</div>
          </div>
        </div>
        """

    if tpl == "fullscreen_image":
        img_path = scene.get("image_path", "")
        kb_scale = round(1.0 + 0.06 * (local_t / max(1.0, scene_dur)), 4)
        img_tag = ""
        if img_path and os.path.exists(img_path):
            with open(img_path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode("ascii")
            img_tag = f'<img src="data:image/jpeg;base64,{b64}" style="width:100%;height:100%;object-fit:cover;transform:scale({kb_scale});"/>'
        else:
            img_tag = f'<div style="width:100%;height:100%;background:radial-gradient(circle at 50% 40%, {secondary}33, #090D16);transform:scale({kb_scale});display:flex;align-items:center;justify-content:center;">{get_contextual_svg_icon(visual_query, accent, secondary, danger, local_t)}</div>'
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px); width:900px; margin:0 auto;">
          <div style="width:900px;height:680px;border-radius:40px;overflow:hidden;border:4px solid {accent};box-shadow:0 24px 64px rgba(0,0,0,0.65);margin-bottom:26px;position:relative;">
            {img_tag}
          </div>
          <div class="headline-text" style="font-size:76px;font-weight:800;color:#FFFFFF;">{kw0}</div>
        </div>
        """

    if tpl == "anchor_expand":
        svg_icon = get_contextual_svg_icon(visual_query, accent, secondary, danger, local_t)
        anchor_shift_y = round(state_b_prog * 85.0, 1)
        anchor_sc = round(1.0 - 0.18 * state_b_prog, 3)
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px); width:880px; margin:0 auto;">
          <div style="opacity:{round(max(0.0, state_b_prog), 2)}; transform: translateY({round((1.0-state_b_prog)*35.0, 1)}px); margin-bottom:24px; background:{surface}; border:4px solid {accent}; border-radius:32px; padding:28px;">
            <div class="headline-text" style="font-size:78px;font-weight:800;color:{accent};">{kw1 or kw0}</div>
          </div>
          <div style="transform: translateY({anchor_shift_y}px) scale({anchor_sc}); background:rgba(15,23,42,0.85); border:3px solid {border}; border-radius:32px; padding:26px;">
            <div style="display:flex;justify-content:center;align-items:center;margin-bottom:18px;">{svg_icon}</div>
            <div class="headline-text" style="font-size:74px;font-weight:800;color:#FFFFFF;">{kw0}</div>
          </div>
        </div>
        """

    if tpl == "process_simulation":
        card_border = success if state_b_prog > 0.5 else danger
        status_label = "الحالة بعد التحول الفوري ✓" if state_b_prog > 0.5 else "الحالة قبل المعالجة..."
        active_kw = (kw1 or kw0) if state_b_prog > 0.5 else kw0
        prompt_fill = int(min(100, (local_t / max(0.3, pivot_rel)) * 100))
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px); width:880px; margin:0 auto;">
          <div style="font-size:48px;font-weight:800;color:{card_border};margin-bottom:16px;">{status_label}</div>
          <div style="background:{surface};border:5px solid {card_border};border-radius:36px;padding:44px 36px;margin-bottom:24px;transform:scale({breath_scale});">
            <div class="headline-text" style="font-size:80px;font-weight:800;color:#FFFFFF;">{active_kw}</div>
          </div>
          <div style="display:flex;align-items:center;justify-content:space-between;background:#0F172A;border:3px solid {border};border-radius:99px;padding:18px 32px;">
            <div style="font-size:44px;font-weight:700;color:#CBD5E1;">أمر التشغيل ({prompt_fill}%)</div>
            <div style="background:{accent};color:#090D16;font-size:44px;font-weight:800;padding:10px 28px;border-radius:99px;">Generate ⚡</div>
          </div>
        </div>
        """

    if tpl == "dual_layer_proof":
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px); width:880px; margin:0 auto;">
          <div style="background:{surface};border:4px solid {secondary};border-radius:36px;overflow:hidden;">
            <div style="padding:32px;background:rgba(16,185,129,0.16);border-bottom:3px solid {border};opacity:{round(max(0.15, state_b_prog), 2)};">
              <div class="headline-text" style="font-size:74px;font-weight:800;color:{accent};">{kw1 or kw0}</div>
            </div>
            <div style="padding:36px;background:rgba(15,23,42,0.92);">
              <div class="headline-text" style="font-size:74px;font-weight:800;color:#FFFFFF;">{kw0}</div>
            </div>
          </div>
        </div>
        """

    if tpl == "editorial_proof_card":
        hl_w = int(min(100, state_b_prog * 100))
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px); width:880px; margin:0 auto;">
          <div style="background:#1E293B;border:4px solid {accent};border-radius:34px;padding:38px;text-align:right;">
            <div style="font-size:44px;font-weight:800;color:{secondary};margin-bottom:18px;">RESEARCH & EVIDENCE • دليل موثق</div>
            <div class="headline-text" style="font-size:76px;font-weight:800;color:#FFFFFF;margin-bottom:20px;">{kw0}</div>
            <div style="display:inline-block;background:linear-gradient(90deg, {accent} {hl_w}%, transparent {hl_w}%);padding:8px 18px;border-radius:14px;">
              <div class="headline-text" style="font-size:72px;font-weight:800;color:#090D16;">{kw1 or kw0}</div>
            </div>
          </div>
        </div>
        """

    if tpl == "minimalist_reset":
        return f"""
        <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px); width:860px; margin:0 auto; padding:60px 20px;">
          <div class="headline-text" style="font-size:78px;font-weight:800;color:#FFFFFF;margin-bottom:22px;letter-spacing:1px;">{kw0}</div>
          {f'<div class="headline-text" style="font-size:72px;font-weight:800;color:#CBD5E1;opacity:{round(max(0.2, state_b_prog), 2)};">{kw1}</div>' if kw1 else ''}
        </div>
        """

    # cta_end
    arrow_y = round(math.sin(local_t * 6.0) * 16.0, 2)
    return f"""
    <div class="stage-card" style="opacity:{opacity}; transform: translateY({translate_y}px) scale({round(env * breath_scale, 3)}); width:880px; margin:0 auto;">
      <div class="headline-text" style="font-size:88px;font-weight:800;color:#FFFFFF;margin-bottom:24px;">
        {kw0}
      </div>
      <div style="background:{accent};color:#090D16;font-size:72px;font-weight:800;padding:28px 48px;border-radius:99px;display:inline-block;margin-bottom:36px;box-shadow:0 16px 40px rgba(250,204,21,0.35);">
        {kw1 or 'الرابط في الأسفل'}
      </div>
      <div style="transform: translateY({arrow_y}px);">
        <svg width="130" height="130" viewBox="0 0 100 100">
          <path d="M50 15 V78 M24 54 L50 82 L76 54" fill="none" stroke="{accent}" stroke-width="12" stroke-linecap="round" stroke-linejoin="round"/>
        </svg>
      </div>
    </div>
    """


def render_caption_html(words: List[Dict[str, Any]], t: float, theme: Dict[str, Any]) -> str:
    """
    يبني شريط الكابشن المتزامن مع الكلمة (بحد أقصى 6 كلمات في الشاشة، حجم خط 54px >= 44px،
    تكبير الكلمة المنطوقة حالياً 15% وتلوينها باللون المميز مع هامش جانبي يمنع تداخل الكلمات).
    """
    if not words:
        return ""

    # إيجاد الكلمة المنطوقة حالياً أو أقرب كلمة
    active_idx = 0
    for i, w in enumerate(words):
        if w["start"] <= t <= w["end"]:
            active_idx = i
            break
        if w["start"] <= t:
            active_idx = i

    # تقسيم الكلمات إلى مجموعات من 5 كلمات كحد أقصى (أقل من الحد الأقصى 6–7 كلمات)
    chunk_size = 5
    chunk_start = (active_idx // chunk_size) * chunk_size
    chunk_words = words[chunk_start:chunk_start + chunk_size]

    accent = theme["accent_primary"]
    spans = []
    for w in chunk_words:
        is_active = (w["index"] == active_idx) and (w["start"] - 0.06 <= t <= w["end"] + 0.06)
        if is_active:
            spans.append(
                f'<span class="caption-word active-word" style="display:inline-block;font-size:56px;font-weight:800;color:{accent};transform:scale(1.15);margin:0 12px;padding:2px 6px;">{w["word"]}</span>'
            )
        else:
            spans.append(
                f'<span class="caption-word" style="display:inline-block;font-size:50px;font-weight:800;color:#FFFFFF;margin:0 7px;padding:2px 4px;">{w["word"]}</span>'
            )

    return "".join(spans)


def build_frame_html(
    scene: Dict[str, Any],
    words: List[Dict[str, Any]],
    theme: Dict[str, Any],
    t: float,
    total_duration: float,
) -> str:
    """
    يبني وثيقة HTML/CSS/SVG كاملة لفريم واحد بدقة 1080×1920 مع التزام صارم بالمناطق الآمنة:
    - المنطقة الآمنة العلوية: 0..250px فارغة من أي نص.
    - منطقة العرض البصري (#visual-stage): 270px..1240px.
    - منطقة الكابشن (#caption-box): 1310px..1540px (فوق المنطقة الآمنة السفلية 1580px..1920px).
    """
    local_t = max(0.0, t - float(scene["start"]))
    scene_dur = max(0.5, float(scene["end"]) - float(scene["start"]))
    stage_html = render_template_stage_html(scene, theme, local_t, scene_dur)
    caption_html = render_caption_html(words, t, theme)

    bg1 = theme["bg_primary"]
    bg2 = theme["bg_secondary"]
    accent = theme["accent_primary"]
    border = theme["surface_border"]
    prog_pct = round(min(100.0, max(0.0, (t / max(1.0, total_duration)) * 100.0)), 2)
    glow_y = int(620 + math.sin(t * 1.8) * 70)

    return f"""<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head>
<meta charset="utf-8"/>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    width: 1080px;
    height: 1920px;
    overflow: hidden;
    background: {bg1};
    font-family: {theme["font_family"]};
    direction: rtl;
    color: #FFFFFF;
  }}
  #root-canvas {{
    width: 1080px;
    height: 1920px;
    position: relative;
    overflow: hidden;
    background: radial-gradient(circle at 50% {glow_y}px, {bg2} 0%, {bg1} 78%);
  }}
  #visual-stage {{
    position: absolute;
    top: 280px;
    left: 70px;
    right: 70px;
    height: 940px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    text-align: center;
  }}
  .stage-card {{
    width: 100%;
    max-width: 920px;
    padding: 20px;
    text-align: center;
  }}
  #caption-container {{
    position: absolute;
    top: 1300px;
    left: 64px;
    right: 64px;
    min-height: 180px;
    max-height: 250px;
    background: rgba(15, 23, 42, 0.88);
    border: 3px solid {border};
    border-radius: 34px;
    padding: 26px 32px;
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    justify-content: center;
    text-align: center;
    line-height: 1.45;
    box-shadow: 0 18px 44px rgba(0, 0, 0, 0.5);
  }}
  #progress-track {{
    position: absolute;
    top: 1564px;
    left: 120px;
    right: 120px;
    height: 8px;
    background: rgba(255,255,255,0.12);
    border-radius: 99px;
    overflow: hidden;
  }}
  #progress-fill {{
    width: {prog_pct}%;
    height: 100%;
    background: {accent};
    border-radius: 99px;
  }}
</style>
</head>
<body>
  <div id="root-canvas">
    <div id="visual-stage">
      {stage_html}
    </div>
    <div id="caption-container">
      {caption_html}
    </div>
    <div id="progress-track">
      <div id="progress-fill"></div>
    </div>
  </div>
</body>
</html>"""

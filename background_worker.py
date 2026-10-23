"""
background_worker.py - محرك العمل المستمر في الخلفية وحفظ الجلسة التلقائي (Persistent Background Worker & Auto-Resume)
========================================================================================================================
يضمن هذا المحرك:
1. استمرار معالجة ورندرة الفيديو في الخلفية (Background Daemon Thread) بنسبة 100% حتى لو خرج المستخدم من متصفح
   جوجل كروم (Google Chrome) أو أغلق شاشة الهاتف أو انقطع اتصال الإنترنت لديه!
2. حفظ حالة التقدم والملف النهائي والكابشن لحظياً على القرص (`outputs/persistent_job_state.json`)، بحيث بمجرد عودة
   المستخدم وفتح الموقع مرة أخرى، يظهر له شريط التقدم الحي (إن كان لا يزال يعالج) أو يظهر له الفيديو الجاهز للتحميل فوراً!
3. تحرير الذاكرة العشوائية (OS-Level RAM Trimming عبر `glibc malloc_trim`) بعد كل مرحلة لمنع انهيار السيرفر (OOM).
"""

import os
import gc
import json
import time
import ctypes
import logging
import threading
import traceback
from typing import Dict, Any, Optional, Callable

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def force_free_ram():
    """
    تحرير الذاكرة العشوائية في بايثون وإجبار نظام لينكس (glibc) على إرجاع الصفحات المحررة
    فوراً إلى نظام التشغيل لمنع تجاوز حد 1GB RAM على Streamlit Cloud.
    """
    try:
        gc.collect()
        libc = ctypes.CDLL("libc.so.6")
        libc.malloc_trim(0)
    except Exception:
        pass


class PersistentBackgroundJobManager:
    """
    مدير المهام الخلفية المستقل عن جلسة المتصفح (WebSocket-Independent Job Manager).
    يعمل في Thread مستقل على السيرفر ويحفظ الحالة في الذاكرة وعلى القرص الصلب معاً.
    """

    def __init__(self, state_file_path: str):
        self.state_file_path = state_file_path
        self._lock = threading.Lock()
        self._worker_thread: Optional[threading.Thread] = None
        self._state: Dict[str, Any] = self._load_state_from_disk()

    def _default_state(self) -> Dict[str, Any]:
        return {
            "job_id": None,
            "status": "idle",  # idle | running | completed | failed
            "progress": 0.0,
            "status_text": "",
            "error_message": None,
            "started_at": 0.0,
            "updated_at": 0.0,
            "input_path": None,
            "output_path": None,
            "selected_style": None,
            "caption_mode": "bottom_modern",
            "file_hash": None,
            "media_analysis": None,
            "caption_words": [],
            "caption_sentences": [],
            "eff_params": {}
        }

    def _load_state_from_disk(self) -> Dict[str, Any]:
        if os.path.exists(self.state_file_path):
            try:
                with open(self.state_file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    base = self._default_state()
                    base.update(data)
                    # إذا كانت الحالة على القرص "running" لكن لا يوجد خيط نشط بعد إعادة تشغيل السيرفر، نتحقق من الملف الناتج
                    if base.get("status") == "running":
                        out_p = base.get("output_path")
                        if out_p and os.path.exists(out_p) and os.path.getsize(out_p) > 10240:
                            base["status"] = "completed"
                            base["progress"] = 1.0
                            base["status_text"] = "اكتمل إنتاج الفيديو في الخلفية بنجاح!"
                        elif time.time() - float(base.get("updated_at", 0.0)) > 600:
                            base["status"] = "idle"
                    return base
            except Exception as e:
                logger.warning(f"تعذر قراءة ملف حالة الخلفية: {e}")
        return self._default_state()

    def _save_state_to_disk_unlocked(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.state_file_path)), exist_ok=True)
            tmp_path = self.state_file_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(self._state, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self.state_file_path)
        except Exception as e:
            logger.debug(f"ملاحظة أثناء حفظ حالة المهمة على القرص: {e}")

    def get_state(self) -> Dict[str, Any]:
        with self._lock:
            # التحقق مما إذا كان الخيط الخلفي لا يزال يعمل
            if self._state.get("status") == "running":
                if self._worker_thread is None or not self._worker_thread.is_alive():
                    out_p = self._state.get("output_path")
                    if out_p and os.path.exists(out_p) and os.path.getsize(out_p) > 10240:
                        self._state["status"] = "completed"
                        self._state["progress"] = 1.0
                        self._state["status_text"] = "اكتمل إنتاج الفيديو بنجاح!"
                        self._save_state_to_disk_unlocked()
            return dict(self._state)

    def is_running(self) -> bool:
        with self._lock:
            return bool(
                self._state.get("status") == "running"
                and self._worker_thread is not None
                and self._worker_thread.is_alive()
            )

    def update_progress(self, percent: float, text: str):
        with self._lock:
            self._state["progress"] = round(min(1.0, max(0.0, float(percent))), 3)
            self._state["status_text"] = str(text)
            self._state["updated_at"] = time.time()
            self._save_state_to_disk_unlocked()

    def clear_job(self):
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return False
            self._state = self._default_state()
            self._save_state_to_disk_unlocked()
            return True

    def start_job(
        self,
        runner_func: Callable[..., str],
        runner_kwargs: Dict[str, Any],
        job_meta: Dict[str, Any],
        cleanup_func: Optional[Callable[[], None]] = None
    ) -> str:
        """
        إطلاق معالجة الفيديو في خيط خلفي مستقل تماماً عن متصفح المستخدم،
        بحيث لا يتوقف أبداً عند الخروج من Google Chrome أو انقطاع الإنترنت.
        """
        with self._lock:
            if self._worker_thread is not None and self._worker_thread.is_alive():
                return str(self._state.get("job_id", "active"))

            job_id = f"job_{int(time.time())}"
            self._state = self._default_state()
            self._state.update({
                "job_id": job_id,
                "status": "running",
                "progress": 0.02,
                "status_text": "🚀 بدأت المعالجة في الخلفية... يمكنك الخروج من المتصفح والعودة لاحقاً بأمان!",
                "error_message": None,
                "started_at": time.time(),
                "updated_at": time.time(),
                "input_path": job_meta.get("input_path"),
                "output_path": job_meta.get("output_path"),
                "selected_style": job_meta.get("selected_style"),
                "caption_mode": job_meta.get("caption_mode", "bottom_modern"),
                "file_hash": job_meta.get("file_hash"),
                "media_analysis": job_meta.get("media_analysis"),
                "eff_params": job_meta.get("eff_params", {})
            })
            self._save_state_to_disk_unlocked()

        def _background_target():
            try:
                force_free_ram()
                kwargs_copy = dict(runner_kwargs)
                kwargs_copy["progress_cb"] = self.update_progress

                final_out_path = runner_func(**kwargs_copy)

                from transcriber import get_last_extracted_transcript
                words_ext, sents_ext = get_last_extracted_transcript()

                with self._lock:
                    self._state["status"] = "completed"
                    self._state["progress"] = 1.0
                    self._state["status_text"] = "🎉 اكتمل إنتاج ورندرة الفيديو في الخلفية بنجاح!"
                    self._state["output_path"] = final_out_path
                    self._state["caption_words"] = words_ext
                    self._state["caption_sentences"] = sents_ext
                    self._state["updated_at"] = time.time()
                    self._save_state_to_disk_unlocked()

            except Exception as err:
                logger.error(f"خطأ في المهمة الخلفية: {err}\n{traceback.format_exc()}")
                with self._lock:
                    self._state["status"] = "failed"
                    self._state["error_message"] = str(err)
                    self._state["status_text"] = f"❌ توقفت المعالجة بسبب خطأ: {str(err)}"
                    self._state["updated_at"] = time.time()
                    self._save_state_to_disk_unlocked()
            finally:
                if cleanup_func is not None:
                    try:
                        cleanup_func()
                    except Exception:
                        pass
                force_free_ram()

        self._worker_thread = threading.Thread(target=_background_target, name=f"StudioWorker_{job_id}", daemon=True)
        self._worker_thread.start()
        return job_id


_SINGLETON_MANAGER: Optional[PersistentBackgroundJobManager] = None
_SINGLETON_LOCK = threading.Lock()


def get_background_job_manager(state_file_path: str) -> PersistentBackgroundJobManager:
    global _SINGLETON_MANAGER
    with _SINGLETON_LOCK:
        if _SINGLETON_MANAGER is None:
            _SINGLETON_MANAGER = PersistentBackgroundJobManager(state_file_path=state_file_path)
        return _SINGLETON_MANAGER

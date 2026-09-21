"""
TENRA Voice Twin - SIP / VoIP Gateway
pyVoIP tabanlı profesyonel telefon santrali ve SIP yönlendirme motoru.
Gelen SIP aramalarını otomatik yanıtlar, Ahmet Eren'in ses ikiziyle konuşur ve görüşmeyi özetler.
"""

import os
import io
import time
import wave
import threading
import logging
import asyncio
from typing import Optional

try:
    import soundfile as sf
    import numpy as np
except ImportError:
    sf = None
    np = None

from voice_twin.call_logs_db import (
    get_setting,
    set_setting,
    add_call,
    get_assistant_status
)
from voice_twin.call_agent import handle_call_turn, summarize_and_save_call
from voice_twin.tts_engine import synthesize_speech

logger = logging.getLogger("TENRA_SIP")
logging.basicConfig(level=logging.INFO)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))


class TenraSIPGateway:
    _instance: Optional["TenraSIPGateway"] = None

    def __init__(self):
        self.phone = None
        self.is_running = False
        self.last_status = "Durduruldu"
        self.active_calls = 0
        self.last_caller = None
        self.lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "TenraSIPGateway":
        if cls._instance is None:
            cls._instance = TenraSIPGateway()
        return cls._instance

    def get_config(self) -> dict:
        return {
            "sip_server": get_setting("sip_server", ""),
            "sip_port": int(get_setting("sip_port", "5060")),
            "sip_user": get_setting("sip_user", ""),
            "sip_password": get_setting("sip_password", ""),
            "sip_my_ip": get_setting("sip_my_ip", "0.0.0.0"),
            "sip_auto_start": get_setting("sip_auto_start", "0") == "1",
            "is_running": self.is_running,
            "last_status": self.last_status,
            "active_calls": self.active_calls,
            "last_caller": self.last_caller
        }

    def save_config(self, cfg: dict):
        if "sip_server" in cfg:
            set_setting("sip_server", str(cfg["sip_server"]).strip())
        if "sip_port" in cfg:
            set_setting("sip_port", str(cfg["sip_port"]).strip())
        if "sip_user" in cfg:
            set_setting("sip_user", str(cfg["sip_user"]).strip())
        if "sip_password" in cfg:
            set_setting("sip_password", str(cfg["sip_password"]).strip())
        if "sip_my_ip" in cfg:
            set_setting("sip_my_ip", str(cfg["sip_my_ip"]).strip())
        if "sip_auto_start" in cfg:
            set_setting("sip_auto_start", "1" if cfg["sip_auto_start"] else "0")

    def start(self) -> dict:
        with self.lock:
            if self.is_running:
                return {"status": "ok", "message": "SIP Gateway zaten calisiyor."}

            cfg = self.get_config()
            server = cfg["sip_server"]
            user = cfg["sip_user"]
            pwd = cfg["sip_password"]
            port = cfg["sip_port"]
            my_ip = cfg["sip_my_ip"] or "0.0.0.0"

            if not server or not user:
                self.last_status = "Hata: Sunucu ve Kullanici Adi gerekli"
                return {"status": "error", "message": "SIP Sunucu ve Kullanici Adi tanimlanmamis."}

            try:
                from pyVoIP.VoIP import VoIPPhone

                self.phone = VoIPPhone(
                    server=server,
                    port=port,
                    username=user,
                    password=pwd,
                    myIP=my_ip,
                    callCallback=self._on_incoming_call
                )
                self.phone.start()
                self.is_running = True
                self.last_status = f"Aktif ({user}@{server})"
                logger.info(f"TENRA SIP Gateway baslatildi: {user}@{server}:{port}")
                return {"status": "ok", "message": f"SIP Gateway baslatildi ({user}@{server})"}
            except Exception as e:
                self.is_running = False
                self.last_status = f"Baslatma Hatasi: {e}"
                logger.error(f"SIP baslatma hatasi: {e}")
                return {"status": "error", "message": str(e)}

    def stop(self) -> dict:
        with self.lock:
            if not self.is_running or not self.phone:
                self.is_running = False
                self.last_status = "Durduruldu"
                return {"status": "ok", "message": "SIP Gateway zaten durdurulmus."}

            try:
                self.phone.stop()
            except Exception as e:
                logger.warning(f"SIP kapatma sirasinda uyari: {e}")
            self.phone = None
            self.is_running = False
            self.last_status = "Durduruldu"
            logger.info("TENRA SIP Gateway durduruldu.")
            return {"status": "ok", "message": "SIP Gateway durduruldu."}

    def _convert_wav_to_pcm(self, audio_path: str) -> bytes:
        """WAV/MP3 ses dosyasını telefon santrali standardı olan 8000Hz 16-bit Mono PCM'e dönüştürür."""
        try:
            if sf is not None and np is not None:
                data, samplerate = sf.read(audio_path)
                # Mono'ya cevir
                if len(data.shape) > 1:
                    data = data.mean(axis=1)
                
                # Resample 8000Hz
                if samplerate != 8000:
                    import scipy.signal
                    num_samples = int(len(data) * 8000 / samplerate)
                    data = scipy.signal.resample(data, num_samples)
                
                data_int16 = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
                return data_int16.tobytes()
        except Exception as e:
            logger.warning(f"Resample hatasi: {e}, fallback wave modulu...")

        # Fallback standart wave
        try:
            with wave.open(audio_path, 'rb') as wf:
                return wf.readframes(wf.getnframes())
        except Exception:
            return b""

    def _on_incoming_call(self, call):
        """Gelen SIP aramasını ayrı bir iş parçacığında karşılar."""
        threading.Thread(target=self._handle_call_thread, args=(call,), daemon=True).start()

    def _handle_call_thread(self, call):
        self.active_calls += 1
        caller = "Bilinmeyen Numara"
        try:
            # Caller ID tespit et
            if hasattr(call, "request") and call.request and "From" in call.request.headers:
                from_header = call.request.headers["From"]
                caller = str(from_header).split(";")[0].replace("<", "").replace(">", "").strip()
        except Exception:
            pass

        self.last_caller = caller
        logger.info(f"[SIP INCOMING] Arama yakalandi: {caller}")

        try:
            # Aramayı aç
            call.answer()
            logger.info(f"[SIP] Arama cevaplandi: {caller}")

            # Durumu al ve selamlama metnini hazirla
            st = get_assistant_status()
            status = st.get("status", "Okulda")
            status_lower = status.lower()

            if status == "Müsait":
                greeting_text = f"Selam! Ben Ahmet'in sesli asistanıyım. Ahmet şu an müsait, sizi dinliyorum."
            elif status == "Özel":
                greeting_text = f"Selam! Ben Ahmet'in sesli asistanıyım. Ahmet şu an biraz meşgul. Önemli bir şey mi vardı, not almamı ister misin?"
            else:
                greeting_text = f"Selam! Ben Ahmet'in sesli asistanıyım. Ahmet şu an {status_lower}. Önemli bir şey mi vardı, not almamı ister misin?"

            # Sentezle ve hatta ses ver
            greeting_audio = synthesize_speech(greeting_text)
            if greeting_audio and os.path.exists(greeting_audio):
                pcm_data = self._convert_wav_to_pcm(greeting_audio)
                if pcm_data:
                    # 160 baytlik RTP paketleri halinde hatta yaz (20ms paket standardı)
                    chunk_size = 320
                    for i in range(0, len(pcm_data), chunk_size):
                        if not call.answered:
                            break
                        call.write_audio(pcm_data[i:i + chunk_size])
                        time.sleep(0.02)

            # Basit diyalog ve dinleme dongusu (15 saniye)
            start_wait = time.time()
            history = [{"role": "assistant", "content": greeting_text}]

            # Kapanana kadar bekle
            while call.answered and (time.time() - start_wait < 30):
                time.sleep(1)

            # Çağrıyı veritabanına kaydet
            add_call(
                caller_name=caller,
                transcript=f"Asistan: {greeting_text}",
                summary=f"SIP Santral araması: {caller} aradı. Asistan karşıladı (Mod: {status}).",
                urgency="normal"
            )

        except Exception as e:
            logger.error(f"[SIP] Cagri yonetim hatasi: {e}")
        finally:
            try:
                call.hangup()
            except Exception:
                pass
            self.active_calls = max(0, self.active_calls - 1)
            logger.info(f"[SIP] Cagri sonlandi: {caller}")


# Global Gateway örneği
sip_gateway = TenraSIPGateway.get_instance()

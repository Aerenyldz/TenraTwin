"""
TENRA Voice Twin - SIP / VoIP Gateway (Faz 1)
pyVoIP ile yerel softphone / ileride NetGSM trunk.

Ses formatı (pyVoIP 1.6): 8 kHz, mono, 8-bit unsigned linear (sessizlik=128).
Whisper CPU'da çalışır (VRAM yok); TTS/RVC ve Ollama GPU'da kalır.
"""

from __future__ import annotations

import audioop
import logging
import os
import tempfile
import threading
import time
import wave
from typing import Optional

try:
    import numpy as np
    import soundfile as sf
except ImportError:
    sf = None
    np = None

from voice_twin.call_logs_db import (
    add_call,
    append_call_transcript,
    get_assistant_status,
    get_setting,
    set_setting,
    update_call_audio,
    update_call_record,
)
from voice_twin.call_agent import handle_call_turn, summarize_and_save_call, build_call_greeting
from voice_twin.call_recorder import save_call_recording
from voice_twin.tts_engine import synthesize_speech

logger = logging.getLogger("TENRA_SIP")
if not logger.handlers:
    logging.basicConfig(level=logging.INFO)

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))

# pyVoIP: 20 ms @ 8 kHz, 8-bit = 160 bayt
FRAME_8K_U8 = 160
SILENCE_U8 = b"\x80" * FRAME_8K_U8


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
            "sip_server": get_setting("sip_server", "127.0.0.1"),
            "sip_port": int(get_setting("sip_port", "5060")),
            "sip_user": get_setting("sip_user", "100"),
            "sip_password": get_setting("sip_password", "tenra100"),
            "sip_my_ip": get_setting("sip_my_ip", "127.0.0.1"),
            "sip_bind_port": int(get_setting("sip_bind_port", "5062")),
            "sip_auto_start": get_setting("sip_auto_start", "0") == "1",
            "gsm_auto_answer": get_setting("gsm_auto_answer", "0") == "1",
            "is_running": self.is_running,
            "last_status": self.last_status,
            "active_calls": self.active_calls,
            "last_caller": self.last_caller,
        }

    def save_config(self, cfg: dict):
        mapping = {
            "sip_server": "sip_server",
            "sip_port": "sip_port",
            "sip_user": "sip_user",
            "sip_password": "sip_password",
            "sip_my_ip": "sip_my_ip",
            "sip_bind_port": "sip_bind_port",
        }
        for key, db_key in mapping.items():
            if key in cfg and cfg[key] is not None:
                set_setting(db_key, str(cfg[key]).strip())
        if "sip_auto_start" in cfg:
            set_setting("sip_auto_start", "1" if cfg["sip_auto_start"] else "0")
        if "gsm_auto_answer" in cfg:
            set_setting("gsm_auto_answer", "1" if cfg["gsm_auto_answer"] else "0")

    def apply_local_lab_defaults(self):
        """MicroSIP + yerel Asterisk labı için hazır değerler."""
        self.save_config({
            "sip_server": "127.0.0.1",
            "sip_port": 5060,
            "sip_user": "100",
            "sip_password": "tenra100",
            "sip_my_ip": "127.0.0.1",
            "sip_bind_port": 5062,
            "sip_auto_start": False,
            "gsm_auto_answer": False,
        })

    def start(self) -> dict:
        with self.lock:
            if self.is_running:
                return {"status": "ok", "message": "SIP Gateway zaten çalışıyor."}

            cfg = self.get_config()
            server = (cfg["sip_server"] or "").strip()
            user = (cfg["sip_user"] or "").strip()
            pwd = cfg["sip_password"] or ""
            port = int(cfg["sip_port"] or 5060)
            my_ip = (cfg["sip_my_ip"] or "127.0.0.1").strip()
            bind_port = int(cfg.get("sip_bind_port") or 5062)

            if not server or not user:
                self.last_status = "Hata: Sunucu ve kullanıcı gerekli"
                return {"status": "error", "message": "SIP sunucu ve kullanıcı tanımlı değil."}

            try:
                from pyVoIP.VoIP import VoIPPhone

                self.phone = VoIPPhone(
                    server,
                    port,
                    user,
                    pwd,
                    myIP=my_ip,
                    callCallback=self._on_incoming_call,
                    sipPort=bind_port,
                    rtpPortLow=10000,
                    rtpPortHigh=20000,
                )
                self.phone.start()
                self.is_running = True
                self.last_status = f"Aktif ({user}@{server}:{port}, bind={bind_port})"
                logger.info(
                    "TENRA SIP Gateway başladı: %s@%s:%s (local SIP %s)",
                    user, server, port, bind_port,
                )
                return {
                    "status": "ok",
                    "message": f"SIP Gateway başladı ({user}@{server})",
                    "config": self.get_config(),
                }
            except Exception as e:
                self.is_running = False
                self.phone = None
                self.last_status = f"Başlatma hatası: {e}"
                logger.error("SIP başlatma hatası: %s", e)
                return {"status": "error", "message": str(e)}

    def stop(self) -> dict:
        with self.lock:
            if not self.is_running or not self.phone:
                self.is_running = False
                self.last_status = "Durduruldu"
                return {"status": "ok", "message": "SIP Gateway zaten durdurulmuş."}
            try:
                self.phone.stop()
            except Exception as e:
                logger.warning("SIP kapatma uyarısı: %s", e)
            self.phone = None
            self.is_running = False
            self.last_status = "Durduruldu"
            logger.info("TENRA SIP Gateway durduruldu.")
            return {"status": "ok", "message": "SIP Gateway durduruldu."}

    # ─── Ses dönüşümü (pyVoIP = 8-bit unsigned @ 8 kHz) ─────────────────────

    def _file_to_pcmu8(self, audio_path: str) -> bytes:
        """WAV/MP3 → 8 kHz mono 8-bit unsigned (sessizlik 0x80)."""
        try:
            if sf is not None and np is not None:
                data, sr = sf.read(audio_path, always_2d=False)
                if getattr(data, "ndim", 1) > 1:
                    data = data.mean(axis=1)
                data = np.asarray(data, dtype=np.float64)
                # float [-1,1] → int16
                pcm16 = (np.clip(data, -1.0, 1.0) * 32767.0).astype(np.int16).tobytes()
                if sr != 8000:
                    pcm16, _ = audioop.ratecv(pcm16, 2, 1, int(sr), 8000, None)
                pcm8_s = audioop.lin2lin(pcm16, 2, 1)  # signed 8-bit
                return audioop.bias(pcm8_s, 1, 128)  # unsigned for pyVoIP
        except Exception as e:
            logger.warning("sf resample: %s — wave fallback", e)

        try:
            with wave.open(audio_path, "rb") as wf:
                nch, sw, sr, nframes = (
                    wf.getnchannels(), wf.getsampwidth(), wf.getframerate(), wf.getnframes()
                )
                raw = wf.readframes(nframes)
            if nch > 1:
                raw = audioop.tomono(raw, sw, 0.5, 0.5)
            if sw != 2:
                raw = audioop.lin2lin(raw, sw, 2)
                sw = 2
            if sr != 8000:
                raw, _ = audioop.ratecv(raw, 2, 1, sr, 8000, None)
            pcm8_s = audioop.lin2lin(raw, 2, 1)
            return audioop.bias(pcm8_s, 1, 128)
        except Exception as e:
            logger.error("PCM dönüşüm başarısız: %s", e)
            return b""

    def _u8_to_wav16(self, pcm_u8: bytes, out_path: str) -> str:
        """pyVoIP buffer → Whisper için 16-bit WAV."""
        if not pcm_u8:
            return ""
        signed = audioop.bias(pcm_u8, 1, -128)
        pcm16 = audioop.lin2lin(signed, 1, 2)
        with wave.open(out_path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(pcm16)
        return out_path

    def _rms_u8(self, chunk: bytes) -> float:
        if not chunk:
            return 0.0
        signed = audioop.bias(chunk, 1, -128)
        try:
            return float(audioop.rms(signed, 1))
        except Exception:
            return 0.0

    def _play_pcm_on_call(self, call, pcm_u8: bytes) -> None:
        """pyVoIP buffer'a yazar ve süre kadar ANSWERED bekler."""
        if not pcm_u8:
            return
        try:
            from pyVoIP.VoIP import CallState
        except ImportError:
            CallState = None

        call.write_audio(pcm_u8)
        duration = len(pcm_u8) / 8000.0
        deadline = time.time() + duration + 0.35
        while time.time() < deadline:
            if CallState and getattr(call, "state", None) != CallState.ANSWERED:
                break
            if hasattr(call, "answered") and not call.answered:
                break
            time.sleep(0.05)

    def _is_answered(self, call) -> bool:
        try:
            from pyVoIP.VoIP import CallState
            st = getattr(call, "state", None)
            if st is not None:
                return st == CallState.ANSWERED
        except Exception:
            pass
        return bool(getattr(call, "answered", False))

    # ─── Çağrı yaşam döngüsü ────────────────────────────────────────────────

    def _on_incoming_call(self, call):
        threading.Thread(
            target=self._handle_call_thread, args=(call,), daemon=True, name="tenra-sip-call"
        ).start()

    def _handle_call_thread(self, call):
        self.active_calls += 1
        caller = self._extract_caller(call)
        self.last_caller = caller
        logger.info("[SIP INCOMING] %s", caller)

        call_id = None
        history: list[dict] = []
        audio_clips: list[str] = []
        transcript_parts: list[str] = []

        try:
            call.answer()
            logger.info("[SIP] Cevaplandı: %s", caller)

            st = get_assistant_status()
            status = st.get("status", "Okulda")
            greeting = self._build_greeting(status)
            history.append({"role": "assistant", "content": greeting})
            transcript_parts.append(f"Asistan: {greeting}")

            call_id = add_call(
                caller_name=caller,
                transcript=f"Asistan: {greeting}",
                summary=f"SIP araması: {caller} (Mod: {status}).",
                urgency="normal",
            )

            greet_path = synthesize_speech(greeting)
            if greet_path and os.path.exists(greet_path):
                audio_clips.append(greet_path)
                pcm = self._file_to_pcmu8(greet_path)
                self._play_pcm_on_call(call, pcm)
                logger.info("[SIP] Selamlama çalındı (%d bayt)", len(pcm))

            # Full-duplex turlar
            max_turns = 8
            for turn in range(max_turns):
                if not self._is_answered(call):
                    break
                logger.info("[SIP] Dinleniyor (tur %d)...", turn + 1)
                utt = self._record_utterance(call, max_seconds=12.0)
                if not utt or len(utt) < 8000 * 0.4:  # ~0.4 sn
                    logger.info("[SIP] Sessizlik / çok kısa — bitir")
                    break

                wav_path = os.path.join(
                    tempfile.gettempdir(), f"tenra_sip_utt_{call_id}_{turn}.wav"
                )
                self._u8_to_wav16(utt, wav_path)
                audio_clips.append(wav_path)

                from voice_twin.pipeline import transcribe_wav
                text = transcribe_wav(wav_path, "tr", soft_vad=True)
                logger.info("[SIP] STT: %r", text)
                if not (text or "").strip():
                    retry = "Sesini net alamadım, tekrar eder misin?"
                    history.append({"role": "assistant", "content": retry})
                    path = synthesize_speech(retry)
                    if path and os.path.exists(path):
                        audio_clips.append(path)
                        self._play_pcm_on_call(call, self._file_to_pcmu8(path))
                    continue

                user_text = text.strip()
                history.append({"role": "user", "content": user_text})
                transcript_parts.append(f"Arayan: {user_text}")

                # LLM (Ollama GPU) — sync bridge
                reply = self._run_async(handle_call_turn(user_text, history[:-1]))
                if not reply:
                    reply = "Anladım, notumu aldım."
                history.append({"role": "assistant", "content": reply})
                transcript_parts.append(f"Asistan: {reply}")

                if call_id:
                    try:
                        append_call_transcript(
                            call_id,
                            f"Arayan: {user_text}\nAsistan: {reply}",
                            summary=f"{caller}: {user_text[:80]}",
                        )
                    except Exception as e:
                        logger.warning("transcript: %s", e)

                reply_path = synthesize_speech(reply)
                if reply_path and os.path.exists(reply_path):
                    audio_clips.append(reply_path)
                    self._play_pcm_on_call(call, self._file_to_pcmu8(reply_path))

                low = user_text.lower()
                if any(x in low for x in ("görüşürüz", "gorusuruz", "bay bay", "hoşça kal", "hosca kal")):
                    break

        except Exception as e:
            logger.error("[SIP] Çağrı hatası: %s", e, exc_info=True)
        finally:
            full_transcript = "\n".join(transcript_parts)
            try:
                if len(history) > 1:
                    summary_data = self._run_async(
                        summarize_and_save_call(caller, history, call_id=call_id)
                    )
                    call_id = summary_data.get("call_id") or call_id
                    full_transcript = summary_data.get("transcript") or full_transcript
                    summary = summary_data.get("summary") or ""
                else:
                    summary = f"SIP: {caller} — yalnızca selamlama."
                    if call_id:
                        update_call_record(call_id, transcript=full_transcript, summary=summary)

                if call_id and audio_clips:
                    saved = save_call_recording(caller, full_transcript, summary, audio_clips)
                    if saved and os.path.isfile(saved) and saved.lower().endswith((".wav", ".mp3")):
                        update_call_audio(call_id, saved)
            except Exception as e:
                logger.warning("[SIP] arşiv: %s", e)

            try:
                call.hangup()
            except Exception:
                pass
            self.active_calls = max(0, self.active_calls - 1)
            logger.info("[SIP] Çağrı sonlandı: %s", caller)

    def _record_utterance(self, call, max_seconds: float = 12.0) -> bytes:
        """Enerji VAD: konuşma başlayınca kaydet, sessizlikte kes."""
        buf = bytearray()
        speech_seen = False
        last_voice = time.time()
        start = time.time()
        wait_speech = 8.0
        silence_end = 1.2
        # 8-bit signed RMS eşiği (deneysel; softphone için düşük)
        threshold = 8.0

        while self._is_answered(call) and (time.time() - start) < max_seconds:
            try:
                chunk = call.read_audio(FRAME_8K_U8, blocking=False)
            except Exception:
                time.sleep(0.02)
                continue
            if not chunk or chunk == SILENCE_U8:
                chunk = SILENCE_U8
            rms = self._rms_u8(chunk)
            buf.extend(chunk)

            if rms >= threshold:
                if not speech_seen:
                    logger.info("[SIP] Konuşma algılandı rms=%.1f", rms)
                speech_seen = True
                last_voice = time.time()
            elif speech_seen and (time.time() - last_voice) >= silence_end:
                break

            if not speech_seen and (time.time() - start) >= wait_speech:
                break
            time.sleep(0.018)

        return bytes(buf) if speech_seen else b""

    @staticmethod
    def _build_greeting(status: str) -> str:
        return build_call_greeting(None, status)

    @staticmethod
    def _extract_caller(call) -> str:
        try:
            if hasattr(call, "request") and call.request and "From" in call.request.headers:
                from_header = str(call.request.headers["From"])
                return from_header.split(";")[0].replace("<", "").replace(">", "").strip()
        except Exception:
            pass
        return "SIP Arayan"

    @staticmethod
    def _run_async(coro):
        """Thread içinden async LLM çağrısı."""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            try:
                return loop.run_until_complete(coro)
            finally:
                loop.close()
        except Exception as e:
            logger.error("async bridge: %s", e)
            return ""


sip_gateway = TenraSIPGateway.get_instance()

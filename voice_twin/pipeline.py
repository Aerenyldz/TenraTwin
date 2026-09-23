"""
TENRA Voice Twin - Tam Sesli Asistan Pipeline v1
STT (Faster-Whisper) → LLM (Ollama hermes3:8b) → TTS (Edge-TTS + RVC)

Kullanım:
  python voice_twin/pipeline.py

Çalışma modu: Terminal tabanlı sesli konuşma simülatörü.
Gerçek telefon entegrasyonu için call_simulator.py ile birleştirilecek.
"""
import asyncio
import os
import sys
import tempfile
import time
import wave
import threading

# Path fix
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

CACHE_DIR = os.path.join(CURRENT_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
LLM_MODEL = os.getenv("CALL_MODEL", "hermes3:8b")

SYSTEM_PROMPT = """Sen Ahmet Eren Yıldız'ın kişisel yapay zeka sesli asistanısın.
Biri Ahmet'i aradığında telefonu sen açarsın.

KURALLAR:
- Maksimum 1-2 kısa cümle söyle. Uzun konuşma yok.
- Ahmet gibi samimi, arkadaşça, doğal konuş.
- Arayanın kim olduğunu ve ne istediğini öğren.
- Önemli notları aldığını belirt.
- Robotik olma, bürokrasi yapma.
"""

# ─────────────────────────────────────────────────────────────────────────────
# STT: Faster-Whisper ile ses → metin
# ─────────────────────────────────────────────────────────────────────────────

_whisper_model = None

def get_whisper_model():
    """Whisper her zaman CPU int8 — RTX 2060 VRAM'i Ollama + RVC için kalsın."""
    global _whisper_model
    if _whisper_model is None:
        print("[STT] Whisper CPU int8 yükleniyor (VRAM kullanmaz, ilk kez ~20-40 sn)...")
        from faster_whisper import WhisperModel
        # Kullanıcı kararı: 6 GB VRAM sadece Hermes + RVC
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
        print("[STT] Whisper hazır (device=cpu, compute_type=int8).")
    return _whisper_model


def transcribe_wav(wav_path: str, language: str = "tr", *, soft_vad: bool = False) -> str:
    """WAV dosyasını metne dönüştürür.

    soft_vad=True: GSM hoparlör sızıntısı gibi zayıf sesler için VAD kapalı.
    """
    try:
        model = get_whisper_model()
        kwargs = {
            "language": language,
            "beam_size": 5,
        }
        if soft_vad:
            # Hoparlörden gelen uzak sesi kesmesin
            kwargs["vad_filter"] = False
        else:
            kwargs["vad_filter"] = True
            kwargs["vad_parameters"] = {"min_silence_duration_ms": 500}

        segments, info = model.transcribe(wav_path, **kwargs)
        text = " ".join(seg.text.strip() for seg in segments).strip()
        return text
    except Exception as e:
        print(f"[STT Hata]: {e}")
        return ""


# ─────────────────────────────────────────────────────────────────────────────
# LLM: Ollama ile metin → yanıt
# ─────────────────────────────────────────────────────────────────────────────

async def get_llm_response(user_text: str, history: list) -> str:
    """Kullanıcı metnine LLM ile yanıt üretir."""
    import httpx

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(history)
    messages.append({"role": "user", "content": user_text})

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/chat",
                json={
                    "model": LLM_MODEL,
                    "messages": messages,
                    "stream": False,
                    "options": {
                        "temperature": 0.6,
                        "num_predict": 80,
                        "stop": ["\n\n", "Arayan:", "Ahmet:"]
                    }
                }
            )
            response.raise_for_status()
            data = response.json()
            return data.get("message", {}).get("content", "").strip()
    except Exception as e:
        print(f"[LLM Hata]: {e}")
        return "Anladım, not aldım. Ahmet'e iletiyorum."


# ─────────────────────────────────────────────────────────────────────────────
# TTS: Edge-TTS + RVC ile metin → Ahmet sesi
# ─────────────────────────────────────────────────────────────────────────────

async def speak(text: str, output_path: str = None) -> str:
    """Metni Ahmet'in sesiyle seslendirir."""
    from voice_twin.tts_engine import synthesize_speech_async
    if not output_path:
        output_path = os.path.join(CACHE_DIR, f"pipeline_{abs(hash(text)) % 100000}.wav")
    result = await synthesize_speech_async(text, output_path)
    return result


def play_wav(path: str):
    """WAV dosyasını çalar (Windows)."""
    try:
        import winsound
        winsound.PlaySound(path, winsound.SND_FILENAME)
    except Exception as e:
        print(f"[Ses Çalma Hata]: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Mikrofon kaydı (pyaudio)
# ─────────────────────────────────────────────────────────────────────────────

def record_microphone(duration_sec: int = 5, sample_rate: int = 16000) -> str:
    """Mikrofondan ses kaydeder ve WAV yolunu döndürür (sounddevice ile)."""
    try:
        import sounddevice as sd
        import soundfile as sf

        print(f"  🎤 Konuşun... ({duration_sec} saniye)")
        audio = sd.rec(int(duration_sec * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
        sd.wait()
        print("  ✅ Kayıt tamamlandı.")

        out_path = os.path.join(CACHE_DIR, "mic_input.wav")
        sf.write(out_path, audio, sample_rate)
        return out_path

    except ImportError:
        print("  [!] sounddevice kurulu değil. Metin modu kullanılıyor.")
        return None
    except Exception as e:
        print(f"  [Mikrofon Hata]: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Ana Döngü
# ─────────────────────────────────────────────────────────────────────────────

async def run_voice_session():
    """Tam sesli asistan oturumu."""
    print("=" * 60)
    print("  🤖 TENRA Sesli Asistan — Ahmet Eren'in Dijital İkizi")
    print("  Çıkmak için: 'q' veya 'quit' yaz")
    print("  Ses modu için: Enter'a bas ve konuş")
    print("=" * 60)

    # Açılış cümlesi
    opening = "Alo, ben Ahmet'in asistanıyım. Ahmet şu an müsait değil. Nasıl yardımcı olabilirim?"
    print(f"\n🔊 Asistan: {opening}")
    opening_wav = await speak(opening)
    play_wav(opening_wav)

    history = []
    use_mic = False

    # pyaudio var mı kontrol et
    try:
        import sounddevice
        use_mic = True
        print("\n✅ Mikrofon modu aktif (Realtek Mikrofon hazır).")
    except ImportError:
        print("\n⚠️ sounddevice bulunamadı. Metin modu kullanılıyor.")

    turn = 0
    while True:
        turn += 1

        # Kullanıcı girişi
        if use_mic:
            input(f"\n[Tur {turn}] Enter'a bas ve konuş...")
            wav_path = record_microphone(duration_sec=6)
            if wav_path:
                user_text = transcribe_wav(wav_path)
                print(f"📝 Arayan: {user_text}")
            else:
                user_text = input("Metinle yaz: ").strip()
        else:
            user_text = input(f"\n[Tur {turn}] Siz: ").strip()

        if not user_text or user_text.lower() in ("q", "quit", "exit", "çıkış"):
            print("\n[Görüşme sonlandı]")
            break

        # LLM yanıtı
        print("💭 Düşünüyor...", end="\r")
        t0 = time.time()
        reply = await get_llm_response(user_text, history)
        elapsed = time.time() - t0
        print(f"🔊 Asistan ({elapsed:.1f}s): {reply}")

        # History güncelle
        history.append({"role": "user", "content": user_text})
        history.append({"role": "assistant", "content": reply})

        # TTS + çal
        print("🎵 Ses üretiliyor...", end="\r")
        reply_wav = await speak(reply)
        play_wav(reply_wav)

        # 5 turdan sonra özet öner
        if turn >= 5:
            print("\n[5 tur tamamlandı — devam etmek için Enter, çıkmak için 'q']")
            cont = input().strip().lower()
            if cont in ("q", "quit"):
                break


if __name__ == "__main__":
    asyncio.run(run_voice_session())

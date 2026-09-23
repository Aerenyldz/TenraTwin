"""
TENRA Voice Twin - TTS & Voice Synthesis Engine
Metinleri seslendirir, Ahmet Eren'in ses klonunu veya nöral ses motorunu yönetir.
"""
import os
import asyncio
import concurrent.futures
import edge_tts
import soundfile as sf
import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
AUDIO_CACHE_DIR = os.path.join(CURRENT_DIR, "cache")
PROCESSED_DIR = os.path.join(PROJECT_ROOT, "ses_veriseti", "processed")
_legacy_dataset = os.path.join(PROJECT_ROOT, "voice_dataset", "processed")
if not os.path.exists(PROCESSED_DIR) and os.path.exists(_legacy_dataset):
    PROCESSED_DIR = _legacy_dataset

os.makedirs(AUDIO_CACHE_DIR, exist_ok=True)

# Varsayılan samimi erkek Türkçe nöral ses
DEFAULT_VOICE = "tr-TR-AhmetNeural"

def load_config():
    config_path = os.path.join(CURRENT_DIR, "config.json")
    if os.path.exists(config_path):
        try:
            import json
            with open(config_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

import re

def normalize_turkish_text(text: str) -> str:
    """ASCII Türkçe yazılmış kelimeleri doğru Türkçe karakterlere çevirir (dogal -> doğal vb.)."""
    replacements = [
        (r"\bdogal\b", "doğal"),
        (r"\bDogal\b", "Doğal"),
        (r"\bartik\b", "artık"),
        (r"\bArtik\b", "Artık"),
        (r"\bkonusabiliyorum\b", "konuşabiliyorum"),
        (r"\bkonusuyor\b", "konuşuyor"),
        (r"\bkonus\b", "konuş"),
        (r"\bnasil\b", "nasıl"),
        (r"\bNasil\b", "Nasıl"),
        (r"\bdegil\b", "değil"),
        (r"\bDegil\b", "Değil"),
        (r"\byagmur\b", "yağmur"),
        (r"\bcagri\b", "çağrı"),
        (r"\bCagri\b", "Çağrı"),
        (r"\begitim\b", "eğitim"),
        (r"\bEgitim\b", "Eğitim"),
        (r"\bgorusuruz\b", "görüşürüz"),
        (r"\bGorusuruz\b", "Görüşürüz"),
    ]
    for pattern, repl in replacements:
        text = re.sub(pattern, repl, text)

    # Rakamları, saatleri ve sayı eklerini Türkçe kelimelere çevir
    try:
        from voice_twin.turkish_num import normalize_turkish_numbers
        text = normalize_turkish_numbers(text)
    except Exception as e:
        print(f"[Sayı Normalizasyonu Uyarısı]: {e}")

    return text

async def synthesize_speech_async(
    text: str,
    output_path: str = None,
    voice: str = DEFAULT_VOICE,
    rate: str = "+6%",
    pitch: str = "+2Hz"
) -> str:
    """
    Metni seslendirir.
    Eğer Fish Audio veya ElevenLabs API yapılandırılmışsa doğrudan Ahmet Eren'in ses klonunu kullanır.
    Yoksa kalibre edilmiş yerel nöral sesi (RVC/Edge-TTS) kullanır.
    """
    text = normalize_turkish_text(text)
    cfg = load_config()
    provider = (os.getenv("VOICE_PROVIDER") or cfg.get("voice_provider") or "fish_audio").strip().lower()

    # Yerel RVC öncelikli (Faz 2): fish/elevenlabs atlanır
    prefer_local = provider in ("rvc", "local", "local_rvc", "edge_rvc")

    # 1. Fish Audio Kontrolü
    fish_key = os.getenv("FISH_AUDIO_API_KEY", cfg.get("fish_api_key", ""))
    fish_ref = os.getenv("FISH_REFERENCE_ID", cfg.get("fish_reference_id", "f5b2d05ab5a1402ebabe0b4703bd09b7"))
    emotion_prompt = cfg.get("fish_emotion_prompt", "[friendly, warm tone]")
    speed = float(cfg.get("fish_speed", 1.06))

    if (not prefer_local) and fish_key and fish_ref:
        try:
            from voice_twin.fish_tts import synthesize_fish_audio
            return await synthesize_fish_audio(
                text=text,
                output_path=output_path,
                reference_id=fish_ref,
                api_key=fish_key,
                emotion_prompt=emotion_prompt,
                speed=speed
            )
        except Exception as e:
            print(f"[Fish Audio Uyarı]: {e}. Yedek motora geçiliyor...")

    # 2. ElevenLabs Kontrolü
    eleven_key = os.getenv("ELEVENLABS_API_KEY", cfg.get("elevenlabs_api_key", ""))
    eleven_vid = os.getenv("ELEVENLABS_VOICE_ID", cfg.get("elevenlabs_voice_id", ""))

    if (not prefer_local) and eleven_key and eleven_vid:
        try:
            from voice_twin.elevenlabs_tts import synthesize_elevenlabs_stream
            return await synthesize_elevenlabs_stream(text, output_path, eleven_vid, eleven_key)
        except Exception as e:
            print(f"[ElevenLabs Uyarı]: {e}. Yerel motora dönülüyor...")

    # 3. Edge-TTS + RVC (yerel)
    cfg_voice = cfg.get("local_voice_fallback") or voice
    cfg_rate = cfg.get("rate_offset") or rate
    cfg_pitch = cfg.get("pitch_offset") or pitch

    if not output_path:
        filename = f"tts_{abs(hash(text)) % 1000000}.wav"
        output_path = os.path.join(AUDIO_CACHE_DIR, filename)

    temp_tts = os.path.join(AUDIO_CACHE_DIR, f"temp_base_{abs(hash(text)) % 1000000}.wav")
    try:
        communicate = edge_tts.Communicate(
            text=text,
            voice=cfg_voice,
            rate=cfg_rate,
            pitch=cfg_pitch if str(cfg_pitch).startswith(("+", "-")) else f"+{cfg_pitch}"
        )
        await communicate.save(temp_tts)

        # RVC Model Kontrolü ve Ses Dönüşümü
        try:
            from voice_twin.rvc_bridge import convert_to_ahmet_voice, get_latest_model
            model = get_latest_model()
            if model:
                print(f"[RVC] Yerel model kullanılıyor: {os.path.basename(model)}")
                final_audio = convert_to_ahmet_voice(temp_tts, output_path, index_rate=0.38)
                return final_audio
            elif prefer_local:
                print("[RVC] voice_provider=rvc ama model bulunamadı (C:\\Applio\\assets\\weights\\). Edge-TTS ham ses.")
        except Exception as e:
            print(f"[RVC Dönüşüm Uyarısı]: {e}. Orijinal TTS sesi kullanılıyor.")

        if output_path != temp_tts:
            import shutil
            shutil.copy2(temp_tts, output_path)
        return output_path
    except Exception as e:
        print(f"[Edge-TTS Hatası]: {e}")
        # Return none or output_path if exists
        if output_path and os.path.exists(output_path):
            return output_path
        raise RuntimeError(f"Tüm ses motorları (Fish Audio & Edge-TTS) başarısız oldu: {e}")

def synthesize_speech(text: str, output_path: str = None, voice: str = DEFAULT_VOICE, rate: str = "+5%", pitch: str = "-5Hz") -> str:
    """Hem senkron hem de asenkron ortamlardan güvenle çağrılabilen sarmalayıcı."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        with concurrent.futures.ThreadPoolExecutor() as executor:
            future = executor.submit(asyncio.run, synthesize_speech_async(text, output_path, voice, rate, pitch))
            return future.result()
    else:
        return asyncio.run(synthesize_speech_async(text, output_path, voice, rate, pitch))

def play_audio(audio_path: str):
    """Sesi sistem hoparlöründen çalar."""
    try:
        import winsound
        if audio_path.endswith(".wav"):
            winsound.PlaySound(audio_path, winsound.SND_FILENAME)
        else:
            os.system(f'powershell -c "(New-Object Media.SoundPlayer \'{audio_path}\').PlaySync();" 2>$null || start "" /min "{audio_path}"')
    except Exception as e:
        print(f"Ses çalma hatası: {e}")

if __name__ == "__main__":
    test_metin = "Selam kanka, ben Ahmet'in yapay zeka ikiziyim. Ahmet şu an derste. Önemli bir şey varsa not alayım?"
    print("Test sesi sentezleniyor...")
    out = synthesize_speech(test_metin)
    print("Sentezlendi:", out)

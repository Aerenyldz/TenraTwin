"""
TENRA Voice Twin - Fish Audio TTS Engine
Fish Audio API üzerinden ultra gerçekçi ve akıcı Ahmet Eren ses sentezi.
Gereksiz uzun duraklamaları yumuşakça sıkılaştırır (Micro Pause Compactor).
"""
import os
import re
import asyncio
import httpx
import numpy as np
import soundfile as sf

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.path.join(CURRENT_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

FISH_API_URL = "https://api.fish.audio/v1/tts"

def tighten_audio_pauses(audio_path: str, max_pause_ms: int = 240, thresh: float = 0.006) -> str:
    """
    Cümle ve noktalama aralarındaki 500-700ms'lik yapay uzun boşlukları,
    harfleri veya kelimeleri kesinlikle budamadan doğal 200-240ms konuşma ritmine sıkılaştırır.
    """
    try:
        data, sr = sf.read(audio_path)
        mono = data.mean(axis=1) if len(data.shape) > 1 else data

        frame_ms = 10
        frame_size = int(sr * frame_ms / 1000)
        max_pause_frames = int(max_pause_ms / frame_ms)

        is_silent = []
        for i in range(0, len(mono) - frame_size, frame_size):
            rms = float(np.sqrt(np.mean(mono[i:i+frame_size]**2)))
            is_silent.append(rms < thresh)

        chunks = []
        i = 0
        total_frames = len(is_silent)
        modified = False

        while i < total_frames:
            if is_silent[i]:
                j = i
                while j < total_frames and is_silent[j]:
                    j += 1
                silence_len = j - i
                if silence_len > max_pause_frames:
                    modified = True
                    kept_frames = max_pause_frames
                    start_sample = i * frame_size
                    end_sample = (i + kept_frames) * frame_size
                    chunks.append(data[start_sample:end_sample])
                else:
                    start_sample = i * frame_size
                    end_sample = j * frame_size
                    chunks.append(data[start_sample:end_sample])
                i = j
            else:
                j = i
                while j < total_frames and not is_silent[j]:
                    j += 1
                start_sample = i * frame_size
                end_sample = min(j * frame_size, len(data))
                chunks.append(data[start_sample:end_sample])
                i = j

        if modified and chunks:
            out_data = np.concatenate(chunks, axis=0)
            if audio_path.lower().endswith(".wav"):
                sf.write(audio_path, out_data, sr)
            else:
                # MP3 ise WAV olarak kaydet
                wav_path = audio_path.rsplit(".", 1)[0] + ".wav"
                sf.write(wav_path, out_data, sr)
                return wav_path
    except Exception as e:
        print(f"[Duraklama Optimizasyonu Bilgisi]: {e}")
    return audio_path


async def synthesize_fish_audio(
    text: str,
    output_path: str = None,
    reference_id: str = "f5b2d05ab5a1402ebabe0b4703bd09b7",
    api_key: str = None,
    emotion_prompt: str = "[fluent, friendly, warm tone]",
    speed: float = 1.08,
    tighten_pauses: bool = True
) -> str:
    """
    Fish Audio API kullanarak metni sese dönüştürür.
    S2.1 modelinde köşeli parantez içinde verilen duygu etiketleri (emotion prompts)
    sesin monoton ve cansız çıkmasını engeller.
    """
    if not api_key:
        api_key = os.getenv("FISH_AUDIO_API_KEY", "")

    if not api_key:
        try:
            import json
            cfg_file = os.path.join(CURRENT_DIR, "config.json")
            if os.path.exists(cfg_file):
                with open(cfg_file, "r", encoding="utf-8") as f:
                    api_key = json.load(f).get("fish_api_key", "")
        except Exception:
            pass

    if not api_key:
        raise ValueError("Fish Audio API anahtarı (api_key) belirtilmedi.")

    if not output_path:
        filename = f"fish_{abs(hash(text)) % 1000000}.wav"
        output_path = os.path.join(CACHE_DIR, filename)

    processed_text = text.strip()
    # Rakamları Türkçe okunuşlarına çevir (örn: 8'de -> sekizde, 14:30 -> on dört otuz)
    try:
        from voice_twin.turkish_num import normalize_turkish_numbers
        processed_text = normalize_turkish_numbers(processed_text)
    except Exception:
        pass

    # Ünlem işaretlerini sohbet ulaması için virgüle dönüştür (cümle sonu değilse)
    processed_text = re.sub(r"!\s+([A-ZÇĞİÖŞÜa-zçğıöşü])", r", \1", processed_text)

    if emotion_prompt and not processed_text.startswith("["):
        processed_text = f"{emotion_prompt} {processed_text}"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "model": "s2.1-pro-free"
    }

    fmt = "wav" if output_path.lower().endswith(".wav") else "mp3"

    payload = {
        "text": processed_text,
        "reference_id": reference_id,
        "format": fmt,
        "prosody": {
            "speed": speed,
            "volume": 0
        },
        "latency": "balanced"
    }

    last_err = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                resp = await client.post(FISH_API_URL, json=payload, headers=headers)
                if resp.status_code != 200:
                    raise RuntimeError(f"Fish Audio API Hatası ({resp.status_code}): {resp.text}")

                with open(output_path, "wb") as f:
                    f.write(resp.content)
                last_err = None
                break
        except Exception as e:
            last_err = e
            if attempt == 0:
                await asyncio.sleep(0.5)

    if last_err is not None:
        raise last_err

    # Duraklama sıkılaştırıcıyı uygula
    if tighten_pauses:
        output_path = tighten_audio_pauses(output_path, max_pause_ms=240)

    return output_path

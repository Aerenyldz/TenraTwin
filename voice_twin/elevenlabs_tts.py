"""
TENRA Voice Twin - ElevenLabs Streaming Voice Engine
Ahmet Eren'in ses klonunu kullanarak ultra düşük gecikmeli, stüdyo doğallığında Türkçe ses üretir.
"""
import os
import httpx
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
CACHE_DIR = os.path.join(CURRENT_DIR, "cache")
os.makedirs(CACHE_DIR, exist_ok=True)

# Çevre değişkenlerinden veya yapılandırmadan oku
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "")

# Varsayılan model: Türkçe ve çok dilli en doğal model
MODEL_ID = "eleven_multilingual_v2"

async def synthesize_elevenlabs_stream(
    text: str,
    output_path: str = None,
    voice_id: str = None,
    api_key: str = None
) -> str:
    """
    ElevenLabs API üzerinden akışkan ses üretir.
    Latency Optimization: 3 (En hızlı tepki süresi ~250ms)
    """
    key = api_key or ELEVENLABS_API_KEY
    vid = voice_id or ELEVENLABS_VOICE_ID

    if not key or not vid:
        raise ValueError("ELEVENLABS_API_KEY veya ELEVENLABS_VOICE_ID eksik!")

    if not output_path:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = os.path.join(CACHE_DIR, f"eleven_{ts}.mp3")

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{vid}/stream?optimize_streaming_latency=3"

    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": key
    }

    payload = {
        "text": text,
        "model_id": MODEL_ID,
        "voice_settings": {
            "stability": 0.50,         # 0.50: Doğal insan vurgusu ve tonlama
            "similarity_boost": 0.85,  # 0.85: Ahmet Eren'in sesine en yüksek benzerlik
            "style": 0.15,             # Hafif esprili/rahat konuşma stili
            "use_speaker_boost": True
        }
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url, headers=headers, json=payload)
        response.raise_for_status()

        with open(output_path, "wb") as f:
            f.write(response.content)

    return output_path

def synthesize_elevenlabs(text: str, output_path: str = None, voice_id: str = None, api_key: str = None) -> str:
    """Senkron sarmalayıcı"""
    import asyncio
    return asyncio.run(synthesize_elevenlabs_stream(text, output_path, voice_id, api_key))

if __name__ == "__main__":
    print("ElevenLabs modülü hazır.")
    print(f"- API Key Tanımlı mı: {'EVET' if ELEVENLABS_API_KEY else 'HAYIR'}")
    print(f"- Voice ID Tanımlı mı: {'EVET' if ELEVENLABS_VOICE_ID else 'HAYIR'}")

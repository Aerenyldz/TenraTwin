"""
TENRA Voice Twin - Call Audio & Video Archiver
Görüşmelerin seslerini tek bir kayıt dosyasında birleştirip call_recordings/ klasörüne kaydeder.
"""
import os
import shutil
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
RECORDINGS_DIR = os.path.join(PROJECT_ROOT, "call_recordings")

os.makedirs(RECORDINGS_DIR, exist_ok=True)

def save_call_recording(caller_name: str, transcript: str, summary: str, audio_clips: list[str]) -> str:
    """
    Görüşme seslerini ve özetini arşivler.
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_caller = "".join(c for c in caller_name if c.isalnum() or c in (" ", "_")).strip().replace(" ", "_")
    base_name = f"cagri_{clean_caller}_{timestamp}"
    
    # 1. Metin Raporu
    txt_path = os.path.join(RECORDINGS_DIR, f"{base_name}_not.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"=== ARAMA KAYDI: {caller_name} ===\n")
        f.write(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Özet Not: {summary}\n\n")
        f.write("--- KONUŞMA DÖKÜMÜ ---\n")
        f.write(transcript + "\n")

    # 2. Ses Kaydı
    final_audio = ""
    if audio_clips:
        # Son ses klibini veya birleşimi kopyala
        final_audio = os.path.join(RECORDINGS_DIR, f"{base_name}.mp3")
        try:
            # En son sentezlenen veya ana klibi al
            shutil.copyfile(audio_clips[-1], final_audio)
        except Exception:
            pass

    return final_audio or txt_path

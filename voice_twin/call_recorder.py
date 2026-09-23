"""
TENRA Voice Twin - Call Audio Archiver
Görüşme seslerini arama_kayitlari/ altına birleştirip kaydeder.
"""
import os
import shutil
import wave
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
RECORDINGS_DIR = os.path.join(PROJECT_ROOT, "arama_kayitlari")
_legacy = os.path.join(PROJECT_ROOT, "call_recordings")
if not os.path.exists(RECORDINGS_DIR) and os.path.exists(_legacy):
    RECORDINGS_DIR = _legacy

os.makedirs(RECORDINGS_DIR, exist_ok=True)


def _concat_wavs(paths: list[str], out_path: str) -> bool:
    """Aynı formatlı WAV dosyalarını uç uca birleştirir."""
    valid = [p for p in paths if p and os.path.isfile(p) and os.path.getsize(p) > 44]
    if not valid:
        return False
    try:
        params = None
        frames = []
        for p in valid:
            with wave.open(p, "rb") as wf:
                pms = (wf.getnchannels(), wf.getsampwidth(), wf.getframerate())
                if params is None:
                    params = pms
                elif pms != params:
                    # Format uyuşmazsa bu klibi atla
                    continue
                frames.append(wf.readframes(wf.getnframes()))
        if not params or not frames:
            return False
        with wave.open(out_path, "wb") as out:
            out.setnchannels(params[0])
            out.setsampwidth(params[1])
            out.setframerate(params[2])
            for fr in frames:
                out.writeframes(fr)
        return os.path.getsize(out_path) > 44
    except Exception as e:
        print(f"[call_recorder] WAV birleştirme: {e}")
        return False


def save_call_recording(
    caller_name: str,
    transcript: str,
    summary: str,
    audio_clips: list[str],
) -> str:
    """
    Metin raporu + birleşik ses kaydı üretir.
    Dönüş: ses dosyası yolu (yoksa txt yolu).
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    clean_caller = "".join(
        c for c in caller_name if c.isalnum() or c in (" ", "_")
    ).strip().replace(" ", "_") or "Arayan"
    base_name = f"cagri_{clean_caller}_{timestamp}"

    txt_path = os.path.join(RECORDINGS_DIR, f"{base_name}_not.txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write(f"=== ARAMA KAYDI: {caller_name} ===\n")
        f.write(f"Tarih: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"Özet Not: {summary}\n\n")
        f.write("--- KONUŞMA DÖKÜMÜ ---\n")
        f.write((transcript or "") + "\n")

    final_audio = ""
    clips = [c for c in (audio_clips or []) if c]
    if clips:
        wav_out = os.path.join(RECORDINGS_DIR, f"{base_name}.wav")
        if _concat_wavs(clips, wav_out):
            final_audio = wav_out
        else:
            # En azından son mevcut klibi kopyala
            for src in reversed(clips):
                if os.path.isfile(src):
                    ext = os.path.splitext(src)[1].lower() or ".wav"
                    dest = os.path.join(RECORDINGS_DIR, f"{base_name}{ext}")
                    try:
                        shutil.copyfile(src, dest)
                        final_audio = dest
                        break
                    except Exception:
                        pass

    return final_audio or txt_path

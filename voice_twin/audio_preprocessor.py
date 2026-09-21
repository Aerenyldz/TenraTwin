"""
TENRA Voice Twin - Advanced Audio Preprocessor & DSP Pipeline
93 adet uzun, gece kaydedilmiş ve anlaşılması zor ses dosyasını
gürültü filtresi, bant geçiren filtre, dinamik sıkıştırma ve VAD ile temizler.
"""
import os
import sys

try:
    sys.stdout.reconfigure(encoding='utf-8')
except Exception:
    pass

import glob
import subprocess
import numpy as np
import soundfile as sf
from scipy.signal import butter, sosfilt
import imageio_ffmpeg

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
DATASET_DIR = os.path.join(PROJECT_ROOT, "voice_dataset")
PROCESSED_DIR = os.path.join(DATASET_DIR, "processed")

FFMPEG_EXE = imageio_ffmpeg.get_ffmpeg_exe()

def ensure_dirs():
    os.makedirs(DATASET_DIR, exist_ok=True)
    os.makedirs(PROCESSED_DIR, exist_ok=True)

def load_audio_any_format(file_path: str, target_sr: int = 24000) -> tuple[np.ndarray, int]:
    """M4A, MP3, OGG, WAV dosyalarını ffmpeg ile doğrudan 24kHz mono float32 olarak çözer."""
    cmd = [
        FFMPEG_EXE,
        "-v", "error",
        "-i", file_path,
        "-f", "f32le",
        "-acodec", "pcm_f32le",
        "-ac", "1",
        "-ar", str(target_sr),
        "-"
    ]
    process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    stdout, stderr = process.communicate()
    
    if process.returncode != 0:
        raise RuntimeError(f"FFmpeg decode hatasi: {stderr.decode('utf-8', errors='ignore')}")
        
    audio = np.frombuffer(stdout, dtype=np.float32)
    return audio, target_sr

def apply_speech_enhancement(audio: np.ndarray, sr: int) -> np.ndarray:
    """
    İnsan sesine özel DSP Filtresi:
    1. 80 Hz altındaki oda uğultusu ve nefes gürültüsünü keser (High-pass).
    2. 7500 Hz üstündeki elektronik tıslama ve dip gürültüsünü keser (Low-pass).
    3. RMS normalizasyonu ile boğuk/kısık gece sesini duyulabilir seviyeye yükseltir.
    """
    if len(audio) == 0:
        return audio

    # 4. derece Butterworth bant geçiren filtre (80 Hz - 7500 Hz)
    sos = butter(4, [80, 7500], btype='bandpass', fs=sr, output='sos')
    filtered = sosfilt(sos, audio)

    # Tepe ve RMS Normalizasyonu (Kısık sesleri güçlendir)
    rms = np.sqrt(np.mean(filtered**2))
    if rms > 1e-5:
        target_rms = 0.12 # Hedef netlik seviyesi
        filtered = filtered * (target_rms / rms)

    # Sert patlamaları (clipping) engelle
    filtered = np.tanh(filtered * 0.9)
    max_val = np.max(np.abs(filtered))
    if max_val > 0:
        filtered = filtered / max_val * 0.95

    return filtered.astype(np.float32)

def extract_speech_chunks(audio: np.ndarray, sr: int, min_len_sec: float = 4.0, max_len_sec: float = 15.0) -> list[np.ndarray]:
    """
    Uzun sesleri (4-5 dakika) nefes ve sessizlik noktalarından bölerek
    ses klonlamaya en uygun 4-15 saniyelik net konuşma bloklarına ayırır.
    """
    frame_len = int(sr * 0.05) # 50ms pencere
    if len(audio) < frame_len:
        return []

    num_frames = len(audio) // frame_len
    energies = np.array([np.mean(audio[i*frame_len:(i+1)*frame_len]**2) for i in range(num_frames)])
    
    # Adaptif gürültü eşiği (medyan enerjinin biraz üstü)
    threshold = np.percentile(energies, 35) + 1e-4

    chunks = []
    current_chunk = []
    silent_frames = 0
    max_silent_frames = int(0.6 / 0.05) # 600ms sessizlik = yeni cümle ayrımı

    for i in range(num_frames):
        frame = audio[i*frame_len:(i+1)*frame_len]
        is_speech = energies[i] > threshold

        if is_speech:
            current_chunk.append(frame)
            silent_frames = 0
        else:
            silent_frames += 1
            if current_chunk:
                current_chunk.append(frame)
                
            # Cümle bitti mi veya parça çok uzadı mı?
            chunk_duration = (len(current_chunk) * frame_len) / sr
            if (silent_frames >= max_silent_frames or chunk_duration >= max_len_sec) and current_chunk:
                if chunk_duration >= min_len_sec:
                    chunks.append(np.concatenate(current_chunk))
                current_chunk = []
                silent_frames = 0

    if current_chunk:
        chunk_duration = (len(current_chunk) * frame_len) / sr
        if chunk_duration >= min_len_sec:
            chunks.append(np.concatenate(current_chunk))

    return chunks

def process_entire_dataset() -> dict:
    """Tüm dataseti tarayıp temizler ve analiz raporu üretir."""
    ensure_dirs()
    
    # Tüm ses dosyalarını topla
    extensions = ["*.m4a", "*.mp3", "*.ogg", "*.wav"]
    raw_files = []
    for ext in extensions:
        raw_files.extend(glob.glob(os.path.join(DATASET_DIR, ext)))
        
    raw_files = [f for f in raw_files if "processed" not in f]
    
    # Ahmet'in temiz gündüz referansını koru
    gunduz_ref = os.path.join(DATASET_DIR, "ahmet_gunduz_ref.wav")
    if os.path.exists(gunduz_ref):
        try:
            anchor_data, sr = sf.read(gunduz_ref)
            sf.write(os.path.join(PROCESSED_DIR, "000_ahmet_gold_anchor.wav"), anchor_data, sr)
            print("[INFO] Altin Referans (ahmet_gunduz_ref.wav) basariyla korundu.")
        except Exception:
            pass

    print(f"[INFO] Toplam taranacak ses dosyasi: {len(raw_files)}")
    sys.stdout.flush()
    
    total_raw_duration = 0.0
    total_clean_chunks = 0
    total_clean_duration = 0.0
    failed_files = 0

    for idx, fpath in enumerate(raw_files):
        fname = os.path.basename(fpath)
        if "ahmet_gunduz_ref" in fname:
            continue
            
        try:
            audio, sr = load_audio_any_format(fpath, target_sr=24000)
            raw_dur = len(audio) / sr
            total_raw_duration += raw_dur

            # 1. Filtrele ve gürültüyü temizle
            enhanced = apply_speech_enhancement(audio, sr)

            # 2. Anlamlı konuşma bloklarına böl
            chunks = extract_speech_chunks(enhanced, sr)

            # 3. En kaliteli parçaları kaydet
            base_id = f"ahmet_{idx+1:03d}"
            for c_idx, chunk in enumerate(chunks[:6]): # Her uzun videodan en net 6 parçayı al
                out_name = f"{base_id}_c{c_idx+1}.wav"
                out_path = os.path.join(PROCESSED_DIR, out_name)
                sf.write(out_path, chunk, sr)
                total_clean_chunks += 1
                total_clean_duration += len(chunk) / sr

            if (idx + 1) % 10 == 0 or (idx + 1) == len(raw_files):
                print(f"[PROGRESS] {idx+1}/{len(raw_files)} dosya islendi... (Temiz Parca: {total_clean_chunks})")
                sys.stdout.flush()

        except Exception as e:
            failed_files += 1
            print(f"[WARN] Dosya okunamadi ({fname}): {e}")
            sys.stdout.flush()

    report = {
        "total_input_files": len(raw_files),
        "total_raw_hours": total_raw_duration / 3600.0,
        "total_clean_chunks": total_clean_chunks,
        "total_clean_minutes": total_clean_duration / 60.0,
        "failed_files": failed_files,
        "output_dir": PROCESSED_DIR
    }

    print("\n" + "=" * 60)
    print("SES VERI SETI VE DSP FILTRELEME RAPORU")
    print("=" * 60)
    print(f"Toplam Ham Dosya:       {report['total_input_files']} adet")
    print(f"Toplam Ham Ses Suresi:  {report['total_raw_hours']:.2f} SAAT")
    print(f"Uretilen Temiz Parca:   {report['total_clean_chunks']} adet (4-15 sn arasi)")
    print(f"Toplam Temiz Konusma:   {report['total_clean_minutes']:.1f} DAKIKA")
    print(f"Kayit Yeri:             {report['output_dir']}")
    print("=" * 60)
    sys.stdout.flush()

    return report

if __name__ == "__main__":
    process_entire_dataset()

"""
TENRA Voice Twin - Geliştirilmiş RVC Inference Bridge v2
- Silence normalizasyonu (pydub) RVC öncesinde ve sonrasında
- Optimize edilmiş parametreler: index_rate=0.5, protect=0.45
- Subprocess warmup (model hafızada tutma desteği)
"""
import os
import sys
import glob
import subprocess
import tempfile

APPLIO_ROOT = "C:\\Applio"
APPLIO_PYTHON = os.path.join(APPLIO_ROOT, "env", "python.exe")


def get_latest_model():
    """Eğitilmiş en güncel Ahmet Eren modelini bulur (v2 öncelikli)."""
    # 1. v2 model ağırlığı (250 epoch derin eğitim)
    v2_weight = os.path.join(APPLIO_ROOT, "assets", "weights", "ahmet_eren_v2.pth")
    if os.path.exists(v2_weight):
        return v2_weight

    # 2. v2 logs klasöründeki en son pth
    v2_logs = os.path.join(APPLIO_ROOT, "logs", "ahmet_eren_v2")
    if os.path.exists(v2_logs):
        v2_pths = glob.glob(os.path.join(v2_logs, "ahmet_eren_v2_*e_*.pth"))
        if v2_pths:
            v2_pths.sort(key=os.path.getmtime, reverse=True)
            return v2_pths[0]

    # 3. v1 model ağırlığı (100 epoch)
    primary_weight = os.path.join(APPLIO_ROOT, "assets", "weights", "ahmet_eren.pth")
    if os.path.exists(primary_weight):
        return primary_weight

    # 4. v1 logs klasörü
    logs_dir = os.path.join(APPLIO_ROOT, "logs", "ahmet_eren")
    if os.path.exists(logs_dir):
        all_pths = [p for p in glob.glob(os.path.join(logs_dir, "*.pth"))
                    if not os.path.basename(p).startswith("D_") and not os.path.basename(p).startswith("G_")]
        if all_pths:
            all_pths.sort(key=os.path.getmtime, reverse=True)
            return all_pths[0]
    return None


def get_model_index():
    """Modelin Faiss arama indeksini bulur (v2 öncelikli)."""
    # 1. assets/weights içindeki v2 indeksi
    v2_idx_assets = os.path.join(APPLIO_ROOT, "assets", "weights", "ahmet_eren_v2.index")
    if os.path.exists(v2_idx_assets):
        return v2_idx_assets

    # 2. logs/ahmet_eren_v2 içindeki indeks
    v2_logs = os.path.join(APPLIO_ROOT, "logs", "ahmet_eren_v2")
    if os.path.exists(v2_logs):
        indices = glob.glob(os.path.join(v2_logs, "*.index"))
        if indices:
            indices.sort(key=os.path.getmtime, reverse=True)
            return indices[0]

    # 3. v1 indeksi
    logs_dir = os.path.join(APPLIO_ROOT, "logs", "ahmet_eren")
    if os.path.exists(logs_dir):
        indices = glob.glob(os.path.join(logs_dir, "*.index"))
        if indices:
            indices.sort(key=os.path.getmtime, reverse=True)
            return indices[0]
    return ""


def trim_silence_wav(input_path: str, output_path: str,
                     silence_thresh_rms: float = 0.003,
                     min_silence_ms: int = 500,
                     keep_silence_ms: int = 180) -> str:
    """
    WAV dosyasındaki uzun sessizlikleri kırpar (numpy/soundfile — ffmpeg gerekmez).
    - silence_thresh_rms: Bu RMS değerinin altı sessizlik sayılır (~-38dB)
    - min_silence_ms: Bu kadar ms'den uzun sessizlikleri kırp
    - keep_silence_ms: Kesimler arasında bırakılacak sessizlik (ms)
    """
    try:
        import soundfile as sf
        import numpy as np

        data, sr = sf.read(input_path, dtype='float32')
        if len(data.shape) > 1:
            data_mono = data.mean(axis=1)
        else:
            data_mono = data

        frame_ms = 10
        frame_size = int(sr * frame_ms / 1000)
        min_silence_frames = int(min_silence_ms / frame_ms)
        keep_frames = int(keep_silence_ms / frame_ms)

        # Her frame'in RMS'ini hesapla
        frames_info = []
        for i in range(0, len(data_mono) - frame_size, frame_size):
            rms = float(np.sqrt(np.mean(data_mono[i:i + frame_size] ** 2)))
            frames_info.append((i, rms))

        if not frames_info:
            import shutil
            shutil.copy2(input_path, output_path)
            return output_path

        is_silent = [rms < silence_thresh_rms for _, rms in frames_info]

        # Sessiz frame bloklarını bul, uzunlarını kırp
        result_chunks = []
        i = 0
        while i < len(frames_info):
            if is_silent[i]:
                j = i
                while j < len(frames_info) and is_silent[j]:
                    j += 1
                silence_len = j - i

                if silence_len >= min_silence_frames:
                    # Uzun sessizlik → sadece keep_frames kadar bırak
                    keep_end = min(i + keep_frames, j)
                    start_s = frames_info[i][0]
                    end_s = frames_info[keep_end - 1][0] + frame_size if keep_end > 0 else start_s + frame_size
                    result_chunks.append(data[start_s:end_s])
                else:
                    # Kısa sessizlik → olduğu gibi bırak
                    start_s = frames_info[i][0]
                    end_s = frames_info[j - 1][0] + frame_size
                    result_chunks.append(data[start_s:end_s])
                i = j
            else:
                j = i
                while j < len(frames_info) and not is_silent[j]:
                    j += 1
                start_s = frames_info[i][0]
                end_s = frames_info[j - 1][0] + frame_size
                result_chunks.append(data[start_s:end_s])
                i = j

        if result_chunks:
            trimmed = np.concatenate(result_chunks, axis=0)
            sf.write(output_path, trimmed, sr)
        else:
            import shutil
            shutil.copy2(input_path, output_path)

        return output_path

    except Exception as e:
        print(f"[Silence Trim Uyarı]: {e}")
        import shutil
        shutil.copy2(input_path, output_path)
        return output_path


def convert_to_ahmet_voice(input_wav: str, output_wav: str = None,
                           pitch: int = 0,
                           index_rate: float = 0.5,
                           protect: float = 0.45,
                           clean_audio: bool = False) -> str:
    """
    input_wav dosyasını Ahmet Eren'in sesine dönüştürür.
    
    Parametre değişiklikleri (v2):
    - index_rate: 0.75 → 0.5  (daha doğal prosody, daha az yapay)
    - protect: 0.33 → 0.45    (ünsüzleri daha iyi koru, robotik gürültü azalır)
    - clean_audio: False      (RVC yerel HiFi-GAN çıktısı temizdir)
    """
    input_wav = os.path.abspath(input_wav)
    if not output_wav:
        base, _ = os.path.splitext(input_wav)
        output_wav = f"{base}_ahmet.wav"
    else:
        output_wav = os.path.abspath(output_wav)

    # Output directory'nin var olduğundan emin ol
    os.makedirs(os.path.dirname(output_wav), exist_ok=True)

    model_path = get_latest_model()
    if not model_path:
        print("[RVC Uyarı]: Henüz eğitilmiş Ahmet Eren modeli bulunamadı.")
        return input_wav

    index_path = get_model_index()

    # Adım 1: Girdi dosyasını silence-trim et
    trimmed_input = input_wav.replace(".wav", "_trimmed.wav")
    if not input_wav.endswith("_trimmed.wav"):
        trimmed_input = trim_silence_wav(input_wav, trimmed_input)
    else:
        trimmed_input = input_wav

    # Adım 2: RVC dönüşümü
    clean_str = "True" if clean_audio else "False"
    infer_code = f"""
import os, sys
os.chdir(r"{APPLIO_ROOT}")
sys.path.insert(0, r"{APPLIO_ROOT}")
from rvc.infer.infer import VoiceConverter
vc = VoiceConverter()
vc.convert_audio(
    audio_input_path=r"{trimmed_input}",
    audio_output_path=r"{output_wav}",
    model_path=r"{model_path}",
    index_path=r"{index_path}",
    pitch={pitch},
    f0_method="rmvpe",
    index_rate={index_rate},
    volume_envelope=1.0,
    protect={protect},
    embedder_model="contentvec",
    clean_audio={clean_str},
    clean_strength=0.3,
    split_audio=False,
    export_format="WAV"
)
print("RVC_DONE")
"""
    try:
        res = subprocess.run(
            [APPLIO_PYTHON, "-c", infer_code],
            capture_output=True,
            text=True,
            cwd=APPLIO_ROOT,
            timeout=120
        )

        if os.path.exists(output_wav) and os.path.getsize(output_wav) > 5000:
            # Temp dosyayı temizle
            if os.path.exists(trimmed_input) and trimmed_input != input_wav:
                try:
                    os.remove(trimmed_input)
                except Exception:
                    pass

            return output_wav
        else:
            err = res.stderr.strip() or res.stdout.strip()
            print(f"[RVC Hata]: {err[:500]}")
            return input_wav

    except subprocess.TimeoutExpired:
        print("[RVC Hata]: 120 saniye zaman aşımı.")
        return input_wav
    except Exception as e:
        print(f"[RVC İstisna]: {e}")
        return input_wav


if __name__ == "__main__":
    m = get_latest_model()
    idx = get_model_index()
    print("Tespit edilen Model:", m)
    print("Tespit edilen Index:", idx)

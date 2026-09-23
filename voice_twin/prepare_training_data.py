import os
import glob
import soundfile as sf
import numpy as np
from scipy import signal

def resample_and_normalize(input_path, output_path, target_sr=40000):
    data, sr = sf.read(input_path)
    # Convert stereo to mono
    if len(data.shape) > 1:
        data = np.mean(data, axis=1)
    
    # Resample if needed
    if sr != target_sr:
        num_samples = int(len(data) * target_sr / sr)
        data = signal.resample(data, num_samples)
    
    # Peak normalization
    max_val = np.max(np.abs(data))
    if max_val > 0.001:
        data = data / max_val * 0.95
    else:
        return False  # Too silent
        
    sf.write(output_path, data, target_sr, subtype='PCM_16')
    return True

def calculate_quality(data, sr):
    if len(data.shape) > 1:
        data = np.mean(data, axis=1)
    if len(data) == 0:
        return 0, 0
    rms = np.sqrt(np.mean(data**2))
    # Spectral centroid approximation via zero crossings / diff
    diff = np.diff(data)
    zcr = np.mean(np.abs(np.diff(np.signbit(data))))
    return rms, zcr

def prepare_dataset():
    output_dir = os.path.abspath("ses_veriseti/training_ready")
    os.makedirs(output_dir, exist_ok=True)
    
    clean_src = os.path.abspath("ses_veriseti/elevenlabs_ready")
    processed_src = os.path.abspath("ses_veriseti/processed")
    
    count = 0
    total_duration = 0.0
    
    # 1. Add all studio/daylight recordings (Gold Standard)
    print("=== [1/2] Stüdyo & Referans Kayıtları Ekleniyor ===")
    clean_files = sorted(glob.glob(os.path.join(clean_src, "*.wav")))
    for f in clean_files:
        basename = os.path.basename(f)
        out_file = os.path.join(output_dir, f"gold_{basename}")
        if resample_and_normalize(f, out_file, target_sr=40000):
            info = sf.info(out_file)
            total_duration += info.duration
            count += 1
            print(f"  [GOLD] {basename} ({info.duration:.1f}s) eklendi.")

    # 2. Filter best chunks from processed dataset (Reject boğuk / muffled / silent)
    print("\n=== [2/2] İşlenmiş Parçalardan En Net Olanlar Seçiliyor ===")
    proc_files = sorted(glob.glob(os.path.join(processed_src, "*.wav")))
    
    candidates = []
    for f in proc_files:
        try:
            data, sr = sf.read(f)
            duration = len(data) / sr
            if duration < 2.0 or duration > 15.0:
                continue
            rms, zcr = calculate_quality(data, sr)
            # Filter: must have clear speech energy (rms > 0.03) and good clarity (zcr > 0.03)
            if rms > 0.03 and zcr > 0.03:
                candidates.append((f, rms * zcr, duration))
        except Exception:
            pass
            
    # Sort by clarity score descending
    candidates.sort(key=lambda x: x[1], reverse=True)
    
    # Take top 80 clearest clips to guarantee pristine quality without muffling
    selected_clips = candidates[:80]
    for idx, (f, score, dur) in enumerate(selected_clips, 1):
        basename = os.path.basename(f)
        out_file = os.path.join(output_dir, f"clean_{idx:03d}_{basename}")
        if resample_and_normalize(f, out_file, target_sr=40000):
            info = sf.info(out_file)
            total_duration += info.duration
            count += 1
            
    print(f"\n[OK] Toplam {count} adet kristal netliğinde ses parçası hazırlandı!")
    print(f"[OK] Toplam Eğitim Süresi: {total_duration / 60:.2f} dakika ({total_duration:.1f} saniye)")
    print(f"[OK] Eğitim Verisi Klasörü: {output_dir}")
    return output_dir

if __name__ == "__main__":
    prepare_dataset()

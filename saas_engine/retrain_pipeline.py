# -*- coding: utf-8 -*-
"""
TENRA Voice Twin - Yeniden Egitim Scripti v2
Dogru Applio core.py parametre isimleriyle.
"""
import os
import sys
import glob
import shutil
import subprocess
import time

PROJECT_ROOT  = os.path.dirname(os.path.abspath(__file__))
DATASET_DIR   = os.path.join(PROJECT_ROOT, "voice_dataset")
PROCESSED_DIR = os.path.join(DATASET_DIR, "processed")
STUDIO_DIR    = os.path.join(DATASET_DIR, "elevenlabs_ready")
TRAIN_DIR     = os.path.join(DATASET_DIR, "training_ready_v2")

APPLIO_ROOT   = "C:\\Applio"
APPLIO_PYTHON = os.path.join(APPLIO_ROOT, "env", "python.exe")
APPLIO_DATASET= os.path.join(APPLIO_ROOT, "assets", "datasets", "ahmet_eren_v2")
MODEL_NAME    = "ahmet_eren_v2"

os.makedirs(TRAIN_DIR, exist_ok=True)
os.makedirs(APPLIO_DATASET, exist_ok=True)

def compute_snr(wav_path):
    try:
        import soundfile as sf
        import numpy as np
        data, sr = sf.read(wav_path, dtype='float32')
        if len(data.shape) > 1:
            data = data.mean(axis=1)
        frame = int(sr * 0.02)
        rms_frames = []
        for i in range(0, len(data) - frame, frame):
            rms = float(np.sqrt(np.mean(data[i:i+frame]**2)))
            if rms > 0:
                rms_frames.append(rms)
        if len(rms_frames) < 5:
            return 0.0
        rms_frames.sort()
        noise_rms  = float(np.mean(rms_frames[:max(1, len(rms_frames)//10)]))
        signal_rms = float(np.mean(rms_frames[int(len(rms_frames)*0.5):]))
        if noise_rms <= 0:
            return 0.0
        import numpy as np
        return 20 * np.log10(signal_rms / noise_rms)
    except Exception:
        return 0.0

def duration_sec(wav_path):
    try:
        import soundfile as sf
        return sf.info(wav_path).duration
    except Exception:
        return 0.0

print("=" * 60)
print("  TENRA Yeniden Egitim v2 - Veri Secimi")
print("=" * 60)

print("\n[1/5] WAV'lar taranıyor...")
wav_files = glob.glob(os.path.join(PROCESSED_DIR, "*.wav"))
print("  Toplam islenmis WAV:", len(wav_files))

scored = []
for wf in wav_files:
    snr = compute_snr(wf)
    dur = duration_sec(wf)
    if 1.0 <= dur <= 12.0 and snr > 12.0:
        scored.append((snr, dur, wf))

scored.sort(key=lambda x: x[0], reverse=True)
print("  SNR>12dB & 1-12s arasi:", len(scored), "dosya")
top_wavs = scored[:150]
print("  Secilen (top-150):", len(top_wavs), "dosya")

print("\n[2/5] Studyo kayitlari ekleniyor...")
studio_wavs = glob.glob(os.path.join(STUDIO_DIR, "*.wav"))
print("  Studyo WAV:", len(studio_wavs), "dosya")

print("\n[3/5] Dosyalar kopyalaniyor...")
for f in glob.glob(os.path.join(TRAIN_DIR, "*.wav")):
    os.remove(f)

copied = 0
for snr, dur, wf in top_wavs:
    dst = os.path.join(TRAIN_DIR, "sel_%04d_%s" % (copied, os.path.basename(wf)))
    shutil.copy2(wf, dst)
    copied += 1

for wf in studio_wavs:
    dst = os.path.join(TRAIN_DIR, "studio_%s" % os.path.basename(wf))
    shutil.copy2(wf, dst)
    copied += 1

print("  Toplam kopyalanan:", copied, "dosya")

for f in glob.glob(os.path.join(TRAIN_DIR, "*.wav")):
    shutil.copy2(f, APPLIO_DATASET)
print("  Applio dataset hazir:", APPLIO_DATASET)

# ─── Adım 4: Preprocess ──────────────────────────────────────────────────────
print("\n[4/5] Applio Preprocess basliyor...")
preprocess_code = (
    "import os,sys\n"
    "os.chdir(r'" + APPLIO_ROOT + "')\n"
    "sys.path.insert(0,r'" + APPLIO_ROOT + "')\n"
    "from core import run_preprocess_script\n"
    "result = run_preprocess_script(\n"
    "    model_name='" + MODEL_NAME + "',\n"
    "    dataset_path=r'" + APPLIO_DATASET + "',\n"
    "    sample_rate=40000,\n"
    "    cpu_cores=4,\n"
    "    cut_preprocess='Simple',\n"
    "    process_effects=False,\n"
    "    noise_reduction=False,\n"
    "    clean_strength=0.7,\n"
    "    chunk_len=3.0,\n"
    "    overlap_len=0.3,\n"
    "    normalization_mode='none'\n"
    ")\n"
    "print('PREPROCESS_RESULT:', result)\n"
)

res = subprocess.run(
    [APPLIO_PYTHON, "-c", preprocess_code],
    capture_output=True, text=True, cwd=APPLIO_ROOT, timeout=600
)
stdout_out = res.stdout + res.stderr
print(stdout_out[-2000:])
if "preprocessed successfully" in stdout_out or "PREPROCESS_RESULT" in stdout_out:
    print("  [OK] Preprocess tamamlandi.")
else:
    print("  [HATA] Preprocess basarisiz. Cikiliyor.")
    sys.exit(1)

# ─── Adım 5a: Feature Extraction ─────────────────────────────────────────────
print("\n[5a/5] Feature Extraction basliyor...")
extract_code = (
    "import os,sys\n"
    "os.chdir(r'" + APPLIO_ROOT + "')\n"
    "sys.path.insert(0,r'" + APPLIO_ROOT + "')\n"
    "from core import run_extract_script\n"
    "result = run_extract_script(\n"
    "    model_name='" + MODEL_NAME + "',\n"
    "    f0_method='rmvpe',\n"
    "    cpu_cores=4,\n"
    "    gpu=0,\n"
    "    sample_rate=40000,\n"
    "    embedder_model='contentvec',\n"
    "    embedder_model_custom=None,\n"
    "    include_mutes=2\n"
    ")\n"
    "print('EXTRACT_RESULT:', result)\n"
)

res = subprocess.run(
    [APPLIO_PYTHON, "-c", extract_code],
    capture_output=True, text=True, cwd=APPLIO_ROOT, timeout=1800
)
stdout_out = res.stdout + res.stderr
print(stdout_out[-2000:])
if "extracted successfully" in stdout_out or "EXTRACT_RESULT" in stdout_out:
    print("  [OK] Feature extraction tamamlandi.")
else:
    print("  [HATA] Extract basarisiz. Cikiliyor.")
    sys.exit(1)

# ─── Adım 5b: 250 Epoch Eğitim ───────────────────────────────────────────────
print("\n[5b/5] 250 Epoch Egitim Basliyor (~5-6 saat)...")
train_code = (
    "import os,sys\n"
    "os.chdir(r'" + APPLIO_ROOT + "')\n"
    "sys.path.insert(0,r'" + APPLIO_ROOT + "')\n"
    "from core import run_train_script\n"
    "result = run_train_script(\n"
    "    model_name='" + MODEL_NAME + "',\n"
    "    save_every_epoch=25,\n"
    "    save_only_latest=False,\n"
    "    save_every_weights=True,\n"
    "    total_epoch=250,\n"
    "    sample_rate=40000,\n"
    "    batch_size=8,\n"
    "    gpu=0,\n"
    "    pretrained=True,\n"
    "    cleanup=False,\n"
    "    index_algorithm='Auto',\n"
    "    cache_data_in_gpu=True,\n"
    "    custom_pretrained=False,\n"
    "    g_pretrained_path=None,\n"
    "    d_pretrained_path=None,\n"
    "    vocoder='HiFi-GAN',\n"
    "    checkpointing=False\n"
    ")\n"
    "print('TRAIN_RESULT:', result)\n"
)

train_start = time.time()
res = subprocess.run(
    [APPLIO_PYTHON, "-c", train_code],
    cwd=APPLIO_ROOT,
    timeout=30000
)
elapsed = time.time() - train_start

if res.returncode == 0:
    print("\n[TAMAM] Egitim tamamlandi! (%.1f saat)" % (elapsed/3600))
    print("Model: C:\\Applio\\assets\\weights\\" + MODEL_NAME + ".pth")
else:
    print("\n[HATA] Egitim basarisiz (code: %d)" % res.returncode)

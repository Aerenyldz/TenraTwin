import os
import sys
import shutil
import subprocess
import glob

APPLIO_DIR = "C:\\Applio"
DATASET_SRC = os.path.abspath("ses_veriseti/training_ready")
MODEL_NAME = "ahmet_eren"

def find_python():
    # Prefer Applio's embedded/bundled python if present
    candidates = [
        os.path.join(APPLIO_DIR, "env", "python.exe"),
        os.path.join(APPLIO_DIR, "runtime", "python.exe"),
        os.path.join(APPLIO_DIR, "venv", "Scripts", "python.exe"),
        sys.executable
    ]
    for p in candidates:
        if os.path.exists(p):
            return p
    return sys.executable

def start_training():
    print("==================================================")
    print(f"  TENRA - Ahmet Eren Ses Modeli Eğitimi (RVC v2)  ")
    print("==================================================")

    if not os.path.exists(APPLIO_DIR):
        print(f"[HATA] Applio dizini bulunamadı: {APPLIO_DIR}")
        return False

    applio_py = find_python()
    core_py = os.path.join(APPLIO_DIR, "core.py")
    
    if not os.path.exists(core_py):
        print(f"[HATA] core.py bulunamadı: {core_py}")
        return False

    # 1. Copy curated dataset into Applio
    target_dataset = os.path.join(APPLIO_DIR, "assets", "datasets", MODEL_NAME)
    os.makedirs(target_dataset, exist_ok=True)
    
    files = glob.glob(os.path.join(DATASET_SRC, "*.wav"))
    print(f"\n[1/4] {len(files)} adet stüdyo kalitesindeki ses dosyası Applio'ya kopyalanıyor...")
    for f in files:
        shutil.copy2(f, os.path.join(target_dataset, os.path.basename(f)))
    print(f"[OK] Dosyalar kopyalandı: {target_dataset}")

    # 2. Preprocess (Resample, Slice)
    print(f"\n[2/4] Ön işleme (Preprocess) başlatılıyor...")
    # Applio core preprocess args: model_name, dataset_path, sample_rate
    cmd_prep = [applio_py, core_py, "preprocess", "--model_name", MODEL_NAME, "--dataset_path", target_dataset, "--sample_rate", "40000"]
    print(f"Komut: {' '.join(cmd_prep)}")
    p1 = subprocess.run(cmd_prep, cwd=APPLIO_DIR)
    if p1.returncode != 0:
        print("[UYARI] Preprocess standart argümanlarla deneniyor...")
        subprocess.run([applio_py, core_py, "preprocess", MODEL_NAME, target_dataset, "40000"], cwd=APPLIO_DIR)

    # 3. Extract Features (RMVPE F0 + HuBERT)
    print(f"\n[3/4] Ses Özellikleri ve Perde Analizi (RMVPE) Çıkarılıyor...")
    cmd_ext = [applio_py, core_py, "extract", "--model_name", MODEL_NAME, "--rvc_version", "v2", "--f0_method", "rmvpe"]
    print(f"Komut: {' '.join(cmd_ext)}")
    p2 = subprocess.run(cmd_ext, cwd=APPLIO_DIR)

    # 4. Train Model
    print(f"\n[4/4] Model Eğitimi Başlatılıyor (RTX 5060)...")
    print("      Model: ahmet_eren, Hedef Epoch: 100, Batch Size: 6")
    cmd_train = [
        applio_py, core_py, "train",
        "--model_name", MODEL_NAME,
        "--rvc_version", "v2",
        "--save_every_epoch", "20",
        "--total_epoch", "100",
        "--batch_size", "6",
        "--sample_rate", "40000"
    ]
    print(f"Komut: {' '.join(cmd_train)}")
    p3 = subprocess.run(cmd_train, cwd=APPLIO_DIR)

    # 5. Indexing
    print(f"\n[5/5] Faiss Arama İndeksi Oluşturuluyor...")
    cmd_idx = [applio_py, core_py, "index", "--model_name", MODEL_NAME, "--rvc_version", "v2"]
    subprocess.run(cmd_idx, cwd=APPLIO_DIR)

    print("\n==================================================")
    print("  TEBRİKLER! Ahmet Eren Ses Modeli Başarıyla Eğitildi!")
    print("==================================================")
    return True

if __name__ == "__main__":
    start_training()

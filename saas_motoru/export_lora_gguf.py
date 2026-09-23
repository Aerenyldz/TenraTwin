"""
TENRA - LoRA Adapter to GGUF Yontemi (v3 - 16-bit Kimlik Yamasi)
Llama.cpp 'bitsandbytes' base modellerini cozemez.
Bu script, kimligi "unsloth/llama-3-8b" (16-bit) olarak yamalar
boylece llama.cpp sorunsuz bir sekilde boyutlari okur ve cevirimi yapar.
"""
import os
import shutil
import subprocess
import json

print("=" * 50)
print("  TENRA HIZLI LORA -> GGUF DONUSTURUCU (v3)")
print("=" * 50)

CHECKPOINT_DIR = "tenra_checkpoints_v2/checkpoint-1000"
LORA_GGUF = "tenra_lora.gguf"
ADAPTER_CONFIG = os.path.join(CHECKPOINT_DIR, "adapter_config.json")

print("[1/2] Llama.cpp cevirici hazirlaniyor (16-bit Yamasi)...")

# adapter_config.json'u yedekle
shutil.copy(ADAPTER_CONFIG, ADAPTER_CONFIG + ".bak")

with open(ADAPTER_CONFIG, "r") as f:
    config_data = json.load(f)

# Kimligi gercek 16-bit huggingface ismine cevir
config_data["base_model_name_or_path"] = "unsloth/llama-3-8b"

with open(ADAPTER_CONFIG, "w") as f:
    json.dump(config_data, f)

print("[2/2] LoRA GGUF'a ceviriliyor (Saniyeler surecek)...")
CONVERT_SCRIPT = os.path.expanduser("~/.unsloth/llama.cpp/convert_lora_to_gguf.py")

result = subprocess.run([
    "python", CONVERT_SCRIPT,
    CHECKPOINT_DIR,
    "--outfile", LORA_GGUF
], capture_output=True, text=True)

print("[3/3] Orijinal Kimlik geri yukleniyor...")
shutil.move(ADAPTER_CONFIG + ".bak", ADAPTER_CONFIG)

if result.returncode != 0:
    print(f"\nHATA OLUŞTU:\n{result.stderr}")
    print(f"Stdout:\n{result.stdout}")
    exit(1)

print("\n" + "=" * 50)
print("  MUHTESEM! LoRA GGUF OLUSTURULDU!")
print(f"  Dosya: {LORA_GGUF} ({os.path.getsize(LORA_GGUF) / 1024**2:.1f} MB)")
print("=" * 50)

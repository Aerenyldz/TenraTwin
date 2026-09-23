"""
TENRA - Checkpoint'ten GGUF'a Donusturme (v5 - Unsloth Orijinal Yontemi)
En guvenli ve hatasiz yontem.

Kullanim:
  cd ~/dijital_ikiz
  source ai_env/bin/activate
  python export_to_gguf.py
"""
import os
os.environ["WANDB_DISABLED"] = "true"

from unsloth import FastLanguageModel

print("=" * 50)
print("  TENRA Model Export - GGUF (v5)")
print("=" * 50)

# Checkpoint yolunu dogrudan Unsloth'a veriyoruz
# Unsloth, base modeli ve LoRA'yi otomatik bulup birlestirecek!
print("\n[1/2] Model ve Checkpoint yukleniyor...")
CHECKPOINT_PATH = "tenra_checkpoints_v2/checkpoint-1000"

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name=CHECKPOINT_PATH,
    max_seq_length=2048,
    load_in_4bit=True,
    local_files_only=False, # Ilk basta base modeli bulabilmesi icin kisa bir sure internete veya cache'e bakar
)

# Unsloth'un hizli GGUF fonksiyonunu kullaniyoruz
print("\n[2/2] GGUF formatina donusturuluyor (Q4_K_M)...")
print("  Bu islem RAM'e yuklenecek, 5-10 dakika surebilir...")

# 8GB VRAM'e sigmadigi icin otomatik olarak CPU RAM kullanacak
model.save_pretrained_gguf(
    "tenra_gguf",
    tokenizer,
    quantization_method="q4_k_m",
)

print("\n" + "=" * 50)
print("  EXPORT TAMAMLANDI!")
print("  GGUF dosyasi 'tenra_gguf' isminde (muhtemelen .gguf uzantili) olusturuldu.")
print("  Siradaki adim: ollama create tenra -f Modelfile")
print("=" * 50)

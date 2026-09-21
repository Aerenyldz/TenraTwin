"""
TENRA Voice Twin - Ses Kayıt Aracı
Mikrofondan 10-15 saniyelik temiz, net ve enerjik ses kaydı alır.
Ses klonlama modeli için referans ses (ahmet_gunduz_ref.wav) oluşturur.
"""
import os
import sys
import time
import sounddevice as sd
import soundfile as sf
import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "voice_dataset")
TARGET_WAV = os.path.join(OUTPUT_DIR, "ahmet_gunduz_ref.wav")

os.makedirs(OUTPUT_DIR, exist_ok=True)

SUGGESTED_TEXT = (
    "Selam, ben Ahmet Eren. Bilgisayar mühendisliği öğrencisiyim. "
    "Yazılım ve yapay zeka sistemleri üzerine çalışıyorum. "
    "Bugün sporda bench press antrenmanım var, akşam da arkadaşlarımla buluşacağım."
)

def record_audio(duration: int = 14, sample_rate: int = 24000):
    print("=" * 60)
    print("🎙️ TENRA - AHMET EREN GÜNDÜZ SES REFERANSI KAYDI")
    print("=" * 60)
    print("\n💡 İpucu: Mikrofona normal konuşma mesafesinde, net ve enerjik bir")
    print("tonlamayla konuş. Aşağıdaki örnek metni okuyabilirsin:\n")
    print("-" * 60)
    print(f'"{SUGGESTED_TEXT}"')
    print("-" * 60)
    print("\nHazır olduğunda [ENTER] tuşuna bas...")
    try:
        input()
    except EOFError:
        pass

    # Geri sayım
    print("Kayıt başlıyor:")
    for i in range(3, 0, -1):
        print(f"  {i}...")
        time.sleep(1)
    print("🔴 KAYIT BAŞLADI! (Şimdi konuş)...")

    # Kaydı al
    try:
        audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
        # İlerleme çubuğu
        for sec in range(duration):
            time.sleep(1)
            remaining = duration - sec - 1
            sys.stdout.write(f"\r⏳ Kaydediliyor: {sec + 1}/{duration} sn (Kalan: {remaining} sn)  ")
            sys.stdout.flush()
        sd.wait()
        print("\n⏹️ Kayıt tamamlandı!")
    except Exception as e:
        print(f"\n❌ Kayıt hatası: {e}")
        return False

    # Normalizasyon
    audio = audio.flatten()
    max_val = np.max(np.abs(audio))
    if max_val > 0:
        audio = audio / max_val * 0.95

    # Kaydet
    sf.write(TARGET_WAV, audio, sample_rate)
    print(f"\n💾 Ses referansı kaydedildi:\n-> {TARGET_WAV}")

    # Geri dinletme
    print("\n🔊 Kaydedilen ses şimdi hoparlörden çalınıyor...")
    try:
        sd.play(audio, sample_rate)
        sd.wait()
    except Exception as e:
        print(f"Dinletme hatası: {e}")

    print("\n" + "=" * 60)
    cevap = input("Sesi beğendin mi? Kaydı onaylıyor musun? (E/H): ").strip().lower()
    if cevap == 'e' or cevap == '':
        print("✅ Harika! Bu ses kaydı ana referans olarak belirlendi.")
        return True
    else:
        print("🔄 Yeniden kaydetmek istersen bu komutu tekrar çalıştırabilirsin.")
        return False

if __name__ == "__main__":
    record_audio()

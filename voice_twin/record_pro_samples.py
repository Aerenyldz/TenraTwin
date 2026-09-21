"""
TENRA Voice Twin - 25-30 Saniyelik Profesyonel Ses Kayıt Aracı
ElevenLabs için 3 adet uzun (25-30 saniye) temiz ses kaydı alır.
"""
import os
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
import time
import sounddevice as sd
import soundfile as sf
import numpy as np

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "voice_dataset", "elevenlabs_ready")
os.makedirs(OUTPUT_DIR, exist_ok=True)

PROMPTS = [
    {
        "id": 1,
        "title": "Metin 1: Günlük Yaşam, Spor & Mühendislik",
        "duration": 25,
        "text": (
            "Selamlar, ben Ahmet Eren Yıldız. Bilgisayar mühendisliği okuyorum, "
            "günümün çoğunu yazılım geliştirerek ve kod yazarak geçiriyorum. "
            "Aynı zamanda düzenli olarak fitness ve ağırlık antrenmanları yapıyorum. "
            "Genelde bench press ve güç odaklı çalışırım. "
            "Akşamları da arkadaşlarımla toplanıp projeler hakkında konuşuruz."
        )
    },
    {
        "id": 2,
        "title": "Metin 2: Sesli Asistan & Çağrı Karşılama",
        "duration": 25,
        "text": (
            "Beni aradığınız için teşekkürler. Şu an derste veya sporda olduğum için "
            "telefona hemen bakamayabilirim. Ama sesli asistanıma ne konuda aradığınızı "
            "ve adınızı söylerseniz, bana anında not iletecek ve gün içinde "
            "en kısa sürede size mutlaka geri döneceğim. Şimdilik görüşmek üzere!"
        )
    },
    {
        "id": 3,
        "title": "Metin 3: Teknoloji & Yapay Zeka Sistemleri",
        "duration": 25,
        "text": (
            "Yapay zeka ve makine öğrenmesi projeleri üzerine yoğunlaşıyorum. "
            "Kendi yerel modellerimi eğitmeyi, ses teknolojilerini ve otonom sistemleri "
            "geliştirmeyi çok seviyorum. Hem backend tarafında Python ve FastAPI ile çalışıyorum "
            "hem de yeni nesil yapay zeka modellerini günlük hayatıma entegre ediyorum."
        )
    }
]

def record_sample(prompt_idx: int, sample_rate: int = 24000):
    item = PROMPTS[prompt_idx]
    duration = item["duration"]
    target_file = os.path.join(OUTPUT_DIR, f"0{item['id']}_ahmet_canli_kayit.wav")

    print("\n" + "=" * 65)
    print(f"🎙️ {item['title']} (Süre: {duration} Saniye)")
    print("=" * 65)
    print("\n💡 Aşağıdaki metni normal hızında, rahat ve anlaşılır şekilde oku:\n")
    print("-" * 65)
    print(f'"{item["text"]}"')
    print("-" * 65)
    print("\nHazır olduğunda [ENTER] tuşuna bas...")
    try:
        input()
    except EOFError:
        pass

    # Geri sayım
    for i in range(3, 0, -1):
        print(f"  {i}...")
        time.sleep(1)
    print("🔴 KAYIT BAŞLADI! (Şimdi oku)...")

    try:
        audio = sd.rec(int(duration * sample_rate), samplerate=sample_rate, channels=1, dtype='float32')
        for sec in range(duration):
            time.sleep(1)
            rem = duration - sec - 1
            sys.stdout.write(f"\r⏳ Kaydediliyor: {sec + 1}/{duration} sn (Kalan: {rem:02d} sn)  ")
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

    sf.write(target_file, audio, sample_rate)
    print(f"💾 Kaydedildi: {os.path.basename(target_file)}")

    # Geri dinletme
    print("🔊 Dinletiliyor...")
    try:
        sd.play(audio, sample_rate)
        sd.wait()
    except Exception:
        pass

    cevap = input("Sesi beğendin mi? Onaylıyor musun? (E/H): ").strip().lower()
    return cevap == 'e' or cevap == ''

def main():
    print("=" * 65)
    print("🎙️ ELEVENLABS İÇİN UZUN SES KAYIT PANELİ")
    print("=" * 65)
    print("Toplam 3 adet 25 saniyelik metin hazırladık.")
    print("İster sırayla hepsini kaydet, ister istediğin birini seç.")
    print("1. Metin 1'i Kaydet (Günlük & Spor)")
    print("2. Metin 2'yi Kaydet (Çağrı Asistanı)")
    print("3. Metin 3'ü Kaydet (Teknoloji & AI)")
    print("4. Hepsini Sırayla Kaydet (Önerilen - Toplam 1.5 dk)")
    
    secim = input("\nSeçimin (1-4, Varsayılan: 4): ").strip()
    if not secim: secim = "4"

    if secim in ["1", "2", "3"]:
        record_sample(int(secim) - 1)
    else:
        for i in range(3):
            record_sample(i)
            print("\nSonraki kayda geçmek için bekleniyor...")
            time.sleep(1)

    print("\n" + "=" * 65)
    print("✅ TÜM KAYITLAR HAZIR!")
    print(f"Dosyaların yeri: {OUTPUT_DIR}")
    print("ElevenLabs'e bu klasördeki tüm dosyaları yükleyebilirsin.")
    print("=" * 65)

if __name__ == "__main__":
    main()

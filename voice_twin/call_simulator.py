"""
TENRA Voice Twin - Interactive Call Simulator
Gelen çağrı senaryosunu test eder:
Mikrofon (STT Faster-Whisper) veya Klavye -> LLM (Ollama) -> TTS (Fish Audio Genç Ahmet) -> Hoparlör
Görüşmeyi kaydeder, özet çıkarır ve veritabanına işler.
"""
import os
import sys
try:
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')
except Exception:
    pass
import asyncio
from voice_twin.call_agent import handle_call_turn, summarize_and_save_call
from voice_twin.tts_engine import synthesize_speech, play_audio
from voice_twin.call_recorder import save_call_recording

async def run_call_simulation(caller_name: str = "Yunus Berk"):
    print("=" * 60)
    print(f"📞 GELEN ÇAĞRI SİMÜLATÖRÜ: {caller_name}")
    print("=" * 60)

    # Girdi modu seçimi
    print("\nNasıl yanıt vermek istersiniz?")
    print("  [1] 🎙️ Mikrofon ile Canlı Konuş (Önerilen)")
    print("  [2] ⌨️ Klavyeden Yaz")
    try:
        choice = input("Seçiminiz (1/2, varsayılan 1): ").strip()
    except (EOFError, KeyboardInterrupt):
        choice = "2"

    use_mic = choice != "2"
    if use_mic:
        from voice_twin.pipeline import record_microphone, transcribe_wav
        print("✅ Mikrofon modu aktif. Her turda Enter'a basıp konuşacaksınız.")
    else:
        print("⌨️ Klavye modu aktif.")

    audio_clips = []

    # 1. Asistan çağrıyı açar
    initial_greeting = f"Selam {caller_name}! Ben Ahmet'in sesli asistanıyım. Ahmet şu an derste. Önemli bir şey mi vardı, not almamı ister misin?"
    print(f"\n🤖 [Ahmet Sesli Asistan]: {initial_greeting}")
    audio_file = synthesize_speech(initial_greeting)
    audio_clips.append(audio_file)
    play_audio(audio_file)

    history = [
        {"role": "assistant", "content": initial_greeting}
    ]

    print("\n(Görüşmeyi bitirmek için 'q' yazabilir veya boş Enter'a basabilirsiniz)\n")

    # Diyalog döngüsü
    turn = 0
    while True:
        turn += 1
        caller_msg = ""

        try:
            if use_mic:
                cmd = input(f"\n[Tur {turn}] 🎙️ Konuşmak için [ENTER]'a basın (Çıkmak için 'q'): ").strip()
                if cmd.lower() in ("q", "quit", "cikis", "çıkış"):
                    print("\n📞 Görüşme kullanıcı tarafından sonlandırıldı.")
                    break

                wav_path = record_microphone(duration_sec=6)
                if wav_path and os.path.exists(wav_path):
                    print("⌛ Sesiniz yazıya dökülüyor...", end="\r")
                    caller_msg = transcribe_wav(wav_path)
                    print(f"👤 [{caller_name} - Mikrofon]: {caller_msg}")
                else:
                    caller_msg = input(f"👤 [{caller_name} - Klavye]: ").strip()
            else:
                caller_msg = input(f"👤 [{caller_name}]: ").strip()

        except (EOFError, KeyboardInterrupt):
            break

        if not caller_msg or caller_msg.lower() in ("q", "quit", "cikis", "çıkış"):
            print("\n📞 Görüşme sonlandırıldı.")
            break

        history.append({"role": "user", "content": caller_msg})

        # Asistan yanıtı (Ollama)
        print("💭 Asistan düşünüyor...", end="\r")
        reply = await handle_call_turn(caller_msg, history)
        history.append({"role": "assistant", "content": reply})

        print(f"🤖 [Ahmet Asistan]: {reply}")
        reply_audio = synthesize_speech(reply)
        audio_clips.append(reply_audio)
        play_audio(reply_audio)

        # Eğer arayan veda ettiyse
        if any(v in caller_msg.lower() for v in ["görüşürüz", "baybay", "tamamdır eyvallah", "kapatıyorum", "öptüm", "kolay gelsin"]):
            print("\n📞 Çağrı tamamlandı.")
            break

    # 3. Görüşme özetini çıkar ve Ahmet'e not bırak
    print("\n⏳ Görüşme analiz ediliyor ve Ahmet için özet not hazırlanıyor...")
    summary_data = await summarize_and_save_call(caller_name, history)

    # 4. Görüşmeyi arama_kayitlari/ altına arşivle
    saved_record = save_call_recording(
        caller_name=caller_name,
        transcript=summary_data.get("transcript", ""),
        summary=summary_data.get("summary", ""),
        audio_clips=audio_clips
    )

    # 5. Ses kaydını veritabanına bağla
    if summary_data.get("call_id") and saved_record:
        from voice_twin.call_logs_db import update_call_audio
        update_call_audio(summary_data["call_id"], saved_record)

    print("\n" + "=" * 60)
    print("📋 AHMET İÇİN YENİ ÇAĞRI NOTU")
    print("=" * 60)
    print(f"👤 Arayan:       {summary_data['caller']}")
    print(f"📌 Durum:        {summary_data['urgency'].upper()}")
    print(f"📝 Özet Not:     {summary_data['summary']}")
    print(f"💾 Ses & Rapor:  {saved_record}")
    print("=" * 60)

if __name__ == "__main__":
    caller = sys.argv[1] if len(sys.argv) > 1 else "Yunus Berk"
    asyncio.run(run_call_simulation(caller))

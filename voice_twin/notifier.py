"""
TENRA Voice Twin - Telegram Bildirim Sistemi
Görüşme bitince telefona:
  - 📋 Özet metin
  - 🔴/🟡/🟢 Aciliyet emoji
  - 🔊 Ses kaydı (WAV)
  gönderir.

KURULUM:
  1. Telegram'da @BotFather'a yaz → /newbot → token al
  2. Bot'a bir mesaj gönder, sonra şunu çalıştır:
     python voice_twin/notifier.py --setup
  3. Chat ID'yi config.json'a kaydet

  veya config.json'a direkt yaz:
  {
    "telegram_token": "123456:ABC...",
    "telegram_chat_id": "987654321"
  }
"""
import os
import sys
import json
import asyncio
import argparse

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(CURRENT_DIR, "config.json")

URGENCY_EMOJI = {
    "acil": "🔴",
    "normal": "🟡",
    "onemsiz": "🟢",
}


def load_config() -> dict:
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_config(cfg: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_telegram_credentials():
    cfg = load_config()
    token = os.getenv("TELEGRAM_TOKEN", cfg.get("telegram_token", ""))
    chat_id = os.getenv("TELEGRAM_CHAT_ID", cfg.get("telegram_chat_id", ""))
    return token, chat_id


async def send_call_notification(
    caller_name: str,
    summary: str,
    urgency: str,
    audio_path: str = None,
    transcript: str = None
) -> bool:
    """
    Görüşme özetini Telegram'a gönderir.
    Returns: True if sent successfully.
    """
    token, chat_id = get_telegram_credentials()
    if not token or not chat_id:
        print("[Telegram] Token veya Chat ID eksik. Config'e ekle.")
        print("           python voice_twin/notifier.py --setup")
        return False

    try:
        import httpx

        emoji = URGENCY_EMOJI.get(urgency, "🟡")
        text_msg = (
            f"{emoji} **Yeni Çağrı** — {caller_name}\n\n"
            f"📋 **Özet:** {summary}\n\n"
            f"⚡ **Aciliyet:** {urgency.capitalize()}"
        )

        if transcript and len(transcript) < 800:
            text_msg += f"\n\n📝 **Konuşma:**\n```\n{transcript}\n```"

        async with httpx.AsyncClient(timeout=15.0) as client:
            # Metin mesajı gönder
            text_url = f"https://api.telegram.org/bot{token}/sendMessage"
            await client.post(text_url, json={
                "chat_id": chat_id,
                "text": text_msg,
                "parse_mode": "Markdown"
            })
            print(f"[Telegram] Metin mesajı gönderildi.")

            # Ses dosyası varsa gönder
            if audio_path and os.path.exists(audio_path):
                audio_url = f"https://api.telegram.org/bot{token}/sendAudio"
                with open(audio_path, "rb") as f:
                    files = {"audio": (os.path.basename(audio_path), f, "audio/wav")}
                    form = {"chat_id": chat_id, "caption": f"🎙 {caller_name} görüşme kaydı"}
                    await client.post(audio_url, data=form, files=files)
                print(f"[Telegram] Ses dosyası gönderildi: {audio_path}")

        return True

    except Exception as e:
        print(f"[Telegram Hata]: {e}")
        return False


def sync_send_notification(caller_name: str, summary: str, urgency: str,
                           audio_path: str = None, transcript: str = None) -> bool:
    """Senkron wrapper — async olmayan koddan çağırılabilir."""
    return asyncio.run(send_call_notification(
        caller_name, summary, urgency, audio_path, transcript
    ))


async def setup_wizard():
    """Telegram bot kurulum sihirbazı."""
    print("=" * 50)
    print("  TENRA Telegram Bot Kurulumu")
    print("=" * 50)
    print()
    print("Adım 1: Telegram'da @BotFather'a '/newbot' yaz")
    print("         → Token al (örn: 123456789:ABCdefGhi...)")
    print()
    token = input("Token: ").strip()

    print()
    print("Adım 2: Bota bir mesaj gönder (örn: /start)")
    print("         Sonra buraya Enter bas...")
    input()

    # Chat ID'yi otomatik al
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getUpdates")
            data = resp.json()
            updates = data.get("result", [])
            if updates:
                chat_id = str(updates[-1]["message"]["chat"]["id"])
                print(f"✅ Chat ID bulundu: {chat_id}")
            else:
                chat_id = input("Chat ID bulunamadı. Manüel gir: ").strip()
    except Exception as e:
        print(f"Hata: {e}")
        chat_id = input("Chat ID manüel gir: ").strip()

    # Kaydet
    cfg = load_config()
    cfg["telegram_token"] = token
    cfg["telegram_chat_id"] = chat_id
    save_config(cfg)
    print(f"\n✅ Kaydedildi: {CONFIG_PATH}")

    # Test gönder
    print("\nTest mesajı gönderiliyor...")
    ok = await send_call_notification(
        caller_name="Test Arayan",
        summary="Bu bir test mesajıdır. TENRA bağlantısı başarılı!",
        urgency="normal"
    )
    if ok:
        print("✅ Test mesajı gönderildi! Telegram'ı kontrol et.")
    else:
        print("❌ Gönderilemedi. Token ve Chat ID'yi kontrol et.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="TENRA Telegram Notifier")
    parser.add_argument("--setup", action="store_true", help="Kurulum sihirbazını çalıştır")
    parser.add_argument("--test", action="store_true", help="Test mesajı gönder")
    args = parser.parse_args()

    if args.setup:
        asyncio.run(setup_wizard())
    elif args.test:
        ok = sync_send_notification(
            caller_name="Test",
            summary="TENRA bağlantısı test edildi.",
            urgency="normal"
        )
        print("OK" if ok else "HATA")
    else:
        print("Kullanım: python voice_twin/notifier.py --setup")
        print("          python voice_twin/notifier.py --test")

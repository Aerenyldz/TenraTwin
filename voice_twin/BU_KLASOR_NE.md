# Bu klasör: SES İKİZİ MOTORU (voice_twin)

Ahmet’in sesi ve konuşma zekâsı burada (bilgisayarda çalışır).

- `call_agent.py` → Ollama (Hermes) diyalog + özet
- `tts_engine.py` → Fish Audio veya RVC ses
- `rvc_bridge.py` → Applio yerel ses klonu
- `call_logs_db.py` → SQLite yardımcıları
- `sip_gateway.py` → ileride SIP santral
- `cache/` → üretilen WAV önbelleği
- `config.json` → yerel ayarlar (git’e girmez)

Not: Telegram bildirici **kaldırıldı**. Kayıtlar sadece uygulamada.

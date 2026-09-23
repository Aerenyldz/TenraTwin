# TENRA — Klasör Haritası (Neyin Neresi?)

Bu dosya proje kökünde **neyin nerede olduğunu** Türkçe anlatır.
Kod klasörlerinin İngilizce teknik adları Python/Android için korunur; yanında Türkçe anlamı vardır.

---

## Hızlı başlat (tek tık)

| Dosya | Ne yapar? |
|--------|-----------|
| `1_SUNUCUYU_BASLAT.bat` | Ollama + TENRA sunucusunu açar (port 8008) |
| `2_APK_OLUSTUR.bat` | Telefona yüklenecek APK üretir |
| `3_ARAYUZU_YAYINLA.bat` | React arayüzünü derleyip sunucuya verir |
| `app-debug.apk` | Hazır APK — telefona kur / veya `http://192.168.1.100:8008/apk` |

---

## Ana klasörler

| Klasör (diskteki ad) | Türkçe anlamı | İçinde ne var? |
|----------------------|---------------|----------------|
| `server/` | **Sunucu** | FastAPI beyin — `api.py` (port 8008) |
| `voice_twin/` | **Ses ikizi motoru** | Ollama diyalog, Fish/RVC ses, SQLite yardımcıları |
| `tenra-mobile/` | **Mobil uygulama** | React arayüz + Android Java (CallReceiver) |
| `saas_motoru/` | **SaaS / klon üretimi** | İleride başkaları için dijital ikiz boru hattı |
| `arama_kayitlari/` | **Arama kayıtları** | Görüşme WAV + metin arşivi |
| `ses_veriseti/` | **Ses eğitim verisi** | RVC eğitimi için örnek sesler |
| `call_logs.db` | **Veritabanı** | Kaçırılan çağrılar, özetler, durum ayarları (uygulama içi) |

---

## Nerede ne yaşar?

```
TELEFON                          BİLGİSAYAR (senin PC)
────────                         ────────────────────
APK (CallReceiver)      ──HTTP──►  server/api.py :8008
  → aramayı açar                    → Ollama hermes3:8b
  → dinler / konuşur                → Fish Audio veya RVC ses
  → geçmişi gösterir                → call_logs.db (sadece burada)
```

- **Konuşma / özet dışarı gitmez** (Telegram/WhatsApp yok). Hepsi uygulama + `call_logs.db`.
- **Hermes (Ollama)** yerel LLM — ayrı API token gerekmez.
- **Tailscale** sadece ev dışındayken; ev Wi‑Fi’de kapalı olabilir.

---

## Ses modeli (RVC) durumu

Kontrol edildi (2026-09-22):

- `C:\Applio\assets\weights\ahmet_eren_v2.pth` → **VAR** (~53 MB)
- `C:\Applio\assets\weights\ahmet_eren_v2.index` → **VAR** (~126 MB)

Şu an varsayılan ses: **Fish Audio** (hızlı).  
İleride tamamen yerele geçince `voice_twin/config.json` içinde:

```json
"voice_provider": "rvc"
```

---

## Daha fazla teknik detay

→ `MASTER_PROMPT.md` (AI asistanlar için tam manifesto)

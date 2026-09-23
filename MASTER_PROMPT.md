# TENRA (TenraTwin) — MASTER PROJECT PROMPT

> Bu belge, projeye dahil AI asistanına kimlik, mimari, güncel durum ve yol haritasını aktarır.

---

## 1. Kimlik ve amaç

- **Sahip:** Ahmet Eren Yıldız  
- **Ürün:** Kişisel AI ses ikizi + otonom telefon sekreteri  
- **Görev:** Telefon çalınca otomatik aç → rehberden tanı → durum moduna göre Ahmet sesiyle konuş → not/özet → **yalnızca uygulama içi geçmiş + SQLite** (Telegram/WhatsApp/dış bildirim YOK)

---

## 2. Tech stack

| Katman | Teknoloji |
|--------|-----------|
| PC sunucu | Windows 11, Python 3.11, FastAPI `:8008` |
| LLM | Ollama `hermes3:8b` (yerel) — ayrı API token yok |
| TTS şimdi | Fish Audio (birincil) |
| TTS ileride | RVC v2 Applio `ahmet_eren_v2.pth` (**kurulu ve hazır**) |
| DB | `call_logs.db` (çağrılar, özetler, ayarlar) |
| Mobil | React 19 + Vite + Capacitor 8 (`ai.tenra.app`) |
| Native | `CallReceiver`, `GsmDialogueService`, `MainActivity`, `TenraPrefsPlugin` |
| Ağ | Wi‑Fi `192.168.1.100:8008` öncelik; Tailscale yedek (evde zorunlu değil) |

---

## 3. Klasör haritası (Türkçe)

Detay: kökteki **`OKU_BUNA.md`**

| Disk adı | Anlam |
|----------|--------|
| `server/` | Sunucu API |
| `voice_twin/` | Ses ikizi + diyalog motoru |
| `tenra-mobile/` | Mobil uygulama |
| `saas_motoru/` | SaaS klon boru hattı (ileride) |
| `arama_kayitlari/` | Ses/metin arşivi |
| `ses_veriseti/` | Eğitim sesleri |
| `1_SUNUCUYU_BASLAT.bat` | Sunucuyu aç |
| `2_APK_OLUSTUR.bat` | APK üret |
| `3_ARAYUZU_YAYINLA.bat` | UI derle |

---

## 4. Çalışan özellikler (güncel)

1. Donanımsal arama yakalama / açma (TelecomManager + HeadsetHook)  
2. Rehberden isim (`ContactsContract`)  
3. Durum moduna göre Fish/RVC selamlama + hoparlör  
4. APK stabil (splash crash çözüldü)  
5. **Dinamik cevap gecikmesi** (UI → SharedPreferences → CallReceiver)  
6. **Çift ses kilidi** (native mutex)  
7. **Full-duplex diyalog** (`GsmDialogueService` + `/api/gsm/turn` + `/api/gsm/listen`)  
8. Safe-area UI, tek ayarlar sekmesi, 5 sn çevrimdışı rozet  
9. Wi‑Fi öncelik / Tailscale yedek  
10. Kayıtlar **sadece uygulama + DB** — dış mesajlaşma yok  

---

## 5. Bilinen sınırlar

- GSM **uplink’e doğrudan ses basılamaz** → hoparlör yolu (Android kısıtı). **Tenra 2.0 birincil yol: SIP/RTP** (`sip_gateway` + yerel Asterisk lab / NetGSM).  
- GSM `CallReceiver` varsayılan **kapalı** (yönetim APK’sı kalır).  
- Barge-in (söz kesme) henüz cilalı değil.  
- Calendar otomasyonu / SaaS multi-tenant henüz yok.
- Whisper STT: **CPU int8** (RTX 2060 6 GB VRAM → Ollama + RVC).

---

## 6. Yol haritası

### Kısa vade (Faz 1 — şimdi)
- Yerel Asterisk + MicroSIP ile SIP full-duplex lab  
- `SIP_YEREL_TEST.md`  
- GSM auto-answer feature flag  

### Orta vade
- NetGSM SIP trunk bağlama (aynı `sip_gateway`)  
- Barge-in / VAD iyileştirme  
- Fish → **RVC yerel** geçiş (`voice_provider: "rvc"`) — model hazır  
- Google Calendar → otomatik durum modu  

### Stratejik
- SIP/Netgsm hat içi ses production  
- Otonom randevu önerisi  

### Uzun vade
- `saas_motoru/` ile çok kullanıcılı abonelik  

---

## 7. Altın kurallar

1. **Her değişiklikte APK derlenmez.** Beyin PC’de (`server/` + `voice_twin/`). APK yalnız Java/Android değişince.  
2. **Dış bildirim yok** (Telegram/WhatsApp bot ekleme).  
3. **API token katmanı yok** — ev ağı + yerel Hermes.  
4. Açıklamalarda Telefon vs Bilgisayar ayrımını net tut.  
5. İmkânsız Android “hat içi inject” vaat etme; hoparlör veya SIP söyle.

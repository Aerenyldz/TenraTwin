# Tenra 2.0 — Yerel SIP lab (ücretsiz, NetGSM yok)

Bu rehber kulaklarınla duyabileceğin uçtan uca testi anlatır.
Hedef: MicroSIP → Asterisk → Tenra PC → Ahmet sesi (RTP).

## Neden Asterisk?

MicroSIP ve Tenra ikisi de “istemci”. Aralarında bir santral (registrar) olmalı.
Docker’daki Asterisk tam da bu: sıfır ücret, LAN içi.

## Adımlar

### 1) Asterisk’i aç
Proje kökünde (Docker Desktop açık olmalı):

```bat
docker compose -f docker-compose.sip-local.yml up -d
```

Windows’ta port mapping kullanılır (`5060` + RTP `10000-10100`). Container `healthy` ve `pjsip show endpoints` içinde **100 / 101** görünmeli.

### 2) Python bağımlılıkları
```bat
python -m pip install -r server\requirements.txt
```
(`pyVoIP` eklendi.)

### 3) Tenra sunucuyu başlat
```bat
1_SUNUCUYU_BASLAT.bat
```
veya:
```bat
python -m uvicorn server.api:app --host 0.0.0.0 --port 8008
```

### 4) Ayarlar (uygulama veya API)
- Ayarlar → **Yerel lab ayarlarını doldur**
  - Tenra: user `100` / pass `tenra100` / server `127.0.0.1` / bind `5062`
- **SIP Başlat**
- GSM otomatik cevap: **Kapalı** (Tenra 2.0)

### 5) MicroSIP
1. MicroSIP indir, hesap ekle:
   - Account name: TenraTest
   - SIP Server: `127.0.0.1` (veya PC’nin LAN IP’si, örn. `192.168.1.100`)
   - User: `101`
   - Domain: aynı IP
   - Password: `tenra101`
   - Transport: UDP
2. Kayıt olunca yeşil/online olsun.
3. Ara: **100**

### 6) Ne duymalısın?
- MicroSIP’te Ahmet’in selamlaması (RVC/Fish, hat içi RTP)
- Konuş → Whisper (CPU) → Hermes → cevap yine RTP’den
- Geçmiş sekmesinde transcript + ses kaydı

## VRAM notu
- Whisper: **CPU int8** (VRAM 0)
- Ollama Hermes + RVC: **GPU** (RTX 2060)

## Sonra NetGSM
Lab çalışınca Ayarlar’daki `sip_server / user / password` alanlarını NetGSM trunk bilgileriyle değiştir; Asterisk’i kapatabilirsin. Kod yolu aynı.

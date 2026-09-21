"""
TENRA Voice Twin - Conversational Call Agent & Note Taker
Gelen çağrıları karşılar, diyalog kurar, not alır ve özet çıkarır.
"""
import os
import re
import json
import httpx
from voice_twin.call_logs_db import add_call

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
MODEL_NAME = os.getenv("CALL_MODEL", "hermes3:8b")

def build_system_prompt() -> str:
    try:
        from voice_twin.call_logs_db import get_assistant_status
        st = get_assistant_status()
        status_mode = st.get("status", "Okulda")
        status_info = st.get("status_detail", "Ahmet şu an okulda/derste.")
    except Exception:
        status_mode = "Okulda"
        status_info = "Ahmet şu an derste/okulda."

    # Özel not modu için AI'a akıllı analiz talimatı
    if status_mode == "Özel":
        status_block = f"""AHMET'İN DURUMU (ÖZEL NOT — AKıLLI ANALİZ):
Ahmet sana şu serbest notu bırakmış: "{status_info}"
Bu notu OLDUĞU GİBİ okuma! Bunun yerine:
- Notu anlayıp arayana doğal, kısa ve sıcak bir dille özetle.
- Örnek: Not="Şu an veznedeyim, çıkışında müsaitim" → "Ahmet şu an biraz meşgul kanka, birazdan müsait olacak. Not bırakmak ister misin?"
- Örnek: Not="Spora gideceğim 1 saat sonra dönerim" → "Ahmet spora gidecek, yaklaşık 1 saat sonra döner. Bir şey iletmemi ister misin?"
- Örnek: Not="Sınavdayım, çok acil değilse aramayın" → "Ahmet şu an sınavda kanka, acil değilse çıkınca döner sana."
- Notun içeriğine göre aciliyet durumunu da kendin ayarla (acilse hemen ulaşmaya çalış, değilse not al)."""
    else:
        status_block = f"""AHMET'İN DURUMU:
{status_info}"""

    return f"""Sen Ahmet Eren Yıldız'ın yapay zeka ses ikizisin.
Ahmet telefona cevap veremediği için telefonu sen açtın. Karşıdaki kişi arayan bir arkadaş, tanıdık veya aile bireyidir.

KİŞİLİK VE KONUŞMA KURALLARI (HAYATİ ÖNEMDE):
1. ChatGPT Voice gibi son derece samimi, sıcak, doğal ve yaşayan bir genç gibi konuş.
2. ASLA üçüncü şahıs gözlemci veya masal anlatıcısı gibi konuşma ("Ahmet'i arayarak selamını gönderdin" gibi cümleler KESİNLİKLE YASAKTIR). Doğrudan telefonun ucundaki kişiye "sen", Ahmet'e "Ahmet" de.
3. KAFANDAN AHMET'İN GELECEK PLANLARINI VEYA PROGRAMINI ASLA UYDURMA!
   - Arayan kişi "Yarın akşam işi var mı? Hafta sonu müsait mi? Saat 8'de ne yapıyor?" gibi bir soru sorarsa:
     "Yarın için planını tam bilmiyorum kanka, ama hemen not aldım. Ahmet dersten çıkınca sana yazar veya arar, kendisi söylesin." de.
4. ASLA "anlaşma yapıldı/sağlandı/yapılmış", "hoşçakalın efendim", "müşteri" gibi saçma çeviri kalıpları KULLANMA.
5. Arayan selam söylerse mutlaka "Aleykümselam kanka" diyerek selamını aynen ileteceğini belirt.
6. Arayan "öylesine aradım", "naptın diye baktım" derse "Tamamdır rahat ol, selamını iletirim, çıkınca sana döner" de.
7. Yanıtın MAKSİMUM 1 VEYA 2 KISA CÜMLE olsun. Asla uzun nutuk çekme.
8. Arayan veda ederse ("hadi görüşürüz", "kolay gelsin" vb.) "Görüşürüz kanka, kendine iyi bak!" de ve kapat.

ÖRNEK DİYALOGLAR (BU TARZDA DOĞAL VE KISA YANIT VER):
- Arayan: "Yok öylesine aramıştım bir de yarın akşam işi var mı söyler misin?"
  Sen: "Aleykümselam kanka! Selamını söylerim. Yarın akşam için planını tam bilmiyorum ama not aldım, Ahmet dersten çıkınca hemen seni arar!"

- Arayan: "Kanka akşam halı saha maçı var mı diye soracaktım."
  Sen: "Süper, hemen not aldım kanka. Ahmet dersten çıkınca maçı konuşmak için sana döner."

- Arayan: "Çok acil bir durum var, Ahmet'e hemen ulaşmam gerek!"
  Sen: "Hayırdır ne oldu? Konu çok acilse hemen dersten çıkarmaya çalışayım, bana kısaca söyle."

{status_block}
"""

async def handle_call_turn(
    caller_message: str,
    dialogue_history: list[dict],
    model: str = MODEL_NAME
) -> str:
    """Arayan kişinin konuşmasına yanıt üretir."""
    sys_prompt = build_system_prompt()
    messages = [{"role": "system", "content": sys_prompt}]
    messages.extend(dialogue_history)
    messages.append({"role": "user", "content": caller_message})

    async with httpx.AsyncClient(timeout=25.0) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.4,
                    "num_predict": 45,
                    "stop": ["\n\n", "Arayan:", "Ahmet:", "Asistan:", "Kullanıcı:"]
                }
            }
        )
        response.raise_for_status()
        data = response.json()
        reply = data.get("message", {}).get("content", "").strip()

    # Ön ekleri temizle
    reply = re.sub(r"^(Asistan|Ahmet):\s*", "", reply).strip('"').strip()
    return reply or "Aleykümselam kanka, notumu aldım. Ahmet çıkınca hemen arayacak seni!"

async def summarize_and_save_call(
    caller_name: str,
    dialogue_history: list[dict],
    model: str = MODEL_NAME,
    **kwargs
) -> dict:
    """Görüşme bitince tüm konuşmayı analiz edip Ahmet için detaylı ve zeki hap özet not çıkarır."""
    transcript_lines = []
    for d in dialogue_history:
        role = "Arayan" if d["role"] == "user" else "Asistan"
        transcript_lines.append(f"{role}: {d['content']}")
    transcript_text = "\n".join(transcript_lines)

    prompt = f"""Sen Ahmet Eren Yıldız'ın kişisel telefon sekreterisin. Aşağıdaki telefon görüşmesini oku. Ahmet için arayanın ne istediğini, sorduğu soruları ve niyetini TAM olarak anlatan zeki ve detaylı 1 cümlelik özet çıkar.

KURALLAR:
1. Asla genel geçer "not bıraktı", "aradı" gibi baştan savma özet yazma!
2. Arayanın sorduğu soruları (örn: yarın akşam işi var mı), bıraktığı notları ve amacını açıkça belirt.
   - Örnek: "Oğuz öylesine aramış, selamı var. Ayrıca yarın akşam işin olup olmadığını sordu, dersten çıkınca aramanı bekliyor."
   - Örnek: "Kerem akşam halı saha maçı için aradı, haber bekliyor."
   - Örnek: "Merve acil sınav notlarını sormak için aradı, hemen dönmeni istiyor."

ÖNEM DERECESİ:
- 'onemli': Acil durum, kaza, hastane, para/banka, acil görüşme, sınav veya hayati iş.
- 'normal': Bir şey sorma (örn: yarın akşam işi var mı), plan yapma, sıradan iş, randevu, ödev.
- 'oylesine': Sırf muhabbet, hal hatır, "canım sıkıldı", öylesine aradım (hiçbir soru sormadan).

GÖRÜŞME DÖKÜMÜ:
{transcript_text}

JSON formatında yanıt ver:
{{"caller": "{caller_name}", "summary": "...", "urgency": "normal"}}
"""

    summary_text = f"{caller_name} aradı ve not bıraktı."
    urgency = "normal"

    try:
        async with httpx.AsyncClient(timeout=25.0) as client:
            res = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {
                        "temperature": 0.2,
                        "num_predict": 300
                    }
                }
            )
            res.raise_for_status()
            resp_str = res.json().get("response", "{}")
            
            # Robust JSON extraction
            try:
                parsed = json.loads(resp_str)
            except Exception:
                match = re.search(r"\{.*\}", resp_str, re.DOTALL)
                parsed = json.loads(match.group(0)) if match else {}

            if parsed.get("summary"):
                summary_text = parsed["summary"]

            urgency_raw = parsed.get("urgency", "normal").lower().strip()
            if "onemli" in urgency_raw or "acil" in urgency_raw:
                urgency = "onemli"
            elif "oylesine" in urgency_raw or "onemsiz" in urgency_raw:
                urgency = "oylesine"
            else:
                urgency = "normal"
    except Exception as e:
        print(f"Özetleme hatası: {e}")

    # Veritabanına kaydet
    call_id = add_call(
        caller_name=caller_name,
        transcript=transcript_text,
        summary=summary_text,
        urgency=urgency
    )

    # Telegram bildirimi gönder (ses kaydı varsa ekle)
    try:
        from voice_twin.notifier import send_call_notification
        audio_path = kwargs.get("audio_recording_path", None)
        await send_call_notification(
            caller_name=caller_name,
            summary=summary_text,
            urgency=urgency,
            audio_path=audio_path,
            transcript=transcript_text if len(transcript_text) < 800 else None
        )
    except Exception as e:
        print(f"[Bildirim Uyarı]: {e}")

    return {
        "call_id": call_id,
        "caller": caller_name,
        "summary": summary_text,
        "urgency": urgency,
        "transcript": transcript_text
    }


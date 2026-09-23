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

# Durum etiketi → selamlamada üçüncü şahıs konuşma (asla "çalışıyorum" deme)
STATUS_SPOKEN = {
    "Müsait": "müsait",
    "Yemekte": "yemekte",
    "Okulda": "derste",
    "Sporda": "sporda",
    "Toplantıda": "toplantıda",
    "Uykuda": "uyuyor",
    "Trafikte": "trafikte",
    "Dışarıda": "dışarıda",
    "Ders": "ders çalışıyor",
    "Ders Çalışıyorum": "ders çalışıyor",  # eski id uyumu
}


def spoken_status_phrase(status: str) -> str:
    """Selamlama için güvenli üçüncü şahıs durum ifadesi."""
    if not status:
        return "biraz meşgul"
    if status == "Özel":
        return "biraz meşgul"
    return STATUS_SPOKEN.get(status, status.lower().replace("çalışıyorum", "çalışıyor"))


def build_call_greeting(caller_name: str | None, status: str) -> str:
    """Tek tip asistan selamı — her yerde aynı kimlik."""
    who = (caller_name or "").strip()
    phrase = spoken_status_phrase(status)
    if status == "Müsait":
        body = "Ahmet şu an müsait, sizi dinliyorum."
    else:
        body = f"Ahmet şu an {phrase}. Önemli bir şey mi vardı, not almamı ister misin?"
    if who and who not in ("Arayan", "Bilinmeyen", "Bilinmeyen Numara"):
        return f"Selam {who}! Ben Ahmet'in sesli asistanıyım. {body}"
    return f"Selam! Ben Ahmet'in sesli asistanıyım. {body}"


def build_system_prompt() -> str:
    try:
        from voice_twin.call_logs_db import get_assistant_status
        st = get_assistant_status()
        status_mode = st.get("status", "Okulda")
        status_info = st.get("status_detail", "Ahmet şu an okulda/derste.")
    except Exception:
        status_mode = "Okulda"
        status_info = "Ahmet şu an derste/okulda."

    if status_mode == "Özel":
        status_block = f"""AHMET'İN DURUMU (ÖZEL NOT — AKILLI ANALİZ):
Ahmet sana şu serbest notu bırakmış: "{status_info}"
Bu notu OLDUĞU GİBİ okuma! Bunun yerine:
- Notu anlayıp arayana doğal, kısa ve sıcak bir dille üçüncü şahısla özetle (Ahmet ...).
- Örnek: Not="Şu an veznedeyim, çıkışında müsaitim" → "Ahmet şu an biraz meşgul kanka, birazdan müsait olacak. Not bırakmak ister misin?"
- Asla "ben veznedeyim / ders çalışıyorum" deme; sen Ahmet değilsin."""
    else:
        spoken = spoken_status_phrase(status_mode)
        status_block = f"""AHMET'İN DURUMU:
Mod: {status_mode} → konuşurken söyle: "Ahmet şu an {spoken}."
Ek bilgi (istersen kısalt): {status_info}
ASLA birinci şahıs kullanma ("çalışıyorum", "yemekteyim", "toplantıdayım" YASAK)."""

    return f"""Sen Ahmet Eren Yıldız'ın TELEFON SEKRETERİ / sesli asistanısın.
Ahmet telefona bakamadığı için sen açtın. Ses Ahmet'inkine benzer olabilir ama SEN AHMET DEĞİLSİN.

KİMLİK (HAYATİ — İKİ ROLÜ KARIŞTIRMA):
1. Kendini tanıt: "Ahmet'in asistanı / sesli asistanı".
2. Ahmet'ten HER ZAMAN üçüncü şahısla bahset: "Ahmet şu an…", "Ahmet çıkınca…", "ona not bırakayım".
3. ASLA Ahmet gibi konuşma: "ben ders çalışıyorum", "ben yemekteyim", "akşam çalışalım" (sen çalışmayacaksın).
4. Arayan Ahmet'e soru soruyorsa ("ne çalışıyorsun?") → Ahmet adına uydurma; "Tam bilmiyorum kanka, not aldım, Ahmet çıkınca söylesin / arasın" de.

STT / YAZIM HATALARI:
Arayan metni ses tanımasından gelebilir, bozuk yazılabilir ("calısıoyrsun", "berab", "aksam").
Anlamı tahmin et, düzeltip yanıtla. Anlamadıysan tek kısa soru sor; asla alakasız konu uydurma (halı saha, maç vb. yoksa EKLEME).

KONUŞMA KURALLARI:
1. Samimi, kısa, 1–2 cümle. ChatGPT Voice gibi doğal.
2. Selam ("selam", "asalamünaleyküm") YOKsa "Aleykümselam" deme.
3. Ahmet'in gelecek planını uydurma; bilmiyorsan not alıp Ahmet'e bırak.
4. Veda ederse: "Görüşürüz kanka, kendine iyi bak!"

ÖRNEKLER:
- Arayan: "ne konusunu calısıoyrsun aksam calısalım berab"
  Sen: "Konuyu bilmiyorum kanka, not aldım. Ahmet dersi bitirince seni arasın, akşam çalışmayı konuşursunuz."

- Arayan: "Yarın akşam işi var mı?"
  Sen: "Yarın için planını tam bilmiyorum ama not aldım, Ahmet çıkınca sana döner."

- Arayan: "Sadece selam vermek istemiştim."
  Sen: "Tamamdır, selamını iletirim kanka. Kolay gelsin!"

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

    async with httpx.AsyncClient(timeout=45.0) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": messages,
                "stream": False,
                "options": {
                    "temperature": 0.35,
                    "num_predict": 70,
                    "stop": ["\n\n", "Arayan:", "Ahmet:", "Asistan:", "Kullanıcı:"]
                }
            }
        )
        response.raise_for_status()
        data = response.json()
        reply = data.get("message", {}).get("content", "").strip()

    # Ön ekleri temizle
    reply = re.sub(r"^(Asistan|Ahmet):\s*", "", reply).strip('"').strip()
    return reply or "Tamam kanka, notumu aldım. Ahmet çıkınca hemen arayacak seni!"


async def summarize_and_save_call(
    caller_name: str,
    dialogue_history: list[dict],
    model: str = MODEL_NAME,
    **kwargs,
) -> dict:
    """Görüşme bitince özet + aciliyet; DB'ye yazar."""
    transcript_lines = []
    for d in dialogue_history:
        role = "Arayan" if d.get("role") == "user" else "Asistan"
        transcript_lines.append(f"{role}: {d.get('content', '')}")
    transcript_text = "\n".join(transcript_lines)

    prompt = f"""Sen Ahmet Eren Yıldız'ın kişisel telefon sekreterisin. Aşağıdaki görüşmeyi oku.
Ahmet için arayanın ne istediğini TAM anlatan 1 cümlelik özet yaz.

KURALLAR:
1. "not bıraktı / aradı" gibi genel özet YASAK.
2. Soruları ve niyeti açık yaz (örn. akşam birlikte çalışmak istedi).

ÖNEM:
- onemli: acil, para, sağlık, sınav
- normal: plan/soru
- oylesine: sadece selam/muhabbet

GÖRÜŞME:
{transcript_text}

JSON: {{"caller": "{caller_name}", "summary": "...", "urgency": "normal"}}
"""

    summary_text = f"{caller_name} aradı ve not bıraktı."
    urgency = "normal"

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            res = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": model,
                    "prompt": prompt,
                    "stream": False,
                    "format": "json",
                    "options": {"temperature": 0.2, "num_predict": 300},
                },
            )
            res.raise_for_status()
            resp_str = res.json().get("response", "{}")
            try:
                parsed = json.loads(resp_str)
            except Exception:
                match = re.search(r"\{.*\}", resp_str, re.DOTALL)
                parsed = json.loads(match.group(0)) if match else {}

            if parsed.get("summary"):
                summary_text = parsed["summary"]

            urgency_raw = str(parsed.get("urgency", "normal")).lower().strip()
            if "onemli" in urgency_raw or "acil" in urgency_raw:
                urgency = "onemli"
            elif "oylesine" in urgency_raw or "onemsiz" in urgency_raw:
                urgency = "oylesine"
            else:
                urgency = "normal"
    except Exception as e:
        print(f"Özetleme hatası: {e}")

    call_id = add_call(
        caller_name=caller_name,
        transcript=transcript_text,
        summary=summary_text,
        urgency=urgency,
    )

    try:
        from voice_twin.notifier import send_call_notification
        await send_call_notification(
            caller_name=caller_name,
            summary=summary_text,
            urgency=urgency,
            audio_path=kwargs.get("audio_recording_path"),
            transcript=transcript_text if len(transcript_text) < 800 else None,
        )
    except Exception as e:
        print(f"[Bildirim Uyarı]: {e}")

    return {
        "call_id": call_id,
        "caller": caller_name,
        "summary": summary_text,
        "urgency": urgency,
        "transcript": transcript_text,
    }

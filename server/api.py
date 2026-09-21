"""
TENRA Voice Twin - Mobile Companion & RTX 2060 Server API
FastAPI backend for PWA Mobile App, Call Management & Remote Voice Synthesis.
"""
import os
import sys
import glob
import sqlite3
from typing import Optional
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# Path setup
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
sys.path.insert(0, PROJECT_ROOT)

from voice_twin.call_logs_db import (
    get_recent_calls,
    get_assistant_status,
    set_assistant_status,
    delete_call,
    add_call,
    get_setting,
    set_setting,
    get_all_settings,
    init_db
)

app = FastAPI(
    title="TenraTwin Voice Server",
    description="RTX 2060 Server & Mobile Companion Backend",
    version="2.2.0"
)

# CORS middleware for local network & Tailscale
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/app") or request.url.path.startswith("/api"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Ensure DB is initialized
init_db()

# Mobile & PWA Static Files
PWA_DIR = os.path.join(CURRENT_DIR, "pwa")
REACT_DIST = os.path.join(PROJECT_ROOT, "tenra-mobile", "dist")

if os.path.exists(REACT_DIST):
    app.mount("/mobile", StaticFiles(directory=REACT_DIST, html=True), name="mobile")

app.mount("/app", StaticFiles(directory=PWA_DIR, html=True), name="pwa")


@app.get("/")
def root():
    """Redirect root to the modern React Mobile interface if built, else fallback PWA."""
    if os.path.exists(REACT_DIST):
        return RedirectResponse(url="/mobile/")
    return RedirectResponse(url="/app/")


# --- Data Models ---
class StatusUpdate(BaseModel):
    status: str
    status_detail: str

class SynthesisRequest(BaseModel):
    text: str

class ChatMessageRequest(BaseModel):
    caller_name: str = "Arayan"
    message: str
    history: list[dict] = []

class CallStartRequest(BaseModel):
    caller_name: str = "Arayan"

class CallEndRequest(BaseModel):
    caller_name: str = "Arayan"
    history: list[dict] = []
    audio_filenames: list[str] = []

class GSMIncomingRequest(BaseModel):
    caller_number: str = "Bilinmeyen Numara"
    caller_name: Optional[str] = None
    timestamp: Optional[int] = None
    action: str = "answered"


# --- Call Management Endpoints ---
@app.get("/api/calls")
def list_calls(limit: int = 20):
    """Gelen çağrıları, özetleri ve ses kayıt bağlantılarını listeler."""
    try:
        calls = get_recent_calls(limit=limit)
        return calls
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/calls/{call_id}/audio")
def stream_call_audio(call_id: int):
    """Çağrıya ait ses kaydını telefona aktarır (streaming audio)."""
    from voice_twin.call_logs_db import get_connection
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT audio_file FROM call_logs WHERE id = ?", (call_id,))
        row = cursor.fetchone()

    if not row or not row[0]:
        raise HTTPException(status_code=404, detail="Ses kaydı bulunamadı.")

    audio_path = row[0]
    # Eğer göreceli yol ise
    if not os.path.isabs(audio_path):
        audio_path = os.path.join(PROJECT_ROOT, audio_path)

    if not os.path.exists(audio_path):
        raise HTTPException(status_code=404, detail=f"Dosya sunucuda bulunamadı: {os.path.basename(audio_path)}")

    media_type = "audio/mpeg" if audio_path.endswith(".mp3") else "audio/wav"
    return FileResponse(audio_path, media_type=media_type, filename=os.path.basename(audio_path))


@app.delete("/api/calls/{call_id}")
def remove_call(call_id: int):
    """Çağrı kaydını veritabanından siler."""
    success = delete_call(call_id)
    if not success:
        raise HTTPException(status_code=404, detail="Çağrı kaydı bulunamadı.")
    return {"status": "ok", "deleted_id": call_id}


class SettingsUpdate(BaseModel):
    settings: dict


@app.post("/api/gsm/incoming")
async def handle_gsm_incoming(payload: GSMIncomingRequest):
    """Native Android CallReceiver tarafından tetiklenen GSM çağrı bildirimi."""
    import uuid
    from voice_twin.tts_engine import synthesize_speech_async

    caller_id_text = payload.caller_name if (payload.caller_name and payload.caller_name != "Arayan") else payload.caller_number
    if not caller_id_text:
        caller_id_text = "Bilinmeyen Numara"

    # Son test numarasını ve durumunu SQLite'a kaydet
    set_setting("gsm_test_number", payload.caller_number)

    st = get_assistant_status()
    status = st.get("status", "Okulda")
    detail = st.get("status_detail", "Ahmet şu an derste.")
    
    if status == "Müsait":
        greeting = f"Selam {caller_id_text}! Ben Ahmet'in sesli asistanıyım. Ahmet şu an müsait, sizi dinliyorum."
    elif status == "Özel":
        greeting = f"Selam {caller_id_text}! Ben Ahmet'in sesli asistanıyım. Ahmet şu an biraz meşgul. Önemli bir şey mi vardı, not almamı ister misin?"
    else:
        greeting = f"Selam {caller_id_text}! Ben Ahmet'in sesli asistanıyım. Ahmet şu an {status.lower()}. Önemli bir şey mi vardı, not almamı ister misin?"
    
    # DB'ye çağrıyı anında kaydet
    summary_text = f"{caller_id_text} aradı. Telefon otomatik karşılandı ve asistan devreye girdi (Mod: {status})."
    call_id = add_call(
        caller_name=caller_id_text,
        transcript=f"Asistan: {greeting}",
        summary=summary_text,
        urgency="normal"
    )

    # Ses dosyasını üret
    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    audio_filename = f"gsm_greet_{uuid.uuid4().hex[:8]}.wav"
    audio_path = os.path.join(cache_dir, audio_filename)
    audio_url = None
    try:
        await synthesize_speech_async(greeting, audio_path)
        if os.path.exists(audio_path):
            audio_url = f"/api/cache/{audio_filename}"
    except Exception as e:
        print(f"[GSM Ses Sentez Hatası]: {e}")

    print(f"[GSM INCOMING] Arama yakalandı ve DB'ye işlendi: {caller_id_text} (ID: #{call_id})")
    return {
        "status": "ok",
        "call_id": call_id,
        "caller_number": payload.caller_number,
        "caller_name": caller_id_text,
        "greeting": greeting,
        "audio_url": audio_url,
        "audio_filename": audio_filename,
        "message": f"GSM araması başarıyla DB'ye kaydedildi (Kayıt No: #{call_id})"
    }


# --- VoIP & SIP Gateway Endpoints ---
class VoIPConfigUpdate(BaseModel):
    sip_server: Optional[str] = None
    sip_port: Optional[int] = 5060
    sip_user: Optional[str] = None
    sip_password: Optional[str] = None
    sip_my_ip: Optional[str] = "0.0.0.0"
    sip_auto_start: Optional[bool] = False

@app.get("/api/voip/config")
def get_voip_config():
    """SIP / VoIP santral yapılandırmasını ve durumunu döndürür."""
    from voice_twin.sip_gateway import sip_gateway
    return sip_gateway.get_config()

@app.post("/api/voip/config")
def save_voip_config(payload: VoIPConfigUpdate):
    """SIP / VoIP santral yapılandırmasını kaydeder."""
    from voice_twin.sip_gateway import sip_gateway
    sip_gateway.save_config(payload.dict(exclude_unset=True))
    return {"status": "ok", "config": sip_gateway.get_config()}

@app.post("/api/voip/start")
def start_voip_gateway():
    """SIP Gateway motorunu başlatır."""
    from voice_twin.sip_gateway import sip_gateway
    return sip_gateway.start()

@app.post("/api/voip/stop")
def stop_voip_gateway():
    """SIP Gateway motorunu durdurur."""
    from voice_twin.sip_gateway import sip_gateway
    return sip_gateway.stop()

@app.api_route("/api/voip/webhook", methods=["GET", "POST"])
async def voip_cloud_webhook(request: Request):
    """
    Bulut VoIP Operatörleri (Twilio Voice, NetGSM, Bulutfon, Zadarma) için Webhook.
    Arama geldiğinde Ahmet'in sesli selamlama sesini oynatır ve karşı tarafın sesini dinler.
    """
    import uuid
    from voice_twin.tts_engine import synthesize_speech_async
    
    # Form data veya JSON oku
    caller_id = "Bilinmeyen Numara"
    try:
        form = await request.form()
        caller_id = form.get("From") or form.get("caller") or "Bilinmeyen Numara"
    except Exception:
        try:
            body = await request.json()
            caller_id = body.get("From") or body.get("caller") or "Bilinmeyen Numara"
        except Exception:
            pass

    st = get_assistant_status()
    status = st.get("status", "Okulda")
    if status == "Müsait":
        greeting = f"Selam! Ben Ahmet'in sesli asistanıyım. Ahmet şu an müsait, sizi dinliyorum."
    elif status == "Özel":
        greeting = f"Selam! Ben Ahmet'in sesli asistanıyım. Ahmet şu an biraz meşgul. Önemli bir şey mi vardı, not almamı ister misin?"
    else:
        greeting = f"Selam! Ben Ahmet'in sesli asistanıyım. Ahmet şu an {status.lower()}. Önemli bir şey mi vardı, not almamı ister misin?"

    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    audio_filename = f"voip_greet_{uuid.uuid4().hex[:8]}.wav"
    audio_path = os.path.join(cache_dir, audio_filename)
    audio_url = None
    try:
        await synthesize_speech_async(greeting, audio_path)
        if os.path.exists(audio_path):
            audio_url = f"/api/cache/{audio_filename}"
    except Exception as e:
        print(f"[VoIP Webhook Ses Hatası]: {e}")

    # Standard TwiML / Voice XML veya JSON yanıtı
    host_url = str(request.base_url).rstrip("/")
    full_audio_url = f"{host_url}{audio_url}" if audio_url else ""

    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {"<Play>" + full_audio_url + "</Play>" if full_audio_url else "<Say language='tr-TR'>" + greeting + "</Say>"}
    <Gather input="speech" action="/api/voip/gather" language="tr-TR" timeout="5" speechTimeout="auto">
        <Say language="tr-TR">Sizi dinliyorum, mesajınızı söyleyebilirsiniz.</Say>
    </Gather>
</Response>"""
    return Response(content=xml_content, media_type="application/xml")


# --- Settings Storage Endpoints ---
@app.get("/api/settings")
def get_settings():
    """Tüm sunucu ve asistan ayarlarını döndürür."""
    return get_all_settings()


@app.post("/api/settings")
def save_settings(payload: SettingsUpdate):
    """Ayarları veritabanına kaydeder."""
    for k, v in payload.settings.items():
        set_setting(k, str(v))
    return {"status": "ok", "settings": get_all_settings()}


# --- Assistant Status Endpoints ---
@app.get("/api/status")
def get_status():
    """Mevcut asistan çağrı modunu getirir."""
    return get_assistant_status()



@app.post("/api/status")
def update_status(payload: StatusUpdate):
    """Asistan modunu günceller (Okulda, Sporda vs.)."""
    set_assistant_status(payload.status, payload.status_detail)
    return {"status": "ok", "updated": payload.dict()}


# --- Live Voice Synthesis Endpoint ---
@app.post("/api/synthesize")
async def synthesize_text(payload: SynthesisRequest):
    """Metni Ahmet Eren'in ses klonuyla anında seslendirip WAV olarak telefona döndürür."""
    if not payload.text.strip():
        raise HTTPException(status_code=400, detail="Metin boş olamaz.")

    try:
        from voice_twin.tts_engine import synthesize_speech_async
        cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
        os.makedirs(cache_dir, exist_ok=True)
        out_wav = os.path.join(cache_dir, f"pwa_test_{abs(hash(payload.text)) % 1000000}.wav")

        result_path = await synthesize_speech_async(payload.text, out_wav)
        if os.path.exists(result_path):
            return FileResponse(result_path, media_type="audio/wav", filename="ahmet_voice.wav")
        else:
            raise HTTPException(status_code=500, detail="Ses dosyası üretilemedi.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# --- Two-Way Interactive Call Endpoints ---
@app.get("/api/cache/{filename}")
def get_cached_audio(filename: str):
    """Sentezlenen sesleri tarayıcıya/telefona anında dinletmek için sunar."""
    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    file_path = os.path.join(cache_dir, filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Ses bulunamadı.")
    media_type = "audio/wav" if filename.endswith(".wav") else "audio/mpeg"
    return FileResponse(file_path, media_type=media_type)


@app.post("/api/call/start")
async def start_call(payload: CallStartRequest):
    """Yeni bir interaktif çağrı başlatır; Ahmet'in asistanı açılış selamını ve sesini üretir."""
    import uuid
    from voice_twin.tts_engine import synthesize_speech_async
    from voice_twin.call_logs_db import get_assistant_status

    st = get_assistant_status()
    status = st.get("status", "Okulda")
    detail = st.get("status_detail", "Ahmet şu an derste.")
    
    status_lower = status.lower()
    if status == "Müsait":
        greeting = f"Selam {payload.caller_name}! Ben Ahmet'in sesli asistanıyım. Ahmet şu an müsait, sizi dinliyorum."
    elif status == "Özel":
        # Özel mod: AI detayı doğal şekilde özetler, olduğu gibi okumaz
        greeting = f"Selam {payload.caller_name}! Ben Ahmet'in sesli asistanıyım. Ahmet şu an biraz meşgul. Önemli bir şey mi vardı, not almamı ister misin?"
    else:
        greeting = f"Selam {payload.caller_name}! Ben Ahmet'in sesli asistanıyım. Ahmet şu an {status_lower}. Önemli bir şey mi vardı, not almamı ister misin?"
    
    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    audio_filename = f"call_greet_{uuid.uuid4().hex[:8]}.wav"
    audio_path = os.path.join(cache_dir, audio_filename)
    
    audio_url = None
    try:
        await synthesize_speech_async(greeting, audio_path)
        if os.path.exists(audio_path):
            audio_url = f"/api/cache/{audio_filename}"
    except Exception as e:
        print(f"[Ses Hatası - Selamlama]: {e}")
        audio_filename = None

    return {
        "greeting": greeting,
        "audio_url": audio_url,
        "audio_filename": audio_filename
    }


@app.post("/api/call/message")
async def handle_call_message(payload: ChatMessageRequest):
    """Kullanıcının yazdığı veya konuştuğu mesaja Ollama + Fish Audio ile iki taraflı yanıt verir."""
    import uuid
    from voice_twin.call_agent import handle_call_turn
    from voice_twin.tts_engine import synthesize_speech_async

    reply = await handle_call_turn(payload.message, payload.history)
    
    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    audio_filename = f"call_reply_{uuid.uuid4().hex[:8]}.wav"
    audio_path = os.path.join(cache_dir, audio_filename)
    
    audio_url = None
    try:
        await synthesize_speech_async(reply, audio_path)
        if os.path.exists(audio_path):
            audio_url = f"/api/cache/{audio_filename}"
    except Exception as e:
        print(f"[Ses Hatası - Yanıt]: {e}")
        audio_filename = None

    return {
        "reply": reply,
        "audio_url": audio_url,
        "audio_filename": audio_filename
    }


@app.post("/api/call/end")
async def end_call(payload: CallEndRequest):
    """Görüşmeyi sonlandırır; konuşmayı özetler, call_logs.db'ye ve ses arşivine işler."""
    from voice_twin.call_agent import summarize_and_save_call
    from voice_twin.call_recorder import save_call_recording
    from voice_twin.call_logs_db import update_call_audio

    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    audio_clips = [os.path.join(cache_dir, f) for f in payload.audio_filenames if os.path.exists(os.path.join(cache_dir, f))]

    summary_data = await summarize_and_save_call(payload.caller_name, payload.history)
    
    saved_record = save_call_recording(
        caller_name=payload.caller_name,
        transcript=summary_data.get("transcript", ""),
        summary=summary_data.get("summary", ""),
        audio_clips=audio_clips
    )
    
    if summary_data.get("call_id") and saved_record:
        update_call_audio(summary_data["call_id"], saved_record)

    return {
        "status": "ok",
        "call_id": summary_data.get("call_id"),
        "summary": summary_data.get("summary"),
        "urgency": summary_data.get("urgency"),
        "saved_record": saved_record
    }


# --- System & Hardware Endpoint ---
@app.get("/api/system")
def get_system_stats():
    """Sunucu donanım ve model durumunu raporlar."""
    gpu_name = "NVIDIA GeForce RTX 5060"
    try:
        import subprocess
        res = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True, text=True, timeout=2
        )
        if res.returncode == 0 and res.stdout.strip():
            gpu_name = res.stdout.strip().split("\n")[0]
    except Exception:
        try:
            import torch
            if torch.cuda.is_available():
                gpu_name = torch.cuda.get_device_name(0)
        except Exception:
            pass

    # Aktif ses modeli kontrolü
    from voice_twin.tts_engine import load_config
    cfg = load_config()
    provider = cfg.get("voice_provider", "fish_audio")
    if provider == "fish_audio":
        model_name = "Fish Audio (Genç Ahmet)"
    else:
        from voice_twin.rvc_bridge import get_latest_model
        model_pth = get_latest_model()
        model_name = os.path.basename(model_pth) if model_pth else "ahmet_eren.pth"

    # Toplam çağrı sayısı
    from voice_twin.call_logs_db import get_connection
    total_calls = 0
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT count(*) FROM call_logs")
        total_calls = cursor.fetchone()[0]

    return {
        "gpu_name": gpu_name,
        "active_voice_model": model_name,
        "llm_model": os.getenv("CALL_MODEL", "hermes3:8b"),
        "total_calls": total_calls,
        "server_status": "online"
    }


if __name__ == "__main__":
    import uvicorn
    # 0.0.0.0 ile yerel ağdaki telefonlardan da erişilebilir kılınır
    print("🚀 TENRA Server Başlatılıyor: http://0.0.0.0:8000/app/")
    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=False)

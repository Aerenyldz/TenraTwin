"""
TENRA Voice Twin - Mobile Companion & RTX Server API
FastAPI backend for PWA Mobile App, Call Management & Remote Voice Synthesis.
"""
import os
import sys
import glob
import sqlite3
import asyncio
from typing import Optional
from contextlib import asynccontextmanager
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
    init_db,
    append_call_transcript,
    update_call_audio,
    update_call_record,
)

# call_id → o aramaya ait ses klipleri (selamlama + utterance + cevap)
_GSM_CLIPS: dict[int, list[str]] = {}


def _gsm_add_clip(call_id: Optional[int], path: str):
    if not call_id or not path:
        return
    _GSM_CLIPS.setdefault(int(call_id), [])
    if path not in _GSM_CLIPS[int(call_id)]:
        _GSM_CLIPS[int(call_id)].append(path)


@asynccontextmanager
async def _lifespan(app: FastAPI):
    # SIP auto-start (lab / NetGSM)
    try:
        from voice_twin.sip_gateway import sip_gateway
        if sip_gateway.get_config().get("sip_auto_start"):
            print("[SIP] auto_start açık — gateway başlatılıyor...")
            print("[SIP]", sip_gateway.start())
    except Exception as e:
        print(f"[SIP] auto_start atlandı: {e}")
    yield
    try:
        from voice_twin.sip_gateway import sip_gateway
        if sip_gateway.is_running:
            sip_gateway.stop()
    except Exception:
        pass


app = FastAPI(
    title="TenraTwin Voice Server",
    description="RTX Server & Mobile Companion Backend",
    version="2.2.0",
    lifespan=_lifespan,
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


@app.api_route("/", methods=["GET", "HEAD"])
def root():
    """Redirect root to the modern React Mobile interface if built, else fallback PWA."""
    if os.path.exists(REACT_DIST):
        return RedirectResponse(url="/mobile/")
    return RedirectResponse(url="/app/")


@app.api_route("/health", methods=["GET", "HEAD"])
def health():
    """Cloudflare, Uptime robot ve monitörler için sağlık kontrolü."""
    return {"status": "ok", "server": "TenraTwin"}


@app.api_route("/apk", methods=["GET", "HEAD"])
def download_apk():
    """Telefondan doğrudan güncel Android APK'sını indirme bağlantısı."""
    apk_path = os.path.join(PROJECT_ROOT, "app-debug.apk")
    if not os.path.exists(apk_path):
        apk_path = os.path.join(PROJECT_ROOT, "tenra-mobile", "android", "app", "build", "outputs", "apk", "debug", "app-debug.apk")
    if not os.path.exists(apk_path):
        raise HTTPException(status_code=404, detail="APK dosyası bulunamadı.")
    return FileResponse(
        apk_path,
        media_type="application/vnd.android.package-archive",
        filename="TenraTwin.apk"
    )


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
        init_db()
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

    # Selamlamada ham numara / "bilinmeyen" okunmasın — rehber ismi varsa kullan
    display_name = None
    cn = (caller_id_text or "").strip()
    if cn and cn not in ("Bilinmeyen Numara", "Bilinmeyen", "Arayan", "Unknown"):
        # Sadece rakam/işaretten oluşuyorsa isim sayma
        if any(ch.isalpha() for ch in cn):
            display_name = cn

    st = get_assistant_status()
    status = st.get("status", "Okulda")
    detail = st.get("status_detail", "Ahmet şu an derste.")

    from voice_twin.call_agent import build_call_greeting
    greeting = build_call_greeting(display_name, status)

    db_name = display_name or cn or "Bilinmeyen Numara"

    # Son test numarasını kaydet
    set_setting("gsm_test_number", payload.caller_number or "")

    summary_text = f"{db_name} aradı. Telefon otomatik karşılandı ve asistan devreye girdi (Mod: {status})."
    call_id = add_call(
        caller_name=db_name,
        transcript=f"Asistan: {greeting}",
        summary=summary_text,
        urgency="normal"
    )

    # Ses dosyasını üret veya önbellekten anında al (0ms gecikme)
    import hashlib
    greet_hash = hashlib.md5(greeting.encode('utf-8')).hexdigest()[:10]
    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    audio_filename = f"gsm_greet_{greet_hash}.wav"
    audio_path = os.path.join(cache_dir, audio_filename)
    audio_url = None

    if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
        audio_url = f"/api/cache/{audio_filename}"
        print(f"[GSM INCOMING] Önbellekten anında ses getirildi (0ms): {audio_filename}")
    else:
        try:
            await synthesize_speech_async(greeting, audio_path)
            if os.path.exists(audio_path):
                audio_url = f"/api/cache/{audio_filename}"
        except Exception as e:
            print(f"[GSM Ses Sentez Hatası]: {e}")

    if call_id and os.path.exists(audio_path):
        _gsm_add_clip(call_id, audio_path)

    print(f"[GSM INCOMING] Arama yakalandı: {db_name} (ID: #{call_id})")
    return {
        "status": "ok",
        "call_id": call_id,
        "caller_number": payload.caller_number,
        "caller_name": db_name,
        "greeting": greeting,
        "audio_url": audio_url,
        "audio_filename": audio_filename,
        "message": f"GSM araması başarıyla DB'ye kaydedildi (Kayıt No: #{call_id})"
    }


class GSMTurnRequest(BaseModel):
    """Walkthrough Adım 3: GSM full-duplex turu (STT metni veya ham not)."""
    caller_name: str = "Arayan"
    message: str
    history: list[dict] = []
    call_id: Optional[int] = None


async def _gsm_produce_reply(caller_name: str, message: str, history: list, call_id: Optional[int]):
    """Ortak GSM tur üretimi: LLM + TTS + DB transcript."""
    import uuid
    from voice_twin.call_agent import handle_call_turn
    from voice_twin.tts_engine import synthesize_speech_async

    reply = await handle_call_turn(message, history or [])

    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    audio_filename = f"gsm_turn_{uuid.uuid4().hex[:8]}.wav"
    audio_path = os.path.join(cache_dir, audio_filename)
    audio_url = None
    try:
        await synthesize_speech_async(reply, audio_path)
        if os.path.exists(audio_path):
            audio_url = f"/api/cache/{audio_filename}"
            _gsm_add_clip(call_id, audio_path)
    except Exception as e:
        print(f"[GSM Turn Ses Hatası]: {e}")

    turn_block = f"Arayan: {message}\nAsistan: {reply}"
    if call_id:
        try:
            append_call_transcript(
                call_id,
                turn_block,
                summary=f"{caller_name}: {message[:80]}"
            )
        except Exception as e:
            print(f"[GSM Turn DB Uyarı]: {e}")

    return {
        "reply": reply,
        "transcript": message,
        "audio_url": audio_url,
        "audio_filename": audio_filename,
        "call_id": call_id,
    }


@app.post("/api/gsm/turn")
async def handle_gsm_turn(payload: GSMTurnRequest):
    """
    Native taraf STT metni ürettikten sonra bu endpoint'e gönderir.
    Ollama yanıt + TTS WAV URL döner.
    """
    if not payload.message.strip():
        raise HTTPException(status_code=400, detail="Mesaj boş olamaz.")
    return await _gsm_produce_reply(
        payload.caller_name, payload.message.strip(), payload.history, payload.call_id
    )


@app.post("/api/gsm/listen")
async def handle_gsm_listen(request: Request):
    """
    Native AudioRecord WAV yükler → Whisper STT → LLM → TTS.
    multipart: audio (file), caller_name, history (JSON string), call_id
    """
    import json as _json
    import uuid as _uuid

    form = await request.form()
    audio = form.get("audio")
    if audio is None or not hasattr(audio, "read"):
        raise HTTPException(status_code=400, detail="audio dosyası gerekli")

    caller_name = str(form.get("caller_name") or "Arayan")
    history_raw = str(form.get("history") or "[]")
    call_id_raw = form.get("call_id")
    call_id = None
    try:
        if call_id_raw not in (None, "", "null"):
            call_id = int(call_id_raw)
    except Exception:
        call_id = None

    try:
        history = _json.loads(history_raw)
        if not isinstance(history, list):
            history = []
    except Exception:
        history = []

    raw = await audio.read()
    if not raw or len(raw) < 500:
        raise HTTPException(status_code=400, detail="Ses çok kısa veya boş")

    # Kalıcı utterance arşivi (geçmiş + birleşik kayıt için)
    archive_dir = os.path.join(PROJECT_ROOT, "arama_kayitlari", "utterances")
    os.makedirs(archive_dir, exist_ok=True)
    utt_name = f"utt_{call_id or 0}_{_uuid.uuid4().hex[:8]}.wav"
    utt_path = os.path.join(archive_dir, utt_name)
    with open(utt_path, "wb") as f:
        f.write(raw)
    _gsm_add_clip(call_id, utt_path)

    try:
        from voice_twin.pipeline import transcribe_wav
        text = await asyncio.to_thread(transcribe_wav, utt_path, "tr", soft_vad=True)
    except Exception as e:
        print(f"[GSM Listen STT Hatası]: {e}")
        text = ""

    print(f"[GSM Listen] call=#{call_id} bytes={len(raw)} text={text!r}")

    if not (text or "").strip():
        # Sessiz döngü yerine kısa "duyamadım" — diyalog canlı kalsın
        from voice_twin.tts_engine import synthesize_speech_async
        retry = "Sesini net alamadım, tekrar eder misin?"
        cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
        os.makedirs(cache_dir, exist_ok=True)
        audio_filename = f"gsm_retry_{_uuid.uuid4().hex[:8]}.wav"
        audio_path = os.path.join(cache_dir, audio_filename)
        audio_url = None
        try:
            await synthesize_speech_async(retry, audio_path)
            if os.path.exists(audio_path):
                audio_url = f"/api/cache/{audio_filename}"
                _gsm_add_clip(call_id, audio_path)
        except Exception as e:
            print(f"[GSM Retry TTS]: {e}")
        return {
            "reply": retry,
            "transcript": "",
            "audio_url": audio_url,
            "audio_filename": audio_filename,
            "call_id": call_id,
            "error": "empty_transcript",
            "message": "Ses anlaşılamadı, tekrar isteniyor.",
        }

    result = await _gsm_produce_reply(caller_name, text.strip(), history, call_id)
    result["transcript"] = text.strip()
    return result


class GSMEndRequest(BaseModel):
    caller_name: str = "Arayan"
    history: list[dict] = []
    call_id: Optional[int] = None


@app.post("/api/gsm/end")
async def handle_gsm_end(payload: GSMEndRequest):
    """
    GSM diyalog bitti: mevcut call_id satırını günceller, ses arşivler.
    """
    from voice_twin.call_agent import summarize_and_save_call
    from voice_twin.call_recorder import save_call_recording

    summary = f"{payload.caller_name} GSM çağrısı sonlandı."
    urgency = "normal"
    call_id = payload.call_id
    transcript = ""

    if payload.history:
        summary_data = await summarize_and_save_call(
            payload.caller_name,
            payload.history,
            call_id=call_id,
        )
        call_id = summary_data.get("call_id") or call_id
        summary = summary_data.get("summary") or summary
        urgency = summary_data.get("urgency") or urgency
        transcript = summary_data.get("transcript") or ""
    elif call_id:
        try:
            calls = get_recent_calls(limit=50)
            row = next((c for c in calls if c["id"] == call_id), None)
            if row:
                summary = row.get("summary") or summary
                urgency = row.get("urgency") or urgency
                transcript = row.get("transcript") or ""
                update_call_record(call_id, summary=summary, urgency=urgency)
        except Exception as e:
            print(f"[GSM End]: {e}")

    # Birleşik ses kaydı
    clips = list(_GSM_CLIPS.pop(int(call_id), [])) if call_id else []
    saved_record = ""
    if call_id:
        try:
            saved_record = save_call_recording(
                payload.caller_name,
                transcript,
                summary,
                clips,
            )
            if saved_record and os.path.isfile(saved_record) and saved_record.lower().endswith((".wav", ".mp3", ".m4a")):
                update_call_audio(call_id, saved_record)
            print(f"[GSM End] call=#{call_id} clips={len(clips)} audio={saved_record}")
        except Exception as e:
            print(f"[GSM End kayıt]: {e}")

    return {
        "status": "ok",
        "call_id": call_id,
        "summary": summary,
        "urgency": urgency,
        "saved_record": saved_record,
    }


# --- VoIP & SIP Gateway Endpoints ---
class VoIPConfigUpdate(BaseModel):
    sip_server: Optional[str] = None
    sip_port: Optional[int] = 5060
    sip_user: Optional[str] = None
    sip_password: Optional[str] = None
    sip_my_ip: Optional[str] = "127.0.0.1"
    sip_bind_port: Optional[int] = 5062
    sip_auto_start: Optional[bool] = False
    gsm_auto_answer: Optional[bool] = False


@app.get("/api/voip/config")
def get_voip_config():
    """SIP / VoIP santral yapılandırmasını ve durumunu döndürür."""
    from voice_twin.sip_gateway import sip_gateway
    return sip_gateway.get_config()


@app.post("/api/voip/config")
def save_voip_config(payload: VoIPConfigUpdate):
    """SIP / VoIP santral yapılandırmasını kaydeder."""
    from voice_twin.sip_gateway import sip_gateway
    sip_gateway.save_config(payload.model_dump(exclude_unset=True))
    return {"status": "ok", "config": sip_gateway.get_config()}


@app.post("/api/voip/local-lab")
def apply_voip_local_lab():
    """MicroSIP + yerel Asterisk için hazır lab ayarlarını yazar (ücretli hat yok)."""
    from voice_twin.sip_gateway import sip_gateway
    sip_gateway.apply_local_lab_defaults()
    return {
        "status": "ok",
        "message": "Yerel lab ayarları uygulandı (100@127.0.0.1 / MicroSIP: 101).",
        "config": sip_gateway.get_config(),
    }


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
    from voice_twin.call_agent import build_call_greeting
    greeting = build_call_greeting(None, status)

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


@app.api_route("/api/voip/gather", methods=["GET", "POST"])
async def voip_gather_handler(request: Request):
    """
    Twilio/NetGSM Gather callback: arayanın konuşmasını alır, LLM yanıtlar, ses oynatır.
    """
    import uuid
    from voice_twin.call_agent import handle_call_turn
    from voice_twin.tts_engine import synthesize_speech_async

    speech_text = ""
    caller_id = "Arayan"
    try:
        form = await request.form()
        speech_text = (
            form.get("SpeechResult")
            or form.get("UnstableSpeechResult")
            or form.get("Digits")
            or ""
        )
        caller_id = form.get("From") or form.get("caller") or "Arayan"
    except Exception:
        try:
            body = await request.json()
            speech_text = body.get("SpeechResult") or body.get("message") or ""
            caller_id = body.get("From") or body.get("caller") or "Arayan"
        except Exception:
            pass

    speech_text = str(speech_text).strip()
    if not speech_text:
        xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Gather input="speech" action="/api/voip/gather" language="tr-TR" timeout="5" speechTimeout="auto">
        <Say language="tr-TR">Sizi duyamadım, tekrar söyler misiniz?</Say>
    </Gather>
</Response>"""
        return Response(content=xml_content, media_type="application/xml")

    try:
        reply = await handle_call_turn(speech_text, [])
    except Exception as e:
        print(f"[VoIP Gather LLM Hatası]: {e}")
        reply = "Anladım, notumu aldım. Ahmet çıkınca sana döner."

    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    audio_filename = f"voip_reply_{uuid.uuid4().hex[:8]}.wav"
    audio_path = os.path.join(cache_dir, audio_filename)
    audio_url = None
    try:
        await synthesize_speech_async(reply, audio_path)
        if os.path.exists(audio_path):
            audio_url = f"/api/cache/{audio_filename}"
    except Exception as e:
        print(f"[VoIP Gather Ses Hatası]: {e}")

    host_url = str(request.base_url).rstrip("/")
    full_audio_url = f"{host_url}{audio_url}" if audio_url else ""

    # Görüşmeyi hafifçe DB'ye düş (tek tur webhook özeti)
    try:
        add_call(
            caller_name=str(caller_id),
            transcript=f"Arayan: {speech_text}\nAsistan: {reply}",
            summary=f"{caller_id} VoIP ile aradı: {speech_text[:120]}",
            urgency="normal"
        )
    except Exception as e:
        print(f"[VoIP Gather DB Uyarı]: {e}")

    play_or_say = (
        f"<Play>{full_audio_url}</Play>"
        if full_audio_url
        else f"<Say language='tr-TR'>{reply}</Say>"
    )
    xml_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    {play_or_say}
    <Gather input="speech" action="/api/voip/gather" language="tr-TR" timeout="5" speechTimeout="auto">
        <Say language="tr-TR">Başka bir şey eklemek ister misiniz?</Say>
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
    return {"status": "ok", "updated": payload.model_dump()}


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
    # Path traversal engeli: sadece dosya adı, üst dizin yok
    safe_name = os.path.basename(filename or "")
    if not safe_name or safe_name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Geçersiz dosya adı.")
    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    file_path = os.path.abspath(os.path.join(cache_dir, safe_name))
    if not file_path.startswith(os.path.abspath(cache_dir) + os.sep):
        raise HTTPException(status_code=400, detail="Geçersiz dosya yolu.")
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Ses bulunamadı.")
    media_type = "audio/wav" if safe_name.endswith(".wav") else "audio/mpeg"
    return FileResponse(file_path, media_type=media_type)


@app.post("/api/call/start")
async def start_call(payload: CallStartRequest):
    """Yeni bir interaktif çağrı başlatır; Ahmet'in asistanı açılış selamını ve sesini üretir."""
    import uuid
    from voice_twin.tts_engine import synthesize_speech_async
    from voice_twin.call_logs_db import get_assistant_status
    from voice_twin.call_agent import build_call_greeting

    st = get_assistant_status()
    status = st.get("status", "Okulda")
    greeting = build_call_greeting(payload.caller_name, status)
    
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


@app.post("/api/call/transcribe")
async def call_transcribe(request: Request):
    """Canlı arama mikrofonu: MediaRecorder blob → Whisper STT → metin."""
    import uuid as _uuid

    form = await request.form()
    audio = form.get("audio")
    if audio is None or not hasattr(audio, "read"):
        raise HTTPException(status_code=400, detail="audio dosyası gerekli")

    raw = await audio.read()
    if not raw or len(raw) < 200:
        raise HTTPException(status_code=400, detail="Ses çok kısa veya boş")

    orig_name = str(getattr(audio, "filename", "") or "clip.webm")
    ext = os.path.splitext(orig_name)[1].lower()
    if ext not in (".wav", ".webm", ".ogg", ".mp3", ".m4a", ".mp4", ".mpeg"):
        # MIME'dan tahmin
        ctype = str(getattr(audio, "content_type", "") or "")
        if "wav" in ctype:
            ext = ".wav"
        elif "ogg" in ctype:
            ext = ".ogg"
        else:
            ext = ".webm"

    cache_dir = os.path.join(PROJECT_ROOT, "voice_twin", "cache")
    os.makedirs(cache_dir, exist_ok=True)
    audio_path = os.path.join(cache_dir, f"live_mic_{_uuid.uuid4().hex[:10]}{ext}")
    with open(audio_path, "wb") as f:
        f.write(raw)

    # webm/ogg → wav (ffmpeg varsa); yoksa doğrudan Whisper dener
    wav_path = audio_path
    if ext != ".wav":
        try:
            import subprocess
            cand = audio_path.rsplit(".", 1)[0] + ".wav"
            subprocess.run(
                ["ffmpeg", "-y", "-i", audio_path, "-ar", "16000", "-ac", "1", cand],
                check=True,
                capture_output=True,
                timeout=30,
            )
            if os.path.exists(cand) and os.path.getsize(cand) > 100:
                wav_path = cand
        except Exception as e:
            print(f"[Transcribe ffmpeg]: {e} — ham dosya ile denenecek")

    try:
        from voice_twin.pipeline import transcribe_wav
        text = await asyncio.to_thread(transcribe_wav, wav_path, "tr", soft_vad=False)
    except Exception as e:
        print(f"[Call Transcribe STT]: {e}")
        raise HTTPException(status_code=500, detail=f"STT hatası: {e}")

    print(f"[Call Transcribe] bytes={len(raw)} text={text!r}")
    return {"text": (text or "").strip()}


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
    # Not: baslat_tenra.bat / mobil istemciler 8008 kullanır
    print("🚀 TENRA Server Başlatılıyor: http://0.0.0.0:8008/")
    uvicorn.run("api:app", host="0.0.0.0", port=8008, reload=False)

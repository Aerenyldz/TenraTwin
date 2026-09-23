import React, { useState, useEffect, useRef } from 'react';
import { Phone, PhoneOff, Mic, MicOff, Send, Volume2, Sparkles, Clock, Zap } from 'lucide-react';
import { startCall, sendCallMessage, endCall, formatAudioUrl, notifyGsmIncoming, transcribeCallAudio } from '../api';
import type { DialogueMessage } from '../types';
import { isNativeAudioLocked, onGsmHandled } from '../nativePrefs';

interface LiveCallBridgeProps {
  onCallEnded?: () => void;
}

export const LiveCallBridge: React.FC<LiveCallBridgeProps> = ({ onCallEnded }) => {
  const [callerName, setCallerName] = useState('Oğuz');
  const [isCalling, setIsCalling] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [inputText, setInputText] = useState('');
  const [dialogue, setDialogue] = useState<DialogueMessage[]>([]);
  const [audioClips, setAudioClips] = useState<string[]>([]);
  const [callDuration, setCallDuration] = useState(0);
  const [isListening, setIsListening] = useState(false);
  const [micHint, setMicHint] = useState<string | null>(null);
  const [lastSummary, setLastSummary] = useState<{ summary: string; urgency: string } | null>(null);
  const [simStatus, setSimStatus] = useState<string | null>(null);
  const [simAudioUrl, setSimAudioUrl] = useState<string | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const sendMessageRef = useRef<(textToSend?: string) => Promise<void>>(async () => {});

  // Call duration timer
  useEffect(() => {
    let timer: any;
    if (isCalling) {
      timer = setInterval(() => setCallDuration((prev) => prev + 1), 1000);
    } else {
      setCallDuration(0);
    }
    return () => clearInterval(timer);
  }, [isCalling]);

  // Auto-scroll chat
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [dialogue, isLoading]);

  // Unmount: mikrofonu kapat
  useEffect(() => {
    return () => {
      try {
        mediaRecorderRef.current?.stop();
      } catch {}
      mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    };
  }, []);

  // Audio playback helper
  const playAudio = (url: string) => {
    if (!url) return;
    const fullUrl = formatAudioUrl(url);
    if (!audioRef.current) {
      audioRef.current = new Audio(fullUrl);
    } else {
      audioRef.current.src = fullUrl;
    }
    audioRef.current.play().catch((err) => console.log('Audio autoplay prevented:', err));
  };

  const stopPlayback = () => {
    if (audioRef.current) {
      try {
        audioRef.current.pause();
        audioRef.current.currentTime = 0;
      } catch {}
    }
  };

  const pickMimeType = (): string | undefined => {
    const candidates = [
      'audio/webm;codecs=opus',
      'audio/webm',
      'audio/ogg;codecs=opus',
      'audio/mp4',
    ];
    for (const t of candidates) {
      if (typeof MediaRecorder !== 'undefined' && MediaRecorder.isTypeSupported(t)) return t;
    }
    return undefined;
  };

  const stopMicTracks = () => {
    mediaStreamRef.current?.getTracks().forEach((t) => t.stop());
    mediaStreamRef.current = null;
    mediaRecorderRef.current = null;
  };

  const finishRecordingAndSend = async (blob: Blob) => {
    setIsListening(false);
    setMicHint('Ses çözülüyor…');
    try {
      if (blob.size < 800) {
        setMicHint('Ses çok kısa — basılı tutup konuş, bitince tekrar tıkla.');
        return;
      }
      const text = await transcribeCallAudio(blob);
      if (!text) {
        setMicHint('Anlaşılamadı, tekrar dene.');
        return;
      }
      setMicHint(null);
      setInputText(text);
      await sendMessageRef.current(text);
    } catch (err: any) {
      console.error(err);
      setMicHint(err?.message || 'Mikrofon / STT hatası');
    }
  };

  const toggleListening = async () => {
    if (isLoading) return;

    // Kayıt açıksa → durdur, Whisper'a gönder
    if (isListening && mediaRecorderRef.current) {
      try {
        mediaRecorderRef.current.stop();
      } catch (err) {
        console.error(err);
        setIsListening(false);
        stopMicTracks();
      }
      return;
    }

    if (typeof MediaRecorder === 'undefined' || !navigator.mediaDevices?.getUserMedia) {
      alert('Bu tarayıcı mikrofon kaydını desteklemiyor. Metin kutusunu kullan.');
      return;
    }

    try {
      stopPlayback(); // TTS çalarken mikrofona sızmasın
      setMicHint('Konuş… bitince mikrofona tekrar bas.');
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          channelCount: 1,
        },
      });
      mediaStreamRef.current = stream;
      chunksRef.current = [];
      const mime = pickMimeType();
      const recorder = mime
        ? new MediaRecorder(stream, { mimeType: mime })
        : new MediaRecorder(stream);

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) chunksRef.current.push(e.data);
      };
      recorder.onerror = () => {
        setIsListening(false);
        setMicHint('Kayıt hatası');
        stopMicTracks();
      };
      recorder.onstop = () => {
        const type = recorder.mimeType || mime || 'audio/webm';
        const blob = new Blob(chunksRef.current, { type });
        stopMicTracks();
        void finishRecordingAndSend(blob);
      };

      mediaRecorderRef.current = recorder;
      recorder.start(250);
      setIsListening(true);
    } catch (err: any) {
      console.error(err);
      setIsListening(false);
      const msg = String(err?.message || err || '');
      if (/Permission|NotAllowed|denied/i.test(msg)) {
        setMicHint('Mikrofon izni reddedildi — tarayıcı ayarlarından aç.');
      } else {
        setMicHint('Mikrofon açılamadı: ' + msg);
      }
    }
  };

  const handleStartCall = async () => {
    setIsLoading(true);
    setDialogue([]);
    setAudioClips([]);
    setLastSummary(null);

    try {
      const res = await startCall(callerName.trim() || 'Arayan');
      setIsCalling(true);
      const greetingMsg: DialogueMessage = {
        role: 'assistant',
        content: res.greeting,
        audio_url: res.audio_url
      };
      setDialogue([greetingMsg]);

      if (res.audio_filename) {
        setAudioClips([res.audio_filename]);
      }

      if (res.audio_url) {
        playAudio(res.audio_url);
      }
    } catch (err: any) {
      alert('Arama başlatılamadı: ' + err.message);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSendMessage = async (textToSend?: string) => {
    const text = (textToSend || inputText).trim();
    if (!text || isLoading || !isCalling) return;

    setInputText('');
    const userMsg: DialogueMessage = { role: 'user', content: text };
    const nextHistory = [...dialogue, userMsg];
    setDialogue(nextHistory);
    setIsLoading(true);

    try {
      // history: mevcut mesaj hariç önceki diyalog (API mesajı ayrıca ekler)
      const res = await sendCallMessage(callerName.trim() || 'Arayan', text, dialogue);
      const assistantMsg: DialogueMessage = {
        role: 'assistant',
        content: res.reply,
        audio_url: res.audio_url
      };
      setDialogue([...nextHistory, assistantMsg]);

      if (res.audio_filename) {
        setAudioClips((prev) => [...prev, res.audio_filename!]);
      }

      if (res.audio_url) {
        playAudio(res.audio_url);
      }
    } catch (err: any) {
      console.error(err);
      setDialogue([
        ...nextHistory,
        { role: 'assistant', content: 'Kusura bakma, bir bağlantı kopukluğu oldu. Tekrar söyler misin?' }
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  // Speech recognition stale closure'ını önle
  sendMessageRef.current = handleSendMessage;

  // Native GSM karşılama: WebView ikinci ses akışı başlatmasın
  useEffect(() => {
    return onGsmHandled(async (detail) => {
      if (detail.callerName) setCallerName(detail.callerName);
      else if (detail.callerNumber) setCallerName(detail.callerNumber);
      if (detail.nativeAudioOwned || (await isNativeAudioLocked())) {
        // Sadece UI bilgilendirmesi — startCall / playAudio yok
        console.log('[LiveCallBridge] Native audio owned — WebView TTS atlandı');
      }
    });
  }, []);

  const handleEndCall = async () => {
    if (!isCalling) return;
    setIsLoading(true);

    try {
      const res = await endCall(callerName.trim() || 'Arayan', dialogue, audioClips);
      setIsCalling(false);
      setLastSummary({ summary: res.summary, urgency: res.urgency });
      if (onCallEnded) onCallEnded();
    } catch (err: any) {
      alert('Görüşme sonlandırılamadı: ' + err.message);
      setIsCalling(false);
    } finally {
      setIsLoading(false);
    }
  };

  const handleSimulateIncoming = async () => {
    setSimStatus('Sunucuya deneme araması gönderiliyor...');
    setSimAudioUrl(null);
    try {
      if (await isNativeAudioLocked()) {
        setSimStatus('Native karşılama aktif — ses CallReceiver’da.');
        setTimeout(() => setSimStatus(null), 5000);
        return;
      }
      const res = await notifyGsmIncoming(callerName.trim() || 'Deneme');
      setSimStatus(`Kayıt OK (ID: #${res.call_id || '—'}) — Ahmet karşıladı`);
      if (res.audio_url) {
        setSimAudioUrl(res.audio_url);
        if (!(await isNativeAudioLocked())) {
          playAudio(res.audio_url);
        }
      }
      setTimeout(() => setSimStatus(null), 8000);
    } catch (err: any) {
      setSimStatus('Hata: ' + err.message);
    }
  };

  const formatTimer = (sec: number) => {
    const m = Math.floor(sec / 60).toString().padStart(2, '0');
    const s = (sec % 60).toString().padStart(2, '0');
    return `${m}:${s}`;
  };

  const getUrgencyBadge = (urgency: string) => {
    const u = urgency.toLowerCase();
    if (u.includes('onemli') || u.includes('acil')) {
      return <span className="urgency-badge badge-onemli">🚨 ÖNEMLİ</span>;
    }
    if (u.includes('normal')) {
      return <span className="urgency-badge badge-normal">📌 NORMAL</span>;
    }
    return <span className="urgency-badge badge-oylesine">☕ ÖYLESİNE</span>;
  };

  return (
    <div className="live-call-container">
      {!isCalling ? (
        <div className="call-lobby-card">
          <div className="lobby-header">
            <div className="lobby-icon-pulse">
              <Phone className="w-8 h-8 text-cyan-400" />
            </div>
            <h2>Canlı Arama</h2>
            <p className="lobby-sub">
              Ahmet ile tarayıcıda deneme konuşması veya gelen arama simülasyonu (geçmişe kaydolur).
            </p>
          </div>

          <div className="lobby-input-group">
            <label>Arayan adı / numara</label>
            <input
              type="text"
              className="tenra-input"
              value={callerName}
              onChange={(e) => setCallerName(e.target.value)}
              placeholder="Örn: Ablam veya +90 555..."
            />
          </div>

          <div className="quick-caller-pills">
            {['Oğuz', 'Ablam', 'Annem', 'Bilinmeyen Numara'].map((name) => (
              <button
                key={name}
                className={`quick-pill ${callerName === name ? 'active' : ''}`}
                onClick={() => setCallerName(name)}
              >
                {name}
              </button>
            ))}
          </div>

          <button
            className="btn-call-start"
            onClick={handleStartCall}
            disabled={isLoading}
          >
            <Phone className="w-5 h-5 mr-2" />
            {isLoading ? 'Arama Başlatılıyor...' : 'Aramayı Başlat / Cevapla'}
          </button>

          <div className="gsm-test-box" style={{ marginTop: '1.25rem', width: '100%' }}>
            <label className="text-xs text-slate-300 font-semibold block mb-1">
              Deneme araması (sunucu kaydı + selamlama sesi)
            </label>
            <button
              type="button"
              className="btn-trigger-gsm"
              onClick={() => void handleSimulateIncoming()}
              style={{ width: '100%' }}
            >
              <Zap className="w-4 h-4 mr-1" />
              Gelen arama simüle et
            </button>
            {simStatus && (
              <div className="mt-2 text-xs font-semibold text-emerald-400 flex items-center justify-between gap-2">
                <span>{simStatus}</span>
                {simAudioUrl && (
                  <button
                    type="button"
                    className="px-2 py-1 bg-cyan-500/20 text-cyan-300 rounded flex items-center text-[11px]"
                    onClick={() => playAudio(simAudioUrl)}
                  >
                    <Volume2 className="w-3 h-3 mr-1" />
                    Dinle
                  </button>
                )}
              </div>
            )}
          </div>

          {lastSummary && (
            <div className="last-summary-card">
              <div className="summary-card-header">
                <Sparkles className="w-5 h-5 text-amber-400" />
                <span className="font-semibold">Son Çağrı Özeti</span>
                {getUrgencyBadge(lastSummary.urgency)}
              </div>
              <p className="summary-text">"{lastSummary.summary}"</p>
            </div>
          )}
        </div>
      ) : (
        <div className="active-call-card">
          {/* Active Call Top Bar */}
          <div className="call-active-bar">
            <div className="call-caller-info">
              <div className="avatar-ring">
                <span className="avatar-initials">
                  {callerName.slice(0, 2).toUpperCase()}
                </span>
                <span className="live-dot"></span>
              </div>
              <div>
                <h3 className="call-title">{callerName}</h3>
                <div className="call-status-line">
                  <span className="timer-badge">
                    <Clock className="w-3.5 h-3.5 mr-1" />
                    {formatTimer(callDuration)}
                  </span>
                  <span className="assistant-active-tag">Ahmet AI Aktif</span>
                </div>
              </div>
            </div>

            <button
              className="btn-call-end"
              onClick={handleEndCall}
              disabled={isLoading}
              title="Görüşmeyi Bitir"
            >
              <PhoneOff className="w-5 h-5 mr-1.5" />
              Bitir
            </button>
          </div>

          {/* Dialogue Stream */}
          <div className="dialogue-scroll-area">
            {dialogue.map((msg, idx) => (
              <div
                key={idx}
                className={`message-row ${msg.role === 'user' ? 'row-user' : 'row-assistant'}`}
              >
                <div className={`message-bubble ${msg.role === 'user' ? 'bubble-user' : 'bubble-assistant'}`}>
                  <div className="message-header">
                    <span className="sender-name">
                      {msg.role === 'user' ? callerName : 'Ahmet (AI İkiz)'}
                    </span>
                    {msg.audio_url && (
                      <button
                        className="btn-play-bubble"
                        onClick={() => playAudio(msg.audio_url!)}
                        title="Sesi Dinle"
                      >
                        <Volume2 className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </div>
                  <p className="message-text">{msg.content}</p>
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="message-row row-assistant">
                <div className="message-bubble bubble-assistant thinking-bubble">
                  <div className="thinking-dots">
                    <span></span><span></span><span></span>
                  </div>
                  <span className="thinking-text">Ahmet düşünüyor ve seslendiriyor...</span>
                </div>
              </div>
            )}
            <div ref={chatEndRef} />
          </div>

          {/* Quick Reply Suggestions */}
          <div className="quick-phrases-bar">
            {[
              'Yarın akşam işin var mı?',
              'Acil bir durum var, bana ulaşsın!',
              'Sadece selam vermek istemiştim.'
            ].map((phrase, i) => (
              <button
                key={i}
                className="phrase-chip"
                onClick={() => handleSendMessage(phrase)}
                disabled={isLoading}
              >
                {phrase}
              </button>
            ))}
          </div>

          {/* Input Controls */}
          <div className="call-input-bar">
            <button
              className={`btn-mic ${isListening ? 'listening' : ''}`}
              onClick={() => void toggleListening()}
              disabled={isLoading}
              title={isListening ? 'Kaydı Bitir' : 'Mikrofonla Konuş'}
            >
              {isListening ? <MicOff className="w-5 h-5" /> : <Mic className="w-5 h-5" />}
            </button>

            <input
              type="text"
              className="chat-input"
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') handleSendMessage();
              }}
              placeholder={
                isListening
                  ? 'Dinliyorum — bitince mikrofona bas'
                  : micHint || 'Mesajınızı yazın veya konuşun...'
              }
              disabled={isLoading}
            />

            <button
              className="btn-send"
              onClick={() => handleSendMessage()}
              disabled={!inputText.trim() || isLoading}
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          {micHint && !isListening && (
            <div className="custom-note-hint" style={{ padding: '0 1rem 0.5rem' }}>
              {micHint}
            </div>
          )}
        </div>
      )}
    </div>
  );
};

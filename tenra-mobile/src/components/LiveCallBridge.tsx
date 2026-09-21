import React, { useState, useEffect, useRef } from 'react';
import { Phone, PhoneOff, Mic, MicOff, Send, Volume2, Sparkles, Clock } from 'lucide-react';
import { startCall, sendCallMessage, endCall, formatAudioUrl } from '../api';
import type { DialogueMessage } from '../types';

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
  const [lastSummary, setLastSummary] = useState<{ summary: string; urgency: string } | null>(null);

  const audioRef = useRef<HTMLAudioElement | null>(null);
  const chatEndRef = useRef<HTMLDivElement | null>(null);
  const recognitionRef = useRef<any>(null);

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

  // Web Speech Recognition setup
  useEffect(() => {
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = false;
      recognition.lang = 'tr-TR';

      recognition.onresult = (event: any) => {
        const transcript = event.results[0][0].transcript;
        if (transcript) {
          setInputText(transcript);
          handleSendMessage(transcript);
        }
        setIsListening(false);
      };

      recognition.onerror = () => {
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognitionRef.current = recognition;
    }
  }, []);

  const toggleListening = () => {
    if (!recognitionRef.current) {
      alert('Tarayıcınız sesli tanımayı desteklemiyor. Metin kutusunu kullanabilirsiniz.');
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
      setIsListening(false);
    } else {
      try {
        recognitionRef.current.start();
        setIsListening(true);
      } catch (err) {
        console.error(err);
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
      const res = await sendCallMessage(callerName.trim() || 'Arayan', text, nextHistory);
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
            <h2>Canlı Sesli Görüşme Testi</h2>
            <p className="lobby-sub">
              Ahmet Eren dijital ikizi ile gerçek zamanlı konuşma veya gelen GSM çağrısı simülasyonu.
            </p>
          </div>

          <div className="lobby-input-group">
            <label>Arayan Kişi Adı / Numarası</label>
            <input
              type="text"
              className="tenra-input"
              value={callerName}
              onChange={(e) => setCallerName(e.target.value)}
              placeholder="Örn: Oğuz veya +90 555..."
            />
          </div>

          <div className="quick-caller-pills">
            {['Oğuz', 'Annem', 'İş Yeri', 'Bilinmeyen Numara'].map((name) => (
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
              onClick={toggleListening}
              title={isListening ? 'Dinlemeyi Durdur' : 'Mikrofonla Konuş'}
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
              placeholder={isListening ? 'Sizi dinliyor, konuşun...' : 'Mesajınızı yazın veya konuşun...'}
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
        </div>
      )}
    </div>
  );
};

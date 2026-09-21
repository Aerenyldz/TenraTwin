import React, { useEffect, useState } from 'react';
import { PhoneIncoming, RefreshCw, Trash2, Play, Pause, ChevronDown, ChevronUp, FileText, Calendar } from 'lucide-react';
import { fetchCalls, deleteCall, getServerUrl } from '../api';
import type { CallRecord } from '../types';

export const CallHistory: React.FC = () => {
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [loading, setLoading] = useState(false);
  const [filter, setFilter] = useState<'all' | 'onemli' | 'normal' | 'oylesine'>('all');
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [playingId, setPlayingId] = useState<number | null>(null);
  const [audioElement, setAudioElement] = useState<HTMLAudioElement | null>(null);

  const loadCalls = async () => {
    setLoading(true);
    try {
      const data = await fetchCalls();
      setCalls(data);
    } catch (err) {
      console.error('Calls could not be loaded:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadCalls();
  }, []);

  const handleDelete = async (id: number) => {
    if (!window.confirm('Bu çağrı kaydını silmek istediğinize emin misiniz?')) return;
    try {
      const ok = await deleteCall(id);
      if (ok) {
        setCalls((prev) => prev.filter((c) => c.id !== id));
      }
    } catch (err) {
      console.error(err);
    }
  };

  const toggleAudio = (call: CallRecord) => {
    if (playingId === call.id) {
      audioElement?.pause();
      setPlayingId(null);
      return;
    }

    if (audioElement) {
      audioElement.pause();
    }

    const audioUrl = `${getServerUrl()}/api/calls/${call.id}/audio`;
    const newAudio = new Audio(audioUrl);
    newAudio.play().catch((err) => console.log('Playback error:', err));
    newAudio.onended = () => setPlayingId(null);
    newAudio.onerror = () => {
      alert('Ses kaydı oynatılamadı veya bulunamadı.');
      setPlayingId(null);
    };

    setAudioElement(newAudio);
    setPlayingId(call.id);
  };

  const getUrgencyBadge = (urgency: string) => {
    const u = (urgency || '').toLowerCase();
    if (u.includes('onemli') || u.includes('acil')) {
      return <span className="urgency-badge badge-onemli">🚨 ÖNEMLİ</span>;
    }
    if (u.includes('normal')) {
      return <span className="urgency-badge badge-normal">📌 NORMAL</span>;
    }
    return <span className="urgency-badge badge-oylesine">☕ ÖYLESİNE</span>;
  };

  const filteredCalls = calls.filter((c) => {
    if (filter === 'all') return true;
    const u = (c.urgency || '').toLowerCase();
    if (filter === 'onemli') return u.includes('onemli') || u.includes('acil');
    if (filter === 'normal') return u.includes('normal');
    if (filter === 'oylesine') return u.includes('oylesine') || u.includes('onemsiz');
    return true;
  });

  return (
    <div className="call-history-container">
      {/* Header & Filter Controls */}
      <div className="history-header">
        <div>
          <h2>Arama Geçmişi & Notlar</h2>
          <p className="history-sub">
            Gelen GSM aramalarının detaylı özetleri ve ses kayıtları
          </p>
        </div>
        <button
          className="btn-refresh"
          onClick={loadCalls}
          disabled={loading}
          title="Yenile"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'spin' : ''}`} />
        </button>
      </div>

      <div className="filter-tabs">
        <button
          className={`filter-tab ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')}
        >
          Tümü ({calls.length})
        </button>
        <button
          className={`filter-tab tab-onemli ${filter === 'onemli' ? 'active' : ''}`}
          onClick={() => setFilter('onemli')}
        >
          🚨 Önemli
        </button>
        <button
          className={`filter-tab tab-normal ${filter === 'normal' ? 'active' : ''}`}
          onClick={() => setFilter('normal')}
        >
          📌 Normal
        </button>
        <button
          className={`filter-tab tab-oylesine ${filter === 'oylesine' ? 'active' : ''}`}
          onClick={() => setFilter('oylesine')}
        >
          ☕ Öylesine
        </button>
      </div>

      {/* Calls List */}
      {filteredCalls.length === 0 ? (
        <div className="empty-history-card">
          <PhoneIncoming className="w-12 h-12 text-slate-500 mb-2" />
          <h3>Henüz Kayıt Yok</h3>
          <p>
            {filter === 'all'
              ? 'Gelen aramalarınız olduğunda özet notlar ve ses kayıtları burada listelenecektir.'
              : 'Seçili filtreye uygun arama kaydı bulunamadı.'}
          </p>
        </div>
      ) : (
        <div className="calls-list">
          {filteredCalls.map((call) => {
            const isExpanded = expandedId === call.id;
            const isAudioPlaying = playingId === call.id;

            return (
              <div key={call.id} className="call-card">
                <div className="call-card-top">
                  <div className="caller-info">
                    <div className="caller-avatar">
                      {call.caller_name.slice(0, 2).toUpperCase()}
                    </div>
                    <div>
                      <h4 className="caller-name">{call.caller_name}</h4>
                      <span className="call-timestamp">
                        <Calendar className="w-3.5 h-3.5 mr-1" />
                        {call.timestamp}
                      </span>
                    </div>
                  </div>
                  <div className="call-card-actions">
                    {getUrgencyBadge(call.urgency)}
                    <button
                      className="btn-icon-delete"
                      onClick={() => handleDelete(call.id)}
                      title="Sil"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                </div>

                {/* Intelligent Summary Note */}
                <div className="call-summary-box">
                  <p className="summary-quote">
                    "{call.summary || 'Özet bulunamadı.'}"
                  </p>
                </div>

                {/* Controls: Audio Playback & Transcript Toggle */}
                <div className="call-card-bottom">
                  {call.audio_file ? (
                    <button
                      className={`btn-play-audio ${isAudioPlaying ? 'playing' : ''}`}
                      onClick={() => toggleAudio(call)}
                    >
                      {isAudioPlaying ? (
                        <>
                          <Pause className="w-4 h-4 mr-1.5" />
                          Durdur
                        </>
                      ) : (
                        <>
                          <Play className="w-4 h-4 mr-1.5" />
                          Ses Kaydını Dinle
                        </>
                      )}
                    </button>
                  ) : (
                    <span className="no-audio-text">Ses kaydı yok</span>
                  )}

                  {call.transcript && (
                    <button
                      className="btn-toggle-transcript"
                      onClick={() => setExpandedId(isExpanded ? null : call.id)}
                    >
                      <FileText className="w-3.5 h-3.5 mr-1" />
                      {isExpanded ? 'Dökümü Gizle' : 'Konuşma Dökümü'}
                      {isExpanded ? (
                        <ChevronUp className="w-3.5 h-3.5 ml-1" />
                      ) : (
                        <ChevronDown className="w-3.5 h-3.5 ml-1" />
                      )}
                    </button>
                  )}
                </div>

                {/* Collapsible Transcript */}
                {isExpanded && call.transcript && (
                  <div className="transcript-accordion">
                    <h5>Görüşme Detayı:</h5>
                    <pre className="transcript-text">{call.transcript}</pre>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};

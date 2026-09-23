import { useState, useEffect } from 'react';
import { Phone, History, Settings } from 'lucide-react';
import { StatusWidget } from './components/StatusWidget';
import { LiveCallBridge } from './components/LiveCallBridge';
import { CallHistory } from './components/CallHistory';
import { SettingsModal } from './components/SettingsModal';
import { pingServer, getServerUrl, ensureLocalServerUrl } from './api';
import { onGsmHandled, syncAutoAnswerDelayToNative } from './nativePrefs';
import './App.css';

type Tab = 'call' | 'history' | 'settings';

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('call');
  const [serverOnline, setServerOnline] = useState<boolean | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [gsmBanner, setGsmBanner] = useState<string | null>(null);

  useEffect(() => {
    ensureLocalServerUrl();
    void syncAutoAnswerDelayToNative(Number(localStorage.getItem('tenra_auto_delay')) || 5);
  }, []);

  useEffect(() => {
    return onGsmHandled((detail) => {
      const label = detail.callerName || detail.callerNumber || 'Arayan';
      setGsmBanner(
        detail.nativeAudioOwned
          ? `${label} — native karşılama aktif (ses CallReceiver'da)`
          : `${label} aradı`
      );
      setActiveTab('history');
      setTimeout(() => setGsmBanner(null), 8000);
    });
  }, []);

  useEffect(() => {
    const checkConnection = async () => {
      const res = await pingServer();
      setServerOnline(res.ok);
      setLatency(res.latencyMs);
    };

    checkConnection();
    const interval = setInterval(checkConnection, 5000);
    return () => clearInterval(interval);
  }, []);


  return (
    <div className="app-viewport">
      {/* Top Application Bar — ayarlar yalnızca alt nav'da */}
      <header className="app-header">
        <div className="header-brand">
          <div className="brand-logo-glow">
            <span className="brand-letter">TT</span>
          </div>
          <div>
            <h1 className="brand-name">TenraTwin</h1>
            <span className="brand-sub">Ahmet Eren &bull; Kişisel Ses İkizi</span>
          </div>
        </div>

        <div className="header-status">
          <div
            className={`connection-pill ${
              serverOnline === true ? 'online' : serverOnline === false ? 'offline' : 'checking'
            }`}
            title={getServerUrl()}
          >
            <span className="pulse-indicator"></span>
            <span className="conn-text">
              {serverOnline === true ? (
                <>Sunucu Aktif {latency !== null && `(${latency}ms)`}</>
              ) : serverOnline === false ? (
                '🔴 Sunucu Çevrimdışı'
              ) : (
                'Bağlanıyor...'
              )}
            </span>
          </div>
        </div>
      </header>

      {gsmBanner && (
        <div className="gsm-native-banner">
          <Phone className="w-4 h-4 mr-2" />
          <span>{gsmBanner}</span>
        </div>
      )}


      {/* Main Content Area */}
      <main className="app-body">
        {activeTab === 'call' && (
          <div className="tab-content">
            <StatusWidget />
            <LiveCallBridge onCallEnded={() => {}} />
          </div>
        )}

        {activeTab === 'history' && (
          <div className="tab-content">
            <CallHistory />
          </div>
        )}

        {activeTab === 'settings' && (
          <div className="tab-content">
            <SettingsModal onNavigateToHistory={() => setActiveTab('history')} />
          </div>
        )}

      </main>

      {/* Bottom Floating Navigation Bar (Mobile Native App Style) */}
      <nav className="bottom-nav">
        <button
          className={`nav-item ${activeTab === 'call' ? 'active' : ''}`}
          onClick={() => setActiveTab('call')}
        >
          <Phone className="nav-icon" />
          <span className="nav-label">Canlı Arama</span>
        </button>

        <button
          className={`nav-item ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => setActiveTab('history')}
        >
          <History className="nav-icon" />
          <span className="nav-label">Arama Geçmişi</span>
        </button>

        <button
          className={`nav-item ${activeTab === 'settings' ? 'active' : ''}`}
          onClick={() => setActiveTab('settings')}
        >
          <Settings className="nav-icon" />
          <span className="nav-label">Ayarlar</span>
        </button>
      </nav>
    </div>
  );
}

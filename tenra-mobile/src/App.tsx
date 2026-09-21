import { useState, useEffect } from 'react';
import { Phone, History, Settings, Download, X } from 'lucide-react';
import { StatusWidget } from './components/StatusWidget';
import { LiveCallBridge } from './components/LiveCallBridge';
import { CallHistory } from './components/CallHistory';
import { SettingsModal } from './components/SettingsModal';
import { pingServer, getServerUrl } from './api';
import './App.css';

type Tab = 'call' | 'history' | 'settings';

export default function App() {
  const [activeTab, setActiveTab] = useState<Tab>('call');
  const [serverOnline, setServerOnline] = useState<boolean | null>(null);
  const [latency, setLatency] = useState<number | null>(null);
  const [deferredPrompt, setDeferredPrompt] = useState<any>(null);
  const [showInstallBanner, setShowInstallBanner] = useState<boolean>(() => {
    if (typeof window !== 'undefined' && window.matchMedia('(display-mode: standalone)').matches) {
      return false;
    }
    return true;
  });

  useEffect(() => {
    const handleBeforeInstall = (e: Event) => {
      e.preventDefault();
      setDeferredPrompt(e);
      setShowInstallBanner(true);
    };

    window.addEventListener('beforeinstallprompt', handleBeforeInstall);
    return () => window.removeEventListener('beforeinstallprompt', handleBeforeInstall);
  }, []);

  const handleInstallClick = async () => {
    if (deferredPrompt) {
      deferredPrompt.prompt();
      const choice = await deferredPrompt.userChoice;
      if (choice.outcome === 'accepted') {
        setDeferredPrompt(null);
        setShowInstallBanner(false);
      }
    } else {
      alert("📲 Uygulamayı Telefona Yüklemek İçin:\n\n1. Chrome tarayıcısında sağ üstteki 3 noktaya (⋮) dokunun.\n2. 'Uygulamayı Yükle' veya 'Ana Ekrana Ekle' seçeneğine basın.");
    }
  };

  useEffect(() => {
    const checkConnection = async () => {
      const res = await pingServer();
      setServerOnline(res.ok);
      setLatency(res.latencyMs);
    };

    checkConnection();
    const interval = setInterval(checkConnection, 15000);
    return () => clearInterval(interval);
  }, []);


  return (
    <div className="app-viewport">
      {/* Top Application Bar */}
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
                'Çevrimdışı'
              ) : (
                'Bağlanıyor...'
              )}
            </span>
          </div>

          <button
            className={`btn-settings-header ${activeTab === 'settings' ? 'active' : ''}`}
            onClick={() => setActiveTab(activeTab === 'settings' ? 'call' : 'settings')}
            title="Ayarlar"
          >
            <Settings className="w-5 h-5" />
          </button>
        </div>
      </header>

      {/* Install App Banner for Mobile PWA */}
      {showInstallBanner && (
        <div className="install-banner">
          <div className="install-info">
            <Download className="w-4 h-4 text-cyan-400 mr-2" />
            <span>TenraTwin'i tam ekran uygulama olarak yükleyin</span>
          </div>
          <div className="install-actions">
            <button className="btn-install-pwa" onClick={handleInstallClick}>
              Yükle
            </button>
            <button className="btn-close-banner" onClick={() => setShowInstallBanner(false)}>
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
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

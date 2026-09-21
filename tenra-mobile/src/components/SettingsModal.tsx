import React, { useState, useEffect } from 'react';
import { Settings, Server, Cpu, Wifi, CheckCircle2, XCircle, RefreshCw, Smartphone, ShieldCheck, Zap, Volume2, PhoneCall, Play, Square } from 'lucide-react';
import {
  getServerUrl,
  setServerUrl,
  pingServer,
  fetchSystemStats,
  notifyGsmIncoming,
  fetchSettings,
  saveServerSettings,
  formatAudioUrl,
  fetchVoIPConfig,
  saveVoIPConfig,
  startVoIPGateway,
  stopVoIPGateway,
  DEFAULT_TAILSCALE_URL,
  DEFAULT_LOCAL_URL
} from '../api';

interface SettingsModalProps {
  onClose?: () => void;
  onNavigateToHistory?: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ onClose: _onClose, onNavigateToHistory }) => {
  const [currentUrl, setCurrentUrlInput] = useState(getServerUrl());
  const [pingResult, setPingResult] = useState<{ ok: boolean; latencyMs: number } | null>(null);
  const [isPinging, setIsPinging] = useState(false);
  const [systemStats, setSystemStats] = useState<any>(null);
  const [autoAnswerDelay, setAutoAnswerDelay] = useState<number>(() => {
    return Number(localStorage.getItem('tenra_auto_delay')) || 10;
  });
  const [testNumber, setTestNumber] = useState<string>(() => {
    return localStorage.getItem('tenra_test_num') || '+90 532 123 45 67';
  });
  const [testStatus, setTestStatus] = useState<string | null>(null);
  const [lastAudioUrl, setLastAudioUrl] = useState<string | null>(null);
  const [voipConfig, setVoipConfig] = useState<any>({
    sip_server: '',
    sip_port: 5060,
    sip_user: '',
    sip_password: '',
    sip_my_ip: '0.0.0.0',
    is_running: false,
    last_status: 'Durduruldu'
  });
  const [isSavingVoip, setIsSavingVoip] = useState(false);
  const [voipMsg, setVoipMsg] = useState<string | null>(null);

  useEffect(() => {
    handlePing(getServerUrl());
    fetchSystemStats().then(setSystemStats).catch(() => {});
    
    // Sunucudan kalıcı ayarları yükle
    fetchSettings().then((data) => {
      if (data.gsm_test_number) {
        setTestNumber(data.gsm_test_number);
        localStorage.setItem('tenra_test_num', data.gsm_test_number);
      }
      if (data.auto_answer_delay) {
        const val = Number(data.auto_answer_delay);
        if (!isNaN(val)) {
          setAutoAnswerDelay(val);
          localStorage.setItem('tenra_auto_delay', String(val));
        }
      }
    }).catch(() => {});

    fetchVoIPConfig().then((data) => {
      if (data && data.sip_server !== undefined) {
        setVoipConfig(data);
      }
    }).catch(() => {});
  }, []);

  const handleSaveVoip = async () => {
    setIsSavingVoip(true);
    try {
      const res = await saveVoIPConfig(voipConfig);
      setVoipMsg('✅ SIP ayarları başarıyla kaydedildi.');
      if (res.config) setVoipConfig(res.config);
    } catch (err: any) {
      setVoipMsg('❌ Hata: ' + err.message);
    } finally {
      setIsSavingVoip(false);
      setTimeout(() => setVoipMsg(null), 4000);
    }
  };

  const handleToggleVoip = async () => {
    try {
      if (voipConfig.is_running) {
        const res = await stopVoIPGateway();
        setVoipMsg(res.message);
      } else {
        const res = await startVoIPGateway();
        setVoipMsg(res.message);
      }
      const updated = await fetchVoIPConfig();
      if (updated) setVoipConfig(updated);
    } catch (err: any) {
      setVoipMsg('❌ Hata: ' + err.message);
    }
    setTimeout(() => setVoipMsg(null), 5000);
  };

  const handlePing = async (urlToTest?: string) => {
    setIsPinging(true);
    const result = await pingServer(urlToTest || currentUrl);
    setPingResult(result);
    setIsPinging(false);
  };

  const handleSaveUrl = (url: string) => {
    setServerUrl(url);
    setCurrentUrlInput(url);
    handlePing(url);
  };

  const handleNumberChange = (num: string) => {
    setTestNumber(num);
    localStorage.setItem('tenra_test_num', num);
    saveServerSettings({ gsm_test_number: num }).catch(() => {});
  };

  const handleDelayChange = (delay: number) => {
    setAutoAnswerDelay(delay);
    localStorage.setItem('tenra_auto_delay', String(delay));
    saveServerSettings({ auto_answer_delay: delay }).catch(() => {});
  };

  const handleTriggerGsmTest = async () => {
    setTestStatus('Aranıyor ve Ahmet Eren AI karşılıyor...');
    setLastAudioUrl(null);
    try {
      const res = await notifyGsmIncoming(testNumber);
      setTestStatus(`✅ Arama Kaydedildi (ID: #${res.call_id || 'OK'}) - Ahmet Asistan Devrede!`);
      if (res.audio_url) {
        setLastAudioUrl(res.audio_url);
        // Otomatik sesi oynat
        const audio = new Audio(formatAudioUrl(res.audio_url));
        audio.play().catch(() => {});
      }
      setTimeout(() => setTestStatus(null), 7000);
    } catch (err: any) {
      setTestStatus('❌ Hata: ' + err.message);
    }
  };


  return (
    <div className="settings-container">
      <div className="settings-header">
        <div className="flex items-center space-x-2">
          <Settings className="w-6 h-6 text-cyan-400" />
          <h2>Sistem ve Bağlantı Ayarları</h2>
        </div>
        <p className="settings-sub">
          NVIDIA RTX Ev Sunucusu ve Android Çağrı Karşılama Yapılandırması
        </p>
      </div>

      {/* Connection Mode Card */}
      <div className="settings-card">
        <div className="card-title">
          <Server className="w-5 h-5 text-indigo-400 mr-2" />
          <span>Sunucu Bağlantı Modu</span>
        </div>
        <p className="card-desc">
          Telefonunuzun bilgisayarınıza nasıl bağlanacağını seçin:
        </p>

        <div className="server-presets">
          <button
            className={`preset-btn ${currentUrl === DEFAULT_TAILSCALE_URL ? 'active' : ''}`}
            onClick={() => handleSaveUrl(DEFAULT_TAILSCALE_URL)}
          >
            <div className="preset-title">
              <ShieldCheck className="w-4 h-4 text-emerald-400 mr-1" />
              Tailscale VPN (Önerilen)
            </div>
            <div className="preset-url">{DEFAULT_TAILSCALE_URL}</div>
            <div className="preset-hint">Spor salonu, sokak, her yerden güvenli erişim</div>
          </button>

          <button
            className={`preset-btn ${currentUrl === DEFAULT_LOCAL_URL ? 'active' : ''}`}
            onClick={() => handleSaveUrl(DEFAULT_LOCAL_URL)}
          >
            <div className="preset-title">
              <Wifi className="w-4 h-4 text-cyan-400 mr-1" />
              Ev İçi Wi-Fi
            </div>
            <div className="preset-url">{DEFAULT_LOCAL_URL}</div>
            <div className="preset-hint">Aynı ev Wi-Fi ağına bağlıyken en düşük gecikme</div>
          </button>
        </div>

        <div className="custom-url-group">
          <label>Özel / Cloud Sunucu Adresi</label>
          <div className="url-input-row">
            <input
              type="text"
              className="tenra-input"
              value={currentUrl}
              onChange={(e) => setCurrentUrlInput(e.target.value)}
              placeholder="http://100.x.x.x:8008"
            />
            <button
              className="btn-save-url"
              onClick={() => handleSaveUrl(currentUrl)}
            >
              Kaydet
            </button>
            <button
              className="btn-ping"
              onClick={() => handlePing(currentUrl)}
              disabled={isPinging}
              title="Gecikme Testi"
            >
              <RefreshCw className={`w-4 h-4 ${isPinging ? 'spin' : ''}`} />
            </button>
          </div>
        </div>

        {pingResult && (
          <div className={`ping-status-box ${pingResult.ok ? 'ping-ok' : 'ping-err'}`}>
            {pingResult.ok ? (
              <>
                <CheckCircle2 className="w-4 h-4 text-emerald-400 mr-1.5" />
                <span>Bağlantı Başarılı &mdash; Gecikme: <strong>{pingResult.latencyMs} ms</strong></span>
              </>
            ) : (
              <>
                <XCircle className="w-4 h-4 text-rose-400 mr-1.5" />
                <span>Sunucuya ulaşılamadı. Lütfen Tailscale veya IP adresini kontrol edin.</span>
              </>
            )}
          </div>
        )}
      </div>

      {/* Android Native Integration Card */}
      <div className="settings-card">
        <div className="card-title">
          <Smartphone className="w-5 h-5 text-amber-400 mr-2" />
          <span>Android Yerel Çağrı Karşılama Servisi</span>
        </div>
        <p className="card-desc">
          Telefonunuza normal GSM araması geldiğinde çalışan <code>CallReceiver.java</code> ayarları.
        </p>

        <div className="setting-row">
          <div>
            <label className="font-semibold block">Otomatik Cevaplama Gecikmesi</label>
            <span className="text-xs text-slate-400">
              Telefon çalmaya başladığında Ahmet'in açması için beklenecek süre. Açılmazsa asistan devreye girer.
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <input
              type="number"
              className="tenra-number-input"
              min="3"
              max="30"
              value={autoAnswerDelay}
              onChange={(e) => handleDelayChange(Number(e.target.value))}
            />
            <span className="text-sm font-medium">sn</span>
          </div>
        </div>

        <div className="gsm-test-box">
          <label className="text-xs text-slate-300 font-semibold block mb-1">
            Gelen GSM Çağrısı Simülasyonu (Numara Sunucuya Kaydedilir)
          </label>
          <div className="flex space-x-2">
            <input
              type="text"
              className="tenra-input text-sm"
              value={testNumber}
              onChange={(e) => handleNumberChange(e.target.value)}
              placeholder="+90 5xx..."
            />
            <button
              className="btn-trigger-gsm"
              onClick={handleTriggerGsmTest}
            >
              <Zap className="w-4 h-4 mr-1" />
              Tetikle
            </button>
          </div>
          {testStatus && (
            <div className="mt-2 text-xs font-semibold text-emerald-400 flex items-center justify-between">
              <span>{testStatus}</span>
              {lastAudioUrl && (
                <button
                  className="px-2 py-1 bg-cyan-500/20 text-cyan-300 rounded flex items-center text-[11px]"
                  onClick={() => {
                    const a = new Audio(formatAudioUrl(lastAudioUrl));
                    a.play().catch(() => {});
                  }}
                >
                  <Volume2 className="w-3 h-3 mr-1" />
                  Cevabı Dinle
                </button>
              )}
            </div>
          )}
          {onNavigateToHistory && testStatus && (
            <button
              className="mt-2 text-xs text-cyan-400 underline block cursor-pointer"
              onClick={onNavigateToHistory}
            >
              📋 Arama Geçmişine Git ve Kaydı Gör &rarr;
            </button>
          )}
        </div>
      </div>

      {/* SIP / VoIP Enterprise Gateway Card */}
      <div className="settings-card">
        <div className="card-title">
          <PhoneCall className="w-5 h-5 text-purple-400 mr-2" />
          <span>SIP / VoIP Profesyonel Santral Entegrasyonu</span>
        </div>
        <p className="card-desc">
          Telefon operatörünüzden (NetGSM, Bulutfon, Zadarma, Twilio) veya yerel PBX santralinizden gelen aramaları doğrudan bu sunucuya yönlendirin. Ahmet Eren ikizi aramayı dijital sesle yanıtlar.
        </p>

        <div className="space-y-3">
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">SIP Sunucu (Host / Domain)</label>
              <input
                type="text"
                className="tenra-input text-sm"
                placeholder="sip.netgsm.com.tr veya 192.168.1.x"
                value={voipConfig.sip_server || ''}
                onChange={(e) => setVoipConfig({ ...voipConfig, sip_server: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">SIP Port</label>
              <input
                type="number"
                className="tenra-input text-sm"
                placeholder="5060"
                value={voipConfig.sip_port || 5060}
                onChange={(e) => setVoipConfig({ ...voipConfig, sip_port: Number(e.target.value) })}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">Dahili No / Kullanıcı Adı</label>
              <input
                type="text"
                className="tenra-input text-sm"
                placeholder="101 veya 0850xxxxxxx"
                value={voipConfig.sip_user || ''}
                onChange={(e) => setVoipConfig({ ...voipConfig, sip_user: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">SIP Şifresi</label>
              <input
                type="password"
                className="tenra-input text-sm"
                placeholder="••••••••"
                value={voipConfig.sip_password || ''}
                onChange={(e) => setVoipConfig({ ...voipConfig, sip_password: e.target.value })}
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-2 items-center pt-2">
            <button
              className="btn-trigger-gsm"
              onClick={handleSaveVoip}
              disabled={isSavingVoip}
            >
              💾 Kaydet
            </button>
            <button
              className={`px-3 py-1.5 rounded text-xs font-semibold flex items-center transition ${
                voipConfig.is_running
                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                  : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
              }`}
              onClick={handleToggleVoip}
            >
              {voipConfig.is_running ? (
                <>
                  <Square className="w-3.5 h-3.5 mr-1" />
                  SIP Gateway Durdur
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 mr-1" />
                  SIP Gateway Başlat
                </>
              )}
            </button>
            <span className="text-xs text-slate-400 ml-auto">
              Durum: <strong>{voipConfig.last_status || (voipConfig.is_running ? 'Aktif' : 'Durduruldu')}</strong>
            </span>
          </div>

          {voipMsg && (
            <div className="text-xs font-semibold text-cyan-300 bg-cyan-950/40 p-2 rounded border border-cyan-800/40">
              {voipMsg}
            </div>
          )}

          <div className="text-[11px] text-slate-400 bg-slate-900/40 p-2 rounded border border-slate-800">
            🌐 <strong>Bulut Webhook URL (Twilio/Bulutfon/Zadarma):</strong><br />
            <code>{getServerUrl()}/api/voip/webhook</code>
          </div>
        </div>
      </div>

      {/* Hardware & Model Stats */}
      {systemStats && (
        <div className="settings-card">
          <div className="card-title">
            <Cpu className="w-5 h-5 text-cyan-400 mr-2" />
            <span>Ev Sunucusu Donanım ve Model Durumu</span>
          </div>
          <div className="stats-grid">
            <div className="stat-box">
              <span className="stat-label">GPU</span>
              <span className="stat-val">{systemStats.gpu_name}</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">LLM Modeli</span>
              <span className="stat-val">{systemStats.llm_model}</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Ses Motoru</span>
              <span className="stat-val">{systemStats.active_voice_model}</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Toplam Çağrı</span>
              <span className="stat-val">{systemStats.total_calls}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

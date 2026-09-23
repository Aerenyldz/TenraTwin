import React, { useState, useEffect } from 'react';
import {
  Settings,
  Server,
  Cpu,
  CheckCircle2,
  XCircle,
  RefreshCw,
  Smartphone,
  PhoneCall,
  Play,
  Square,
} from 'lucide-react';
import {
  getServerUrl,
  ensureLocalServerUrl,
  pingServer,
  fetchSystemStats,
  fetchSettings,
  saveServerSettings,
  fetchVoIPConfig,
  saveVoIPConfig,
  startVoIPGateway,
  stopVoIPGateway,
  applyVoIPLocalLab,
} from '../api';
import { syncAutoAnswerDelayToNative, syncGsmAutoAnswerToNative } from '../nativePrefs';

interface SettingsModalProps {
  onClose?: () => void;
  onNavigateToHistory?: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = () => {
  const [serverUrl, setServerUrlState] = useState(getServerUrl());
  const [pingResult, setPingResult] = useState<{ ok: boolean; latencyMs: number } | null>(null);
  const [isPinging, setIsPinging] = useState(false);
  const [systemStats, setSystemStats] = useState<any>(null);
  const [autoAnswerDelay, setAutoAnswerDelay] = useState<number>(() => {
    return Number(localStorage.getItem('tenra_auto_delay')) || 5;
  });
  const [voipConfig, setVoipConfig] = useState<any>({
    sip_server: '127.0.0.1',
    sip_port: 5060,
    sip_user: '100',
    sip_password: 'tenra100',
    sip_my_ip: '127.0.0.1',
    sip_bind_port: 5062,
    sip_auto_start: false,
    gsm_auto_answer: false,
    is_running: false,
    last_status: 'Durduruldu',
  });
  const [gsmAutoAnswer, setGsmAutoAnswer] = useState<boolean>(() => {
    return localStorage.getItem('tenra_gsm_auto_answer') === '1';
  });
  const [isSavingVoip, setIsSavingVoip] = useState(false);
  const [voipMsg, setVoipMsg] = useState<string | null>(null);

  const refreshConnection = async () => {
    const url = ensureLocalServerUrl();
    setServerUrlState(url);
    setIsPinging(true);
    const result = await pingServer(url);
    setPingResult(result);
    setIsPinging(false);
  };

  useEffect(() => {
    void refreshConnection();
    fetchSystemStats().then(setSystemStats).catch(() => {});

    fetchSettings()
      .then((data) => {
        if (data.auto_answer_delay) {
          const val = Number(data.auto_answer_delay);
          if (!isNaN(val)) {
            setAutoAnswerDelay(val);
            void syncAutoAnswerDelayToNative(val);
          }
        }
      })
      .catch(() => {});

    void syncAutoAnswerDelayToNative(Number(localStorage.getItem('tenra_auto_delay')) || 5);

    fetchVoIPConfig()
      .then((data) => {
        if (data && data.sip_server !== undefined) {
          setVoipConfig(data);
          if (typeof data.gsm_auto_answer === 'boolean') {
            setGsmAutoAnswer(data.gsm_auto_answer);
            void syncGsmAutoAnswerToNative(data.gsm_auto_answer);
          }
        }
      })
      .catch(() => {});

    void syncGsmAutoAnswerToNative(localStorage.getItem('tenra_gsm_auto_answer') === '1');

    const interval = setInterval(() => {
      void refreshConnection();
      fetchSystemStats().then(setSystemStats).catch(() => {});
      fetchVoIPConfig()
        .then((data) => {
          if (data) setVoipConfig(data);
        })
        .catch(() => {});
    }, 8000);
    return () => clearInterval(interval);
  }, []);

  const handleGsmAutoAnswerToggle = async (enabled: boolean) => {
    setGsmAutoAnswer(enabled);
    await syncGsmAutoAnswerToNative(enabled);
    try {
      await saveVoIPConfig({ ...voipConfig, gsm_auto_answer: enabled });
      setVoipConfig((prev: any) => ({ ...prev, gsm_auto_answer: enabled }));
    } catch {
      /* native prefs yeter */
    }
  };

  const handleSaveVoip = async () => {
    setIsSavingVoip(true);
    try {
      const payload = { ...voipConfig, gsm_auto_answer: gsmAutoAnswer };
      const res = await saveVoIPConfig(payload);
      setVoipMsg('SIP ayarları kaydedildi.');
      if (res.config) setVoipConfig(res.config);
      await syncGsmAutoAnswerToNative(gsmAutoAnswer);
    } catch (err: any) {
      setVoipMsg('Hata: ' + err.message);
    } finally {
      setIsSavingVoip(false);
      setTimeout(() => setVoipMsg(null), 4000);
    }
  };

  const handleApplyLocalLab = async () => {
    try {
      const res = await applyVoIPLocalLab();
      if (res.config) setVoipConfig(res.config);
      setGsmAutoAnswer(false);
      await syncGsmAutoAnswerToNative(false);
      setVoipMsg(res.message || 'Yerel lab ayarları hazır.');
    } catch (err: any) {
      setVoipMsg('Lab hatası: ' + err.message);
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
      setVoipMsg('Hata: ' + err.message);
    }
    setTimeout(() => setVoipMsg(null), 5000);
  };

  const handleDelayChange = (delay: number) => {
    setAutoAnswerDelay(delay);
    void syncAutoAnswerDelayToNative(delay);
    saveServerSettings({ auto_answer_delay: delay }).catch(() => {});
  };

  return (
    <div className="settings-container">
      <div className="settings-header">
        <div className="flex items-center space-x-2">
          <Settings className="w-6 h-6 text-cyan-400" />
          <h2>Ayarlar</h2>
        </div>
        <p className="settings-sub">
          Ev sunucusu, SIP hattı ve asistan durumu — bağlantı otomatik yerel
        </p>
      </div>

      {/* Otomatik yerel bağlantı — seçim yok */}
      <div className="settings-card">
        <div className="card-title">
          <Server className="w-5 h-5 text-indigo-400 mr-2" />
          <span>Ev Sunucusu</span>
        </div>
        <p className="card-desc">
          Uygulama her zaman aynı ağdaki PC’ye bağlanır. Wi‑Fi / Tailscale / cloud seçimi yok.
        </p>

        <div className="ping-status-box ping-ok" style={{ marginBottom: '0.75rem' }}>
          <span className="text-xs text-slate-300">
            Adres: <code>{serverUrl}</code>
          </span>
          <button
            type="button"
            className="btn-ping"
            onClick={() => void refreshConnection()}
            disabled={isPinging}
            title="Yenile"
            style={{ marginLeft: 'auto' }}
          >
            <RefreshCw className={`w-4 h-4 ${isPinging ? 'spin' : ''}`} />
          </button>
        </div>

        {pingResult && (
          <div className={`ping-status-box ${pingResult.ok ? 'ping-ok' : 'ping-err'}`}>
            {pingResult.ok ? (
              <>
                <CheckCircle2 className="w-4 h-4 text-emerald-400 mr-1.5" />
                <span>
                  Bağlantı başarılı — gecikme: <strong>{pingResult.latencyMs} ms</strong>
                </span>
              </>
            ) : (
              <>
                <XCircle className="w-4 h-4 text-rose-400 mr-1.5" />
                <span>Sunucuya ulaşılamadı. PC’de Tenra sunucusunun açık olduğundan emin ol.</span>
              </>
            )}
          </div>
        )}
      </div>

      {/* GSM opsiyonel — deneme araması Canlı Arama’da */}
      <div className="settings-card">
        <div className="card-title">
          <Smartphone className="w-5 h-5 text-amber-400 mr-2" />
          <span>GSM otomatik cevap (opsiyonel)</span>
        </div>
        <p className="card-desc">
          Tenra 2.0 birincil yol SIP. Bu anahtar kapalı kalsın; eski hoparlör yolu yalnızca
          gerekirse açılsın. Deneme araması için Canlı Arama sekmesini kullan.
        </p>

        <div className="setting-row">
          <div>
            <label className="font-semibold block">CallReceiver açık</label>
            <span className="text-xs text-slate-400">Kapalı = önerilen (derste hoparlör yok)</span>
          </div>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={gsmAutoAnswer}
              onChange={(e) => void handleGsmAutoAnswerToggle(e.target.checked)}
            />
            {gsmAutoAnswer ? 'Açık' : 'Kapalı'}
          </label>
        </div>

        {gsmAutoAnswer && (
          <div className="setting-row">
            <div>
              <label className="font-semibold block">Cevap gecikmesi</label>
              <span className="text-xs text-slate-400">Kaç saniye sonra otomatik açılsın</span>
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
        )}
      </div>

      {/* SIP */}
      <div className="settings-card">
        <div className="card-title">
          <PhoneCall className="w-5 h-5 text-purple-400 mr-2" />
          <span>SIP / VoIP (birincil hat)</span>
        </div>
        <p className="card-desc">
          Yerel Asterisk + MicroSIP lab, sonra NetGSM. Ses PC’de RTP ile akar.
        </p>

        <div className="space-y-3">
          <button type="button" className="btn-trigger-gsm" onClick={() => void handleApplyLocalLab()}>
            Yerel lab ayarlarını doldur (100 / 101)
          </button>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">SIP Sunucu</label>
              <input
                type="text"
                className="tenra-input text-sm"
                value={voipConfig.sip_server || ''}
                onChange={(e) => setVoipConfig({ ...voipConfig, sip_server: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">Sunucu Port</label>
              <input
                type="number"
                className="tenra-input text-sm"
                value={voipConfig.sip_port || 5060}
                onChange={(e) => setVoipConfig({ ...voipConfig, sip_port: Number(e.target.value) })}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">Dahili / Kullanıcı</label>
              <input
                type="text"
                className="tenra-input text-sm"
                value={voipConfig.sip_user || ''}
                onChange={(e) => setVoipConfig({ ...voipConfig, sip_user: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">SIP Şifresi</label>
              <input
                type="password"
                className="tenra-input text-sm"
                value={voipConfig.sip_password || ''}
                onChange={(e) => setVoipConfig({ ...voipConfig, sip_password: e.target.value })}
              />
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">Bu PC IP</label>
              <input
                type="text"
                className="tenra-input text-sm"
                value={voipConfig.sip_my_ip || ''}
                onChange={(e) => setVoipConfig({ ...voipConfig, sip_my_ip: e.target.value })}
              />
            </div>
            <div>
              <label className="text-xs text-slate-300 font-semibold block mb-1">Yerel bind port</label>
              <input
                type="number"
                className="tenra-input text-sm"
                value={voipConfig.sip_bind_port || 5062}
                onChange={(e) =>
                  setVoipConfig({ ...voipConfig, sip_bind_port: Number(e.target.value) })
                }
              />
            </div>
          </div>

          <div className="flex flex-wrap gap-2 items-center pt-2">
            <button className="btn-trigger-gsm" onClick={handleSaveVoip} disabled={isSavingVoip}>
              Kaydet
            </button>
            <button
              className={`px-3 py-1.5 rounded text-xs font-semibold flex items-center transition ${
                voipConfig.is_running
                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                  : 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
              }`}
              onClick={() => void handleToggleVoip()}
            >
              {voipConfig.is_running ? (
                <>
                  <Square className="w-3.5 h-3.5 mr-1" />
                  SIP Durdur
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 mr-1" />
                  SIP Başlat
                </>
              )}
            </button>
            <span className="text-xs text-slate-400 ml-auto">
              Durum:{' '}
              <strong>
                {voipConfig.last_status || (voipConfig.is_running ? 'Aktif' : 'Durduruldu')}
              </strong>
            </span>
          </div>

          {voipMsg && (
            <div className="text-xs font-semibold text-cyan-300 bg-cyan-950/40 p-2 rounded border border-cyan-800/40">
              {voipMsg}
            </div>
          )}
        </div>
      </div>

      {systemStats && (
        <div className="settings-card">
          <div className="card-title">
            <Cpu className="w-5 h-5 text-cyan-400 mr-2" />
            <span>Donanım ve model</span>
          </div>
          <div className="stats-grid">
            <div className="stat-box">
              <span className="stat-label">GPU</span>
              <span className="stat-val">{systemStats.gpu_name}</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">LLM</span>
              <span className="stat-val">{systemStats.llm_model}</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Ses</span>
              <span className="stat-val">{systemStats.active_voice_model}</span>
            </div>
            <div className="stat-box">
              <span className="stat-label">Çağrı</span>
              <span className="stat-val">{systemStats.total_calls}</span>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

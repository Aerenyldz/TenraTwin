// TENRA Mobile Companion App Logic - Two-Way Interactive Voice & Text Call
const API_BASE = window.location.origin;

// State Management
let isCallActive = false;
let callHistory = [];
let callAudioFilenames = [];
let currentAudioPlayer = null;
let speechRecognizer = null;
let isRecordingVoice = false;

// Tab Switching
function initTabs() {
  const navBtns = document.querySelectorAll('.nav-item');
  const tabs = document.querySelectorAll('.tab-content');

  navBtns.forEach((btn) => {
    btn.addEventListener('click', () => {
      navBtns.forEach((b) => b.classList.remove('active'));
      tabs.forEach((t) => t.classList.remove('active'));

      btn.classList.add('active');
      const targetTab = document.getElementById(btn.dataset.tab);
      if (targetTab) targetTab.classList.add('active');

      if (btn.dataset.tab === 'tab-calls') loadCalls();
      if (btn.dataset.tab === 'tab-system') loadSystemInfo();
    });
  });
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. İKİ TARAFLI CANLI ÇAĞRI (Live Interactive Call)
// ─────────────────────────────────────────────────────────────────────────────

async function toggleLiveCall() {
  if (!isCallActive) {
    await startLiveCall();
  } else {
    await endLiveCall();
  }
}

async function startLiveCall() {
  const callerName = document.getElementById('live-caller-name').value.trim() || 'Arayan Kişi';
  const btn = document.getElementById('btn-toggle-call');
  const btnIcon = document.getElementById('call-btn-icon');
  const btnText = document.getElementById('call-btn-text');
  const container = document.getElementById('live-dialogue-container');
  const inputArea = document.getElementById('live-input-area');

  btn.disabled = true;
  btnText.textContent = 'Bağlanıyor...';

  // Unlock mobile audio playback on touch gesture
  try {
    if (!currentAudioPlayer) {
      currentAudioPlayer = new Audio();
    }
    // Dummy load to prime the audio pipeline
    currentAudioPlayer.load();
  } catch (e) {
    console.warn('Audio prime warning:', e);
  }

  // Instant visual feedback for user
  container.innerHTML = `
    <div class="bubble bubble-assistant" style="border-color: var(--accent-blue);">
      <div style="font-weight: 600; color: #38bdf8; margin-bottom: 4px;">📞 Çağrı Bağlanıyor...</div>
      <div style="font-size: 0.85rem; color: var(--text-muted);">Ahmet Eren'in ses klonu ve asistanı hazırlanıyor...</div>
    </div>
  `;

  try {
    const res = await fetch(`${API_BASE}/api/call/start`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ caller_name: callerName })
    });

    if (!res.ok) {
      const errText = await res.text();
      throw new Error(`Sunucu hatası (${res.status}): ${errText}`);
    }
    const data = await res.json();

    isCallActive = true;
    callHistory = [{ role: 'assistant', content: data.greeting }];
    callAudioFilenames = data.audio_filename ? [data.audio_filename] : [];

    // UI Güncelle
    btn.className = 'btn-call-end';
    btnIcon.textContent = '🔴';
    btnText.textContent = 'Görüşmeyi Bitir';
    inputArea.style.display = 'flex';

    // Diyalog alanını temizle ve asistanın ilk selamını yaz
    container.innerHTML = '';
    appendAssistantBubble(data.greeting, data.audio_url);

    // Sesi otomatik oynat
    if (data.audio_url) {
      playAssistantAudio(data.audio_url);
    }

  } catch (err) {
    alert('Arama başlatılırken hata oluştu: ' + err.message);
    btn.className = 'btn-call-start';
    btnIcon.textContent = '📞';
    btnText.textContent = 'Aramayı Başlat';
    container.innerHTML = `
      <div class="bubble bubble-assistant" style="border-color: #ef4444; color: #f87171;">
        ❌ Bağlantı hatası: ${escapeHtml(err.message)}
      </div>
    `;
  } finally {
    btn.disabled = false;
  }
}

async function endLiveCall() {
  const callerName = document.getElementById('live-caller-name').value.trim() || 'Arayan Kişi';
  const btn = document.getElementById('btn-toggle-call');
  const btnIcon = document.getElementById('call-btn-icon');
  const btnText = document.getElementById('call-btn-text');
  const container = document.getElementById('live-dialogue-container');
  const inputArea = document.getElementById('live-input-area');

  btn.disabled = true;
  btnText.textContent = 'Özet Çıkarılıyor...';

  try {
    const res = await fetch(`${API_BASE}/api/call/end`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        caller_name: callerName,
        history: callHistory,
        audio_filenames: callAudioFilenames
      })
    });

    if (!res.ok) throw new Error('Görüşme sonlandırılamadı');
    const data = await res.json();

    isCallActive = false;
    btn.className = 'btn-call-start';
    btnIcon.textContent = '📞';
    btnText.textContent = 'Yeni Arama Başlat';
    inputArea.style.display = 'none';

    // Bitiş özet kartını göster
    const summaryCard = document.createElement('div');
    summaryCard.className = 'bubble bubble-assistant';
    summaryCard.style.borderColor = 'var(--accent-cyan)';
    summaryCard.innerHTML = `
      <div style="font-weight: 700; color: #34d399; margin-bottom: 6px;">📋 Görüşme Tamamlandı ve Kaydedildi!</div>
      <div style="font-size: 0.85rem; margin-bottom: 4px;"><strong>Özet:</strong> ${escapeHtml(data.summary || 'Özet çıkarıldı.')}</div>
      <div style="font-size: 0.75rem; color: var(--text-muted); margin-top: 6px;">
        💡 Bu arama tüm ses kaydıyla birlikte <strong>"Çağrılar"</strong> sekmesine eklendi.
      </div>
    `;
    container.appendChild(summaryCard);
    container.scrollTop = container.scrollHeight;

    // Çağrılar listesini otomatik yenile
    loadCalls();

  } catch (err) {
    alert('Sonlandırma hatası: ' + err.message);
    btn.disabled = false;
    btnText.textContent = 'Görüşmeyi Bitir';
  } finally {
    btn.disabled = false;
  }
}

async function sendLiveMessage() {
  if (!isCallActive) return;

  const input = document.getElementById('live-user-input');
  const message = input.value.trim();
  if (!message) return;

  const callerName = document.getElementById('live-caller-name').value.trim() || 'Arayan Kişi';
  const container = document.getElementById('live-dialogue-container');

  // 1. Kullanıcı balonunu ekle
  appendUserBubble(message);
  input.value = '';
  callHistory.push({ role: 'user', content: message });

  // 2. Yükleniyor balonu
  const loadingId = 'loading-' + Date.now();
  const loadingEl = document.createElement('div');
  loadingEl.id = loadingId;
  loadingEl.className = 'bubble bubble-assistant';
  loadingEl.innerHTML = '<span style="color: var(--text-muted);">💭 Ahmet düşünüyor ve seslendiriyor...</span>';
  container.appendChild(loadingEl);
  container.scrollTop = container.scrollHeight;

  try {
    const res = await fetch(`${API_BASE}/api/call/message`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        caller_name: callerName,
        message: message,
        history: callHistory
      })
    });

    if (!res.ok) throw new Error('Cevap alınamadı');
    const data = await res.json();

    // Yükleniyor'u kaldır
    const loadItem = document.getElementById(loadingId);
    if (loadItem) loadItem.remove();

    // 3. Asistan yanıt balonunu ekle
    callHistory.push({ role: 'assistant', content: data.reply });
    if (data.audio_filename) {
      callAudioFilenames.push(data.audio_filename);
    }

    appendAssistantBubble(data.reply, data.audio_url);

    // 4. Asistanın sesini hoparlörden çal
    if (data.audio_url) {
      playAssistantAudio(data.audio_url);
    }

    // Arayan veda ettiyse görüşmeyi bitirmeyi öner
    if (/(görüşürüz|baybay|kapatıyorum|eyvallah|hadi görüşürüz)/i.test(message)) {
      setTimeout(() => {
        endLiveCall();
      }, 5000);
    }

  } catch (err) {
    const loadItem = document.getElementById(loadingId);
    if (loadItem) {
      loadItem.innerHTML = `<span style="color: #ef4444;">❌ Hata: ${err.message}</span>`;
    }
  }
}

function handleInputKey(e) {
  if (e.key === 'Enter') {
    e.preventDefault();
    sendLiveMessage();
  }
}

function appendUserBubble(text) {
  const container = document.getElementById('live-dialogue-container');
  const bubble = document.createElement('div');
  bubble.className = 'bubble bubble-user';
  bubble.innerHTML = `
    <div>${escapeHtml(text)}</div>
    <div class="bubble-meta"><span>Siz</span><span>${new Date().toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span></div>
  `;
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
}

function appendAssistantBubble(text, audioUrl) {
  const container = document.getElementById('live-dialogue-container');
  const bubble = document.createElement('div');
  bubble.className = 'bubble bubble-assistant';

  let replayBtn = '';
  if (audioUrl) {
    replayBtn = `<button class="btn-replay-audio" onclick="playAssistantAudio('${audioUrl}')">🔊 Yeniden Dinle</button>`;
  }

  bubble.innerHTML = `
    <div>${escapeHtml(text)}</div>
    <div class="bubble-meta">
      <span>🤖 Ahmet Eren (Genç Ahmet)</span>
      ${replayBtn}
    </div>
  `;
  container.appendChild(bubble);
  container.scrollTop = container.scrollHeight;
}

function playAssistantAudio(audioUrl) {
  try {
    if (!currentAudioPlayer) {
      currentAudioPlayer = new Audio();
    }
    currentAudioPlayer.pause();
    currentAudioPlayer.src = audioUrl;
    const playPromise = currentAudioPlayer.play();
    if (playPromise !== undefined) {
      playPromise.catch((err) => {
        console.warn('Otomatik ses çalma engellendi (kullanıcı etkileşimi gerekebilir):', err);
      });
    }
  } catch (e) {
    console.error('Audio play hatası:', e);
  }
}

// 🎙️ Mikrofon ile Konuşma (Web Speech API)
function toggleVoiceInput() {
  const micBtn = document.getElementById('btn-live-mic');
  const micIcon = document.getElementById('mic-icon');
  const inputEl = document.getElementById('live-user-input');

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;

  if (!SpeechRecognition) {
    alert('Tarayıcınız doğrudan mikrofonla konuşmayı desteklemiyor. Lütfen Chrome veya Safari kullanın ya da mesajınızı yazın.');
    inputEl.focus();
    return;
  }

  if (isRecordingVoice) {
    if (speechRecognizer) speechRecognizer.stop();
    return;
  }

  try {
    speechRecognizer = new SpeechRecognition();
    speechRecognizer.lang = 'tr-TR';
    speechRecognizer.continuous = false;
    speechRecognizer.interimResults = false;

    speechRecognizer.onstart = () => {
      isRecordingVoice = true;
      micBtn.classList.add('recording');
      micIcon.textContent = '⏹️';
      inputEl.placeholder = 'Dinliyorum... Konuşun...';
    };

    speechRecognizer.onresult = (event) => {
      const spokenText = event.results[0][0].transcript;
      inputEl.value = spokenText;
      // Otomatik olarak gönder
      sendLiveMessage();
    };

    speechRecognizer.onerror = (event) => {
      console.warn('Ses tanıma hatası:', event.error);
    };

    speechRecognizer.onend = () => {
      isRecordingVoice = false;
      micBtn.classList.remove('recording');
      micIcon.textContent = '🎙️';
      inputEl.placeholder = 'Konuş veya mesajını yaz...';
    };

    speechRecognizer.start();

  } catch (err) {
    console.error('Speech init hatası:', err);
    isRecordingVoice = false;
    micBtn.classList.remove('recording');
    micIcon.textContent = '🎙️';
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 2. ÇAĞRI GEÇMİŞİ VE KAYITLAR (Calls Tab)
// ─────────────────────────────────────────────────────────────────────────────

async function loadCalls() {
  const container = document.getElementById('calls-list');
  if (!container) return;

  try {
    const res = await fetch(`${API_BASE}/api/calls`);
    if (!res.ok) throw new Error('API Hatası');
    const calls = await res.json();

    if (!calls || calls.length === 0) {
      container.innerHTML = `
        <div style="text-align: center; padding: 40px 20px; color: var(--text-muted);">
          <div style="font-size: 2.2rem; margin-bottom: 8px;">📭</div>
          Henüz gelen bir çağrı notu bulunmuyor.
        </div>
      `;
      return;
    }

    container.innerHTML = calls.map((c) => {
      const hasAudio = c.audio_file && c.audio_file.length > 0;
      const audioUrl = hasAudio ? `${API_BASE}/api/calls/${c.id}/audio` : '';

      const urgencyKey = (c.urgency || 'normal').toLowerCase();
      let badgeLabel = '📌 NORMAL';
      if (urgencyKey === 'onemli' || urgencyKey === 'acil') {
        badgeLabel = '🚨 ÖNEMLİ';
      } else if (urgencyKey === 'oylesine' || urgencyKey === 'onemsiz') {
        badgeLabel = '☕ ÖYLESİNE';
      }

      return `
        <div class="call-card">
          <div class="call-top">
            <div>
              <div class="caller-name">${escapeHtml(c.caller_name)}</div>
              <div class="call-time">${escapeHtml(c.timestamp)}</div>
            </div>
            <span class="urgency-badge ${urgencyKey}">${badgeLabel}</span>
          </div>

          <div class="call-summary">
            <strong>Özet:</strong> ${escapeHtml(c.summary)}
          </div>

          ${hasAudio ? `
            <div class="audio-player-box">
              <audio controls preload="none" src="${audioUrl}">
                Tarayıcınız ses oynatmayı desteklemiyor.
              </audio>
            </div>
          ` : ''}

          <button class="transcript-toggle" onclick="toggleTranscript(${c.id})">
            <span>📜</span> Konuşma Dökümünü Gör
          </button>
          <div id="transcript-${c.id}" class="transcript-body">
            ${escapeHtml(c.transcript || 'Döküm bulunamadı.')}
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    container.innerHTML = `
      <div style="text-align: center; padding: 30px; color: #f87171;">
        Çağrılar yüklenirken bağlantı hatası oluştu.
      </div>
    `;
  }
}

function toggleTranscript(id) {
  const el = document.getElementById(`transcript-${id}`);
  if (el) el.classList.toggle('open');
}

// ─────────────────────────────────────────────────────────────────────────────
// 3. ASİSTAN DURUMU (Status Management)
// ─────────────────────────────────────────────────────────────────────────────

const STATUS_DETAILS = {
  Okulda: 'Ahmet şu an derste, önemli bir şey varsa not alıyorum.',
  Sporda: 'Ahmet sporda, antrenman bitince arar. Not bırakayım mı?',
  Toplantıda: 'Toplantıdayım, acil değilse mesaj bırakın.',
  Müsait: 'Ahmet müsait, telefonu kendisine aktarıyorum.'
};

async function loadStatus() {
  try {
    const res = await fetch(`${API_BASE}/api/status`);
    if (res.ok) {
      const data = await res.json();
      updateStatusUI(data.status, data.status_detail);
    }
  } catch (err) {
    console.warn('Status yüklenemedi:', err);
  }
}

function updateStatusUI(status, detail) {
  document.querySelectorAll('.status-btn').forEach((btn) => {
    btn.classList.toggle('active', btn.dataset.status === status);
  });
  const hintEl = document.getElementById('current-status-hint');
  if (hintEl) {
    hintEl.textContent = `⚡ Aktif Cevap: "${detail}"`;
  }
}

async function setStatus(newStatus) {
  const detail = STATUS_DETAILS[newStatus] || 'Ahmet şu an müsait değil.';
  updateStatusUI(newStatus, detail);

  try {
    await fetch(`${API_BASE}/api/status`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status: newStatus, status_detail: detail })
    });
  } catch (err) {
    console.error('Status güncellenemedi:', err);
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 4. SES TESTİ VE SENTEZİ (Voice Test)
// ─────────────────────────────────────────────────────────────────────────────

async function runVoiceTest() {
  const input = document.getElementById('test-text');
  const btn = document.getElementById('btn-synthesize');
  const audioEl = document.getElementById('test-audio-player');
  const text = input.value.trim();

  if (!text) return;

  btn.disabled = true;
  btn.innerHTML = '⏳ Ses Üretiliyor...';

  try {
    const res = await fetch(`${API_BASE}/api/synthesize`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text })
    });

    if (res.ok) {
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      audioEl.src = url;
      audioEl.style.display = 'block';
      audioEl.play();
    } else {
      alert('Ses üretimi başarısız oldu.');
    }
  } catch (err) {
    alert('Sunucuya bağlanılamadı.');
  } finally {
    btn.disabled = false;
    btn.innerHTML = '🔊 Sentezle & Dinle';
  }
}

function setTestPrompt(text) {
  const el = document.getElementById('test-text');
  if (el) {
    el.value = text;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 5. SUNUCU DURUMU (System Information)
// ─────────────────────────────────────────────────────────────────────────────

async function loadSystemInfo() {
  const container = document.getElementById('system-info-body');
  if (!container) return;

  try {
    const res = await fetch(`${API_BASE}/api/system`);
    if (res.ok) {
      const d = await res.json();
      container.innerHTML = `
        <div class="info-row">
          <span class="info-label">Ekran Kartı</span>
          <span class="info-val">${d.gpu_name || 'NVIDIA RTX'}</span>
        </div>
        <div class="info-row">
          <span class="info-label">Aktif Ses Modeli</span>
          <span class="info-val" style="color: var(--accent-cyan);">${d.active_voice_model || 'Genç Ahmet (Fish Audio)'}</span>
        </div>
        <div class="info-row">
          <span class="info-label">LLM Zihin Modeli</span>
          <span class="info-val">${d.llm_model || 'hermes3:8b'}</span>
        </div>
        <div class="info-row">
          <span class="info-label">Whisper STT</span>
          <span class="info-val">Faster-Whisper (Türkçe)</span>
        </div>
        <div class="info-row">
          <span class="info-label">Kayıtlı Toplam Çağrı</span>
          <span class="info-val">${d.total_calls || 0}</span>
        </div>
        <div class="info-row">
          <span class="info-label">Sunucu Durumu</span>
          <span class="info-val" style="color: #34d399;">● Çevrimiçi (Port 8008)</span>
        </div>
      `;
    }
  } catch (err) {
    container.innerHTML = '<div style="color: #f87171; padding: 10px;">Bilgiler alınamadı.</div>';
  }
}

// Utilities
function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Global function bindings to ensure onclick handlers work across all browsers
window.toggleLiveCall = toggleLiveCall;
window.startLiveCall = startLiveCall;
window.endLiveCall = endLiveCall;
window.sendLiveMessage = sendLiveMessage;
window.toggleVoiceInput = toggleVoiceInput;
window.handleInputKey = handleInputKey;
window.playAssistantAudio = playAssistantAudio;
window.setStatus = setStatus;
window.loadCalls = loadCalls;
window.toggleTranscript = toggleTranscript;
window.runVoiceTest = runVoiceTest;
window.setTestPrompt = setTestPrompt;
window.loadSystemInfo = loadSystemInfo;

// Unregister any lingering Service Worker
if ('serviceWorker' in navigator) {
  navigator.serviceWorker.getRegistrations().then((regs) => {
    regs.forEach((r) => r.unregister());
  });
}

// Initial Boot
function bootApp() {
  initTabs();
  loadStatus();
  loadCalls();

  // Polling for new calls every 10 seconds
  setInterval(() => {
    const activeTab = document.querySelector('.tab-content.active');
    if (activeTab && activeTab.id === 'tab-calls') {
      loadCalls();
    }
  }, 10000);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', bootApp);
} else {
  bootApp();
}

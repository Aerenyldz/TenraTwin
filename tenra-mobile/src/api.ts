import type { AssistantStatus, CallRecord, DialogueMessage } from './types';

const STORAGE_KEY = 'tenra_server_url';
export const DEFAULT_TAILSCALE_URL = 'http://100.93.198.21:8008';
export const DEFAULT_LOCAL_URL = 'http://192.168.1.100:8008';

export function getServerUrl(): string {
  const saved = localStorage.getItem(STORAGE_KEY);
  if (saved) return saved.replace(/\/+$/, '');
  
  // Eğer tarayıcı veya PWA içindeyse, açıldığı adresi (Cloudflare HTTPS veya yerel IP) doğrudan kullan
  if (typeof window !== 'undefined' && window.location && window.location.origin) {
    if (window.location.protocol.startsWith('http') && !window.location.origin.includes(':5173')) {
      return window.location.origin.replace(/\/+$/, '');
    }
  }
  return DEFAULT_LOCAL_URL;
}


export function setServerUrl(url: string) {
  const cleaned = url.replace(/\/+$/, '');
  localStorage.setItem(STORAGE_KEY, cleaned);
}

export async function pingServer(targetUrl?: string): Promise<{ ok: boolean; latencyMs: number }> {
  const base = targetUrl || getServerUrl();
  const start = performance.now();
  try {
    const res = await fetch(`${base}/api/status`, { signal: AbortSignal.timeout(4000) });
    const latencyMs = Math.round(performance.now() - start);
    return { ok: res.ok, latencyMs };
  } catch {
    return { ok: false, latencyMs: 0 };
  }
}

export async function fetchStatus(): Promise<AssistantStatus> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/status`);
  if (!res.ok) throw new Error('Durum alınamadı');
  return res.json();
}

export async function updateStatus(status: string, detail: string): Promise<void> {
  const base = getServerUrl();
  await fetch(`${base}/api/status`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, status_detail: detail })
  });
}

export async function fetchCalls(): Promise<CallRecord[]> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/calls`);
  if (!res.ok) throw new Error('Çağrılar alınamadı');
  return res.json();
}

export async function startCall(callerName: string): Promise<{ greeting: string; audio_url?: string; audio_filename?: string }> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/call/start`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ caller_name: callerName })
  });
  if (!res.ok) throw new Error('Arama başlatılamadı');
  return res.json();
}

export async function sendCallMessage(
  callerName: string,
  message: string,
  history: DialogueMessage[]
): Promise<{ reply: string; audio_url?: string; audio_filename?: string }> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/call/message`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      caller_name: callerName,
      message,
      history
    })
  });
  if (!res.ok) throw new Error('Cevap alınamadı');
  return res.json();
}

export async function endCall(
  callerName: string,
  history: DialogueMessage[],
  audioFilenames: string[]
): Promise<{ summary: string; urgency: string; call_id?: number }> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/call/end`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      caller_name: callerName,
      history,
      audio_filenames: audioFilenames
    })
  });
  if (!res.ok) throw new Error('Görüşme sonlandırılamadı');
  return res.json();
}

export function formatAudioUrl(urlOrPath: string): string {
  if (!urlOrPath) return '';
  if (urlOrPath.startsWith('http')) return urlOrPath;
  const base = getServerUrl();
  if (urlOrPath.startsWith('/')) return `${base}${urlOrPath}`;
  return `${base}/${urlOrPath}`;
}

export async function deleteCall(callId: number): Promise<boolean> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/calls/${callId}`, { method: 'DELETE' });
  return res.ok;
}

export async function notifyGsmIncoming(callerNumber: string): Promise<any> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/gsm/incoming`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ caller_number: callerNumber, action: 'manual_trigger' })
  });
  return res.json();
}

export async function fetchSystemStats(): Promise<any> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/system`);
  if (!res.ok) throw new Error('Sistem durumu alınamadı');
  return res.json();
}

export async function fetchSettings(): Promise<Record<string, string>> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/settings`);
  if (!res.ok) return {};
  return res.json();
}

export async function saveServerSettings(settings: Record<string, any>): Promise<any> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/settings`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings })
  });
  return res.json();
}

export async function fetchVoIPConfig(): Promise<any> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/voip/config`);
  if (!res.ok) return {};
  return res.json();
}

export async function saveVoIPConfig(config: Record<string, any>): Promise<any> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/voip/config`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  });
  return res.json();
}

export async function startVoIPGateway(): Promise<any> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/voip/start`, { method: 'POST' });
  return res.json();
}

export async function stopVoIPGateway(): Promise<any> {
  const base = getServerUrl();
  const res = await fetch(`${base}/api/voip/stop`, { method: 'POST' });
  return res.json();
}



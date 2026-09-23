import type { AssistantStatus, CallRecord, DialogueMessage } from './types';
import { syncServerUrlToNative } from './nativePrefs';

const STORAGE_KEY = 'tenra_server_url';
export const DEFAULT_TAILSCALE_URL = 'http://100.93.198.21:8008';
export const DEFAULT_LOCAL_URL = 'http://192.168.1.100:8008';

/** Sayfa sunucudan geliyorsa origin; değilse ev Wi‑Fi varsayılanı. */
export function resolveLocalServerUrl(): string {
  if (typeof window !== 'undefined' && window.location?.origin) {
    const origin = window.location.origin.replace(/\/+$/, '');
    if (
      window.location.protocol.startsWith('http') &&
      !origin.includes(':5173') &&
      !origin.includes('localhost') &&
      !origin.includes('127.0.0.1')
    ) {
      return origin;
    }
    // Vite / localhost önizleme → gerçek ev sunucusu
    if (origin.includes(':5173') || origin.includes('localhost') || origin.includes('127.0.0.1')) {
      return DEFAULT_LOCAL_URL;
    }
  }
  return DEFAULT_LOCAL_URL;
}

export function getServerUrl(): string {
  return resolveLocalServerUrl();
}

export function setServerUrl(url: string) {
  const cleaned = url.replace(/\/+$/, '');
  localStorage.setItem(STORAGE_KEY, cleaned);
  void syncServerUrlToNative(cleaned);
}

/** Eski Tailscale/cloud seçimini sil, yereli yaz, native'e sync. */
export function ensureLocalServerUrl(): string {
  const url = resolveLocalServerUrl();
  setServerUrl(url);
  return url;
}

async function apiFetch(path: string, init?: RequestInit): Promise<Response> {
  const base = getServerUrl();
  return fetch(`${base}${path}`, init);
}

export async function pingServer(targetUrl?: string): Promise<{ ok: boolean; latencyMs: number }> {
  const base = targetUrl || getServerUrl();
  const start = performance.now();
  try {
    const res = await fetch(`${base}/api/status`, {
      signal: AbortSignal.timeout(4000),
    });
    const latencyMs = Math.round(performance.now() - start);
    return { ok: res.ok, latencyMs };
  } catch {
    return { ok: false, latencyMs: 0 };
  }
}

export async function fetchStatus(): Promise<AssistantStatus> {
  const res = await apiFetch('/api/status');
  if (!res.ok) throw new Error('Durum alınamadı');
  return res.json();
}

export async function updateStatus(status: string, detail: string): Promise<void> {
  await apiFetch('/api/status', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ status, status_detail: detail })
  });
}

export async function fetchCalls(): Promise<CallRecord[]> {
  const res = await apiFetch('/api/calls');
  if (!res.ok) throw new Error('Çağrılar alınamadı');
  return res.json();
}

export async function startCall(callerName: string): Promise<{ greeting: string; audio_url?: string; audio_filename?: string }> {
  const res = await apiFetch('/api/call/start', {
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
  const res = await apiFetch('/api/call/message', {
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

/** Mikrofon kaydını Whisper ile metne çevir. */
export async function transcribeCallAudio(blob: Blob): Promise<string> {
  const form = new FormData();
  const ext = blob.type.includes('ogg')
    ? 'ogg'
    : blob.type.includes('mp4') || blob.type.includes('m4a')
      ? 'm4a'
      : blob.type.includes('wav')
        ? 'wav'
        : 'webm';
  form.append('audio', blob, `mic.${ext}`);
  const res = await apiFetch('/api/call/transcribe', {
    method: 'POST',
    body: form,
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => '');
    throw new Error(detail || 'Ses anlaşılamadı');
  }
  const data = await res.json();
  return (data.text || '').trim();
}

export async function endCall(
  callerName: string,
  history: DialogueMessage[],
  audioFilenames: string[]
): Promise<{ summary: string; urgency: string; call_id?: number }> {
  const res = await apiFetch('/api/call/end', {
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
  const res = await apiFetch(`/api/calls/${callId}`, { method: 'DELETE' });
  return res.ok;
}

export async function notifyGsmIncoming(callerNumber: string): Promise<any> {
  const res = await apiFetch('/api/gsm/incoming', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ caller_number: callerNumber, action: 'manual_trigger' })
  });
  return res.json();
}

export async function fetchSystemStats(): Promise<any> {
  const res = await apiFetch('/api/system');
  if (!res.ok) throw new Error('Sistem durumu alınamadı');
  return res.json();
}

export async function fetchSettings(): Promise<Record<string, string>> {
  const res = await apiFetch('/api/settings');
  if (!res.ok) return {};
  return res.json();
}

export async function saveServerSettings(settings: Record<string, any>): Promise<any> {
  const res = await apiFetch('/api/settings', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ settings })
  });
  return res.json();
}

export async function fetchVoIPConfig(): Promise<any> {
  const res = await apiFetch('/api/voip/config');
  if (!res.ok) return {};
  return res.json();
}

export async function saveVoIPConfig(config: Record<string, any>): Promise<any> {
  const res = await apiFetch('/api/voip/config', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config)
  });
  return res.json();
}

export async function startVoIPGateway(): Promise<any> {
  const res = await apiFetch('/api/voip/start', { method: 'POST' });
  return res.json();
}

export async function stopVoIPGateway(): Promise<any> {
  const res = await apiFetch('/api/voip/stop', { method: 'POST' });
  return res.json();
}

export async function applyVoIPLocalLab(): Promise<any> {
  const res = await apiFetch('/api/voip/local-lab', { method: 'POST' });
  return res.json();
}

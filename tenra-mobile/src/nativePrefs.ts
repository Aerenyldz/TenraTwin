/**
 * Capacitor native SharedPreferences köprüsü (TenraPrefsPlugin).
 * Web/PWA'da no-op fallback ile localStorage kullanılır.
 */
import { registerPlugin, Capacitor } from '@capacitor/core';

interface TenraPrefsPlugin {
  set(options: { key: string; value: string }): Promise<void>;
  get(options: { key: string }): Promise<{ value: string | null }>;
  setAudioMutex(options: { active: boolean; ttlMs?: number }): Promise<void>;
  isAudioMutexActive(): Promise<{ active: boolean }>;
}

const TenraPrefs = registerPlugin<TenraPrefsPlugin>('TenraPrefs');

export const NATIVE_KEYS = {
  serverUrl: 'tenra_server_url',
  autoDelay: 'auto_answer_delay',
  gsmAutoAnswer: 'gsm_auto_answer',
} as const;

export function isNativeApp(): boolean {
  try {
    return Capacitor.isNativePlatform();
  } catch {
    return false;
  }
}

export async function nativeSet(key: string, value: string): Promise<void> {
  localStorage.setItem(key, value);
  if (!isNativeApp()) return;
  try {
    await TenraPrefs.set({ key, value });
  } catch (e) {
    console.warn('[TenraPrefs] set failed:', e);
  }
}

export async function nativeGet(key: string): Promise<string | null> {
  if (isNativeApp()) {
    try {
      const res = await TenraPrefs.get({ key });
      if (res.value != null) return res.value;
    } catch (e) {
      console.warn('[TenraPrefs] get failed:', e);
    }
  }
  return localStorage.getItem(key);
}

export async function syncServerUrlToNative(url: string): Promise<void> {
  await nativeSet(NATIVE_KEYS.serverUrl, url);
  // CallReceiver alt anahtar
  if (isNativeApp()) {
    try {
      await TenraPrefs.set({ key: 'server_url', value: url });
    } catch {
      /* ignore */
    }
  }
}

export async function syncAutoAnswerDelayToNative(seconds: number): Promise<void> {
  const v = String(Math.max(3, Math.min(30, seconds)));
  localStorage.setItem('tenra_auto_delay', v);
  await nativeSet(NATIVE_KEYS.autoDelay, v);
}

/** Tenra 2.0: varsayılan kapalı. true = eski GSM hoparlör yolu. */
export async function syncGsmAutoAnswerToNative(enabled: boolean): Promise<void> {
  const v = enabled ? '1' : '0';
  localStorage.setItem('tenra_gsm_auto_answer', v);
  await nativeSet(NATIVE_KEYS.gsmAutoAnswer, v);
}

export async function isNativeAudioLocked(): Promise<boolean> {
  if (!isNativeApp()) return false;
  try {
    const res = await TenraPrefs.isAudioMutexActive();
    return !!res.active;
  } catch {
    return false;
  }
}

/** GSM native karşılama olayını dinle */
export function onGsmHandled(
  handler: (detail: { callerName: string; callerNumber: string; nativeAudioOwned: boolean }) => void
): () => void {
  const listener = (e: Event) => {
    const detail = (e as CustomEvent).detail || {};
    handler({
      callerName: detail.callerName || '',
      callerNumber: detail.callerNumber || '',
      nativeAudioOwned: detail.nativeAudioOwned !== false,
    });
  };
  window.addEventListener('tenra-gsm-handled', listener);
  return () => window.removeEventListener('tenra-gsm-handled', listener);
}

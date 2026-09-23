package ai.tenra.app;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.database.Cursor;
import android.media.AudioAttributes;
import android.media.AudioManager;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.os.SystemClock;
import android.provider.CallLog;
import android.provider.ContactsContract;
import android.telecom.TelecomManager;
import android.telephony.TelephonyManager;
import android.util.Log;
import android.view.KeyEvent;

import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;

/**
 * Gelen GSM aramasını yakalar, rehberi çözar, açar, hoparlörden yüksek sesle selamlar.
 * Karşı tarafın duyması için: hoparlör + STREAM_MUSIC (kulaklık kanalı değil).
 */
public class CallReceiver extends BroadcastReceiver {
    private static final String TAG = "TENRA_CallReceiver";
    private static volatile boolean isRinging = false;
    private static volatile boolean isOffhook = false;
    private static volatile long lastAnswerAt = 0;
    private static String incomingNumber = "";
    private static String callerName = "";
    private static MediaPlayer activePlayer = null;
    private static int lastCallId = -1;
    private static String lastServerBase = "";

    /** OFFHOOK gelmeden hazır olan ses — bağlantı oturunca çalınır */
    private static String pendingAudioUrl = null;
    private static String pendingName = "";
    private static String pendingNumber = "";
    private static int pendingCallId = -1;
    private static String pendingServer = "";
    private static Context appContext = null;

    @Override
    public void onReceive(Context context, Intent intent) {
        appContext = context.getApplicationContext();
        String action = intent.getAction();
        if (!TelephonyManager.ACTION_PHONE_STATE_CHANGED.equals(action)) return;

        String state = intent.getStringExtra(TelephonyManager.EXTRA_STATE);

        if (TelephonyManager.EXTRA_STATE_RINGING.equals(state)) {
            // Tenra 2.0: GSM otomatik cevap varsayılan KAPALI — SIP yolu birincil
            if (!isGsmAutoAnswerEnabled(context)) {
                Log.d(TAG, "GSM auto-answer KAPALI — CallReceiver pasif (SIP/yönetim modu)");
                return;
            }
            isRinging = true;
            isOffhook = false;

            String raw = intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER);
            incomingNumber = resolveBestNumber(context, raw);
            callerName = resolveContactName(context, incomingNumber);
            Log.d(TAG, "RINGING num=" + incomingNumber + " isim=" + callerName);

            final PendingResult pendingResult = goAsync();
            int delaySec = readAutoAnswerDelaySec(context);

            PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
            final PowerManager.WakeLock wakeLock;
            if (pm != null) {
                wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "TENRA:CallDelayWakeLock");
                wakeLock.acquire((delaySec + 10) * 1000L);
            } else {
                wakeLock = null;
            }

            new Handler(Looper.getMainLooper()).postDelayed(() -> {
                try {
                    if (isRinging) {
                        // Cevap anında numarayı yeniden çöz (Android bazen RINGING'de null verir)
                        incomingNumber = resolveBestNumber(context, incomingNumber);
                        callerName = resolveContactName(context, incomingNumber);
                        Log.d(TAG, "Cevap öncesi num=" + incomingNumber + " isim=" + callerName);
                        answerCall(context, incomingNumber, callerName);
                    }
                } catch (Exception e) {
                    Log.e(TAG, "Gecikmeli yanıt hatası: " + e.getMessage());
                } finally {
                    if (wakeLock != null && wakeLock.isHeld()) {
                        try { wakeLock.release(); } catch (Exception ignored) {}
                    }
                    try { pendingResult.finish(); } catch (Exception ignored) {}
                }
            }, delaySec * 1000L);

        } else if (TelephonyManager.EXTRA_STATE_OFFHOOK.equals(state)) {
            isRinging = false;
            isOffhook = true;
            Log.d(TAG, "OFFHOOK — görüşme aktif, hoparlör + bekleyen ses kontrol");
            forceSpeakerLoud(context);
            // Hat otursun diye kısa bekle, sonra bekleyen selamlamayı çal
            new Handler(Looper.getMainLooper()).postDelayed(() -> {
                if (isOffhook && pendingAudioUrl != null) {
                    String url = pendingAudioUrl;
                    pendingAudioUrl = null;
                    playAudioStream(context, url, pendingName, pendingNumber, pendingCallId, pendingServer);
                }
            }, 900);

        } else if (TelephonyManager.EXTRA_STATE_IDLE.equals(state)) {
            isRinging = false;
            isOffhook = false;
            pendingAudioUrl = null;
            Log.d(TAG, "IDLE — arama bitti");
            stopAudio();
            TenraPrefsPlugin.writeString(context, TenraPrefsPlugin.KEY_AUDIO_LOCK, "0");
            GsmDialogueService.stopFromReceiver(context);
        }
    }

    private boolean isGsmAutoAnswerEnabled(Context context) {
        try {
            SharedPreferences prefs = context.getSharedPreferences(TenraPrefsPlugin.PREFS_NAME, Context.MODE_PRIVATE);
            // Varsayılan: kapalı (Tenra 2.0 SIP-first)
            String raw = prefs.getString(TenraPrefsPlugin.KEY_GSM_AUTO_ANSWER, "0");
            if (raw == null) raw = "0";
            raw = raw.trim().toLowerCase();
            return raw.equals("1") || raw.equals("true") || raw.equals("yes") || raw.equals("on");
        } catch (Exception e) {
            return false;
        }
    }

    private int readAutoAnswerDelaySec(Context context) {
        try {
            SharedPreferences prefs = context.getSharedPreferences(TenraPrefsPlugin.PREFS_NAME, Context.MODE_PRIVATE);
            String raw = prefs.getString(TenraPrefsPlugin.KEY_AUTO_DELAY, null);
            if (raw == null || raw.trim().isEmpty()) {
                raw = prefs.getString("tenra_auto_delay", "5");
            }
            int sec = Integer.parseInt(raw.trim());
            if (sec < 3) sec = 3;
            if (sec > 30) sec = 30;
            return sec;
        } catch (Exception e) {
            return 5;
        }
    }

    /** Intent + CallLog ile en iyi numarayı bul */
    private String resolveBestNumber(Context context, String raw) {
        if (raw != null && !raw.trim().isEmpty() && !raw.equals("Bilinmeyen Numara")) {
            return raw.trim();
        }
        String fromLog = getLastIncomingFromCallLog(context);
        if (fromLog != null && !fromLog.isEmpty()) {
            Log.d(TAG, "Numara CallLog'dan alındı: " + fromLog);
            return fromLog;
        }
        if (incomingNumber != null && !incomingNumber.isEmpty() && !incomingNumber.equals("Bilinmeyen Numara")) {
            return incomingNumber;
        }
        return "Bilinmeyen Numara";
    }

    private String getLastIncomingFromCallLog(Context context) {
        try {
            Cursor c = context.getContentResolver().query(
                    CallLog.Calls.CONTENT_URI,
                    new String[]{CallLog.Calls.NUMBER, CallLog.Calls.CACHED_NAME, CallLog.Calls.TYPE, CallLog.Calls.DATE},
                    CallLog.Calls.TYPE + "=? OR " + CallLog.Calls.TYPE + "=?",
                    new String[]{
                            String.valueOf(CallLog.Calls.INCOMING_TYPE),
                            String.valueOf(CallLog.Calls.MISSED_TYPE)
                    },
                    CallLog.Calls.DATE + " DESC LIMIT 1"
            );
            if (c != null) {
                try {
                    if (c.moveToFirst()) {
                        int numIdx = c.getColumnIndex(CallLog.Calls.NUMBER);
                        if (numIdx >= 0) {
                            String n = c.getString(numIdx);
                            if (n != null && !n.trim().isEmpty()) return n.trim();
                        }
                    }
                } finally {
                    c.close();
                }
            }
        } catch (SecurityException se) {
            Log.w(TAG, "CallLog izni yok: " + se.getMessage());
        } catch (Exception e) {
            Log.w(TAG, "CallLog okuma: " + e.getMessage());
        }
        return null;
    }

    private String getCachedNameFromCallLog(Context context, String phone) {
        try {
            Cursor c = context.getContentResolver().query(
                    CallLog.Calls.CONTENT_URI,
                    new String[]{CallLog.Calls.CACHED_NAME, CallLog.Calls.NUMBER},
                    null, null,
                    CallLog.Calls.DATE + " DESC LIMIT 5"
            );
            if (c != null) {
                try {
                    String digits = digitsOnly(phone);
                    while (c.moveToNext()) {
                        int nIdx = c.getColumnIndex(CallLog.Calls.NUMBER);
                        int nameIdx = c.getColumnIndex(CallLog.Calls.CACHED_NAME);
                        String n = nIdx >= 0 ? c.getString(nIdx) : null;
                        String name = nameIdx >= 0 ? c.getString(nameIdx) : null;
                        if (name != null && !name.trim().isEmpty() && n != null
                                && digitsMatch(digitsOnly(n), digits)) {
                            return name.trim();
                        }
                    }
                } finally {
                    c.close();
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "CallLog isim: " + e.getMessage());
        }
        return null;
    }

    private String resolveContactName(Context context, String phoneNumber) {
        if (phoneNumber == null || phoneNumber.equals("Bilinmeyen Numara")) {
            return "Bilinmeyen Numara";
        }

        // 1) CallLog önbellek ismi (Ablam vb. sık burada)
        String cached = getCachedNameFromCallLog(context, phoneNumber);
        if (cached != null) {
            Log.d(TAG, "İsim CallLog cache: " + cached);
            return cached;
        }

        // 2) PhoneLookup — birden fazla numara varyantı
        for (String variant : phoneVariants(phoneNumber)) {
            String name = lookupPhoneFilter(context, variant);
            if (name != null) {
                Log.d(TAG, "İsim PhoneLookup (" + variant + "): " + name);
                return name;
            }
        }

        // 3) Son 10 hane ile Contacts araması
        String bySuffix = lookupByLastDigits(context, digitsOnly(phoneNumber));
        if (bySuffix != null) {
            Log.d(TAG, "İsim son-hane eşleşmesi: " + bySuffix);
            return bySuffix;
        }

        Log.w(TAG, "Rehberde bulunamadı: " + phoneNumber);
        return phoneNumber;
    }

    private List<String> phoneVariants(String phone) {
        Set<String> set = new LinkedHashSet<>();
        String raw = phone.trim();
        set.add(raw);
        String d = digitsOnly(raw);
        if (!d.isEmpty()) {
            set.add(d);
            if (d.startsWith("90") && d.length() >= 12) {
                set.add("0" + d.substring(2));
                set.add("+" + d);
                set.add(d.substring(2));
            }
            if (d.startsWith("0") && d.length() >= 11) {
                set.add("+90" + d.substring(1));
                set.add("90" + d.substring(1));
            }
            if (d.length() == 10) {
                set.add("0" + d);
                set.add("+90" + d);
                set.add("90" + d);
            }
        }
        return new ArrayList<>(set);
    }

    private String lookupPhoneFilter(Context context, String phone) {
        try {
            Uri uri = Uri.withAppendedPath(
                    ContactsContract.PhoneLookup.CONTENT_FILTER_URI,
                    Uri.encode(phone)
            );
            Cursor cursor = context.getContentResolver().query(
                    uri,
                    new String[]{ContactsContract.PhoneLookup.DISPLAY_NAME},
                    null, null, null
            );
            if (cursor != null) {
                try {
                    if (cursor.moveToFirst()) {
                        int index = cursor.getColumnIndex(ContactsContract.PhoneLookup.DISPLAY_NAME);
                        if (index != -1) {
                            String name = cursor.getString(index);
                            if (name != null && !name.trim().isEmpty()) return name.trim();
                        }
                    }
                } finally {
                    cursor.close();
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "PhoneLookup hata: " + e.getMessage());
        }
        return null;
    }

    private String lookupByLastDigits(Context context, String digits) {
        if (digits == null || digits.length() < 7) return null;
        String suffix = digits.length() > 10 ? digits.substring(digits.length() - 10) : digits;
        try {
            Cursor cursor = context.getContentResolver().query(
                    ContactsContract.CommonDataKinds.Phone.CONTENT_URI,
                    new String[]{
                            ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME,
                            ContactsContract.CommonDataKinds.Phone.NUMBER
                    },
                    null, null, null
            );
            if (cursor != null) {
                try {
                    while (cursor.moveToNext()) {
                        int nameIdx = cursor.getColumnIndex(ContactsContract.CommonDataKinds.Phone.DISPLAY_NAME);
                        int numIdx = cursor.getColumnIndex(ContactsContract.CommonDataKinds.Phone.NUMBER);
                        String name = nameIdx >= 0 ? cursor.getString(nameIdx) : null;
                        String num = numIdx >= 0 ? cursor.getString(numIdx) : null;
                        if (name == null || num == null) continue;
                        if (digitsMatch(digitsOnly(num), suffix) || digitsMatch(digitsOnly(num), digits)) {
                            return name.trim();
                        }
                    }
                } finally {
                    cursor.close();
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "Contacts tarama: " + e.getMessage());
        }
        return null;
    }

    private static String digitsOnly(String s) {
        if (s == null) return "";
        return s.replaceAll("\\D+", "");
    }

    private static boolean digitsMatch(String a, String b) {
        if (a == null || b == null || a.isEmpty() || b.isEmpty()) return false;
        if (a.equals(b)) return true;
        String shortA = a.length() > 10 ? a.substring(a.length() - 10) : a;
        String shortB = b.length() > 10 ? b.substring(b.length() - 10) : b;
        return shortA.equals(shortB);
    }

    private void answerCall(Context context, String number, String name) {
        long now = SystemClock.elapsedRealtime();
        if (now - lastAnswerAt < 8000) {
            Log.w(TAG, "answerCall debounce");
            return;
        }
        lastAnswerAt = now;

        boolean answered = false;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try {
                TelecomManager tm = (TelecomManager) context.getSystemService(Context.TELECOM_SERVICE);
                if (tm != null) {
                    tm.acceptRingingCall();
                    answered = true;
                    Log.d(TAG, "TelecomManager accept OK");
                }
            } catch (Exception e) {
                Log.w(TAG, "TelecomManager: " + e.getMessage());
            }
        }
        if (!answered) {
            try {
                AudioManager am = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
                if (am != null) {
                    long eventTime = SystemClock.uptimeMillis();
                    am.dispatchMediaKeyEvent(new KeyEvent(eventTime, eventTime, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_HEADSETHOOK, 0));
                    am.dispatchMediaKeyEvent(new KeyEvent(eventTime, eventTime, KeyEvent.ACTION_UP, KeyEvent.KEYCODE_HEADSETHOOK, 0));
                    answered = true;
                }
            } catch (Exception e) {
                Log.e(TAG, "HeadsetHook: " + e.getMessage());
            }
        }

        forceSpeakerLoud(context);
        TenraPrefsPlugin.acquireAudioLock(context, 60000);
        notifyTenraServerAndPlay(context, number, name);

        try {
            Intent launchIntent = new Intent(context, MainActivity.class);
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            launchIntent.putExtra("auto_call", true);
            launchIntent.putExtra("native_audio_owned", true);
            launchIntent.putExtra("caller_number", number);
            launchIntent.putExtra("caller_name", name);
            context.startActivity(launchIntent);
        } catch (Exception e) {
            Log.w(TAG, "MainActivity: " + e.getMessage());
        }
    }

    /** Hoparlör + tüm ses kanalları max — GSM sırasında MEDIA çoğu telefonda susturulur, ALARM geçer */
    static void forceSpeakerLoud(Context context) {
        try {
            AudioManager am = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
            if (am == null) return;
            am.setMode(AudioManager.MODE_IN_COMMUNICATION);
            am.setSpeakerphoneOn(true);
            int[] streams = new int[]{
                    AudioManager.STREAM_MUSIC,
                    AudioManager.STREAM_VOICE_CALL,
                    AudioManager.STREAM_ALARM,
                    AudioManager.STREAM_RING,
                    AudioManager.STREAM_NOTIFICATION
            };
            for (int s : streams) {
                try {
                    am.setStreamVolume(s, am.getStreamMaxVolume(s), 0);
                } catch (Exception ignored) {}
            }
            Log.d(TAG, "Hoparlör LOUD (IN_COMMUNICATION + tüm stream max)");
        } catch (Exception e) {
            Log.w(TAG, "forceSpeakerLoud: " + e.getMessage());
        }
    }

    private void notifyTenraServerAndPlay(Context context, String number, String name) {
        new Thread(() -> {
            // Son bir kez isim tazele
            String num = resolveBestNumber(context, number);
            String nam = resolveContactName(context, num);
            Log.d(TAG, "Sunucuya gidecek: " + nam + " / " + num);

            SharedPreferences prefs = context.getSharedPreferences(TenraPrefsPlugin.PREFS_NAME, Context.MODE_PRIVATE);
            String customUrl = prefs.getString(TenraPrefsPlugin.KEY_SERVER_URL,
                    prefs.getString(TenraPrefsPlugin.KEY_SERVER_URL_ALT, ""));

            java.util.List<String> candidateUrls = new java.util.ArrayList<>();
            if (customUrl != null && !customUrl.trim().isEmpty()) candidateUrls.add(customUrl.trim());
            candidateUrls.add("http://192.168.1.100:8008");
            candidateUrls.add("http://100.93.198.21:8008");

            for (String candidate : candidateUrls) {
                final String serverUrl = candidate.endsWith("/") ? candidate : candidate + "/";
                try {
                    URL url = new URL(serverUrl + "api/gsm/incoming");
                    HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("POST");
                    conn.setRequestProperty("Content-Type", "application/json; utf-8");
                    conn.setRequestProperty("Accept", "application/json");
                    conn.setDoOutput(true);
                    conn.setConnectTimeout(3000);
                    conn.setReadTimeout(20000);

                    JSONObject json = new JSONObject();
                    json.put("caller_name", nam);
                    json.put("caller_number", num);
                    json.put("action", "auto_answered");

                    try (OutputStream os = conn.getOutputStream()) {
                        os.write(json.toString().getBytes("utf-8"));
                    }

                    int code = conn.getResponseCode();
                    Log.d(TAG, "gsm/incoming " + code + " @ " + serverUrl);
                    if (code == 200) {
                        BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), "utf-8"));
                        StringBuilder response = new StringBuilder();
                        String line;
                        while ((line = br.readLine()) != null) response.append(line.trim());
                        br.close();

                        JSONObject resJson = new JSONObject(response.toString());
                        String audioUrl = resJson.optString("audio_url", "");
                        final int callId = resJson.optInt("call_id", -1);
                        lastCallId = callId;
                        lastServerBase = serverUrl;

                        if (!audioUrl.isEmpty()) {
                            final String full = audioUrl.startsWith("http")
                                    ? audioUrl
                                    : serverUrl + audioUrl.replaceFirst("^/", "");
                            // KRİTİK: diyalogu MediaPlayer'a bağlama — hemen başlat
                            // (eski yol: selamlama bitsin diye bekliyordu → hiç listen gitmiyordu)
                            new Handler(Looper.getMainLooper()).post(() -> {
                                forceSpeakerLoud(context);
                                startDialogueService(context, nam, num, callId, serverUrl, full);
                            });
                            // Yedek: 2.5 sn sonra hâlâ yoksa tekrar dene
                            new Handler(Looper.getMainLooper()).postDelayed(() -> {
                                if (!GsmDialogueService.isRunning()) {
                                    Log.w(TAG, "Diyalog yedek başlatma");
                                    startDialogueService(context, nam, num, callId, serverUrl, full);
                                }
                            }, 2500);
                            conn.disconnect();
                            break;
                        } else {
                            startDialogueService(context, nam, num, callId, serverUrl, null);
                        }
                    }
                    conn.disconnect();
                } catch (Exception e) {
                    Log.w(TAG, "Sunucu denemesi fail: " + e.getMessage());
                }
            }
        }).start();
    }

    private void startDialogueService(Context context, String name, String number,
                                      int callId, String serverUrl, String greetingUrl) {
        if (GsmDialogueService.isRunning()) {
            Log.d(TAG, "Diyalog zaten çalışıyor — atlandı");
            return;
        }
        try {
            Intent svc = new Intent(context, GsmDialogueService.class);
            svc.putExtra("caller_name", name);
            svc.putExtra("caller_number", number);
            svc.putExtra("call_id", callId);
            svc.putExtra("server_url", serverUrl != null ? serverUrl : lastServerBase);
            if (greetingUrl != null && !greetingUrl.isEmpty()) {
                svc.putExtra("greeting_url", greetingUrl);
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(svc);
            } else {
                context.startService(svc);
            }
            Log.d(TAG, "GsmDialogueService başlatıldı callId=" + callId + " greet=" + (greetingUrl != null));
        } catch (Exception e) {
            Log.e(TAG, "Diyalog servisi: " + e.getMessage(), e);
            try {
                Intent launch = new Intent(context, MainActivity.class);
                launch.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                launch.putExtra("auto_call", true);
                launch.putExtra("start_dialogue", true);
                launch.putExtra("caller_name", name);
                launch.putExtra("caller_number", number);
                launch.putExtra("call_id", callId);
                launch.putExtra("server_url", serverUrl);
                launch.putExtra("greeting_url", greetingUrl);
                context.startActivity(launch);
            } catch (Exception e2) {
                Log.e(TAG, "Activity yedek de fail: " + e2.getMessage());
            }
        }
    }

    private synchronized void playAudioStream(Context context, String audioUrl,
                                              String name, String number, int callId, String serverUrl) {
        startDialogueService(context, name, number, callId, serverUrl, audioUrl);
    }

    private synchronized void stopAudio() {
        if (activePlayer != null) {
            try {
                if (activePlayer.isPlaying()) activePlayer.stop();
                activePlayer.release();
            } catch (Exception ignored) {}
            activePlayer = null;
        }
    }
}

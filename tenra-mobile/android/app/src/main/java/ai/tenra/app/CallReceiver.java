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

/**
 * TENRA Native Call Receiver (Dual-Engine & Resilient)
 * Gelen GSM telefon aramasını yakalar:
 * 1. goAsync() ve WakeLock ile Android'in süreci arka planda öldürmesini engeller.
 * 2. Numarayı alır ve telefon rehberinden (ContactsContract) arayan kişinin ismini çözer.
 * 3. 10 saniye sonra Çift Motor (TelecomManager + Headset Hook) ile aramayı yanıtlar.
 * 4. Hoparlörü açar, TENRA sunucusuna bildirir ve dönen ses dosyasını karşı tarafa seslendirir.
 */
public class CallReceiver extends BroadcastReceiver {
    private static final String TAG = "TENRA_CallReceiver";
    private static volatile boolean isRinging = false;
    private static String incomingNumber = "";
    private static String callerName = "";
    private static MediaPlayer activePlayer = null;

    @Override
    public void onReceive(Context context, Intent intent) {
        String action = intent.getAction();
        if (TelephonyManager.ACTION_PHONE_STATE_CHANGED.equals(action)) {
            String state = intent.getStringExtra(TelephonyManager.EXTRA_STATE);

            if (TelephonyManager.EXTRA_STATE_RINGING.equals(state)) {
                isRinging = true;
                incomingNumber = intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER);
                if (incomingNumber == null || incomingNumber.trim().isEmpty()) {
                    incomingNumber = "Bilinmeyen Numara";
                }

                // Rehberden ismi çöz
                callerName = getContactName(context, incomingNumber);
                Log.d(TAG, "Gelen arama: " + incomingNumber + " (Rehber: " + callerName + ")");

                // Android'in arka planda süreci dondurmasını/öldürmesini engelle
                final PendingResult pendingResult = goAsync();

                // CPU'nun uykuya geçmesini 15 saniyeliğine engelle
                PowerManager pm = (PowerManager) context.getSystemService(Context.POWER_SERVICE);
                final PowerManager.WakeLock wakeLock;
                if (pm != null) {
                    wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "TENRA:CallDelayWakeLock");
                    wakeLock.acquire(15000);
                } else {
                    wakeLock = null;
                }

                // 10 saniye sonra otomatik aç
                new Handler(Looper.getMainLooper()).postDelayed(() -> {
                    try {
                        if (isRinging) {
                            Log.d(TAG, "10 saniye doldu, arama otomatik yanıtlanıyor...");
                            answerCall(context, incomingNumber, callerName);
                        } else {
                            Log.d(TAG, "Arama 10 saniye dolmadan kapandı veya elle açıldı.");
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Gecikmeli yanıt hatası: " + e.getMessage());
                    } finally {
                        if (wakeLock != null && wakeLock.isHeld()) {
                            try {
                                wakeLock.release();
                            } catch (Exception ignored) {}
                        }
                        try {
                            pendingResult.finish();
                        } catch (Exception ignored) {}
                    }
                }, 10000);

            } else if (TelephonyManager.EXTRA_STATE_OFFHOOK.equals(state)) {
                isRinging = false;
                Log.d(TAG, "Görüşme başladı (Offhook).");
            } else if (TelephonyManager.EXTRA_STATE_IDLE.equals(state)) {
                isRinging = false;
                Log.d(TAG, "Arama sonlandı (Idle).");
                stopAudio();
            }
        }
    }

    /**
     * Android Rehber API'si üzerinden numaranın kime ait olduğunu sorgular.
     */
    private String getContactName(Context context, String phoneNumber) {
        if (phoneNumber == null || phoneNumber.equals("Bilinmeyen Numara")) {
            return "Bilinmeyen Numara";
        }
        try {
            Uri uri = Uri.withAppendedPath(ContactsContract.PhoneLookup.CONTENT_FILTER_URI, Uri.encode(phoneNumber));
            String[] projection = new String[]{ContactsContract.PhoneLookup.DISPLAY_NAME};
            Cursor cursor = context.getContentResolver().query(uri, projection, null, null, null);
            if (cursor != null) {
                try {
                    if (cursor.moveToFirst()) {
                        int index = cursor.getColumnIndex(ContactsContract.PhoneLookup.DISPLAY_NAME);
                        if (index != -1) {
                            String name = cursor.getString(index);
                            if (name != null && !name.trim().isEmpty()) {
                                return name.trim();
                            }
                        }
                    }
                } finally {
                    cursor.close();
                }
            }
        } catch (Exception e) {
            Log.w(TAG, "Rehber sorgulama hatası: " + e.getMessage());
        }
        return phoneNumber;
    }

    /**
     * Çift Motorlu Çağrı Cevaplama:
     * 1. Motor: TelecomManager.acceptRingingCall()
     * 2. Motor (Yedek): Kulaklık tuşu simülasyonu (KEYCODE_HEADSETHOOK)
     */
    private void answerCall(Context context, String number, String name) {
        boolean answered = false;

        // 1. Motor: TelecomManager (Android 8+)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            try {
                TelecomManager tm = (TelecomManager) context.getSystemService(Context.TELECOM_SERVICE);
                if (tm != null) {
                    tm.acceptRingingCall();
                    answered = true;
                    Log.d(TAG, "[1. Motor - TelecomManager] Çağrı başarıyla kabul edildi.");
                }
            } catch (SecurityException se) {
                Log.w(TAG, "[1. Motor] İzin eksik veya sistem engelledi: " + se.getMessage());
            } catch (Exception e) {
                Log.w(TAG, "[1. Motor Hatası]: " + e.getMessage());
            }
        }

        // 2. Motor: Donanım Kulaklık Butonu Simülasyonu (Tüm Android sürümlerinde evrensel yöntem)
        if (!answered) {
            try {
                Log.d(TAG, "[2. Motor - HeadsetHook] Kulaklık butonuyla çağrı açma simüle ediliyor...");
                AudioManager am = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
                if (am != null) {
                    long eventTime = SystemClock.uptimeMillis();
                    KeyEvent downEvent = new KeyEvent(eventTime, eventTime, KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_HEADSETHOOK, 0);
                    KeyEvent upEvent = new KeyEvent(eventTime, eventTime, KeyEvent.ACTION_UP, KeyEvent.KEYCODE_HEADSETHOOK, 0);

                    am.dispatchMediaKeyEvent(downEvent);
                    am.dispatchMediaKeyEvent(upEvent);
                    answered = true;
                    Log.d(TAG, "[2. Motor] HeadsetHook çağrı açma sinyali başarıyla iletildi.");
                }
            } catch (Exception e) {
                Log.e(TAG, "[2. Motor Hatası]: " + e.getMessage());
            }
        }

        // Hoparlörü Aç
        try {
            AudioManager am = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
            if (am != null) {
                am.setMode(AudioManager.MODE_IN_CALL);
                am.setSpeakerphoneOn(true);
                Log.d(TAG, "Hoparlör açıldı (Speakerphone ON).");
            }
        } catch (Exception e) {
            Log.w(TAG, "Hoparlör açma hatası: " + e.getMessage());
        }

        // Sunucuya bildir ve selamlama sesini çal
        notifyTenraServerAndPlay(context, number, name);

        // Uygulamayı ekrana getir
        try {
            Intent launchIntent = new Intent(context, MainActivity.class);
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_SINGLE_TOP);
            launchIntent.putExtra("auto_call", true);
            launchIntent.putExtra("caller_number", number);
            launchIntent.putExtra("caller_name", name);
            context.startActivity(launchIntent);
        } catch (Exception e) {
            Log.w(TAG, "MainActivity başlatma uyarısı: " + e.getMessage());
        }
    }

    private void notifyTenraServerAndPlay(Context context, String number, String name) {
        new Thread(() -> {
            SharedPreferences prefs = context.getSharedPreferences("CapacitorStorage", Context.MODE_PRIVATE);
            String customUrl = prefs.getString("server_url", prefs.getString("tenra_server_url", ""));
            
            java.util.List<String> candidateUrls = new java.util.ArrayList<>();
            if (customUrl != null && !customUrl.trim().isEmpty()) {
                candidateUrls.add(customUrl.trim());
            }
            candidateUrls.add("http://192.168.1.100:8008");
            candidateUrls.add("http://100.93.198.21:8008");

            for (String serverUrl : candidateUrls) {
                if (!serverUrl.endsWith("/")) serverUrl += "/";
                try {
                    Log.d(TAG, "Sunucuya bağlanılıyor: " + serverUrl);
                    URL url = new URL(serverUrl + "api/gsm/incoming");
                    HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                    conn.setRequestMethod("POST");
                    conn.setRequestProperty("Content-Type", "application/json; utf-8");
                    conn.setRequestProperty("Accept", "application/json");
                    conn.setDoOutput(true);
                    conn.setConnectTimeout(3000);
                    conn.setReadTimeout(12000);

                    JSONObject json = new JSONObject();
                    json.put("caller_name", name);
                    json.put("caller_number", number);
                    json.put("action", "auto_answered");

                    try (OutputStream os = conn.getOutputStream()) {
                        byte[] input = json.toString().getBytes("utf-8");
                        os.write(input, 0, input.length);
                    }

                    int code = conn.getResponseCode();
                    Log.d(TAG, "TENRA Sunucu bildirimi yapıldı (" + serverUrl + "). Durum: " + code);

                    if (code == 200) {
                        BufferedReader br = new BufferedReader(new InputStreamReader(conn.getInputStream(), "utf-8"));
                        StringBuilder response = new StringBuilder();
                        String responseLine;
                        while ((responseLine = br.readLine()) != null) {
                            response.append(responseLine.trim());
                        }
                        br.close();

                        JSONObject resJson = new JSONObject(response.toString());
                        String audioUrl = resJson.optString("audio_url", "");
                        if (!audioUrl.isEmpty()) {
                            String fullAudioUrl = audioUrl.startsWith("http") ? audioUrl : serverUrl + audioUrl.replaceFirst("^/", "");
                            Log.d(TAG, "Selamlama sesi çalınıyor: " + fullAudioUrl);
                            playAudioStream(context, fullAudioUrl);
                            conn.disconnect();
                            break; // Başarılı, diğer adresleri denemeye gerek yok
                        }
                    }
                    conn.disconnect();
                } catch (Exception e) {
                    Log.w(TAG, "Sunucu denemesi (" + serverUrl + ") başarısız: " + e.getMessage());
                }
            }
        }).start();
    }

    private synchronized void playAudioStream(Context context, String audioUrl) {
        try {
            stopAudio();

            // Hoparlör ve ses seviyelerini en yükseğe al
            try {
                AudioManager am = (AudioManager) context.getSystemService(Context.AUDIO_SERVICE);
                if (am != null) {
                    am.setMode(AudioManager.MODE_IN_CALL);
                    am.setSpeakerphoneOn(true);
                    int maxVoice = am.getStreamMaxVolume(AudioManager.STREAM_VOICE_CALL);
                    am.setStreamVolume(AudioManager.STREAM_VOICE_CALL, maxVoice, 0);
                    int maxMusic = am.getStreamMaxVolume(AudioManager.STREAM_MUSIC);
                    am.setStreamVolume(AudioManager.STREAM_MUSIC, maxMusic, 0);
                }
            } catch (Exception ignored) {}

            activePlayer = new MediaPlayer();
            activePlayer.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build());
            activePlayer.setDataSource(audioUrl);
            activePlayer.setOnPreparedListener(mp -> {
                Log.d(TAG, "MediaPlayer hazır, ses çalınıyor: " + audioUrl);
                mp.start();
            });
            activePlayer.setOnCompletionListener(mp -> stopAudio());
            activePlayer.setOnErrorListener((mp, what, extra) -> {
                Log.w(TAG, "MediaPlayer hatası: what=" + what + ", extra=" + extra);
                stopAudio();
                return true;
            });
            activePlayer.prepareAsync();
        } catch (Exception e) {
            Log.e(TAG, "playAudioStream hatası: " + e.getMessage());
        }
    }

    private synchronized void stopAudio() {
        if (activePlayer != null) {
            try {
                if (activePlayer.isPlaying()) {
                    activePlayer.stop();
                }
                activePlayer.release();
            } catch (Exception ignored) {}
            activePlayer = null;
        }
    }
}

package ai.tenra.app;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.media.AudioAttributes;
import android.media.AudioFormat;
import android.media.AudioManager;
import android.media.AudioRecord;
import android.media.MediaPlayer;
import android.media.MediaRecorder;
import android.content.pm.ServiceInfo;
import android.os.Build;
import android.os.Handler;
import android.os.IBinder;
import android.os.Looper;
import android.speech.RecognitionListener;
import android.speech.RecognizerIntent;
import android.speech.SpeechRecognizer;
import android.util.Log;

import androidx.core.app.NotificationCompat;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.BufferedReader;
import java.io.ByteArrayOutputStream;
import java.io.DataOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.util.ArrayList;
import java.util.Locale;

/**
 * Adım 3 — GSM iki yönlü diyalog döngüsü:
 * Selamlama bitti → dinle (SpeechRecognizer veya AudioRecord+Whisper)
 * → /api/gsm/turn veya /api/gsm/listen → TTS çal → tekrar dinle.
 */
public class GsmDialogueService extends Service {
    private static final String TAG = "TENRA_GsmDialogue";
    private static final String CHANNEL_ID = "tenra_gsm_dialogue";
    private static final int NOTIF_ID = 4208;
    public static final String ACTION_STOP = "ai.tenra.app.STOP_DIALOGUE";

    private static volatile boolean running = false;

    private String callerName = "Arayan";
    private String callerNumber = "";
    private String serverBase = "";
    private int callId = -1;
    private String greetingUrl = null;

    private final JSONArray history = new JSONArray();
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private SpeechRecognizer speechRecognizer;
    private MediaPlayer replyPlayer;
    private AudioRecord audioRecord;
    private volatile boolean listening = false;
    private volatile boolean playing = false;
    private int turnCount = 0;
    private static final int MAX_TURNS = 12;

    @Override
    public void onCreate() {
        super.onCreate();
        createChannel();
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopDialogue("stop_action");
            return START_NOT_STICKY;
        }

        if (intent != null) {
            callerName = intent.getStringExtra("caller_name");
            if (callerName == null || callerName.isEmpty()) callerName = "Arayan";
            callerNumber = intent.getStringExtra("caller_number");
            if (callerNumber == null) callerNumber = "";
            serverBase = intent.getStringExtra("server_url");
            if (serverBase == null) serverBase = "";
            callId = intent.getIntExtra("call_id", -1);
            greetingUrl = intent.getStringExtra("greeting_url");
        }

        if (serverBase == null || serverBase.trim().isEmpty()) {
            serverBase = resolveServerUrl();
        }
        if (!serverBase.endsWith("/")) serverBase += "/";

        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
                startForeground(NOTIF_ID, buildNotification("Ahmet AI aktif — selamlama"),
                        ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE);
            } else {
                startForeground(NOTIF_ID, buildNotification("Ahmet AI aktif — selamlama"));
            }
        } catch (Exception e) {
            Log.e(TAG, "startForeground FAIL: " + e.getMessage(), e);
            // Yine de dinlemeyi dene
            try {
                startForeground(NOTIF_ID, buildNotification("Ahmet AI (yedek)"));
            } catch (Exception e2) {
                Log.e(TAG, "startForeground yedek de fail: " + e2.getMessage());
            }
        }
        running = true;
        TenraPrefsPlugin.acquireAudioLock(this, 120000);
        CallReceiver.forceSpeakerLoud(this);

        if (greetingUrl != null && !greetingUrl.isEmpty()) {
            final String g = greetingUrl;
            greetingUrl = null; // bir kez
            new Thread(() -> playGreetingThenListen(g), "tenra-greet").start();
        } else {
            mainHandler.postDelayed(this::beginListenCycle, 800);
        }
        return START_STICKY;
    }

    /** Selamlamayı yerel dosyaya indir + ALARM kanalından çal (GSM'de MEDIA susturulur) */
    private void playGreetingThenListen(String url) {
        if (!running) return;
        playing = true;
        updateNotification("Selamlama çalınıyor...");
        File local = null;
        try {
            local = downloadToCache(url, "greet_");
            final String path = local.getAbsolutePath();
            mainHandler.post(() -> playLocalFile(path, false, true));
        } catch (Exception e) {
            Log.e(TAG, "Selamlama indirme/çalma: " + e.getMessage(), e);
            playing = false;
            // URL'den doğrudan dene
            mainHandler.post(() -> playReply(url, false));
        }
    }

    private File downloadToCache(String urlStr, String prefix) throws Exception {
        URL url = new URL(urlStr);
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setConnectTimeout(5000);
        conn.setReadTimeout(30000);
        conn.connect();
        File f = new File(getCacheDir(), prefix + System.currentTimeMillis() + ".wav");
        try (java.io.InputStream in = conn.getInputStream();
             FileOutputStream out = new FileOutputStream(f)) {
            byte[] buf = new byte[8192];
            int n;
            while ((n = in.read(buf)) > 0) out.write(buf, 0, n);
        }
        conn.disconnect();
        Log.d(TAG, "İndirildi: " + f.getAbsolutePath() + " size=" + f.length());
        return f;
    }

    private void playLocalFile(String path, boolean endAfter, boolean isGreeting) {
        if (!running) return;
        playing = true;
        listening = false;
        stopReplyPlayer();
        CallReceiver.forceSpeakerLoud(this);
        TenraPrefsPlugin.acquireAudioLock(this, 60000);
        updateNotification(isGreeting ? "Ahmet selamlıyor..." : "Ahmet konuşuyor...");

        try {
            replyPlayer = new MediaPlayer();
            // ALARM: arama sırasında MEDIA çoğu OEM'de susturulur; ALARM geçer
            replyPlayer.setAudioAttributes(new AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_ALARM)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build());
            replyPlayer.setVolume(1.0f, 1.0f);
            replyPlayer.setDataSource(path);
            replyPlayer.setOnPreparedListener(mp -> {
                CallReceiver.forceSpeakerLoud(this);
                Log.d(TAG, "Çalıyor (ALARM): " + path);
                mp.start();
                mainHandler.postDelayed(() -> CallReceiver.forceSpeakerLoud(this), 400);
            });
            replyPlayer.setOnCompletionListener(mp -> {
                stopReplyPlayer();
                playing = false;
                if (!running) return;
                if (endAfter) stopDialogue("farewell");
                else mainHandler.postDelayed(this::beginListenCycle, 600);
            });
            replyPlayer.setOnErrorListener((mp, what, extra) -> {
                Log.w(TAG, "playLocal hata what=" + what);
                stopReplyPlayer();
                playing = false;
                if (running) mainHandler.postDelayed(this::beginListenCycle, 500);
                return true;
            });
            replyPlayer.prepareAsync();
            // Takılırsa dinlemeye geç
            mainHandler.postDelayed(() -> {
                if (running && playing && !listening) {
                    Log.w(TAG, "Çalma timeout — dinlemeye geç");
                    stopReplyPlayer();
                    playing = false;
                    beginListenCycle();
                }
            }, isGreeting ? 20000 : 25000);
        } catch (Exception e) {
            Log.e(TAG, "playLocalFile: " + e.getMessage());
            playing = false;
            if (running) mainHandler.postDelayed(this::beginListenCycle, 500);
        }
    }

    @Override
    public void onDestroy() {
        stopDialogue("destroy");
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    public static void stopFromReceiver(Context ctx) {
        Intent i = new Intent(ctx, GsmDialogueService.class);
        i.setAction(ACTION_STOP);
        try {
            ctx.startService(i);
        } catch (Exception e) {
            Log.w(TAG, "stopFromReceiver: " + e.getMessage());
        }
    }

    public static boolean isRunning() {
        return running;
    }

    private void stopDialogue(String reason) {
        Log.d(TAG, "Diyalog durduruluyor: " + reason);
        boolean wasRunning = running;
        running = false;
        listening = false;
        playing = false;
        mainHandler.removeCallbacksAndMessages(null);
        destroySpeechRecognizer();
        stopReplyPlayer();
        stopAudioRecord();

        if (wasRunning) {
            final String hist = history.toString();
            final String name = callerName;
            final int cid = callId;
            final String base = serverBase;
            final Context appCtx = getApplicationContext();
            new Thread(() -> postGsmEnd(appCtx, base, name, cid, hist), "tenra-gsm-end").start();
        }

        stopForeground(true);
        stopSelf();
    }

    private void postGsmEnd(Context ctx, String base, String name, int cid, String historyJson) {
        try {
            if (base == null || base.isEmpty()) return;
            if (!base.endsWith("/")) base = base + "/";
            URL url = new URL(base + "api/gsm/end");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json; utf-8");
            conn.setDoOutput(true);
            conn.setConnectTimeout(4000);
            conn.setReadTimeout(60000);
            JSONObject body = new JSONObject();
            body.put("caller_name", name);
            body.put("history", new JSONArray(historyJson));
            if (cid > 0) body.put("call_id", cid);
            try (OutputStream os = conn.getOutputStream()) {
                os.write(body.toString().getBytes("utf-8"));
            }
            Log.d(TAG, "gsm/end HTTP " + conn.getResponseCode());
            conn.disconnect();
        } catch (Exception e) {
            Log.w(TAG, "gsm/end: " + e.getMessage());
        }
    }

    private void beginListenCycle() {
        if (!running) return;
        if (turnCount >= MAX_TURNS) {
            stopDialogue("max_turns");
            return;
        }
        if (playing) return;

        updateNotification("Ablayı / arayanı dinliyorum...");
        ensureSpeakerphone();

        // GSM sırasında Google SpeechRecognizer çoğu cihazda çalışmaz.
        // Doğrudan mikrofon kaydı + sunucu Whisper kullan.
        new Thread(this::recordAndUploadLoop, "tenra-vad").start();
    }

    private void startSpeechRecognizer() {
        // GSM full-duplex için kullanılmıyor; yedek bırakıldı
        new Thread(this::recordAndUploadLoop, "tenra-vad-sr").start();
    }

    private void destroySpeechRecognizer() {
        if (speechRecognizer != null) {
            try {
                speechRecognizer.cancel();
                speechRecognizer.destroy();
            } catch (Exception ignored) {}
            speechRecognizer = null;
        }
        listening = false;
    }

    /** Enerji tabanlı VAD + WAV → /api/gsm/listen (GSM hoparlör yolu için hassas) */
    private void recordAndUploadLoop() {
        if (!running || playing) return;
        listening = true;
        updateNotification("Arayanı dinliyorum (mikrofon)...");
        ensureSpeakerphone();

        final int sampleRate = 16000;
        final int channelConfig = AudioFormat.CHANNEL_IN_MONO;
        final int audioFormat = AudioFormat.ENCODING_PCM_16BIT;
        int minBuf = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat);
        if (minBuf <= 0) minBuf = sampleRate * 2;
        int bufSize = Math.max(minBuf, sampleRate); // ~1 sn

        try {
            // Hoparlörden gelen karşı taraf sesi için MIC daha iyi yakalar
            audioRecord = new AudioRecord(
                    MediaRecorder.AudioSource.MIC,
                    sampleRate, channelConfig, audioFormat, bufSize
            );
            if (audioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                try { audioRecord.release(); } catch (Exception ignored) {}
                audioRecord = new AudioRecord(
                        MediaRecorder.AudioSource.VOICE_RECOGNITION,
                        sampleRate, channelConfig, audioFormat, bufSize
                );
            }
            if (audioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                try { audioRecord.release(); } catch (Exception ignored) {}
                audioRecord = new AudioRecord(
                        MediaRecorder.AudioSource.VOICE_COMMUNICATION,
                        sampleRate, channelConfig, audioFormat, bufSize
                );
            }
            if (audioRecord.getState() != AudioRecord.STATE_INITIALIZED) {
                Log.e(TAG, "AudioRecord başlatılamadı");
                listening = false;
                mainHandler.postDelayed(this::beginListenCycle, 1500);
                return;
            }

            audioRecord.startRecording();
            Log.d(TAG, "Kayıt başladı — arayan konuşsun");

            ByteArrayOutputStream pcm = new ByteArrayOutputStream();
            byte[] buf = new byte[minBuf];
            long start = System.currentTimeMillis();
            boolean speechSeen = false;
            long lastSpeechAt = start;
            final int maxMs = 16000;
            final int silenceEndMs = 1400;
            final int waitForSpeechMs = 8000;
            final double threshold = 180.0; // hoparlör sızıntısı için çok düşük eşik

            while (running && listening && (System.currentTimeMillis() - start) < maxMs) {
                int n = audioRecord.read(buf, 0, buf.length);
                if (n <= 0) continue;
                pcm.write(buf, 0, n);

                double rms = rms16(buf, n);
                if (rms > threshold) {
                    if (!speechSeen) Log.d(TAG, "Konuşma algılandı rms=" + (int) rms);
                    speechSeen = true;
                    lastSpeechAt = System.currentTimeMillis();
                } else if (speechSeen && (System.currentTimeMillis() - lastSpeechAt) > silenceEndMs) {
                    Log.d(TAG, "Sessizlik — kayıt bitiyor");
                    break;
                }
                if (!speechSeen && (System.currentTimeMillis() - start) > waitForSpeechMs) {
                    Log.d(TAG, "10sn konuşma yok — yine de buffer gönder / tekrar dinle");
                    break;
                }
            }

            stopAudioRecord();
            listening = false;

            byte[] pcmBytes = pcm.toByteArray();
            // En az ~1.2 sn veri
            if (pcmBytes.length < sampleRate * 2) {
                Log.d(TAG, "Kayıt çok kısa, tekrar dinle");
                mainHandler.postDelayed(this::beginListenCycle, 600);
                return;
            }

            // Konuşma net algılanmasa bile Whisper'a gönder (sessizliği kendi filtreler)
            if (!speechSeen) {
                Log.d(TAG, "VAD zayıf — yine de Whisper'a gönderiliyor (" + pcmBytes.length + " byte)");
            }

            File wav = writeWav(pcmBytes, sampleRate);
            Log.d(TAG, "WAV hazır: " + wav.getAbsolutePath() + " size=" + wav.length());
            postListenAudio(wav);
        } catch (Exception e) {
            Log.e(TAG, "recordAndUploadLoop: " + e.getMessage(), e);
            listening = false;
            stopAudioRecord();
            if (running) mainHandler.postDelayed(this::beginListenCycle, 1200);
        }
    }

    private void sendTextTurn(String text) {
        if (!running) return;
        updateNotification("Ahmet düşünüyor...");
        try {
            // veda algısı
            String lower = text.toLowerCase(Locale.ROOT);
            if (lower.contains("görüşürüz") || lower.contains("gorusuruz")
                    || lower.contains("bay bay") || lower.contains("hoşça kal")
                    || lower.contains("hosca kal") || lower.contains("kapat")) {
                // yine de bir tur cevapla, sonra bitir
            }

            URL url = new URL(serverBase + "api/gsm/turn");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json; utf-8");
            conn.setRequestProperty("Accept", "application/json");
            conn.setDoOutput(true);
            conn.setConnectTimeout(4000);
            conn.setReadTimeout(45000);

            JSONObject body = new JSONObject();
            body.put("caller_name", callerName);
            body.put("message", text);
            body.put("history", history);
            if (callId > 0) body.put("call_id", callId);

            try (OutputStream os = conn.getOutputStream()) {
                os.write(body.toString().getBytes("utf-8"));
            }

            int code = conn.getResponseCode();
            String resp = readBody(conn);
            conn.disconnect();
            if (code != 200) {
                Log.w(TAG, "turn HTTP " + code + ": " + resp);
                mainHandler.postDelayed(this::beginListenCycle, 1200);
                return;
            }

            JSONObject json = new JSONObject(resp);
            String reply = json.optString("reply", "");
            String audioUrl = json.optString("audio_url", "");

            history.put(new JSONObject().put("role", "user").put("content", text));
            if (!reply.isEmpty()) {
                history.put(new JSONObject().put("role", "assistant").put("content", reply));
            }
            turnCount++;

            if (!audioUrl.isEmpty()) {
                String full = audioUrl.startsWith("http") ? audioUrl : serverBase + audioUrl.replaceFirst("^/", "");
                mainHandler.post(() -> playReply(full, shouldEndAfter(text, reply)));
            } else {
                boolean end = shouldEndAfter(text, reply);
                if (end) stopDialogue("farewell");
                else mainHandler.postDelayed(this::beginListenCycle, 600);
            }
        } catch (Exception e) {
            Log.e(TAG, "sendTextTurn: " + e.getMessage(), e);
            if (running) mainHandler.postDelayed(this::beginListenCycle, 1500);
        }
    }

    private void postListenAudio(File wav) {
        if (!running) return;
        updateNotification("Ses sunucuya gönderiliyor...");
        try {
            String boundary = "----Tenra" + System.currentTimeMillis();
            URL url = new URL(serverBase + "api/gsm/listen");
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setDoOutput(true);
            conn.setConnectTimeout(4000);
            conn.setReadTimeout(90000);
            conn.setRequestProperty("Content-Type", "multipart/form-data; boundary=" + boundary);

            try (DataOutputStream out = new DataOutputStream(conn.getOutputStream())) {
                writeFormField(out, boundary, "caller_name", callerName);
                writeFormField(out, boundary, "history", history.toString());
                if (callId > 0) writeFormField(out, boundary, "call_id", String.valueOf(callId));

                out.writeBytes("--" + boundary + "\r\n");
                out.writeBytes("Content-Disposition: form-data; name=\"audio\"; filename=\"utterance.wav\"\r\n");
                out.writeBytes("Content-Type: audio/wav\r\n\r\n");
                try (FileInputStream fis = new FileInputStream(wav)) {
                    byte[] buf = new byte[8192];
                    int n;
                    while ((n = fis.read(buf)) > 0) out.write(buf, 0, n);
                }
                out.writeBytes("\r\n");
                out.writeBytes("--" + boundary + "--\r\n");
                out.flush();
            }

            int code = conn.getResponseCode();
            String resp = readBody(conn);
            conn.disconnect();
            try { wav.delete(); } catch (Exception ignored) {}

            if (code != 200) {
                Log.w(TAG, "listen HTTP " + code + ": " + resp);
                mainHandler.postDelayed(this::beginListenCycle, 1200);
                return;
            }

            JSONObject json = new JSONObject(resp);
            String transcript = json.optString("transcript", "");
            String reply = json.optString("reply", "");
            String audioUrl = json.optString("audio_url", "");
            boolean empty = "empty_transcript".equals(json.optString("error"));

            if (!transcript.isEmpty()) {
                history.put(new JSONObject().put("role", "user").put("content", transcript));
            }
            if (!reply.isEmpty()) {
                history.put(new JSONObject().put("role", "assistant").put("content", reply));
            }
            turnCount++;

            // empty olsa bile "duyamadım" sesi varsa çal — sessiz döngü olmasın
            if (!audioUrl.isEmpty()) {
                String full = audioUrl.startsWith("http") ? audioUrl : serverBase + audioUrl.replaceFirst("^/", "");
                mainHandler.post(() -> playReply(full, !empty && shouldEndAfter(transcript, reply)));
            } else if (empty) {
                mainHandler.postDelayed(this::beginListenCycle, 700);
            } else {
                if (shouldEndAfter(transcript, reply)) stopDialogue("farewell");
                else mainHandler.postDelayed(this::beginListenCycle, 600);
            }
        } catch (Exception e) {
            Log.e(TAG, "postListenAudio: " + e.getMessage(), e);
            if (running) mainHandler.postDelayed(this::beginListenCycle, 1500);
        }
    }

    private boolean shouldEndAfter(String user, String reply) {
        String u = (user == null ? "" : user).toLowerCase(Locale.ROOT);
        String r = (reply == null ? "" : reply).toLowerCase(Locale.ROOT);
        return u.contains("görüşürüz") || u.contains("gorusuruz") || u.contains("bay bay")
                || r.contains("görüşürüz") || r.contains("kendine iyi bak");
    }

    private void playReply(String audioUrl, boolean endAfter) {
        if (!running) return;
        playing = true;
        listening = false;
        destroySpeechRecognizer();
        stopReplyPlayer();
        TenraPrefsPlugin.acquireAudioLock(this, 60000);
        updateNotification("Ahmet konuşuyor...");
        CallReceiver.forceSpeakerLoud(this);

        new Thread(() -> {
            try {
                File local = downloadToCache(audioUrl, "reply_");
                mainHandler.post(() -> playLocalFile(local.getAbsolutePath(), endAfter, false));
            } catch (Exception e) {
                Log.e(TAG, "playReply indir: " + e.getMessage());
                mainHandler.post(() -> {
                    try {
                        replyPlayer = new MediaPlayer();
                        replyPlayer.setAudioAttributes(new AudioAttributes.Builder()
                                .setUsage(AudioAttributes.USAGE_ALARM)
                                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                                .build());
                        replyPlayer.setVolume(1.0f, 1.0f);
                        replyPlayer.setDataSource(audioUrl);
                        replyPlayer.setOnPreparedListener(mp -> {
                            CallReceiver.forceSpeakerLoud(this);
                            mp.start();
                        });
                        replyPlayer.setOnCompletionListener(mp -> {
                            stopReplyPlayer();
                            playing = false;
                            if (!running) return;
                            if (endAfter) stopDialogue("farewell");
                            else mainHandler.postDelayed(this::beginListenCycle, 800);
                        });
                        replyPlayer.setOnErrorListener((mp, what, extra) -> {
                            stopReplyPlayer();
                            playing = false;
                            if (running) mainHandler.postDelayed(this::beginListenCycle, 800);
                            return true;
                        });
                        replyPlayer.prepareAsync();
                    } catch (Exception ex) {
                        playing = false;
                        if (running) mainHandler.postDelayed(this::beginListenCycle, 800);
                    }
                });
            }
        }, "tenra-reply").start();
    }

    private void stopReplyPlayer() {
        if (replyPlayer != null) {
            try {
                if (replyPlayer.isPlaying()) replyPlayer.stop();
                replyPlayer.release();
            } catch (Exception ignored) {}
            replyPlayer = null;
        }
    }

    private void stopAudioRecord() {
        if (audioRecord != null) {
            try {
                audioRecord.stop();
            } catch (Exception ignored) {}
            try {
                audioRecord.release();
            } catch (Exception ignored) {}
            audioRecord = null;
        }
    }

    private void ensureSpeakerphone() {
        CallReceiver.forceSpeakerLoud(this);
    }

    private String resolveServerUrl() {
        SharedPreferences prefs = getSharedPreferences(TenraPrefsPlugin.PREFS_NAME, MODE_PRIVATE);
        String custom = prefs.getString(TenraPrefsPlugin.KEY_SERVER_URL,
                prefs.getString(TenraPrefsPlugin.KEY_SERVER_URL_ALT, ""));
        if (custom != null && !custom.trim().isEmpty()) return custom.trim();
        return "http://192.168.1.100:8008";
    }

    private void createChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel ch = new NotificationChannel(
                    CHANNEL_ID, "TENRA Canlı Arama", NotificationManager.IMPORTANCE_LOW);
            ch.setDescription("GSM iki yönlü diyalog");
            NotificationManager nm = getSystemService(NotificationManager.class);
            if (nm != null) nm.createNotificationChannel(ch);
        }
    }

    private Notification buildNotification(String text) {
        Intent open = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(
                this, 0, open,
                PendingIntent.FLAG_UPDATE_CURRENT | PendingIntent.FLAG_IMMUTABLE
        );
        return new NotificationCompat.Builder(this, CHANNEL_ID)
                .setContentTitle("TenraTwin Asistan")
                .setContentText(text)
                .setSmallIcon(android.R.drawable.ic_btn_speak_now)
                .setContentIntent(pi)
                .setOngoing(true)
                .build();
    }

    private void updateNotification(String text) {
        try {
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            if (nm != null) nm.notify(NOTIF_ID, buildNotification(text));
        } catch (Exception ignored) {}
    }

    private static double rms16(byte[] buf, int len) {
        if (len < 2) return 0;
        long sum = 0;
        int samples = len / 2;
        for (int i = 0; i + 1 < len; i += 2) {
            short s = (short) ((buf[i] & 0xff) | (buf[i + 1] << 8));
            sum += (long) s * s;
        }
        return Math.sqrt(sum / (double) Math.max(1, samples));
    }

    private File writeWav(byte[] pcm, int sampleRate) throws Exception {
        File f = new File(getCacheDir(), "gsm_utt_" + System.currentTimeMillis() + ".wav");
        int channels = 1;
        int byteRate = sampleRate * channels * 2;
        try (FileOutputStream out = new FileOutputStream(f)) {
            writeString(out, "RIFF");
            writeInt(out, 36 + pcm.length);
            writeString(out, "WAVE");
            writeString(out, "fmt ");
            writeInt(out, 16);
            writeShort(out, (short) 1);
            writeShort(out, (short) channels);
            writeInt(out, sampleRate);
            writeInt(out, byteRate);
            writeShort(out, (short) (channels * 2));
            writeShort(out, (short) 16);
            writeString(out, "data");
            writeInt(out, pcm.length);
            out.write(pcm);
        }
        return f;
    }

    private static void writeString(FileOutputStream out, String s) throws Exception {
        out.write(s.getBytes("US-ASCII"));
    }
    private static void writeInt(FileOutputStream out, int v) throws Exception {
        out.write(ByteBuffer.allocate(4).order(ByteOrder.LITTLE_ENDIAN).putInt(v).array());
    }
    private static void writeShort(FileOutputStream out, short v) throws Exception {
        out.write(ByteBuffer.allocate(2).order(ByteOrder.LITTLE_ENDIAN).putShort(v).array());
    }

    private static void writeFormField(DataOutputStream out, String boundary, String name, String value) throws Exception {
        out.writeBytes("--" + boundary + "\r\n");
        out.writeBytes("Content-Disposition: form-data; name=\"" + name + "\"\r\n\r\n");
        out.writeBytes(value + "\r\n");
    }

    private static String readBody(HttpURLConnection conn) {
        try {
            BufferedReader br = new BufferedReader(new InputStreamReader(
                    conn.getResponseCode() >= 400 ? conn.getErrorStream() : conn.getInputStream(), "utf-8"));
            StringBuilder sb = new StringBuilder();
            String line;
            while ((line = br.readLine()) != null) sb.append(line);
            br.close();
            return sb.toString();
        } catch (Exception e) {
            return "";
        }
    }
}

package ai.tenra.app;

import android.Manifest;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import androidx.annotation.NonNull;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import android.os.Handler;
import android.os.Looper;

import com.getcapacitor.BridgeActivity;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends BridgeActivity {
    private static final String TAG = "TENRA_MainActivity";
    private static final int PERMISSION_REQUEST_CODE = 1001;

    private boolean pendingAutoCall = false;
    private boolean pendingNativeAudioOwned = false;
    private String pendingCallerName = "";
    private String pendingCallerNumber = "";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        registerPlugin(TenraPrefsPlugin.class);
        super.onCreate(savedInstanceState);

        captureCallExtras(getIntent());

        new Handler(Looper.getMainLooper()).postDelayed(() -> {
            try {
                requestRequiredPermissions();
            } catch (Exception e) {
                Log.e(TAG, "İzin isteme hatası: " + e.getMessage(), e);
            }
            notifyWebOfPendingCall();
        }, 500);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        captureCallExtras(intent);
        notifyWebOfPendingCall();
    }

    private void captureCallExtras(Intent intent) {
        if (intent == null) return;
        if (intent.getBooleanExtra("auto_call", false)) {
            pendingAutoCall = true;
            pendingNativeAudioOwned = intent.getBooleanExtra("native_audio_owned", true);
            pendingCallerName = intent.getStringExtra("caller_name");
            pendingCallerNumber = intent.getStringExtra("caller_number");
            if (pendingCallerName == null) pendingCallerName = "";
            if (pendingCallerNumber == null) pendingCallerNumber = "";
            if (pendingNativeAudioOwned) {
                TenraPrefsPlugin.acquireAudioLock(this, 60000);
            }
            Log.d(TAG, "auto_call yakalandı (native_audio_owned=" + pendingNativeAudioOwned + ")");
        }
        // CallReceiver FGS başlatamazsa yedek yol
        if (intent.getBooleanExtra("start_dialogue", false) && !GsmDialogueService.isRunning()) {
            try {
                Intent svc = new Intent(this, GsmDialogueService.class);
                svc.putExtra("caller_name", intent.getStringExtra("caller_name"));
                svc.putExtra("caller_number", intent.getStringExtra("caller_number"));
                svc.putExtra("call_id", intent.getIntExtra("call_id", -1));
                svc.putExtra("server_url", intent.getStringExtra("server_url"));
                svc.putExtra("greeting_url", intent.getStringExtra("greeting_url"));
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    startForegroundService(svc);
                } else {
                    startService(svc);
                }
                Log.d(TAG, "Diyalog Activity yedeğinden başlatıldı");
            } catch (Exception e) {
                Log.e(TAG, "start_dialogue yedek: " + e.getMessage());
            }
        }
    }

    private void notifyWebOfPendingCall() {
        if (!pendingAutoCall || getBridge() == null || getBridge().getWebView() == null) return;
        try {
            String name = pendingCallerName.replace("\\", "\\\\").replace("'", "\\'");
            String number = pendingCallerNumber.replace("\\", "\\\\").replace("'", "\\'");
            boolean owned = pendingNativeAudioOwned;
            String js = "window.dispatchEvent(new CustomEvent('tenra-gsm-handled',{detail:{"
                    + "callerName:'" + name + "',"
                    + "callerNumber:'" + number + "',"
                    + "nativeAudioOwned:" + owned
                    + "}}));";
            getBridge().getWebView().post(() ->
                    getBridge().getWebView().evaluateJavascript(js, null)
            );
            // Tek seferlik; tekrar onResume'da spam olmasın
            pendingAutoCall = false;
        } catch (Exception e) {
            Log.w(TAG, "JS event gönderilemedi: " + e.getMessage());
        }
    }

    private void requestRequiredPermissions() {
        List<String> permissionsNeeded = new ArrayList<>();

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) {
            permissionsNeeded.add(Manifest.permission.READ_PHONE_STATE);
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ANSWER_PHONE_CALLS) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.ANSWER_PHONE_CALLS);
            }
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALL_LOG) != PackageManager.PERMISSION_GRANTED) {
            permissionsNeeded.add(Manifest.permission.READ_CALL_LOG);
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            permissionsNeeded.add(Manifest.permission.READ_CONTACTS);
        }

        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            permissionsNeeded.add(Manifest.permission.RECORD_AUDIO);
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.POST_NOTIFICATIONS);
            }
        }

        if (!permissionsNeeded.isEmpty()) {
            Log.d(TAG, "Gerekli izinler kullanıcıdan isteniyor: " + permissionsNeeded);
            ActivityCompat.requestPermissions(
                    this,
                    permissionsNeeded.toArray(new String[0]),
                    PERMISSION_REQUEST_CODE
            );
        } else {
            Log.d(TAG, "Tüm arama ve rehber izinleri zaten verilmiş.");
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, @NonNull String[] permissions, @NonNull int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == PERMISSION_REQUEST_CODE) {
            for (int i = 0; i < permissions.length; i++) {
                if (grantResults.length > i && grantResults[i] == PackageManager.PERMISSION_GRANTED) {
                    Log.d(TAG, "İzin verildi: " + permissions[i]);
                } else {
                    Log.w(TAG, "İzin reddedildi: " + permissions[i]);
                }
            }
        }
    }
}

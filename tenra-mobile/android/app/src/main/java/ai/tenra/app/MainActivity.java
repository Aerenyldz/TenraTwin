package ai.tenra.app;

import android.Manifest;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.util.Log;
import androidx.annotation.NonNull;
import androidx.core.app.ActivityCompat;
import androidx.core.content.ContextCompat;

import com.getcapacitor.BridgeActivity;

import java.util.ArrayList;
import java.util.List;

public class MainActivity extends BridgeActivity {
    private static final String TAG = "TENRA_MainActivity";
    private static final int PERMISSION_REQUEST_CODE = 1001;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        requestRequiredPermissions();
    }

    /**
     * Android 8+ ve 10+ için gelen aramaları yakalama, cevaplama ve rehber okuma izinlerini
     * kullanıcıdan çalışma zamanında (Runtime Dialog) talep eder.
     */
    private void requestRequiredPermissions() {
        List<String> permissionsNeeded = new ArrayList<>();

        // 1. Telefon Durumu ve Arama Cevaplama
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_PHONE_STATE) != PackageManager.PERMISSION_GRANTED) {
            permissionsNeeded.add(Manifest.permission.READ_PHONE_STATE);
        }

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (ContextCompat.checkSelfPermission(this, Manifest.permission.ANSWER_PHONE_CALLS) != PackageManager.PERMISSION_GRANTED) {
                permissionsNeeded.add(Manifest.permission.ANSWER_PHONE_CALLS);
            }
        }

        // 2. Arama Kaydı ve Numara Tespiti (Android 9+)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CALL_LOG) != PackageManager.PERMISSION_GRANTED) {
            permissionsNeeded.add(Manifest.permission.READ_CALL_LOG);
        }

        // 3. Rehberden İsim Okuma (Kimin aradığını tespit etmek için)
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.READ_CONTACTS) != PackageManager.PERMISSION_GRANTED) {
            permissionsNeeded.add(Manifest.permission.READ_CONTACTS);
        }

        // 4. Mikrofon İzni
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            permissionsNeeded.add(Manifest.permission.RECORD_AUDIO);
        }

        // 5. Android 13+ Bildirim İzni
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

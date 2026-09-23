package ai.tenra.app;

import android.content.Context;
import android.content.SharedPreferences;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

/**
 * React ↔ Android SharedPreferences köprüsü.
 * CallReceiver ile aynı "CapacitorStorage" deposunu kullanır.
 */
@CapacitorPlugin(name = "TenraPrefs")
public class TenraPrefsPlugin extends Plugin {
    public static final String PREFS_NAME = "CapacitorStorage";
    public static final String KEY_SERVER_URL = "tenra_server_url";
    public static final String KEY_SERVER_URL_ALT = "server_url";
    public static final String KEY_AUTO_DELAY = "auto_answer_delay";
    public static final String KEY_GSM_AUTO_ANSWER = "gsm_auto_answer";
    public static final String KEY_AUDIO_LOCK = "tenra_native_audio_lock";
    public static final String KEY_AUDIO_LOCK_UNTIL = "tenra_native_audio_lock_until";

    private SharedPreferences prefs() {
        return getContext().getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
    }

    @PluginMethod
    public void set(PluginCall call) {
        String key = call.getString("key");
        String value = call.getString("value", "");
        if (key == null || key.isEmpty()) {
            call.reject("key gerekli");
            return;
        }
        prefs().edit().putString(key, value).apply();
        // server_url eşlemesi: CallReceiver her iki anahtarı da okur
        if (KEY_SERVER_URL.equals(key) || KEY_SERVER_URL_ALT.equals(key)) {
            prefs().edit()
                    .putString(KEY_SERVER_URL, value)
                    .putString(KEY_SERVER_URL_ALT, value)
                    .apply();
        }
        call.resolve();
    }

    @PluginMethod
    public void get(PluginCall call) {
        String key = call.getString("key");
        if (key == null || key.isEmpty()) {
            call.reject("key gerekli");
            return;
        }
        JSObject ret = new JSObject();
        ret.put("value", prefs().getString(key, null));
        call.resolve(ret);
    }

    @PluginMethod
    public void setAudioMutex(PluginCall call) {
        boolean active = Boolean.TRUE.equals(call.getBoolean("active", true));
        int ttlMs = call.getInt("ttlMs", 45000);
        SharedPreferences.Editor ed = prefs().edit();
        if (active) {
            ed.putString(KEY_AUDIO_LOCK, "1");
            ed.putString(KEY_AUDIO_LOCK_UNTIL, String.valueOf(System.currentTimeMillis() + ttlMs));
        } else {
            ed.putString(KEY_AUDIO_LOCK, "0");
            ed.putString(KEY_AUDIO_LOCK_UNTIL, "0");
        }
        ed.apply();
        call.resolve();
    }

    @PluginMethod
    public void isAudioMutexActive(PluginCall call) {
        SharedPreferences p = prefs();
        boolean flag = "1".equals(p.getString(KEY_AUDIO_LOCK, "0"));
        long until = 0;
        try {
            until = Long.parseLong(p.getString(KEY_AUDIO_LOCK_UNTIL, "0"));
        } catch (Exception ignored) {}
        boolean active = flag && until > System.currentTimeMillis();
        JSObject ret = new JSObject();
        ret.put("active", active);
        call.resolve(ret);
    }

    /** CallReceiver'dan statik erişim */
    public static void writeString(Context ctx, String key, String value) {
        ctx.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .edit().putString(key, value).apply();
    }

    public static String readString(Context ctx, String key, String def) {
        return ctx.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE)
                .getString(key, def);
    }

    public static void acquireAudioLock(Context ctx, long ttlMs) {
        SharedPreferences.Editor ed = ctx.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE).edit();
        ed.putString(KEY_AUDIO_LOCK, "1");
        ed.putString(KEY_AUDIO_LOCK_UNTIL, String.valueOf(System.currentTimeMillis() + ttlMs));
        ed.apply();
    }

    public static boolean isAudioLocked(Context ctx) {
        SharedPreferences p = ctx.getSharedPreferences(PREFS_NAME, Context.MODE_PRIVATE);
        if (!"1".equals(p.getString(KEY_AUDIO_LOCK, "0"))) return false;
        try {
            return Long.parseLong(p.getString(KEY_AUDIO_LOCK_UNTIL, "0")) > System.currentTimeMillis();
        } catch (Exception e) {
            return false;
        }
    }
}

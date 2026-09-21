"""
TENRA Voice Twin - Call Logs Database
Gelen aramaları, konuşma dökümlerini, ses kaydı dosya yolunu ve özet notları SQLite'ta saklar.
"""
import os
import sqlite3
from datetime import datetime

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
DB_PATH = os.path.join(PROJECT_ROOT, "call_logs.db")

def get_connection():
    return sqlite3.connect(DB_PATH)

def init_db():
    """Çağrı ve not veritabanını ilklendirir."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS call_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                caller_name TEXT NOT NULL,
                timestamp TEXT NOT NULL,
                transcript TEXT NOT NULL,
                summary TEXT NOT NULL,
                urgency TEXT DEFAULT 'normal', -- 'acil', 'normal', 'onemsiz'
                audio_file TEXT DEFAULT '',
                is_read INTEGER DEFAULT 0
            )
        """)
        conn.commit()

        # Eksik sütun kontrolü ve otomatik migrasyon
        cursor.execute("PRAGMA table_info(call_logs)")
        cols = [c[1] for c in cursor.fetchall()]
        if "audio_file" not in cols:
            cursor.execute("ALTER TABLE call_logs ADD COLUMN audio_file TEXT DEFAULT ''")
            conn.commit()

        # Asistan Ayarları Tablosu
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS assistant_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)
        cursor.execute("INSERT OR IGNORE INTO assistant_settings (key, value) VALUES ('status', 'Okulda')")
        cursor.execute("INSERT OR IGNORE INTO assistant_settings (key, value) VALUES ('status_detail', 'Ahmet şu an derste, önemli bir şey varsa not alıyorum.')")
        conn.commit()

def add_call(caller_name: str, transcript: str, summary: str, urgency: str = "normal", audio_file: str = "") -> int:
    """Yeni bir arama kaydı, ses dosyası ve özet not ekler."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO call_logs (caller_name, timestamp, transcript, summary, urgency, audio_file, is_read)
            VALUES (?, ?, ?, ?, ?, ?, 0)
        """, (caller_name, datetime.now().strftime("%Y-%m-%d %H:%M:%S"), transcript, summary, urgency, audio_file))
        conn.commit()
        return cursor.lastrowid

def update_call_audio(call_id: int, audio_file: str):
    """Çağrı kaydına ses dosyası yolunu bağlar."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE call_logs SET audio_file = ? WHERE id = ?", (audio_file, call_id))
        conn.commit()

def mark_call_read(call_id: int):
    """Çağrıyı okundu olarak işaretler."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE call_logs SET is_read = 1 WHERE id = ?", (call_id,))
        conn.commit()

def get_assistant_status() -> dict:
    """Mevcut asistan durumunu (Okulda, Sporda vs.) döndürür."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM assistant_settings")
        rows = dict(cursor.fetchall())
        return {
            "status": rows.get("status", "Okulda"),
            "status_detail": rows.get("status_detail", "Ahmet şu an derste, notunuzu alabilirim.")
        }

def set_assistant_status(status: str, status_detail: str):
    """Asistan durumunu günceller."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO assistant_settings (key, value) VALUES ('status', ?)", (status,))
        cursor.execute("INSERT OR REPLACE INTO assistant_settings (key, value) VALUES ('status_detail', ?)", (status_detail,))
        conn.commit()

def get_setting(key: str, default: str = "") -> str:
    """Belirtilen anahtara ait ayar değerini getirir."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM assistant_settings WHERE key = ?", (key,))
        row = cursor.fetchone()
        return row[0] if row else default

def set_setting(key: str, value: str):
    """Belirtilen ayar değerini SQLite'a kaydeder."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT OR REPLACE INTO assistant_settings (key, value) VALUES (?, ?)", (key, str(value)))
        conn.commit()

def get_all_settings() -> dict:
    """Tüm ayarları sözlük olarak döndürür."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT key, value FROM assistant_settings")
        return dict(cursor.fetchall())


def get_recent_calls(limit: int = 20) -> list[dict]:
    """Son çağrıları ve notları listeler."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, caller_name, timestamp, summary, urgency, is_read, transcript, audio_file
            FROM call_logs
            ORDER BY id DESC
            LIMIT ?
        """, (limit,))
        rows = cursor.fetchall()
        return [
            {
                "id": r[0],
                "caller_name": r[1],
                "timestamp": r[2],
                "summary": r[3],
                "urgency": r[4],
                "is_read": bool(r[5]),
                "transcript": r[6],
                "audio_file": r[7] if len(r) > 7 else ""
            }
            for r in rows
        ]

def delete_call(call_id: int) -> bool:
    """Belirtilen çağrı kaydını siler."""
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM call_logs WHERE id = ?", (call_id,))
        conn.commit()
        return cursor.rowcount > 0

if __name__ == "__main__":
    init_db()
    print("Call logs database hazır:", DB_PATH)



# init_db.py
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "backend.db")

def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    # readings: store raw JSON too for forensics
    c.execute("""
    CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        meterID TEXT NOT NULL,
        seq INTEGER NOT NULL,
        ts INTEGER NOT NULL,
        value REAL,
        raw TEXT,
        received_at INTEGER DEFAULT (strftime('%s','now'))
    )
    """)
    # index for quick last-seq lookup
    c.execute("CREATE INDEX IF NOT EXISTS idx_meter_seq ON readings(meterID, seq)")
    conn.commit()
    conn.close()

def get_last_seq(meterID):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT seq FROM readings WHERE meterID=? ORDER BY seq DESC LIMIT 1", (meterID,))
    row = c.fetchone()
    conn.close()
    return row[0] if row else 0

def store_reading(payload: dict):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        "INSERT INTO readings (meterID, seq, ts, value, raw) VALUES (?,?,?,?,?)",
        (
            payload.get("meterID"),
            payload.get("seq"),
            payload.get("ts"),
            payload.get("value"),
            json_dump(payload)
        )
    )
    conn.commit()
    conn.close()

def json_dump(obj):
    import json
    return json.dumps(obj, separators=(",", ":"), sort_keys=False)

# init_db.py
import sqlite3
import os
import json
import logging
import time

# ---------- Config ----------
DB_PATH = os.path.join(os.path.dirname(__file__), "backend.db")

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("backend.log"),
        logging.StreamHandler()
    ]
)

# ---------- Initialization ----------
def init_db():
    """
    Initialize the SQLite database with the readings table.
    Each entry contains:
        - meterID: unique meter address
        - seq: sequence number (for replay detection)
        - ts: timestamp of reading
        - value: measured energy
        - raw: full JSON for forensic audit
        - blockchain_hash: placeholder for on-chain commit
        - suspicious: flag from IDS (0/1)
        - score: IDS score
        - reasons: IDS reasons (JSON string)
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
                CREATE TABLE IF NOT EXISTS readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meterID TEXT NOT NULL,
                    seq INTEGER NOT NULL,
                    ts INTEGER NOT NULL,
                    value REAL,
                    raw TEXT,
                    blockchain_hash TEXT,
                    suspicious INTEGER DEFAULT 0,
                    score REAL DEFAULT 0.0,
                    reasons TEXT,
                    received_at INTEGER DEFAULT (strftime('%s','now'))
                )
            """)
            c.execute("CREATE INDEX IF NOT EXISTS idx_meter_seq ON readings(meterID, seq)")
            conn.commit()
            logging.info("Database initialized successfully.")
    except Exception as e:
        logging.error(f"Database initialization failed: {e}")
        raise


# ---------- Helper Functions ----------
def get_last_seq(meterID: str) -> int:
    """Return the last sequence number for the given meterID, or 0 if none."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("SELECT seq FROM readings WHERE meterID=? ORDER BY seq DESC LIMIT 1", (meterID,))
            row = c.fetchone()
            return row[0] if row else 0
    except Exception as e:
        logging.error(f"Error fetching last seq for {meterID}: {e}")
        return 0


def store_reading(payload: dict, suspicious: bool = False, reasons: list = None,
                  score: float = 0.0, blockchain_hash: str = None, 
                  ids_confidence: float = 0.0, forensic_result: dict = None, 
                  request_id: str = None):
    """
    Store a verified reading in the database.
    Includes optional blockchain reference and IDS results.
    """
    if not payload or "meterID" not in payload or "seq" not in payload:
        logging.warning(f"Invalid payload skipped: {payload}")
        return

    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute(
                """
                INSERT INTO readings
                (meterID, seq, ts, value, raw, blockchain_hash, suspicious, score, reasons)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.get("meterID"),
                    int(payload.get("seq")),
                    int(payload.get("ts")),
                    float(payload.get("value", 0.0)),
                    json.dumps(payload, separators=(",", ":"), sort_keys=False),
                    blockchain_hash,
                    1 if suspicious else 0,
                    float(score),
                    json.dumps(reasons) if reasons else None
                )
            )
            conn.commit()
            logging.info(f"Stored reading: meter={payload.get('meterID')} seq={payload.get('seq')} suspicious={suspicious} score={score}")
    except Exception as e:
        logging.error(f"Failed to store reading: {e}")
        raise


# ---------- Utility ----------
def dump_all_readings(limit: int = 10):
    """Quick debug utility — print recent readings."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT meterID, seq, ts, value, blockchain_hash, suspicious, score, reasons
                FROM readings
                ORDER BY id DESC
                LIMIT ?
            """, (limit,))
            rows = c.fetchall()
            for r in rows:
                print(r)
    except Exception as e:
        logging.error(f"Failed to dump readings: {e}")


def get_reading_history(meterID: str, limit: int = 10) -> list:
    """Get recent reading history for a meter"""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT meterID, seq, ts, value, raw, blockchain_hash, suspicious, 
                       score, reasons, received_at
                FROM readings
                WHERE meterID = ?
                ORDER BY seq DESC
                LIMIT ?
            """, (meterID, limit))
            
            rows = c.fetchall()
            readings = []
            
            for row in rows:
                try:
                    raw_data = json.loads(row[4]) if row[4] else {}
                    reasons = json.loads(row[8]) if row[8] else []
                except:
                    raw_data = {}
                    reasons = []
                
                readings.append({
                    "meterID": row[0],
                    "seq": row[1],
                    "ts": row[2],
                    "value": row[3],
                    "blockchain_hash": row[5],
                    "suspicious": bool(row[6]),
                    "score": row[7],
                    "reasons": reasons,
                    "received_at": row[9]
                })
            
            return readings
            
    except Exception as e:
        logging.error(f"Failed to get reading history for {meterID}: {e}")
        return []
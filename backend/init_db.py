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

# --- Dashboard query helpers ---

def list_readings(meterID: str | None = None, limit: int = 50, offset: int = 0,
                  ts_from: int | None = None, ts_to: int | None = None) -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            params = []
            where = []
            if meterID:
                where.append("meterID = ?")
                params.append(meterID)
            if ts_from is not None:
                where.append("ts >= ?")
                params.append(int(ts_from))
            if ts_to is not None:
                where.append("ts <= ?")
                params.append(int(ts_to))
            where_clause = ("WHERE " + " AND ".join(where)) if where else ""
            q = f"""
                SELECT meterID, seq, ts, value, blockchain_hash, suspicious, score, reasons, received_at
                FROM readings
                {where_clause}
                ORDER BY ts DESC
                LIMIT ? OFFSET ?
            """
            params.extend([int(limit), int(offset)])
            c.execute(q, params)
            rows = c.fetchall()
            out = []
            for r in rows:
                try:
                    reasons = json.loads(r[7]) if r[7] else []
                except:
                    reasons = []
                out.append({
                    "meterID": r[0], "seq": r[1], "ts": r[2], "value": r[3],
                    "blockchain_hash": r[4], "suspicious": bool(r[5]),
                    "score": r[6], "reasons": reasons, "received_at": r[8]
                })
            return out
    except Exception as e:
        logging.error(f"list_readings failed: {e}")
        return []


def list_alerts(limit: int = 50, offset: int = 0, meterID: str | None = None,
                min_score: float = 0.0, ts_from: int | None = None, ts_to: int | None = None) -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            params = []
            where = ["suspicious = 1"]
            if meterID:
                where.append("meterID = ?")
                params.append(meterID)
            if min_score > 0.0:  # Changed: Only add condition if score > 0
                where.append("score >= ?")
                params.append(float(min_score))
            if ts_from is not None:
                where.append("ts >= ?")
                params.append(int(ts_from))
            if ts_to is not None:
                where.append("ts <= ?")
                params.append(int(ts_to))
            where_clause = "WHERE " + " AND ".join(where)
            q = f"""
                SELECT meterID, seq, ts, value, blockchain_hash, score, reasons, received_at
                FROM readings
                {where_clause}
                ORDER BY ts DESC
                LIMIT ? OFFSET ?
            """
            params.extend([int(limit), int(offset)])
            c.execute(q, params)
            rows = c.fetchall()
            out = []
            for r in rows:
                try:
                    reasons = json.loads(r[6]) if r[6] else []
                except:
                    reasons = []
                out.append({
                    "meterID": r[0], "seq": r[1], "ts": r[2], "value": r[3],
                    "blockchain_hash": r[4], "score": r[5], "reasons": reasons, "received_at": r[7]
                })
            return out
    except Exception as e:
        logging.error(f"list_alerts failed: {e}")
        return []


def list_meters() -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT meterID,
                       MAX(seq) as last_seq,
                       MAX(ts) as last_ts,
                       SUM(CASE WHEN suspicious=1 THEN 1 ELSE 0 END) as suspicious_count,
                       COUNT(*) as total
                FROM readings
                GROUP BY meterID
                ORDER BY last_ts DESC
            """)
            rows = c.fetchall()
            return [{
                "meterID": r[0],
                "last_seq": r[1] or 0,
                "last_update": r[2],
                "recent_suspicious_count": r[3] or 0,
                "total_readings": r[4] or 0
            } for r in rows]
    except Exception as e:
        logging.error(f"list_meters failed: {e}")
        return []


def get_meter_details(meterID: str) -> dict | None:  # Changed return type
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT MAX(seq), MAX(ts),
                       SUM(CASE WHEN suspicious=1 THEN 1 ELSE 0 END),
                       COUNT(*),
                       AVG(score)
                FROM readings
                WHERE meterID=?
            """, (meterID,))
            row = c.fetchone()
            
            # Check if meter exists
            if not row or row[3] == 0:
                return None
            
            return {
                "meterID": meterID,
                "last_seq": row[0] or 0,
                "last_update": row[1],
                "suspicious_count": row[2] or 0,
                "total_readings": row[3] or 0,
                "average_score": round(row[4] or 0.0, 3)
            }
    except Exception as e:
        logging.error(f"get_meter_details failed: {e}")
        return None 


def get_latest_readings(limit: int = 20) -> list[dict]:
    try:
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("""
                SELECT meterID, seq, ts, value, blockchain_hash, suspicious, score, reasons, received_at
                FROM readings
                ORDER BY ts DESC
                LIMIT ?
            """, (int(limit),))
            rows = c.fetchall()
            out = []
            for r in rows:
                try:
                    reasons = json.loads(r[7]) if r[7] else []
                except:
                    reasons = []
                out.append({
                    "meterID": r[0], "seq": r[1], "ts": r[2], "value": r[3],
                    "blockchain_hash": r[4], "suspicious": bool(r[5]),
                    "score": r[6], "reasons": reasons, "received_at": r[8]
                })
            return out
    except Exception as e:
        logging.error(f"get_latest_readings failed: {e}")
        return []
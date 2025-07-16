import sqlite3
from pathlib import Path

DB_FILE = 'starspy.db'

def get_connection():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                message_id TEXT UNIQUE,
                author TEXT,
                content TEXT,
                timestamp TEXT,
                score INTEGER,
                rsi_handle TEXT,
                source_file TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS import_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                filename TEXT UNIQUE,
                import_time TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()

def fetch_messages(limit=100):
    with get_connection() as conn:
        return conn.execute("""
            SELECT * FROM messages ORDER BY timestamp DESC LIMIT ?
        """, (limit,)).fetchall()

def fetch_watchlist_hits():
    wi

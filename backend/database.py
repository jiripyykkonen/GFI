import sqlite3
from pathlib import Path


# Keep one database regardless of the folder from which Uvicorn is started.
DATABASE_PATH = Path(__file__).resolve().parent / "prices.db"


def get_connection():
    return sqlite3.connect(DATABASE_PATH)


def setup_database():
    conn = get_connection()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            commodity TEXT NOT NULL,
            price REAL NOT NULL,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()

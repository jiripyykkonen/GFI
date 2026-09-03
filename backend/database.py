import os
import sqlite3
from pathlib import Path

try:
    import psycopg
except ImportError:
    psycopg = None

# Keep one database regardless of the folder from which Uvicorn is started.
DATABASE_PATH = Path(__file__).resolve().parent / "prices.db"
DATABASE_URL = os.getenv("DATABASE_URL")


class DatabaseConnection:
    """Use SQLite locally and PostgreSQL on Render through the same small API."""

    def __init__(self, connection, is_postgres):
        self.connection = connection
        self.is_postgres = is_postgres

    def execute(self, query, parameters=()):
        if self.is_postgres:
            query = query.replace("?", "%s")
        return self.connection.execute(query, parameters)

    def commit(self):
        self.connection.commit()

    def close(self):
        self.connection.close()


def get_connection():
    if DATABASE_URL:
        if psycopg is None:
            raise RuntimeError("PostgreSQL support is not installed. Run: pip install -r requirements.txt")
        return DatabaseConnection(psycopg.connect(DATABASE_URL), is_postgres=True)
    return DatabaseConnection(sqlite3.connect(DATABASE_PATH), is_postgres=False)


def setup_database():
    conn = get_connection()

    if conn.is_postgres:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS prices (
                id INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                commodity TEXT NOT NULL,
                price DOUBLE PRECISION NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
    else:
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


def has_prices():
    """Return whether the database already has imported observations."""
    conn = get_connection()
    try:
        return conn.execute("SELECT 1 FROM prices LIMIT 1").fetchone() is not None
    finally:
        conn.close()

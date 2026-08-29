from fastapi import FastAPI
import sqlite3
import requests
import os

from dotenv import load_dotenv
from fastapi.middleware.cors import CORSMiddleware
import threading
import time

load_dotenv()

ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")

app = FastAPI()


app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_connection():
    return sqlite3.connect("prices.db")


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


setup_database()


@app.get("/")
def home():
    return {
        "message": "Commodity Analytics API is running"
    }


@app.get("/api/status")
def status():
    return {
        "status": "ok"
    }


@app.post("/api/prices")
def add_price(commodity: str, price: float):
    conn = get_connection()

    conn.execute(
        "INSERT INTO prices (commodity, price) VALUES (?, ?)",
        (commodity, price)
    )

    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "commodity": commodity,
        "price": price
    }


@app.get("/api/prices")
def get_prices():
    conn = get_connection()

    cursor = conn.execute("""
        SELECT id, commodity, price, timestamp
        FROM prices
        ORDER BY timestamp DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    prices = []

    for row in rows:
        prices.append({
            "id": row[0],
            "commodity": row[1],
            "price": row[2],
            "timestamp": row[3]
        })

    return {
        "count": len(prices),
        "data": prices
    }
@app.get("/api/prices/gold")
def get_gold_prices():
    conn = get_connection()

    cursor = conn.execute("""
        SELECT id, commodity, price, timestamp
        FROM prices
        WHERE commodity = 'gold'
        ORDER BY timestamp ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    prices = []

    for row in rows:
        prices.append({
            "id": row[0],
            "commodity": row[1],
            "price": row[2],
            "timestamp": row[3]
        })

    return {
        "count": len(prices),
        "data": prices
    }
@app.get("/api/alpha/gold")
def get_gold():
    if not ALPHA_VANTAGE_API_KEY:
        return {
            "status": "error",
            "message": "ALPHA_VANTAGE_API_KEY puuttuu .env-tiedostosta"
        }

    url = "https://www.alphavantage.co/query"

    params = {
        "function": "GOLD_SILVER_SPOT",
        "symbol": "GOLD",
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()

    data = response.json()

    # Alpha Vantage palauttaa hinnan tekstinä
    price = float(data["price"])

    # Tallennetaan tietokantaan
    conn = get_connection()

    conn.execute(
        "INSERT INTO prices (commodity, price) VALUES (?, ?)",
        ("gold", price)
    )

    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "commodity": "gold",
        "price": price,
        "timestamp": data["timestamp"]
    }

def fetch_and_save_commodity(function, symbol, commodity_name):
    if not ALPHA_VANTAGE_API_KEY:
        print("ALPHA_VANTAGE_API_KEY puuttuu")
        return

    url = "https://www.alphavantage.co/query"

    params = {
        "function": function,
        "symbol": symbol,
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        if "price" not in data:
            print(f"{commodity_name}: Alpha Vantage ei palauttanut hintaa")
            print(data)
            return

        price = float(data["price"])

        conn = get_connection()

        conn.execute(
            """
            INSERT INTO prices (commodity, price)
            VALUES (?, ?)
            """,
            (commodity_name, price)
        )

        conn.commit()
        conn.close()

        print(
            f"{commodity_name.capitalize()} tallennettu: "
            f"${price:.2f}"
        )

    except Exception as e:
        print(
            f"{commodity_name} datan haku epäonnistui: {e}"
        )


def commodity_collector():
    while True:

        fetch_and_save_commodity(
            "GOLD_SILVER_SPOT",
            "GOLD",
            "gold"
        )

        time.sleep(60)


collector_thread = threading.Thread(
    target=commodity_collector,
    daemon=True
)

collector_thread.start()


@app.get("/api/alpha/oil")
def get_oil():

    if not ALPHA_VANTAGE_API_KEY:
        return {
            "status": "error",
            "message": "ALPHA_VANTAGE_API_KEY puuttuu"
        }

    url = "https://www.alphavantage.co/query"

    params = {
        "function": "WTI",
        "interval": "daily",
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    return response.json()
def fetch_and_save_oil():
    if not ALPHA_VANTAGE_API_KEY:
        print("ALPHA_VANTAGE_API_KEY puuttuu")
        return

    url = "https://www.alphavantage.co/query"

    params = {
        "function": "WTI",
        "interval": "daily",
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    try:
        response = requests.get(
            url,
            params=params,
            timeout=10
        )

        response.raise_for_status()

        data = response.json()

        if "data" not in data:
            print("Alpha Vantage ei palauttanut Oil-dataa")
            print(data)
            return

        conn = get_connection()

        for item in data["data"]:

            if item["value"] == ".":
                continue

            price = float(item["value"])
            date = item["date"]

            # Estetään saman päivän duplikaatit
            existing = conn.execute(
                """
                SELECT id
                FROM prices
                WHERE commodity = 'oil'
                AND DATE(timestamp) = ?
                """,
                (date,)
            ).fetchone()

            if existing:
                continue

            conn.execute(
                """
                INSERT INTO prices
                (commodity, price, timestamp)
                VALUES (?, ?, ?)
                """,
                ("oil", price, date)
            )

        conn.commit()
        conn.close()

        print("Oil-historia tallennettu SQLiteen")

    except Exception as e:
        print(f"Oil-datan haku epäonnistui: {e}")

@app.get("/api/prices/oil")
def get_oil_prices(days: int = 90):

    conn = get_connection()

    cursor = conn.execute("""
        SELECT id, commodity, price, timestamp
        FROM prices
        WHERE commodity = 'oil'
        AND timestamp >= date('now', ?)
        ORDER BY timestamp ASC
    """, (f"-{days} days",))

    rows = cursor.fetchall()
    conn.close()

    prices = []

    for row in rows:
        prices.append({
            "id": row[0],
            "commodity": row[1],
            "price": row[2],
            "timestamp": row[3]
        })

    return {
        "count": len(prices),
        "data": prices
    }
@app.get("/api/import/oil")
def import_oil():

    fetch_and_save_oil()

    return {
        "status": "ok",
        "message": "Oil data imported"
    }

@app.get("/api/alpha/copper")
def get_copper():

    if not ALPHA_VANTAGE_API_KEY:
        return {
            "status": "error",
            "message": "ALPHA_VANTAGE_API_KEY puuttuu"
        }

    url = "https://www.alphavantage.co/query"

    params = {
        "function": "COPPER",
        "interval": "monthly",
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    return response.json()

@app.post("/api/import/copper")
def import_copper():

    if not ALPHA_VANTAGE_API_KEY:
        return {
            "status": "error",
            "message": "ALPHA_VANTAGE_API_KEY puuttuu"
        }

    url = "https://www.alphavantage.co/query"

    params = {
        "function": "COPPER",
        "interval": "monthly",
        "apikey": ALPHA_VANTAGE_API_KEY
    }

    response = requests.get(
        url,
        params=params,
        timeout=10
    )

    response.raise_for_status()

    data = response.json()

    if "data" not in data:
        return {
            "status": "error",
            "message": "Copper-dataa ei löytynyt",
            "response": data
        }

    conn = get_connection()

    imported = 0

    for item in data["data"]:

        date = item["date"]
        value = item["value"]

        # Ohitetaan puuttuvat arvot
        if value == ".":
            continue

        price = float(value)

        # Estetään duplikaatit
        existing = conn.execute(
            """
            SELECT id
            FROM prices
            WHERE commodity = ?
            AND timestamp = ?
            """,
            ("copper", date)
        ).fetchone()

        if existing:
            continue

        conn.execute(
            """
            INSERT INTO prices
            (commodity, price, timestamp)
            VALUES (?, ?, ?)
            """,
            ("copper", price, date)
        )

        imported += 1

    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "commodity": "copper",
        "imported": imported
    }



@app.get("/api/prices/copper")
def get_copper_prices():

    conn = get_connection()

    cursor = conn.execute("""
        SELECT id, commodity, price, timestamp
        FROM prices
        WHERE commodity = 'copper'
        ORDER BY timestamp ASC
    """)

    rows = cursor.fetchall()
    conn.close()

    prices = []

    for row in rows:
        prices.append({
            "id": row[0],
            "commodity": row[1],
            "price": row[2],
            "timestamp": row[3]
        })

    return {
        "count": len(prices),
        "data": prices
    }
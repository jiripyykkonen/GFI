from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from database import get_connection, has_prices, setup_database
from services.commodities import (
    get_prices_for_commodity,
    save_spot_commodity,
    save_historical_commodity,
    save_oil_history,
    save_commodity_history,
    refresh_commodity_history,
    refresh_moex_if_market_open,
    save_moex_history,
)


scheduler = BackgroundScheduler()
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start scheduled commodity refreshes for the lifetime of this API process."""
    scheduler.add_job(
        refresh_commodity_history,
        trigger="cron",
        day_of_week="mon-fri",
        hour=20,
        minute=0,
        timezone="UTC",
        id="commodity-daily-refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.add_job(
        refresh_moex_if_market_open,
        trigger="interval",
        hours=1,
        id="moex-hourly-refresh",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    # A newly-created Render Postgres database is empty. Seed it once without
    # re-importing history on every subsequent restart.
    if not has_prices():
        scheduler.add_job(
            refresh_commodity_history,
            id="initial-commodity-import",
            replace_existing=True,
        )
    try:
        yield
    finally:
        scheduler.shutdown(wait=False)


app = FastAPI(lifespan=lifespan)


# --------------------------------------------------
# CORS
# --------------------------------------------------

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


# --------------------------------------------------
# DATABASE
# --------------------------------------------------

setup_database()


# --------------------------------------------------
# BASIC ENDPOINTS
# --------------------------------------------------

@app.get("/")
def home():
    """Serve the browser app from the same service as the API."""
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/api/status")
def status():
    return {
        "status": "ok"
    }


# --------------------------------------------------
# MANUAL PRICE INSERT
# --------------------------------------------------

@app.post("/api/prices")
def add_price(commodity: str, price: float):

    conn = get_connection()

    conn.execute(
        """
        INSERT INTO prices
        (commodity, price)
        VALUES (?, ?)
        """,
        (commodity, price)
    )

    conn.commit()
    conn.close()

    return {
        "status": "ok",
        "commodity": commodity,
        "price": price
    }


# --------------------------------------------------
# PRICE HISTORY
# --------------------------------------------------

@app.get("/api/prices/{commodity}")
def get_prices(commodity: str):

    return get_prices_for_commodity(commodity)


# --------------------------------------------------
# ALPHA VANTAGE - GOLD
# --------------------------------------------------

@app.get("/api/alpha/gold")
def get_gold():

    return save_spot_commodity(
        function="GOLD_SILVER_SPOT",
        symbol="GOLD",
        commodity_name="gold"
    )


# --------------------------------------------------
# ALPHA VANTAGE - OIL
# --------------------------------------------------

@app.get("/api/alpha/oil")
def get_oil():

    from api.alpha_vantage import get_alpha_vantage_data

    return get_alpha_vantage_data(
        function="WTI",
        interval="daily"
    )


# --------------------------------------------------
# ALPHA VANTAGE - COPPER
# --------------------------------------------------

@app.get("/api/alpha/copper")
def get_copper():

    from api.alpha_vantage import get_alpha_vantage_data

    return get_alpha_vantage_data(
        function="COPPER",
        interval="monthly"
    )


# --------------------------------------------------
# IMPORT OIL HISTORY
# --------------------------------------------------

@app.post("/api/import/oil")
def import_oil():

    return save_oil_history()


# --------------------------------------------------
# IMPORT GOLD HISTORY
# --------------------------------------------------

@app.post("/api/import/gold")
def import_gold():

    return save_commodity_history("gold")


# --------------------------------------------------
# IMPORT COPPER HISTORY
# --------------------------------------------------

@app.post("/api/import/copper")
def import_copper():

    return save_historical_commodity(
        function="COPPER",
        commodity_name="copper",
        interval="monthly"
    )


@app.post("/api/import/all")
def import_all_commodity_history():
    """Import gold, oil, and copper one at a time from Alpha Vantage."""
    return {
        commodity: save_commodity_history(commodity)
        for commodity in ("gold", "oil", "copper", "moex")
    }


@app.post("/api/import/moex")
def import_moex():
    return save_moex_history()


@app.get("/api/moex/quote")
def get_moex_quote():
    return refresh_moex_if_market_open()


@app.post("/api/refresh/hourly")
def run_hourly_refresh_now():
    """Run the same refresh action now, without waiting for the next hourly job."""
    return refresh_commodity_history()

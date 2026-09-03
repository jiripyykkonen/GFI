from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from api.alpha_vantage import get_alpha_vantage_data
from api.moex import get_imoex_daily_history, get_imoex_latest_value
from database import get_connection


COMMODITY_HISTORY_CONFIG = {
    # Alpha Vantage supports daily history for gold and WTI oil.
    "gold": {"function": "GOLD_SILVER_HISTORY", "symbol": "GOLD", "interval": "daily"},
    "oil": {"function": "WTI", "interval": "daily"},
    # Alpha Vantage's global copper feed only supports monthly, quarterly, or annual data.
    "copper": {"function": "COPPER", "interval": "monthly"},
}
HISTORY_FALLBACK_YEARS = (10, 5, 3)
MOEX_TIMEZONE = ZoneInfo("Europe/Moscow")


def save_spot_commodity(function, symbol, commodity_name):
    data = get_alpha_vantage_data(function=function, symbol=symbol)
    if "price" not in data:
        return {"status": "error", "message": "Alpha Vantage did not return a price.", "response": data}

    price = float(data["price"])
    conn = get_connection()
    try:
        conn.execute("INSERT INTO prices (commodity, price) VALUES (?, ?)", (commodity_name, price))
        conn.commit()
    finally:
        conn.close()
    return {"status": "ok", "commodity": commodity_name, "price": price, "timestamp": data.get("timestamp")}


def get_prices_for_commodity(commodity):
    conn = get_connection()
    try:
        rows = conn.execute(
            "SELECT id, commodity, price, timestamp FROM prices WHERE commodity = ? ORDER BY timestamp ASC",
            (commodity,),
        ).fetchall()
    finally:
        conn.close()
    keys = ("id", "commodity", "price", "timestamp")
    return {"count": len(rows), "data": [dict(zip(keys, row)) for row in rows]}


def _cutoff_for_years(years):
    today = date.today()
    try:
        return today.replace(year=today.year - years)
    except ValueError:  # February 29
        return today.replace(year=today.year - years, day=28)


def _valid_history_rows(data):
    rows = []
    for item in data.get("data", []):
        # Gold/Silver history uses ``price``; the other commodity feeds use ``value``.
        value = item.get("value", item.get("price"))
        if value in (None, "."):
            continue
        try:
            rows.append((date.fromisoformat(item["date"]), float(value)))
        except (KeyError, TypeError, ValueError):
            continue
    return sorted(rows)


def _choose_history_window(rows):
    """Prefer 10 years; use 5 or 3 only if that much data is unavailable."""
    earliest = rows[0][0]
    for years in HISTORY_FALLBACK_YEARS:
        cutoff = _cutoff_for_years(years)
        if earliest <= cutoff:
            return years, [(row_date, price) for row_date, price in rows if row_date >= cutoff]
    return None, []


def save_commodity_history(commodity_name):
    """Fetch available daily/monthly history, preferring 10 years then 5 or 3."""
    if commodity_name == "moex":
        return save_moex_history()

    config = COMMODITY_HISTORY_CONFIG.get(commodity_name)
    if config is None:
        raise ValueError(f"Unsupported commodity: {commodity_name}")

    rows = _valid_history_rows(get_alpha_vantage_data(**config))
    if not rows:
        return {"status": "error", "commodity": commodity_name, "message": "No usable commodity history was returned."}

    years_selected, selected_rows = _choose_history_window(rows)
    if years_selected is None:
        return {
            "status": "error", "commodity": commodity_name,
            "message": "Less than three years of usable history is available.",
            "available_from": rows[0][0].isoformat(),
        }

    conn = get_connection()
    try:
        imported = 0
        for row_date, price in selected_rows:
            timestamp = row_date.isoformat()
            exists = conn.execute(
                "SELECT 1 FROM prices WHERE commodity = ? AND timestamp = ?",
                (commodity_name, timestamp),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO prices (commodity, price, timestamp) VALUES (?, ?, ?)",
                    (commodity_name, price, timestamp),
                )
                imported += 1
        conn.commit()
    finally:
        conn.close()

    return {
        "status": "ok", "commodity": commodity_name, "years_selected": years_selected,
        "interval": config["interval"],
        "records_received": len(selected_rows), "imported": imported,
        "from_date": selected_rows[0][0].isoformat(), "to_date": selected_rows[-1][0].isoformat(),
    }


def save_historical_commodity(function, commodity_name, interval="monthly"):
    """Compatibility wrapper for the original copper import endpoint."""
    return save_commodity_history(commodity_name)


def save_oil_history():
    """Compatibility wrapper for the original oil import endpoint."""
    return save_commodity_history("oil")


def refresh_commodity_history():
    """Run one refresh pass; suitable for the hourly scheduler and manual use."""
    results = {}
    for commodity_name in COMMODITY_HISTORY_CONFIG:
        try:
            results[commodity_name] = save_commodity_history(commodity_name)
        except Exception as error:
            # One unavailable endpoint must not prevent the other commodities refreshing.
            results[commodity_name] = {"status": "error", "message": str(error)}
    return results


def _save_price_rows(commodity_name, rows):
    """Save date/price rows while leaving already-imported observations intact."""
    conn = get_connection()
    try:
        imported = 0
        for timestamp, price in rows:
            exists = conn.execute(
                "SELECT 1 FROM prices WHERE commodity = ? AND timestamp = ?",
                (commodity_name, timestamp),
            ).fetchone()
            if not exists:
                conn.execute(
                    "INSERT INTO prices (commodity, price, timestamp) VALUES (?, ?, ?)",
                    (commodity_name, price, timestamp),
                )
                imported += 1
        conn.commit()
        return imported
    finally:
        conn.close()


def save_moex_history():
    """Import IMOEX daily candles, preferring 10 years then 5 or 3."""
    today = date.today()
    rows = []
    years_selected = None

    for years in HISTORY_FALLBACK_YEARS:
        cutoff = _cutoff_for_years(years)
        candles = get_imoex_daily_history(cutoff - timedelta(days=14), today)
        rows = [
            (str(candle.get("BEGIN", candle.get("begin")))[:10], float(candle.get("CLOSE", candle.get("close"))))
            for candle in candles
            if candle.get("BEGIN", candle.get("begin"))
            and candle.get("CLOSE", candle.get("close")) is not None
        ]
        rows = [(timestamp, price) for timestamp, price in rows if timestamp >= cutoff.isoformat()]
        if rows and date.fromisoformat(rows[0][0]) <= cutoff + timedelta(days=14):
            years_selected = years
            break

    if years_selected is None:
        return {"status": "error", "commodity": "moex", "message": "Less than three years of IMOEX history is available."}

    imported = _save_price_rows("moex", rows)
    return {
        "status": "ok", "commodity": "moex", "symbol": "IMOEX", "interval": "daily",
        "years_selected": years_selected, "records_received": len(rows), "imported": imported,
        "from_date": rows[0][0], "to_date": rows[-1][0],
    }


def is_imoex_market_open(now=None):
    """IMOEX main-session window, Monday-Friday, in Moscow exchange time."""
    now = now or datetime.now(MOEX_TIMEZONE)
    if now.tzinfo is None:
        now = now.replace(tzinfo=MOEX_TIMEZONE)
    local_time = now.astimezone(MOEX_TIMEZONE)
    return local_time.weekday() < 5 and time(10, 0) <= local_time.time() < time(18, 50)


def refresh_moex_if_market_open():
    """Save one current IMOEX observation only while its main market is open."""
    if not is_imoex_market_open():
        return {"status": "skipped", "commodity": "moex", "message": "IMOEX main market is closed."}

    price = get_imoex_latest_value()
    timestamp = datetime.now(MOEX_TIMEZONE).isoformat(timespec="seconds")
    imported = _save_price_rows("moex", [(timestamp, price)])
    return {"status": "ok", "commodity": "moex", "price": price, "imported": imported, "timestamp": timestamp}

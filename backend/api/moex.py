"""Client for the public Moscow Exchange ISS API (no API key required)."""

from datetime import date

import requests


BASE_URL = "https://iss.moex.com/iss"
IMOEX_PATH = "/engines/stock/markets/index/securities/IMOEX"


def _request(path, params=None):
    response = requests.get(f"{BASE_URL}{path}.json", params=params, timeout=20)
    response.raise_for_status()
    return response.json()


def _rows(payload, block_name):
    """Convert ISS's columns/data table format to dictionaries."""
    block = payload.get(block_name, {})
    return [dict(zip(block.get("columns", []), row)) for row in block.get("data", [])]


def get_imoex_daily_history(from_date: date, to_date: date):
    """Return all available daily IMOEX candles between two calendar dates."""
    candles = []
    start = 0
    while True:
        payload = _request(
            f"{IMOEX_PATH}/candles",
            {
                "from": from_date.isoformat(),
                "till": to_date.isoformat(),
                "interval": 24,  # daily candles
                "start": start,
            },
        )
        page = _rows(payload, "candles")
        candles.extend(page)
        if len(page) < 500:
            break
        start += len(page)
    return candles


def get_imoex_latest_value():
    """Return the latest IMOEX index value published by ISS."""
    payload = _request(IMOEX_PATH)
    for row in _rows(payload, "marketdata"):
        for field in ("CURRENTVALUE", "LAST", "LASTTOPREVPRICE"):
            value = row.get(field)
            if value not in (None, ""):
                return float(value)
    raise RuntimeError("MOEX ISS did not return a current IMOEX value")

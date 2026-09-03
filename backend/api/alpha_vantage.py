"""Small client for Alpha Vantage commodity endpoints."""

import os

import requests
from dotenv import load_dotenv


load_dotenv()
ALPHA_VANTAGE_API_KEY = os.getenv("ALPHA_VANTAGE_API_KEY")
BASE_URL = "https://www.alphavantage.co/query"


def get_alpha_vantage_data(function, symbol=None, interval=None):
    """Return the decoded response from an Alpha Vantage request."""
    if not ALPHA_VANTAGE_API_KEY:
        raise RuntimeError("ALPHA_VANTAGE_API_KEY is missing from the .env file")

    params = {"function": function, "apikey": ALPHA_VANTAGE_API_KEY}
    if symbol:
        params["symbol"] = symbol
    if interval:
        params["interval"] = interval

    response = requests.get(BASE_URL, params=params, timeout=20)
    response.raise_for_status()
    data = response.json()
    error_message = data.get("Error Message") or data.get("Note") or data.get("Information")
    if error_message:
        raise RuntimeError(f"Alpha Vantage request failed: {error_message}")
    return data

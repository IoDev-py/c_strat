import hmac
import hashlib
import requests
import time

# Replace with your MEXC API Key and Secret
API_KEY = "mx0vglLaimWy9wDPUr"
SECRET_KEY = "273ca89504f6465cbbb3f1f2a0a0e934"
BASE_URL = "https://api.mexc.com"

def generate_signature(secret_key, params):
    """Generate HMAC SHA256 signature for MEXC API."""
    return hmac.new(secret_key.encode(), params.encode(), hashlib.sha256).hexdigest()

def market_order(symbol, side, quantity):
    """Place a market order on MEXC."""
    endpoint = "/api/v3/order"
    timestamp = int(time.time() * 1000)
    params = f"symbol={symbol}&side={side}&type=MARKET&quantity={quantity}&timestamp={timestamp}"
    signature = generate_signature(SECRET_KEY, params)
    full_params = f"{params}&signature={signature}"
    url = BASE_URL + endpoint + "?" + full_params
    headers = {
        'Content-Type': 'application/json',
        "X-MEXC-APIKEY": API_KEY
    }
    response = requests.post(url, headers=headers)
    return response.json()

def market_buy(symbol, quantity):
    """Execute a market buy order."""
    return market_order(symbol, "BUY", quantity)

def market_sell(symbol, quantity):
    """Execute a market sell order."""
    return market_order(symbol, "SELL", quantity)

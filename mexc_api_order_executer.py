import time
import hmac
import hashlib
import requests
from urllib.parse import urlencode

# MEXC API Base URL
BASE_URL = "https://api.mexc.com"

# Replace with your MEXC API credentials
API_KEY = "mx0vglLaimWy9wDPUr"
SECRET_KEY = "273ca89504f6465cbbb3f1f2a0a0e934"

def generate_signature(secret_key, params):
    """
    Generate HMAC SHA256 signature for MEXC API.
    
    :param secret_key: MEXC API Secret Key.
    :param params: The query string (without signature) to be signed.
    :return: HMAC SHA256 signature as a string.
    """
    return hmac.new(secret_key.encode(), params.encode(), hashlib.sha256).hexdigest()

def market_order(symbol, side, quantity):
    """
    Place a market order on MEXC.

    :param symbol: Trading pair (e.g., "ETHUSDT").
    :param side: "BUY" or "SELL".
    :param quantity: Amount of the base asset to trade.
    :return: API response as JSON.
    """
    endpoint = "/api/v3/order"

    timestamp = int(time.time() * 1000)

    # Construct query string
    params = f"symbol={symbol}&side={side}&type=MARKET&quantity={quantity}&timestamp={timestamp}"

    # Generate signature for the query string
    signature = generate_signature(SECRET_KEY, params)

    # Append signature to the query string
    full_params = f"{params}&signature={signature}"
    url = BASE_URL + endpoint + "?" + full_params

    headers = {
        'Content-Type': 'application/json',
        "X-MEXC-APIKEY": API_KEY
    }

    # Make the POST request
    response = requests.post(url, headers=headers)
    return response.json()

def market_buy(symbol, quantity):
    """Execute a market buy order."""
    return market_order(symbol, "BUY", quantity)

def market_sell(symbol, quantity):
    """Execute a market sell order."""
    return market_order(symbol, "SELL", quantity)

# Example usage
if __name__ == "__main__":
    # Replace with your trading pair and quantity
    trading_pair = "ETHUSDC"
    quantity = 0.01  # Amount of ETH to buy/sell

    # Market Buy
    print("Executing Market Buy...")
    buy_response = market_buy(trading_pair, quantity)
    print("Buy Response:", buy_response)

    # Market Sell
    print("Executing Market Sell...")
    sell_response = market_sell(trading_pair, quantity)
    print("Sell Response:", sell_response)
import websocket
from websocket import WebSocketApp
import json
from datetime import datetime


# Callback function for incoming WebSocket messages
def on_message(ws, message):
    data = json.loads(message)

    print(data)
    
    # Check if the data contains kline information
    if 'k' in data and 'c' in data['k']:  # 'k' for kline data and 'c' for close price
        close_price = float(data['k']['c'])
        symbol = data['s']
        timestamp = datetime.now()

        # Implement your pattern detection logic here
        # Example: simple check for logging a buy opportunity


# Function to start the WebSocket
def start_websocket(symbol='ETHUSDT', interval='Min1'):
    url = f"wss://wbs.mexc.com/ws"

    def on_open(ws):
        # Send the subscription message when the WebSocket opens
        subscribe_message = {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.kline.v3.api@{symbol}@{interval}"],
            "id": 1
        }
        ws.send(json.dumps(subscribe_message))
        print(f"Subscribed to {symbol} kline data with interval {interval}")

    # Create WebSocketApp
    ws = websocket.WebSocketApp(url, on_message=on_message, on_open=on_open)
    ws.run_forever()

# Start the WebSocket with the given symbol and interval
if __name__ == "__main__":
    start_websocket(symbol='ETHUSDT', interval='Min1')
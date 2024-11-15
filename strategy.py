import websocket
import json
import pandas as pd
from collections import deque

# Parameters
LOOKBACK_PERIOD = 10  # Number of candles to look back for volume average
TREND_CONFIRMATION_PERIOD = 3  # Number of candles for trend confirmation
GAIN_TARGET_PERCENT = 0.0001  # 0.01% gain

# Global variables for tracking real-time data
candle_data = deque(maxlen=LOOKBACK_PERIOD + TREND_CONFIRMATION_PERIOD)
current_price = None
entry_price = None
position_open = False

# Function to check if the pattern is met
def check_pattern():
    if len(candle_data) < LOOKBACK_PERIOD + TREND_CONFIRMATION_PERIOD:
        return False

    current_candle = candle_data[-1]
    close = current_candle['Close']
    high = current_candle['High']
    low = current_candle['Low']
    volume = current_candle['Volume']

    # Condition 1: Close in the top 30% of the range
    close_position = (close - low) / (high - low)
    if close_position <= 0.7:
        return False

    # Condition 2: Volume greater than the average of the last LOOKBACK_PERIOD candles
    volume_avg = pd.DataFrame(candle_data)[-LOOKBACK_PERIOD:]['Volume'].mean()
    if volume <= volume_avg:
        return False

    # Trend confirmation: check if the last TREND_CONFIRMATION_PERIOD candles have upward or stable closes
    for i in range(-TREND_CONFIRMATION_PERIOD, -1):
        if candle_data[i]['Close'] < candle_data[i - 1]['Close']:
            return False

    return True

# WebSocket message handler
def on_message(ws, message):
    global current_price, entry_price, position_open

    # Parse the incoming data (assuming JSON with price information)
    data = json.loads(message)
    candle = {
        'Close': float(data['close']),
        'High': float(data['high']),
        'Low': float(data['low']),
        'Volume': float(data['volume'])
    }
    current_price = candle['Close']
    candle_data.append(candle)

    # Check for the pattern
    if not position_open and check_pattern():
        entry_price = current_price
        position_open = True
        print(f"Pattern detected. Bought at {entry_price}")

    # Check for exit condition if position is open
    if position_open:
        target_price = entry_price * (1 + GAIN_TARGET_PERCENT)
        if current_price >= target_price:
            print(f"Sold at {current_price} for a 0.01% gain")
            position_open = False  # Close the position
            entry_price = None  # Reset entry price
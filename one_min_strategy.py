import psycopg2
import pandas as pd
import logging
from datetime import datetime
from decimal import Decimal
import traceback


# Configure logging
logging.basicConfig(filename='strategy_mexc_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')

# Parameters for the strategy
LOOKBACK_PERIOD = 10  # Number of candles to look back for volume average
TREND_CONFIRMATION_PERIOD = 3  # Number of candles for trend confirmation
GAIN_TARGET_PERCENT = Decimal('0.0005')  # 0.05% gain
MAX_SIMULTANEOUS_TRADES = 4  # Maximum number of open trades at the same time

# Database connection function
def create_db_connection():
    try:
        conn = psycopg2.connect(
            database="spot_strategy",
            user="ioantautean",
            password="",
            host="127.0.0.1",
            port="5432"
        )
        cursor = conn.cursor()
        return conn, cursor
    except psycopg2.Error as db_err:
        logging.error("Failed to connect to the database")
        logging.error(db_err)
        raise  # Stop execution if DB connection fails

# Function to get and form all available 1-minute candles from stored data
def get_all_candles():
    conn, cursor = create_db_connection()
    query = """
        SELECT timestamp, open_price, high_price, low_price, close_price, volume
        FROM price_data_v12
        ORDER BY timestamp;
    """
    cursor.execute(query)
    data = cursor.fetchall()
    conn.close()
    
    # Convert the data to a DataFrame
    df = pd.DataFrame(data, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
    df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')  # Ensure timestamp is in seconds
    df.set_index('datetime', inplace=True)

    # Check if there is enough data
    if df.empty:
        logging.info("No data available to form 1-minute candles.")
        return pd.DataFrame()

    # Resample data to form 1-minute OHLCV candles
    ohlcv = df.resample('1min').agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'  # Sum the volume for the period
    })

    # Drop any rows with NaN values (incomplete intervals)
    ohlcv.dropna(inplace=True)

    # Convert the resampled data to a list of dictionary objects
    candles = []
    for index, row in ohlcv.iterrows():
        candle = {
            'timestamp': index,       # End time of the 1-minute period
            'open': Decimal(row['open']),
            'close': Decimal(row['close']),
            'high': Decimal(row['high']),
            'low': Decimal(row['low']),
            'volume': Decimal(row['volume'])   # Total volume for the 1-minute period
        }
        candles.append(candle)

    return pd.DataFrame(candles)

# Function to check if the pattern is met
def check_pattern(candle_data):
    if len(candle_data) < LOOKBACK_PERIOD + TREND_CONFIRMATION_PERIOD:
        logging.info(f"Insufficient data: {len(candle_data)} candles available, but {LOOKBACK_PERIOD + TREND_CONFIRMATION_PERIOD} required.")
        return False, None

    current_candle = candle_data.iloc[-1]
    close = current_candle['close']
    high = current_candle['high']
    low = current_candle['low']
    volume = current_candle['volume']

    # Log the current candle's data
    logging.info(
        f"Evaluating Candle - Timestamp: {current_candle.name}, Open: {current_candle['open']}, High: {high}, "
        f"Low: {low}, Close: {close}, Volume: {volume}"
    )

    # Condition 1: Close in the top 30% of the range
    close_position = (close - low) / (high - low) if (high - low) > 0 else Decimal('0')
    if close_position <= Decimal('0.7'):
        logging.info(
            f"Condition 1 failed: Close position {close_position:.4f} not in the top 30% of the range."
        )
        return False, None
    logging.info("Condition 1 passed: Close in the top 30% of the range.")

    # Condition 2: Volume greater than the average of the last LOOKBACK_PERIOD candles
    volume_avg = Decimal(candle_data['volume'][-LOOKBACK_PERIOD:].mean())
    if volume <= volume_avg:
        logging.info(
            f"Condition 2 failed: Volume {volume} not greater than average volume {volume_avg} of the last {LOOKBACK_PERIOD} candles."
        )
        return False, None
    logging.info("Condition 2 passed: Volume greater than average.")

    # Trend confirmation: check if the last TREND_CONFIRMATION_PERIOD candles have upward or stable closes
    for i in range(1, TREND_CONFIRMATION_PERIOD):
        if candle_data['close'].iloc[-i] < candle_data['close'].iloc[-(i + 1)]:
            logging.info(
                f"Condition 3 failed: Candle {i} close {candle_data['close'].iloc[-i]} "
                f"is less than candle {i+1} close {candle_data['close'].iloc[-(i + 1)]}."
            )
            return False, None
    logging.info("Condition 3 passed: Trend confirmed with upward or stable closes.")

    logging.info("All conditions met for entry.")
    return True, close


# Function to log a trade entry (returns a trade_id)
def log_trade_entry(entry_time, entry_price):
    try:
        conn, cursor = create_db_connection()
        insert_query = """
            INSERT INTO trade_log_v12 (entry_time, entry_price)
            VALUES (%s, %s)
            RETURNING id;
        """
        cursor.execute(insert_query, (entry_time, entry_price))
        conn.commit()
        trade_id = cursor.fetchone()[0]
        conn.close()        

        logging.info(f"Trade {trade_id} opened at {entry_time} with entry price {entry_price}")
        
        return trade_id
    except Exception as e:
        logging.error("Error logging trade entry")
        logging.error(traceback.format_exc())
        raise
    

def run_strategy(trade_manager):
    # Get the 1-minute candles
    all_candles = get_all_candles()

    if all_candles.empty:
        return

    # Analyze only the latest candle (current live candle)
    current_candle = all_candles.iloc[-1]  # Get the most recent candle
    pattern_data = all_candles.iloc[-(LOOKBACK_PERIOD + TREND_CONFIRMATION_PERIOD):]  # Only the required lookback period

    # Log current candle details
    logging.info(
        f"Current Candle - Timestamp: {current_candle['timestamp']}, Open: {current_candle['open']}, "
        f"High: {current_candle['high']}, Low: {current_candle['low']}, Close: {current_candle['close']}, Volume: {current_candle['volume']}"
    )

    # Check if the pattern is detected for the current candle
    pattern_detected, entry_price = check_pattern(pattern_data)

    # Entry Logic
    if pattern_detected and len(trade_manager.active_trades) < MAX_SIMULTANEOUS_TRADES:
        entry_time = current_candle['timestamp']
        target_price = entry_price * (1 + GAIN_TARGET_PERCENT)

        # Use TradeManager to check for duplicates
        if trade_manager.is_duplicate_trade(entry_time, entry_price):
            return  # Skip duplicate entries

        # Log a new trade entry
        trade_id = log_trade_entry(entry_time, entry_price)
        trade_manager.add_trade(trade_id, entry_time, entry_price, target_price)
        logging.info(f"Trade {trade_id} added to TradeManager.")
        logging.info(f"Trade {trade_id} opened at {entry_time} with entry price {entry_price}")
        print(f"Trade {trade_id} opened at {entry_time} with entry price {entry_price}")
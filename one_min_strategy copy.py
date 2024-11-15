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
GAIN_TARGET_PERCENT = Decimal('0.0001')  # 0.01% gain
MAX_SIMULTANEOUS_TRADES = 4  # Maximum number of open trades at the same time

# Global variables for tracking trades
active_trades = []
completed_trades = []  # List to store completed trades with entry time and entry price  # List to store active trades with trade_id, entry price, and target price

# Database connection function
def db_connect():
    try:
        conn = psycopg2.connect(
            database="spot_strategy",
            user="ioantautean",
            password="",
            host="127.0.0.1",
            port="5432"
        )
        return conn
    except psycopg2.Error as db_err:
        logging.error("Failed to connect to the database")
        logging.error(db_err)
        raise  # Stop execution if DB connection fails

# Function to get and form all available 1-minute candles from stored data
def get_all_candles():
    conn = db_connect()
    cursor = conn.cursor()
    query = """
        SELECT timestamp, open_price, high_price, low_price, close_price, volume
        FROM price_data
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
        return False, None

    current_candle = candle_data.iloc[-1]
    close = current_candle['close']
    high = current_candle['high']
    low = current_candle['low']
    volume = current_candle['volume']

    # Condition 1: Close in the top 30% of the range
    close_position = (close - low) / (high - low)
    if close_position <= Decimal('0.7'):
        return False, None

    # Condition 2: Volume greater than the average of the last LOOKBACK_PERIOD candles
    volume_avg = Decimal(candle_data['volume'][-LOOKBACK_PERIOD:].mean())
    if volume <= volume_avg:
        return False, None

    # Trend confirmation: check if the last TREND_CONFIRMATION_PERIOD candles have upward or stable closes
    for i in range(1, TREND_CONFIRMATION_PERIOD):
        if candle_data['close'].iloc[-i] < candle_data['close'].iloc[-(i + 1)]:
            return False, None

    return True, close

# Function to log a trade entry (returns a trade_id)
def log_trade_entry(entry_time, entry_price):
    try:
        conn = db_connect()
        cursor = conn.cursor()
        insert_query = """
            INSERT INTO trade_log (entry_time, entry_price)
            VALUES (%s, %s)
            RETURNING id;
        """
        cursor.execute(insert_query, (entry_time, entry_price))
        conn.commit()
        trade_id = cursor.fetchone()[0]
        conn.close()

        target_price = entry_price * (1 + GAIN_TARGET_PERCENT)
        active_trades.append({'trade_id': trade_id, 'entry_time': entry_time, 'entry_price': entry_price, 'target_price': target_price})
        logging.info(f"Trade {trade_id} opened at {entry_time} with entry price {entry_price}")
        logging.info(f"Active trades count: {len(active_trades)}")
        logging.info(f"Active trades: {active_trades}")
        return trade_id
    except Exception as e:
        logging.error("Error logging trade entry")
        logging.error(traceback.format_exc())
        raise

# Function to log a trade exit into the database
def log_trade_exit(trade_id, exit_time, exit_price):
    try:
        # Find and remove the trade from active_trades
        trade = next((t for t in active_trades if t['trade_id'] == trade_id), None)
        if trade:
            profit = exit_price - trade['entry_price']
            conn = db_connect()
            cursor = conn.cursor()
            update_query = """
                UPDATE trade_log
                SET exit_time = %s, exit_price = %s, profit = %s
                WHERE id = %s;
            """
            cursor.execute(update_query, (exit_time, exit_price, profit, trade_id))
            conn.commit()
            conn.close()

            # Append to completed_trades
            completed_trades.append({'entry_time': trade['entry_time'], 'entry_price': trade['entry_price']})
            # Remove the trade from active_trades
            active_trades.remove(trade)
            
            logging.info(f"Trade ID {trade_id} closed at {exit_price} on {exit_time}, profit: {profit}")
        else:
            logging.warning(f"Trade ID {trade_id} not found in active_trades.")
    except Exception as e:
        logging.error("Error logging trade exit")
        logging.error(traceback.format_exc())
        raise


# Strategy function
def run_strategy():
    # Get the 1-minute candles
    all_candles = get_all_candles()
    
    if all_candles.empty:
        return

    # Check each candle for the pattern
    for i in range(LOOKBACK_PERIOD + TREND_CONFIRMATION_PERIOD, len(all_candles)):
        pattern_data = all_candles.iloc[:i + 1]
        pattern_detected, entry_price = check_pattern(pattern_data)

        # Check if we can open a new trade
        if pattern_detected and len(active_trades) < MAX_SIMULTANEOUS_TRADES:
            # Ensure there is no existing or completed trade with the same entry time and entry price
            existing_or_completed_trade = any(
                (trade['entry_time'] == pattern_data.iloc[-1]['timestamp'] and trade['entry_price'] == entry_price)
                for trade in active_trades + completed_trades
            )
            if existing_or_completed_trade:
                logging.info(f"Duplicate or completed trade detected at {pattern_data.iloc[-1]['timestamp']} with entry price {entry_price}. Skipping entry.")
                continue
            entry_time = pattern_data.iloc[-1]['timestamp']
            trade_id = log_trade_entry(entry_time, entry_price)
            print(f"Trade {trade_id} opened at {entry_time} with entry price {entry_price}")

        # Check if any active trades meet the exit condition
        for trade in active_trades.copy():
            if all_candles['high'].iloc[i] >= trade['target_price']:
                log_trade_exit(trade['trade_id'], all_candles.iloc[i]['timestamp'], trade['target_price'])
                print(f"Trade {trade['trade_id']} exited at {all_candles.iloc[i]['timestamp']} with price {trade['target_price']}")

if __name__ == "__main__":
    run_strategy()

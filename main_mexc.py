import websocket
from websocket import WebSocketApp
import json
from datetime import datetime, timedelta
import logging
import traceback
import psycopg2
from psycopg2 import sql
import threading
import time
from one_min_strategy import run_strategy


# Configure logging
logging.basicConfig(filename='main_mexc_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')


# Database connection setup
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


# Create initial connection
conn, cursor = create_db_connection()


# Callback function for incoming WebSocket messages
def on_message(ws, message):
    try:
        data = json.loads(message)

        if 'd' in data and 'k' in data['d']:
            kline = data['d']['k']
            symbol = data['s']
            interval = kline['i']
            open_price = float(kline['o'])
            close_price = float(kline['c'])
            high_price = float(kline['h'])
            low_price = float(kline['l'])
            volume = float(kline['v'])
            number_of_trades = kline.get('n', 0)  # Ensure it defaults to 0 if missing

            # Insert the data into PostgreSQL
            insert_query = sql.SQL("""
                INSERT INTO price_data_v2 (symbol, interval, open_price, close_price, high_price, low_price, volume, number_of_trades, timestamp)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW());
            """)
            cursor.execute(insert_query, (symbol, interval, open_price, close_price, high_price, low_price, volume, number_of_trades))
            conn.commit()  # Commit the transaction

    except Exception as e:
        logging.error("Error processing WebSocket message")
        logging.error(traceback.format_exc())
        close_db_connection()


# Function to close DB connection
def close_db_connection():
    try:
        if cursor:
            cursor.close()
        if conn:
            conn.close()
        logging.info("Database connection closed")
    except Exception as close_err:
        logging.error("Error closing the database connection")
        logging.error(close_err)


# Other WebSocket callbacks
def on_error(ws, error):
    logging.error(f"WebSocket error: {error}")
    close_db_connection()


def on_close(ws, close_status_code, close_msg):
    logging.info(f"WebSocket closed with status: {close_status_code}, message: {close_msg}")
    close_db_connection()


def on_open(ws):
    logging.info("WebSocket connected")
    subscribe_message = {
        "method": "SUBSCRIPTION",
        "params": [f"spot@public.kline.v3.api@ETHUSDT@Min1"], # symbol='ETHUSDT', interval='Min1'
        "id": 1
    }
    ws.send(json.dumps(subscribe_message))
    logging.info("Subscribed to ETHUSDT kline data with interval Min1")


# Start the WebSocket
def start_websocket():
    url = "wss://wbs.mexc.com/ws"
    ws = websocket.WebSocketApp(
        url,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close,
        on_open=on_open
    )
    while True:
        try:
            ws.run_forever()
        except Exception as e:
            logging.error("WebSocket connection terminated unexpectedly")
            logging.error(traceback.format_exc())
            time.sleep(5)  # Wait before reconnecting
            conn, cursor = create_db_connection()  # Re-establish DB connection


# Function to wait until the next 1-minute interval and run the strategy
def run_strategy_every_min():
    while True:
        now = datetime.now()
        next_interval = (now + timedelta(minutes=1 - (now.minute % 1))).replace(second=0, microsecond=0)
        time_to_wait = (next_interval - now).total_seconds()

        # Wait until the next 1-minute interval
        print(f"Waiting for synchronization. Next analysis at: {next_interval}")
        time.sleep(time_to_wait)

        # Run the strategy once the interval is reached
        run_strategy()


# Start the WebSocket with the given symbol and interval
if __name__ == "__main__":
    # Start the WebSocket in a separate thread
    websocket_thread = threading.Thread(target=start_websocket, daemon=True)
    websocket_thread.start()

    run_strategy_every_min()
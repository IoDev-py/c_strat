import logging
import traceback
import psycopg2


# Configure logging
logging.basicConfig(filename='trade_manager_log.txt', level=logging.INFO, format='%(asctime)s - %(message)s')

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


class TradeManager:
    def __init__(self):
        self.active_trades = []
        self.completed_trades = []
        self.logged_duplicates = set()  # Track logged duplicates to avoid repeated logging
    

    def add_trade(self, trade_id, entry_time, entry_price, target_price):
        trade = {
            "trade_id": trade_id,
            "entry_time": entry_time,
            "entry_price": entry_price,
            "target_price": target_price,
        }
        self.active_trades.append(trade)
        logging.info(f"Active trades count: {len(self.active_trades)}")
        logging.info(f"Active trades: {self.active_trades}")


    def remove_trade(self, trade_id):
        for trade in self.active_trades:
            if trade["trade_id"] == trade_id:
                self.completed_trades.append(trade)
                self.active_trades.remove(trade)
                return trade
        return None


    # Function to log a trade exit into the database
    def log_trade_exit(self, trade_id, exit_time, exit_price):
        try:
            # Find and remove the trade from active_trades
            conn, cursor = create_db_connection()  # Create a new connection for each operation
            update_query = """
                UPDATE trade_log_v12
                SET exit_time = %s, exit_price = %s
                WHERE id = %s;
            """
            cursor.execute(update_query, (exit_time, exit_price, trade_id))
            conn.commit()
            conn.close()
            print(f"Trade ID {trade_id} closed at {exit_price} on {exit_time}")
            logging.info(f"Trade ID {trade_id} closed at {exit_price} on {exit_time}")

        except Exception as e:
            logging.error("Error logging trade exit")
            logging.error(traceback.format_exc())
            raise
    

    def check_exit_conditions(self, current_price):
        exited_trades = []
        for trade in self.active_trades[:]:
            if current_price >= trade["target_price"]:
                self.remove_trade(trade["trade_id"])
                exited_trades.append(trade)
        return exited_trades

    def is_duplicate_trade(self, entry_time, entry_price):
        # Check active and completed trades for a match
        existing_or_completed_trade = any(
            (trade["entry_time"] == entry_time and trade["entry_price"] == entry_price)
            for trade in self.active_trades + self.completed_trades
        )

        if existing_or_completed_trade:
            # Log duplicate trades only once
            if (entry_time, entry_price) not in self.logged_duplicates:
                logging.info(
                    f"Duplicate or completed trade detected at {entry_time} with entry price {entry_price}. Skipping entry."
                )
                self.logged_duplicates.add((entry_time, entry_price))
            return True
        return False


    # New method to check if there are any active trades
    def has_active_trades(self):
        return len(self.active_trades) > 0
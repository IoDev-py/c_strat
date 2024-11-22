import logging
import traceback
import psycopg2
import time
import hmac
import hashlib
import requests
import mexc_api_spot_order


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
        self.first_buy_quantity = None  # Track the first buy quantity
        self.api_key = "mx0vglLaimWy9wDPUr"
        self.secret_key = "273ca89504f6465cbbb3f1f2a0a0e934"
        self.base_url = "https://api.mexc.com"
        

    def generate_signature(self, params):
        """Generate HMAC SHA256 signature for MEXC API."""
        return hmac.new(self.secret_key.encode(), params.encode(), hashlib.sha256).hexdigest()


    def get_account_info(self):
        """Fetch account information from MEXC."""
        endpoint = "/api/v3/account"
        timestamp = int(time.time() * 1000)

        # Construct query string
        params = f"timestamp={timestamp}"
        signature = self.generate_signature(params)
        full_params = f"{params}&signature={signature}"
        url = self.base_url + endpoint + "?" + full_params

        headers = {
            'Content-Type': 'application/json',
            "X-MEXC-APIKEY": self.api_key
        }

        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logging.error("Error fetching account info")
            logging.error(e)
            return None

    def calculate_quantity(self, trading_pair):
        """
        Calculate the trading quantity based on 25% of the account balance for the given trading pair.

        :param trading_pair: The trading pair (e.g., "ETHUSDT").
        :return: Calculated quantity or None if the balance cannot be fetched.
        """
        account_info = self.get_account_info()
        if not account_info or "balances" not in account_info:
            logging.error("Failed to fetch account balance.")
            return None

        base_asset = trading_pair[:-4]  # Extract the base asset (e.g., "ETH" from "ETHUSDT")
        for balance in account_info["balances"]:
            if balance["asset"] == base_asset:
                available_balance = float(balance["free"])
                quantity = available_balance * 0.25  # Use 25% of the available balance
                logging.info(f"Calculated quantity for {base_asset}: {quantity}")
                return quantity

        logging.error(f"Balance for {base_asset} not found in account info.")
        return None


    def add_trade(self, trade_id, entry_time, entry_price, target_price):
        """Add a new trade and execute a market buy order."""
        if not self.first_buy_quantity:
            self.first_buy_quantity = self.calculate_quantity("ETHUSDC")
        quantity = self.first_buy_quantity or 0
        trade = {
            "trade_id": trade_id,
            "entry_time": entry_time,
            "entry_price": entry_price,
            "target_price": target_price,
            "quantity": quantity,
        }
        self.active_trades.append(trade)
        logging.info(f"Trade added: {trade}")

        # Execute market buy order
        response = mexc_api_spot_order.market_buy("ETHUSDC", quantity)
        logging.info(f"Market Buy Executed: {response}")


    def remove_trade(self, trade_id):
        """Remove a trade and execute a market sell order."""
        trade = next((t for t in self.active_trades if t["trade_id"] == trade_id), None)
        if trade:
            self.active_trades.remove(trade)
            self.completed_trades.append(trade)

            # Execute market sell order
            response = mexc_api_spot_order.market_sell("ETHUSDC", trade["quantity"])
            logging.info(f"Market Sell Executed: {response}")

            # Reset the first buy quantity only if no other active trades remain
            if not self.active_trades:  # Check if active trades list is empty
                if trade["quantity"] == self.first_buy_quantity:
                    self.first_buy_quantity = None
                    logging.info("First buy quantity reset as there are no active trades.")
            else:
                logging.info("First buy quantity retained as other active trades exist.")
            return trade
        return None


    # Function to log a trade exit into the database
    def log_trade_exit(self, trade_id, exit_time, exit_price):
        try:
            # Find and remove the trade from active_trades
            conn, cursor = create_db_connection()  # Create a new connection for each operation
            update_query = """
                UPDATE trade_log_v13
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
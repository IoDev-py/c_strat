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

def get_account_info():
    """
    Get account information.

    :param timestamp
    :return: API response as JSON.
    """
    endpoint = "/api/v3/account"

    timestamp = int(time.time() * 1000)

    # Construct query string
    params = f"timestamp={timestamp}"
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
    response = requests.get(url, headers=headers)
    return response.json()


# Example usage
if __name__ == "__main__":
    account_info_response = get_account_info()
    print("Account info:", account_info_response)
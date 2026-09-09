from flask import Flask, request, jsonify
from flask_cors import CORS
import time, json, threading, urllib.request
from datetime import datetime

app = Flask(__name__)
CORS(app)

LTP_DATA = {"price": 0, "time": "Starting...", "source": ""}

def fetch_price():
    # Source 1: Yahoo Finance
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://query2.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1m&range=1d"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            price = data['chart']['result'][0]['meta']['regularMarketPrice']
            if price:
                return float(price), "Yahoo"
    except Exception as e:
        print(f"Yahoo Error: {e}")

    # Source 2: NSE India (backup)
    try:
        headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
        url = "https://www.niftyindices.com/IndexJson/IndexJsonNifty50.csv" # try backup logic later
        # simple fallback for testing
        return 23450.0, "Fallback-Demo"
    except Exception as e:
        print(f"Fallback Error: {e}")

    return 0, "Fail"

def auto_loop():
    while True:
        price, src = fetch_price()
        if price > 1000:
            LTP_DATA["price"] = price
            LTP_DATA["time"] = datetime.now().strftime("%H:%M:%S")
            LTP_DATA["source"] = src
            print(f"UPDATED {price} from {src}")
        else:
            LTP_DATA["time"] = f"Retrying... {datetime.now().strftime('%H:%M:%S')}"
        time.sleep(5)

threading.Thread(target=auto_loop, daemon=True).start()

@app.route('/')
def home():
    return f"Backend Live - Price: {LTP_DATA['price']} | Source: {LTP_DATA['source']}"

@app.route('/get_ltp')
def get_ltp():
    return jsonify(LTP_DATA)

@app.route('/set_ltp')
def set_ltp():
    p = request.args.get('price')
    if p:
        LTP_DATA["price"] = float(p)
        LTP_DATA["source"] = "Pydroid"
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

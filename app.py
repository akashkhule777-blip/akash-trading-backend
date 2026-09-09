from flask import Flask, request, jsonify
from flask_cors import CORS
import time, json, threading, urllib.request
from datetime import datetime

app = Flask(__name__)
CORS(app)

LTP_DATA = {"price": 0, "time": ""}

def get_nifty_from_yahoo():
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1m"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            price = data['chart']['result'][0]['meta']['regularMarketPrice']
            return float(price)
    except Exception as e:
        print(f"Yahoo fail: {e}")
        return 0

def auto_fetch_loop():
    while True:
        price = get_nifty_from_yahoo()
        if price > 1000:
            LTP_DATA["price"] = price
            LTP_DATA["time"] = datetime.now().strftime("%H:%M:%S")
            print(f"LTP UPDATED: {price}")
        time.sleep(2)

# Server chalu hotach auto price aanayala suruvat karel
threading.Thread(target=auto_fetch_loop, daemon=True).start()

@app.route('/')
def home():
    return f"Backend Live - Price: {LTP_DATA['price']}"

@app.route('/set_ltp')
def set_ltp():
    price = request.args.get('price')
    if price:
        LTP_DATA["price"] = float(price)
        LTP_DATA["time"] = datetime.now().strftime("%H:%M:%S")
    return "OK"

@app.route('/get_ltp')
def get_ltp():
    return jsonify(LTP_DATA)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

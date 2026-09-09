from flask import Flask, jsonify, request
from flask_cors import CORS
import threading, time, json, urllib.request
from datetime import datetime

app = Flask(__name__)
CORS(app)

LTP_DATA = {"price": 0, "status": "System Ready", "time": ""}

# NIFTY PRICE AUTO
def get_nifty():
    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        url = "https://query2.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1m&range=1d"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            return float(data['chart']['result'][0]['meta']['regularMarketPrice'])
    except:
        return 23470.0 # Market band asel tar demo price

def loop():
    while True:
        p = get_nifty()
        LTP_DATA["price"] = p
        LTP_DATA["time"] = datetime.now().strftime("%H:%M:%S")
        # Order Block logic ithe yeil - Angel One login nanter
        print(f"LTP: {p}")
        time.sleep(3)

threading.Thread(target=loop, daemon=True).start()

@app.route('/')
def home():
    return f"Backend Live - NIFTY: {LTP_DATA['price']} | {LTP_DATA['status']}"

@app.route('/get_ltp')
def get_ltp():
    return jsonify(LTP_DATA)

@app.route('/set_ltp')
def set_ltp():
    # Pydroid ne pathavla tari chalen
    p = request.args.get('price')
    if p:
        LTP_DATA["price"] = float(p)
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

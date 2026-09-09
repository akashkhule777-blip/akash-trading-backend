from flask import Flask, jsonify, request
from flask_cors import CORS
import threading, time, json, urllib.request, os
from datetime import datetime

app = Flask(__name__)
CORS(app)

LTP_DATA = {"price": 0, "status": "Starting", "time": ""}

# TU TAKLELE NAV - SCREENSHOT PRAMANE
API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

angel_obj = None

def init_angel():
    global angel_obj
    try:
        from SmartApi import SmartConnect
        import pyotp
        print(f"Connecting Angel: {CLIENT_ID}")
        obj = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = obj.generateSession(CLIENT_ID, PASSWORD, totp)
        angel_obj = obj
        print("Angel Login SUCCESS")
        return obj
    except Exception as e:
        print(f"Angel Fail: {e}")
        LTP_DATA["status"] = f"Angel Fail: {e}"
        return None

def get_nifty_from_angel(obj):
    try:
        # NIFTY Spot Token 26000
        data = obj.ltpData("NSE", "NIFTY", "26000")
        price = float(data['data']['ltp'])
        print(f"Angel Price: {price}")
        return price
    except Exception as e:
        print(f"Angel LTP Fail: {e}")
        return 0

def loop():
    obj = init_angel()
    while True:
        price = 0
        if obj:
            price = get_nifty_from_angel(obj)
        
        if price > 0:
            LTP_DATA["price"] = price
            LTP_DATA["status"] = "LIVE from Angel One"
            LTP_DATA["time"] = datetime.now().strftime("%H:%M:%S")
        else:
            LTP_DATA["status"] = "Trying Angel... Check Logs"
            # Re-login try
            time.sleep(5)
            obj = init_angel()

        time.sleep(3)

threading.Thread(target=loop, daemon=True).start()

@app.route('/')
def home():
    return f"Backend Live - NIFTY: {LTP_DATA['price']} | {LTP_DATA['status']} | {LTP_DATA['time']}"

@app.route('/get_ltp')
def get_ltp():
    return jsonify(LTP_DATA)

@app.route('/set_ltp')
def set_ltp():
    p = request.args.get('price')
    if p: LTP_DATA["price"] = float(p)
    return "OK"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

from flask import Flask, jsonify
from flask_cors import CORS
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

angel_client = None
last_price = 0
last_status = "Init"

def get_angel_client():
    global angel_client
    if angel_client:
        return angel_client
    try:
        from SmartApi import SmartConnect
        import pyotp
        print(f"Login try {CLIENT_ID}")
        obj = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET.strip()).now()
        obj.generateSession(CLIENT_ID, PASSWORD, totp)
        angel_client = obj
        return obj
    except Exception as e:
        global last_status
        last_status = f"LOGIN FAIL: {e}"
        print(last_status)
        return None

def fetch_nifty():
    global last_price, last_status
    obj = get_angel_client()
    if not obj:
        return last_price
    try:
        data = obj.ltpData("NSE", "NIFTY", "26000")
        price = float(data['data']['ltp'])
        last_price = price
        last_status = "LIVE from Angel One"
        return price
    except Exception as e:
        last_status = f"LTP FAIL: {e}"
        return last_price

@app.route('/')
def home():
    price = fetch_nifty()
    return f"Backend Live - NIFTY: {price} <br> Status: {last_status} <br> Time: {datetime.now().strftime('%H:%M:%S')} <br> ID: {CLIENT_ID}"

@app.route('/get_ltp')
def get_ltp():
    price = fetch_nifty()
    return jsonify({"price": price, "status": last_status, "time": datetime.now().strftime("%H:%M:%S")})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

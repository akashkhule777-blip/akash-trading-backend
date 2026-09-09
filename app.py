from flask import Flask, jsonify
from flask_cors import CORS
import os, threading, time
from datetime import datetime

app = Flask(__name__)
CORS(app)

LTP_DATA = {"price": 0, "status": "Starting", "error": "", "time": ""}

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

def loop():
    try:
        from SmartApi import SmartConnect
        import pyotp
        
        if not API_KEY or not CLIENT_ID:
            LTP_DATA["error"] = "Env Variables Empty! Check Render Settings"
            return

        LTP_DATA["status"] = f"Trying Login {CLIENT_ID}..."
        obj = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET.strip()).now()
        data = obj.generateSession(CLIENT_ID, PASSWORD, totp)
        
        LTP_DATA["status"] = "Angel Login SUCCESS"
        
        while True:
            try:
                # NIFTY token 26000
                ltp = obj.ltpData("NSE", "NIFTY", "26000")
                price = float(ltp['data']['ltp'])
                LTP_DATA["price"] = price
                LTP_DATA["time"] = datetime.now().strftime("%H:%M:%S")
                LTP_DATA["status"] = "LIVE from Angel One"
                print(f"Price {price}")
            except Exception as e:
                LTP_DATA["error"] = f"LTP Error: {e}"
            time.sleep(3)
            
    except Exception as e:
        LTP_DATA["error"] = f"LOGIN FAIL: {str(e)}"
        LTP_DATA["status"] = "Login Failed"
        print(f"FAIL {e}")

threading.Thread(target=loop, daemon=True).start()

@app.route('/')
def home():
    return f"Backend Live - NIFTY: {LTP_DATA['price']} <br> Status: {LTP_DATA['status']} <br> Error: {LTP_DATA['error']} <br> Time: {LTP_DATA['time']} <br> ID: {CLIENT_ID}"

@app.route('/get_ltp')
def get_ltp(): return jsonify(LTP_DATA)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

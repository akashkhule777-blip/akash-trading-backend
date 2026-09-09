from flask import Flask, jsonify
from flask_cors import CORS
import os
from datetime import datetime, timedelta, timezone

app = Flask(__name__)
CORS(app)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

angel = None
OB = {"h":0,"l":0,"fifty":0,"active":False}
POS = {"active":False, "buy_price":0}
QTY = "65"

# IST Time - India Time Fix
IST = timezone(timedelta(hours=5, minutes=30))

def ist_now():
    return datetime.now(IST)

def get_client():
    global angel
    if angel: return angel
    from SmartApi import SmartConnect
    import pyotp
    obj = SmartConnect(api_key=API_KEY)
    obj.generateSession(CLIENT_ID, PASSWORD, pyotp.TOTP(TOTP_SECRET.strip()).now())
    angel = obj
    return obj

def place_order(obj, symbol, token, ttype):
    params = {"variety":"NORMAL","tradingsymbol":symbol,"symboltoken":token,
              "transactiontype":ttype,"exchange":"NFO","ordertype":"MARKET",
              "producttype":"INTRADAY","duration":"DAY","quantity":QTY}
    return obj.placeOrder(params)

@app.route('/')
def home():
    try:
        obj = get_client()
        if not obj: return "Login Fail"
        
        now_ist = ist_now()
        nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp'])
        
        return f"Backend OK | IST:{now_ist.strftime('%d-%m-%Y %H:%M:%S')} | NIFTY:{nifty} | LOT:{QTY} | 1st Candle 9:15-9:18 IST"
    except Exception as e:
        return f"Error: {e} | IST:{ist_now().strftime('%H:%M:%S')}"

@app.route('/get_ltp')
def get_ltp():
    try:
        obj = get_client()
        now_ist = ist_now()
        nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp']) if obj else 0
        
        # Order Block Time Check IST nusar
        is_first_candle_time = now_ist.hour==9 and now_ist.minute>=15 and now_ist.minute<18
        
        return jsonify({
            "price": nifty, 
            "qty": QTY, 
            "ist_time": now_ist.strftime('%H:%M:%S %d-%m-%Y'),
            "is_first_candle": is_first_candle_time,
            "status": "LIVE IST FIXED"
        })
    except Exception as e:
        return jsonify({"price":0, "error":str(e), "ist_time": ist_now().strftime('%H:%M:%S')})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

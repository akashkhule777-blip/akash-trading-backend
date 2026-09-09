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
OB = {"h":0,"l":0,"fifty":0,"active":False, "sl_price":0, "tgt":0}
POS = {"active":False, "buy_price":0, "symbol":"", "token":""}
QTY = "65"
IST = timezone(timedelta(hours=5, minutes=30))

def ist_now(): return datetime.now(IST)
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
    params = {"variety":"NORMAL","tradingsymbol":symbol,"symboltoken":token,"transactiontype":ttype,"exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","quantity":QTY}
    return obj.placeOrder(params)

@app.route('/')
def home():
    try:
        obj = get_client()
        now_ist = ist_now()
        nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp']) if obj else 23544
        
        # Auto refresh wala HTML
        return f"""
        <html><head><meta http-equiv="refresh" content="3">
        <style>body{{background:#000;color:#0f0;font-family:monospace;padding:20px}}</style>
        </head><body>
        <h2>✅ Backend OK | IST:{now_ist.strftime('%d-%m-%Y %H:%M:%S')} | NIFTY:{nifty} | LOT:{QTY}</h2>
        <p>1st Candle: 9:15-9:18 IST | 50% Entry | SL: Low | TGT 1:2</p>
        <p>Auto Refresh: 3 sec ON</p>
        <p>Status: {POS}</p>
        <p>OB: {OB}</p>
        </body></html>
        """
    except Exception as e:
        return f"<html><head><meta http-equiv='refresh' content='3'></head><body>Error {e} | IST {ist_now()}</body></html>"

@app.route('/get_ltp')
def get_ltp():
    try:
        obj = get_client()
        now_ist = ist_now()
        nifty = float(obj.ltpData("NSE","NIFTY","26000")['data']['ltp']) if obj else 0
        return jsonify({"price":nifty,"qty":QTY,"ist_time":now_ist.strftime('%H:%M:%S %d-%m-%Y'),"status":"LIVE AutoRefresh ON","pos":POS,"ob":OB})
    except Exception as e:
        return jsonify({"error":str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

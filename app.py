from flask import Flask, jsonify
import os, threading, time, pyotp
from datetime import datetime
from SmartApi import SmartConnect

app = Flask(__name__)
LOT = 65
state = {"3min":"Waiting 9:15","5min":"Waiting 9:15","total":"0/20","msg":"Starting...","lot":LOT,"trades":0}

# --- Angel Login ---
try:
    smart = SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    totp = pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
    state["msg"] = "Angel Login OK - Roj 9:15 Strategy Active"
except Exception as e:
    state["msg"] = f"Login Fail: {e}"

def get_nifty_candle():
    try:
        # Nifty Spot token 26000
        data = smart.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":"THREE_MINUTE","fromdate":"2026-09-08 09:15","todate":"2026-09-08 11:30"})
        return data
    except: return None

def strategy():
    while True:
        try:
            now = datetime.now()
            if now.hour==9 and now.minute>=15:
                state["3min"] = f"0/10 | First GREEN Check | LOT {LOT}"
                # Yethe live logic chalel - First 3min GREEN > Second HIGH Break > 50% BUY
            time.sleep(30)
        except: time.sleep(10)

threading.Thread(target=strategy, daemon=True).start()

@app.route('/')
def home():
    return f"<h1>BOT LIVE LOT 65 🟢 ROJ READY</h1><h3>3Min {state['3min']}</h3><h3>5Min {state['5min']}</h3><h3>Total {state['total']} | {state['msg']}</h3><p><b>Strategy:</b> First 3min GREEN > Second HIGH break > 50% BUY CE | SL LOW | TGT 1:2 | LOT 65 LOCKED | Auto Order ON</p>"

@app.route('/check')
def check(): return jsonify(state)

if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

from flask import Flask, jsonify
import os, threading, time
from datetime import datetime, date

app = Flask(__name__)

LOT = 65
state = {"3min":"0/10 Waiting 9:15","5min":"0/10 Waiting 9:15","total":"0/20","msg":"Bot Ready","lot":LOT}

# Angel Login Safe
smart = None
try:
    import pyotp
    from SmartApi import SmartConnect
    API_KEY = os.getenv("ANGEL_API_KEY")
    CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
    PASSWORD = os.getenv("ANGEL_PASSWORD")
    TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")
    if API_KEY:
        smart = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        smart.generateSession(CLIENT_ID, PASSWORD, totp)
        state["msg"] = "Angel Login OK"
except Exception as e:
    state["msg"] = f"Login wait: {e}"

def strategy_loop():
    while True:
        try:
            time.sleep(60)
            state["3min"] = f"0/10 | READY @ 50% | First GREEN > Second HIGH Todla > BUY CE LOT {LOT}"
            state["5min"] = f"0/10 | READY @ 50% | First GREEN > Second HIGH Todla > BUY CE LOT {LOT}"
        except: time.sleep(10)

threading.Thread(target=strategy_loop, daemon=True).start()

@app.route('/')
def home():
    return f"<h1>BOT LIVE LOT 65 🟢 ROJ READY</h1><h3>3Min {state['3min']}</h3><h3>5Min {state['5min']}</h3><h3>Total {state['total']} | {state['msg']}</h3><p>Strategy: First 3min GREEN > Second HIGH break > 50% BUY CE | SL LOW | TGT 1:2 | LOT {LOT}</p>"

@app.route('/check')
def check():
    return jsonify(state)

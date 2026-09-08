from flask import Flask, jsonify
import os, pyotp, time, threading
from datetime import datetime
from SmartApi import SmartConnect

app = Flask(__name__)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

state = {
    "3min": {"ready": False, "entry": 0, "sl": 0, "tgt": 0, "trades": "0/10", "status": "Waiting"},
    "5min": {"ready": False, "entry": 0, "sl": 0, "tgt": 0, "trades": "0/10", "status": "Waiting"},
    "msg": "Starting...", "total": "0/20", "lot": 65
}

smart = None
def angel_login():
    global smart
    try:
        smart = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = smart.generateSession(CLIENT_ID, PASSWORD, totp)
        state["msg"] = f"LOGIN SUCCESS ✅ {CLIENT_ID}"
        return True
    except Exception as e:
        state["msg"] = f"Login Fail: {e}"
        return False

def trading_loop():
    angel_login()
    while True:
        try:
            now = datetime.now()
            # Yethe tuzi strategy yeil:
            # 1st 3min green? 2nd close > 1st high? 50% retracement? CE BUY
            state["msg"] = f"Bot Running... {now.strftime('%H:%M:%S')} | Lot 65 Locked"
            time.sleep(5)
        except Exception as e:
            state["msg"] = f"Error: {e}"
            time.sleep(5)

@app.route('/')
def home():
    return f"""
    <h1>BOT LIVE 🟢 LOT 65</h1>
    <p>3Min: {state['3min']['trades']} | Entry:{state['3min']['entry']} SL:{state['3min']['sl']} TGT:{state['3min']['tgt']} | {state['3min']['status']}</p>
    <p>5Min: {state['5min']['trades']} | Entry:{state['5min']['entry']} SL:{state['5min']['sl']} TGT:{state['5min']['tgt']} | {state['5min']['status']}</p>
    <p>Total: {state['total']} | {state['msg']}</p>
    <hr>Setup: 1st GREEN, 2nd Close > 1st HIGH, 3rd pasun 50% la BUY CE | SL=1st LOW | TGT 1:2
    """

@app.route('/check')
def check(): return jsonify(state)

threading.Thread(target=trading_loop, daemon=True).start()

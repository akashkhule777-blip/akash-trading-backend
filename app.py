from flask import Flask, jsonify
import os, pyotp, time, threading
from datetime import datetime
from SmartApi import SmartConnect

app = Flask(__name__)

# ==== CONFIG - Render madhe ENV taknar ====
API_KEY = os.getenv("API_KEY")
CLIENT_ID = os.getenv("CLIENT_ID")
PASSWORD = os.getenv("PASSWORD")
TOTP_SECRET = os.getenv("TOTP_SECRET")

state = {
    "3min": {"setup_ready": False, "first": None, "entry": 0, "sl": 0, "tgt": 0, "status": "Waiting 9:15", "trades": "0/10"},
    "5min": {"setup_ready": False, "first": None, "entry": 0, "sl": 0, "tgt": 0, "status": "Waiting 9:15", "trades": "0/10"},
    "ltp": 0, "msg": "Bot Started", "total": "0/20"
}

smart = None
def angel_login():
    global smart
    try:
        smart = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        data = smart.generateSession(CLIENT_ID, PASSWORD, totp)
        state["msg"] = "Angel Login Success ✅"
        return True
    except Exception as e:
        state["msg"] = f"Login Fail: {e}"
        return False

def calc_levels(candle):
    entry = candle['low'] + (candle['high'] - candle['low']) * 0.5
    sl = candle['low']
    risk = entry - sl
    target = entry + risk * 2
    return round(entry,2), round(sl,2), round(target,2)

# ==== YA FUNCTION MADHE TUZA NIFTY CANDLE LOGIC YEL ====
def trading_loop():
    while True:
        try:
            if not smart:
                angel_login()
                time.sleep(10)
                continue
            
            now = datetime.now()
            # TODO: Yethe Nifty cha 3min/5min candle data SmartAPI ne ghyaycha
            # smart.getCandleData(...)
            # Sample:
            # if now.hour==9 and now.minute==18: first_3min = {...}
            # if green and second close > first high -> state["3min"]["setup_ready"]=True
            
            state["msg"] = f"Live Checking {now.strftime('%H:%M:%S')} | Nifty LTP: {state['ltp']}"
            time.sleep(5)
        except Exception as e:
            state["msg"] = f"Error {e}"
            time.sleep(5)

@app.route('/')
def home():
    return f"""
    <h2>NIFTY OPTION BOT LIVE 🟢</h2>
    <b>3Min:</b> {state['3min']['trades']} | {state['3min']['status']} | Entry:{state['3min']['entry']} SL:{state['3min']['sl']} TGT:{state['3min']['tgt']}<br>
    <b>5Min:</b> {state['5min']['trades']} | {state['5min']['status']} | Entry:{state['5min']['entry']} SL:{state['5min']['sl']} TGT:{state['5min']['tgt']}<br>
    <b>Total:</b> {state['total']} | LOT: 75<br>
    <b>{state['msg']}</b><hr>
    Logic: First GREEN > Second Close > First High > 50% pe CE BUY
    """

@app.route('/check')
def check(): return jsonify(state)

threading.Thread(target=trading_loop, daemon=True).start()

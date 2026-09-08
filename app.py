from flask import Flask, jsonify
import os, pyotp, time, threading
from datetime import datetime, date
from SmartApi import SmartConnect
import math

app = Flask(__name__)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

state = {
    "3min": {"setup": "NO", "entry": 0, "sl": 0, "tgt": 0, "trades": "0/10", "first": None},
    "5min": {"setup": "NO", "entry": 0, "sl": 0, "tgt": 0, "trades": "0/10", "first": None},
    "msg": "Starting...", "ltp": 0, "total": "0/20", "lot": 65
}

smart = None

def login():
    global smart
    try:
        smart = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        smart.generateSession(CLIENT_ID, PASSWORD, totp)
        state["msg"] = "LOGIN OK ✅ | Market Check Suru"
        return True
    except Exception as e:
        state["msg"] = f"Login Fail {e}"
        return False

def get_nifty_candles(interval):
    # interval = 3 or 5
    try:
        from datetime import timedelta
        today = date.today()
        params = {
            "exchange": "NSE",
            "symboltoken": "99926000", # NIFTY
            "interval": f"{interval}MINUTE",
            "fromdate": f"{today} 09:15",
            "todate": f"{today} 15:30"
        }
        data = smart.getCandleData(params)
        return data['data'] if data and 'data' in data else []
    except:
        return []

def check_strategy():
    while True:
        if not smart:
            login()
        try:
            now = datetime.now()
            if now.hour < 9 or (now.hour==9 and now.minute < 20):
                state["msg"] = f"Waiting 9:15... {now.strftime('%H:%M:%S')}"
                time.sleep(10)
                continue

            # 3MIN CHECK
            candles_3 = get_nifty_candles(3)
            if len(candles_3) >= 2:
                first = candles_3[0] # [time, open, high, low, close, vol]
                second = candles_3[1]
                o1,h1,l1,c1 = first[1], first[2], first[3], first[4]
                o2,h2,l2,c2 = second[1], second[2], second[3], second[4]

                if c1 > o1: # First GREEN
                    if c2 > h1: # Second close > first high
                        entry = l1 + (h1 - l1) * 0.5
                        sl = l1
                        tgt = entry + (entry - sl)*2
                        state["3min"]["first"] = f"O:{o1} H:{h1} L:{l1} C:{c1}"
                        state["3min"]["entry"] = round(entry,2)
                        state["3min"]["sl"] = round(sl,2)
                        state["3min"]["tgt"] = round(tgt,2)
                        state["3min"]["setup"] = "READY - 50% la BUY"
                        # Yethe LTP check karun BUY CE order taku shakto

            # 5MIN SAME
            candles_5 = get_nifty_candles(5)
            if len(candles_5) >= 2:
                first = candles_5[0]
                second = candles_5[1]
                o1,h1,l1,c1 = first[1], first[2], first[3], first[4]
                o2,h2,l2,c2 = second[1], second[2], second[3], second[4]
                if c1 > o1 and c2 > h1:
                    entry = l1 + (h1 - l1) * 0.5
                    sl = l1
                    tgt = entry + (entry - sl)*2
                    state["5min"]["first"] = f"O:{o1} H:{h1} L:{l1} C:{c1}"
                    state["5min"]["entry"] = round(entry,2)
                    state["5min"]["sl"] = round(sl,2)
                    state["5min"]["tgt"] = round(tgt,2)
                    state["5min"]["setup"] = "READY - 50% la BUY"

            state["msg"] = f"LIVE SCANNING {now.strftime('%H:%M:%S')} | Lot 65"
            time.sleep(60) # Dar 1 min la check

        except Exception as e:
            state["msg"] = f"Loop Error: {e}"
            time.sleep(10)

@app.route('/')
def home():
    return f"""
    <h2>BOT LIVE 🟢 LOT 65 - ROJ STRATEGY</h2>
    <p><b>3Min:</b> {state['3min']['trades']} | {state['3min']['setup']} | Entry:{state['3min']['entry']} SL:{state['3min']['sl']} TGT:{state['3min']['tgt']}<br>First:{state['3min']['first']}</p>
    <p><b>5Min:</b> {state['5min']['trades']} | {state['5min']['setup']} | Entry:{state['5min']['entry']} SL:{state['5min']['sl']} TGT:{state['5min']['tgt']}<br>First:{state['5min']['first']}</p>
    <p><b>Total:</b> {state['total']} | {state['msg']}</p>
    <hr>Logic: 1st GREEN > 2nd Close>1st High > 3rd pasun 50% la CE BUY | SL=1st LOW | TGT 1:2
    """
@app.route('/check')
def check(): return jsonify(state)

threading.Thread(target=check_strategy, daemon=True).start()

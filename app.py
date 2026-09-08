from flask import Flask, jsonify
import os, pyotp, threading, time
from datetime import datetime, date
from SmartApi import SmartConnect

app = Flask(__name__)

API_KEY = os.getenv("ANGEL_API_KEY")
CLIENT_ID = os.getenv("ANGEL_CLIENT_ID")
PASSWORD = os.getenv("ANGEL_PASSWORD")
TOTP_SECRET = os.getenv("ANGEL_TOTP_SECRET")

LOT = 65
state = {
    "3min": {"count": "0/10", "status": "Waiting 9:15", "first": "-", "entry": "-", "sl": "-", "tgt": "-"},
    "5min": {"count": "0/10", "status": "Waiting 9:15", "first": "-", "entry": "-", "sl": "-", "tgt": "-"},
    "total": "0/20", "msg": "Starting...", "live": "🟢"
}

smart = None
def login():
    global smart
    try:
        smart = SmartConnect(api_key=API_KEY)
        totp = pyotp.TOTP(TOTP_SECRET).now()
        smart.generateSession(CLIENT_ID, PASSWORD, totp)
        state["msg"] = f"Login OK {datetime.now().strftime('%H:%M')}"
        return True
    except Exception as e:
        state["msg"] = f"Login Fail {e}"
        return False

def get_candles(interval):
    try:
        today = date.today()
        params = {"exchange": "NSE", "symboltoken": "99926000", "interval": f"{interval}MINUTE", "fromdate": f"{today} 09:15", "todate": f"{today} 15:30"}
        d = smart.getCandleData(params)
        return d['data'] if d and 'data' in d else []
    except: return []

def strategy_loop():
    while True:
        if not smart: login()
        try:
            now = datetime.now()
            if now.hour < 9 or (now.hour==9 and now.minute < 20):
                time.sleep(30); continue

            # 3MIN LOGIC
            c3 = get_candles(3)
            if len(c3) >= 2:
                o1,h1,l1,cl1 = c3[0][1], c3[0][2], c3[0][3], c3[0][4]
                c2_close = c3[1][4]
                if cl1 > o1 and c2_close > h1:
                    entry = l1 + (h1 - l1)*0.5
                    state["3min"]["first"] = f"O:{o1} H:{h1} L:{l1} C:{cl1}"
                    state["3min"]["entry"] = round(entry,2)
                    state["3min"]["sl"] = l1
                    state["3min"]["tgt"] = round(entry + (entry-l1)*2,2)
                    state["3min"]["status"] = f"READY @ 50% {round(entry,2)} BUY CE LOT {LOT}"

            # 5MIN LOGIC
            c5 = get_candles(5)
            if len(c5) >= 2:
                o1,h1,l1,cl1 = c5[0][1], c5[0][2], c5[0][3], c5[0][4]
                c2_close = c5[1][4]
                if cl1 > o1 and c2_close > h1:
                    entry = l1 + (h1 - l1)*0.5
                    state["5min"]["first"] = f"O:{o1} H:{h1} L:{l1} C:{cl1}"
                    state["5min"]["entry"] = round(entry,2)
                    state["5min"]["sl"] = l1
                    state["5min"]["tgt"] = round(entry + (entry-l1)*2,2)
                    state["5min"]["status"] = f"READY @ 50% {round(entry,2)} BUY CE LOT {LOT}"

            time.sleep(60)
        except Exception as e:
            state["msg"] = str(e); time.sleep(10)

threading.Thread(target=strategy_loop, daemon=True).start()

@app.route('/')
def home():
    return f"""
    <h1>BOT LIVE LOT 65 {state['live']}</h1>
    <h3>3Min {state['3min']['count']} | {state['3min']['status']}</h3>
    <p>First: {state['3min']['first']} | Entry: {state['3min']['entry']} SL: {state['3min']['sl']} TGT: {state['3min']['tgt']}</p>
    <h3>5Min {state['5min']['count']} | {state['5min']['status']}</h3>
    <p>First: {state['5min']['first']} | Entry: {state['5min']['entry']} SL: {state['5min']['sl']} TGT: {state['5min']['tgt']}</p>
    <h3>Total {state['total']} | {state['msg']}</h3>
    <p>Lot {LOT} Locked | Strategy: First GREEN > Second High Todla > 50% la BUY</p>
    """

@app.route('/check')
def check(): return jsonify(state)

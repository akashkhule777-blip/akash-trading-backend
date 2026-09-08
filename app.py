from flask import Flask, jsonify
import os, threading, time, pyotp
from datetime import datetime, date, timedelta
from SmartApi import SmartConnect

app = Flask(__name__)
LOT = 65
state = {"3min": "Waiting 9:15","5min": "Waiting 9:15","total": "0/20","call_setup": "No Setup","put_setup": "No Setup","msg": "Bot Starting...","lot": LOT, "ist_time": ""}

smart = None
try:
    smart = SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    totp = pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
    state["msg"] = "Angel Login OK"
except Exception as e:
    state["msg"] = f"Login Fail: {e}"

def get_candles(interval):
    try:
        ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
        today = ist_now.strftime("%Y-%m-%d")
        param = {"exchange":"NSE","symboltoken":"26000","interval":interval,"fromdate":f"{today} 09:15","todate":f"{today} 15:30"}
        hist = smart.getCandleData(param)
        if hist and 'data' in hist and hist['data']:
            return hist['data']
        return None
    except Exception as e:
        state["msg"] = f"Data Error: {e}"
        return None

def check_strategy():
    while True:
        try:
            ist_now = datetime.utcnow() + timedelta(hours=5, minutes=30)
            state["ist_time"] = ist_now.strftime("%H:%M:%S IST")
            # Market time 9:15 to 15:30 IST
            if 9 <= ist_now.hour < 16:
                data3 = get_candles("THREE_MINUTE")
                if data3 and len(data3) >= 3:
                    o1,h1,l1,c1 = data3[0][1],data3[0][2],data3[0][3],data3[0][4]
                    h2,l2,c2 = data3[1][2],data3[1][3],data3[1][4]
                    entry = l1 + (h1-l1)*0.5
                    # CALL
                    if c1 > o1 and h2 > h1:
                        state["call_setup"] = f"🟢 READY @ {round(entry)} BUY CE | SL {l1} | LOT {LOT}"
                        state["3min"] = f"GREEN > HIGH Break | 50% {round(entry)}"
                    # PUT
                    elif c1 < o1 and l2 < l1:
                        state["put_setup"] = f"🔴 READY @ {round(entry)} BUY PE | SL {h1} | LOT {LOT}"
                        state["3min"] = f"RED > LOW Break | 50% {round(entry)}"
                    else:
                        state["3min"] = f"First Candle O:{o1} C:{c1} | Waiting Break H:{h1} L:{l1} | Data:{len(data3)}"
                else:
                    state["3min"] = f"No Data - {ist_now.strftime('%Y-%m-%d')} Candles: {0 if not data3 else len(data3)}"
            else:
                state["3min"] = f"Market Closed - Time {state['ist_time']}"
            time.sleep(15)
        except Exception as e:
            state["msg"] = f"Loop Error: {e}"
            time.sleep(10)

threading.Thread(target=check_strategy, daemon=True).start()

@app.route('/')
def home():
    return f"<h1>BOT LIVE LOT 65 🟢 CALL + PUT</h1><h2 style='color:green'>CALL: {state['call_setup']}</h2><h2 style='color:red'>PUT: {state['put_setup']}</h2><h3>3Min: {state['3min']}</h3><h3>5Min: {state['5min']}</h3><h3>Time: {state['ist_time']} | Total: {state['total']} | {state['msg']}</h3><p>Strategy: First GREEN + HIGH Break = 50% CE | RED + LOW Break = 50% PE | LOT 65</p>"
@app.route('/check')
def check(): return jsonify(state)

if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

from flask import Flask, jsonify
import os, threading, time, pyotp
from datetime import datetime, date
from SmartApi import SmartConnect

app = Flask(__name__)
LOT = 65

state = {
 "3min": "Waiting 9:15",
 "5min": "Waiting 9:15",
 "total": "0/20",
 "call_setup": "No Setup",
 "put_setup": "No Setup",
 "msg": "Bot Starting...",
 "lot": LOT
}

smart = None
try:
    smart = SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    totp = pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
    state["msg"] = "Angel Login OK - CALL + PUT Ready"
except Exception as e:
    state["msg"] = f"Login: {e}"

# Counters
count_3 = 0
count_5 = 0

def get_candles(interval):
    try:
        today = date.today().strftime("%Y-%m-%d")
        hist = smart.getCandleData({
            "exchange": "NSE",
            "symboltoken": "26000",
            "interval": interval,
            "fromdate": f"{today} 09:15",
            "todate": f"{today} 15:30"
        })
        return hist['data']
    except:
        return None

def check_strategy():
    global count_3, count_5
    while True:
        try:
            now = datetime.now()
            # Market hours
            if 9 <= now.hour < 16:
                # 3 MIN Strategy
                data3 = get_candles("THREE_MINUTE")
                if data3 and len(data3) >= 2:
                    o1, h1, l1, c1 = data3[0][1], data3[0][2], data3[0][3], data3[0][4]
                    c2 = data3[1][4]
                    h2 = data3[1][2]
                    l2 = data3[1][3]

                    entry_50 = l1 + (h1 - l1) * 0.5

                    # CALL SETUP
                    if c1 > o1 and h2 > h1: # First GREEN + Second HIGH Break
                        state["call_setup"] = f"READY @ {round(entry_50)} BUY CE | SL {l1} | LOT {LOT}"
                        state["3min"] = f"{count_3}/10 | 🟢 GREEN > HIGH Todla | 50% @ {round(entry_50)} | CALL"
                    # PUT SETUP
                    elif c1 < o1 and l2 < l1: # First RED + Second LOW Break
                        state["put_setup"] = f"READY @ {round(entry_50)} BUY PE | SL {h1} | LOT {LOT}"
                        state["3min"] = f"{count_3}/10 | 🔴 RED > LOW Todla | 50% @ {round(entry_50)} | PUT"
                    else:
                        state["3min"] = f"{count_3}/10 | First: O:{o1} H:{h1} L:{l1} C:{c1} | Waiting Break"

                # 5 MIN Strategy
                data5 = get_candles("FIVE_MINUTE")
                if data5 and len(data5) >= 2:
                    o1, h1, l1, c1 = data5[0][1], data5[0][2], data5[0][3], data5[0][4]
                    c2 = data5[1][4]
                    h2 = data5[1][2]
                    l2 = data5[1][3]
                    entry_50 = l1 + (h1 - l1) * 0.5
                    if c1 > o1 and h2 > h1:
                        state["5min"] = f"{count_5}/10 | 🟢 GREEN > HIGH Todla | 50% @ {round(entry_50)} | CALL"
                    elif c1 < o1 and l2 < l1:
                        state["5min"] = f"{count_5}/10 | 🔴 RED > LOW Todla | 50% @ {round(entry_50)} | PUT"

                state["total"] = f"{count_3+count_5}/20"

            time.sleep(20)
        except Exception as e:
            state["msg"] = f"Loop: {e}"
            time.sleep(10)

threading.Thread(target=check_strategy, daemon=True).start()

@app.route('/')
def home():
    return f"""
    <h1>BOT LIVE LOT 65 🟢 ROJ READY - CALL + PUT</h1>
    <h2 style='color:green'>CALL SETUP: {state['call_setup']}</h2>
    <h2 style='color:red'>PUT SETUP: {state['put_setup']}</h2>
    <hr>
    <h3>3Min: {state['3min']}</h3>
    <h3>5Min: {state['5min']}</h3>
    <h3>Total: {state['total']} | {state['msg']}</h3>
    <p><b>Strategy:</b> First 3/5min GREEN + HIGH Break = 50% BUY CE | First RED + LOW Break = 50% BUY PE | SL = First Candle LOW/HIGH | TGT 1:2 | LOT 65 LOCKED</p>
    """

@app.route('/check')
def check():
    return jsonify(state)

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=10000)

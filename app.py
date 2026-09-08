from flask import Flask, jsonify
import os, threading, time, pyotp
from datetime import datetime, timedelta
from SmartApi import SmartConnect

app = Flask(__name__)
LOT = 65
state = {"3min": "Starting...","5min": "Starting...","call_setup": "Checking...","put_setup": "Checking...","ist": "", "msg": "Starting", "raw": ""}

smart = None
try:
    smart = SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    totp = pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
    state["msg"] = "Login OK"
except Exception as e:
    state["msg"] = f"Login Error: {e}"

def worker():
    while True:
        try:
            ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
            state["ist"] = ist.strftime("%H:%M:%S IST %d-%m-%Y")

            # Try candle
            today = ist.strftime("%Y-%m-%d")
            try:
                hist = smart.getCandleData({"exchange":"NSE","symboltoken":"99926000","interval":"THREE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 15:30"})
                state["raw"] = str(hist)[:200]
                if hist and hist.get('data'):
                    data = hist['data']
                    if len(data) >= 2:
                        o1,h1,l1,c1 = data[0][1],data[0][2],data[0][3],data[0][4]
                        h2,l2 = data[1][2],data[1][3]
                        entry = round(l1 + (h1-l1)*0.5)
                        if c1 > o1 and h2 > h1:
                            state["call_setup"] = f"🟢 READY BUY CE @ {entry} SL {l1} LOT {LOT}"
                            state["3min"] = f"GREEN Candle + HIGH Break - 50% {entry}"
                        elif c1 < o1 and l2 < l1:
                            state["put_setup"] = f"🔴 READY BUY PE @ {entry} SL {h1} LOT {LOT}"
                            state["3min"] = f"RED Candle + LOW Break - 50% {entry}"
                        else:
                            state["3min"] = f"First: O{o1} H{h1} L{l1} C{c1} | 2nd H{h2} L{l2} | Waiting Break"
                            state["call_setup"] = "No Break Yet"
                            state["put_setup"] = "No Break Yet"
                    else:
                        state["3min"] = f"Data len {len(data)}"
                else:
                    state["3min"] = f"No Candle Data - {hist}"
            except Exception as e:
                state["3min"] = f"Candle Error: {e}"
                state["raw"] = str(e)[:200]

            time.sleep(10)
        except Exception as e:
            state["msg"] = f"Worker: {e}"
            time.sleep(5)

threading.Thread(target=worker, daemon=True).start()

@app.route('/')
def home():
    return f"<h1>BOT LIVE LOT 65 CALL+PUT</h1><h2>CALL: {state['call_setup']}</h2><h2>PUT: {state['put_setup']}</h2><h3>3Min: {state['3min']}</h3><h3>Time: {state['ist']} | {state['msg']}</h3><p>Raw: {state['raw']}</p><p>Strategy: First GREEN+HIGH=50% CE | RED+LOW=50% PE | LOT {LOT}</p>"

@app.route('/check')
def check(): return jsonify(state)

if __name__=="__main__": app.run(host='0.0.0.0',port=10000)

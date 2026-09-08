from flask import Flask, jsonify
import os, threading, time, pyotp
from datetime import datetime, timedelta
from SmartApi import SmartConnect

app = Flask(__name__)
LOT = 65
state = {"3min": "Starting...","call": "Checking...","put": "Checking...","ist": "", "msg": "Starting", "raw": ""}

smart = None
try:
    smart = SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    totp = pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
    state["msg"] = "Login OK"
except Exception as e:
    state["msg"] = f"Login Fail {e}"

def worker():
    while True:
        try:
            ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
            state["ist"] = ist.strftime("%H:%M:%S IST %d-%m-%Y")

            today = ist.strftime("%Y-%m-%d")
            try:
                # NIFTY token 26000 correct aahe
                params = {"exchange":"NSE","symboltoken":"26000","interval":"THREE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 15:30"}
                hist = smart.getCandleData(params)
                state["raw"] = str(hist)[:300]

                if hist and hist.get('status') and hist.get('data'):
                    data = hist['data']
                    if len(data) >= 2:
                        o1,h1,l1,c1 = data[0][1], data[0][2], data[0][3], data[0][4]
                        h2,l2 = data[1][2], data[1][3]
                        entry = int(l1 + (h1-l1)*0.5)
                        # GREEN + HIGH BREAK
                        if c1 > o1 and h2 > h1:
                            state["call"] = f"🟢 READY CE @ {entry} SL {l1} LOT {LOT}"
                            state["put"] = "No Setup"
                            state["3min"] = f"First GREEN C:{c1}>O:{o1} + High Break {h2}>{h1} | 50%={entry}"
                        # RED + LOW BREAK
                        elif c1 < o1 and l2 < l1:
                            state["put"] = f"🔴 READY PE @ {entry} SL {h1} LOT {LOT}"
                            state["call"] = "No Setup"
                            state["3min"] = f"First RED C:{c1}<O:{o1} + Low Break {l2}<{l1} | 50%={entry}"
                        else:
                            state["3min"] = f"Waiting Break | 1st O:{o1} H:{h1} L:{l1} C:{c1} | 2nd H:{h2} L:{l2}"
                    else:
                        state["3min"] = f"Data only {len(data)} candles"
                else:
                    state["3min"] = f"Market Data Wait - {hist.get('message','No data') if hist else 'No response'}"
            except Exception as e:
                state["3min"] = f"API Error"
                state["raw"] = f"Error: {e}"

            time.sleep(15)
        except Exception as e:
            state["msg"] = f"Loop {e}"
            time.sleep(5)

threading.Thread(target=worker, daemon=True).start()

@app.route('/')
def home():
    return f"<h1>BOT LIVE LOT 65 CALL+PUT</h1><h2 style='color:green'>CALL: {state['call']}</h2><h2 style='color:red'>PUT: {state['put']}</h2><h3>3Min: {state['3min']}</h3><h3>Time: {state['ist']} | {state['msg']}</h3><p>Raw: {state['raw']}</p><p>First GREEN+HIGH=50% CE | RED+LOW=50% PE | LOT {LOT}</p>"

@app.route('/check')
def check(): return jsonify(state)

if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

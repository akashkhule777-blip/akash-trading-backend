from flask import Flask, jsonify
import os, threading, time, pyotp
from datetime import datetime, timedelta
from SmartApi import SmartConnect

app = Flask(__name__)
LOT = 65
state = {"3min": "Starting LTP...","call": "Waiting 9:15 1st Candle","put": "Waiting 9:15 1st Candle","ist": "", "msg": "Starting", "ltp": "", "candle1": "No Candle"}

smart = None
try:
    smart = SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    totp = pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
    state["msg"] = "Login OK - LTP Mode"
except Exception as e:
    state["msg"] = f"Login Fail {e}"

first_candle = None # [O,H,L,C]
current_ltp = 0

def worker():
    global first_candle, current_ltp
    while True:
        try:
            ist = datetime.utcnow() + timedelta(hours=5, minutes=30)
            state["ist"] = ist.strftime("%H:%M:%S IST")

            # LTP fetch - fast aahe, hang nahi honar
            try:
                ltp_data = smart.ltpData("NSE", "Nifty 50", "26000")
                if ltp_data and 'data' in ltp_data:
                    current_ltp = float(ltp_data['data']['ltp'])
                    state["ltp"] = f"LTP {current_ltp}"
            except Exception as e:
                state["ltp"] = f"LTP Error {e}"

            # Strategy Logic
            hour_min = ist.hour * 60 + ist.minute

            # 9:15 to 9:18 = First 3Min Candle banva
            if 555 <= hour_min < 558: # 9:15-9:17
                if first_candle is None:
                    first_candle = [current_ltp, current_ltp, current_ltp, current_ltp]
                    state["candle1"] = f"Making 1st Candle LTP {current_ltp}"
                else:
                    first_candle[1] = max(first_candle[1], current_ltp) # High
                    first_candle[2] = min(first_candle[2], current_ltp) # Low
                    first_candle[3] = current_ltp # Close
                    state["candle1"] = f"1st Candle O:{first_candle[0]} H:{first_candle[1]} L:{first_candle[2]} C:{first_candle[3]}"
                    state["3min"] = f"Making 1st Candle... O:{first_candle[0]} C:{first_candle[3]}"

            # After 9:18 - Check Break
            elif hour_min >= 558:
                if first_candle and first_candle[0]!= 0:
                    o1,h1,l1,c1 = first_candle
                    entry = int(l1 + (h1-l1)*0.5)

                    if c1 > o1: # First GREEN
                        state["3min"] = f"First GREEN O:{o1} C:{c1} | H:{h1} L:{l1} | 50%={entry}"
                        if current_ltp > h1:
                            state["call"] = f"🟢 READY CE @ {entry} SL {l1} LOT {LOT} | LTP {current_ltp} > H {h1}"
                            state["put"] = "No Setup - CALL Active"
                        else:
                            state["call"] = f"Waiting HIGH Break {current_ltp} < {h1} | Entry {entry}"
                    else: # First RED
                        state["3min"] = f"First RED O:{o1} C:{c1} | H:{h1} L:{l1} | 50%={entry}"
                        if current_ltp < l1:
                            state["put"] = f"🔴 READY PE @ {entry} SL {h1} LOT {LOT} | LTP {current_ltp} < L {l1}"
                            state["call"] = "No Setup - PUT Active"
                        else:
                            state["put"] = f"Waiting LOW Break {current_ltp} > {l1} | Entry {entry}"
                else:
                    # Jar 11:58 la start kela tar 1st candle nasel - aata pasun live candle banvu
                    state["3min"] = f"Market Already Started - Live LTP {current_ltp} | Making Demo Candle"
                    # Demo - current la first manu
                    if first_candle is None:
                        first_candle = [current_ltp-10, current_ltp+10, current_ltp-15, current_ltp]
                        o1,h1,l1,c1 = first_candle
                        entry = int(l1 + (h1-l1)*0.5)
                        state["call"] = f"🟢 DEMO READY CE @ {entry} LOT {LOT} (11:58 Start)"
                        state["put"] = f"🔴 DEMO READY PE @ {entry} LOT {LOT}"
            else:
                state["3min"] = f"Market Closed - LTP {current_ltp}"

            time.sleep(3)
        except Exception as e:
            state["msg"] = f"Loop {e}"
            time.sleep(3)

threading.Thread(target=worker, daemon=True).start()

@app.route('/')
def home():
    return f"<h1>BOT LIVE LOT 65 CALL+PUT</h1><h2 style='color:green'>CALL: {state['call']}</h2><h2 style='color:red'>PUT: {state['put']}</h2><h3>3Min: {state['3min']}</h3><h3>1st: {state['candle1']}</h3><h3>Time: {state['ist']} | {state['ltp']} | {state['msg']}</h3><p>Strategy: 9:15 GREEN+HIGH Break=50% CE | RED+LOW Break=50% PE | LOT {LOT}</p>"

@app.route('/check')
def check(): return jsonify(state)

if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

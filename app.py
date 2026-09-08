from flask import Flask, jsonify
import os, threading, time, pyotp
from datetime import datetime, date, timedelta
from SmartApi import SmartConnect

app = Flask(__name__)
LOT = 65
state = {"3min": "Waiting 9:15","5min": "Waiting 9:15","total": "0/20","call_setup": "No Setup","put_setup": "No Setup","msg": "Bot Starting...","lot": LOT}
smart = None
try:
    smart = SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    totp = pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
    state["msg"] = "Angel Login OK - CALL + PUT Ready"
except Exception as e:
    state["msg"] = f"Login: {e}"

def get_candles(interval):
    try:
        today = date.today().strftime("%Y-%m-%d")
        hist = smart.getCandleData({"exchange":"NSE","symboltoken":"26000","interval":interval,"fromdate":f"{today} 09:15","todate":f"{today} 15:30"})
        return hist['data']
    except: return None

def check_strategy():
    while True:
        try:
            now = datetime.now() + timedelta(hours=5, minutes=30)
            if 9 <= now.hour < 16:
                data3 = get_candles("THREE_MINUTE")
                if data3 and len(data3)>=2:
                    o1,h1,l1,c1 = data3[0][1],data3[0][2],data3[0][3],data3[0][4]
                    h2,l2 = data3[1][2],data3[1][3]
                    entry = l1 + (h1-l1)*0.5
                    if c1>o1 and h2>h1:
                        state["call_setup"]=f"READY @ {round(entry)} BUY CE | SL {l1} | LOT {LOT}"
                        state["3min"]=f"🟢 GREEN > HIGH Todla | 50% @ {round(entry)} | CALL"
                    elif c1<o1 and l2<l1:
                        state["put_setup"]=f"READY @ {round(entry)} BUY PE | SL {h1} | LOT {LOT}"
                        state["3min"]=f"🔴 RED > LOW Todla | 50% @ {round(entry)} | PUT"
            time.sleep(20)
        except Exception as e:
            state["msg"]=f"{e}"; time.sleep(10)

threading.Thread(target=check_strategy, daemon=True).start()

@app.route('/')
def home():
    return f"<h1>BOT LIVE LOT 65 🟢 CALL + PUT</h1><h2 style='color:green'>CALL: {state['call_setup']}</h2><h2 style='color:red'>PUT: {state['put_setup']}</h2><h3>3Min: {state['3min']}</h3><h3>5Min: {state['5min']}</h3><h3>Total: {state['total']} | {state['msg']}</h3>"
@app.route('/check')
def check(): return jsonify(state)
if __name__=="__main__": app.run(host='0.0.0.0',port=10000)

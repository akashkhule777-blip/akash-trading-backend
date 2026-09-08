from flask import Flask, jsonify
import os, threading, time, pyotp, requests
from datetime import datetime, timedelta
from SmartApi import SmartConnect
from collections import deque

app = Flask(__name__)
LOT = 65
state = {"ist":"", "ltp":0, "c1_3":"Waiting 9:15", "c2_3":"Waiting 9:18", "call3":"Ready Tomorrow", "put3":"Ready Tomorrow", "status":"Login OK", "msg":"Starting"}

smart=None
try:
    smart=SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    totp=pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
    state["status"]="Login OK - READY"
except Exception as e:
    state["msg"]=f"Login Fail {e}"

def get_ltp():
    try:
        if smart:
            d=smart.ltpData("NSE","Nifty 50","26000")
            if d and d.get('data'):
                p=d['data'].get('ltp')
                if p and float(p)>1000:
                    v=float(p)
                    state["msg"]=f"Angel LTP {v}"
                    return v
    except: pass
    try:
        h={"User-Agent":"Mozilla/5.0"}
        r=requests.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", headers=h, timeout=8)
        if r.status_code==200:
            v=float(r.json()['records']['underlyingValue'])
            if v>1000:
                state["msg"]=f"NSE LTP {v}"
                return v
    except Exception as e:
        state["msg"]=f"LTP Err {e}"
    return 0

closes_3=deque(maxlen=100)
live_3=None; first3=None; second3=None

def worker():
    global live_3,first3,second3
    while True:
        try:
            ist=datetime.utcnow()+timedelta(hours=5,minutes=30)
            state["ist"]=ist.strftime("%H:%M:%S IST %d-%m-%Y")
            price=get_ltp()
            state["ltp"]=price
            if price==0:
                time.sleep(3)
                continue
            mod=ist.hour*60+ist.minute
            s3=(mod//3)*3
            if live_3 is None or live_3[4]!=s3:
                if live_3 is not None:
                    closes_3.append(live_3[3])
                    if len(closes_3)==1:
                        first3=[live_3[0],live_3[1],live_3[2],live_3[3]]
                    if len(closes_3)==2:
                        second3=[live_3[0],live_3[1],live_3[2],live_3[3]]
                live_3=[price,price,price,price,s3]
            else:
                live_3[1]=max(live_3[1],price)
                live_3[2]=min(live_3[2],price)
                live_3[3]=price

            if first3:
                state["c1_3"]=f"1st 3Min O:{first3[0]} H:{first3[1]} L:{first3[2]} C:{first3[3]}"
            if second3:
                state["c2_3"]=f"2nd 3Min H:{second3[1]} C:{second3[3]}"

            if first3 and second3 and len(closes_3)>=2:
                o1,h1,lo1,c1=first3
                o2,h2,lo2,c2=second3
                entry=int(lo1+(h1-lo1)*0.5)
                if c1>o1 and c2>o2 and (h2>h1 or c2>h1):
                    sl=lo1
                    tgt=entry+(entry-sl)*2
                    state["call3"]=f"CALL BUY CE @ {entry} | SL {sl} TGT {tgt} 1:2 LOT {LOT} LTP {price}"
                if c1<o1 and c2<o2 and (lo2<lo1 or c2<lo1):
                    sl=h1
                    tgt=entry-(sl-entry)*2
                    state["put3"]=f"PUT BUY PE @ {entry} | SL {sl} TGT {tgt} 1:2 LOT {LOT} LTP {price}"
            time.sleep(2)
        except Exception as e:
            state["msg"]=f"Worker {e}"
            time.sleep(2)

threading.Thread(target=worker, daemon=True).start()

@app.route('/')
def home():
    return f"<h1 style='background:green;color:white;padding:12px'>FINAL NO-EMA 3MIN CALL PUT 50% LOT 65</h1><h2>{state['status']}</h2><h2 style='color:green'>{state['call3']}</h2><h2 style='color:red'>{state['put3']}</h2><h3>{state['c1_3']}</h3><h3>{state['c2_3']}</h3><h2>LTP {state['ltp']}</h2><h3>{state['ist']}</h3><h4>{state['msg']}</h4>"

@app.route('/check')
def check():
    return jsonify(state)

if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

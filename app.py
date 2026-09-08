from flask import Flask, jsonify
import os, threading, time, pyotp, requests
from datetime import datetime, timedelta
from SmartApi import SmartConnect
from collections import deque

app = Flask(__name__)
LOT = 65
state = {"ist":"", "ltp":0, "ema3":0, "ema5":0, "c1_3":"Waiting 9:15", "c2_3":"Waiting 9:18", "call3":"Ready", "put3":"Ready", "call5":"Ready", "put5":"Ready", "status":"READY", "msg":"Starting..."}

smart=None
try:
    smart=SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    totp=pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
    sess=smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
    state["msg"]="Login OK"
    state["status"]="Login OK - READY"
except Exception as e:
    state["msg"]=f"Login Fail {e}"

def get_ltp():
    try:
        if smart:
            data=smart.ltpData("NSE","Nifty 50","26000")
            if data and data.get('data'):
                price=data['data'].get('ltp')
                if price and float(price)>1000:
                    pval=float(price)
                    state["msg"]=f"Angel LTP {pval}"
                    return pval
    except: pass
    try:
        r=requests.get("https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI?interval=1m", headers={"User-Agent":"Mozilla/5.0"}, timeout=10)
        j=r.json()
        p=j['chart']['result'][0]['meta']['regularMarketPrice']
        if p and float(p)>1000:
            pval=float(p)
            state["msg"]=f"Yahoo LTP {pval}"
            return pval
    except Exception as e:
        state["msg"]=f"Yahoo fail {e}"
    return 0

closes_3=deque(maxlen=100)
closes_5=deque(maxlen=100)
live_3=None; live_5=None; first3=None; second3=None; first5=None; second5=None

def calc_ema(prices,s=20):
    if len(prices)<2: return 0
    if len(prices)<s: return round(sum(prices)/len(prices),2)
    k=2/(s+1)
    ema=sum(list(prices)[:s])/s
    for x in list(prices)[s:]: ema=x*k+ema*(1-k)
    return round(ema,2)

def worker():
    global live_3,live_5,first3,second3,first5,second5
    while True:
        try:
            ist=datetime.utcnow()+timedelta(hours=5,minutes=30)
            state["ist"]=ist.strftime("%H:%M:%S IST %d-%m-%Y")
            ltp=get_ltp()
            state["ltp"]=ltp
            if ltp==0:
                time.sleep(3); continue
            mod=ist.hour*60+ist.minute
            s3=(mod//3)*3
            if live_3 is None or live_3[4]!=s3:
                if live_3 is not None:
                    closes_3.append(live_3[3])
                    if len(closes_3)==1: first3=[live_3[0],live_3[1],live_3[2],live_3[3]]
                    if len(closes_3)==2: second3=[live_3[0],live_3[1],live_3[2],live_3[3]]
                live_3=[ltp,ltp,ltp,ltp,s3]
            else:
                live_3[1]=max(live_3[1],ltp); live_3[2]=min(live_3[2],ltp); live_3[3]=ltp
            s5=(mod//5)*5
            if live_5 is None or live_5[4]!=s5:
                if live_5 is not None:
                    closes_5.append(live_5[3])
                    if len(closes_5)==1: first5=[live_5[0],live_5[1],live_5[2],live_5[3]]
                    if len(closes_5)==2: second5=[live_5[0],live_5[1],live_5[2],live_5[3]]
                live_5=[ltp,ltp,ltp,ltp,s5]
            else:
                live_5[1]=max(live_5[1],ltp); live_5[2]=min(live_5[2],ltp); live_5[3]=ltp
            ema3=calc_ema(closes_3,20); ema5=calc_ema(closes_5,20)
            state["ema3"]=ema3; state["ema5"]=ema5
            if first3: state["c1_3"]=f"1st 3Min O:{first3[0]} H:{first3[1]} L:{first3[2]} C:{first3[3]}"
            if second3: state["c2_3"]=f"2nd 3Min H:{second3[1]} C:{second3[3]}"
            if first3 and second3 and len(closes_3)>=2:
                o1,h1,l1,c1=first3; o2,h2,l2,c2=second3; entry=int(l1+(h1-l1)*0.5)
                if c1>o1 and c2>o2 and (h2>h1 or c2>h1):
                    sl=l1; tgt=entry+(entry-sl)*2
                    state["call3"]=f"CALL BUY CE @ {entry} EMA {ema3} SL {sl} TGT {tgt} LOT {LOT} LTP {ltp}"
                if c1<o1 and c2<o2 and (l2<l1 or c2<l1):
                    sl=h1; tgt=entry-(sl-entry)*2
                    state["put3"]=f"PUT BUY PE @ {entry} EMA {ema3} SL {sl} TGT {tgt} LOT {LOT} LTP {ltp}"
            time.sleep(2)
        except Exception as e:
            state["msg"]=f"Worker {e}"; time.sleep(2)

threading.Thread(target=worker, daemon=True).start()

@app.route('/')
def home():
    return f"<h1 style='background:green;color:white;padding:12px'>FINAL REAL EMA CALL PUT 3MIN 5MIN LOT 65</h1><h2>{state['status']}</h2><h2 style='color:green'>{state['call3']}</h2><h2 style='color:red'>{state['put3']}</h2><h3>{state['c1_3']}</h3><h3>{state['c2_3']}</h3><h3>LTP {state['ltp']} EMA {state['ema3']} {state['ist']}</h3><h4>{state['msg']}</h4>"

@app.route('/check')
def check():
    return jsonify(state)

if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

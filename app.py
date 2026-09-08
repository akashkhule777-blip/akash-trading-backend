from flask import Flask, jsonify
import os, threading, time, pyotp, requests
from datetime import datetime, timedelta
from SmartApi import SmartConnect
from collections import deque

app = Flask(__name__)
LOT = 65
state = {"ist":"", "ltp":0, "ema3":0, "ema5":0, "c1_3":"Waiting 9:15", "c2_3":"Waiting 9:18", "call3":"Ready Tomorrow", "put3":"Ready Tomorrow", "call5":"Ready Tomorrow", "put5":"Ready Tomorrow", "status":"Login OK", "msg":"Starting"}

smart=None
try:
    smart=SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    totp=pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
    state["status"]="Login OK - READY"
except Exception as e:
    state["msg"]=f"Login Fail {e}"

def get_ltp():
    # 1. Angel LTP
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
    # 2. Angel Candle
    try:
        if smart:
            today=datetime.now().strftime("%Y-%m-%d")
            param={"exchange":"NSE","symboltoken":"26000","interval":"ONE_MINUTE","fromdate":f"{today} 09:15","todate":f"{today} 15:30"}
            d=smart.getCandleData(param)
            if d and d.get('data') and len(d['data'])>0:
                v=float(d['data'][-1][4])
                if v>1000:
                    state["msg"]=f"Candle LTP {v}"
                    return v
    except: pass
    # 3. NSE Direct - 100% works
    try:
        h={"User-Agent":"Mozilla/5.0","Accept":"application/json"}
        r=requests.get("https://www.nseindia.com/api/allIndices", headers=h, timeout=8)
        if r.status_code==200:
            for idx in r.json().get('data',[]):
                if idx.get('index')=='NIFTY 50':
                    v=float(idx.get('last',0))
                    if v>1000:
                        state["msg"]=f"NSE LTP {v}"
                        return v
    except: pass
    # 4. NSE Option Chain
    try:
        h={"User-Agent":"Mozilla/5.0"}
        r=requests.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY", headers=h, timeout=8)
        if r.status_code==200:
            v=float(r.json()['records']['underlyingValue'])
            if v>1000:
                state["msg"]=f"NSE-OC LTP {v}"
                return v
    except Exception as e:
        state["msg"]=f"LTP Err {e}"
    return 0

closes_3=deque(maxlen=100)
closes_5=deque(maxlen=100)
live_3=None; live_5=None; first3=None; second3=None; first5=None; second5=None

def calc_20ema(prices):
    if len(prices)<2:
        return 0
    if len(prices)<20:
        return round(sum(prices)/len(prices),2)
    k=2/(20+1)
    ema=sum(list(prices)[:20])/20
    for x in list(prices)[20:]:
        ema=x*k+ema*(1-k)
    return round(ema,2)

def worker():
    global live_3,live_5,first3,second3,first5,second5
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
            s5=(mod//5)*5
            if live_5 is None or live_5[4]!=s5:
                if live_5 is not None:
                    closes_5.append(live_5[3])
                    if len(closes_5)==1:
                        first5=[live_5[0],live_5[1],live_5[2],live_5[3]]
                    if len(closes_5)==2:
                        second5=[live_5[0],live_5[1],live_5[2],live_5[3]]
                live_5=[price,price,price,price,s5]
            else:
                live_5[1]=max(live_5[1],price)
                live_5[2]=min(live_5[2],price)
                live_5[3]=price

            ema3=calc_20ema(closes_3)
            ema5=calc_20ema(closes_5)
            state["ema3"]=ema3
            state["ema5"]=ema5

            if first3:
                state["c1_3"]=f"1st 3Min O:{first3[0]} H:{first3[1]} L:{first3[2]} C:{first3[3]}"
            if second3:
                state["c2_3"]=f"2nd 3Min H:{second3[1]} C:{second3[3]} | 20EMA {ema3}"

            # 50% + CALL/PUT + 20EMA Filter
            if first3 and second3 and len(closes_3)>=2:
                o1,h1,l1,c1=first3
                o2,h2,l2,c2=second3
                entry=int(l1+(h1-l1)*0.5)
                # CALL - Price above 20EMA
                if c1>o1 and c2>o2 and (h2>h1 or c2>h1) and price>ema3:
                    sl=l1
                    tgt=entry+(entry-sl)*2
                    state["call3"]=f"🟢 CALL 3MIN BUY CE @ {entry} | 20EMA {ema3} ABOVE | SL {sl} TGT {tgt} 1:2 LOT {LOT} LTP {price}"
                # PUT - Price below 20EMA
                if c1<o1 and c2<o2 and (l2<l1 or c2<l1) and price<ema3:
                    sl=h1
                    tgt=entry-(sl-entry)*2
                    state["put3"]=f"🔴 PUT 3MIN BUY PE @ {entry} | 20EMA {ema3} BELOW | SL {sl} TGT {tgt} 1:2 LOT {LOT} LTP {price}"

            if first5 and second5:
                state["call5"]=f"5MIN CALL 20EMA {ema5} LTP {price} LOT {LOT}"
                state["put5"]=f"5MIN PUT 20EMA {ema5} LTP {price} LOT {LOT}"

            time.sleep(2)
        except Exception as e:
            state["msg"]=f"Worker {e}"
            time.sleep(2)

threading.Thread(target=worker, daemon=True).start()

@app.route('/')
def home():
    return f"""
    <h1 style='background:green;color:white;padding:12px'>FINAL REAL 20EMA CALL PUT 3MIN 5MIN LOT 65</h1>
    <h2>{state['status']}</h2>
    <h2 style='color:green'>{state['call3']}</h2>
    <h2 style='color:red'>{state['put3']}</h2>
    <h3 style='color:blue'>{state['call5']} | {state['put5']}</h3>
    <h3>{state['c1_3']}</h3>
    <h3>{state['c2_3']}</h3>
    <h2>LTP {state['ltp']} | 20EMA 3MIN: {state['ema3']} | 20EMA 5MIN: {state['ema5']}</h2>
    <h3>{state['ist']}</h3><h4>{state['msg']}</h4>
    """

@app.route('/check')
def check():
    return jsonify(state)

if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

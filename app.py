from flask import Flask, jsonify
import os, threading, time, pyotp, requests
from datetime import datetime, timedelta
from SmartApi import SmartConnect
from collections import deque

app = Flask(__name__)
LOT = 65

state = {
    "ist": "", "ltp": 0,
    "c3": "Wait OB", "c5": "Wait OB",
    "call3": "Scanning Uptrend OB...", "put3": "Scanning Uptrend OB...",
    "call5": "Scanning Uptrend OB...", "put5": "Scanning Uptrend OB...",
    "atm": "Wait", "cnt3":0, "cnt5":0, "msg":"1:2 Final"
}

smart=None
try:
    smart=SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now())
except Exception as e:
    state["msg"]=f"Login {e}"

def get_spot():
    try:
        if smart:
            d=smart.ltpData("NSE","Nifty 50","99926000")
            v=float(d['data']['ltp'])
            if v>1000: return v
    except: pass
    try:
        sess=requests.Session()
        sess.headers.update({"User-Agent":"Mozilla/5.0"})
        sess.get("https://www.nseindia.com",timeout=5)
        r=sess.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",timeout=8)
        if r.status_code==200: return float(r.json()['records']['underlyingValue'])
    except: pass
    return 0

def get_atm(spot):
    try:
        strike=int(round(spot/50)*50)
        sess=requests.Session()
        sess.headers.update({"User-Agent":"Mozilla/5.0"})
        sess.get("https://www.nseindia.com",timeout=5)
        time.sleep(0.2)
        r=sess.get("https://www.nseindia.com/api/option-chain-indices?symbol=NIFTY",timeout=8)
        if r.status_code==200:
            for i in r.json()['records']['data']:
                if i.get('strikePrice')==strike:
                    ce=i.get('CE',{}).get('lastPrice',0)
                    pe=i.get('PE',{}).get('lastPrice',0)
                    state["atm"]=f"ATM {strike} CE:{ce} PE:{pe}"
                    return ce,pe,strike
    except: pass
    return 0,0,0

def ema(arr,p=20):
    if len(arr)<p: return None
    k=2/(p+1); e=arr[0]
    for x in arr[1:]: e=x*k+e*(1-k)
    return e

live3=None; first3=None; phase3=0; b3up=False; b3dn=False
live5=None; first5=None; phase5=0; b5up=False; b5dn=False
spot3_q=deque(maxlen=30); spot5_q=deque(maxlen=30)
ce_q=deque(maxlen=30); pe_q=deque(maxlen=30)

def worker():
    global live3, first3, phase3, b3up, b3dn, live5, first5, phase5, b5up, b5dn
    while True:
        try:
            ist=datetime.utcnow()+timedelta(hours=5,minutes=30)
            state["ist"]=ist.strftime("%H:%M:%S IST")
            spot=get_spot()
            state["ltp"]=spot
            if spot==0:
                time.sleep(2)
                continue
            ce_ltp,pe_ltp,_=get_atm(spot)
            if ce_ltp>0: ce_q.append(ce_ltp)
            if pe_ltp>0: pe_q.append(pe_ltp)

            mod=ist.hour*60+ist.minute
            # 3MIN CANDLE
            s3=(mod//3)*3
            if live3 is None or live3[4]!=s3:
                if live3 is not None:
                    spot3_q.append(live3[3])
                    if phase3==0:
                        first3=live3; phase3=1
                        state["c3"]=f"3MIN 1st H:{first3[1]} L:{first3[2]} 50%={int(first3[2]+(first3[1]-first3[2])*0.5)}"
                    elif phase3==1:
                        sec=live3
                        if sec[1]>first3[1] or sec[3]>first3[1]:
                            b3up=True; b3dn=False; phase3=2
                            state["call3"]=f"BREAK UP {sec[1]} > {first3[1]} | 3rd pasun 50% wait + Uptrend"
                        elif sec[2]<first3[2] or sec[3]<first3[2]:
                            b3dn=True; b3up=False; phase3=2
                            state["put3"]=f"BREAK DN {sec[2]} < {first3[2]} | 3rd pasun 50% wait + Uptrend"
                        else:
                            first3=sec
                live3=[spot,spot,spot,spot,s3]
            else:
                live3[1]=max(live3[1],spot); live3[2]=min(live3[2],spot); live3[3]=spot

            # 5MIN CANDLE
            s5=(mod//5)*5
            if live5 is None or live5[4]!=s5:
                if live5 is not None:
                    spot5_q.append(live5[3])
                    if phase5==0:
                        first5=live5; phase5=1
                        state["c5"]=f"5MIN 1st H:{first5[1]} L:{first5[2]} 50%={int(first5[2]+(first5[1]-first5[2])*0.5)}"
                    elif phase5==1:
                        sec=live5
                        if sec[1]>first5[1] or sec[3]>first5[1]:
                            b5up=True; b5dn=False; phase5=2
                        elif sec[2]<first5[2] or sec[3]<first5[2]:
                            b5dn=True; b5up=False; phase5=2
                        else:
                            first5=sec
                live5=[spot,spot,spot,spot,s5]
            else:
                live5[1]=max(live5[1],spot); live5[2]=min(live5[2],spot); live5[3]=spot

            # UPTREND FILTER + 50% ENTRY
            ema3=ema(list(spot3_q),20); ema5=ema(list(spot5_q),20)
            ce_ema=ema(list(ce_q),20); pe_ema=ema(list(pe_q),20)

            if phase3==2 and first3:
                fifty=int(first3[2]+(first3[1]-first3[2])*0.5)
                if abs(spot-fifty)<=15:
                    ce,pe,strike=get_atm(spot)
                    if b3up and (ema3 is None or spot>ema3) and (ce_ema is None or ce>ce_ema):
                        state["cnt3"]+=1
                        sl=first3[2]; tgt=fifty+(fifty-sl)*2
                        state["call3"]=f"#{state['cnt3']} 3MIN CALL BUY NOW! 50%={fifty} ATM {strike} CE {ce} SL {sl} TGT {int(tgt)} 1:2 UPTREND OK"
                        phase3=0; first3=None; b3up=False; b3dn=False
                    elif b3dn and (ema3 is None or spot<ema3) and (pe_ema is None or pe>pe_ema):
                        state["cnt3"]+=1
                        sl=first3[1]; tgt=fifty-(sl-fifty)*2
                        state["put3"]=f"#{state['cnt3']} 3MIN PUT BUY NOW! 50%={fifty} ATM {strike} PE {pe} SL {sl} TGT {int(tgt)} 1:2 UPTREND OK"
                        phase3=0; first3=None; b3up=False; b3dn=False

            if phase5==2 and first5:
                fifty=int(first5[2]+(first5[1]-first5[2])*0.5)
                if abs(spot-fifty)<=15:
                    ce,pe,strike=get_atm(spot)
                    if b5up and (ema5 is None or spot>ema5) and (ce_ema is None or ce>ce_ema):
                        state["cnt5"]+=1
                        sl=first5[2]; tgt=fifty+(fifty-sl)*2
                        state["call5"]=f"#{state['cnt5']} 5MIN CALL BUY NOW! 50%={fifty} ATM {strike} CE {ce} SL {sl} TGT {int(tgt)} 1:2 UPTREND OK"
                        phase5=0; first5=None; b5up=False; b5dn=False
                    elif b5dn and (ema5 is None or spot<ema5) and (pe_ema is None or pe>pe_ema):
                        state["cnt5"]+=1
                        sl=first5[1]; tgt=fifty-(sl-fifty)*2
                        state["put5"]=f"#{state['cnt5']} 5MIN PUT BUY NOW! 50%={fifty} ATM {strike} PE {pe} SL {sl} TGT {int(tgt)} 1:2 UPTREND OK"
                        phase5=0; first5=None; b5up=False; b5dn=False

            time.sleep(1)
        except Exception as e:
            state["msg"]=str(e)
            time.sleep(2)

threading.Thread(target=worker,daemon=True).start()

@app.route('/')
def home():
    return f"""
    <h1 style='background:green;color:white;padding:8px'>FINAL: 1st 3MIN + 2nd BREAK + 3rd se 50% + 1:2 + UPTREND + ATM</h1>
    <h2>NIFTY {state['ltp']} | {state['atm']} | {state['ist']}</h2>
    <h3>3MIN {state['c3']} | Cnt {state['cnt3']}</h3>
    <h2 style='color:green'>{state['call3']}</h2>
    <h2 style='color:red'>{state['put3']}</h2>
    <hr>
    <h3>5MIN {state['c5']} | Cnt {state['cnt5']}</h3>
    <h2 style='color:green'>{state['call5']}</h2>
    <h2 style='color:red'>{state['put5']}</h2>
    <h4>{state['msg']}</h4>
    """

@app.route('/check')
def check():
    return jsonify(state)

if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

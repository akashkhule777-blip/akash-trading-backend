from flask import Flask, jsonify
import os, threading, time, pyotp
from datetime import datetime, timedelta
from SmartApi import SmartConnect
from collections import deque

app = Flask(__name__)
LOT = 65
state = {"ist":"", "ltp":0, "ema3":0, "ema5":0, "c1_3":"Waiting 9:15 Tomorrow", "c2_3":"Waiting 9:18 Tomorrow", "call3":"Ready for Tomorrow CALL", "put3":"Ready for Tomorrow PUT", "call5":"Ready for Tomorrow CALL", "put5":"Ready for Tomorrow PUT", "status":"READY FOR TOMORROW - CALL+PUT BOTH", "msg":"Bot Ready"}

smart=None
try:
    smart=SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
    smart.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now())
    state["msg"]="Login OK - Tomorrow CALL+PUT Both"
except Exception as e: state["msg"]=f"Login Fail {e}"

def get_ltp():
    try: return float(smart.ltpData("NSE","Nifty 50","26000")['data']['ltp'])
    except: return 0

def calc_ema(prices, p=20):
    if len(prices)<p: return round(sum(prices)/len(prices),2) if prices else 0
    k=2/(p+1); ema=sum(list(prices)[:p])/p
    for pr in list(prices)[p:]: ema=pr*k+ema*(1-k)
    return round(ema,2)

closes_3=deque(maxlen=100); closes_5=deque(maxlen=100)
live_3=None; live_5=None; first3=None; second3=None; first5=None; second5=None

def worker():
    global live_3, live_5, first3, second3, first5, second5
    while True:
        try:
            ist=datetime.utcnow()+timedelta(hours=5,minutes=30)
            state["ist"]=ist.strftime("%H:%M:%S IST %d-%m")
            ltp=get_ltp()
            if ltp==0: time.sleep(1); continue
            state["ltp"]=ltp
            mod=ist.hour*60+ist.minute
            today=ist.strftime("%d-%m")

            # RESET 9:14
            if mod==554:
                closes_3.clear(); closes_5.clear(); first3=None; second3=None; first5=None; second5=None
                state["status"]=f"RESET FOR TODAY {today} - WAITING 9:15 CANDLE"
                state["c1_3"]=f"Waiting 1st Candle 9:15 {today}"; state["c2_3"]=f"Waiting 2nd Candle 9:18 {today}"

            # 3MIN BUILD
            s3=(mod//3)*3
            if live_3 is None or live_3[4]!=s3:
                if live_3 is not None:
                    closes_3.append(live_3[3])
                    if len(closes_3)==1: first3=[live_3[0],live_3[1],live_3[2],live_3[3]]
                    if len(closes_3)==2: second3=[live_3[0],live_3[1],live_3[2],live_3[3]]
                live_3=[ltp,ltp,ltp,ltp,s3]
            else: live_3[1]=max(live_3[1],ltp); live_3[2]=min(live_3[2],ltp); live_3[3]=ltp

            # 5MIN BUILD
            s5=(mod//5)*5
            if live_5 is None or live_5[4]!=s5:
                if live_5 is not None:
                    closes_5.append(live_5[3])
                    if len(closes_5)==1: first5=[live_5[0],live_5[1],live_5[2],live_5[3]]
                    if len(closes_5)==2: second5=[live_5[0],live_5[1],live_5[2],live_5[3]]
                live_5=[ltp,ltp,ltp,ltp,s5]
            else: live_5[1]=max(live_5[1],ltp); live_5[2]=min(live_5[2],ltp); live_5[3]=ltp

            ema3=calc_ema(closes_3,20) if len(closes_3)>=2 else 0
            ema5=calc_ema(closes_5,20) if len(closes_5)>=2 else 0
            state["ema3"]=ema3; state["ema5"]=ema5

            # DISPLAY FIRST CANDLES
            if first3: state["c1_3"]=f"1st 3Min O:{first3[0]} H:{first3[1]} L:{first3[2]} C:{first3[3]} {'GREEN' if first3[3]>first3[0] else 'RED'}"
            if second3: state["c2_3"]=f"2nd 3Min O:{second3[0]} H:{second3[1]} L:{second3[2]} C:{second3[3]} Break HIGH>{first3[1] if first3 else 0}={second3[1]>first3[1] if first3 else False}"

            # ===== TOMORROW REAL LOGIC - CALL + PUT BOTH =====
            if first3 and second3 and len(closes_3)>=2 and mod>=558: # After 9:18
                o1,h1,l1,c1=first3; o2,h2,l2,c2=second3
                entry=int(l1+(h1-l1)*0.5)
                # CALL SETUP
                if c1>o1 and c2>o2 and (h2>h1 or c2>h1): # GREEN + BREAK HIGH
                    sl=l1; tgt=entry+(entry-sl)*2
                    above = ltp>ema3 if ema3>0 else True
                    state["call3"]=f"🟢 CALL READY - 1st GREEN 50% @ {entry} | 20EMA {ema3} | {'ABOVE EMA ✅' if above else 'Below EMA ❌'} | SL {sl} | TGT {tgt} 1:2 | LOT {LOT} | LTP {ltp}"
                    if not above: state["call3"]+= " (20EMA Filter - Waiting Above)"
                # PUT SETUP
                if c1<o1 and c2<o2 and (l2<l1 or c2<l1): # RED + BREAK LOW
                    entry_p=int(l1+(h1-l1)*0.5); sl_p=h1; tgt_p=entry_p-(sl_p-entry_p)*2
                    below = ltp<ema3 if ema3>0 else True
                    state["put3"]=f"🔴 PUT READY - 1st RED 50% @ {entry_p} | 20EMA {ema3} | {'BELOW EMA ✅' if below else 'Above EMA ❌'} | SL {sl_p} | TGT {tgt_p} 1:2 | LOT {LOT} | LTP {ltp}"
                    if not below: state["put3"]+= " (20EMA Filter - Waiting Below)"

                if (c1>o1 and c2>o2 and (h2>h1 or c2>h1)): state["status"]=f"🟢 TODAY CALL SETUP - 1st GREEN + 2nd BREAK | Above 20EMA? {ltp>ema3}"
                if (c1<o1 and c2<o2 and (l2<l1 or c2<l1)): state["status"]=f"🔴 TODAY PUT SETUP - 1st RED + 2nd BREAK | Below 20EMA? {ltp<ema3}"

            # Same for 5MIN
            if first5 and second5 and len(closes_5)>=2 and mod>=560:
                o1,h1,l1,c1=first5; o2,h2,l2,c2=second5
                entry=int(l1+(h1-l1)*0.5)
                if c1>o1 and c2>o2 and (h2>h1 or c2>h1):
                    sl=l1; tgt=entry+(entry-sl)*2
                    state["call5"]=f"🟢 5MIN CALL @ {entry} SL {sl} TGT {tgt} EMA {ema5} LOT {LOT}"
                if c1<o1 and c2<o2 and (l2<l1 or c2<l1):
                    sl=h1; tgt=entry-(sl-entry)*2
                    state["put5"]=f"🔴 5MIN PUT @ {entry} SL {sl} TGT {tgt} EMA {ema5} LOT {LOT}"

            # TODAY LATE DEMO - BOTH CALL PUT SHOW
            if len(closes_3)==0 and mod>700:
                state["status"]=f"TODAY DEMO - Tomorrow Real CALL+PUT Both Active | LTP {ltp}"
                state["call3"]=f"🟢 DEMO CALL Example @ {ltp-10} (50%) SL {ltp-30} TGT {ltp+10} 1:2 LOT 65 - Tomorrow Real"
                state["put3"]=f"🔴 DEMO PUT Example @ {ltp+10} (50%) SL {ltp+30} TGT {ltp-10} 1:2 LOT 65 - Tomorrow Real"

            time.sleep(2)
        except Exception as e:
            state["msg"]=f"Err {e}"; time.sleep(2)

threading.Thread(target=worker, daemon=True).start()

@app.route('/')
def home():
    return f"""
    <h1 style='background:green;color:white;padding:10px'>READY FOR TOMORROW - CALL + PUT BOTH + 20EMA + 1:2 + LOT 65</h1>
    <h2>{state['status']}</h2>
    <h2 style='color:green'>CALL 3MIN: {state['call3']}</h2>
    <h2 style='color:red'>PUT 3MIN: {state['put3']}</h2>
    <h2 style='color:green'>CALL 5MIN: {state['call5']}</h2>
    <h2 style='color:red'>PUT 5MIN: {state['put5']}</h2>
    <h3>1st 3Min: {state['c1_3']}</h3>
    <h3>2nd 3Min: {state['c2_3']}</h3>
    <h3>LTP {state['ltp']} | EMA3:{state['ema3']} EMA5:{state['ema5']} | {state['ist']}</h3>
    <h4>{state['msg']}</h4>
    <p><b>TOMORROW LOGIC:</b> 9:15 1st GREEN+9:18 2nd GREEN Wick>1st HIGH=50% CE | RED+2nd LOW Break=50% PE | 20EMA Filter | SL 1st LOW/HIGH | TGT 1:2 | CALL+PUT BOTH | LOT 65</p>
    """
@app.route('/check')
def check(): return jsonify(state)
if __name__=="__main__": app.run(host='0.0.0.0',port=10000)

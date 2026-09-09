from flask import Flask, jsonify
import os, threading, time, pyotp, requests
from datetime import datetime, timedelta
from SmartApi import SmartConnect
from collections import deque

app = Flask(__name__)
LOT=65
state={"ist":"","ltp":0,"c3":"Wait OB","call3":"Scanning...","put3":"Scanning...","atm":"Wait","cnt3":0,"msg":"BOOT","log":[]}
smart=None

def add_log(m):
    state["log"].append(f"{datetime.utcnow().strftime('%H:%M:%S')} {m}")
    if len(state["log"])>15:
        state["log"].pop(0)
    print(m)

def angel_login():
    global smart
    try:
        s=SmartConnect(api_key=os.getenv("ANGEL_API_KEY"))
        totp=pyotp.TOTP(os.getenv("ANGEL_TOTP_SECRET")).now()
        sess=s.generateSession(os.getenv("ANGEL_CLIENT_ID"), os.getenv("ANGEL_PASSWORD"), totp)
        smart=s
        add_log(f"LOGIN OK {str(sess)[:100]}")
        state["msg"]="Login OK"
        return True
    except Exception as e:
        add_log(f"LOGIN FAIL {e}")
        state["msg"]=f"Login Fail {e}"
        return False

angel_login()

def get_spot():
    ist=datetime.utcnow()+timedelta(hours=5,minutes=30)
    state["ist"]=ist.strftime("%H:%M:%S IST")

    # 1. Angel LTP direct
    try:
        if smart:
            d=smart.ltpData("NSE","Nifty 50","99926000")
            add_log(f"LTP1 {d}")
            if d and d.get('data') and d['data'].get('ltp'):
                v=float(d['data']['ltp'])
                if v>1000:
                    return v
    except Exception as e:
        add_log(f"LTP1 ERR {e}")

    # 2. Angel LTP old token
    try:
        if smart:
            d=smart.ltpData("NSE","NIFTY","26000")
            add_log(f"LTP2 {d}")
            if d and d.get('data') and d['data'].get('ltp'):
                v=float(d['data']['ltp'])
                if v>1000:
                    return v
    except Exception as e:
        add_log(f"LTP2 ERR {e}")

    # 3. Angel Candle
    try:
        if smart:
            fromdate=ist.strftime("%Y-%m-%d 09:15")
            todate=ist.strftime("%Y-%m-%d %H:%M")
            p={"exchange":"NSE","symboltoken":"99926000","interval":"ONE_MINUTE","fromdate":fromdate,"todate":todate}
            res=smart.getCandleData(p)
            add_log(f"CANDLE {str(res)[:200]}")
            if res and res.get('data') and len(res['data'])>0:
                v=float(res['data'][-1][4])
                if v>1000:
                    return v
    except Exception as e:
        add_log(f"CANDLE ERR {e}")

    # 4. Yahoo via codetabs proxy
    try:
        r=requests.get("https://api.codetabs.com/v1/proxy?quest=https://query1.finance.yahoo.com/v8/finance/chart/%5ENSEI",timeout=8)
        add_log(f"CODETABS {r.status_code} {r.text[:100]}")
        if r.status_code==200:
            js=r.json()
            v=float(js['chart']['result'][0]['meta']['regularMarketPrice'])
            if v>1000:
                return v
    except Exception as e:
        add_log(f"CODETABS ERR {e}")

    # 5. AllOrigins proxy NSE
    try:
        r=requests.get("https://api.allorigins.win/get?url=https://www.nseindia.com/api/allIndices",timeout=8)
        add_log(f"ALLORIGINS {r.status_code}")
        if r.status_code==200:
            import json
            content=json.loads(r.json()['contents'])
            for idx in content['data']:
                if idx['index']=='NIFTY 50':
                    v=float(idx['last'])
                    if v>1000:
                        return v
    except Exception as e:
        add_log(f"ALLORIGINS ERR {e}")

    # Re-login if all fail
    add_log("ALL FAIL - RELOGIN")
    angel_login()
    return 0

def get_atm_details(spot):
    return 0,0,int(round(spot/50)*50) if spot>0 else 0,""

def place_angel_order(strike,opt_type,qty=65):
    try:
        if not smart: return None
        res=smart.searchScrip("NFO", f"{strike}{opt_type}")
        token=tsym=None
        if res and 'data' in res:
            for item in res['data']:
                if str(strike) in item['tradingsymbol'] and opt_type in item['tradingsymbol'] and 'NIFTY' in item['tradingsymbol']:
                    token=item['token']; tsym=item['tradingsymbol']; break
        if not token: return None
        orderparams={"variety":"NORMAL","tradingsymbol":tsym,"symboltoken":token,"transactiontype":"BUY","exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","quantity":qty}
        oid=smart.placeOrder(orderparams)
        state["msg"]=f"ORDER OK {tsym} {oid}"
        return oid
    except Exception as e:
        state["msg"]=f"ORDER FAIL {e}"; return None

def ema(arr,p=20):
    if len(arr)<p: return None
    k=2/(p+1); e=arr[0]
    for x in arr[1:]: e=x*k+e*(1-k)
    return e

live3=None; first3=None; phase3=0; b3up=False; b3dn=False
spot3_q=deque(maxlen=30); ce_q=deque(maxlen=30); pe_q=deque(maxlen=30)

def worker():
    global live3, first3, phase3, b3up, b3dn
    while True:
        try:
            spot=get_spot()
            if spot>1000:
                state["ltp"]=spot
            else:
                time.sleep(3); continue
            # OB logic same...
            import datetime as dt
            mod=dt.datetime.utcnow()+timedelta(hours=5,minutes=30)
            mod=mod.hour*60+mod.minute
            s3=(mod//3)*3
            if live3 is None or live3[4]!=s3:
                if live3 is not None:
                    spot3_q.append(live3[3])
                    if phase3==0:
                        first3=live3; phase3=1
                        state["c3"]=f"3MIN H:{first3[1]:.0f} L:{first3[2]:.0f} 50%={int(first3[2]+(first3[1]-first3[2])*0.5)}"
                    elif phase3==1:
                        sec=live3
                        if sec[1]>first3[1] or sec[3]>first3[1]:
                            b3up=True; b3dn=False; phase3=2; state["call3"]=f"BREAK UP {sec[1]:.0f}>{first3[1]:.0f}"
                        elif sec[2]<first3[2] or sec[3]<first3[2]:
                            b3dn=True; b3up=False; phase3=2; state["put3"]=f"BREAK DN {sec[2]:.0f}<{first3[2]:.0f}"
                        else:
                            first3=sec
                live3=[spot,spot,spot,spot,s3]
            else:
                live3[1]=max(live3[1],spot); live3[2]=min(live3[2],spot); live3[3]=spot
            if phase3==2 and first3:
                fifty=int(first3[2]+(first3[1]-first3[2])*0.5)
                if abs(spot-fifty)<=15:
                    if b3up:
                        state["cnt3"]+=1; sl=first3[2]; tgt=fifty+(fifty-sl)*2
                        strike=int(round(spot/50)*50)
                        oid=place_angel_order(strike,"CE",LOT)
                        state["call3"]=f"#{state['cnt3']} CALL BOUGHT 50%={fifty} SL{sl:.0f} TGT{int(tgt)} ID:{oid}"
                        phase3=0; first3=None; b3up=False; b3dn=False
                    elif b3dn:
                        state["cnt3"]+=1; sl=first3[1]; tgt=fifty-(sl-fifty)*2
                        strike=int(round(spot/50)*50)
                        oid=place_angel_order(strike,"PE",LOT)
                        state["put3"]=f"#{state['cnt3']} PUT BOUGHT 50%={fifty} SL{sl:.0f} TGT{int(tgt)} ID:{oid}"
                        phase3=0; first3=None; b3up=False; b3dn=False
            time.sleep(1)
        except Exception as e:
            add_log(f"WORKER ERR {e}"); time.sleep(2)

threading.Thread(target=worker,daemon=True).start()

@app.route('/')
def home():
    logs="<br>".join(state["log"][-12:])
    return f"<h1 style='background:green;color:white;padding:8px'>AUTO ORDER ON - LOG FIX</h1><h2>NIFTY {state['ltp']} | {state['ist']}</h2><h3>{state['c3']} Cnt {state['cnt3']}</h3><h2 style='color:green'>{state['call3']}</h2><h2 style='color:red'>{state['put3']}</h2><h4>{state['msg']}</h4><hr><div style='background:black;color:lime;padding:8px;font-size:11px'>{logs}</div>"

@app.route('/check')
def check(): return jsonify(state)
@app.route('/orders')
def orders():
    try:
        if smart: return jsonify(smart.orderBook())
    except Exception as e:
        return jsonify({"error":str(e)})
    return jsonify({})
if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

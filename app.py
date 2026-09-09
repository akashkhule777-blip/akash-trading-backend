from flask import Flask, jsonify
import os, threading, time, pyotp, requests
from datetime import datetime, timedelta
from SmartApi import SmartConnect

app = Flask(__name__)
state={"ist":"","ltp":0,"c3":"Wait OB","call3":"Scanning NSE...","put3":"Scanning NSE...","atm":"Wait","cnt3":0,"msg":"BOOT","log":[]}

api_key=os.getenv("ANGEL_API_KEY")
client_id=os.getenv("ANGEL_CLIENT_ID")
pwd=os.getenv("ANGEL_PASSWORD")
totp_secret=os.getenv("ANGEL_TOTP_SECRET")
smart=None

def add_log(m):
    ts=datetime.utcnow().strftime("%H:%M:%S")
    state["log"].append(f"{ts} {m}")
    if len(state["log"])>25:
        state["log"].pop(0)
    print(m)

def angel_login():
    global smart
    try:
        s=SmartConnect(api_key=api_key)
        totp=pyotp.TOTP(totp_secret).now()
        data=s.generateSession(client_id, pwd, totp)
        smart=s
        add_log("LOGIN OK - ORDER READY")
        state["msg"]="Login OK NSE LTP ON"
        return True
    except Exception as e:
        add_log(f"LOGIN FAIL {e}")
        return False

angel_login()

def get_nse_ltp():
    ist=datetime.utcnow()+timedelta(hours=5,minutes=30)
    state["ist"]=ist.strftime("%H:%M:%S IST")
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
    # 1. NSE allIndices - MOST RELIABLE
    try:
        add_log("TRY NSE ALL INDICES")
        # First get cookie from NSE
        s = requests.Session()
        s.get("https://www.nseindia.com", headers=headers, timeout=5)
        r = s.get("https://www.nseindia.com/api/allIndices", headers=headers, timeout=5)
        add_log(f"NSE ALL {r.status_code} len {len(r.text)}")
        if r.status_code==200:
            js=r.json()
            for item in js.get('data',[]):
                if item.get('index')=='NIFTY 50':
                    v=float(item.get('last',0))
                    if v>1000:
                        add_log(f"NSE OK {v}")
                        return v
    except Exception as e:
        add_log(f"NSE ALL ERR {e}")

    # 2. NSE 50 via marketStatus
    try:
        add_log("TRY NSE MARKETSTATUS")
        s = requests.Session()
        s.get("https://www.nseindia.com", headers=headers, timeout=5)
        r = s.get("https://www.nseindia.com/api/marketStatus", headers=headers, timeout=5)
        add_log(f"NSE STATUS {r.status_code}")
        if r.status_code==200:
            js=r.json()
            for m in js.get('marketState',[]):
                for idx in m.get('marketStatus',[]):
                    # search
                    pass
    except Exception as e:
        add_log(f"NSE STATUS ERR {e}")

    # 3. NiftyTrader free API - very light
    try:
        add_log("TRY NIFTYTRADER")
        r = requests.get("https://api.niftytrader.in/api/FinNiftyNiftyBankNiftyIncludesNifty50AndIndices", headers=headers, timeout=5)
        add_log(f"NIFTYTRADER {r.status_code}")
        if r.status_code==200:
            js=r.json()
            # parse
    except Exception as e:
        add_log(f"NIFTYTRADER ERR {e}")

    # 4. Simple Google search page - no allorigins
    try:
        add_log("TRY GOOGLE DIRECT")
        r = requests.get("https://www.google.com/finance/quote/NIFTY:INDEXNSE", headers=headers, timeout=5)
        add_log(f"GOOGLE {r.status_code} len {len(r.text)}")
        if r.status_code==200:
            import re
            m=re.search(r'YMlKec fxKbKc">([^<]+)', r.text)
            if m:
                txt=m.group(1).replace('₹','').replace(',','').strip()
                v=float(txt)
                if v>1000:
                    add_log(f"GOOGLE OK {v}")
                    return v
    except Exception as e:
        add_log(f"GOOGLE ERR {e}")

    return 0

def place_order(strike,opt_type):
    try:
        if not smart: return None
        res=smart.searchScrip("NFO", f"{strike}{opt_type}")
        token=tsym=None
        if res and 'data' in res:
            for item in res['data']:
                if str(strike) in item['tradingsymbol'] and opt_type in item['tradingsymbol']:
                    token=item['token']; tsym=item['tradingsymbol']; break
        if not token: return None
        orderparams={"variety":"NORMAL","tradingsymbol":tsym,"symboltoken":token,"transactiontype":"BUY","exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","quantity":65}
        oid=smart.placeOrder(orderparams)
        state["msg"]=f"ORDER OK {tsym} {oid}"
        add_log(f"ORDER {tsym} {oid}")
        return oid
    except Exception as e:
        add_log(f"ORDER ERR {e}"); return None

live3=None; first3=None; phase3=0; b3up=False; b3dn=False

def worker():
    global live3, first3, phase3, b3up, b3dn
    fails=0
    while True:
        try:
            spot=get_nse_ltp()
            if spot>1000:
                state["ltp"]=spot
                fails=0
            else:
                fails+=1
                add_log(f"SPOT 0 fail {fails}")
                if fails>4:
                    angel_login()
                    fails=0
                time.sleep(3); continue

            mod=datetime.utcnow()+timedelta(hours=5,minutes=30)
            mod=mod.hour*60+mod.minute
            s3=(mod//3)*3
            if live3 is None or live3[4]!=s3:
                if live3 is not None:
                    if phase3==0:
                        first3=live3; phase3=1
                        state["c3"]=f"3MIN H:{first3[1]:.0f} L:{first3[2]:.0f} 50%={int(first3[2]+(first3[1]-first3[2])*0.5)}"
                        add_log(state["c3"])
                    elif phase3==1:
                        sec=live3
                        if sec[1]>first3[1]:
                            b3up=True; b3dn=False; phase3=2; state["call3"]=f"BREAK UP {sec[1]:.0f}>{first3[1]:.0f}"
                            add_log(state["call3"])
                        elif sec[2]<first3[2]:
                            b3dn=True; b3up=False; phase3=2; state["put3"]=f"BREAK DN {sec[2]:.0f}<{first3[2]:.0f}"
                            add_log(state["put3"])
                        else:
                            first3=sec
                live3=[spot,spot,spot,spot,s3]
            else:
                live3[1]=max(live3[1],spot); live3[2]=min(live3[2],spot); live3[3]=spot

            if phase3==2 and first3:
                fifty=int(first3[2]+(first3[1]-first3[2])*0.5)
                if abs(spot-fifty)<=15:
                    strike=int(round(spot/50)*50)
                    if b3up:
                        state["cnt3"]+=1; oid=place_order(strike,"CE")
                        state["call3"]=f"#{state['cnt3']} CALL {strike}CE 50%={fifty} ID:{oid}"
                        phase3=0; first3=None; b3up=False; b3dn=False
                    elif b3dn:
                        state["cnt3"]+=1; oid=place_order(strike,"PE")
                        state["put3"]=f"#{state['cnt3']} PUT {strike}PE 50%={fifty} ID:{oid}"
                        phase3=0; first3=None; b3up=False; b3dn=False
            time.sleep(1)
        except Exception as e:
            add_log(f"WORKER ERR {e}"); time.sleep(2)

threading.Thread(target=worker,daemon=True).start()

@app.route('/')
def home():
    logs="<br>".join(state["log"][-20:])
    return f"<h1 style='background:green;color:white;padding:8px'>AUTO ORDER ON - NSE DIRECT</h1><h2>NIFTY {state['ltp']} | {state['ist']}</h2><h3>{state['c3']} Cnt {state['cnt3']}</h3><h2 style='color:green'>{state['call3']}</h2><h2 style='color:red'>{state['put3']}</h2><h4>{state['msg']}</h4><div style='background:black;color:lime;padding:10px;font-size:12px;height:280px;overflow:auto'>{logs}</div>"
@app.route('/check')
def check(): return jsonify(state)
if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

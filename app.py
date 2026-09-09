from flask import Flask, jsonify
import os, threading, time, pyotp, requests
from datetime import datetime, timedelta
from SmartApi import SmartConnect
from collections import deque

app = Flask(__name__)
LOT=65
state={"ist":"","ltp":0,"c3":"Wait OB","call3":"Scanning...","put3":"Scanning...","atm":"Wait","cnt3":0,"msg":"BOOT","log":[]}
jwt_token=None
api_key=os.getenv("ANGEL_API_KEY")
client_id=os.getenv("ANGEL_CLIENT_ID")
pwd=os.getenv("ANGEL_PASSWORD")
totp_secret=os.getenv("ANGEL_TOTP_SECRET")
smart=None

def add_log(m):
    ts=datetime.utcnow().strftime("%H:%M:%S")
    state["log"].append(f"{ts} {m}")
    if len(state["log"])>20:
        state["log"].pop(0)
    print(m)

def angel_login():
    global jwt_token, smart
    try:
        s=SmartConnect(api_key=api_key)
        totp=pyotp.TOTP(totp_secret).now()
        data=s.generateSession(client_id, pwd, totp)
        jwt_token=data['data']['jwtToken']
        smart=s
        add_log(f"LOGIN OK {jwt_token[:15]}")
        state["msg"]="Login OK"
        return True
    except Exception as e:
        add_log(f"LOGIN FAIL {e}")
        return False

angel_login()

def get_spot():
    ist=datetime.utcnow()+timedelta(hours=5,minutes=30)
    state["ist"]=ist.strftime("%H:%M:%S IST")

    # METHOD 1: Direct getLtpData via HTTP (same as login)
    try:
        if jwt_token:
            url="https://apiconnect.angelone.in/rest/secure/angelbroking/order/v1/getLtpData"
            headers={
                "Authorization": f"Bearer {jwt_token}",
                "Content-Type":"application/json",
                "Accept":"application/json",
                "X-UserType":"USER",
                "X-SourceID":"WEB",
                "X-ClientLocalIP":"127.0.0.1",
                "X-ClientPublicIP":"127.0.0.1",
                "X-MACAddress":"00:00:00:00:00:00",
                "X-PrivateKey": api_key
            }
            body={"exchange":"NSE","tradingsymbol":"Nifty 50","symboltoken":"99926000"}
            r=requests.post(url,headers=headers,json=body,timeout=5)
            add_log(f"LTP HTTP {r.status_code} {r.text[:250]}")
            if r.status_code==200:
                js=r.json()
                if js.get('data') and js['data'].get('ltp'):
                    v=float(js['data']['ltp'])
                    if v>1000:
                        add_log(f"SUCCESS {v}")
                        return v
    except Exception as e:
        add_log(f"LTP HTTP ERR {e}")

    # METHOD 2: SDK fallback
    try:
        if smart:
            d=smart.ltpData("NSE","Nifty 50","99926000")
            add_log(f"SDK {str(d)[:200]}")
            if d and d.get('data') and d['data'].get('ltp'):
                return float(d['data']['ltp'])
    except Exception as e:
        add_log(f"SDK ERR {e}")

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
        return oid
    except Exception as e:
        add_log(f"ORDER ERR {e}"); return None

live3=None; first3=None; phase3=0; b3up=False; b3dn=False

def worker():
    global live3, first3, phase3, b3up, b3dn
    fails=0
    while True:
        try:
            spot=get_spot()
            if spot>1000:
                state["ltp"]=spot
                fails=0
            else:
                fails+=1
                add_log(f"SPOT 0 fail {fails}")
                if fails>3:
                    angel_login()
                    fails=0
                time.sleep(2); continue

            mod=datetime.utcnow()+timedelta(hours=5,minutes=30)
            mod=mod.hour*60+mod.minute
            s3=(mod//3)*3
            if live3 is None or live3[4]!=s3:
                if live3 is not None:
                    if phase3==0:
                        first3=live3; phase3=1
                        state["c3"]=f"3MIN H:{first3[1]:.0f} L:{first3[2]:.0f} 50%={int(first3[2]+(first3[1]-first3[2])*0.5)}"
                    elif phase3==1:
                        sec=live3
                        if sec[1]>first3[1]:
                            b3up=True; b3dn=False; phase3=2; state["call3"]=f"BREAK UP {sec[1]:.0f}>{first3[1]:.0f} 50% wait"
                        elif sec[2]<first3[2]:
                            b3dn=True; b3up=False; phase3=2; state["put3"]=f"BREAK DN {sec[2]:.0f}<{first3[2]:.0f} 50% wait"
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
                        state["cnt3"]+=1
                        oid=place_order(strike,"CE")
                        state["call3"]=f"#{state['cnt3']} CALL BOUGHT {strike}CE 50%={fifty} ID:{oid}"
                        phase3=0; first3=None; b3up=False; b3dn=False
                    elif b3dn:
                        state["cnt3"]+=1
                        oid=place_order(strike,"PE")
                        state["put3"]=f"#{state['cnt3']} PUT BOUGHT {strike}PE 50%={fifty} ID:{oid}"
                        phase3=0; first3=None; b3up=False; b3dn=False
            time.sleep(1)
        except Exception as e:
            add_log(f"WORKER {e}"); time.sleep(2)

threading.Thread(target=worker,daemon=True).start()

@app.route('/')
def home():
    logs="<br>".join(state["log"][-15:])
    return f"<h1 style='background:green;color:white;padding:8px'>AUTO ORDER ON - LTP HTTP</h1><h2>NIFTY {state['ltp']} | {state['ist']}</h2><h3>{state['c3']} Cnt {state['cnt3']}</h3><h2 style='color:green'>{state['call3']}</h2><h2 style='color:red'>{state['put3']}</h2><h4>{state['msg']}</h4><div style='background:black;color:lime;padding:10px;font-size:13px'>{logs}</div>"
@app.route('/check')
def check(): return jsonify(state)
if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

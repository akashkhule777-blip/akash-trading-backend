from flask import Flask, jsonify, request
import os, threading, time, pyotp
from datetime import datetime, timedelta
from SmartApi import SmartConnect

app = Flask(__name__)
state={"ist":"","ltp":0,"c3":"Wait OB","call3":"Waiting for Local LTP...","put3":"Waiting for Local LTP...","atm":"Wait","cnt3":0,"msg":"BOOT - HYBRID MODE","log":[]}

api_key=os.getenv("ANGEL_API_KEY")
client_id=os.getenv("ANGEL_CLIENT_ID")
pwd=os.getenv("ANGEL_PASSWORD")
totp_secret=os.getenv("ANGEL_TOTP_SECRET")
smart=None
last_ltp_update = 0

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
        add_log("LOGIN OK - READY FOR ORDER")
        state["msg"]="Login OK - Waiting LTP from Local"
        return True
    except Exception as e:
        add_log(f"LOGIN FAIL {e}")
        return False

angel_login()

@app.route('/set_ltp')
def set_ltp():
    global last_ltp_update
    try:
        price = float(request.args.get('price',0))
        if price>1000:
            state["ltp"]=price
            state["ist"]=(datetime.utcnow()+timedelta(hours=5,minutes=30)).strftime("%H:%M:%S IST")
            last_ltp_update=time.time()
            state["msg"]=f"LTP Updated {price} from Local"
            return jsonify({"status":"ok","ltp":price})
    except Exception as e:
        add_log(f"SET LTP ERR {e}")
    return jsonify({"status":"fail"})

def place_order(strike,opt_type):
    try:
        if not smart:
            add_log("SMART NONE - RELOGIN")
            angel_login()
            return None
        res=smart.searchScrip("NFO", f"{strike}{opt_type}")
        token=tsym=None
        if res and 'data' in res:
            for item in res['data']:
                if str(strike) in item['tradingsymbol'] and opt_type in item['tradingsymbol']:
                    token=item['token']; tsym=item['tradingsymbol']; break
        if not token:
            add_log(f"TOKEN NOT FOUND {strike}{opt_type}")
            return None
        orderparams={"variety":"NORMAL","tradingsymbol":tsym,"symboltoken":token,"transactiontype":"BUY","exchange":"NFO","ordertype":"MARKET","producttype":"INTRADAY","duration":"DAY","quantity":65}
        oid=smart.placeOrder(orderparams)
        state["msg"]=f"ORDER OK {tsym} {oid}"
        add_log(f"ORDER SUCCESS {tsym} {oid}")
        return oid
    except Exception as e:
        add_log(f"ORDER ERR {e}"); return None

live3=None; first3=None; phase3=0; b3up=False; b3dn=False

def worker():
    global live3, first3, phase3, b3up, b3dn
    while True:
        try:
            # Check if LTP is stale
            if time.time() - last_ltp_update > 15 and last_ltp_update!=0:
                state["call3"]=f"LTP STALE! Local script band aahe! Last {int(time.time()-last_ltp_update)}s ago"
                time.sleep(1); continue

            spot=state["ltp"]
            if spot<1000:
                time.sleep(0.5); continue

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
                            b3up=True; b3dn=False; phase3=2; state["call3"]=f"BREAK UP {sec[1]:.0f}>{first3[1]:.0f} 50% wait"
                            add_log(state["call3"])
                        elif sec[2]<first3[2]:
                            b3dn=True; b3up=False; phase3=2; state["put3"]=f"BREAK DN {sec[2]:.0f}<{first3[2]:.0f} 50% wait"
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
                        add_log(state["call3"])
                        phase3=0; first3=None; b3up=False; b3dn=False
                    elif b3dn:
                        state["cnt3"]+=1; oid=place_order(strike,"PE")
                        state["put3"]=f"#{state['cnt3']} PUT {strike}PE 50%={fifty} ID:{oid}"
                        add_log(state["put3"])
                        phase3=0; first3=None; b3up=False; b3dn=False
            time.sleep(0.5)
        except Exception as e:
            add_log(f"WORKER ERR {e}"); time.sleep(1)

threading.Thread(target=worker,daemon=True).start()

@app.route('/')
def home():
    logs="<br>".join(state["log"][-22:])
    age = int(time.time()-last_ltp_update) if last_ltp_update else 999
    return f"<h1 style='background:green;color:white;padding:8px'>AUTO ORDER ON - HYBRID MODE</h1><h2>NIFTY {state['ltp']} | {state['ist']} | Age {age}s</h2><h3>{state['c3']} Cnt {state['cnt3']}</h3><h2 style='color:green'>{state['call3']}</h2><h2 style='color:red'>{state['put3']}</h2><h4>{state['msg']}</h4><div style='background:black;color:lime;padding:10px;font-size:12px;height:300px;overflow:auto'>{logs}</div><p>Send LTP: /set_ltp?price=23511</p>"
@app.route('/check')
def check(): return jsonify(state)

if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

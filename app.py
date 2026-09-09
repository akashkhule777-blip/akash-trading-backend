from flask import Flask, jsonify
import os, threading, time, pyotp
from datetime import datetime, timedelta
from SmartApi import SmartConnect
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

app = Flask(__name__)
state={"ist":"","ltp":0,"c3":"Wait OB","call3":"Scanning WS...","put3":"Scanning WS...","atm":"Wait","cnt3":0,"msg":"BOOT","log":[]}

api_key=os.getenv("ANGEL_API_KEY")
client_id=os.getenv("ANGEL_CLIENT_ID")
pwd=os.getenv("ANGEL_PASSWORD")
totp_secret=os.getenv("ANGEL_TOTP_SECRET")
smart=None
jwt_token=None
feed_token=None
sws=None

def add_log(m):
    ts=datetime.utcnow().strftime("%H:%M:%S")
    state["log"].append(f"{ts} {m}")
    if len(state["log"])>25:
        state["log"].pop(0)
    print(m)

def angel_login():
    global jwt_token, feed_token, smart
    try:
        s=SmartConnect(api_key=api_key)
        totp=pyotp.TOTP(totp_secret).now()
        data=s.generateSession(client_id, pwd, totp)
        jwt_token=data['data']['jwtToken']
        feed_token=data['data']['feedToken']
        smart=s
        add_log(f"LOGIN OK jwt {jwt_token[:8]} feed {feed_token[:8]}")
        state["msg"]="Login OK WS connecting..."
        return True
    except Exception as e:
        add_log(f"LOGIN FAIL {e}")
        return False

def start_websocket():
    global sws
    try:
        add_log("WS CONNECTING...")
        sws = SmartWebSocketV2(jwt_token, api_key, client_id, feed_token)

        def on_data(wsapp, msg):
            try:
                # msg = {'exchange_type':1,'token':'99926000','last_traded_price':2347695}
                if msg.get('token')=='99926000' or str(msg.get('token'))=='99926000':
                    ltp = msg.get('last_traded_price',0)
                    if ltp>0:
                        # Angel sends price *100
                        price = ltp/100
                        if price>1000:
                            state["ltp"]=price
                            state["ist"]=(datetime.utcnow()+timedelta(hours=5,minutes=30)).strftime("%H:%M:%S IST")
                            # add_log(f"WS LTP {price}") # too much log
            except Exception as e:
                add_log(f"WS DATA ERR {e}")

        def on_open(wsapp):
            add_log("WS OPENED")
            try:
                # Subscribe NIFTY 50 token 99926000 NSE = exchange_type 1
                token_list = [{"exchangeType": 1, "tokens": ["99926000"]}]
                sws.subscribe("NSE", "NIFTY", ["99926000"])
                # OR use generic
                sws.subscribe(1, 1, ["99926000"])
                add_log("WS SUBSCRIBED NIFTY 99926000")
                state["msg"]="WS Subscribed"
            except Exception as e:
                add_log(f"WS SUB ERR {e}")

        def on_error(wsapp, error):
            add_log(f"WS ERROR {error}")
            state["msg"]=f"WS Error {error}"

        def on_close(wsapp):
            add_log("WS CLOSED - RECONNECT")
            state["msg"]="WS Closed Reconnect in 3s"
            time.sleep(3)
            start_websocket()

        sws.on_open = on_open
        sws.on_data = on_data
        sws.on_error = on_error
        sws.on_close = on_close

        sws.connect()

    except Exception as e:
        add_log(f"WS CONNECT FAIL {e}")
        time.sleep(5)
        start_websocket()

angel_login()
threading.Thread(target=start_websocket, daemon=True).start()

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

def strategy_worker():
    global live3, first3, phase3, b3up, b3dn
    while True:
        try:
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
                        phase3=0; first3=None; b3up=False; b3dn=False
                    elif b3dn:
                        state["cnt3"]+=1; oid=place_order(strike,"PE")
                        state["put3"]=f"#{state['cnt3']} PUT {strike}PE 50%={fifty} ID:{oid}"
                        phase3=0; first3=None; b3up=False; b3dn=False
            time.sleep(0.5)
        except Exception as e:
            add_log(f"STRATEGY ERR {e}"); time.sleep(1)

threading.Thread(target=strategy_worker, daemon=True).start()

@app.route('/')
def home():
    logs="<br>".join(state["log"][-20:])
    return f"<h1 style='background:green;color:white;padding:8px'>AUTO ORDER ON - WS NIFTY</h1><h2>NIFTY {state['ltp']} | {state['ist']}</h2><h3>{state['c3']} Cnt {state['cnt3']}</h3><h2 style='color:green'>{state['call3']}</h2><h2 style='color:red'>{state['put3']}</h2><h4>{state['msg']}</h4><div style='background:black;color:lime;padding:10px;font-size:12px;height:250px;overflow:auto'>{logs}</div>"

@app.route('/check')
def check(): return jsonify(state)

if __name__=="__main__":
    app.run(host='0.0.0.0',port=10000)

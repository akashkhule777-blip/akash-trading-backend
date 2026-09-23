from flask import Flask
from datetime import datetime, timezone, timedelta
import os, json, threading, time, pyotp
from SmartApi import SmartConnect

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
def ist_now(): return datetime.now(timezone.utc).astimezone(IST)
FILE = "/tmp/ob_final.json"
QTY = 65
API_KEY = os.environ.get("ANGEL_API_KEY")
CLIENT_ID = os.environ.get("ANGEL_CLIENT_ID")
MPIN = os.environ.get("ANGEL_PASSWORD")
TOTP_SECRET = os.environ.get("ANGEL_TOTP_SECRET")

def load():
    if os.path.exists(FILE):
        try:
            with open(FILE,'r') as f: return json.load(f)
        except: pass
    return {"nifty":0,"atm":0,"action":"Starting...","ob_high":0,"ob_low":0,"ob_50":0,"type":"","symbol":"","exp":"","time_str":""}
def save(d):
    with open(FILE,'w') as f: json.dump(d,f)

def get_tue():
    d=ist_now().date()
    off=(1-d.weekday())%7
    if off==0 and ist_now().hour>=15: off=7
    return d+timedelta(days=off)

def find_ob(c):
    for i in range(len(c)-4,1,-1):
        try:
            p=c[i]; c1=c[i+1]; c2=c[i+2]
            if p[1]>p[4] and c1[4]>c1[1] and c2[4]>p[2]:
                return {"high":p[2],"low":p[3],"50":(p[2]+p[3])/2}
        except: continue
    return None

def run():
    try:
        smart=SmartConnect(api_key=API_KEY)
        smart.generateSession(CLIENT_ID, MPIN, pyotp.TOTP(TOTP_SECRET).now())
        print("Login OK")
    except Exception as e:
        print(f"Fail {e}"); return

    tok=None; trad=None; last_exp=None; last_h=0
    while True:
        try:
            now=ist_now()
            if now.hour<9 or (now.hour==9 and now.minute<15) or now.hour>=15 and now.minute>=30:
                d=load(); d["action"]=f"Market Band {now.strftime('%H:%M')}"; d["time_str"]=now.strftime("%H:%M:%S"); save(d); time.sleep(60); continue
            d=load(); d["time_str"]=now.strftime("%H:%M:%S")
            exp=get_tue()
            if last_exp!=exp or tok is None:
                try:
                    ltp=smart.ltpData("NSE","NIFTY","26000")['data']['ltp']
                    atm=int(round(ltp/50)*50)
                    d["nifty"]=ltp; d["atm"]=atm
                    sym=f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}CE"
                    s=smart.searchScrip("NFO",sym)
                    if s and s.get('data'):
                        tok=s['data'][0]['symboltoken']; trad=s['data'][0]['tradingsymbol']
                        last_exp=exp; d["symbol"]=trad; d["exp"]=str(exp)
                except Exception as e:
                    d["action"]=f"Token Wait 60s {e}"; save(d); time.sleep(60); continue
            if not tok: time.sleep(60); continue
            try:
                frm=(ist_now()-timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
                to=ist_now().strftime("%Y-%m-%d %H:%M")
                res=smart.getCandleData({"exchange":"NFO","symboltoken":tok,"interval":"THREE_MINUTE","fromdate":frm,"todate":to})
                data=res.get('data') if isinstance(res, dict) else []
            except Exception as e:
                if "Access denied" in str(e):
                    d["action"]=f"Angel Block 2min wait {now.strftime('%H:%M:%S')}"; save(d); time.sleep(120); continue
                d["action"]=f"Wait {e}"; save(d); time.sleep(60); continue
            if len(data)<10: time.sleep(60); continue
            ob=find_ob(data)
            if ob:
                d["ob_high"]=round(ob["high"],2); d["ob_low"]=round(ob["low"],2); d["ob_50"]=round(ob["50"],2); d["type"]=f"CE BULLISH ATM {d['atm']}"
                is_break=data[-2][2] > ob["high"]
                if is_break and ob["high"]!=last_h:
                    lp=round(ob["50"],1)
                    d["action"]=f"BREAK zala! LIMIT {lp} Pending taktoy..."; save(d)
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":trad,"symboltoken":tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":str(lp),"producttype":"CARRYFORWARD","duration":"DAY","quantity":QTY})
                        last_h=ob["high"]; d["action"]=f"PENDING DONE {trad} @ {lp} | Angel App Orders madhe bagh"
                    except Exception as e: d["action"]=f"Order Fail {e}"
                elif not is_break:
                    d["action"]=f"OB milala - Break chi vaat | 50% {round(ob['50'],2)} | SL {round(ob['low'],2)}"
            else:
                d["action"]=f"OB shodhtoy NIFTY {d['nifty']} ATM {d['atm']}"
            save(d); time.sleep(60)
        except Exception as e:
            d=load(); d["action"]=f"Loop Err {e}"; save(d); time.sleep(60)

threading.Thread(target=run, daemon=True).start()

@app.route('/')
def home():
    d=load()
    return f"<html><head><meta http-equiv='refresh' content='60'><style>body{{background:#0e0e0e;color:#fff;font-family:Arial;padding:10px}}.g{{color:#00ff88}}.y{{color:#ffeb3b}}.b{{border:1px solid #333;padding:10px;border-radius:10px}}</style></head><body><h2 class=g>NIFTY {d['nifty']} | ATM {d['atm']} | {d['time_str']}</h2><div class=b>{d['symbol']}<br>{d['type']}<br>50% {d['ob_50']} | SL {d['ob_low']}</div><h3 class=y>{d['action']}</h3><p>60s MODE FIXED</p></body></html>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

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
    return {"nifty":0,"atm":0,"action":"Starting...","ob_50":0,"ob_low":0,"symbol":"","exp":"","time_str":""}

def save(d):
    with open(FILE,'w') as f: json.dump(d,f)

def get_tue():
    d=ist_now().date()
    off=(1-d.weekday())%7
    if off==0 and ist_now().hour>=15: off=7
    return d+timedelta(days=off)

def find_ob(c):
    # Tumchya box pramane OB - shevatchi moti hirvi candle
    try:
        # Shevatche 15 candle madhun sarvat moti bullish candle shodh
        best=None
        best_body=0
        for i in range(len(c)-5, max(5, len(c)-20), -1):
            p=c[i]
            body = p[4]-p[1]
            if body>0 and body>best_body:
                best_body=body
                best=p
        if best:
            return {"high":best[2],"low":best[3],"50":(best[2]+best[3])/2}
    except: pass
    # Fallback - last 10 candles chi range
    try:
        last10=c[-12:-2]
        h=max(x[2] for x in last10)
        l=min(x[3] for x in last10)
        return {"high":h,"low":l,"50":(h+l)/2}
    except:
        return None

def run():
    try:
        smart=SmartConnect(api_key=API_KEY)
        smart.generateSession(CLIENT_ID, MPIN, pyotp.TOTP(TOTP_SECRET).now())
    except Exception as e:
        d=load(); d["action"]=f"LOGIN FAIL {e}"; save(d)
        return

    tok=None; trad=None; last_exp=None; last_h=0
    while True:
        try:
            now=ist_now()
            d=load()
            d["time_str"]=now.strftime("%H:%M:%S")
            exp=get_tue()
            if last_exp!=exp or tok is None:
                try:
                    ltp=smart.ltpData("NSE","NIFTY","26000")['data']['ltp']
                    atm=int(round(ltp/50)*50)
                    d["nifty"]=ltp; d["atm"]=atm
                    sym=f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}CE"
                    s=smart.searchScrip("NFO", sym)
                    if s and s.get('data'):
                        tok=s['data'][0]['symboltoken']
                        trad=s['data'][0]['tradingsymbol']
                        last_exp=exp; d["symbol"]=trad; d["exp"]=str(exp)
                except Exception as e:
                    d["action"]=f"Token wait {e}"; save(d); time.sleep(120); continue

            if not tok: time.sleep(120); continue

            try:
                frm=(ist_now()-timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
                to=ist_now().strftime("%Y-%m-%d %H:%M")
                res=smart.getCandleData({"exchange":"NFO","symboltoken":tok,"interval":"THREE_MINUTE","fromdate":frm,"todate":to})
                data=res.get('data') if isinstance(res, dict) else []
            except Exception as e:
                if "Access denied" in str(e):
                    d["action"]=f"Angel Block - 5 min thambtoy {now.strftime('%H:%M:%S')}"
                    save(d); time.sleep(300); continue
                d["action"]=f"Wait {e}"; save(d); time.sleep(120); continue

            if not data or len(data)<10:
                d["action"]=f"Data wait ATM {d['atm']}"
                save(d); time.sleep(120); continue

            ob=find_ob(data)
            if ob:
                d["ob_50"]=round(ob["50"],2); d["ob_low"]=round(ob["low"],2)
                is_break=data[-2][2] > ob["high"]
                if is_break and ob["high"]!=last_h:
                    lp=int(round(ob["50"]))
                    d["action"]=f"BREAK zala LIMIT {lp} taktoy"
                    save(d)
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":trad,"symboltoken":tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":lp,"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        last_h=ob["high"]; d["action"]=f"PENDING DONE {trad} @ {lp}"
                    except Exception as e: d["action"]=f"Order Fail {e}"
                else:
                    d["action"]=f"OB milala 50% {d['ob_50']} SL {d['ob_low']} Break vaat"
            else:
                d["action"]=f"OB shodhtoy ATM {d['atm']}"

            save(d)
            time.sleep(120)
        except Exception as e:
            d=load(); d["action"]=f"Loop {e}"; save(d); time.sleep(120)

threading.Thread(target=run, daemon=True).start()

@app.route('/')
def home():
    d=load()
    return f"<html><head><meta http-equiv='refresh' content='20'><style>body{{background:#0e0e0e;color:#fff;font-family:Arial;padding:15px}}.g{{color:#00ff88;font-size:20px}}.y{{color:#ffeb3b}}.b{{border:1px solid #333;padding:10px;border-radius:10px}}</style></head><body><h2 class=g>NIFTY {d['nifty']} ATM {d['atm']}</h2><div class=b>{d['symbol']}<br>{d['exp']}<br>50% {d['ob_50']} SL {d['ob_low']}</div><h3 class=y>{d['action']}</h3><p>{d['time_str']} | 120s Fix + OB Fix ON</p></body></html>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

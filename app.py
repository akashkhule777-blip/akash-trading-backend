from flask import Flask
from datetime import datetime, timezone, timedelta
import os, json, threading, time, pyotp
from SmartApi import SmartConnect

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
def ist_now(): return datetime.now(timezone.utc).astimezone(IST)

FILE = "/tmp/ob.json"
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
    return {"nifty":0,"atm":0,"action":"Starting...","ce_50":0,"ce_sl":0,"pe_50":0,"pe_sl":0,"ce_sym":"","pe_sym":"","exp":"","time_str":""}

def save(d):
    with open(FILE,'w') as f: json.dump(d,f)

def get_tue():
    d=ist_now().date()
    off=(1-d.weekday())%7
    if off==0 and ist_now().hour>=15: off=7
    return d+timedelta(days=off)

def find_ob(c):
    try:
        for i in range(len(c)-5, max(5,len(c)-20), -1):
            p=c[i]
            if p[4]>p[1]: # bullish
                return {"high":p[2],"low":p[3],"50":(p[2]+p[3])/2}
        last10=c[-12:-2]
        h=max(x[2] for x in last10)
        l=min(x[3] for x in last10)
        return {"high":h,"low":l,"50":(h+l)/2}
    except: return None

def run():
    try:
        smart=SmartConnect(api_key=API_KEY)
        smart.generateSession(CLIENT_ID, MPIN, pyotp.TOTP(TOTP_SECRET).now())
    except Exception as e:
        d=load(); d["action"]=f"LOGIN FAIL {e}"; save(d); return

    ce_tok=None; pe_tok=None; ce_trad=None; pe_trad=None; last_exp=None
    ce_h=0; pe_h=0

    while True:
        try:
            now=ist_now(); d=load(); d["time_str"]=now.strftime("%H:%M:%S")
            exp=get_tue()

            if last_exp!=exp or not ce_tok:
                try:
                    ltp=smart.ltpData("NSE","NIFTY","26000")['data']['ltp']
                    atm=int(round(ltp/50)*50)
                    d["nifty"]=ltp; d["atm"]=atm
                    ce_sym=f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}CE"
                    pe_sym=f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}PE"
                    ce_s=smart.searchScrip("NFO", ce_sym)
                    pe_s=smart.searchScrip("NFO", pe_sym)
                    if ce_s and ce_s.get('data'):
                        ce_tok=ce_s['data'][0]['symboltoken']; ce_trad=ce_s['data'][0]['tradingsymbol']; d["ce_sym"]=ce_trad
                    if pe_s and pe_s.get('data'):
                        pe_tok=pe_s['data'][0]['symboltoken']; pe_trad=pe_s['data'][0]['tradingsymbol']; d["pe_sym"]=pe_trad
                    last_exp=exp; d["exp"]=str(exp)
                except Exception as e:
                    d["action"]=f"Token wait {e}"; save(d); time.sleep(180); continue

            if not ce_tok or not pe_tok: time.sleep(180); continue

            # CE Candle
            try:
                frm=(ist_now()-timedelta(days=3)).strftime("%Y-%m-%d %H:%M")
                to=ist_now().strftime("%Y-%m-%d %H:%M")
                ce_res=smart.getCandleData({"exchange":"NFO","symboltoken":ce_tok,"interval":"THREE_MINUTE","fromdate":frm,"todate":to})
                ce_data=ce_res.get('data') if isinstance(ce_res, dict) else []
                time.sleep(2)
                pe_res=smart.getCandleData({"exchange":"NFO","symboltoken":pe_tok,"interval":"THREE_MINUTE","fromdate":frm,"todate":to})
                pe_data=pe_res.get('data') if isinstance(pe_res, dict) else []
            except Exception as e:
                if "Access denied" in str(e):
                    d["action"]=f"Angel Block 5 min wait {now.strftime('%H:%M:%S')}"; save(d); time.sleep(300); continue
                d["action"]=f"Wait {e}"; save(d); time.sleep(180); continue

            ce_ob=find_ob(ce_data) if ce_data else None
            pe_ob=find_ob(pe_data) if pe_data else None

            if ce_ob: d["ce_50"]=round(ce_ob["50"],2); d["ce_sl"]=round(ce_ob["low"],2)
            if pe_ob: d["pe_50"]=round(pe_ob["50"],2); d["pe_sl"]=round(pe_ob["low"],2)

            msg=[]
            if ce_ob:
                if ce_data[-2][2] > ce_ob["high"] and ce_ob["high"]!=ce_h:
                    lp=int(round(ce_ob["50"]))
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":lp,"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        ce_h=ce_ob["high"]; msg.append(f"CE BUY {lp}")
                    except Exception as e: msg.append(f"CE Fail {e}")
                else: msg.append(f"CE OB {d['ce_50']} SL {d['ce_sl']}")

            if pe_ob:
                if pe_data[-2][2] > pe_ob["high"] and pe_ob["high"]!=pe_h:
                    lp=int(round(pe_ob["50"]))
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":lp,"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                        pe_h=pe_ob["high"]; msg.append(f"PE BUY {lp}")
                    except Exception as e: msg.append(f"PE Fail {e}")
                else: msg.append(f"PE OB {d['pe_50']} SL {d['pe_sl']}")

            d["action"]=" | ".join(msg) if msg else f"OB shodhtoy ATM {d['atm']}"
            save(d); time.sleep(180)

        except Exception as e:
            d=load(); d["action"]=f"Err {e}"; save(d); time.sleep(180)

threading.Thread(target=run, daemon=True).start()

@app.route('/')
def home():
    d=load()
    return f"<html><head><meta http-equiv='refresh' content='30'><meta name='viewport' content='width=device-width'><style>body{{background:#111;color:#fff;font-family:Arial;padding:12px}}.g{{color:#00ff88;font-size:20px}}.y{{color:#ffeb3b}}.b{{border:1px solid #333;padding:10px;border-radius:10px;margin-bottom:8px}}</style></head><body><h2 class=g>NIFTY {d['nifty']} ATM {d['atm']}</h2><div class=b>CE: {d['ce_sym']}<br>50% {d['ce_50']} SL {d['ce_sl']}</div><div class=b>PE: {d['pe_sym']}<br>50% {d['pe_50']} SL {d['pe_sl']}</div><div class=b>{d['exp']}</div><h3 class=y>{d['action']}</h3><p>{d['time_str']} | CE+PE Donhi ON | 3min Gap</p></body></html>"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=10000)

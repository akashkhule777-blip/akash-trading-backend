from flask import Flask
from datetime import datetime, timezone, timedelta
import os, json, threading, time, pyotp
from SmartApi import SmartConnect

app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
def ist_now(): return datetime.now(timezone.utc).astimezone(IST)
FILE = "/tmp/ob.json"

def load():
    if os.path.exists(FILE):
        try:
            with open(FILE,'r') as f: return json.load(f)
        except: pass
    return {"nifty":0,"atm":0,"action":"Starting...","ce_50":0,"ce_sl":0,"pe_50":0,"pe_sl":0,"ce_sym":"","pe_sym":"","exp":"","time_str":"","log":""}

def save(d):
    with open(FILE,'w') as f: json.dump(d,f)

def get_next_tue():
    d = ist_now().date()
    # pudhcha Tuesday
    days_ahead = (1 - d.weekday()) % 7
    if days_ahead == 0 and ist_now().hour >= 15:
        days_ahead = 7
    return d + timedelta(days=days_ahead)

def find_ob(c):
    try:
        if len(c) < 10: return None
        # last 12 candles cha box
        box = c[-12:-2]
        highs = [float(x[2]) for x in box]
        lows = [float(x[3]) for x in box]
        h = max(highs); l = min(lows)
        if h==l: return None
        return {"high":h,"low":l,"50":(h+l)/2}
    except Exception as e:
        return None

def run():
    try:
        smart = SmartConnect(api_key=os.environ.get("ANGEL_API_KEY"))
        smart.generateSession(os.environ.get("ANGEL_CLIENT_ID"), os.environ.get("ANGEL_PASSWORD"), pyotp.TOTP(os.environ.get("ANGEL_TOTP_SECRET")).now())
    except Exception as e:
        d=load(); d["action"]=f"LOGIN FAIL {e}"; save(d); return

    ce_tok=pe_tok=None
    ce_trad=pe_trad=None
    last_exp=None

    while True:
        try:
            now = ist_now()
            d = load()
            d["time_str"] = now.strftime("%H:%M:%S")
            exp = get_next_tue()
            d["exp"]=str(exp)

            if last_exp!=exp or not ce_tok:
                try:
                    ltp_data = smart.ltpData("NSE","NIFTY","26000")
                    ltp = ltp_data['data']['ltp']
                    atm = int(round(ltp/50)*50)
                    d["nifty"]=ltp; d["atm"]=atm

                    ce_sym = f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}CE"
                    pe_sym = f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}PE"

                    s1 = smart.searchScrip("NFO", ce_sym)
                    time.sleep(1)
                    s2 = smart.searchScrip("NFO", pe_sym)

                    if s1 and s1.get('data'):
                        ce_tok = str(s1['data'][0]['symboltoken'])
                        ce_trad = s1['data'][0]['tradingsymbol']
                        d["ce_sym"]=ce_trad
                    if s2 and s2.get('data'):
                        pe_tok = str(s2['data'][0]['symboltoken'])
                        pe_trad = s2['data'][0]['tradingsymbol']
                        d["pe_sym"]=pe_trad

                    last_exp=exp
                    d["log"]=f"CE {ce_tok} PE {pe_tok}"
                except Exception as e:
                    d["action"]=f"Token Err {e}"; save(d)
                    if "Access denied" in str(e): time.sleep(600)
                    else: time.sleep(60)
                    continue

            if not ce_tok: time.sleep(60); continue

            # CANDLE - ONE_MINUTE ne gheu - THREE_MINUTE la data nasto
            try:
                frm = (ist_now() - timedelta(days=5)).strftime("%Y-%m-%d %H:%M")
                to = ist_now().strftime("%Y-%m-%d %H:%M")

                c1 = smart.getCandleData({"exchange":"NFO","symboltoken":ce_tok,"interval":"ONE_MINUTE","fromdate":frm,"todate":to})
                ce_data = c1.get('data') if isinstance(c1, dict) and isinstance(c1.get('data'), list) else []

                time.sleep(3)

                c2 = smart.getCandleData({"exchange":"NFO","symboltoken":pe_tok,"interval":"ONE_MINUTE","fromdate":frm,"todate":to})
                pe_data = c2.get('data') if isinstance(c2, dict) and isinstance(c2.get('data'), list) else []

                d["log"] = f"CE len {len(ce_data)} PE len {len(pe_data)}"

                if len(ce_data)==0 and len(pe_data)==0:
                    d["action"]=f"Candle empty - Market band? Len 0 | {d['log']}"
                    save(d); time.sleep(180); continue

            except Exception as e:
                if "Access denied" in str(e):
                    d["action"]=f"Angel Block 10 min {now.strftime('%H:%M:%S')}"
                    save(d); time.sleep(600); continue
                d["action"]=f"Candle Err {e}"; save(d); time.sleep(120); continue

            ce_ob = find_ob(ce_data)
            pe_ob = find_ob(pe_data)

            if ce_ob:
                d["ce_50"]=round(ce_ob["50"],2); d["ce_sl"]=round(ce_ob["low"],2)
            if pe_ob:
                d["pe_50"]=round(pe_ob["50"],2); d["pe_sl"]=round(pe_ob["low"],2)

            if ce_ob or pe_ob:
                d["action"]=f"CE {d['ce_50']} SL {d['ce_sl']} | PE {d['pe_50']} SL {d['pe_sl']} | Ready"
            else:
                d["action"]=f"Candle wait... len CE {len(ce_data)} PE {len(pe_data)}"

            # Order fakt break var
            try:
                if ce_ob and len(ce_data)>2:
                    if float(ce_data[-2][2]) > ce_ob["high"]:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":int(ce_ob["50"]),"producttype":"INTRADAY","duration":"DAY","quantity":65})
            except: pass

            save(d)
            time.sleep(180)

        except Exception as e:
            d=load(); d["action"]=f"Loop {e}"; save(d); time.sleep(180)

threading.Thread(target=run, daemon=True).start()

@app.route('/')
def home():
    d=load()
    return f"<html><head><meta http-equiv='refresh' content='20'><meta name='viewport' content='width=device-width'><style>body{{background:#111;color:#fff;font-family:Arial;padding:10px}}.g{{color:#0f0;font-size:20px}}.y{{color:#ffeb3b}}.b{{border:1px solid #444;padding:8px;border-radius:8px;margin:6px 0}}</style></head><body><h2 class=g>NIFTY {d['nifty']} ATM {d['atm']}</h2><div class=b>CE: {d['ce_sym']}<br>50% {d['ce_50']} SL {d['ce_sl']}</div><div class=b>PE: {d['pe_sym']}<br>50% {d['pe_50']} SL {d['pe_sl']}</div><div class=b>EXP: {d['exp']}<br>{d['log']}</div><h3 class=y>{d['action']}</h3><p>{d['time_str']} | Donhi ON</p></body></html>"

if __name__=='__main__':
    app.run(host='0.0.0.0', port=10000)

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
    return {"nifty":0,"atm":0,"action":"Starting...","ce_50":0,"ce_sl":0,"ce_h":0,"ce_l":0,"pe_50":0,"pe_sl":0,"pe_h":0,"pe_l":0,"ce_sym":"","pe_sym":"","exp":"","time_str":"","log":""}
def save(d):
    with open(FILE,'w') as f: json.dump(d,f)

def get_tue():
    d = ist_now().date()
    off = (1 - d.weekday()) % 7
    if off == 0 and ist_now().hour >= 15: off = 7
    return d + timedelta(days=off)

def find_option_ob(c):
    try:
        if not c or len(c) < 20: return None
        # Option cha box - shevatche 15 candle
        # Tuzya photo madhe jasa box kadhlas tasa
        box = c[-16:-2] # last 2 sodun
        h = max(float(x[2]) for x in box)
        l = min(float(x[3]) for x in box)
        return {"high":h,"low":l,"50":(h+l)/2.0}
    except: return None

def get_candles(smart, token):
    # 3 interval try karu - ek na ek la data yeil
    for interval in ["THREE_MINUTE","FIVE_MINUTE","ONE_MINUTE"]:
        try:
            frm = (ist_now() - timedelta(days=6)).strftime("%Y-%m-%d %H:%M")
            to = ist_now().strftime("%Y-%m-%d %H:%M")
            res = smart.getCandleData({"exchange":"NFO","symboltoken":token,"interval":interval,"fromdate":frm,"todate":to})
            if isinstance(res, dict):
                data = res.get('data')
                if isinstance(data, list) and len(data) > 15:
                    return data, interval
        except: pass
        time.sleep(1)
    return [], "NO DATA"

def run():
    try:
        smart = SmartConnect(api_key=os.environ.get("ANGEL_API_KEY"))
        smart.generateSession(os.environ.get("ANGEL_CLIENT_ID"), os.environ.get("ANGEL_PASSWORD"), pyotp.TOTP(os.environ.get("ANGEL_TOTP_SECRET")).now())
    except Exception as e:
        d=load(); d["action"]=f"LOGIN FAIL {e}"; save(d); return

    ce_tok=pe_tok=ce_trad=pe_trad=None; last_exp=None
    ce_entry_done=False; pe_entry_done=False

    while True:
        try:
            now=ist_now(); d=load(); exp=get_tue()
            ltp = smart.ltpData("NSE","NIFTY","26000")['data']['ltp']
            atm = int(round(ltp/50)*50)
            d["nifty"]=ltp; d["atm"]=atm; d["exp"]=str(exp)
            d["time_str"]=now.strftime("%H:%M:%S")

            if last_exp!=exp or not ce_tok:
                ce_sym = f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}CE"
                pe_sym = f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}PE"
                try:
                    s1 = smart.searchScrip("NFO", ce_sym)
                    time.sleep(1)
                    s2 = smart.searchScrip("NFO", pe_sym)
                    if s1 and s1.get('data'): ce_tok=str(s1['data'][0]['symboltoken']); ce_trad=s1['data'][0]['tradingsymbol']; d["ce_sym"]=ce_trad
                    if s2 and s2.get('data'): pe_tok=str(s2['data'][0]['symboltoken']); pe_trad=s2['data'][0]['tradingsymbol']; d["pe_sym"]=pe_trad
                    last_exp=exp; ce_entry_done=False; pe_entry_done=False
                except Exception as e:
                    if "Access denied" in str(e): time.sleep(600); continue
                    time.sleep(60); continue

            if not ce_tok: time.sleep(60); continue

            ce_data, ce_int = get_candles(smart, ce_tok)
            time.sleep(2)
            pe_data, pe_int = get_candles(smart, pe_tok)

            d["log"]=f"CE {len(ce_data)} {ce_int} | PE {len(pe_data)} {pe_int}"

            ce_ob = find_option_ob(ce_data)
            pe_ob = find_option_ob(pe_data)

            if ce_ob:
                d["ce_h"]=round(ce_ob["high"],2); d["ce_l"]=round(ce_ob["low"],2)
                d["ce_50"]=round(ce_ob["50"],2); d["ce_sl"]=round(ce_ob["low"],2)
            if pe_ob:
                d["pe_h"]=round(pe_ob["high"],2); d["pe_l"]=round(pe_ob["low"],2)
                d["pe_50"]=round(pe_ob["50"],2); d["pe_sl"]=round(pe_ob["low"],2)

            msg=[]
            # CE OPTION BREAK LOGIC
            if ce_ob and len(ce_data)>2:
                last_candle_high = float(ce_data[-2][2])
                if last_candle_high > ce_ob["high"] and not ce_entry_done:
                    lp = int(ce_ob["50"])
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":lp,"producttype":"INTRADAY","duration":"DAY","quantity":65})
                        msg.append(f"CE BREAK BUY 50% {lp}")
                        ce_entry_done=True
                    except Exception as e: msg.append(f"CE Fail {e}")
                else:
                    msg.append(f"CE BOX {d['ce_l']}-{d['ce_h']} 50% {d['ce_50']}")

            if pe_ob and len(pe_data)>2:
                last_candle_high = float(pe_data[-2][2])
                if last_candle_high > pe_ob["high"] and not pe_entry_done:
                    lp = int(pe_ob["50"])
                    try:
                        smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":lp,"producttype":"INTRADAY","duration":"DAY","quantity":65})
                        msg.append(f"PE BREAK BUY 50% {lp}")
                        pe_entry_done=True
                    except Exception as e: msg.append(f"PE Fail {e}")
                else:
                    msg.append(f"PE BOX {d['pe_l']}-{d['pe_h']} 50% {d['pe_50']}")

            if not msg:
                d["action"]=f"Candle wait {d['log']}"
            else:
                d["action"]=" | ".join(msg)

            save(d)
            time.sleep(180)

        except Exception as e:
            d=load(); d["action"]=f"Err {e}"; save(d); time.sleep(120)

threading.Thread(target=run, daemon=True).start()

@app.route('/')
def home():
    d=load()
    return f"<html><head><meta http-equiv='refresh' content='15'><meta name='viewport' content='width=device-width'><style>body{{background:#111;color:#fff;font-family:Arial;padding:10px}}.g{{color:#0f0;font-size:20px}}.y{{color:#ffeb3b;font-size:13px}}.b{{border:1px solid #444;padding:8px;border-radius:8px;margin:6px 0;background:#1a1a1a}}</style></head><body><h2 class=g>NIFTY {d['nifty']} ATM {d['atm']}</h2><div class=b>CE: {d['ce_sym']}<br>BOX {d['ce_l']} - {d['ce_h']}<br><b>50% {d['ce_50']} SL {d['ce_sl']}</b></div><div class=b>PE: {d['pe_sym']}<br>BOX {d['pe_l']} - {d['pe_h']}<br><b>50% {d['pe_50']} SL {d['pe_sl']}</b></div><div class=b>EXP {d['exp']}<br>{d['log']}</div><h3 class=y>{d['action']}</h3><p>{d['time_str']} | OPTION CHART ONLY</p></body></html>"

if __name__=='__main__':
    app.run(host='0.0.0.0', port=10000)

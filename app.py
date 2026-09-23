from flask import Flask
from datetime import datetime, timezone, timedelta
import os, json, threading, time, pyotp
from SmartApi import SmartConnect
app = Flask(__name__)
IST = timezone(timedelta(hours=5, minutes=30))
def ist_now(): return datetime.now(timezone.utc).astimezone(IST)
FILE = "/tmp/ob.json"
QTY = 65
def load():
    if os.path.exists(FILE):
        try:
            with open(FILE,'r') as f: return json.load(f)
        except: pass
    return {"nifty":0,"atm":0,"action":"Starting","ce_50":0,"ce_sl":0,"ce_h":0,"ce_l":0,"pe_50":0,"pe_sl":0,"pe_h":0,"pe_l":0,"ce_sym":"","pe_sym":"","exp":"","time_str":"","log":""}
def save(d):
    with open(FILE,'w') as f: json.dump(d,f)
def get_tue():
    d=ist_now().date()
    off=(1-d.weekday())%7
    if off==0 and ist_now().hour>=15: off=7
    return d+timedelta(days=off)
def find_ob(c):
    if not c or len(c)<20: return None
    box=c[-16:-2]
    h=max(float(x[2]) for x in box)
    l=min(float(x[3]) for x in box)
    return {"high":h,"low":l,"50":(h+l)/2}
def get_candles(smart, token):
    for interval in ["ONE_MINUTE","THREE_MINUTE","FIVE_MINUTE","ONE_DAY","ONE_HOUR"]:
        try:
            frm=(ist_now()-timedelta(days=10)).strftime("%Y-%m-%d %H:%M")
            to=ist_now().strftime("%Y-%m-%d %H:%M")
            res=smart.getCandleData({"exchange":"NFO","symboltoken":str(token),"interval":interval,"fromdate":frm,"todate":to})
            if res and res.get('data') and len(res['data'])>5:
                return res['data'],interval
        except Exception as e:
            pass
        time.sleep(0.5)
    return [],"NO DATA"
def parse_search(res):
    try:
        if isinstance(res,str):
            import json as js; res=js.loads(res)
        if res.get('data'):
            for item in res['data']:
                if 'PE' in item.get('tradingsymbol','') or 'CE' in item.get('tradingsymbol',''):
                    return item
            if len(res['data'])>0:
                return res['data'][0]
    except: pass
    return None

def run():
    try:
        smart=SmartConnect(api_key=os.environ.get("ANGEL_API_KEY"))
        smart.generateSession(os.environ.get("ANGEL_CLIENT_ID"),os.environ.get("ANGEL_PASSWORD"),pyotp.TOTP(os.environ.get("ANGEL_TOTP_SECRET")).now())
    except Exception as e:
        d=load();d["action"]=f"LOGIN FAIL {e}";save(d);return
    ce_tok=pe_tok=ce_trad=pe_trad=None;last_exp=None;ce_done=False;pe_done=False
    while True:
        try:
            now=ist_now();d=load();exp=get_tue()
            ltp=smart.ltpData("NSE","NIFTY","26000")['data']['ltp']
            atm=int(round(ltp/50)*50)
            d["nifty"]=ltp;d["atm"]=atm;d["exp"]=str(exp);d["time_str"]=now.strftime("%H:%M:%S")
            if last_exp!=exp or not ce_tok or not pe_tok:
                try:
                    # CE search
                    r1=smart.searchScrip("NFO",f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}CE")
                    time.sleep(1.5)
                    # PE search - 2 try
                    r2=smart.searchScrip("NFO",f"NIFTY{exp.strftime('%d%b%y').upper()}{atm}PE")
                    time.sleep(1)
                    if not r2 or len(str(r2))<10:
                        r2=smart.searchScrip("NFO",f"{atm} PE {exp.strftime('%d%b%y')}")
                    p1=parse_search(r1);p2=parse_search(r2)
                    if p1: ce_tok=p1['symboltoken'];ce_trad=p1['tradingsymbol'];d["ce_sym"]=ce_trad
                    if p2: pe_tok=p2['symboltoken'];pe_trad=p2['tradingsymbol'];d["pe_sym"]=pe_trad
                    else:
                        # PE token = CE token + 1 trick for NIFTY
                        if ce_tok:
                            try:
                                pe_tok=str(int(ce_tok)+1)
                                pe_trad=ce_trad.replace('CE','PE')
                                d["pe_sym"]=pe_trad+f" (guess {pe_tok})"
                            except: pass
                    last_exp=exp;ce_done=False;pe_done=False
                except Exception as e:
                    d["action"]=f"SEARCH ERR {e}";save(d);time.sleep(30);continue
            ce_data,ce_int=get_candles(smart,ce_tok) if ce_tok else ([],"NO TOK")
            time.sleep(0.8)
            pe_data,pe_int=get_candles(smart,pe_tok) if pe_tok else ([],"NO TOK")
            ce_ob=find_ob(ce_data);pe_ob=find_ob(pe_data)
            d["log"]=f"CE {len(ce_data)} {ce_int} | PE {len(pe_data)} {pe_int} | REAL {QTY}"
            if ce_ob: d["ce_h"]=round(ce_ob["high"],2);d["ce_l"]=round(ce_ob["low"],2);d["ce_50"]=round(ce_ob["50"],2);d["ce_sl"]=round(ce_ob["low"],2)
            if pe_ob: d["pe_h"]=round(pe_ob["high"],2);d["pe_l"]=round(pe_ob["low"],2);d["pe_50"]=round(pe_ob["50"],2);d["pe_sl"]=round(pe_ob["low"],2)
            msgs=[]
            if ce_ob and not ce_done and len(ce_data)>2 and float(ce_data[-1][4])>ce_ob["high"]:
                try:
                    smart.placeOrder({"variety":"NORMAL","tradingsymbol":ce_trad,"symboltoken":ce_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":float(d["ce_50"]),"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                    msgs.append(f"CE BUY {d['ce_50']} PADLA");ce_done=True
                except Exception as e: msgs.append(f"CE {e}")
            if pe_ob and not pe_done and len(pe_data)>2 and float(pe_data[-1][4])>pe_ob["high"]:
                try:
                    smart.placeOrder({"variety":"NORMAL","tradingsymbol":pe_trad,"symboltoken":pe_tok,"transactiontype":"BUY","exchange":"NFO","ordertype":"LIMIT","price":float(d["pe_50"]),"producttype":"INTRADAY","duration":"DAY","quantity":QTY})
                    msgs.append(f"PE BUY {d['pe_50']} PADLA");pe_done=True
                except Exception as e: msgs.append(f"PE {e}")
            if not msgs:
                c_msg=f"CE {d['ce_l']}-{d['ce_h']}" if ce_ob else f"CE {ce_int}"
                p_msg=f"PE {d['pe_l']}-{d['pe_h']}" if pe_ob else f"PE {pe_int} TOK:{pe_tok}"
                msgs.append(f"{c_msg} | {p_msg}")
            d["action"]=" | ".join(msgs)
            save(d);time.sleep(60)
        except Exception as e:
            d=load();d["action"]=f"ERR {e}";save(d);time.sleep(30)
threading.Thread(target=run,daemon=True).start()
@app.route('/')
def home():
    d=load()
    return f"<html><head><meta http-equiv='refresh' content='10'><meta name='viewport' content='width=device-width'><style>body{{background:#111;color:#fff;font-family:Arial;padding:10px}}.g{{color:#0f0;font-size:20px}}.y{{color:#ffeb3b;font-size:13px}}.b{{border:1px solid #444;padding:8px;border-radius:8px;margin:6px 0;background:#1a1a1a}}</style></head><body><h2 class=g>NIFTY {d['nifty']} ATM {d['atm']}</h2><div class=b>CE {d['ce_sym']}<br>BOX {d['ce_l']}-{d['ce_h']} 50% {d['ce_50']} SL {d['ce_sl']}</div><div class=b>PE {d['pe_sym']}<br>BOX {d['pe_l']}-{d['pe_h']} 50% {d['pe_50']} SL {d['pe_sl']}</div><div class=b>{d['exp']} | {d['log']}</div><h3 class=y>{d['action']}</h3><p>{d['time_str']} | 65 REAL</p></body></html>"
if __name__=='__main__':
    app.run(host='0.0.0.0',port=10000)
